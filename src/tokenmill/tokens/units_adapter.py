"""A download-free measurement unit: UTF-8 bytes.

Every other tokenizer tokenmill offers has to fetch a vocabulary before it can
count anything. On an air-gapped machine that leaves a user with a converter and
no measurement at all, which is most of the point of the tool.

``bytes`` fills that gap honestly. It counts UTF-8 bytes — a fact about the
text, exact and deterministic, needing nothing but the standard library. It is
**not** a model's tokenizer and does not pretend to be: its
:attr:`~tokenmill.tokens.base.TokenizerInfo.is_model_tokenizer` is ``False``, its
unit is spelled out as ``UTF-8 bytes``, and the CLI prints a warning whenever a
count comes from it.

Use it to see whether a conversion or a post-processor made the text smaller.
Do not use it to predict what a model will bill you, and do not put a number it
produced in a document without saying it is bytes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from tokenmill.core.errors import TokenizerNotFound
from tokenmill.tokens.base import TokenizerInfo

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tokenmill.tokens.base import Tokenizer

__all__ = ["BytesTokenizer", "UnitsProvider"]

_ID: Final = "bytes"


class BytesTokenizer:
    """Counts UTF-8 bytes.

    Attributes:
        info: What this tokenizer is.
    """

    def __init__(self) -> None:
        """Initialise the tokenizer. Never fails and never touches the network."""
        self.info = TokenizerInfo(
            id=_ID,
            provider=UnitsProvider.id,
            description="UTF-8 bytes; a download-free size measure, not a model tokenizer",
            counts="UTF-8 bytes",
            is_model_tokenizer=False,
            requires_network=False,
        )

    def count(self, text: str) -> int:
        """Return the number of UTF-8 bytes in ``text``.

        Args:
            text: The text to measure.

        Returns:
            The byte count.
        """
        return len(text.encode("utf-8"))

    def encode(self, text: str) -> list[int]:
        """Return the UTF-8 byte values of ``text``.

        Args:
            text: The text to encode.

        Returns:
            One integer in ``0..255`` per byte.
        """
        return list(text.encode("utf-8"))


class UnitsProvider:
    """Serves the download-free measurement units.

    Attributes:
        id: The provider id, ``units``.
    """

    id = "units"

    def aliases(self) -> tuple[str, ...]:
        """Return the unit ids usable without the ``units:`` prefix."""
        return (_ID,)

    def available(self) -> bool:
        """Return True; this provider needs nothing at all."""
        return True

    def create(self, spec: str) -> Tokenizer:
        """Build a unit counter.

        Args:
            spec: Must be ``bytes``.

        Returns:
            The tokenizer.

        Raises:
            TokenizerNotFound: If ``spec`` is anything else.
        """
        if spec != _ID:
            raise TokenizerNotFound(spec, (_ID,))
        return BytesTokenizer()
