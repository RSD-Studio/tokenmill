"""Shared plumbing for the web backends.

Three of the four web backends are extractors: they are handed a page and
return the part of it a reader came for. What distinguishes them from
``markdownify_html`` is not the Markdown they emit but what they throw away, so
the number worth reporting about a web conversion is **how much of the page's
visible text was furniture** — and that is a different question from how many
markup characters disappeared.

:func:`note_web_metrics` measures both, separately, and is called by every web
backend so the four are comparable:

* ``html_characters`` — the page as delivered, markup and all.
* ``visible_text_characters`` — the same page with tags, scripts and styles
  removed, and nothing else removed. This is every word a reader would see:
  article, navigation, cookie banner, advertisements, footer.
* ``output_characters`` — what the backend produced.
* ``boilerplate_reduction`` — ``1 - output / visible``, i.e. the share of the
  page's *text* the backend discarded. For a faithful markup converter this is
  approximately zero, because it discards no text; for an extractor it is the
  measurement that says the extraction worked.

The distinction matters because it is exactly the mistake ``RESEARCH.md``
Category 7 warns about. Converting ``boilerplate.html`` with a markup converter
removes about 45% of its bytes and strips no boilerplate whatsoever; reporting
that as a boilerplate figure would credit the serialiser for work the extractor
does. Two numbers, measured separately, cannot be confused for one another.

**These are character counts, not token counts.** The pipeline measures tokens,
with a named tokenizer, and its before/after pair is the token claim. The ratio
here is a fact about the text and is labelled as one everywhere it appears.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Final

from tokenmill.core.protocol import ConversionContext

__all__ = ["note_web_metrics", "visible_text"]

#: Elements whose contents are code or styling rather than anything a reader
#: sees. Their text is not part of the page's visible text at any point, so it
#: belongs to neither the article nor the boilerplate.
_INVISIBLE: Final[frozenset[str]] = frozenset({"script", "style", "template", "noscript"})


class _VisibleTextExtractor(HTMLParser):
    """Collects the text a reader would see, and nothing else.

    Deliberately not an extraction algorithm. It removes markup and the
    contents of script and style elements, and keeps every other word — the
    navigation, the cookie banner and the footer included. That is the point:
    it is the denominator the extractors are measured against, so it must not
    do any of their work.
    """

    def __init__(self) -> None:
        """Initialise with an empty buffer and no suppressed element open."""
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._suppressed: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Begin suppressing content when an invisible element opens.

        Args:
            tag: The element name.
            attrs: Its attributes, unused.
        """
        del attrs
        if tag in _INVISIBLE:
            self._suppressed.append(tag)
            return
        # An element boundary separates words even when the markup has no
        # whitespace at it. Without this, `<nav>Home</nav><p>Article</p>` counts
        # as the single run "HomeArticle", which is both one character short and
        # a word that does not exist on the page.
        self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        """Stop suppressing when the matching invisible element closes.

        Args:
            tag: The element name.
        """
        if tag in _INVISIBLE:
            if self._suppressed and self._suppressed[-1] == tag:
                self._suppressed.pop()
            return
        self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        """Collect a run of text unless it is inside an invisible element.

        Args:
            data: The text.
        """
        if not self._suppressed:
            self._chunks.append(data)

    def text(self) -> str:
        """Return the collected text with runs of whitespace collapsed.

        Returns:
            The visible text. Whitespace is normalised so that the count
            measures words rather than a page's indentation, which would
            otherwise make a prettily-formatted page look as though it carried
            more text than a minified one.
        """
        return " ".join("".join(self._chunks).split())


def visible_text(html: str) -> str:
    """Return the text a reader would see on a page, markup removed.

    Args:
        html: The page source.

    Returns:
        The visible text, whitespace collapsed. Malformed markup is tolerated:
        :mod:`html.parser` is lenient by design, and a page that fails to parse
        strictly is a page tokenmill should still be able to describe.
    """
    parser = _VisibleTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


def note_web_metrics(
    context: ConversionContext,
    *,
    html: str,
    output: str,
    strips_boilerplate: bool,
) -> None:
    """Record how much markup, and how much *text*, a web conversion removed.

    Args:
        context: Collects the notes.
        html: The page as it was handed to the backend.
        output: What the backend produced.
        strips_boilerplate: Whether this backend attempts extraction at all.
            Recorded so a reader of the result can tell an extractor's ratio
            from a markup converter's, which mean quite different things.
    """
    visible = visible_text(html)
    context.note("strips_boilerplate", strips_boilerplate)
    context.note("html_characters", len(html))
    context.note("visible_text_characters", len(visible))
    context.note("output_characters", len(output))
    if visible:
        # Negative is a real outcome — a converter can emit more characters
        # than the page had visible text, because Markdown syntax costs
        # something — and clamping it would hide exactly the case worth seeing.
        context.note("boilerplate_reduction", round(1 - len(output) / len(visible), 4))
    else:
        # A page with no visible text at all has no denominator. Reporting a
        # ratio anyway would be inventing one.
        context.note("boilerplate_reduction", None)
