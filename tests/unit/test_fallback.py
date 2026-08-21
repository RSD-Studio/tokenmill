"""The fallback chain: candidate ordering, walking it, and reporting it.

Phase 2's third acceptance criterion is that "the fallback chain demonstrably
works when the primary backend is uninstalled". There are two distinct ways a
preferred backend can be out of the running and both are tested here:

* **It is not installed.** The registry filters it out before ranking, so the
  next backend is simply chosen. This is the uninstalled case the criterion
  names.
* **It is installed and it fails on this particular file.** The pipeline
  catches the :class:`~tokenmill.core.errors.ConversionError`, records the
  attempt, and gives the next candidate a turn.

The third case matters as much as the first two: an explicit ``--backend``
never falls back, because a measurement attributed to a converter the user did
not choose is worse than an error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.doubles import EchoConverter, make_info
from tokenmill.core.errors import (
    BackendUnavailable,
    ConversionError,
    CorruptSource,
    UnsupportedFormat,
)
from tokenmill.core.models import Availability, ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.protocol import BaseConverter, ConversionContext
from tokenmill.core.registry import Registry
from tokenmill.post.base import PostProcessorRegistry
from tokenmill.tokens.registry import TokenizerRegistry

OFFLINE = ConvertOptions(tokenizer="bytes")


class FailingConverter(BaseConverter):
    """A backend that is available and always fails on the file it is given."""

    def __init__(self, backend_id: str, *, priority: int = 0, message: str = "no good") -> None:
        super().__init__()
        self.info = make_info(backend_id, priority=priority)
        self._message = message
        self.calls = 0

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        del source, options, context
        self.calls += 1
        raise CorruptSource(self._message, backend_id=self.info.id)


@pytest.fixture
def text_file(tmp_path: Path) -> Source:
    path = tmp_path / "input.txt"
    path.write_text("Body.\n", encoding="utf-8")
    return Source.from_path(path)


def make_pipeline(*converters: object) -> Pipeline:
    """Build a pipeline over exactly the given backends and nothing else."""
    registry = Registry()
    for converter in converters:
        registry.register(converter)  # type: ignore[arg-type]
    return Pipeline(
        backends=registry,
        post_processors=PostProcessorRegistry(),
        tokenizers=TokenizerRegistry(),
    )


class TestCandidateOrdering:
    def test_the_chain_is_ordered_best_first(self, text_file: Source) -> None:
        registry = Registry()
        registry.register(EchoConverter("low", priority=1))
        registry.register(EchoConverter("high", priority=99))

        chain = registry.candidates(text_file)

        assert [c.info.id for c in chain] == ["high", "low"]

    def test_an_unavailable_backend_is_not_in_the_chain(self, text_file: Source) -> None:
        """This is the "primary backend is uninstalled" case, at registry level."""
        registry = Registry()
        registry.register(
            EchoConverter(
                "preferred",
                priority=99,
                availability=Availability.missing_dependency("nothing", hint="pip install it"),
            )
        )
        registry.register(EchoConverter("secondary", priority=1))

        chain = registry.candidates(text_file)

        assert [c.info.id for c in chain] == ["secondary"]

    def test_an_explicit_backend_yields_a_chain_of_exactly_one(self, text_file: Source) -> None:
        registry = Registry()
        registry.register(EchoConverter("first", priority=99))
        registry.register(EchoConverter("second", priority=1))

        chain = registry.candidates(text_file, backend_id="second")

        assert [c.info.id for c in chain] == ["second"]

    def test_an_explicit_backend_that_cannot_run_is_an_error(self, text_file: Source) -> None:
        registry = Registry()
        registry.register(
            EchoConverter(
                "broken",
                availability=Availability.missing_dependency("nope", hint="pip install nope"),
            )
        )

        with pytest.raises(BackendUnavailable, match="not available"):
            registry.candidates(text_file, backend_id="broken")

    def test_a_format_nothing_claims_still_raises_unsupportedformat(self, tmp_path: Path) -> None:
        registry = Registry()
        registry.register(EchoConverter("text_only"))
        path = tmp_path / "thing.definitelynotaformat"
        path.write_text("x", encoding="utf-8")

        with pytest.raises(UnsupportedFormat):
            registry.candidates(Source.from_path(path))

    def test_select_returns_the_head_of_the_chain(self, text_file: Source) -> None:
        registry = Registry()
        registry.register(EchoConverter("low", priority=1))
        registry.register(EchoConverter("high", priority=99))

        assert registry.select(text_file) is registry.candidates(text_file)[0]


class TestWalkingTheChain:
    def test_a_failing_backend_hands_over_to_the_next(self, text_file: Source) -> None:
        pipeline = make_pipeline(
            FailingConverter("broken", priority=99), EchoConverter("working", priority=1)
        )

        result = pipeline.run(text_file, OFFLINE)

        assert result.backend_id == "working"
        assert result.text == "Body.\n"

    def test_the_first_backend_that_works_ends_the_chain(self, text_file: Source) -> None:
        never = FailingConverter("never_reached", priority=1)
        pipeline = make_pipeline(EchoConverter("working", priority=99), never)

        pipeline.run(text_file, OFFLINE)

        assert never.calls == 0

    def test_every_attempt_is_recorded_in_order(self, text_file: Source) -> None:
        pipeline = make_pipeline(
            FailingConverter("first", priority=99, message="first said no"),
            FailingConverter("second", priority=50, message="second said no"),
            EchoConverter("third", priority=1),
        )

        result = pipeline.run(text_file, OFFLINE)

        assert [(a.backend_id, a.ok) for a in result.attempts] == [
            ("first", False),
            ("second", False),
            ("third", True),
        ]
        assert result.attempts[0].error is not None
        assert "first said no" in result.attempts[0].error

    def test_a_conversion_that_did_not_fall_back_records_one_attempt(
        self, text_file: Source
    ) -> None:
        pipeline = make_pipeline(EchoConverter("working"))

        result = pipeline.run(text_file, OFFLINE)

        assert [(a.backend_id, a.ok) for a in result.attempts] == [("working", True)]

    def test_a_fallback_warns_so_it_is_never_invisible(self, text_file: Source) -> None:
        pipeline = make_pipeline(
            FailingConverter("broken", priority=99, message="it went wrong"),
            EchoConverter("working", priority=1),
        )

        result = pipeline.run(text_file, OFFLINE)

        assert any("broken" in w and "fell back" in w for w in result.warnings)

    def test_the_backends_own_warnings_survive_the_fallback(self, text_file: Source) -> None:
        pipeline = make_pipeline(
            FailingConverter("broken", priority=99),
            EchoConverter("working", priority=1, warn="something looked odd"),
        )

        result = pipeline.run(text_file, OFFLINE)

        assert "something looked odd" in result.warnings

    def test_when_every_backend_fails_the_error_says_what_was_tried(
        self, text_file: Source
    ) -> None:
        pipeline = make_pipeline(
            FailingConverter("first", priority=99), FailingConverter("second", priority=1)
        )

        with pytest.raises(ConversionError) as excinfo:
            pipeline.run(text_file, OFFLINE)

        assert excinfo.value.hint is not None
        assert "first" in excinfo.value.hint
        assert "second" in excinfo.value.hint

    def test_a_single_candidate_failure_keeps_its_own_hint(self, text_file: Source) -> None:
        """One backend, one failure: nothing was "tried and failed" but it."""

        class Hinted(FailingConverter):
            def _convert(
                self, source: Source, options: ConvertOptions, context: ConversionContext
            ) -> str:
                del source, options, context
                raise CorruptSource("bad file", backend_id=self.info.id, hint="check the file")

        pipeline = make_pipeline(Hinted("only"))

        with pytest.raises(ConversionError) as excinfo:
            pipeline.run(text_file, OFFLINE)

        assert excinfo.value.hint == "check the file"

    def test_the_error_keeps_its_original_class(self, text_file: Source) -> None:
        pipeline = make_pipeline(
            FailingConverter("first", priority=99), FailingConverter("second", priority=1)
        )

        with pytest.raises(CorruptSource):
            pipeline.run(text_file, OFFLINE)


class TestFallbackCanBeTurnedOff:
    def test_no_fallback_stops_at_the_first_failure(self, text_file: Source) -> None:
        never = EchoConverter("working", priority=1)
        pipeline = make_pipeline(FailingConverter("broken", priority=99), never)

        with pytest.raises(CorruptSource, match="no good"):
            pipeline.run(text_file, OFFLINE.with_(fallback=False))

    def test_no_fallback_still_records_the_attempt_it_made(self, text_file: Source) -> None:
        pipeline = make_pipeline(FailingConverter("broken", priority=99), EchoConverter("working"))

        with pytest.raises(CorruptSource):
            pipeline.run(text_file, OFFLINE.with_(fallback=False))

    def test_an_explicit_backend_never_falls_back_even_with_fallback_on(
        self, text_file: Source
    ) -> None:
        """Phase 1's rule: a measurement must be attributable to the named backend."""
        working = EchoConverter("working", priority=1)
        pipeline = make_pipeline(FailingConverter("broken", priority=99), working)

        with pytest.raises(CorruptSource, match="no good"):
            pipeline.run(text_file, OFFLINE.with_(backend="broken"))
