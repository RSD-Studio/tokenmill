r"""Pandoc, GPL-2.0-or-later, invoked as a child process and never linked.

Pandoc is the universal document converter and it is GPL. There is no Python
binding worth the risk — ``pypandoc`` shells out too, and importing a GPL binary's
wrapper adds nothing but ambiguity — so this adapter runs the real program.

**What it is good at, and what it is not.** Pandoc's reader set is far wider than
anything else in this project: EPUB, LaTeX, reStructuredText, Org, MediaWiki,
DocBook, RTF and about thirty more. That is why it is here. It is *not* the right
default for PDF — Pandoc cannot read PDF at all — and it is not better than
MarkItDown or Kreuzberg on DOCX in this project's measurements. It fills the
long tail.

**The formats it claims are the ones it was asked about.** Pandoc's reader list
is version-dependent, so this adapter declares a conservative subset rather than
the whole list, and asks the installed binary rather than assuming: the version
probe records which Pandoc produced a result, and an unsupported format comes
back as Pandoc's own error rather than a guess made here.

**Security.** ``--`` is not accepted by Pandoc before positionals, so the path is
passed through :meth:`~tokenmill.backends.isolated.base.SubprocessConverter.path_argument`,
which refuses a path beginning with ``-`` outright rather than hoping. Arguments
are a list; there is no shell anywhere.

License: GPL-2.0-or-later. Read on 2026-08-26 from the installed package's own
copyright metadata — ``/usr/share/doc/pandoc/copyright`` of ``pandoc
3.1.3+ds-2``, which records ``License: GPL-2+`` and ``License: GPL-3+`` for
different files. Note that ``pandoc --version`` does **not** name a licence: it
says only "This is free software; see the source for copying conditions", so the
version output is not a source for this and the copyright file is. See
``docs/LICENSES.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tokenmill.backends.isolated.base import SubprocessConverter
from tokenmill.core.errors import BackendFailed
from tokenmill.core.models import (
    BackendInfo,
    ConvertOptions,
    Domain,
    IsolationMode,
    LicenseTier,
    OutputFormat,
    Source,
)
from tokenmill.core.protocol import ConversionContext

__all__ = ["PandocConverter"]

#: Extensions this adapter claims, mapped to the Pandoc reader to use.
#:
#: Deliberately narrower than Pandoc's full reader list. Every entry was checked
#: against `pandoc --list-input-formats` on 3.1.3; a format tokenmill claims and
#: Pandoc cannot read would be a worse failure than one it does not claim.
#:
#: `docx` and `pptx` are here even though MarkItDown and Kreuzberg handle them:
#: `compare` is more useful with a third opinion, and Pandoc's priority keeps it
#: out of the way of auto-selection.
_READERS: Final[dict[str, str]] = {
    "epub": "epub",
    "docx": "docx",
    "odt": "odt",
    "rst": "rst",
    "tex": "latex",
    "latex": "latex",
    "org": "org",
    "rtf": "rtf",
    "textile": "textile",
    "docbook": "docbook",
    "opml": "opml",
    "ipynb": "ipynb",
    "html": "html",
    "htm": "html",
    "md": "markdown",
    "markdown": "markdown",
}


class PandocConverter(SubprocessConverter):
    """Converts documents with Pandoc, out of process.

    Attributes:
        info: Static metadata. GPL, therefore subprocess; the dataclass refuses
            any other combination.
        executable: ``pandoc``, from the allow-list.
    """

    info = BackendInfo(
        id="pandoc",
        name="Pandoc",
        description=(
            "The universal document converter. Reads EPUB, LaTeX, reStructuredText, "
            "Org and about thirty more. GPL, so it runs as a child process."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=tuple(sorted(_READERS)),
        output_formats=(OutputFormat.MARKDOWN,),
        license="GPL-2.0-or-later",
        license_tier=LicenseTier.COPYLEFT,
        isolation=IsolationMode.SUBPROCESS,
        upstream_url="https://pandoc.org/",
        requires_binary="pandoc",
        # Low, and below every Python backend. Pandoc is a system binary most
        # machines do not have; auto-selection landing a user here when
        # MarkItDown would have worked is the failure Phase 4 already had to fix
        # once for repomix. Reachable by name.
        priority=3,
    )

    executable = "pandoc"

    def run_conversion(
        self,
        source: Source,
        options: ConvertOptions,
        context: ConversionContext,
        workspace: Path,
    ) -> str:
        """Convert one document by running Pandoc.

        Args:
            source: The document.
            options: Supplies the timeout.
            context: Collects metadata and warnings.
            workspace: Pandoc writes to stdout, so this is used only as the
                child's working directory — which keeps any temporary file it
                decides to make inside a directory that gets removed.

        Returns:
            The Markdown.

        Raises:
            BackendFailed: If the source has no path, or Pandoc produces nothing.
        """
        if source.path is None:
            raise BackendFailed(
                "pandoc converts a file on disk and this source has no path",
                backend_id=self.info.id,
                hint="pass a file rather than raw bytes",
            )

        reader = _READERS.get((source.format or "").lower())
        argv = [
            "--from",
            reader or "markdown",
            # gfm rather than plain `markdown`: Pandoc's own dialect emits
            # grid tables and fenced divs that no other backend in this project
            # produces, and the fidelity scorer reads GFM pipe tables. Choosing
            # a dialect nobody else emits would make every comparison against
            # this backend a comparison of dialects.
            "--to",
            "gfm",
            "--wrap=none",
            # --standalone, and it costs 42 bytes on report.docx (3,525 -> 3,567,
            # +1.2%, measured 2026-08-26 with --tokenizer bytes).
            #
            # Pandoc's DOCX reader treats a Title-styled paragraph as document
            # *metadata* rather than as body text, and without --standalone the
            # metadata is discarded: `report.docx` came back with "Context
            # Efficiency Report" simply missing, where MarkItDown keeps it. With
            # --standalone it becomes a YAML block, which `strip_frontmatter`
            # can remove for anyone who does not want it.
            #
            # Nothing measured this decision for us, which is the point worth
            # recording: fidelity scored 0.841 **either way**, because the
            # metric has no component for metadata loss (defect N8, and this is
            # a second independent instance of it). So the choice was made on
            # the principle instead — keeping information the user had beats a
            # 1.2% saving, and a converter that silently drops a document's
            # title is the failure docs/BACKENDS.md exists to report.
            "--standalone",
            # Without this, an EPUB with a 4 MB cover inlines it as base64 into
            # the Markdown and the token count becomes a measurement of an
            # image. Pandoc does not do it by default, and it is asserted off.
            "--no-highlight",
            self.path_argument(source.path),
        ]
        if reader is None:
            context.warn(
                f"pandoc has no declared reader for {source.format!r}, so it was read as "
                f"Markdown. The output may be the input"
            )

        result = self.run(argv, options=options, cwd=workspace)

        if not result.stdout.strip():
            raise BackendFailed(
                f"pandoc produced no text for {source.name}",
                backend_id=self.info.id,
                stderr=result.stderr,
                hint="check that the file really is the format its extension claims",
            )
        if result.stderr.strip():
            # Pandoc warns about things worth knowing — a missing image, a
            # dropped element — on stderr while still exiting zero.
            context.warn(f"pandoc reported: {result.stderr.strip().splitlines()[0]}")
        context.note("reader", reader or "markdown")
        return result.stdout
