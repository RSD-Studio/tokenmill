"""The post-processor contract and registry.

Post-processors are the second half of the pipeline: converter produces raw
Markdown, then an ordered, individually toggleable chain of post-processors
turns it into the final text. They are plugins in exactly the same way backends
are, discovered through the ``tokenmill.postprocessors`` entry point group.

Two rules govern them, and both come from ``CONTRIBUTING.md``:

* **Destructive steps are opt-in.** A post-processor that can lose information
  the user might have wanted sets :attr:`PostProcessor.destructive` and is not
  in the default chain. The default chain must never be able to damage a
  document.
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
        destructive: Whether it can discard information. Destructive
            post-processors are never in the default chain.
        order: Position in the chain; lower runs first.
    """

    id: str
    name: str
    description: str
    destructive: bool
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

        Every non-destructive post-processor, in chain order. Destructive ones
        are excluded by construction, so the default pipeline cannot lose
        anything the converter produced.

        Returns:
            The default chain.
        """
        return tuple(p for p in self if not p.destructive)

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
