"""Web and HTML backends.

Four backends. ``trafilatura`` extracts a page's article and is the default;
``readability`` is an independent second extraction; ``markdownify_html``
converts the whole page faithfully, boilerplate included; ``crawl4ai`` drives a
real browser for pages that only exist once JavaScript has run.

``fetch`` holds the URL-retrieval policy they all share, and ``_common`` holds
the boilerplate metric that makes an extractor's output comparable with a markup
converter's.
"""

from __future__ import annotations

__all__: list[str] = []
