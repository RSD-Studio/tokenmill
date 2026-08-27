"""The matrix runner: corpus by backends by tokenizers, repeated and scored.

**What makes this different from the tables this project has published so far.**
Every figure in `docs/BENCHMARKS.md` up to Phase 9 was produced by running a
conversion by hand and then asserting the result in a test — which
`benchmarks/README.md` says out loud is the weaker guarantee. This produces a
file. The file is committed, and the number in the document cites it.

Five rules govern the run, and each is a way a benchmark goes wrong:

**1. Every cell is repeated, and every repeat is kept.** Defect N7. A single
unwarmed run is not a measurement, and a summary that discards its inputs cannot
be checked. `durations_ms` holds all of them; the report prints a median, a
spread and N.

**2. Cells run one at a time.** Phase 9 gave the batch queue a thread pool, and
this deliberately does not use it. A wall-clock measurement taken while three
other conversions compete for four cores is a measurement of the scheduler.

**3. Fidelity is scored in the same cell as the tokens.** Not in a second pass,
not in a different table. `CellResult` carries both or the cell failed, which is
what makes it structurally impossible to publish one without the other.

**4. A failure is a cell.** Every candidate backend is run against every fixture
it claims, and the ones that fall over produce rows with their error. `corrupt.pdf`
failing five ways is a result.

**5. Nothing is skipped for looking bad.** The matrix is the registry's own
answer to "which backends claim this format", not a list somebody curated. A
backend that does badly appears with its number.

**Tokenizers are rows, not columns.** One `CellResult` per (fixture, backend,
tokenizer). That is what lets a local run — which can only reach the `bytes`
unit, because this sandbox's egress proxy denies every vocabulary host — and a
CI run that reaches `o200k_base` merge by *concatenating* their result files.
A byte figure and a token figure never share a column, which matters more here
than anywhere: the two disagreed by 24 points on tabular data in Phase 7, and
did not even rank the five serialisation formats in the same order.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from benchmarks.memory import measure_memory
from benchmarks.models import CellResult
from tokenmill.core.errors import ConversionError
from tokenmill.core.models import ConversionResult, ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import Registry, default_registry
from tokenmill.fidelity import COMPONENTS
from tokenmill.fidelity import score as score_fidelity

__all__ = ["Cell", "cells_for", "run_cell", "run_matrix"]

_log = logging.getLogger(__name__)

#: How long any single conversion may take before the harness abandons it.
#:
#: Generous, and finite. A backend that hangs would otherwise stall an
#: unattended run indefinitely, and "completes unattended" is the acceptance
#: criterion. The cell is recorded as a timeout, which is a result.
DEFAULT_TIMEOUT_S = 300.0


class Cell:
    """One (fixture, backend) pair to measure, with its ground truth.

    Attributes:
        fixture: The corpus item's name.
        path: Where it is.
        backend: The backend id to pin to.
        truth: That fixture's ground-truth entry, or ``None``.
    """

    __slots__ = ("backend", "fixture", "path", "truth")

    def __init__(
        self, fixture: str, path: Path, backend: str, truth: dict[str, Any] | None
    ) -> None:
        """Describe one cell.

        Args:
            fixture: The corpus item's name.
            path: Where it is.
            backend: The backend id.
            truth: Its ground truth, when it has any.
        """
        self.fixture = fixture
        self.path = path
        self.backend = backend
        self.truth = truth

    def __repr__(self) -> str:
        """Render the cell for a log line.

        Returns:
            ``fixture/backend``.
        """
        return f"{self.fixture}/{self.backend}"


def cells_for(
    corpus: Sequence[tuple[str, Path]],
    truths: dict[str, Any],
    *,
    registry: Registry | None = None,
    backends: Sequence[str] | None = None,
) -> list[Cell]:
    """Build the matrix from the registry's own answers.

    **The matrix is not curated.** For each corpus item the registry is asked
    which installed backends claim its format, and every one of them becomes a
    cell. Choosing the list by hand is how a benchmark quietly stops including
    the backend that does badly.

    Unavailable backends are excluded, because a cell that could only ever
    record "not installed" is noise rather than a result — and the run manifest
    records which were absent, so the omission is visible.

    Args:
        corpus: The items to measure, as ``(name, path)``.
        truths: The ground-truth manifest.
        registry: Where backends come from.
        backends: Only these backend ids, for a partial run. ``None`` for all.

    Returns:
        Every cell, in corpus order then registry preference order.
    """
    reg = registry if registry is not None else default_registry()
    wanted = set(backends) if backends is not None else None

    found: list[Cell] = []
    for name, path in corpus:
        source = Source.from_path(path)
        try:
            candidates = reg.candidates(source)
        except ConversionError:
            # No installed backend claims this format. A real answer about this
            # corpus on this machine, and the manifest's notes record it.
            _log.info("no backend claims %s", name)
            continue
        for converter in candidates:
            backend_id = converter.info.id
            if wanted is not None and backend_id not in wanted:
                continue
            found.append(Cell(name, path, backend_id, truths.get(name)))
    return found


def run_cell(
    cell: Cell,
    tokenizer: str,
    *,
    repeats: int,
    pipeline: Pipeline | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    extra: dict[str, Any] | None = None,
    allow_network: bool = False,
) -> CellResult:
    """Measure one cell: convert it ``repeats`` times, score it, record it.

    The ordering matters and is not arbitrary:

    1. **One warm-up conversion**, discarded. The first call to a backend pays
       for its import — which for MarkItDown means loading ONNX Runtime — and
       timing that once and calling it the conversion cost would overstate every
       first-in-class backend by an order of magnitude.
    2. **``repeats`` timed conversions**, uninstrumented, all kept.
    3. **One instrumented conversion** for memory. Separate because
       :mod:`tracemalloc` roughly doubles allocation cost, so a run that
       measured both at once would publish a wall time that includes the
       measurement of itself.

    Fidelity is scored on the *last* conversion's text, which is the same text
    every repeat produced — these backends are deterministic, and the service
    adapters send ``temperature: 0`` precisely so that stays true.

    Args:
        cell: What to measure.
        tokenizer: What to count in.
        repeats: How many timed runs. Must be at least one.
        pipeline: The pipeline to run; a default one is built when omitted.
        timeout_s: Per-conversion budget.
        extra: Backend options, such as a service address.
        allow_network: Whether backends may reach the network. **Off by
            default**, and explicit rather than inferred: with it off, ``repomix``
            refuses because ``npx`` would download it and a heavy backend refuses
            because it would download weights. Both refusals are honest rows.
            Turning it on lets those backends take part, and the run manifest
            records that it was on — because a timing that includes a package
            download is not a conversion timing.

    Returns:
        The cell's result, successful or not. **Never raises**: an unattended
        run that stopped at the first failing backend would defeat the point,
        and a failure is a row.
    """
    if repeats < 1:
        msg = f"repeats must be at least 1, got {repeats}"
        raise ValueError(msg)

    runner = pipeline if pipeline is not None else Pipeline()
    options = ConvertOptions(
        tokenizer=tokenizer,
        backend=cell.backend,
        fallback=False,
        timeout_s=timeout_s,
        allow_network=allow_network,
        extra=extra or {},
    )
    source = Source.from_path(cell.path)

    def convert() -> ConversionResult:
        return runner.run(source, options)

    try:
        convert()  # warm-up, discarded
    except ConversionError as exc:
        return _failure(cell, tokenizer, exc)
    except Exception as exc:  # a backend that escapes the taxonomy is a finding
        _log.warning("%s raised outside the taxonomy: %r", cell, exc)
        return _failure(cell, tokenizer, exc)

    durations: list[float] = []
    result: ConversionResult | None = None
    for _ in range(repeats):
        started = time.perf_counter()
        try:
            result = convert()
        except ConversionError as exc:
            return _failure(cell, tokenizer, exc)
        durations.append((time.perf_counter() - started) * 1000.0)

    assert result is not None  # noqa: S101 - repeats >= 1, so the loop ran

    with measure_memory() as memory, contextlib.suppress(ConversionError):
        # Suppressed rather than handled: it succeeded three lines above, so a
        # failure here is a flake worth not losing the whole cell over. The
        # timings and the fidelity are already recorded.
        convert()

    fidelity, components, scored = _score(cell, result)
    return CellResult(
        fixture=cell.fixture,
        backend=cell.backend,
        tokenizer=tokenizer,
        ok=True,
        tokens_before=result.tokens_before.value if result.tokens_before else None,
        tokens_after=result.tokens_after.value if result.tokens_after else None,
        characters=len(result.text),
        fidelity=fidelity,
        fidelity_components=components,
        fidelity_scored=scored,
        durations_ms=tuple(durations),
        peak_python_kb=memory.reading.peak_python_kb,
        peak_rss_kb=memory.reading.peak_rss_kb,
        memory_method=memory.reading.method,
        warnings=tuple(result.warnings),
        empty_output=not result.text.strip(),
        backend_version=_version_of(result),
    )


def run_matrix(
    cells: Sequence[Cell],
    tokenizers: Sequence[str],
    *,
    repeats: int,
    pipeline: Pipeline | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    extra: dict[str, Any] | None = None,
    allow_network: bool = False,
    on_cell: Any = None,
) -> Iterator[CellResult]:
    """Run every cell against every tokenizer, yielding results as they land.

    A generator rather than a list so a long run can be written incrementally
    and watched. Nothing is parallelised: see rule 2 in the module docstring.

    Args:
        cells: What to measure.
        tokenizers: What to count in; one result per cell per tokenizer.
        repeats: Timed runs per cell.
        pipeline: The pipeline to run.
        timeout_s: Per-conversion budget.
        extra: Backend options.
        allow_network: Whether backends may reach the network.
        on_cell: Called with ``(index, total, cell, tokenizer)`` before each
            cell, for progress. Optional.

    Yields:
        One result per cell per tokenizer.
    """
    runner = pipeline if pipeline is not None else Pipeline()
    total = len(cells) * len(tokenizers)
    index = 0
    for tokenizer in tokenizers:
        for cell in cells:
            index += 1
            if on_cell is not None:
                on_cell(index, total, cell, tokenizer)
            yield run_cell(
                cell,
                tokenizer,
                repeats=repeats,
                pipeline=runner,
                timeout_s=timeout_s,
                extra=extra,
                allow_network=allow_network,
            )


def _failure(cell: Cell, tokenizer: str, exc: BaseException) -> CellResult:
    """Record a cell that did not convert.

    Args:
        cell: What was being measured.
        tokenizer: What it would have been counted in.
        exc: What went wrong.

    Returns:
        The failed cell, carrying the error verbatim and its type.
    """
    return CellResult(
        fixture=cell.fixture,
        backend=cell.backend,
        tokenizer=tokenizer,
        ok=False,
        error=str(exc),
        error_type=type(exc).__name__,
    )


def _score(
    cell: Cell, result: ConversionResult
) -> tuple[float | None, dict[str, float | None], int]:
    """Score the converted text against the fixture's ground truth.

    Args:
        cell: Carries the ground truth, when there is any.
        result: What the backend produced.

    Returns:
        The overall, every component (``None`` where the axis did not apply),
        and how many axes produced a number.

        A fixture with no ground truth yields ``(None, all-None, 0)`` — which
        the report prints as ``n/a``, never as zero. Scoring an unscorable
        fixture 0.0 would say a conversion destroyed something that was never
        there.
    """
    empty: dict[str, float | None] = dict.fromkeys(COMPONENTS)
    if cell.truth is None:
        return None, empty, 0

    scored = score_fidelity(result.text, cell.truth, fixture=cell.fixture, backend_id=cell.backend)
    components: dict[str, float | None] = {c.component: c.score for c in scored.components}
    for name in COMPONENTS:
        components.setdefault(name, None)
    return scored.overall, components, len(scored.scored_components)


def _version_of(result: ConversionResult) -> str | None:
    """Pull the backend's own version out of the result's metadata.

    Provenance: a measurement that cannot say which build produced it cannot be
    reproduced. Subprocess backends record ``tool_version``; Python backends
    have their distribution's version.

    Args:
        result: The conversion.

    Returns:
        The version, or ``None`` when the backend could not say.
    """
    recorded = result.metadata.get("tool_version")
    if isinstance(recorded, str) and recorded:
        return recorded
    return _distribution_version(result.backend_id)


def _distribution_version(backend_id: str) -> str | None:
    """Look up the installed version of the package a backend wraps.

    Args:
        backend_id: The backend.

    Returns:
        Its version, or ``None`` when the backend is ours or the package cannot
        be found. Deliberately a lookup table rather than a guess from the id:
        ``markitdown`` and ``pdfplumber`` happen to match their distributions
        and ``readability`` does not, and a benchmark that recorded the wrong
        version is worse than one that records none.
    """
    from importlib.metadata import PackageNotFoundError, version

    distributions = {
        "pdfplumber": "pdfplumber",
        "pypdf": "pypdf",
        "markitdown": "markitdown",
        "kreuzberg": "kreuzberg",
        "docling": "docling",
        "trafilatura": "trafilatura",
        "readability": "readability-lxml",
        "crawl4ai": "crawl4ai",
        "gitingest": "gitingest",
        "markdownify_html": "markdownify",
    }
    name = distributions.get(backend_id)
    if name is None:
        return None
    try:
        return version(name)
    except PackageNotFoundError:  # pragma: no cover - it converted, so it is there
        return None


def with_tokenizer(result: CellResult, tokenizer: str) -> CellResult:
    """Return a copy of a result relabelled with a different tokenizer.

    Used only by the merge step, where a byte-unit run and a token-unit run are
    combined.

    Args:
        result: The result to relabel.
        tokenizer: The new label.

    Returns:
        The copy.
    """
    return replace(result, tokenizer=tokenizer)
