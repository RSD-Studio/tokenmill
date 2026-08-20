r"""The tokenmill error taxonomy.

Every failure tokenmill can produce is one of these. The point of a closed
taxonomy is that a caller — the CLI today, the GUI in Phase 8 — can map each
class to one actionable message without ever showing a raw traceback.

The hierarchy is::

    TokenmillError
    ├── ConfigError
    ├── TokenizerError
    │   ├── TokenizerNotFound
    │   └── TokenizerUnavailable
    └── ConversionError
        ├── UnsupportedFormat
        ├── BackendUnavailable
        ├── BackendFailed
        ├── Timeout
        ├── CorruptSource
        └── NetworkRequired

``ConversionError`` and its six subclasses are the taxonomy named in
``docs/DEVELOPMENT_PLAN.md`` §1.4. ``TokenmillError``, ``ConfigError`` and
``TokenizerError`` sit alongside it so that a caller can catch everything this
library raises with one ``except`` without also swallowing unrelated
``Exception``\\s.

Every error carries a ``hint`` where a user can act on it. The CLI prints the
hint on its own line; the GUI will render it as the call to action.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = [
    "BackendFailed",
    "BackendUnavailable",
    "ConfigError",
    "ConversionError",
    "CorruptSource",
    "NetworkRequired",
    "Timeout",
    "TokenizerError",
    "TokenizerNotFound",
    "TokenizerUnavailable",
    "TokenmillError",
    "UnsupportedFormat",
]


class TokenmillError(Exception):
    """Base class for every error tokenmill raises deliberately.

    Attributes:
        message: The human-readable description of what went wrong.
        hint: An optional actionable next step, such as an install command.
    """

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        """Initialise the error.

        Args:
            message: What went wrong, in plain language.
            hint: An optional actionable next step shown to the user.
        """
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        """Return the message, with the hint appended when there is one."""
        if self.hint:
            return f"{self.message} ({self.hint})"
        return self.message


class ConfigError(TokenmillError):
    """Configuration was malformed or contradictory."""


class TokenizerError(TokenmillError):
    """Base class for tokenizer resolution and loading failures."""


class TokenizerNotFound(TokenizerError):
    """No registered provider recognises the requested tokenizer id.

    Attributes:
        tokenizer_id: The id that could not be resolved.
        known: The tokenizer ids that *are* available, for the error message.
    """

    def __init__(self, tokenizer_id: str, known: Sequence[str] = ()) -> None:
        """Initialise the error.

        Args:
            tokenizer_id: The unresolvable id.
            known: Ids that are registered, used to build the hint.
        """
        hint = f"known tokenizers: {', '.join(known)}" if known else None
        super().__init__(f"unknown tokenizer {tokenizer_id!r}", hint=hint)
        self.tokenizer_id = tokenizer_id
        self.known = tuple(known)


class TokenizerUnavailable(TokenizerError):
    """A tokenizer is registered but cannot be loaded right now.

    The usual causes are a missing optional dependency or, for BPE tokenizers
    that fetch their vocabulary on first use, no network access.

    Attributes:
        tokenizer_id: The tokenizer that could not be loaded.
    """

    def __init__(self, tokenizer_id: str, reason: str, *, hint: str | None = None) -> None:
        """Initialise the error.

        Args:
            tokenizer_id: The tokenizer that could not be loaded.
            reason: Why it could not be loaded.
            hint: An optional actionable next step.
        """
        super().__init__(f"tokenizer {tokenizer_id!r} is unavailable: {reason}", hint=hint)
        self.tokenizer_id = tokenizer_id
        self.reason = reason


class ConversionError(TokenmillError):
    """Base class for every failure to convert a source.

    A backend's ``convert()`` may raise only subclasses of this. Anything else
    escaping a backend is a bug in that backend, and ``BaseConverter`` wraps it
    in :class:`BackendFailed` so it still reaches the caller as a typed error.

    Attributes:
        backend_id: The backend that failed, when the failure is attributable.
    """

    def __init__(
        self, message: str, *, backend_id: str | None = None, hint: str | None = None
    ) -> None:
        """Initialise the error.

        Args:
            message: What went wrong, in plain language.
            backend_id: The backend the failure is attributable to, if any.
            hint: An optional actionable next step.
        """
        super().__init__(message, hint=hint)
        self.backend_id = backend_id


class UnsupportedFormat(ConversionError):
    """No available backend claims to handle this source."""


class BackendUnavailable(ConversionError):
    """The requested backend exists but cannot run.

    Raised when a backend's :meth:`~tokenmill.core.protocol.Converter.is_available`
    reports anything other than present — a missing dependency, a missing
    binary, or an unsupported platform.
    """


class BackendFailed(ConversionError):
    """The backend ran and failed.

    Attributes:
        stderr: Captured error output, for subprocess backends (Phase 7).
    """

    def __init__(
        self,
        message: str,
        *,
        backend_id: str | None = None,
        stderr: str | None = None,
        hint: str | None = None,
    ) -> None:
        """Initialise the error.

        Args:
            message: What went wrong.
            backend_id: The backend that failed.
            stderr: Captured standard error, for out-of-process backends.
            hint: An optional actionable next step.
        """
        super().__init__(message, backend_id=backend_id, hint=hint)
        self.stderr = stderr


class Timeout(ConversionError):
    """The conversion exceeded its time budget."""


class CorruptSource(ConversionError):
    """The input could not be parsed because it is damaged or truncated."""


class NetworkRequired(ConversionError):
    """The operation needs network access that is unavailable or disallowed.

    tokenmill is default-deny on the network: converting a local file never
    reaches out. This is raised when something genuinely needs the network — a
    URL fetch with fetching disabled, or a tokenizer whose vocabulary has to be
    downloaded on first use.
    """
