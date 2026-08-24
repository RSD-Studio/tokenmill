"""Prompt compression via LLMLingua-2 — the advanced, off-by-default reducer.

**Read this before enabling it.** `RESEARCH.md` Category 6's own caveat is the
warning that matters: prompt compression *"works best on redundant RAG context;
it is not universally safe and can hurt reasoning tasks"*. Microsoft's published
figures for LLMLingua-2 are 2-5x compression, task-agnostic, at BERT-level
speed — measured on their benchmarks, not on your task. **Evaluate it on your
own task before trusting it**, which is what `tokenmill fidelity` and
`tokenmill compare` are for.

It is off by default, destructive, and last in the chain (order 900).

## What this adapter does not assume

**Nothing is downloaded without permission.** The model is loaded with
`local_files_only=True` unless the run carries `allow_network`, so a first use
on an air-gapped machine is a clear refusal naming the download rather than a
silent multi-gigabyte fetch. That flag is passed through llmlingua's
`model_config`, which reaches `from_pretrained` untouched — **no environment
variable is set**, so this adds no process-global state to the five
`docs/ARCHITECTURE.md` already records.

**`trust_remote_code` is off.** llmlingua defaults it to *true*, which means a
model repository can execute arbitrary code on load. LLMLingua-2's own models
are token classifiers that need nothing of the kind. Turned off here, and
overridable only deliberately.

**Nothing is imported at module load.** `llmlingua` pulls `transformers` and
`torch`; importing those to register a post-processor would put a multi-second
import and hundreds of megabytes of RAM into every `tokenmill convert`.

## The state of verification, stated plainly

**The success path of this module has never been executed anywhere.** The model
lives on `huggingface.co`, which this project's development environment denies
at the egress proxy, so no compression has ever been run and no ratio has ever
been produced. What *is* tested here: the refusal path, the missing-dependency
path, the import-time guarantee, the ratio arithmetic, and the needle assertion
against a stub. Anything claiming otherwise would be fabricated, and
`PROGRESS.md` records the gap rather than implying it away.

This is the same posture Phase 2 took with docling's PDF path.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any, Final

from tokenmill.core.errors import BackendUnavailable, NetworkRequired
from tokenmill.core.models import ConvertOptions
from tokenmill.post.base import BasePostProcessor

__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_RATE",
    "SMALL_MODEL",
    "PromptCompressor",
]

_log = logging.getLogger(__name__)

#: LLMLingua-2's documented default, from Microsoft's own README. Chosen so a
#: ratio produced here is comparable with their published figures rather than
#: with a different model that happens to be smaller.
DEFAULT_MODEL: Final = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank"

#: The smaller alternative, also from upstream's README. Set
#: ``extra['compress_model']`` to it for a lighter download.
SMALL_MODEL: Final = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"

#: The fraction of the prompt to keep. 0.5 halves it. Conservative by the
#: standards of the published figures, which go to 0.2 and below.
DEFAULT_RATE: Final = 0.5

#: Tokens LLMLingua-2 is told never to drop. Newlines and pipes carry Markdown's
#: structure, and `RESEARCH.md` Category 7's rule — keep structure, strip
#: boilerplate — applies to a compressor at least as much as to a converter.
DEFAULT_FORCE_TOKENS: Final = ("\n", "|", "#")


class PromptCompressor(BasePostProcessor):
    """Compresses text with LLMLingua-2, if the user asks and the model is there.

    Attributes:
        id: ``compress``.
        name: Display name.
        description: One-line summary.
        destructive: True, and more literally than anything else in the chain —
            it deletes words on a model's judgement.
        order: 900, the compression band: last, after every other reduction.
    """

    id = "compress"
    name = "Prompt compression (LLMLingua-2)"
    description = (
        "Drop low-information tokens with LLMLingua-2. Suits redundant RAG "
        "context; can degrade reasoning tasks. Off by default; needs "
        '`pip install "tokenmill[compress]"` and a model download.'
    )
    destructive = True
    order = 900

    def process(self, text: str, options: ConvertOptions) -> str:
        """Compress ``text`` towards the requested ratio.

        Args:
            text: The text to compress.
            options: Read for ``allow_network`` and for
                ``extra['compress_ratio']``, ``extra['compress_model']``,
                ``extra['compress_device']``, ``extra['compress_cache_dir']``
                and ``extra['compress_force_tokens']``.

        Returns:
            The compressed text. Text too short to compress meaningfully is
            returned unchanged: a compressor that mangled a two-line document
            to hit a ratio would be obeying the number rather than the point.

        Raises:
            BackendUnavailable: If llmlingua is not installed.
            NetworkRequired: If the model is not cached and the run does not
                permit a download. The message names the size, the cache path
                and the exact command that fetches it.
        """
        if len(text.split()) < _MIN_WORDS:
            _log.info("text is too short to compress (%d words); left alone", len(text.split()))
            return text

        rate = _rate(options)
        compressor = self._load(options)
        force = options.extra.get("compress_force_tokens", DEFAULT_FORCE_TOKENS)
        force_tokens = (
            list(force) if isinstance(force, (list, tuple)) else list(DEFAULT_FORCE_TOKENS)
        )

        try:
            result = compressor.compress_prompt(
                text,
                rate=rate,
                force_tokens=force_tokens,
                # Digits are exactly the kind of low-frequency token a
                # perplexity-style filter discards and a reader most needs kept:
                # identifiers, versions, measurements.
                force_reserve_digit=True,
            )
        except Exception as exc:  # llmlingua raises many unrelated types
            msg = f"LLMLingua-2 failed to compress: {exc}"
            raise BackendUnavailable(msg, hint="try a smaller --compress-ratio") from exc

        compressed = result.get("compressed_prompt") if isinstance(result, dict) else None
        if not isinstance(compressed, str) or not compressed.strip():
            # A compressor that returned nothing has not saved anything; it has
            # destroyed the document, and the fidelity scorer would score it 0.
            msg = "LLMLingua-2 returned an empty document"
            raise BackendUnavailable(
                msg, hint="raise the ratio; a ratio this low removes everything"
            )

        _log.info(
            "compressed %s -> %s tokens (rate %.2f)",
            result.get("origin_tokens"),
            result.get("compressed_tokens"),
            rate,
        )
        return compressed

    def _load(self, options: ConvertOptions) -> Any:
        """Build the LLMLingua-2 compressor.

        Args:
            options: Supplies the model, device, cache path and network
                permission.

        Returns:
            The loaded compressor.

        Raises:
            BackendUnavailable: If llmlingua is not installed.
            NetworkRequired: If the model must be downloaded and may not be.
        """
        model_name = options.extra.get("compress_model", DEFAULT_MODEL)
        if not isinstance(model_name, str) or not model_name:
            model_name = DEFAULT_MODEL
        device = options.extra.get("compress_device", "cpu")
        cache_dir = options.extra.get("compress_cache_dir")

        llmlingua = _import_llmlingua()

        model_config: dict[str, Any] = {
            # llmlingua defaults this to True, which lets a model repository
            # execute arbitrary code on load. LLMLingua-2's models do not need
            # it.
            "trust_remote_code": False,
            # The whole download story: without network permission the model is
            # loaded from the cache or not at all.
            "local_files_only": not options.allow_network,
        }
        if isinstance(cache_dir, str) and cache_dir:
            model_config["cache_dir"] = cache_dir

        try:
            return llmlingua.PromptCompressor(
                model_name=model_name,
                device_map=str(device),
                use_llmlingua2=True,
                model_config=model_config,
            )
        except Exception as exc:  # transformers raises many unrelated types
            if options.allow_network:
                msg = f"could not load the LLMLingua-2 model {model_name!r}: {exc}"
                raise BackendUnavailable(
                    msg, hint="check the model name and that the download completed"
                ) from exc
            raise _download_required(model_name, cache_dir) from exc


#: Below this, compression has nothing to work with and the ratio is noise.
_MIN_WORDS: Final = 50


def _rate(options: ConvertOptions) -> float:
    """Resolve the fraction of the prompt to keep.

    Args:
        options: Supplies ``extra['compress_ratio']``.

    Returns:
        The rate, clamped to a sane open interval. A rate of 0 would ask for an
        empty document and a rate of 1 would ask for no compression; both are
        better refused than obeyed.
    """
    raw = options.extra.get("compress_ratio", DEFAULT_RATE)
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return DEFAULT_RATE
    return min(max(float(raw), 0.05), 1.0)


def _import_llmlingua() -> Any:
    """Import llmlingua, keeping its import-time warnings non-fatal.

    `transformers` is among the noisiest libraries in the ecosystem at import
    time, and this project's own suite runs under ``-W error``. Phase 2 lost a
    CI round to onnxruntime warning about Windows and Phase 4 lost one to
    pathspec; the same class of failure would report a perfectly healthy
    compressor as broken.

    Warnings are logged rather than raised, and not suppressed. A post-processor
    has no channel to attach a conversion warning to — unlike a backend, which
    has its context — which is a real gap recorded in ``PROGRESS.md``.

    Returns:
        The ``llmlingua`` module.

    Raises:
        BackendUnavailable: If it is not installed.
    """
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            import llmlingua
        for entry in caught:
            _log.warning("%s: %s", entry.category.__name__, entry.message)
    except ImportError as exc:
        msg = "prompt compression needs LLMLingua, which is not installed"
        raise BackendUnavailable(
            msg,
            hint='install it with `pip install "tokenmill[compress]"` — note that '
            "it resolves to 63 packages including PyTorch and the CUDA stack; see "
            "docs/BACKENDS.md for the CPU-only install",
        ) from exc
    return llmlingua


def _download_required(model_name: str, cache_dir: Any) -> NetworkRequired:
    """Build the refusal for a model that is not cached.

    Explicit, per the Phase 6 acceptance criterion: the message names what
    would be downloaded, where it would go, and the exact command that does it,
    so the user chooses rather than discovers.

    Args:
        model_name: The model that is missing.
        cache_dir: Where the user asked the cache to live, if anywhere.

    Returns:
        The error to raise.
    """
    where = cache_dir if isinstance(cache_dir, str) and cache_dir else "the HuggingFace cache"
    return NetworkRequired(
        f"the LLMLingua-2 model {model_name!r} is not in {where}, and this run may not download it",
        hint=(
            "compression models are large — hundreds of megabytes to a few "
            "gigabytes. Re-run with --allow-network to fetch it (the download "
            "resumes if interrupted), set extra['compress_cache_dir'] to choose "
            f"where it lands, or use the smaller {SMALL_MODEL!r}. "
            "Once cached, compression runs entirely offline."
        ),
    )
