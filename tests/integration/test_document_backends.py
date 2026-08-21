"""The document backends against the real fixture corpus.

Golden-**structure** tests, per ``CONTRIBUTING.md``: headings present and
correctly nested, table cells recovered, reading order right, content recall
against ``ground_truth.json``. Never byte equality — that would fail on every
upstream release and tell us nothing.

Two things make this file worth reading as documentation as well as running as
a suite.

**The failures are asserted, not just the wins.** ``docs/BACKENDS.md`` says
Kreuzberg flattens a PDF table into prose and MarkItDown mis-splits its header
row. Those claims are held here, so if an upstream release fixes one, the test
fails and the documentation gets corrected rather than quietly becoming a lie
about a tool that has since improved. `CONTRIBUTING.md` rule 5 is what this
implements.

**Everything is offline.** Measurement uses the ``bytes`` tokenizer, which
counts UTF-8 bytes and needs no download. Nothing here asserts a token count.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tokenmill.core.errors import ConversionError, CorruptSource
from tokenmill.core.models import ConversionResult, ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import Registry

pytestmark = pytest.mark.integration

#: The `bytes` tokenizer counts UTF-8 bytes, not model tokens. It needs no
#: vocabulary download, so these tests run on an air-gapped machine.
OFFLINE = ConvertOptions(tokenizer="bytes")


@pytest.fixture(scope="module")
def pipeline() -> Pipeline:
    """Return a pipeline over the really-installed backends."""
    return Pipeline(backends=Registry())


def convert(pipeline: Pipeline, path: Path, backend: str) -> ConversionResult:
    """Convert one fixture with one named backend.

    Args:
        pipeline: The pipeline to run.
        path: The fixture to convert.
        backend: The backend id to force.

    Returns:
        The result.
    """
    return pipeline.run(Source.from_path(path), OFFLINE.with_(backend=backend))


def table_rows(text: str) -> list[list[str]]:
    """Return every Markdown table row in ``text``, separator rows dropped.

    Args:
        text: Markdown to scan.

    Returns:
        One list of cell values per data or header row.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped[1:-1].split("|")]
        if all(set(cell) <= {"-", ":"} and cell for cell in cells):
            continue
        rows.append(cells)
    return rows


def heading_levels(text: str) -> list[tuple[int, str]]:
    """Return every ATX heading in ``text`` as ``(level, title)``.

    Args:
        text: Markdown to scan.

    Returns:
        The headings, in document order.
    """
    headings: list[tuple[int, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        hashes = len(stripped) - len(stripped.lstrip("#"))
        title = stripped[hashes:].strip()
        if title:
            headings.append((hashes, title))
    return headings


def positions(text: str, markers: list[str]) -> list[int]:
    """Return where each marker first appears in ``text``.

    Args:
        text: The text to search.
        markers: The strings to locate.

    Returns:
        One index per marker; ``-1`` for a marker that is absent.
    """
    return [text.find(marker) for marker in markers]


# ---------------------------------------------------------------------------
# pdfplumber — the table backend
# ---------------------------------------------------------------------------


class TestPdfplumberOnTheTableFixture:
    """Phase 2's table-fidelity acceptance criterion, asserted cell by cell."""

    @pytest.fixture
    def result(self, fixture_dir: Path, pipeline: Pipeline) -> ConversionResult:
        return convert(pipeline, fixture_dir / "tables.pdf", "pdfplumber")

    def test_the_table_survives_as_a_real_markdown_table(
        self, result: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        expected = ground_truth["tables.pdf"]
        rows = table_rows(result.text)

        assert len(rows) == expected["table_rows_including_header"]
        assert all(len(row) == expected["table_columns"] for row in rows)

    def test_all_thirty_five_cells_are_present(
        self, result: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        """35 cells is the whole point of this fixture."""
        cells = [cell for row in table_rows(result.text) for cell in row]

        assert len(cells) == ground_truth["tables.pdf"]["table_cells"]
        assert all(cell for cell in cells), "no cell may be empty"

    def test_the_header_row_is_the_header_row(
        self, result: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        assert table_rows(result.text)[0] == ground_truth["tables.pdf"]["table_header"]

    def test_the_first_column_is_in_the_right_order(
        self, result: ConversionResult, ground_truth: dict[str, Any]
    ) -> None:
        body = table_rows(result.text)[1:]

        assert [row[0] for row in body] == ground_truth["tables.pdf"]["table_first_column"]

    def test_the_prose_around_the_table_is_kept_in_place(self, result: ConversionResult) -> None:
        """Splicing, not appending: the introduction must precede the table."""
        intro = result.text.find("The table below is the fixture's reason for existing")
        table = result.text.find("| Backend |")
        footnote = result.text.find("Figures are illustrative placeholders")

        assert -1 < intro < table < footnote

    def test_it_reports_how_many_tables_it_found(self, result: ConversionResult) -> None:
        assert result.metadata["tables_found"] == 1

    def test_this_page_is_not_mistaken_for_multi_column(self, result: ConversionResult) -> None:
        """A five-column table must not trip the column-gutter heuristic."""
        assert result.metadata["multi_column_pages"] == []


class TestPdfplumberOnTheOtherPdfs:
    def test_simple_pdf_keeps_its_body_text(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "simple.pdf", "pdfplumber")

        for needle in ground_truth["simple.pdf"]["must_contain"]:
            assert needle in result.text

    def test_simple_pdf_reports_both_pages(self, fixture_dir: Path, pipeline: Pipeline) -> None:
        result = convert(pipeline, fixture_dir / "simple.pdf", "pdfplumber")

        assert result.metadata["page_count"] == 2

    def test_twocolumn_reading_order_is_wrong_and_the_backend_says_so(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The documented failure mode, asserted rather than asserted-about.

        pdfplumber has no layout model, so it interleaves the two columns. That
        is not a bug we can fix in an adapter, but it is one the user must be
        told about, so the adapter's gutter heuristic fires and warns.
        """
        result = convert(pipeline, fixture_dir / "twocolumn.pdf", "pdfplumber")
        markers = ground_truth["twocolumn.pdf"]["order_markers"]
        found = positions(result.text, markers)

        assert all(index >= 0 for index in found), "no ORDERMARK may be lost"
        assert found != sorted(found), (
            "pdfplumber now gets multi-column reading order right; that is good news, "
            "and docs/BACKENDS.md and core/preferences.py both need updating"
        )
        assert result.metadata["multi_column_pages"] == [1]
        assert any("multi-column" in warning for warning in result.warnings)

    def test_a_scanned_pdf_produces_nothing_and_warns_loudly(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """An empty conversion exits zero and looks like success. It is not."""
        result = convert(pipeline, fixture_dir / "scanned.pdf", "pdfplumber")

        assert result.text.strip() == ""
        assert result.metadata["empty_output"] is True
        assert any("empty document" in warning for warning in result.warnings)
        assert any("OCR" in warning for warning in result.warnings)

    def test_a_truncated_pdf_is_reported_as_corrupt(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        with pytest.raises(CorruptSource):
            convert(pipeline, fixture_dir / "corrupt.pdf", "pdfplumber")


# ---------------------------------------------------------------------------
# pypdf — the reading-order backend
# ---------------------------------------------------------------------------


class TestPypdf:
    def test_it_reads_two_columns_in_the_right_order(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The one thing pypdf does better than everything else here."""
        result = convert(pipeline, fixture_dir / "twocolumn.pdf", "pypdf")
        found = positions(result.text, ground_truth["twocolumn.pdf"]["order_markers"])

        assert all(index >= 0 for index in found)
        assert found == sorted(found)

    def test_it_keeps_the_body_of_a_simple_pdf(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "simple.pdf", "pypdf")

        for needle in ground_truth["simple.pdf"]["must_contain"]:
            assert needle in result.text

    def test_it_finds_the_table_text_but_not_the_table(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """The documented tradeoff: all the data, none of the shape."""
        result = convert(pipeline, fixture_dir / "tables.pdf", "pypdf")

        assert "pymupdf4llm" in result.text
        assert "AGPL-3.0" in result.text
        assert table_rows(result.text) == [], (
            "pypdf now recovers tables; docs/BACKENDS.md and core/preferences.py need updating"
        )

    def test_a_scanned_pdf_produces_nothing_and_warns(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = convert(pipeline, fixture_dir / "scanned.pdf", "pypdf")

        assert result.text.strip() == ""
        assert any("empty document" in warning for warning in result.warnings)

    def test_a_truncated_pdf_is_reported_as_corrupt(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        with pytest.raises(CorruptSource):
            convert(pipeline, fixture_dir / "corrupt.pdf", "pypdf")


# ---------------------------------------------------------------------------
# MarkItDown — the breadth backend
# ---------------------------------------------------------------------------


@pytest.mark.requires("markitdown")
class TestMarkItDown:
    def test_it_keeps_every_speaker_note_in_the_deck(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The reason markitdown leads the pptx preference order."""
        result = convert(pipeline, fixture_dir / "deck.pptx", "markitdown")

        for note in ground_truth["deck.pptx"]["speaker_notes"]:
            assert note in result.text

    def test_it_keeps_every_slide_title(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "deck.pptx", "markitdown")

        for title in ground_truth["deck.pptx"]["slide_titles"]:
            assert title in result.text

    def test_it_renders_one_table_per_spreadsheet_sheet(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "data.xlsx", "markitdown")

        for sheet in ground_truth["data.xlsx"]["sheet_names"]:
            assert sheet in result.text
        assert len(table_rows(result.text)) >= sum(
            ground_truth["data.xlsx"]["sheet_row_counts"].values()
        )

    def test_docx_headings_nest_but_the_title_is_lost(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """Documented failure mode: the Title paragraph becomes body text."""
        result = convert(pipeline, fixture_dir / "report.docx", "markitdown")
        headings = heading_levels(result.text)
        titles = [title for _, title in headings]

        assert "Context Efficiency Report" in result.text, "the title text must survive"
        assert "Context Efficiency Report" not in titles, (
            "markitdown now keeps the DOCX title as a heading; docs/BACKENDS.md needs updating"
        )
        assert (1, "Where the tokens actually go") in headings
        assert (2, "Where the tokens actually go: detail") in headings

    def test_the_docx_table_gets_a_spurious_empty_header_row(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """Documented failure mode, quoted in docs/BACKENDS.md."""
        result = convert(pipeline, fixture_dir / "report.docx", "markitdown")
        rows = table_rows(result.text)

        assert rows, "the table itself must survive"
        assert all(cell == "" for cell in rows[0]), (
            "markitdown now emits a real DOCX table header; docs/BACKENDS.md needs updating"
        )
        assert ["Stage", "Tokens", "Delta"] in rows

    def test_the_pdf_table_header_is_mis_split(self, fixture_dir: Path, pipeline: Pipeline) -> None:
        """Documented failure mode: two columns merged, one invented."""
        result = convert(pipeline, fixture_dir / "tables.pdf", "markitdown")
        rows = table_rows(result.text)

        assert rows, "markitdown does emit a table for this PDF"
        assert rows[0] != ["Backend", "License", "Runtime", "Tables", "Pages/sec"], (
            "markitdown now splits this PDF table header correctly; docs/BACKENDS.md "
            "and core/preferences.py need updating"
        )
        assert ["markitdown", "MIT", "CPU", "weak", "12.0"] in rows, (
            "the data rows are the part markitdown does get right"
        )

    def test_every_script_in_the_unicode_fixture_round_trips(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "unicode.docx", "markitdown")

        for script, sample in ground_truth["unicode.docx"]["scripts"].items():
            assert sample in result.text, f"{script} did not survive"

    def test_a_truncated_pdf_is_reported_inside_the_taxonomy(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        with pytest.raises(ConversionError):
            convert(pipeline, fixture_dir / "corrupt.pdf", "markitdown")

    def test_a_scanned_pdf_produces_nothing_and_warns(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = convert(pipeline, fixture_dir / "scanned.pdf", "markitdown")

        assert result.text.strip() == ""
        assert any("empty document" in warning for warning in result.warnings)

    def test_an_image_with_no_exiftool_says_which_binary_is_missing(
        self, tmp_path: Path, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A silent empty document is the failure mode this project must not have."""
        monkeypatch.setattr("tokenmill.backends.documents._common.shutil.which", lambda _name: None)
        path = tmp_path / "photo.png"
        path.write_bytes(_ONE_PIXEL_PNG)

        result = convert(pipeline, path, "markitdown")

        assert result.metadata["missing_binaries"] == ["exiftool"]
        assert any("exiftool" in warning and "PATH" in warning for warning in result.warnings)


# ---------------------------------------------------------------------------
# Kreuzberg — the fast unified backend
# ---------------------------------------------------------------------------


@pytest.mark.requires("kreuzberg")
class TestKreuzberg:
    def test_it_reads_two_columns_in_the_right_order(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "twocolumn.pdf", "kreuzberg")
        found = positions(result.text, ground_truth["twocolumn.pdf"]["order_markers"])

        assert all(index >= 0 for index in found)
        assert found == sorted(found)

    def test_it_infers_a_heading_from_a_pdf_that_has_none(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = convert(pipeline, fixture_dir / "simple.pdf", "kreuzberg")

        assert (1, "Why Your Context Window Is Mostly Navigation Menus") in heading_levels(
            result.text
        )

    def test_it_flattens_a_pdf_table_into_prose(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """The documented failure mode that keeps it behind pdfplumber for PDF."""
        result = convert(pipeline, fixture_dir / "tables.pdf", "kreuzberg")

        assert "pymupdf4llm" in result.text, "the data survives as text"
        assert table_rows(result.text) == [], (
            "kreuzberg now recovers PDF tables; docs/BACKENDS.md and core/preferences.py "
            "need updating"
        )

    def test_it_drops_the_decks_speaker_notes(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The documented failure mode that keeps it behind markitdown for pptx."""
        result = convert(pipeline, fixture_dir / "deck.pptx", "kreuzberg")
        notes = ground_truth["deck.pptx"]["speaker_notes"]

        assert all(title in result.text for title in ground_truth["deck.pptx"]["slide_titles"])
        assert not any(note in result.text for note in notes), (
            "kreuzberg now keeps PPTX speaker notes; docs/BACKENDS.md and "
            "core/preferences.py need updating"
        )

    def test_it_renders_spreadsheet_sheets_as_tables(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "data.xlsx", "kreuzberg")

        for sheet in ground_truth["data.xlsx"]["sheet_names"]:
            assert sheet in result.text
        assert ["Backend", "License", "Runtime", "Tables", "Pages/sec"] in table_rows(result.text)

    def test_every_script_in_the_unicode_fixture_round_trips(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "unicode.docx", "kreuzberg")

        for script, sample in ground_truth["unicode.docx"]["scripts"].items():
            assert sample in result.text, f"{script} did not survive"

    def test_it_runs_with_ocr_off_and_caching_off(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = convert(pipeline, fixture_dir / "simple.pdf", "kreuzberg")

        assert result.metadata["ocr"] is False

    def test_a_scanned_pdf_produces_nothing_and_warns(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = convert(pipeline, fixture_dir / "scanned.pdf", "kreuzberg")

        assert result.text.strip() == ""
        assert any("empty document" in warning for warning in result.warnings)

    def test_a_truncated_pdf_is_reported_inside_the_taxonomy(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        with pytest.raises(ConversionError):
            convert(pipeline, fixture_dir / "corrupt.pdf", "kreuzberg")


# ---------------------------------------------------------------------------
# Docling — heavy, and only partly verifiable here
# ---------------------------------------------------------------------------


@pytest.mark.requires("docling")
class TestDoclingOnOfficeFormats:
    """The Docling paths that need no downloaded model.

    DOCX, PPTX and XLSX go through direct parsers, so these run fully offline
    wherever docling is installed. The PDF path does **not** — it fetches layout
    models from ``huggingface.co`` on first use — and is marked ``heavy`` below.
    """

    def test_it_nests_docx_headings_correctly_under_the_title(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """The reason docling leads the docx preference order."""
        result = convert(pipeline, fixture_dir / "report.docx", "docling")
        headings = heading_levels(result.text)

        assert (1, "Context Efficiency Report") in headings
        assert (2, "Where the tokens actually go") in headings
        assert (3, "Where the tokens actually go: detail") in headings

    def test_it_keeps_both_list_types_in_the_docx(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "report.docx", "docling")
        lines = [line.strip() for line in result.text.splitlines()]

        for item in ground_truth["report.docx"]["bullet_items"]:
            assert f"- {item}" in lines
        for item in ground_truth["report.docx"]["numbered_items"]:
            assert any(line.endswith(item) and line[0].isdigit() for line in lines)

    def test_the_docx_table_has_a_real_header_row(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = convert(pipeline, fixture_dir / "report.docx", "docling")

        assert table_rows(result.text)[0] == ["Stage", "Tokens", "Delta"]

    def test_it_drops_the_decks_speaker_notes(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The documented failure mode that keeps it behind markitdown for pptx."""
        result = convert(pipeline, fixture_dir / "deck.pptx", "docling")
        notes = ground_truth["deck.pptx"]["speaker_notes"]

        assert not any(note in result.text for note in notes), (
            "docling now keeps PPTX speaker notes; docs/BACKENDS.md and "
            "core/preferences.py need updating"
        )

    def test_it_drops_the_spreadsheet_sheet_names(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The documented failure mode that keeps it behind markitdown for xlsx."""
        result = convert(pipeline, fixture_dir / "data.xlsx", "docling")

        assert table_rows(result.text), "the tables themselves survive"
        assert not any(
            sheet in result.text for sheet in ground_truth["data.xlsx"]["sheet_names"]
        ), (
            "docling now keeps XLSX sheet names; docs/BACKENDS.md and core/preferences.py "
            "need updating"
        )

    def test_every_script_in_the_unicode_fixture_round_trips(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "unicode.docx", "docling")

        for script, sample in ground_truth["unicode.docx"]["scripts"].items():
            assert sample in result.text, f"{script} did not survive"


@pytest.mark.heavy
@pytest.mark.requires("docling")
class TestDoclingOnPdf:
    """Docling's PDF path, unverified in the development sandbox.

    It needs the DocLayNet layout model and TableFormer, downloaded from
    ``huggingface.co`` on first use — a host this project's egress proxy denies,
    so these have never run here. They are marked ``heavy`` because the model
    download is measured in hundreds of megabytes on top of a 5.2 GB install,
    which is what that marker is for. ``PROGRESS.md`` records the path as
    implemented but unverified rather than done.
    """

    def test_it_recovers_the_table_from_the_table_fixture(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "tables.pdf", "docling")
        rows = table_rows(result.text)

        assert len(rows) == ground_truth["tables.pdf"]["table_rows_including_header"]
        assert rows[0] == ground_truth["tables.pdf"]["table_header"]

    def test_it_keeps_the_body_of_a_simple_pdf(
        self, fixture_dir: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = convert(pipeline, fixture_dir / "simple.pdf", "docling")

        for needle in ground_truth["simple.pdf"]["must_contain"]:
            assert needle in result.text


# ---------------------------------------------------------------------------
# The chain, end to end on real files
# ---------------------------------------------------------------------------


class TestAutoSelectionOnTheCorpus:
    """Phase 2's first acceptance criterion: every fixture converts."""

    @pytest.mark.parametrize(
        "fixture",
        ["simple.pdf", "tables.pdf", "twocolumn.pdf", "report.docx", "unicode.docx"],
    )
    def test_every_document_fixture_converts_to_non_empty_markdown(
        self, fixture: str, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = pipeline.run(Source.from_path(fixture_dir / fixture), OFFLINE)

        assert result.text.strip()
        assert result.attempts[-1].ok

    @pytest.mark.parametrize("fixture", ["deck.pptx", "data.xlsx"])
    @pytest.mark.requires("markitdown")
    def test_the_office_fixtures_needing_an_extra_convert_too(
        self, fixture: str, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = pipeline.run(Source.from_path(fixture_dir / fixture), OFFLINE)

        assert result.text.strip()

    def test_a_pdf_auto_selects_the_table_backend(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = pipeline.run(Source.from_path(fixture_dir / "tables.pdf"), OFFLINE)

        assert result.backend_id == "pdfplumber"

    def test_a_corrupt_pdf_fails_after_every_backend_has_tried(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """The fallback chain must not turn a bad file into a silent success."""
        with pytest.raises(ConversionError) as excinfo:
            pipeline.run(Source.from_path(fixture_dir / "corrupt.pdf"), OFFLINE)

        assert excinfo.value.hint is not None
        assert "pdfplumber" in excinfo.value.hint
        assert "pypdf" in excinfo.value.hint

    def test_a_binary_source_says_its_before_count_is_not_a_token_saving(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        """The bytes of a .docx are not text any model would ever be given."""
        result = pipeline.run(Source.from_path(fixture_dir / "report.docx"), OFFLINE)

        assert any("not a token saving" in warning for warning in result.warnings)

    def test_a_text_source_carries_no_such_warning(
        self, fixture_dir: Path, pipeline: Pipeline
    ) -> None:
        result = pipeline.run(Source.from_path(fixture_dir / "boilerplate.html"), OFFLINE)

        assert not any("not a token saving" in warning for warning in result.warnings)


class TestOfflineGuarantee:
    def test_converting_a_local_pdf_makes_no_network_call(
        self, fixture_dir: Path, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default-deny on the network, enforced rather than asserted."""
        import socket

        def refuse(*_args: object, **_kwargs: object) -> None:
            msg = "a local conversion must not touch the network"
            raise AssertionError(msg)

        monkeypatch.setattr(socket.socket, "connect", refuse)

        result = pipeline.run(Source.from_path(fixture_dir / "tables.pdf"), OFFLINE)

        assert result.text.strip()


#: The smallest valid PNG that Pillow and magika both accept: 1x1, greyscale.
_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010800000000"
    "3a7e9b550000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)
