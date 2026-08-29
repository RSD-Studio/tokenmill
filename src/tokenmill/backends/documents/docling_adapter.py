"""The ``docling`` backend: the best structure fidelity in the permissive tier.

Docling is the one backend here that understands a document as a document. On
``tests/fixtures/report.docx`` it is the **only** converter in this tier that
gets the whole structure right at once::

    # Context Efficiency Report
    ## Where the tokens actually go
    ### Where the tokens actually go: detail
    - Strip navigation
    1. Keep headings
    1. Nested detail under the last item
    | Stage          |   Tokens | Delta   |

Three correct heading levels with the title at the top, both lists with their
markers, the sub-list restarted as a nested list rather than flattened, and a
real table header row. MarkItDown keeps the list markers too, but demotes the
title to body text, flattens the sub-list into the parent numbering and emits
an **empty header row** above the real one; Kreuzberg collides the title with
the H1s and loses both lists entirely.

It is also the most expensive thing tokenmill can install. ``pip install
docling`` resolves to **122 packages and about 5.2 GB**, PyTorch and the CUDA
runtime among them. That is why it lives behind its own ``docling`` extra and
is imported lazily, and why the ``clean-core-install`` CI job exists.

**The PDF path needs a model download; the Office paths do not.** This is the
distinction that decides how the backend behaves and where it is ranked:

* DOCX, PPTX, XLSX, HTML, CSV and the OpenDocument formats go through direct
  parsers. They work fully offline, with no model, immediately.
* PDF needs the DocLayNet layout model and TableFormer, fetched from
  ``huggingface.co`` on first use and cached afterwards. On a machine that
  cannot reach that host the conversion fails, and this adapter turns that into
  a :class:`~tokenmill.core.errors.NetworkRequired` with an actionable hint
  rather than an ``httpx.ProxyError`` traceback.

Because of that download, ``tokenmill.core.preferences`` ranks docling **first
for DOCX and last for PDF**. Auto-selecting it for a PDF would start a
several-hundred-megabyte download from a command the user thought was local.
Ask for it by name — ``--backend docling`` — and it will happily do the work.

OCR is disabled. Docling's default PDF pipeline enables RapidOCR, which fetches
its own weights from a third host again; OCR is Phase 9, so this adapter turns
it off and lets a scanned PDF come back empty with a warning.

License: docling is MIT, verified against the installed package metadata
(2.121.0), as are ``docling-core``, ``docling-parse``, ``docling-ibm-models``
and ``docling-slim``. A licence audit of the full 122-package resolution found
**no GPL or AGPL anywhere in the tree**. Permissive, so it may be imported into
our process.

**Verification status.** The Office paths in this module were run against the
fixture corpus and their output read. The PDF path was **not** — this sandbox's
egress proxy denies ``huggingface.co``, so the models cannot be fetched here.
``PROGRESS.md`` records that as unverified rather than done.
"""

from __future__ import annotations

import warnings
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

from tokenmill.backends._common import (
    classify_failure,
    probe_module,
    source_as_file,
    warn_on_empty_output,
)
from tokenmill.core.errors import ConversionError
from tokenmill.core.globalstate import process_global_state
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

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterator

__all__ = ["DoclingConverter"]


@contextmanager
def _docling_own_deprecations_muted() -> Iterator[None]:
    """Stop Docling's internal deprecation warnings from failing a conversion.

    Docling 2.121.0's PDF pipeline reads its own deprecated
    ``generate_table_images`` field during ``_init_models``, and pydantic
    dutifully raises a ``DeprecationWarning`` about it. Under ``-W error`` —
    which this project's own test suite sets, and which plenty of applications
    embedding tokenmill will too — that warning becomes an exception, and a
    perfectly good PDF conversion fails with a message about a field the user
    has never heard of and cannot set.

    Nothing tokenmill does causes it and nothing tokenmill can do avoids it, so
    the only honest options are to suppress it or to let a third-party library's
    internal housekeeping break real conversions. The filter is scoped to this
    one call and matched on the message, so an unrelated warning still gets
    through.

    :func:`warnings.catch_warnings` is not thread-safe (defect D2), so this is
    held under :func:`~tokenmill.core.globalstate.process_global_state`.

    **This block covers the whole conversion, not just an import, and that has a
    cost worth stating**: two docling conversions cannot overlap. Docling's
    deprecation warning is raised while the document is being converted rather
    than while the module is being imported, so there is nowhere narrower to put
    it. `docs/BENCHMARKS.md` reports what that means for a parallel batch.

    Yields:
        Nothing; the filter is active for the duration of the block.
    """
    with process_global_state("docling conversion"), warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"This field is deprecated\.",
            category=DeprecationWarning,
        )
        yield


class DoclingConverter(BaseConverter):
    """Converts documents to Markdown with Docling's unified document model.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="docling",
        name="Docling",
        description=(
            "Best structure fidelity in the permissive tier: correct heading "
            "nesting, lists and table headers. Pulls PyTorch, and its PDF path "
            "downloads layout models on first use."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=(
            "pdf",
            "docx",
            "pptx",
            "xlsx",
            "html",
            "htm",
            "xhtml",
            "csv",
            "adoc",
            "asciidoc",
            "odt",
            "ods",
            "odp",
        ),
        output_formats=(OutputFormat.MARKDOWN,),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/docling-project/docling",
        install_extra="docling",
        # Ranked per format in tokenmill.core.preferences: first for DOCX,
        # last for PDF. This declared value only applies to formats the map
        # does not mention.
        priority=15,
    )

    def _probe(self) -> Availability:
        """Check that docling is importable.

        Returns:
            Present when docling is installed, otherwise a missing dependency
            with the install command.
        """
        return probe_module("docling", install_extra="docling")

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Convert the source with Docling and export it as Markdown.

        Args:
            source: The input to convert.
            options: Unused beyond what :class:`BaseConverter` already applied.
            context: Collects page counts and any warning.

        Returns:
            The Markdown.

        Raises:
            ConversionError: If Docling cannot parse the file, or — for PDFs on
                a machine with no route to the model host — cannot fetch the
                layout models it needs.
        """
        del options

        # Imported here, not at module scope: CONTRIBUTING.md rule 3, and this
        # one matters more than most — importing docling imports PyTorch.
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter(format_options=self._format_options())

        with source_as_file(source, self.info.id) as path:
            try:
                with _docling_own_deprecations_muted():
                    converted = converter.convert(str(path))
                document = converted.document
                text = str(document.export_to_markdown())
            except ConversionError:
                raise
            except Exception as exc:
                raise classify_failure(exc, source=source, backend_id=self.info.id) from exc

        self._note_metadata(document, context)
        context.note("ocr", False)

        warn_on_empty_output(
            text,
            source=source,
            context=context,
            reason=(
                "Docling parsed the file with OCR disabled and found no text. For a PDF that "
                "means no text layer — a scanned or image-only document — and reading it would "
                "need OCR, which tokenmill does not ship yet"
            ),
        )
        return text

    @staticmethod
    def _format_options() -> dict[Any, Any]:
        """Build Docling's per-format pipeline options.

        Only the PDF pipeline is configured, and only to turn OCR off. Docling's
        default enables RapidOCR, which downloads its own weights from a third
        host on first use — a surprise download inside what the user asked to be
        a local conversion. OCR is Phase 9.

        Returns:
            The mapping to hand to ``DocumentConverter(format_options=...)``.
        """
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import PdfFormatOption

        pdf_options = PdfPipelineOptions()
        pdf_options.do_ocr = False
        return {InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}

    @staticmethod
    def _note_metadata(document: Any, context: ConversionContext) -> None:
        """Record the structured facts Docling reports about the document.

        Read defensively: ``DoclingDocument``'s shape varies across versions and
        a missing attribute is not worth failing a good conversion over.

        Args:
            document: The ``DoclingDocument``.
            context: Collects the notes.
        """
        for attribute, key in (("pages", "page_count"), ("tables", "tables_found")):
            value = getattr(document, attribute, None)
            if value is None:
                continue
            # `len` rather than a type check: DoclingDocument exposes these as a
            # mapping in some versions and a sequence in others, and an unsized
            # one is not worth failing a good conversion over.
            with suppress(TypeError):
                context.note(key, len(value))
