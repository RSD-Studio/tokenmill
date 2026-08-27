r"""PyMuPDF4LLM, AGPL-3.0, run in a **separate interpreter** and never imported.

PyMuPDF4LLM is the strongest Markdown-from-PDF converter in `RESEARCH.md`'s
Category 1, and it is AGPL-3.0. ``CONTRIBUTING.md`` rule 2 therefore forbids
importing it, and :class:`~tokenmill.core.models.BackendInfo` will not let this
adapter claim otherwise.

**Why a separate interpreter and not just a subprocess.** The obvious reading of
"run it out of process" is ``sys.executable -c "import pymupdf4llm; ..."``, and
that would be wrong here for a reason the licence test makes concrete: to run in
*this* interpreter, the AGPL package would have to be installed in *this*
environment, where it is importable by anything. Phase 7's own test —
``test_nothing_copyleft_is_importable_in_this_environment`` — asserts that no
copyleft distribution is installed at all, and it is right to. So the tool lives
in an environment of its own, and this adapter finds an interpreter that has it.

That is also the shape Phase 9 needs: a heavy GPU converter is installed in its
own environment or container, and the adapter reaches it across a boundary. This
is the CPU-sized rehearsal for that.

**Where the interpreter is looked for**, in order, first hit wins:

1. ``--extra pymupdf4llm_python=/path/to/python``, for someone who knows exactly
   which environment they mean.
2. ``~/.local/share/tokenmill/pymupdf4llm/bin/python`` (``Scripts\\python.exe`` on
   Windows) — the conventional location the install hint tells people to create.
3. A ``.venv-pymupdf4llm`` beside the current working directory.

Nothing is guessed at beyond those. An interpreter that exists but cannot import
the package is reported **unavailable with the install command**, not "available"
followed by a failure on every document.

**The driver is a string, deliberately.** The few lines of Python that call
``pymupdf4llm.to_markdown`` are a module-level constant passed to ``python -c``,
not a ``.py`` file in this package. If they were a file, this repository would
contain the literal statement ``import pymupdf4llm``, and Phase 7's static scan —
which greps our own tree for exactly that — would be correct to fail on it. The
path is passed as ``sys.argv[1]`` and never interpolated into the source.

License: AGPL-3.0. Read from the published package metadata for pymupdf4llm
0.0.31, 2026-08-26, not from `RESEARCH.md`. See ``docs/LICENSES.md`` for why a
subprocess boundary is the answer and an import is not.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

from tokenmill.backends.isolated.base import SubprocessConverter
from tokenmill.core.errors import BackendFailed, CorruptSource
from tokenmill.core.models import (
    Availability,
    BackendInfo,
    ConvertOptions,
    Domain,
    IsolationMode,
    LicenseTier,
    OutputFormat,
    Source,
)
from tokenmill.core.protocol import ConversionContext

__all__ = ["PyMuPDF4LLMConverter"]

#: The whole program that touches AGPL code, as a string rather than a file.
#:
#: Kept minimal on purpose: it reads one path from argv, converts, and writes
#: UTF-8 to stdout. It does no argument parsing, so there is no flag for a
#: hostile filename to impersonate, and the path never reaches a shell.
#:
#: `reconfigure` rather than a print(): on Windows the default stdout encoding
#: is not UTF-8, and a document with an em dash in it would otherwise die of a
#: UnicodeEncodeError inside the child, where the traceback is much less useful.
_DRIVER: Final = """\
import sys
import pymupdf4llm
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.write(pymupdf4llm.to_markdown(sys.argv[1]))
"""

#: A one-liner that answers "can this interpreter run the driver at all".
_IMPORT_CHECK: Final = "import pymupdf4llm; print(pymupdf4llm.__doc__ and 1 or 1)"

#: Strings PyMuPDF puts in a traceback when the *file* is the problem rather
#: than the code. Read out of the real traceback `corrupt.pdf` produces, not
#: guessed at: ``FzErrorSyntax: code=8: array not closed before end of file``
#: raised as ``pymupdf.FileDataError``.
_CORRUPT_MARKERS: Final = ("FileDataError", "FzErrorSyntax", "FzErrorFormat")

#: How to create the environment this adapter looks for.
_INSTALL_HINT: Final = (
    "PyMuPDF4LLM is AGPL-3.0 and is never installed alongside tokenmill. Create "
    "an environment of its own and tokenmill will find it: "
    "python -m venv ~/.local/share/tokenmill/pymupdf4llm && "
    "~/.local/share/tokenmill/pymupdf4llm/bin/pip install pymupdf4llm "
    "(or pass --extra pymupdf4llm_python=/path/to/python)"
)


def _interpreter_names() -> tuple[str, ...]:
    """Return the interpreter's path within a virtual environment, per platform.

    Returns:
        The relative paths to try inside a venv directory.
    """
    if sys.platform == "win32":
        return (r"Scripts\python.exe",)
    return ("bin/python3", "bin/python")


def _candidate_roots() -> tuple[Path, ...]:
    """Return the virtual environments this adapter will look inside.

    Returns:
        Directory paths, most-conventional first. Nothing here is created; a
        path that does not exist is simply skipped.
    """
    return (
        Path.home() / ".local" / "share" / "tokenmill" / "pymupdf4llm",
        Path.cwd() / ".venv-pymupdf4llm",
    )


class PyMuPDF4LLMConverter(SubprocessConverter):
    """Markdown from PDFs via PyMuPDF4LLM, out of process.

    Attributes:
        info: Static metadata. ``license_tier`` is copyleft and ``isolation`` is
            subprocess; :meth:`~tokenmill.core.models.BackendInfo.__post_init__`
            refuses any other combination.
        executable: ``python-agpl`` — the allow-list entry standing for "an
            interpreter that may import an AGPL package". Discovery is overridden
            below, because the thing being located is an environment rather than
            a program on ``PATH``.
    """

    info = BackendInfo(
        id="pymupdf4llm",
        name="PyMuPDF4LLM",
        description=(
            "Markdown from PDFs with headings and tables preserved. AGPL-3.0, so "
            "it runs in a separate interpreter and is never imported."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=("pdf",),
        output_formats=(OutputFormat.MARKDOWN,),
        license="AGPL-3.0",
        license_tier=LicenseTier.COPYLEFT,
        isolation=IsolationMode.SUBPROCESS,
        upstream_url="https://github.com/pymupdf/RAG",
        install_extra=None,
        requires_binary="python (a separate environment with pymupdf4llm)",
        # Below pdfplumber and kreuzberg despite being the better converter:
        # auto-selection must not land a user on a backend that needs an
        # environment they have not built, when a Python one is installed and
        # works. Reachable by name, like docling.
        priority=5,
    )

    executable = "python-agpl"

    def discover(self) -> str | None:
        """Locate an interpreter that has PyMuPDF4LLM installed.

        Overrides the base's ``PATH`` search: what is wanted is not a program
        called ``python`` but a specific *environment*, and the one on ``PATH``
        is this one, which must not have the package.

        Returns:
            The interpreter's path, or ``None`` when no candidate exists. Whether
            it can actually import the package is :meth:`_probe`'s question.
        """
        if self._resolved is not None:
            return self._resolved

        for root in _candidate_roots():
            for relative in _interpreter_names():
                candidate = root / relative
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    self._resolved = str(candidate)
                    return self._resolved
        return None

    def _interpreter(self, options: ConvertOptions) -> str | None:
        """Return the interpreter to use, honouring an explicit override.

        Args:
            options: May carry ``pymupdf4llm_python`` in ``extra``.

        Returns:
            The interpreter path, or ``None`` when there is none.
        """
        override = options.extra.get("pymupdf4llm_python")
        if isinstance(override, str) and override.strip():
            return override.strip()
        return self.discover()

    def _probe(self) -> Availability:
        """Report availability, checking that the package really is importable.

        Costs one short-lived child process, once per instance, and that is the
        point: an interpreter that exists but has no PyMuPDF4LLM in it would
        otherwise be reported available and then fail on every document, which is
        precisely the dishonesty ``CONTRIBUTING.md`` rule 5 is about.

        Returns:
            Present when a candidate interpreter imports the package.
        """
        interpreter = self.discover()
        if interpreter is None:
            return Availability.missing_binary("pymupdf4llm environment", hint=_INSTALL_HINT)

        from tokenmill.backends._subprocess import run_tool

        try:
            result = run_tool(
                [interpreter, "-c", _IMPORT_CHECK],
                backend_id=self.info.id,
                timeout_s=30.0,
                expect_success=False,
            )
        except Exception:  # a probe must never raise; report it as unavailable
            return Availability.missing_binary("pymupdf4llm environment", hint=_INSTALL_HINT)

        if result.returncode != 0:
            return Availability.missing_dependency("pymupdf4llm", hint=_INSTALL_HINT)
        return Availability.present()

    def probe_version(self) -> str | None:
        """Return PyMuPDF4LLM's version, asked of the child interpreter.

        The base class's ``--version`` probe would report the *interpreter's*
        version, which says nothing about what produced the Markdown. Phase 10
        needs to know which converter made a measurement, so the question is
        asked of the package instead.

        Returns:
            A string like ``pymupdf4llm 0.0.31``, or ``None`` when it could not
            be determined.
        """
        if self._version_probed:
            return self._version
        self._version_probed = True

        interpreter = self.discover()
        if interpreter is None:
            return None

        from tokenmill.backends._subprocess import run_tool

        try:
            result = run_tool(
                [
                    interpreter,
                    "-c",
                    "import importlib.metadata as m; print(m.version('pymupdf4llm'))",
                ],
                backend_id=self.info.id,
                timeout_s=30.0,
                expect_success=False,
            )
        except Exception:
            return None

        if result.returncode != 0 or not result.stdout.strip():
            return None
        self._version = f"pymupdf4llm {result.stdout.strip().splitlines()[0]}"
        return self._version

    def _translate(self, failure: BackendFailed, source: Source) -> Exception:
        """Turn a child's traceback into the error the rest of tokenmill uses.

        Two problems with the raw failure, both visible the first time this ran
        against `corrupt.pdf`:

        **The message was the wrong line.**
        :func:`~tokenmill.backends._subprocess._first_meaningful_line` takes the
        first line of stderr, which for a Python traceback is always
        ``Traceback (most recent call last):``. The informative line is the last
        one. That helper is right for the tools it was written for — a Node or
        Rust program's first stderr line *is* its error — and wrong for a Python
        child, so the adapter that has a Python child fixes it rather than
        changing a shared function under the backends that depend on it.

        **The class was wrong.** A damaged PDF is
        :class:`~tokenmill.core.errors.CorruptSource` everywhere else in this
        project: pdfplumber, pypdf and kreuzberg all raise it with a message
        naming the damage. A subprocess backend reporting the same file as a
        generic backend failure would make `compare` show four backends
        disagreeing about what went wrong when they agree.

        Args:
            failure: What ``run_tool`` raised.
            source: The input, for the message.

        Returns:
            The error to raise instead. Always an exception; never raised here,
            so the caller's ``raise ... from exc`` keeps the original cause.
        """
        stderr = failure.stderr or ""
        last = ""
        for line in reversed(stderr.splitlines()):
            if line.strip() and not line.startswith((" ", "\t")):
                last = line.strip()
                break

        if any(marker in stderr for marker in _CORRUPT_MARKERS):
            return CorruptSource(
                f"{source.name} could not be parsed: {last or 'the PDF could not be opened'}",
                backend_id=self.info.id,
                hint="the file appears damaged or truncated; check it opens in a normal viewer",
            )
        return BackendFailed(
            f"pymupdf4llm failed on {source.name}: {last or 'no error output'}",
            backend_id=self.info.id,
            stderr=stderr,
            hint=failure.hint,
        )

    def run_conversion(
        self,
        source: Source,
        options: ConvertOptions,
        context: ConversionContext,
        workspace: Path,
    ) -> str:
        """Convert one PDF by running the driver in the separate interpreter.

        Args:
            source: The PDF.
            options: Supplies the timeout and any interpreter override.
            context: Collects metadata and warnings.
            workspace: Unused — PyMuPDF4LLM writes to stdout, so nothing is
                staged. Accepted because the base class guarantees the directory
                exists and is cleaned up either way.

        Returns:
            The Markdown.

        Raises:
            BackendFailed: If the source has no path, or the child fails.
        """
        if source.path is None:
            raise BackendFailed(
                "pymupdf4llm converts a file on disk and this source has no path",
                backend_id=self.info.id,
                hint="pass a PDF file rather than raw bytes",
            )

        interpreter = self._interpreter(options)
        if interpreter is None:
            raise BackendFailed(
                "no interpreter with pymupdf4llm was found",
                backend_id=self.info.id,
                hint=_INSTALL_HINT,
            )

        from tokenmill.backends._subprocess import run_tool

        try:
            result = run_tool(
                [interpreter, "-c", _DRIVER, self.path_argument(source.path)],
                backend_id=self.info.id,
                timeout_s=options.timeout_s,
                cwd=workspace,
            )
        except BackendFailed as exc:
            raise self._translate(exc, source) from exc

        if not result.stdout.strip():
            raise BackendFailed(
                f"pymupdf4llm produced no text for {source.name}",
                backend_id=self.info.id,
                stderr=result.stderr,
                hint="the PDF may be a scan with no text layer; try an OCR backend",
            )
        # Overwrite the base's note: it records the *allow-list* name, which
        # here is "python", and the tool that actually did the work is the
        # package that interpreter imported.
        context.note("tool", "pymupdf4llm")
        context.note("interpreter", interpreter)
        return result.stdout
