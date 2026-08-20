"""Tokenizer discovery and resolution.

Tokenizer providers are found through the ``tokenmill.tokenizers`` entry point
group — the same plugin mechanism the backends use, so a third party can add a
tokenizer with a ``pip install`` and no core edit.

Ids resolve two ways:

* ``provider:spec`` — explicit, e.g. ``tiktoken:o200k_base``, ``hf:gpt2``.
* a bare alias — e.g. ``o200k_base``, which providers claim through
  :meth:`~tokenmill.tokens.base.TokenizerProvider.aliases`.

Instances are cached per id, because loading a BPE vocabulary is expensive and a
batch run measures every file with the same tokenizer.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import Final

from tokenmill.core.errors import TokenizerNotFound
from tokenmill.tokens.base import Tokenizer, TokenizerProvider

__all__ = [
    "TOKENIZER_ENTRY_POINT_GROUP",
    "TokenizerRegistry",
    "default_tokenizer_registry",
    "reset_default_tokenizer_registry",
]

#: The entry point group tokenizer plugins register under.
TOKENIZER_ENTRY_POINT_GROUP: Final = "tokenmill.tokenizers"

_log = logging.getLogger(__name__)


class TokenizerRegistry:
    """Holds the tokenizer providers available in this process."""

    def __init__(self, entry_point_group: str = TOKENIZER_ENTRY_POINT_GROUP) -> None:
        """Initialise an empty registry; discovery is deferred to first use.

        Args:
            entry_point_group: The entry point group to scan.
        """
        self._group = entry_point_group
        self._providers: dict[str, TokenizerProvider] = {}
        self._cache: dict[str, Tokenizer] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Scan entry points once, on first use."""
        if self._loaded:
            return
        self.load_from(entry_points(group=self._group))

    def load_from(self, eps: Iterable[EntryPoint]) -> None:
        """Load providers from an explicit set of entry points.

        Args:
            eps: The entry points to load.
        """
        for ep in eps:
            try:
                factory = ep.load()
                provider = factory() if callable(factory) else factory
                if not isinstance(provider, TokenizerProvider):
                    msg = f"{type(provider).__name__} is not a TokenizerProvider"
                    raise TypeError(msg)
            except Exception as exc:
                # Same rule as backends: a broken plugin is not allowed to take
                # every other tokenizer down with it.
                _log.warning("tokenizer plugin %r failed to load: %s", ep.name, exc)
                _log.debug("plugin load traceback", exc_info=True)
                continue
            self.register(provider)
        self._loaded = True

    def register(self, provider: TokenizerProvider) -> None:
        """Add a provider directly, bypassing entry points.

        Args:
            provider: The provider to add.
        """
        self._providers[provider.id] = provider
        self._loaded = True

    def providers(self) -> tuple[TokenizerProvider, ...]:
        """Return every registered provider, ordered by id."""
        self._ensure_loaded()
        return tuple(self._providers[k] for k in sorted(self._providers))

    def aliases(self) -> tuple[str, ...]:
        """Return every bare id that resolves without a provider prefix."""
        names: set[str] = set()
        for provider in self.providers():
            names.update(provider.aliases())
        return tuple(sorted(names))

    def get(self, tokenizer_id: str) -> Tokenizer:
        """Resolve a tokenizer id to a tokenizer.

        Resolution does not load the vocabulary — that happens on first count,
        so a tokenizer that will fail to download still resolves here and fails
        with a precise error at the point of use.

        Args:
            tokenizer_id: ``provider:spec`` or a bare alias.

        Returns:
            The tokenizer, cached for the life of the registry.

        Raises:
            TokenizerNotFound: If no provider serves the id.
            TokenizerUnavailable: If a provider serves it but cannot build it.
        """
        self._ensure_loaded()
        cached = self._cache.get(tokenizer_id)
        if cached is not None:
            return cached

        tokenizer = self._resolve(tokenizer_id)
        self._cache[tokenizer_id] = tokenizer
        return tokenizer

    def _resolve(self, tokenizer_id: str) -> Tokenizer:
        """Find the provider for an id and have it build the tokenizer.

        Args:
            tokenizer_id: ``provider:spec`` or a bare alias.

        Returns:
            The tokenizer.

        Raises:
            TokenizerNotFound: If no provider serves the id.
        """
        if ":" in tokenizer_id:
            provider_id, _, spec = tokenizer_id.partition(":")
            provider = self._providers.get(provider_id)
            if provider is None:
                raise TokenizerNotFound(tokenizer_id, self._known())
            return provider.create(spec)

        for provider in self.providers():
            if tokenizer_id in provider.aliases():
                return provider.create(tokenizer_id)
        raise TokenizerNotFound(tokenizer_id, self._known())

    def _known(self) -> tuple[str, ...]:
        """Return every resolvable id, for error messages."""
        names = list(self.aliases())
        names.extend(f"{p.id}:<spec>" for p in self.providers() if not p.aliases())
        return tuple(names)


_DEFAULT: TokenizerRegistry | None = None


def default_tokenizer_registry() -> TokenizerRegistry:
    """Return the process-wide tokenizer registry, building it on first call.

    Returns:
        The shared registry.
    """
    global _DEFAULT  # one deliberate process-wide cache
    if _DEFAULT is None:
        _DEFAULT = TokenizerRegistry()
    return _DEFAULT


def reset_default_tokenizer_registry() -> None:
    """Discard the process-wide tokenizer registry. Only useful in tests."""
    global _DEFAULT  # one deliberate process-wide cache
    _DEFAULT = None
