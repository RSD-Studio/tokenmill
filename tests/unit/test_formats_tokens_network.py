"""The five serialisation formats measured in **real model tokens**.

`docs/BENCHMARKS.md` has carried a format comparison since Phase 5 — CSV 216,
TOON 240, markdown 332, keyvalue 456, JSON 543 — and every one of those numbers
is UTF-8 bytes, because the development sandbox cannot reach a tokenizer
vocabulary host. The published claims that table is set beside are model tokens:
GetCrux's "CSV uses ~56% fewer tokens than JSON", and the TOON repository's
"42.6% fewer tokens than JSON".

So the page has been comparing a byte percentage with a token percentage and
saying three times over that it will not draw the conclusion. This file is what
lets the conclusion finally be drawn, in the unit the claims are actually made
in. It runs behind the `network` marker, in the blocking `tokenizers` CI job.

This is the first time TOON's own benchmark figure can be checked against our
own data in its own currency, and the answer is allowed to be unflattering. The
assertions below deliberately bound the *shape* of the result — an ordering, and
a floor on the saving — rather than pinning exact numbers that would break on a
tiktoken release. The exact numbers are printed for the log to record.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenmill.core.compare import FormatComparison, compare_formats
from tokenmill.core.models import ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.formats.base import default_format_registry
from tokenmill.tokens.registry import default_tokenizer_registry

pytestmark = [pytest.mark.network, pytest.mark.integration]

#: The tokenizer the published claims are quoted in.
TOKENIZER = "o200k_base"

#: The order `docs/BENCHMARKS.md` publishes, cheapest first in bytes.
FORMATS = ("csv", "toon", "markdown", "keyvalue", "json")


@pytest.fixture(scope="module")
def comparison(fixture_dir: Path) -> FormatComparison:
    """Re-encode `tables.pdf`'s table in every format, counting real tokens.

    The same path `docs/BENCHMARKS.md` documents: `pdfplumber` recovers the 6x5
    table from `tables.pdf`, and `compare --formats` re-serialises it.
    """
    options = ConvertOptions(tokenizer=TOKENIZER, backend="pdfplumber")
    result = Pipeline().run(Source.from_path(fixture_dir / "tables.pdf"), options)
    counter = default_tokenizer_registry().get(TOKENIZER)
    return compare_formats(
        result.text,
        FORMATS,
        registry=default_format_registry(),
        count=counter.count,
        tokenizer_id=TOKENIZER,
        source_name="tables.pdf",
    )


class TestTheFormatComparisonInRealTokens:
    def test_every_format_was_counted_with_a_real_tokenizer(
        self, comparison: FormatComparison
    ) -> None:
        """Guard the guard: a silent fallback to `bytes` makes the rest vacuous."""
        assert comparison.tokenizer_id == TOKENIZER
        for row in comparison.rows:
            assert row.ok, f"{row.format_id} failed to encode: {row.error}"
            assert row.tokens is not None
            assert row.tokens.tokenizer_id == TOKENIZER

    def test_the_numbers_are_printed_so_a_ci_log_records_them(
        self,
        comparison: FormatComparison,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The only place these figures can be *read out* of a run.

        `docs/BENCHMARKS.md` may not carry a token figure until this has printed
        one in a green CI run, per the project's rule that a figure not in
        captured output does not go in a document.
        """
        by_id = {row.format_id: row for row in comparison.rows}
        json_tokens = by_id["json"].tokens
        assert json_tokens is not None

        with capsys.disabled():
            print()
            for row in comparison.rows:
                assert row.tokens is not None
                delta = (row.tokens.value - json_tokens.value) / json_tokens.value
                print(
                    f"BENCHMARK tables.pdf pdfplumber format={row.format_id} "
                    f"{TOKENIZER}: {row.tokens.value} tokens "
                    f"({delta:+.4f} vs json), {row.characters} bytes"
                )

    def test_csv_and_toon_both_beat_json_in_tokens_too(self, comparison: FormatComparison) -> None:
        """The direction the byte table showed, now in the published unit.

        RESEARCH.md Category 7 reports CSV at ~56% fewer tokens than JSON and
        TOON at 42.6%. This asserts only that both are genuinely cheaper by a
        wide margin, not that we reproduce either figure — one 6x5 table is not
        a corpus, and `docs/BENCHMARKS.md` says so beside the numbers.
        """
        by_id = {row.format_id: row for row in comparison.rows}
        json_tokens = by_id["json"].tokens
        assert json_tokens is not None

        for cheaper in ("csv", "toon"):
            tokens = by_id[cheaper].tokens
            assert tokens is not None
            saving = 1 - tokens.value / json_tokens.value
            assert saving > 0.20, (
                f"{cheaper} saves only {saving:.1%} of JSON's tokens on tables.pdf. "
                f"The byte table shows -60% and -56%; a token figure this far off "
                f"is a finding to investigate before publishing, not a number to publish"
            )

    def test_json_is_the_most_expensive_and_csv_the_cheapest(
        self, comparison: FormatComparison
    ) -> None:
        """The byte ordering held in tokens, or the byte ordering proved nothing."""
        counted = [
            (row.tokens.value, row.format_id) for row in comparison.rows if row.tokens is not None
        ]

        assert min(counted)[1] == "csv"
        assert max(counted)[1] == "json"

    def test_the_byte_ordering_and_the_token_ordering_agree(
        self, comparison: FormatComparison
    ) -> None:
        """Whether the locally-measurable proxy tracks the real thing.

        Every format figure recorded in `PROGRESS.md` and most of
        `docs/BENCHMARKS.md` is in bytes because that is all this sandbox can
        produce. If the two orderings ever disagree, those pages stop being a
        usable proxy and must say so rather than being quietly trusted.
        """
        counted = [r for r in comparison.rows if r.tokens is not None and r.characters is not None]
        assert len(counted) == len(FORMATS)

        by_tokens = [r.format_id for r in sorted(counted, key=lambda r: r.tokens.value)]  # type: ignore[union-attr]
        by_bytes = [r.format_id for r in sorted(counted, key=lambda r: r.characters or 0)]

        assert by_tokens == by_bytes, (
            f"formats rank {by_tokens} in tokens but {by_bytes} in bytes; the byte "
            f"figures published in docs/BENCHMARKS.md are not a proxy for the token "
            f"figures and the page must say so"
        )
