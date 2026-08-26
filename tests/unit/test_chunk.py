"""Token-aware chunking through Chonkie.

Chunking is the one Phase 5 post-processor whose dependency is optional, so the
tests split in two: the behaviour (which needs Chonkie) and the refusal path
(which must be right whether it is installed or not).

The unit story is what makes this checkable offline. Chonkie's `ByteTokenizer`
was verified against tokenmill's own `bytes` counter on multibyte text and
emoji, so `--tokenizer bytes --chunk-size N` means N UTF-8 bytes — the same unit
every other number in the report is in, and no vocabulary download anywhere.
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest

from tokenmill.core.errors import BackendUnavailable
from tokenmill.core.models import ConvertOptions
from tokenmill.post.base import default_post_registry
from tokenmill.post.chunk import DEFAULT_CHUNK_SIZE, Chunker
from tokenmill.tokens.registry import default_tokenizer_registry

BYTES = ConvertOptions(tokenizer="bytes")


def byte_count(text: str) -> int:
    """Count UTF-8 bytes with tokenmill's own counter."""
    return default_tokenizer_registry().get("bytes").count(text)


@pytest.fixture(scope="module")
def long_text(fixture_dir: Path) -> str:
    """Return the long redundant fixture."""
    return (fixture_dir / "long_context.md").read_text(encoding="utf-8")


class TestTheContract:
    """True whether or not Chonkie is installed."""

    def test_it_loses_nothing_and_is_still_not_in_the_default_chain(self) -> None:
        """Both halves, because they used to be one flag and could not both be true.

        Chunking inserts marker comments and discards nothing, so `destructive`
        is False — which under the pre-Phase-7 contract would have put it in the
        default chain, because that flag was also the mechanism. `chunk` is the
        processor that made the case for splitting them.
        """
        processor = default_post_registry().get("chunk")

        assert processor.destructive is False
        assert processor.in_default_chain is False
        assert "chunk" not in [p.id for p in default_post_registry().default_chain()]

    def test_it_sits_in_the_chunking_band(self) -> None:
        # docs/ARCHITECTURE.md reserves 700-899 for chunking: after every
        # reduction, before compression.
        assert 700 <= default_post_registry().get("chunk").order < 900

    def test_an_empty_document_is_returned_unchanged(self) -> None:
        # Checked before Chonkie is imported, so it holds on a core install.
        assert Chunker().process("   \n", BYTES) == "   \n"

    def test_a_missing_chonkie_is_an_actionable_error_not_a_silent_no_op(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Phase 1 settled that a flag which silently does nothing is worse than
        # no flag. Returning the text unchanged would look like a document that
        # needed no chunking.
        real_import = builtins.__import__

        def refuse(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "chonkie":
                raise ImportError("no chonkie here")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", refuse)
        with pytest.raises(BackendUnavailable) as caught:
            Chunker().process("some text that is long enough to matter", BYTES)
        assert "chunk" in (caught.value.hint or "")


@pytest.mark.requires("chonkie")
class TestChunking:
    def test_a_document_that_fits_in_one_chunk_is_returned_unchanged(self) -> None:
        # A separator that appeared only to say "this was not split" is pure
        # cost.
        text = "one short paragraph.\n"
        assert Chunker().process(text, BYTES) == text

    def test_a_long_document_is_split_and_marked(self, long_text: str) -> None:
        out = Chunker().process(long_text, BYTES.with_(extra={"chunk_size": 20000}))
        assert out.count("<!-- tokenmill:chunk") == 3
        assert "<!-- tokenmill:chunk 2/4 -->" in out

    def test_no_chunk_exceeds_the_requested_size(self, long_text: str) -> None:
        size = 8000
        out = Chunker().process(long_text, BYTES.with_(extra={"chunk_size": size}))
        pieces = out.split("\n\n<!-- tokenmill")
        assert pieces
        for piece in pieces:
            assert byte_count(piece) <= size

    def test_the_size_is_in_the_run_s_own_unit(self, long_text: str) -> None:
        # The whole point of routing tokenmill's `bytes` id onto Chonkie's
        # ByteTokenizer: the number the user typed and the number the report
        # shows are the same kind of thing.
        out = Chunker().process(long_text, BYTES.with_(extra={"chunk_size": 5000}))
        first = out.split("\n\n<!-- tokenmill")[0]
        assert byte_count(first) <= 5000

    def test_smaller_chunks_mean_more_chunks(self, long_text: str) -> None:
        few = Chunker().process(long_text, BYTES.with_(extra={"chunk_size": 40000}))
        many = Chunker().process(long_text, BYTES.with_(extra={"chunk_size": 5000}))
        assert many.count("tokenmill:chunk") > few.count("tokenmill:chunk")

    def test_no_content_is_lost(self, long_text: str) -> None:
        out = Chunker().process(long_text, BYTES.with_(extra={"chunk_size": 9000}))
        needle = "RSD-TOKENMILL-4417"
        assert out.count(needle) == long_text.count(needle)

    def test_chunking_costs_tokens_rather_than_saving_them(self, long_text: str) -> None:
        # Worth asserting because it is the opposite of what a "token reduction
        # toolkit" reads like it should do. The markers are the cost, and the
        # per-stage report shows it as a rise.
        out = Chunker().process(long_text, BYTES.with_(extra={"chunk_size": 8000}))
        assert byte_count(out) > byte_count(long_text)

    def test_an_invalid_size_falls_back_to_the_default(self, long_text: str) -> None:
        out = Chunker().process(long_text, BYTES.with_(extra={"chunk_size": -5}))
        assert out.count("tokenmill:chunk") > 0
        assert DEFAULT_CHUNK_SIZE > 0

    def test_the_token_chunker_is_selectable(self, long_text: str) -> None:
        out = Chunker().process(
            long_text, BYTES.with_(extra={"chunk_size": 9000, "chunker": "token"})
        )
        assert out.count("tokenmill:chunk") > 0

    def test_a_separator_can_be_overridden(self, long_text: str) -> None:
        out = Chunker().process(
            long_text,
            BYTES.with_(extra={"chunk_size": 20000, "chunk_separator": "\n===SPLIT===\n"}),
        )
        assert "===SPLIT===" in out
        assert "tokenmill:chunk" not in out

    def test_an_unresolvable_tokenizer_says_which_flag_avoids_the_download(
        self, long_text: str
    ) -> None:
        options = ConvertOptions(tokenizer="no-such-vocabulary", extra={"chunk_size": 9000})
        with pytest.raises(BackendUnavailable) as caught:
            Chunker().process(long_text, options)
        assert "--tokenizer bytes" in (caught.value.hint or "")
