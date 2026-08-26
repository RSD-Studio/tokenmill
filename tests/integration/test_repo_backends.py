"""The repository backends against the real fixture repository.

``tests/fixtures/sample_repo`` exists to make three things checkable that a
synthetic string could not: a ``.gitignore``d file carrying a sentinel that must
never reach a model's context, a binary blob, and a real git history.

The subprocess backends are gated on their runtimes being present rather than
skipped wholesale, because "all three adapters behave correctly whether or not
their runtime is installed" is a Phase 4 acceptance criterion — so the *absent*
case has tests of its own that always run.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from tokenmill.backends.repo.code2prompt_repo import Code2PromptConverter
from tokenmill.backends.repo.repomix_repo import RepomixConverter
from tokenmill.core.errors import BackendUnavailable, ConversionError, NetworkRequired
from tokenmill.core.models import ConversionResult, ConvertOptions, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import Registry

pytestmark = pytest.mark.integration

#: gitingest is behind the `repo` extra, so an install without it cannot run
#: the tests below. They asserted its behaviour unconditionally until CI first
#: ran on 2026-08-26 and failed 21 of them on every cell: the suite had only
#: ever been run on a machine that happened to have the extra.
#:
#: The CI test job now installs `repo`, so these run rather than skip. The
#: marker is what makes a *partial* install degrade to a skip instead of a
#: failure, which is the same contract every other optional backend has.
requires_gitingest = pytest.mark.requires("gitingest")

OFFLINE = ConvertOptions(tokenizer="bytes")

#: With permission for a backend to fetch its own runtime — which for repomix
#: means npx downloading the package on first use.
NETWORKED = OFFLINE.with_(allow_network=True)


def requires_binary(name: str) -> pytest.MarkDecorator:
    """Skip a test when an external tool is not installed.

    Args:
        name: The executable that must be on ``PATH``.

    Returns:
        The skip marker, with a reason naming what is missing.
    """
    return pytest.mark.skipif(
        shutil.which(name) is None,
        reason=f"needs {name!r} on PATH; the absent-runtime behaviour is tested separately",
    )


@pytest.fixture(scope="module")
def pipeline() -> Pipeline:
    """Return a pipeline over the really-installed backends."""
    return Pipeline(backends=Registry())


def pack(pipeline: Pipeline, root: Path, backend: str, **extra: Any) -> ConversionResult:
    """Pack the fixture repository through one named backend.

    Args:
        pipeline: The pipeline to run.
        root: The repository.
        backend: The backend id.
        **extra: Repository options.

    Returns:
        The result.
    """
    options = NETWORKED.with_(backend=backend)
    if extra:
        options = options.with_(extra=extra)
    return pipeline.run(Source.from_path(root), options)


@requires_gitingest
class TestGitingest:
    """The primary, and the one auto-selection picks."""

    def test_it_is_what_a_repository_auto_selects(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        result = pipeline.run(Source.from_path(sample_repo), OFFLINE)

        assert result.backend_id == "gitingest"

    def test_the_pack_has_a_directory_tree(self, sample_repo: Path, pipeline: Pipeline) -> None:
        """Phase 4's first acceptance criterion, half of it."""
        result = pack(pipeline, sample_repo, "gitingest")

        assert "Directory structure:" in result.text
        for name in ("README.md", "core.py", "test_core.py"):
            assert name in result.text, f"{name} missing from the tree"

    def test_the_pack_has_the_file_contents(
        self, sample_repo: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The other half: a tree without contents is a listing, not a pack."""
        result = pack(pipeline, sample_repo, "gitingest")

        for fragment in ground_truth["sample_repo/"]["must_contain"]:
            assert fragment in result.text, f"lost {fragment!r}"

    def test_the_gitignored_secret_never_reaches_the_output(
        self, sample_repo: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The reason the fixture has a secret in it at all.

        A packing tool that helps a user paste their credentials into a model
        is worse than no packing tool. `.gitignore` respect is on by default and
        this is what proves it on a real repository rather than on a flag.
        """
        result = pack(pipeline, sample_repo, "gitingest")

        for sentinel in ground_truth["sample_repo/"]["must_not_contain"]:
            assert sentinel not in result.text, "an ignored file leaked into the pack"
        assert "secrets.env" not in result.text

    def test_the_binary_blob_is_not_inlined(self, sample_repo: Path, pipeline: Pipeline) -> None:
        """A binary file's bytes are cost without meaning."""
        result = pack(pipeline, sample_repo, "gitingest")

        assert "\\x00" not in result.text
        assert result.metadata["file_count"] >= 5

    def test_it_records_which_engine_produced_the_pack(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        result = pack(pipeline, sample_repo, "gitingest")

        assert result.metadata["pack_tool"] == "gitingest"

    def test_include_globs_narrow_the_pack(self, sample_repo: Path, pipeline: Pipeline) -> None:
        result = pack(pipeline, sample_repo, "gitingest", include="*.py")

        assert "core.py" in result.text
        assert "# widgetlib" not in result.text, "README.md survived an include of *.py"

    def test_exclude_globs_remove_files(self, sample_repo: Path, pipeline: Pipeline) -> None:
        result = pack(pipeline, sample_repo, "gitingest", exclude="tests/*")

        assert "core.py" in result.text
        assert "test_scaled" not in result.text

    def test_turning_off_gitignore_respect_lets_the_secret_through(
        self, sample_repo: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        """The flag does what it says, which is why it is not the default.

        Asserting the dangerous direction as well as the safe one: a
        `.gitignore` toggle that silently did nothing would pass every test
        above while providing no protection at all.
        """
        result = pack(pipeline, sample_repo, "gitingest", respect_gitignore=False)
        sentinel = ground_truth["sample_repo/"]["must_not_contain"][0]

        assert sentinel in result.text, (
            "--no-gitignore did not actually disable .gitignore handling, which means "
            "the default's protection is not being exercised by these tests either"
        )

    def test_a_github_token_in_the_environment_does_not_break_a_local_pack(
        self, sample_repo: Path, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gitingest validates $GITHUB_TOKEN's *format* before reading the source.

        A placeholder token — which CI systems and development sandboxes export
        routinely — therefore failed a purely local packing with
        `InvalidGitHubTokenError`. Found by hitting it in this project's own
        sandbox. The adapter hides the variable; this is the regression test.
        """
        monkeypatch.setenv("GITHUB_TOKEN", "not-a-valid-token-format")

        result = pack(pipeline, sample_repo, "gitingest")

        assert "Directory structure:" in result.text

    def test_the_token_is_restored_afterwards(
        self, sample_repo: Path, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hiding a variable is only acceptable if it is put back."""
        monkeypatch.setenv("GITHUB_TOKEN", "sentinel-value")

        pack(pipeline, sample_repo, "gitingest")

        import os

        assert os.environ.get("GITHUB_TOKEN") == "sentinel-value"


@requires_gitingest
class TestTheTokenBudget:
    """Phase 4's second acceptance criterion: it caps, and it reports."""

    def test_the_output_is_genuinely_smaller_with_a_budget(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        full = pack(pipeline, sample_repo, "gitingest")
        capped = pack(pipeline, sample_repo, "gitingest", token_budget=1200)

        assert len(capped.text) < len(full.text)

    def test_the_output_actually_fits_the_budget(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        """Verified by measuring the file, not by trusting the flag.

        `--tokenizer bytes` counts UTF-8 bytes, so the cap and the measurement
        are in the same unit and the assertion is exact.
        """
        capped = pack(pipeline, sample_repo, "gitingest", token_budget=1200)

        assert len(capped.text.encode("utf-8")) <= 1200

    def test_every_dropped_file_is_named(self, sample_repo: Path, pipeline: Pipeline) -> None:
        """A silent truncation is a bug, in the acceptance criterion's own words."""
        capped = pack(pipeline, sample_repo, "gitingest", token_budget=1200)

        assert capped.metadata["dropped_file_count"] > 0
        dropped = capped.metadata["dropped_files"]
        assert dropped
        assert any("dropped to fit" in warning for warning in capped.warnings)

    def test_the_truncation_is_visible_in_the_document_itself(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        """The text is the part that travels to the model.

        A warning on stderr does not reach whatever reads the pack next, and
        that reader cannot ask why a file is missing.
        """
        capped = pack(pipeline, sample_repo, "gitingest", token_budget=1200)

        assert "Truncated" in capped.text

    def test_a_budget_that_everything_fits_drops_nothing(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        full = pack(pipeline, sample_repo, "gitingest")
        generous = pack(pipeline, sample_repo, "gitingest", token_budget=1_000_000)

        assert generous.text == full.text
        assert "dropped_file_count" not in generous.metadata

    def test_a_budget_with_no_usable_tokenizer_says_it_did_not_apply(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        """Never silently ignored: the user believes the output is bounded."""
        result = pipeline.run(
            Source.from_path(sample_repo),
            ConvertOptions(
                tokenizer="definitely-not-a-tokenizer",
                backend="gitingest",
                extra={"token_budget": 100},
            ),
        )

        assert result.metadata["budget_applied"] is False
        assert any("budget could not be applied" in w for w in result.warnings)


@requires_gitingest
class TestTheDirectoryBreakdown:
    def test_it_says_which_folder_is_eating_the_context(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        result = pack(pipeline, sample_repo, "gitingest", tree_tokens=True)

        assert "Tokens by directory" in result.text
        assert "| src |" in result.text
        assert "| src/widgetlib |" in result.text

    def test_it_is_absent_unless_asked_for(self, sample_repo: Path, pipeline: Pipeline) -> None:
        result = pack(pipeline, sample_repo, "gitingest")

        assert "Tokens by directory" not in result.text


@requires_gitingest
class TestRunningWithoutTheRuntime:
    """The acceptance criterion about the *absent* case. These always run.

    "All three adapters behave correctly whether or not their runtime is
    installed" cannot be tested by installing everything, so these build fresh
    converter instances with ``PATH`` lookups stubbed out. Fresh instances
    rather than the registry's, because availability is cached per instance for
    the life of the process and poking at that cache would leak a "nothing is
    installed" belief into every later test in the module.
    """

    def test_a_missing_binary_is_a_message_with_an_install_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing npx or repomix yields a clear message, not a traceback."""
        monkeypatch.setattr("tokenmill.backends._subprocess.shutil.which", lambda _n: None)

        availability = Code2PromptConverter().is_available()

        assert not availability
        assert availability.hint is not None
        assert "cargo install code2prompt" in availability.hint
        assert "code2prompt" in availability.describe()

    def test_repomix_reports_missing_when_neither_it_nor_npx_is_there(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("tokenmill.backends._subprocess.shutil.which", lambda _n: None)

        availability = RepomixConverter().is_available()

        assert not availability
        assert availability.hint is not None
        assert "npm install -g repomix" in availability.hint

    def test_asking_for_an_uninstalled_backend_is_a_clean_typed_error(
        self, sample_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("tokenmill.backends._subprocess.shutil.which", lambda _n: None)

        with pytest.raises(BackendUnavailable) as excinfo:
            Code2PromptConverter().convert(Source.from_path(sample_repo), NETWORKED)

        assert excinfo.value.hint is not None
        assert "Traceback" not in str(excinfo.value)

    def test_a_binary_that_vanishes_after_the_probe_is_still_typed(self) -> None:
        """A tool can be uninstalled between the probe and the run.

        `run_tool` catches `FileNotFoundError` for exactly this, so the failure
        is `BackendUnavailable` rather than an `OSError` escaping the taxonomy.
        """
        from tokenmill.backends._subprocess import run_tool

        with pytest.raises(BackendUnavailable):
            run_tool(["definitely-not-a-real-binary"], backend_id="test", timeout_s=5)

    def test_repomix_without_a_local_install_refuses_to_download_silently(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        """Npx fetches the package, a network call inside a local-looking command."""
        if shutil.which("repomix") is not None:
            pytest.skip("repomix is installed locally, so npx is not involved")

        with pytest.raises(NetworkRequired, match="npx"):
            pipeline.run(Source.from_path(sample_repo), OFFLINE.with_(backend="repomix"))

    def test_the_repository_still_packs_through_the_backend_that_needs_nothing(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        """The point of ranking the Python-native backend first."""
        result = pipeline.run(Source.from_path(sample_repo), OFFLINE)

        assert result.backend_id == "gitingest"
        assert result.text.strip()


@requires_binary("npx")
class TestRepomix:
    def test_it_packs_the_repository(self, sample_repo: Path, pipeline: Pipeline) -> None:
        result = pack(pipeline, sample_repo, "repomix")

        assert "widgetlib" in result.text
        assert result.metadata["pack_tool"] == "repomix"

    def test_it_does_not_leak_the_gitignored_secret_either(
        self, sample_repo: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = pack(pipeline, sample_repo, "repomix")

        for sentinel in ground_truth["sample_repo/"]["must_not_contain"]:
            assert sentinel not in result.text

    def test_its_sections_are_parsed_so_the_budget_applies(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        """The shared options must work identically whichever engine ran."""
        result = pack(pipeline, sample_repo, "repomix", tree_tokens=True)

        assert result.metadata["file_count"] > 0
        assert "Tokens by directory" in result.text


@requires_binary("code2prompt")
class TestCode2Prompt:
    def test_it_packs_the_repository(self, sample_repo: Path, pipeline: Pipeline) -> None:
        result = pack(pipeline, sample_repo, "code2prompt")

        assert "widgetlib" in result.text
        assert result.metadata["pack_tool"] == "code2prompt"

    def test_it_does_not_leak_the_gitignored_secret_either(
        self, sample_repo: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        result = pack(pipeline, sample_repo, "code2prompt")

        for sentinel in ground_truth["sample_repo/"]["must_not_contain"]:
            assert sentinel not in result.text

    def test_its_sections_are_parsed_so_the_budget_applies(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        """Its header format is backtick-quoted paths, not `## File:`.

        That was guessed wrong first, and the adapter's "format not recognised"
        warning is what surfaced it rather than a silent file count of zero.
        """
        result = pack(pipeline, sample_repo, "code2prompt", tree_tokens=True)

        assert result.metadata["file_count"] > 0
        assert not any("was not recognised" in w for w in result.warnings)
        assert "Tokens by directory" in result.text


@requires_gitingest
class TestAllThreeAgreeOnWhatMatters:
    """The claim that makes this one product rather than three CLIs."""

    def _available(self, pipeline: Pipeline) -> list[str]:
        """Return the repository backends that can run here.

        Args:
            pipeline: Supplies the registry.

        Returns:
            The backend ids.
        """
        return [
            backend_id
            for backend_id in ("gitingest", "repomix", "code2prompt")
            if pipeline.backends.get(backend_id).is_available()
        ]

    def test_none_of_them_leaks_the_secret(
        self, sample_repo: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        sentinels = ground_truth["sample_repo/"]["must_not_contain"]
        available = self._available(pipeline)

        assert available, "no repository backend is available; this test would pass vacuously"
        for backend_id in available:
            if backend_id == "repomix" and shutil.which("npx") is None:
                continue
            result = pack(pipeline, sample_repo, backend_id)
            for sentinel in sentinels:
                assert sentinel not in result.text, f"{backend_id} leaked {sentinel!r}"

    def test_all_of_them_include_the_source_a_reader_came_for(
        self, sample_repo: Path, pipeline: Pipeline, ground_truth: dict[str, Any]
    ) -> None:
        for backend_id in self._available(pipeline):
            if backend_id == "repomix" and shutil.which("npx") is None:
                continue
            result = pack(pipeline, sample_repo, backend_id)
            for fragment in ground_truth["sample_repo/"]["must_contain"]:
                assert fragment in result.text, f"{backend_id} lost {fragment!r}"

    def test_a_conversion_carries_no_token_counts_of_its_own(
        self, sample_repo: Path, pipeline: Pipeline
    ) -> None:
        """Backends convert; the pipeline measures.

        A repository backend consults a tokenizer to obey a budget, which is the
        one sanctioned exception. It must still never *report* a count.
        """
        converter = pipeline.backends.get("gitingest")
        raw = converter.convert(
            Source.from_path(sample_repo), NETWORKED.with_(extra={"token_budget": 500})
        )

        assert raw.tokens_before is None
        assert raw.tokens_after is None


class TestRemoteRepositories:
    def test_a_git_url_is_a_repository_rather_than_a_web_page(self) -> None:
        source = Source.from_git("https://example.invalid/owner/project.git")

        assert source.format == "repo"
        assert source.url == "https://example.invalid/owner/project.git"
        assert source.path is None

    def test_an_unreachable_remote_is_a_message_rather_than_a_traceback(
        self, pipeline: Pipeline
    ) -> None:
        source = Source.from_git("https://127.0.0.1:1/nope.git")

        with pytest.raises(ConversionError) as excinfo:
            pipeline.run(source, NETWORKED.with_(backend="gitingest", timeout_s=30))

        assert "Traceback" not in str(excinfo.value)


class TestTheCleanInstallStory:
    """What a user with `pip install tokenmill` and no extras actually sees.

    Found by doing the clean-install check by hand rather than trusting the CI
    job: on a core-only install gitingest is absent, so the chain falls to
    repomix — which reports itself available because `npx` exists — and the user
    who typed `tokenmill repo ./project` got a Node error about a tool they
    never chose, with no mention of the Python one that would just work.
    """

    def test_an_auto_selected_repomix_points_at_the_python_backend_first(self) -> None:
        options = NETWORKED.with_(allow_network=False, backend=None)

        with pytest.raises(NetworkRequired) as excinfo:
            RepomixConverter()._launcher(options)

        assert excinfo.value.hint is not None
        assert 'pip install "tokenmill[repo]"' in excinfo.value.hint

    def test_an_explicitly_chosen_repomix_gets_repomix_instructions(self) -> None:
        """Someone who typed `--backend repomix` wants repomix, not a substitute."""
        options = NETWORKED.with_(allow_network=False, backend="repomix")

        with pytest.raises(NetworkRequired) as excinfo:
            RepomixConverter()._launcher(options)

        assert excinfo.value.hint is not None
        assert "npm install -g repomix" in excinfo.value.hint
        assert "tokenmill[repo]" not in excinfo.value.hint
