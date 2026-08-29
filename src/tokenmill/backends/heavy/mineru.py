r"""MinerU, and the licence that made a fourth tier necessary.

**This backend is why ``LicenseTier.RESTRICTED`` exists.** MinerU's wheel does
not carry an SPDX identifier from the standard list::

    Name: mineru
    Version: 3.4.5
    License-Expression: LicenseRef-MinerU-Open-Source-License
    License-File: LICENSE.md

and the bundled ``LICENSE.md`` says, in full and in two languages:

    MinerU is licensed under Apache License 2.0 **and is subject to the
    additional terms below.**

    **1. Commercial License and Thresholds.** [...] if you and your Affiliates,
    on a consolidated basis, meet either of the following thresholds, you must
    obtain a separate commercial license [...] a. monthly active users (MAU)
    exceed 100 million; or b. total monthly revenue exceeds USD 20 million.

    **2. Online Service Attribution Obligation.** If you provide online services
    to third parties based on MinerU, you must clearly and prominently indicate
    [...] that MinerU is used.

    **3. Termination.** [...] this License and all rights granted under this
    License will terminate automatically [...]

None of tokenmill's three existing tiers described that. It is not copyleft —
nothing obliges anyone to publish source. It is not non-commercial — commercial
use is expressly allowed below the thresholds. And calling it permissive would
have been a lie with a consequence a user could hit: **``tokenmill gui
--server`` is an online service**, so an operator converting documents through
MinerU behind it inherits clause 2, and tokenmill would have been the reason
nobody told them.

``docs/research/RESEARCH.md`` records MinerU as AGPL-3.0. That was true of its
predecessor — ``magic-pdf`` 1.3.12 on PyPI still says ``License: AGPL-3.0`` —
and is not true of ``mineru`` 3.4.5. The fifth licence correction in this
project, and the second in this phase.

**The practical rule this adapter follows.** Restricted is treated exactly like
copyleft by the mechanism: never imported, always out of process. The
obligations are the **user's** to read, and tokenmill must not accept them
quietly on their behalf, so every result carries the licence in its metadata and
``tokenmill backends`` prints the tier.

**Unverified.** No MinerU conversion has been run here: no GPU, and its models
live on a host this sandbox cannot reach.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tokenmill.backends.heavy.base import HeavyConverter, environment_root, first_markdown
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

__all__ = ["MinerUConverter"]

#: What MinerU reads. Broader than Marker's: it added the Office formats in 3.x.
_FORMATS: Final[tuple[str, ...]] = ("pdf", "png", "jpg", "jpeg", "docx", "pptx", "xlsx")

#: The warning every MinerU result carries, because a licence obligation nobody
#: is told about is one nobody complies with.
_ATTRIBUTION_NOTICE: Final = (
    "MinerU's licence (LicenseRef-MinerU-Open-Source-License) adds two terms to "
    "Apache-2.0 that are yours rather than tokenmill's: if you provide an online "
    "service based on it you must say so prominently, and above 100M monthly "
    "active users or USD 20M monthly revenue you need a separate commercial "
    "licence. Note that `tokenmill gui --server` is an online service. See "
    "docs/LICENSES.md."
)


class MinerUConverter(HeavyConverter):
    """Converts documents with MinerU, out of process and never imported.

    Attributes:
        info: Static metadata; the tier is ``RESTRICTED``.
        executable: ``mineru``, from the allow-list.
        command: The console script the ``mineru`` package installs.
    """

    info = BackendInfo(
        id="mineru",
        name="MinerU",
        description=(
            "Layout-aware PDF and Office conversion with formula and table "
            "recognition. Source-available with a revenue threshold and an "
            "online-service attribution obligation; needs a GPU."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=_FORMATS,
        output_formats=(OutputFormat.MARKDOWN,),
        license="LicenseRef-MinerU-Open-Source-License",
        license_tier=LicenseTier.RESTRICTED,
        isolation=IsolationMode.SUBPROCESS,
        install_extra=None,
        requires_gpu=True,
        requires_network=True,
        requires_binary="mineru",
        upstream_url="https://github.com/opendatalab/MinerU",
        priority=1,
    )

    executable = "mineru"
    command = "mineru"
    install_steps = (
        f"python -m venv {environment_root('mineru')}",
        f"{environment_root('mineru')}/bin/pip install 'mineru[core]'",
    )
    weights_licence = None

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Convert, attaching the licence obligation to the result.

        The warning is unconditional and it is not decoration. Clause 2 binds
        whoever runs this, and the only moment tokenmill can tell them is the
        moment they run it.

        Args:
            source: The document.
            options: How to convert it.
            context: Collects the notice.

        Returns:
            The converted text.

        Raises:
            ConversionError: As the base class does.
        """
        context.warn(_ATTRIBUTION_NOTICE)
        context.note("licence_obligations", "attribution for online services; revenue threshold")
        return super()._convert(source, options, context)

    def build_argv(self, source: Path, outdir: Path) -> list[str]:
        """Build MinerU's arguments.

        Args:
            source: The document.
            outdir: Where MinerU should write.

        Returns:
            The arguments after the executable.
        """
        return [
            "-p",
            self.path_argument(source),
            "-o",
            self.path_argument(outdir),
        ]

    def read_output(self, outdir: Path, source: Path) -> str | None:
        """Read the Markdown MinerU wrote.

        MinerU nests ``<stem>/<method>/<stem>.md``. Searched rather than
        reconstructed: the middle component is the parsing method it chose, and
        predicting it here would make the adapter wrong the first time somebody
        passed a different one.

        Args:
            outdir: Where MinerU was told to write.
            source: The original document, unused.

        Returns:
            The Markdown, or ``None``.
        """
        del source
        return first_markdown(outdir)
