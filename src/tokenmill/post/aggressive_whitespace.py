"""Aggressive whitespace cleanup.

`normalize_whitespace` is careful on purpose: it leaves fenced code alone and
preserves Markdown hard line breaks, because a non-destructive step that
quietly changes how a document renders is not one.

This is the version that does not care. It removes what the careful one
protects, for people who have decided that rendering does not matter because
nothing is going to render the document — it is going into a prompt.

**Destructive**, and specifically:

* **Hard line breaks are removed.** Two trailing spaces stop meaning anything.
* **Runs of spaces inside a line collapse to one**, so aligned text and ASCII
  layout lose their alignment.
* **Indentation is removed from paragraph text**, though list and code
  indentation is kept, because those carry structure rather than presentation.

Fenced code blocks are still left completely alone. Whitespace inside a code
block is syntax in several languages, and a post-processor that reindented
somebody's Python would be producing broken content, not cheaper content.
"""

from __future__ import annotations

import re
from typing import Final

from tokenmill.core.models import ConvertOptions
from tokenmill.post.base import BasePostProcessor

__all__ = ["AggressiveWhitespaceCleaner"]

#: Opens or closes a fenced code block.
_FENCE_RE: Final = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

#: A list marker, whose indentation carries nesting and is preserved.
_LIST_RE: Final = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d{1,9}[.)])[ \t]+")

#: An indented code block: four or more spaces, which is content, not padding.
_INDENTED_CODE_RE: Final = re.compile(r"^(?: {4,}|\t)")

#: A run of two or more spaces or tabs inside a line.
_RUN_RE: Final = re.compile(r"[ \t]{2,}")

#: An inline code span, whose contents are protected from collapsing.
_CODE_SPAN_RE: Final = re.compile(r"(?P<ticks>`+)(?P<body>.+?)(?P=ticks)", re.DOTALL)


class AggressiveWhitespaceCleaner(BasePostProcessor):
    """Collapses every run of whitespace that is not load-bearing.

    Attributes:
        id: ``aggressive_whitespace``.
        name: Display name.
        description: One-line summary.
        destructive: True — hard line breaks and alignment are lost.
        order: 150, after ``normalize_whitespace`` so it starts from tidy input.
    """

    id = "aggressive_whitespace"
    name = "Aggressive whitespace"
    description = (
        "Collapse runs of spaces, drop hard line breaks and remove paragraph "
        "indentation. Leaves fenced code, list nesting and indented code alone."
    )
    destructive = True
    order = 150

    def process(self, text: str, options: ConvertOptions) -> str:  # noqa: ARG002
        """Collapse the document's whitespace.

        Args:
            text: The Markdown to clean.
            options: Unused; this post-processor takes no settings.

        Returns:
            The cleaned Markdown, with one blank line at most between blocks
            and a single trailing newline. The empty string stays empty.
        """
        if not text.strip():
            return ""

        out: list[str] = []
        fence: str | None = None
        blank_run = 0
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if fence is not None:
                out.append(line)
                if line.strip().startswith(fence):
                    fence = None
                continue

            match = _FENCE_RE.match(line)
            if match:
                fence = match.group("fence")
                out.append(line.rstrip())
                blank_run = 0
                continue

            if not line.strip():
                blank_run += 1
                if blank_run == 1:
                    out.append("")
                continue

            blank_run = 0
            out.append(self._clean(line))

        return "\n".join(out).strip("\n") + "\n"

    @staticmethod
    def _clean(line: str) -> str:
        """Clean one line of ordinary text.

        Args:
            line: The line.

        Returns:
            The line with its runs of internal whitespace collapsed and its
            padding removed, keeping list and indented-code indentation.
        """
        if _INDENTED_CODE_RE.match(line) and not _LIST_RE.match(line):
            return line.rstrip()

        list_match = _LIST_RE.match(line)
        prefix = list_match.group("indent") if list_match else ""
        body = line[len(prefix) :].rstrip()

        # Collapse runs everywhere except inside inline code spans, where the
        # spacing may be part of the sample.
        pieces: list[str] = []
        position = 0
        for span in _CODE_SPAN_RE.finditer(body):
            pieces.append(_RUN_RE.sub(" ", body[position : span.start()]))
            pieces.append(span.group(0))
            position = span.end()
        pieces.append(_RUN_RE.sub(" ", body[position:]))
        return prefix + "".join(pieces)
