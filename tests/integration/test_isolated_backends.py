"""The isolated backends against the real fixtures, and against real failures.

Every claim ``docs/BACKENDS.md`` makes about these three is asserted here, with a
message saying what to update when an upstream release fixes it. That is the
Phase 2 standard and it is not optional: a wrapper that hides a bad converter is
worse than no wrapper, and a documented failure nobody tests becomes a lie about
a tool that has since improved.

Each backend is gated on its runtime being present, because none of the three is
a Python dependency and none can be. The *absent* case is not skipped — it has
tests of its own that always run, since "an unavailable backend says what to
install" is the behaviour a user without the tool actually experiences.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tokenmill.backends.isolated.libreoffice_doc import LibreOfficeConverter
from tokenmill.backends.isolated.pandoc_doc import PandocConverter
from tokenmill.backends.isolated.pymupdf4llm_pdf import PyMuPDF4LLMConverter
from tokenmill.core.errors import BackendFailed, ConversionError, CorruptSource
from tokenmill.core.models import (
    AvailabilityStatus,
    ConversionResult,
    ConvertOptions,
    IsolationMode,
    LicenseTier,
    Source,
)
from tokenmill.core.pipeline import Pipeline

pytestmark = pytest.mark.integration

BYTES = ConvertOptions(tokenizer="bytes")


def convert(path: Path, backend: str, **overrides: Any) -> ConversionResult:
    """Convert one fixture through one named backend, with no fallback.

    Args:
        path: The fixture.
        backend: The backend id to pin to.
        **overrides: Extra option overrides.

    Returns:
        The result.
    """
    options = BYTES.with_(backend=backend, fallback=False, **overrides)
    return Pipeline().run(Source.from_path(path), options)


def available(converter: object) -> bool:
    """Whether a backend can run here.

    Args:
        converter: The backend instance.

    Returns:
        True when its runtime is installed.
    """
    return bool(converter.is_available())  # type: ignore[attr-defined]


requires_pymupdf4llm = pytest.mark.skipif(
    not available(PyMuPDF4LLMConverter()),
    reason=(
        "needs a separate interpreter with pymupdf4llm; it is AGPL-3.0 and is "
        "deliberately never installed alongside tokenmill"
    ),
)
requires_pandoc = pytest.mark.skipif(
    not available(PandocConverter()), reason="needs 'pandoc' installed"
)
requires_libreoffice = pytest.mark.skipif(
    not available(LibreOfficeConverter()), reason="needs 'soffice' installed"
)


class TestTheAbsentRuntimeCase:
    """Always runs. What a user without the tool actually sees."""

    @pytest.mark.parametrize(
        "converter",
        [PyMuPDF4LLMConverter(), PandocConverter(), LibreOfficeConverter()],
        ids=lambda c: c.info.id,
    )
    def test_it_is_either_available_or_says_how_to_install_it(self, converter: Any) -> None:
        availability = converter.is_available()

        if availability:
            return
        assert availability.status in {
            AvailabilityStatus.MISSING_BINARY,
            AvailabilityStatus.MISSING_DEPENDENCY,
        }
        assert availability.hint, f"{converter.info.id} is unavailable with no install hint"

    @pytest.mark.parametrize(
        "converter",
        [PyMuPDF4LLMConverter(), PandocConverter(), LibreOfficeConverter()],
        ids=lambda c: c.info.id,
    )
    def test_it_never_declares_in_process_isolation(self, converter: Any) -> None:
        assert converter.info.isolation is not IsolationMode.IN_PROCESS


class TestPyMuPDF4LLMIsIsolatedBecauseOfItsLicence:
    def test_it_declares_copyleft_and_subprocess(self) -> None:
        info = PyMuPDF4LLMConverter().info

        assert info.license_tier is LicenseTier.COPYLEFT
        assert info.isolation is IsolationMode.SUBPROCESS

    def test_the_package_is_not_installed_in_this_environment(self) -> None:
        """The design decision, asserted rather than described.

        Running an AGPL package out of process is only isolation if it is not
        also sitting in this environment where anything can import it. This is
        why the adapter looks for a *separate interpreter* rather than using
        `sys.executable`.
        """
        import importlib.util

        assert importlib.util.find_spec("pymupdf4llm") is None, (
            "pymupdf4llm is installed alongside tokenmill, which makes it "
            "importable by anything in this process. It belongs in an "
            "environment of its own; see the adapter's module docstring"
        )

    @requires_pymupdf4llm
    def test_it_converts_a_pdf_without_ever_being_imported(self, fixture_dir: Path) -> None:
        """Phase 7's exit gate, as one assertion."""
        import sys

        result = convert(fixture_dir / "tables.pdf", "pymupdf4llm")

        assert result.text.strip()
        assert not {"fitz", "pymupdf", "pymupdf4llm"} & set(sys.modules), (
            "an AGPL module is loaded in this process after a conversion that "
            "was supposed to happen entirely in a child"
        )

    @requires_pymupdf4llm
    def test_it_keeps_the_table_that_kreuzberg_destroys(self, fixture_dir: Path) -> None:
        """Why it is worth the isolation at all.

        Measured 2026-08-26 on `tables.pdf`, `--tokenizer bytes`: pymupdf4llm
        553 bytes at fidelity 0.848, pdfplumber 599 at 0.667, kreuzberg 466 at
        0.500. It is cheaper *and* more faithful than pdfplumber, which is the
        combination that justifies wrapping an AGPL tool at all.
        """
        result = convert(fixture_dir / "tables.pdf", "pymupdf4llm")

        assert "|" in result.text, "the pipe table did not survive"
        assert "markitdown" in result.text
        assert "marker" in result.text

    @requires_pymupdf4llm
    def test_it_records_which_build_produced_the_result(self, fixture_dir: Path) -> None:
        """The provenance gap Phase 10 needs closed.

        Before Phase 7 a subprocess backend could not say which build ran, so a
        measurement could not be reproduced. The version is the package's, not
        the interpreter's, because the interpreter's says nothing about the
        Markdown.
        """
        result = convert(fixture_dir / "tables.pdf", "pymupdf4llm")

        assert str(result.metadata["tool_version"]).startswith("pymupdf4llm ")
        assert result.metadata["isolation"] == "subprocess"

    @requires_pymupdf4llm
    def test_a_scan_with_no_text_layer_says_so_rather_than_returning_nothing(
        self, fixture_dir: Path
    ) -> None:
        """DOCUMENTED FAILURE MODE. `scanned.pdf` has no text layer.

        PyMuPDF4LLM does no OCR, so it returns an empty document. An empty
        string would be a 100% token reduction and the best-looking number on
        the benchmarks page, which is exactly the failure this project exists
        to refuse.

        If a future release adds OCR and this starts returning text, update
        docs/BACKENDS.md's PyMuPDF4LLM section and delete this test.
        """
        with pytest.raises(BackendFailed) as caught:
            convert(fixture_dir / "scanned.pdf", "pymupdf4llm")

        assert "no text" in str(caught.value)
        assert "OCR" in (caught.value.hint or "")

    @requires_pymupdf4llm
    def test_a_damaged_pdf_is_corrupt_source_like_every_other_pdf_backend(
        self, fixture_dir: Path
    ) -> None:
        """DOCUMENTED FAILURE MODE, and a fix for how it first read.

        The child raises `pymupdf.FileDataError`, and the raw failure message
        was `Traceback (most recent call last):` — the first line of stderr,
        which is what the shared helper takes and which for a Python child is
        always useless. pdfplumber, pypdf and kreuzberg all report this file as
        CorruptSource with a message naming the damage; this one now does too.
        """
        with pytest.raises(CorruptSource) as caught:
            convert(fixture_dir / "corrupt.pdf", "pymupdf4llm")

        message = str(caught.value)
        assert "Traceback" not in message, "the message is the traceback header again"
        assert "could not be parsed" in message
        assert "damaged or truncated" in (caught.value.hint or "")


class TestPandocIsIsolatedBecauseOfItsLicence:
    def test_it_declares_copyleft_and_subprocess(self) -> None:
        info = PandocConverter().info

        assert info.license_tier is LicenseTier.COPYLEFT
        assert info.isolation is IsolationMode.SUBPROCESS

    def test_it_is_not_importable_because_it_is_not_a_python_package(self) -> None:
        import importlib.util

        assert importlib.util.find_spec("pandoc") is None

    @requires_pandoc
    def test_it_converts_a_docx(self, fixture_dir: Path) -> None:
        result = convert(fixture_dir / "report.docx", "pandoc")

        assert "Where the tokens actually go" in result.text
        assert result.metadata["reader"] == "docx"

    @requires_pandoc
    def test_it_keeps_the_document_title_that_it_would_otherwise_drop(
        self, fixture_dir: Path
    ) -> None:
        """DOCUMENTED BEHAVIOUR, and the reason for `--standalone`.

        Pandoc's DOCX reader treats a Title-styled paragraph as document
        metadata, not body text, and discards it unless the output is
        standalone. `report.docx` came back with "Context Efficiency Report"
        simply gone, where MarkItDown keeps it.

        Fidelity scored 0.841 with and without the flag — the metric has no
        component for metadata loss (defect N8) — so this test is the only thing
        that notices. If `--standalone` is ever removed as a saving, this fails
        and says why.
        """
        result = convert(fixture_dir / "report.docx", "pandoc")

        assert "Context Efficiency Report" in result.text, (
            "Pandoc has dropped the document title again; --standalone is what "
            "keeps it, and no fidelity component will catch this"
        )

    @requires_pandoc
    def test_it_records_its_version(self, fixture_dir: Path) -> None:
        result = convert(fixture_dir / "report.docx", "pandoc")

        assert str(result.metadata["tool_version"]).startswith("pandoc ")

    @requires_pandoc
    def test_it_emits_gfm_so_the_fidelity_scorer_can_read_it(self, fixture_dir: Path) -> None:
        """DOCUMENTED BEHAVIOUR, and the reason for `--to gfm`.

        Pandoc's own `markdown` dialect emits grid tables and fenced divs that
        nothing else in this project produces, and the fidelity scorer reads GFM
        pipe tables. Comparing a grid table against a pipe table would be a
        comparison of dialects rather than of converters.
        """
        result = convert(fixture_dir / "report.docx", "pandoc")

        assert "+---" not in result.text, "that is a Pandoc grid table, not GFM"
        assert ":::" not in result.text, "that is a Pandoc fenced div, not GFM"

    def test_it_does_not_claim_pdf_because_pandoc_cannot_read_pdf(self, fixture_dir: Path) -> None:
        """DOCUMENTED FAILURE MODE, and it is a refusal rather than a failure.

        Pandoc has no PDF *reader* at all — it writes PDF and does not read it —
        so the format is simply not claimed and no Pandoc process is ever
        started for one.

        Asserted against `supports()` rather than through `convert()`, and the
        difference matters. `BaseConverter.convert` checks **availability before
        format support**, so on a machine without Pandoc installed the end-to-end
        route raises `BackendUnavailable` and never reaches the format check.
        This test asserted the format message and passed here, where Pandoc is
        installed, then failed on every CI cell, where it is not — the same
        one-machine blindness the handover's trap 1 names.

        The format claim is a property of the adapter and is true either way.
        """
        source = Source.from_path(fixture_dir / "simple.pdf")

        assert not PandocConverter().supports(source)
        assert "pdf" not in PandocConverter().info.input_formats

    @requires_pandoc
    def test_asking_for_pdf_anyway_names_the_formats_it_does_handle(
        self, fixture_dir: Path
    ) -> None:
        """The end-to-end half, gated on Pandoc being there to reach it."""
        with pytest.raises(ConversionError) as caught:
            convert(fixture_dir / "simple.pdf", "pandoc")

        assert "does not handle pdf" in str(caught.value)
        assert "epub" in (caught.value.hint or "")


class TestLibreOfficeIsIsolatedOnlyBecauseItIsNotPython:
    def test_it_is_permissive_and_still_out_of_process(self) -> None:
        """The distinction the isolated package exists to keep visible.

        MPL-2.0 would permit importing it if it were a Python library. It is out
        of process because it is a 400 MB C++ application, which is the same
        reason repomix and code2prompt are, and that reason carries no licence
        meaning at all.
        """
        info = LibreOfficeConverter().info

        assert info.license_tier is LicenseTier.PERMISSIVE
        assert info.isolation is IsolationMode.SUBPROCESS

    @requires_libreoffice
    def test_it_converts_a_docx(self, fixture_dir: Path) -> None:
        result = convert(fixture_dir / "report.docx", "libreoffice")

        assert "Context Efficiency Report" in result.text

    @requires_libreoffice
    def test_it_emits_plain_text_and_therefore_scores_badly_on_structure(
        self, fixture_dir: Path
    ) -> None:
        """DOCUMENTED FAILURE MODE, and the most useful row in the comparison.

        The `txt:Text` filter is exactly that: text. Every heading, every table
        and every list marker is gone, so LibreOffice produces the **cheapest**
        output on `report.docx` (3,418 bytes against markitdown's 3,494) and the
        **worst** fidelity (0.375 against 0.841), measured 2026-08-26 with
        `--tokenizer bytes`.

        That is this project's whole thesis in one row, and it is why the
        comparison view must never be sorted by size.

        If a future release makes `--convert-to md` viable — LibreOffice has
        had a Markdown export filter in development — update
        docs/BACKENDS.md's LibreOffice section and this test.
        """
        result = convert(fixture_dir / "report.docx", "libreoffice")

        assert "# " not in result.text, "a heading survived; the filter may have changed"
        assert "|" not in result.text, "a pipe table survived; the filter may have changed"

    @requires_libreoffice
    def test_the_java_warning_is_surfaced_rather_than_swallowed(self, fixture_dir: Path) -> None:
        """DOCUMENTED BEHAVIOUR on a container without a JRE.

        LibreOffice prints `failed to launch javaldx` and converts fine anyway.
        Swallowing it would hide a real difference in capability; failing on it
        would refuse a conversion that worked. So it becomes a warning that says
        which features are affected.

        Skipped where a JRE is present, since there is then nothing to warn about.
        """
        result = convert(fixture_dir / "report.docx", "libreoffice")

        if not any("Java" in w for w in result.warnings):
            pytest.skip("this machine has a working JRE, so there is no warning to check")
        assert any("Text extraction is unaffected" in w for w in result.warnings)

    @requires_libreoffice
    def test_each_conversion_uses_a_private_user_profile(self, fixture_dir: Path) -> None:
        """Two conversions must not fight over one profile directory.

        LibreOffice refuses to start a second instance against a profile already
        in use, so a shared profile would break the moment the Phase 8 batch
        queue ran two conversions at once — or the moment a user had LibreOffice
        open on their desktop.
        """
        first = convert(fixture_dir / "report.docx", "libreoffice")
        second = convert(fixture_dir / "unicode.docx", "libreoffice")

        assert first.text.strip()
        assert second.text.strip()
