"""Fidelity scoring: what a token saving cost.

Brought forward from Phase 10 ahead of Phase 5, because Phase 5's
post-processors can each be measured as a win in tokens and a loss in fidelity,
and defaults argued rather than measured are how a token-reduction toolkit ends
up recommending the converter that destroys the most.

Phase 10 proper still owns the corpus x backends x formats matrix, wall time,
peak memory and the committed result files. This package is only the scorer.
"""

from tokenmill.fidelity.ground_truth import load_ground_truth, resolve_fixture
from tokenmill.fidelity.models import COMPONENTS, ComponentScore, FidelityScore
from tokenmill.fidelity.scorer import score

__all__ = [
    "COMPONENTS",
    "ComponentScore",
    "FidelityScore",
    "load_ground_truth",
    "resolve_fixture",
    "score",
]
