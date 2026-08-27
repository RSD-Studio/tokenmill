"""Writing results out, and the rule that makes the output honest.

Three formats, and each has a different job:

* **`results.csv`** — one flat row per cell, for anybody who wants to load it
  into something else. Every fidelity component is its own column.
* **`results.json`** — the same cells with **every repeat's timing** kept, so a
  published median can be recomputed rather than trusted, plus the run manifest.
* **`report.md`** — the human table, which is what `docs/BENCHMARKS.md` quotes.

**The rule this module enforces.** `benchmarks/README.md`:

> The fidelity axis is the point. Token savings without a fidelity measurement
> is not a result — a converter that emits an empty string scores a 100%
> reduction.

:func:`render_markdown` will not emit a token column without a fidelity column
beside it, and :func:`check_report` asserts that of any rendered report. That is
what "structurally impossible to publish" means here: not a convention, not a
review checklist, a function that raises.

**Rows are never sorted by size.** Phase 5 settled this for `compare` and the
reasoning applies harder to a document somebody will quote from: on `tables.pdf`
the cheapest backend is the one that flattens the table, so a leaderboard
rewards whichever converter destroyed the most. Rows stay in the registry's
preference order within each fixture, with fidelity beside every count.

**Failures and empty outputs are rendered, not filtered.** `corrupt.pdf` failing
five ways and `scanned.pdf` returning nothing are the two most informative parts
of this corpus.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from benchmarks.models import CellResult, RunManifest
from tokenmill.fidelity import COMPONENTS

__all__ = [
    "check_report",
    "render_markdown",
    "write_csv",
    "write_json",
    "write_results",
]

#: The columns `results.csv` carries, in order. Fixed rather than derived from
#: the first row, so a run in which the first cell failed does not silently
#: produce a narrower file than one in which it succeeded.
_CSV_COLUMNS: tuple[str, ...] = (
    "fixture",
    "backend",
    "tokenizer",
    "ok",
    "tokens_before",
    "tokens_after",
    "reduction",
    "characters",
    "fidelity",
    "fidelity_scored",
    *(f"fidelity_{name}" for name in COMPONENTS),
    "n",
    "median_ms",
    "min_ms",
    "max_ms",
    "spread_ratio",
    "peak_python_kb",
    "peak_rss_kb",
    "baseline_rss_kb",
    "added_rss_kb",
    "memory_method",
    "empty_output",
    "backend_version",
    "error_type",
    "error",
    "warnings",
)


class ReportError(RuntimeError):
    """A report that would have published a token count without a fidelity one."""


def write_results(
    directory: Path,
    results: Sequence[CellResult],
    manifest: RunManifest,
) -> dict[str, Path]:
    """Write every output format for one run.

    Args:
        directory: Where to write. Created if it does not exist.
        results: Every cell.
        manifest: What the run was a measurement of.

    Returns:
        The files written, by kind.

    Raises:
        ReportError: If the rendered Markdown would show a token column with no
            fidelity column. See the module docstring.
    """
    directory.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(results, manifest)
    check_report(markdown)

    paths = {
        "csv": directory / "results.csv",
        "json": directory / "results.json",
        "markdown": directory / "report.md",
        "manifest": directory / "manifest.json",
    }
    write_csv(paths["csv"], results)
    write_json(paths["json"], results, manifest)
    # newline="" throughout, as `compare --write` does: a byte count published
    # about a file has to match the file, and text-mode newline translation on
    # Windows breaks that.
    paths["markdown"].write_text(markdown, encoding="utf-8", newline="")
    paths["manifest"].write_text(
        json.dumps(manifest.to_json(), indent=2) + "\n", encoding="utf-8", newline=""
    )
    return paths


def write_csv(path: Path, results: Sequence[CellResult]) -> None:
    """Write the flat one-row-per-cell file.

    Args:
        path: Where to write.
        results: Every cell.
    """
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_CSV_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for result in results:
            writer.writerow(result.to_row())


def write_json(path: Path, results: Sequence[CellResult], manifest: RunManifest) -> None:
    """Write the full-detail file, repeats and all.

    Args:
        path: Where to write.
        results: Every cell.
        manifest: The run's provenance, embedded so the file stands alone.
    """
    payload = {
        "manifest": manifest.to_json(),
        "results": [result.to_json() for result in results],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="")


def load_results(path: Path) -> tuple[list[CellResult], dict[str, object]]:
    """Read a `results.json` back.

    Used by the merge step and by the tests that assert a published number is
    the number in the file.

    Args:
        path: The file.

    Returns:
        The cells and the raw manifest mapping.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    cells = [
        CellResult(
            fixture=row["fixture"],
            backend=row["backend"],
            tokenizer=row["tokenizer"],
            ok=row["ok"],
            error=row.get("error"),
            error_type=row.get("error_type"),
            tokens_before=row.get("tokens_before"),
            tokens_after=row.get("tokens_after"),
            characters=row.get("characters"),
            fidelity=row.get("fidelity"),
            fidelity_components=row.get("fidelity_components") or {},
            fidelity_scored=row.get("fidelity_scored", 0),
            durations_ms=tuple(row.get("durations_ms") or ()),
            peak_python_kb=row.get("peak_python_kb"),
            peak_rss_kb=row.get("peak_rss_kb"),
            baseline_rss_kb=row.get("baseline_rss_kb"),
            memory_method=row.get("memory_method", "none"),
            warnings=tuple(row.get("warnings") or ()),
            empty_output=row.get("empty_output", False),
            backend_version=row.get("backend_version"),
        )
        for row in payload["results"]
    ]
    return cells, payload.get("manifest", {})


def check_report(markdown: str) -> None:
    """Refuse a report that shows tokens without fidelity.

    The whole point of this package, expressed as a function that raises rather
    than as a rule somebody remembers. Every table that has a `tokens` column
    must have a `fidelity` column.

    Args:
        markdown: The rendered report.

    Raises:
        ReportError: If any table breaks the rule.
    """
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        headers = [cell.strip().lower() for cell in line.strip("|").split("|")]
        if not any(h.startswith("tokens") for h in headers):
            continue
        if not any("fidelity" in h for h in headers):
            msg = (
                "a results table shows a token count with no fidelity column "
                "beside it. benchmarks/README.md: token savings without a "
                "fidelity measurement is not a result — a converter that emits "
                f"an empty string scores a 100% reduction. Offending header: {line}"
            )
            raise ReportError(msg)


def render_markdown(results: Sequence[CellResult], manifest: RunManifest) -> str:
    """Render the human-readable report.

    Args:
        results: Every cell.
        manifest: The run's provenance, rendered as a header so the table is
            never separated from what it is a measurement of.

    Returns:
        The Markdown.
    """
    out: list[str] = [
        "# Benchmark results",
        "",
        f"Run at **{manifest.started_at}** on {manifest.platform_description}, "
        f"Python {manifest.python}, {manifest.cpu_count} cores.",
        "",
        f"- tokenmill `{manifest.tokenmill_version}` at commit "
        f"`{manifest.git_commit or 'unknown'}`"
        f"{' **(working tree dirty)**' if manifest.git_dirty else ''}",
        f"- corpus digest `{manifest.corpus_digest}`",
        f"- **N = {manifest.repeats}** timed repeats per cell, plus one discarded "
        f"warm-up and one instrumented pass for memory",
        f"- counted in: {', '.join(f'`{t}`' for t in manifest.tokenizers)}",
        "",
    ]
    if manifest.notes:
        out.append("**About this run:**")
        out.append("")
        out.extend(f"- {note}" for note in manifest.notes)
        out.append("")

    for tokenizer in manifest.tokenizers:
        rows = [r for r in results if r.tokenizer == tokenizer]
        if not rows:
            continue
        out.extend(_section(tokenizer, rows))

    out.extend(_failures_section(results))
    out.extend(_timing_section(results, manifest))
    return "\n".join(out) + "\n"


def _section(tokenizer: str, rows: Sequence[CellResult]) -> list[str]:
    """Render the main table for one tokenizer.

    Args:
        tokenizer: What these counts are in.
        rows: The cells counted in it.

    Returns:
        The lines.
    """
    unit = "UTF-8 bytes, **not model tokens**" if tokenizer == "bytes" else "model tokens"
    out = [
        f"## Counted in `{tokenizer}`",
        "",
        f"Counts are {unit}.",
        "",
        "Rows are in the registry's preference order within each fixture, **not**",
        "sorted by size. On `tables.pdf` the cheapest backend is the one that",
        "flattens the table, so a leaderboard here would recommend whichever",
        "converter destroyed the most.",
        "",
        "| Fixture | Backend | Tokens | Change | Fidelity | Scored | Median | N | Spread |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        out.append(_row(row))
    out.append("")
    return out


def _row(row: CellResult) -> str:
    """Render one cell as a Markdown table row.

    Args:
        row: The cell.

    Returns:
        The row.
    """
    if not row.ok:
        return f"| `{row.fixture}` | `{row.backend}` | **fail** | — | n/a | 0 | — | {row.n} | — |"
    tokens = "—" if row.tokens_after is None else f"{row.tokens_after:,}"
    if row.empty_output:
        tokens = f"{tokens} **(empty)**"
    change = "—" if row.reduction is None else _change(row.reduction)
    fidelity = "n/a" if row.fidelity is None else f"{row.fidelity:.3f}"
    median = "—" if row.median_ms is None else f"{row.median_ms:,.0f} ms"
    spread = "—" if row.spread_ratio is None else f"{row.spread_ratio:.1f}x"
    return (
        f"| `{row.fixture}` | `{row.backend}` | {tokens} | {change} | {fidelity} | "
        f"{row.fidelity_scored} | {median} | {row.n} | {spread} |"
    )


def _change(reduction: float) -> str:
    """Render a saving with the sign this project prints everywhere else.

    **`CellResult.reduction` is positive for a saving** — it is the fraction
    removed — and every user-facing table in tokenmill prints a saving as a
    *negative* change, because that is what happened to the document's size:
    `tokens: 12,481 -> 6,802 (-45.5%)`.

    Formatting `reduction` directly would print a 19.8% saving as `+19.8%`,
    which reads as growth. The first run of this harness did exactly that, and
    it is the same class of error `PROGRESS.md` records from Phase 1, where a
    conversion that made a document *larger* was reported as a 71% saving.
    `tests/unit/test_benchmark_harness.py` asserts both directions.

    Args:
        reduction: The fraction removed; negative when the output grew.

    Returns:
        The signed percentage, with a true minus sign to match the other tables.
    """
    return f"{-reduction:+.1%}".replace("-", "\u2212")


def _failures_section(results: Sequence[CellResult]) -> list[str]:
    """Render the failures and the empty outputs, which are results.

    Args:
        results: Every cell.

    Returns:
        The lines.
    """
    failures = [r for r in results if not r.ok]
    empties = [r for r in results if r.ok and r.empty_output]
    out = ["## Failures and empty outputs", ""]
    if not failures and not empties:
        out += ["Nothing failed and nothing came back empty.", ""]
        return out

    out += [
        "These are results rather than omissions. A benchmark that reported only",
        "the cells that worked would be a marketing document.",
        "",
    ]
    if failures:
        out += ["| Fixture | Backend | Error | Message |", "|---|---|---|---|"]
        seen: set[tuple[str, str]] = set()
        for row in failures:
            key = (row.fixture, row.backend)
            if key in seen:
                continue
            seen.add(key)
            message = (row.error or "").replace("|", "\\|").replace("\n", " ")
            out.append(
                f"| `{row.fixture}` | `{row.backend}` | `{row.error_type}` | {message[:160]} |"
            )
        out.append("")
    if empties:
        out += [
            "**Succeeded and produced nothing**, which is the single most",
            "misleading cell a benchmark can contain: it scores a 100% reduction.",
            "",
            "| Fixture | Backend | Fidelity |",
            "|---|---|---|",
        ]
        seen = set()
        for row in empties:
            key = (row.fixture, row.backend)
            if key in seen:
                continue
            seen.add(key)
            fidelity = "n/a" if row.fidelity is None else f"{row.fidelity:.3f}"
            out.append(f"| `{row.fixture}` | `{row.backend}` | {fidelity} |")
        out.append("")
    return out


def _timing_section(results: Sequence[CellResult], manifest: RunManifest) -> list[str]:
    """Render the timing and memory table, with its limitations attached.

    Args:
        results: Every cell.
        manifest: For N.

    Returns:
        The lines.
    """
    # One row per (fixture, backend): timings do not depend on the tokenizer, so
    # rendering them once per tokenizer would triple the table and imply three
    # measurements where there was one.
    seen: set[tuple[str, str]] = set()
    rows: list[CellResult] = []
    for row in results:
        key = (row.fixture, row.backend)
        if row.ok and key not in seen:
            seen.add(key)
            rows.append(row)

    methods = {r.memory_method for r in rows}
    out = [
        "## Wall time and memory",
        "",
        f"**N = {manifest.repeats}** timed repeats per cell, median and spread. The",
        "spread is `slowest / fastest`, which says more on this sample size than a",
        "standard deviation would.",
        "",
    ]
    if "proc-sampling" in methods:
        out += [
            "`added RSS` is how much resident memory the conversion added to this",
            "process **and its descendants**, sampled every 5 ms: the peak during the",
            "cell minus the reading taken immediately before it. It is the only",
            "figure here that means anything for a subprocess backend, and the only",
            "one that is comparable between rows.",
            "",
            "`peak RSS` is the raw peak, published beside it so the subtraction is",
            "checkable. **Do not compare peaks between rows.** A Python process's",
            "resident set does not shrink, so the peak column climbs through the run",
            "as each cell inherits every library the earlier cells imported; the last",
            "row's peak is mostly the first fifty rows' imports. Both figures are",
            "lower bounds: a peak occurring between two samples is missed.",
            "",
        ]
    if "tracemalloc-only" in methods:
        out += [
            "On this platform the resident set could not be sampled, so only Python",
            "allocations are reported — blind to a C library's own memory and to every",
            "child process. Reported as `n/a` rather than as zero.",
            "",
        ]
    out += [
        "`peak Python` is `tracemalloc`'s peak: exact for Python objects, blind to",
        "everything else. The two are different measurements and neither is *the*",
        "memory used.",
        "",
        "| Fixture | Backend | Median | Min | Max | Spread | Added RSS | Peak RSS |"
        " Peak Python | Version |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        added = "n/a" if row.added_rss_kb is None else f"{row.added_rss_kb / 1024:,.0f} MiB"
        rss = "n/a" if row.peak_rss_kb is None else f"{row.peak_rss_kb / 1024:,.0f} MiB"
        python_kb = "n/a" if row.peak_python_kb is None else f"{row.peak_python_kb / 1024:,.1f} MiB"
        out.append(
            f"| `{row.fixture}` | `{row.backend}` | "
            f"{row.median_ms:,.0f} ms | {row.min_ms:,.0f} ms | {row.max_ms:,.0f} ms | "
            f"{row.spread_ratio:.1f}x | {added} | {rss} | {python_kb} | "
            f"{row.backend_version or '—'} |"
        )
    out.append("")
    return out


def merge(runs: Iterable[Sequence[CellResult]]) -> list[CellResult]:
    """Combine several runs' cells into one set.

    This is the whole mechanism for the thing the sandbox makes necessary: a
    local run can only reach the `bytes` unit, because the egress proxy denies
    every tokenizer vocabulary host, and a CI run can reach `o200k_base`. Since
    a cell is keyed by (fixture, backend, **tokenizer**), the two merge by
    concatenation and a byte figure can never land in a token column.

    Later runs win on an exact key collision, so re-running one tokenizer
    replaces its rows rather than duplicating them.

    Args:
        runs: The result sets, oldest first.

    Returns:
        Every cell, deduplicated by (fixture, backend, tokenizer).
    """
    merged: dict[tuple[str, str, str], CellResult] = {}
    for run in runs:
        for cell in run:
            merged[(cell.fixture, cell.backend, cell.tokenizer)] = cell
    return list(merged.values())
