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

from tokenmill.cli.format import format_table, format_tokens
from tokenmill.cli.main import app
from tokenmill.core.models import TokenCount

runner = CliRunner()

#: A tokenizer that needs no download, so CLI tests measure real numbers rather
#: than depending on network access.
OFFLINE = ["--tokenizer", "bytes"]


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
        result = runner.invoke(app, ["convert", str(page), *OFFLINE])

        assert result.exit_code == 0
        assert "# Title" in result.stdout
        assert "backend:" not in result.stdout
        assert "backend:  markdownify_html" in result.stderr

    def test_the_output_flag_writes_a_file(self, page: Path, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "out.md"

        result = runner.invoke(app, ["convert", str(page), "-o", str(target), *OFFLINE])

        assert result.exit_code == 0
        assert "# Title" in target.read_text(encoding="utf-8")
        assert f"wrote {target}" in result.stderr

    def test_quiet_suppresses_the_report_but_not_the_markdown(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), "--quiet", *OFFLINE])

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
        result = runner.invoke(app, ["convert", str(page), "--json", *OFFLINE])

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
        result = runner.invoke(app, ["convert", str(page), *OFFLINE])

        assert "[Nav](/x)" in result.stdout

    def test_a_tokenizer_that_cannot_load_still_yields_the_document(self, page: Path) -> None:
        result = runner.invoke(app, ["convert", str(page), "-t", "nonsense"])

        assert result.exit_code == 0
        assert "# Title" in result.stdout
        assert "not measured" in result.stderr


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

    def test_a_domain_with_no_backends_says_so_without_failing(self) -> None:
        result = runner.invoke(app, ["backends", "--domain", "repo"])

        assert result.exit_code == 0
        assert "no backends matched" in result.stderr


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

        result = self._run(tmp_path, "convert", str(page), "--tokenizer", "bytes")

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
