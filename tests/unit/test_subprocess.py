"""The minimum subprocess runner Phase 4 needs and Phase 7 replaces.

What is worth guarding here is small and sharp: arguments are a list and never
a shell string, a path that reads as an option is refused rather than passed,
and every way a child process can go wrong lands somewhere in the error
taxonomy rather than escaping as an `OSError`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tokenmill.backends._subprocess import (
    ToolResult,
    find_tool,
    probe_tool,
    run_tool,
    safe_path_argument,
)
from tokenmill.core.errors import BackendFailed, BackendUnavailable, Timeout

#: A Python that exists, for tests that need a real child process.
PYTHON = sys.executable


class TestFindingATool:
    def test_a_tool_on_path_is_found(self) -> None:
        assert find_tool("git") is not None

    def test_a_tool_that_is_not_there_is_none(self) -> None:
        assert find_tool("definitely-not-a-real-binary-name") is None

    def test_a_missing_tool_probes_as_missing_with_its_install_command(self) -> None:
        availability = probe_tool("definitely-not-a-real-binary-name", hint="install it somehow")

        assert not availability
        assert availability.hint == "install it somehow"
        assert "definitely-not-a-real-binary-name" in availability.describe()

    def test_a_present_tool_probes_as_available(self) -> None:
        assert probe_tool("git", hint="install git")


class TestRunningATool:
    def test_it_captures_stdout(self) -> None:
        result = run_tool([PYTHON, "-c", "print('hello')"], backend_id="test", timeout_s=30)

        assert result.stdout.strip() == "hello"
        assert result.returncode == 0

    def test_it_captures_stderr_separately(self) -> None:
        result = run_tool(
            [PYTHON, "-c", "import sys; sys.stderr.write('problem')"],
            backend_id="test",
            timeout_s=30,
        )

        assert result.stdout == ""
        assert "problem" in result.stderr

    def test_it_records_the_argv_it_ran(self) -> None:
        """Provenance: a subprocess backend cannot report a package version."""
        result = run_tool([PYTHON, "-c", "pass"], backend_id="test", timeout_s=30)

        assert result.argv == (PYTHON, "-c", "pass")

    def test_a_non_zero_exit_is_a_typed_failure_carrying_stderr(self) -> None:
        with pytest.raises(BackendFailed) as excinfo:
            run_tool(
                [PYTHON, "-c", "import sys; sys.stderr.write('the reason\\n'); sys.exit(3)"],
                backend_id="test",
                timeout_s=30,
            )

        assert "exited 3" in excinfo.value.message
        assert "the reason" in excinfo.value.message
        assert excinfo.value.stderr is not None
        assert "the reason" in excinfo.value.stderr

    def test_a_non_zero_exit_can_be_allowed_when_the_code_means_something(self) -> None:
        result = run_tool(
            [PYTHON, "-c", "import sys; sys.exit(2)"],
            backend_id="test",
            timeout_s=30,
            expect_success=False,
        )

        assert result.returncode == 2

    def test_a_tool_that_fails_silently_still_produces_a_readable_message(self) -> None:
        """`exited 1` followed by nothing reads like a formatting bug."""
        with pytest.raises(BackendFailed, match="no error output"):
            run_tool([PYTHON, "-c", "raise SystemExit(1)"], backend_id="test", timeout_s=30)

    def test_a_missing_binary_is_backend_unavailable_not_an_oserror(self) -> None:
        with pytest.raises(BackendUnavailable) as excinfo:
            run_tool(["definitely-not-a-real-binary"], backend_id="test", timeout_s=30)

        assert excinfo.value.hint is not None

    def test_a_slow_child_is_killed_and_reported_as_a_timeout(self) -> None:
        with pytest.raises(Timeout, match="did not finish"):
            run_tool(
                [PYTHON, "-c", "import time; time.sleep(30)"],
                backend_id="test",
                timeout_s=0.5,
            )

    def test_stdin_is_closed_so_a_prompting_tool_cannot_hang(self) -> None:
        """A child that reads stdin gets EOF immediately rather than waiting."""
        result = run_tool(
            [PYTHON, "-c", "import sys; print(repr(sys.stdin.read()))"],
            backend_id="test",
            timeout_s=30,
        )

        assert result.stdout.strip() == "''"

    def test_an_empty_argv_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="at least an executable"):
            run_tool([], backend_id="test", timeout_s=30)

    def test_it_runs_in_the_directory_it_is_given(self, tmp_path: Path) -> None:
        result = run_tool(
            [PYTHON, "-c", "import os; print(os.getcwd())"],
            backend_id="test",
            timeout_s=30,
            cwd=tmp_path,
        )

        assert str(tmp_path.resolve()) in result.stdout


class TestArgumentSafety:
    """The injection the plan's risk register names by name.

    A repository path is attacker-controlled input the moment someone runs
    tokenmill on a checkout they did not write, and a directory called
    ``--config=evil`` is a legal directory name.
    """

    def test_a_normal_path_passes_through(self, tmp_path: Path) -> None:
        assert safe_path_argument(tmp_path, backend_id="test") == str(tmp_path)

    def test_a_path_that_would_read_as_an_option_is_refused(self) -> None:
        with pytest.raises(BackendFailed, match="beginning with"):
            safe_path_argument(Path("--config=evil"), backend_id="test")

    def test_the_refusal_says_what_to_do_about_it(self) -> None:
        with pytest.raises(BackendFailed) as excinfo:
            safe_path_argument(Path("-rf"), backend_id="test")

        assert excinfo.value.hint is not None

    def test_a_path_merely_containing_a_dash_is_fine(self, tmp_path: Path) -> None:
        """Only the leading character matters; dashes in names are ordinary."""
        path = tmp_path / "my-project-2024"

        assert safe_path_argument(path, backend_id="test").endswith("my-project-2024")


class TestNoShellAnywhere:
    def test_shell_metacharacters_in_an_argument_are_data_not_syntax(self, tmp_path: Path) -> None:
        """The property `shell=True` would destroy, asserted rather than assumed.

        If any of this were passed through a shell, the semicolon would end the
        command and the rest would run as another one. As a list element it is
        simply a string that happens to contain punctuation.
        """
        marker = tmp_path / "should-not-exist"
        hostile = f"; touch {marker}; echo "

        result = run_tool(
            [PYTHON, "-c", "import sys; print(len(sys.argv[1]))", hostile],
            backend_id="test",
            timeout_s=30,
        )

        assert result.stdout.strip() == str(len(hostile))
        assert not marker.exists(), "a shell interpreted the argument"


class TestToolResult:
    def test_it_carries_everything_needed_to_describe_a_run(self) -> None:
        result = ToolResult(
            stdout="out", stderr="err", returncode=0, argv=("a", "b"), duration_s=0.5
        )

        assert result.stdout == "out"
        assert result.argv == ("a", "b")
