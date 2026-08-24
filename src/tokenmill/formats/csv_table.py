"""RFC 4180 comma-separated values.

`RESEARCH.md` Category 7 records CSV as both the cheapest and one of the
weakest formats depending on whose test you read: GetCrux measured it using
~56% fewer tokens than JSON *with higher accuracy*, and ImprovingAgents'
eleven-format test found CSV among the weakest on comprehension at ~44.3%.
Both are in the docs; neither is restated here as a recommendation.

The stdlib `csv` module does the work, which is the point — quoting, embedded
delimiters, embedded newlines and doubled quotes are RFC 4180's problem and it
has already solved them.
"""

from __future__ import annotations

import csv
import io

from tokenmill.formats.base import BaseTableEncoder, Table, TableError

__all__ = ["CsvTableEncoder"]


class CsvTableEncoder(BaseTableEncoder):
    """Encodes a table as RFC 4180 CSV.

    Attributes:
        id: ``csv``.
        name: Display name.
        description: One-line summary.
        media_type: ``text/csv``.
    """

    id = "csv"
    name = "CSV"
    description = "RFC 4180 comma-separated values, header row first."
    media_type = "text/csv"

    def encode(self, table: Table) -> str:
        """Serialise a table as CSV.

        Args:
            table: The table to serialise.

        Returns:
            The CSV, with LF line endings rather than RFC 4180's CRLF. LF is
            what every other encoder here emits and what the token count is
            taken over; a stray CR per row would be a real and misleading
            difference in the comparison this package exists to support.
        """
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(table.headers)
        writer.writerows(table.rows)
        return buffer.getvalue()

    def decode(self, text: str) -> Table:
        """Read a table back from CSV.

        Args:
            text: The CSV.

        Returns:
            The table.

        Raises:
            TableError: If the text has no header row.
        """
        rows = list(csv.reader(io.StringIO(text, newline="")))
        if not rows:
            msg = "no CSV content: a header row is required"
            raise TableError(msg)
        return Table.of(rows[0], rows[1:])
