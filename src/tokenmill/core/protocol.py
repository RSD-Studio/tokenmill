"""The backend contract: the ``Converter`` protocol and a base implementation.

The protocol is deliberately three methods wide. Every hook we might want later
— streaming, progress, batching — is a hook nobody needs yet, and a protocol is
the one thing in this codebase that is expensive to change once third parties
implement it.

:class:`BaseConverter` is where the shared behaviour lives so that an adapter
author writes only the part that is actually specific to their tool: timing,
availability caching, warning collection, size limits, result assembly and the
guarantee that only :class:`~tokenmill.core.errors.ConversionError` subclasses
escape ``convert()``.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from tokenmill.core.errors import (
    BackendFailed,
    BackendUnavailable,
    ConversionError,
    CorruptSource,
    UnsupportedFormat,
)
from tokenmill.core.models import (
    Availability,
    BackendInfo,
    ConversionResult,
    ConvertOptions,
    OutputFormat,
    Source,
    freeze_metadata,
)

__all__ = ["BaseConverter", "ConversionContext", "Converter"]

_log = logging.getLogger(__name__)


@runtime_checkable
class Converter(Protocol):
    """What every backend must provide.

    Implementations are usually written by subclassing :class:`BaseConverter`,
    but the protocol is what the registry and the pipeline actually depend on,
    so a backend may implement it directly.

    Attributes:
        info: Static metadata about this backend.
    """

    info: BackendInfo

    def is_available(self) -> Availability:
        """Report whether this backend can run right now.

        Must never raise and must be cheap — an import probe, a ``PATH``
        lookup, a platform check. The registry calls this to decide what to
        offer, and the CLI calls it for every backend on every listing, so the
        result is expected to be cached per process.

        Returns:
            Why the backend can or cannot run.
        """
        ...

    def supports(self, source: Source) -> bool:
        """Report whether this backend claims to handle the given source.

        This is about format, not availability — a backend supports PDFs
        whether or not its dependency is installed.

        Args:
            source: The input under consideration.

        Returns:
            True when the backend claims the source's format.
        """
        ...

    def convert(self, source: Source, options: ConvertOptions) -> ConversionResult:
        """Convert the source.

        Args:
            source: The input to convert.
            options: How to convert it.

        Returns:
            The conversion result, with token counts left unset — the pipeline
            measures.

        Raises:
            ConversionError: And only ``ConversionError`` subclasses. Anything
                else escaping is a bug in the backend.
        """
        ...


class ConversionContext:
    """Scratch space handed to a backend for the duration of one conversion.

    Backends collect warnings and structured metadata here instead of trying to
    assemble an immutable :class:`~tokenmill.core.models.ConversionResult`
    themselves. :class:`BaseConverter` folds it into the result afterwards.
    """

    def __init__(self) -> None:
        """Initialise an empty context."""
        self.warnings: list[str] = []
        self.metadata: dict[str, Any] = {}
        self.stages: list[tuple[str, str]] = []

    def warn(self, message: str) -> None:
        """Record a non-fatal problem for the user.

        Args:
            message: What went wrong that did not stop the conversion.
        """
        _log.debug("conversion warning: %s", message)
        self.warnings.append(message)

    def stage(self, name: str, text: str) -> None:
        """Record an intermediate text so the pipeline can measure it.

        This is the one way a backend can put a row into ``--show-stages``, and
        it does **not** breach "backends do not measure": the backend hands over
        text and the pipeline does every count, exactly as it does for the
        converter's own output. A backend still cannot report a number.

        It exists because the two most interesting reductions this project makes
        happen *inside* a backend and were therefore invisible in the per-stage
        report (defect D8). Extracting an article from a page is two distinct
        savings — dropping the markup, then dropping the furniture — and a
        repository pack that a token budget truncated shows only its final size.

        Use it sparingly. The text is held until the pipeline has measured it
        and is then dropped, so a stage costs memory for the length of one
        conversion; recording every intermediate of a multi-pass converter would
        be a real cost for a report nobody reads.

        Args:
            name: The stage's name, as it appears in the report.
            text: The document as it left that stage.
        """
        self.stages.append((name, text))

    def note(self, key: str, value: Any) -> None:
        """Record a structured fact about the conversion.

        Args:
            key: The fact's name, such as ``page_count``.
            value: The value, which must be JSON-serialisable.
        """
        self.metadata[key] = value


class BaseConverter(ABC):
    """Shared behaviour for backends that run in this process.

    Subclasses supply :attr:`info` and implement :meth:`_convert`. Everything
    else — timing, the availability cache, the size guard, error wrapping — is
    handled here so that every backend behaves identically in the ways users
    can observe.

    Attributes:
        info: Static metadata; set as a class attribute by the subclass.
    """

    info: BackendInfo

    def __init__(self) -> None:
        """Initialise the per-instance availability cache."""
        self._availability: Availability | None = None

    def is_available(self) -> Availability:
        """Return whether this backend can run, probing at most once.

        The probe result is cached for the life of the instance, and the
        registry holds one instance per process, so a repeated ``backends``
        listing costs one probe rather than one per call. A probe that raises is
        reported as broken rather than propagating.

        Returns:
            Why the backend can or cannot run.
        """
        if self._availability is None:
            try:
                self._availability = self._probe()
            except Exception as exc:  # a probe must never raise; report it as broken
                _log.debug("availability probe for %s raised", self.info.id, exc_info=True)
                self._availability = Availability.broken(f"{type(exc).__name__}: {exc}")
        return self._availability

    def _probe(self) -> Availability:
        """Check whether the backend's requirements are satisfied.

        The default assumes a backend with no requirements beyond the core
        install. Backends with an optional dependency override this and probe
        for it with :func:`importlib.util.find_spec`, never a real import — the
        point is to answer the question cheaply and without side effects.

        Returns:
            Why the backend can or cannot run.
        """
        return Availability.present()

    def supports(self, source: Source) -> bool:
        """Return whether this backend claims the source's format.

        Args:
            source: The input under consideration.

        Returns:
            True when :attr:`info` lists the source's format.
        """
        return self.info.supports_format(source.format)

    def convert(self, source: Source, options: ConvertOptions) -> ConversionResult:
        """Convert the source, enforcing the contract every backend shares.

        Checks availability, format support and the size limit, times the
        conversion, and guarantees that only
        :class:`~tokenmill.core.errors.ConversionError` subclasses escape.

        Args:
            source: The input to convert.
            options: How to convert it.

        Returns:
            The conversion result. Token counts are left unset; the pipeline
            fills them in, because measurement is the pipeline's job and a
            backend should not have to know about tokenizers.

        Raises:
            BackendUnavailable: If this backend cannot run.
            UnsupportedFormat: If it does not claim this source's format.
            ConversionError: If the conversion itself fails.
        """
        availability = self.is_available()
        if not availability:
            raise BackendUnavailable(
                f"backend {self.info.id!r} is not available: {availability.describe()}",
                backend_id=self.info.id,
                hint=availability.hint,
            )
        if not self.supports(source):
            raise UnsupportedFormat(
                f"backend {self.info.id!r} does not handle {source.format or 'this'} sources",
                backend_id=self.info.id,
                hint=f"formats it does handle: {', '.join(self.info.input_formats)}",
            )

        self._check_size(source, options)

        context = ConversionContext()
        started = time.perf_counter()
        try:
            text = self._convert(source, options, context)
        except ConversionError:
            raise
        except Exception as exc:
            # A backend that raises something outside the taxonomy has a bug,
            # but the user still gets a typed, printable error rather than a
            # traceback out of the CLI.
            _log.debug("backend %s raised an untyped error", self.info.id, exc_info=True)
            raise BackendFailed(
                f"backend {self.info.id!r} failed: {type(exc).__name__}: {exc}",
                backend_id=self.info.id,
            ) from exc
        duration = time.perf_counter() - started

        return ConversionResult(
            text=text,
            output_format=self._output_format(options),
            source_name=source.name,
            backend_id=self.info.id,
            duration_s=duration,
            warnings=tuple(context.warnings),
            metadata=freeze_metadata(context.metadata),
            internal_stages=tuple(context.stages),
        )

    def _check_size(self, source: Source, options: ConvertOptions) -> None:
        """Reject sources larger than the configured limit.

        Every input is treated as hostile: several backends hand documents to
        C libraries or external binaries, so an unbounded read is a denial of
        service waiting to happen.

        Args:
            source: The input to measure.
            options: Supplies ``max_bytes``.

        Raises:
            CorruptSource: If the source exceeds the limit.
        """
        size: int | None = None
        if source.path is not None and source.path.is_file():
            size = source.path.stat().st_size
        elif source.data is not None:
            size = len(source.data)
        if size is not None and size > options.max_bytes:
            raise CorruptSource(
                f"{source.name} is {size} bytes, over the {options.max_bytes}-byte limit",
                backend_id=self.info.id,
                hint="raise --max-bytes if this file is genuinely meant to be this large",
            )

    def _output_format(self, options: ConvertOptions) -> OutputFormat:
        """Return the format this backend will actually emit.

        Args:
            options: The requested options.

        Returns:
            The requested format if the backend supports it, otherwise the
            backend's first declared output format.
        """
        if options.output_format in self.info.output_formats:
            return options.output_format
        return self.info.output_formats[0]

    @abstractmethod
    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Do the actual conversion.

        This is the only method an adapter author has to write. By the time it
        is called, availability, format support and size have all been checked.

        Args:
            source: The input to convert.
            options: How to convert it.
            context: Collects warnings and metadata for the result.

        Returns:
            The converted text.

        Raises:
            ConversionError: On any failure. Other exceptions are wrapped in
                :class:`~tokenmill.core.errors.BackendFailed` by the caller, but
                raising a precise error yields a much better message.
        """
