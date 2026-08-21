"""The format-to-backend preference map.

These tests hold the map to two things. That it is *well formed* — every id it
names exists, every format it ranks is claimed by the backends it ranks — so a
renamed backend cannot leave a dead entry silently deciding nothing. And that
its *semantics* are what the docstring claims: a number in the map replaces a
declared priority for that one format and leaves every other format alone, so a
third-party backend can outrank the built-ins without editing core.
"""

from __future__ import annotations

import pytest

from tests.doubles import make_info
from tokenmill.core.models import IsolationMode, LicenseTier
from tokenmill.core.preferences import (
    FORMAT_PREFERENCES,
    effective_priority,
    preference_rationale,
)
from tokenmill.core.registry import Registry

INSTALLED = {converter.info.id: converter.info for converter in Registry()}


class TestTheMapIsWellFormed:
    def test_every_ranked_format_is_a_bare_lowercase_token(self) -> None:
        for fmt in FORMAT_PREFERENCES:
            assert fmt == fmt.lower()
            assert not fmt.startswith(".")

    def test_no_format_ranks_the_same_backend_twice(self) -> None:
        for fmt, ranking in FORMAT_PREFERENCES.items():
            assert len(set(ranking)) == len(ranking), f"{fmt} ranks a backend twice"

    def test_every_ranking_is_a_strict_order(self) -> None:
        """Two backends on the same number would be ordered by id, silently."""
        for fmt, ranking in FORMAT_PREFERENCES.items():
            values = list(ranking.values())
            assert len(set(values)) == len(values), f"{fmt} gives two backends equal rank"

    def test_every_named_backend_exists(self) -> None:
        """A renamed backend must not leave an entry here quietly ranking nothing."""
        for fmt, ranking in FORMAT_PREFERENCES.items():
            for backend_id in ranking:
                assert backend_id in INSTALLED, (
                    f"{fmt} ranks {backend_id!r}, which no installed backend provides"
                )

    def test_every_named_backend_actually_claims_that_format(self) -> None:
        for fmt, ranking in FORMAT_PREFERENCES.items():
            for backend_id in ranking:
                assert INSTALLED[backend_id].supports_format(fmt), (
                    f"{backend_id!r} is ranked for {fmt!r} but does not claim it"
                )

    def test_every_ranked_format_has_a_recorded_rationale(self) -> None:
        """A ranking with no reason recorded is a preference nobody can review."""
        for fmt in FORMAT_PREFERENCES:
            rationale = preference_rationale(fmt)
            assert rationale, f"{fmt} is ranked with no rationale"
            assert len(rationale) > 20


class TestEffectivePriority:
    def test_the_map_replaces_the_declared_priority_for_that_format(self) -> None:
        info = make_info("markitdown", priority=30)

        assert effective_priority(info, "pptx") == FORMAT_PREFERENCES["pptx"]["markitdown"]

    def test_a_backend_the_map_does_not_name_keeps_its_declared_priority(self) -> None:
        info = make_info("somebody_elses_pdf_backend", priority=100)

        assert effective_priority(info, "pdf") == 100

    def test_an_unranked_format_leaves_every_priority_alone(self) -> None:
        info = make_info("markitdown", priority=30)

        assert effective_priority(info, "ipynb") == 30

    def test_the_format_is_matched_case_insensitively(self) -> None:
        info = make_info("markitdown", priority=30)

        assert effective_priority(info, "PPTX") == effective_priority(info, "pptx")

    def test_a_third_party_backend_can_outrank_the_built_ins(self) -> None:
        """The map is a default, not a gate. This is the property that makes it so."""
        theirs = make_info("brilliant_pdf", priority=1000)
        ours = make_info("pdfplumber", priority=40)

        assert effective_priority(theirs, "pdf") > effective_priority(ours, "pdf")


class TestTheRankingsWeChose:
    """The orderings that Phase 2 observed on the fixture corpus.

    Each of these is a claim about a real conversion, quoted in
    ``docs/BACKENDS.md``. If one of them stops being true — an upstream release
    fixes or breaks something — the map is wrong and this is where it shows.
    The integration tests are what check the underlying behaviour; these check
    that the map still says what we decided it should say.
    """

    @pytest.mark.parametrize(
        ("source_format", "winner", "loser"),
        [
            # pdfplumber is the only one that recovers tables.pdf as a table.
            ("pdf", "pdfplumber", "markitdown"),
            ("pdf", "pdfplumber", "pypdf"),
            # docling downloads models for PDF, so it never leads there...
            ("pdf", "pypdf", "docling"),
            # ...but it needs none for Office formats, where it is the best.
            ("docx", "docling", "markitdown"),
            ("docx", "docling", "kreuzberg"),
            # markitdown is the only one that keeps PPTX speaker notes.
            ("pptx", "markitdown", "docling"),
            ("pptx", "markitdown", "kreuzberg"),
            # docling drops XLSX sheet names.
            ("xlsx", "markitdown", "docling"),
            ("xlsx", "kreuzberg", "docling"),
            # HTML stays with the web backend until Phase 3 revisits it.
            ("html", "markdownify_html", "markitdown"),
        ],
    )
    def test_the_preferred_backend_outranks_the_alternative(
        self, source_format: str, winner: str, loser: str
    ) -> None:
        ranking = FORMAT_PREFERENCES[source_format]

        assert ranking[winner] > ranking[loser]

    def test_docling_is_last_for_pdf_because_its_pdf_path_downloads_models(self) -> None:
        ranking = FORMAT_PREFERENCES["pdf"]

        assert ranking["docling"] == min(ranking.values())

    def test_docling_is_first_for_docx_because_that_path_needs_no_model(self) -> None:
        ranking = FORMAT_PREFERENCES["docx"]

        assert ranking["docling"] == max(ranking.values())


class TestTheMapDoesNotChangeTheLicencePosition:
    def test_no_ranked_backend_is_copyleft_and_in_process(self) -> None:
        """Ranking must never be a route around CONTRIBUTING.md rule 2."""
        for ranking in FORMAT_PREFERENCES.values():
            for backend_id in ranking:
                info = INSTALLED[backend_id]
                if info.license_tier is not LicenseTier.PERMISSIVE:
                    assert info.isolation is not IsolationMode.IN_PROCESS
