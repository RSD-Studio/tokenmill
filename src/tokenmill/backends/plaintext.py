"""The ``plaintext`` reference backend: read a text file, pass it through.

This backend exists to prove the architecture, not to be clever. It is the
simplest thing that can be a backend — no dependency, no failure mode beyond an
unreadable file — which makes it the control case for the protocol-conformance
suite: if a test fails for ``plaintext``, the fault is in the framework rather
than in a converter.

It also has a real job. ``.md`` and ``.txt`` inputs need no conversion, and
running them through a heavier converter would only risk damaging them. Passing
them through unchanged, then measuring and post-processing them like anything
else, is the correct behaviour.

License: this adapter is part of tokenmill (Apache-2.0). It wraps nothing.
"""

from __future__ import annotations

from tokenmill.core.errors import CorruptSource
from tokenmill.core.models import (
    BackendInfo,
    ConvertOptions,
    Domain,
    LicenseTier,
    OutputFormat,
    Source,
)
from tokenmill.core.protocol import BaseConverter, ConversionContext

__all__ = ["PlaintextConverter"]


class PlaintextConverter(BaseConverter):
    """Passes text and Markdown through unchanged.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="plaintext",
        name="Plain text",
        description="Reads text and Markdown files through unchanged, then measures them.",
        domains=(Domain.TEXT,),
        input_formats=("txt", "md", "markdown", "text", "rst", "log"),
        output_formats=(OutputFormat.MARKDOWN, OutputFormat.TEXT),
        license="Apache-2.0",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/RSD-Studio/tokenmill",
        install_extra=None,
        priority=50,
    )

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Read the source and return its text unchanged.

        Args:
            source: The input to read.
            options: Unused; this backend has no settings.
            context: Collects the character count and any decoding warning.

        Returns:
            The source's text.

        Raises:
            CorruptSource: If the source has no readable content — a URL that
                has not been fetched, or a directory.
        """
        del options
        try:
            raw = source.read_bytes()
        except ValueError as exc:
            raise CorruptSource(
                f"{source.name} has no readable text content",
                backend_id=self.info.id,
                hint="plaintext converts files, bytes and literal text",
            ) from exc

        text = raw.decode("utf-8", errors="replace")
        if "�" in text and "�" not in raw.decode("utf-8", errors="ignore"):
            # Replacement characters that were not already in the source mean we
            # guessed the encoding wrong. Say so rather than silently returning
            # mojibake that will be measured and reported as if it were correct.
            context.warn(
                f"{source.name} is not valid UTF-8; undecodable bytes were replaced with U+FFFD"
            )
        context.note("characters", len(text))
        context.note("bytes", len(raw))
        return text
