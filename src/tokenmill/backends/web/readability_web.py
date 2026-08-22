"""The ``readability`` backend: Firefox Reader View's algorithm, as a fallback.

``readability-lxml`` is a Python port of the arc90/Mozilla readability
algorithm — the one behind Firefox's Reader View. It scores a page's elements
by text density and link density, keeps the highest-scoring subtree, and
returns it as HTML. This adapter then converts that HTML to Markdown with
markdownify, which is already in the core install.

**Why it is here when trafilatura ranks above it.** Extraction is a judgement,
and a second, independently-implemented judgement is worth having: trafilatura
declines outright on pages it cannot read as articles, and at that point a
second opinion beats the whole page with its navigation attached. It sits
between trafilatura and ``markdownify_html`` in the chain for that reason.

**What it does on our corpus, measured rather than assumed.** On
``tests/fixtures/boilerplate.html`` it removes all six of the manifest's
``boilerplate_markers_must_be_absent`` and keeps the article, the headings and
the table — and its output is **byte-identical to trafilatura's** apart from
the spacing inside the table's separator row (``| --- |`` against ``|---|``).
2,864 characters against 2,854.

That is worth stating plainly because the obvious thing to write here would
have been that readability trades precision for recall, which is the general
reputation of the algorithm. On this page it does no such thing: the two agree
completely. One fixture is not a benchmark, and Phase 10's harness over a real
corpus is what could support a claim about their relative behaviour. Until
then this page says what was measured and nothing more.

**Its documented weakness.** The scoring is about text and link density, so the
pages it is weakest on are the ones that are mostly links. It returns an empty
result rather than raising when it finds nothing, which this adapter turns into
a failure so the chain continues.

License: readability-lxml is Apache-2.0, verified against the installed package
metadata (0.8.4.1). It is in the ``web`` extra rather than the core install
because it duplicates a job trafilatura already does; nothing in the core needs
it.
"""

from __future__ import annotations

from typing import Any, Final

from tokenmill.backends._common import (
    classify_failure,
    probe_module,
    warnings_as_conversion_warnings,
)
from tokenmill.backends.web._common import note_web_metrics
from tokenmill.core.errors import BackendFailed, ConversionError, CorruptSource
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

__all__ = ["ReadabilityConverter"]

#: Passed to markdownify when turning readability's cleaned HTML into Markdown.
#: ATX headings for the same reason ``markdownify_html`` uses them: they survive
#: past level two and every downstream consumer expects them.
_MARKDOWNIFY_OPTIONS: Final[dict[str, Any]] = {"heading_style": "ATX"}


class ReadabilityConverter(BaseConverter):
    """Extracts a page's main content with the Reader View algorithm.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="readability",
        name="Readability",
        description=(
            "Firefox Reader View's extraction algorithm. An independent "
            "second opinion when trafilatura declines a page."
        ),
        domains=(Domain.WEB,),
        input_formats=("html", "htm", "xhtml"),
        output_formats=(OutputFormat.MARKDOWN,),
        license="Apache-2.0",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/buriy/python-readability",
        install_extra="web",
        priority=30,
    )

    def _probe(self) -> Availability:
        """Check that readability and markdownify are both importable.

        Both are needed: readability produces HTML, and this adapter's job is
        finished by markdownify. Reporting only the missing one would send a
        user to install a package and hit the same wall again.

        Returns:
            Present when both are installed, otherwise a missing dependency
            with the install command.
        """
        readability = probe_module("readability", install_extra="web")
        if not readability:
            return readability
        return probe_module("markdownify", hint="pip install markdownify")

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Extract the source page's main content as Markdown.

        Args:
            source: The HTML to extract from. A URL source has already been
                fetched by the pipeline by the time it arrives here.
            options: Unused beyond what :class:`BaseConverter` already applied.
            context: Collects the extraction metrics, the detected title and
                any warning.

        Returns:
            The extracted Markdown.

        Raises:
            CorruptSource: If the source has no readable content, or is empty.
            BackendFailed: If readability finds no main content, so that the
                fallback chain can offer the page to another backend.
            ConversionError: If readability or markdownify fails.
        """
        del options

        # Imported here, not at module scope: CONTRIBUTING.md rule 3.
        with warnings_as_conversion_warnings(context, activity="importing readability"):
            import markdownify
            import readability

        try:
            html = source.read_text()
        except ValueError as exc:
            raise CorruptSource(
                f"{source.name} has no readable HTML content",
                backend_id=self.info.id,
                hint="readability extracts from HTML files, bytes and fetched pages",
            ) from exc

        if not html.strip():
            raise CorruptSource(f"{source.name} is empty", backend_id=self.info.id)

        try:
            with warnings_as_conversion_warnings(context, activity="extracting with readability"):
                document = readability.Document(html)
                title = str(document.short_title() or "")
                summary_html = str(document.summary(html_partial=True) or "")
        except ConversionError:
            raise
        except Exception as exc:
            raise classify_failure(exc, source=source, backend_id=self.info.id) from exc

        if title:
            context.note("title", title)

        try:
            body = str(markdownify.markdownify(summary_html, **_MARKDOWNIFY_OPTIONS))
        except Exception as exc:
            raise BackendFailed(
                f"markdownify could not convert readability's output for {source.name}: "
                f"{type(exc).__name__}: {exc}",
                backend_id=self.info.id,
            ) from exc

        # readability drops the <h1> along with the rest of the page header,
        # so the extracted body routinely has no title. Restoring it is worth
        # the two lines: a document whose title is gone is harder to use, and
        # the title is one the algorithm itself identified rather than one
        # invented here.
        text = body.strip()
        if title and text and title not in text.split("\n", 1)[0]:
            text = f"# {title}\n\n{text}"
        if text:
            text += "\n"

        note_web_metrics(context, html=html, output=text, strips_boilerplate=True)

        if not text.strip():
            raise BackendFailed(
                f"readability found no main content in {source.name}; the page may be "
                f"mostly links, which is what its scoring is weakest on",
                backend_id=self.info.id,
                hint=(
                    "try --backend markdownify_html to convert the whole page, boilerplate included"
                ),
            )
        return text
