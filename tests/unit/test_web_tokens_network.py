"""The boilerplate reduction in **real model tokens**, not bytes.

This file exists because of a gap the development sandbox cannot close. Phase
3's acceptance criterion is stated against ``docs/research/RESEARCH.md``
Category 7, whose figures — Cloudflare's 80%, the community 82%, FormatArc's
~70% — are all **model-token** measurements. The sandbox these adapters were
written in cannot reach either tokenizer vocabulary host
(``openaipublic.blob.core.windows.net`` and ``huggingface.co`` are both denied
at the egress proxy), so every local number is UTF-8 bytes.

A byte percentage is not a token percentage. They are close for ASCII prose and
they are not the same claim, and the project's rule is that a figure which is
not in captured output does not go in a document. So the byte figure is
asserted in ``tests/integration/test_web_backends.py`` and labelled as bytes,
and the figure the acceptance criterion is actually about is asserted here,
behind the ``network`` marker, where the blocking ``tokenizers`` CI job runs it.

Until a green CI run has printed the number, ``docs/BENCHMARKS.md`` records the
token figure as unverified and publishes only the byte figure, as a byte figure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenmill.core.models import ConversionResult, ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline

pytestmark = [pytest.mark.network, pytest.mark.integration]

#: The real tokenizer the published figures are quoted in the currency of.
TOKENS = ConvertOptions(tokenizer="o200k_base")


def convert(path: Path, backend: str) -> ConversionResult:
    """Convert one fixture through one named backend, counting real tokens.

    Args:
        path: The fixture.
        backend: The backend id to pin to.

    Returns:
        The result.
    """
    return Pipeline().run(Source.from_path(path), TOKENS.with_(backend=backend))


class TestTheBoilerplateReductionInRealTokens:
    def test_both_counts_are_real_model_tokens(self, fixture_dir: Path) -> None:
        """Guard the guard: a fallback to `bytes` would make the rest vacuous."""
        result = convert(fixture_dir / "boilerplate.html", "trafilatura")

        assert result.tokens_before is not None
        assert result.tokens_after is not None
        assert result.tokens_before.tokenizer_id == "o200k_base"
        assert result.tokens_after.tokenizer_id == "o200k_base"

    def test_the_reduction_lands_in_the_published_band(self, fixture_dir: Path) -> None:
        """Phase 3's acceptance criterion, in the units it is stated in.

        RESEARCH.md Category 7 reports 70-90% across three independent
        measurements of HTML against extracted Markdown. This asserts our own
        figure is in that band on our own fixture. If it is not, the number is
        to be investigated before it is reported anywhere — a percentage
        outside the band is either a bug or a fixture that does not represent
        what the literature measured, and both are findings rather than numbers
        to publish.
        """
        result = convert(fixture_dir / "boilerplate.html", "trafilatura")
        ratio = result.reduction_ratio

        assert ratio is not None
        assert 0.70 <= ratio <= 0.90, (
            f"o200k_base reduction on boilerplate.html is {ratio:.1%}, outside "
            f"RESEARCH.md's 70-90% band. Investigate before publishing it."
        )

    def test_the_number_is_printed_so_a_ci_log_records_it(
        self, fixture_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The only place the publishable figure can be *read out* of a run.

        `docs/BENCHMARKS.md` may not carry a token percentage until this has
        printed one in a green CI run, per the project's rule that a figure not
        in captured output does not go in a document. Printing it here is what
        makes the CI log the citable source.
        """
        result = convert(fixture_dir / "boilerplate.html", "trafilatura")

        assert result.tokens_before is not None
        assert result.tokens_after is not None
        assert result.reduction_ratio is not None
        with capsys.disabled():
            print(
                f"\nBENCHMARK boilerplate.html trafilatura o200k_base: "
                f"{result.tokens_before.value} -> {result.tokens_after.value} tokens "
                f"({result.reduction_ratio:.4f} reduction)"
            )

    def test_extraction_beats_markup_removal_in_tokens_too(
        self, fixture_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The byte comparison holds in tokens, or the byte one proved nothing."""
        page = fixture_dir / "boilerplate.html"
        extracted = convert(page, "trafilatura")
        raw = convert(page, "markdownify_html")

        assert extracted.reduction_ratio is not None
        assert raw.reduction_ratio is not None
        with capsys.disabled():
            print(
                f"\nBENCHMARK boilerplate.html markdownify_html o200k_base: "
                f"{raw.reduction_ratio:.4f} reduction"
            )
        assert extracted.reduction_ratio > raw.reduction_ratio + 0.20

    def test_the_byte_measure_and_the_token_measure_agree_in_direction(
        self, fixture_dir: Path
    ) -> None:
        """Not that they are equal — they are not, and must never be conflated.

        What this checks is that the local byte figure, which is all the
        development sandbox can produce, is a usable proxy for the shape of the
        answer: same sign, same order of magnitude. If the two ever disagree
        materially, every byte figure recorded in PROGRESS.md becomes suspect
        and should be re-read as the different measurement it is.
        """
        page = fixture_dir / "boilerplate.html"
        in_tokens = convert(page, "trafilatura").reduction_ratio
        in_bytes = (
            Pipeline()
            .run(Source.from_path(page), ConvertOptions(tokenizer="bytes", backend="trafilatura"))
            .reduction_ratio
        )

        assert in_tokens is not None
        assert in_bytes is not None
        assert abs(in_tokens - in_bytes) < 0.15, (
            f"token reduction {in_tokens:.1%} and byte reduction {in_bytes:.1%} differ by "
            f"more than 15 points; the byte figures recorded locally are not a proxy for "
            f"the token figures and PROGRESS.md should say so"
        )
