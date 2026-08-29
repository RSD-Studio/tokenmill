r"""olmOCR: Allen AI's document OCR, and the one with the honest install story.

Apache-2.0, verified from the published wheel::

    Name: olmocr
    Version: 0.4.27
    License:                                  Apache License
    Classifier: License :: OSI Approved :: Apache Software License

    olmocr-0.4.27.dist-info/licenses/LICENSE  (11,359 bytes)
                                 Apache License
                           Version 2.0, January 2004

**The hardware requirement here is real in a way the others' are not.** Marker
and Surya are slow without a GPU; olmOCR's pipeline runs a vision-language model
through vLLM, and vLLM has no CPU path worth the name and no Metal backend at
all. On a machine without an NVIDIA card this does not run slowly — it does not
run. ``tokenmill doctor`` says so rather than letting somebody discover it after
a 15 GB download.

That is also why this adapter's ``requires_gpu`` is not decorative: it is what
``doctor`` reads to decide whether to recommend the backend at all.

**Unverified.** No olmOCR conversion has been run here.
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

__all__ = ["OlmOcrConverter"]

_FORMATS: Final[tuple[str, ...]] = ("pdf", "png", "jpg", "jpeg")


class OlmOcrConverter(HeavyConverter):
    """Runs olmOCR's pipeline out of process.

    Attributes:
        info: Static metadata.
        executable: ``olmocr``, from the allow-list.
        command: The console script ``olmocr`` installs.
    """

    info = BackendInfo(
        id="olmocr",
        name="olmOCR",
        description=(
            "Allen AI's document OCR, a vision-language model served through "
            "vLLM. Genuinely needs an NVIDIA GPU — there is no CPU or Metal "
            "path — and never a tokenmill dependency."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=_FORMATS,
        output_formats=(OutputFormat.MARKDOWN,),
        license="Apache-2.0",
        license_tier=LicenseTier.PERMISSIVE,
        isolation=IsolationMode.SUBPROCESS,
        install_extra=None,
        requires_gpu=True,
        requires_network=True,
        requires_binary="olmocr",
        upstream_url="https://github.com/allenai/olmocr",
        priority=1,
    )

    executable = "olmocr"
    command = "olmocr"
    install_steps = (
        f"python -m venv {environment_root('olmocr')}",
        f"{environment_root('olmocr')}/bin/pip install olmocr[gpu]",
    )
    weights_licence = None

    def build_argv(self, source: Path, outdir: Path) -> list[str]:
        """Build olmOCR's arguments.

        Args:
            source: The document.
            outdir: The workspace olmOCR writes into.

        Returns:
            The arguments after the executable.
        """
        return [
            self.path_argument(outdir),
            "--pdfs",
            self.path_argument(source),
            "--markdown",
        ]

    def read_output(self, outdir: Path, source: Path) -> str | None:
        """Read the Markdown olmOCR wrote.

        Args:
            outdir: The workspace it was given.
            source: The original document, unused.

        Returns:
            The Markdown, or ``None``.
        """
        del source
        return first_markdown(outdir)
