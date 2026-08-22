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

Phase 2 adds the **fallback chain**. The registry no longer returns one backend
but an ordered chain of every installed backend that claims the source's format,
ranked by :mod:`tokenmill.core.preferences`. The pipeline walks it until one
succeeds. Two rules keep that from becoming a way to hide failures:

* **Every attempt is recorded** on the result as a
  :class:`~tokenmill.core.models.BackendAttempt`, and a fallback attaches a
  warning naming the backend that failed and why. A conversion that quietly
  came from the third choice would attribute a measurement to the wrong tool.
* **An explicit ``--backend`` never falls back.** The chain is one long, and a
  failure is an error.

**A binary document has no "before".** Converting a ``.docx`` used to report
``68,190 -> 3,494``, where the first figure was the zip archive's own bytes
decoded as text. Nobody would ever hand a model the bytes of a ``.docx``, so
that number cannot be subtracted from anything, and a percentage between the two
is not a saving. The pipeline now reports no ``tokens_before`` for such a source
and records :attr:`~tokenmill.core.models.ConversionResult.source_bytes`
instead, so the honest figure — how much the *output* costs — is the headline
and the input's size is reported as a size.

The comparison that is meaningful for a document is between *backends* on the
same file, and that is what Phase 5's ``compare`` command is for. The
before/after pair keeps its full meaning where both sides really are text a
model could be given: HTML to Markdown in Phase 3, and compression in Phase 6.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import replace

from tokenmill.core.errors import ConversionError, TokenizerError, UnsupportedFormat
from tokenmill.core.models import (
    BackendAttempt,
    ConversionResult,
    ConvertOptions,
    Source,
    StageCount,
)
from tokenmill.core.protocol import Converter
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

        candidates = self.backends.candidates(source, backend_id=opts.backend)
        chain = self.post_processors.resolve(opts.post_processors)
        meter = self._meter(opts)

        result, attempts = self._convert_with_fallback(source, opts, candidates)
        warnings = [*_fallback_warnings(attempts), *result.warnings]

        source_stage, source_bytes = self._source_stage(source, meter, warnings)
        stages: list[StageCount] = [source_stage] if source_stage is not None else []
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

        # `after` is the last stage that was actually counted. `before` is the
        # first — but *only* when there is a source stage to be first. A binary
        # document has none, and falling through to the converter's own output
        # would quietly redefine "before" as "after conversion", which is a
        # worse lie than reporting nothing.
        measured = [stage for stage in stages if stage.tokens is not None]
        tokens_after = measured[-1].tokens if measured else None
        tokens_before = None
        if source_stage is not None and measured and measured[0] is source_stage:
            tokens_before = source_stage.tokens

        return replace(
            result,
            text=text,
            duration_s=time.perf_counter() - started,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            stages=tuple(stages),
            post_processors=tuple(p.id for p in chain),
            warnings=tuple(warnings),
            attempts=attempts,
            source_bytes=source_bytes,
        )

    def _convert_with_fallback(
        self,
        source: Source,
        options: ConvertOptions,
        candidates: Sequence[Converter],
    ) -> tuple[ConversionResult, tuple[BackendAttempt, ...]]:
        """Try each candidate backend in turn until one converts the source.

        Args:
            source: The input to convert.
            options: How to convert it; ``fallback`` decides whether a failure
                moves on to the next candidate.
            candidates: The backends to try, best first. Never empty — the
                registry raises rather than returning an empty chain.

        Returns:
            The successful backend's result, and the record of every attempt.

        Raises:
            ConversionError: The last failure, when every candidate failed. It
                carries a hint listing what else was tried, so the user can see
                that the fallback happened and still did not help.
        """
        attempts: list[BackendAttempt] = []
        failure: ConversionError | None = None
        for converter in candidates:
            backend_id = converter.info.id
            try:
                result = converter.convert(source, options)
            except ConversionError as exc:
                _log.info("backend %s failed on %s: %s", backend_id, source.name, exc)
                attempts.append(BackendAttempt(backend_id, ok=False, error=str(exc)))
                failure = exc
                if not options.fallback:
                    break
                continue
            attempts.append(BackendAttempt(backend_id, ok=True))
            return result, tuple(attempts)

        if failure is None:  # pragma: no cover - candidates() never returns empty
            msg = f"no backend was tried for {source.name!r}"
            raise UnsupportedFormat(msg)

        # Re-raise the last failure rather than a new error of the same class:
        # the type, the __cause__ and the traceback are all worth keeping, and a
        # plugin's ConversionError subclass may not share the base initialiser.
        # Only the hint is amended, to say that falling back did not help.
        if len(attempts) > 1:
            failure.hint = (
                f"every backend that handles this source failed: "
                f"{', '.join(a.backend_id for a in attempts)}"
            )
        raise failure

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
    ) -> tuple[StageCount | None, int | None]:
        """Measure the untouched input, when measuring it means anything.

        Three cases, and the difference between them is the whole point:

        * **Text.** HTML, Markdown, a ``.txt``. Measured normally; its count is
          a real "before" that the output can be compared against.
        * **A binary document.** A PDF, or an OOXML zip. Its bytes do not decode
          as text, and counting the mojibake they decode to is arithmetically
          fine and semantically empty. There is **no source stage** and no
          before-count — only the file's size, which is reported as a size.
        * **Nothing readable.** A repository directory, or a URL that has not
          been fetched. No stage, no size, and a warning saying so.

        Args:
            source: The input to measure.
            meter: The meter, or ``None`` when no tokenizer resolved.
            warnings: Collects a warning if the source cannot be read at all.

        Returns:
            The source stage and the input's size in bytes. Either may be
            ``None``; a ``None`` stage means there is no comparable before.
        """
        try:
            data = source.read_bytes()
        except ValueError:
            warnings.append(
                f"{source.name} has no readable source text, so there is no before-count "
                f"to compare against"
            )
            return None, None

        try:
            raw = data.decode("utf-8")
        except UnicodeDecodeError:
            # Deliberately no warning. This is the normal, expected shape of a
            # document conversion, and a disclaimer printed on every single one
            # of them would train users to skim past the warning block — which
            # is where "this PDF has no text layer" and "these columns are
            # interleaved" live. Reporting no before-count says it better than
            # a sentence apologising for one.
            return None, len(data)
        return _measure(SOURCE_STAGE, raw, meter), len(data)


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


def _fallback_warnings(attempts: Sequence[BackendAttempt]) -> list[str]:
    """Describe any backend that failed before the one that succeeded.

    A fallback that leaves no trace is indistinguishable from the preferred
    backend having worked, which would make the reported measurement look like
    it came from a converter that never ran.

    Args:
        attempts: Every attempt, in order.

    Returns:
        One warning per failed attempt, empty when the first backend worked.
    """
    return [
        f"backend {attempt.backend_id!r} failed and tokenmill fell back to the next "
        f"one: {attempt.error}"
        for attempt in attempts
        if not attempt.ok
    ]


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
