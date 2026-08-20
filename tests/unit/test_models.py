"""The data model: construction, immutability and the arithmetic on results."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tests.doubles import make_info
from tokenmill.core.models import (
    Availability,
    AvailabilityStatus,
    BackendInfo,
    ConversionResult,
    ConvertOptions,
    Domain,
    IsolationMode,
    LicenseTier,
    OutputFormat,
    Source,
    SourceKind,
    StageCount,
    TokenCount,
    freeze_metadata,
)


class TestSource:
    def test_from_path_classifies_a_file(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        target.write_text("hello", encoding="utf-8")

        source = Source.from_path(target)

        assert source.kind is SourceKind.FILE
        assert source.name == "note.md"
        assert source.format == "md"
        assert source.read_text() == "hello"

    def test_from_path_classifies_a_directory_as_a_repo(self, tmp_path: Path) -> None:
        source = Source.from_path(tmp_path)

        assert source.kind is SourceKind.REPO
        assert source.format == "repo"

    def test_from_path_resolves_relative_and_dotdot_segments(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        (tmp_path / "a" / "f.txt").write_text("x", encoding="utf-8")

        source = Source.from_path(nested / ".." / "f.txt")

        assert source.path == (tmp_path / "a" / "f.txt").resolve()
        assert ".." not in str(source.path)

    def test_from_path_rejects_a_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            Source.from_path(tmp_path / "nope.txt")

    def test_from_url_rejects_a_non_http_scheme(self) -> None:
        with pytest.raises(ValueError, match="unsupported URL scheme"):
            Source.from_url("file:///etc/passwd")

    def test_from_url_sets_the_url_pseudo_format(self) -> None:
        source = Source.from_url("https://example.com/page")

        assert source.kind is SourceKind.URL
        assert source.format == "url"

    def test_from_bytes_guesses_the_media_type_from_the_name(self) -> None:
        source = Source.from_bytes(b"<p>hi</p>", name="page.html")

        assert source.media_type == "text/html"
        assert source.format == "html"

    def test_from_text_round_trips(self) -> None:
        source = Source.from_text("plain")

        assert source.format == "text"
        assert source.read_text() == "plain"
        assert source.read_bytes() == b"plain"

    def test_read_text_replaces_undecodable_bytes_rather_than_raising(self) -> None:
        source = Source.from_bytes(b"caf\xe9", name="latin.txt")

        # A converter should report a mangled character, not abort on one.
        assert source.read_text() == "caf�"

    def test_read_bytes_rejects_a_source_with_no_local_content(self) -> None:
        source = Source.from_url("https://example.com")

        with pytest.raises(ValueError, match="no readable bytes"):
            source.read_bytes()

    def test_a_source_is_immutable(self) -> None:
        source = Source.from_text("x")

        with pytest.raises(dataclasses.FrozenInstanceError):
            source.name = "other"  # type: ignore[misc]


class TestAvailability:
    def test_present_is_truthy(self) -> None:
        availability = Availability.present()

        assert availability
        assert availability.is_available
        assert availability.describe() == "available"

    def test_missing_dependency_is_falsy_and_carries_an_install_hint(self) -> None:
        availability = Availability.missing_dependency("docling", "torch")

        assert not availability
        assert availability.missing == ("docling", "torch")
        assert availability.hint == "pip install docling torch"
        assert availability.describe() == "missing dependency: docling, torch"

    def test_missing_binary_names_the_executable(self) -> None:
        availability = Availability.missing_binary("npx", hint="install Node.js")

        assert availability.status is AvailabilityStatus.MISSING_BINARY
        assert availability.describe() == "missing binary: npx"

    def test_unsupported_reports_its_reason(self) -> None:
        availability = Availability.unsupported("needs a GPU")

        assert availability.describe() == "needs a GPU"

    def test_broken_reports_the_load_error_and_blames_the_plugin(self) -> None:
        availability = Availability.broken("ImportError: no module named 'nope'")

        assert not availability
        assert availability.status is AvailabilityStatus.BROKEN
        assert "ImportError" in availability.describe()
        assert availability.hint is not None
        assert "report it to its author" in availability.hint


class TestBackendInfo:
    def test_supports_format_ignores_case_and_a_leading_dot(self) -> None:
        info = make_info("b", input_formats=("html", "htm"))

        assert info.supports_format("HTML")
        assert info.supports_format(".htm")
        assert not info.supports_format("pdf")

    @pytest.mark.parametrize("tier", [LicenseTier.COPYLEFT, LicenseTier.NON_COMMERCIAL])
    def test_a_non_permissive_backend_cannot_declare_in_process_isolation(
        self, tier: LicenseTier
    ) -> None:
        """CONTRIBUTING.md rule 2, enforced where it cannot be argued with.

        A copyleft adapter that says it runs in-process must not be
        constructible at all, let alone registrable.
        """
        with pytest.raises(ValueError, match="must run out of process"):
            BackendInfo(
                id="pymupdf4llm",
                name="PyMuPDF4LLM",
                description="AGPL",
                domains=(Domain.DOCUMENTS,),
                input_formats=("pdf",),
                license="AGPL-3.0",
                license_tier=tier,
                upstream_url="https://example.invalid",
                isolation=IsolationMode.IN_PROCESS,
            )

    def test_a_copyleft_backend_may_declare_subprocess_isolation(self) -> None:
        info = BackendInfo(
            id="pandoc",
            name="Pandoc",
            description="GPL, out of process",
            domains=(Domain.DOCUMENTS,),
            input_formats=("docx",),
            license="GPL-2.0-or-later",
            license_tier=LicenseTier.COPYLEFT,
            upstream_url="https://pandoc.org",
            isolation=IsolationMode.SUBPROCESS,
        )

        assert info.isolation is IsolationMode.SUBPROCESS


class TestTokenCount:
    def test_a_count_carries_its_tokenizer(self) -> None:
        count = TokenCount(value=4102, tokenizer_id="o200k_base")

        assert str(count) == "4102 (o200k_base)"


class TestConversionResult:
    @staticmethod
    def _result(before: int | None, after: int | None, tokenizer: str = "t") -> ConversionResult:
        return ConversionResult(
            text="out",
            output_format=OutputFormat.MARKDOWN,
            source_name="in",
            backend_id="b",
            duration_s=0.1,
            tokens_before=None if before is None else TokenCount(before, tokenizer),
            tokens_after=None if after is None else TokenCount(after, tokenizer),
        )

    def test_delta_and_ratio_on_a_reduction(self) -> None:
        result = self._result(1000, 250)

        assert result.token_delta == 750
        assert result.reduction_ratio == pytest.approx(0.75)

    def test_a_conversion_that_grew_the_text_reports_a_negative_ratio(self) -> None:
        """Growth is a real outcome and must not be clamped to zero."""
        result = self._result(100, 150)

        assert result.token_delta == -50
        assert result.reduction_ratio == pytest.approx(-0.5)

    def test_unmeasured_counts_give_no_delta_rather_than_zero(self) -> None:
        assert self._result(None, None).token_delta is None
        assert self._result(100, None).reduction_ratio is None

    def test_a_zero_token_input_has_no_ratio(self) -> None:
        assert self._result(0, 0).reduction_ratio is None

    def test_with_warning_returns_a_copy(self) -> None:
        original = self._result(10, 5)

        updated = original.with_warning("careful")

        assert updated.warnings == ("careful",)
        assert original.warnings == ()

    def test_a_result_is_immutable(self) -> None:
        result = self._result(10, 5)

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.text = "tampered"  # type: ignore[misc]


class TestConvertOptions:
    def test_with_replaces_only_the_named_fields(self) -> None:
        options = ConvertOptions(tokenizer="a", backend="b")

        updated = options.with_(tokenizer="c")

        assert updated.tokenizer == "c"
        assert updated.backend == "b"
        assert options.tokenizer == "a"

    def test_defaults_deny_the_network(self) -> None:
        """Converting a local file must never reach out."""
        assert ConvertOptions().allow_network is False


class TestStageCountAndMetadata:
    def test_a_stage_may_record_characters_without_tokens(self) -> None:
        stage = StageCount(stage="convert", characters=42)

        assert stage.tokens is None

    def test_freeze_metadata_returns_a_read_only_view(self) -> None:
        frozen = freeze_metadata({"pages": 3})

        assert frozen["pages"] == 3
        with pytest.raises(TypeError):
            frozen["pages"] = 4  # type: ignore[index]

    def test_freeze_metadata_copies_so_later_mutation_cannot_leak_in(self) -> None:
        original = {"pages": 3}

        frozen = freeze_metadata(original)
        original["pages"] = 99

        assert frozen["pages"] == 3

    def test_freeze_metadata_of_nothing_is_empty(self) -> None:
        assert dict(freeze_metadata(None)) == {}
