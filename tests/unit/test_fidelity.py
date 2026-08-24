"""The fidelity scorer, tested against text written by hand.

The first test in this file is the one that makes the metric worth having: a
converter that emits nothing must not score well. Everything else follows from
`benchmarks/README.md`'s rule that a token saving without a fidelity number is
not a result.

Backend output is scored in `tests/integration/test_fidelity_backends.py`; this
file uses hand-written text so every expected number can be counted by eye.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from tokenmill.core.errors import ConfigError
from tokenmill.fidelity import COMPONENTS, load_ground_truth, resolve_fixture, score
from tokenmill.fidelity import markdown as md

BOILERPLATE_TRUTH: dict[str, Any] = {
    "expected_headings": ["Alpha", "Beta"],
    "must_contain": ["load-bearing", "pdfplumber"],
    "boilerplate_markers_must_be_absent": ["Accept all cookies", "Subscribe now"],
    "table_rows_including_header": 2,
    "table_columns": 2,
}

GOOD_OUTPUT = """# Alpha

The rule is load-bearing.

## Beta

| Backend | License |
| --- | --- |
| pdfplumber | MIT |
"""


class TestTheEmptyDocument:
    """A converter that emits nothing scores nothing.

    This is the failure `benchmarks/README.md` names, and the arithmetic alone
    does not prevent it: an empty string genuinely contains no boilerplate, so
    `boilerplate_rejection` would score it 1.0 without the explicit rule.
    """

    @pytest.mark.parametrize("text", ["", "   ", "\n\n\t\n"])
    def test_an_empty_document_scores_zero_on_every_scored_component(self, text: str) -> None:
        result = score(text, BOILERPLATE_TRUTH, fixture="synthetic")
        scored = [c for c in result.components if c.scored]
        assert scored, "the fixture should have supported at least one component"
        assert all(c.score == 0.0 for c in scored), [(c.component, c.score) for c in scored]

    def test_an_empty_document_is_not_credited_for_rejecting_boilerplate(self) -> None:
        result = score("", BOILERPLATE_TRUTH, fixture="synthetic")
        rejection = result.get("boilerplate_rejection")
        assert rejection.score == 0.0
        assert "no content" in rejection.detail

    def test_an_empty_document_scores_zero_overall(self) -> None:
        assert score("", BOILERPLATE_TRUTH, fixture="synthetic").overall == 0.0

    def test_an_empty_document_does_not_invent_components_it_has_no_truth_for(self) -> None:
        result = score("", BOILERPLATE_TRUTH, fixture="synthetic")
        assert result.get("reading_order").score is None
        assert result.get("structure_retention").score is None


class TestAMissingScoreIsNotAZero:
    """`None` means "not measured here" and never "measured as zero"."""

    def test_a_component_without_ground_truth_scores_none(self) -> None:
        result = score(GOOD_OUTPUT, {"must_contain": ["load-bearing"]}, fixture="synthetic")
        assert result.get("heading_recall").score is None
        assert result.get("table_integrity").score is None
        assert result.get("reading_order").score is None

    def test_an_unscored_component_says_why(self) -> None:
        result = score(GOOD_OUTPUT, {"must_contain": ["x"]}, fixture="synthetic")
        assert "no headings" in result.get("heading_recall").detail

    def test_every_component_is_present_even_when_it_did_not_apply(self) -> None:
        result = score(GOOD_OUTPUT, {}, fixture="synthetic")
        assert tuple(c.component for c in result.components) == COMPONENTS

    def test_a_score_with_no_ground_truth_at_all_has_no_overall(self) -> None:
        result = score(GOOD_OUTPUT, {}, fixture="synthetic")
        assert result.overall is None
        assert result.scored_components == ()

    def test_the_overall_names_the_components_it_is_made_of(self) -> None:
        result = score(GOOD_OUTPUT, BOILERPLATE_TRUTH, fixture="synthetic")
        assert result.scored_components == (
            "heading_recall",
            "content_recall",
            "table_integrity",
            "boilerplate_rejection",
        )

    def test_the_overall_is_the_unweighted_mean_of_what_scored(self) -> None:
        result = score(GOOD_OUTPUT, BOILERPLATE_TRUTH, fixture="synthetic")
        scores = [c.score for c in result.components if c.score is not None]
        assert result.overall == pytest.approx(sum(scores) / len(scores))


class TestHeadingRecall:
    def test_a_heading_that_survived_as_a_heading_counts(self) -> None:
        result = score(GOOD_OUTPUT, BOILERPLATE_TRUTH, fixture="synthetic")
        assert result.get("heading_recall").score == 1.0

    def test_a_heading_that_survived_only_as_prose_does_not_count(self) -> None:
        text = "Alpha\n\nBeta\n\nload-bearing pdfplumber\n"
        component = score(text, BOILERPLATE_TRUTH, fixture="synthetic").get("heading_recall")
        assert component.score == 0.0
        assert "present as plain text" in component.detail

    def test_a_setext_heading_counts_as_a_heading(self) -> None:
        text = "Alpha\n=====\n\nBeta\n----\n"
        component = score(text, {"expected_headings": ["Alpha", "Beta"]}, fixture="s").get(
            "heading_recall"
        )
        assert component.score == 1.0

    def test_a_level_is_enforced_when_ground_truth_records_one(self) -> None:
        truth = {"expected_headings": [["Title", 0], ["Section", 1]]}
        good = score("# Title\n\n## Section\n", truth, fixture="s").get("heading_recall")
        assert good.score == 1.0
        demoted = score("## Title\n\n## Section\n", truth, fixture="s").get("heading_recall")
        assert demoted.score == 0.5
        assert "found at level 2, expected 1" in demoted.missing[0]

    def test_a_heading_inside_a_code_fence_is_not_a_heading(self) -> None:
        text = "```sh\n# Alpha\n```\n\n## Beta\n"
        component = score(text, {"expected_headings": ["Alpha", "Beta"]}, fixture="s").get(
            "heading_recall"
        )
        assert component.score == 0.5
        assert component.missing == ("Alpha",)

    def test_missing_headings_are_named_rather_than_counted(self) -> None:
        truth = {"expected_headings": ["Alpha", "Gamma"]}
        component = score("# Alpha\n", truth, fixture="s").get("heading_recall")
        assert component.missing == ("Gamma",)


class TestContentRecall:
    def test_required_passages_present_score_one(self) -> None:
        assert score(GOOD_OUTPUT, BOILERPLATE_TRUTH, fixture="s").get("content_recall").score == 1.0

    def test_a_reflowed_passage_still_counts(self) -> None:
        truth = {"must_contain": ["the rule is load-bearing"]}
        text = "The rule\nis   load-bearing.\n"
        assert score(text, truth, fixture="s").get("content_recall").score == 1.0

    def test_a_dropped_passage_is_named(self) -> None:
        truth = {"must_contain": ["kept", "dropped"]}
        component = score("kept\n", truth, fixture="s").get("content_recall")
        assert component.score == 0.5
        assert component.missing == ("dropped",)


class TestTableIntegrity:
    def test_a_table_that_stayed_a_table_scores_one(self) -> None:
        assert (
            score(GOOD_OUTPUT, BOILERPLATE_TRUTH, fixture="s").get("table_integrity").score == 1.0
        )

    def test_a_table_flattened_into_prose_scores_zero(self) -> None:
        text = "# Alpha\n\n## Beta\n\nBackend License pdfplumber MIT load-bearing\n"
        assert score(text, BOILERPLATE_TRUTH, fixture="s").get("table_integrity").score == 0.0

    def test_known_cell_values_must_be_inside_a_table_not_merely_present(self) -> None:
        truth = {"table_cells": 4, "table_header": ["Backend", "License"]}
        prose = "Backend License pdfplumber MIT\n"
        assert score(prose, truth, fixture="s").get("table_integrity").score == 0.0
        table = "| Backend | License |\n| --- | --- |\n| pdfplumber | MIT |\n"
        assert score(table, truth, fixture="s").get("table_integrity").score == 1.0

    def test_pipes_without_a_delimiter_row_are_not_a_table(self) -> None:
        text = "| Backend | License |\n| pdfplumber | MIT |\n"
        truth = {"table_cells": 4, "table_header": ["Backend", "License"]}
        assert score(text, truth, fixture="s").get("table_integrity").score == 0.0

    def test_blank_cells_are_not_recovered_cells(self) -> None:
        # MarkItDown emits report.docx's table with an invented blank header
        # row and the real header demoted to a body row. The four parsed cells
        # include two blanks; counting those would score 4 of 4 and hide the
        # two cells that really were lost.
        text = "|  |  |\n| --- | --- |\n| Stage | Tokens |\n"
        truth = {"table_rows_including_header": 2, "table_columns": 2}
        component = score(text, truth, fixture="s").get("table_integrity")
        assert component.found == 2
        assert component.score == 0.5

    def test_a_table_split_in_two_is_not_penalised(self) -> None:
        text = "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n| c | d |\n| --- | --- |\n| 3 | 4 |\n"
        truth = {"table_rows_including_header": 2, "table_columns": 2}
        assert score(text, truth, fixture="s").get("table_integrity").score == 1.0


class TestStructureRetention:
    def test_list_items_must_come_back_as_list_items(self) -> None:
        truth = {"bullet_items": ["Strip navigation", "Strip advertising"]}
        as_list = "- Strip navigation\n- Strip advertising\n"
        assert score(as_list, truth, fixture="s").get("structure_retention").score == 1.0
        as_prose = "Strip navigation. Strip advertising.\n"
        assert score(as_prose, truth, fixture="s").get("structure_retention").score == 0.0

    def test_link_targets_count_in_any_lossless_form(self) -> None:
        truth = {"expected_link_targets": ["https://example.com/a"]}
        inline = "[a](https://example.com/a)\n"
        reference = "[a][1]\n\n[1]: https://example.com/a\n"
        for text in (inline, reference):
            assert score(text, truth, fixture="s").get("structure_retention").score == 1.0

    def test_a_stripped_link_target_is_a_loss(self) -> None:
        truth = {"expected_link_targets": ["https://example.com/a"]}
        assert score("a\n", truth, fixture="s").get("structure_retention").score == 0.0

    def test_code_fences_are_counted(self) -> None:
        truth = {"expected_code_fences": 2}
        both = "```py\nx = 1\n```\n\n```sh\nls\n```\n"
        assert score(both, truth, fixture="s").get("structure_retention").score == 1.0
        one = "```py\nx = 1\n```\n"
        assert score(one, truth, fixture="s").get("structure_retention").score == 0.5


class TestBoilerplateRejection:
    def test_boilerplate_that_is_gone_scores_one(self) -> None:
        assert (
            score(GOOD_OUTPUT, BOILERPLATE_TRUTH, fixture="s").get("boilerplate_rejection").score
            == 1.0
        )

    def test_boilerplate_that_stayed_scores_zero_and_is_named(self) -> None:
        text = GOOD_OUTPUT + "\nAccept all cookies\nSubscribe now\n"
        component = score(text, BOILERPLATE_TRUTH, fixture="s").get("boilerplate_rejection")
        assert component.score == 0.0
        assert set(component.missing) == {"Accept all cookies", "Subscribe now"}

    def test_must_not_contain_is_read_as_boilerplate_too(self) -> None:
        truth = {"must_not_contain": ["SECRET_KEY"]}
        assert score("safe\n", truth, fixture="s").get("boilerplate_rejection").score == 1.0
        assert score("SECRET_KEY=1\n", truth, fixture="s").get("boilerplate_rejection").score == 0.0


class TestReadingOrder:
    MARKERS: ClassVar[dict[str, Any]] = {"order_markers": [f"MARK {i:02d}" for i in range(1, 5)]}

    def test_sentinels_in_order_score_one(self) -> None:
        text = "\n".join(f"MARK {i:02d}" for i in range(1, 5))
        assert score(text, self.MARKERS, fixture="s").get("reading_order").score == 1.0

    def test_interleaved_sentinels_score_below_one(self) -> None:
        text = "MARK 01\nMARK 03\nMARK 02\nMARK 04\n"
        component = score(text, self.MARKERS, fixture="s").get("reading_order")
        assert component.score is not None
        assert 0.0 < component.score < 1.0

    def test_reversed_sentinels_score_the_floor(self) -> None:
        text = "\n".join(f"MARK {i:02d}" for i in range(4, 0, -1))
        assert score(text, self.MARKERS, fixture="s").get("reading_order").score == 0.25

    def test_absent_sentinels_count_against_the_score(self) -> None:
        # Two sentinels kept in sequence is not a reading-order pass for a
        # document that lost the other two.
        text = "MARK 01\nMARK 02\n"
        component = score(text, self.MARKERS, fixture="s").get("reading_order")
        assert component.score == 0.5
        assert "2 of 4 were present at all" in component.detail
        assert set(component.missing) == {"MARK 03", "MARK 04"}


class TestTheMarkdownReader:
    def test_a_pipe_inside_a_code_fence_is_not_a_table(self) -> None:
        assert md.tables("```sh\n| a | b |\n| --- | --- |\n```\n") == ()

    def test_a_list_marker_inside_a_code_fence_is_not_a_list(self) -> None:
        assert md.list_item_lines("```sh\n- not a list\n```\n") == ()

    def test_an_unterminated_fence_still_counts_as_one_block(self) -> None:
        assert md.code_fence_count("```py\nx = 1\n") == 1

    def test_a_thematic_break_is_not_a_setext_heading(self) -> None:
        assert md.headings("\n---\n") == ()

    def test_image_and_link_targets_are_both_returned(self) -> None:
        text = "![alt](img.png) and [text](https://example.com)\n"
        assert md.link_targets(text) == ("img.png", "https://example.com")

    def test_an_image_is_not_double_counted_as_a_link(self) -> None:
        assert md.link_targets("![alt](img.png)\n") == ("img.png",)

    def test_closing_hashes_are_not_part_of_the_title(self) -> None:
        assert md.headings("## Beta ##\n") == (md.Heading(2, "Beta"),)


class TestGroundTruthLoading:
    def test_the_repository_corpus_loads(self, fixture_dir: Path) -> None:
        fixtures = load_ground_truth(fixture_dir)
        assert "boilerplate.html" in fixtures

    def test_a_directory_or_a_file_both_work(self, fixture_dir: Path) -> None:
        by_dir = load_ground_truth(fixture_dir)
        by_file = load_ground_truth(fixture_dir / "ground_truth.json")
        assert by_dir.keys() == by_file.keys()

    def test_a_path_resolves_to_its_fixture(self, fixture_dir: Path) -> None:
        fixtures = load_ground_truth(fixture_dir)
        name, truth = resolve_fixture(fixtures, "tests/fixtures/tables.pdf")
        assert name == "tables.pdf"
        assert truth["table_cells"] == 35

    def test_a_directory_fixture_resolves_without_its_trailing_slash(
        self, fixture_dir: Path
    ) -> None:
        fixtures = load_ground_truth(fixture_dir)
        name, _ = resolve_fixture(fixtures, "sample_repo")
        assert name == "sample_repo/"

    def test_an_unknown_fixture_lists_what_is_available(self, fixture_dir: Path) -> None:
        fixtures = load_ground_truth(fixture_dir)
        with pytest.raises(ConfigError) as caught:
            resolve_fixture(fixtures, "nope.pdf")
        assert "tables.pdf" in (caught.value.hint or "")

    def test_a_missing_manifest_names_the_regeneration_command(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError) as caught:
            load_ground_truth(tmp_path)
        assert "make_fixtures.py" in (caught.value.hint or "")

    def test_invalid_json_is_a_config_error_not_a_traceback(self, tmp_path: Path) -> None:
        (tmp_path / "ground_truth.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_ground_truth(tmp_path)

    def test_a_manifest_without_fixtures_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "ground_truth.json").write_text('{"other": 1}', encoding="utf-8")
        with pytest.raises(ConfigError):
            load_ground_truth(tmp_path)
