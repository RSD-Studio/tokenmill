"""tokenmill — one interface over open-source document, web, repo and prompt converters.

tokenmill turns four kinds of input into token-efficient text and reports exactly
how many tokens the conversion saved:

* documents (PDF, DOCX, PPTX, XLSX, EPUB, images, audio, email) -> Markdown
* web pages (URL or saved HTML) -> boilerplate-stripped Markdown
* code repositories (local path or Git URL) -> a single prompt-ready file
* prompts and raw text -> compressed text (opt-in, off by default)

Every conversion reports tokens before and tokens after under a tokenizer the
user chooses. That measurement is the point of the project, not a side feature.

Typical use::

    from tokenmill import ConvertOptions, Source, convert

    result = convert(
        Source.from_path("page.html"),
        ConvertOptions(tokenizer="o200k_base"),
    )
    print(result.text)
    print(result.tokens_before, "->", result.tokens_after)

``result.tokens_before`` and ``result.tokens_after`` are ``None`` when no
tokenizer could be loaded — on an air-gapped machine, for instance, where a BPE
vocabulary cannot be downloaded. The conversion still succeeds and the warning
says why. tokenmill never substitutes an estimate for a measurement.

**Importing this module pulls in nothing but the standard library.** The data
model is built from dataclasses rather than pydantic, backends import their
dependencies lazily, and the CLI lives behind a console script, so
``import tokenmill`` stays free even in an environment where only the core tier
is installed. ``tests/unit/test_package.py`` enforces it.
"""

from __future__ import annotations

from tokenmill.core.errors import (
    BackendFailed,
    BackendUnavailable,
    ConfigError,
    ConversionError,
    CorruptSource,
    NetworkRequired,
    Timeout,
    TokenizerError,
    TokenizerNotFound,
    TokenizerUnavailable,
    TokenmillError,
    UnsupportedFormat,
)
from tokenmill.core.models import (
    Availability,
    AvailabilityStatus,
    BackendAttempt,
    BackendInfo,
    ConversionResult,
    ConvertOptions,
    Domain,
    ImageHandling,
    IsolationMode,
    LicenseTier,
    LinkHandling,
    OutputFormat,
    Source,
    SourceKind,
    StageCount,
    TokenCount,
)
from tokenmill.core.pipeline import Pipeline, convert
from tokenmill.core.protocol import BaseConverter, ConversionContext, Converter
from tokenmill.core.registry import Registry, default_registry

__all__ = [
    "Availability",
    "AvailabilityStatus",
    "BackendAttempt",
    "BackendFailed",
    "BackendInfo",
    "BackendUnavailable",
    "BaseConverter",
    "ConfigError",
    "ConversionContext",
    "ConversionError",
    "ConversionResult",
    "ConvertOptions",
    "Converter",
    "CorruptSource",
    "Domain",
    "ImageHandling",
    "IsolationMode",
    "LicenseTier",
    "LinkHandling",
    "NetworkRequired",
    "OutputFormat",
    "Pipeline",
    "Registry",
    "Source",
    "SourceKind",
    "StageCount",
    "Timeout",
    "TokenCount",
    "TokenizerError",
    "TokenizerNotFound",
    "TokenizerUnavailable",
    "TokenmillError",
    "UnsupportedFormat",
    "__version__",
    "convert",
    "default_registry",
]

__version__ = "0.1.0"
