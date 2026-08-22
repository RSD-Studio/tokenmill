"""The shared plumbing behind the document adapters.

The interesting one is :func:`classify_failure`. Five libraries raise five
unrelated exception hierarchies for the same three underlying problems, and the
whole point of the taxonomy is that a user sees the same message whichever
backend hit it. That mapping is worth testing directly, including the case it
must get wrong-side-safe: an exception it does not recognise stays
``BackendFailed`` rather than being guessed into a claim that the user's file is
damaged.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from tokenmill.backends._common import (
    classify_failure,
    missing_binary_note,
    probe_module,
    render_markdown_table,
    source_as_file,
    warn_on_empty_output,
    warnings_as_conversion_warnings,
)
from tokenmill.core.errors import BackendFailed, CorruptSource, NetworkRequired
from tokenmill.core.models import AvailabilityStatus, Source
from tokenmill.core.protocol import ConversionContext

SOURCE = Source.from_text("body", name="thing.pdf")


class TestProbeModule:
    def test_an_installed_module_is_present(self) -> None:
        assert probe_module("json").status is AvailabilityStatus.PRESENT

    def test_an_absent_module_reports_the_extra_that_supplies_it(self) -> None:
        availability = probe_module("definitely_not_installed", install_extra="documents")

        assert availability.status is AvailabilityStatus.MISSING_DEPENDENCY
        assert availability.missing == ("definitely_not_installed",)
        assert availability.hint == 'pip install "tokenmill[documents]"'

    def test_an_explicit_hint_wins(self) -> None:
        availability = probe_module("definitely_not_installed", hint="pip install tokenmill")

        assert availability.hint == "pip install tokenmill"

    def test_probing_does_not_import_the_module(self) -> None:
        """The probe runs on every backends listing; importing would cost real time."""
        import sys

        probe_module("this_module_does_not_exist_either")

        assert "this_module_does_not_exist_either" not in sys.modules


class TestClassifyFailure:
    @pytest.mark.parametrize(
        "message",
        [
            "Stream has ended unexpectedly",
            "Unexpected EOF",
            "EOF marker not found",
            "Invalid PDF: PdfiumLibraryInternalError",
            "the file is truncated",
        ],
    )
    def test_a_damaged_file_becomes_corruptsource(self, message: str) -> None:
        error = classify_failure(ValueError(message), source=SOURCE, backend_id="somebackend")

        assert isinstance(error, CorruptSource)
        assert error.backend_id == "somebackend"
        assert error.hint is not None

    @pytest.mark.parametrize(
        "message",
        [
            "403 Forbidden",
            "Max retries exceeded with url: /models",
            "We couldn't connect to https://huggingface.co",
            "Failed to download https://example.invalid/model.pth",
            "Connection refused",
        ],
    )
    def test_a_network_failure_becomes_networkrequired(self, message: str) -> None:
        error = classify_failure(OSError(message), source=SOURCE, backend_id="docling")

        assert isinstance(error, NetworkRequired)
        assert error.hint is not None
        assert "download" in error.hint

    def test_an_unrecognised_failure_stays_backendfailed(self) -> None:
        """Guessing harder would mean blaming a user's file for our bug."""
        error = classify_failure(
            RuntimeError("something entirely unexpected"), source=SOURCE, backend_id="whatever"
        )

        assert isinstance(error, BackendFailed)
        assert type(error) is BackendFailed

    def test_it_reads_the_cause_chain_not_just_the_outermost_exception(self) -> None:
        """Libraries here routinely wrap the informative exception in a bland one."""
        inner = OSError("Max retries exceeded with url: /models")
        outer = RuntimeError("conversion failed")
        outer.__cause__ = inner

        error = classify_failure(outer, source=SOURCE, backend_id="docling")

        assert isinstance(error, NetworkRequired)

    def test_the_message_names_the_source_and_the_backend(self) -> None:
        error = classify_failure(ValueError("Unexpected EOF"), source=SOURCE, backend_id="pypdf")

        assert "thing.pdf" in error.message

    def test_a_cycle_in_the_cause_chain_terminates(self) -> None:
        first = RuntimeError("first")
        second = RuntimeError("second")
        first.__cause__ = second
        second.__cause__ = first

        error = classify_failure(first, source=SOURCE, backend_id="whatever")

        assert isinstance(error, BackendFailed)


class TestSourceAsFile:
    def test_a_file_source_is_yielded_in_place(self, tmp_path: Path) -> None:
        path = tmp_path / "real.pdf"
        path.write_bytes(b"%PDF-")

        with source_as_file(Source.from_path(path), "backend") as yielded:
            assert yielded == path

    def test_a_bytes_source_is_written_out_with_its_extension(self) -> None:
        source = Source.from_bytes(b"%PDF-1.7", name="memory.pdf")

        with source_as_file(source, "backend") as path:
            assert path.suffix == ".pdf"
            assert path.read_bytes() == b"%PDF-1.7"

    def test_the_temporary_file_is_cleaned_up(self) -> None:
        source = Source.from_bytes(b"x", name="memory.pdf")

        with source_as_file(source, "backend") as path:
            recorded = path

        assert not recorded.exists()

    def test_the_temporary_file_is_cleaned_up_even_when_the_body_raises(self) -> None:
        source = Source.from_bytes(b"x", name="memory.pdf")
        recorded: Path | None = None

        def blow_up() -> None:
            nonlocal recorded
            with source_as_file(source, "backend") as path:
                recorded = path
                msg = "boom"
                raise RuntimeError(msg)

        with pytest.raises(RuntimeError):
            blow_up()

        assert recorded is not None
        assert not recorded.exists()

    def test_a_source_with_no_content_is_reported_as_corrupt(self, tmp_path: Path) -> None:
        directory = tmp_path / "adirectory"
        directory.mkdir()

        with (
            pytest.raises(CorruptSource, match="no readable content"),
            source_as_file(Source.from_path(directory), "backend"),
        ):
            pass  # pragma: no cover - the context manager raises on entry


class TestWarnOnEmptyOutput:
    def test_non_empty_output_is_left_alone(self) -> None:
        context = ConversionContext()

        warn_on_empty_output("text", source=SOURCE, context=context, reason="whatever")

        assert context.warnings == []
        assert "empty_output" not in context.metadata

    def test_empty_output_warns_and_is_recorded(self) -> None:
        context = ConversionContext()

        warn_on_empty_output("", source=SOURCE, context=context, reason="no text layer")

        assert context.metadata["empty_output"] is True
        assert any("no text layer" in warning for warning in context.warnings)

    def test_whitespace_only_output_counts_as_empty(self) -> None:
        """A converter returning two newlines has produced nothing."""
        context = ConversionContext()

        warn_on_empty_output("\n\n", source=SOURCE, context=context, reason="no text layer")

        assert context.metadata["empty_output"] is True


class TestWarningsAsConversionWarnings:
    def test_a_warning_inside_the_block_becomes_a_conversion_warning(self) -> None:
        context = ConversionContext()

        with warnings_as_conversion_warnings(context, activity="importing something"):
            warnings.warn("your platform is unsupported", UserWarning, stacklevel=1)

        assert context.warnings == [
            "importing something: UserWarning: your platform is unsupported"
        ]

    def test_a_warning_inside_the_block_is_not_fatal_under_error_filters(self) -> None:
        """The whole point: -W error must not turn a library's chatter into a failure."""
        context = ConversionContext()

        def noisy_import() -> None:
            with warnings_as_conversion_warnings(context, activity="importing something"):
                warnings.warn("noisy but harmless", UserWarning, stacklevel=1)

        # The error filter has to be established *outside* the helper, which is
        # the situation the helper exists for: pytest's filterwarnings=error is
        # already in force by the time a backend imports its dependency.
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            noisy_import()

        assert len(context.warnings) == 1

    def test_a_quiet_block_adds_nothing(self) -> None:
        context = ConversionContext()

        with warnings_as_conversion_warnings(context, activity="importing something"):
            pass

        assert context.warnings == []

    def test_several_warnings_are_all_reported(self) -> None:
        context = ConversionContext()

        with warnings_as_conversion_warnings(context, activity="importing something"):
            warnings.warn("first", UserWarning, stacklevel=1)
            warnings.warn("second", DeprecationWarning, stacklevel=1)

        assert len(context.warnings) == 2
        assert "DeprecationWarning: second" in context.warnings[1]

    def test_an_exception_inside_the_block_still_propagates(self) -> None:
        """It downgrades warnings, not errors."""
        context = ConversionContext()

        def blow_up() -> None:
            with warnings_as_conversion_warnings(context, activity="importing something"):
                msg = "boom"
                raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="boom"):
            blow_up()


class TestMissingBinaryNote:
    def test_a_binary_that_exists_is_not_reported(self) -> None:
        import sys

        executable = Path(sys.executable).name

        assert missing_binary_note([executable]) == ()

    def test_a_binary_that_does_not_exist_is_reported(self) -> None:
        assert missing_binary_note(["definitely-not-a-real-binary"]) == (
            "definitely-not-a-real-binary",
        )

    def test_the_order_given_is_preserved(self) -> None:
        missing = missing_binary_note(["not-real-a", "not-real-b"])

        assert missing == ("not-real-a", "not-real-b")


class TestRenderMarkdownTable:
    def test_the_first_row_becomes_the_header(self) -> None:
        rendered = render_markdown_table([["a", "b"], ["1", "2"]])

        assert rendered == "| a | b |\n| --- | --- |\n| 1 | 2 |\n"

    def test_no_rows_renders_nothing(self) -> None:
        assert render_markdown_table([]) == ""

    def test_none_cells_become_empty(self) -> None:
        """Pdfplumber returns None for a blank cell."""
        rendered = render_markdown_table([["a", "b"], ["1", None]])

        assert rendered.endswith("| 1 |  |\n")

    def test_pipes_in_cells_are_escaped(self) -> None:
        rendered = render_markdown_table([["a"], ["x|y"]])

        assert "x\\|y" in rendered

    def test_newlines_in_cells_are_flattened(self) -> None:
        """A Markdown table row cannot span lines, so a wrapped cell is joined."""
        rendered = render_markdown_table([["a"], ["one\ntwo"]])

        assert "| one two |" in rendered

    def test_ragged_rows_are_padded_rather_than_dropped(self) -> None:
        """A table recovered from a PDF routinely has a short row."""
        rendered = render_markdown_table([["a", "b", "c"], ["1", "2"]])

        assert rendered.endswith("| 1 | 2 |  |\n")


class TestTheDocumentsCompatibilityShim:
    """``tokenmill.backends.documents._common`` still re-exports these.

    Phase 3 moved the module up a level, because web and repository adapters
    need the same helpers and "documents" stopped being a true name for them.
    The old path stays: `docs/ADDING_A_BACKEND.md` told third-party adapter
    authors to import from it, and breaking those for a rename would be a poor
    trade. If this test fails, either the shim was deleted — which needs a
    deprecation cycle first — or a helper was added to `_common` without being
    re-exported.
    """

    def test_every_public_helper_is_reachable_by_the_old_path(self) -> None:
        from tokenmill.backends import _common as new
        from tokenmill.backends.documents import _common as old

        assert set(old.__all__) == set(new.__all__)
        for name in new.__all__:
            assert getattr(old, name) is getattr(new, name), f"{name} is not the same object"
