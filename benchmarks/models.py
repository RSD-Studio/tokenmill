"""What one benchmark cell records, and why each field is shaped as it is.

`benchmarks/README.md` set the rule this package exists to satisfy, in Phase 0,
and the project has been unable to honour it for ten phases:

> every number published in `docs/BENCHMARKS.md` or the README must trace back
> to a committed raw result file here.

Every figure in this project so far has instead been "asserted by a test", which
that page says out loud is the weaker guarantee. A `CellResult` is what makes
the stronger one possible: one row per (fixture, backend, tokenizer), written to
disk, committed, and cited.

Four decisions in this module are worth stating, because each is a way the
benchmark could have been quietly wrong.

**A timing is never one run.** Defect N7: every timing this project has
published is a single unrepeated, unwarmed measurement, which is not a
measurement of anything. `durations_ms` holds *every* repeat, and the report
prints a median with a spread and the value of N. Keeping the raw repeats rather
than only their summary means somebody can recompute the summary, or notice that
one run of five took ten times as long — which is exactly the shape of an
outlier a median hides.

**Fidelity is not optional.** A `CellResult` that succeeded carries `fidelity`
and `fidelity_components`, and the report will not emit a token column without
the fidelity column beside it. `None` is permitted and means *this fixture has
no ground truth for this*, which is a different statement from zero and is
printed as `n/a`.

**A failure is a row, not an omission.** `ok=False` cells carry the error, its
type, and the backend that produced it. `corrupt.pdf` failing five ways is a
result; a benchmark that reported only the cells that worked would be a
marketing document, and `docs/DEVELOPMENT_PLAN.md`'s risk register names that
by name.

**Memory is reported with its method attached.** There is no portable,
honest "peak memory" for a process that spawns children, so the record carries
both what was measured and how, and the report says which. A single confident
number here would be the most quietly wrong thing in the file.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = ["CellResult", "RunManifest"]


@dataclass(frozen=True, slots=True)
class CellResult:
    """One (fixture, backend, tokenizer) cell of the matrix.

    Attributes:
        fixture: The corpus item's name.
        backend: The backend id that converted it.
        tokenizer: What the counts are in. A separate row per tokenizer rather
            than a column, so a run that could only reach the ``bytes`` unit and
            a run that reached ``o200k_base`` merge by concatenation.
        ok: Whether the conversion succeeded.
        error: What went wrong, verbatim.
        error_type: Its class name, so failures can be grouped without parsing
            prose.
        tokens_before: The input's cost, where the input is text a model could
            have been given. ``None`` for a binary document — Phase 2 settled
            that and `docs/ARCHITECTURE.md` records why.
        tokens_after: The output's cost.
        characters: The output's length, which is exact whether or not a
            tokenizer loaded.
        fidelity: The overall score, or ``None`` when the fixture has no ground
            truth. Never inferred.
        fidelity_components: Each named axis, ``None`` where it did not apply.
        fidelity_scored: How many axes produced a number. Carried because an
            overall built from two components is not comparable with one built
            from five, and a reader who cannot see which is which will compare
            them anyway.
        durations_ms: Every repeat's wall time, in order.
        peak_python_kb: Peak Python allocations during the last repeat, from
            :mod:`tracemalloc`. Exact for Python objects; blind to a C library's
            own allocations and to a child process.
        peak_rss_kb: Peak resident set of this process and its descendants
            during the last repeat, or ``None`` where that could not be
            sampled. See :attr:`memory_method`.
        baseline_rss_kb: The process tree's resident set just before the
            instrumented pass. ``peak_rss_kb`` on its own climbs across a matrix
            run because a Python process's resident set does not shrink, so the
            interesting figure is :attr:`added_rss_kb`, the difference.
        memory_method: How ``peak_rss_kb`` was obtained, so the number can be
            read correctly rather than trusted.
        warnings: What the conversion warned about — an empty document, a
            fallback, a missing binary. Kept because the warnings are often the
            result.
        empty_output: Whether the conversion produced nothing. A success that
            produced nothing is the single most misleading cell in a benchmark,
            so it gets its own flag rather than being inferred from a zero.
        backend_version: The version of the tool that produced this, where it
            is knowable. Provenance: a measurement that cannot say what produced
            it cannot be reproduced.
    """

    fixture: str
    backend: str
    tokenizer: str
    ok: bool
    error: str | None = None
    error_type: str | None = None
    tokens_before: int | None = None
    tokens_after: int | None = None
    characters: int | None = None
    fidelity: float | None = None
    fidelity_components: Mapping[str, float | None] = field(default_factory=dict)
    fidelity_scored: int = 0
    durations_ms: tuple[float, ...] = ()
    peak_python_kb: int | None = None
    peak_rss_kb: int | None = None
    baseline_rss_kb: int | None = None
    memory_method: str = "none"
    warnings: tuple[str, ...] = ()
    empty_output: bool = False
    backend_version: str | None = None

    @property
    def added_rss_kb(self) -> int | None:
        """Resident memory this cell added over what the process already held.

        Returns:
            ``peak_rss_kb - baseline_rss_kb``, or ``None`` when either is
            unknown. This — not the peak — is the figure to compare between
            backends, because the peak carries every import made by every cell
            that ran before it.
        """
        if self.peak_rss_kb is None or self.baseline_rss_kb is None:
            return None
        return max(0, self.peak_rss_kb - self.baseline_rss_kb)

    @property
    def n(self) -> int:
        """How many repeats produced a timing.

        Returns:
            The count. Published beside every timing, because a median of three
            and a median of thirty are different claims.
        """
        return len(self.durations_ms)

    @property
    def median_ms(self) -> float | None:
        """The middle timing.

        Returns:
            The median, or ``None`` when nothing was timed. A median rather than
            a mean: one repeat that hit a cold page cache should not move the
            headline, and the spread below is where it shows up instead.
        """
        return statistics.median(self.durations_ms) if self.durations_ms else None

    @property
    def min_ms(self) -> float | None:
        """The fastest repeat.

        Returns:
            The minimum, or ``None``.
        """
        return min(self.durations_ms) if self.durations_ms else None

    @property
    def max_ms(self) -> float | None:
        """The slowest repeat.

        Returns:
            The maximum, or ``None``.
        """
        return max(self.durations_ms) if self.durations_ms else None

    @property
    def spread_ratio(self) -> float | None:
        """How far apart the fastest and slowest repeats were.

        Returns:
            ``max / min``, or ``None`` when nothing was timed or the fastest was
            zero. A ratio rather than a standard deviation because these
            distributions are small-N and skewed, and "the slowest run took 4x
            the fastest" is a sentence a reader can act on where "sigma = 180
            ms" is not.
        """
        if not self.durations_ms:
            return None
        fastest = min(self.durations_ms)
        return max(self.durations_ms) / fastest if fastest > 0 else None

    @property
    def reduction(self) -> float | None:
        """The saving, where before and after are both real token counts.

        Returns:
            The fraction saved, or ``None`` when there is no comparable
            before-count — which is every binary document, and is not zero.
        """
        if self.tokens_before is None or self.tokens_after is None:
            return None
        if self.tokens_before <= 0:
            return None
        return (self.tokens_before - self.tokens_after) / self.tokens_before

    def to_row(self) -> dict[str, Any]:
        """Flatten this cell for CSV.

        One row per cell with every component as its own column, so the CSV can
        be loaded into anything without a parser for nested values.

        Returns:
            The row.
        """
        row: dict[str, Any] = {
            "fixture": self.fixture,
            "backend": self.backend,
            "tokenizer": self.tokenizer,
            "ok": self.ok,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "reduction": None if self.reduction is None else round(self.reduction, 4),
            "characters": self.characters,
            "fidelity": None if self.fidelity is None else round(self.fidelity, 4),
            "fidelity_scored": self.fidelity_scored,
            "n": self.n,
            "median_ms": None if self.median_ms is None else round(self.median_ms, 2),
            "min_ms": None if self.min_ms is None else round(self.min_ms, 2),
            "max_ms": None if self.max_ms is None else round(self.max_ms, 2),
            "spread_ratio": None if self.spread_ratio is None else round(self.spread_ratio, 2),
            "peak_python_kb": self.peak_python_kb,
            "peak_rss_kb": self.peak_rss_kb,
            "baseline_rss_kb": self.baseline_rss_kb,
            "added_rss_kb": self.added_rss_kb,
            "memory_method": self.memory_method,
            "empty_output": self.empty_output,
            "backend_version": self.backend_version,
            "error_type": self.error_type,
            "error": self.error,
            "warnings": " | ".join(self.warnings),
        }
        for name, value in self.fidelity_components.items():
            row[f"fidelity_{name}"] = None if value is None else round(value, 4)
        return row

    def to_json(self) -> dict[str, Any]:
        """Render this cell for the JSON result file.

        Unlike :meth:`to_row` this keeps **every repeat's timing**, because the
        raw measurements are what makes a published median checkable.

        Returns:
            The JSON-ready mapping.
        """
        return {
            "fixture": self.fixture,
            "backend": self.backend,
            "tokenizer": self.tokenizer,
            "ok": self.ok,
            "error": self.error,
            "error_type": self.error_type,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "reduction": self.reduction,
            "characters": self.characters,
            "fidelity": self.fidelity,
            "fidelity_components": dict(self.fidelity_components),
            "fidelity_scored": self.fidelity_scored,
            "durations_ms": list(self.durations_ms),
            "n": self.n,
            "median_ms": self.median_ms,
            "spread_ratio": self.spread_ratio,
            "peak_python_kb": self.peak_python_kb,
            "peak_rss_kb": self.peak_rss_kb,
            "baseline_rss_kb": self.baseline_rss_kb,
            "added_rss_kb": self.added_rss_kb,
            "memory_method": self.memory_method,
            "warnings": list(self.warnings),
            "empty_output": self.empty_output,
            "backend_version": self.backend_version,
        }


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Everything needed to say what a result file is a measurement *of*.

    A number without this is not reproducible, and reproducibility is the
    acceptance criterion. It is written beside every result set.

    Attributes:
        started_at: When the run began, ISO-8601 in UTC.
        tokenmill_version: What produced it.
        git_commit: The commit the run was made at, or ``None`` outside a
            checkout. This is the single most important field: it is what turns
            "we measured 18.3%" into "we measured 18.3% *with this code*".
        git_dirty: Whether the tree had uncommitted changes. A dirty run is
            still worth having and is worth flagging, because it cannot be
            reproduced from the commit alone.
        python: The interpreter version.
        platform_description: OS, release and architecture.
        cpu_count: How many cores, which bounds what a timing means.
        corpus_digest: A digest over the fixture files, so a result set can be
            checked against the corpus it claims to describe.
        repeats: How many times each cell was run.
        tokenizers: What was counted in.
        backend_versions: The version of every backend that took part.
        notes: Anything qualifying the whole run — no GPU, a blocked host, a
            backend that was absent.
    """

    started_at: str
    tokenmill_version: str
    git_commit: str | None
    git_dirty: bool
    python: str
    platform_description: str
    cpu_count: int
    corpus_digest: str
    repeats: int
    tokenizers: Sequence[str]
    backend_versions: Mapping[str, str | None] = field(default_factory=dict)
    notes: Sequence[str] = ()

    def to_json(self) -> dict[str, Any]:
        """Render the manifest.

        Returns:
            The JSON-ready mapping.
        """
        return {
            "started_at": self.started_at,
            "tokenmill_version": self.tokenmill_version,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "python": self.python,
            "platform": self.platform_description,
            "cpu_count": self.cpu_count,
            "corpus_digest": self.corpus_digest,
            "repeats": self.repeats,
            "tokenizers": list(self.tokenizers),
            "backend_versions": dict(self.backend_versions),
            "notes": list(self.notes),
        }
