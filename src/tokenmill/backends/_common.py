"""Shared plumbing for every backend adapter.

Five adapters wrap five third-party libraries that agree on almost nothing: they
want a path or a file object, they raise their own exception hierarchies, and
they disagree about what "empty" means. The helpers here are the small set of
behaviours all five must nevertheless share, so that a user sees one product
rather than five wrappers.

Three of them carry real decisions:

* :func:`classify_failure` maps a library's own exception onto the tokenmill
  taxonomy. It is deliberately conservative — an exception it cannot recognise
  becomes :class:`~tokenmill.core.errors.BackendFailed`, not a guess.
* :func:`warn_on_empty_output` exists because an empty conversion exits zero and
  looks like success. ``tests/fixtures/scanned.pdf`` has no text layer by
  design, and every backend in this tier returns nothing for it. That must be
  loud.
* :func:`source_as_file` gives libraries that only accept a path one, without
  making every adapter reimplement temporary-file handling for byte and text
  sources.
* :func:`warnings_as_conversion_warnings` stops a third-party library's
  import-time chatter from being fatal under ``-W error``, without hiding it.
"""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import warnings
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from tokenmill.core.errors import (
    BackendFailed,
    ConversionError,
    CorruptSource,
    NetworkRequired,
)
from tokenmill.core.models import Availability, Source
from tokenmill.core.protocol import ConversionContext

__all__ = [
    "classify_failure",
    "missing_binary_note",
    "probe_module",
    "render_markdown_table",
    "source_as_file",
    "warn_on_empty_output",
    "warnings_as_conversion_warnings",
]

#: Substrings that mark a failure as "this file is damaged", checked
#: case-insensitively against the exception text. Kept tight: a loose match here
#: would relabel a genuine bug in a backend as a bad input and send the user
#: hunting for a problem in their document.
_CORRUPT_MARKERS: Final[tuple[str, ...]] = (
    "unexpected eof",
    "stream has ended unexpectedly",
    "eof marker not found",
    "invalid pdf",
    "is not a pdf",
    "not a zip file",
    "bad magic number",
    "file has not been decrypted",
    "damaged",
    "truncated",
    "corrupt",
    "malformed",
)

#: Substrings that mark a failure as "this needed the network and did not get
#: it". Several backends in this tier fetch a model on first use, and on an
#: air-gapped machine that is the failure a user will actually hit, so it gets
#: its own error class and its own hint rather than a generic one.
_NETWORK_MARKERS: Final[tuple[str, ...]] = (
    "connection refused",
    "connection error",
    "connection aborted",
    "failed to establish a new connection",
    "max retries exceeded",
    "name or service not known",
    "temporary failure in name resolution",
    "network is unreachable",
    "proxy",
    "403 forbidden",
    "407 proxy",
    "failed to download",
    "couldn't connect to",
    "we couldn't connect to",
    "offline mode is enabled",
    "read timed out",
    "connect timeout",
)


def probe_module(
    module: str, *, install_extra: str | None = None, hint: str | None = None
) -> Availability:
    """Report whether an optional dependency is importable, without importing it.

    ``importlib.util.find_spec`` rather than a ``try: import`` because the probe
    runs for every ``tokenmill backends`` listing and the Phase 8 GUI will repaint
    that list far more often than that. Importing costs whatever the dependency
    costs, and for this tier that can be PyTorch.

    Args:
        module: The importable top-level module name.
        install_extra: The tokenmill extra that supplies it, used to build the
            default hint.
        hint: An explicit install command, overriding the default.

    Returns:
        Present when the module is importable, otherwise a missing dependency
        carrying the install command.
    """
    if importlib.util.find_spec(module) is not None:
        return Availability.present()
    if hint is None:
        hint = (
            f'pip install "tokenmill[{install_extra}]"'
            if install_extra
            else f"pip install {module}"
        )
    return Availability.missing_dependency(module, hint=hint)


@contextmanager
def source_as_file(source: Source, backend_id: str) -> Iterator[Path]:
    """Yield a real filesystem path for a source, for libraries that need one.

    A ``FILE`` source already has one and is yielded unchanged — no copy, no
    temporary directory. Byte and text sources are written to a temporary file
    whose suffix carries the format, because several of these libraries sniff
    the type from the name.

    Args:
        source: The input to materialise.
        backend_id: Attributed on failure.

    Yields:
        A path that exists for the duration of the ``with`` block.

    Raises:
        CorruptSource: If the source has no readable content at all — a
            repository directory, or a URL that has not been fetched.
    """
    if source.path is not None and source.path.is_file():
        yield source.path
        return

    try:
        data = source.read_bytes()
    except ValueError as exc:
        raise CorruptSource(
            f"{source.name} has no readable content",
            backend_id=backend_id,
            hint="this backend converts files and bytes, not directories or unfetched URLs",
        ) from exc

    suffix = Path(source.name).suffix or ""
    with tempfile.TemporaryDirectory(prefix="tokenmill-") as directory:
        path = Path(directory) / f"source{suffix}"
        path.write_bytes(data)
        yield path


@contextmanager
def warnings_as_conversion_warnings(context: ConversionContext, *, activity: str) -> Iterator[None]:
    """Turn warnings raised inside the block into conversion warnings.

    A library that warns at import time must not be able to fail a conversion.
    Under ``-W error`` — which this project's own test suite sets, and which
    applications embedding tokenmill may too — any such warning becomes an
    exception, and ``BaseConverter`` then reports a perfectly healthy converter
    as broken.

    This is not hypothetical. ``markitdown`` imports ``magika``, which imports
    ``onnxruntime``, which warns ``Unsupported Windows version (2025server)``
    the moment it loads. On the Windows CI runners that turned every MarkItDown
    conversion into ``BackendFailed``, for a reason that had nothing to do with
    the document.

    Suppressing it outright would be the wrong fix — "your platform is
    unsupported" is exactly the kind of thing a user should hear. So each
    warning is captured and handed to the user as a conversion warning instead:
    non-fatal, still visible, attributed to the thing that raised it.

    Note that :func:`warnings.catch_warnings` manipulates global state and is
    not thread-safe. That is fine today — nothing runs conversions concurrently
    — and is recorded in ``PROGRESS.md`` as something the Phase 8 batch runner
    has to account for.

    Args:
        context: Collects whatever was warned about.
        activity: What was happening, for the message.

    Yields:
        Nothing; warnings are collected for the duration of the block.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield
    for entry in caught:
        context.warn(f"{activity}: {entry.category.__name__}: {entry.message}")


def classify_failure(exc: Exception, *, source: Source, backend_id: str) -> ConversionError:
    """Map a third-party library's exception onto the tokenmill taxonomy.

    Every adapter in this tier funnels its wrapped library's exceptions through
    here so that the same underlying problem reads the same way whichever
    backend hit it: a truncated PDF is a
    :class:`~tokenmill.core.errors.CorruptSource` from all four PDF backends,
    even though the four libraries raise four unrelated exception types.

    Anything unrecognised becomes :class:`~tokenmill.core.errors.BackendFailed`.
    Guessing harder would mean telling a user their file is damaged when the
    real fault is in the converter.

    Args:
        exc: What the library raised.
        source: The input being converted, for the message.
        backend_id: The backend to attribute the failure to.

    Returns:
        The error to raise. Never raises on its own account.
    """
    text = _exception_text(exc)
    lowered = text.lower()

    if any(marker in lowered for marker in _NETWORK_MARKERS):
        return NetworkRequired(
            f"{backend_id} could not reach the network while converting {source.name}: {text}",
            backend_id=backend_id,
            hint=(
                "this backend downloads a model or vocabulary on first use; run it once "
                "on a networked machine, or choose a backend that needs no download"
            ),
        )
    if any(marker in lowered for marker in _CORRUPT_MARKERS):
        return CorruptSource(
            f"{source.name} could not be parsed: {text}",
            backend_id=backend_id,
            hint="the file appears damaged or truncated; check it opens in a normal viewer",
        )
    return BackendFailed(
        f"{backend_id} failed on {source.name}: {text}",
        backend_id=backend_id,
    )


def _exception_text(exc: BaseException) -> str:
    """Render an exception and its causes as one searchable string.

    Libraries in this tier routinely wrap the informative exception inside a
    generic one, so the marker that says "this was a network failure" is often
    two levels down the ``__cause__`` chain rather than in ``str(exc)``.

    Args:
        exc: The exception to render.

    Returns:
        ``Type: message`` for the exception and each of its causes, joined by
        ``: caused by ``. Cycles and runaway chains are bounded.
    """
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(parts) < 5:
        seen.add(id(current))
        message = str(current).strip()
        parts.append(f"{type(current).__name__}: {message}" if message else type(current).__name__)
        current = current.__cause__ or current.__context__
    return ": caused by ".join(parts)


def warn_on_empty_output(
    text: str, *, source: Source, context: ConversionContext, reason: str
) -> None:
    """Attach a warning when a conversion produced nothing.

    An empty conversion exits zero, writes an empty file and looks exactly like
    success. It is not: something went in and nothing came out.
    ``tests/fixtures/scanned.pdf`` is in the corpus precisely to keep this path
    honest — it has no text layer, every backend in this tier returns nothing
    for it, and OCR is Phase 9.

    Args:
        text: What the backend produced.
        source: The input, for the message.
        context: Collects the warning.
        reason: The likely cause, in the backend's own terms.
    """
    if text.strip():
        return
    context.note("empty_output", True)
    context.warn(
        f"{source.name} converted to an empty document: {reason}. "
        f"The conversion succeeded; there was simply nothing to extract."
    )


def missing_binary_note(names: Sequence[str]) -> tuple[str, ...]:
    """Return the subset of ``names`` that is not on ``PATH``.

    MarkItDown shells out to ``exiftool`` and ``ffmpeg`` for image and audio
    formats and, when they are absent, returns an empty string rather than
    raising. Naming the missing binary turns that silence into something the
    user can act on.

    Args:
        names: Executable names to look for.

    Returns:
        Those that could not be found, in the order given.
    """
    return tuple(name for name in names if shutil.which(name) is None)


def render_markdown_table(rows: Sequence[Sequence[str | None]]) -> str:
    """Render a grid of cells as a GitHub-flavoured Markdown table.

    Ragged rows are padded rather than rejected: a table recovered from a PDF
    routinely has a row the extractor read one cell short, and dropping the
    whole table over it would lose far more than it saved.

    Args:
        rows: The cells, first row treated as the header. ``None`` cells — which
            is what pdfplumber returns for a blank cell — become empty strings.

    Returns:
        The table with a trailing newline, or an empty string when there are no
        rows.
    """
    grid = [[_escape_cell(cell) for cell in row] for row in rows if row]
    if not grid:
        return ""

    width = max(len(row) for row in grid)
    padded = [[*row, *[""] * (width - len(row))] for row in grid]

    header, *body = padded
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines) + "\n"


def _escape_cell(cell: str | None) -> str:
    """Make one cell safe to place inside a Markdown table.

    Args:
        cell: The raw value, possibly ``None`` or spanning several lines.

    Returns:
        The value with pipes escaped and newlines flattened to spaces, since a
        Markdown table row cannot contain either.
    """
    if cell is None:
        return ""
    return " ".join(cell.replace("|", "\\|").split())
