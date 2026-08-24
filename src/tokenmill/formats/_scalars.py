"""Deciding when a cell may be written as a number, and still read back exactly.

A :class:`~tokenmill.formats.base.Table` holds strings, because that is what a
converter lifts off a page. But writing every cell as a string would distort the
one measurement this package exists to make: CSV writes ``9.99`` bare while JSON
and TOON would write ``"9.99"``, so a comparison of the three would credit CSV
with two characters per numeric cell that a real application would never have
spent. The format that looked cheapest would be the one whose quoting rules we
had sidestepped.

So a cell is written as a native number, boolean or null **exactly when doing so
round-trips to the identical string**, and as a quoted string otherwise. The
test is not "does it look numeric" but "does rendering the parsed value
reproduce the original characters", which is strictly stronger and is what keeps
the property tests honest:

===========  =========================  ==========================================
Cell         Written as                 Why
===========  =========================  ==========================================
``9.99``     number ``9.99``            ``9.99`` renders back identically
``42``       number ``42``              likewise
``05``       string ``"05"``            JSON forbids the leading zero; ``5`` would
                                        come back
``+1``       string ``"+1"``            not valid JSON; ``1`` would come back
``1e-6``     string ``"1e-6"``          renders back as ``1e-06``
``true``     boolean ``true``           renders back identically
``TRUE``     string ``"TRUE"``          renders back as ``true``
===========  =========================  ==========================================

The asymmetry is deliberate. A cell is only ever *demoted* to a quoted string,
never promoted into a value it cannot become again, so no round trip can lose a
leading zero or reformat an exponent.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["as_cell", "as_native", "renders_natively"]


def as_native(cell: str) -> Any:
    """Return the native value a cell may safely be written as.

    Args:
        cell: The cell's string value.

    Returns:
        An ``int``, ``float``, ``bool`` or ``None`` when writing the cell as
        that value renders back to exactly these characters; otherwise the
        string unchanged.
    """
    if not renders_natively(cell):
        return cell
    return json.loads(cell)


def renders_natively(cell: str) -> bool:
    """Report whether a cell survives being written as a native JSON value.

    Args:
        cell: The cell's string value.

    Returns:
        True when parsing the cell and rendering it again reproduces it
        character for character.
    """
    if not cell or cell.strip() != cell:
        return False
    try:
        parsed = json.loads(cell)
    except ValueError:
        return False
    if isinstance(parsed, (str, list, dict)):
        return False
    if isinstance(parsed, float) and (parsed != parsed or parsed in (float("inf"), float("-inf"))):
        return False
    return json.dumps(parsed) == cell


def as_cell(value: Any) -> str:
    """Return the string a decoded value belongs in.

    The inverse of :func:`as_native`. Rendering with ``json.dumps`` rather than
    ``str`` is what makes it exact: ``str(True)`` is ``"True"`` and would not
    round-trip, while ``json.dumps(True)`` is ``"true"``, which is the text the
    encoder wrote.

    Args:
        value: A value read back out of an encoded document.

    Returns:
        Its cell string.
    """
    if isinstance(value, str):
        return value
    return json.dumps(value)
