"""The benchmark harness, and the guarantees a published number rests on.

`benchmarks/README.md` set the rule in Phase 0 that this package exists to make
satisfiable — every published number traces to a committed raw file — and the
tests here are about the ways that could still be false:

* **A summary that cannot be recomputed.** The raw repeats must survive into the
  result file, or a median is something a reader has to take on trust.
* **A token count without a fidelity one.** The report writer *refuses*, and
  that refusal is tested by rendering a report that breaks the rule and watching
  it raise.
* **A sign error.** `reduction` is positive for a saving and every table in this
  project prints a saving as negative. The first run of this harness printed a
  19.8% saving as `+19.8%`, which reads as growth — the same class of error
  Phase 1 recorded when a conversion that grew a document by 71% was reported as
  a 71% saving.
* **A failure quietly dropped.** A cell that failed must appear as a row.
* **A merged byte figure landing in a token column.** The one thing the two-run
  design exists to prevent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from benchmarks.harness import Cell, _portable_message, cells_for, run_cell
from benchmarks.models import CellResult, RunManifest
from benchmarks.report import (
    ReportError,
    check_report,
    load_results,
    merge,
    write_results,
)
from benchmarks.run import observed_versions

from tokenmill.core.registry import Registry


def _manifest(**overrides: object) -> RunManifest:
    """Build a manifest for a test.

    Args:
        **overrides: Fields to replace.

    Returns:
        The manifest.
    """
    fields: dict[str, object] = {
        "started_at": "2026-08-27T00:00:00+00:00",
        "tokenmill_version": "0.1.0",
        "git_commit": "abc123",
        "git_dirty": False,
        "python": "3.11.15",
        "platform_description": "Linux on x86_64",
        "cpu_count": 4,
        "corpus_digest": "deadbeef",
        "repeats": 5,
        "tokenizers": ["bytes"],
    }
    fields.update(overrides)
    return RunManifest(**fields)  # type: ignore[arg-type]


def _cell(**overrides: object) -> CellResult:
    """Build a successful cell for a test.

    Args:
        **overrides: Fields to replace.

    Returns:
        The cell.
    """
    fields: dict[str, object] = {
        "fixture": "article.html",
        "backend": "trafilatura",
        "tokenizer": "bytes",
        "ok": True,
        "tokens_before": 3560,
        "tokens_after": 2854,
        "characters": 2854,
        "fidelity": 1.0,
        "fidelity_components": {"content_recall": 1.0, "table_integrity": None},
        "fidelity_scored": 3,
        "durations_ms": (4.1, 4.3, 4.0, 9.9, 4.2),
        "peak_python_kb": 2048,
        "peak_rss_kb": 91000,
        "memory_method": "proc-sampling",
    }
    fields.update(overrides)
    return CellResult(**fields)  # type: ignore[arg-type]


class TestATimingIsNeverOneRun:
    """Defect N7, closed.

    Every timing this project published before Phase 10 was one unrepeated,
    unwarmed run, which is not a measurement of anything.
    """

    def test_the_median_is_not_moved_by_one_slow_repeat(self) -> None:
        """Which is the reason it is a median rather than a mean.

        The fixture's repeats include one at 9.9 ms against four around 4.1 —
        the shape of a cold page cache. The mean would be 5.3; the median is
        4.2, and the spread is where the outlier shows up instead.
        """
        cell = _cell()

        assert cell.median_ms == pytest.approx(4.2)
        assert cell.spread_ratio == pytest.approx(9.9 / 4.0)

    def test_every_repeat_survives_into_the_result_file(self, tmp_path: Path) -> None:
        """A summary whose inputs were discarded cannot be checked."""
        write_results(tmp_path, [_cell()], _manifest())

        payload = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))

        assert payload["results"][0]["durations_ms"] == [4.1, 4.3, 4.0, 9.9, 4.2]

    def test_n_is_reported_beside_the_median(self, tmp_path: Path) -> None:
        """A median of three and a median of thirty are different claims."""
        write_results(tmp_path, [_cell()], _manifest())

        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "N = 5" in report
        assert "| 5 |" in report

    def test_a_cell_with_no_repeats_is_refused(self) -> None:
        cell = Cell("x.md", Path("x.md"), "plaintext", None)

        with pytest.raises(ValueError, match="at least 1"):
            run_cell(cell, "bytes", repeats=0)


class TestFidelityCannotBeOmitted:
    """The rule `benchmarks/README.md` states, enforced as a function that raises."""

    def test_a_token_column_without_fidelity_is_refused(self) -> None:
        broken = "| Fixture | Backend | Tokens | Change |\n|---|---|---|---|\n"

        with pytest.raises(ReportError, match="fidelity"):
            check_report(broken)

    def test_the_real_report_passes_its_own_check(self, tmp_path: Path) -> None:
        write_results(tmp_path, [_cell()], _manifest())

        check_report((tmp_path / "report.md").read_text(encoding="utf-8"))

    def test_an_unscorable_fixture_reads_n_a_and_never_zero(self, tmp_path: Path) -> None:
        """An axis with no ground truth reads n/a, never zero.

        `long_context.md` has no table. Scoring its table integrity 0.0 would
        say one was destroyed; 1.0 would say one survived. Both are lies.
        """
        write_results(
            tmp_path,
            [_cell(fixture="long_context.md", fidelity=None, fidelity_scored=0)],
            _manifest(),
        )

        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "| n/a |" in report
        assert "| 0.000 |" not in report


class TestTheSignConvention:
    """A reduction prints as negative, because that is what happened to the size.

    The first run of this harness printed a 19.8% saving as `+19.8%`. Phase 1
    recorded the mirror image: a conversion that grew a document by 71% reported
    as a 71% saving. Both directions are asserted here.
    """

    def test_a_saving_prints_as_negative(self, tmp_path: Path) -> None:
        write_results(tmp_path, [_cell(tokens_before=3560, tokens_after=2854)], _manifest())

        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "\u221219.8%" in report, "a 19.8% saving must print as a negative change"
        assert "+19.8%" not in report

    def test_growth_prints_as_positive(self, tmp_path: Path) -> None:
        """The CSV-through-a-tutorial-backend case: 62 bytes in, 106 out."""
        write_results(tmp_path, [_cell(tokens_before=62, tokens_after=106)], _manifest())

        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "+71.0%" in report

    def test_no_before_count_prints_a_dash_rather_than_zero(self, tmp_path: Path) -> None:
        """A binary document has no comparable before. Phase 2 settled that."""
        write_results(tmp_path, [_cell(tokens_before=None)], _manifest())

        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "| — |" in report


class TestFailuresAreResults:
    def test_a_failed_cell_is_a_row(self, tmp_path: Path) -> None:
        failed = CellResult(
            fixture="corrupt.pdf",
            backend="pdfplumber",
            tokenizer="bytes",
            ok=False,
            error="corrupt.pdf could not be parsed: EOF marker not found",
            error_type="CorruptSource",
        )

        write_results(tmp_path, [_cell(), failed], _manifest())
        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "**fail**" in report
        assert "CorruptSource" in report
        assert "EOF marker not found" in report

    def test_an_empty_success_is_flagged_rather_than_read_as_a_saving(self, tmp_path: Path) -> None:
        """The single most misleading cell a benchmark can contain.

        `scanned.pdf` through any backend in the light tier succeeds and
        produces nothing, which scores a 100% reduction. It gets its own section.
        """
        empty = _cell(
            fixture="scanned.pdf",
            backend="pypdf",
            tokens_after=0,
            characters=0,
            fidelity=0.0,
            empty_output=True,
        )

        write_results(tmp_path, [empty], _manifest())
        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "**(empty)**" in report
        assert "Succeeded and produced nothing" in report

    def test_the_csv_has_a_row_for_a_failure_too(self, tmp_path: Path) -> None:
        failed = CellResult(
            fixture="corrupt.pdf",
            backend="pypdf",
            tokenizer="bytes",
            ok=False,
            error="boom",
            error_type="CorruptSource",
        )

        write_results(tmp_path, [failed], _manifest())
        csv_text = (tmp_path / "results.csv").read_text(encoding="utf-8")

        assert "corrupt.pdf,pypdf,bytes,False" in csv_text


class TestMergingUnits:
    """The mechanism that lets a byte run and a token run become one table.

    This sandbox cannot reach a tokenizer vocabulary host, so a local run can
    only measure `bytes` and a CI run measures `o200k_base`. They merge because
    a cell is keyed by tokenizer — which is also what makes it impossible for a
    byte figure to land in a token column.
    """

    def test_two_units_merge_without_colliding(self) -> None:
        local = [_cell(tokenizer="bytes", tokens_after=2854)]
        ci = [_cell(tokenizer="o200k_base", tokens_after=629)]

        merged = merge([local, ci])

        assert len(merged) == 2
        assert {c.tokenizer for c in merged} == {"bytes", "o200k_base"}
        by_unit = {c.tokenizer: c.tokens_after for c in merged}
        assert by_unit["bytes"] == 2854
        assert by_unit["o200k_base"] == 629

    def test_re_running_a_unit_replaces_rather_than_duplicates(self) -> None:
        first = [_cell(tokenizer="bytes", tokens_after=1)]
        second = [_cell(tokenizer="bytes", tokens_after=2)]

        merged = merge([first, second])

        assert len(merged) == 1
        assert merged[0].tokens_after == 2

    def test_each_unit_gets_its_own_section_in_the_report(self, tmp_path: Path) -> None:
        """So no reader can mistake one for the other.

        Phase 7 found the two units disagreeing by 24 points on tabular data and
        not even ranking the serialisation formats in the same order.
        """
        cells = [_cell(tokenizer="bytes"), _cell(tokenizer="o200k_base", tokens_after=629)]

        write_results(tmp_path, cells, _manifest(tokenizers=["bytes", "o200k_base"]))
        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "## Counted in `bytes`" in report
        assert "## Counted in `o200k_base`" in report
        assert "not model tokens" in report

    def test_a_result_file_round_trips(self, tmp_path: Path) -> None:
        """The committed file has to be readable, or the merge step is fiction."""
        original = [_cell(), _cell(backend="readability", tokens_after=2864)]

        write_results(tmp_path, original, _manifest())
        loaded, manifest = load_results(tmp_path / "results.json")

        assert [c.backend for c in loaded] == ["trafilatura", "readability"]
        assert loaded[0].durations_ms == original[0].durations_ms
        assert manifest["git_commit"] == "abc123"


class TestProvenance:
    """A number that cannot say what produced it cannot be reproduced."""

    def test_the_report_names_the_commit_and_the_corpus(self, tmp_path: Path) -> None:
        write_results(tmp_path, [_cell()], _manifest())

        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "abc123" in report
        assert "deadbeef" in report

    def test_a_dirty_tree_is_flagged(self, tmp_path: Path) -> None:
        """A dirty run says so rather than looking like a clean one.

        It is still worth having, and it cannot be reproduced from the commit
        alone.
        """
        write_results(tmp_path, [_cell()], _manifest(git_dirty=True))

        assert "working tree dirty" in (tmp_path / "report.md").read_text(encoding="utf-8")

    def test_the_memory_method_is_reported_beside_the_memory(self, tmp_path: Path) -> None:
        """There is no single honest "peak memory", so the number says which it is."""
        write_results(tmp_path, [_cell()], _manifest())

        report = (tmp_path / "report.md").read_text(encoding="utf-8")

        assert "sampled every 5 ms" in report
        assert "lower bound" in report


class TestTheMatrixIsNotCurated:
    def test_the_cells_come_from_the_registry(self, fixture_dir: Path) -> None:
        """The matrix comes from the registry, not from a curated list.

        Choosing the list by hand is how a benchmark stops including the backend
        that does badly.
        """
        registry = Registry()
        corpus = [("tables.pdf", fixture_dir / "tables.pdf")]

        cells = cells_for(corpus, {}, registry=registry)

        claimed = {
            c.info.id for c in registry if c.is_available() and c.info.supports_format("pdf")
        }
        assert {c.backend for c in cells} == claimed

    def test_ground_truth_is_attached_where_it_exists(self, fixture_dir: Path) -> None:
        from tokenmill.fidelity import load_ground_truth

        truths = dict(load_ground_truth(fixture_dir))
        corpus = [
            ("tables.pdf", fixture_dir / "tables.pdf"),
            ("long_context.md", fixture_dir / "long_context.md"),
        ]

        cells = cells_for(corpus, truths)

        by_fixture = {c.fixture: c.truth for c in cells}
        assert by_fixture["tables.pdf"] is not None
        assert by_fixture["long_context.md"] is not None


class TestTheManifestRecordsVersionsItActuallySaw:
    """A manifest that lists every backend against ``None`` records nothing.

    The first committed run had exactly that: thirteen installed backends, all
    mapped to ``null``, under a field whose docstring promised "the version of
    every backend that took part". The per-cell figures were right the whole
    time; the manifest was simply never filled from them.
    """

    def test_a_backends_version_comes_from_its_cells(self) -> None:
        results = [
            _cell(backend="trafilatura", backend_version="2.2.0"),
            _cell(backend="pandoc", backend_version="pandoc 3.1.3"),
        ]
        versions = observed_versions(results, {"trafilatura": None, "pandoc": None})
        assert versions == {"trafilatura": "2.2.0", "pandoc": "pandoc 3.1.3"}

    def test_an_installed_backend_with_no_cells_stays_unknown(self) -> None:
        versions = observed_versions(
            [_cell(backend="trafilatura", backend_version="2.2.0")],
            {"trafilatura": None, "code2prompt": None},
        )
        assert versions["code2prompt"] is None

    def test_a_backend_that_could_not_say_stays_unknown(self) -> None:
        versions = observed_versions(
            [_cell(backend="repomix", backend_version=None)], {"repomix": None}
        )
        assert versions["repomix"] is None

    def test_disagreeing_versions_are_both_reported_rather_than_one_picked(self) -> None:
        results = [
            _cell(backend="pandoc", backend_version="pandoc 3.1.3"),
            _cell(backend="pandoc", backend_version="pandoc 3.5"),
        ]
        versions = observed_versions(results, {"pandoc": None})
        assert versions["pandoc"] == "pandoc 3.1.3, pandoc 3.5"

    def test_the_committed_manifest_names_a_version_for_every_backend_that_ran(self) -> None:
        """The regression this class exists for, asserted against the real file."""
        root = Path(__file__).resolve().parents[2]
        results_dir = root / "benchmarks" / "results" / "2026-08-27"
        manifest = json.loads((results_dir / "manifest.json").read_text(encoding="utf-8"))
        rows = json.loads((results_dir / "results.json").read_text(encoding="utf-8"))["results"]
        ran = {row["backend"] for row in rows if row["backend_version"]}
        assert ran, "the committed run should have backends that reported a version"
        for backend in sorted(ran):
            assert manifest["backend_versions"].get(backend), (
                f"{backend} produced rows with a version but the manifest records none"
            )


class TestMemoryIsComparableBetweenRows:
    """A peak resident set is not a per-cell figure and must not read as one.

    The first committed run's memory column climbed from 50 MiB on the first
    row to 375 MiB on the last, in step order rather than in any order related
    to the backends. That is what a process-tree peak does: a Python process's
    resident set does not shrink, so every cell inherits the imports of every
    cell before it. The peak stays in the report — it is what was measured —
    but the comparable figure beside it is the difference from a baseline read
    immediately before the cell.
    """

    def test_the_added_figure_subtracts_the_baseline(self) -> None:
        row = _cell(peak_rss_kb=736 * 1024, baseline_rss_kb=370 * 1024)
        assert row.added_rss_kb == 366 * 1024

    def test_a_cell_that_freed_more_than_it_took_reports_zero_not_a_negative(self) -> None:
        row = _cell(peak_rss_kb=100, baseline_rss_kb=140)
        assert row.added_rss_kb == 0

    def test_an_unsampled_platform_reports_none_rather_than_zero(self) -> None:
        assert _cell(peak_rss_kb=None, baseline_rss_kb=None).added_rss_kb is None
        assert _cell(peak_rss_kb=1000, baseline_rss_kb=None).added_rss_kb is None

    def test_the_report_publishes_both_and_warns_against_comparing_peaks(
        self, tmp_path: Path
    ) -> None:
        rows = [_cell(peak_rss_kb=736 * 1024, baseline_rss_kb=370 * 1024)]
        write_results(tmp_path, rows, _manifest())
        text = (tmp_path / "report.md").read_text(encoding="utf-8")
        assert "Added RSS" in text
        assert "Do not compare peaks between rows" in text
        assert "366 MiB" in text
        assert "736 MiB" in text

    def test_the_baseline_survives_a_round_trip(self, tmp_path: Path) -> None:
        write_results(tmp_path, [_cell(peak_rss_kb=500, baseline_rss_kb=200)], _manifest())
        loaded, _ = load_results(tmp_path / "results.json")
        assert loaded[0].baseline_rss_kb == 200
        assert loaded[0].added_rss_kb == 300

    def test_a_real_measurement_records_a_baseline_below_its_peak(self) -> None:
        """Not a stub: allocate and check the sampler saw the growth."""
        from benchmarks.memory import measure_memory, sampling_supported

        if not sampling_supported():
            pytest.skip("no /proc on this platform, so there is no baseline to record")
        with measure_memory() as measured:
            ballast = bytearray(64 * 1024 * 1024)
            ballast[::4096] = b"\x01" * (len(ballast) // 4096)
        reading = measured.reading
        assert reading.baseline_rss_kb is not None
        assert reading.peak_rss_kb is not None
        assert reading.peak_rss_kb >= reading.baseline_rss_kb
        # The 64 MiB is touched page by page, so it is resident, and it is still
        # alive when the sampler takes its closing reading. Half of it is a floor
        # loose enough to survive a differently-tuned allocator and tight enough
        # that a sampler which never ran would fail.
        assert reading.added_rss_kb is not None
        assert reading.added_rss_kb > 32 * 1024
        del ballast


class TestCommittedResultsAreMachineIndependent:
    """Two runs of the same corpus on two machines should differ in timings only.

    The first committed run recorded `/home/user/tokenmill/tests/fixtures/
    corrupt.pdf` inside a pymupdf error message. Nothing secret, but it is the
    accident of one checkout's location written into published data, and it
    would make the identical failure read differently in the CI run whose rows
    have to merge with these.
    """

    def test_the_checkout_root_is_replaced_in_error_text(self) -> None:
        root = str(Path(__file__).resolve().parents[2])
        message = f"Failed to open file '{root}/tests/fixtures/corrupt.pdf' as type pdf."
        assert _portable_message(message) == (
            "Failed to open file '<repo>/tests/fixtures/corrupt.pdf' as type pdf."
        )

    def test_a_path_outside_the_checkout_is_left_alone(self) -> None:
        message = "could not find /usr/lib/libreoffice/program/soffice.bin"
        assert _portable_message(message) == message

    def test_the_committed_results_name_no_absolute_checkout_path(self) -> None:
        root = Path(__file__).resolve().parents[2]
        raw = (root / "benchmarks" / "results" / "2026-08-27" / "results.json").read_text(
            encoding="utf-8"
        )
        assert str(root) not in raw

    def test_the_committed_csv_uses_the_repositorys_line_endings(self) -> None:
        root = Path(__file__).resolve().parents[2]
        raw = (root / "benchmarks" / "results" / "2026-08-27" / "results.csv").read_bytes()
        assert b"\r\n" not in raw
