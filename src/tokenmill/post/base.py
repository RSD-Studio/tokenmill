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
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from importlib.metadata import EntryPoint, entry_points
from typing import Final, Protocol, runtime_checkable

from tokenmill.core.models import ConvertOptions

__all__ = [
    "POSTPROCESSOR_ENTRY_POINT_GROUP",
    "BasePostProcessor",
    "PostProcessor",
    "PostProcessorRegistry",
    "default_post_registry",
    "reset_default_post_registry",
]

#: The entry point group post-processor plugins register under.
POSTPROCESSOR_ENTRY_POINT_GROUP: Final = "tokenmill.postprocessors"

_log = logging.getLogger(__name__)


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
