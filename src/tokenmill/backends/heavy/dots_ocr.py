r"""dots.ocr: layout and text in one 1.7B vision-language model.

The smallest of the vision-language OCR backends and the one with the most
practical hardware story: 1.7B parameters fits on a card that cannot hold the
others. It answers layout detection and text recognition in a single pass, where
Surya runs them as separate models.

**No PyPI package, so no subprocess adapter.** dots.ocr is published as weights
and served through vLLM, the same shape as DeepSeek-OCR, so it is a
:class:`~tokenmill.backends.heavy.vllm_service.VllmOcrConverter` and the address
comes from ``--extra dots_ocr_url=...``.

**Licence: reported MIT, unverified here.** The weights and code are published
under MIT according to the project's own repository. This sandbox cannot reach
either the repository or the model host, so nothing has been read from an
artefact — unlike Marker, Surya, MinerU and olmOCR, whose wheels were downloaded
and whose bundled licence files were read. ``docs/LICENSES.md`` keeps that
distinction, because "we read it" and "they say so" are different claims and the
project has been caught out by the second four times.

**Unverified end to end.** No dots.ocr deployment has been talked to; the HTTP
path is verified against a real local server.
"""

from __future__ import annotations

from typing import Final

from tokenmill.backends.heavy.vllm_service import VllmOcrConverter
from tokenmill.core.models import (
    BackendInfo,
    Domain,
    IsolationMode,
    LicenseTier,
    OutputFormat,
)

__all__ = ["DotsOcrConverter"]

_FORMATS: Final[tuple[str, ...]] = ("png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif")


class DotsOcrConverter(VllmOcrConverter):
    """Reads a page image through a dots.ocr deployment you are running.

    Attributes:
        info: Static metadata.
        model_name: What vLLM was started with.
        prompt: dots.ocr's own layout-and-text instruction.
    """

    info = BackendInfo(
        id="dots_ocr",
        name="dots.ocr",
        description=(
            "Layout detection and text recognition in one 1.7B vision-language "
            "model — small enough for a card that cannot hold the others. "
            "Reached over HTTP; you run the model."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=_FORMATS,
        output_formats=(OutputFormat.MARKDOWN,),
        license="MIT (reported; unverified — see docs/LICENSES.md)",
        license_tier=LicenseTier.PERMISSIVE,
        isolation=IsolationMode.SERVICE,
        install_extra=None,
        requires_gpu=True,
        requires_network=True,
        upstream_url="https://github.com/rednote-hilab/dots.ocr",
        priority=1,
    )

    model_name = "rednote-hilab/dots.ocr"
    prompt = (
        "Extract the text content from this document image and return it as "
        "Markdown, preserving the reading order, the heading levels and any "
        "tables."
    )
