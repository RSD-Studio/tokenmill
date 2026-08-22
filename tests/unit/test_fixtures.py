"""Validate the synthetic test corpus.

These tests guard the fixtures themselves. Every later phase asserts converter
output against `ground_truth.json`, so if the corpus silently changes shape the
failures land here rather than being blamed on a backend.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

EXPECTED_FIXTURES = [
    "article.html",
    "boilerplate.html",
    "corrupt.pdf",
    "data.xlsx",
    "deck.pptx",
    "jsrendered.html",
    "long_context.md",
    "report.docx",
    "sample_repo/",
    "scanned.pdf",
    "simple.pdf",
    "tables.pdf",
    "twocolumn.pdf",
    "unicode.docx",
]


def test_every_planned_fixture_is_present(fixture_dir: Path) -> None:
    missing = [name for name in EXPECTED_FIXTURES if not (fixture_dir / name.rstrip("/")).exists()]
    assert missing == []


def test_ground_truth_covers_every_fixture(ground_truth: dict[str, Any]) -> None:
    assert sorted(ground_truth) == sorted(EXPECTED_FIXTURES)


def test_every_ground_truth_entry_is_described(ground_truth: dict[str, Any]) -> None:
    undescribed = [name for name, facts in ground_truth.items() if not facts.get("description")]
    assert undescribed == []


@pytest.mark.parametrize("name", [n for n in EXPECTED_FIXTURES if not n.endswith("/")])
def test_fixture_files_are_non_empty(fixture_dir: Path, name: str) -> None:
    assert (fixture_dir / name).stat().st_size > 0


def test_corrupt_pdf_keeps_its_magic_but_loses_its_trailer(fixture_dir: Path) -> None:
    """The error-path fixture must be sniffable as a PDF yet unparseable."""
    data = (fixture_dir / "corrupt.pdf").read_bytes()
    assert data.startswith(b"%PDF-")
    assert b"%%EOF" not in data
    assert len(data) < (fixture_dir / "simple.pdf").stat().st_size


def test_scanned_pdf_is_larger_than_its_digital_source(fixture_dir: Path) -> None:
    """Rasterised pages should dwarf the vector original; if not, it did not rasterise."""
    assert (fixture_dir / "scanned.pdf").stat().st_size > 10 * (
        fixture_dir / "simple.pdf"
    ).stat().st_size


def test_boilerplate_html_wraps_the_same_article(
    fixture_dir: Path, ground_truth: dict[str, Any]
) -> None:
    """The two HTML fixtures must differ only in boilerplate.

    This pairing is what makes the Phase 3 boilerplate-reduction measurement
    meaningful: the article body is identical, so any token delta between them
    is attributable to the surrounding furniture.
    """
    clean = (fixture_dir / "article.html").read_text(encoding="utf-8")
    noisy = (fixture_dir / "boilerplate.html").read_text(encoding="utf-8")

    assert len(noisy) > 3 * len(clean)
    for marker in ground_truth["boilerplate.html"]["boilerplate_markers_must_be_absent"]:
        assert marker in noisy
        assert marker not in clean

    # Every article paragraph present in the clean fixture is present verbatim
    # in the noisy one.
    for line in clean.splitlines():
        stripped = line.strip()
        if stripped.startswith("<p>"):
            assert stripped in noisy


def test_unicode_fixture_ground_truth_spans_multiple_scripts(ground_truth: dict[str, Any]) -> None:
    scripts = ground_truth["unicode.docx"]["scripts"]
    assert {"Urdu", "Arabic", "Chinese", "Japanese", "Korean", "Emoji"} <= set(scripts)
    assert all(text.strip() for text in scripts.values())


def test_long_context_carries_a_findable_needle(
    fixture_dir: Path, ground_truth: dict[str, Any]
) -> None:
    facts = ground_truth["long_context.md"]
    text = (fixture_dir / "long_context.md").read_text(encoding="utf-8")
    assert text.count(facts["needle"]) == facts["needle_occurrences"]
    assert len(text) == facts["character_count"]


def test_long_context_publishes_no_unmeasured_token_count(ground_truth: dict[str, Any]) -> None:
    """No fabricated numbers: the token count stays null until we measure one."""
    facts = ground_truth["long_context.md"]
    assert facts["token_count"] is None
    assert facts["token_count_note"]


def test_sample_repo_is_a_real_git_repo_with_a_pinned_commit(
    sample_repo: Path, ground_truth: dict[str, Any]
) -> None:
    """The recreated repo must land on exactly the recorded commit.

    The .git directory is not committed, so this also proves that materialising
    it from the committed working files is deterministic.
    """
    facts = ground_truth["sample_repo/"]
    assert (sample_repo / ".git").is_dir()
    assert len(facts["head_commit"]) == 40
    for relative in facts["tracked_files"]:
        assert (sample_repo / relative).exists()

    head = subprocess.run(  # noqa: S603
        [shutil.which("git") or "git", "rev-parse", "HEAD"],
        cwd=sample_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head == facts["head_commit"]


def test_sample_repo_hides_a_secret_that_ingestion_must_not_leak(
    sample_repo: Path, ground_truth: dict[str, Any]
) -> None:
    """The .gitignore'd secret exists on disk so backends can be caught leaking it."""
    repo = sample_repo
    facts = ground_truth["sample_repo/"]
    secret = facts["must_not_contain"][0]

    assert (repo / "secrets.env").exists()
    assert secret in (repo / "secrets.env").read_text(encoding="utf-8")
    assert "secrets.env" in (repo / ".gitignore").read_text(encoding="utf-8")
    assert "secrets.env" not in facts["tracked_files"]


def test_sample_repo_is_not_committed_as_a_gitlink() -> None:
    """The outer repository must track the fixture's files, not a submodule.

    Running the test suite recreates `tests/fixtures/sample_repo/.git`, so a
    later `git add tests/` can silently turn the fixture into a gitlink (mode
    160000). Git stores no contents for a gitlink, so anyone cloning tokenmill
    would get an empty `sample_repo/` and every repo-backend test would skip.
    This test is the standing guard against that.
    """
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not available")

    repo_root = Path(__file__).parent.parent.parent
    result = subprocess.run(  # noqa: S603
        [git, "ls-files", "--stage", "--", "tests/fixtures/sample_repo"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not inside a git work tree")

    entries = [line.split() for line in result.stdout.splitlines() if line.strip()]
    gitlinks = [entry[3] for entry in entries if entry[0] == "160000"]
    assert gitlinks == [], f"sample_repo committed as a gitlink: {gitlinks}"
    assert entries, "sample_repo files are not tracked at all"


class TestTheJavascriptRenderedFixture:
    """The fixture that makes a browser-driving backend's claim checkable.

    Without a page whose content genuinely does not exist in the response body,
    "crawl4ai renders JavaScript" is an untestable assertion about a 677 MB
    dependency. These assertions are about the *fixture*, and they are what stop
    the backend test that depends on it from passing vacuously.
    """

    def test_the_sentinel_does_not_appear_in_the_source(self, fixture_dir: Path) -> None:
        """The property the whole fixture rests on.

        The first version of this fixture embedded the sentinel whole inside the
        script, so a plain read of the file contained it and the backend test
        proved nothing. The script now joins it from two halves at run time.
        """
        source = (fixture_dir / "jsrendered.html").read_text(encoding="utf-8")

        assert "RSD-TOKENMILL-RENDERED-9317" not in source

    def test_the_placeholder_is_the_only_text_outside_the_script(
        self, fixture_dir: Path, ground_truth: dict[str, Any]
    ) -> None:
        """What a parser sees, as opposed to what is merely in the bytes.

        The rendered title and paragraphs *are* in the source — they are string
        literals inside the script — so an assertion that they are absent from
        the file would be false. What matters is that they are not *visible
        text*: a converter that reads the response body finds only the
        placeholder, which is why the sentinel and not the title is what the
        backend test asserts on.
        """
        from tokenmill.backends.web._common import visible_text

        facts = ground_truth["jsrendered.html"]
        visible = visible_text((fixture_dir / "jsrendered.html").read_text(encoding="utf-8"))

        assert visible == facts["unrendered_placeholder"]
        assert facts["rendered_title"] not in visible

    def test_the_placeholder_clears_crawl4ais_anti_bot_threshold(self, fixture_dir: Path) -> None:
        """Fifty visible characters, or the success path is unreachable.

        Crawl4AI refuses any page under 5,000 bytes whose *un-rendered* body
        holds fewer than 50 characters of visible text, calling it
        ``Structural: minimal_text on small page``. That is a false positive on
        small client-rendered pages, and it made the first version of this
        fixture impossible to render. The placeholder is a full sentence for
        that reason, and this test is why nobody will shorten it back.
        """
        from tokenmill.backends.web._common import visible_text

        source = (fixture_dir / "jsrendered.html").read_text(encoding="utf-8")

        assert len(visible_text(source)) >= 50

    def test_it_needs_no_network_to_render(self, fixture_dir: Path) -> None:
        """Everything is inserted through the DOM; nothing is fetched."""
        source = (fixture_dir / "jsrendered.html").read_text(encoding="utf-8")

        for fetcher in ("fetch(", "XMLHttpRequest", "src=", "href="):
            assert fetcher not in source, f"the fixture would reach the network via {fetcher!r}"
