"""The CLI: output routing, error presentation, and the broken-backend gate.

:class:`TestBrokenBackendDoesNotCrashTheCli` is the second half of Phase 1's exit
gate. It installs a real distribution — a ``.dist-info`` directory with an
``entry_points.txt`` naming a module that raises on import — into a temporary
directory on ``PYTHONPATH``, then runs the CLI as a subprocess. That is the same
path a user's broken ``pip install`` would take, rather than a simulation of it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tokenmill.cli.format import _percent_change, format_bytes, format_table, format_tokens
from tokenmill.cli.main import app
from tokenmill.core.models import TokenCount

runner = CliRunner()

#: A tokenizer that needs no download, so CLI tests measure real numbers rather
#: than depending on network access.
OFFLINE = ["--tokenizer", "bytes"]

#: Pins the tests below that are about *the CLI* — where output goes, what the
#: JSON looks like, whether a post-processor ran — to the backend they were
#: written against.
#:
#: Phase 3 made trafilatura the default for HTML, which is a real and deliberate
#: change to what `tokenmill convert page.html` produces. These tests would
#: otherwise start failing for a reason that has nothing to do with what they
#: check: trafilatura *extracts*, so on the four-element page below it returns
#: prose with no `# Title` heading at all. Loosening the assertions would leave
#: them asserting nothing; naming the backend keeps them exact.
#:
#: The new default is covered by `TestTheDefaultBackendForAWebPage`, and the
#: extraction itself by `tests/integration/test_web_backends.py`.
RAW = ["--backend", "markdownify_html"]


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's own tokenmill config out of the CLI tests."""
    for name in list(__import__("os").environ):
        if name.startswith("TOKENMILL_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def page(tmp_path: Path) -> Path:
    """Write a small HTML page and return its path."""
    path = tmp_path / "page.html"
    path.write_text(
        "<html><body><nav><a href='/x'>Nav</a></nav>"
        "<h1>Title</h1><p>Body text here.</p></body></html>",
        encoding="utf-8",
    )
    return path


class TestConvert:
    def test_markdown_goes_to_stdout_and_the_report_to_stderr(self, page: Path) -> None:
        """So `tokenmill convert page.html > page.md` writes exactly Markdown."""
        result = runner.invoke(app, ["convert", str(page), *OFFLINE, *RAW])

        assert result.exit_code == 0
        assert "# Title" in result.stdout
        assert "backend:" not in result.stdout
        assert "backend:  markdownify_html" in result.stderr

    def test_the_output_flag_writes_a_file(self, page: Path, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "out.md"

        result = runner.invoke(app, ["convert", str(page), "-o", str(target), *OFFLINE, *RAW])

        assert result.exit_code == 0
        assert "# Title" in target.read_text(encoding="utf-8")
        assert f"wrote {target}" in result.stderr

    def test_quiet_suppresses_the_report_but_not_the_markdown(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), "--quiet", *OFFLINE, *RAW])

        assert "# Title" in result.stdout
        assert result.stderr.strip() == ""

    def test_the_report_shows_a_real_before_and_after(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), *OFFLINE])

        assert "tokens:" in result.stderr
        assert "->" in result.stderr

    def test_show_stages_lists_every_stage(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), "--show-stages", *OFFLINE])

        for stage in ("source", "convert", "normalize_whitespace"):
            assert stage in result.stderr

    def test_json_output_is_parseable_and_carries_the_counts(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), "--json", *OFFLINE, *RAW])

        payload = json.loads(result.stdout)

        assert payload["backend"] == "markdownify_html"
        assert payload["tokenizer"] == "bytes"
        assert payload["tokens_before"] > payload["tokens_after"] > 0
        assert payload["stages"]
        assert "# Title" in payload["text"]

    def test_an_unmeasured_run_reports_null_rather_than_omitting_the_field(
        self, page: Path
    ) -> None:
        """A consumer must be able to tell "not measured" from "measured zero"."""
        result = runner.invoke(app, ["convert", str(page), "--json", "-t", "nonsense"])

        payload = json.loads(result.stdout)

        assert payload["tokens_before"] is None
        assert payload["tokens_after"] is None
        assert payload["text"]

    def test_a_named_backend_is_used(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), "-b", "markdownify_html", *OFFLINE])

        assert result.exit_code == 0
        assert "backend:  markdownify_html" in result.stderr

    def test_an_unknown_backend_fails_with_a_message_not_a_traceback(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), "-b", "imaginary", *OFFLINE])

        assert result.exit_code == 1
        assert "error: no backend named 'imaginary'" in result.stderr
        assert "Traceback" not in result.stderr

    def test_a_missing_file_fails_with_a_hint(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["convert", str(tmp_path / "nope.html"), *OFFLINE])

        assert result.exit_code == 1
        assert "no such file" in result.stderr
        assert "hint:" in result.stderr

    def test_an_unsupported_format_lists_what_is_supported(self, tmp_path: Path) -> None:
        odd = tmp_path / "thing.wat"
        odd.write_text("x", encoding="utf-8")

        result = runner.invoke(app, ["convert", str(odd), *OFFLINE])

        assert result.exit_code == 1
        assert "no backend handles wat" in result.stderr

    def test_an_unknown_post_processor_fails_with_a_message(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), "--post", "nonsense", *OFFLINE])

        assert result.exit_code == 1
        assert "no post-processor named" in result.stderr

    def test_asking_for_link_stripping_pulls_in_the_destructive_processor(self, page: Path) -> None:
        """It is not in the default chain, so the flag would otherwise do nothing."""
        result = runner.invoke(app, ["convert", str(page), "--links", "strip", *OFFLINE])

        assert result.exit_code == 0
        assert "links" in result.stderr
        assert "[Nav](/x)" not in result.stdout
        assert "Nav" in result.stdout

    def test_the_default_chain_leaves_links_alone(self, page: Path) -> None:
        """About the post-processor chain, so the backend is pinned."""
        result = runner.invoke(app, ["convert", str(page), *OFFLINE, *RAW])

        assert "[Nav](/x)" in result.stdout

    def test_a_tokenizer_that_cannot_load_still_yields_the_document(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), "-t", "nonsense", *RAW])

        assert result.exit_code == 0
        assert "# Title" in result.stdout
        assert "not measured" in result.stderr


class TestTheDefaultBackendForAWebPage:
    """Phase 3 changed what `tokenmill convert page.html` produces."""

    @pytest.fixture
    def article(self, fixture_dir: Path) -> Path:
        """The corpus's noisy page — long enough for extraction to engage."""
        return fixture_dir / "boilerplate.html"

    def test_a_web_page_now_auto_selects_the_extractor(self, article: Path) -> None:
        result = runner.invoke(app, ["convert", str(article), *OFFLINE])

        assert result.exit_code == 0
        assert "backend:  trafilatura" in result.stderr

    def test_the_report_says_how_much_of_the_page_was_boilerplate(self, article: Path) -> None:
        """A second line, because it answers a different question from `tokens`."""
        result = runner.invoke(app, ["convert", str(article), *OFFLINE])

        assert "page:" in result.stderr
        assert "removed as boilerplate" in result.stderr
        assert "visible characters" in result.stderr

    def test_a_markup_conversion_says_it_removed_no_boilerplate(self, article: Path) -> None:
        """And that Markdown syntax made it bigger, which is the honest answer."""
        result = runner.invoke(app, ["convert", str(article), *OFFLINE, *RAW])

        assert "no boilerplate removed" in result.stderr
        assert "Markdown syntax added" in result.stderr

    def test_the_web_metrics_reach_the_json_output(self, article: Path) -> None:
        result = runner.invoke(app, ["convert", str(article), *OFFLINE, "--json"])

        payload = json.loads(result.stdout)

        assert payload["web"]["strips_boilerplate"] is True
        assert payload["web"]["boilerplate_reduction"] > 0
        assert payload["web"]["visible_text_characters"] > 0

    def test_a_document_conversion_carries_no_web_object(self, fixture_dir: Path) -> None:
        """Absent rather than null, and never a fabricated zero.

        Phase 5 changed this from `"web": null` to the key being absent, closing
        defect D9. The rule the payload now follows: `null` means "applies here,
        no value" and an absent key means "does not apply". A PDF has no
        visible-text ratio to have a value.
        """
        result = runner.invoke(
            app, ["convert", str(fixture_dir / "tables.pdf"), *OFFLINE, "--json"]
        )

        payload = json.loads(result.stdout)

        assert "web" not in payload


class TestTheFetchFlags:
    """The URL-fetching policy as a user sets it. No live URL is used."""

    def test_offline_refuses_a_url_rather_than_fetching_it(self) -> None:
        result = runner.invoke(
            app, ["convert", "https://example.invalid/page", "--offline", *OFFLINE]
        )

        assert result.exit_code == 1
        assert "disabled" in result.stderr
        assert "--offline" in result.stderr

    def test_offline_does_not_affect_a_local_file(self, page: Path) -> None:
        """The guarantee is about local conversions never reaching out at all."""
        result = runner.invoke(app, ["convert", str(page), "--offline", *OFFLINE, *RAW])

        assert result.exit_code == 0
        assert "# Title" in result.stdout

    def test_the_flags_are_documented_in_help(self) -> None:
        result = runner.invoke(app, ["convert", "--help"])

        for flag in ("--offline", "--ignore-robots", "--allow-network", "--user-agent"):
            assert flag in result.stdout

    def test_a_flag_that_was_not_passed_does_not_clobber_a_configured_value(
        self, tmp_path: Path
    ) -> None:
        """`--offline` is a flag, so its False must mean "not passed".

        The autouse fixture chdirs into ``tmp_path``, so a ``tokenmill.toml``
        written there is the one the CLI finds.
        """
        (tmp_path / "tokenmill.toml").write_text("fetch = false\n", encoding="utf-8")

        result = runner.invoke(
            app, ["convert", "https://example.invalid/page", "--tokenizer", "bytes"]
        )

        assert result.exit_code == 1
        assert "disabled" in result.stderr


class TestFallbackAtTheCommandLine:
    """The Phase 2 fallback chain, as a user sees it."""

    @pytest.fixture
    def corrupt_pdf(self, fixture_dir: Path) -> Path:
        """The corpus's truncated PDF, which every PDF backend refuses."""
        return fixture_dir / "corrupt.pdf"

    def test_a_file_no_backend_can_read_fails_and_lists_what_was_tried(
        self, corrupt_pdf: Path
    ) -> None:
        result = runner.invoke(app, ["convert", str(corrupt_pdf), *OFFLINE])

        assert result.exit_code == 1
        assert "pdfplumber" in result.output
        assert "pypdf" in result.output

    def test_no_fallback_stops_at_the_preferred_backend(self, corrupt_pdf: Path) -> None:
        result = runner.invoke(app, ["convert", str(corrupt_pdf), "--no-fallback", *OFFLINE])

        assert result.exit_code == 1
        assert "every backend" not in result.output

    def test_the_attempt_chain_reaches_the_json_output(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app, ["convert", str(fixture_dir / "tables.pdf"), *OFFLINE, "--json"]
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["attempts"] == [{"backend": "pdfplumber", "ok": True, "error": None}]

    def test_a_conversion_that_did_not_fall_back_prints_no_attempts_line(
        self, fixture_dir: Path
    ) -> None:
        """One backend, one line. The chain is only worth showing when it was walked."""
        result = runner.invoke(app, ["convert", str(fixture_dir / "tables.pdf"), *OFFLINE])

        assert result.exit_code == 0
        assert "attempts:" not in result.output

    def test_a_fallback_prints_the_chain_that_was_walked(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.html"
        empty.write_text("   \n", encoding="utf-8")

        result = runner.invoke(app, ["convert", str(empty), *OFFLINE])

        if result.exit_code != 0:
            pytest.skip("no document backend is installed to fall back to")
        # The head of the chain is whichever backend `preferences` ranks first
        # for HTML today, and that is allowed to change. What must not change is
        # that a walked chain is *shown*: the backend that failed, an arrow, and
        # the backend that produced the text.
        assert "attempts: " in result.output
        assert "(failed) ->" in result.output
        assert "backend:  " in result.output


class TestTheHeadlineForABinaryDocument:
    """A document conversion reports what the output costs, not a fake saving."""

    def test_it_reports_the_output_cost_and_the_input_size(self, fixture_dir: Path) -> None:
        result = runner.invoke(app, ["convert", str(fixture_dir / "report.docx"), *OFFLINE])

        assert result.exit_code == 0
        assert "no comparable before" in result.output
        assert "->" not in result.output.split("tokens:")[1].splitlines()[0]

    def test_it_prints_no_percentage(self, fixture_dir: Path) -> None:
        """A percentage here would be between a zip archive and its text. Meaningless."""
        result = runner.invoke(app, ["convert", str(fixture_dir / "report.docx"), *OFFLINE])
        headline = result.output.split("tokens:")[1].splitlines()[0]

        assert "%" not in headline

    def test_a_text_source_still_gets_its_before_and_after(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), *OFFLINE])
        headline = result.output.split("tokens:")[1].splitlines()[0]

        assert "->" in headline
        assert "%" in headline

    def test_the_json_carries_the_size_and_a_null_before(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app, ["convert", str(fixture_dir / "report.docx"), *OFFLINE, "--json"]
        )
        payload = json.loads(result.output)

        assert payload["tokens_before"] is None
        assert payload["source_bytes"] == (fixture_dir / "report.docx").stat().st_size
        assert payload["tokens_after"] is not None


class TestFormatBytes:
    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (0, "0 B"),
            (512, "512 B"),
            (1024, "1.0 KiB"),
            (38_297, "37.4 KiB"),
            (5 * 1024 * 1024, "5.0 MiB"),
            (3 * 1024**3, "3.0 GiB"),
        ],
    )
    def test_it_picks_a_readable_unit(self, count: int, expected: str) -> None:
        assert format_bytes(count) == expected


class TestBackends:
    def test_it_lists_the_reference_backends_with_licences(self) -> None:
        result = runner.invoke(app, ["backends"])

        assert result.exit_code == 0
        assert "plaintext" in result.stdout
        assert "markdownify_html" in result.stdout
        assert "MIT" in result.stdout
        assert "permissive" in result.stdout

    def test_the_licence_column_is_present_for_every_row(self) -> None:
        """Licence tiering is a visible product feature, not documentation."""
        result = runner.invoke(app, ["backends", "--all"])

        assert "license" in result.stdout
        assert "isolation" in result.stdout

    def test_domain_filtering_works(self) -> None:
        result = runner.invoke(app, ["backends", "--domain", "web"])

        assert "markdownify_html" in result.stdout
        assert "plaintext" not in result.stdout

    def test_json_output_carries_the_full_metadata(self) -> None:
        result = runner.invoke(app, ["backends", "--json"])

        payload = {entry["id"]: entry for entry in json.loads(result.stdout)}

        assert payload["markdownify_html"]["license"] == "MIT"
        assert payload["markdownify_html"]["license_tier"] == "permissive"
        assert payload["markdownify_html"]["isolation"] == "in-process"
        assert payload["markdownify_html"]["available"] is True
        assert payload["plaintext"]["input_formats"]

    def test_the_repo_domain_now_lists_the_repository_backends(self) -> None:
        """Phase 4 filled a domain that used to be empty.

        This test previously asserted that `--domain repo` matched nothing,
        which was true until the repository backends existed. Repointed rather
        than deleted: what it is really about is that `--domain` filters, and
        that is still worth asserting.
        """
        result = runner.invoke(app, ["backends", "--domain", "repo", "--all"])

        assert result.exit_code == 0
        assert "gitingest" in result.stdout
        assert "pdfplumber" not in result.stdout

    def test_an_empty_listing_says_so_without_failing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every domain has a backend now, so the empty case needs an empty registry.

        The branch is still reachable in the wild — a domain whose backends are
        all uninstalled lists nothing without `--all` — so it keeps its test.
        """
        from tokenmill.core.registry import Registry

        # An entry point group nothing registers under, so discovery succeeds
        # and finds nothing. A bare `Registry()` would scan the real group.
        monkeypatch.setattr(
            "tokenmill.cli.main.default_registry",
            lambda: Registry("tokenmill.backends.deliberately-absent"),
        )

        result = runner.invoke(app, ["backends"])

        assert result.exit_code == 0
        assert "no backends matched" in result.stderr
        assert "--all" in result.stderr


class TestTokens:
    def test_it_counts_a_file(self, tmp_path: Path) -> None:
        target = tmp_path / "a.txt"
        target.write_text("abcdef", encoding="utf-8")

        result = runner.invoke(app, ["tokens", str(target), *OFFLINE])

        assert result.exit_code == 0
        assert "6" in result.stdout

    def test_it_counts_a_literal_string(self) -> None:
        result = runner.invoke(app, ["tokens", "--text", "café", *OFFLINE])

        assert result.exit_code == 0
        assert "5" in result.stdout

    def test_a_non_model_tokenizer_is_labelled_as_such(self) -> None:
        """`bytes` must never be mistaken for a model token count."""
        result = runner.invoke(app, ["tokens", "--text", "abc", "-t", "bytes"])

        assert "do not quote this as a token count" in result.stderr

    def test_json_output_says_what_is_being_counted(self) -> None:
        result = runner.invoke(app, ["tokens", "--text", "abc", "--json", *OFFLINE])

        payload = json.loads(result.stdout)

        assert payload["tokens"] == 3
        assert payload["counts"] == "UTF-8 bytes"
        assert payload["is_model_tokenizer"] is False

    def test_list_shows_the_registered_tokenizers(self) -> None:
        result = runner.invoke(app, ["tokens", "--list"])

        assert "o200k_base" in result.stdout
        assert "bytes" in result.stdout
        assert "hf:<spec>" in result.stdout

    def test_giving_both_a_path_and_text_is_refused(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["tokens", str(tmp_path), "--text", "x", *OFFLINE])

        assert result.exit_code == 1
        assert "exactly one" in result.stderr

    def test_giving_neither_is_refused(self) -> None:
        result = runner.invoke(app, ["tokens", *OFFLINE])

        assert result.exit_code == 1
        assert "exactly one" in result.stderr

    def test_an_unloadable_tokenizer_reports_the_reason_and_a_hint(self, tmp_path: Path) -> None:
        """Unlike `convert`, counting is the whole job here, so it must fail."""
        target = tmp_path / "a.txt"
        target.write_text("x", encoding="utf-8")

        result = runner.invoke(app, ["tokens", str(target), "-t", "nonsense"])

        assert result.exit_code == 1
        assert "unknown tokenizer" in result.stderr
        assert "hint:" in result.stderr


class TestRootOptions:
    def test_version_prints_and_exits(self) -> None:
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "tokenmill" in result.stdout

    def test_no_arguments_prints_help_rather_than_an_error(self) -> None:
        result = runner.invoke(app, [])

        assert result.exit_code == 0
        assert "convert" in result.stdout


class TestFormatting:
    def test_a_table_aligns_columns_and_has_no_trailing_whitespace(self) -> None:
        table = format_table(["a", "bbb"], [["xxxx", "y"]])

        for line in table.split("\n"):
            assert line == line.rstrip()
        assert "xxxx" in table

    def test_a_table_with_no_rows_still_shows_its_shape(self) -> None:
        table = format_table(["id", "license"], [])

        assert "id" in table
        assert "license" in table

    def test_a_row_of_the_wrong_width_is_refused(self) -> None:
        with pytest.raises(ValueError, match="expected 2"):
            format_table(["a", "b"], [["only-one"]])

    def test_an_unmeasured_count_renders_as_na_never_as_zero(self) -> None:
        assert format_tokens(None) == "n/a"
        assert format_tokens(TokenCount(0, "t")) == "0"

    def test_counts_get_thousands_separators(self) -> None:
        assert format_tokens(TokenCount(1234567, "t")) == "1,234,567"

    def test_a_reduction_is_reported_as_a_negative_change(self) -> None:
        assert _percent_change(1000, 550) == "-45.0%"

    def test_growth_is_reported_as_growth_not_as_a_reduction(self) -> None:
        """A conversion that made the document bigger must not read as a saving.

        Observed on a real third-party backend whose Markdown table was larger
        than its CSV input: the report said "-71.0%" for a 71% increase.
        """
        assert _percent_change(62, 106) == "+71.0%"

    def test_no_change_says_so_rather_than_printing_zero_percent(self) -> None:
        assert _percent_change(100, 100) == "unchanged"

    def test_a_change_from_zero_has_no_meaningful_percentage(self) -> None:
        assert _percent_change(0, 50) == "n/a"


class TestBrokenBackendDoesNotCrashTheCli:
    """Phase 1 exit gate: a broken plugin is reported, not fatal."""

    @staticmethod
    def _install_broken_plugin(root: Path) -> None:
        """Write a distribution whose backend entry point raises on import.

        Args:
            root: A directory that will be placed on ``PYTHONPATH``.
        """
        (root / "brokenmill.py").write_text(
            "raise ImportError(\"No module named 'definitely_not_installed'\")\n",
            encoding="utf-8",
        )
        dist = root / "brokenmill-0.1.0.dist-info"
        dist.mkdir()
        dist.joinpath("METADATA").write_text(
            "Metadata-Version: 2.1\nName: brokenmill\nVersion: 0.1.0\n", encoding="utf-8"
        )
        dist.joinpath("entry_points.txt").write_text(
            "[tokenmill.backends]\nbrokenmill = brokenmill:BrokenConverter\n", encoding="utf-8"
        )

    def _run(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the CLI as a subprocess with the broken plugin installed.

        Args:
            root: The directory holding the broken distribution.
            *args: Arguments to the CLI.

        Returns:
            The completed process.
        """
        env = {**__import__("os").environ, "PYTHONPATH": str(root)}
        return subprocess.run(  # noqa: S603
            [sys.executable, "-m", "tokenmill.cli.main", *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_backends_lists_the_broken_plugin_as_unavailable(self, tmp_path: Path) -> None:
        self._install_broken_plugin(tmp_path)

        result = self._run(tmp_path, "backends", "--all")

        assert result.returncode == 0, result.stderr
        assert "brokenmill" in result.stdout
        assert "failed to load" in result.stdout
        assert "Traceback" not in result.stderr

    def test_the_working_backends_are_unaffected(self, tmp_path: Path) -> None:
        self._install_broken_plugin(tmp_path)

        result = self._run(tmp_path, "backends")

        assert result.returncode == 0, result.stderr
        assert "plaintext" in result.stdout
        assert "markdownify_html" in result.stdout

    def test_conversion_still_works_with_a_broken_plugin_installed(
        self, tmp_path: Path, page: Path
    ) -> None:
        self._install_broken_plugin(tmp_path)

        result = self._run(tmp_path, "convert", str(page), "--tokenizer", "bytes", *RAW)

        assert result.returncode == 0, result.stderr
        assert "# Title" in result.stdout

    def test_asking_for_the_broken_backend_by_name_is_a_clean_error(
        self, tmp_path: Path, page: Path
    ) -> None:
        self._install_broken_plugin(tmp_path)

        result = self._run(tmp_path, "convert", str(page), "-b", "brokenmill")

        assert result.returncode == 1
        assert "failed to load" in result.stderr
        assert "Traceback" not in result.stderr


class TestFidelity:
    """`tokenmill fidelity` — the second half of every token measurement."""

    def test_it_scores_converted_text_against_a_fixture(
        self, fixture_dir: Path, tmp_path: Path
    ) -> None:
        converted = tmp_path / "out.md"
        converted.write_text(
            "# Why Your Context Window Is Mostly Navigation Menus\n", encoding="utf-8"
        )
        result = runner.invoke(
            app,
            [
                "fidelity",
                str(converted),
                "--against",
                "boilerplate.html",
                "--corpus",
                str(fixture_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "heading_recall" in result.output
        assert "overall:" in result.output

    def test_a_component_without_ground_truth_prints_n_a_never_zero(
        self, fixture_dir: Path, tmp_path: Path
    ) -> None:
        converted = tmp_path / "out.md"
        converted.write_text("nothing in particular\n", encoding="utf-8")
        result = runner.invoke(
            app,
            ["fidelity", str(converted), "-a", "boilerplate.html", "--corpus", str(fixture_dir)],
        )
        assert result.exit_code == 0, result.output
        reading_order = next(
            line for line in result.output.splitlines() if line.startswith("reading_order")
        )
        assert "n/a" in reading_order
        assert "0.000" not in reading_order

    def test_the_overall_names_what_it_is_made_of(self, fixture_dir: Path, tmp_path: Path) -> None:
        converted = tmp_path / "out.md"
        converted.write_text("# Converter Comparison\n", encoding="utf-8")
        result = runner.invoke(
            app,
            ["fidelity", str(converted), "-a", "tables.pdf", "--corpus", str(fixture_dir)],
        )
        assert "unweighted mean of" in result.output

    def test_json_carries_null_for_a_component_that_did_not_apply(
        self, fixture_dir: Path, tmp_path: Path
    ) -> None:
        converted = tmp_path / "out.md"
        converted.write_text("# Converter Comparison\n", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "fidelity",
                str(converted),
                "-a",
                "tables.pdf",
                "--corpus",
                str(fixture_dir),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        by_name = {c["component"]: c for c in payload["components"]}
        assert by_name["reading_order"]["score"] is None
        assert set(payload["scored_components"]) <= set(by_name)

    def test_it_reads_standard_input(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app,
            ["fidelity", "-", "-a", "tables.pdf", "--corpus", str(fixture_dir)],
            input="# Converter Comparison\n",
        )
        assert result.exit_code == 0, result.output
        assert "heading_recall" in result.output

    def test_an_unknown_fixture_lists_the_known_ones(
        self, fixture_dir: Path, tmp_path: Path
    ) -> None:
        converted = tmp_path / "out.md"
        converted.write_text("x\n", encoding="utf-8")
        result = runner.invoke(
            app,
            ["fidelity", str(converted), "-a", "nope.pdf", "--corpus", str(fixture_dir)],
        )
        assert result.exit_code == 1
        assert "tables.pdf" in result.output

    def test_a_missing_corpus_names_the_generator(self, tmp_path: Path) -> None:
        converted = tmp_path / "out.md"
        converted.write_text("x\n", encoding="utf-8")
        result = runner.invoke(
            app,
            ["fidelity", str(converted), "-a", "tables.pdf", "--corpus", str(tmp_path / "gone")],
        )
        assert result.exit_code == 1
        assert "make_fixtures.py" in result.output

    def test_a_binary_input_says_to_convert_it_first(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app,
            [
                "fidelity",
                str(fixture_dir / "tables.pdf"),
                "-a",
                "tables.pdf",
                "--corpus",
                str(fixture_dir),
            ],
        )
        assert result.exit_code == 1
        assert "convert" in result.output


class TestJsonProvenance:
    """Defect D9: the JSON was inconsistent in two ways a consumer would trip on."""

    def test_the_unit_travels_with_the_number(self, fixture_dir: Path) -> None:
        # Without this, a consumer reading `"tokenizer": "bytes"` has no
        # machine-readable signal that these are not model tokens, and the only
        # warning was a sentence on stderr.
        result = runner.invoke(
            app, ["convert", str(fixture_dir / "tables.pdf"), "--json", *OFFLINE]
        )
        payload = json.loads(result.output)
        assert payload["counts"] == "UTF-8 bytes"
        assert payload["is_model_tokenizer"] is False

    def test_the_web_object_is_absent_rather_than_null_for_a_document(
        self, fixture_dir: Path
    ) -> None:
        # `null` means "applies here, no value"; an absent key means "does not
        # apply". A PDF has no web measurement to have a value.
        result = runner.invoke(
            app, ["convert", str(fixture_dir / "tables.pdf"), "--json", *OFFLINE]
        )
        assert "web" not in json.loads(result.output)

    def test_the_web_object_is_present_for_a_page(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app, ["convert", str(fixture_dir / "boilerplate.html"), "--json", *OFFLINE]
        )
        payload = json.loads(result.output)
        assert "web" in payload
        assert payload["web"]["strips_boilerplate"] is True

    def test_token_counts_stay_null_rather_than_absent(self, fixture_dir: Path) -> None:
        # The other half of the rule: a binary document has no comparable
        # before-count, and null is how that is said.
        result = runner.invoke(
            app, ["convert", str(fixture_dir / "tables.pdf"), "--json", *OFFLINE]
        )
        payload = json.loads(result.output)
        assert "tokens_before" in payload
        assert payload["tokens_before"] is None
        assert payload["source_bytes"] is not None

    def test_compare_json_carries_the_same_provenance(self, fixture_dir: Path) -> None:
        result = runner.invoke(
            app, ["compare", str(fixture_dir / "tables.pdf"), "--json", *OFFLINE]
        )
        payload = json.loads(result.output)
        assert payload["backends"]["counts"] == "UTF-8 bytes"
        assert payload["backends"]["is_model_tokenizer"] is False
