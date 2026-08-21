"""The ``markitdown`` backend: breadth, and the honest cost of it.

MarkItDown converts more formats than anything else in this tier — Office, mail,
notebooks, archives, images, audio — which is exactly what it is for. Reach for
it when the question is "can tokenmill open this at all".

Where it wins on our fixtures, measured rather than assumed:

* ``deck.pptx`` — the **only** backend in this tier that keeps speaker notes.
  All four notes come through under a ``### Notes:`` heading.
* ``data.xlsx`` — one Markdown table per sheet, each under a heading naming the
  sheet.

Where it loses, quoted in ``docs/BACKENDS.md``:

* ``tables.pdf`` — it emits a Markdown table, but the header row is mis-split:
  ``| Backend | License | Runtime | Tables Pages/sec |      |`` merges two
  columns and invents an empty one. The six data rows are correct, so 30 of the
  35 cells survive in the right shape and five do not.
* ``report.docx`` — the document Title becomes body text rather than a heading,
  the bullet list loses its markers, and the table is emitted with an **empty
  header row** above the real one.
* ``twocolumn.pdf`` — reading order is wrong; the output starts mid-document at
  ``ORDERMARK 08``.
* Images and audio need ``exiftool`` and ``ffmpeg``. Without them MarkItDown
  returns an empty string and no error, so this adapter checks ``PATH`` and says
  which binary is missing. A silent empty document is the failure mode this
  project exists to not have.

Plugins are disabled. MarkItDown will load third-party converter plugins from
the environment if asked, and a backend whose behaviour depends on what else is
installed cannot be reported honestly.

License: markitdown is MIT, verified against the installed package metadata
(0.1.7). Permissive, so it may be imported into our process. It lives behind the
``documents`` extra rather than in core: its Office and PDF converters pull
pandas, lxml, mammoth and onnxruntime (via magika), which is more weight than
``pip install tokenmill`` promises — but all of it CPU-only, wheel-installable
and permissively licensed.
"""

from __future__ import annotations

from typing import Final

from tokenmill.backends.documents._common import (
    classify_failure,
    missing_binary_note,
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

__all__ = ["MarkItDownConverter"]

#: Formats MarkItDown hands to ``exiftool`` for metadata, and to an OCR or
#: speech plugin for content. Without those binaries it returns an empty string
#: rather than raising, so we check and say so.
_IMAGE_FORMATS: Final[frozenset[str]] = frozenset({"jpg", "jpeg", "png"})
_AUDIO_FORMATS: Final[frozenset[str]] = frozenset({"wav", "mp3", "m4a"})


class MarkItDownConverter(BaseConverter):
    """Converts Office, mail, archive and media files to Markdown.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="markitdown",
        name="MarkItDown",
        description=(
            "The broadest converter in the light tier: Office, mail, notebooks, "
            "archives, images and audio. Keeps PPTX speaker notes; weak on PDF "
            "layout and DOCX structure."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=(
            "pdf",
            "docx",
            "pptx",
            "xlsx",
            "xls",
            "csv",
            "json",
            "jsonl",
            "ipynb",
            "epub",
            "msg",
            "zip",
            "html",
            "htm",
            "jpg",
            "jpeg",
            "png",
            "wav",
            "mp3",
            "m4a",
        ),
        output_formats=(OutputFormat.MARKDOWN,),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/microsoft/markitdown",
        install_extra="documents",
        priority=30,
    )

    def _probe(self) -> Availability:
        """Check that markitdown is importable.

        Returns:
            Present when markitdown is installed, otherwise a missing
            dependency with the install command.
        """
        return probe_module("markitdown", install_extra="documents")

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Convert the source with MarkItDown.

        Args:
            source: The input to convert.
            options: Unused beyond what :class:`BaseConverter` already applied.
            context: Collects the title, any missing binary, and any warning.

        Returns:
            The Markdown.

        Raises:
            ConversionError: If MarkItDown cannot convert the file.
        """
        del options

        # Imported here, not at module scope: CONTRIBUTING.md rule 3.
        from markitdown import MarkItDown

        self._warn_about_missing_binaries(source, context)

        with source_as_file(source, self.info.id) as path:
            try:
                # enable_plugins=False deliberately: a backend whose output
                # depends on which third-party markitdown plugins happen to be
                # installed cannot be described honestly in docs/BACKENDS.md.
                result = MarkItDown(enable_plugins=False).convert(str(path))
            except ConversionError:
                raise
            except Exception as exc:
                raise classify_failure(exc, source=source, backend_id=self.info.id) from exc

        text = str(result.markdown or "")
        title = getattr(result, "title", None)
        if title:
            context.note("title", str(title))
        context.note("plugins_enabled", False)

        warn_on_empty_output(
            text,
            source=source,
            context=context,
            reason=self._empty_reason(source),
        )
        return text

    def _warn_about_missing_binaries(self, source: Source, context: ConversionContext) -> None:
        """Warn up front when the helper binaries this format needs are absent.

        Args:
            source: The input, whose format decides which binaries matter.
            context: Collects the warning and the structured fact.
        """
        needed = self._binaries_for(source.format)
        if not needed:
            return
        missing = missing_binary_note(needed)
        if not missing:
            return
        context.note("missing_binaries", list(missing))
        context.warn(
            f"MarkItDown uses {', '.join(missing)} for {source.format} files and "
            f"{'they are' if len(missing) > 1 else 'it is'} not on PATH; expect little or "
            f"no content. Install {' and '.join(missing)}, or use a backend that does not "
            f"need {'them' if len(missing) > 1 else 'it'}"
        )

    @staticmethod
    def _binaries_for(source_format: str) -> tuple[str, ...]:
        """Return the external binaries MarkItDown needs for a format.

        Args:
            source_format: The source's format token.

        Returns:
            The executable names, empty for formats handled in pure Python.
        """
        if source_format in _IMAGE_FORMATS:
            return ("exiftool",)
        if source_format in _AUDIO_FORMATS:
            return ("exiftool", "ffmpeg")
        return ()

    def _empty_reason(self, source: Source) -> str:
        """Explain, in MarkItDown's terms, why a conversion produced nothing.

        Args:
            source: The input that converted to nothing.

        Returns:
            The likeliest cause for this format.
        """
        if source.format in _IMAGE_FORMATS:
            return (
                "MarkItDown reads image files for embedded metadata and, with an OCR plugin, "
                "for text. Without exiftool on PATH and without such a plugin there is "
                "nothing for it to report. OCR is not part of tokenmill yet"
            )
        if source.format in _AUDIO_FORMATS:
            return (
                "MarkItDown reads audio files for metadata and, with a speech-recognition "
                "backend, for a transcript. Without exiftool and ffmpeg on PATH there is "
                "nothing for it to report"
            )
        if source.format == "pdf":
            return (
                "MarkItDown found no text layer in this PDF, which is what a scanned or "
                "image-only document looks like. Extracting text from page images needs OCR, "
                "which tokenmill does not ship yet"
            )
        return "MarkItDown parsed the file but found no extractable text in it"
