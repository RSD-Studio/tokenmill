"""The `compare` command: one input, several backends or serialisations.

The behaviour worth defending here is not the arithmetic — that is checked
against `wc -c` in the verification log — but the two rules that keep the table
from being a machine for picking the worst converter:

* rows stay in preference order rather than being sorted by size;
* a fidelity score sits beside every token count, and where none exists the
  report says the comparison cannot answer the question.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from tokenmill.cli.format import format_backend_comparison
from tokenmill.cli.main import app
from tokenmill.core.compare import (
    BackendComparison,
    ComparisonRow,
    FormatComparison,
    compare_backends,
    compare_format_tables,
    compare_formats,
)
from tokenmill.core.models import ConvertOptions, Source, TokenCount
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import Registry
from tokenmill.fidelity.models import ComponentScore, FidelityScore
from tokenmill.formats.base import TableError, default_format_registry

runner = CliRunner()
OFFLINE = ["--tokenizer", "bytes"]


def _row(
    backend_id: str, tokens: int | None, fidelity: float | None, *, ok: bool = True
) -> ComparisonRow:
    """Build a comparison row without running a conversion."""
    score = (
        FidelityScore(
            fixture="f",
            backend_id=backend_id,
            components=(
                ComponentScore(component="content_recall", score=fidelity, expected=1, found=1),
            ),
        )
        if fidelity is not None
        else None
    )
    return ComparisonRow(
        backend_id=backend_id,
        tokens=TokenCount(value=tokens, tokenizer_id="bytes") if tokens is not None else None,
        characters=tokens,
        duration_s=0.01,
        fidelity=score,
        text="x" * (tokens or 0),
        error=None if ok else "it failed",
    )


class TestTheAntiLeaderboardRules:
    def test_rows_keep_preference_order_rather_than_being_sorted_by_size(self) -> None:
        comparison = BackendComparison(
            source_name="f",
            tokenizer_id="bytes",
            rows=(_row("first", 900, 1.0), _row("second", 100, 0.1)),
        )
        report = format_backend_comparison(comparison)
        assert report.index("first") < report.index("second")

    def test_the_cheapest_and_the_most_faithful_are_both_named(self) -> None:
        comparison = BackendComparison(
            source_name="f",
            tokenizer_id="bytes",
            rows=(_row("faithful", 900, 1.0), _row("small", 100, 0.1)),
        )
        assert comparison.cheapest is not None
        assert comparison.cheapest.backend_id == "small"
        assert comparison.most_faithful is not None
        assert comparison.most_faithful.backend_id == "faithful"

    def test_a_cheapest_that_is_not_the_best_is_stated_outright(self) -> None:
        comparison = BackendComparison(
            source_name="f",
            tokenizer_id="bytes",
            rows=(_row("faithful", 900, 1.0), _row("small", 100, 0.1)),
        )
        assert comparison.cheapest_is_most_faithful is False
        assert "NOT the most faithful" in format_backend_comparison(comparison)

    def test_agreement_is_stated_too(self) -> None:
        comparison = BackendComparison(
            source_name="f",
            tokenizer_id="bytes",
            rows=(_row("best", 100, 1.0), _row("worse", 900, 0.1)),
        )
        assert comparison.cheapest_is_most_faithful is True
        assert "also the most faithful" in format_backend_comparison(comparison)

    def test_no_ground_truth_says_the_table_cannot_answer_the_question(self) -> None:
        comparison = BackendComparison(
            source_name="f",
            tokenizer_id="bytes",
            rows=(_row("a", 100, None), _row("b", 900, None)),
        )
        assert comparison.cheapest_is_most_faithful is None
        report = format_backend_comparison(comparison)
        assert "cannot say what any of these savings cost" in report

    def test_a_failure_is_a_row_not_an_omission(self) -> None:
        comparison = BackendComparison(
            source_name="f",
            tokenizer_id="bytes",
            rows=(_row("works", 100, 1.0), _row("broken", None, None, ok=False)),
        )
        report = format_backend_comparison(comparison)
        assert "broken" in report
        assert "failed" in report


class TestCompareBackends:
    def test_every_named_backend_gets_a_row_including_the_ones_that_fail(
        self, fixture_dir: Path
    ) -> None:
        comparison = compare_backends(
            Source.from_path(fixture_dir / "tables.pdf"),
            ["pdfplumber", "no_such_backend"],
            options=ConvertOptions(tokenizer="bytes"),
            pipeline=Pipeline(backends=Registry()),
        )
        assert [row.backend_id for row in comparison.rows] == [
            "pdfplumber",
            "no_such_backend",
        ]
        assert comparison.rows[0].ok
        assert not comparison.rows[1].ok

    def test_a_row_is_produced_by_the_backend_it_names(self, fixture_dir: Path) -> None:
        # Fallback is forced off inside compare_backends: a row headed `pypdf`
        # that pdfplumber actually produced would make the table a lie.
        comparison = compare_backends(
            Source.from_path(fixture_dir / "corrupt.pdf"),
            ["pdfplumber", "pypdf"],
            options=ConvertOptions(tokenizer="bytes"),
            pipeline=Pipeline(backends=Registry()),
        )
        assert all(not row.ok for row in comparison.rows)

    def test_fidelity_is_scored_when_ground_truth_is_given(
        self, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        comparison = compare_backends(
            Source.from_path(fixture_dir / "tables.pdf"),
            ["pdfplumber"],
            options=ConvertOptions(tokenizer="bytes"),
            pipeline=Pipeline(backends=Registry()),
            truth=ground_truth["tables.pdf"],
            fixture="tables.pdf",
        )
        score = comparison.rows[0].fidelity
        assert score is not None
        assert score.get("table_integrity").score == 1.0


class TestCompareFormats:
    def test_every_format_encodes_the_same_table(self, fixture_dir: Path) -> None:
        text = (fixture_dir / "structured.md").read_text(encoding="utf-8")
        comparison = compare_formats(
            text,
            ["markdown", "csv", "json", "toon", "keyvalue"],
            registry=default_format_registry(),
            count=lambda s: len(s.encode("utf-8")),
            tokenizer_id="bytes",
            source_name="structured.md",
        )
        assert [row.format_id for row in comparison.rows] == [
            "markdown",
            "csv",
            "json",
            "toon",
            "keyvalue",
        ]
        assert all(row.ok for row in comparison.rows)

    def test_the_counts_are_the_encoded_lengths(self, fixture_dir: Path) -> None:
        text = (fixture_dir / "structured.md").read_text(encoding="utf-8")
        comparison = compare_formats(
            text,
            ["csv", "json"],
            registry=default_format_registry(),
            count=lambda s: len(s.encode("utf-8")),
            tokenizer_id="bytes",
            source_name="structured.md",
        )
        for row in comparison.rows:
            assert row.text is not None
            assert row.tokens is not None
            assert row.tokens.value == len(row.text.encode("utf-8"))

    def test_a_format_that_cannot_represent_the_table_is_a_row_not_a_crash(self) -> None:
        # MarkItDown's blank header row: JSON, TOON and key-value all key each
        # row by column name and cannot express it.
        text = "|  |  |\n| --- | --- |\n| Stage | Tokens |\n"
        comparison = compare_formats(
            text,
            ["markdown", "json"],
            registry=default_format_registry(),
            count=len,
            tokenizer_id="bytes",
            source_name="x",
        )
        by_id = {row.format_id: row for row in comparison.rows}
        assert by_id["markdown"].ok
        assert not by_id["json"].ok
        assert "no name" in (by_id["json"].error or "")


class TestTheCommand:
    def test_it_compares_a_document_across_its_backends(self, fixture_dir: Path) -> None:
        result = runner.invoke(app, ["compare", str(fixture_dir / "tables.pdf"), *OFFLINE])
        assert result.exit_code == 0, result.output
        assert "pdfplumber" in result.output
        assert "fidelity" in result.output

    def test_ground_truth_is_detected_for_a_file_inside_the_corpus(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app,
            ["compare", str(fixture_dir / "tables.pdf"), "--corpus", str(fixture_dir), *OFFLINE],
        )
        assert "no ground truth" not in result.output
        assert "most faithful:" in result.output

    def test_ground_truth_is_not_guessed_from_a_filename_alone(
        self, fixture_dir: Path, tmp_path: Path
    ) -> None:
        # Scoring somebody's own tables.pdf against ours would produce a
        # plausible number that means nothing.
        impostor = tmp_path / "tables.pdf"
        impostor.write_bytes((fixture_dir / "tables.pdf").read_bytes())
        result = runner.invoke(
            app, ["compare", str(impostor), "--corpus", str(fixture_dir), *OFFLINE]
        )
        assert "cannot say what any of these savings cost" in result.output

    def test_named_backends_are_honoured(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app,
            ["compare", str(fixture_dir / "tables.pdf"), "--backends", "pypdf", *OFFLINE],
        )
        assert result.exit_code == 0, result.output
        assert "pypdf" in result.output
        assert "pdfplumber" not in result.output

    def test_formats_are_compared_when_asked(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app,
            [
                "compare",
                str(fixture_dir / "tables.pdf"),
                "--backends",
                "pdfplumber",
                "--formats",
                "csv,toon,json",
                *OFFLINE,
            ],
        )
        assert result.exit_code == 0, result.output
        assert "serialisation(s)" in result.output
        assert "toon" in result.output

    def test_a_source_with_no_table_says_so_rather_than_crashing(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app,
            [
                "compare",
                str(fixture_dir / "long_context.md"),
                "--formats",
                "csv",
                *OFFLINE,
            ],
        )
        assert result.exit_code == 1
        assert "table" in result.output

    def test_variants_are_written_for_eyeballing(self, fixture_dir: Path, tmp_path: Path) -> None:
        out = tmp_path / "variants"
        result = runner.invoke(
            app,
            [
                "compare",
                str(fixture_dir / "tables.pdf"),
                "--backends",
                "pdfplumber,pypdf",
                "--formats",
                "csv",
                "--write",
                str(out),
                *OFFLINE,
            ],
        )
        assert result.exit_code == 0, result.output
        assert (out / "pdfplumber.md").exists()
        assert (out / "pypdf.md").exists()
        assert (out / "table.csv").exists()

    def test_the_written_variants_match_the_reported_counts(
        self, fixture_dir: Path, tmp_path: Path
    ) -> None:
        # The exit-gate check, as a test: every number in the table is the
        # byte length of the file it wrote.
        #
        # This can only fail on Windows, and it did: text-mode writing rewrote
        # every \n as \r\n, so pdfplumber's file was 615 bytes against a
        # reported 599. There is no way to provoke that on Linux or macOS, so
        # the CI Windows cells are the only place this assertion has teeth --
        # which is the argument for keeping them.
        out = tmp_path / "variants"
        result = runner.invoke(
            app,
            [
                "compare",
                str(fixture_dir / "tables.pdf"),
                "--backends",
                "pdfplumber,pypdf",
                "--write",
                str(out),
                "--json",
                *OFFLINE,
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        for row in payload["backends"]["rows"]:
            if row["tokens"] is None:
                continue
            written = (out / f"{row['backend']}.md").read_bytes()
            assert len(written) == row["tokens"], row["backend"]
            assert b"\r\n" not in written, row["backend"]

    def test_json_carries_the_verdict(self, fixture_dir: Path) -> None:
        """Pinned to a fixed backend set, because the verdict depends on one.

        This asked for *every available* backend until Phase 7, and the answer
        changed the moment `pymupdf4llm` was registered: on `tables.pdf` it
        scores 0.848 against pdfplumber's 0.667 and became the most faithful.
        Nothing was wrong with either the old assertion or the new backend — the
        test was reading an answer that depends on what happens to be installed,
        which is the class of bug CI found twenty-one of when it first ran.

        So the identities are asserted against a named set, and the property
        that actually matters is asserted separately, over whatever is there.
        """
        result = runner.invoke(
            app,
            [
                "compare",
                str(fixture_dir / "tables.pdf"),
                "--backends",
                "pdfplumber,kreuzberg,pypdf",
                "--corpus",
                str(fixture_dir),
                "--json",
                *OFFLINE,
            ],
        )
        payload = json.loads(result.stdout)
        assert payload["backends"]["cheapest"] == "kreuzberg"
        assert payload["backends"]["most_faithful"] == "pdfplumber"
        assert payload["backends"]["cheapest_is_most_faithful"] is False

    def test_the_cheapest_backend_is_not_the_most_faithful_whatever_is_installed(
        self, fixture_dir: Path
    ) -> None:
        """The finding, over the real backend set rather than a pinned one.

        `tables.pdf` exists to make this true: the cheapest converter gets there
        by destroying the table. Which backend wins each half varies with what is
        installed; that they are different backends does not, and it is the
        reason `compare` is not sorted by size.
        """
        result = runner.invoke(
            app,
            [
                "compare",
                str(fixture_dir / "tables.pdf"),
                "--corpus",
                str(fixture_dir),
                "--json",
                *OFFLINE,
            ],
        )
        payload = json.loads(result.stdout)["backends"]

        assert payload["cheapest"] != payload["most_faithful"]
        assert payload["cheapest_is_most_faithful"] is False


class TestEveryTableIsCompared:
    """Defect N4: `--formats` re-encoded the first table and stopped.

    Invisible on this corpus, because `tables.pdf` has exactly one table — which
    is why the defect survived five phases and why the input here is written by
    hand rather than taken from a fixture. Adding a three-table fixture to make
    the bug visible would be a fixture added to flatter a test, which
    `CONTRIBUTING.md` and the handover both rule out.
    """

    TEXT = (
        "# Report\n\n"
        "| Region | Q1 | Q2 |\n| --- | --- | --- |\n| North | 120 | 140 |\n"
        "| South | 90 | 95 |\n\n"
        "Prose between the tables.\n\n"
        "| Team | People |\n| --- | --- |\n| Platform | 12 |\n| Data | 7 |\n\n"
        "More prose.\n\n"
        "| Date | Severity |\n| --- | --- |\n| 2026-01-04 | high |\n"
    )

    def _compare(self, text: str) -> tuple[FormatComparison, ...]:
        """Compare every table in `text` across two formats.

        Args:
            text: The Markdown to read.

        Returns:
            One comparison per table.
        """
        return compare_format_tables(
            text,
            ["markdown", "csv"],
            registry=default_format_registry(),
            count=len,
            tokenizer_id="bytes",
            source_name="report.md",
        )

    def test_a_three_table_document_produces_three_comparisons(self) -> None:
        comparisons = self._compare(self.TEXT)

        assert len(comparisons) == 3

    def test_each_comparison_knows_which_table_it_is(self) -> None:
        """So a report can say "table 2 of 3" rather than showing one silently."""
        comparisons = self._compare(self.TEXT)

        assert [c.table_index for c in comparisons] == [0, 1, 2]
        assert [c.table_count for c in comparisons] == [3, 3, 3]

    def test_the_tables_are_the_right_ones_in_document_order(self) -> None:
        comparisons = self._compare(self.TEXT)

        assert [len(c.table.headers) for c in comparisons] == [3, 2, 2]
        assert [len(c.table.rows) for c in comparisons] == [2, 2, 1]
        assert comparisons[0].table.headers == ("Region", "Q1", "Q2")
        assert comparisons[2].table.headers == ("Date", "Severity")

    def test_tables_of_different_shapes_can_have_different_cheapest_formats(self) -> None:
        """The reason comparing only the first is wrong, not merely incomplete.

        A document's tables do not share an answer: the cheapest serialisation
        depends on the shape, so reporting the first table's verdict as the
        document's is a measurement of a question nobody asked.
        """
        comparisons = self._compare(self.TEXT)

        assert all(c.cheapest is not None for c in comparisons)
        sizes = [c.cheapest.characters for c in comparisons if c.cheapest]
        assert len(set(sizes)) > 1, (
            "every table encoded to the same size, so this input cannot "
            "demonstrate that the tables are independently compared"
        )

    def test_a_single_table_document_still_reports_a_count_of_one(self) -> None:
        """The common case keeps its shape; nothing says "table 1 of 1"."""
        comparisons = self._compare("| a | b |\n| --- | --- |\n| 1 | 2 |\n")

        assert len(comparisons) == 1
        assert comparisons[0].table_count == 1

    def test_text_with_no_table_still_raises(self) -> None:
        with pytest.raises(TableError, match="no Markdown table"):
            self._compare("Just prose, no tables at all.\n")
