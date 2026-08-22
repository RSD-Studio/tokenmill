"""The ``pdfplumber`` backend: digital PDFs, with the tables kept as tables.

pdfplumber's ``extract_text`` is unremarkable — it is ``extract_tables`` that
earns this backend its place. On ``tests/fixtures/tables.pdf`` it recovers the
7x5 grid **completely**, all 35 cells in the right rows, where the other light
backends either mis-split the header row or flatten the whole table into prose.
That is Phase 2's table-fidelity acceptance criterion, and this is the backend
that meets it.

Recovering the cells is only half the job. ``extract_text`` alone renders a
table as loose words on lines, so this adapter splices the two together: for
each page it walks the detected tables top to bottom, emitting the text between
them and a rendered Markdown table in their place. The result reads in document
order with the grid intact.

**What it does not do, and this is not a small caveat.** pdfplumber has no
layout model, so it reads a page in scan-line order. On the two-column
``twocolumn.pdf`` fixture that interleaves the columns — the observed output
starts ``Two Column Reading boilerplate, because it is pure cost.``, which is
the first line of column one followed by a line from column two. For
multi-column documents use ``pypdf`` or ``kreuzberg``, both of which get that
fixture's ``ORDERMARK`` sentinels in the right order. ``docs/BACKENDS.md``
quotes the output.

Because that failure is silent — interleaved columns are still fluent English,
and nothing about the output says it is out of order — this adapter looks for a
column gutter and **warns** when it finds one. It is a heuristic and it says so;
it changes nothing about the extraction, it only tells the user the one thing
they could not otherwise have known.

License: pdfplumber is MIT, verified against the installed package metadata
(0.11.10) rather than taken from ``docs/research/RESEARCH.md``. Permissive, so
it may be imported into our process. It is in the core install: pure Python
over ``pdfminer.six`` and ``pypdfium2``, wheels on every platform in the CI
matrix, no system binary, no PyTorch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tokenmill.backends._common import (
    classify_failure,
    probe_module,
    render_markdown_table,
    source_as_file,
    warn_on_empty_output,
)
from tokenmill.core.errors import ConversionError
from tokenmill.core.models import (
    Availability,
    BackendInfo,
    ConvertOptions,
    Domain,
    LicenseTier,
    OutputFormat,
    Source,
)
from tokenmill.core.protocol import BaseConverter, ConversionContext

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = ["PdfplumberConverter"]

#: Ignore a gap smaller than this many PDF points between one table and the
#: next. Cropping a sliver of a page yields a stray fragment of a table border
#: rather than any text, and pdfplumber rejects a zero-height crop outright.
_MIN_BAND_HEIGHT = 2.0

# --- multi-column detection ------------------------------------------------
#
# Calibrated against the fixture corpus rather than guessed. Measuring the
# largest gap between adjacent word centres, as a fraction of page width:
#
#     simple.pdf    p0  10.8pt (1.8%)   single column
#     simple.pdf    p1   9.4pt (1.5%)   single column
#     tables.pdf    p0  23.9pt (3.9%)   single column with a 5-column table
#     twocolumn.pdf p0  37.8pt (6.2%)   two columns
#
# The thresholds below sit in the gap between 3.9% and 6.2%, with the balance
# and word-count conditions there to stop a short page or a lopsided one
# tripping it. This only ever raises a warning, so a false positive costs a
# sentence and a false negative costs nothing that was not already lost.

#: A gutter must be at least this many points wide, and at least this fraction
#: of the page width, to count as a column break.
_GUTTER_MIN_POINTS = 30.0
_GUTTER_MIN_FRACTION = 0.05

#: Each side of the gutter must hold at least this share of the page's words.
_GUTTER_MIN_BALANCE = 0.25

#: Below this many words there is not enough evidence to call it either way.
_GUTTER_MIN_WORDS = 50


class PdfplumberConverter(BaseConverter):
    """Converts digital PDFs to Markdown, preserving ruled tables.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="pdfplumber",
        name="pdfplumber",
        description=(
            "Digital PDFs with their tables intact. Best table fidelity in the "
            "core install; reads multi-column pages in the wrong order."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=("pdf",),
        output_formats=(OutputFormat.MARKDOWN,),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/jsvine/pdfplumber",
        install_extra=None,
        priority=40,
    )

    def _probe(self) -> Availability:
        """Check that pdfplumber is importable.

        Returns:
            Present when pdfplumber is installed, otherwise a missing
            dependency with the install command.
        """
        return probe_module("pdfplumber", hint="pip install tokenmill")

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Extract the PDF's text and tables, in document order.

        Args:
            source: The PDF to convert.
            options: Unused beyond what :class:`BaseConverter` already applied.
            context: Collects page and table counts, and any warning.

        Returns:
            The Markdown: page text with each detected table rendered as a
            Markdown table in the position it occupies on the page.

        Raises:
            ConversionError: If the file cannot be parsed. Damaged files become
                :class:`~tokenmill.core.errors.CorruptSource`; anything else
                becomes :class:`~tokenmill.core.errors.BackendFailed`.
        """
        del options

        # Imported here, not at module scope: CONTRIBUTING.md rule 3.
        import pdfplumber

        pages: list[str] = []
        table_count = 0
        multi_column: list[int] = []
        with source_as_file(source, self.info.id) as path:
            try:
                with pdfplumber.open(path) as pdf:
                    for number, page in enumerate(pdf.pages, start=1):
                        rendered, tables = _page_to_markdown(page)
                        table_count += tables
                        if _looks_multi_column(page):
                            multi_column.append(number)
                        if rendered.strip():
                            pages.append(rendered.strip())
                    page_count = len(pdf.pages)
            except ConversionError:
                raise
            except Exception as exc:
                raise classify_failure(exc, source=source, backend_id=self.info.id) from exc

        text = "\n\n".join(pages)
        if text and not text.endswith("\n"):
            text += "\n"

        context.note("page_count", page_count)
        context.note("tables_found", table_count)
        context.note("detects_headings", False)
        context.note("multi_column_pages", multi_column)
        if multi_column:
            pages_listed = ", ".join(str(number) for number in multi_column)
            context.warn(
                f"{source.name} looks multi-column on page(s) {pages_listed}. pdfplumber has no "
                f"layout model and reads a page in scan-line order, so the columns are very "
                f"likely interleaved in this output. This is a heuristic, not a certainty — "
                f"check the text, and try --backend pypdf or --backend kreuzberg, which read "
                f"columns in order"
            )
        warn_on_empty_output(
            text,
            source=source,
            context=context,
            reason=(
                f"pdfplumber found no text layer across {page_count} page(s), which is what a "
                f"scanned or image-only PDF looks like. Extracting text from page images needs "
                f"OCR, which tokenmill does not ship yet"
            ),
        )
        return text


def _page_to_markdown(page: Any) -> tuple[str, int]:
    """Render one page as Markdown, with its tables in place.

    Walks the page top to bottom: the text above each table, then the table,
    then on to the next. Splicing rather than appending is what keeps the
    document readable — a table dumped at the end of the page loses the prose
    that introduces it.

    Args:
        page: A ``pdfplumber.page.Page``.

    Returns:
        The page's Markdown, and how many tables were rendered.
    """
    try:
        tables = page.find_tables()
    except Exception:
        # A page whose table detection fails still has text worth extracting,
        # and losing the page would be a far worse outcome than losing a grid.
        return _text_or_empty(page), 0

    if not tables:
        return _text_or_empty(page), 0

    _, page_top, _, page_bottom = page.bbox
    parts: list[str] = []
    cursor = page_top
    rendered = 0

    for table in sorted(tables, key=lambda t: (t.bbox[1], t.bbox[0])):
        _, top, _, bottom = table.bbox
        above = _band(page, cursor, min(top, page_bottom))
        if above:
            parts.append(above)
        markdown = render_markdown_table(_table_rows(table))
        if markdown:
            parts.append(markdown.rstrip("\n"))
            rendered += 1
        cursor = max(cursor, min(bottom, page_bottom))

    below = _band(page, cursor, page_bottom)
    if below:
        parts.append(below)
    return "\n\n".join(parts), rendered


def _table_rows(table: Any) -> Sequence[Sequence[str | None]]:
    """Return a detected table's cells, or nothing if extraction fails.

    Args:
        table: A ``pdfplumber.table.Table``.

    Returns:
        The rows of cells; empty when the table could not be extracted.
    """
    try:
        rows = table.extract()
    except Exception:
        return ()
    return rows if rows else ()


def _band(page: Any, top: float, bottom: float) -> str:
    """Extract the text from a horizontal band of a page.

    Args:
        page: A ``pdfplumber.page.Page``.
        top: The band's upper edge, in PDF points from the top of the page.
        bottom: The band's lower edge.

    Returns:
        The band's text, stripped, or an empty string when the band is too thin
        to hold any or cropping it fails.
    """
    if bottom - top < _MIN_BAND_HEIGHT:
        return ""
    x0, _, x1, _ = page.bbox
    try:
        return (page.crop((x0, top, x1, bottom)).extract_text() or "").strip()
    except Exception:
        return ""


def _looks_multi_column(page: Any) -> bool:
    """Guess whether a page is laid out in more than one column.

    Looks for a vertical gutter: a wide gap in the distribution of word centres
    with a substantial share of the page's words on either side of it. Deliberately
    a guess and deliberately conservative — see the calibration table above the
    thresholds. It informs a warning and nothing else.

    Args:
        page: A ``pdfplumber.page.Page``.

    Returns:
        True when the page shows a column gutter.
    """
    try:
        words = page.extract_words()
    except Exception:
        return False
    if len(words) < _GUTTER_MIN_WORDS:
        return False

    centres = sorted((word["x0"] + word["x1"]) / 2 for word in words)
    threshold = max(_GUTTER_MIN_POINTS, page.width * _GUTTER_MIN_FRACTION)
    total = len(centres)
    for index in range(1, total):
        if centres[index] - centres[index - 1] < threshold:
            continue
        balance = min(index, total - index) / total
        if balance >= _GUTTER_MIN_BALANCE:
            return True
    return False


def _text_or_empty(page: Any) -> str:
    """Extract a page's text, treating failure as an empty page.

    Args:
        page: A ``pdfplumber.page.Page``.

    Returns:
        The page's text, or an empty string.
    """
    try:
        return (page.extract_text() or "").strip()
    except Exception:
        return ""
