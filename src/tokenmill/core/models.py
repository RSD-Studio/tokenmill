"""The tokenmill data model.

These are the types every other module speaks in, and they are the architecture
contract from ``docs/DEVELOPMENT_PLAN.md`` §1.1. Changing any of them is a
breaking change requiring owner sign-off.

Everything here is a frozen dataclass. Dataclasses rather than pydantic models
so that ``import tokenmill`` pulls in nothing but the standard library — see
``docs/ARCHITECTURE.md`` for the reasoning. Frozen because a
:class:`ConversionResult` is a record of something that already happened and
must carry enough provenance to reproduce it; mutating one after the fact would
make the provenance a lie.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

__all__ = [
    "Availability",
    "AvailabilityStatus",
    "BackendAttempt",
    "BackendInfo",
    "ConversionResult",
    "ConvertOptions",
    "Domain",
    "ImageHandling",
    "IsolationMode",
    "LicenseTier",
    "LinkHandling",
    "OutputFormat",
    "Source",
    "SourceKind",
    "StageCount",
    "TokenCount",
    "freeze_metadata",
]

_EMPTY_METADATA: Final[Mapping[str, Any]] = MappingProxyType({})


class Domain(StrEnum):
    """The four input domains tokenmill covers."""

    DOCUMENTS = "documents"
    WEB = "web"
    REPO = "repo"
    TEXT = "text"


class LicenseTier(StrEnum):
    """How a backend's licence constrains the way we may invoke it.

    This is the machine-readable half of the licence policy in
    ``CONTRIBUTING.md``. The registry refuses to run a backend whose tier
    contradicts its isolation mode.
    """

    #: MIT / Apache / BSD and friends. May be imported into our process.
    PERMISSIVE = "permissive"
    #: AGPL / GPL. Must be invoked out of process; never imported.
    COPYLEFT = "copyleft"
    #: Weights or code under a non-commercial licence. Excluded by default.
    NON_COMMERCIAL = "non-commercial"


class IsolationMode(StrEnum):
    """How a backend is invoked."""

    #: Imported and called directly. Only legal for permissive licences.
    IN_PROCESS = "in-process"
    #: Executed as a child process; we exchange files and stdout.
    SUBPROCESS = "subprocess"
    #: Reached over HTTP, typically a container.
    SERVICE = "service"


class OutputFormat(StrEnum):
    """Serialisations tokenmill can emit.

    Phase 1 emits Markdown and plain text only. CSV, TOON and JSON encoders
    arrive in Phase 5; they are deliberately absent here rather than stubbed.
    """

    MARKDOWN = "markdown"
    TEXT = "text"


class SourceKind(StrEnum):
    """What the user actually handed us."""

    FILE = "file"
    BYTES = "bytes"
    URL = "url"
    REPO = "repo"
    TEXT = "text"


class AvailabilityStatus(StrEnum):
    """Why a backend can or cannot run."""

    PRESENT = "present"
    MISSING_DEPENDENCY = "missing-dependency"
    MISSING_BINARY = "missing-binary"
    UNSUPPORTED = "unsupported"
    BROKEN = "broken"


class ImageHandling(StrEnum):
    """What the ``links`` post-processor does with Markdown images."""

    KEEP = "keep"
    ALT = "alt"
    STRIP = "strip"


class LinkHandling(StrEnum):
    """What the ``links`` post-processor does with Markdown links."""

    KEEP = "keep"
    STRIP = "strip"


@dataclass(frozen=True, slots=True)
class Availability:
    """The result of probing whether a backend can run.

    Probes never raise and never do real work — they check for an import, a
    binary on ``PATH``, or a platform. A backend that cannot run is greyed out
    with an install hint; it is never an ``ImportError`` at startup.

    Attributes:
        status: Why the backend can or cannot run.
        missing: Dependency or binary names that were looked for and not found.
        reason: Free text explaining an ``UNSUPPORTED`` or ``BROKEN`` status.
        hint: The command that would fix it, when one exists.
    """

    status: AvailabilityStatus
    missing: tuple[str, ...] = ()
    reason: str | None = None
    hint: str | None = None

    def __bool__(self) -> bool:
        """Return whether the backend can run."""
        return self.status is AvailabilityStatus.PRESENT

    @property
    def is_available(self) -> bool:
        """Whether the backend can run. Explicit alias for :meth:`__bool__`."""
        return bool(self)

    def describe(self) -> str:
        """Return a one-line explanation suitable for a CLI or GUI listing."""
        if self.status is AvailabilityStatus.PRESENT:
            return "available"
        if self.status is AvailabilityStatus.MISSING_DEPENDENCY:
            return f"missing dependency: {', '.join(self.missing)}"
        if self.status is AvailabilityStatus.MISSING_BINARY:
            return f"missing binary: {', '.join(self.missing)}"
        return self.reason or self.status.value

    @classmethod
    def present(cls) -> Availability:
        """Return an availability meaning "this backend can run"."""
        return cls(AvailabilityStatus.PRESENT)

    @classmethod
    def missing_dependency(cls, *names: str, hint: str | None = None) -> Availability:
        """Return an availability for one or more absent Python packages.

        Args:
            *names: The importable names that were not found.
            hint: An install command; defaults to ``pip install <names>``.

        Returns:
            The corresponding availability.
        """
        return cls(
            AvailabilityStatus.MISSING_DEPENDENCY,
            missing=names,
            hint=hint or f"pip install {' '.join(names)}",
        )

    @classmethod
    def missing_binary(cls, name: str, *, hint: str | None = None) -> Availability:
        """Return an availability for an executable that is not on ``PATH``.

        Args:
            name: The executable that was looked for.
            hint: How to install it.

        Returns:
            The corresponding availability.
        """
        return cls(AvailabilityStatus.MISSING_BINARY, missing=(name,), hint=hint)

    @classmethod
    def unsupported(cls, reason: str, *, hint: str | None = None) -> Availability:
        """Return an availability for a backend that cannot run here at all.

        Args:
            reason: Why not — wrong platform, no GPU, and so on.
            hint: An optional next step.

        Returns:
            The corresponding availability.
        """
        return cls(AvailabilityStatus.UNSUPPORTED, reason=reason, hint=hint)

    @classmethod
    def broken(cls, reason: str) -> Availability:
        """Return an availability for a backend that failed to load.

        This is what a third-party plugin whose entry point raises on import
        degrades to. It is reported like any other unavailable backend rather
        than being allowed to take the process down with it.

        Args:
            reason: The exception text from the failed load.

        Returns:
            The corresponding availability.
        """
        return cls(
            AvailabilityStatus.BROKEN,
            reason=reason,
            hint="this backend's plugin failed to load; report it to its author",
        )


@dataclass(frozen=True, slots=True)
class BackendInfo:
    """Static metadata describing one backend.

    Every field here is visible to the user: the CLI's ``backends`` command
    prints the licence and availability, and the GUI will badge them. Licence is
    not documentation — :attr:`license_tier` and :attr:`isolation` together are
    what the registry enforces.

    Attributes:
        id: Stable identifier, used as the ``--backend`` value and the entry
            point name. Lowercase, underscore-separated.
        name: Human-readable display name.
        description: One sentence on what it is good at.
        domains: Which input domains it serves.
        input_formats: Lowercase extensions without the dot, plus the pseudo
            formats ``url``, ``repo`` and ``text``.
        output_formats: What it can emit.
        license: The SPDX identifier of the wrapped tool's licence.
        license_tier: How that licence constrains invocation.
        isolation: How the backend is invoked.
        install_extra: The ``pip install tokenmill[...]`` extra that supplies
            it, or ``None`` when it is part of the core install.
        requires_gpu: Whether usable performance needs a GPU.
        requires_network: Whether it must reach the network to work.
        requires_binary: An executable that must be on ``PATH``, if any.
        upstream_url: Where the wrapped tool lives.
        priority: Auto-selection rank; higher wins. See
            :meth:`~tokenmill.core.registry.Registry.select`.
    """

    id: str
    name: str
    description: str
    domains: tuple[Domain, ...]
    input_formats: tuple[str, ...]
    license: str
    license_tier: LicenseTier
    upstream_url: str
    output_formats: tuple[OutputFormat, ...] = (OutputFormat.MARKDOWN,)
    isolation: IsolationMode = IsolationMode.IN_PROCESS
    install_extra: str | None = None
    requires_gpu: bool = False
    requires_network: bool = False
    requires_binary: str | None = None
    priority: int = 0

    def __post_init__(self) -> None:
        """Enforce the licence policy that the whole project rests on.

        Raises:
            ValueError: If a copyleft or non-commercial backend declares that it
                runs in-process. ``CONTRIBUTING.md`` rule 2 says AGPL/GPL tools
                are never imported, and this is where that becomes unarguable:
                a violating adapter cannot even be constructed.
        """
        if self.license_tier is not LicenseTier.PERMISSIVE and (
            self.isolation is IsolationMode.IN_PROCESS
        ):
            msg = (
                f"backend {self.id!r} declares licence tier {self.license_tier.value!r} "
                f"with isolation {self.isolation.value!r}; non-permissive backends must "
                f"run out of process (see CONTRIBUTING.md rule 2)"
            )
            raise ValueError(msg)

    def supports_format(self, extension: str) -> bool:
        """Return whether this backend claims the given input format.

        Args:
            extension: A lowercase extension without the dot, or one of the
                pseudo formats ``url`` / ``repo`` / ``text``.

        Returns:
            True when the format is claimed.
        """
        return extension.lower().lstrip(".") in self.input_formats


@dataclass(frozen=True, slots=True)
class Source:
    """What the user gave us to convert.

    Construct these with the classmethods rather than the initialiser: they set
    the kind and the display name consistently.

    Attributes:
        kind: Which of the five shapes this is.
        name: A short display name, used in output and error messages.
        path: The file or directory, for ``FILE`` and ``REPO`` sources.
        data: Raw bytes, for ``BYTES`` sources.
        url: The address, for ``URL`` sources.
        text: The literal text, for ``TEXT`` sources.
        media_type: An IANA media type when one is known.
    """

    kind: SourceKind
    name: str
    path: Path | None = None
    data: bytes | None = None
    url: str | None = None
    text: str | None = None
    media_type: str | None = None

    @classmethod
    def from_path(cls, path: str | Path, *, media_type: str | None = None) -> Source:
        """Build a file or repository source from a filesystem path.

        A directory becomes a ``REPO`` source, a file a ``FILE`` source. The
        path is resolved so that backends never see a relative path and
        ``..`` cannot escape into somewhere unexpected.

        Args:
            path: The file or directory.
            media_type: Overrides the type guessed from the extension.

        Returns:
            The source.

        Raises:
            FileNotFoundError: If the path does not exist.
        """
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            msg = f"no such file or directory: {resolved}"
            raise FileNotFoundError(msg)
        kind = SourceKind.REPO if resolved.is_dir() else SourceKind.FILE
        guessed = media_type
        if guessed is None and kind is SourceKind.FILE:
            guessed = mimetypes.guess_type(resolved.name)[0]
        return cls(kind=kind, name=resolved.name, path=resolved, media_type=guessed)

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str, media_type: str | None = None) -> Source:
        """Build a source from raw bytes already in memory.

        Args:
            data: The content.
            name: A display name, ideally with an extension so format detection
                works.
            media_type: An IANA media type when known.

        Returns:
            The source.
        """
        guessed = media_type or mimetypes.guess_type(name)[0]
        return cls(kind=SourceKind.BYTES, name=name, data=data, media_type=guessed)

    @classmethod
    def from_url(cls, url: str) -> Source:
        """Build a source from a URL.

        Args:
            url: An ``http`` or ``https`` address.

        Returns:
            The source.

        Raises:
            ValueError: If the scheme is not ``http`` or ``https``.
        """
        if not url.startswith(("http://", "https://")):
            msg = f"unsupported URL scheme: {url!r} (expected http:// or https://)"
            raise ValueError(msg)
        return cls(kind=SourceKind.URL, name=url, url=url, media_type="text/html")

    @classmethod
    def from_text(cls, text: str, *, name: str = "<text>") -> Source:
        """Build a source from a literal string.

        Args:
            text: The content.
            name: A display name.

        Returns:
            The source.
        """
        return cls(kind=SourceKind.TEXT, name=name, text=text, media_type="text/plain")

    @property
    def format(self) -> str:
        """Return the format token used to match backends.

        Returns:
            A lowercase extension without the dot for file and bytes sources,
            or the pseudo formats ``url``, ``repo`` and ``text``.
        """
        if self.kind is SourceKind.URL:
            return "url"
        if self.kind is SourceKind.REPO:
            return "repo"
        if self.kind is SourceKind.TEXT:
            return "text"
        return Path(self.name).suffix.lower().lstrip(".")

    def read_bytes(self) -> bytes:
        """Return the source's content as bytes.

        Returns:
            The bytes of a file, the literal bytes of a ``BYTES`` source, or the
            UTF-8 encoding of a ``TEXT`` source.

        Raises:
            ValueError: For sources that have no local content — a URL that has
                not been fetched, or a repository directory.
        """
        if self.data is not None:
            return self.data
        if self.text is not None:
            return self.text.encode("utf-8")
        if self.kind is SourceKind.FILE and self.path is not None:
            return self.path.read_bytes()
        msg = f"{self.kind.value} source {self.name!r} has no readable bytes"
        raise ValueError(msg)

    def read_text(self, encoding: str = "utf-8") -> str:
        """Return the source's content as text.

        Args:
            encoding: The encoding to decode with. Decoding is lenient —
                undecodable bytes are replaced rather than raising — because a
                converter should report a mangled character, not abort.

        Returns:
            The decoded text.

        Raises:
            ValueError: For sources that have no local content.
        """
        if self.text is not None:
            return self.text
        return self.read_bytes().decode(encoding, errors="replace")


@dataclass(frozen=True, slots=True)
class TokenCount:
    """A token count together with the tokenizer that produced it.

    Never pass a bare ``int`` around for a token count. "4,102 tokens" is not a
    fact until you say which tokenizer counted them: the same text is a
    different number under ``o200k_base`` than under ``cl100k_base``. Bundling
    the two makes it impossible to compare counts that are not comparable.

    Attributes:
        value: The number of tokens.
        tokenizer_id: The tokenizer that counted them.
    """

    value: int
    tokenizer_id: str

    def __str__(self) -> str:
        """Return the count with its tokenizer, e.g. ``4102 (o200k_base)``."""
        return f"{self.value} ({self.tokenizer_id})"


@dataclass(frozen=True, slots=True)
class StageCount:
    """The size of the text as it leaves one pipeline stage.

    Attributes:
        stage: The stage name — ``source``, ``convert``, or a post-processor id.
        characters: Length of the text in characters.
        tokens: The token count, or ``None`` when no tokenizer was available.
    """

    stage: str
    characters: int
    tokens: TokenCount | None = None


@dataclass(frozen=True, slots=True)
class ConvertOptions:
    """Everything that varies between one conversion and the next.

    Attributes:
        tokenizer: The tokenizer id to measure with.
        backend: Force a specific backend id instead of auto-selecting.
        output_format: What the pipeline should emit.
        post_processors: Post-processor ids to run, in order. ``None`` means the
            registry's default chain.
        image_handling: What the ``links`` post-processor does with images.
        link_handling: What the ``links`` post-processor does with links.
        allow_network: Whether backends may make network calls. Default-deny:
            converting a local file never reaches out.
        fallback: Whether auto-selection may try the next candidate backend
            when the preferred one fails. Never applies to an explicit
            :attr:`backend`, which must run or error.
        timeout_s: Wall-clock budget for a single conversion.
        max_bytes: Refuse sources larger than this, as a denial-of-service
            guard on hostile input.
        extra: Backend-specific options, ignored by backends that do not know
            them.
    """

    tokenizer: str = "o200k_base"
    backend: str | None = None
    output_format: OutputFormat = OutputFormat.MARKDOWN
    post_processors: tuple[str, ...] | None = None
    image_handling: ImageHandling = ImageHandling.KEEP
    link_handling: LinkHandling = LinkHandling.KEEP
    allow_network: bool = False
    fallback: bool = True
    timeout_s: float = 120.0
    max_bytes: int = 256 * 1024 * 1024
    extra: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_METADATA)

    def with_(self, **changes: Any) -> ConvertOptions:
        """Return a copy with the given fields replaced.

        Args:
            **changes: Field names and their new values.

        Returns:
            The updated copy; the original is untouched.
        """
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class BackendAttempt:
    """One backend's turn at converting a source.

    A conversion may try several backends: the preference map orders the
    candidates for the source's format, and auto-selection walks that order
    until one succeeds. Every attempt is recorded, successful or not, so the
    result says which backends were tried and why the earlier ones did not
    produce the text — otherwise a fallback is invisible and the measurement
    looks like it came from the backend the user expected.

    Attributes:
        backend_id: The backend that was tried.
        ok: Whether it produced the text in the result.
        error: The error it failed with, when it failed.
    """

    backend_id: str
    ok: bool
    error: str | None = None

    def describe(self) -> str:
        """Return a one-line summary suitable for a CLI or GUI listing."""
        if self.ok:
            return f"{self.backend_id}: converted"
        return f"{self.backend_id}: {self.error or 'failed'}"


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """The immutable record of one completed conversion.

    Carries enough provenance to reproduce it: which backend ran, which
    post-processors ran in which order, which tokenizer measured it, and how
    long it took.

    Attributes:
        text: The converted output.
        output_format: What :attr:`text` is.
        source_name: The display name of the input.
        backend_id: The backend that produced :attr:`text`.
        duration_s: Wall-clock seconds for the whole pipeline.
        tokens_before: Tokens in the raw input, or ``None`` if unmeasured.
        tokens_after: Tokens in :attr:`text`, or ``None`` if unmeasured.
        stages: Per-stage sizes, in execution order.
        post_processors: The post-processor ids that ran, in order.
        warnings: Non-fatal problems worth telling the user about.
        metadata: Backend-specific structured facts — page count, tables found.
        attempts: Every backend tried, in order, including the one that
            succeeded. Empty for a result assembled by a backend directly
            rather than by the pipeline.
    """

    text: str
    output_format: OutputFormat
    source_name: str
    backend_id: str
    duration_s: float
    tokens_before: TokenCount | None = None
    tokens_after: TokenCount | None = None
    stages: tuple[StageCount, ...] = ()
    post_processors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_METADATA)
    attempts: tuple[BackendAttempt, ...] = ()

    @property
    def token_delta(self) -> int | None:
        """Return tokens saved, or ``None`` if either end was not measured.

        Positive means the conversion made the text cheaper.
        """
        if self.tokens_before is None or self.tokens_after is None:
            return None
        return self.tokens_before.value - self.tokens_after.value

    @property
    def reduction_ratio(self) -> float | None:
        """Return the fraction of tokens removed, in ``[0, 1]`` when it shrank.

        Returns:
            ``None`` when either end was not measured or the input was empty.
            The value is negative if the conversion made the text *larger*,
            which is a real outcome and must not be clamped away.
        """
        if self.tokens_before is None or self.tokens_after is None:
            return None
        if self.tokens_before.value == 0:
            return None
        return (self.tokens_before.value - self.tokens_after.value) / self.tokens_before.value

    def with_warning(self, warning: str) -> ConversionResult:
        """Return a copy with one more warning appended.

        Args:
            warning: The message to add.

        Returns:
            The updated copy.
        """
        return replace(self, warnings=(*self.warnings, warning))


def freeze_metadata(values: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return a read-only view of ``values``.

    Used by backends assembling a :class:`ConversionResult`, so that metadata
    handed to an immutable result cannot be mutated behind its back.

    Args:
        values: The mapping to freeze, or ``None``.

    Returns:
        A read-only mapping; empty when ``values`` is ``None``.
    """
    if not values:
        return _EMPTY_METADATA
    return MappingProxyType(dict(values))
