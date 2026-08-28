"""The article pack's generated files must match the data they claim to describe.

Two of this project's published errors were transcription: a character count
printed under a heading that said bytes, and a `compare` example in the README
naming `pdfplumber` as the most faithful PDF backend for two phases after
`pymupdf4llm` overtook it. Both survived review because a human had typed the
number once and nobody re-derived it.

So the article pack's tables are a function of `results.json`, and this is the
check that they still are.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from docs.article.make_tables import DEFAULT_RUN, render

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "docs" / "article" / "TABLES.md"


@pytest.fixture(scope="module")
def committed_run() -> tuple[list[dict[str, object]], dict[str, object]]:
    """Load the run the pack describes.

    Returns:
        Its cells and its manifest.
    """
    payload = json.loads((DEFAULT_RUN / "results.json").read_text(encoding="utf-8"))
    return payload["results"], payload["manifest"]


class TestTheTablesAreNotTranscribed:
    def test_the_committed_tables_match_the_committed_data(
        self, committed_run: tuple[list[dict[str, object]], dict[str, object]]
    ) -> None:
        rows, manifest = committed_run
        assert TABLES.read_text(encoding="utf-8") == render(rows, manifest), (
            "docs/article/TABLES.md is out of date with "
            "benchmarks/results/. Run: uv run python docs/article/make_tables.py"
        )

    def test_the_tables_name_the_commit_they_came_from(
        self, committed_run: tuple[list[dict[str, object]], dict[str, object]]
    ) -> None:
        _, manifest = committed_run
        assert str(manifest["git_commit"])[:7] in TABLES.read_text(encoding="utf-8")

    def test_the_unit_warning_survives_a_regeneration(
        self, committed_run: tuple[list[dict[str, object]], dict[str, object]]
    ) -> None:
        """The single most important sentence in the pack."""
        rows, manifest = committed_run
        assert "UTF-8 bytes, not model tokens" in render(rows, manifest)

    def test_a_saving_renders_with_a_real_minus_sign(
        self, committed_run: tuple[list[dict[str, object]], dict[str, object]]
    ) -> None:
        """The sign bug this project has shipped twice, in its typographic form."""
        rows, manifest = committed_run
        text = render(rows, manifest)
        # boilerplate.html through trafilatura saves 77.1%.
        assert "−77.1%" in text
        assert "+77.1%" not in text

    def test_growth_still_renders_as_positive(
        self, committed_run: tuple[list[dict[str, object]], dict[str, object]]
    ) -> None:
        """Both directions, because asserting only one is how the bug got in."""
        rows, manifest = committed_run
        grew = [
            r
            for r in rows
            if r["ok"] and isinstance(r.get("reduction"), float) and r["reduction"] < 0  # type: ignore[operator]
        ]
        assert grew, "the corpus should contain at least one conversion that grows"
        assert "+9.5%" in render(rows, manifest)


class TestEveryFidelityCarriesItsComponentCount:
    def test_no_bare_fidelity_score_is_published(
        self, committed_run: tuple[list[dict[str, object]], dict[str, object]]
    ) -> None:
        """A 1.000 from one component and from four are different claims."""
        rows, manifest = committed_run
        text = render(rows, manifest)
        for line in text.splitlines():
            if not line.startswith("| `"):
                continue
            for cell in (c.strip() for c in line.split("|")):
                if len(cell) == 5 and cell[1] == "." and cell.replace(".", "").isdigit():
                    pytest.fail(f"bare fidelity score with no component count: {line}")


class TestTheChartScriptIsUsableWithoutMatplotlib:
    def test_it_says_what_to_run_instead_of_raising(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Matplotlib is deliberately not a dependency, so this path is the normal one."""
        import builtins

        from docs.article import make_charts

        real_import = builtins.__import__

        def refuse(name: str, *args: object, **kwargs: object) -> object:
            if name == "matplotlib":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", refuse)
        assert make_charts.main([]) == 2
        assert "uv run --with matplotlib" in capsys.readouterr().out
