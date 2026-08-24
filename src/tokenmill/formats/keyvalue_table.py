"""Markdown-KV: one ``key: value`` block per row.

`RESEARCH.md` Category 7 records this as the accuracy winner and the token
loser of an eleven-format test: it *"topped an 11-format test at ~60.7%
accuracy, ~16 points ahead of CSV, but used more tokens"*.

It is in this package precisely because it loses on tokens. A comparison that
only offered formats which win would be a machine for picking whichever one
this project happened to like, and the Phase 10 harness rule — treat every
option identically, report the result that contradicts the expectation —
applies to formats as much as to backends.
"""

from __future__ import annotations

import json

from tokenmill.formats.base import (
    BaseTableEncoder,
    Table,
    TableError,
    require_named_columns,
)

__all__ = ["KeyValueTableEncoder"]


class KeyValueTableEncoder(BaseTableEncoder):
    """Encodes a table as blocks of ``key: value`` lines.

    Attributes:
        id: ``keyvalue``.
        name: Display name.
        description: One-line summary.
        media_type: ``text/plain``.
    """

    id = "keyvalue"
    name = "Key-value"
    description = (
        "One 'key: value' line per field, one blank-line-separated block per "
        "row. Costs the most tokens; scores best on comprehension in the one "
        "published test that compares them."
    )
    media_type = "text/plain"

    def encode(self, table: Table) -> str:
        """Serialise a table as key-value blocks.

        Args:
            table: The table to serialise.

        Returns:
            The encoded text, ending in a newline.
        """
        require_named_columns(table, "Key-value")
        blocks = [
            "\n".join(
                f"{_encode_token(header)}: {_encode_token(cell)}"
                for header, cell in zip(table.headers, row, strict=False)
            )
            for row in table.rows
        ]
        if not blocks:
            # An empty table still has to carry its columns, or decoding gives
            # a table with no headers rather than a table with no rows.
            return "\n".join(f"{_encode_token(h)}:" for h in table.headers) + "\n"
        return "\n\n".join(blocks) + "\n"

    def decode(self, text: str) -> Table:
        """Read a table back from key-value blocks.

        Args:
            text: The encoded text.

        Returns:
            The table.

        Raises:
            TableError: If a line carries no colon, or a block's keys differ
                from the first block's.
        """
        blocks = [block for block in text.split("\n\n") if block.strip()]
        if not blocks:
            msg = "no key-value content"
            raise TableError(msg)

        parsed: list[list[tuple[str, str]]] = []
        empty_marker = True
        for block in blocks:
            pairs: list[tuple[str, str]] = []
            # split("\n"), never splitlines(): see the Markdown encoder.
            for line in block.split("\n"):
                if not line.strip():
                    continue
                key, separator, value = _partition(line)
                if not separator:
                    msg = f"line carries no colon: {line!r}"
                    raise TableError(msg)
                # A table with no rows is written as bare `key:` lines with
                # nothing after the colon. A single row whose cells are all
                # empty strings is written as `key: ""`. Deciding on the raw
                # text keeps those apart; deciding on the decoded value did
                # not, and the round-trip property test caught it.
                if value.strip():
                    empty_marker = False
                pairs.append((_decode_token(key.strip()), _decode_token(value.strip())))
            parsed.append(pairs)

        headers = tuple(key for key, _ in parsed[0])
        if len(parsed) == 1 and empty_marker:
            return Table.of(headers, ())
        rows = []
        for pairs in parsed:
            if tuple(key for key, _ in pairs) != headers:
                msg = "every block must carry the same keys in the same order"
                raise TableError(msg)
            rows.append(tuple(value for _, value in pairs))
        return Table.of(headers, rows)


def _encode_token(token: str) -> str:
    """Quote a key or value that would otherwise not survive the round trip.

    Args:
        token: The raw string.

    Returns:
        The string as-is when it is unambiguous, otherwise its JSON-quoted
        form. Quoting is needed for anything empty, carrying a line break, a
        colon or surrounding whitespace, or already starting with a quote —
        each of which would otherwise be read back as a different value or as
        a block boundary.
    """
    if (
        not token
        or token != token.strip()
        or ":" in token
        or "\n" in token
        or "\r" in token
        or token.startswith('"')
    ):
        return json.dumps(token, ensure_ascii=False)
    return token


def _decode_token(token: str) -> str:
    """Reverse :func:`_encode_token`.

    Args:
        token: The encoded string.

    Returns:
        The raw value.

    Raises:
        TableError: If a quoted token is malformed.
    """
    if not token.startswith('"'):
        return token
    try:
        value = json.loads(token)
    except json.JSONDecodeError as exc:
        msg = f"malformed quoted value {token!r}"
        raise TableError(msg) from exc
    if not isinstance(value, str):
        msg = f"quoted value is not a string: {token!r}"
        raise TableError(msg)
    return value


def _partition(line: str) -> tuple[str, str, str]:
    """Split a line at the colon that separates its key from its value.

    A quoted key may itself contain a colon — a column literally named ``:``
    encodes to ``":":`` — so splitting at the first colon in the line cuts
    inside the quotes and produces a key of ``"``. Found by the round-trip
    property test.

    Args:
        line: The line to split.

    Returns:
        The key text, the separator (empty when there is none), and the value
        text.
    """
    if line.lstrip().startswith('"'):
        start = line.index('"')
        index = start + 1
        while index < len(line):
            if line[index] == "\\":
                index += 2
                continue
            if line[index] == '"':
                key, separator, value = line[: index + 1], "", ""
                remainder = line[index + 1 :]
                if remainder.lstrip().startswith(":"):
                    separator = ":"
                    value = remainder.split(":", 1)[1]
                return key, separator, value
            index += 1
        msg = f"unterminated quoted key: {line!r}"
        raise TableError(msg)
    return line.partition(":")
