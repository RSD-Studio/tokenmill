"""The shared repository layer: options, sections, budget and breakdown.

The budget is what most of this file is about, because "the token budget flag
genuinely caps output, and what got dropped is reported" is a Phase 4 acceptance
criterion and a silent truncation is a bug by that criterion's own words.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenmill.backends.repo._common import (
    DEFAULT_MAX_FILE_BYTES,
    PackedFile,
    apply_budget,
    directory_totals,
    matches_any,
    read_repo_options,
    render_truncation_note,
    repo_workdir,
    split_sections,
)
from tokenmill.core.errors import BackendFailed, CorruptSource, NetworkRequired
from tokenmill.core.models import ConvertOptions, Source

#: Counting characters stands in for a tokenizer: exact, offline, and it makes
#: every expected number in this file checkable by hand.
CHARS = len


def section(path: str, body: str) -> PackedFile:
    """Build a packed section of a known size.

    Args:
        path: The file's path.
        body: Its contents.

    Returns:
        The section.
    """
    return PackedFile(path=path, text=body)


class TestReadingOptions:
    def test_the_defaults_are_conservative(self) -> None:
        settings = read_repo_options(ConvertOptions())

        assert settings.include == ()
        assert settings.exclude == ()
        assert settings.respect_gitignore is True
        assert settings.skip_binary is True
        assert settings.max_file_bytes == DEFAULT_MAX_FILE_BYTES
        assert settings.token_budget is None

    def test_comma_separated_globs_are_split(self) -> None:
        settings = read_repo_options(ConvertOptions(extra={"include": "*.py, src/**"}))

        assert settings.include == ("*.py", "src/**")

    def test_a_list_of_globs_is_accepted_too(self) -> None:
        settings = read_repo_options(ConvertOptions(extra={"exclude": ["a", "b"]}))

        assert settings.exclude == ("a", "b")

    def test_booleans_are_read_in_the_spellings_people_use(self) -> None:
        for value in (False, "false", "no", "off", "0"):
            settings = read_repo_options(ConvertOptions(extra={"respect_gitignore": value}))

            assert settings.respect_gitignore is False, value

    def test_a_malformed_value_falls_back_instead_of_failing_the_conversion(self) -> None:
        """`extra` is documented as options a backend may ignore.

        A typo in one of them must not be able to fail a conversion that would
        otherwise have worked.
        """
        settings = read_repo_options(
            ConvertOptions(extra={"max_file_bytes": "not a number", "token_budget": "nonsense"})
        )

        assert settings.max_file_bytes == DEFAULT_MAX_FILE_BYTES
        assert settings.token_budget is None

    def test_a_branch_that_would_read_as_an_option_never_reaches_git(self) -> None:
        """`--upload-pack=` turns a clone into arbitrary command execution.

        The option parser keeps whatever it was given, because `RepoOptions` is
        a record of what was asked for. The refusal happens at the layer that
        would actually hand it to git.
        """
        from tokenmill.backends.repo._common import _read_branch

        assert _read_branch(ConvertOptions(extra={"branch": "--upload-pack=evil"})) is None
        assert _read_branch(ConvertOptions(extra={"branch": "main"})) == "main"


class TestSplittingAPackIntoSections:
    def test_gitingest_headers_are_recognised(self) -> None:
        text = (
            "Directory structure:\n└── x\n\n"
            "================================================\n"
            "FILE: a.py\n"
            "================================================\n"
            "print('a')\n"
            "================================================\n"
            "FILE: b.py\n"
            "================================================\n"
            "print('b')\n"
        )

        preamble, sections = split_sections(text, "gitingest")

        assert "Directory structure" in preamble
        assert [s.path for s in sections] == ["a.py", "b.py"]

    def test_repomix_headers_are_recognised(self) -> None:
        text = "# Summary\n\n## File: src/a.py\n```python\nx = 1\n```\n## File: b.md\ntext\n"

        preamble, sections = split_sections(text, "repomix")

        assert preamble == "# Summary\n\n"
        assert [s.path for s in sections] == ["src/a.py", "b.md"]

    def test_code2prompt_headers_are_recognised(self) -> None:
        """Backtick-quoted paths, not `## File:`.

        The first version of this pattern guessed `## File:` from repomix and
        was wrong; running code2prompt is what corrected it.
        """
        text = (
            "Project Path: x\n\n`README.md`:\n\n```md\n# hi\n```\n\n`src/a.py`:\n\n```py\nx\n```\n"
        )

        _, sections = split_sections(text, "code2prompt")

        assert [s.path for s in sections] == ["README.md", "src/a.py"]

    def test_re_joining_the_parts_reproduces_the_pack(self) -> None:
        """The budget depends on this: sections are slices, not reconstructions."""
        text = "head\n## File: a\nbody a\n## File: b\nbody b\n"

        preamble, sections = split_sections(text, "repomix")

        assert preamble + "".join(s.text for s in sections) == text

    def test_a_header_string_inside_a_file_is_not_a_header(self) -> None:
        """Anchored to the start of a line, so quoted text cannot fake one.

        A repository containing documentation *about* repomix would otherwise
        split in the middle of a file.
        """
        text = "head\n## File: real.md\nthe format is `## File: fake.md` inline\n"

        _, sections = split_sections(text, "repomix")

        assert [s.path for s in sections] == ["real.md"]

    def test_an_unrecognised_format_yields_no_sections_rather_than_guessing(self) -> None:
        """Which the adapters must report, not treat as an empty repository."""
        preamble, sections = split_sections("something else entirely", "repomix")

        assert preamble == "something else entirely"
        assert sections == []


class TestTheTokenBudget:
    def test_no_budget_leaves_the_pack_alone_and_says_it_did_not_apply(self) -> None:
        sections = [section("a", "x" * 100)]

        text, report = apply_budget("head", sections, budget=None, count=CHARS, unit="chars")

        assert text == "head" + "x" * 100
        assert report.applied is False

    def test_a_pack_that_already_fits_is_untouched(self) -> None:
        sections = [section("a", "x" * 10)]

        text, report = apply_budget("head", sections, budget=1000, count=CHARS, unit="chars")

        assert text == "head" + "x" * 10
        assert report.applied is True
        assert report.dropped == ()

    def test_files_that_do_not_fit_are_dropped_whole(self) -> None:
        """Never partially: half a module is worse than no module.

        A model cannot tell that the rest was cut, and will reason about a class
        whose methods have vanished.
        """
        sections = [section("keep.py", "k" * 20), section("drop.py", "d" * 500)]

        text, report = apply_budget("h", sections, budget=200, count=CHARS, unit="chars")

        assert "k" * 20 in text
        assert "d" * 500 not in text
        assert [path for path, _ in report.dropped] == ["drop.py"]

    def test_every_dropped_file_is_reported_with_what_it_would_have_cost(self) -> None:
        """A silent truncation is a bug; this is the assertion that says so."""
        sections = [section("a", "a" * 10), section("big.py", "b" * 900)]

        _, report = apply_budget("h", sections, budget=100, count=CHARS, unit="chars")

        assert report.dropped == (("big.py", 900),)
        assert report.total == 911
        assert report.kept == ("a",)

    def test_the_output_genuinely_fits_the_budget_including_the_note(self) -> None:
        """The acceptance criterion, and the bug the first version had.

        The truncation note is part of the output. A first version appended it
        after the budget was computed and produced 1,482 bytes against a
        1,200-byte cap — a cap exceeded by the explanation of the cap.
        """
        sections = [section(f"f{n}.py", "x" * 200) for n in range(20)]

        text, report = apply_budget("head\n", sections, budget=900, count=CHARS, unit="chars")

        assert len(text) <= 900, f"emitted {len(text)} against a budget of 900"
        assert report.emitted == len(text)
        assert report.over_budget is False

    def test_a_later_smaller_file_still_fits_after_a_big_one_is_skipped(self) -> None:
        """One enormous file must not waste the whole remaining budget."""
        sections = [
            section("small1.py", "a" * 10),
            section("huge.py", "b" * 5000),
            section("small2.py", "c" * 10),
        ]

        text, report = apply_budget("h", sections, budget=200, count=CHARS, unit="chars")

        assert "a" * 10 in text
        assert "c" * 10 in text
        assert [path for path, _ in report.dropped] == ["huge.py"]

    def test_the_directory_tree_is_never_dropped(self) -> None:
        """It is the only thing telling a reader which files are missing."""
        preamble = "Directory structure:\n" + "t" * 400
        sections = [section("a.py", "x" * 100)]

        text, report = apply_budget(preamble, sections, budget=50, count=CHARS, unit="chars")

        assert text.startswith("Directory structure:")
        assert report.over_budget is True

    def test_going_over_budget_is_reported_rather_than_hidden(self) -> None:
        preamble = "p" * 500
        sections = [section("a.py", "x" * 100)]

        _, report = apply_budget(preamble, sections, budget=10, count=CHARS, unit="chars")

        assert report.over_budget is True
        assert report.budget is not None
        assert report.emitted > report.budget

    def test_without_a_tokenizer_the_budget_is_not_applied_and_says_so(self) -> None:
        """Never silently ignored: a cap that quietly did nothing is worse."""
        sections = [section("a", "x" * 1000)]

        text, report = apply_budget("h", sections, budget=10, count=None, unit="o200k_base")

        assert "x" * 1000 in text
        assert report.applied is False

    def test_the_note_names_every_dropped_file_and_its_cost(self) -> None:
        sections = [section("a", "a" * 5), section("gone.py", "g" * 400)]

        _, report = apply_budget("h", sections, budget=60, count=CHARS, unit="chars")
        note = render_truncation_note(report)

        assert "Truncated to fit" in note
        assert "gone.py" in note
        assert "400" in note

    def test_no_note_when_nothing_was_dropped(self) -> None:
        _, report = apply_budget("h", [section("a", "x")], budget=999, count=CHARS, unit="chars")

        assert render_truncation_note(report) == ""


class TestTheDirectoryBreakdown:
    def test_it_rolls_up_through_every_ancestor(self) -> None:
        """A question about a subtree, not about a single level of it."""
        sections = [
            section("src/pkg/a.py", "x" * 100),
            section("src/pkg/b.py", "x" * 100),
            section("tests/t.py", "x" * 50),
        ]

        table = directory_totals(sections, count=CHARS, unit="chars")

        assert "| src | 200 |" in table
        assert "| src/pkg | 200 |" in table
        assert "| tests | 50 |" in table

    def test_shares_are_of_the_whole_pack(self) -> None:
        sections = [section("a/x.py", "x" * 75), section("b/y.py", "x" * 25)]

        table = directory_totals(sections, count=CHARS, unit="chars")

        assert "75.0%" in table
        assert "25.0%" in table

    def test_the_biggest_directory_comes_first(self) -> None:
        sections = [section("small/a", "x" * 10), section("big/b", "x" * 900)]

        table = directory_totals(sections, count=CHARS, unit="chars")
        rows = [line for line in table.splitlines() if line.startswith("| ")]

        assert rows[2].startswith("| big ")

    def test_a_file_at_the_root_is_still_credited_somewhere(self) -> None:
        """Otherwise top-level files vanish from the breakdown entirely."""
        table = directory_totals([section("README.md", "x" * 40)], count=CHARS, unit="chars")

        assert "| . | 40 |" in table

    def test_windows_separators_do_not_change_the_answer(self) -> None:
        """These paths come from three external tools on three platforms."""
        table = directory_totals([section("src\\pkg\\a.py", "x" * 10)], count=CHARS, unit="chars")

        assert "| src | 10 |" in table
        assert "| src/pkg | 10 |" in table

    def test_no_sections_yields_no_table_rather_than_an_empty_one(self) -> None:
        assert directory_totals([], count=CHARS, unit="chars") == ""


class TestGlobMatching:
    def test_a_bare_pattern_matches_a_nested_file(self) -> None:
        """`*.py` should mean what a user means by it."""
        assert matches_any("src/pkg/a.py", ["*.py"])

    def test_a_path_pattern_matches_the_whole_path(self) -> None:
        assert matches_any("src/pkg/a.py", ["src/*/a.py"])

    def test_a_non_match_is_a_non_match(self) -> None:
        assert not matches_any("src/a.py", ["*.md"])


class TestTheWorkingDirectory:
    def test_a_local_directory_is_used_in_place(self, tmp_path: Path) -> None:
        """Nothing is copied, and the user's own tree is never written to."""
        with repo_workdir(Source.from_path(tmp_path), ConvertOptions(), "test") as root:
            assert root == tmp_path.resolve()

    def test_a_file_is_not_a_repository(self, tmp_path: Path) -> None:
        target = tmp_path / "a.txt"
        target.write_text("x", encoding="utf-8")

        with (
            pytest.raises(CorruptSource, match="not a repository"),
            repo_workdir(Source.from_path(target), ConvertOptions(), "test"),
        ):
            pass  # pragma: no cover - the context manager raises on entry

    def test_offline_refuses_to_clone(self) -> None:
        source = Source.from_git("https://example.invalid/x.git")

        with (
            pytest.raises(NetworkRequired, match="disabled"),
            repo_workdir(source, ConvertOptions(fetch=False), "test"),
        ):
            pass  # pragma: no cover - the context manager raises on entry

    def test_an_ext_url_is_refused_because_it_makes_git_run_a_command(self) -> None:
        """`ext::sh -c ...` is remote code execution, not a transport."""
        with pytest.raises(ValueError, match="unsupported Git URL scheme"):
            Source.from_git("ext::sh -c 'touch /tmp/pwned'")

    def test_a_file_url_is_refused_too(self) -> None:
        with pytest.raises(ValueError, match="unsupported Git URL scheme"):
            Source.from_git("file:///etc")

    def test_a_scheme_that_slips_past_the_source_is_refused_at_the_clone(self) -> None:
        """Belt and braces: the check exists at both layers deliberately.

        A URL can become an `ext::` one through a redirect in a repository's own
        config, so the layer that would actually execute one checks again.
        """
        from tokenmill.core.models import SourceKind

        sneaky = Source(kind=SourceKind.REPO, name="x", url="ext::sh -c evil", format_hint="repo")

        with (
            pytest.raises(BackendFailed, match="refusing to clone"),
            repo_workdir(sneaky, ConvertOptions(), "test"),
        ):
            pass  # pragma: no cover - the context manager raises on entry
