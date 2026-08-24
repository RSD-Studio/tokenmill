"""Markdown link and image handling.

URLs are expensive. A long tracking URL can cost more tokens than the sentence
containing it, and for most LLM tasks the link *text* carries the meaning while
the target carries none. Images are worse: a base64 data URI in an ``img`` tag
can dominate a document.

This post-processor can drop them — which is why it is **destructive** and
therefore not in the default chain. It does nothing at all under the default
options (:attr:`~tokenmill.core.models.ImageHandling.KEEP` and
:attr:`~tokenmill.core.models.LinkHandling.KEEP`); a user has to ask for a
change, and the CLI adds it to the chain automatically when they do.

Scope: inline links and images, ``[text](url)`` and ``![alt](url)``. Phase 5
adds :attr:`~tokenmill.core.models.LinkHandling.REFERENCE`, which moves targets
into a definition list at the foot of the document — a saving exactly when a
target repeats, and a small cost when none does.

Autolinks (``<https://example.com>``) and bare URLs in prose are still left
alone. Rewriting a bare URL means deciding where it ends, and the answer differs
between Markdown flavours; guessing wrong corrupts the sentence around it.

Code — both fenced blocks and inline spans — is never touched: a URL in a code
sample is content.
"""

from __future__ import annotations

import re
from typing import Final

from tokenmill.core.models import ConvertOptions, ImageHandling, LinkHandling
from tokenmill.post.base import BasePostProcessor

__all__ = ["LinkHandler"]

#: Opens or closes a fenced code block.
_FENCE_RE: Final = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

#: ``![alt](target)``. The alt text may not contain brackets, and the target may
#: not contain whitespace or a closing paren — enough for what converters emit,
#: and it fails closed by leaving anything more exotic alone.
_IMAGE_RE: Final = re.compile(r"!\[(?P<alt>[^\]\[]*)\]\((?P<target>[^()\s]*(?:\s+\"[^\"]*\")?)\)")

#: ``[text](target)``, excluding images, which the negative lookbehind skips.
_LINK_RE: Final = re.compile(
    r"(?<!!)\[(?P<text>[^\]\[]*)\]\((?P<target>[^()\s]*(?:\s+\"[^\"]*\")?)\)"
)

#: An existing reference definition, ``[label]: target``.
_DEFINITION_RE: Final = re.compile(r"^ {0,3}\[[^\]]+\]:\s*\S+")

#: An inline code span, so its contents can be protected from rewriting.
_CODE_SPAN_RE: Final = re.compile(r"(?P<ticks>`+)(?P<body>.+?)(?P=ticks)", re.DOTALL)


class LinkHandler(BasePostProcessor):
    """Rewrites or removes Markdown links and images.

    Attributes:
        id: ``links``.
        name: Display name.
        description: One-line summary.
        destructive: True — it can discard URLs the user wanted.
        order: 200, after whitespace normalisation.
    """

    id = "links"
    name = "Links and images"
    description = (
        "Drop or flatten Markdown links and images to remove URL tokens. "
        "Controlled by --images and --links; does nothing under the defaults."
    )
    destructive = True
    order = 200

    def process(self, text: str, options: ConvertOptions) -> str:
        """Apply the configured link and image handling.

        Args:
            text: The Markdown to rewrite.
            options: Supplies ``image_handling`` and ``link_handling``.

        Returns:
            The rewritten Markdown. Returned unchanged when both settings are
            ``KEEP``, so having this in the chain costs nothing by default.
        """
        if (
            options.image_handling is ImageHandling.KEEP
            and options.link_handling is LinkHandling.KEEP
        ):
            return text

        definitions: dict[str, int] = {}
        out: list[str] = []
        fence: str | None = None
        for line in text.split("\n"):
            if fence is not None:
                out.append(line)
                if line.strip().startswith(fence):
                    fence = None
                continue
            match = _FENCE_RE.match(line)
            if match:
                fence = match.group("fence")
                out.append(line)
                continue
            out.append(self._rewrite_line(line, options, definitions))

        body = "\n".join(out)
        if not definitions:
            return body
        # Definitions are emitted in first-use order, so the numbering a reader
        # meets going down the document is ascending.
        ordered = sorted(definitions.items(), key=lambda item: item[1])
        block = "\n".join(f"[{index}]: {target}" for target, index in ordered)
        return body.rstrip("\n") + "\n\n" + block + "\n"

    def _rewrite_line(self, line: str, options: ConvertOptions, definitions: dict[str, int]) -> str:
        """Rewrite one line, leaving inline code spans alone.

        Args:
            line: The line to rewrite.
            options: Supplies the handling modes.
            definitions: Collects targets seen in reference mode, mapping each
                to its label. Shared across lines so a repeated target is
                defined once, which is the only case where the mode saves
                anything.

        Returns:
            The rewritten line.
        """
        if _DEFINITION_RE.match(line):
            # Already a reference definition. Rewriting it would produce a
            # definition for a definition.
            return line
        pieces: list[str] = []
        position = 0
        for span in _CODE_SPAN_RE.finditer(line):
            pieces.append(self._rewrite_text(line[position : span.start()], options, definitions))
            pieces.append(span.group(0))
            position = span.end()
        pieces.append(self._rewrite_text(line[position:], options, definitions))
        return "".join(pieces)

    @staticmethod
    def _rewrite_text(text: str, options: ConvertOptions, definitions: dict[str, int]) -> str:
        """Rewrite the links and images in a stretch of ordinary text.

        Images are handled before links so that ``![alt](url)`` is never
        mistaken for a link to a target beginning with ``!``.

        Args:
            text: The text to rewrite.
            options: Supplies the handling modes.
            definitions: Collects targets seen in reference mode, mapping each
                to the label that will stand in for it.

        Returns:
            The rewritten text.
        """
        if options.image_handling is ImageHandling.ALT:
            text = _IMAGE_RE.sub(lambda m: m.group("alt"), text)
        elif options.image_handling is ImageHandling.STRIP:
            text = _IMAGE_RE.sub("", text)

        if options.link_handling is LinkHandling.STRIP:
            text = _LINK_RE.sub(lambda m: m.group("text"), text)
        elif options.link_handling is LinkHandling.REFERENCE:

            def to_reference(match: re.Match[str]) -> str:
                target = match.group("target")
                label = definitions.setdefault(target, len(definitions) + 1)
                return f"[{match.group('text')}][{label}]"

            text = _LINK_RE.sub(to_reference, text)
        return text
