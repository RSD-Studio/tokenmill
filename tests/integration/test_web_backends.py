"""The web backends against the real fixture corpus.

This is the other half of the pair. ``test_reference_backends.py`` asserts that
``markdownify_html`` keeps every string in ``boilerplate.html``'s
``boilerplate_markers_must_be_absent`` list, because a markup converter does not
strip page furniture. This file asserts that the extractors remove them, from
the same list in the same manifest, on the same page.

That list is named for what an extractor is supposed to achieve, so it is used
here as the acceptance test rather than as documentation. Between the two files
the difference between converting a page and extracting from it is measured in
both directions, on one fixture, rather than argued about.

**Every number here is in characters or UTF-8 bytes, never model tokens.** The
sandbox these were written in cannot reach either tokenizer vocabulary host, so
the model-token figure — the one RESEARCH.md's 70-90% band is stated in — is
asserted in ``tests/unit/test_web_tokens_network.py`` behind the ``network``
marker instead, and published nowhere until a green CI run has printed it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tokenmill.core.errors import BackendFailed, ConversionError, CorruptSource, NetworkRequired
from tokenmill.core.models import ConversionResult, ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import Registry

pytestmark = pytest.mark.integration

OFFLINE = ConvertOptions(tokenizer="bytes")

#: The same, with the permission crawl4ai requires. A browser runs the page's
#: scripts and loads whatever they ask for, which is a broader thing than
#: retrieving one address, so it is asked for explicitly.
NETWORKED = OFFLINE.with_(allow_network=True)


@pytest.fixture(scope="module")
def pipeline() -> Pipeline:
    """Return a pipeline over the really-installed backends."""
    return Pipeline(backends=Registry())


@pytest.fixture(scope="module")
def boilerplate_markers(ground_truth: dict[str, Any]) -> list[str]:
    """Return the strings the corpus says belong only to the wrapper."""
    markers: list[str] = ground_truth["boilerplate.html"]["boilerplate_markers_must_be_absent"]
    return markers


def convert(pipeline: Pipeline, path: Path, backend: str) -> ConversionResult:
    """Convert one fixture through one named backend.

    Args:
        pipeline: The pipeline to run.
        path: The fixture.
        backend: The backend id to pin to.

    Returns:
        The result.
    """
    return pipeline.run(Source.from_path(path), OFFLINE.with_(backend=backend))


@pytest.fixture(scope="module")
def trafilatura_boilerplate(fixture_dir: Path, pipeline: Pipeline) -> ConversionResult:
    """Extract ``boilerplate.html`` with trafilatura once for the whole module."""
    return convert(pipeline, fixture_dir / "boilerplate.html", "trafilatura")


class TestTrafilaturaStripsTheBoilerplate:
    """The mirror of ``test_the_boilerplate_survives_because_this_backend_does_not_extract``."""

    def test_every_boilerplate_marker_is_gone(
        self, trafilatura_boilerplate: ConversionResult, boilerplate_markers: list[str]
    ) -> None:
        """The acceptance test for Phase 3, taken from the manifest's own list."""
        survivors = [m for m in boilerplate_markers if m in trafilatura_boilerplate.text]

        assert survivors == [], (
            f"trafilatura left {len(survivors)} of {len(boilerplate_markers)} boilerplate "
            f"markers in the output: {survivors}. Extraction is this backend's entire "
            f"contribution; if upstream has changed, update docs/BACKENDS.md rather than "
            f"this assertion."
        )

    def test_the_article_title_survives_as_a_heading(
        self, trafilatura_boilerplate: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        title = ground_truth["boilerplate.html"]["article_title"]

        assert f"# {title}" in trafilatura_boilerplate.text

    def test_every_section_heading_survives(
        self, trafilatura_boilerplate: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        """Stripping boilerplate must not cost structure.

        RESEARCH.md Category 7's rule for this repository is "keep structure,
        strip boilerplate", citing arXiv:2407.05750 measuring +8-33% F1 when
        layout survives. An extractor that took the headings with the navigation
        would be trading accuracy for a better-looking percentage.
        """
        title, *sections = ground_truth["boilerplate.html"]["expected_headings"]

        assert f"# {title}" in trafilatura_boilerplate.text
        for heading in sections:
            assert f"## {heading}" in trafilatura_boilerplate.text, f"lost {heading!r}"

    def test_the_whole_article_body_survives(
        self, trafilatura_boilerplate: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        for sentence in ground_truth["article.html"]["must_contain"]:
            assert sentence in trafilatura_boilerplate.text

    def test_the_summary_table_survives_as_a_markdown_table(
        self, trafilatura_boilerplate: ConversionResult
    ) -> None:
        """A table dropped to save its pipe characters is a table lost."""
        text = trafilatura_boilerplate.text

        assert "| Backend | License | Runtime | Tables | Pages/sec |" in text
        for row_label in ("markitdown", "docling", "pdfplumber", "pypdf", "marker"):
            assert f"| {row_label} |" in text

    def test_it_says_in_its_metadata_that_it_extracts(
        self, trafilatura_boilerplate: ConversionResult
    ) -> None:
        assert trafilatura_boilerplate.metadata["strips_boilerplate"] is True


class TestTheMeasuredReduction:
    """The exit-gate numbers, in the units this sandbox can actually produce."""

    def test_the_byte_reduction_is_in_the_published_order_of_magnitude(
        self, trafilatura_boilerplate: ConversionResult
    ) -> None:
        """RESEARCH.md Category 7 reports 70-90% for HTML-to-extracted-Markdown.

        Ours is measured in **UTF-8 bytes**, not model tokens, because neither
        tokenizer vocabulary host is reachable where this test was written. A
        byte percentage is a different claim from a token percentage and is
        never published as one. What this asserts is that our figure is in the
        same order of magnitude as the literature's, which is what the
        acceptance criterion asks and all a byte measure can support.
        """
        ratio = trafilatura_boilerplate.reduction_ratio

        assert ratio is not None
        assert 0.70 <= ratio <= 0.90, (
            f"byte reduction {ratio:.1%} is outside RESEARCH.md's 70-90% band; "
            f"investigate before publishing it"
        )

    def test_extraction_beats_markup_removal_by_a_wide_margin(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """The comparison that says where the saving came from.

        Both backends see the same bytes. markdownify_html removes markup and
        keeps every word; trafilatura removes markup *and* the page furniture.
        The gap between them is the extraction, and it is the thing
        RESEARCH.md Category 7 says is routinely misattributed to Markdown
        syntax.
        """
        page = fixture_dir / "boilerplate.html"
        extracted = convert(pipeline, page, "trafilatura")
        raw = convert(pipeline, page, "markdownify_html")

        assert extracted.reduction_ratio is not None
        assert raw.reduction_ratio is not None
        assert extracted.reduction_ratio > raw.reduction_ratio + 0.20

    def test_the_boilerplate_metric_separates_text_from_markup(
        self, trafilatura_boilerplate: ConversionResult, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """Two numbers that must not be confused for one another.

        ``reduction_ratio`` counts everything that went away, markup included.
        ``boilerplate_reduction`` counts only the share of the page's *visible
        text* that was discarded, so a faithful markup converter scores near
        zero on it however many bytes it removed. Reporting one as the other is
        exactly the misattribution RESEARCH.md warns about.
        """
        raw = convert(pipeline, fixture_dir / "boilerplate.html", "markdownify_html")

        extracted_share = trafilatura_boilerplate.metadata["boilerplate_reduction"]
        raw_share = raw.metadata["boilerplate_reduction"]

        assert extracted_share > 0.30, "the extractor should discard a lot of the page's text"
        # Negative, and that is the point: markdownify discards none of the
        # page's text and *adds* Markdown syntax — bullets, link targets, table
        # pipes — so it emits more characters than the page had visible text
        # even while removing 45% of its bytes. Two numbers, opposite signs,
        # same conversion. Confusing them is the misattribution RESEARCH.md
        # Category 7 is about.
        assert raw_share < 0, "a markup converter adds syntax rather than discarding text"

    def test_the_clean_article_reduces_far_less_because_it_has_no_boilerplate(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """The control case, and the honest limit on the headline number.

        ``article.html`` is the same article with nothing wrapped around it.
        Extraction has almost nothing to remove, so the saving collapses — which
        is RESEARCH.md's own point that the win is about boilerplate and not
        about the format.
        """
        clean = convert(pipeline, fixture_dir / "article.html", "trafilatura")
        noisy = convert(pipeline, fixture_dir / "boilerplate.html", "trafilatura")

        assert clean.reduction_ratio is not None
        assert noisy.reduction_ratio is not None
        assert clean.reduction_ratio < noisy.reduction_ratio


class TestTrafilaturaFailureModes:
    """Documented in ``docs/BACKENDS.md``; asserted here so the docs cannot rot.

    Both of these were found by running the backend and reading the output, not
    by reasoning about what an extractor probably does. The first thing written
    here was a test asserting that trafilatura declines a page of nothing but
    links — it does not, it extracts the link text — and it was replaced by
    what actually happens.
    """

    def test_a_short_page_loses_its_structure_and_keeps_its_navigation(
        self, tmp_path: Path, pipeline: Pipeline
    ) -> None:
        """Below ~250 characters of content, extraction does not run at all.

        ``MIN_EXTRACTED_SIZE`` is 250 in trafilatura's default settings. Under
        it, the main algorithm yields nothing and a baseline extractor returns
        the page's raw text instead — with no Markdown structure and with the
        navigation still in it. So a short page gets neither of the two things
        this backend is for, and gets them silently.

        This is why the CLI tests pin ``--backend markdownify_html``: their
        four-element sample page is far under the threshold.
        """
        page = tmp_path / "short.html"
        page.write_text(
            "<html><body><nav><a href='/x'>Nav</a></nav>"
            "<h1>Title</h1><p>Body text here.</p></body></html>",
            encoding="utf-8",
        )

        result = pipeline.run(Source.from_path(page), OFFLINE.with_(backend="trafilatura"))

        assert "# Title" not in result.text, "structure unexpectedly survived; update BACKENDS.md"
        assert "Nav" in result.text, "navigation unexpectedly stripped; update BACKENDS.md"

    def test_a_long_enough_page_does_get_structure_and_does_lose_the_navigation(
        self, tmp_path: Path, pipeline: Pipeline
    ) -> None:
        """The other side of the same threshold, so the claim above is bounded.

        Without this, "short pages behave differently" would be untested as a
        *contrast* and could quietly become "all pages behave that way".
        """
        prose = "This is a sentence of real prose that is long enough to matter. " * 12
        page = tmp_path / "long.html"
        page.write_text(
            f"<html><body><nav><a href='/x'>Nav</a></nav>"
            f"<article><h1>Title</h1><p>{prose}</p></article></body></html>",
            encoding="utf-8",
        )

        result = pipeline.run(Source.from_path(page), OFFLINE.with_(backend="trafilatura"))

        assert "Nav" not in result.text
        assert prose.split(".")[0] in result.text

    def test_a_page_with_no_text_at_all_fails_so_the_chain_can_take_over(
        self, tmp_path: Path, pipeline: Pipeline
    ) -> None:
        """Failing rather than returning an empty document is deliberate.

        It lets another backend convert the page instead, and the attempt chain
        shows the user it happened. A scanned PDF is the opposite case — there
        is nothing for *anyone* to extract — and the document backends warn
        rather than fail on it.
        """
        page = tmp_path / "scriptonly.html"
        page.write_text(
            "<html><head><style>p{color:red}</style></head>"
            "<body><script>var x = 1;</script></body></html>",
            encoding="utf-8",
        )

        with pytest.raises(BackendFailed, match="no main content"):
            pipeline.run(Source.from_path(page), OFFLINE.with_(backend="trafilatura"))

    def test_that_failure_hands_over_to_the_whole_page_converter(
        self, tmp_path: Path, pipeline: Pipeline
    ) -> None:
        """The user still gets a result, and can see the chain that ran."""
        page = tmp_path / "scriptonly.html"
        page.write_text(
            "<html><head><style>p{color:red}</style></head>"
            "<body><script>var x = 1;</script></body></html>",
            encoding="utf-8",
        )

        result = pipeline.run(Source.from_path(page), OFFLINE)

        assert result.attempts[0].backend_id == "trafilatura"
        assert not result.attempts[0].ok
        assert any("fell back" in warning for warning in result.warnings)

    def test_an_empty_file_is_reported_as_corrupt(self, tmp_path: Path, pipeline: Pipeline) -> None:
        empty = tmp_path / "empty.html"
        empty.write_text("  \n", encoding="utf-8")

        with pytest.raises(CorruptSource, match="is empty"):
            pipeline.run(Source.from_path(empty), OFFLINE.with_(backend="trafilatura"))


@pytest.mark.requires("readability")
class TestReadability:
    def test_it_also_strips_every_boilerplate_marker(
        self, fixture_dir: Path, pipeline: Pipeline, boilerplate_markers: list[str]
    ) -> None:
        result = convert(pipeline, fixture_dir / "boilerplate.html", "readability")

        survivors = [m for m in boilerplate_markers if m in result.text]

        assert survivors == [], f"readability left {survivors}"

    def test_it_keeps_the_article_body(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "boilerplate.html", "readability")

        for sentence in ground_truth["article.html"]["must_contain"]:
            assert sentence in result.text

    def test_it_restores_the_title_the_algorithm_dropped(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The page header is discarded by readability, title included.

        The adapter puts back the title readability itself identified, rather
        than inventing one, because a document with no title is harder to use.
        """
        result = convert(pipeline, fixture_dir / "boilerplate.html", "readability")
        title = ground_truth["boilerplate.html"]["article_title"]

        assert f"# {title}" in result.text
        assert result.metadata["title"] == title

    def test_it_agrees_with_trafilatura_almost_exactly_on_this_page(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """Measured, and contrary to what the algorithms' reputations suggest.

        The obvious claim to make about readability is that it trades precision
        for recall. On ``boilerplate.html`` it does not: the two outputs are
        identical apart from the spacing inside the table's separator row,
        2,864 characters against 2,854. One fixture is not a benchmark, so no
        general claim about their relative quality is made anywhere — Phase 10's
        harness over a real corpus is what could support one.

        If an upstream release makes them diverge here, ``docs/BACKENDS.md``
        needs correcting and this test is what will say so.
        """
        page = fixture_dir / "boilerplate.html"
        readability = convert(pipeline, page, "readability")
        trafilatura = convert(pipeline, page, "trafilatura")

        difference = abs(len(readability.text) - len(trafilatura.text))

        assert difference < 0.05 * len(trafilatura.text), (
            f"the two extractors now differ by {difference} characters on this page; "
            f"docs/BACKENDS.md says they agree and needs updating"
        )

    def test_an_empty_file_is_reported_as_corrupt(self, tmp_path: Path, pipeline: Pipeline) -> None:
        empty = tmp_path / "empty.html"
        empty.write_text("  \n", encoding="utf-8")

        with pytest.raises(CorruptSource, match="is empty"):
            pipeline.run(Source.from_path(empty), OFFLINE.with_(backend="readability"))


class TestSelection:
    """Which backend actually runs, which is a product decision worth pinning."""

    def test_a_web_page_auto_selects_the_extractor(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """Phase 3's headline behaviour change, asserted rather than assumed."""
        result = pipeline.run(Source.from_path(fixture_dir / "boilerplate.html"), OFFLINE)

        assert result.backend_id == "trafilatura"

    def test_an_installed_documents_extra_cannot_change_which_backend_converts_a_page(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """The invariant written down in ``preferences.py``.

        markitdown, kreuzberg and docling all claim HTML. If installing a
        document extra could change which backend converts a web page, every
        measurement recorded in PROGRESS.md would stop being reproducible.
        """
        result = pipeline.run(Source.from_path(fixture_dir / "boilerplate.html"), OFFLINE)

        assert result.backend_id in {"trafilatura", "readability", "markdownify_html"}

    def test_auto_selection_never_reaches_for_the_browser(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """No browser without being asked for one by name.

        Starting a browser in a command a user thought was cheap is the same
        mistake as starting a model download, which Phase 2 settled for docling.
        """
        candidates = pipeline.backends.candidates(
            Source.from_path(fixture_dir / "boilerplate.html")
        )

        assert candidates[0].info.id != "crawl4ai"
        assert candidates[-1].info.id == "crawl4ai" or "crawl4ai" not in {
            c.info.id for c in candidates
        }


@pytest.mark.browser
@pytest.mark.requires("crawl4ai")
class TestCrawl4AI:
    """Everything here was observed by running it; see docs/BACKENDS.md.

    These need a Playwright browser as well as the package. Where one is
    absent the render fails with an actionable message rather than a
    traceback, which is itself asserted below.
    """

    def test_it_refuses_to_render_without_network_permission(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """A browser executes the page's scripts, which is more than a fetch."""
        with pytest.raises(NetworkRequired, match="browser"):
            pipeline.run(
                Source.from_path(fixture_dir / "boilerplate.html"),
                OFFLINE.with_(backend="crawl4ai"),
            )

    def test_the_refusal_points_at_the_backend_that_does_not_need_it(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        with pytest.raises(ConversionError) as excinfo:
            pipeline.run(
                Source.from_path(fixture_dir / "boilerplate.html"),
                OFFLINE.with_(backend="crawl4ai"),
            )

        assert excinfo.value.hint is not None
        assert "trafilatura" in excinfo.value.hint

    def test_it_sees_content_that_only_exists_after_javascript_runs(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The backend's whole reason for existing, checked rather than claimed.

        The sentinel is assembled from two halves by the fixture's own script,
        so it appears nowhere in the file's bytes. Finding it in the output is
        therefore proof that a browser executed the page, not that some text
        was located.
        """
        facts = ground_truth["jsrendered.html"]
        page = fixture_dir / "jsrendered.html"
        sentinel = facts["rendered_sentinel"]

        assert sentinel not in page.read_text(encoding="utf-8"), (
            "the sentinel leaked into the fixture's source, which makes this test vacuous; "
            "regenerate the corpus"
        )

        result = pipeline.run(Source.from_path(page), NETWORKED.with_(backend="crawl4ai"))

        assert result.text.count(sentinel) == facts["rendered_sentinel_occurrences"]
        assert facts["rendered_title"] in result.text
        assert facts["unrendered_placeholder"] not in result.text

    def test_a_parser_on_the_same_page_sees_only_the_placeholder(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The control. Without it the test above proves nothing about rendering."""
        facts = ground_truth["jsrendered.html"]

        result = pipeline.run(
            Source.from_path(fixture_dir / "jsrendered.html"),
            OFFLINE.with_(backend="trafilatura"),
        )

        assert facts["unrendered_placeholder"] in result.text
        assert facts["rendered_sentinel"] not in result.text

    def test_its_pruning_filter_leaves_boilerplate_trafilatura_removes(
        self, fixture_dir: Path, pipeline: Pipeline, boilerplate_markers: list[str]
    ) -> None:
        """The documented cost of choosing this backend, quoted from real output.

        Its filter scores blocks by text and link density rather than
        identifying an article, so a prose-heavy advertisement scores like
        prose. Three of the corpus's six markers survive — the cookie banner,
        the sponsored slot and the newsletter block — where trafilatura leaves
        none.

        If an upstream release improves this, the test fails and
        ``docs/BACKENDS.md`` gets corrected rather than quietly becoming a lie
        about a tool that has since got better.
        """
        result = pipeline.run(
            Source.from_path(fixture_dir / "boilerplate.html"),
            NETWORKED.with_(backend="crawl4ai"),
        )

        survivors = {m for m in boilerplate_markers if m in result.text}

        assert survivors == {
            "Accept all cookies",
            "SPONSORED: Cut your cloud bill by 40%",
            "Subscribe to our newsletter",
        }, f"crawl4ai's pruning now leaves {survivors}; update docs/BACKENDS.md"

    def test_it_keeps_the_headings_and_the_table(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """Weaker extraction, but it is not destroying structure to get there."""
        result = pipeline.run(
            Source.from_path(fixture_dir / "boilerplate.html"),
            NETWORKED.with_(backend="crawl4ai"),
        )

        for heading in ground_truth["boilerplate.html"]["expected_headings"]:
            assert heading in result.text, f"lost {heading!r}"
        # Cells are padded, so match on the row's content rather than its
        # exact spacing — CONTRIBUTING.md asks for structure, not bytes.
        assert "| markitdown " in result.text
        assert "| --- |" in result.text

    def test_a_small_client_rendered_page_is_refused_as_anti_bot_blocking(
        self, tmp_path: Path, pipeline: Pipeline
    ) -> None:
        """A false positive on exactly the pages this backend is for.

        Crawl4AI's anti-bot detector inspects the **un-rendered** response body
        and refuses any page under 5,000 bytes whose body holds fewer than 50
        characters of visible text, reporting
        ``Structural: minimal_text on small page``. A small single-page
        application shell is precisely that, so the one class of page a
        browser-driving backend is uniquely able to handle is the class its own
        guard rejects.

        tokenmill cannot fix this from outside, so it surfaces it as a typed,
        printable failure — and the chain then offers the page to a backend that
        can at least return the shell. ``tests/fixtures/jsrendered.html`` carries
        a full-sentence placeholder specifically to stay above the threshold.
        """
        shell = tmp_path / "spa.html"
        shell.write_text(
            "<html><body><div id='root'>Loading</div>"
            "<script>document.getElementById('root').textContent = 'Hydrated';</script>"
            "</body></html>",
            encoding="utf-8",
        )

        with pytest.raises(ConversionError, match=r"anti-bot|minimal_text"):
            pipeline.run(Source.from_path(shell), NETWORKED.with_(backend="crawl4ai"))

    def test_a_missing_browser_is_a_message_rather_than_a_traceback(
        self, fixture_dir: Path, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure a plain ``pip install crawl4ai`` actually produces.

        Installing the package does not install a browser; ``playwright
        install chromium`` does. Pointing Playwright at an empty directory
        reproduces that state without uninstalling anything.
        """
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_browsers := Path("/nonexistent")))
        del tmp_browsers

        with pytest.raises(ConversionError) as excinfo:
            pipeline.run(
                Source.from_path(fixture_dir / "jsrendered.html"),
                NETWORKED.with_(backend="crawl4ai"),
            )

        assert "Traceback" not in str(excinfo.value)
        assert excinfo.value.hint is not None
        assert "playwright install" in excinfo.value.hint
