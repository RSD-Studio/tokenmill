"""Tabular data, and the encoders that serialise it.

`RESEARCH.md` Category 7 is the reason this package exists: the same table costs
very different amounts depending on how it is serialised, and the differences
are large enough to matter and narrow enough to be easy to overstate. A user
should be able to measure it **on their own data** rather than take anyone's
benchmark, which is what `tokenmill compare --formats` is for.

**Cells are strings, and every encoder is exactly lossless.**

This is the load-bearing decision in the package and it deserves its reasoning.
A Markdown table lifted out of a PDF contains text: `9.99` in a price column is
the four characters a converter read off the page, not a float. An encoder that
"helpfully" emitted it as a JSON number would not round-trip — `05` comes back
as `5`, and `1e-6` as `1e-06` — so the acceptance criterion for this package
(lossless round-trips, proven by property tests) would be met only for tables
that happen not to contain those.

Keeping cells as strings also makes the token comparison *fair*: every format is
handed identical data and the difference measured is the format's own overhead.
TOON still wins where `RESEARCH.md` says it wins — by declaring the field names
once instead of repeating them per row — rather than by silently dropping quotes
that JSON was made to carry.

Encoders register through the `tokenmill.formats` entry point group, the same
mechanism backends, post-processors and tokenizers use. There is no hard-coded
list.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Final, Protocol, runtime_checkable

__all__ = [
    "FORMAT_ENTRY_POINT_GROUP",
    "BaseTableEncoder",
    "Table",
    "TableEncoder",
    "TableEncoderRegistry",
    "TableError",
    "default_format_registry",
    "require_named_columns",
    "reset_default_format_registry",
]

#: The entry point group table-encoder plugins register under.
FORMAT_ENTRY_POINT_GROUP: Final = "tokenmill.formats"

_log = logging.getLogger(__name__)


class TableError(ValueError):
    """Raised when text cannot be read back as a table.

    A ``ValueError`` rather than a ``ConversionError``: decoding a table is not
    a conversion, and the taxonomy in ``docs/ARCHITECTURE.md`` describes what a
    backend does to a source. Growing it per package is the failure mode the
    Phase 0-4 review was checking for.
    """


@dataclass(frozen=True, slots=True)
class Table:
    """A header row and its data rows, every cell a string.

    Attributes:
        headers: The column names, in order.
        rows: One tuple of cells per data row. Every row has as many cells as
            there are headers; :meth:`validated` is how that is enforced.
    """

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    @classmethod
    def of(cls, headers: Sequence[str], rows: Iterable[Sequence[str]]) -> Table:
        """Build a table, padding and truncating rows to the header's width.

        Real converter output is ragged: a backend that mis-splits a header row
        emits rows of differing widths, and refusing to represent that would
        mean this package could not encode the very output it exists to
        measure.

        Args:
            headers: The column names.
            rows: The data rows.

        Returns:
            The table, with every row exactly as wide as ``headers``.
        """
        width = len(headers)
        fixed = tuple(tuple([*row, *([""] * (width - len(row)))][:width]) for row in rows)
        return cls(headers=tuple(headers), rows=fixed)

    @property
    def cells(self) -> int:
        """Count every data cell, excluding the header row.

        Returns:
            The number of cells.
        """
        return len(self.rows) * len(self.headers)


@runtime_checkable
class TableEncoder(Protocol):
    """Serialises a :class:`Table` to text, and reads it back.

    Attributes:
        id: Stable identifier, used as a ``--formats`` value and entry point
            name.
        name: Human-readable display name.
        description: One sentence on what it produces.
        media_type: The IANA media type of the output, for callers that need
            one.
    """

    id: str
    name: str
    description: str
    media_type: str

    def encode(self, table: Table) -> str:
        """Serialise a table.

        Args:
            table: The table to serialise.

        Returns:
            The encoded text, ending in a single newline.
        """
        ...

    def decode(self, text: str) -> Table:
        """Read a table back.

        Args:
            text: Text this encoder produced.

        Returns:
            The table.

        Raises:
            TableError: If the text is not in this format.
        """
        ...


class BaseTableEncoder(ABC):
    """Convenience base supplying the attribute declarations."""

    id: str
    name: str
    description: str
    media_type: str = "text/plain"

    @abstractmethod
    def encode(self, table: Table) -> str:
        """Serialise a table.

        Args:
            table: The table to serialise.

        Returns:
            The encoded text.
        """

    @abstractmethod
    def decode(self, text: str) -> Table:
        """Read a table back.

        Args:
            text: Text this encoder produced.

        Returns:
            The table.
        """


class TableEncoderRegistry:
    """Holds the table encoders available in this process."""

    def __init__(self, entry_point_group: str = FORMAT_ENTRY_POINT_GROUP) -> None:
        """Initialise an empty registry; discovery is deferred to first use.

        Args:
            entry_point_group: The entry point group to scan.
        """
        self._group = entry_point_group
        self._encoders: dict[str, TableEncoder] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Scan entry points once, on first use."""
        if self._loaded:
            return
        self.load_from(entry_points(group=self._group))

    def load_from(self, eps: Iterable[EntryPoint]) -> None:
        """Load encoders from an explicit set of entry points.

        Args:
            eps: The entry points to load.
        """
        for ep in eps:
            try:
                factory = ep.load()
                encoder = factory() if callable(factory) else factory
                if not isinstance(encoder, TableEncoder):
                    msg = f"{type(encoder).__name__} is not a TableEncoder"
                    raise TypeError(msg)
            except Exception as exc:
                _log.warning("format plugin %r failed to load: %s", ep.name, exc)
                _log.debug("plugin load traceback", exc_info=True)
                continue
            self._encoders[encoder.id] = encoder
        self._loaded = True

    def register(self, encoder: TableEncoder) -> None:
        """Add an encoder directly, bypassing entry points.

        Args:
            encoder: The encoder to add.
        """
        self._encoders[encoder.id] = encoder
        self._loaded = True

    def __iter__(self) -> Iterator[TableEncoder]:
        """Iterate over the loaded encoders, in id order."""
        self._ensure_loaded()
        return iter(sorted(self._encoders.values(), key=lambda e: e.id))

    def __len__(self) -> int:
        """Return how many encoders are registered."""
        self._ensure_loaded()
        return len(self._encoders)

    def get(self, encoder_id: str) -> TableEncoder:
        """Return one encoder by id.

        Args:
            encoder_id: The id to look up.

        Returns:
            The encoder.

        Raises:
            KeyError: If the id is unknown.
        """
        self._ensure_loaded()
        try:
            return self._encoders[encoder_id]
        except KeyError:
            known = ", ".join(sorted(self._encoders)) or "none"
            msg = f"no table format named {encoder_id!r} (known: {known})"
            raise KeyError(msg) from None

    def ids(self) -> tuple[str, ...]:
        """Return every registered encoder id, in id order."""
        return tuple(e.id for e in self)


_DEFAULT: TableEncoderRegistry | None = None


def default_format_registry() -> TableEncoderRegistry:
    """Return the process-wide encoder registry, building it on first call.

    Returns:
        The shared registry.
    """
    global _DEFAULT  # one deliberate process-wide cache
    if _DEFAULT is None:
        _DEFAULT = TableEncoderRegistry()
    return _DEFAULT


def reset_default_format_registry() -> None:
    """Discard the process-wide encoder registry. Only useful in tests."""
    global _DEFAULT  # one deliberate process-wide cache
    _DEFAULT = None


def require_named_columns(table: Table, format_name: str) -> None:
    """Refuse a table whose columns cannot become distinct keys.

    The three record-shaped formats — JSON, TOON and key-value — turn each row
    into an object keyed by column name, so two columns called the same thing
    collapse into one and a column called nothing has no key at all. Encoding
    anyway would silently drop data, which is the failure this whole package is
    supposed to make visible rather than commit.

    This is not hypothetical. MarkItDown emits ``report.docx``'s table with an
    invented header row of three empty cells (``docs/BACKENDS.md``), so the
    first table a user tries this on may well be one of these.

    Args:
        table: The table about to be encoded.
        format_name: The format's display name, for the message.

    Raises:
        TableError: If any column name is empty or repeated.
    """
    blank = sum(1 for header in table.headers if not header.strip())
    duplicates = sorted({h for h in table.headers if table.headers.count(h) > 1 and h.strip()})
    if not blank and not duplicates:
        return

    problems = []
    if blank:
        problems.append(f"{blank} column(s) have no name")
    if duplicates:
        problems.append("repeated column name(s): " + ", ".join(repr(d) for d in duplicates))
    msg = (
        f"{format_name} keys each row by column name, so this table cannot be "
        f"encoded: {'; '.join(problems)}"
    )
    raise TableError(msg)
