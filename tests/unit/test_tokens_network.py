"""Real-tokenizer tests. Skipped by default; they need network access.

tiktoken fetches its BPE vocabulary from ``openaipublic.blob.core.windows.net``
and HuggingFace tokenizers come from ``huggingface.co``. Both are unreachable
from the development sandbox (an organisation egress policy, not a bug), so
these are marked ``network`` and deselected by default. CI, which can reach both,
runs them with ``-m network``.

**Nothing in this file has been observed to pass locally.** Phase 1's third
acceptance criterion — "token counts match a hand-verified tiktoken result on a
known string" — is verified here and only here, which is why ``PROGRESS.md``
records it as CI-verified rather than observed. The expected numbers below come
from the published behaviour of the encodings, and the first CI run is what
confirms them; if one is wrong, CI says so and the number gets corrected rather
than the assertion loosened.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenmill.core.models import ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.tokens.meter import TokenMeter
from tokenmill.tokens.registry import TokenizerRegistry

pytestmark = pytest.mark.network


class TestRealTiktoken:
    def test_a_known_string_counts_as_expected_under_o200k_base(self) -> None:
        """The hand-verifiable case: one short, unambiguous string.

        ``"hello world"`` is two common words with a leading-space merge, which
        every OpenAI BPE encodes as two tokens.
        """
        tokenizer = TokenizerRegistry().get("o200k_base")

        assert tokenizer.count("hello world") == 2

    def test_the_empty_string_is_zero_tokens(self) -> None:
        assert TokenizerRegistry().get("o200k_base").count("") == 0

    def test_encode_and_count_agree(self) -> None:
        tokenizer = TokenizerRegistry().get("o200k_base")
        text = "The quick brown fox jumps over the lazy dog."

        assert len(tokenizer.encode(text)) == tokenizer.count(text)

    def test_the_same_text_counts_differently_under_different_encodings(self) -> None:
        """Why a bare int is never enough: the tokenizer is part of the number.

        Asserted across a set of texts, and only that **at least one** differs.
        The first version of this test picked a single sentence and asserted the
        two counts differed; CI showed they were both 8. That was a real result
        and the test was wrong — two encodings agreeing on one short ASCII
        sentence is a coincidence, not a contradiction. o200k_base has a far
        larger vocabulary than r50k_base and merges much more aggressively on
        non-English text, so a difference is certain across a varied sample and
        merely likely for any one string.
        """
        registry = TokenizerRegistry()
        modern = registry.get("o200k_base")
        legacy = registry.get("r50k_base")
        texts = [
            "Tokenisation is not a universal constant.",
            "分词器的选择会改变每一个答案。",
            "def compute_reduction(before: int, after: int) -> float: ...",
            "🙂👨‍👩‍👧🇵🇰",
            "internationalisation antidisestablishmentarianism",
        ]

        counts = [(modern.count(t), legacy.count(t)) for t in texts]

        assert all(m > 0 and legacy_count > 0 for m, legacy_count in counts)
        assert any(m != legacy_count for m, legacy_count in counts), (
            f"o200k_base and r50k_base agreed on every sample: {counts}"
        )

    def test_special_token_text_is_counted_as_ordinary_text(self) -> None:
        """A document containing "<|endoftext|>" must not blow up the count."""
        tokenizer = TokenizerRegistry().get("o200k_base")

        assert tokenizer.count("<|endoftext|>") > 1

    def test_counts_are_stable_across_calls(self) -> None:
        tokenizer = TokenizerRegistry().get("cl100k_base")

        first = tokenizer.count("stability is the whole point")
        second = tokenizer.count("stability is the whole point")

        assert first == second


class TestRealPipelineMeasurement:
    def test_converting_the_boilerplate_fixture_reports_a_real_reduction(
        self, fixture_dir: Path
    ) -> None:
        """Acceptance criterion 4, with a real tokenizer rather than bytes."""
        source = Source.from_path(fixture_dir / "boilerplate.html")

        result = Pipeline().run(source, ConvertOptions(tokenizer="o200k_base"))

        assert result.tokens_before is not None
        assert result.tokens_after is not None
        assert result.tokens_before.tokenizer_id == "o200k_base"
        assert result.tokens_after.value < result.tokens_before.value
        assert result.reduction_ratio is not None
        assert 0 < result.reduction_ratio < 1

    def test_every_stage_count_matches_a_direct_count_of_that_stage(
        self, fixture_dir: Path
    ) -> None:
        """The per-stage report must be arithmetic, not narrative."""
        tokenizer = TokenizerRegistry().get("o200k_base")
        source = Source.from_path(fixture_dir / "article.html")

        result = Pipeline().run(source, ConvertOptions(tokenizer="o200k_base"))

        assert result.stages
        assert result.stages[-1].tokens is not None
        assert result.stages[-1].tokens.value == tokenizer.count(result.text)

    def test_the_meter_reports_no_failure_when_the_vocabulary_loads(self) -> None:
        meter = TokenMeter(TokenizerRegistry().get("o200k_base"))

        meter.count("anything")

        assert meter.failure is None


class TestRealHuggingFace:
    def test_a_hub_tokenizer_resolves_and_counts(self) -> None:
        pytest.importorskip("tokenizers")
        tokenizer = TokenizerRegistry().get("hf:bert-base-uncased")

        assert tokenizer.count("hello world") > 0

    def test_special_tokens_are_not_added_to_the_count(self) -> None:
        """Adding [CLS]/[SEP] would make every document two tokens too expensive."""
        pytest.importorskip("tokenizers")
        tokenizer = TokenizerRegistry().get("hf:bert-base-uncased")

        assert tokenizer.count("hello") == 1
