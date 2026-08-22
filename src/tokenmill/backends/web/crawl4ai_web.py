"""The ``crawl4ai`` backend: for pages that are only there once JavaScript runs.

Every other web backend parses the HTML a server sent. That is the right thing
almost always, and it is useless for a page whose content is assembled in the
browser: a single-page application, a documentation site that hydrates its body
from JSON, an article behind a client-side renderer. For those, the response
body genuinely does not contain the article, and no extractor can find what is
not there.

Crawl4AI drives a real Chromium through Playwright, waits for the page to
settle, and converts what the browser ended up displaying. That is its entire
contribution here, and it is why this is the one backend that declares
:attr:`~tokenmill.core.models.BackendInfo.fetches_urls`: the fetch *is* the
feature, and it cannot be done after the fact to a response somebody already
saved.

**Three deliberate constraints, because a browser is not a fetch.**

*It is never auto-selected.* :mod:`tokenmill.core.preferences` ranks it last
for every format it claims, so it has to be asked for by name. Launching a
browser inside a command a user thought was a download is the same mistake as
starting a several-hundred-megabyte model download, which Phase 2 settled for
docling.

*It requires ``--allow-network``, even on a local file.* A browser does not
retrieve one address; it executes whatever scripts the page carries and loads
whatever subresources they ask for, from anywhere. Rendering a saved HTML file
can therefore reach the network, which would break the guarantee that
converting a local file does not. So this backend asks for the broader
permission rather than the narrower one, and says why when it refuses.

*It lives behind its own extra.* ``pip install crawl4ai`` resolves to **94
packages and 677 MB** in our measurement, before Playwright downloads a browser
on top. That is far short of docling's 5.2 GB but far past what belongs in a
core install, and it follows the same rule: the heavy tool gets a group named
after itself, so ``pip install "tokenmill[web]"`` stays light.

**What it does on our corpus, including where it loses.** On
``tests/fixtures/boilerplate.html`` its pruning filter removes the navigation,
the trending rail, the social rail and the footer — but **leaves the cookie
banner, the sponsored advertisement and the newsletter block**, three of the
six markers the corpus says an extractor should remove. Trafilatura removes all
six. The pruning filter scores blocks by text density and link density rather
than identifying an article, so a prose-heavy advertisement scores like prose.
``tests/integration/test_web_backends.py`` asserts this, so an upstream
improvement fails the test and corrects the documentation.

The conclusion for a user is narrow and worth stating plainly: reach for this
backend when the page needs JavaScript, and expect to accept weaker extraction
in exchange. Trafilatura is the better extractor on any page that arrives
whole.

License: Crawl4AI is Apache-2.0 and Playwright is Apache-2.0, both verified
against the installed package metadata (0.9.2 and 1.62.0). A licence audit of
all 94 packages the install resolves to found no GPL, no AGPL, and no PyTorch.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
from typing import Any, Final

from tokenmill.backends._common import classify_failure, warnings_as_conversion_warnings
from tokenmill.backends.web._common import note_web_metrics, warn_if_client_rendered
from tokenmill.core.errors import BackendFailed, ConversionError, CorruptSource, NetworkRequired
from tokenmill.core.models import (
    Availability,
    BackendInfo,
    ConvertOptions,
    Domain,
    LicenseTier,
    OutputFormat,
    Source,
    SourceKind,
)
from tokenmill.core.protocol import BaseConverter, ConversionContext

__all__ = ["Crawl4AIConverter"]

#: Pruning threshold for the content filter that produces "fit" Markdown.
#: Crawl4AI's own documented default; left at it deliberately, because tuning a
#: threshold against our single fixture would be fitting to one page.
_PRUNE_THRESHOLD: Final = 0.48

#: What to tell a user whose Playwright browser is missing. The package
#: installing without a browser is the normal outcome of ``pip install``, so
#: this is the failure people will actually hit.
_BROWSER_HINT: Final = (
    "crawl4ai needs a Playwright browser; run 'python -m playwright install chromium' "
    "(or 'crawl4ai-setup') once"
)


class Crawl4AIConverter(BaseConverter):
    """Renders a page in a real browser and converts what it displayed.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="crawl4ai",
        name="Crawl4AI",
        description=(
            "Renders a page in a real Chromium so JavaScript runs, then "
            "converts it. Needs --allow-network and a browser; weaker "
            "extraction than trafilatura."
        ),
        domains=(Domain.WEB,),
        input_formats=("html", "htm", "xhtml", "url"),
        output_formats=(OutputFormat.MARKDOWN,),
        license="Apache-2.0",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/unclecode/crawl4ai",
        install_extra="crawl4ai",
        requires_network=True,
        fetches_urls=True,
        # Last for everything. Auto-selection must never start a browser.
        priority=-10,
    )

    def _probe(self) -> Availability:
        """Check that crawl4ai and Playwright are both importable.

        The browser itself is deliberately *not* probed. Locating a Playwright
        install means importing Playwright and asking its registry, which is
        neither cheap nor free of side effects, and this probe runs on every
        ``tokenmill backends`` listing. A missing browser is reported at
        conversion time instead, with the command that fixes it.

        Returns:
            Present when both packages are installed, otherwise a missing
            dependency with the install command.
        """
        for module, extra in (("crawl4ai", "crawl4ai"), ("playwright", "crawl4ai")):
            if importlib.util.find_spec(module) is None:
                return Availability.missing_dependency(
                    module, hint=f'pip install "tokenmill[{extra}]"'
                )
        return Availability.present()

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Render the source in a browser and return the resulting Markdown.

        Args:
            source: A URL, or a local HTML file to render from disk.
            options: Supplies ``allow_network``, which this backend requires,
                and the timeout.
            context: Collects the render metrics and any warning.

        Returns:
            The Markdown of the rendered page.

        Raises:
            NetworkRequired: If ``allow_network`` is false. A browser executes
                the page's scripts and loads whatever they ask for, so this is
                a broader permission than fetching one address and it is asked
                for explicitly.
            CorruptSource: If the source is neither a URL nor a local file.
            BackendFailed: If the browser is missing, or the render fails.
        """
        if not options.allow_network:
            raise NetworkRequired(
                f"crawl4ai renders {source.name} in a browser, which executes the page's "
                f"scripts and may load resources from anywhere",
                backend_id=self.info.id,
                hint=(
                    "pass --allow-network to permit that, or use --backend trafilatura, "
                    "which parses the page without running it"
                ),
            )

        target = self._target_url(source)

        with warnings_as_conversion_warnings(context, activity="importing crawl4ai"):
            # Imported here, not at module scope: CONTRIBUTING.md rule 3.
            import crawl4ai

        try:
            markdown, status, rendered_html = _render(crawl4ai, target, options.timeout_s)
        except ConversionError:
            raise
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                raise BackendFailed(
                    f"crawl4ai could not start a browser to render {source.name}",
                    backend_id=self.info.id,
                    hint=_BROWSER_HINT,
                ) from exc
            raise classify_failure(exc, source=source, backend_id=self.info.id) from exc

        context.note("rendered_url", target)
        context.note("javascript_rendered", True)
        if status is not None:
            context.note("http_status", status)

        # Measured against the *rendered* DOM rather than the response body,
        # which is the only comparison that means anything here: the whole
        # point of this backend is that the two differ.
        note_web_metrics(context, html=rendered_html, output=markdown, strips_boilerplate=True)
        # Against the *rendered* DOM. If a page still looks client-rendered after
        # a browser has run it, the scripts did not finish or the content needs
        # an interaction, and either way the reduction is not what it appears.
        warn_if_client_rendered(
            context, html=rendered_html, source_name=source.name, backend_id=self.info.id
        )

        if not markdown.strip():
            raise BackendFailed(
                f"crawl4ai rendered {source.name} but produced no text",
                backend_id=self.info.id,
                hint="the page may render nothing without interaction, or may have failed to load",
            )
        return markdown

    def _target_url(self, source: Source) -> str:
        """Return the address the browser should open.

        Args:
            source: The input.

        Returns:
            The URL, or a ``file://`` URL for a local file.

        Raises:
            CorruptSource: If the source is neither, since a browser has
                nothing to navigate to.
        """
        if source.kind is SourceKind.URL and source.url:
            return source.url
        if source.path is not None and source.path.is_file():
            return source.path.as_uri()
        if source.url:
            return source.url
        raise CorruptSource(
            f"crawl4ai needs a URL or a file on disk, and {source.name} is neither",
            backend_id=self.info.id,
            hint="pass an http(s) address, or a saved .html file",
        )


def _render(crawl4ai: Any, url: str, timeout_s: float) -> tuple[str, int | None, str]:
    """Drive Crawl4AI's async API from synchronous code.

    tokenmill is synchronous and Crawl4AI is not. :func:`asyncio.run` is the
    right call in a plain CLI process, and the wrong one inside anything that
    already has a running event loop — which the Phase 8 GUI will. Running the
    coroutine on its own loop in a worker thread is correct in both cases, so
    this does that unconditionally rather than behaving differently depending
    on the caller.

    Args:
        crawl4ai: The imported module, passed in so this function does not
            repeat the lazy import.
        url: The address to render.
        timeout_s: Wall-clock budget for the render.

    Returns:
        The Markdown, the HTTP status if the crawler reported one, and the
        rendered HTML.

    Raises:
        BackendFailed: If the crawl reports failure.
    """

    async def crawl() -> tuple[str, int | None, str]:
        browser = crawl4ai.BrowserConfig(headless=True, verbose=False)
        generator = crawl4ai.DefaultMarkdownGenerator(
            content_filter=crawl4ai.PruningContentFilter(
                threshold=_PRUNE_THRESHOLD, threshold_type="fixed"
            )
        )
        run = crawl4ai.CrawlerRunConfig(
            cache_mode=crawl4ai.CacheMode.BYPASS,
            verbose=False,
            markdown_generator=generator,
            page_timeout=int(timeout_s * 1000),
            # Load the caller's Markdown-free bytes through a real browser even
            # for a `file://` URL. Crawl4AI's default is to skip the browser
            # entirely for local files — see `_crawl` in its
            # `async_crawler_strategy`, which routes to the browser only when one
            # of a handful of flags is set — and without this the adapter would
            # silently return a parse of the response body. That is a worse
            # trafilatura with a 677 MB dependency attached, and it would make
            # every claim on this page about rendering untrue. Found by running
            # it against `tests/fixtures/jsrendered.html` and getting the
            # placeholder back.
            process_in_browser=True,
        )
        async with crawl4ai.AsyncWebCrawler(config=browser) as crawler:
            result = await crawler.arun(url=url, config=run)
        if not getattr(result, "success", False):
            message = str(getattr(result, "error_message", "") or "the crawl reported failure")
            raise BackendFailed(
                f"crawl4ai could not render {url}: {message}", backend_id="crawl4ai"
            )

        markdown = result.markdown
        # Prefer the pruned "fit" Markdown when the filter produced any. It is
        # what makes this an extractor rather than a renderer, and an empty
        # fit result on a page the filter found nothing in must fall back to
        # the whole page rather than to nothing.
        text = str(getattr(markdown, "fit_markdown", "") or "")
        if not text.strip():
            text = str(getattr(markdown, "raw_markdown", "") or str(markdown))
        return text, getattr(result, "status_code", None), str(getattr(result, "html", "") or "")

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(crawl())).result()
