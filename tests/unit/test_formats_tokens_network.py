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

    def test_csv_is_the_cheapest_in_both_units(self, comparison: FormatComparison) -> None:
        """The one ordering claim that either unit safely supports."""
        by_tokens = [(r.tokens.value, r.format_id) for r in comparison.rows if r.tokens]
        by_bytes = [(r.characters or 0, r.format_id) for r in comparison.rows]

        assert min(by_tokens)[1] == "csv"
        assert min(by_bytes)[1] == "csv"

    def test_the_byte_ordering_is_not_a_proxy_for_the_token_ordering(
        self, comparison: FormatComparison
    ) -> None:
        """**The finding**, asserted as the finding rather than papered over.

        This file originally asserted that the two orderings agree, because that
        was the honest hypothesis and the byte figures were all this project
        could produce. CI run 89 falsified it, which is what the test was for:

            bytes : csv, toon, markdown, keyvalue, json
            tokens: csv, toon, markdown, json,     keyvalue

        `keyvalue` is 456 bytes against JSON's 543 — **16% smaller** — and costs
        167 tokens against JSON's 164, **1.8% more**. Its repeated `Backend: `,
        `License: ` field labels are cheap in bytes and expensive in tokens,
        where JSON's punctuation-heavy syntax merges into single BPE tokens.

        So the assertion is inverted: the disagreement is now the documented
        state, and this fails if a future tiktoken release makes the two agree —
        at which point `docs/BENCHMARKS.md` gets to relax its warning rather
        than keep one that has stopped being true.
        """
        by_tokens = [r.format_id for r in sorted(comparison.rows, key=_tokens)]
        by_bytes = [r.format_id for r in sorted(comparison.rows, key=_characters)]

        assert by_tokens != by_bytes, (
            "the byte and token orderings now agree, where run 89 recorded them "
            "disagreeing at the json/keyvalue boundary. That is good news and "
            "docs/BENCHMARKS.md's Units section should be relaxed to match"
        )
        assert by_tokens[:3] == by_bytes[:3] == ["csv", "toon", "markdown"], (
            "the disagreement has spread beyond the json/keyvalue pair; "
            "re-measure before publishing anything from either unit"
        )

    def test_the_published_claims_do_not_reproduce_on_our_data(
        self, comparison: FormatComparison
    ) -> None:
        """The first time TOON's own figure could be checked in its own unit.

        `RESEARCH.md` Category 7 carries GetCrux's "CSV uses ~56% fewer tokens
        than JSON" and the TOON repository's "42.6% fewer tokens than JSON".
        Measured on our 6x5 table in `o200k_base`, CSV saves **36.0%** and TOON
        **29.9%** — both well short.

        That is not a refutation: one 6x5 table is not a corpus, and TOON's
        advantage grows with row count because its header is declared once.
        It is a reason not to restate either claim as ours, which
        `CONTRIBUTING.md` rule 4 forbids anyway.

        Asserted as a band rather than a point so a tiktoken release does not
        break it, and wide enough that only a real change moves it.
        """
        by_id = {r.format_id: r for r in comparison.rows}
        json_tokens = by_id["json"].tokens
        assert json_tokens is not None

        savings = {}
        for name in ("csv", "toon"):
            tokens = by_id[name].tokens
            assert tokens is not None
            savings[name] = 1 - tokens.value / json_tokens.value

        assert 0.30 <= savings["csv"] <= 0.45, (
            f"CSV saves {savings['csv']:.1%} of JSON's tokens; run 89 measured "
            f"36.0%. GetCrux's ~56% is a different corpus and is not ours to quote"
        )
        assert 0.22 <= savings["toon"] <= 0.38, (
            f"TOON saves {savings['toon']:.1%} of JSON's tokens; run 89 measured "
            f"29.9%, against the TOON repository's own 42.6%. If this has moved, "
            f"docs/BENCHMARKS.md's comparison table is out of date"
        )

    def test_the_byte_proxy_overstates_the_saving_and_by_how_much(
        self, comparison: FormatComparison
    ) -> None:
        """Every byte figure in this repository is optimistic, and this says so.

        CSV saves 60.2% of JSON's *bytes* and 36.0% of its *tokens*: the proxy
        overstates by 24 points. `PROGRESS.md` and most of
        `docs/BENCHMARKS.md` are in bytes because that is all the development
        sandbox can produce, and this is the size of the error that carries.
        """
        by_id = {r.format_id: r for r in comparison.rows}
        json_row = by_id["json"]
        csv_row = by_id["csv"]
        assert json_row.tokens is not None
        assert csv_row.tokens is not None
        assert json_row.characters is not None
        assert csv_row.characters is not None

        in_tokens = 1 - csv_row.tokens.value / json_row.tokens.value
        in_bytes = 1 - csv_row.characters / json_row.characters

        assert in_bytes > in_tokens, (
            "the byte figure no longer flatters the token figure; "
            "docs/BENCHMARKS.md's Units section says it does"
        )
        assert in_bytes - in_tokens > 0.15, (
            f"the gap between the byte saving ({in_bytes:.1%}) and the token "
            f"saving ({in_tokens:.1%}) has narrowed to {in_bytes - in_tokens:.1%}; "
            f"run 89 measured 24 points and the docs quote that"
        )


def _tokens(row: object) -> int:
    """Sort key: a row's token count.

    Args:
        row: A :class:`~tokenmill.core.compare.FormatRow`.

    Returns:
        Its token count, or -1 when it has none.
    """
    tokens = getattr(row, "tokens", None)
    return tokens.value if tokens is not None else -1


def _characters(row: object) -> int:
    """Sort key: a row's byte length.

    Args:
        row: A :class:`~tokenmill.core.compare.FormatRow`.

    Returns:
        Its length, or -1 when it has none.
    """
    return getattr(row, "characters", None) or -1
