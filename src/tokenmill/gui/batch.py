"""The batch queue, and why it does not use a thread pool.

**This is where defect D2 comes due.** `docs/REVIEW_PHASES_0_6.md` §4 counts the
process-global state a conversion touches, and none of it is thread-safe:

```
src/tokenmill/backends/_common.py                    warnings.catch_warnings
src/tokenmill/backends/documents/docling_adapter.py  warnings.catch_warnings
src/tokenmill/backends/repo/gitingest_repo.py        warnings.catch_warnings
src/tokenmill/post/compress.py                       warnings.catch_warnings
src/tokenmill/backends/repo/gitingest_repo.py        os.environ, the stdlib root
                                                     logger's handlers and level,
                                                     loguru's activation registry
```

`warnings.catch_warnings` saves and restores a **module-global** filter list. Two
threads entering it at once interleave their save and restore, and the loser
leaves the process with the other's filters — which under this project's
`filterwarnings = ["error"]` means a warning that should have been forwarded as a
`ConversionWarning` becomes a raised exception in an unrelated conversion, or
the reverse. The gitingest adapter is worse: it reconfigures the *root logger's
handlers and level* and restores them afterwards.

So `Pipeline.run` cannot go on a thread pool, and the handover says so directly.

**What this does instead: one worker thread, conversions serialised.**

The acceptance criterion is "a 20-file batch runs with a responsive UI and
correct aggregate totals" — which asks for the UI not to block, not for
parallelism. A single worker gives exactly that: the work is off the event loop,
so the interface stays live, and only one conversion touches the global state at
a time, so it stays correct.

**Why not a process pool**, which would be both safe and parallel: it is the
right answer eventually and the wrong one now.

* `ConversionResult` would have to cross a pickle boundary, and it carries the
  whole converted text. A 20-file batch of large documents copies every byte
  twice for no benefit the user can see.
* It would put a *sixth* kind of process-global concern — child process
  lifecycle — into a project whose review is already tracking that count as a
  defect, and the handover asks to be told before the number moves.
* Several backends already spawn their own children. A process pool of
  conversions each starting `soffice` or a second Python interpreter multiplies
  processes rather than parallelising work.

**One argument that does *not* hold, recorded because it was the first one
reached for.** Worker start-up looked expensive and is not: `import tokenmill`
plus building the registry and scanning entry points measures **0.133 s**
(median of five, this container, 2026-08-26), not the several tenths guessed
at. Per-worker start-up is a real cost and a small one, and the case against a
process pool rests on the three reasons above rather than on that.

The honest position is that batch throughput is bounded by one conversion at a
time, that this is a consequence of D2 rather than a design preference, and that
fixing D2 properly — making the adapters stop reaching for global state — is
what unlocks parallelism. `PROGRESS.md` records it as deferred work with that
reasoning, and the cost is measured rather than asserted: see
`docs/BENCHMARKS.md`.

**Cancellation is cooperative and honest about it.** A conversion already handed
to a backend cannot be interrupted — a subprocess has its own timeout and an
in-process C library has nothing to interrupt — so cancelling marks every
*queued* item cancelled and lets the running one finish. The UI says that rather
than pretending the button stops work instantly.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Sequence
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


class BatchRunner:
    """Runs a batch on one background thread, leaving the caller's thread free.

    Thread-safety here is about the runner's *own* state — the item list and the
    cancel flag — which is guarded by one lock. The conversions themselves are
    serialised onto a single worker for the reason in the module docstring.

    Attributes:
        on_change: Called after every state transition, with the runner. Used by
            the UI to refresh; called on the worker thread, so a UI toolkit that
            needs its own thread must marshal.
    """

    def __init__(
        self,
        requests: Sequence[ConversionRequest],
        *,
        pipeline: Pipeline | None = None,
        on_change: Callable[[BatchRunner], None] | None = None,
    ) -> None:
        """Prepare a batch without starting it.

        Args:
            requests: What to convert, in order.
            pipeline: The pipeline to run; one is built on the worker thread
                when omitted, so that entry-point scanning is not paid on the
                caller's thread either.
            on_change: Called after each state transition.
        """
        self._requests = list(requests)
        self._pipeline = pipeline
        self.on_change = on_change
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
        self._thread = threading.Thread(target=self._run, name="tokenmill-batch", daemon=True)
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
        """Convert every queued item in order, on the worker thread."""
        pipeline = self._pipeline if self._pipeline is not None else Pipeline()
        try:
            for index, request in enumerate(self._requests):
                if self._cancel.is_set():
                    self._set(index, state=ItemState.CANCELLED)
                    continue
                self._set(index, state=ItemState.RUNNING)
                summary = convert(request, pipeline=pipeline)
                self._set(
                    index,
                    state=ItemState.DONE if summary.ok else ItemState.FAILED,
                    summary=summary,
                )
        finally:
            # In a finally block so that an unexpected error still releases
            # anything waiting on this batch. A UI that hung because the worker
            # died would be worse than one that showed a failed item.
            self._finished.set()
            self._notify()

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
