"""The two reference backends against the real fixture corpus.

These assert on **structure** — headings present, article body intact,
boilerplate accounted for — rather than byte equality, per ``CONTRIBUTING.md``.
Byte-comparing a converter's output makes the test fail on every upstream
release for no good reason.

They also pin down what ``markdownify_html`` does *not* do. It is a faithful
markup converter, not an extractor: navigation, cookie banners and
advertisements survive it. Phase 3's Trafilatura adapter is what removes those,
and the tests below are written so that when it lands, the difference is
measurable rather than asserted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tokenmill.core.errors import CorruptSource
from tokenmill.core.models import ConversionResult, ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import Registry

pytestmark = pytest.mark.integration

#: Measured with the `bytes` tokenizer, which needs no download and so works in
#: an air-gapped environment. It counts UTF-8 bytes, not model tokens.
OFFLINE = ConvertOptions(tokenizer="bytes")


@pytest.fixture(scope="module")
def pipeline() -> Pipeline:
    """Return a pipeline over the really-installed backends."""
    return Pipeline(backends=Registry())


@pytest.fixture(scope="module")
def boilerplate_result(fixture_dir: Path, pipeline: Pipeline) -> ConversionResult:
    """Convert ``boilerplate.html`` once for the whole module."""
    return pipeline.run(Source.from_path(fixture_dir / "boilerplate.html"), OFFLINE)


@pytest.fixture(scope="module")
def article_result(fixture_dir: Path, pipeline: Pipeline) -> ConversionResult:
    """Convert ``article.html`` once for the whole module."""
    return pipeline.run(Source.from_path(fixture_dir / "article.html"), OFFLINE)


@pytest.fixture(scope="module")
def boilerplate_markers(ground_truth: dict[str, Any]) -> list[str]:
    """Return the strings the corpus says belong only to the wrapper."""
    markers: list[str] = ground_truth["boilerplate.html"]["boilerplate_markers_must_be_absent"]
    return markers


class TestMarkdownifyOnTheBoilerplateFixture:
    def test_the_expected_backend_ran(self, boilerplate_result: ConversionResult) -> None:
        assert boilerplate_result.backend_id == "markdownify_html"

    def test_the_article_title_is_an_atx_heading(
        self, boilerplate_result: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        title = ground_truth["boilerplate.html"]["article_title"]

        assert f"# {title}" in boilerplate_result.text

    def test_every_article_section_heading_survives(
        self, boilerplate_result: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        """The corpus manifest lists the title first, then the H2 sections."""
        title, *sections = ground_truth["boilerplate.html"]["expected_headings"]

        assert f"# {title}" in boilerplate_result.text
        for heading in sections:
            assert f"## {heading}" in boilerplate_result.text, f"lost {heading!r}"

    def test_the_article_body_is_intact(
        self, boilerplate_result: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        """Every paragraph of the clean article must appear in the noisy one."""
        facts = ground_truth["article.html"]
        for sentence in facts.get("must_contain", []):
            assert sentence in boilerplate_result.text

    def test_the_summary_table_survives_as_a_markdown_table(
        self, boilerplate_result: ConversionResult
    ) -> None:
        assert "| Backend | License | Runtime | Tables | Pages/sec |" in boilerplate_result.text
        for row_label in ("markitdown", "docling", "pdfplumber", "pypdf", "marker"):
            assert f"| {row_label} |" in boilerplate_result.text

    def test_scripts_and_styles_are_gone(self, boilerplate_result: ConversionResult) -> None:
        """Raw JavaScript in the output would be a straightforward bug."""
        lowered = boilerplate_result.text.lower()

        assert "<script" not in lowered
        assert "gtag(" not in boilerplate_result.text
        assert "function" not in boilerplate_result.text

    def test_no_html_tags_survive_in_the_markdown(
        self, boilerplate_result: ConversionResult
    ) -> None:
        for tag in ("<div", "<nav", "<span", "<header", "<footer"):
            assert tag not in boilerplate_result.text.lower()

    def test_the_boilerplate_survives_because_this_backend_does_not_extract(
        self, boilerplate_result: ConversionResult, boilerplate_markers: list[str]
    ) -> None:
        """Documenting the limitation, not asserting it is desirable.

        Phase 3's trafilatura adapter is what strips these. If a future change
        makes them disappear here, that is a behaviour change worth noticing.
        """
        for marker in boilerplate_markers:
            assert marker in boilerplate_result.text, (
                f"{marker!r} vanished; markdownify_html is a markup converter and "
                f"is not expected to strip boilerplate"
            )

    def test_the_backend_says_so_in_its_metadata(
        self, boilerplate_result: ConversionResult
    ) -> None:
        assert boilerplate_result.metadata["strips_boilerplate"] is False

    def test_the_conversion_makes_the_document_measurably_smaller(
        self, boilerplate_result: ConversionResult
    ) -> None:
        assert boilerplate_result.tokens_before is not None
        assert boilerplate_result.tokens_after is not None
        assert boilerplate_result.tokens_after.value < boilerplate_result.tokens_before.value
        assert boilerplate_result.reduction_ratio is not None
        assert boilerplate_result.reduction_ratio > 0

    def test_the_reduction_is_markup_removal_not_extraction(
        self, boilerplate_result: ConversionResult
    ) -> None:
        """A sanity bound, so an implausible number cannot pass unnoticed.

        Removing tags from this fixture roughly halves it. A boilerplate_result far outside
        that band means something is being dropped that should not be, and the
        test should fail rather than let a wrong number be reported.
        """
        assert boilerplate_result.reduction_ratio is not None
        assert 0.30 < boilerplate_result.reduction_ratio < 0.65


class TestMarkdownifyOnTheCleanArticle:
    def test_it_converts_and_keeps_the_title(
        self, article_result: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        assert ground_truth["article.html"]["article_title"] in article_result.text

    def test_a_page_with_little_markup_reduces_far_less(
        self, article_result: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        """The comparison that shows where the saving actually comes from.

        The clean article and the boilerplate page share a byte-identical body.
        The clean one has proportionally less markup, so markup removal buys
        proportionally less — which is exactly the point ``RESEARCH.md``
        Category 7 makes about misattributing the win to Markdown syntax.
        """
        del ground_truth
        assert article_result.reduction_ratio is not None
        assert 0 < article_result.reduction_ratio < 0.35

    def test_no_boilerplate_markers_appear_in_the_clean_article(
        self, article_result: ConversionResult, boilerplate_markers: list[str]
    ) -> None:
        for marker in boilerplate_markers:
            assert marker not in article_result.text


class TestPlaintextBackend:
    def test_it_passes_markdown_through_unchanged_apart_from_whitespace(
        self, fixture_dir: Path
    ) -> None:
        source = fixture_dir / "long_context.md"

        result = Pipeline().run(Source.from_path(source), OFFLINE)

        assert result.backend_id == "plaintext"
        original = source.read_text(encoding="utf-8")
        assert result.text.strip() == original.strip()

    def test_the_needle_fact_survives(
        self, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        result = Pipeline().run(Source.from_path(fixture_dir / "long_context.md"), OFFLINE)

        facts = ground_truth["long_context.md"]

        assert result.text.count(facts["needle"]) == facts["needle_occurrences"]

    def test_unicode_round_trips(self, tmp_path: Path) -> None:
        source = tmp_path / "scripts.txt"
        text = "اردو 中文 日本語 Ελληνικά Русский 🙂👨‍👩‍👧 ∑∫"
        source.write_text(text, encoding="utf-8")

        result = Pipeline().run(Source.from_path(source), OFFLINE)

        assert result.text.strip() == text

    def test_undecodable_bytes_are_reported_rather_than_hidden(self, tmp_path: Path) -> None:
        source = tmp_path / "latin.txt"
        source.write_bytes("café".encode("latin-1"))

        result = Pipeline().run(Source.from_path(source), OFFLINE)

        assert any("not valid UTF-8" in w for w in result.warnings)


class TestErrorPaths:
    def test_an_empty_html_file_is_reported_as_corrupt(self, tmp_path: Path) -> None:
        """markdownify_html's own error path, pinned to that backend.

        Phase 2 gave HTML more than one candidate backend, so this has to name
        the backend it is about. Run through auto-selection it now falls back
        instead — see the test below, which records what that does.
        """
        empty = tmp_path / "empty.html"
        empty.write_text("   \n", encoding="utf-8")

        with pytest.raises(CorruptSource, match="is empty"):
            Pipeline().run(Source.from_path(empty), OFFLINE.with_(backend="markdownify_html"))

    def test_an_empty_html_file_falls_back_and_says_so(self, tmp_path: Path) -> None:
        """The Phase 2 behaviour change, asserted rather than left to be noticed.

        Before the fallback chain, an empty HTML file was a hard error from the
        one backend that claimed HTML. Now the document backends get a turn,
        and they return an empty document rather than raising — so the run
        succeeds with nothing in it. That is only acceptable because both facts
        are visible: the attempt chain names the backend that failed, and the
        empty-output warning says nothing was extracted.
        """
        empty = tmp_path / "empty.html"
        empty.write_text("   \n", encoding="utf-8")

        try:
            result = Pipeline().run(Source.from_path(empty), OFFLINE)
        except CorruptSource:
            pytest.skip("no document backend is installed to fall back to")

        assert result.text.strip() == ""
        assert result.attempts[0].backend_id == "markdownify_html"
        assert not result.attempts[0].ok
        assert any("fell back" in warning for warning in result.warnings)
        assert any("empty document" in warning for warning in result.warnings)

    def test_a_file_over_the_size_limit_is_refused(self, fixture_dir: Path) -> None:
        source = Source.from_path(fixture_dir / "boilerplate.html")

        with pytest.raises(CorruptSource, match="over the"):
            Pipeline().run(source, OFFLINE.with_(max_bytes=100))

    def test_html_with_no_text_outside_scripts_warns_about_an_empty_result(
        self, tmp_path: Path
    ) -> None:
        """An empty conversion exits zero and looks like success. It is not."""
        page = tmp_path / "scriptonly.html"
        page.write_text(
            "<html><head><style>p{color:red}</style></head>"
            "<body><script>var x = 1;</script></body></html>",
            encoding="utf-8",
        )

        result = Pipeline().run(Source.from_path(page), OFFLINE)

        assert any("empty document" in w for w in result.warnings)


class TestOfflineGuarantee:
    def test_converting_a_local_file_makes_no_network_call(
        self, fixture_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default-deny on the network, enforced rather than asserted in docs."""
        import socket

        def refuse(*_args: Any, **_kwargs: Any) -> Any:
            msg = "a local conversion must not open a socket"
            raise AssertionError(msg)

        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)

        result = Pipeline().run(Source.from_path(fixture_dir / "boilerplate.html"), OFFLINE)

        assert result.text
