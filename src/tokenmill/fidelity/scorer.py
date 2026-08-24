"""Scoring converted text against a fixture's hand-labelled ground truth.

This is the measuring instrument the rest of the token-reduction work is built
against. Phase 5 adds post-processors that each strip something; Phase 6 adds a
compressor that strips a great deal. Every one of them can be measured as a win
in tokens, and the cost is invisible unless something goes looking for it.

Six components, each answering one question that ``ground_truth.json`` already
carries the answer to:

============================ ==================================================
``heading_recall``           Of the headings ground truth says exist, how many
                             survive *as headings*, at the right level.
``content_recall``           Of the sentences ground truth marks
                             ``must_contain``, how many survive.
``table_integrity``          Cells recovered, and whether they are still in a
                             table rather than flattened into prose.
``structure_retention``      List markers, code fences and link targets kept.
``boilerplate_rejection``    Of the markers ground truth says must be absent,
                             how many are.
``reading_order``            Where ground truth carries ordered sentinels,
                             whether they come back ascending.
============================ ==================================================

**The empty-document rule, and why it is a special case.** An empty string
contains no boilerplate, so the arithmetic for ``boilerplate_rejection`` scores
it 1.0 — a converter that destroyed the document is credited with perfect
extraction. That is precisely the failure ``benchmarks/README.md`` names,
reappearing *inside* the instrument built to catch it. So a document with no
non-whitespace content scores 0.0 on every component that has ground truth, and
says so. Crediting a total loss for what it did not emit is not a measurement.

**Recall and rejection are a pair.** Neither alone says extraction worked.
``markdownify_html`` keeps the whole page, so it scores high recall and almost
no rejection; a converter that emitted only the cookie banner would score the
reverse. Both are reported, always, and the overall averages them — which is
also why :meth:`~tokenmill.fidelity.models.FidelityScore.overall` carries the
names of what composed it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from tokenmill.fidelity import markdown as md
from tokenmill.fidelity.models import COMPONENTS, ComponentScore, FidelityScore

__all__ = ["score"]

#: How many missing items a component reports by name before it stops listing.
#: Enough to act on, few enough to print.
_MAX_MISSING: Final = 8


def score(
    text: str,
    truth: Mapping[str, Any],
    *,
    fixture: str,
    backend_id: str | None = None,
) -> FidelityScore:
    """Score converted text against one fixture's ground truth.

    Args:
        text: The converted text to assess.
        truth: That fixture's entry from ``ground_truth.json``.
        fixture: The fixture's name, carried onto the result for reporting.
        backend_id: The backend that produced ``text``, when known. Recorded,
            never inferred.

    Returns:
        The score. Every component in
        :data:`~tokenmill.fidelity.models.COMPONENTS` is present; those without
        ground truth carry ``None`` rather than being omitted, so a reader can
        see that the axis was considered and did not apply.
    """
    empty = not text.strip()
    measured = {name: scorer(text, truth) for name, scorer in _SCORERS.items()}
    # Built in COMPONENTS order rather than in whatever order the scorers were
    # declared, so adding a component to one and forgetting the other is a
    # KeyError here rather than a quietly reordered report for every reader.
    components = tuple(
        _zero_if_scored(measured[name]) if empty else measured[name] for name in COMPONENTS
    )
    return FidelityScore(fixture=fixture, components=components, backend_id=backend_id)


def _zero_if_scored(component: ComponentScore) -> ComponentScore:
    """Collapse a scored component to zero for an empty document.

    Args:
        component: The component as measured.

    Returns:
        The component with a zero score and an explanation, or unchanged when
        it had no ground truth to score against — an axis that did not apply
        does not start applying because the document is empty.
    """
    if not component.scored:
        return component
    return ComponentScore(
        component=component.component,
        score=0.0,
        expected=component.expected,
        found=0,
        detail=(
            "the document has no content, so nothing survived and nothing is credited as removed"
        ),
        missing=component.missing,
    )


def _absent(component: str, reason: str) -> ComponentScore:
    """Build a component that did not apply to this fixture.

    Args:
        component: The axis name.
        reason: Why there was nothing to measure.

    Returns:
        An unscored component carrying the reason.
    """
    return ComponentScore(component=component, score=None, detail=reason)


def _strings(value: Any) -> tuple[str, ...]:
    """Coerce a ground-truth value to a tuple of strings.

    Args:
        value: The raw ground-truth value.

    Returns:
        The strings it contains, empty when it is not a list of strings.
    """
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _heading_recall(text: str, truth: Mapping[str, Any]) -> ComponentScore:
    """Score how many expected headings survived as headings.

    Ground truth carries headings in two shapes: a plain list of titles, and a
    list of ``[title, level]`` pairs for the fixtures where the level is known
    (``report.docx`` has a title at level 0 and sections beneath it). Where a
    level is given it is enforced, mapping ground-truth level *n* onto Markdown
    ``#`` repeated *n + 1* times, because a heading that came back one rank out
    has lost the hierarchy that made it useful.

    A heading found only as ordinary text does **not** count as recovered — the
    heading did not survive, its words did. That distinction is the whole
    measurement: ``pdfplumber`` emits ``tables.pdf``'s section titles as plain
    lines and ``kreuzberg`` emits one of them as ``#``, and a scorer that
    counted text would call those equal. The count that did survive as text is
    reported in the detail, because it is the actionable half.

    Args:
        text: The converted text.
        truth: The fixture's ground truth.

    Returns:
        The component, or an unscored one when the fixture lists no headings.
    """
    raw = truth.get("expected_headings")
    if not isinstance(raw, list) or not raw:
        return _absent("heading_recall", "this fixture's ground truth lists no headings")

    expected: list[tuple[str, int | None]] = []
    for entry in raw:
        if isinstance(entry, str):
            expected.append((entry, None))
        elif isinstance(entry, list) and len(entry) == 2 and isinstance(entry[0], str):
            level = entry[1] if isinstance(entry[1], int) else None
            expected.append((entry[0], level))

    if not expected:
        return _absent("heading_recall", "this fixture's ground truth lists no headings")

    found_headings = md.headings(text)
    body = md.normalise(text).casefold()
    missing: list[str] = []
    as_text_only = 0
    recovered = 0

    for title, level in expected:
        needle = md.normalise(title).casefold()
        matches = [h for h in found_headings if needle in md.normalise(h.title).casefold()]
        wanted_level = None if level is None else level + 1
        if matches and (wanted_level is None or any(h.level == wanted_level for h in matches)):
            recovered += 1
            continue
        if matches:
            # Present as a heading, but not at the rank ground truth records.
            missing.append(f"{title} (found at level {matches[0].level}, expected {wanted_level})")
            continue
        missing.append(title)
        if needle in body:
            as_text_only += 1

    detail = f"{recovered} of {len(expected)} headings recovered as headings"
    if as_text_only:
        detail += f"; {as_text_only} present as plain text but not marked up as headings"
    return ComponentScore(
        component="heading_recall",
        score=recovered / len(expected),
        expected=len(expected),
        found=recovered,
        detail=detail,
        missing=tuple(missing[:_MAX_MISSING]),
    )


def _content_recall(text: str, truth: Mapping[str, Any]) -> ComponentScore:
    """Score how much of the content ground truth requires survived.

    Args:
        text: The converted text.
        truth: The fixture's ground truth.

    Returns:
        The component, or an unscored one when the fixture names no required
        content.
    """
    required = _strings(truth.get("must_contain"))
    if not required:
        return _absent("content_recall", "this fixture's ground truth names no required content")

    body = md.normalise(text).casefold()
    present = [needle for needle in required if md.normalise(needle).casefold() in body]
    missing = [needle for needle in required if needle not in present]
    return ComponentScore(
        component="content_recall",
        score=len(present) / len(required),
        expected=len(required),
        found=len(present),
        detail=f"{len(present)} of {len(required)} required passages present",
        missing=tuple(missing[:_MAX_MISSING]),
    )


def _table_integrity(text: str, truth: Mapping[str, Any]) -> ComponentScore:
    """Score whether a table came back as a table.

    Two measurements, chosen by what ground truth offers, and the detail always
    says which one ran:

    * **By value.** When ground truth records actual cell values
      (``table_header`` and ``table_first_column``), the score is the fraction
      of those values found *inside a parsed Markdown table*. This is the
      strong form: it catches a converter that keeps every word but loses the
      grid, which is exactly what ``docs/BACKENDS.md`` documents Kreuzberg
      doing to ``tables.pdf``.
    * **By shape.** Otherwise the score is how much of the expected cell count
      came back inside tables, capped at 1.0, because a converter that
      helpfully splits one table into two has not lost anything.

    Args:
        text: The converted text.
        truth: The fixture's ground truth.

    Returns:
        The component, or an unscored one when the fixture has no table.
    """
    rows = truth.get("table_rows_including_header")
    columns = truth.get("table_columns")
    declared_cells = truth.get("table_cells")
    if isinstance(declared_cells, int):
        expected_cells = declared_cells
    elif isinstance(rows, int) and isinstance(columns, int):
        expected_cells = rows * columns
    else:
        return _absent("table_integrity", "this fixture's ground truth records no table")

    found_tables = md.tables(text)
    in_tables = {md.normalise(cell).casefold() for table in found_tables for cell in table.cells}

    known = [*_strings(truth.get("table_header")), *_strings(truth.get("table_first_column"))]
    if known:
        present = [value for value in known if md.normalise(value).casefold() in in_tables]
        missing = [value for value in known if value not in present]
        return ComponentScore(
            component="table_integrity",
            score=len(present) / len(known),
            expected=len(known),
            found=len(present),
            detail=(
                f"{len(present)} of {len(known)} known cell values found inside a Markdown "
                f"table; {len(found_tables)} table(s) parsed from the output"
            ),
            missing=tuple(missing[:_MAX_MISSING]),
        )

    # Empty cells are not recovered cells. MarkItDown emits `report.docx`'s
    # table with an invented blank header row and the real header demoted to a
    # body row; counting those three blanks would score the defect as though it
    # had recovered extra data. Capped at 1.0 because a converter that splits
    # one table into two has not lost anything.
    found_cells = sum(1 for table in found_tables for cell in table.cells if cell.strip())
    return ComponentScore(
        component="table_integrity",
        score=min(found_cells / expected_cells, 1.0) if expected_cells else 0.0,
        expected=expected_cells,
        found=found_cells,
        detail=(
            f"{found_cells} of {expected_cells} expected cells came back inside "
            f"{len(found_tables)} parsed table(s); ground truth records no cell values, "
            f"so this is a shape check rather than a value check"
        ),
    )


def _structure_retention(text: str, truth: Mapping[str, Any]) -> ComponentScore:
    """Score whether list markers, code fences and link targets survived.

    Every element ground truth names counts once, and an element counts as
    retained only when it comes back *as that kind of structure*: a bullet as a
    list item, not as a sentence; a link target inside a link, not as bare text.
    ``RESEARCH.md`` Category 7 is the reason this is a component at all —
    "LLMs Understand Layout" (arXiv:2407.05750) measures +8-33% F1 when layout
    survives, so structure lost in pursuit of a lower token count is a cost, not
    a saving.

    Args:
        text: The converted text.
        truth: The fixture's ground truth.

    Returns:
        The component, or an unscored one when the fixture names no structural
        elements.
    """
    bullets = _strings(truth.get("bullet_items"))
    numbered = _strings(truth.get("numbered_items"))
    targets = _strings(truth.get("expected_link_targets"))
    fences = truth.get("expected_code_fences")
    wanted_fences = fences if isinstance(fences, int) and fences > 0 else 0
    has_fences = wanted_fences > 0

    if not (bullets or numbered or targets or has_fences):
        return _absent(
            "structure_retention",
            "this fixture's ground truth names no list items, links or code fences",
        )

    expected = 0
    found = 0
    missing: list[str] = []

    items = {md.normalise(item).casefold() for item in md.list_item_lines(text)}
    for item in (*bullets, *numbered):
        expected += 1
        needle = md.normalise(item).casefold()
        if any(needle in candidate for candidate in items):
            found += 1
        else:
            missing.append(f"list item: {item}")

    found_targets = set(md.link_targets(text))
    for target in targets:
        expected += 1
        if target in found_targets:
            found += 1
        else:
            missing.append(f"link target: {target}")

    if has_fences:
        actual = md.code_fence_count(text)
        expected += wanted_fences
        found += min(actual, wanted_fences)
        if actual < wanted_fences:
            missing.append(f"code fences: {actual} of {wanted_fences} present")

    return ComponentScore(
        component="structure_retention",
        score=found / expected if expected else None,
        expected=expected,
        found=found,
        detail=f"{found} of {expected} structural elements retained as structure",
        missing=tuple(missing[:_MAX_MISSING]),
    )


def _boilerplate_rejection(text: str, truth: Mapping[str, Any]) -> ComponentScore:
    """Score how much of what should be gone is gone.

    This number is meaningless on its own and is never reported on its own: a
    converter that emitted nothing rejects everything. It is half of a pair
    with ``content_recall``, and the two together are what says extraction
    worked.

    Args:
        text: The converted text.
        truth: The fixture's ground truth.

    Returns:
        The component, or an unscored one when the fixture names nothing that
        must be absent.
    """
    markers = (
        *_strings(truth.get("boilerplate_markers_must_be_absent")),
        *_strings(truth.get("must_not_contain")),
    )
    if not markers:
        return _absent(
            "boilerplate_rejection",
            "this fixture's ground truth names nothing that must be absent",
        )

    body = md.normalise(text).casefold()
    still_present = [marker for marker in markers if md.normalise(marker).casefold() in body]
    rejected = len(markers) - len(still_present)
    return ComponentScore(
        component="boilerplate_rejection",
        score=rejected / len(markers),
        expected=len(markers),
        found=rejected,
        detail=f"{rejected} of {len(markers)} markers that must be absent are absent",
        missing=tuple(still_present[:_MAX_MISSING]),
    )


def _reading_order(text: str, truth: Mapping[str, Any]) -> ComponentScore:
    """Score whether ordered sentinels came back in ascending order.

    ``twocolumn.pdf`` carries ``ORDERMARK 01`` to ``ORDERMARK 12`` down one
    column and then the other. A backend that interleaves the columns recovers
    every sentinel and puts them in the wrong sequence, which no recall metric
    can see.

    The score is the longest ascending subsequence of the sentinels that were
    found, over the number ground truth lists. A sentinel that is missing
    counts against the score rather than being excluded from it: order cannot
    be confirmed for text that is not there, and dividing by the found count
    would let a backend that dropped ten of twelve markers score 1.0 for
    keeping the remaining two in sequence. The found count is in the detail, so
    the two effects stay separable.

    Args:
        text: The converted text.
        truth: The fixture's ground truth.

    Returns:
        The component, or an unscored one when the fixture has no sentinels.
    """
    markers = _strings(truth.get("order_markers"))
    if not markers:
        return _absent("reading_order", "this fixture's ground truth carries no order sentinels")

    positions = [(text.find(marker), marker) for marker in markers]
    found = [(index, marker) for index, marker in positions if index >= 0]
    missing = [marker for index, marker in positions if index < 0]
    ascending = _longest_ascending_run([index for index, _ in found])

    return ComponentScore(
        component="reading_order",
        score=ascending / len(markers),
        expected=len(markers),
        found=ascending,
        detail=(
            f"{ascending} of {len(markers)} sentinels form the longest ascending run; "
            f"{len(found)} of {len(markers)} were present at all"
        ),
        missing=tuple(missing[:_MAX_MISSING]),
    )


def _longest_ascending_run(positions: Sequence[int]) -> int:
    """Return the length of the longest strictly ascending subsequence.

    Args:
        positions: Where each sentinel was found, in the order ground truth
            lists them.

    Returns:
        How many sentinels appear in the document in the order they should.
        Quadratic, which is irrelevant at a dozen sentinels and keeps the
        implementation readable.
    """
    if not positions:
        return 0
    best = [1] * len(positions)
    for i in range(1, len(positions)):
        for j in range(i):
            if positions[j] < positions[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
    return max(best)


#: Maps each component to the function that measures it. Consulted through
#: :data:`~tokenmill.fidelity.models.COMPONENTS`, so the declared component list
#: is the single source of truth for what a score contains and in what order.
_SCORERS: Final[dict[str, Callable[[str, Mapping[str, Any]], ComponentScore]]] = {
    "heading_recall": _heading_recall,
    "content_recall": _content_recall,
    "table_integrity": _table_integrity,
    "structure_retention": _structure_retention,
    "boilerplate_rejection": _boilerplate_rejection,
    "reading_order": _reading_order,
}
