r"""Surya: OCR, layout and reading order in 90+ languages.

Marker's engine, usable on its own. Where Marker produces a whole Markdown
document, Surya answers the narrower questions — what text is on this page, in
what order, in what layout — which makes it the backend for a scanned document
rather than for a digital one.

**Its licence is not what the plan says either.** ``RESEARCH.md`` and
``DEVELOPMENT_PLAN.md`` record Surya as GPL-3.0. The published wheel says::

    Name: surya-ocr
    Version: 0.22.1
    License: Apache-2.0
    Project-URL: Repository, https://github.com/datalab-to/surya

    surya_ocr-0.22.1.dist-info/licenses/LICENSE  (9,135 bytes)
        Apache License
        Version 2.0, January 2004

Same publisher as Marker, same relicensing, same conclusion: permissive code,
run out of process for dependency reasons rather than licence ones.

**`scanned.pdf` is the regression target.** Every backend in every tier below
this one returns an empty document for it — that is documented in
``docs/BACKENDS.md`` and scored 0.000 by the fidelity scorer, deliberately, as
the honest measurement of "no OCR here". Surya is the backend that would move
that number, and **it has not been run**: this sandbox has no GPU and cannot
reach the weights. The 0.000 stands.
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

__all__ = ["SuryaConverter"]

#: What Surya reads. Images first, because a scanned page is the case it exists
#: for and the case nothing else here can serve at all.
_FORMATS: Final[tuple[str, ...]] = ("pdf", "png", "jpg", "jpeg", "tiff", "tif", "webp", "bmp")


class SuryaConverter(HeavyConverter):
    """Runs Surya's OCR pipeline out of process.

    Attributes:
        info: Static metadata.
        executable: ``surya_ocr``, from the allow-list.
        command: The console script ``surya-ocr`` installs.
    """

    info = BackendInfo(
        id="surya",
        name="Surya",
        description=(
            "OCR, layout detection and reading order in 90+ languages — Marker's "
            "engine on its own. The only backend here that reads a scanned page. "
            "Needs a GPU; never a tokenmill dependency."
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
        requires_binary="surya_ocr",
        upstream_url="https://github.com/datalab-to/surya",
        priority=1,
    )

    executable = "surya_ocr"
    command = "surya_ocr"
    install_steps = (
        f"python -m venv {environment_root('surya')}",
        f"{environment_root('surya')}/bin/pip install surya-ocr",
    )
    weights_licence = None

    def build_argv(self, source: Path, outdir: Path) -> list[str]:
        """Build Surya's arguments.

        Args:
            source: The document or image.
            outdir: Where Surya should write.

        Returns:
            The arguments after the executable.
        """
        return [
            self.path_argument(source),
            "--output_dir",
            self.path_argument(outdir),
        ]

    def read_output(self, outdir: Path, source: Path) -> str | None:
        """Read what Surya produced, preferring Markdown and falling back to JSON.

        Surya's CLI writes JSON — text lines with bounding boxes — rather than
        Markdown, because bounding boxes are what it is for. Newer releases can
        emit Markdown directly. Both are handled: the Markdown when it is there,
        and otherwise the recognised text lines lifted out of the JSON in
        reading order.

        Reading order is Surya's own, not reconstructed here. Sorting boxes
        ourselves would be a layout engine, which `docs/BACKENDS.md` has said
        since Phase 2 is not an adapter's job.

        Args:
            outdir: Where Surya was told to write.
            source: The original document, unused.

        Returns:
            The text, or ``None`` when nothing was produced.
        """
        del source
        markdown = first_markdown(outdir)
        if markdown is not None:
            return markdown
        return _text_from_surya_json(outdir)


def _text_from_surya_json(outdir: Path) -> str | None:
    """Lift the recognised text out of Surya's JSON results.

    Args:
        outdir: The directory Surya wrote into.

    Returns:
        One line per recognised text line, pages separated by a blank line, or
        ``None`` when there is no readable JSON.

    Raises:
        Nothing: a JSON file in a shape this does not recognise yields ``None``,
        and the caller reports "wrote no Markdown" with the tool's own stderr
        attached, which is more useful than a parse error about a file the user
        has never seen.
    """
    import json

    files = sorted(path for path in outdir.rglob("*.json") if path.is_file())
    if not files:
        return None

    lines: list[str] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except ValueError:
            continue
        for pages in _iter_page_lists(payload):
            for page in pages:
                if not isinstance(page, dict):
                    continue
                page_lines = [
                    str(item.get("text", "")).strip()
                    for item in page.get("text_lines", [])
                    if isinstance(item, dict) and str(item.get("text", "")).strip()
                ]
                if page_lines:
                    lines.extend(page_lines)
                    lines.append("")
    text = "\n".join(lines).strip()
    return f"{text}\n" if text else None


def _iter_page_lists(payload: object) -> list[list[object]]:
    """Find the per-page lists inside Surya's JSON, whatever it is keyed by.

    Surya keys its top-level object by input filename, and has also emitted a
    bare list. Both shapes are handled rather than one being assumed, because
    the difference is invisible until somebody with a GPU runs it.

    Args:
        payload: The decoded JSON.

    Returns:
        Every list of pages found, empty when the shape is unrecognised.
    """
    if isinstance(payload, list):
        return [list(payload)]
    if isinstance(payload, dict):
        return [list(value) for value in payload.values() if isinstance(value, list)]
    return []
