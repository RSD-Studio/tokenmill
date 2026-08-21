"""Test doubles shared across the unit tests.

The important one is :class:`WordPieceTokenizer`. tokenmill's real tokenizers all
download a vocabulary on first use, so on a machine without access to
``openaipublic.blob.core.windows.net`` or ``huggingface.co`` they cannot run at
all. Testing the measurement layer against them would mean testing nothing.

So the arithmetic — ``TokenMeter``, per-stage accounting, the registry, the
before/after maths — is tested against a tokenizer whose output is written down
here and hand-checkable. Tests that need a *real* BPE tokenizer are marked
``network`` and skipped by default; see ``tests/unit/test_tokens_network.py``.
"""

from __future__ import annotations

import re
from typing import Final

from tokenmill.core.errors import NetworkRequired, TokenizerNotFound
from tokenmill.core.models import (
    Availability,
    BackendInfo,
    ConvertOptions,
    Domain,
    LicenseTier,
    OutputFormat,
    Source,
)
from tokenmill.core.protocol import BaseConverter, ConversionContext
from tokenmill.tokens.base import Tokenizer, TokenizerInfo

#: Splits text into words, punctuation marks and whitespace runs. Chosen because
#: a human can count the pieces of any short string by eye, which is what makes
#: the golden vectors in test_tokens.py verifiable rather than circular.
_PIECE_RE: Final = re.compile(r"\w+|\s+|[^\w\s]")


class WordPieceTokenizer:
    """A deterministic, offline stand-in for a real tokenizer."""

    def __init__(self, tokenizer_id: str = "fake-wordpiece") -> None:
        """Initialise the tokenizer.

        Args:
            tokenizer_id: The id counts from this tokenizer will carry.
        """
        self.info = TokenizerInfo(
            id=tokenizer_id,
            provider="test",
            description="deterministic word/punctuation/whitespace splitter",
            counts="pieces",
            is_model_tokenizer=False,
            requires_network=False,
        )

    def count(self, text: str) -> int:
        """Return the number of pieces in ``text``."""
        return len(self.encode(text))

    def encode(self, text: str) -> list[int]:
        """Return one id per piece, derived from the piece's hash."""
        return [hash(piece) & 0xFFFF for piece in _PIECE_RE.findall(text)]


class UnavailableTokenizer:
    """A tokenizer that always fails the way an air-gapped tiktoken does."""

    def __init__(self, tokenizer_id: str = "needs-network") -> None:
        """Initialise the tokenizer.

        Args:
            tokenizer_id: The id it reports.
        """
        self.info = TokenizerInfo(
            id=tokenizer_id,
            provider="test",
            description="always fails to load, like a BPE with no network",
            requires_network=True,
        )

    def count(self, text: str) -> int:
        """Raise, as a tokenizer with no reachable vocabulary would.

        Args:
            text: Ignored.

        Raises:
            NetworkRequired: Always.
        """
        del text
        raise NetworkRequired("no route to the vocabulary host", hint="connect to a network")

    def encode(self, text: str) -> list[int]:
        """Raise, as a tokenizer with no reachable vocabulary would.

        Args:
            text: Ignored.

        Raises:
            NetworkRequired: Always.
        """
        return [0] * self.count(text)


class StaticProvider:
    """A tokenizer provider serving one fixed tokenizer."""

    def __init__(self, provider_id: str, tokenizer: Tokenizer) -> None:
        """Initialise the provider.

        Args:
            provider_id: The provider's id.
            tokenizer: The tokenizer it hands out.
        """
        self.id = provider_id
        self._tokenizer = tokenizer

    def aliases(self) -> tuple[str, ...]:
        """Return the single id this provider claims."""
        return (self._tokenizer.info.id,)

    def available(self) -> bool:
        """Return True; this provider needs nothing."""
        return True

    def create(self, spec: str) -> Tokenizer:
        """Return the fixed tokenizer.

        Args:
            spec: Must match the tokenizer's id.

        Returns:
            The tokenizer.

        Raises:
            TokenizerNotFound: If ``spec`` does not match.
        """
        if spec != self._tokenizer.info.id:
            raise TokenizerNotFound(spec, self.aliases())
        return self._tokenizer


def make_info(backend_id: str, **overrides: object) -> BackendInfo:
    """Build a plausible :class:`BackendInfo` for a fake backend.

    Args:
        backend_id: The backend's id.
        **overrides: Fields to override.

    Returns:
        The metadata.
    """
    defaults: dict[str, object] = {
        "id": backend_id,
        "name": backend_id,
        "description": "a test backend",
        "domains": (Domain.TEXT,),
        "input_formats": ("txt",),
        "output_formats": (OutputFormat.MARKDOWN,),
        "license": "MIT",
        "license_tier": LicenseTier.PERMISSIVE,
        "upstream_url": "https://example.invalid",
    }
    defaults.update(overrides)
    return BackendInfo(**defaults)  # type: ignore[arg-type]


class EchoConverter(BaseConverter):
    """A backend that returns a fixed string, or the source's own text."""

    def __init__(
        self,
        backend_id: str = "echo",
        *,
        output: str | None = None,
        availability: Availability | None = None,
        warn: str | None = None,
        **info_overrides: object,
    ) -> None:
        """Initialise the backend.

        Args:
            backend_id: The backend's id.
            output: Text to return instead of the source's own.
            availability: What :meth:`_probe` should report.
            warn: A warning to attach to every conversion.
            **info_overrides: Fields to override on the ``BackendInfo``.
        """
        super().__init__()
        self.info = make_info(backend_id, **info_overrides)
        self._output = output
        self._declared = availability if availability is not None else Availability.present()
        self._warn = warn
        self.calls = 0

    def _probe(self) -> Availability:
        """Return the availability this double was constructed with."""
        self.calls += 1
        return self._declared

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Return the configured output, or the source's text.

        Args:
            source: The input.
            options: Unused.
            context: Collects the optional warning.

        Returns:
            The text.
        """
        del options
        if self._warn is not None:
            context.warn(self._warn)
        context.note("double", True)
        return self._output if self._output is not None else source.read_text()


class ExplodingConverter(BaseConverter):
    """A backend whose ``_convert`` raises something outside the taxonomy."""

    def __init__(self, backend_id: str = "exploding") -> None:
        """Initialise the backend.

        Args:
            backend_id: The backend's id.
        """
        super().__init__()
        self.info = make_info(backend_id)

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Raise a plain exception.

        Args:
            source: Unused.
            options: Unused.
            context: Unused.

        Raises:
            RuntimeError: Always.
        """
        del source, options, context
        msg = "this backend has a bug"
        raise RuntimeError(msg)
