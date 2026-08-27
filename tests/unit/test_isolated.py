"""The hardened subprocess base: discovery, versions, the allow-list, cleanup.

These are the mechanics rather than the adapters. What they are checking is the
list `tokenmill.backends._subprocess`'s docstring wrote as Phase 7's
specification — no discovery beyond PATH, no version probing, no allow-list, no
temp-file lifecycle — so each class below is one line of that list, closed.

The cleanup tests deliberately exercise the **failure** paths as well as the
happy one. A converter that removes its scratch directory only when everything
went well fills a disk exactly when something is already going wrong, and that
is the case nobody writes a test for.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tokenmill.backends.isolated.base import (
    ALLOWED_EXECUTABLES,
    ExecutableSpec,
    SubprocessConverter,
)
from tokenmill.core.errors import BackendFailed, Timeout
from tokenmill.core.models import (
    BackendInfo,
    ConvertOptions,
    Domain,
    IsolationMode,
    LicenseTier,
    Source,
)
from tokenmill.core.protocol import ConversionContext

BYTES = ConvertOptions(tokenizer="bytes")


class _Recorder(SubprocessConverter):
    """A converter that reports what happened to its workspace.

    Runs the interpreter running these tests, so it needs nothing installed and
    behaves the same on all three platforms.
    """

    info = BackendInfo(
        id="recorder",
        name="Recorder",
        description="A test double that runs this interpreter.",
        domains=(Domain.TEXT,),
        input_formats=("txt",),
        license="Apache-2.0",
        license_tier=LicenseTier.PERMISSIVE,
        isolation=IsolationMode.SUBPROCESS,
        upstream_url="https://example.invalid",
    )
    executable = "python-agpl"

    def __init__(self, script: str = "pass", *, fail: bool = False) -> None:
        """Initialise with the child program to run.

        Args:
            script: Python source for the child.
            fail: Raise inside ``run_conversion`` after the child returns, to
                exercise the failure path through the workspace context manager.
        """
        super().__init__()
        self.script = script
        self.fail = fail
        self.seen_workspace: Path | None = None

    def discover(self) -> str | None:
        """Return this interpreter, so the double needs nothing installed."""
        return sys.executable

    def run_conversion(
        self,
        source: Source,  # noqa: ARG002 - part of the base's signature
        options: ConvertOptions,
        context: ConversionContext,  # noqa: ARG002 - part of the base's signature
        workspace: Path,
    ) -> str:
        """Run the script, note the workspace, and optionally fail afterwards."""
        self.seen_workspace = workspace
        (workspace / "scratch.txt").write_text("temporary", encoding="utf-8")
        result = self.run(["-c", self.script], options=options, cwd=workspace)
        if self.fail:
            raise BackendFailed("deliberate", backend_id=self.info.id)
        return result.stdout


@pytest.fixture
def text_source(tmp_path: Path) -> Source:
    """A trivial source, since these tests are about the mechanics."""
    path = tmp_path / "input.txt"
    path.write_text("hello", encoding="utf-8")
    return Source.from_path(path)


class TestTheAllowList:
    """What makes isolation enforced rather than declared."""

    def test_every_entry_carries_an_install_hint(self) -> None:
        for key, spec in ALLOWED_EXECUTABLES.items():
            assert spec.install_hint.strip(), f"{key} has no install hint"
            assert spec.name.strip()

    def test_a_backend_naming_an_executable_that_is_not_listed_is_refused(self) -> None:
        """The check that stops an adapter inventing a program to run."""

        class Rogue(_Recorder):
            executable = "curl"

        with pytest.raises(BackendFailed, match="ALLOWED_EXECUTABLES"):
            _ = Rogue().spec

    def test_the_refusal_says_what_to_do_about_it(self) -> None:
        class Rogue(_Recorder):
            executable = "definitely-not-listed"

        with pytest.raises(BackendFailed) as caught:
            _ = Rogue().spec

        assert "install hint" in str(caught.value)


class TestDiscoveryBeyondPath:
    def test_a_configured_search_path_is_used_when_path_misses(self, tmp_path: Path) -> None:
        """The case that finds LibreOffice inside a macOS .app bundle.

        `shutil.which` cannot: the binary has never been on PATH there.
        """
        binary = tmp_path / "madeup-tool"
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o755)

        spec = ExecutableSpec(
            name="madeup-tool-not-on-path",
            version_args=(),
            install_hint="install it",
            windows_name="madeup-tool-not-on-path.exe",
            search_paths={sys.platform: (str(binary),)},
        )

        class Configured(_Recorder):
            executable = "configured"

            @property
            def spec(self) -> ExecutableSpec:
                return spec

        converter = Configured()
        converter._resolved = None
        assert SubprocessConverter.discover(converter) == str(binary)

    def test_an_absent_tool_is_unavailable_with_the_hint_rather_than_a_crash(self) -> None:
        spec = ExecutableSpec(
            name="absolutely-not-installed-anywhere",
            version_args=(),
            install_hint="apt install nothing",
        )

        class Absent(_Recorder):
            @property
            def spec(self) -> ExecutableSpec:
                return spec

            def discover(self) -> str | None:
                # The base's real search, rather than the double's shortcut:
                # this test is about what happens when it finds nothing.
                return SubprocessConverter.discover(self)

        availability = Absent().is_available()

        assert not availability
        assert availability.hint == "apt install nothing"


class TestVersionProbing:
    """The provenance gap: tokenmill could not say which build produced a result."""

    def test_the_version_is_probed_and_recorded_in_the_metadata(self, text_source: Source) -> None:
        converter = _Recorder("pass")

        result = converter.convert(text_source, BYTES)

        assert result.metadata["tool_version"] is not None
        assert "Python" in str(result.metadata["tool_version"])
        assert result.metadata["isolation"] == "subprocess"

    def test_it_is_probed_once_and_then_cached(self) -> None:
        converter = _Recorder("pass")

        first = converter.probe_version()
        converter._resolved = "/nonexistent/python"  # a second probe would fail
        second = converter.probe_version()

        assert first == second

    def test_a_tool_with_no_version_flag_reports_none_rather_than_guessing(self) -> None:
        spec = ExecutableSpec(name="python", version_args=(), install_hint="install python")

        class Silent(_Recorder):
            @property
            def spec(self) -> ExecutableSpec:
                return spec

        assert Silent().probe_version() is None

    def test_an_unprobeable_version_warns_rather_than_failing_the_conversion(
        self, text_source: Source
    ) -> None:
        """A tool that cannot say its version still converts documents."""
        spec = ExecutableSpec(name="python", version_args=(), install_hint="install python")

        class Silent(_Recorder):
            @property
            def spec(self) -> ExecutableSpec:
                return spec

        result = Silent("pass").convert(text_source, BYTES)

        assert result.metadata["tool_version"] is None
        assert any("which build produced it" in w for w in result.warnings)


class TestTheWorkspaceLifecycle:
    def test_the_workspace_is_removed_after_a_successful_conversion(
        self, text_source: Source
    ) -> None:
        converter = _Recorder("pass")

        converter.convert(text_source, BYTES)

        assert converter.seen_workspace is not None
        assert not converter.seen_workspace.exists()

    def test_the_workspace_is_removed_after_the_backend_fails(self, text_source: Source) -> None:
        """The path that gets forgotten, and the one that fills a disk."""
        converter = _Recorder("pass", fail=True)

        with pytest.raises(BackendFailed):
            converter.convert(text_source, BYTES)

        assert converter.seen_workspace is not None
        assert not converter.seen_workspace.exists()

    def test_the_workspace_is_removed_after_the_child_exits_non_zero(
        self, text_source: Source
    ) -> None:
        converter = _Recorder("import sys; sys.exit(3)")

        with pytest.raises(BackendFailed):
            converter.convert(text_source, BYTES)

        assert converter.seen_workspace is not None
        assert not converter.seen_workspace.exists()

    def test_the_workspace_is_removed_after_a_timeout(self, text_source: Source) -> None:
        """Timeout and cleanup on the same path, which is the acceptance criterion."""
        converter = _Recorder("import time; time.sleep(30)")

        with pytest.raises(Timeout):
            converter.convert(text_source, BYTES.with_(timeout_s=1.0))

        assert converter.seen_workspace is not None
        assert not converter.seen_workspace.exists()

    def test_each_conversion_gets_a_workspace_of_its_own(self, text_source: Source) -> None:
        """The Phase 8 batch queue runs conversions concurrently.

        Two conversions sharing a scratch directory would race on the output
        filename, which is exactly how the LibreOffice adapter would break.
        """
        first = _Recorder("pass")
        second = _Recorder("pass")

        first.convert(text_source, BYTES)
        second.convert(text_source, BYTES)

        assert first.seen_workspace != second.seen_workspace


class TestTimeoutsAreTheTaxonomysTimeout:
    def test_a_slow_child_raises_the_taxonomys_timeout_not_something_untyped(
        self, text_source: Source
    ) -> None:
        converter = _Recorder("import time; time.sleep(30)")

        with pytest.raises(Timeout) as caught:
            converter.convert(text_source, BYTES.with_(timeout_s=1.0))

        assert caught.value.backend_id == "recorder"

    def test_a_failing_child_carries_its_stderr_on_the_exception(self, text_source: Source) -> None:
        converter = _Recorder(
            "import sys; sys.stderr.write('the child explained itself\\n'); sys.exit(1)"
        )

        with pytest.raises(BackendFailed) as caught:
            converter.convert(text_source, BYTES)

        assert "the child explained itself" in (caught.value.stderr or "")
