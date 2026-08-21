"""HuggingFace-backed tokenizers, for measuring against open-weight models.

Reached as ``hf:<model>``, e.g. ``hf:meta-llama/Llama-3.1-8B``. The ``tokenizers``
package is not part of the core install — counting Llama tokens is not something
every user needs, and the core tier stays light — so this adapter degrades to
"unavailable, here is the install command" when it is absent.

Like tiktoken, the vocabulary is downloaded on first use, from
``huggingface.co``. Where that host is unreachable the tokenizer is unavailable
and says so; it never approximates.

License: ``tokenizers`` and ``huggingface_hub`` are Apache-2.0
(``docs/research/RESEARCH.md``, Category 7).
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any, Final

from tokenmill.core.errors import NetworkRequired, TokenizerNotFound, TokenizerUnavailable
from tokenmill.tokens.base import TokenizerInfo

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tokenmill.tokens.base import Tokenizer

__all__ = ["HuggingFaceProvider", "HuggingFaceTokenizer"]

_INSTALL_HINT: Final = 'pip install "tokenmill[tokenizers]"'
_OFFLINE_HINT: Final = (
    "HuggingFace tokenizers are downloaded on first use; set HF_HOME to a warmed "
    "cache directory, or HF_HUB_OFFLINE=1 once it is populated, to work offline"
)


class HuggingFaceTokenizer:
    """One HuggingFace tokenizer, loaded lazily.

    Attributes:
        info: What this tokenizer is.
    """

    def __init__(self, model_id: str) -> None:
        """Prepare a tokenizer for a model without loading it.

        Args:
            model_id: A HuggingFace repository id, e.g. ``bert-base-uncased``.
        """
        self._model_id = model_id
        self._tokenizer: Any | None = None
        self.info = TokenizerInfo(
            id=f"hf:{model_id}",
            provider=HuggingFaceProvider.id,
            description=f"the tokenizer published with {model_id}",
            counts="model tokens",
            is_model_tokenizer=True,
            requires_network=True,
        )

    def _load(self) -> Any:
        """Load and cache the HuggingFace tokenizer.

        Returns:
            The ``tokenizers.Tokenizer``.

        Raises:
            TokenizerUnavailable: If the ``tokenizers`` package is absent.
            NetworkRequired: If the vocabulary cannot be fetched.
        """
        if self._tokenizer is not None:
            return self._tokenizer
        try:
            from tokenizers import Tokenizer as HFTokenizer
        except ImportError as exc:
            raise TokenizerUnavailable(
                self.info.id, "the `tokenizers` package is not installed", hint=_INSTALL_HINT
            ) from exc

        try:
            self._tokenizer = HFTokenizer.from_pretrained(self._model_id)
        except Exception as exc:
            raise NetworkRequired(
                f"could not load the tokenizer for {self._model_id!r}: {type(exc).__name__}: {exc}",
                hint=_OFFLINE_HINT,
            ) from exc
        return self._tokenizer

    def count(self, text: str) -> int:
        """Return the number of tokens in ``text``.

        Args:
            text: The text to measure.

        Returns:
            The token count.

        Raises:
            TokenizerUnavailable: If the ``tokenizers`` package is absent.
            NetworkRequired: If the vocabulary cannot be fetched.
        """
        return len(self.encode(text))

    def encode(self, text: str) -> list[int]:
        """Return the token ids for ``text``.

        Special tokens are not added: we are measuring a document, not building
        a model input, and a ``[CLS]``/``[SEP]`` pair would make every count two
        too high.

        Args:
            text: The text to encode.

        Returns:
            The token ids.

        Raises:
            TokenizerUnavailable: If the ``tokenizers`` package is absent.
            NetworkRequired: If the vocabulary cannot be fetched.
        """
        encoding = self._load().encode(text, add_special_tokens=False)
        ids: list[int] = list(encoding.ids)
        return ids


class HuggingFaceProvider:
    """Serves any tokenizer published on the HuggingFace Hub.

    Attributes:
        id: The provider id, ``hf``.
    """

    id = "hf"

    def aliases(self) -> tuple[str, ...]:
        """Return no aliases.

        The set of HuggingFace models is open-ended, so there is nothing to
        enumerate: this provider is reachable only as ``hf:<model>``.

        Returns:
            An empty tuple.
        """
        return ()

    def available(self) -> bool:
        """Return whether the ``tokenizers`` package is importable.

        Returns:
            True when it is installed.
        """
        return importlib.util.find_spec("tokenizers") is not None

    def create(self, spec: str) -> Tokenizer:
        """Build a tokenizer for a HuggingFace model.

        Args:
            spec: The repository id, e.g. ``bert-base-uncased``.

        Returns:
            The tokenizer, with its vocabulary not yet loaded.

        Raises:
            TokenizerNotFound: If ``spec`` is empty.
        """
        if not spec:
            raise TokenizerNotFound("hf:", ("hf:<model-id>",))
        return HuggingFaceTokenizer(spec)
