"""The pipeline: stage ordering, measurement, and the separation of the two.

The behaviour worth guarding hardest is that a **measurement failure is not a
conversion failure**. On an air-gapped machine every tokenizer in the core
install is unloadable, and a user must still get their converted document with
the counts honestly marked unavailable — not an error where a document should
have been, and above all not an estimate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.doubles import (
    EchoConverter,
    ExplodingConverter,
    StaticProvider,
    UnavailableTokenizer,
    WordPieceTokenizer,
)
from tokenmill.core.errors import BackendUnavailable, ConversionError, UnsupportedFormat
from tokenmill.core.models import Availability, ConvertOptions, Source
from tokenmill.core.pipeline import CONVERT_STAGE, SOURCE_STAGE, Pipeline, convert
from tokenmill.core.protocol import BaseConverter
from tokenmill.core.registry import Registry
from tokenmill.post.base import PostProcessorRegistry
from tokenmill.tokens.registry import TokenizerRegistry


@pytest.fixture
def tokenizers() -> TokenizerRegistry:
    """Return a registry holding only the offline fake tokenizer."""
    registry = TokenizerRegistry()
    registry.register(StaticProvider("test", WordPieceTokenizer("wp")))
    return registry


@pytest.fixture
def broken_tokenizers() -> TokenizerRegistry:
    """Return a registry whose tokenizer always fails to load."""
    registry = TokenizerRegistry()
    registry.register(StaticProvider("test", UnavailableTokenizer("wp")))
    return registry


def build(
    converter: BaseConverter,
    tokenizers: TokenizerRegistry,
    post: PostProcessorRegistry | None = None,
) -> Pipeline:
    """Assemble a pipeline around one backend.

    Args:
        converter: The backend to register.
        tokenizers: The tokenizer registry to measure with.
        post: The post-processor registry; the real one by default.

    Returns:
        The pipeline.
    """
    backends = Registry()
    backends.register(converter)
    return Pipeline(
        backends=backends,
        post_processors=post if post is not None else PostProcessorRegistry(),
        tokenizers=tokenizers,
    )


def source_file(tmp_path: Path, content: str, name: str = "in.txt") -> Source:
    """Write ``content`` to a file and return it as a source.

    Args:
        tmp_path: Where to write.
        content: The file's content.
        name: The file name.

    Returns:
        The source.
    """
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return Source.from_path(path)


OPTS = ConvertOptions(tokenizer="wp")


class TestStages:
    def test_stages_are_source_then_convert_then_each_post_processor(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="converted"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS)

        assert [s.stage for s in result.stages] == [
            SOURCE_STAGE,
            CONVERT_STAGE,
            "normalize_whitespace",
        ]

    def test_an_explicit_chain_runs_and_is_reported_in_order(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="[a](b)  \ntext"), tokenizers)

        result = pipeline.run(
            source_file(tmp_path, "raw"),
            OPTS.with_(post_processors=("links", "normalize_whitespace")),
        )

        assert result.post_processors == ("links", "normalize_whitespace")
        assert [s.stage for s in result.stages][-2:] == ["links", "normalize_whitespace"]

    def test_post_processors_actually_transform_the_text(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="body\n\n\n\nmore\n"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS)

        assert result.text == "body\n\nmore\n"

    def test_an_empty_chain_leaves_the_converter_output_untouched(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        raw = "body\n\n\n\nmore\n"
        pipeline = build(EchoConverter(output=raw), tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS.with_(post_processors=()))

        assert result.text == raw
        assert result.post_processors == ()

    def test_every_stage_count_matches_a_direct_count_of_that_stage_text(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        """The per-stage report is arithmetic, not narrative."""
        tokenizer = WordPieceTokenizer("wp")
        pipeline = build(EchoConverter(output="one two three\n\n\n\nfour"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "the source text"), OPTS)

        assert result.stages[0].tokens is not None
        assert result.stages[0].tokens.value == tokenizer.count("the source text")
        assert result.stages[-1].tokens is not None
        assert result.stages[-1].tokens.value == tokenizer.count(result.text)

    def test_characters_are_recorded_on_every_stage(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="abcdef"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "abc"), OPTS)

        assert result.stages[0].characters == 3
        assert result.stages[1].characters == 6


class TestMeasurement:
    def test_before_and_after_bracket_the_whole_run(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="one"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "one two three"), OPTS)

        assert result.tokens_before is not None
        assert result.tokens_after is not None
        # "one two three" is 5 pieces; the converter emits "one" and the
        # whitespace normaliser appends the trailing newline, making 2.
        assert result.tokens_before.value == 5
        assert result.tokens_after.value == 2
        assert result.token_delta == 3

    def test_counts_carry_the_tokenizer_id(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="x"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "y"), OPTS)

        assert result.tokens_before is not None
        assert result.tokens_before.tokenizer_id == "wp"

    def test_the_backend_does_not_measure_the_pipeline_does(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        converter = EchoConverter(output="x")
        raw = converter.convert(source_file(tmp_path, "y"), OPTS)

        assert raw.tokens_before is None

        piped = build(converter, tokenizers).run(source_file(tmp_path, "y"), OPTS)

        assert piped.tokens_before is not None


class TestMeasurementFailureIsNotConversionFailure:
    def test_the_document_is_still_returned_when_the_tokenizer_cannot_load(
        self, tmp_path: Path, broken_tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="the converted document"), broken_tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS)

        assert result.text == "the converted document\n"

    def test_counts_are_none_rather_than_estimated(
        self, tmp_path: Path, broken_tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="x"), broken_tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS)

        assert result.tokens_before is None
        assert result.tokens_after is None
        assert result.token_delta is None
        assert result.reduction_ratio is None

    def test_the_user_is_told_why_counting_failed(
        self, tmp_path: Path, broken_tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="x"), broken_tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS)

        assert any("token counting unavailable" in w for w in result.warnings)

    def test_character_counts_stay_exact_when_tokens_cannot_be_counted(
        self, tmp_path: Path, broken_tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="abcdef"), broken_tokenizers)

        result = pipeline.run(source_file(tmp_path, "abc"), OPTS)

        assert [s.characters for s in result.stages][:2] == [3, 6]
        assert all(s.tokens is None for s in result.stages)

    def test_an_unknown_tokenizer_warns_rather_than_aborting(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="x"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS.with_(tokenizer="nope"))

        assert result.text
        assert result.tokens_before is None
        assert any("could not be resolved" in w for w in result.warnings)


class TestErrorHandling:
    def test_a_backend_bug_surfaces_as_a_conversion_error(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(ExplodingConverter(), tokenizers)

        with pytest.raises(ConversionError, match="has a bug"):
            pipeline.run(source_file(tmp_path, "raw"), OPTS)

    def test_an_unavailable_named_backend_is_an_error(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(
            EchoConverter("needy", availability=Availability.missing_dependency("nope")),
            tokenizers,
        )

        with pytest.raises(BackendUnavailable):
            pipeline.run(source_file(tmp_path, "raw"), OPTS.with_(backend="needy"))

    def test_an_unhandled_format_is_an_error(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(input_formats=("txt",)), tokenizers)

        with pytest.raises(UnsupportedFormat):
            pipeline.run(source_file(tmp_path, "raw", name="in.wat"), OPTS)

    def test_backend_warnings_survive_into_the_result(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="x", warn="the source looked odd"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS)

        assert "the source looked odd" in result.warnings

    def test_a_source_with_no_before_text_says_so_instead_of_guessing(
        self, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="x", input_formats=("url",)), tokenizers)

        result = pipeline.run(Source.from_url("https://example.com"), OPTS)

        assert result.stages[0].characters == 0
        assert result.stages[0].tokens is None
        assert any("no readable source text" in w for w in result.warnings)


class TestProvenance:
    def test_the_result_records_which_backend_actually_ran(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter("chosen", output="x"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS)

        assert result.backend_id == "chosen"

    def test_the_result_records_the_source_name_and_a_duration(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="x"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS)

        assert result.source_name == "in.txt"
        assert result.duration_s > 0

    def test_backend_metadata_survives_into_the_result(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="x"), tokenizers)

        result = pipeline.run(source_file(tmp_path, "raw"), OPTS)

        assert result.metadata["double"] is True


class TestConvenienceEntryPoint:
    def test_convert_uses_the_pipeline_it_is_given(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="via convert()"), tokenizers)

        result = convert(source_file(tmp_path, "raw"), OPTS, pipeline=pipeline)

        assert result.text.strip() == "via convert()"

    def test_convert_falls_back_to_default_options(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(output="x"), tokenizers)

        result = convert(source_file(tmp_path, "raw"), pipeline=pipeline)

        assert result.text
