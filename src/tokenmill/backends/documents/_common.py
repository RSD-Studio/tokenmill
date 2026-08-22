"""Compatibility re-export of the shared adapter plumbing.

The helpers here were written in Phase 2, when documents were the only tier
that had adapters. Phase 3 and Phase 4 add web and repository adapters that
need the same behaviour — the same availability probe, the same mapping from a
library's own exception onto the tokenmill taxonomy, the same "an empty
conversion is not a success" warning — so the module moved up one level to
:mod:`tokenmill.backends._common`, where its name is true of all three tiers.

This module stays because other code imports it: the five document adapters did
until this change, ``tests/unit/test_documents_common.py`` still does, and any
third-party adapter written against ``docs/ADDING_A_BACKEND.md`` before Phase 3
would too. Removing it would break those for no gain. New code should import
from :mod:`tokenmill.backends._common`.
"""

from __future__ import annotations

from tokenmill.backends._common import (
    classify_failure,
    missing_binary_note,
    probe_module,
    render_markdown_table,
    source_as_file,
    warn_on_empty_output,
    warnings_as_conversion_warnings,
)

__all__ = [
    "classify_failure",
    "missing_binary_note",
    "probe_module",
    "render_markdown_table",
    "source_as_file",
    "warn_on_empty_output",
    "warnings_as_conversion_warnings",
]
