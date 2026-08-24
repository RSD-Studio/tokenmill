"""Heading normalisation.

Converters disagree about heading depth in ways that have nothing to do with
the document. Kreuzberg infers a PDF's headings and starts at `#`; MarkItDown
demotes a DOCX title so its sections start at `#` one level too shallow; an
HTML fragment lifted out of a page routinely starts at `##` because the page's
`<h1>` was the site name. The result is a corpus of documents whose heading
levels are not comparable with each other.

This repairs two things:

* **The shallowest heading becomes `#`.** A document that starts at `##` is
  promoted so its top level is level one.
* **Skipped levels are closed up.** `#` followed by `####` becomes `#` followed
  by `##`, so depth reflects nesting rather than whatever the source happened
  to use.

Setext headings are rewritten as ATX on the way through, because two spellings
of the same thing cost tokens and confuse every downstream reader.

**Destructive**, and worth being explicit about why, because it removes nothing:
the original levels are not recoverable afterwards. A document where the jump
from `#` to `####` was meaningful — a specification with deliberately deep
numbering — comes out saying something different. `RESEARCH.md` Category 7 is
the reason this is off by default: *"LLMs Understand Layout"* (arXiv:2407.05750)
measures +8-33% F1 when layout is preserved, so changing structure to save
tokens is a trade rather than a win.
"""

from __future__ import annotations

import re
from typing import Final

from tokenmill.core.models import ConvertOptions
from tokenmill.post.base import BasePostProcessor

__all__ = ["HeadingNormalizer"]

#: Opens or closes a fenced code block.
_FENCE_RE: Final = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

#: An ATX heading.
_ATX_RE: Final = re.compile(r"^ {0,3}(?P<hashes>#{1,6})[ \t]+(?P<title>.*?)[ \t]*#*[ \t]*$")

#: A setext underline.
_SETEXT_RE: Final = re.compile(r"^ {0,3}(?P<rule>=+|-+)[ \t]*$")

#: A list marker, so a list item above a dashed rule is not read as a heading.
_LIST_RE: Final = re.compile(r"^[ \t]*([-*+]|\d{1,9}[.)])[ \t]+")

#: The deepest heading Markdown has.
_MAX_LEVEL: Final = 6

#: Opens a front-matter block when it is the document's first content line.
_FRONT_MATTER_RE: Final = re.compile(r"^(-{3,}|\+{3,})\s*$")


def _skip_front_matter(lines: list[str], out: list[tuple[int, str, str]]) -> int:
    """Pass a leading front-matter block through untouched.

    Front matter is not Markdown, and its closing ``---`` looks exactly like a
    setext underline: without this, ``draft: false`` on the last line of a YAML
    block becomes a level-two heading and then gets promoted to ``#``. That is
    not hypothetical — it is what this post-processor did to
    ``tests/fixtures/structured.md`` the first time it was run, and it was
    caught by reading the output rather than by a test.

    Args:
        lines: Every line of the document.
        out: Receives the front-matter lines verbatim, as non-headings.

    Returns:
        The index of the first line after the block, or 0 when there is none.
    """
    first = 0
    while first < len(lines) and not lines[first].strip():
        first += 1
    if first >= len(lines) or not _FRONT_MATTER_RE.match(lines[first].strip()):
        return 0
    opener = lines[first].strip()[0]
    for index in range(first + 1, len(lines)):
        candidate = lines[index].strip()
        if _FRONT_MATTER_RE.match(candidate) and candidate[0] == opener:
            out.extend((0, "", line) for line in lines[: index + 1])
            return index + 1
    return 0


class HeadingNormalizer(BasePostProcessor):
    """Promotes headings to start at level one and closes up skipped levels.

    Attributes:
        id: ``normalize_headings``.
        name: Display name.
        description: One-line summary.
        destructive: True — the original levels cannot be recovered.
        order: 400, the reformatting band.
    """

    id = "normalize_headings"
    name = "Normalise headings"
    description = (
        "Promote the shallowest heading to level one, close up skipped levels, "
        "and rewrite setext headings as ATX."
    )
    destructive = True
    order = 400

    def process(self, text: str, options: ConvertOptions) -> str:  # noqa: ARG002
        """Normalise the heading hierarchy.

        Args:
            text: The Markdown to normalise.
            options: Unused; this post-processor takes no settings.

        Returns:
            The Markdown with a normalised heading hierarchy. Returned
            unchanged when it has no headings — there is nothing to normalise
            and shifting nothing is better than reflowing the document.
        """
        parsed = self._parse(text)
        if not any(level for level, _, _ in parsed):
            return text

        # Depth comes from each heading's position in the *ancestor chain* at
        # that point in the document, not from a global remap of the distinct
        # levels used. A global map is the obvious implementation and it is
        # wrong: on a document going `##`, `####`, `###` it maps 2->1, 3->2,
        # 4->3 and emits `#`, `###`, `##`, which still skips a level. Walking a
        # stack emits `#`, `##`, `##` — the subsection and the section become
        # the siblings they are, both children of the title.
        ancestors: list[int] = []
        out: list[str] = []
        for level, title, raw in parsed:
            if not level:
                out.append(raw)
                continue
            while ancestors and ancestors[-1] >= level:
                ancestors.pop()
            ancestors.append(level)
            out.append("#" * min(len(ancestors), _MAX_LEVEL) + " " + title)
        return "\n".join(out)

    @staticmethod
    def _parse(text: str) -> list[tuple[int, str, str]]:
        """Classify every line as a heading or not.

        Args:
            text: The Markdown.

        Returns:
            One ``(level, title, raw_line)`` per output line, with ``level`` 0
            for lines that are not headings. A setext heading collapses its two
            source lines into one entry, which is what rewrites it as ATX.
        """
        lines = text.split("\n")
        out: list[tuple[int, str, str]] = []
        fence: str | None = None
        index = _skip_front_matter(lines, out)
        while index < len(lines):
            line = lines[index]
            if fence is not None:
                out.append((0, "", line))
                if line.strip().startswith(fence):
                    fence = None
                index += 1
                continue

            match = _FENCE_RE.match(line)
            if match:
                fence = match.group("fence")
                out.append((0, "", line))
                index += 1
                continue

            atx = _ATX_RE.match(line)
            if atx and atx.group("title").strip():
                out.append((len(atx.group("hashes")), atx.group("title").strip(), line))
                index += 1
                continue

            underline = _SETEXT_RE.match(lines[index + 1]) if index + 1 < len(lines) else None
            if underline and line.strip() and not _LIST_RE.match(line):
                level = 1 if underline.group("rule").startswith("=") else 2
                out.append((level, line.strip(), line))
                index += 2
                continue

            out.append((0, "", line))
            index += 1
        return out
