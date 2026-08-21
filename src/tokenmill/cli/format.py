"""Plain-text presentation helpers for the CLI.

Deliberately plain text rather than a rendered table library. CLI output is
read by people, but it is also piped into ``grep``, pasted into issues and
captured into ``PROGRESS.md`` verification logs, and box-drawing characters and
colour make all three worse. Aligned columns and stable ordering are what
actually help.
"""

from __future__ import annotations

from collections.abc import Sequence

from tokenmill.core.models import ConversionResult, StageCount, TokenCount

__all__ = ["format_result_report", "format_stage_table", "format_table", "format_tokens"]


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
    if result.post_processors:
        lines.append(f"post:     {' -> '.join(result.post_processors)}")

    before, after = result.tokens_before, result.tokens_after
    if before is not None and after is not None:
        lines.append(
            f"tokens:   {before.value:,} -> {after.value:,}  "
            f"({_percent_change(before.value, after.value)}, {before.tokenizer_id})"
        )
    else:
        lines.append("tokens:   not measured — see warnings below")

    if show_stages and result.stages:
        lines.extend(["", format_stage_table(result.stages)])

    if result.warnings:
        lines.append("")
        lines.extend(f"warning:  {warning}" for warning in result.warnings)
    return "\n".join(lines)
