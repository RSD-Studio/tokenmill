"""Every GUI action, driven through the same API the interface calls.

`docs/DEVELOPMENT_PLAN.md` asks for exactly this: *a test that drives every GUI
action through that same API keeps the boundary honest*, and *test the API layer
programmatically; use headless browser tests only for the few flows worth the
maintenance cost*.

So this file is the GUI's test suite. It imports no browser and no UI toolkit,
runs on a core-only install, and takes about a second — which means it runs on
all nine CI cells rather than on the one where a browser happens to be
installed. `tests/unit/test_gui_boundary.py` is what stops the interface
quietly growing a second route that this does not cover.

Every panel of the interface appears below as a class, so a reader can check the
coverage claim against the screenshots in `docs/images/` rather than take it on
trust.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest

from tokenmill.core.models import IsolationMode, LicenseTier, Source
from tokenmill.gui import api
from tokenmill.gui.batch import BatchRunner, ItemState, requests_for

MakeRequest = Callable[..., api.ConversionRequest]

pytestmark = pytest.mark.integration

#: `bytes`, because the development sandbox cannot download a vocabulary and
#: this suite must run identically here and in CI.
BYTES = "bytes"


@pytest.fixture
def request_for(fixture_dir: Path) -> MakeRequest:
    """Build a conversion request for one fixture, scoring fidelity."""

    def make(name: str, **overrides: object) -> api.ConversionRequest:
        return api.ConversionRequest(
            source=Source.from_path(fixture_dir / name),
            tokenizer=BYTES,
            corpus=fixture_dir,
            **overrides,  # type: ignore[arg-type]
        )

    return make


class TestTheSourcePanel:
    """Files, URLs and pasted text all become a Source the API accepts."""

    def test_a_file_converts(self, request_for: MakeRequest) -> None:
        summary = api.convert(request_for("article.html"))

        assert summary.ok
        assert summary.text.strip()
        assert summary.backend_id

    def test_pasted_text_converts(self) -> None:
        request = api.ConversionRequest(
            source=Source.from_text("# A heading\n\nSome prose.\n"), tokenizer=BYTES
        )

        summary = api.convert(request)

        assert summary.ok
        assert "A heading" in summary.text

    def test_a_url_source_is_refused_rather_than_fetched_without_permission(self) -> None:
        """`fetch` and `allow_network` are two permissions, and the GUI has both."""
        request = api.ConversionRequest(
            source=Source.from_url("https://example.invalid/page"),
            tokenizer=BYTES,
            fetch=False,
        )

        summary = api.convert(request)

        assert not summary.ok
        assert summary.error


class TestTheTokenPanel:
    """The centrepiece: before, after, delta, per stage."""

    def test_it_reports_before_after_and_the_ratio(self, request_for: MakeRequest) -> None:
        summary = api.convert(request_for("boilerplate.html", backend="trafilatura"))

        assert summary.tokens_before == 12481
        assert summary.tokens_after == 2854
        assert summary.reduction_ratio is not None
        assert 0.77 <= summary.reduction_ratio <= 0.78

    def test_the_counts_carry_the_tokenizer_they_are_in(self, request_for: MakeRequest) -> None:
        """A bare number is not a token count; the unit is part of its meaning."""
        summary = api.convert(request_for("article.html"))

        assert summary.tokenizer_id == BYTES

    def test_the_per_stage_breakdown_is_arithmetically_consistent(
        self, request_for: MakeRequest
    ) -> None:
        summary = api.convert(request_for("boilerplate.html", backend="trafilatura"))

        assert len(summary.stages) >= 2
        for previous, current in zip(summary.stages, summary.stages[1:], strict=False):
            assert current.delta == current.tokens - previous.tokens
        assert summary.stages[0].delta is None

    def test_a_binary_document_has_no_before_count_and_says_so(
        self, request_for: MakeRequest
    ) -> None:
        """Phase 2 settled this and the GUI must not invent one.

        `None` renders as "n/a". A zero here would make every PDF look like an
        infinite saving.
        """
        summary = api.convert(request_for("simple.pdf"))

        assert summary.ok
        assert summary.tokens_before is None
        assert summary.reduction_ratio is None
        assert summary.tokens_after is not None


class TestFidelitySitsBesideTokens:
    def test_a_scored_fixture_carries_its_fidelity(self, request_for: MakeRequest) -> None:
        summary = api.convert(request_for("tables.pdf", backend="pdfplumber"))

        assert summary.fidelity is not None
        assert 0.0 <= summary.fidelity <= 1.0

    def test_no_corpus_means_none_rather_than_zero(self, fixture_dir: Path) -> None:
        """`None` is not zero, and this is where it matters most."""
        request = api.ConversionRequest(
            source=Source.from_path(fixture_dir / "tables.pdf"), tokenizer=BYTES, corpus=None
        )

        assert api.convert(request).fidelity is None

    def test_a_failed_fidelity_lookup_does_not_cost_the_conversion(
        self, fixture_dir: Path, tmp_path: Path
    ) -> None:
        """Scoring is a bonus. A missing manifest must not fail a conversion."""
        request = api.ConversionRequest(
            source=Source.from_path(fixture_dir / "article.html"),
            tokenizer=BYTES,
            corpus=tmp_path,
        )

        summary = api.convert(request)

        assert summary.ok
        assert summary.fidelity is None


class TestTheBackendSelector:
    def test_unavailable_backends_are_listed_rather_than_hidden(self) -> None:
        """The plan: greyed out with an install hint, never hidden."""
        choices = api.backend_choices()

        assert choices
        for choice in choices:
            if not choice.available:
                assert choice.hint, f"{choice.id} is unavailable with no install hint"

    def test_every_choice_carries_a_licence_a_tier_and_a_badge(self) -> None:
        for choice in api.backend_choices():
            assert choice.license.strip()
            assert isinstance(choice.license_tier, LicenseTier)
            assert choice.badge in {"CPU", "GPU"}

    def test_the_copyleft_backends_are_visible_as_such(self) -> None:
        """A user should be able to see what is isolated and why."""
        copyleft = [c for c in api.backend_choices() if c.license_tier is LicenseTier.COPYLEFT]

        assert copyleft, "no copyleft backends registered; Phase 7 added two"
        for choice in copyleft:
            assert choice.isolation is not IsolationMode.IN_PROCESS
            assert choice.isolated

    def test_a_domain_filter_narrows_the_list(self) -> None:
        from tokenmill.core.models import Domain

        web = api.backend_choices(Domain.WEB)

        assert web
        assert all("web" in c.domains for c in web)


class TestTheOptionsPanel:
    def test_the_post_processor_list_shows_both_flags(self) -> None:
        """Phase 7 split them, and the interface shows the one for the user."""
        processors = api.post_processor_choices()

        assert processors
        chunk = next(p for p in processors if p.id == "chunk")
        assert chunk.destructive is False
        assert chunk.in_default_chain is False

    def test_only_normalize_whitespace_runs_by_default(self) -> None:
        default = [p.id for p in api.post_processor_choices() if p.in_default_chain]

        assert default == ["normalize_whitespace"]

    def test_an_explicit_chain_is_honoured(self, request_for: MakeRequest) -> None:
        summary = api.convert(request_for("structured.md", post_processors=("strip_frontmatter",)))

        assert summary.ok
        assert not summary.text.lstrip().startswith("---")

    def test_the_tokenizer_and_format_lists_are_not_empty(self) -> None:
        assert BYTES in api.tokenizer_choices()
        assert "markdown" in api.format_choices()
        assert "toon" in api.format_choices()


class TestTheComparisonView:
    def test_rows_come_back_in_preference_order_and_not_sorted_by_size(
        self, request_for: MakeRequest
    ) -> None:
        """The one ordering rule the GUI must not undo.

        On `tables.pdf` the cheapest backend is the one that destroys the table.
        `docs/ARCHITECTURE.md` explains why compare is not sorted by size; this
        asserts the order survives the API layer, so a sorted view would be the
        interface's own doing and the boundary test would find it.
        """
        asked = ["pdfplumber", "pypdf", "kreuzberg"]

        comparison = api.compare_across_backends(request_for("tables.pdf"), asked)

        assert [row.backend_id for row in comparison.rows] == asked

    def test_fidelity_is_carried_beside_tokens(self, request_for: MakeRequest) -> None:
        """Without it the view is a machine for picking the worst backend."""
        comparison = api.compare_across_backends(
            request_for("tables.pdf"), ["pdfplumber", "kreuzberg"]
        )

        for row in comparison.rows:
            assert row.tokens is not None
            assert row.fidelity is not None

    def test_the_cheapest_is_not_the_most_faithful_on_tables_pdf(
        self, request_for: MakeRequest
    ) -> None:
        comparison = api.compare_across_backends(
            request_for("tables.pdf"), ["pdfplumber", "kreuzberg"]
        )

        assert comparison.cheapest is not None
        assert comparison.most_faithful is not None
        assert comparison.cheapest.backend_id != comparison.most_faithful.backend_id

    def test_a_failing_backend_is_a_row_rather_than_an_exception(
        self, request_for: MakeRequest
    ) -> None:
        """A comparison must survive one backend falling over."""
        comparison = api.compare_across_backends(
            request_for("corrupt.pdf"), ["pdfplumber", "pypdf"]
        )

        assert len(comparison.rows) == 2
        assert any(not row.ok for row in comparison.rows)
        for row in comparison.rows:
            if not row.ok:
                assert row.error

    def test_the_format_comparison_re_encodes_a_table(self, request_for: MakeRequest) -> None:
        summary = api.convert(request_for("tables.pdf", backend="pdfplumber"))

        comparison = api.compare_across_formats(
            summary.text,
            ["markdown", "csv", "toon", "json"],
            tokenizer=BYTES,
            source_name="tables.pdf",
        )

        assert len(comparison.rows) == 4
        assert comparison.cheapest is not None
        assert comparison.cheapest.format_id == "csv"


class TestTheBatchQueue:
    def test_a_twenty_file_batch_completes_with_correct_aggregate_totals(
        self, fixture_dir: Path
    ) -> None:
        """The acceptance criterion, in the units it is stated in.

        Twenty items, every one converted, and the totals checked against a
        manual summation rather than against themselves.
        """
        names = [
            "article.html",
            "boilerplate.html",
            "structured.md",
            "simple.pdf",
            "tables.pdf",
            "report.docx",
            "unicode.docx",
            "deck.pptx",
            "data.xlsx",
            "twocolumn.pdf",
        ]
        paths = [str(fixture_dir / n) for n in names] * 2
        assert len(paths) == 20

        template = api.ConversionRequest(
            source=Source.from_path(fixture_dir / names[0]), tokenizer=BYTES, corpus=fixture_dir
        )
        runner = BatchRunner(requests_for(paths, template))
        totals = runner.run_to_completion(timeout_s=300)

        assert totals.total == 20
        assert totals.done == 20
        assert totals.failed == 0

        items = runner.items
        assert sum(i.summary.tokens_after or 0 for i in items if i.summary) == (
            totals.tokens_produced
        )
        comparable = [
            i.summary
            for i in items
            if i.summary
            and i.summary.tokens_before is not None
            and i.summary.tokens_after is not None
        ]
        assert totals.comparable == len(comparable)
        assert totals.tokens_before == sum(s.tokens_before or 0 for s in comparable)

    def test_the_aggregate_ratio_only_counts_comparable_items(self, fixture_dir: Path) -> None:
        """The bug this caught: a batch that appeared to have grown.

        Summing `after` over every item while summing `before` over only the
        ones that had one reported the fixture corpus at -16.7% — a saving of
        minus seventeen percent, on a batch that saved 59%. The denominator was
        missing the binary documents the numerator included.
        """
        paths = [str(fixture_dir / n) for n in ("article.html", "simple.pdf", "report.docx")]
        template = api.ConversionRequest(
            source=Source.from_path(fixture_dir / "article.html"), tokenizer=BYTES
        )
        totals = BatchRunner(requests_for(paths, template)).run_to_completion(timeout_s=120)

        assert totals.comparable == 1, "only article.html has a before-count"
        assert totals.reduction_ratio is not None
        assert totals.reduction_ratio > 0, "a real saving, not a negative one"
        assert totals.tokens_produced > totals.tokens_after, (
            "tokens_produced covers every item; tokens_after only the comparable ones"
        )

    def test_a_batch_of_binary_documents_reports_no_ratio_rather_than_zero(
        self, fixture_dir: Path
    ) -> None:
        paths = [str(fixture_dir / n) for n in ("simple.pdf", "report.docx")]
        template = api.ConversionRequest(
            source=Source.from_path(fixture_dir / "simple.pdf"), tokenizer=BYTES
        )
        totals = BatchRunner(requests_for(paths, template)).run_to_completion(timeout_s=120)

        assert totals.comparable == 0
        assert totals.reduction_ratio is None

    def test_the_caller_thread_is_free_while_the_batch_runs(self, fixture_dir: Path) -> None:
        """A responsive UI means the work is not on the thread drawing it."""
        paths = [str(fixture_dir / "boilerplate.html")] * 6
        template = api.ConversionRequest(
            source=Source.from_path(fixture_dir / "boilerplate.html"), tokenizer=BYTES
        )
        runner = BatchRunner(requests_for(paths, template))

        runner.start()
        polls = 0
        while runner.running and polls < 20_000:
            polls += 1
            time.sleep(0.001)
        runner.wait(timeout_s=120)

        assert polls > 5, "the caller never got control back while the batch ran"
        assert runner.totals.done == 6

    def test_a_failure_does_not_stop_the_batch(self, fixture_dir: Path) -> None:
        """Twenty files must not stop at the first bad one."""
        paths = [str(fixture_dir / n) for n in ("article.html", "corrupt.pdf", "structured.md")]
        template = api.ConversionRequest(
            source=Source.from_path(fixture_dir / "article.html"),
            tokenizer=BYTES,
            backend=None,
        )
        totals = BatchRunner(requests_for(paths, template)).run_to_completion(timeout_s=120)

        assert totals.total == 3
        assert totals.done + totals.failed == 3
        assert totals.done >= 2

    def test_cancelling_marks_the_queue_and_says_what_it_does_not_do(
        self, fixture_dir: Path
    ) -> None:
        """Cancellation is cooperative, and the interface says so."""
        paths = [str(fixture_dir / "boilerplate.html")] * 8
        template = api.ConversionRequest(
            source=Source.from_path(fixture_dir / "boilerplate.html"), tokenizer=BYTES
        )
        runner = BatchRunner(requests_for(paths, template))

        runner.start()
        runner.cancel()
        runner.wait(timeout_s=120)

        assert runner.cancelled
        states = [i.state for i in runner.items]
        assert ItemState.CANCELLED in states
        assert all(s is not ItemState.QUEUED for s in states)

    def test_an_empty_batch_finishes_rather_than_hanging(self) -> None:
        """A user dropping a folder of unsupported files is a real case."""
        runner = BatchRunner([])

        assert runner.run_to_completion(timeout_s=5).total == 0
        assert not runner.running


class TestCostEstimation:
    def test_it_multiplies_the_users_own_rate(self) -> None:
        estimate = api.estimate_cost(1_500_000, 2.50, "$")

        assert estimate.cost == pytest.approx(3.75)
        assert estimate.currency == "$"

    def test_no_rate_table_ships_anywhere_in_the_package(self) -> None:
        """The restraint is the feature.

        Prices change, and a stale table in this repository would be a confident
        lie about somebody's bill. Asserted rather than intended: the API takes a
        rate and there is no default for it.
        """
        import inspect

        signature = inspect.signature(api.estimate_cost)

        assert signature.parameters["rate_per_million"].default is inspect.Parameter.empty

    def test_a_negative_rate_is_refused_rather_than_rendered(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            api.estimate_cost(1000, -1.0)
        with pytest.raises(ValueError, match="negative"):
            api.estimate_cost(-1, 1.0)


class TestFailureIsReadable:
    def test_a_backend_failure_is_a_summary_with_a_message_and_a_hint(
        self, request_for: MakeRequest
    ) -> None:
        """The acceptance criterion: readable and actionable, not a traceback."""
        summary = api.convert(request_for("corrupt.pdf", backend="pdfplumber"))

        assert not summary.ok
        assert summary.error
        assert "Traceback" not in summary.error
        assert summary.error_hint

    def test_an_unavailable_backend_says_what_to_install(self) -> None:
        summary = api.convert(
            api.ConversionRequest(
                source=Source.from_text("hello"), tokenizer=BYTES, backend="docling"
            )
        )

        if summary.ok:
            pytest.skip("docling is installed here, so there is no unavailability to check")
        assert summary.error
        assert summary.error_hint
