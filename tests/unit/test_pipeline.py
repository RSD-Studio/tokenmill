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
    make_info,
)
from tokenmill.core.errors import BackendUnavailable, ConversionError, UnsupportedFormat
from tokenmill.core.models import Availability, ConvertOptions, Source
from tokenmill.core.pipeline import CONVERT_STAGE, SOURCE_STAGE, Pipeline, convert
from tokenmill.core.protocol import BaseConverter, ConversionContext
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
        self, tokenizers: TokenizerRegistry, tmp_path: Path
    ) -> None:
        """No readable input means no source stage at all, and a warning.

        Phase 2 dropped the zero-character placeholder row this used to emit.
        One rule now covers both ways a source can lack a comparable before —
        unreadable, and binary — and that rule is "there is no source stage".
        A row reporting zero characters communicated nothing the absent
        before-count did not already say.

        Phase 3 changed which sources this is *about*. It used to use a URL,
        because a URL had no readable bytes; the pipeline now fetches one, so a
        URL has a real before-count and is covered by
        ``TestUrlFetching`` instead. A repository directory is the case that
        remains genuinely unreadable, and it is the one Phase 4 cares about.
        """
        (tmp_path / "file.txt").write_text("content", encoding="utf-8")
        pipeline = build(EchoConverter(output="x", input_formats=("repo",)), tokenizers)

        result = pipeline.run(Source.from_path(tmp_path), OPTS)

        assert result.stages[0].stage != SOURCE_STAGE
        assert result.tokens_before is None
        assert result.source_bytes is None
        assert any("no readable source text" in w for w in result.warnings)


class TestABinaryDocumentHasNoComparableBefore:
    """Counting the bytes of a .docx decoded as text is not a measurement.

    Nobody hands a model the bytes of a zip archive, so that figure cannot be
    subtracted from the output's. The pipeline reports no before-count and the
    file's size instead. The delta keeps its meaning where both sides really
    are text a model could be given.
    """

    def test_a_binary_source_reports_no_before_count(
        self, tokenizers: TokenizerRegistry, tmp_path: Path
    ) -> None:
        path = tmp_path / "thing.bin"
        path.write_bytes(b"\xff\xfe\x00binary\x00payload")
        pipeline = build(EchoConverter(output="converted", input_formats=("bin",)), tokenizers)

        result = pipeline.run(Source.from_path(path), OPTS)

        assert result.tokens_before is None
        assert result.tokens_after is not None
        assert result.token_delta is None
        assert result.reduction_ratio is None

    def test_it_records_the_size_instead(
        self, tokenizers: TokenizerRegistry, tmp_path: Path
    ) -> None:
        payload = b"\xff\xfe\x00binary\x00payload"
        path = tmp_path / "thing.bin"
        path.write_bytes(payload)
        pipeline = build(EchoConverter(output="converted", input_formats=("bin",)), tokenizers)

        result = pipeline.run(Source.from_path(path), OPTS)

        assert result.source_bytes == len(payload)

    def test_there_is_no_source_stage_to_mistake_for_one(
        self, tokenizers: TokenizerRegistry, tmp_path: Path
    ) -> None:
        """The trap this avoids: `before` silently becoming `after conversion`."""
        path = tmp_path / "thing.bin"
        path.write_bytes(b"\xff\xfe\x00binary")
        pipeline = build(EchoConverter(output="converted", input_formats=("bin",)), tokenizers)

        result = pipeline.run(Source.from_path(path), OPTS)

        assert SOURCE_STAGE not in [stage.stage for stage in result.stages]
        assert result.stages[0].stage == CONVERT_STAGE

    def test_it_does_not_warn_about_it(self, tokenizers: TokenizerRegistry, tmp_path: Path) -> None:
        """A disclaimer on every document conversion would devalue the real warnings."""
        path = tmp_path / "thing.bin"
        path.write_bytes(b"\xff\xfe\x00binary")
        pipeline = build(EchoConverter(output="converted", input_formats=("bin",)), tokenizers)

        result = pipeline.run(Source.from_path(path), OPTS)

        assert result.warnings == ()

    def test_a_text_source_keeps_its_before_and_after(
        self, tokenizers: TokenizerRegistry, tmp_path: Path
    ) -> None:
        """The delta is untouched where it means something."""
        path = tmp_path / "thing.txt"
        path.write_text("the source text", encoding="utf-8")
        pipeline = build(EchoConverter(output="short", input_formats=("txt",)), tokenizers)

        result = pipeline.run(Source.from_path(path), OPTS)

        assert result.tokens_before is not None
        assert result.tokens_after is not None
        assert result.stages[0].stage == SOURCE_STAGE
        assert result.source_bytes == len("the source text")


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


class StagedConverter(BaseConverter):
    """A backend that records an intermediate text before returning its output."""

    def __init__(
        self,
        backend_id: str = "staged",
        *,
        stage_name: str = "halfway",
        stage_text: str = "middle text",
        output: str = "final",
        **info_overrides: object,
    ) -> None:
        """Initialise the backend.

        Args:
            backend_id: The backend's id.
            stage_name: The name to record the intermediate under.
            stage_text: The intermediate text.
            output: What to return as the conversion's result.
            **info_overrides: Fields to override on the ``BackendInfo``.
        """
        super().__init__()
        self.info = make_info(backend_id, **info_overrides)
        self._stage_name = stage_name
        self._stage_text = stage_text
        self._output = output

    def _probe(self) -> Availability:
        """Report that this backend can always run."""
        return Availability.present()

    def _convert(
        self,
        source: Source,  # noqa: ARG002
        options: ConvertOptions,  # noqa: ARG002
        context: ConversionContext,
    ) -> str:
        """Record the intermediate and return the output."""
        context.stage(self._stage_name, self._stage_text)
        return self._output


class TestBackendRecordedStages:
    """Defect D8: the two most interesting reductions happen inside a backend.

    Boilerplate removal happens inside a web converter and budget truncation
    inside a repository backend, so neither appeared in `--show-stages` — the
    numbers were in warnings and metadata, which is not where a reader looking
    for "where did the tokens go" looks.

    A backend now hands intermediate *text* to the pipeline, which measures it
    like any other stage. That does not breach "backends do not measure": the
    backend still cannot report a number.
    """

    def test_a_backend_stage_appears_between_source_and_convert(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(StagedConverter(), tokenizers)
        result = pipeline.run(source_file(tmp_path, "original text"), OPTS)

        assert [stage.stage for stage in result.stages] == [
            SOURCE_STAGE,
            "halfway",
            CONVERT_STAGE,
            "normalize_whitespace",
        ]

    def test_a_backend_stage_is_measured_by_the_pipeline_not_the_backend(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(StagedConverter(stage_text="0123456789"), tokenizers)
        result = pipeline.run(source_file(tmp_path, "x" * 20), OPTS)

        halfway = next(s for s in result.stages if s.stage == "halfway")
        assert halfway.characters == 10
        assert halfway.tokens is not None

    def test_a_backend_stage_never_becomes_the_before_count(
        self, tokenizers: TokenizerRegistry
    ) -> None:
        # `tokens_before` is the source stage or nothing at all. A backend stage
        # sitting between source and convert must not be able to claim it for a
        # source that has no readable text of its own.
        pipeline = build(StagedConverter(input_formats=("bin",)), tokenizers)
        result = pipeline.run(Source.from_bytes(b"\xff\xfe\x00bin", name="x.bin"), OPTS)

        assert result.tokens_before is None
        assert any(stage.stage == "halfway" for stage in result.stages)

    def test_the_intermediate_text_is_dropped_from_the_result(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        # Transport only: a result handed to a caller must not carry a second
        # copy of the document.
        pipeline = build(StagedConverter(stage_text="a" * 5000), tokenizers)
        result = pipeline.run(source_file(tmp_path, "in"), OPTS)

        assert result.internal_stages == ()

    def test_a_backend_that_records_nothing_is_unaffected(
        self, tmp_path: Path, tokenizers: TokenizerRegistry
    ) -> None:
        pipeline = build(EchoConverter(), tokenizers)
        result = pipeline.run(source_file(tmp_path, "hello"), OPTS)

        assert [stage.stage for stage in result.stages] == [
            SOURCE_STAGE,
            CONVERT_STAGE,
            "normalize_whitespace",
        ]
