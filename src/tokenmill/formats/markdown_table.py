"""GitHub-flavoured Markdown pipe tables.

The baseline every other format is measured against, because it is what the
converters actually emit: `pdfplumber` recovers `tables.pdf` as one of these,
and `compare --formats` starts by reading one back.

The decoder is deliberately more forgiving than the encoder. It has to read
tables written by thirteen backends and by hand, so it accepts rows with or
without leading and trailing pipes and ignores the delimiter row's alignment
colons. The encoder emits one canonical shape.
"""

from __future__ import annotations

import re
from typing import Final

from tokenmill.formats.base import BaseTableEncoder, Table, TableError

__all__ = ["MarkdownTableEncoder"]

#: A GFM delimiter row: pipes, dashes, colons and spaces, with at least one dash.
_DELIMITER_RE: Final = re.compile(r"^[ \t]*\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")


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
        # split("\n"), never splitlines(): the latter also breaks on U+0085,
        # U+2028, U+2029, \x0b and \x0c, which are ordinary cell content and
        # would be torn across rows. Found by the round-trip property test.
        lines = [line for line in text.split("\n") if line.strip()]
        for index, line in enumerate(lines[:-1]):
            if "|" not in line or not _DELIMITER_RE.match(lines[index + 1]):
                continue
            headers = _split(line)
            body = []
            for candidate in lines[index + 2 :]:
                if "|" not in candidate:
                    break
                body.append(_split(candidate))
            return Table.of(headers, body)
        msg = "no Markdown table found: a header row must be followed by a delimiter row"
        raise TableError(msg)


def _escape(cell: str) -> str:
    """Escape a cell for a pipe table.

    Args:
        cell: The raw value.

    Returns:
        The value with backslashes and pipes escaped and line breaks flattened.
    """
    escaped = cell.replace("\\", "\\\\").replace("|", "\\|")
    return escaped.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _split(line: str) -> list[str]:
    r"""Split one pipe row into unescaped cells.

    Splits on unescaped pipes only, so a cell containing ``\\|`` survives.

    Args:
        line: The row.

    Returns:
        The cell values.
    """
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\\|"):
        stripped = stripped[:-1]

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
    return cells
