"""Reading structure back out of Markdown, so fidelity can be measured on it.

Every fidelity component asks a question about *structure*, not about bytes:
did the heading survive as a heading, did the table survive as a table, is the
list still a list. Answering those means parsing the converted text back into
the few structures that carry meaning.

This is deliberately a small, strict reader rather than a full CommonMark
parser. It recognises what the corpus and the thirteen backends actually
produce — ATX and setext headings, GFM pipe tables, list markers, fenced code
blocks and both link forms — and nothing else. A fuller parser would be a
dependency in the core install, and ``CONTRIBUTING.md`` rule 1 is not worth
spending on a measurement module.

The one rule that runs through all of it: **fenced code blocks are opaque.** A
``#`` inside a code fence is a comment in somebody's shell script, not a
heading, and a ``|`` inside one is a pipe operator. Counting either would make
a backend that emits more code score as though it emitted more structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from tokenmill.formats.markdown_table import scan_tables

__all__ = [
    "Heading",
    "Table",
    "code_fence_count",
    "headings",
    "link_targets",
    "list_item_lines",
    "normalise",
    "tables",
]

#: An ATX heading: up to three leading spaces, one to six hashes, a space, the
#: title, and optionally a run of closing hashes. Per CommonMark.
_ATX_RE: Final = re.compile(r"^ {0,3}(?P<hashes>#{1,6})[ \t]+(?P<title>.*?)[ \t]*#*[ \t]*$")

#: A setext underline: a run of ``=`` (level 1) or ``-`` (level 2).
_SETEXT_RE: Final = re.compile(r"^ {0,3}(?P<rule>=+|-+)[ \t]*$")

#: Opens or closes a fenced code block.
_FENCE_RE: Final = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

#: A bullet or ordered list marker at the start of a line.
_LIST_RE: Final = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d{1,9}[.)])[ \t]+(?P<rest>.*)$")

#: An inline image. Matched before links, because a link pattern also matches
#: the tail of an image.
_IMAGE_RE: Final = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<target>[^)\s]*)")

#: An inline link, excluding images.
_INLINE_LINK_RE: Final = re.compile(r"(?<!!)\[(?P<text>[^\]]*)\]\((?P<target>[^)\s]*)")

#: A reference-style link definition, e.g. ``[1]: https://example.com``.
_LINK_DEFINITION_RE: Final = re.compile(r"^ {0,3}\[(?P<label>[^\]]+)\]:[ \t]*(?P<target>\S+)")


@dataclass(frozen=True, slots=True)
class Heading:
    """One heading recovered from converted text.

    Attributes:
        level: 1 for ``#``, 6 for ``######``.
        title: The heading text, with markup delimiters left in place.
    """

    level: int
    title: str


@dataclass(frozen=True, slots=True)
class Table:
    """One GFM pipe table recovered from converted text.

    Attributes:
        rows: Every row including the header, each as a tuple of cell values.
            The delimiter row is not included — it is punctuation, not data.
    """

    rows: tuple[tuple[str, ...], ...]

    @property
    def cells(self) -> tuple[str, ...]:
        """Every cell value in the table, header included.

        Returns:
            The cells, in row-major order.
        """
        return tuple(cell for row in self.rows for cell in row)


def normalise(text: str) -> str:
    """Collapse whitespace so a comparison survives a backend's reflowing.

    Backends disagree about line width, indentation and whether a paragraph is
    one line or many, and none of that is a fidelity difference. Comparing
    normalised text asks "is this content here", which is the question the
    ``must_contain`` ground truth is asking.

    Args:
        text: The text to normalise.

    Returns:
        The text with every run of whitespace collapsed to one space, and the
        ends stripped.
    """
    return " ".join(text.split())


def _uncoded_lines(text: str) -> list[tuple[int, str]]:
    """Return the lines that are not inside a fenced code block.

    Args:
        text: The Markdown to scan.

    Returns:
        ``(index, line)`` pairs for every line outside a fence, keeping the
        original index so a caller can still look at neighbouring lines.
    """
    out: list[tuple[int, str]] = []
    fence: str | None = None
    for index, line in enumerate(text.splitlines()):
        if fence is not None:
            if line.strip().startswith(fence):
                fence = None
            continue
        match = _FENCE_RE.match(line)
        if match:
            fence = match.group("fence")
            continue
        out.append((index, line))
    return out


def headings(text: str) -> tuple[Heading, ...]:
    """Return every heading in ``text``, in document order.

    Recognises ATX (``## Title``) and setext (a line underlined with ``===`` or
    ``---``). Setext matters because it is what several HTML-to-Markdown
    converters emit for ``<h1>`` and ``<h2>``, and a scorer that only knew ATX
    would report those backends as having destroyed every heading.

    Args:
        text: The Markdown to scan.

    Returns:
        The headings found, outside fenced code blocks.
    """
    lines = text.splitlines()
    visible = _uncoded_lines(text)
    visible_indexes = {index for index, _ in visible}
    found: list[Heading] = []
    consumed: set[int] = set()

    for index, line in visible:
        if index in consumed:
            continue
        atx = _ATX_RE.match(line)
        if atx and atx.group("title").strip():
            found.append(Heading(len(atx.group("hashes")), atx.group("title").strip()))
            continue

        # Setext: this line is the title and the *next* one is the underline.
        # A `---` under a blank line is a thematic break, not a heading, which
        # is why the title line must have content.
        next_index = index + 1
        if next_index not in visible_indexes or not line.strip():
            continue
        underline = _SETEXT_RE.match(lines[next_index])
        if underline is None:
            continue
        # A list item followed by a dashed rule is a list and a break, not a
        # heading. Excluding it keeps `- item` out of the heading count.
        if _LIST_RE.match(line):
            continue
        level = 1 if underline.group("rule").startswith("=") else 2
        found.append(Heading(level, line.strip()))
        consumed.add(next_index)

    return tuple(found)


def tables(text: str) -> tuple[Table, ...]:
    """Return every GFM pipe table in ``text``.

    A run of pipe-bearing lines is only a table when a delimiter row follows
    the header. That strictness is the whole point of the ``table_integrity``
    component: a backend that flattens a table into prose sometimes leaves the
    pipes behind, and counting those as a surviving table would score the
    failure this project documents as a success.

    The scanning itself lives in :func:`tokenmill.formats.markdown_table.scan_tables`,
    which is the project's one pipe-table parser (defect N3). What this function
    contributes is the preparation: fenced code blocks are dropped first, so a
    ``|`` in somebody's shell script is a pipe operator rather than a column
    boundary. It scans with ``unescape=False`` because this text came out of a
    converter and was never escaped by us — see that module's docstring.

    Args:
        text: The Markdown to scan.

    Returns:
        The tables found, outside fenced code blocks, in document order.
    """
    visible = [line for _, line in _uncoded_lines(text)]
    return tuple(Table(rows) for rows in scan_tables(visible, unescape=False))


def list_item_lines(text: str) -> tuple[str, ...]:
    """Return the content of every list item in ``text``.

    Args:
        text: The Markdown to scan.

    Returns:
        The text following each list marker, outside fenced code blocks. The
        marker itself is dropped: the question a fidelity check asks is whether
        a known item is *still marked as* an item, and the marker character a
        converter chose is not a fidelity difference.
    """
    items: list[str] = []
    for _, line in _uncoded_lines(text):
        match = _LIST_RE.match(line)
        if match and match.group("rest").strip():
            items.append(match.group("rest").strip())
    return tuple(items)


def code_fence_count(text: str) -> int:
    """Count the fenced code blocks in ``text``.

    Args:
        text: The Markdown to scan.

    Returns:
        How many fenced blocks were opened. An unterminated fence at the end of
        the document still counts as one: the content is fenced, whether or not
        the converter closed it.
    """
    count = 0
    fence: str | None = None
    for line in text.splitlines():
        if fence is not None:
            if line.strip().startswith(fence):
                fence = None
            continue
        match = _FENCE_RE.match(line)
        if match:
            fence = match.group("fence")
            count += 1
    return count


def link_targets(text: str) -> tuple[str, ...]:
    """Return every link and image target in ``text``.

    Covers inline links, inline images and reference-style link definitions,
    because the ``links`` post-processor's three modes (inline, reference,
    strip) can move a target between those forms without losing it, and a
    fidelity check must not report a conversion between two lossless forms as a
    loss.

    Args:
        text: The Markdown to scan.

    Returns:
        The targets found, in document order, including duplicates.
    """
    targets: list[str] = []
    for _, line in _uncoded_lines(text):
        definition = _LINK_DEFINITION_RE.match(line)
        if definition:
            targets.append(definition.group("target"))
            continue
        remaining = line
        for match in _IMAGE_RE.finditer(line):
            targets.append(match.group("target"))
        # Blank out the images so the link pattern cannot re-match their tails.
        remaining = _IMAGE_RE.sub(lambda m: " " * len(m.group(0)), remaining)
        for match in _INLINE_LINK_RE.finditer(remaining):
            targets.append(match.group("target"))
    return tuple(targets)
