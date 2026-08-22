"""The ``kreuzberg`` backend: one fast extractor across a lot of formats.

Kreuzberg v4 is a Rust core with Python bindings and — as of 4.10.2 — **no
required Python dependencies at all**. That makes it the cheapest way to add
broad format coverage to an install, and it is fast: it converts every fixture
in our corpus without a perceptible pause.

What it is good at, on our fixtures:

* ``twocolumn.pdf`` — correct reading order, ``ORDERMARK 01`` through ``12``
  ascending, which pdfplumber and MarkItDown both get wrong.
* ``simple.pdf`` — it infers headings from a PDF that has no heading structure
  at all, emitting ``# Why Your Context Window Is Mostly Navigation Menus``.
* ``data.xlsx``, ``.csv``, ``.tsv`` — clean Markdown tables under a heading per
  sheet.

What it is bad at, and this one is disqualifying for the format it matters
most in:

* ``tables.pdf`` — **the table is destroyed.** The 7x5 grid comes back as a
  heading followed by one run-on paragraph:
  ``markitdown MIT CPU weak 12.0 docling MIT CPU strong 0.8 ...``. Nothing is
  lost as *text*, but the structure that made it a table is gone. Use
  ``pdfplumber`` when a PDF's tables carry the meaning.
* ``deck.pptx`` — speaker notes are dropped. Only MarkItDown keeps them.
* ``report.docx`` — the title and the H1s all flatten to ``#``, and both lists
  lose their markers.
* ``data.xlsx`` — numeric cells are coerced, so ``12.0`` comes back as ``12``.

OCR is switched off explicitly. Kreuzberg can drive Tesseract or EasyOCR, but
OCR is Phase 9, EasyOCR pulls PyTorch, and a backend that silently changes
behaviour depending on whether a system binary happens to be installed cannot be
described honestly. Caching is off for the same reason: a converter that writes
to a cache directory behind the user's back makes measurements irreproducible.

License: kreuzberg is MIT, verified against the installed package metadata
(4.10.2). ``docs/research/RESEARCH.md`` flags that the newer "Xberg" v1 line
moved to Elastic-2.0 while the v4 line stayed MIT — hence the ``<5`` pin on the
``documents`` extra, so a future major cannot change our licence position by
resolving a new version.
"""

from __future__ import annotations

from typing import Any

from tokenmill.backends.documents._common import (
    classify_failure,
    probe_module,
    source_as_file,
    warn_on_empty_output,
)
from tokenmill.core.errors import ConversionError
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

__all__ = ["KreuzbergConverter"]


class KreuzbergConverter(BaseConverter):
    """Converts documents to Markdown with Kreuzberg's Rust extraction core.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="kreuzberg",
        name="Kreuzberg",
        description=(
            "Fast unified extraction over a Rust core. Good reading order and "
            "heading inference; flattens PDF tables into prose and drops PPTX "
            "speaker notes."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=(
            "pdf",
            "docx",
            "pptx",
            "xlsx",
            "csv",
            "tsv",
            "rtf",
            "eml",
            "json",
            "xml",
            "html",
            "htm",
            "xhtml",
        ),
        output_formats=(OutputFormat.MARKDOWN,),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/Goldziher/kreuzberg",
        install_extra="documents",
        priority=25,
    )

    def _probe(self) -> Availability:
        """Check that kreuzberg is importable.

        Returns:
            Present when kreuzberg is installed, otherwise a missing dependency
            with the install command.
        """
        return probe_module("kreuzberg", install_extra="documents")

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Extract the source as Markdown.

        Args:
            source: The input to convert.
            options: Unused beyond what :class:`BaseConverter` already applied.
            context: Collects the detected media type and any warning.

        Returns:
            The Markdown.

        Raises:
            ConversionError: If Kreuzberg cannot parse the file.
        """
        del options

        # Imported here, not at module scope: CONTRIBUTING.md rule 3.
        import kreuzberg

        # Two `type: ignore`s, both because kreuzberg 4.10.2's shipped type
        # information disagrees with the package that is actually installed:
        # `OutputFormat` is defined inside an `if not TYPE_CHECKING:` block in
        # its `__init__.py`, so a type checker cannot see it, and `disable_ocr`
        # is absent from the `ExtractionConfig` stub while the real initialiser
        # accepts it. Both were verified against the installed package, and
        # reality wins — see PROGRESS.md, Decisions. `warn_unused_ignores` is
        # on, so if upstream fixes either one, mypy will tell us to delete the
        # ignore rather than letting it rot here.
        config = kreuzberg.ExtractionConfig(
            output_format=kreuzberg.OutputFormat.MARKDOWN,  # type: ignore[attr-defined]
            # OCR is Phase 9. Leaving it on would make output depend on whether
            # a Tesseract binary happens to be present, which is not something
            # docs/BACKENDS.md could describe truthfully.
            disable_ocr=True,  # type: ignore[call-arg]
            # A converter that writes to a cache directory behind the user's
            # back makes a second run of the same command unreproducible.
            use_cache=False,
        )

        with source_as_file(source, self.info.id) as path:
            try:
                result = kreuzberg.extract_file_sync(str(path), config=config)
            except ConversionError:
                raise
            except Exception as exc:
                raise classify_failure(exc, source=source, backend_id=self.info.id) from exc

        text = str(result.content or "")
        self._note_metadata(result, context)
        context.note("ocr", False)

        warn_on_empty_output(
            text,
            source=source,
            context=context,
            reason=(
                "Kreuzberg parsed the file with OCR disabled and found no text layer, which is "
                "what a scanned or image-only document looks like. OCR is not part of tokenmill "
                "yet"
            ),
        )
        return text

    @staticmethod
    def _note_metadata(result: Any, context: ConversionContext) -> None:
        """Record the structured facts Kreuzberg reports about the document.

        Kreuzberg's metadata shape varies by extractor and by version, so every
        field is read defensively: a missing one is simply not noted rather than
        an error. Metadata is a convenience, not a contract.

        Args:
            result: The ``kreuzberg.ExtractionResult``.
            context: Collects the notes.
        """
        mime = getattr(result, "mime_type", None)
        if mime:
            context.note("mime_type", str(mime))

        metadata = getattr(result, "metadata", None)
        if not isinstance(metadata, dict):
            return
        for key in ("title", "page_count", "languages"):
            value = metadata.get(key)
            if value is not None:
                context.note(key, value if isinstance(value, int | str) else str(value))
