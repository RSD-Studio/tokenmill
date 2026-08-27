r"""GitHub-flavoured Markdown pipe tables, and the one parser that reads them.

The baseline every other format is measured against, because it is what the
converters actually emit: `pdfplumber` recovers `tables.pdf` as one of these,
and `compare --formats` starts by reading one back.

The decoder is deliberately more forgiving than the encoder. It has to read
tables written by thirteen backends and by hand, so it accepts rows with or
without leading and trailing pipes and ignores the delimiter row's alignment
colons. The encoder emits one canonical shape.

**This module owns pipe-table parsing for the whole project** (defect N3). Until
Phase 7 there were two implementations: this one and a second in
`tokenmill.fidelity.markdown`, written separately and deliberately differing in
strictness. Two parsers for one syntax is one bug reported twice and fixed once,
so they are now a single :func:`scan_tables` with the difference expressed as an
argument rather than as duplicated code.

The difference is real and worth keeping, which is why it is a flag and not a
merge to the stricter of the two:

* **Round-tripping a table** (`unescape=True`) must undo the escaping
  :func:`_escape` applies, or `\\|` inside a cell tears the row in half.
* **Measuring fidelity** (`unescape=False`) must not. It counts cells in text a
  converter produced, which was never escaped by us, so treating a backslash as
  an escape character would silently alter the content being scored.

What each caller does *before* scanning still differs, and legitimately so:
fidelity drops fenced code blocks first, because a `|` in a shell script is a
pipe operator; the encoder drops blank lines instead. Line preparation is the
caller's; recognising a table is this module's.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from tokenmill.formats.base import BaseTableEncoder, Table, TableError

__all__ = ["MarkdownTableEncoder", "is_delimiter_row", "scan_tables", "split_row"]

#: A GFM delimiter row: pipes, dashes, colons and spaces, with at least one dash.
_DELIMITER_RE: Final = re.compile(r"^[ \t]*\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")


def is_delimiter_row(line: str) -> bool:
    """Return whether ``line`` is a GFM table delimiter row.

    This is what separates a table from a line that merely contains pipes, and
    it is the whole reason the `table_integrity` fidelity component can tell a
    surviving table from a flattened one: a backend that mangles a table often
    leaves the pipes behind but not the delimiter.

    Args:
        line: The line to test.

    Returns:
        True when the line is a delimiter row.
    """
    return "|" in line and _DELIMITER_RE.match(line) is not None


def split_row(line: str, *, unescape: bool = True) -> tuple[str, ...]:
    r"""Split one pipe-delimited row into its cell values.

    Args:
        line: The row, with or without leading and trailing pipes.
        unescape: Treat ``\|`` and ``\\`` as escapes, as :meth:`
            MarkdownTableEncoder.encode` writes them. Pass ``False`` when
            reading text this project did not encode — see the module
            docstring.

    Returns:
        The trimmed cell values.
    """
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not (unescape and stripped.endswith("\\|")):
        stripped = stripped[:-1]

    if not unescape:
        return tuple(cell.strip() for cell in stripped.split("|"))

    cells: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(stripped):
        char = stripped[index]
        if char == "\\" and index + 1 < len(stripped) and stripped[index + 1] in "\\|":
            current.append(stripped[index + 1])
            index += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return tuple(cells)


def scan_tables(
    lines: Sequence[str],
    *,
    unescape: bool = True,
    limit: int | None = None,
) -> list[tuple[tuple[str, ...], ...]]:
    """Find every pipe table in an already-prepared sequence of lines.

    A run of pipe-bearing lines is only a table when a delimiter row follows the
    header. That strictness is deliberate and is what makes the
    `table_integrity` fidelity component mean anything.

    The delimiter row is not returned: it is punctuation, not data.

    Args:
        lines: The lines to scan. **Prepared by the caller** — this function
            does no fence-stripping and no blank-line filtering, because the two
            callers legitimately want different preparation.
        unescape: Passed to :func:`split_row`.
        limit: Stop after this many tables. ``None`` finds all of them.

    Returns:
        One entry per table, each a tuple of rows, each row a tuple of cells.
        The header is the first row.
    """
    found: list[tuple[tuple[str, ...], ...]] = []
    index = 0
    while index < len(lines):
        header = lines[index]
        if "|" not in header or index + 1 >= len(lines):
            index += 1
            continue
        if not is_delimiter_row(lines[index + 1]):
            index += 1
            continue

        rows = [split_row(header, unescape=unescape)]
        cursor = index + 2
        while cursor < len(lines) and "|" in lines[cursor]:
            rows.append(split_row(lines[cursor], unescape=unescape))
            cursor += 1
        found.append(tuple(rows))
        if limit is not None and len(found) >= limit:
            return found
        index = cursor
    return found


class MarkdownTableEncoder(BaseTableEncoder):
    """Encodes a table as a GFM pipe table.

    Attributes:
        id: ``markdown``.
        name: Display name.
        description: One-line summary.
        media_type: ``text/markdown``.
    """

    id = "markdown"
    name = "Markdown table"
    description = "A GitHub-flavoured pipe table, the shape converters emit."
    media_type = "text/markdown"

    def encode(self, table: Table) -> str:
        """Serialise a table as a pipe table.

        Args:
            table: The table to serialise.

        Returns:
            The Markdown, ending in a newline.

        Note:
            **The two lossy cases in this package**, both of them GFM's limits
            rather than this encoder's, and both documented instead of papered
            over with a non-standard escape that other tools could not read:

            * A pipe table is line-oriented, so a cell containing a line break
              cannot be represented; the break becomes a space.
            * Cell padding is not content, so leading and trailing whitespace
              in a cell is lost. Every Markdown renderer strips it.

            Backslashes and pipes are escaped and round-trip exactly. The
            round-trip property test draws cells without those two properties
            for this format and with them for every other.
        """
        rows = [
            self._row(table.headers),
            "| " + " | ".join("---" for _ in table.headers) + " |",
            *(self._row(row) for row in table.rows),
        ]
        return "\n".join(rows) + "\n"

    @staticmethod
    def _row(cells: tuple[str, ...]) -> str:
        """Render one row.

        Args:
            cells: The cell values.

        Returns:
            The pipe-delimited row.
        """
        return "| " + " | ".join(_escape(cell) for cell in cells) + " |"

    def decode(self, text: str) -> Table:
        """Read the first pipe table out of ``text``.

        Args:
            text: Markdown containing a table.

        Returns:
            The table.

        Raises:
            TableError: If no pipe table with a delimiter row is present.
        """
        tables = self.decode_all(text, limit=1)
        if not tables:
            msg = "no Markdown table found: a header row must be followed by a delimiter row"
            raise TableError(msg)
        return tables[0]

    def decode_all(self, text: str, *, limit: int | None = None) -> tuple[Table, ...]:
        """Read every pipe table out of ``text``, in document order.

        Defect N4: ``compare --formats`` re-encoded only the first table in a
        document, which is fine on a fixture with one and wrong on a real
        report. Nothing about reading a table was ever limited to the first —
        :func:`scan_tables` has always found them all — so this is the function
        :meth:`decode` should have been built on.

        Args:
            text: Markdown that may contain tables.
            limit: Stop after this many. ``None`` finds all of them.

        Returns:
            The tables, in the order they appear. Empty when there are none;
            unlike :meth:`decode` this does not raise, because "how many tables
            are in here" is a question with a legitimate answer of zero.
        """
        # split("\n"), never splitlines(): the latter also breaks on U+0085,
        # U+2028, U+2029, \x0b and \x0c, which are ordinary cell content and
        # would be torn across rows. Found by the round-trip property test.
        lines = [line for line in text.split("\n") if line.strip()]
        return tuple(
            Table.of(list(rows[0]), [list(row) for row in rows[1:]])
            for rows in scan_tables(lines, unescape=True, limit=limit)
        )


def _escape(cell: str) -> str:
    """Escape a cell for a pipe table.

    Args:
        cell: The raw value.

    Returns:
        The value with backslashes and pipes escaped and line breaks flattened.
    """
    escaped = cell.replace("\\", "\\\\").replace("|", "\\|")
    return escaped.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
