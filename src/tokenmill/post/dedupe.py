"""Duplicate-block removal.

Repetition is the cheapest thing to remove and the easiest to remove too much
of. A page that repeats its navigation in the footer, a repository pack that
carries the same licence header in forty files, a RAG context assembled from
overlapping chunks — all of them pay for the same text more than once.

**Destructive**, and more obviously so than most: the second copy of a block
might have been deliberate. Off by default.

Two rules keep it from being a document shredder, and both were chosen against
`tests/fixtures/structured.md` rather than in the abstract:

* **Fenced code blocks are never removed and never merged.** Two identical
  code samples in a tutorial are two examples, not a mistake.
* **A block must be long enough to be worth removing.** Without a floor, a
  document with two sections called `### Notes` loses the second heading, and
  a document with two `- yes` list items loses one. The floor is measured in
  characters after whitespace normalisation.
"""

from __future__ import annotations

import re
from typing import Final

from tokenmill.core.models import ConvertOptions
from tokenmill.post.base import BasePostProcessor

__all__ = ["DEFAULT_MIN_BLOCK_CHARS", "DuplicateBlockRemover"]

#: Opens or closes a fenced code block.
_FENCE_RE: Final = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

#: How long a block must be, in characters after whitespace collapsing, before
#: a repeat of it is removed. 80 is two lines of prose: long enough that a
#: repeat is redundancy rather than coincidence, short enough to catch a
#: repeated cookie banner. Overridable through ``ConvertOptions.extra``.
DEFAULT_MIN_BLOCK_CHARS: Final = 80


class DuplicateBlockRemover(BasePostProcessor):
    """Removes later, exact repeats of a block.

    Attributes:
        id: ``dedupe_blocks``.
        name: Display name.
        description: One-line summary.
        destructive: True — a repeat may have been deliberate.
        order: 250, in the content-reduction band, after link handling so that
            two blocks differing only in a stripped URL are seen as identical.
    """

    id = "dedupe_blocks"
    name = "Remove duplicate blocks"
    description = (
        "Drop later, exact repeats of a paragraph or block. Keeps the first "
        "occurrence; never touches fenced code; ignores short blocks."
    )
    destructive = True
    order = 250

    def process(self, text: str, options: ConvertOptions) -> str:
        """Remove repeated blocks, keeping the first of each.

        Args:
            text: The document.
            options: Read for ``extra['dedupe_min_chars']``, which overrides
                :data:`DEFAULT_MIN_BLOCK_CHARS`.

        Returns:
            The document with later duplicates removed.
        """
        minimum = options.extra.get("dedupe_min_chars", DEFAULT_MIN_BLOCK_CHARS)
        floor = minimum if isinstance(minimum, int) and minimum >= 0 else DEFAULT_MIN_BLOCK_CHARS

        kept: list[str] = []
        seen: set[str] = set()
        for block, is_code in _blocks(text):
            if is_code:
                kept.append(block)
                continue
            key = " ".join(block.split())
            if len(key) >= floor and key in seen:
                continue
            if len(key) >= floor:
                seen.add(key)
            kept.append(block)
        return "\n\n".join(kept) + ("\n" if text.endswith("\n") else "")


def _blocks(text: str) -> list[tuple[str, bool]]:
    """Split a document into blank-line-separated blocks.

    A fenced code block is one block however many blank lines it contains, so
    that a blank line inside a code sample cannot split it into fragments that
    are then deduplicated against each other.

    Args:
        text: The document.

    Returns:
        ``(block, is_code)`` pairs, in document order, with empty blocks
        dropped.
    """
    out: list[tuple[str, bool]] = []
    current: list[str] = []
    fence: str | None = None

    def flush() -> None:
        if current and "\n".join(current).strip():
            out.append(("\n".join(current).strip("\n"), False))
        current.clear()

    lines = text.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        if fence is None:
            match = _FENCE_RE.match(line)
            if match:
                flush()
                fence = match.group("fence")
                block = [line]
                index += 1
                while index < len(lines):
                    block.append(lines[index])
                    if lines[index].strip().startswith(fence):
                        index += 1
                        break
                    index += 1
                out.append(("\n".join(block), True))
                fence = None
                continue
            if not line.strip():
                flush()
                index += 1
                continue
        current.append(line)
        index += 1
    flush()
    return out
