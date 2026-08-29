"""Backends that run outside the tokenmill process.

Two different reasons put an adapter in here, and only one of them is about
licences:

* **Licence.** ``CONTRIBUTING.md`` rule 2: AGPL and GPL tools are never imported.
  PyMuPDF4LLM (AGPL-3.0) and Pandoc (GPL-2.0-or-later) are here for this reason,
  and :class:`~tokenmill.core.models.BackendInfo` will not let either of them
  claim in-process isolation.
* **Language.** A tool that is not Python cannot be imported at any price.
  LibreOffice is here for this reason; it is MPL-2.0 and permissive, and running
  it out of process carries no licence meaning at all. So are ``repomix``
  (TypeScript) and ``code2prompt`` (Rust), which live under ``backends/repo/``
  because that is the domain they serve.

The distinction is kept visible because the isolation column would otherwise
imply a licence constraint that is not there — and because the tools that are
out of process for language reasons are safe practice for the mechanism: getting
it wrong on an MIT tool carries no licence risk.

**Why this package is called ``external`` and not ``isolated``.** Defect N9:
this is a **process, language and licence boundary, and it is not a sandbox**.
There are no resource limits, no filesystem confinement and no network
namespace; a tool launched through here runs with exactly the access the user
has. "Isolation" is the word an operating system uses for containment, so it
invites a security reading this layer does not deserve, and three documents had
grown a paragraph apologising for the name. ``external`` says the true thing —
the converter runs outside this process — and says nothing about safety, so no
paragraph is needed.

The enum stayed :class:`~tokenmill.core.models.IsolationMode`, and
:attr:`~tokenmill.core.models.BackendInfo.isolation` stayed too. Its *values* —
``in-process``, ``subprocess``, ``service`` — are already precise about
mechanism rather than about protection, they are printed by ``tokenmill
backends`` and carried in ``--json`` output, and renaming a field of the Phase 1
contract is a breaking change with no user-visible gain. The package and the
prose were what oversold; those are what changed.
"""

from __future__ import annotations

__all__: list[str] = []
