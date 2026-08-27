"""Plain-text presentation helpers for the CLI.

Deliberately plain text rather than a rendered table library. CLI output is
read by people, but it is also piped into ``grep``, pasted into issues and
captured into ``PROGRESS.md`` verification logs, and box-drawing characters and
colour make all three worse. Aligned columns and stable ordering are what
actually help.
"""

from __future__ import annotations

from collections.abc import Sequence

from tokenmill.backends.heavy.doctor import Diagnosis
from tokenmill.core.compare import BackendComparison, FormatComparison
from tokenmill.core.models import BackendAttempt, ConversionResult, StageCount, TokenCount
from tokenmill.fidelity.models import FidelityScore

__all__ = [
    "format_backend_comparison",
    "format_bytes",
    "format_diagnosis",
    "format_fidelity_report",
    "format_format_comparison",
    "format_result_report",
    "format_stage_table",
    "format_table",
    "format_tokens",
]


def format_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render rows as a fixed-width table with a dashed rule under the header.

    Args:
        headers: Column headings.
        rows: The rows; every row must have as many cells as there are headers.

    Returns:
        The rendered table, without a trailing newline. Returns just the header
        when there are no rows, so the caller can still see the shape.

    Raises:
        ValueError: If a row's width does not match the header's.
    """
    for index, row in enumerate(rows):
        if len(row) != len(headers):
            msg = f"row {index} has {len(row)} cells, expected {len(headers)}"
            raise ValueError(msg)

    widths = [len(header) for header in headers]
    for row in rows:
        for column, cell in enumerate(row):
            widths[column] = max(widths[column], len(cell))

    def line(cells: Sequence[str]) -> str:
        # The last column is not padded: trailing spaces are invisible noise
        # that shows up as diff churn when output is pasted into a document.
        padded = [cell.ljust(widths[i]) for i, cell in enumerate(cells[:-1])]
        return "  ".join([*padded, cells[-1]]).rstrip()

    out = [line(headers), "  ".join("-" * width for width in widths)]
    out.extend(line(row) for row in rows)
    return "\n".join(out)


def format_tokens(count: TokenCount | None) -> str:
    """Render a token count for display.

    Args:
        count: The count, or ``None`` when nothing could be measured.

    Returns:
        The number with thousands separators, or ``n/a``. Never a guess: a
        missing count is shown as missing.
    """
    if count is None:
        return "n/a"
    return f"{count.value:,}"


def format_bytes(count: int) -> str:
    """Render a byte count in the largest unit that keeps it readable.

    Args:
        count: The number of bytes.

    Returns:
        A short string such as ``512 B``, ``37.2 KiB`` or ``2.4 MiB``. Binary
        units, because this describes a file on disk rather than a transfer
        rate, and every file manager the user has open agrees.
    """
    size = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    raise AssertionError  # pragma: no cover - the loop always returns


def format_stage_table(stages: Sequence[StageCount]) -> str:
    """Render the per-stage measurements as a table.

    Each row shows the size of the text as it left that stage, and how it
    changed from the stage before — which is what tells a user *where* the
    saving came from.

    Args:
        stages: The stages, in execution order.

    Returns:
        The rendered table.
    """
    rows: list[list[str]] = []
    previous: StageCount | None = None
    for stage in stages:
        rows.append(
            [
                stage.stage,
                f"{stage.characters:,}",
                format_tokens(stage.tokens),
                _stage_delta(previous, stage),
            ]
        )
        previous = stage
    return format_table(["stage", "chars", "tokens", "change"], rows)


def _stage_delta(previous: StageCount | None, current: StageCount) -> str:
    """Describe how one stage changed the text relative to the one before it.

    Args:
        previous: The preceding stage, or ``None`` for the first.
        current: The stage being described.

    Returns:
        A signed percentage against tokens where both were counted, against
        characters otherwise, or ``-`` for the first stage.
    """
    if previous is None:
        return "-"
    if (
        previous.tokens is not None
        and current.tokens is not None
        and previous.tokens.tokenizer_id == current.tokens.tokenizer_id
        and previous.tokens.value > 0
    ):
        before, after = previous.tokens.value, current.tokens.value
        unit = ""
    elif previous.characters > 0:
        before, after = previous.characters, current.characters
        unit = " chars"
    else:
        return "-"
    if before == after:
        return f"no change{unit}"
    change = (after - before) / before * 100
    return f"{change:+.1f}%{unit}"


def _percent_change(before: int, after: int) -> str:
    """Describe the change in a count as a signed percentage of the count.

    The sign follows the **count**, not the saving: ``-45.5%`` means the text
    got 45.5% cheaper, ``+71.0%`` means it got 71% more expensive. Reporting a
    conversion that made a document bigger as though it were a reduction would
    be exactly the kind of misleading number this project must not print, so
    growth is shown as growth.

    Args:
        before: The count going in.
        after: The count coming out.

    Returns:
        The signed percentage, or ``unchanged``/``n/a`` where no percentage is
        meaningful.
    """
    if before == after:
        return "unchanged"
    if before == 0:
        return "n/a"
    return f"{(after - before) / before * 100:+.1f}%"


def _format_attempts(attempts: Sequence[BackendAttempt]) -> str:
    """Render the backend chain that was walked, in order.

    Args:
        attempts: Every attempt made, in order.

    Returns:
        A one-line chain such as ``pdfplumber (failed) -> markitdown``.
    """
    return " -> ".join(
        attempt.backend_id if attempt.ok else f"{attempt.backend_id} (failed)"
        for attempt in attempts
    )


def _format_boilerplate(result: ConversionResult) -> str | None:
    """Describe how much of a web page's text the backend discarded.

    Deliberately a *second* line rather than a replacement for the ``tokens``
    line, because it answers a different question. ``tokens`` says what the
    conversion cost changed to, markup removal included; this says how much of
    what a reader would have *seen* was navigation, banners and footers. On
    ``boilerplate.html`` those are 77% and 43%, and reporting either as the
    other is the misattribution ``RESEARCH.md`` Category 7 is about.

    Args:
        result: The conversion to describe.

    Returns:
        The line, or ``None`` when the backend recorded no web metrics — every
        document and repository conversion, and any web backend that could not
        measure a page with no visible text at all.
    """
    share = result.metadata.get("boilerplate_reduction")
    if not isinstance(share, int | float):
        return None
    visible = result.metadata.get("visible_text_characters")
    if not isinstance(visible, int) or visible <= 0:
        return None

    # Characters, and it says so. The `tokens` line above is the token claim;
    # this one must never be mistaken for a second one.
    if share > 0:
        return f"page:     {share:.1%} of {visible:,} visible characters removed as boilerplate"
    if share == 0:
        return f"page:     none of {visible:,} visible characters removed as boilerplate"
    return (
        f"page:     no boilerplate removed; Markdown syntax added {-share:.1%} to "
        f"{visible:,} visible characters"
    )


def format_result_report(result: ConversionResult, *, show_stages: bool) -> str:
    """Render the human-readable report for one conversion.

    Args:
        result: The conversion to describe.
        show_stages: Include the per-stage breakdown.

    Returns:
        The report, without a trailing newline.
    """
    lines = [
        f"source:   {result.source_name}",
        f"backend:  {result.backend_id}",
        f"format:   {result.output_format.value}",
        f"duration: {result.duration_s * 1000:.0f} ms",
    ]
    # Only worth a line when a fallback actually happened. A conversion that
    # quietly came from the third-choice backend would otherwise look exactly
    # like one the preferred backend handled, and the measurement would be
    # attributed to a converter that never ran.
    if len(result.attempts) > 1:
        lines.append(f"attempts: {_format_attempts(result.attempts)}")
    if result.post_processors:
        lines.append(f"post:     {' -> '.join(result.post_processors)}")

    before, after = result.tokens_before, result.tokens_after
    if before is not None and after is not None:
        # Both sides are text a model could be given, so the delta means
        # something. This is the web and plain-text case.
        lines.append(
            f"tokens:   {before.value:,} -> {after.value:,}  "
            f"({_percent_change(before.value, after.value)}, {before.tokenizer_id})"
        )
    elif after is not None:
        # A binary document. There is no comparable "before" — see
        # tokenmill.core.pipeline — so the honest headline is what the output
        # costs, with the input reported as the size it is.
        lines.append(f"tokens:   {after.value:,}  ({after.tokenizer_id})")
        if result.source_bytes is not None:
            lines.append(f"size:     {format_bytes(result.source_bytes)} in, no comparable before")
    else:
        lines.append("tokens:   not measured — see warnings below")

    boilerplate = _format_boilerplate(result)
    if boilerplate is not None:
        lines.append(boilerplate)

    if show_stages and result.stages:
        lines.extend(["", format_stage_table(result.stages)])

    if result.warnings:
        lines.append("")
        lines.extend(f"warning:  {warning}" for warning in result.warnings)
    return "\n".join(lines)


def format_score(score: float | None) -> str:
    """Render one component score.

    Args:
        score: The fraction, or ``None`` when the component did not apply.

    Returns:
        The score to three decimal places, or ``n/a``. Never ``0.000`` for a
        component that was not measured — that is the distinction the whole
        fidelity package exists to preserve, and it must survive being printed.
    """
    return "n/a" if score is None else f"{score:.3f}"


def format_fidelity_report(score: FidelityScore) -> str:
    """Render a fidelity score as a table a person can act on.

    Args:
        score: The score to render.

    Returns:
        The report: one row per component with its score, what it counted and
        one sentence of detail, then the overall and the components it was
        composed of.
    """
    rows = [
        [
            component.component,
            format_score(component.score),
            ("-" if component.expected is None else f"{component.found}/{component.expected}"),
            component.detail,
        ]
        for component in score.components
    ]
    out = [
        f"fidelity: {score.fixture}" + (f" via {score.backend_id}" if score.backend_id else ""),
        "",
        format_table(["component", "score", "count", "detail"], rows),
        "",
    ]

    if score.overall is None:
        out.append(
            "overall: n/a — this fixture's ground truth supported no component, so "
            "the text was not assessed. That is not the same as scoring zero."
        )
    else:
        out.append(
            f"overall: {score.overall:.3f} "
            f"(unweighted mean of {', '.join(score.scored_components)})"
        )

    named = [c for c in score.components if c.missing]
    if named:
        out.append("")
        out.append("what is missing:")
        out.extend(
            f"  {component.component}: {item}" for component in named for item in component.missing
        )
    return "\n".join(out)


def _clip(text: str, limit: int) -> str:
    """Shorten a message for a table cell, saying that it was shortened.

    Args:
        text: The message.
        limit: How many characters to keep.

    Returns:
        The message, with an ellipsis when it was cut. A silently truncated
        error reads as a badly-worded one.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "\u2026"


def _relative(value: int | None, best: int | None) -> str:
    """Render one row's size relative to the cheapest.

    Args:
        value: This row's count.
        best: The cheapest count.

    Returns:
        ``base`` for the cheapest row, a percentage above it otherwise, or a
        dash when either number is missing.
    """
    if value is None or best is None or best == 0:
        return "-"
    if value == best:
        return "base"
    return f"+{(value - best) / best * 100:.0f}%"


def format_backend_comparison(comparison: BackendComparison) -> str:
    """Render a backend comparison as a table.

    Rows stay in the registry's preference order rather than being sorted by
    size. Sorting by tokens is a leaderboard, and a leaderboard on this data
    rewards whichever converter destroyed the most — the one that emits nothing
    wins by a distance. The cheapest and the most faithful are named underneath
    instead, and when they differ that is said outright.

    Args:
        comparison: The comparison to render.

    Returns:
        The report.
    """
    cheapest = comparison.cheapest
    best_tokens = cheapest.tokens.value if cheapest and cheapest.tokens else None

    rows = []
    for row in comparison.rows:
        if not row.ok:
            rows.append([row.backend_id, "failed", "-", "-", "-", _clip(row.error or "", 60)])
            continue
        overall = row.fidelity.overall if row.fidelity else None
        components = (
            f"{len(row.fidelity.scored_components)} scored"
            if row.fidelity and row.fidelity.scored_components
            else "no ground truth"
        )
        rows.append(
            [
                row.backend_id,
                format_tokens(row.tokens),
                _relative(row.tokens.value if row.tokens else None, best_tokens),
                f"{row.duration_s * 1000:.0f} ms" if row.duration_s is not None else "-",
                format_score(overall),
                components,
            ]
        )

    out = [
        f"comparing {comparison.source_name} across {len(comparison.rows)} backend(s)",
        f"counts in {comparison.tokenizer_id}",
        "",
        format_table(["backend", "tokens", "vs best", "time", "fidelity", "components"], rows),
        "",
    ]

    best = comparison.most_faithful
    if cheapest is not None:
        out.append(f"cheapest:      {cheapest.backend_id} ({format_tokens(cheapest.tokens)})")
    if best is not None:
        out.append(
            f"most faithful: {best.backend_id} "
            f"({format_score(best.fidelity.overall if best.fidelity else None)})"
        )

    verdict = comparison.cheapest_is_most_faithful
    if verdict is None:
        out.append(
            "No fidelity ground truth for this input, so this table cannot say what "
            "any of these savings cost. Pass --against to score against a corpus "
            "fixture; without it, the cheapest row is only the smallest one."
        )
    elif verdict:
        out.append("The cheapest option is also the most faithful one here.")
    else:
        out.append(
            "The cheapest option is NOT the most faithful one. A token saving "
            "without a fidelity number is not a result."
        )
    return "\n".join(out)


def format_format_comparison(comparison: FormatComparison) -> str:
    """Render a format comparison as a table.

    Args:
        comparison: The comparison to render.

    Returns:
        The report.
    """
    cheapest = comparison.cheapest
    best_tokens = cheapest.tokens.value if cheapest and cheapest.tokens else None

    rows = []
    for row in comparison.rows:
        if not row.ok:
            rows.append([row.format_id, "n/a", "-", _clip(row.error or "", 60)])
            continue
        rows.append(
            [
                row.format_id,
                format_tokens(row.tokens),
                _relative(row.tokens.value if row.tokens else None, best_tokens),
                f"{row.characters:,} characters" if row.characters is not None else "-",
            ]
        )

    table = comparison.table
    # "table 2 of 3" rather than nothing: a report that shows one table without
    # saying how many the document had is defect N4's silence in a new place.
    which = (
        ""
        if comparison.table_count <= 1
        else f" (table {comparison.table_index + 1} of {comparison.table_count})"
    )
    out = [
        f"comparing {len(comparison.rows)} serialisation(s) of a "
        f"{len(table.rows)}x{len(table.headers)} table from {comparison.source_name}{which}",
        f"counts in {comparison.tokenizer_id}",
        "",
        format_table(["format", "tokens", "vs best", "size"], rows),
        "",
    ]
    if cheapest is not None:
        out.append(f"cheapest: {cheapest.format_id} ({format_tokens(cheapest.tokens)})")
    out.append(
        "Format savings carry accuracy trade-offs and are model-dependent. See "
        "docs/BENCHMARKS.md; TOON's wins are narrow (uniform arrays) and CSV "
        "scores among the weakest on comprehension in one published test."
    )
    return "\n".join(out)


def format_diagnosis(diagnosis: Diagnosis) -> str:
    """Render `tokenmill doctor`'s findings.

    Three sections, in the order a reader needs them: what this machine is, what
    is installed, and what it would take to install the rest. The last is the
    reason the command exists, so it is not folded into a hint column that gets
    clipped — `docs/REVIEW_PHASES_0_8.md` N10 was exactly that mistake, found in
    a screenshot rather than by a test.

    Args:
        diagnosis: What was found.

    Returns:
        The report.
    """
    out: list[str] = ["tokenmill doctor", ""]
    out += [
        f"python:    {diagnosis.python}",
        f"platform:  {diagnosis.platform_description}",
        f"gpu:       {diagnosis.gpu.accelerator.value} — {diagnosis.gpu.detail}",
    ]
    for device in diagnosis.gpu.devices:
        out.append(f"           {device.describe()}")
    if diagnosis.gpu.driver:
        out.append(f"           driver {diagnosis.gpu.driver}")
    out.append("")

    out.append("external tools")
    tool_rows = [[name, path or "not found"] for name, path in diagnosis.tools]
    out += [format_table(["tool", "location"], tool_rows), ""]

    out.append(f"backends ({diagnosis.available_count} of {len(diagnosis.backends)} available)")
    rows = [
        [
            b.backend_id,
            b.tier.value,
            "gpu" if b.requires_gpu else "cpu",
            "available" if b.usable_here else _clip(b.availability.describe(), 46),
        ]
        for b in diagnosis.backends
    ]
    out += [format_table(["id", "tier", "needs", "status"], rows), ""]

    heavy = [b for b in diagnosis.heavy if not b.usable_here]
    if heavy:
        out.append("how to install the GPU tier")
        out.append("")
        for backend in heavy:
            out.append(f"  {backend.name} ({backend.backend_id}) — {backend.licence}")
            if backend.weights_licence is None:
                out.append(
                    "    weights licence: NOT VERIFIED. The code's licence above is not "
                    "the weights'; read the model card before relying on it."
                )
            else:
                out.append(f"    weights licence: {backend.weights_licence}")
            for step in backend.install_steps:
                out.append(f"    $ {step}")
            if not backend.install_steps:
                out.append(f"    {backend.availability.hint or 'see docs/BACKENDS.md'}")
            for note in backend.notes:
                out.append(f"    note: {note}")
            if backend.torch:
                out.append(f"    torch: {backend.torch}")
            out.append("")

    for warning in diagnosis.warnings:
        out.append(f"note: {warning}")
    return "\n".join(out)
