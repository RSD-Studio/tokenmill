"""The format-to-backend preference map.

Phase 1 had one candidate per format, so ranking backends was a formality: a
single ``BackendInfo.priority`` and a deterministic tie-break were enough. Phase
2 installs five document backends that overlap heavily — four of them convert
PDFs and three convert every Office format — and "best" turns out to be a
different backend for each format. A single global priority cannot say that
``markitdown`` is the right choice for ``.pptx`` and the wrong one for ``.docx``,
so the ranking becomes per format.

**Every number below comes from running the backend on our own fixture corpus**,
not from ``docs/research/RESEARCH.md`` and not from a vendor's claim. The
observations behind each are written out in ``docs/BACKENDS.md``, quoted from the
real output, and the losing cases are recorded there too — a preference map that
only records the wins is a marketing document.

How the map interacts with the rest of selection:

* A number here **replaces** the backend's declared
  :attr:`~tokenmill.core.models.BackendInfo.priority` for that one format. A
  backend the map does not mention keeps its declared priority, so a third-party
  PDF backend that declares ``priority=100`` outranks everything here without
  anyone editing this file. The map is a default, not a gate.
* Ranking is not filtering. An unavailable backend is dropped by the registry
  before this ordering is applied, which is what makes the map and the fallback
  chain the same mechanism: uninstall the preferred backend and the next one
  runs.
* An explicit ``--backend`` ignores the map entirely. Phase 1 settled that
  substituting a backend the user did not ask for makes the measurement
  unattributable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from tokenmill.core.models import BackendInfo

__all__ = ["FORMAT_PREFERENCES", "effective_priority", "preference_rationale"]

#: Per-format backend rankings. Higher wins. See the module docstring for how
#: these combine with a backend's declared priority.
#:
#: The rationale for each format is in :data:`_RATIONALE` and, at length with
#: quoted output, in ``docs/BACKENDS.md``.
FORMAT_PREFERENCES: Final[Mapping[str, Mapping[str, int]]] = {
    # pdfplumber is the only backend that reproduces the 7x5 grid in
    # tables.pdf as a real Markdown table with all 35 cells. kreuzberg and
    # pypdf get twocolumn.pdf's reading order right where pdfplumber does not,
    # so they rank above markitdown, which loses on both counts. docling is
    # last on purpose: its PDF path downloads layout and table models on first
    # use, and auto-selection must never start a several-hundred-megabyte
    # download the user did not ask for. Ask for it by name.
    "pdf": {
        "pdfplumber": 60,
        "kreuzberg": 50,
        "markitdown": 40,
        "pypdf": 30,
        "docling": 10,
    },
    # docling is the only backend that keeps report.docx's title as a heading
    # *and* nests the H1s and H2s beneath it, giving three correct levels where
    # markitdown gives two and loses the title and kreuzberg collides the title
    # with the H1s. It also keeps the nested list item nested, and gives the
    # table a real header row where markitdown emits an empty one above it. It
    # needs no downloaded model for Office formats, so preferring it here costs
    # nothing a user did not already install.
    "docx": {"docling": 80, "markitdown": 60, "kreuzberg": 40},
    # markitdown is the only backend that keeps deck.pptx's speaker notes.
    "pptx": {"markitdown": 80, "docling": 50, "kreuzberg": 30},
    # markitdown and kreuzberg both emit one Markdown table per sheet under a
    # heading naming the sheet; docling drops the sheet names entirely.
    "xlsx": {"markitdown": 80, "kreuzberg": 60, "docling": 30},
    # HTML belongs to Phase 3, where trafilatura brings real boilerplate
    # extraction. The document backends handle HTML competently and are
    # reachable by name, but they rank below the core web backend so that
    # installing a documents extra cannot quietly change which backend
    # converts a web page — that would make Phase 1's recorded measurements
    # irreproducible.
    "html": {"markdownify_html": 50, "markitdown": 20, "kreuzberg": 15, "docling": 10},
    "htm": {"markdownify_html": 50, "markitdown": 20, "kreuzberg": 15, "docling": 10},
    "xhtml": {"markdownify_html": 50, "kreuzberg": 15, "docling": 10},
    # Tabular text: kreuzberg renders a Markdown table, markitdown emits the
    # rows as text.
    "csv": {"kreuzberg": 60, "markitdown": 40, "docling": 30},
}

#: One sentence per format explaining the ranking above, for the CLI and docs.
_RATIONALE: Final[Mapping[str, str]] = {
    "pdf": (
        "pdfplumber first: the only backend that recovers a bordered table as a "
        "Markdown table. kreuzberg and pypdf next: correct multi-column reading "
        "order. docling last: its PDF path downloads models on first use."
    ),
    "docx": (
        "docling first: the only backend that keeps the title as a heading and "
        "nests H1/H2 beneath it, and the only one that keeps a nested list "
        "nested and gives the table a real header row."
    ),
    "pptx": "markitdown first: the only backend that keeps speaker notes.",
    "xlsx": "markitdown and kreuzberg keep sheet names as headings; docling drops them.",
    "html": (
        "markdownify_html first: HTML is the web domain's, and an installed "
        "documents extra must not change which backend converts a page. Real "
        "boilerplate extraction arrives with trafilatura in Phase 3."
    ),
    "htm": (
        "markdownify_html first: HTML is the web domain's, and an installed "
        "documents extra must not change which backend converts a page."
    ),
    "xhtml": (
        "markdownify_html first: HTML is the web domain's, and an installed "
        "documents extra must not change which backend converts a page."
    ),
    "csv": "kreuzberg first: it renders a Markdown table where markitdown emits rows as text.",
}


def effective_priority(info: BackendInfo, source_format: str) -> int:
    """Return the priority to rank a backend by for one source format.

    Args:
        info: The backend's declared metadata.
        source_format: A lowercase extension without the dot, or one of the
            pseudo formats ``url`` / ``repo`` / ``text``.

    Returns:
        The number from :data:`FORMAT_PREFERENCES` when the map names this
        backend for this format, otherwise the backend's own declared
        :attr:`~tokenmill.core.models.BackendInfo.priority`.
    """
    ranked = FORMAT_PREFERENCES.get(source_format.lower())
    if ranked is None:
        return info.priority
    return ranked.get(info.id, info.priority)


def preference_rationale(source_format: str) -> str | None:
    """Return why the backends for a format are ordered the way they are.

    Args:
        source_format: A lowercase extension without the dot.

    Returns:
        One sentence, or ``None`` when the format has no explicit ranking and
        the declared priorities decide it.
    """
    return _RATIONALE.get(source_format.lower())
