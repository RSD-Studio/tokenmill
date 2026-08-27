"""Reading licences out of installed metadata, and classifying what they permit.

``CONTRIBUTING.md`` rule 2 is the rule this project's licence position rests on:
permissive tools may be imported into the tokenmill process, AGPL and GPL tools
never are. Until Phase 7 that rule was enforced in exactly one place —
:meth:`~tokenmill.core.models.BackendInfo.__post_init__` refuses to construct a
copyleft backend claiming in-process isolation — which checks what an adapter
*declares*. This module checks what is actually installed, so the two can be
compared and a declaration can be caught being wrong.

**Everything here reads the installed distribution's own metadata.** Not
``docs/research/RESEARCH.md``, not a project's README, not a prompt. Phase 2
found `RESEARCH.md` wrong about a dependency count, Phase 3 found it incomplete
about a licence tree, and Phase 5 found the package under a format's own GitHub
organisation was a stub whose ``encode()`` raised ``NotImplementedError``. The
package wins, every time.

Three things this module deliberately does **not** do:

* **It does not decide policy.** It reports what a licence is and which tier it
  falls in. Whether a given tier may be imported is
  :class:`~tokenmill.core.models.LicenseTier` and the rule in
  ``CONTRIBUTING.md``; whether a particular backend obeys it is
  ``tests/unit/test_license_isolation.py``.
* **It does not treat LGPL as copyleft.** LGPL exists precisely to permit use as
  a library without relicensing the caller, and the project's rule names AGPL and
  GPL. An LGPL distribution is reported with its expression intact so an auditor
  can see it, and it is not a violation. Said out loud because "it contains the
  letters GPL" is the reading that would otherwise be applied.
* **It does not resolve a disjunction for you silently.** ``tld`` ships
  ``MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later``: the recipient chooses one,
  and tokenmill takes MPL-1.1. :func:`classify` therefore reads ``OR`` as "the
  most permissive branch wins", which is what a disjunctive licence means, and
  :attr:`LicenseRecord.expression` keeps the whole string so the choice is
  visible rather than assumed. ``docs/LICENSES.md`` explains the choice in prose.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import Distribution, distributions, packages_distributions
from pathlib import Path
from typing import Final

from tokenmill.core.models import LicenseTier

__all__ = [
    "KNOWN_COPYLEFT_MODULES",
    "LicenseRecord",
    "audit_installed",
    "classify",
    "copyleft_violations",
    "distribution_for_module",
    "imported_top_level_modules",
    "tier_for_module",
]

#: SPDX identifiers, and the free-text spellings that mean them, which oblige us
#: to release our own source if we link the code into our process.
#:
#: ``LGPL`` is excluded on purpose and the module docstring says why. The
#: negative lookahead is what does it: ``GPL`` matches, ``LGPL`` does not.
_COPYLEFT_RE: Final = re.compile(
    r"(?<![A-Za-z])(?:A?GPL|GNU\s+(?:Affero\s+)?General\s+Public\s+License)(?![a-z])",
    re.IGNORECASE,
)

#: Spellings that mean "you may not use this commercially". Excluded by default
#: under `CONTRIBUTING.md` rule 2; the Jina ReaderLM weights are the example
#: `docs/LICENSES.md` names.
#:
#: Ordered before :data:`_PURCHASABLE_RE` in :func:`classify` because
#: "non-commercial" contains "commercial" and would otherwise match it.
_NON_COMMERCIAL_RE: Final = re.compile(
    r"(?:non[-\s]?commercial|CC[-\s]?BY[-\s]?NC|\bRAIL\b)",
    re.IGNORECASE,
)

#: A branch of a disjunction that has to be **bought**, and which tokenmill
#: therefore does not hold.
#:
#: Found by reading PyMuPDF4LLM's installed metadata rather than by thinking
#: about it. It states::
#:
#:     Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License
#:
#: A naive disjunction rule — "the recipient chooses, so the most permissive
#: branch wins" — reads the second half as unencumbered and calls the package
#: permissive. It is not: the free branch is AGPL-3.0 and the other one costs
#: money nobody here has spent. Written in SPDX form
#: (``AGPL-3.0-only OR LicenseRef-Artifex-Commercial``) that mistake classified
#: PyMuPDF4LLM — the flagship copyleft tool this whole phase exists to isolate —
#: as permissive, which would have let it be imported.
#:
#: `tld` is the case this must not break: ``MPL-1.1 OR GPL-2.0-only OR
#: LGPL-2.1-or-later`` has three branches, all genuinely available, and taking
#: MPL-1.1 is a real choice rather than an unbought one.
_PURCHASABLE_RE: Final = re.compile(
    r"(?:\bcommercial\b|\bproprietary\b|\benterprise\s+licen[cs]e\b)",
    re.IGNORECASE,
)

#: Top-level module names known to belong to a copyleft distribution, whether or
#: not that distribution is installed here.
#:
#: The metadata audit can only classify what is present. This table is what makes
#: the *static* check work — a Phase 9 adapter that grows ``import fitz`` must
#: fail on a CPU-only developer machine where PyMuPDF was never installed, not
#: only on a machine that happens to have it.
#:
#: Every entry names where the licence was read from. Nothing goes in here from
#: memory.
KNOWN_COPYLEFT_MODULES: Final[Mapping[str, str]] = {
    # PyMuPDF and its Markdown wrapper. Both state, in the installed
    # distribution metadata of version 1.28.2 read here on 2026-08-26:
    #   "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License"
    # The branch tokenmill holds is the AGPL one; see _PURCHASABLE_RE.
    "fitz": "PyMuPDF 1.28.2, AGPL-3.0 or Artifex Commercial",
    "pymupdf": "PyMuPDF 1.28.2, AGPL-3.0 or Artifex Commercial",
    "pymupdf4llm": "pymupdf4llm 1.28.2, AGPL-3.0 or Artifex Commercial",
    # Phase 9's GPU tier. Named now so an adapter written then cannot import one
    # by accident; `docs/LICENSES.md` carries the same list.
    "marker": "marker-pdf, GPL-3.0",
    "surya": "surya-ocr, GPL-3.0",
    # RESEARCH.md's appendix tools, none of which is wrapped.
    "firecrawl": "Firecrawl core, AGPL-3.0",
    "omniparse": "omniparse, GPL",
    "html2text": "html2text, GPL-3.0",
}


@dataclass(frozen=True, slots=True)
class LicenseRecord:
    """What one installed distribution says about its own licence.

    Attributes:
        name: The distribution name, as its metadata spells it.
        version: The installed version.
        expression: The licence as the package states it — an SPDX expression, a
            classifier, or free text — kept verbatim so a disjunction or an
            unusual spelling stays visible.
        tier: What that expression permits, under :func:`classify`.
        source: Which metadata field the expression came from, so an audit can
            be re-derived rather than trusted.
    """

    name: str
    version: str
    expression: str
    tier: LicenseTier
    source: str

    @property
    def is_copyleft(self) -> bool:
        """Whether this distribution may not be imported into our process.

        Returns:
            True for AGPL and GPL. LGPL is not copyleft for this purpose; see
            the module docstring.
        """
        return self.tier is LicenseTier.COPYLEFT


def classify(expression: str) -> LicenseTier:
    """Classify a licence expression into the tier it permits.

    Handles SPDX disjunction: ``A OR B`` lets the recipient choose, so the tier
    is the **most permissive** branch. Conjunction (``AND``) means every part
    applies, so the tier is the **least permissive** branch.

    Args:
        expression: An SPDX expression, a trove classifier's tail, or free text.

    Returns:
        The tier. An empty or unrecognised expression is
        :attr:`~tokenmill.core.models.LicenseTier.PERMISSIVE`, which is
        deliberate: this function is one half of the check and
        :func:`audit_installed` reports the raw expression beside it, so an
        unreadable licence surfaces as a licence an auditor has to read rather
        than as a false accusation.
    """
    text = expression.strip()
    if not text:
        return LicenseTier.PERMISSIVE

    # Disjunction: the recipient picks, so one permissive branch is enough — but
    # only among the branches actually on offer. A branch that has to be bought
    # is not one tokenmill holds; see _PURCHASABLE_RE, which exists because
    # PyMuPDF4LLM's real metadata is exactly this shape.
    #
    # Case-insensitive on purpose. SPDX spells the operators in capitals and
    # free-text metadata does not: PyMuPDF4LLM writes "or" in a sentence, and a
    # case-sensitive split got the right answer there by luck while getting the
    # SPDX spelling of the same licence wrong.
    if re.search(r"\bOR\b", text, re.IGNORECASE):
        branches = re.split(r"\bOR\b", text, flags=re.IGNORECASE)
        available = [b for b in branches if not _PURCHASABLE_RE.search(b)]
        if not available:
            # Every way to use this costs money, so it is not ours to import on
            # any terms. The most conservative tier, rather than a guess.
            return LicenseTier.NON_COMMERCIAL
        return min((classify(branch) for branch in available), key=_permissiveness)

    if re.search(r"\bAND\b", text, re.IGNORECASE):
        branches = re.split(r"\bAND\b", text, flags=re.IGNORECASE)
        return max((classify(branch) for branch in branches), key=_permissiveness)

    # Non-commercial before purchasable: "non-commercial" contains "commercial".
    if _NON_COMMERCIAL_RE.search(text):
        return LicenseTier.NON_COMMERCIAL
    if _COPYLEFT_RE.search(text):
        return LicenseTier.COPYLEFT
    if _PURCHASABLE_RE.search(text):
        # Not a disjunction, so there is no free branch to fall back to. A
        # licence that must be bought is not open source at all, which
        # CONTRIBUTING.md rule 1 excludes before rule 2 is even reached.
        return LicenseTier.NON_COMMERCIAL
    return LicenseTier.PERMISSIVE


def _permissiveness(tier: LicenseTier) -> int:
    """Rank tiers so ``min`` is the most permissive.

    Args:
        tier: The tier to rank.

    Returns:
        0 for permissive, 1 for copyleft, 2 for non-commercial.
    """
    return {
        LicenseTier.PERMISSIVE: 0,
        LicenseTier.COPYLEFT: 1,
        LicenseTier.NON_COMMERCIAL: 2,
    }[tier]


def _read_expression(dist: Distribution) -> tuple[str, str]:
    """Pull the best available licence statement out of one distribution.

    Modern packaging metadata carries ``License-Expression`` (PEP 639) and it is
    authoritative when present. Older packages carry trove classifiers, which are
    coarse but structured. Oldest of all is the free-text ``License`` field,
    which may be anything from ``MIT`` to a full licence body.

    Args:
        dist: The installed distribution.

    Returns:
        The expression and the name of the field it came from.
    """
    meta = dist.metadata

    # `.get()` rather than indexing, and the type: ignore is the price.
    #
    # `PackageMetadata.__getitem__` returning None for a missing header is
    # deprecated — "Implicit None on return values is deprecated and will raise
    # KeyErrors" — and under this project's `filterwarnings = ["error"]` that is
    # not a warning, it is a failure. Indexing was the first thing written here
    # because typeshed's PackageMetadata protocol declares `__getitem__` and not
    # `get`, so mypy accepted it; CI failed five tests on py3.12 and py3.13 with
    # it. The runtime object is an `email.message.Message` and has `.get()`.
    #
    # Trap 2 in the handover, exactly: mypy pushed towards the deprecated API and
    # only the matrix caught it.
    expression = meta.get("License-Expression")  # type: ignore[attr-defined]
    if expression and expression.strip():
        return expression.strip(), "License-Expression"

    classifiers = [
        line.split("::")[-1].strip()
        for line in (meta.get_all("Classifier") or [])
        if line.startswith("License ::")
    ]
    if classifiers:
        return " AND ".join(classifiers), "Classifier"

    legacy = meta.get("License")  # type: ignore[attr-defined]
    if legacy and legacy.strip():
        # A free-text License field is sometimes the entire licence body. Only
        # the first line is a name; the rest is the text of the licence and
        # matching "GPL" inside a paragraph of MIT boilerplate would be a false
        # positive. Kreuzberg's metadata is exactly this shape.
        first = legacy.strip().splitlines()[0].strip()
        return (first or legacy.strip()[:80]), "License"

    return "", "unstated"


def audit_installed(dists: Iterable[Distribution] | None = None) -> tuple[LicenseRecord, ...]:
    """Read and classify the licence of every installed distribution.

    Args:
        dists: The distributions to audit. Defaults to everything importable in
            this environment. Passed explicitly by the tests, which feed it a
            synthetic distribution to prove the check catches one.

    Returns:
        One record per distribution, sorted by name, case-insensitively.
    """
    source = distributions() if dists is None else dists
    records: list[LicenseRecord] = []
    for dist in source:
        name = dist.metadata["Name"]
        if not name:
            # A malformed .dist-info with no Name. Skipping is right: there is
            # nothing to report it as, and it cannot be imported by name either.
            continue
        expression, field = _read_expression(dist)
        records.append(
            LicenseRecord(
                name=name,
                version=dist.version or "unknown",
                expression=expression,
                tier=classify(expression),
                source=field,
            )
        )
    return tuple(sorted(records, key=lambda r: r.name.lower()))


def copyleft_violations(
    records: Iterable[LicenseRecord],
    *,
    allowed: Iterable[str] = (),
) -> tuple[LicenseRecord, ...]:
    """Return the installed distributions that must not be importable.

    Args:
        records: The audit to filter, from :func:`audit_installed`.
        allowed: Distribution names permitted despite classifying as copyleft.
            Every entry needs a written reason in ``docs/LICENSES.md``; the test
            that calls this asserts the list is short and that each name is
            documented there.

    Returns:
        The violating records, in the order given.
    """
    exempt = {name.lower().replace("_", "-") for name in allowed}
    return tuple(
        record
        for record in records
        if record.is_copyleft and record.name.lower().replace("_", "-") not in exempt
    )


@lru_cache(maxsize=1)
def _module_to_distribution() -> Mapping[str, tuple[str, ...]]:
    """Map every importable top-level module to the distributions providing it.

    Cached because it walks the whole environment and the answer cannot change
    within a process without an install.

    Returns:
        Module name to distribution names.
    """
    return {module: tuple(names) for module, names in packages_distributions().items()}


def distribution_for_module(module: str) -> str | None:
    """Return the distribution that provides an importable top-level module.

    Args:
        module: A top-level module name, such as ``trafilatura``.

    Returns:
        The distribution's name, or ``None`` when the module is not installed or
        is part of the standard library.
    """
    providers = _module_to_distribution().get(module)
    return providers[0] if providers else None


def tier_for_module(module: str) -> LicenseTier | None:
    """Classify the licence of whatever provides a top-level module.

    Consults :data:`KNOWN_COPYLEFT_MODULES` first, so a module that is *not*
    installed here still answers correctly. That is the whole point: an adapter
    that grows ``import fitz`` must be caught on a machine where PyMuPDF was
    never installed, which is every machine this project's CI runs on.

    Args:
        module: A top-level module name.

    Returns:
        The tier, or ``None`` when the module is neither known to be copyleft nor
        installed — a standard-library module, or simply absent.
    """
    if module in KNOWN_COPYLEFT_MODULES:
        return LicenseTier.COPYLEFT

    name = distribution_for_module(module)
    if name is None:
        return None
    for record in audit_installed():
        if record.name == name:
            return record.tier
    return None


def imported_top_level_modules(path: Path) -> frozenset[str]:
    """Return every top-level module a Python file imports, without importing it.

    Parsed rather than executed, for the obvious reason: this is used to prove
    that a module does *not* pull in a copyleft package, and importing it to find
    out would be the very thing being checked for.

    Both statement forms are covered, at any nesting depth — which matters here,
    because ``CONTRIBUTING.md`` rule 3 puts every heavy import *inside*
    ``_convert()`` rather than at module level. A scan that only looked at the
    top of the file would find nothing in any adapter in this project.

    Args:
        path: The Python file to scan.

    Returns:
        The top-level names, so ``import a.b.c`` and ``from a.b import d`` both
        yield ``a``. Relative imports are excluded: they cannot reach a
        third-party package.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                found.add(node.module.split(".")[0])
    return frozenset(found)
