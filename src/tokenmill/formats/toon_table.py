"""TOON — Token-Oriented Object Notation, tabular form.

Implemented here rather than wrapped, which is a departure from this project's
usual rule and needs its reasons on the record. All three were checked on
2026-08-24, not taken from `RESEARCH.md`:

1. **The official Python port is a stub.** `toon-format` 0.1.0 on PyPI is the
   package under the format's own GitHub organisation, ships `py.typed` and a
   complete API surface, and both entry points raise::

       >>> toon_format.encode({"a": 1})
       NotImplementedError: TOON encoder is not yet implemented

2. **The third-party ports diverge from the specification's own canonical
   output.** `toon-py` 1.0.2 works and round-trips, but emits `users[2,]{...}`
   where the spec writes `users[2]{...}` — §6 makes the delimiter in the
   bracket segment optional and comma the default. A redundant character in
   every array header is a small thing, except that the format's entire claim
   is token efficiency.

3. **The acceptance criterion is lossless round-tripping**, and that can only
   be guaranteed for an encoder and decoder written as a pair.

Against those: writing a serialiser is not the same as writing a converter, so
"wrap the best tool" does not apply the way it does to a PDF reader. And it
costs no dependency at all, which matters while defect D4 is open.

**What this implements**, from the specification (Working Draft 4.1, MIT,
`github.com/toon-format/spec`, fetched 2026-08-24):

* the tabular form for an array of uniform objects — `§9.3`, the shape a
  document's table has and the only shape `RESEARCH.md` finds TOON reliably
  wins on;
* string quoting and escaping — `§7.1`, `§7.2`;
* key encoding — `§7.3`;
* LF line endings and two-space indentation — `§1.2`, `§1.3`.

**What it does not implement**: list form, keyed tabular form, nested field
groups, non-comma delimiters, length markers, and the strict-mode validator.
Those are for values this package never produces, because a :class:`Table` is
by construction an array of uniform flat objects. A document naming any of them
will not decode here, and says so rather than guessing.

**Conformance to the reference implementation is unverified.** The reference is
TypeScript and cannot be run in this environment. What is verified is that this
encoder and decoder round-trip every table the property tests generate, and that
the output matches the specification's own worked examples.

`RESEARCH.md` Category 7's framing is the honest one and is not softened here:
TOON's wins are **real but narrow** — uniform arrays only — and
model-dependent. Independent work (Matveev, arXiv:2603.03306) finds that as
structure moves from aligned to non-aligned, *"TOON performance collapses"*, to
0% one-shot accuracy on a nested case. This encoder deliberately covers only the
aligned shape, which is the shape the evidence supports.
"""

from __future__ import annotations

import re
from typing import Final

from tokenmill.formats._scalars import renders_natively
from tokenmill.formats.base import (
    BaseTableEncoder,
    Table,
    TableError,
    require_named_columns,
)

__all__ = ["ToonTableEncoder"]

#: A key that may be emitted unquoted (spec §7.3).
_BARE_KEY_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

#: A string that looks like a number and must therefore be quoted (spec §7.2),
#: so that a decoder cannot mistake the string "42" for the number 42.
_NUMERIC_RE: Final = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$", re.IGNORECASE)

#: The header of a tabular array (spec §6), with the default comma delimiter.
_HEADER_RE: Final = re.compile(r"^(?P<key>.*?)\[(?P<length>\d+)\]\{(?P<fields>.*)\}:$")

#: Characters that force quoting wherever they appear in a value (spec §7.2).
_FORCE_QUOTE: Final = frozenset(':"\\[]{},')

#: Escapes, spec §7.1. Ordered so the backslash rule is applied first.
_ESCAPES: Final = (("\\", "\\\\"), ('"', '\\"'), ("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t"))

#: The key this encoder files a table's rows under. TOON needs a name for the
#: array; a bare table has none, so one is chosen and the decoder accepts any.
DEFAULT_KEY: Final = "rows"


class ToonTableEncoder(BaseTableEncoder):
    """Encodes a table in TOON's tabular form.

    Attributes:
        id: ``toon``.
        name: Display name.
        description: One-line summary.
        media_type: ``text/plain``, which is what the specification registers
            nothing better than at Working Draft status.
    """

    id = "toon"
    name = "TOON"
    description = (
        "Token-Oriented Object Notation, tabular form: field names declared "
        "once, then one row per record."
    )
    media_type = "text/plain"

    def encode(self, table: Table) -> str:
        """Serialise a table in TOON tabular form.

        Args:
            table: The table to serialise.

        Returns:
            The TOON document, ending in a newline. The saving over JSON comes
            from declaring the field names once in the header instead of
            repeating them on every row — which is exactly what `RESEARCH.md`
            attributes it to, and is why the saving grows with row count and
            vanishes at one row.
        """
        require_named_columns(table, "TOON")
        fields = ",".join(_encode_key(header) for header in table.headers)
        lines = [f"{DEFAULT_KEY}[{len(table.rows)}]{{{fields}}}:"]
        lines.extend("  " + ",".join(_encode_value(cell) for cell in row) for row in table.rows)
        return "\n".join(lines) + "\n"

    def decode(self, text: str) -> Table:
        """Read a table back from TOON tabular form.

        Args:
            text: The TOON document.

        Returns:
            The table.

        Raises:
            TableError: If the document is not a single tabular array, if the
                declared length disagrees with the number of rows, or if a row
                has the wrong number of cells. Each is a strict-mode error in
                the specification and none is guessed past: a length that does
                not match its rows means the document was truncated, and
                returning the rows anyway would hide that.
        """
        # split("\n") per spec 1.2, and never splitlines(): the latter also
        # breaks on U+0085 and friends, which are legal inside a cell.
        lines = [line for line in text.replace("\r\n", "\n").split("\n") if line.strip(" \t")]
        if not lines:
            msg = "no TOON content"
            raise TableError(msg)

        match = _HEADER_RE.match(lines[0].strip())
        if match is None:
            msg = (
                f"not a TOON tabular array header: {lines[0].strip()!r}. This decoder "
                f"reads the tabular form only; list and keyed forms are not supported"
            )
            raise TableError(msg)

        headers = tuple(_decode_token(field) for field in _split_cells(match.group("fields")))
        declared = int(match.group("length"))
        rows = []
        for line in lines[1:]:
            cells = [_decode_token(cell) for cell in _split_cells(line.strip())]
            if len(cells) != len(headers):
                msg = (
                    f"row has {len(cells)} cells, header declares {len(headers)} fields: "
                    f"{line.strip()!r}"
                )
                raise TableError(msg)
            rows.append(tuple(cells))

        if len(rows) != declared:
            msg = f"header declares {declared} rows, document carries {len(rows)}"
            raise TableError(msg)
        return Table.of(headers, rows)


def _encode_key(key: str) -> str:
    """Encode a field name, quoting it when the specification requires it.

    Args:
        key: The field name.

    Returns:
        The encoded name (spec §7.3).
    """
    return key if _BARE_KEY_RE.match(key) else _quote(key)


def _encode_value(value: str) -> str:
    """Encode a cell, quoting it when the specification requires it.

    Every cell here is a string, so anything that could be read back as a
    number, a boolean or null must be quoted — otherwise the round trip would
    silently change the value's type.

    Args:
        value: The cell.

    Returns:
        The encoded cell (spec §7.2).
    """
    # A cell that renders back identically as a JSON scalar is written bare:
    # it really is that number, and quoting it would cost two characters per
    # numeric cell in a format whose entire claim is token efficiency. Anything
    # else that could be *misread* as a scalar must be quoted (spec 7.2), or
    # the round trip would change its type.
    if renders_natively(value):
        return value
    if (
        not value
        # Python-whitespace rather than the spec's minimum of space and tab:
        # U+0085, U+2028 and \x0b are whitespace to str.strip() but not to the
        # spec, so an unquoted cell made of one would be trimmed away by any
        # decoder that strips its lines. Quoting more than 7.2 requires is
        # always permitted; losing a cell is not.
        or value != value.strip()
        or value in {"true", "false", "null"}
        or _NUMERIC_RE.match(value)
        or any(char in _FORCE_QUOTE for char in value)
        or any(ord(char) < 0x20 for char in value)
        or value.startswith(("-", "#"))
    ):
        return _quote(value)
    return value


def _quote(value: str) -> str:
    """Quote and escape a string per spec §7.1.

    Args:
        value: The raw string.

    Returns:
        The quoted, escaped string.
    """
    escaped = value
    for raw, replacement in _ESCAPES:
        escaped = escaped.replace(raw, replacement)
    escaped = "".join(char if ord(char) >= 0x20 else f"\\u{ord(char):04x}" for char in escaped)
    return f'"{escaped}"'


def _split_cells(line: str) -> list[str]:
    """Split a comma-delimited row, respecting quoted cells.

    Args:
        line: The row.

    Returns:
        The raw cell tokens, still quoted where they were quoted.

    Raises:
        TableError: If a quoted cell is never closed.
    """
    cells: list[str] = []
    current: list[str] = []
    in_quotes = False
    index = 0
    while index < len(line):
        char = line[index]
        if in_quotes:
            if char == "\\" and index + 1 < len(line):
                current.append(line[index : index + 2])
                index += 2
                continue
            if char == '"':
                in_quotes = False
            current.append(char)
            index += 1
            continue
        if char == '"':
            in_quotes = True
            current.append(char)
            index += 1
            continue
        if char == ",":
            cells.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1

    if in_quotes:
        msg = f"unterminated quoted value in {line!r}"
        raise TableError(msg)
    cells.append("".join(current))
    return cells


def _decode_token(token: str) -> str:
    """Decode one cell or field name back to its string value.

    Args:
        token: The raw token, quoted or not.

    Returns:
        The value. Unquoted tokens are returned as written: this package's
        tables hold strings, so ``42`` read back is the two characters, and a
        conforming encoder would have quoted it had it been the string ``"42"``
        — which is why :func:`_encode_value` quotes numeric-looking strings.

    Raises:
        TableError: If a quoted token carries an escape the specification does
            not define.
    """
    # Spec 12 trims spaces and tabs only.
    stripped = token.strip(" \t")
    if not (len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"')):
        return stripped

    body = stripped[1:-1]
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        if index + 1 >= len(body):
            msg = f"trailing backslash in {token!r}"
            raise TableError(msg)
        marker = body[index + 1]
        simple = {"\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t"}
        if marker in simple:
            out.append(simple[marker])
            index += 2
            continue
        if marker == "u":
            hex_digits = body[index + 2 : index + 6]
            if len(hex_digits) != 4 or any(c not in "0123456789abcdefABCDEF" for c in hex_digits):
                msg = f"malformed \\u escape in {token!r}"
                raise TableError(msg)
            out.append(chr(int(hex_digits, 16)))
            index += 6
            continue
        msg = f"undefined escape {marker!r} in {token!r}"
        raise TableError(msg)
    return "".join(out)
