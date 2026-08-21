"""The tokenizer contract.

A tokenizer here is anything that can turn text into a count of units, paired
with an id that says what those units *are*. The id is not decoration: a count
without its tokenizer is not a fact, which is why
:class:`~tokenmill.core.models.TokenCount` refuses to exist without one.

Providers, not tokenizers, are what get registered. One provider serves a family
of related tokenizers — the tiktoken provider serves ``o200k_base``,
``cl100k_base`` and the rest — so the registry does not need an entry point per
encoding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["Tokenizer", "TokenizerInfo", "TokenizerProvider"]


@dataclass(frozen=True, slots=True)
class TokenizerInfo:
    """What a tokenizer is and what it costs to use.

    Attributes:
        id: The canonical id, e.g. ``o200k_base``. This is what appears in every
            :class:`~tokenmill.core.models.TokenCount` it produces.
        provider: The provider that created it, e.g. ``tiktoken``.
        description: One line on what it is and which models use it.
        counts: The unit being counted, in words — ``"BPE tokens"``,
            ``"UTF-8 bytes"``. Printed by the CLI so a user is never left
            guessing whether a number means model tokens.
        is_model_tokenizer: Whether this counts the tokens a real model would
            bill for. False for measurement units that are useful but are not a
            model's tokenizer; the CLI labels those explicitly.
        requires_network: Whether first use may need to download a vocabulary.
    """

    id: str
    provider: str
    description: str
    counts: str = "tokens"
    is_model_tokenizer: bool = True
    requires_network: bool = False


@runtime_checkable
class Tokenizer(Protocol):
    """Something that can count the tokens in a string.

    Attributes:
        info: What this tokenizer is.
    """

    info: TokenizerInfo

    def count(self, text: str) -> int:
        """Return the number of tokens in ``text``.

        Args:
            text: The text to measure.

        Returns:
            The token count. Must be 0 for the empty string, and must be
            deterministic: the same text always yields the same number.
        """
        ...

    def encode(self, text: str) -> list[int]:
        """Return the token ids for ``text``.

        Args:
            text: The text to encode.

        Returns:
            The token ids. ``len(encode(t)) == count(t)`` must hold.
        """
        ...


@runtime_checkable
class TokenizerProvider(Protocol):
    """Creates tokenizers for a family of related ids.

    Attributes:
        id: The provider's own id, used as the ``provider:spec`` prefix.
    """

    id: str

    def aliases(self) -> tuple[str, ...]:
        """Return ids this provider answers to without its prefix.

        ``o200k_base`` resolves without the user writing ``tiktoken:``. A
        provider that serves an open-ended set — any HuggingFace model name —
        returns an empty tuple and is reachable only through its prefix.

        Returns:
            The bare ids this provider claims.
        """
        ...

    def create(self, spec: str) -> Tokenizer:
        """Build a tokenizer.

        Args:
            spec: The part after the ``provider:`` prefix, or a bare alias.

        Returns:
            The tokenizer.

        Raises:
            TokenizerUnavailable: If it cannot be loaded — a missing optional
                dependency, or a vocabulary that has to be downloaded and
                cannot be.
            TokenizerNotFound: If this provider does not serve ``spec``.
        """
        ...
