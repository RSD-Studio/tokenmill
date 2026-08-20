"""The conversion pipeline: converter, then post-processors, then measurement.

::

    Source ──▶ [Converter] ──▶ raw Markdown ──▶ [PostProcessor chain] ──▶ final text
                                     │                    │                    │
                                     └────────────────────┴────────────────────┘
                                                        │
                                                   TokenMeter
                                        (source · convert · each stage · final)

The pipeline is what makes measurement first-class rather than an afterthought.
Every stage is measured as the text leaves it, so a user can see not just that
the document got cheaper but *which step made it cheaper* — the converter, or a
particular post-processor.

Two design decisions are worth stating, because both are load-bearing:

**The backend does not measure; the pipeline does.** A backend author should
never have to know a tokenizer exists. It returns text; the pipeline counts it.

**A measurement failure is not a conversion failure.** If the tokenizer cannot
load — no network for its vocabulary — every count is ``None``, a warning is
attached, and the converted document is still returned. The user gets their
Markdown with the count honestly marked unavailable. We never substitute an
estimate for a measurement.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace

from tokenmill.core.errors import TokenizerError
from tokenmill.core.models import ConversionResult, ConvertOptions, Source, StageCount
from tokenmill.core.registry import Registry, default_registry
from tokenmill.post.base import PostProcessorRegistry, default_post_registry
from tokenmill.tokens.meter import TokenMeter
from tokenmill.tokens.registry import TokenizerRegistry, default_tokenizer_registry

__all__ = ["Pipeline", "convert"]

_log = logging.getLogger(__name__)

#: The stage name for the untouched input.
SOURCE_STAGE = "source"

#: The stage name for the converter's raw output.
CONVERT_STAGE = "convert"


class Pipeline:
    """Runs a source through a backend, a post-processor chain and the meter.

    Attributes:
        backends: Where converters come from.
        post_processors: Where post-processors come from.
        tokenizers: Where tokenizers come from.
    """

    def __init__(
        self,
        backends: Registry | None = None,
        post_processors: PostProcessorRegistry | None = None,
        tokenizers: TokenizerRegistry | None = None,
    ) -> None:
        """Initialise the pipeline.

        Args:
            backends: Backend registry; defaults to the process-wide one.
            post_processors: Post-processor registry; defaults to the
                process-wide one.
            tokenizers: Tokenizer registry; defaults to the process-wide one.
        """
        self.backends = backends if backends is not None else default_registry()
        self.post_processors = (
            post_processors if post_processors is not None else default_post_registry()
        )
        self.tokenizers = tokenizers if tokenizers is not None else default_tokenizer_registry()

    def run(self, source: Source, options: ConvertOptions | None = None) -> ConversionResult:
        """Convert a source and measure every stage.

        Args:
            source: The input to convert.
            options: How to convert it; defaults are used when omitted.

        Returns:
            The result, with per-stage counts, before/after totals, the ordered
            list of post-processors that ran, and any warnings.

        Raises:
            ConversionError: If backend selection or conversion fails. Failures
                to *measure* do not raise — they produce ``None`` counts and a
                warning.
            KeyError: If ``options.post_processors`` names an unknown
                post-processor.
        """
        opts = options if options is not None else ConvertOptions()
        started = time.perf_counter()

        converter = self.backends.select(source, backend_id=opts.backend)
        chain = self.post_processors.resolve(opts.post_processors)
        meter = self._meter(opts)

        result = converter.convert(source, opts)
        warnings = list(result.warnings)

        stages: list[StageCount] = [self._source_stage(source, meter, warnings)]
        stages.append(_measure(CONVERT_STAGE, result.text, meter))

        text = result.text
        for processor in chain:
            text = processor.process(text, opts)
            stages.append(_measure(processor.id, text, meter))

        if meter is None:
            warnings.append(
                f"tokenizer {opts.tokenizer!r} could not be resolved, so nothing was "
                f"counted; character counts are exact"
            )
        elif meter.failure is not None:
            warnings.append(
                f"token counting unavailable ({meter.failure}); character counts are exact"
            )

        # before/after come from the first and last stages that were actually
        # counted, so a partially-measured run still reports a comparable pair
        # rather than a number measured against nothing.
        measured = [stage for stage in stages if stage.tokens is not None]
        tokens_before = measured[0].tokens if measured else None
        tokens_after = measured[-1].tokens if measured else None

        return replace(
            result,
            text=text,
            duration_s=time.perf_counter() - started,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            stages=tuple(stages),
            post_processors=tuple(p.id for p in chain),
            warnings=tuple(warnings),
        )

    def _meter(self, options: ConvertOptions) -> TokenMeter | None:
        """Build the meter for this run, or ``None`` if the tokenizer is unknown.

        An unresolvable tokenizer id is a user error worth reporting, but it is
        not worth refusing to convert over: the document is still produced and
        the counts come back empty with a warning.

        Args:
            options: Supplies the tokenizer id.

        Returns:
            The meter, or ``None``.
        """
        try:
            return TokenMeter(self.tokenizers.get(options.tokenizer))
        except TokenizerError as exc:
            _log.warning("tokenizer %r unavailable: %s", options.tokenizer, exc)
            return None

    def _source_stage(
        self, source: Source, meter: TokenMeter | None, warnings: list[str]
    ) -> StageCount:
        """Measure the untouched input.

        A source with no local text — a repository directory, or a URL that has
        not been fetched — has no meaningful "before" count. That is recorded as
        zero characters and no tokens rather than being guessed at.

        Args:
            source: The input to measure.
            meter: The meter, or ``None`` when no tokenizer resolved.
            warnings: Collects a warning if the source cannot be read.

        Returns:
            The source stage's measurements.
        """
        try:
            raw = source.read_text()
        except ValueError:
            warnings.append(
                f"{source.name} has no readable source text, so there is no before-count "
                f"to compare against"
            )
            return StageCount(stage=SOURCE_STAGE, characters=0, tokens=None)
        return _measure(SOURCE_STAGE, raw, meter)


def _measure(stage: str, text: str, meter: TokenMeter | None) -> StageCount:
    """Measure one stage, with or without a working tokenizer.

    Args:
        stage: The stage name.
        text: The text as it leaves that stage.
        meter: The meter, or ``None`` when no tokenizer resolved.

    Returns:
        The stage's measurements. Characters are always recorded; tokens are
        recorded only when a tokenizer is available.
    """
    if meter is None:
        return StageCount(stage=stage, characters=len(text), tokens=None)
    return meter.measure_stage(stage, text)


def convert(
    source: Source, options: ConvertOptions | None = None, *, pipeline: Pipeline | None = None
) -> ConversionResult:
    """Convert a source with the default pipeline.

    The one-call entry point for library users and the function the CLI and the
    Phase 8 GUI both go through, so that every surface behaves identically.

    Args:
        source: The input to convert.
        options: How to convert it; defaults are used when omitted.
        pipeline: A pipeline to use instead of a freshly built default one.

    Returns:
        The conversion result.

    Raises:
        ConversionError: If backend selection or conversion fails.
    """
    return (pipeline if pipeline is not None else Pipeline()).run(source, options)
