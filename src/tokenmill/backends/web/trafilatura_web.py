"""The ``trafilatura`` backend: the article, without the website around it.

This is the backend Phase 3 exists for, and the one that makes tokenmill's
central claim measurable. Every other web backend converts a page; this one
decides which *part* of the page was the page.

**What it does on our corpus.** ``tests/fixtures/boilerplate.html`` is
``article.html``'s body wrapped in a cookie banner, a five-section navigation
menu repeated in the footer, two advertisement slots, a newsletter modal, a
trending rail, a social rail and two inline scripts. Trafilatura returns the
article and nothing else:

* All six of the manifest's ``boilerplate_markers_must_be_absent`` are **gone**
  — ``Accept all cookies``, ``SPONSORED: Cut your cloud bill by 40%``,
  ``Trending right now``, ``Subscribe to our newsletter``,
  ``© 2026 Example Media Group`` and ``Follow us on social``.
* All six expected headings survive at the right level, the seven article
  paragraphs are intact, and the 7x5 summary table comes back as a real
  Markdown table.

That is the difference between this backend and ``markdownify_html``, which
keeps every one of those markers because stripping them is not a markup
converter's job. Both are correct at what they do, and
``tests/integration/test_web_backends.py`` asserts both, so the difference is
measured rather than asserted.

**Where it is the wrong choice.** Extraction is a judgement about what matters,
and a page whose content is not an article is a page it will judge wrongly. It
is built for editorial and documentation pages; on a link directory, a search
results page, or a page that is genuinely all navigation, it can return nothing
at all. When that happens this adapter fails rather than returning an empty
document, so the fallback chain hands over to ``markdownify_html``, and the
attempt chain shows it happened. Reach for ``--backend markdownify_html``
directly when you want the whole page, boilerplate included.

**Trafilatura's own fallbacks are switched off.** It will call out to
readability and justext when its primary algorithm is unsure, which would make
this backend's output depend on which *other* extractors happen to be installed
— the same objection that made MarkItDown run with plugins disabled in Phase 2.
A backend whose output depends on the environment cannot be described honestly
in ``docs/BACKENDS.md``. tokenmill has its own fallback chain; it is visible in
``ConversionResult.attempts`` and it names the backend that ran.

License: trafilatura is Apache-2.0, verified against the installed package
metadata (2.2.0). Its dependency tree carries one licence worth knowing about:
``courlan`` requires ``tld``, which is tri-licensed
``MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later``. That is a disjunction — the
recipient chooses — and tokenmill takes the MPL-1.1 option, which is
file-level copyleft like the ``certifi`` MPL-2.0 already accepted in Phase 1
and obliges us only to publish changes to ``tld``'s own files, of which we make
none. See ``docs/LICENSES.md``.
"""

from __future__ import annotations

from typing import Any, Final

from tokenmill.backends._common import (
    classify_failure,
    probe_module,
    warnings_as_conversion_warnings,
)
from tokenmill.backends.web._common import note_web_metrics, warn_if_client_rendered
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

__all__ = ["TrafilaturaConverter"]

#: Settings passed to ``trafilatura.extract`` on every conversion.
#:
#: Every one is set explicitly even where it matches today's default, because a
#: default that changes upstream changes our output silently, and
#: ``docs/BACKENDS.md`` describes behaviour we are supposed to be able to
#: reproduce.
_EXTRACT_OPTIONS: Final[dict[str, Any]] = {
    "output_format": "markdown",
    # Structure is worth keeping. RESEARCH.md Category 7 cites "LLMs Understand
    # Layout" (arXiv:2407.05750) measuring +8-33% F1 when layout survives, and
    # the repo's rule from it is "keep structure, strip boilerplate". Dropping
    # a table to save its pipe characters is the wrong side of that trade.
    "include_tables": True,
    "include_formatting": True,
    # Links are kept: a documentation page whose references have been deleted
    # has lost information a reader may need. Stripping them is available as a
    # deliberate choice through the `links` post-processor.
    "include_links": True,
    # Comment sections are boilerplate by any reading.
    "include_comments": False,
    # No YAML front matter. The pipeline records provenance on the result; a
    # backend writing metadata into the document itself would have it counted
    # as content.
    "with_metadata": False,
    # Trafilatura's internal fallback to readability and justext is off — see
    # the module docstring. tokenmill's own chain does this job visibly.
    "fast": True,
}


class TrafilaturaConverter(BaseConverter):
    """Extracts the main content of a web page as Markdown with Trafilatura.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="trafilatura",
        name="Trafilatura",
        description=(
            "Extracts a page's main content and discards navigation, banners, "
            "advertisements and footers. The right default for a web page; "
            "returns nothing on a page that is not an article."
        ),
        domains=(Domain.WEB,),
        input_formats=("html", "htm", "xhtml"),
        output_formats=(OutputFormat.MARKDOWN,),
        license="Apache-2.0",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/adbar/trafilatura",
        install_extra=None,
        priority=40,
    )

    def _probe(self) -> Availability:
        """Check that trafilatura is importable.

        Returns:
            Present when trafilatura is installed, otherwise a missing
            dependency with the install command.
        """
        return probe_module("trafilatura", hint="pip install trafilatura")

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Extract the source page's main content as Markdown.

        Args:
            source: The HTML to extract from. A URL source has already been
                fetched by the pipeline by the time it arrives here.
            options: Unused beyond what :class:`BaseConverter` already applied.
            context: Collects the extraction metrics and any warning.

        Returns:
            The extracted Markdown.

        Raises:
            CorruptSource: If the source has no readable content, or is empty.
            BackendFailed: If trafilatura finds no main content to extract, so
                that the fallback chain can offer the page to a backend that
                converts all of it.
            ConversionError: If trafilatura itself fails.
        """
        del options

        # Imported here, not at module scope: CONTRIBUTING.md rule 3.
        with warnings_as_conversion_warnings(context, activity="importing trafilatura"):
            import trafilatura

        try:
            html = source.read_text()
        except ValueError as exc:
            raise CorruptSource(
                f"{source.name} has no readable HTML content",
                backend_id=self.info.id,
                hint="trafilatura extracts from HTML files, bytes and fetched pages",
            ) from exc

        if not html.strip():
            raise CorruptSource(f"{source.name} is empty", backend_id=self.info.id)

        try:
            with warnings_as_conversion_warnings(context, activity="extracting with trafilatura"):
                extracted = trafilatura.extract(
                    html,
                    url=source.url,
                    **_EXTRACT_OPTIONS,
                )
        except ConversionError:
            raise
        except Exception as exc:
            raise classify_failure(exc, source=source, backend_id=self.info.id) from exc

        text = str(extracted) if extracted else ""
        note_web_metrics(context, html=html, output=text, strips_boilerplate=True)
        warn_if_client_rendered(
            context, html=html, source_name=source.name, backend_id=self.info.id
        )

        if not text.strip():
            # Deliberately a failure rather than an empty document with a
            # warning, which is how the document backends treat a scanned PDF.
            # The cases differ: a scanned PDF has no text for *anyone* to
            # extract, whereas a page trafilatura declined is a page another
            # backend can convert in full. Failing hands it to the chain, and
            # the user gets their page with `attempts:` showing what happened.
            raise BackendFailed(
                f"trafilatura found no main content in {source.name}; the page may be a "
                f"link directory, a search results page, or otherwise not an article",
                backend_id=self.info.id,
                hint=(
                    "try --backend markdownify_html to convert the whole page, boilerplate included"
                ),
            )
        return text
