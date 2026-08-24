"""The fidelity scorer against real backend output.

`tests/unit/test_fidelity.py` proves the arithmetic on text written by hand.
This file proves the thing that actually matters: that the score separates
backends whose difference `docs/BACKENDS.md` already documents in prose.

The four claims held here are the acceptance criteria for the Phase 10 fidelity
slice, and each is a claim about a *pair* of results rather than about one
number, because that is what a fidelity score is for:

* trafilatura and markdownify_html both keep the article, and only trafilatura
  removes the website around it. High recall alone does not say extraction
  worked; high rejection alone does not either.
* pdfplumber keeps `tables.pdf`'s grid and kreuzberg flattens it, which
  `docs/BACKENDS.md` records as "the table is destroyed... one run-on
  paragraph".
* pypdf reads `twocolumn.pdf` in the right order and pdfplumber interleaves the
  columns, which until now was a warning rather than a number.

Everything here is offline and measured in nothing at all — the fidelity score
needs no tokenizer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tokenmill.core.models import ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import Registry
from tokenmill.fidelity import FidelityScore, resolve_fixture, score

pytestmark = pytest.mark.integration

OFFLINE = ConvertOptions(tokenizer="bytes", fetch=False)


@pytest.fixture(scope="module")
def pipeline() -> Pipeline:
    """Return a pipeline over the really-installed backends."""
    return Pipeline(backends=Registry())


def fidelity(
    pipeline: Pipeline,
    fixture_dir: Path,
    ground_truth: dict[str, Any],
    fixture: str,
    backend: str,
) -> FidelityScore:
    """Convert one fixture with one backend and score the result.

    Args:
        pipeline: The pipeline to run.
        fixture_dir: Where the corpus lives.
        ground_truth: The loaded manifest.
        fixture: The fixture's filename.
        backend: The backend id to force.

    Returns:
        The fidelity score for that backend's output.
    """
    result = pipeline.run(Source.from_path(fixture_dir / fixture), OFFLINE.with_(backend=backend))
    name, truth = resolve_fixture(ground_truth, fixture)
    return score(result.text, truth, fixture=name, backend_id=backend)


def scored(result: FidelityScore, component: str) -> float:
    """Return one component's score, failing loudly if it did not apply.

    Keeps "this component had no ground truth" a different test failure from
    "this component scored badly", which is the distinction the whole scorer is
    built to preserve.

    Args:
        result: The score to read.
        component: The axis to fetch.

    Returns:
        That component's score.
    """
    value = result.get(component).score
    assert value is not None, f"{component} had no ground truth to score against"
    return value


class TestExtractionNeedsBothHalves:
    """Recall and rejection together are what say extraction worked."""

    @pytest.mark.requires("trafilatura")
    def test_trafilatura_keeps_the_article_and_removes_the_website(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        result = fidelity(pipeline, fixture_dir, ground_truth, "boilerplate.html", "trafilatura")
        assert result.get("content_recall").score == 1.0
        assert result.get("heading_recall").score == 1.0
        assert result.get("boilerplate_rejection").score == 1.0

    def test_markdownify_keeps_the_article_and_the_website_with_it(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        # Correct behaviour for this backend: it converts markup faithfully and
        # does not extract. The near-zero rejection is the measurement that
        # says so, and PROGRESS.md has said it in prose since Phase 1.
        result = fidelity(
            pipeline, fixture_dir, ground_truth, "boilerplate.html", "markdownify_html"
        )
        assert result.get("content_recall").score == 1.0
        assert result.get("heading_recall").score == 1.0
        assert result.get("boilerplate_rejection").score == 0.0

    @pytest.mark.requires("trafilatura")
    def test_the_pair_is_what_separates_them_not_either_number_alone(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        extracted = fidelity(pipeline, fixture_dir, ground_truth, "boilerplate.html", "trafilatura")
        converted = fidelity(
            pipeline, fixture_dir, ground_truth, "boilerplate.html", "markdownify_html"
        )
        assert scored(extracted, "content_recall") == scored(converted, "content_recall")
        assert extracted.overall is not None
        assert converted.overall is not None
        assert extracted.overall > converted.overall


class TestATableThatSurvivedAsATable:
    """`docs/BACKENDS.md`: Kreuzberg destroys `tables.pdf`'s grid."""

    def test_pdfplumber_recovers_the_grid(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        result = fidelity(pipeline, fixture_dir, ground_truth, "tables.pdf", "pdfplumber")
        assert result.get("table_integrity").score == 1.0

    @pytest.mark.requires("kreuzberg")
    def test_kreuzberg_scores_far_below_pdfplumber_on_the_same_file(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        # If this fails because kreuzberg improved, that is good news: update
        # docs/BACKENDS.md's "Failure modes" section and this assertion.
        flattened = fidelity(pipeline, fixture_dir, ground_truth, "tables.pdf", "kreuzberg")
        grid = fidelity(pipeline, fixture_dir, ground_truth, "tables.pdf", "pdfplumber")
        assert scored(flattened, "table_integrity") < scored(grid, "table_integrity") - 0.5

    @pytest.mark.requires("kreuzberg")
    def test_kreuzberg_keeps_the_words_it_lost_the_grid(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        # The point of scoring tables separately: content recall cannot see this.
        result = fidelity(pipeline, fixture_dir, ground_truth, "tables.pdf", "kreuzberg")
        assert result.get("content_recall").score == 1.0
        assert result.get("table_integrity").score == 0.0


class TestReadingOrderIsNowANumber:
    """pdfplumber interleaves `twocolumn.pdf`; pypdf does not."""

    def test_pypdf_reads_the_columns_in_order(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        result = fidelity(pipeline, fixture_dir, ground_truth, "twocolumn.pdf", "pypdf")
        assert result.get("reading_order").score == 1.0

    def test_pdfplumber_interleaves_and_the_score_shows_it(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        result = fidelity(pipeline, fixture_dir, ground_truth, "twocolumn.pdf", "pdfplumber")
        assert scored(result, "reading_order") < 1.0

    def test_content_recall_cannot_see_the_difference(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        # Both backends recover every sentinel; only their order differs. This
        # is the whole reason reading order is its own component.
        interleaved = fidelity(pipeline, fixture_dir, ground_truth, "twocolumn.pdf", "pdfplumber")
        ordered = fidelity(pipeline, fixture_dir, ground_truth, "twocolumn.pdf", "pypdf")
        assert scored(interleaved, "content_recall") == scored(ordered, "content_recall")
        assert "12 of 12 were present at all" in interleaved.get("reading_order").detail


class TestAConverterThatEmitsNothing:
    """The failure `benchmarks/README.md` names, against a real fixture."""

    def test_an_empty_conversion_scores_zero_against_a_real_fixture(
        self, ground_truth: dict[str, Any]
    ) -> None:
        name, truth = resolve_fixture(ground_truth, "boilerplate.html")
        assert score("", truth, fixture=name).overall == 0.0

    def test_a_scanned_pdf_with_no_text_layer_scores_zero(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        # Every backend returns an empty document for scanned.pdf and every one
        # of them warns. Its ground truth states what the page says anyway, so
        # the score reads 0.0 rather than staying silent: that is the honest
        # measurement of "this tier has no OCR", and Phase 9 should move it.
        result = pipeline.run(
            Source.from_path(fixture_dir / "scanned.pdf"), OFFLINE.with_(backend="pdfplumber")
        )
        name, truth = resolve_fixture(ground_truth, "scanned.pdf")
        assert result.text.strip() == ""
        assert score(result.text, truth, fixture=name).overall == 0.0


class TestAGreatReductionThatLostTheContent:
    """The result the whole slice exists to contradict.

    `convert jsrendered.html` reports the largest reduction in the corpus,
    -90.7%, and achieves it by losing every word of the article: the page's
    content is inserted by a script, so a parser sees a placeholder. Defect D1
    added a warning for this in the last phase. A warning is not a number, and
    a benchmark table full of numbers is where this result would otherwise
    look like the best one on the page.
    """

    @pytest.mark.requires("trafilatura")
    def test_the_biggest_reduction_in_the_corpus_scores_the_worst_fidelity(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        result = fidelity(pipeline, fixture_dir, ground_truth, "jsrendered.html", "trafilatura")
        assert result.overall == 0.0
        assert scored(result, "content_recall") == 0.0
        assert scored(result, "heading_recall") == 0.0

    def test_the_placeholder_is_what_came_back_instead(
        self, pipeline: Pipeline, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        # Not an empty document — a document full of the wrong thing, which no
        # emptiness check would catch.
        result = pipeline.run(
            Source.from_path(fixture_dir / "jsrendered.html"),
            OFFLINE.with_(backend="markdownify_html"),
        )
        assert result.text.strip()
        name, truth = resolve_fixture(ground_truth, "jsrendered.html")
        assert score(result.text, truth, fixture=name).overall == 0.0
