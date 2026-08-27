"""Backends that run outside the tokenmill process.

Two different reasons put an adapter in here, and only one of them is about
licences:

* **Licence.** ``CONTRIBUTING.md`` rule 2: AGPL and GPL tools are never imported.
  PyMuPDF4LLM (AGPL-3.0) and Pandoc (GPL-2.0-or-later) are here for this reason,
  and :class:`~tokenmill.core.models.BackendInfo` will not let either of them
  claim in-process isolation.
* **Language.** A tool that is not Python cannot be imported at any price.
  LibreOffice is here for this reason; it is MPL-2.0 and permissive, and its
  isolation carries no licence meaning at all. So are ``repomix`` (TypeScript)
  and ``code2prompt`` (Rust), which live under ``backends/repo/`` because that is
  the domain they serve.

The distinction is kept visible because the isolation column would otherwise
imply a licence constraint that is not there — and because the tools that are
isolated for language reasons are safe practice for the mechanism: getting the
isolation wrong on an MIT tool carries no licence risk.
"""

from __future__ import annotations

__all__: list[str] = []
