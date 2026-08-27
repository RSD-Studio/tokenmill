"""The batch queue, and how many conversions it runs at once.

**Phase 8 ran one at a time, and defect D2 was why.** `Pipeline.run` could not
safely go on a thread pool: several adapters reach for process-global state —
the warnings filter list, the stdlib root logger's handlers, `os.environ`,
loguru's activation registry — and none of it survives two threads interleaving
their save and restore. `docs/ARCHITECTURE.md` and
`tokenmill.core.globalstate` carry the worked example. Batch throughput was
bounded by a defect rather than by the work, and the acceptance criterion — a
responsive interface, not a fast one — hid that.

**Phase 9 fixed D2 and this became a thread pool.** Every block that touches
global state now runs under one process-wide reentrant lock, and, more
importantly, those blocks were narrowed first: for the document and web
adapters they cover an *import*, which after the first conversion is a
`sys.modules` lookup. So the lock costs microseconds for most backends and the
pool is real.

Two backends still serialise against themselves, and that is stated here rather
than left in a benchmark footnote:

* **docling** — its deprecation filter has to be active while the document is
  converted, not merely while the module is imported.
* **gitingest** — pathspec warns while it builds ignore rules, loguru's registry
  must stay set while it logs, and `GITHUB_TOKEN` is read at the top of the
  call.

Everything else — pdfplumber, pypdf, plaintext, trafilatura, readability,
markdownify_html, markitdown, kreuzberg, pandoc, LibreOffice, PyMuPDF4LLM,
repomix, code2prompt — runs fully in parallel.

**Whether the pool helps depends entirely on the backend, and the difference is
large.** Measured on this container (4 cores), 12 files, median of 5 runs,
2026-08-27:

| Batch | Serial | 4 workers | Speedup |
|---|---|---|---|
| In-process (pdfplumber, markitdown, trafilatura — auto-selected) | 1.13 s | 1.25 s | **0.91x** |
| `pymupdf4llm` (a separate Python interpreter per conversion) | 14.59 s | 9.50 s | **1.54x** |
| `pandoc` + `libreoffice` (real external programs) | 11.89 s | 3.82 s | **3.12x** |

The GIL explains both ends. An in-process backend parsing a PDF holds it, so
threads add contention and overlap nothing — parallelism *costs* 9%. A
subprocess backend spends its time in `wait()` with the GIL released, so four
really do run at once.

**The default is 4 anyway, and that is a judgement rather than a measurement.**
It costs 9% of 1.13 s on the cheapest workload and saves 8 seconds on the
expensive one. Nobody notices the first; everybody notices the second.
`BatchRunner(..., workers=1)` restores the Phase 8 behaviour exactly, for anyone
converting only with in-process backends who would rather have the 9%.

Capped at 4 rather than set to the core count: several backends spawn their own
children and one of them is LibreOffice, so a pool as wide as the machine
multiplies processes instead of parallelising work.

**Why not a process pool**, which would sidestep the shared interpreter
entirely: `ConversionResult` carries the whole converted text across a pickle
boundary, so a batch of large documents copies every byte twice; and several
backends already spawn children, so a pool of conversions each starting
`soffice` multiplies processes. Measured start-up is not the objection — that is
0.133 s — and `docs/ARCHITECTURE.md` records the reasoning.

**Ordering is by index, not by completion.** `items` is always in the order the
caller supplied, whatever order the pool finishes in, because a list that
reorders itself while a user watches is worse than a slower one.

**Cancellation is cooperative and honest about it.** A conversion already handed
to a backend cannot be interrupted — a subprocess has its own timeout and an
in-process C library has nothing to interrupt — so cancelling marks every
*queued* item cancelled and lets running ones finish. The UI says that rather
than pretending the button stops work instantly.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from tokenmill.core.pipeline import Pipeline
from tokenmill.gui.api import ConversionRequest, ConversionSummary, convert

__all__ = ["BatchItem", "BatchRunner", "BatchTotals", "ItemState", "requests_for"]

_log = logging.getLogger(__name__)


class ItemState(StrEnum):
    """Where one batch item has got to."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class BatchItem:
    """One entry in the queue.

    Frozen, and replaced rather than mutated as it progresses, so a UI thread
    reading an item can never see one half-updated.

    Attributes:
        index: Position in the batch, stable across re-orderings.
        name: What is being converted, for display.
        state: Where it has got to.
        summary: The result, once there is one.
    """

    index: int
    name: str
    state: ItemState = ItemState.QUEUED
    summary: ConversionSummary | None = None


@dataclass(frozen=True, slots=True)
class BatchTotals:
    """The aggregate row under a batch.

    Attributes:
        total: How many items there are.
        done: How many succeeded.
        failed: How many failed.
        cancelled: How many were cancelled before they ran.
        tokens_before: Summed input cost, over the **comparable** items only —
            those that have both a before and an after count.
        tokens_after: Summed output cost of those same comparable items.
        tokens_produced: Summed output cost of **every** item, comparable or
            not. This is what the batch actually costs to send to a model, and
            it is a different number from :attr:`tokens_after`.
        comparable: How many items had a before-count to compare against.
        duration_ms: Summed wall-clock time.
        tokenizer_id: What the counts are in, or ``None`` when items disagree.
    """

    total: int = 0
    done: int = 0
    failed: int = 0
    cancelled: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_produced: int = 0
    comparable: int = 0
    duration_ms: int = 0
    tokenizer_id: str | None = None

    @property
    def finished(self) -> int:
        """How many items have reached a terminal state.

        Returns:
            The count.
        """
        return self.done + self.failed + self.cancelled

    @property
    def reduction_ratio(self) -> float | None:
        """The batch's overall saving, over the comparable items only.

        Computed from summed counts rather than by averaging the per-item
        ratios, which would weight a 100-byte file the same as a 100 KB one and
        produce a number that is the saving on nothing.

        **Only items with both counts are in it**, and that took a real bug to
        get right. A binary document has no comparable before-count — Phase 2
        settled that, and `docs/ARCHITECTURE.md` records why: the "before" for a
        PDF would be a file size, not a token count of anything a model would
        read. Summing ``after`` over every item while summing ``before`` over
        only the ones that had one produced a batch of the fixture corpus
        reporting **-16.7%**, a 20-file batch that appeared to have *grown* the
        document. It had not; the denominator was missing four PDFs and three
        Office files that the numerator included.

        Returns:
            The ratio over comparable items, or ``None`` when there are none —
            which is every batch of binary documents, and is not zero.
        """
        if self.comparable == 0 or self.tokens_before <= 0:
            return None
        return (self.tokens_before - self.tokens_after) / self.tokens_before


#: How long :meth:`BatchRunner.wait` polls between checks.
_POLL_S: Final = 0.02

#: The most conversions to run at once when the caller does not say.
#:
#: Capped rather than set to the core count: several backends spawn their own
#: child processes and one of them is LibreOffice, so a pool as wide as the
#: machine multiplies processes instead of parallelising work. Four overlaps the
#: subprocess and I/O waits that dominate this workload without doing that.
_DEFAULT_WORKERS: Final = 4


class BatchRunner:
    """Runs a batch on a pool of background threads, leaving the caller free.

    Thread-safety here is about the runner's *own* state — the item list and the
    cancel flag — which is guarded by one lock. The conversions are safe to
    overlap because of `tokenmill.core.globalstate`; see the module docstring
    for the two backends that still serialise against themselves.

    Attributes:
        on_change: Called after every state transition, with the runner. Used by
            the UI to refresh; called on a worker thread, so a UI toolkit that
            needs its own thread must marshal.
        workers: How many conversions run at once.
    """

    def __init__(
        self,
        requests: Sequence[ConversionRequest],
        *,
        pipeline: Pipeline | None = None,
        on_change: Callable[[BatchRunner], None] | None = None,
        workers: int | None = None,
    ) -> None:
        """Prepare a batch without starting it.

        Args:
            requests: What to convert, in order.
            pipeline: The pipeline to run; one is built on the worker thread
                when omitted, so that entry-point scanning is not paid on the
                caller's thread either.
            on_change: Called after each state transition.
            workers: How many conversions to run at once. Defaults to
                ``min(4, cpu_count)``; ``1`` restores the Phase 8 behaviour,
                which is what the benchmark in ``docs/BENCHMARKS.md`` compares
                against.

        Raises:
            ValueError: If ``workers`` is less than one. A pool of zero would
                accept the batch and never run it.
        """
        if workers is not None and workers < 1:
            msg = f"workers must be at least 1, got {workers}"
            raise ValueError(msg)
        self._requests = list(requests)
        self._pipeline = pipeline
        self.on_change = on_change
        self.workers = (
            workers if workers is not None else min(_DEFAULT_WORKERS, os.cpu_count() or 1)
        )
        self._lock = threading.Lock()
        self._items: list[BatchItem] = [
            BatchItem(index=i, name=r.source.name) for i, r in enumerate(self._requests)
        ]
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._finished = threading.Event()
        if not self._requests:
            # An empty batch is finished the moment it is created. Without this
            # `wait()` on one would block forever, which is a real case: a user
            # dropping a folder of unsupported files.
            self._finished.set()

    # -------------------------------------------------------------- inspection

    @property
    def items(self) -> tuple[BatchItem, ...]:
        """A snapshot of every item's current state.

        Returns:
            The items, safe to read from another thread.
        """
        with self._lock:
            return tuple(self._items)

    @property
    def totals(self) -> BatchTotals:
        """The aggregate row, recomputed from the current item states.

        Returns:
            The totals.
        """
        items = self.items
        done = failed = cancelled = 0
        before = after = produced = comparable = duration = 0
        tokenizers: set[str] = set()
        for item in items:
            if item.state is ItemState.DONE:
                done += 1
            elif item.state is ItemState.FAILED:
                failed += 1
            elif item.state is ItemState.CANCELLED:
                cancelled += 1
            summary = item.summary
            if summary is None:
                continue
            duration += summary.duration_ms
            if summary.tokens_after is not None:
                produced += summary.tokens_after
            # Both counts, or neither: see BatchTotals.reduction_ratio.
            if summary.tokens_before is not None and summary.tokens_after is not None:
                before += summary.tokens_before
                after += summary.tokens_after
                comparable += 1
            if summary.tokenizer_id is not None:
                tokenizers.add(summary.tokenizer_id)
        return BatchTotals(
            total=len(items),
            done=done,
            failed=failed,
            cancelled=cancelled,
            tokens_before=before,
            tokens_after=after,
            tokens_produced=produced,
            comparable=comparable,
            duration_ms=duration,
            # None when the items disagree: summing o200k_base tokens and bytes
            # into one number would be a category error, and TokenCount exists
            # precisely so that a bare int cannot happen elsewhere.
            tokenizer_id=next(iter(tokenizers)) if len(tokenizers) == 1 else None,
        )

    @property
    def running(self) -> bool:
        """Whether the worker is still going.

        Returns:
            True until every item has reached a terminal state.
        """
        return not self._finished.is_set()

    @property
    def cancelled(self) -> bool:
        """Whether cancellation has been requested.

        Returns:
            True after :meth:`cancel`.
        """
        return self._cancel.is_set()

    # ----------------------------------------------------------------- control

    def start(self) -> None:
        """Begin converting, on a thread of its own.

        Returns immediately. Calling it twice is a no-op rather than an error,
        because a double-clicked button should not raise.
        """
        if self._thread is not None or not self._requests:
            return
        self._thread = threading.Thread(
            target=self._run, name="tokenmill-batch-supervisor", daemon=True
        )
        self._thread.start()

    def cancel(self) -> None:
        """Stop after the current item.

        **Queued items are cancelled; the running one is allowed to finish.** A
        conversion already inside a backend cannot be interrupted — a subprocess
        has its own timeout and an in-process C library has nothing to interrupt
        — and a button that claimed otherwise would be lying.
        """
        self._cancel.set()

    def wait(self, timeout_s: float | None = None) -> bool:
        """Block until the batch finishes. For tests and headless use.

        Args:
            timeout_s: How long to wait, or ``None`` for indefinitely.

        Returns:
            True when the batch finished, False on timeout.
        """
        return self._finished.wait(timeout_s)

    def run_to_completion(self, timeout_s: float | None = None) -> BatchTotals:
        """Start the batch and wait for it. For the CLI and for tests.

        Args:
            timeout_s: How long to wait.

        Returns:
            The totals.
        """
        self.start()
        self.wait(timeout_s)
        return self.totals

    # ------------------------------------------------------------------ worker

    def _run(self) -> None:
        """Convert every queued item, on a pool of worker threads."""
        pipeline = self._pipeline if self._pipeline is not None else Pipeline()
        try:
            if self.workers == 1:
                for index in range(len(self._requests)):
                    self._run_one(index, pipeline)
                return
            with ThreadPoolExecutor(
                max_workers=self.workers, thread_name_prefix="tokenmill-batch"
            ) as pool:
                # `map` rather than submitting and gathering: nothing here reads
                # a return value — every result is written into the item list as
                # it lands — and `map` propagates an exception from a worker
                # into this thread, where the `finally` below still releases
                # anything waiting.
                list(pool.map(lambda i: self._run_one(i, pipeline), range(len(self._requests))))
        finally:
            # In a finally block so that an unexpected error still releases
            # anything waiting on this batch. A UI that hung because the worker
            # died would be worse than one that showed a failed item.
            self._finished.set()
            self._notify()

    def _run_one(self, index: int, pipeline: Pipeline) -> None:
        """Convert one item, unless the batch has been cancelled.

        Args:
            index: Which item.
            pipeline: The pipeline to run it through. Shared across the pool:
                it holds registries, which are read-only after discovery, and
                building one per worker would pay for entry-point scanning
                once per thread.
        """
        if self._cancel.is_set():
            self._set(index, state=ItemState.CANCELLED)
            return
        self._set(index, state=ItemState.RUNNING)
        summary = convert(self._requests[index], pipeline=pipeline)
        self._set(
            index,
            state=ItemState.DONE if summary.ok else ItemState.FAILED,
            summary=summary,
        )

    def _set(
        self,
        index: int,
        *,
        state: ItemState,
        summary: ConversionSummary | None = None,
    ) -> None:
        """Replace one item's state and tell the listener.

        Args:
            index: Which item.
            state: Its new state.
            summary: Its result, when there is one.
        """
        with self._lock:
            item = self._items[index]
            self._items[index] = replace(
                item, state=state, summary=summary if summary is not None else item.summary
            )
        self._notify()

    def _notify(self) -> None:
        """Call the change listener, never letting it break the batch."""
        if self.on_change is None:
            return
        try:
            self.on_change(self)
        except Exception:  # a UI callback must not kill the conversion loop
            _log.debug("batch listener raised", exc_info=True)


def requests_for(
    paths: Iterable[str],
    template: ConversionRequest,
) -> tuple[ConversionRequest, ...]:
    """Build one request per path from a template.

    Args:
        paths: The files to convert.
        template: The options every item shares; its ``source`` is replaced.

    Returns:
        One request per path, in the order given.
    """
    from tokenmill.core.models import Source

    return tuple(replace(template, source=Source.from_path(path)) for path in paths)
