"""JSON, as an array of objects.

The format everything else is compared against, because it is what an
application already has. `RESEARCH.md` Category 7's headline comparisons —
TOON's 42.6% fewer tokens, CSV's ~56% fewer — are all measured against this
shape, so it is the one that has to be right.

Emitted compactly. A pretty-printed variant would cost tokens for whitespace
nobody reads, and the whole point of the comparison is what the model is
charged.
"""

from __future__ import annotations

import json
from typing import Any

from tokenmill.formats._scalars import as_cell, as_native
from tokenmill.formats.base import (
    BaseTableEncoder,
    Table,
    TableError,
    require_named_columns,
)

__all__ = ["JsonTableEncoder"]


class JsonTableEncoder(BaseTableEncoder):
    """Encodes a table as a JSON array of objects.

    Attributes:
        id: ``json``.
        name: Display name.
        description: One-line summary.
        media_type: ``application/json``.
    """

    id = "json"
    name = "JSON"
    description = "A compact JSON array of objects, one per row."
    media_type = "application/json"

    def encode(self, table: Table) -> str:
        """Serialise a table as JSON.

        Args:
            table: The table to serialise.

        Returns:
            The JSON, ending in a newline. A cell is written as a bare number,
            boolean or null when that renders back to the identical string, and
            as a quoted string otherwise — see :mod:`tokenmill.formats._scalars`
            for why the test is "renders back identically" rather than "looks
            numeric".
        """
        require_named_columns(table, "JSON")
        payload = [
            {header: as_native(cell) for header, cell in zip(table.headers, row, strict=False)}
            for row in table.rows
        ]
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

    def decode(self, text: str) -> Table:
        """Read a table back from JSON.

        Args:
            text: The JSON.

        Returns:
            The table. Header order follows the first object's key order, which
            is what :meth:`encode` wrote and what ``json`` preserves.

        Raises:
            TableError: If the text is not a JSON array of objects, or the
                objects disagree about their keys.
        """
        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError as exc:
            msg = f"not valid JSON: {exc}"
            raise TableError(msg) from exc
        if not isinstance(payload, list):
            msg = "expected a JSON array of objects"
            raise TableError(msg)
        if not payload:
            # An array of objects carries its column names on the objects, so
            # zero rows means zero recoverable columns. Format-inherent, like
            # the Markdown encoder's line breaks: the alternative is a wrapper
            # object on every table, which would add tokens to every row of
            # every comparison to serve an edge case that carries no data.
            return Table.of((), ())
        if not all(isinstance(item, dict) for item in payload):
            msg = "expected every element to be a JSON object"
            raise TableError(msg)

        headers = tuple(payload[0])
        rows = []
        for item in payload:
            if tuple(item) != headers:
                msg = "every object must carry the same keys in the same order"
                raise TableError(msg)
            rows.append(tuple(as_cell(value) for value in item.values()))
        return Table.of(headers, rows)
