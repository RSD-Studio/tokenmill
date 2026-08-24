"""What a fidelity score is, and why it is never a single number.

``benchmarks/README.md`` states the rule this package exists to enforce:

    Token savings without a fidelity measurement is not a result — a converter
    that emits an empty string scores a 100% reduction.

The counter-measurement is a :class:`FidelityScore`: a set of named
:class:`ComponentScore` values plus an overall. It is deliberately *not* an
opaque number, for a reason that is easy to state and easy to forget — a score
a user cannot decompose is a score they cannot act on. "0.62" tells nobody
whether to change backend, change post-processors or accept the loss.
"Headings 1.00, tables 0.00" tells them exactly.

Two rules govern the arithmetic, and both matter more than the numbers:

**A component with no ground truth scores ``None``.** Not zero, not one.
``tables.pdf`` has a table and ``long_context.md`` does not; scoring the second
one's table integrity as 0.0 would say a table was destroyed, and scoring it 1.0
would say a table survived. Both are lies about a document with no table in it.
This is the same rule ``ground_truth.json`` already follows for ``token_count``,
where Phase 0 wrote ``null`` rather than a characters-over-four guess.

**The overall is an unweighted mean of the components that scored, and it names
them.** Unweighted because any weighting would encode an opinion about whether a
lost table matters more than a lost heading, and that opinion belongs to the
user with the document, not to this module. Naming them because an overall
computed from two components is not comparable with one computed from five, and
a reader who cannot see which is which will compare them anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "COMPONENTS",
    "ComponentScore",
    "FidelityScore",
]

#: Every component a :class:`FidelityScore` may carry, in report order.
#:
#: Report order is deliberate rather than alphabetical: it runs from what a
#: document *is* (its headings and its prose) through what it *contains*
#: (tables, structure) to what a converter should have *removed* or *kept in
#: sequence*. A reader scanning the table top to bottom sees recall before
#: rejection, which is the order the two acceptance criteria in the Phase 10
#: slice pair them in — high recall alone does not mean extraction worked, and
#: neither does high rejection alone.
COMPONENTS: Final[tuple[str, ...]] = (
    "heading_recall",
    "content_recall",
    "table_integrity",
    "structure_retention",
    "boilerplate_rejection",
    "reading_order",
)


@dataclass(frozen=True, slots=True)
class ComponentScore:
    """One named axis of fidelity, scored or explicitly not scored.

    Attributes:
        component: The axis, one of :data:`COMPONENTS`.
        score: The fraction recovered, ``0.0`` to ``1.0``, or ``None`` when the
            fixture's ground truth says nothing about this axis. ``None`` means
            "not measured here" and never "measured as zero".
        expected: How many things ground truth said to look for, or ``None``
            when the axis did not score.
        found: How many of them were recovered, or ``None`` when the axis did
            not score.
        detail: One sentence a user can act on. When :attr:`score` is ``None``
            this says why the axis did not apply; when it scored, this says how
            it was measured and what the shortfall was.
        missing: The specific things that were not recovered, so the user can
            look at them rather than at a percentage. Capped by the caller.
    """

    component: str
    score: float | None
    expected: int | None = None
    found: int | None = None
    detail: str = ""
    missing: tuple[str, ...] = ()

    @property
    def scored(self) -> bool:
        """Whether this component produced a number.

        Returns:
            True when ground truth supported the measurement.
        """
        return self.score is not None


@dataclass(frozen=True, slots=True)
class FidelityScore:
    """The full fidelity picture for one piece of converted text.

    Attributes:
        fixture: The ground-truth entry the text was scored against.
        backend_id: The backend that produced the text, when known. Carried so
            a score can be attributed; the scorer never infers it.
        components: One :class:`ComponentScore` per axis in
            :data:`COMPONENTS` order. Axes with no ground truth are present
            with a ``None`` score rather than absent, because a reader needs to
            see that an axis was *considered* and did not apply.
    """

    fixture: str
    components: tuple[ComponentScore, ...]
    backend_id: str | None = None

    @property
    def scored_components(self) -> tuple[str, ...]:
        """Name the components the overall is composed of.

        Returns:
            The components that produced a number, in report order. An overall
            built from two of these is not comparable with one built from five,
            which is why the names travel with the number everywhere it is
            reported.
        """
        return tuple(c.component for c in self.components if c.scored)

    @property
    def overall(self) -> float | None:
        """The unweighted mean of the components that scored.

        Returns:
            The mean, or ``None`` when no component had ground truth to score
            against. ``None`` here means the text was never really assessed,
            which is a different statement from "it scored badly" and must not
            be rendered as ``0.00``.
        """
        scores = [c.score for c in self.components if c.score is not None]
        if not scores:
            return None
        return sum(scores) / len(scores)

    def get(self, component: str) -> ComponentScore:
        """Return one component by name.

        Args:
            component: The axis to fetch, one of :data:`COMPONENTS`.

        Returns:
            That component's score.

        Raises:
            KeyError: If the component is not part of this score.
        """
        for candidate in self.components:
            if candidate.component == component:
                return candidate
        known = ", ".join(c.component for c in self.components) or "none"
        msg = f"no fidelity component named {component!r} (known: {known})"
        raise KeyError(msg)
