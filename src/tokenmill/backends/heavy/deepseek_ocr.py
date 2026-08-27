r"""DeepSeek-OCR: the most on-theme backend in the project, and the least verified.

**Why it gets its own module docstring rather than a line in a table.** Every
other backend here reduces tokens by converting a document into a cheaper
representation of the same text. DeepSeek-OCR's claim is different in kind: that
a page *rendered as an image* and fed to a vision encoder costs fewer tokens than
the same page's text, because the encoder compresses it optically. If that holds,
the cheapest way to give a model a document is sometimes to give it a picture of
one — which is the exact opposite of everything this project does, and is why the
plan singles it out.

**The paper's numbers are the paper's numbers.** DeepSeek's own report describes
compression ratios of roughly 10x at high decoding precision, degrading as the
ratio rises past about 20x. That is DeepSeek's measurement of DeepSeek's model on
DeepSeek's benchmark, restated here as theirs and cited as theirs.
``CONTRIBUTING.md`` rule 4 forbids restating a vendor claim as fact, and this is
the backend where the temptation is largest.

**Ours are absent, and that is the honest status.** Measuring optical compression
on our own corpus needs the model running, which needs a GPU and
``huggingface.co``, and this environment has neither. So:

* **No compression ratio has been produced by this code**, here or anywhere.
* ``docs/BACKENDS.md`` and ``docs/BENCHMARKS.md`` carry the paper's figure,
  attributed, and **no figure of ours**.
* The adapter records the service's own ``prompt_tokens`` and
  ``completion_tokens`` on every result, namespaced ``service_*``, because that
  pair *is* the measurement — vision tokens in, text tokens out — and the first
  person to run this with a GPU gets the number the project has been unable to.

What is verified is the HTTP path, against a real local server: request shape,
response parsing, error bodies, timeouts and the refusal when no address is
configured.

**Not the PyPI package.** ``pip install deepseek-ocr`` installs a third party's
SDK for a hosted API — see :mod:`tokenmill.backends.heavy.vllm_service`. This
adapter talks to a model **you** are serving.
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

__all__ = ["DeepSeekOcrConverter"]

_FORMATS: Final[tuple[str, ...]] = ("png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif")


class DeepSeekOcrConverter(VllmOcrConverter):
    """Reads a page image through a DeepSeek-OCR deployment you are running.

    Attributes:
        info: Static metadata.
        model_name: What vLLM was started with.
        prompt: DeepSeek-OCR's own Markdown instruction.
    """

    info = BackendInfo(
        id="deepseek_ocr",
        name="DeepSeek-OCR",
        description=(
            "Optical context compression: a page image through a vision encoder, "
            "which its authors report costs far fewer tokens than the same page's "
            "text. Reached over HTTP; you run the model."
        ),
        domains=(Domain.DOCUMENTS,),
        input_formats=_FORMATS,
        output_formats=(OutputFormat.MARKDOWN,),
        # The model weights' licence, not a package's: there is no package.
        # Reported by DeepSeek as MIT for the code and the weights; NOT verified
        # here, because the host it is published on is denied at this
        # environment's egress proxy. docs/LICENSES.md records it as reported.
        license="MIT (reported; unverified — see docs/LICENSES.md)",
        license_tier=LicenseTier.PERMISSIVE,
        isolation=IsolationMode.SERVICE,
        install_extra=None,
        requires_gpu=True,
        requires_network=True,
        upstream_url="https://github.com/deepseek-ai/DeepSeek-OCR",
        priority=1,
    )

    model_name = "deepseek-ai/DeepSeek-OCR"
    #: DeepSeek-OCR's own documented instruction for Markdown output. The
    #: leading `<image>` token is part of its prompt format rather than a
    #: mistake: the model expects the image referenced in the text.
    prompt = "<image>\n<|grounding|>Convert the document to markdown."
