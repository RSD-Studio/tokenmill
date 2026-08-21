"""Whitespace normalisation — the one post-processor that runs by default.

Converters leave a lot of incidental whitespace behind: trailing spaces at the
end of lines, long runs of blank lines where HTML block elements used to be,
and whatever line endings the source file happened to use. All of it costs
tokens and none of it carries meaning.

This post-processor is **non-destructive**, and that claim is meant literally
rather than approximately:

* Fenced code blocks are passed through untouched. Whitespace inside a code
  block is content.
* Markdown hard line breaks — a line ending in two or more spaces, followed by
  another line of text — are preserved as exactly two spaces. Stripping them
  would silently change how the document renders, which is the kind of quiet
  damage ``CONTRIBUTING.md`` rule 5 exists to prevent.

Everything more aggressive than this belongs to Phase 5, is opt-in, and is not
in this module.
"""

from __future__ import annotations

import re
from typing import Final

from tokenmill.core.models import ConvertOptions
from tokenmill.post.base import BasePostProcessor

__all__ = ["WhitespaceNormalizer"]

#: Opens or closes a fenced code block: three or more backticks or tildes,
#: optionally indented by up to three spaces, per CommonMark.
_FENCE_RE: Final = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

#: A line that is empty or contains only whitespace.
_BLANK_RE: Final = re.compile(r"^\s*$")


class WhitespaceNormalizer(BasePostProcessor):
    """Collapses incidental whitespace without touching content.

    Attributes:
        id: ``normalize_whitespace``.
        name: Display name.
        description: One-line summary.
        destructive: False — this never discards content.
        order: 100, early: later post-processors get tidy input.
    """

    id = "normalize_whitespace"
    name = "Normalise whitespace"
    description = (
        "Normalise line endings, strip trailing spaces and collapse runs of blank "
        "lines, leaving fenced code blocks and hard line breaks intact."
    )
    destructive = False
    order = 100

    def process(self, text: str, options: ConvertOptions) -> str:  # noqa: ARG002
        """Normalise the whitespace in ``text``.

        Args:
            text: The text to normalise.
            options: Unused; this post-processor takes no settings.

        Returns:
            The normalised text: LF line endings, no trailing whitespace outside
            code blocks and hard breaks, at most one blank line between blocks,
            no leading or trailing blank lines, and a single trailing newline.
            The empty string stays empty rather than becoming a lone newline.
        """
        if not text.strip():
            return ""

        normalised = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalised.split("\n")
        out: list[str] = []
        fence: str | None = None

        for index, line in enumerate(lines):
            if fence is not None:
                out.append(line)
                if line.strip().startswith(fence):
                    fence = None
                continue

            match = _FENCE_RE.match(line)
            if match:
                fence = match.group("fence")
                out.append(line.rstrip())
                continue

            out.append(self._strip_line(line, lines, index))

        collapsed = self._collapse_blank_runs(out)
        return "\n".join(collapsed).strip("\n") + "\n"

    @staticmethod
    def _strip_line(line: str, lines: list[str], index: int) -> str:
        """Strip a line's trailing whitespace, keeping a hard line break.

        Args:
            line: The line to strip.
            lines: Every line, so the next one can be inspected.
            index: This line's position in ``lines``.

        Returns:
            The line with trailing whitespace removed, or ending in exactly two
            spaces where it carried a Markdown hard line break.
        """
        stripped = line.rstrip()
        if not stripped:
            return ""
        had_hard_break = len(line) - len(stripped) >= 2
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if had_hard_break and not _BLANK_RE.match(next_line):
            return stripped + "  "
        return stripped

    @staticmethod
    def _collapse_blank_runs(lines: list[str]) -> list[str]:
        """Reduce every run of two or more blank lines to a single blank line.

        Args:
            lines: The lines to collapse.

        Returns:
            The collapsed lines. Blank lines inside fenced code blocks have
            already been emitted verbatim by the caller and are not seen here,
            so this cannot damage a code block.
        """
        out: list[str] = []
        blank_run = 0
        fence: str | None = None
        for line in lines:
            if fence is not None:
                out.append(line)
                if line.strip().startswith(fence):
                    fence = None
                continue
            match = _FENCE_RE.match(line)
            if match:
                fence = match.group("fence")
                blank_run = 0
                out.append(line)
                continue
            if line == "":
                blank_run += 1
                if blank_run > 1:
                    continue
            else:
                blank_run = 0
            out.append(line)
        return out
