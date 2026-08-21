"""The ``markdownify_html`` reference backend: HTML to Markdown, faithfully.

This is the second of Phase 1's two deliberately trivial backends. Where
``plaintext`` proves the framework with a converter that does nothing, this one
proves it with a converter that has a real third-party dependency, a real
optional import, and a real failure mode.

**What it does and does not do.** It converts HTML markup to Markdown. It does
*not* strip boilerplate: navigation, cookie banners, advertisements and footers
all survive, because they are ordinary HTML elements and this is a faithful
markup converter. On ``tests/fixtures/boilerplate.html`` it removes about half
the characters — all of it markup, script and style — and every navigation link
is still there afterwards.

Boilerplate removal is Trafilatura's job and arrives in Phase 3, where the
70-90% reduction the literature reports (``docs/research/RESEARCH.md``,
Category 7) becomes measurable. Do not read this backend's output as evidence
for that number; it is a different operation.

License: markdownify is MIT (``docs/research/RESEARCH.md``, Category 4). It is
permissive, so it may be imported into our process. It pulls in
BeautifulSoup 4 and parses with the standard library's ``html.parser``, so it
adds no compiled dependency to the core install.
"""

from __future__ import annotations

import importlib.util
from typing import Any, Final

from tokenmill.core.errors import BackendFailed, CorruptSource
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

__all__ = ["MarkdownifyHtmlConverter"]

#: Options passed to markdownify on every conversion.
#:
#: ATX headings (``## Heading``) rather than markdownify's setext default: they
#: survive past level two, and they are what every downstream Markdown consumer
#: expects. Everything else is left at markdownify's defaults on purpose — a
#: reference adapter should be a thin wrapper, not a pile of opinions.
_MARKDOWNIFY_OPTIONS: Final[dict[str, Any]] = {"heading_style": "ATX"}


class MarkdownifyHtmlConverter(BaseConverter):
    """Converts HTML to Markdown with markdownify.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="markdownify_html",
        name="markdownify (HTML)",
        description=(
            "Converts HTML markup to Markdown. Faithful, not selective: "
            "boilerplate survives. Use trafilatura (Phase 3) to strip it."
        ),
        domains=(Domain.WEB,),
        input_formats=("html", "htm", "xhtml"),
        output_formats=(OutputFormat.MARKDOWN,),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/matthewwithanm/python-markdownify",
        install_extra=None,
        priority=10,
    )

    def _probe(self) -> Availability:
        """Check that markdownify is importable.

        Uses :func:`importlib.util.find_spec` rather than an import: the probe
        runs for every ``tokenmill backends`` listing and must stay cheap.

        Returns:
            Present when markdownify is installed, otherwise a missing
            dependency with the install command.
        """
        if importlib.util.find_spec("markdownify") is None:
            return Availability.missing_dependency("markdownify", hint="pip install markdownify")
        return Availability.present()

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Convert the source's HTML to Markdown.

        Args:
            source: The HTML to convert.
            options: Unused beyond what :class:`BaseConverter` already applied.
            context: Collects size metadata and any warning.

        Returns:
            The Markdown.

        Raises:
            CorruptSource: If the source has no readable content, or contains no
                HTML at all.
            BackendFailed: If markdownify itself raises.
        """
        del options

        # Imported here, not at module scope: CONTRIBUTING.md rule 3 requires a
        # backend module to import cleanly with its dependency absent, so that a
        # missing dependency is a greyed-out row rather than a startup crash.
        import markdownify

        try:
            html = source.read_text()
        except ValueError as exc:
            raise CorruptSource(
                f"{source.name} has no readable HTML content",
                backend_id=self.info.id,
                hint="markdownify_html converts HTML files, bytes and literal text",
            ) from exc

        if not html.strip():
            raise CorruptSource(
                f"{source.name} is empty",
                backend_id=self.info.id,
            )

        try:
            markdown = markdownify.markdownify(html, **_MARKDOWNIFY_OPTIONS)
        except Exception as exc:
            raise BackendFailed(
                f"markdownify could not parse {source.name}: {type(exc).__name__}: {exc}",
                backend_id=self.info.id,
            ) from exc

        text = str(markdown)
        if not text.strip():
            # An empty conversion exits zero and looks like success. It is not:
            # something was handed in and nothing came out. Say so loudly.
            context.warn(
                f"{source.name} converted to an empty document; it may contain no "
                f"text outside scripts and styles"
            )

        context.note("html_characters", len(html))
        context.note("markdown_characters", len(text))
        context.note("strips_boilerplate", False)
        return text
