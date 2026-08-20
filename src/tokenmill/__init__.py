"""tokenmill — one interface over open-source document, web, repo and prompt converters.

tokenmill turns four kinds of input into token-efficient text and reports exactly
how many tokens the conversion saved:

* documents (PDF, DOCX, PPTX, XLSX, EPUB, images, audio, email) -> Markdown
* web pages (URL or saved HTML) -> boilerplate-stripped Markdown
* code repositories (local path or Git URL) -> a single prompt-ready file
* prompts and raw text -> compressed text (opt-in, off by default)

Every conversion reports tokens before and tokens after under a tokenizer the
user chooses. That measurement is the point of the project, not a side feature.

This module deliberately exposes nothing but the version at Phase 0; the public
API lands in Phase 1 (see ``docs/DEVELOPMENT_PLAN.md``). Importing tokenmill
must never require an optional dependency, so keep this module free of
third-party imports.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.0.0"
