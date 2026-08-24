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

from typer.testing import CliRunner

from tokenmill.cli.format import format_backend_comparison
from tokenmill.cli.main import app
from tokenmill.core.compare import (
    BackendComparison,
    ComparisonRow,
    compare_backends,
    compare_formats,
)
from tokenmill.core.models import ConvertOptions, Source, TokenCount
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import Registry
from tokenmill.fidelity.models import ComponentScore, FidelityScore
from tokenmill.formats.base import default_format_registry

runner = CliRunner()
OFFLINE = ["--tokenizer", "bytes"]


def _json_part(output: str) -> str:
    """Return just the JSON from mixed stdout and stderr.

    tokenmill writes machine output to stdout and everything else to stderr, but
    Click 8.4's test runner merges the two, so `--write`'s "wrote N variants"
    note lands after the JSON document.

    Args:
        output: The captured output.

    Returns:
        The JSON document.
    """
    return output[: output.rindex("}") + 1]


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
        payload = json.loads(_json_part(result.output))
        for row in payload["backends"]["rows"]:
            if row["tokens"] is None:
                continue
            written = (out / f"{row['backend']}.md").read_bytes()
            assert len(written) == row["tokens"], row["backend"]

    def test_json_carries_the_verdict(self, fixture_dir: Path) -> None:
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
        payload = json.loads(_json_part(result.output))
        assert payload["backends"]["cheapest"] == "kreuzberg"
        assert payload["backends"]["most_faithful"] == "pdfplumber"
        assert payload["backends"]["cheapest_is_most_faithful"] is False
