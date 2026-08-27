"""The hardened subprocess base every out-of-process backend subclasses.

``tokenmill.backends._subprocess`` was Phase 4's minimum: a ``PATH`` lookup, a
list of arguments, a timeout and captured output. Its docstring lists what it
does **not** do, and that list was written as this module's specification:

===========================  ============================================
`_subprocess` gap            Where it is closed here
===========================  ============================================
No binary discovery          :meth:`SubprocessConverter.discover`, which
beyond ``PATH``              consults an explicit search path and the
                             platform's usual install locations, not only
                             ``PATH``.
No version probing           :meth:`SubprocessConverter.probe_version`,
                             cached per process, recorded into the result's
                             metadata as provenance.
No allow-list                :data:`ALLOWED_EXECUTABLES`. An adapter may
                             only invoke a name declared here, checked at
                             launch. This is what makes a copyleft tool's
                             isolation *enforced* rather than declared.
No temp-file lifecycle       :meth:`SubprocessConverter.workspace`, which
                             removes the directory on every path including
                             the failure and timeout ones.
No streaming                 Still not done, and still recorded. See below.
===========================  ============================================

**Why an allow-list matters more than it looks.** Without one, any adapter can
name any executable, so "this AGPL tool runs out of process" is a claim the
adapter makes about itself. With one, the set of programs tokenmill will launch
is a fixed, reviewable list in a single file, and an adapter that tried to
invoke something else fails before the process starts. The licence isolation
tests read this table.

**What is still not done.** Output is buffered whole, so a tool that emits a
gigabyte holds a gigabyte in memory; the mitigation is the size cap
:class:`~tokenmill.core.protocol.BaseConverter` already applies to the input and
the ``--max-bytes`` a caller can lower. There is no sandboxing: no resource
limits, no filesystem confinement, no network namespace. A tool run through here
has the same access the user does. Both are recorded in ``PROGRESS.md`` under
deferred work rather than being quietly absent.

**Security.** ``shell=False`` and a list of arguments, always; there is no code
path in this module that accepts a command string. Every path argument goes
through :func:`~tokenmill.backends._subprocess.safe_path_argument`, which refuses
one beginning with ``-``, and adapters place ``--`` before positionals where the
tool supports it. Phase 4 already had to refuse ``ext::`` in a git URL at two
layers; the assumption here is the same one — every argument is hostile.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from abc import abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from tokenmill.backends._subprocess import ToolResult, run_tool, safe_path_argument
from tokenmill.core.errors import BackendFailed, BackendUnavailable
from tokenmill.core.models import Availability, ConvertOptions, Source
from tokenmill.core.protocol import BaseConverter, ConversionContext

__all__ = [
    "ALLOWED_EXECUTABLES",
    "ExecutableSpec",
    "SubprocessConverter",
]

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExecutableSpec:
    """One program tokenmill is permitted to launch.

    Attributes:
        name: The executable's base name on POSIX.
        windows_name: Its name on Windows, when that differs. Pandoc is
            ``pandoc`` on both; LibreOffice is ``soffice`` on POSIX and
            ``soffice.exe`` on Windows, and lives outside ``PATH`` there.
        version_args: Arguments that make it print its version and exit. Empty
            when the tool has no such flag, in which case no version is probed
            and the result says so rather than guessing.
        search_paths: Absolute locations to try when ``PATH`` does not have it,
            per platform key (``linux``, ``darwin``, ``win32``). This is the
            "binary discovery beyond PATH" `_subprocess` said it did not do.
        install_hint: What to tell a user who does not have it. Required, for the
            same reason :func:`~tokenmill.backends._subprocess.probe_tool`
            requires one: a missing tool without an install command is a dead end.
    """

    name: str
    version_args: tuple[str, ...]
    install_hint: str
    windows_name: str | None = None
    search_paths: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def platform_name(self) -> str:
        """Return the executable's name on the running platform.

        Returns:
            The Windows name on Windows when one is declared, otherwise
            :attr:`name`.
        """
        if sys.platform == "win32" and self.windows_name:
            return self.windows_name
        return self.name


#: Every executable tokenmill may launch, by the id an adapter asks for.
#:
#: The paths are the platforms' usual install locations, and they are consulted
#: only after ``PATH`` fails. `docs/REVIEW_PHASES_0_6.md` warned that Pandoc and
#: LibreOffice "are system binaries with different names, paths and exit codes on
#: three operating systems"; this table is where that lives, so an adapter never
#: guesses at a path and an absent tool is reported unavailable rather than
#: crashed into.
ALLOWED_EXECUTABLES: Final[Mapping[str, ExecutableSpec]] = {
    "pandoc": ExecutableSpec(
        name="pandoc",
        version_args=("--version",),
        install_hint=(
            "install Pandoc: 'apt install pandoc' / 'brew install pandoc' / "
            "'winget install --id JohnMacFarlane.Pandoc', or see "
            "https://pandoc.org/installing.html"
        ),
        search_paths={
            "linux": ("/usr/bin/pandoc", "/usr/local/bin/pandoc"),
            "darwin": ("/opt/homebrew/bin/pandoc", "/usr/local/bin/pandoc"),
            "win32": (r"C:\Program Files\Pandoc\pandoc.exe",),
        },
    ),
    "soffice": ExecutableSpec(
        name="soffice",
        windows_name="soffice.exe",
        version_args=("--version",),
        install_hint=(
            "install LibreOffice: 'apt install libreoffice' / "
            "'brew install --cask libreoffice' / "
            "'winget install --id TheDocumentFoundation.LibreOffice', or see "
            "https://www.libreoffice.org/download/"
        ),
        search_paths={
            "linux": ("/usr/bin/soffice", "/usr/lib/libreoffice/program/soffice"),
            # The macOS bundle puts it inside the .app and never on PATH, which
            # is exactly the case `find_tool` alone cannot handle.
            "darwin": ("/Applications/LibreOffice.app/Contents/MacOS/soffice",),
            "win32": (
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            ),
        },
    ),
    "python-agpl": ExecutableSpec(
        # Not a program name: the id under which an adapter asks for "a Python
        # interpreter that may import an AGPL package". The executable really is
        # sys.executable, and PyMuPDF4LLMConverter overrides discovery to say so.
        # It is in this table because the allow-list is checked at launch and an
        # id that is absent from it cannot be run at all.
        name="python",
        version_args=("--version",),
        install_hint=(
            "PyMuPDF4LLM is AGPL-3.0 and is deliberately never installed "
            "alongside tokenmill, because a package in this environment is a "
            "package anything here can import. Give it one of its own: "
            "python -m venv ~/.local/share/tokenmill/pymupdf4llm && "
            "~/.local/share/tokenmill/pymupdf4llm/bin/pip install pymupdf4llm"
        ),
    ),
}


class SubprocessConverter(BaseConverter):
    """A backend that converts by running a program, never by importing one.

    Subclasses declare :attr:`executable` — a key of :data:`ALLOWED_EXECUTABLES`
    — and implement :meth:`build_command`, which turns a source and a workspace
    into an argument list. Everything else is here: discovery, the availability
    probe, the version probe, the timeout, the temp-file lifecycle and the
    mapping of failures into the error taxonomy.

    Attributes:
        executable: Which entry of the allow-list this backend launches.
    """

    executable: str

    def __init__(self) -> None:
        """Initialise the availability and version caches."""
        super().__init__()
        self._resolved: str | None = None
        self._version: str | None = None
        self._version_probed = False

    # ---------------------------------------------------------------- discovery

    @property
    def spec(self) -> ExecutableSpec:
        """The allow-list entry for this backend's executable.

        Returns:
            The specification.

        Raises:
            BackendFailed: If the backend names an executable that is not on the
                allow-list. A programming error in the adapter, and deliberately
                loud: the allow-list is what makes isolation enforced rather than
                declared, so slipping past it must not be possible by accident.
        """
        try:
            return ALLOWED_EXECUTABLES[self.executable]
        except KeyError:
            msg = (
                f"backend {self.info.id!r} wants to run {self.executable!r}, which is "
                f"not in ALLOWED_EXECUTABLES. Add it there, with an install hint, "
                f"before an adapter can launch it"
            )
            raise BackendFailed(msg, backend_id=self.info.id) from None

    def discover(self) -> str | None:
        """Locate this backend's executable, cached for the life of the instance.

        ``PATH`` first, because a user who installed the tool deliberately wants
        the one they installed. Then the platform's usual locations from
        :attr:`ExecutableSpec.search_paths`, which is what finds LibreOffice
        inside a macOS ``.app`` bundle where it has never been on ``PATH``.

        Returns:
            The absolute path, or ``None`` when the tool is not installed.
        """
        if self._resolved is not None:
            return self._resolved

        spec = self.spec
        found = shutil.which(spec.platform_name())
        if found is None:
            for candidate in spec.search_paths.get(sys.platform, ()):
                path = Path(candidate)
                if path.is_file() and os.access(path, os.X_OK):
                    found = str(path)
                    break

        self._resolved = found
        return found

    def _probe(self) -> Availability:
        """Report availability by looking for the executable.

        Returns:
            Present when it was found, otherwise a missing binary carrying the
            allow-list's install hint.
        """
        spec = self.spec
        if self.discover() is None:
            return Availability.missing_binary(spec.platform_name(), hint=spec.install_hint)
        return Availability.present()

    # ------------------------------------------------------------------ version

    def probe_version(self) -> str | None:
        """Return the tool's version string, probed at most once per instance.

        **Provenance is why this exists.** A Python backend's version is knowable
        from its distribution metadata; before Phase 7 a subprocess backend's was
        not, so tokenmill could not say which Repomix produced a given pack. That
        is the gap that most affects reproducing a measurement, and Phase 10 will
        need it.

        A probe that fails is not an error. The tool may be old, may not have the
        flag, or may write its version to stderr — none of which stops it
        converting. ``None`` means "not known", which the result records honestly
        rather than filling in.

        Returns:
            The first line of the version output, or ``None``.
        """
        if self._version_probed:
            return self._version
        self._version_probed = True

        spec = self.spec
        binary = self.discover()
        if binary is None or not spec.version_args:
            return None

        try:
            result = run_tool(
                [binary, *spec.version_args],
                backend_id=self.info.id,
                timeout_s=_VERSION_TIMEOUT_S,
                expect_success=False,
            )
        except (BackendUnavailable, BackendFailed, OSError):
            _log.debug("version probe for %s failed", self.info.id, exc_info=True)
            return None

        # Some tools print the version to stderr; LibreOffice has done both
        # across releases. Take whichever stream said something.
        text = result.stdout.strip() or result.stderr.strip()
        self._version = text.splitlines()[0].strip() if text else None
        return self._version

    # --------------------------------------------------------------- workspace

    @contextmanager
    def workspace(self) -> Iterator[Path]:
        """Yield a private temporary directory, removed on every exit path.

        Including the failure and timeout paths, which is the half that gets
        forgotten: a converter that leaks a directory per failed conversion
        fills a disk exactly when something is already going wrong.

        Yields:
            The directory. It is empty on entry and gone after the block.
        """
        directory = Path(tempfile.mkdtemp(prefix=f"tokenmill-{self.info.id}-"))
        try:
            yield directory
        finally:
            # ignore_errors: on Windows a child that has not fully exited can
            # still hold a handle on a file in here, and failing the conversion
            # because cleanup was slow would be worse than leaving one directory.
            shutil.rmtree(directory, ignore_errors=True)

    # ----------------------------------------------------------------- running

    def run(
        self,
        argv: Sequence[str],
        *,
        options: ConvertOptions,
        cwd: Path | None = None,
        expect_success: bool = True,
    ) -> ToolResult:
        """Run this backend's executable, checked against the allow-list.

        Args:
            argv: The arguments **after** the executable. The executable itself
                is supplied here from :meth:`discover`, so an adapter cannot
                substitute one.
            options: Supplies the timeout.
            cwd: Working directory for the child.
            expect_success: Raise :class:`~tokenmill.core.errors.BackendFailed`
                on a non-zero exit.

        Returns:
            What the tool produced.

        Raises:
            BackendUnavailable: If the executable has gone since the probe.
            Timeout: If it exceeds the budget.
            BackendFailed: If it exits non-zero and ``expect_success`` is set.
        """
        binary = self.discover()
        if binary is None:
            spec = self.spec
            raise BackendUnavailable(
                f"{spec.platform_name()} is not installed or not on PATH",
                backend_id=self.info.id,
                hint=spec.install_hint,
            )

        return run_tool(
            [binary, *argv],
            backend_id=self.info.id,
            timeout_s=options.timeout_s,
            cwd=cwd,
            expect_success=expect_success,
        )

    def path_argument(self, path: Path) -> str:
        """Render a path as an argument that cannot be read as an option.

        Args:
            path: The path to pass.

        Returns:
            The path as a string.

        Raises:
            BackendFailed: If it begins with ``-``.
        """
        return safe_path_argument(path, backend_id=self.info.id)

    # ------------------------------------------------------------------ convert

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Convert by running the tool in a private workspace.

        Records the tool's version into the result's metadata, so a measurement
        taken today can say what produced it.

        Args:
            source: The input to convert.
            options: How to convert it.
            context: Collects warnings and metadata.

        Returns:
            The converted text.

        Raises:
            ConversionError: On any failure, already in the taxonomy.
        """
        version = self.probe_version()
        context.note("tool", self.spec.platform_name())
        context.note("tool_version", version)
        context.note("isolation", self.info.isolation.value)
        if version is None:
            context.warn(
                f"could not determine the version of {self.spec.platform_name()}, so this "
                f"result cannot say which build produced it"
            )

        with self.workspace() as workspace:
            return self.run_conversion(source, options, context, workspace)

    @abstractmethod
    def run_conversion(
        self,
        source: Source,
        options: ConvertOptions,
        context: ConversionContext,
        workspace: Path,
    ) -> str:
        """Do the conversion, given a scratch directory that will be cleaned up.

        This is the only method an isolated adapter has to write.

        Args:
            source: The input to convert.
            options: How to convert it.
            context: Collects warnings and metadata.
            workspace: An empty private directory, removed after this returns or
                raises.

        Returns:
            The converted text.

        Raises:
            ConversionError: On any failure.
        """


#: How long a ``--version`` call may take before it is abandoned.
#:
#: Short on purpose: this runs during a conversion the user is waiting on, and a
#: tool that cannot print its own version in ten seconds is not going to convert
#: a document. Failing the probe costs a `tool_version` of ``None`` and a
#: warning, not the conversion.
_VERSION_TIMEOUT_S: Final = 10.0
