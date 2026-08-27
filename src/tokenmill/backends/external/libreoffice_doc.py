r"""LibreOffice headless, MPL-2.0, out of process because it is not Python.

**This backend's process boundary carries no licence meaning**, and saying so is
the point of putting it beside the other two. LibreOffice is MPL-2.0 — file-level
copyleft, the same shape as ``certifi``, and perfectly importable if it were a
Python library. It is out of process because it is a 400 MB C++ application, and
for no other reason. ``repomix`` and ``code2prompt`` are the same case.

That makes it useful practice: getting the boundary wrong here costs a bug, not
a licence problem.

**What it is for.** The legacy Office formats nothing else in this project reads
— ``.doc``, ``.xls``, ``.ppt``, ``.rtf``, ``.wpd`` — plus ODF. MarkItDown and
Kreuzberg cover the modern OOXML formats better and faster.

**Two things about running it that are not obvious**, both found here rather than
read about:

* **A user profile is per-process, and it is not optional.** LibreOffice keeps a
  single profile directory and refuses to run a second instance against one
  already in use. A converter that assumed a default profile would fail the
  moment a user had LibreOffice open, or the moment two conversions overlapped —
  which the Phase 8 batch queue does by design. Every run here gets a private
  profile inside the workspace, via ``-env:UserInstallation``, and it is removed
  with the workspace.
* **Failure is silent and exit status is useless.** On a document it cannot load,
  ``soffice`` prints ``Error: source file could not be loaded`` to stderr and
  **exits zero**. This adapter therefore checks for the output file rather than
  trusting the exit code, and reports the missing file as a failure with
  stderr attached.

**Filters are a separate install from the binary.** A machine can have ``soffice``
on ``PATH`` and still convert nothing: this project's own container ships
``libreoffice-core`` without ``libreoffice-writer``, so the binary runs, exits
zero and produces ``Error: source file could not be loaded`` for every input.

Phase 7 reported that as a conversion failure carrying the install hint and left
the availability probe saying "available", on the grounds that a filter set is
not a file with a predictable path. It is, near enough: LibreOffice describes
each document component in its configuration registry, as ``writer.xcd``,
``calc.xcd`` and friends, and a core-only install has the registry directory and
none of those files. :meth:`LibreOfficeConverter._probe` now looks, and this
backend reports itself **unavailable with the ``apt`` line** on such a machine
instead of accepting work it cannot do.

The check only ever downgrades on **positive** evidence — a registry directory
that was found and that contains no component. An install whose layout we do not
recognise keeps the old answer, because "I could not find the registry" is not
the same fact as "there are no filters", and a probe that guessed would make a
working LibreOffice disappear from somebody's backend list. The runtime failure
above stays as the backstop for exactly that case.

This was found the way trap 1 in the handover says it will be: on a fresh
container without the tools a previous session had installed, where six tests
that should have skipped failed instead.

License: MPL-2.0. Read on 2026-08-26 from
``/usr/share/doc/libreoffice-core/copyright`` of ``libreoffice-core
4:24.2.7-0ubuntu0.24.04.6``, which records ``License: MPL-2.0``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tokenmill.backends.external.base import SubprocessConverter
from tokenmill.core.errors import BackendFailed
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

__all__ = ["LibreOfficeConverter"]

#: The formats this backend claims.
#:
#: Weighted towards the legacy ones, which are the reason it is here. The modern
#: OOXML formats are included so `compare` has a third opinion, and the priority
#: keeps auto-selection away from them.
_FORMATS: Final[tuple[str, ...]] = (
    "doc",
    "docx",
    "odt",
    "ods",
    "odp",
    "ppt",
    "pptx",
    "rtf",
    "wpd",
    "xls",
    "xlsx",
)

#: What LibreOffice says when it loaded nothing. It exits **zero** anyway.
_LOAD_FAILURE: Final = "source file could not be loaded"

#: Where LibreOffice keeps its configuration registry, relative to a directory
#: above the executable. Two spellings because the macOS bundle uses
#: ``Contents/Resources`` where Linux and Windows use ``share``.
_REGISTRY_DIRS: Final[tuple[tuple[str, ...], ...]] = (
    ("share", "registry"),
    ("Resources", "registry"),
)

#: How far above the executable to look for the registry. Two is enough on all
#: three platforms — ``program/soffice`` and ``Contents/MacOS/soffice`` are both
#: two levels down from the install root — and a third would start matching
#: ``/usr/share``, which belongs to the whole system rather than to LibreOffice.
_REGISTRY_SEARCH_DEPTH: Final = 3

#: One registry file per document component. A build carrying none of these can
#: start, print its version and load nothing.
_COMPONENT_REGISTRY_FILES: Final[tuple[str, ...]] = (
    "writer.xcd",
    "calc.xcd",
    "impress.xcd",
    "draw.xcd",
)

#: What to install when the components are missing. Named per-distribution
#: because "install LibreOffice" is exactly the advice that fails here — it is
#: already installed.
_COMPONENTS_HINT: Final = (
    "LibreOffice is installed without its document components, so it can start "
    "and convert nothing. Install them too: "
    "'apt install libreoffice-writer libreoffice-calc libreoffice-impress', or "
    "install the full 'libreoffice' package rather than 'libreoffice-core'"
)


class LibreOfficeConverter(SubprocessConverter):
    """Converts documents with a headless LibreOffice, out of process.

    Attributes:
        info: Static metadata. Permissive and still out of process — see the
            module docstring.
        executable: ``soffice``, from the allow-list, which knows where the
            macOS bundle hides it.
    """

    info = BackendInfo(
        id="libreoffice",
        name="LibreOffice",
        description=(
            "Headless LibreOffice. Reads the legacy Office formats nothing else "
            "here does — .doc, .xls, .ppt, .rtf — plus ODF."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=_FORMATS,
        output_formats=(OutputFormat.TEXT,),
        license="MPL-2.0",
        license_tier=LicenseTier.PERMISSIVE,
        # Permissive, and still out of process: it is a C++ application, not a
        # library we could import at any price. BackendInfo permits this
        # combination; only the reverse is refused.
        isolation=IsolationMode.SUBPROCESS,
        upstream_url="https://www.libreoffice.org/",
        requires_binary="soffice",
        priority=2,
    )

    executable = "soffice"

    def _probe(self) -> Availability:
        """Report availability, and refuse a LibreOffice that has no filters.

        Two questions, in order: is the binary there, and can it load a
        document. The second is the one Phase 7 left unasked, and the answer
        costs one :meth:`~pathlib.Path.is_file` per component.

        Returns:
            Whatever the base probe said, unless a registry directory was found
            and contains no document component — in which case unsupported,
            carrying the package names to install.
        """
        base = super()._probe()
        if not base:
            return base
        registry = self._registry_dir()
        if registry is None:
            # No evidence either way. Keep the binary's answer; the runtime
            # check in run_conversion is the backstop.
            return base
        if any((registry / name).is_file() for name in _COMPONENT_REGISTRY_FILES):
            return base
        return Availability.unsupported(
            f"LibreOffice at {self.discover()} has no document components installed",
            hint=_COMPONENTS_HINT,
        )

    def _registry_dir(self) -> Path | None:
        """Locate LibreOffice's configuration registry from its executable.

        ``PATH`` usually holds a symlink — ``/usr/bin/soffice`` pointing into
        ``/usr/lib/libreoffice/program`` — so the real path is resolved first,
        or every parent examined would be the wrong tree.

        Returns:
            The registry directory, or ``None`` when this install's layout is
            not one of the three recognised ones.
        """
        binary = self.discover()
        if binary is None:  # pragma: no cover - _probe checks this first
            return None
        try:
            resolved = Path(binary).resolve()
        except OSError:  # pragma: no cover - a path that cannot be resolved
            return None
        for parent in list(resolved.parents)[:_REGISTRY_SEARCH_DEPTH]:
            for parts in _REGISTRY_DIRS:
                candidate = parent.joinpath(*parts)
                if candidate.is_dir():
                    return candidate
        return None

    def run_conversion(
        self,
        source: Source,
        options: ConvertOptions,
        context: ConversionContext,
        workspace: Path,
    ) -> str:
        """Convert one document by running LibreOffice headless.

        Args:
            source: The document.
            options: Supplies the timeout.
            context: Collects metadata and warnings.
            workspace: Holds both the private user profile and the output file,
                and is removed afterwards either way.

        Returns:
            The extracted text.

        Raises:
            BackendFailed: If the source has no path, or LibreOffice wrote no
                output file — which is how it reports failure, since it exits
                zero regardless.
        """
        if source.path is None:
            raise BackendFailed(
                "libreoffice converts a file on disk and this source has no path",
                backend_id=self.info.id,
                hint="pass a file rather than raw bytes",
            )

        profile = workspace / "profile"
        outdir = workspace / "out"
        outdir.mkdir()

        argv = [
            # as_uri() rather than string formatting: LibreOffice wants a URL
            # here, and a path with a space or a '#' in it is otherwise silently
            # truncated at the first one.
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            # --norestore stops it offering to recover a document from a
            # previous crashed run, which on a shared profile would block
            # forever with stdin closed.
            "--norestore",
            "--convert-to",
            "txt:Text",
            "--outdir",
            self.path_argument(outdir),
            self.path_argument(source.path),
        ]

        result = self.run(argv, options=options, cwd=workspace)

        produced = sorted(outdir.glob("*.txt"))
        if not produced:
            stderr = result.stderr.strip()
            hint = (
                "LibreOffice is installed but has no import filter for this format. "
                "Install the component packages too: 'apt install libreoffice-writer "
                "libreoffice-calc libreoffice-impress'"
                if _LOAD_FAILURE in stderr
                else "check that the file really is the format its extension claims"
            )
            raise BackendFailed(
                f"libreoffice wrote no output for {source.name} "
                f"(it exits 0 even when it converts nothing)",
                backend_id=self.info.id,
                stderr=result.stderr,
                hint=hint,
            )

        text = produced[0].read_text(encoding="utf-8", errors="replace")
        if "javaldx" in result.stderr:
            context.warn(
                "LibreOffice could not start its Java runtime. Text extraction is "
                "unaffected; some spreadsheet functions and database features are not"
            )
        context.note("filter", "txt:Text")
        return text
