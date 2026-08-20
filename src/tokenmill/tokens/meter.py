"""Token measurement: the number this whole project exists to produce.

:class:`TokenMeter` wraps one tokenizer and does the arithmetic — count a
string, count each pipeline stage, work out what was saved. It is deliberately
thin and deliberately free of I/O so that its behaviour can be tested exactly,
against a tokenizer whose output is known, without depending on a vocabulary
download. See ``tests/unit/test_tokens.py``.

Measurement failure is not conversion failure. If the tokenizer cannot load —
no network for its vocabulary, optional dependency absent — the meter records
``None`` and a warning, and the conversion still returns its Markdown. A user on
an air-gapped machine gets their converted document with the count honestly
marked unavailable, rather than an error where a document should have been. The
alternative, guessing, is the one thing we will not do.
"""

from __future__ import annotations

from collections.abc import Sequence

from tokenmill.core.errors import NetworkRequired, TokenizerError
from tokenmill.core.models import StageCount, TokenCount
from tokenmill.tokens.base import Tokenizer

__all__ = ["TokenMeter"]


class TokenMeter:
    """Counts tokens with one tokenizer and reports what changed.

    Attributes:
        tokenizer: The tokenizer doing the counting.
    """

    def __init__(self, tokenizer: Tokenizer) -> None:
        """Initialise the meter.

        Args:
            tokenizer: The tokenizer to measure with.
        """
        self.tokenizer = tokenizer
        self._failure: str | None = None

    @property
    def tokenizer_id(self) -> str:
        """Return the id every count from this meter carries."""
        return self.tokenizer.info.id

    @property
    def failure(self) -> str | None:
        """Return why counting failed, or ``None`` if it has not.

        Set the first time a count fails, so the pipeline can attach one
        warning to the result rather than one per stage.
        """
        return self._failure

    def count(self, text: str) -> TokenCount | None:
        """Count the tokens in ``text``.

        Args:
            text: The text to measure.

        Returns:
            The count, or ``None`` if the tokenizer could not be loaded — a
            missing optional dependency, or a vocabulary that cannot be
            downloaded. Once it has failed once, later calls return ``None``
            immediately rather than retrying a download that will not succeed.
        """
        if self._failure is not None:
            return None
        try:
            value = self.tokenizer.count(text)
        except (TokenizerError, NetworkRequired) as exc:
            # Both are measurement failures, and neither is a reason to throw
            # away a document we successfully converted. NetworkRequired is the
            # common one: tiktoken and HuggingFace both fetch their vocabulary
            # on first use, so an air-gapped machine lands here.
            self._failure = str(exc)
            return None
        return TokenCount(value=value, tokenizer_id=self.tokenizer_id)

    def measure_stage(self, stage: str, text: str) -> StageCount:
        """Measure the text leaving one pipeline stage.

        Characters are always recorded, even when tokens cannot be: a character
        count needs no vocabulary, and it still shows the user which stage
        shrank the text.

        Args:
            stage: The stage name.
            text: The text as it leaves that stage.

        Returns:
            The stage's measurements.
        """
        return StageCount(stage=stage, characters=len(text), tokens=self.count(text))

    def measure_stages(self, stages: Sequence[tuple[str, str]]) -> tuple[StageCount, ...]:
        """Measure several stages in order.

        Args:
            stages: ``(stage_name, text)`` pairs in execution order.

        Returns:
            One :class:`~tokenmill.core.models.StageCount` per stage.
        """
        return tuple(self.measure_stage(name, text) for name, text in stages)

    @staticmethod
    def delta(before: TokenCount | None, after: TokenCount | None) -> int | None:
        """Return how many tokens were saved between two counts.

        Args:
            before: The count going in.
            after: The count coming out.

        Returns:
            ``before - after``, positive when the text got cheaper. ``None`` if
            either count is missing, or if the two used different tokenizers —
            subtracting an ``o200k_base`` count from a ``cl100k_base`` one
            produces a number with no meaning, so the meter refuses rather than
            returning something that looks like an answer.
        """
        if before is None or after is None:
            return None
        if before.tokenizer_id != after.tokenizer_id:
            return None
        return before.value - after.value

    @staticmethod
    def reduction(before: TokenCount | None, after: TokenCount | None) -> float | None:
        """Return the fraction of tokens removed.

        Args:
            before: The count going in.
            after: The count coming out.

        Returns:
            The saved fraction — ``0.8`` for an 80% reduction. Negative when the
            text grew, which is a real result and is not clamped. ``None`` if
            either count is missing, the tokenizers differ, or ``before`` is
            zero, since a ratio against nothing is undefined.
        """
        difference = TokenMeter.delta(before, after)
        if difference is None or before is None or before.value == 0:
            return None
        return difference / before.value
