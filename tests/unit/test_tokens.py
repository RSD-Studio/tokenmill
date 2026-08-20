"""Token measurement: the meter's arithmetic, and tokenizer resolution.

Everything here runs offline. tokenmill's real tokenizers download a vocabulary
on first use, so testing the arithmetic against them would mean testing nothing
on a machine without network access — and would make the test suite's result
depend on the weather. The arithmetic is therefore checked against
:class:`~tests.doubles.WordPieceTokenizer`, whose output is small enough to
verify by hand, plus the ``bytes`` tokenizer, which is exact and needs nothing.

Tests that require a real BPE tokenizer live in ``test_tokens_network.py`` behind
the ``network`` marker.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import Any

import pytest

from tests.doubles import StaticProvider, UnavailableTokenizer, WordPieceTokenizer
from tokenmill.core.errors import TokenizerNotFound, TokenizerUnavailable
from tokenmill.core.models import TokenCount
from tokenmill.tokens.base import Tokenizer, TokenizerProvider
from tokenmill.tokens.meter import TokenMeter
from tokenmill.tokens.registry import (
    TOKENIZER_ENTRY_POINT_GROUP,
    TokenizerRegistry,
    default_tokenizer_registry,
    reset_default_tokenizer_registry,
)
from tokenmill.tokens.tiktoken_adapter import ENCODINGS, TiktokenProvider, TiktokenTokenizer
from tokenmill.tokens.units_adapter import BytesTokenizer, UnitsProvider

#: Hand-counted golden vectors for the fake tokenizer, which splits text into
#: words, punctuation marks and whitespace runs. Each expectation below is the
#: piece list written out, so the numbers are checkable by reading them.
GOLDEN_WORDPIECE = [
    ("", 0, []),
    ("a", 1, ["a"]),
    ("one two", 3, ["one", " ", "two"]),
    ("a  b", 3, ["a", "  ", "b"]),
    ("Hello, world!", 5, ["Hello", ",", " ", "world", "!"]),
    ("# Heading", 3, ["#", " ", "Heading"]),
    ("\n\n", 1, ["\n\n"]),
]

#: Golden vectors for the ``bytes`` tokenizer. UTF-8 byte counts, worked out
#: from the encoding rules: ASCII is one byte, "é" is two, "→" three, and the
#: emoji four.
GOLDEN_BYTES = [
    ("", 0),
    ("abc", 3),
    ("café", 5),
    ("a→b", 5),
    ("🙂", 4),
    ("naïve résumé", 15),
]


class TestGoldenVectors:
    @pytest.mark.parametrize(("text", "expected", "pieces"), GOLDEN_WORDPIECE)
    def test_the_fake_tokenizer_matches_its_hand_counted_pieces(
        self, text: str, expected: int, pieces: list[str]
    ) -> None:
        assert len(pieces) == expected, "the golden vector disagrees with itself"
        assert WordPieceTokenizer().count(text) == expected

    @pytest.mark.parametrize(("text", "expected"), GOLDEN_BYTES)
    def test_bytes_counts_utf8_bytes_exactly(self, text: str, expected: int) -> None:
        assert BytesTokenizer().count(text) == expected
        assert BytesTokenizer().count(text) == len(text.encode("utf-8"))

    @pytest.mark.parametrize(("text", "expected", "pieces"), GOLDEN_WORDPIECE)
    def test_encode_and_count_agree(self, text: str, expected: int, pieces: list[str]) -> None:
        del pieces
        tokenizer = WordPieceTokenizer()

        assert len(tokenizer.encode(text)) == tokenizer.count(text) == expected

    def test_counting_is_deterministic(self) -> None:
        tokenizer = WordPieceTokenizer()

        assert tokenizer.count("repeatable") == tokenizer.count("repeatable")


class TestTokenMeter:
    def test_a_count_carries_the_tokenizer_id(self) -> None:
        meter = TokenMeter(WordPieceTokenizer("mine"))

        count = meter.count("one two")

        assert count == TokenCount(value=3, tokenizer_id="mine")

    def test_measure_stage_records_characters_and_tokens(self) -> None:
        meter = TokenMeter(WordPieceTokenizer())

        stage = meter.measure_stage("convert", "Hello, world!")

        assert stage.stage == "convert"
        assert stage.characters == 13
        assert stage.tokens is not None
        assert stage.tokens.value == 5

    def test_measure_stages_preserves_order(self) -> None:
        meter = TokenMeter(WordPieceTokenizer())

        stages = meter.measure_stages([("source", "a b"), ("convert", "a"), ("post", "")])

        assert [s.stage for s in stages] == ["source", "convert", "post"]
        assert [s.tokens.value for s in stages if s.tokens] == [3, 1, 0]

    def test_per_stage_counts_are_arithmetically_consistent(self) -> None:
        """Every stage count must equal a direct count of that stage's text."""
        tokenizer = WordPieceTokenizer()
        meter = TokenMeter(tokenizer)
        texts = ["the source text", "the converted text", "converted"]

        stages = meter.measure_stages([(f"s{i}", t) for i, t in enumerate(texts)])

        for stage, text in zip(stages, texts, strict=True):
            assert stage.tokens is not None
            assert stage.tokens.value == tokenizer.count(text)

    def test_delta_is_positive_when_the_text_got_cheaper(self) -> None:
        before = TokenCount(1000, "t")
        after = TokenCount(250, "t")

        assert TokenMeter.delta(before, after) == 750
        assert TokenMeter.reduction(before, after) == pytest.approx(0.75)

    def test_delta_is_negative_when_the_text_grew(self) -> None:
        assert TokenMeter.delta(TokenCount(100, "t"), TokenCount(140, "t")) == -40
        assert TokenMeter.reduction(TokenCount(100, "t"), TokenCount(140, "t")) == pytest.approx(
            -0.4
        )

    def test_counts_from_different_tokenizers_are_not_subtracted(self) -> None:
        """The number would be meaningless, so there must not be one."""
        before = TokenCount(1000, "o200k_base")
        after = TokenCount(900, "cl100k_base")

        assert TokenMeter.delta(before, after) is None
        assert TokenMeter.reduction(before, after) is None

    def test_a_missing_count_yields_no_delta(self) -> None:
        assert TokenMeter.delta(None, TokenCount(1, "t")) is None
        assert TokenMeter.reduction(TokenCount(1, "t"), None) is None

    def test_a_ratio_against_zero_is_undefined_not_zero(self) -> None:
        assert TokenMeter.reduction(TokenCount(0, "t"), TokenCount(0, "t")) is None


class TestMeterFailureHandling:
    def test_an_unloadable_tokenizer_yields_none_rather_than_an_estimate(self) -> None:
        meter = TokenMeter(UnavailableTokenizer())

        assert meter.count("some text") is None
        assert meter.failure is not None
        assert "vocabulary host" in meter.failure

    def test_a_failed_stage_still_records_exact_characters(self) -> None:
        meter = TokenMeter(UnavailableTokenizer())

        stage = meter.measure_stage("convert", "abcdef")

        assert stage.characters == 6
        assert stage.tokens is None

    def test_a_failed_tokenizer_is_not_retried(self) -> None:
        """A download that failed once will fail again.

        Retrying it once per stage would turn a 3-stage run into three timeouts.
        """

        class CountingFailure(UnavailableTokenizer):
            def __init__(self) -> None:
                super().__init__()
                self.attempts = 0

            def count(self, text: str) -> int:
                self.attempts += 1
                return super().count(text)

        tokenizer = CountingFailure()
        meter = TokenMeter(tokenizer)

        for _ in range(5):
            meter.count("text")

        assert tokenizer.attempts == 1


class TestTokenizerRegistry:
    def test_a_bare_alias_resolves(self) -> None:
        registry = TokenizerRegistry()
        registry.register(StaticProvider("test", WordPieceTokenizer("wp")))

        assert registry.get("wp").info.id == "wp"

    def test_a_prefixed_id_resolves(self) -> None:
        registry = TokenizerRegistry()
        registry.register(StaticProvider("test", WordPieceTokenizer("wp")))

        assert registry.get("test:wp").info.id == "wp"

    def test_instances_are_cached_because_loading_a_vocabulary_is_expensive(self) -> None:
        registry = TokenizerRegistry()
        registry.register(StaticProvider("test", WordPieceTokenizer("wp")))

        assert registry.get("wp") is registry.get("wp")

    def test_an_unknown_id_lists_what_is_known(self) -> None:
        registry = TokenizerRegistry()
        registry.register(StaticProvider("test", WordPieceTokenizer("wp")))

        with pytest.raises(TokenizerNotFound) as excinfo:
            registry.get("nonsense")

        assert "wp" in str(excinfo.value)

    def test_an_unknown_provider_prefix_is_rejected(self) -> None:
        registry = TokenizerRegistry()
        registry.register(StaticProvider("test", WordPieceTokenizer("wp")))

        with pytest.raises(TokenizerNotFound):
            registry.get("nosuchprovider:wp")

    def test_a_broken_tokenizer_plugin_does_not_hide_the_working_ones(self) -> None:
        registry = TokenizerRegistry()

        registry.load_from(
            [
                EntryPoint(
                    name="broken",
                    value=f"{__name__}:no_such_attribute",
                    group=TOKENIZER_ENTRY_POINT_GROUP,
                ),
                EntryPoint(
                    name="units",
                    value="tokenmill.tokens.units_adapter:UnitsProvider",
                    group=TOKENIZER_ENTRY_POINT_GROUP,
                ),
            ]
        )

        assert registry.get("bytes").info.id == "bytes"

    def test_the_installed_entry_points_expose_all_three_providers(self) -> None:
        registry = TokenizerRegistry()

        assert {p.id for p in registry.providers()} == {"tiktoken", "hf", "units"}

    def test_aliases_include_the_default_tokenizer(self) -> None:
        registry = TokenizerRegistry()

        assert "o200k_base" in registry.aliases()

    def test_default_registry_is_process_wide(self) -> None:
        reset_default_tokenizer_registry()
        try:
            assert default_tokenizer_registry() is default_tokenizer_registry()
        finally:
            reset_default_tokenizer_registry()


class TestProviders:
    def test_every_provider_implements_the_protocol(self) -> None:
        for provider in (TiktokenProvider(), UnitsProvider()):
            assert isinstance(provider, TokenizerProvider)

    def test_the_bytes_tokenizer_implements_the_protocol(self) -> None:
        assert isinstance(BytesTokenizer(), Tokenizer)

    def test_tiktoken_advertises_the_default_encoding(self) -> None:
        assert "o200k_base" in TiktokenProvider().aliases()
        assert "o200k_base" in ENCODINGS

    def test_tiktoken_rejects_an_unknown_encoding_without_touching_the_network(self) -> None:
        with pytest.raises(TokenizerNotFound):
            TiktokenProvider().create("not_an_encoding")

    def test_constructing_a_tiktoken_tokenizer_does_not_load_anything(self) -> None:
        """Resolution must be free.

        The download happens at the first count, so an unavailable tokenizer
        still resolves and then fails with a precise error at the point of use.
        """
        tokenizer = TiktokenTokenizer("o200k_base")

        assert tokenizer.info.id == "o200k_base"
        assert tokenizer.info.requires_network is True
        assert tokenizer.info.is_model_tokenizer is True

    def test_bytes_declares_itself_as_not_a_model_tokenizer(self) -> None:
        """It counts a real thing, but not the thing people mean by "tokens"."""
        info = BytesTokenizer().info

        assert info.is_model_tokenizer is False
        assert info.counts == "UTF-8 bytes"
        assert info.requires_network is False

    def test_units_rejects_anything_but_bytes(self) -> None:
        with pytest.raises(TokenizerNotFound):
            UnitsProvider().create("furlongs")

    def test_the_hf_provider_is_reachable_only_by_prefix(self) -> None:
        from tokenmill.tokens.hf_adapter import HuggingFaceProvider

        assert HuggingFaceProvider().aliases() == ()

    def test_the_hf_provider_rejects_an_empty_model_id(self) -> None:
        from tokenmill.tokens.hf_adapter import HuggingFaceProvider

        with pytest.raises(TokenizerNotFound):
            HuggingFaceProvider().create("")

    def test_an_absent_optional_dependency_is_reported_not_raised_as_importerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CONTRIBUTING.md rule 3, for the tokenizer layer."""
        import builtins

        from tokenmill.tokens.hf_adapter import HuggingFaceTokenizer

        real_import = builtins.__import__

        def refuse(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "tokenizers":
                msg = "No module named 'tokenizers'"
                raise ImportError(msg)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", refuse)

        with pytest.raises(TokenizerUnavailable, match="not installed"):
            HuggingFaceTokenizer("bert-base-uncased").count("x")
