"""The ``pypdf`` backend: the smallest, most predictable PDF reader we have.

pypdf extracts text and nothing else. No tables, no headings, no layout model —
it walks the page's text objects in the order the PDF's content stream lists
them and returns what it finds. That sounds like a weakness and mostly is, but
it buys one property the more capable backends lack: on
``tests/fixtures/twocolumn.pdf`` it emits ``ORDERMARK 01`` through
``ORDERMARK 12`` **in ascending order**, where pdfplumber and MarkItDown
interleave the two columns. For a multi-column document, reading order is worth
more than a table it was never going to find.

Two honest caveats, both observed rather than assumed:

* That reading order is a property of how the PDF was *written*, not a promise
  pypdf makes. A generator that emits its content stream out of visual order
  will come back out of order. It happens to be right for our fixture, and it
  is right for most PDFs produced by a layout engine that fills frames in
  order.
* On ``tests/fixtures/tables.pdf`` the 7x5 grid comes back as one cell per
  line, ``Backend`` then ``License`` then ``Runtime`` and so on. The data is all
  there; the shape is gone. Use ``pdfplumber`` when the shape matters.

pypdf is the last-resort member of the PDF chain: it is in the core install, it
has essentially no dependencies, and it is the backend that still works when
everything heavier has failed.

License: pypdf is BSD-3-Clause, verified against the installed package metadata
(6.16.1). ``docs/research/RESEARCH.md`` says "BSD-3" and is correct. Permissive,
so it may be imported into our process; pure Python, zero required dependencies
on Python 3.11+.
"""

from __future__ import annotations

from typing import Any

from tokenmill.backends.documents._common import (
    classify_failure,
    probe_module,
    source_as_file,
    warn_on_empty_output,
)
from tokenmill.core.errors import ConversionError, CorruptSource
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

__all__ = ["PypdfConverter"]


class PypdfConverter(BaseConverter):
    """Extracts plain text from digital PDFs, in content-stream order.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="pypdf",
        name="pypdf",
        description=(
            "Plain text from digital PDFs. No tables and no headings, but it "
            "keeps multi-column reading order where the layout-blind "
            "extractors do not."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=("pdf",),
        output_formats=(OutputFormat.MARKDOWN, OutputFormat.TEXT),
        license="BSD-3-Clause",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/py-pdf/pypdf",
        install_extra=None,
        priority=20,
    )

    def _probe(self) -> Availability:
        """Check that pypdf is importable.

        Returns:
            Present when pypdf is installed, otherwise a missing dependency
            with the install command.
        """
        return probe_module("pypdf", hint="pip install tokenmill")

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Extract the PDF's text, one blank-line-separated block per page.

        Args:
            source: The PDF to convert.
            options: Unused beyond what :class:`BaseConverter` already applied.
            context: Collects the page count and any warning.

        Returns:
            The extracted text.

        Raises:
            ConversionError: If the file cannot be parsed or is encrypted with
                a password we do not have.
        """
        del options

        # Imported here, not at module scope: CONTRIBUTING.md rule 3.
        import pypdf

        with source_as_file(source, self.info.id) as path:
            try:
                reader = pypdf.PdfReader(path)
                self._unlock(reader, source, context)
                pages = [self._page_text(page) for page in reader.pages]
                page_count = len(reader.pages)
            except ConversionError:
                raise
            except Exception as exc:
                raise classify_failure(exc, source=source, backend_id=self.info.id) from exc

        text = "\n\n".join(page for page in pages if page)
        if text and not text.endswith("\n"):
            text += "\n"

        context.note("page_count", page_count)
        context.note("detects_tables", False)
        context.note("detects_headings", False)
        warn_on_empty_output(
            text,
            source=source,
            context=context,
            reason=(
                f"pypdf found no text layer across {page_count} page(s), which is what a scanned "
                f"or image-only PDF looks like. Extracting text from page images needs OCR, "
                f"which tokenmill does not ship yet"
            ),
        )
        return text

    def _unlock(self, reader: Any, source: Source, context: ConversionContext) -> None:
        """Open an encrypted PDF that carries an empty owner password.

        Many PDFs are "encrypted" only to set permission flags and open with an
        empty password. Those convert fine and are worth a note rather than a
        refusal. One that needs a real password cannot be converted, and saying
        so beats returning a blank document.

        Args:
            reader: The ``pypdf.PdfReader``.
            source: The input, for the message.
            context: Records that the file was encrypted.

        Raises:
            CorruptSource: If the file needs a password we do not have.
        """
        if not reader.is_encrypted:
            return
        context.note("encrypted", True)
        try:
            opened = reader.decrypt("")
        except Exception as exc:
            opened = 0
            context.warn(f"{source.name} could not be decrypted: {type(exc).__name__}: {exc}")
        if not opened:
            raise CorruptSource(
                f"{source.name} is password-protected",
                backend_id=self.info.id,
                hint="tokenmill cannot supply a PDF password; decrypt the file first",
            )
        context.warn(
            f"{source.name} is encrypted but opened with an empty password; "
            f"its permission flags were ignored"
        )

    @staticmethod
    def _page_text(page: Any) -> str:
        """Extract one page's text, treating failure as an empty page.

        Args:
            page: A ``pypdf.PageObject``.

        Returns:
            The page's text, stripped, or an empty string.
        """
        try:
            return (page.extract_text() or "").strip()
        except Exception:
            return ""
