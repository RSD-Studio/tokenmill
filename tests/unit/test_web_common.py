"""The web metrics helper: two numbers that must not be confused.

``reduction_ratio`` on a result counts everything that went away, markup
included. ``boilerplate_reduction`` in a web backend's metadata counts only the
share of the page's **visible text** that was discarded. A faithful markup
converter scores near zero — in fact negative — on the second however many bytes
it removed, and that difference is the whole point of measuring both.
"""

from __future__ import annotations

from tokenmill.backends.web._common import note_web_metrics, visible_text
from tokenmill.core.protocol import ConversionContext


class TestVisibleText:
    def test_tags_are_removed_and_their_text_kept(self) -> None:
        assert visible_text("<p>Hello <b>world</b></p>") == "Hello world"

    def test_script_contents_are_not_visible_text(self) -> None:
        """JavaScript is neither article nor boilerplate; nobody reads it."""
        html = "<body><p>Real text</p><script>var secret = 'not text';</script></body>"

        assert visible_text(html) == "Real text"

    def test_style_contents_are_not_visible_text(self) -> None:
        html = "<head><style>p{color:red}</style></head><body><p>Real</p></body>"

        assert visible_text(html) == "Real"

    def test_noscript_and_template_are_excluded_too(self) -> None:
        html = "<body><noscript>enable js</noscript><template>t</template><p>Real</p></body>"

        assert visible_text(html) == "Real"

    def test_navigation_is_kept_because_it_is_the_denominator(self) -> None:
        """It must not do the extractor's job, or the measurement is circular."""
        html = "<body><nav><a href='/'>Home</a></nav><p>Article</p></body>"

        assert "Home" in visible_text(html)

    def test_whitespace_is_collapsed_so_indentation_is_not_counted_as_text(self) -> None:
        """Otherwise a pretty-printed page looks richer than a minified one."""
        html = "<body>\n    <p>One</p>\n\n    <p>Two</p>\n</body>"

        assert visible_text(html) == "One Two"

    def test_entities_are_decoded(self) -> None:
        assert visible_text("<p>caf&eacute; &amp; more</p>") == "café & more"

    def test_malformed_markup_is_tolerated(self) -> None:
        """html.parser is lenient by design, and a broken page still has text."""
        assert "text" in visible_text("<p>text<div><span></p>")

    def test_a_page_with_no_text_yields_nothing(self) -> None:
        assert visible_text("<html><body><script>x=1</script></body></html>") == ""


class TestNoteWebMetrics:
    def test_an_extractor_that_discards_half_the_text_reports_half(self) -> None:
        context = ConversionContext()
        html = "<body><nav>aaaa</nav><p>bbbb</p></body>"  # visible: "aaaa bbbb", 9 chars

        note_web_metrics(context, html=html, output="bbbb", strips_boilerplate=True)

        assert context.metadata["visible_text_characters"] == 9
        assert context.metadata["output_characters"] == 4
        assert context.metadata["boilerplate_reduction"] == round(1 - 4 / 9, 4)

    def test_a_converter_that_adds_syntax_reports_a_negative_share(self) -> None:
        """Markdown bullets, link targets and table pipes cost characters.

        Negative is the correct answer and must not be clamped: it is precisely
        what distinguishes a markup converter from an extractor, and hiding it
        would leave the two looking like the same kind of number.
        """
        context = ConversionContext()

        note_web_metrics(context, html="<p>abcd</p>", output="**abcd**", strips_boilerplate=False)

        assert context.metadata["boilerplate_reduction"] < 0

    def test_a_page_with_no_visible_text_reports_no_ratio_rather_than_zero(self) -> None:
        """No denominator means no fraction. Reporting one would invent it."""
        context = ConversionContext()

        note_web_metrics(context, html="<script>x=1</script>", output="", strips_boilerplate=True)

        assert context.metadata["boilerplate_reduction"] is None

    def test_the_backend_records_whether_it_extracts_at_all(self) -> None:
        """So a reader of the result can tell which kind of ratio it is."""
        extractor, converter = ConversionContext(), ConversionContext()

        note_web_metrics(extractor, html="<p>x</p>", output="x", strips_boilerplate=True)
        note_web_metrics(converter, html="<p>x</p>", output="x", strips_boilerplate=False)

        assert extractor.metadata["strips_boilerplate"] is True
        assert converter.metadata["strips_boilerplate"] is False

    def test_the_raw_html_length_is_recorded_separately_from_the_text_length(self) -> None:
        """The two denominators the two ratios use, kept apart on purpose."""
        context = ConversionContext()
        html = "<html><body><p>four</p></body></html>"

        note_web_metrics(context, html=html, output="four", strips_boilerplate=True)

        assert context.metadata["html_characters"] == len(html)
        assert context.metadata["visible_text_characters"] == 4
