"""tiktoken-backed tokenizers — the counts that match OpenAI models.

This is the default measurement path. ``o200k_base`` is what GPT-4o and o-series
models tokenise with, ``cl100k_base`` what GPT-4 and GPT-3.5-turbo use.

**tiktoken downloads its vocabulary on first use**, from
``openaipublic.blob.core.windows.net``. On a machine that cannot reach that host
the tokenizer is genuinely unavailable, and this adapter says so — it raises
:class:`~tokenmill.core.errors.NetworkRequired` with the offline cache
instructions rather than guessing a count. An estimated token count presented as
a measured one would be the single most damaging thing this project could ship.

To use it offline, pre-populate tiktoken's cache on a networked machine and
point ``TIKTOKEN_CACHE_DIR`` at the result.

License: tiktoken is MIT (``docs/research/RESEARCH.md``, Category 7).
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any, Final

from tokenmill.core.errors import NetworkRequired, TokenizerNotFound, TokenizerUnavailable
from tokenmill.tokens.base import TokenizerInfo

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tokenmill.tokens.base import Tokenizer

__all__ = ["TiktokenProvider", "TiktokenTokenizer"]

#: Encodings we advertise, with the model families they belong to. tiktoken
#: knows others; these are the ones worth putting in front of a user.
ENCODINGS: Final[dict[str, str]] = {
    "o200k_base": "GPT-4o, GPT-4.1 and o-series models",
    "cl100k_base": "GPT-4, GPT-3.5-turbo, text-embedding-3",
    "p50k_base": "Codex and older text-davinci models",
    "r50k_base": "GPT-3 (davinci, curie, babbage, ada)",
}

_OFFLINE_HINT: Final = (
    "tiktoken downloads its vocabulary on first use; set TIKTOKEN_CACHE_DIR to a "
    "directory populated on a networked machine to use it offline"
)


class TiktokenTokenizer:
    """One tiktoken encoding, loaded lazily.

    Attributes:
        info: What this tokenizer is.
    """

    def __init__(self, encoding_name: str) -> None:
        """Prepare a tokenizer for an encoding without loading it.

        The vocabulary is not fetched until the first :meth:`count` or
        :meth:`encode`, so constructing one is free and cannot fail.

        Args:
            encoding_name: A tiktoken encoding name, e.g. ``o200k_base``.
        """
        self._encoding_name = encoding_name
        self._encoding: Any | None = None
        self.info = TokenizerInfo(
            id=encoding_name,
            provider=TiktokenProvider.id,
            description=ENCODINGS.get(encoding_name, "a tiktoken BPE encoding"),
            counts="BPE tokens",
            is_model_tokenizer=True,
            requires_network=True,
        )

    def _load(self) -> Any:
        """Load and cache the tiktoken encoding.

        Returns:
            The ``tiktoken.Encoding``.

        Raises:
            TokenizerUnavailable: If tiktoken is not installed.
            NetworkRequired: If the vocabulary cannot be fetched.
        """
        if self._encoding is not None:
            return self._encoding
        try:
            import tiktoken
        except ImportError as exc:  # pragma: no cover - tiktoken is a core dependency
            raise TokenizerUnavailable(
                self._encoding_name, "tiktoken is not installed", hint="pip install tiktoken"
            ) from exc

        try:
            self._encoding = tiktoken.get_encoding(self._encoding_name)
        except ValueError as exc:
            raise TokenizerNotFound(self._encoding_name, tuple(ENCODINGS)) from exc
        except Exception as exc:
            # tiktoken raises whatever its HTTP layer raises. Any failure to
            # obtain the vocabulary means we cannot count, and the honest answer
            # is to say so rather than to approximate.
            raise NetworkRequired(
                f"could not load the {self._encoding_name!r} vocabulary: "
                f"{type(exc).__name__}: {exc}",
                hint=_OFFLINE_HINT,
            ) from exc
        return self._encoding

    def count(self, text: str) -> int:
        """Return the number of BPE tokens in ``text``.

        Args:
            text: The text to measure.

        Returns:
            The token count.

        Raises:
            TokenizerUnavailable: If tiktoken is not installed.
            NetworkRequired: If the vocabulary cannot be fetched.
        """
        return len(self.encode(text))

    def encode(self, text: str) -> list[int]:
        """Return the BPE token ids for ``text``.

        Special tokens in the input are encoded as ordinary text rather than
        being treated as control tokens: the input is a document, not a prompt
        we control, and letting ``<|endoftext|>`` in a converted file change the
        tokenisation would make counts depend on document content in a way users
        would not expect.

        Args:
            text: The text to encode.

        Returns:
            The token ids.

        Raises:
            TokenizerUnavailable: If tiktoken is not installed.
            NetworkRequired: If the vocabulary cannot be fetched.
        """
        encoding = self._load()
        ids: list[int] = encoding.encode(text, disallowed_special=())
        return ids


class TiktokenProvider:
    """Serves the tiktoken encodings.

    Attributes:
        id: The provider id, ``tiktoken``.
    """

    id = "tiktoken"

    def aliases(self) -> tuple[str, ...]:
        """Return the encoding names usable without the ``tiktoken:`` prefix."""
        return tuple(ENCODINGS)

    def available(self) -> bool:
        """Return whether the tiktoken package is importable.

        Checks for the module without importing it — importing tiktoken is not
        free, and this is called for every ``tokenmill tokenizers`` listing.

        Returns:
            True when tiktoken is installed.
        """
        return importlib.util.find_spec("tiktoken") is not None

    def create(self, spec: str) -> Tokenizer:
        """Build a tokenizer for a tiktoken encoding.

        Args:
            spec: The encoding name, e.g. ``o200k_base``.

        Returns:
            The tokenizer, with its vocabulary not yet loaded.

        Raises:
            TokenizerNotFound: If ``spec`` is not a known encoding name.
        """
        if spec not in ENCODINGS:
            raise TokenizerNotFound(spec, tuple(ENCODINGS))
        return TiktokenTokenizer(spec)
