"""The post-processor contract and registry.

Post-processors are the second half of the pipeline: converter produces raw
Markdown, then an ordered, individually toggleable chain of post-processors
turns it into the final text. They are plugins in exactly the same way backends
are, discovered through the ``tokenmill.postprocessors`` entry point group.

Three rules govern them, and they come from ``CONTRIBUTING.md``:

* **The default chain is opt-out, and it is one flag that says so.** A
  post-processor sets :attr:`PostProcessor.in_default_chain` to declare whether
  it runs when the user asks for nothing, and ``default_chain()`` reads exactly
  that. The default chain must never be able to damage a document.
* **Destructive is documentation, and it is a separate question.**
  :attr:`PostProcessor.destructive` says whether a step can lose information the
  user might have wanted. Until Phase 7 it was *also* the mechanism keeping a
  step out of the default chain, which made ``chunk`` — which loses nothing and
  only inserts markers — declare itself destructive in order to stay out. One
  flag carrying two meanings meant one of them had to be a lie; now the
  mechanism and the description are separate, and both can be true.
* **Order is explicit.** Each declares an :attr:`PostProcessor.order`, and the
  chain runs in ascending order so the result does not depend on entry point
  iteration order. ``docs/ARCHITECTURE.md`` records the reserved ranges.

**A post-processor can now say something** (defect N2, the owner's §3.3). Until
Phase 9 the whole contract was ``process(text, options) -> str``, where a
backend gets a :class:`~tokenmill.core.protocol.ConversionContext` that collects
warnings and structured facts. So the compressor could only *log* its achieved
ratio, and a processor that wanted to say "there was no front matter to strip"
had no channel at all.

:class:`PostProcessContext` is that channel, and it arrives as an **optional
third parameter**. The shape is deliberately the uglier of the two available:

* A clean break — making the third parameter required — would have broken every
  third-party post-processor ever written against the Phase 1 contract, for a
  feature none of them asked for.
* Instead, :meth:`PostProcessorRegistry.wants_context` asks each processor's own
  ``process`` signature whether it takes one, caches the answer, and the
  pipeline calls it with two arguments or three accordingly. A plugin written
  against the old contract is called exactly as it was and cannot tell the
  difference.

**The signature is the declaration**, rather than a ``wants_context = True``
class attribute. An author who writes ``def process(self, text, options,
context)`` has declared their intent as clearly as anyone can; making them *also*
set a flag would be a trap that fails at runtime with an argument-count error.
The introspection is done once per processor and cached, so the chain does not
pay for it per conversion.

Note that :meth:`BasePostProcessor.process` keeps its **two**-parameter
declaration. A subclass adding an optional third parameter is *widening*, which
is a legal override; the base declaring it would have made every existing
two-parameter subclass an illegal *narrowing* override on upgrade — undoing the
entire point of the optional-parameter shape. mypy said so, in nine files, which
is how this was caught.
"""

from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from importlib.metadata import EntryPoint, entry_points
from typing import Any, Final, Protocol, runtime_checkable

from tokenmill.core.models import ConvertOptions

__all__ = [
    "POSTPROCESSOR_ENTRY_POINT_GROUP",
    "BasePostProcessor",
    "PostProcessContext",
    "PostProcessor",
    "PostProcessorRegistry",
    "default_post_registry",
    "reset_default_post_registry",
]

#: The entry point group post-processor plugins register under.
POSTPROCESSOR_ENTRY_POINT_GROUP: Final = "tokenmill.postprocessors"

_log = logging.getLogger(__name__)


class PostProcessContext:
    """Scratch space handed to one post-processor for one run.

    The post-processing half of
    :class:`~tokenmill.core.protocol.ConversionContext`, and deliberately
    smaller than it. A post-processor may **warn** and may **note** a structured
    fact; it may not record a stage, because the pipeline already measures the
    text leaving every post-processor and a second mechanism would give two
    answers to one question.

    Attributes:
        processor_id: Whose context this is. Set by the pipeline, and used to
            attribute a warning and to namespace a note, so that two processors
            noting ``ratio`` do not overwrite each other.
    """

    def __init__(self, processor_id: str) -> None:
        """Initialise an empty context.

        Args:
            processor_id: The post-processor this belongs to.
        """
        self.processor_id = processor_id
        self.warnings: list[str] = []
        self.metadata: dict[str, Any] = {}

    def warn(self, message: str) -> None:
        """Record a non-fatal problem for the user.

        Args:
            message: What the user should know that did not stop the run.
        """
        _log.debug("post-processor warning (%s): %s", self.processor_id, message)
        self.warnings.append(message)

    def note(self, key: str, value: Any) -> None:
        """Record a structured fact about what this processor did.

        Args:
            key: The fact's name, such as ``achieved_ratio``.
            value: The value, which must be JSON-serialisable.
        """
        self.metadata[key] = value


@runtime_checkable
class PostProcessor(Protocol):
    """A single transformation applied to converted text.

    Attributes:
        id: Stable identifier, used as the ``--post`` value and entry point name.
        name: Human-readable display name.
        description: One sentence on what it does.
        destructive: Whether it can discard information the user might have
            wanted. **Documentation, not mechanism** — see the module docstring.
            It is what the CLI and the GUI show a user deciding whether to
            enable a step, and it is never consulted to build a chain.
        in_default_chain: Whether this runs when the user names no chain. This
            is the mechanism :meth:`PostProcessorRegistry.default_chain` reads.
            Anything destructive must set it ``False``; something that is not
            destructive may still set it ``False`` because it reshapes the
            document, which is what ``chunk`` does.
        order: Position in the chain; lower runs first.
    """

    id: str
    name: str
    description: str
    destructive: bool
    in_default_chain: bool
    order: int

    def process(self, text: str, options: ConvertOptions) -> str:
        """Transform the text.

        Must be pure: no I/O, no network, no mutation of ``options``. Must be
        idempotent where that is meaningful, so that running a chain twice does
        not keep changing the document.

        **This signature is unchanged from Phase 1 on purpose.** An
        implementation may take an optional third ``context`` parameter — see
        the module docstring — and still satisfies this protocol, because an
        extra parameter with a default does not stop a callable being callable
        with two arguments. Declaring the third parameter *here* would have done
        the opposite: it would have stopped every existing two-parameter
        implementation matching.

        Args:
            text: The text as it arrives from the previous stage.
            options: The conversion options, for post-processors that take
                settings from them.

        Returns:
            The transformed text.
        """
        ...


class BasePostProcessor(ABC):
    """Convenience base for post-processors.

    Supplies the attribute declarations so a subclass writes only
    :meth:`process` and its class-level metadata.
    """

    id: str
    name: str
    description: str
    destructive: bool = False
    in_default_chain: bool = True
    order: int = 500

    @abstractmethod
    def process(self, text: str, options: ConvertOptions) -> str:
        """Transform the text.

        **Declared with two parameters on purpose, and it is not an oversight.**
        A subclass that wants a context *widens* this to
        ``process(self, text, options, context=None)``, which is a legal
        override — an implementation may accept more than its base promises.
        Declaring the third parameter here would have made every existing
        two-parameter subclass, in this repository and in anybody else's, an
        illegal *narrowing* override the moment they upgraded. The whole point
        of the optional-parameter shape is that nobody has to change anything,
        and putting it on the base would have undone that.

        Args:
            text: The text as it arrives from the previous stage.
            options: The conversion options.

        Returns:
            The transformed text.
        """


class PostProcessorRegistry:
    """Holds the post-processors available in this process."""

    def __init__(self, entry_point_group: str = POSTPROCESSOR_ENTRY_POINT_GROUP) -> None:
        """Initialise an empty registry; discovery is deferred to first use.

        Args:
            entry_point_group: The entry point group to scan.
        """
        self._group = entry_point_group
        self._processors: dict[str, PostProcessor] = {}
        self._wants_context: dict[int, bool] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Scan entry points once, on first use."""
        if self._loaded:
            return
        self.load_from(entry_points(group=self._group))

    def load_from(self, eps: Iterable[EntryPoint]) -> None:
        """Load post-processors from an explicit set of entry points.

        Args:
            eps: The entry points to load.
        """
        for ep in eps:
            try:
                factory = ep.load()
                processor = factory() if callable(factory) else factory
                if not isinstance(processor, PostProcessor):
                    msg = f"{type(processor).__name__} is not a PostProcessor"
                    raise TypeError(msg)
            except Exception as exc:
                _log.warning("post-processor plugin %r failed to load: %s", ep.name, exc)
                _log.debug("plugin load traceback", exc_info=True)
                continue
            self._processors[processor.id] = processor
        self._loaded = True

    def register(self, processor: PostProcessor) -> None:
        """Add a post-processor directly, bypassing entry points.

        Args:
            processor: The post-processor to add.
        """
        self._processors[processor.id] = processor
        self._loaded = True

    def __iter__(self) -> Iterator[PostProcessor]:
        """Iterate over the loaded post-processors in chain order."""
        self._ensure_loaded()
        return iter(sorted(self._processors.values(), key=lambda p: (p.order, p.id)))

    def __len__(self) -> int:
        """Return how many post-processors are registered."""
        self._ensure_loaded()
        return len(self._processors)

    def get(self, processor_id: str) -> PostProcessor:
        """Return one post-processor by id.

        Args:
            processor_id: The id to look up.

        Returns:
            The post-processor.

        Raises:
            KeyError: If the id is unknown.
        """
        self._ensure_loaded()
        try:
            return self._processors[processor_id]
        except KeyError:
            known = ", ".join(sorted(self._processors)) or "none"
            msg = f"no post-processor named {processor_id!r} (known: {known})"
            raise KeyError(msg) from None

    def ids(self) -> tuple[str, ...]:
        """Return every registered post-processor id, in chain order."""
        return tuple(p.id for p in self)

    def wants_context(self, processor: PostProcessor) -> bool:
        """Report whether a post-processor's ``process`` takes a context.

        Introspected once per processor object and cached, because the answer
        cannot change and the chain would otherwise pay for it on every
        conversion.

        A signature that cannot be read at all — a C extension, an exotic
        callable — answers ``False``. That is the safe direction: calling with
        two arguments is what every post-processor written before Phase 9
        expects, so a processor whose signature is unreadable is treated as one
        of those rather than being handed an argument it may not accept.

        Args:
            processor: The post-processor to ask.

        Returns:
            True when it accepts a third positional or keyword ``context``.
        """
        key = id(processor)
        cached = self._wants_context.get(key)
        if cached is not None:
            return cached
        answer = _accepts_context(processor)
        self._wants_context[key] = answer
        return answer

    def run(
        self,
        processor: PostProcessor,
        text: str,
        options: ConvertOptions,
        context: PostProcessContext,
    ) -> str:
        """Call one post-processor, with a context only if it takes one.

        The single place that decision is made, so the pipeline, the tests and
        anything else driving a chain cannot disagree about it.

        Args:
            processor: The post-processor to run.
            text: The text arriving from the previous stage.
            options: The conversion options.
            context: Collects warnings and notes; discarded unmentioned where
                the processor was written against the Phase 1 contract.

        Returns:
            The transformed text.
        """
        if self.wants_context(processor):
            return processor.process(text, options, context)  # type: ignore[call-arg]
        return processor.process(text, options)

    def default_chain(self) -> tuple[PostProcessor, ...]:
        """Return the post-processors that run when the user asks for nothing.

        Every post-processor that declares :attr:`PostProcessor.in_default_chain`
        **and** is not destructive, in chain order.

        The second half is redundant against a correctly declared processor, and
        it is deliberately kept anyway. Splitting the flag would otherwise have
        weakened a Phase 1 guarantee that held *by construction*: a third-party
        post-processor written against the old contract sets ``destructive =
        True`` and says nothing about ``in_default_chain``, which
        :class:`BasePostProcessor` defaults to ``True`` — so a plugin that was
        correctly excluded before this change would have silently joined the
        default chain on upgrade. Reading both flags means the default pipeline
        still cannot damage a document by construction rather than by test.

        A processor declaring both is a contradiction rather than a preference,
        and ``tests/unit/test_post_phase5.py`` asserts the implication over the
        whole registry from both ends so it surfaces as a failure rather than
        being quietly resolved here.

        Returns:
            The default chain.
        """
        return tuple(p for p in self if p.in_default_chain and not p.destructive)

    def resolve(self, ids: tuple[str, ...] | None) -> tuple[PostProcessor, ...]:
        """Turn a requested chain into post-processors.

        An explicit list runs **in the order the user gave**, not in declared
        order: someone naming a chain by hand means that sequence.

        Args:
            ids: The requested ids, or ``None`` for the default chain.

        Returns:
            The chain to run.

        Raises:
            KeyError: If any id is unknown.
        """
        if ids is None:
            return self.default_chain()
        return tuple(self.get(pid) for pid in ids)


_DEFAULT: PostProcessorRegistry | None = None


def default_post_registry() -> PostProcessorRegistry:
    """Return the process-wide post-processor registry, building it on first call.

    Returns:
        The shared registry.
    """
    global _DEFAULT  # one deliberate process-wide cache
    if _DEFAULT is None:
        _DEFAULT = PostProcessorRegistry()
    return _DEFAULT


def reset_default_post_registry() -> None:
    """Discard the process-wide post-processor registry. Only useful in tests."""
    global _DEFAULT  # one deliberate process-wide cache
    _DEFAULT = None


def _accepts_context(processor: PostProcessor) -> bool:
    """Read a post-processor's signature to see whether it wants a context.

    Args:
        processor: The post-processor to inspect.

    Returns:
        True when ``process`` can be called with a third argument.
    """
    try:
        signature = inspect.signature(processor.process)
    except (TypeError, ValueError):
        # A builtin, a C extension, or something else with no readable
        # signature. Treated as a Phase 1 processor; see `wants_context`.
        return False

    positional = 0
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            # `*args` would swallow a context silently rather than using it, and
            # a processor written that way has declared nothing. Not enough.
            continue
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            continue
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            if parameter.name == "context":
                return True
            continue
        positional += 1
    # `self` is already bound off a method object, so `text` and `options` are
    # the first two and a third is the context.
    return positional >= 3
