"""Prompt compression: every path that can be executed without the model.

**What these tests do not do.** They do not test LLMLingua-2. The model lives on
`huggingface.co`, which this project's development environment denies at the
egress proxy, so no compression has ever been run here and no ratio has ever
been produced. `PROGRESS.md` records that as unverified rather than implying
otherwise.

**What they do test** is all of tokenmill's own logic around it, against a stub
standing in for the library: that nothing is imported at module load, that
nothing downloads without permission, that `trust_remote_code` is off, that the
refusal names the size and the command, that a compressor returning nothing is
an error rather than a triumphant 100% saving, and that the needle in
`long_context.md` survives.

The stub is honest about being a stub: it asserts on the arguments tokenmill
passes, which is the half of the contract tokenmill owns.
"""

from __future__ import annotations

import builtins
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

from tokenmill.core.errors import BackendUnavailable, NetworkRequired
from tokenmill.core.models import ConvertOptions
from tokenmill.post.base import default_post_registry
from tokenmill.post.compress import (
    DEFAULT_MODEL,
    DEFAULT_RATE,
    SMALL_MODEL,
    PromptCompressor,
)

#: A path that is never created; only its passing-through is checked.
CACHE_DIR = Path("/var/tmp/tokenmill-models")  # noqa: S108

OFFLINE = ConvertOptions(tokenizer="bytes")
ONLINE = ConvertOptions(tokenizer="bytes", allow_network=True)

#: Long enough to be worth compressing, per the module's own floor.
LONG = " ".join(f"sentence number {index} with some filler words in it." for index in range(40))


class StubCompressor:
    """Stands in for `llmlingua.PromptCompressor`, recording how it was called."""

    last_init: ClassVar[dict[str, Any]] = {}
    last_call: ClassVar[dict[str, Any]] = {}
    #: What `compress_prompt` should hand back, or an exception to raise.
    behaviour: Any = None

    def __init__(self, **kwargs: Any) -> None:
        StubCompressor.last_init = kwargs
        config = kwargs.get("model_config")
        # A real `from_pretrained(local_files_only=True)` raises when the model
        # is not in the cache, which is the case this stub models.
        if isinstance(config, dict) and config.get("local_files_only") and not self.cached:
            raise OSError("model not found in cache")

    #: Whether the pretend model is already downloaded.
    cached: bool = True

    def compress_prompt(self, text: str, **kwargs: Any) -> Any:
        """Record the call and return whatever the test asked for."""
        StubCompressor.last_call = {"text": text, **kwargs}
        if isinstance(StubCompressor.behaviour, Exception):
            raise StubCompressor.behaviour
        if StubCompressor.behaviour is not None:
            return StubCompressor.behaviour
        kept = " ".join(text.split()[: max(1, len(text.split()) // 2)])
        return {
            "compressed_prompt": kept,
            "origin_tokens": len(text.split()),
            "compressed_tokens": len(kept.split()),
            "rate": kwargs.get("rate"),
        }


@pytest.fixture
def stub_llmlingua(monkeypatch: pytest.MonkeyPatch) -> type[StubCompressor]:
    """Install a fake `llmlingua` module for the duration of one test."""
    import types

    module = types.ModuleType("llmlingua")
    module.PromptCompressor = StubCompressor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llmlingua", module)
    StubCompressor.last_init = {}
    StubCompressor.last_call = {}
    StubCompressor.behaviour = None
    StubCompressor.cached = True
    return StubCompressor


class TestTheContract:
    """True whether or not LLMLingua is installed."""

    def test_it_is_destructive_and_therefore_not_in_the_default_chain(self) -> None:
        processor = default_post_registry().get("compress")
        assert processor.destructive is True
        assert "compress" not in [p.id for p in default_post_registry().default_chain()]

    def test_it_sits_last_in_the_chain(self) -> None:
        # docs/ARCHITECTURE.md reserves 900-999 for compression: after every
        # other reduction, because compressing then stripping would waste work.
        registry = default_post_registry()
        assert registry.get("compress").order >= 900
        assert [p.id for p in registry][-1] == "compress"

    def test_nothing_is_imported_at_module_load(self) -> None:
        # llmlingua pulls transformers and torch. Importing those to register a
        # post-processor would put seconds and hundreds of megabytes into every
        # `tokenmill convert`, including the ones that never compress.
        import tokenmill.post.compress  # noqa: F401

        assert "llmlingua" not in sys.modules
        assert "torch" not in sys.modules
        assert "transformers" not in sys.modules

    def test_a_missing_llmlingua_names_the_extra_and_its_real_cost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_import = builtins.__import__

        def refuse(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "llmlingua":
                raise ImportError("no llmlingua here")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", refuse)
        with pytest.raises(BackendUnavailable) as caught:
            PromptCompressor().process(LONG, OFFLINE)
        hint = caught.value.hint or ""
        assert "tokenmill[compress]" in hint
        assert "CUDA" in hint

    def test_short_text_is_left_alone_before_anything_is_imported(self) -> None:
        text = "Too short to compress.\n"
        assert PromptCompressor().process(text, OFFLINE) == text


class TestNothingDownloadsWithoutPermission:
    def test_the_model_is_loaded_local_only_unless_network_is_allowed(
        self, stub_llmlingua: type[StubCompressor]
    ) -> None:
        stub_llmlingua.cached = True
        PromptCompressor().process(LONG, OFFLINE)
        assert stub_llmlingua.last_init["model_config"]["local_files_only"] is True

    def test_permission_lets_it_download(self, stub_llmlingua: type[StubCompressor]) -> None:
        PromptCompressor().process(LONG, ONLINE)
        assert stub_llmlingua.last_init["model_config"]["local_files_only"] is False

    def test_an_uncached_model_without_permission_is_a_refusal_naming_the_command(
        self, stub_llmlingua: type[StubCompressor]
    ) -> None:
        stub_llmlingua.cached = False
        with pytest.raises(NetworkRequired) as caught:
            PromptCompressor().process(LONG, OFFLINE)
        hint = caught.value.hint or ""
        assert "--allow-network" in hint
        assert "resumes if interrupted" in hint
        assert "compress_cache_dir" in hint
        assert SMALL_MODEL in hint
        assert "entirely offline" in hint

    def test_a_cached_model_works_with_no_network_permission(
        self, stub_llmlingua: type[StubCompressor]
    ) -> None:
        # "Fully offline once cached", as far as it can be shown without a
        # cache: the load is attempted with local_files_only and succeeds.
        stub_llmlingua.cached = True
        out = PromptCompressor().process(LONG, OFFLINE)
        assert out
        assert stub_llmlingua.last_init["model_config"]["local_files_only"] is True

    def test_trust_remote_code_is_off(self, stub_llmlingua: type[StubCompressor]) -> None:
        # llmlingua defaults it to True, which lets a model repository execute
        # arbitrary code on load.
        PromptCompressor().process(LONG, OFFLINE)
        assert stub_llmlingua.last_init["model_config"]["trust_remote_code"] is False

    @pytest.mark.usefixtures("stub_llmlingua")
    def test_no_environment_variable_is_set(self) -> None:
        # docs/ARCHITECTURE.md records five pieces of process-global state
        # manipulated during a conversion. This deliberately adds none: the
        # offline switch rides in llmlingua's model_config instead.
        import os

        before = dict(os.environ)
        PromptCompressor().process(LONG, OFFLINE)
        assert dict(os.environ) == before

    def test_the_cache_directory_is_passed_through(
        self, stub_llmlingua: type[StubCompressor]
    ) -> None:
        options = OFFLINE.with_(extra={"compress_cache_dir": str(CACHE_DIR)})
        PromptCompressor().process(LONG, options)
        assert stub_llmlingua.last_init["model_config"]["cache_dir"] == str(CACHE_DIR)


class TestTheCompressionCall:
    def test_the_default_model_is_the_one_upstream_documents(
        self, stub_llmlingua: type[StubCompressor]
    ) -> None:
        PromptCompressor().process(LONG, OFFLINE)
        assert stub_llmlingua.last_init["model_name"] == DEFAULT_MODEL
        assert stub_llmlingua.last_init["use_llmlingua2"] is True

    def test_the_model_is_overridable(self, stub_llmlingua: type[StubCompressor]) -> None:
        options = OFFLINE.with_(extra={"compress_model": SMALL_MODEL})
        PromptCompressor().process(LONG, options)
        assert stub_llmlingua.last_init["model_name"] == SMALL_MODEL

    def test_it_runs_on_the_cpu_by_default(self, stub_llmlingua: type[StubCompressor]) -> None:
        PromptCompressor().process(LONG, OFFLINE)
        assert stub_llmlingua.last_init["device_map"] == "cpu"

    def test_the_requested_ratio_reaches_the_library(
        self, stub_llmlingua: type[StubCompressor]
    ) -> None:
        PromptCompressor().process(LONG, OFFLINE.with_(extra={"compress_ratio": 0.25}))
        assert stub_llmlingua.last_call["rate"] == 0.25

    @pytest.mark.parametrize(
        ("given", "expected"),
        [(0.0, 0.05), (-1, 0.05), (2.0, 1.0), (0.5, 0.5), ("nonsense", DEFAULT_RATE)],
    )
    def test_the_ratio_is_clamped_rather_than_obeyed(
        self, stub_llmlingua: type[StubCompressor], given: Any, expected: float
    ) -> None:
        # A rate of 0 asks for an empty document and a rate above 1 asks for
        # more text than went in. Both are better refused than obeyed.
        PromptCompressor().process(LONG, OFFLINE.with_(extra={"compress_ratio": given}))
        assert stub_llmlingua.last_call["rate"] == expected

    def test_markdown_structure_is_protected(self, stub_llmlingua: type[StubCompressor]) -> None:
        # RESEARCH.md Category 7: keep structure, strip boilerplate. It applies
        # to a compressor at least as much as to a converter.
        PromptCompressor().process(LONG, OFFLINE)
        assert "\n" in stub_llmlingua.last_call["force_tokens"]
        assert "|" in stub_llmlingua.last_call["force_tokens"]

    def test_digits_are_reserved(self, stub_llmlingua: type[StubCompressor]) -> None:
        # Identifiers, versions and measurements are exactly what a
        # low-information filter discards and a reader most needs kept.
        PromptCompressor().process(LONG, OFFLINE)
        assert stub_llmlingua.last_call["force_reserve_digit"] is True


class TestARatioIsNotASuccessOnItsOwn:
    def test_an_empty_result_is_an_error_not_a_hundred_percent_saving(
        self, stub_llmlingua: type[StubCompressor]
    ) -> None:
        # The failure benchmarks/README.md names, arriving through a new door.
        stub_llmlingua.behaviour = {"compressed_prompt": "   "}
        with pytest.raises(BackendUnavailable, match="empty document"):
            PromptCompressor().process(LONG, OFFLINE)

    def test_a_library_failure_becomes_an_actionable_error(
        self, stub_llmlingua: type[StubCompressor]
    ) -> None:
        stub_llmlingua.behaviour = RuntimeError("something went wrong inside torch")
        with pytest.raises(BackendUnavailable, match="failed to compress"):
            PromptCompressor().process(LONG, OFFLINE)

    def test_the_needle_must_survive(
        self, stub_llmlingua: type[StubCompressor], fixture_dir: Path
    ) -> None:
        # long_context.md was built for this: 42 passages, each restated six
        # times, with one checkable fact. A compressor that drops the needle has
        # failed regardless of its ratio.
        #
        # Against the stub this checks tokenmill's own half of the contract —
        # that it asks for digits to be reserved and passes the text through
        # whole. The real assertion needs the model and is marked unverified.
        text = (fixture_dir / "long_context.md").read_text(encoding="utf-8")
        needle = "RSD-TOKENMILL-4417"
        assert text.count(needle) == 2

        stub_llmlingua.behaviour = {
            "compressed_prompt": text,
            "origin_tokens": 1,
            "compressed_tokens": 1,
        }
        out = PromptCompressor().process(text, OFFLINE.with_(extra={"compress_ratio": 0.5}))

        assert stub_llmlingua.last_call["text"] == text
        assert stub_llmlingua.last_call["force_reserve_digit"] is True
        assert out.count(needle) == 2
