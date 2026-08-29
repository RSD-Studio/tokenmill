"""Comparing backends and formats on one input.

This is the answer to a question the project has been deferring since Phase 2.
A document and a repository have **no before-count** — nobody hands a model the
bytes of a `.docx` or the contents of a directory — so `convert` correctly
reports one number and a size. The comparison that means something for those
inputs is between *backends on the same input*, and that is what this does.

Two rules, both of which are about not lying:

**Fidelity sits beside tokens in every row.** Without it this is a machine for
recommending whichever converter destroys the most, because the converter that
emits an empty string wins on tokens by a distance. Where no ground truth
exists the column reads `n/a` and the caller is told the comparison is
incomplete rather than shown a blank that looks like a pass.

**Rows are in the registry's own preference order, not sorted by size.**
Sorting by tokens *is* a leaderboard, and a leaderboard on this data rewards
the wrong thing. The cheapest and the most faithful rows are both named
explicitly, and when they differ that is stated — which is the result a reader
should actually take away.

Phase 10's harness rule applies here early: every backend is treated
identically, and a result that contradicts `docs/research/RESEARCH.md` is
reported as-is with a note rather than buried.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tokenmill.core.errors import ConversionError
from tokenmill.core.models import ConvertOptions, Source, TokenCount
from tokenmill.core.pipeline import Pipeline
from tokenmill.fidelity.models import FidelityScore
from tokenmill.fidelity.scorer import score as score_fidelity
from tokenmill.formats.base import Table, TableEncoderRegistry, TableError
from tokenmill.formats.markdown_table import MarkdownTableEncoder

__all__ = [
    "BackendComparison",
    "ComparisonRow",
    "FormatComparison",
    "FormatRow",
    "compare_backends",
    "compare_format_tables",
    "compare_formats",
]


@dataclass(frozen=True, slots=True)
class ComparisonRow:
    """One backend's result on the input.

    Attributes:
        backend_id: Which backend produced it.
        tokens: What the final text costs, or ``None`` when no tokenizer could
            be loaded.
        characters: The final text's length, always available.
        duration_s: Wall time for the whole pipeline run.
        fidelity: The score against ground truth, or ``None`` when there was
            none to score against.
        text: The converted text, for a caller that wants to write it out.
        error: Why this backend produced nothing, when it failed. A failure is
            a row rather than an omission — a backend that cannot read the file
            is a result.
        warnings: Anything the conversion reported.
    """

    backend_id: str
    tokens: TokenCount | None = None
    characters: int | None = None
    duration_s: float | None = None
    fidelity: FidelityScore | None = None
    text: str | None = None
    error: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether this backend produced a document.

        Returns:
            True when it converted successfully.
        """
        return self.error is None


@dataclass(frozen=True, slots=True)
class BackendComparison:
    """Every backend's result on one input.

    Attributes:
        source_name: What was compared.
        tokenizer_id: What the counts are in. Part of the number's meaning.
        rows: One per backend, in the registry's preference order.
    """

    source_name: str
    tokenizer_id: str
    rows: tuple[ComparisonRow, ...]

    @property
    def cheapest(self) -> ComparisonRow | None:
        """The successful row with the fewest tokens.

        Returns:
            The row, or ``None`` when nothing succeeded or nothing was counted.
        """
        counted = [
            (row.tokens.value, index, row)
            for index, row in enumerate(self.rows)
            if row.ok and row.tokens is not None
        ]
        if not counted:
            return None
        # The index breaks ties by preference order, so two backends producing
        # identical output name the preferred one rather than an arbitrary one.
        return min(counted)[2]

    @property
    def most_faithful(self) -> ComparisonRow | None:
        """The successful row with the highest overall fidelity.

        Returns:
            The row, or ``None`` when nothing was scored.
        """
        scored = [
            (row.fidelity.overall, -index, row)
            for index, row in enumerate(self.rows)
            if row.ok and row.fidelity is not None and row.fidelity.overall is not None
        ]
        if not scored:
            return None
        # `-index` breaks ties towards the preferred backend rather than the
        # last one to score the same.
        return max(scored)[2]

    @property
    def cheapest_is_most_faithful(self) -> bool | None:
        """Whether the cheapest option is also the best one.

        Returns:
            True or False when both are known, ``None`` when either is not.
            ``None`` matters: it means the comparison could not answer the only
            question worth asking, which a caller must say rather than imply.
        """
        cheapest = self.cheapest
        best = self.most_faithful
        if cheapest is None or best is None:
            return None
        return cheapest.backend_id == best.backend_id


@dataclass(frozen=True, slots=True)
class FormatRow:
    """One serialisation's cost for the same table.

    Attributes:
        format_id: Which encoder produced it.
        tokens: What it costs, or ``None`` when nothing could be counted.
        characters: Its length.
        text: The encoded text.
        error: Why this format could not represent the table, when it could
            not. A table whose columns have no names cannot become JSON, and
            saying so is more useful than omitting the row.
    """

    format_id: str
    tokens: TokenCount | None = None
    characters: int | None = None
    text: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Whether this format could represent the table.

        Returns:
            True when it encoded successfully.
        """
        return self.error is None


@dataclass(frozen=True, slots=True)
class FormatComparison:
    """The same table in several serialisations.

    Attributes:
        source_name: What the table came from.
        tokenizer_id: What the counts are in.
        table: The table every row encodes.
        rows: One per format, in id order.
        table_index: Which table in the document this is, counting from zero.
        table_count: How many tables the document had. Reported so a reader can
            see that a document with three tables produced three comparisons —
            defect N4 was that only the first was ever compared, and a report
            that shows one table without saying how many there were is the
            same silence in a different place.
    """

    source_name: str
    tokenizer_id: str
    table: Table
    rows: tuple[FormatRow, ...]
    table_index: int = 0
    table_count: int = 1

    @property
    def cheapest(self) -> FormatRow | None:
        """The successful row with the fewest tokens.

        Returns:
            The row, or ``None`` when nothing was counted.
        """
        counted = [
            (row.tokens.value, index, row)
            for index, row in enumerate(self.rows)
            if row.ok and row.tokens is not None
        ]
        if not counted:
            return None
        return min(counted)[2]


def compare_backends(
    source: Source,
    backend_ids: Sequence[str],
    *,
    options: ConvertOptions | None = None,
    pipeline: Pipeline | None = None,
    truth: Mapping[str, Any] | None = None,
    fixture: str | None = None,
) -> BackendComparison:
    """Convert one source with several backends and measure each.

    Args:
        source: The input, which may be a file, a page or a repository.
        backend_ids: The backends to try, in the order they should be reported.
        options: The conversion options; each run forces one backend and
            disables fallback, so that a row always describes the backend it
            names.
        pipeline: The pipeline to run; a default one is built when omitted.
        truth: Ground truth to score each result against, when there is any.
        fixture: The ground truth's fixture name, for the score's provenance.

    Returns:
        The comparison, one row per backend, failures included.
    """
    runner = pipeline if pipeline is not None else Pipeline()
    opts = options if options is not None else ConvertOptions()
    rows: list[ComparisonRow] = []

    for backend_id in backend_ids:
        started = time.perf_counter()
        try:
            # Fallback off: a row headed `pypdf` that was actually produced by
            # pdfplumber would make the whole table a lie.
            result = runner.run(source, opts.with_(backend=backend_id, fallback=False))
        except ConversionError as exc:
            rows.append(
                ComparisonRow(
                    backend_id=backend_id,
                    duration_s=time.perf_counter() - started,
                    error=str(exc),
                )
            )
            continue

        fidelity = (
            score_fidelity(
                result.text, truth, fixture=fixture or source.name, backend_id=backend_id
            )
            if truth is not None
            else None
        )
        rows.append(
            ComparisonRow(
                backend_id=backend_id,
                tokens=result.tokens_after,
                characters=len(result.text),
                duration_s=result.duration_s,
                fidelity=fidelity,
                text=result.text,
                warnings=result.warnings,
            )
        )

    return BackendComparison(source_name=source.name, tokenizer_id=opts.tokenizer, rows=tuple(rows))


def compare_formats(
    text: str,
    format_ids: Sequence[str],
    *,
    registry: TableEncoderRegistry,
    count: Any,
    tokenizer_id: str,
    source_name: str,
) -> FormatComparison:
    """Re-encode the first table in ``text`` in several serialisations.

    Kept for callers that genuinely want one table. Anything reporting on a
    whole document should use :func:`compare_format_tables`, which is what
    closes defect N4.

    Args:
        text: Converted Markdown containing a table.
        format_ids: The formats to encode in.
        registry: Where the encoders come from.
        count: Counts one string, or ``None`` when no tokenizer loaded.
        tokenizer_id: The tokenizer's id, for the counts' provenance.
        source_name: What the table came from.

    Returns:
        The comparison, one row per format.

    Raises:
        TableError: If ``text`` carries no table to compare. There is nothing
            honest to report in that case — every format would encode an empty
            table identically.
    """
    tables = MarkdownTableEncoder().decode_all(text)
    if not tables:
        msg = "no Markdown table found: a header row must be followed by a delimiter row"
        raise TableError(msg)
    return _compare_one_table(
        tables[0],
        format_ids,
        registry=registry,
        count=count,
        tokenizer_id=tokenizer_id,
        source_name=source_name,
        table_index=0,
        table_count=len(tables),
    )


def compare_format_tables(
    text: str,
    format_ids: Sequence[str],
    *,
    registry: TableEncoderRegistry,
    count: Any,
    tokenizer_id: str,
    source_name: str,
) -> tuple[FormatComparison, ...]:
    """Re-encode **every** table in ``text`` in several serialisations.

    Defect N4. ``compare --formats`` used to re-encode the first table and stop,
    which is invisible on a fixture that has one and wrong on a real report:
    a document whose three tables have different shapes will not have one
    cheapest format, and reporting the first table's answer as the document's
    is a measurement of something nobody asked about.

    Args:
        text: Converted Markdown that may contain tables.
        format_ids: The formats to encode in.
        registry: Where the encoders come from.
        count: Counts one string, or ``None`` when no tokenizer loaded.
        tokenizer_id: The tokenizer's id, for the counts' provenance.
        source_name: What the tables came from.

    Returns:
        One comparison per table, in document order.

    Raises:
        TableError: If ``text`` carries no table at all.
    """
    tables = MarkdownTableEncoder().decode_all(text)
    if not tables:
        msg = "no Markdown table found: a header row must be followed by a delimiter row"
        raise TableError(msg)
    return tuple(
        _compare_one_table(
            table,
            format_ids,
            registry=registry,
            count=count,
            tokenizer_id=tokenizer_id,
            source_name=source_name,
            table_index=index,
            table_count=len(tables),
        )
        for index, table in enumerate(tables)
    )


def _compare_one_table(
    table: Table,
    format_ids: Sequence[str],
    *,
    registry: TableEncoderRegistry,
    count: Any,
    tokenizer_id: str,
    source_name: str,
    table_index: int,
    table_count: int,
) -> FormatComparison:
    """Encode one already-decoded table in each requested format.

    Args:
        table: The table to encode.
        format_ids: The formats to encode in.
        registry: Where the encoders come from.
        count: Counts one string, or ``None`` when no tokenizer loaded.
        tokenizer_id: The tokenizer's id, for the counts' provenance.
        source_name: What the table came from.
        table_index: Which table in the document this is.
        table_count: How many the document had.

    Returns:
        The comparison, one row per format.
    """
    rows: list[FormatRow] = []
    for format_id in format_ids:
        encoder = registry.get(format_id)
        try:
            encoded = encoder.encode(table)
        except TableError as exc:
            rows.append(FormatRow(format_id=format_id, error=str(exc)))
            continue
        tokens = (
            TokenCount(value=count(encoded), tokenizer_id=tokenizer_id)
            if count is not None
            else None
        )
        rows.append(
            FormatRow(
                format_id=format_id,
                tokens=tokens,
                characters=len(encoded),
                text=encoded,
            )
        )
    return FormatComparison(
        source_name=source_name,
        tokenizer_id=tokenizer_id,
        table=table,
        rows=tuple(rows),
        table_index=table_index,
        table_count=table_count,
    )
