r"""Marker: the highest-quality PDF-to-Markdown converter in the survey.

**Its licence is not what the plan says, and this was read from the artefact.**
``docs/DEVELOPMENT_PLAN.md`` and ``docs/research/RESEARCH.md`` both record Marker
as GPL-3.0. The published wheel disagrees::

    $ python -m pip download --no-deps marker-pdf
    marker_pdf-2.0.0-py3-none-any.whl

    Name: marker-pdf
    Version: 2.0.0
    License: Apache-2.0
    Project-URL: Repository, https://github.com/datalab-to/marker

    marker_pdf-2.0.0.dist-info/licenses/LICENSE  (11,358 bytes)
                                 Apache License
                           Version 2.0, January 2004

The bundled licence file is the real Apache 2.0 text, not a GPL. Marker's code
was GPL-3.0 in the versions ``RESEARCH.md`` surveyed and is Apache-2.0 at 2.0.0.
That is the **fourth** time this project has found ``RESEARCH.md`` wrong about a
licence, and the first time it was wrong in the direction that would have made
us *over*-restrict rather than under-restrict.

**So Marker could legally be imported, and it still is not.** The reason is
``CONTRIBUTING.md`` rule 1 rather than rule 2: importing it would put PyTorch,
transformers and a CUDA stack into tokenmill's dependency tree. Same mechanism
as PyMuPDF4LLM, different rule, and the ``BackendInfo`` says so —
``license_tier`` is ``PERMISSIVE`` and ``isolation`` is ``SUBPROCESS``, a
combination the model permits precisely for cases like this one.

**The weights are a separate licence and it is unverified.** Marker downloads
its layout, OCR and table models from ``huggingface.co``, which this sandbox
cannot reach, so nothing here has read them. ``RESEARCH.md`` records them as
carrying use restrictions with a revenue threshold, which is credible and is
*not* the same claim as the code's licence. ``docs/LICENSES.md`` records it as
unverified rather than repeating it as fact, and this adapter attaches
``weights_licence: unverified`` to every result it ever produces.

**Unverified end to end.** No Marker conversion has been performed by this code,
here or anywhere: this sandbox has no GPU and cannot reach the model host. What
*is* verified is the absent-runtime path — which is what almost every user
experiences — and the argument construction, against a stub that records what it
was called with.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tokenmill.backends.heavy.base import HeavyConverter, environment_root, first_markdown
from tokenmill.core.models import (
    BackendInfo,
    Domain,
    IsolationMode,
    LicenseTier,
    OutputFormat,
)

__all__ = ["MarkerConverter"]

#: The formats Marker claims. PDFs are what it is for; the Office and image
#: formats work and are slower and worse than the light tier, so the priority
#: keeps auto-selection away from all of it.
_FORMATS: Final[tuple[str, ...]] = ("pdf", "png", "jpg", "jpeg", "pptx", "docx", "xlsx", "epub")


class MarkerConverter(HeavyConverter):
    """Converts documents with Marker, in an environment of its own.

    Attributes:
        info: Static metadata. Permissive **and** out of process; see the module
            docstring.
        executable: ``marker_single``, from the allow-list.
        command: The console script ``marker-pdf`` installs.
    """

    info = BackendInfo(
        id="marker",
        name="Marker",
        description=(
            "The highest-quality PDF-to-Markdown converter in the survey: layout "
            "models, OCR and table recognition. Needs a GPU and about 5 GB of "
            "weights; never a tokenmill dependency."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=_FORMATS,
        output_formats=(OutputFormat.MARKDOWN,),
        license="Apache-2.0",
        # Permissive, and still out of process. Rule 1, not rule 2: importing it
        # would put PyTorch in the dependency tree.
        license_tier=LicenseTier.PERMISSIVE,
        isolation=IsolationMode.SUBPROCESS,
        install_extra=None,
        requires_gpu=True,
        requires_network=True,
        requires_binary="marker_single",
        upstream_url="https://github.com/datalab-to/marker",
        # Below every light backend: this is opt-in by name, because
        # auto-selecting a backend that downloads 5 GB is the same mistake
        # core/preferences.py already refuses to make for docling.
        priority=1,
    )

    executable = "marker_single"
    command = "marker_single"
    install_steps = (
        f"python -m venv {environment_root('marker')}",
        f"{environment_root('marker')}/bin/pip install marker-pdf",
    )
    #: Not verified: the weights live on huggingface.co, which this sandbox
    #: cannot reach. `RESEARCH.md` reports use restrictions with a revenue
    #: threshold; that is recorded as a report, not repeated as a fact.
    weights_licence = None

    def build_argv(self, source: Path, outdir: Path) -> list[str]:
        """Build Marker's arguments.

        ``--output_format markdown`` is passed explicitly even though it is the
        default: a default that changes upstream would silently start producing
        JSON, and the failure would look like "Marker wrote no Markdown" rather
        than like a flag.

        Args:
            source: The document to convert.
            outdir: Where Marker should write.

        Returns:
            The arguments after the executable.
        """
        return [
            self.path_argument(source),
            "--output_dir",
            self.path_argument(outdir),
            "--output_format",
            "markdown",
        ]

    def read_output(self, outdir: Path, source: Path) -> str | None:
        """Read the Markdown Marker wrote.

        Marker nests a directory per document under the output directory and
        names the file after the input's stem. Searched rather than
        reconstructed, so a layout change upstream costs nothing.

        Args:
            outdir: Where Marker was told to write.
            source: The original document, unused; the search finds the file.

        Returns:
            The Markdown, or ``None``.
        """
        del source
        return first_markdown(outdir)
