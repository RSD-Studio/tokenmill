"""The public API the GUI is allowed to call, and the only thing it may call.

`docs/DEVELOPMENT_PLAN.md` names this phase's risk precisely: *GUI logic
creeping into the UI layer*. Its mitigation is a rule — the GUI may only call
the public library API — and a test that drives every GUI action through that
same API.

A rule needs a surface to be a rule about, so this module is it. Everything the
interface can do is a function here, and `app.py` contains layout, event
handlers and no conversion logic whatsoever. The consequences are worth being
explicit about:

* **Every GUI action is reachable without a browser.**
  `tests/integration/test_gui_api.py` exercises the whole feature set at this
  layer, in-process, in about a second. Playwright is reserved for the couple of
  flows where the browser genuinely is the thing under test.
* **The same surface is the HTTP API.** NiceGUI runs on FastAPI, so exposing
  these functions as endpoints later is a routing change and not a rewrite.
* **A feature that cannot be expressed here does not belong in the GUI.** If the
  interface needs something the library cannot do, the library grows it and the
  CLI gets it too. That is how the two stay in step.

Nothing here imports `nicegui`. This module works on a core-only install with no
`gui` extra, and the tests for it run on every CI cell rather than only where the
extra happens to be installed.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tokenmill.core.compare import BackendComparison, FormatComparison, compare_backends
from tokenmill.core.compare import compare_formats as _compare_formats
from tokenmill.core.errors import ConversionError, TokenizerError
from tokenmill.core.models import (
    Availability,
    ConversionResult,
    ConvertOptions,
    Domain,
    ImageHandling,
    IsolationMode,
    LicenseTier,
    LinkHandling,
    OutputFormat,
    Source,
)
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import default_registry
from tokenmill.fidelity import load_ground_truth, resolve_fixture
from tokenmill.fidelity import score as score_fidelity
from tokenmill.formats.base import default_format_registry
from tokenmill.post.base import default_post_registry
from tokenmill.tokens.registry import default_tokenizer_registry

__all__ = [
    "BackendChoice",
    "ConversionRequest",
    "ConversionSummary",
    "CostEstimate",
    "PostProcessorChoice",
    "StageRow",
    "backend_choices",
    "compare_across_backends",
    "compare_across_formats",
    "convert",
    "estimate_cost",
    "format_choices",
    "post_processor_choices",
    "tokenizer_choices",
]


@dataclass(frozen=True, slots=True)
class BackendChoice:
    """One row of the GUI's backend selector.

    Everything the interface needs to render a backend, including the reasons it
    might be unusable. `docs/DEVELOPMENT_PLAN.md` requires unavailable backends
    to be *greyed out with an install hint, never hidden and never crashing*, so
    the unavailable ones are in this list with :attr:`hint` filled in.

    Attributes:
        id: The backend id.
        name: Display name.
        description: One sentence on what it is good at.
        domains: Which input domains it serves.
        license: The SPDX identifier.
        license_tier: Permissive, copyleft or non-commercial.
        isolation: In-process, subprocess or service.
        available: Whether it can run right now.
        status: Why, in words, when it cannot.
        hint: The command that would fix it.
        badge: ``CPU`` or ``GPU``, for the badge the plan asks for.
        install_extra: The extra that supplies it, when there is one.
    """

    id: str
    name: str
    description: str
    domains: tuple[str, ...]
    license: str
    license_tier: LicenseTier
    isolation: IsolationMode
    available: bool
    status: str
    hint: str | None
    badge: str
    install_extra: str | None

    @property
    def isolated(self) -> bool:
        """Whether this backend runs outside the tokenmill process.

        Returns:
            True for subprocess and service backends.
        """
        return self.isolation is not IsolationMode.IN_PROCESS


@dataclass(frozen=True, slots=True)
class PostProcessorChoice:
    """One row of the GUI's post-processor list.

    Attributes:
        id: The post-processor id.
        name: Display name.
        description: What it does.
        destructive: Whether it can lose information. Shown to the user; this is
            the flag's whole job since Phase 7 split it from the mechanism.
        in_default_chain: Whether it runs when nothing is chosen.
        order: Position in the chain.
    """

    id: str
    name: str
    description: str
    destructive: bool
    in_default_chain: bool
    order: int


@dataclass(frozen=True, slots=True)
class StageRow:
    """One row of the per-stage token breakdown.

    Attributes:
        name: The stage's name.
        tokens: What the document cost after it.
        delta: Change from the previous stage, or ``None`` for the first.
    """

    name: str
    tokens: int
    delta: int | None


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """What a conversion would cost to send to a model.

    **No rate table ships with tokenmill and none ever will.** Prices change, and
    a stale one in this repository becomes a lie told confidently. The rate is
    the user's, typed in, and this is arithmetic on it.

    Attributes:
        tokens: The token count the estimate is for.
        rate_per_million: What the user said their model costs.
        currency: The user's label for their own units. Not validated and not
            converted — tokenmill has no exchange rates either.
        cost: The result.
    """

    tokens: int
    rate_per_million: float
    currency: str
    cost: float


@dataclass(frozen=True, slots=True)
class ConversionSummary:
    """Everything the results panel shows about one conversion.

    Attributes:
        source_name: What was converted.
        backend_id: What converted it.
        text: The output.
        output_format: What it is.
        tokens_before: The input's cost, or ``None`` for a binary document that
            has no comparable before-count.
        tokens_after: The output's cost.
        tokenizer_id: What the counts are in. Part of the number's meaning.
        reduction_ratio: The saving, or ``None`` when there is no before-count.
        duration_ms: Wall-clock time.
        warnings: Non-fatal problems the user should see.
        metadata: Structured facts the backend recorded.
        stages: The per-stage breakdown.
        fidelity: What the conversion cost in accuracy, when there is ground
            truth for the source. ``None`` is not zero and the GUI must not
            render it as one.
        error: Why it failed, when it did. A summary always exists; a failed one
            carries this instead of text.
        error_hint: What to do about the failure.
    """

    source_name: str
    backend_id: str | None
    text: str
    output_format: str
    tokens_before: int | None
    tokens_after: int | None
    tokenizer_id: str | None
    reduction_ratio: float | None
    duration_ms: int
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    stages: tuple[StageRow, ...] = ()
    fidelity: float | None = None
    error: str | None = None
    error_hint: str | None = None

    @property
    def ok(self) -> bool:
        """Whether the conversion succeeded.

        Returns:
            True when there is no error.
        """
        return self.error is None


@dataclass(frozen=True, slots=True)
class ConversionRequest:
    """One thing the user asked for, in the form the GUI collects it.

    Attributes:
        source: The input.
        tokenizer: Which tokenizer to count in.
        backend: A pinned backend, or ``None`` to auto-select.
        post_processors: The chain, or ``None`` for the default.
        output_format: What to emit.
        image_handling: What the `links` processor does with images.
        link_handling: What it does with links.
        allow_network: Whether backends may make network calls of their own.
        fetch: Whether a URL source may be retrieved.
        timeout_s: Per-conversion budget.
        score_fidelity: Whether to score the result against ground truth.
        corpus: Where to look for ground truth.
        extra: Per-backend settings.
    """

    source: Source
    tokenizer: str = "o200k_base"
    backend: str | None = None
    post_processors: tuple[str, ...] | None = None
    output_format: OutputFormat = OutputFormat.MARKDOWN
    image_handling: ImageHandling = ImageHandling.KEEP
    link_handling: LinkHandling = LinkHandling.KEEP
    allow_network: bool = False
    fetch: bool = True
    timeout_s: float = 120.0
    score_fidelity: bool = True
    corpus: Path | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_options(self) -> ConvertOptions:
        """Build the library options this request implies.

        Returns:
            The options.
        """
        return ConvertOptions(
            tokenizer=self.tokenizer,
            backend=self.backend,
            post_processors=self.post_processors,
            output_format=self.output_format,
            image_handling=self.image_handling,
            link_handling=self.link_handling,
            allow_network=self.allow_network,
            fetch=self.fetch,
            timeout_s=self.timeout_s,
            extra=dict(self.extra),
        )


def backend_choices(domain: Domain | None = None) -> tuple[BackendChoice, ...]:
    """List every registered backend, available or not.

    Unavailable backends are **included**, with the reason and the install
    command, because the plan requires them greyed out rather than hidden. A
    backend a user cannot find is indistinguishable from one that does not exist,
    and they then go looking for another tool.

    Args:
        domain: Restrict to backends serving this domain.

    Returns:
        The choices, in the registry's own order.
    """
    choices: list[BackendChoice] = []
    for converter in default_registry():
        info = converter.info
        if domain is not None and domain not in info.domains:
            continue
        availability: Availability = converter.is_available()
        choices.append(
            BackendChoice(
                id=info.id,
                name=info.name,
                description=info.description,
                domains=tuple(d.value for d in info.domains),
                license=info.license,
                license_tier=info.license_tier,
                isolation=info.isolation,
                available=bool(availability),
                status=availability.describe(),
                hint=availability.hint,
                badge="GPU" if info.requires_gpu else "CPU",
                install_extra=info.install_extra,
            )
        )
    return tuple(choices)


def post_processor_choices() -> tuple[PostProcessorChoice, ...]:
    """List every registered post-processor in chain order.

    Returns:
        The choices.
    """
    return tuple(
        PostProcessorChoice(
            id=p.id,
            name=p.name,
            description=p.description,
            destructive=p.destructive,
            in_default_chain=p.in_default_chain,
            order=p.order,
        )
        for p in default_post_registry()
    )


def tokenizer_choices() -> tuple[str, ...]:
    """List every tokenizer id the GUI can offer.

    Returns:
        The ids, sorted.
    """
    return tuple(sorted(default_tokenizer_registry().aliases()))


def format_choices() -> tuple[str, ...]:
    """List every table encoder id.

    Returns:
        The ids, sorted.
    """
    return tuple(sorted(e.id for e in default_format_registry()))


def convert(request: ConversionRequest, *, pipeline: Pipeline | None = None) -> ConversionSummary:
    """Run one conversion and return everything the results panel needs.

    **A failure is a summary, not an exception.** The plan requires backend
    failure to surface as a readable, actionable message, and a batch of twenty
    must not stop at the first bad file. So a `ConversionError` becomes a
    summary with :attr:`ConversionSummary.error` set, and the caller renders it
    like any other row.

    Args:
        request: What the user asked for.
        pipeline: The pipeline to use; a default one is built when omitted.

    Returns:
        The summary, successful or not.
    """
    runner = pipeline if pipeline is not None else Pipeline()
    started = time.perf_counter()
    try:
        result = runner.run(request.source, request.to_options())
    except ConversionError as exc:
        return ConversionSummary(
            source_name=request.source.name,
            backend_id=exc.backend_id,
            text="",
            output_format="",
            tokens_before=None,
            tokens_after=None,
            tokenizer_id=None,
            reduction_ratio=None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc),
            error_hint=exc.hint,
        )
    return _summarise(result, request)


def _summarise(result: ConversionResult, request: ConversionRequest) -> ConversionSummary:
    """Turn a library result into the shape the interface renders.

    Args:
        result: What the pipeline produced.
        request: What was asked for, for the fidelity lookup.

    Returns:
        The summary.
    """
    stages: list[StageRow] = []
    previous: int | None = None
    for stage in result.stages:
        if stage.tokens is None:
            # No tokenizer loaded. A stage row with a fabricated count would be
            # worse than no row; the panel shows the character counts instead.
            continue
        value = stage.tokens.value
        stages.append(
            StageRow(
                name=stage.stage,
                tokens=value,
                delta=None if previous is None else value - previous,
            )
        )
        previous = value

    return ConversionSummary(
        source_name=result.source_name,
        backend_id=result.backend_id,
        text=result.text,
        output_format=result.output_format.value,
        tokens_before=result.tokens_before.value if result.tokens_before else None,
        tokens_after=result.tokens_after.value if result.tokens_after else None,
        tokenizer_id=(
            result.tokens_after.tokenizer_id
            if result.tokens_after
            else (result.tokens_before.tokenizer_id if result.tokens_before else None)
        ),
        reduction_ratio=result.reduction_ratio,
        duration_ms=int(result.duration_s * 1000),
        warnings=result.warnings,
        metadata=dict(result.metadata),
        stages=tuple(stages),
        fidelity=_fidelity_of(result, request),
    )


def _fidelity_of(result: ConversionResult, request: ConversionRequest) -> float | None:
    """Score a result against ground truth, when there is any for its source.

    **`None` is not zero**, and the GUI must render it as "n/a" rather than as a
    failing score. A fixture with no ground truth is unmeasured, which is a
    different thing from a conversion that destroyed the document.

    Args:
        result: The conversion to score.
        request: Supplies the corpus location and whether to score at all.

    Returns:
        The overall score, or ``None`` when there is no ground truth, no corpus,
        or scoring failed for any reason — none of which should cost the user
        their conversion.
    """
    if not request.score_fidelity or request.corpus is None:
        return None
    try:
        fixtures = load_ground_truth(request.corpus)
        name, truth = resolve_fixture(fixtures, request.source.name)
        return score_fidelity(result.text, truth, fixture=name).overall
    except Exception:  # scoring is a bonus; never let it fail a conversion
        return None


def compare_across_backends(
    request: ConversionRequest,
    backend_ids: Sequence[str],
    *,
    pipeline: Pipeline | None = None,
) -> BackendComparison:
    """Run one input through several backends and measure each.

    **The rows come back in preference order and are not sorted by size**, and
    the GUI must render them that way. On `tables.pdf` the cheapest backend is
    the one that destroys the table; a view sorted by token count is a machine
    for recommending it. `docs/ARCHITECTURE.md` has the reasoning and
    `tests/integration/test_gui_api.py` asserts the order survives this layer.

    Args:
        request: The input and the options.
        backend_ids: The backends to try, in the order to report them.
        pipeline: The pipeline to use.

    Returns:
        The comparison, failures included as rows.
    """
    truth: Mapping[str, Any] | None = None
    fixture: str | None = None
    if request.corpus is not None:
        try:
            fixtures = load_ground_truth(request.corpus)
            fixture, truth = resolve_fixture(fixtures, request.source.name)
        except Exception:
            # No ground truth for this input is the normal case outside the
            # corpus. The comparison still runs; the fidelity column is n/a.
            truth, fixture = None, None

    return compare_backends(
        request.source,
        backend_ids,
        options=request.to_options(),
        pipeline=pipeline,
        truth=truth,
        fixture=fixture,
    )


def compare_across_formats(
    text: str,
    format_ids: Sequence[str],
    *,
    tokenizer: str,
    source_name: str,
) -> FormatComparison:
    """Re-encode the first table in some converted text in several formats.

    Args:
        text: Converted Markdown containing a table.
        format_ids: The encoders to try.
        tokenizer: What to count in.
        source_name: What the table came from.

    Returns:
        The comparison.

    Raises:
        TableError: If the text carries no table.
    """
    try:
        counter = default_tokenizer_registry().get(tokenizer)
        count = counter.count
        tokenizer_id = tokenizer
    except TokenizerError:
        # A tokenizer that will not load must not take the comparison with it:
        # the byte lengths are still worth showing, and the panel says the
        # counts are missing rather than inventing them.
        count = None
        tokenizer_id = tokenizer

    return _compare_formats(
        text,
        format_ids,
        registry=default_format_registry(),
        count=count,
        tokenizer_id=tokenizer_id,
        source_name=source_name,
    )


def estimate_cost(tokens: int, rate_per_million: float, currency: str = "$") -> CostEstimate:
    """Multiply a token count by a rate the user supplied.

    That is the whole feature, and the restraint is the point. tokenmill ships no
    rate table: model prices change, and a stale one in this repository would be
    a confident lie about somebody's bill.

    Args:
        tokens: The token count.
        rate_per_million: Cost per million tokens, from the user.
        currency: The user's own label for their units. Not validated, not
            converted — there are no exchange rates here either.

    Returns:
        The estimate.

    Raises:
        ValueError: If the token count or the rate is negative. A negative bill
            is a typo, and silently rendering one would be worse than refusing.
    """
    if tokens < 0:
        msg = f"token count cannot be negative: {tokens}"
        raise ValueError(msg)
    if rate_per_million < 0:
        msg = f"rate cannot be negative: {rate_per_million}"
        raise ValueError(msg)
    return CostEstimate(
        tokens=tokens,
        rate_per_million=rate_per_million,
        currency=currency,
        cost=tokens / 1_000_000 * rate_per_million,
    )
