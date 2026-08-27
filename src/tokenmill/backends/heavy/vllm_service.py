r"""Vision-language OCR models reached over HTTP, not installed.

DeepSeek-OCR and dots.ocr are not Python packages. They are **model weights**
published on a model host, served by vLLM behind an OpenAI-compatible HTTP API.
There is nothing to ``pip install``, which makes the subprocess pattern the
other four heavy backends use inapplicable and the service pattern the only
honest one.

**A trap worth naming, because a careful person walks straight into it.** There
*is* a ``deepseek-ocr`` package on PyPI. It is not DeepSeek's::

    Name: deepseek-ocr
    Version: 0.3.0
    Summary: A simple and efficient Python SDK for DeepSeek-OCR API
    License-Expression: MIT
    Project-URL: Repository, https://github.com/BukeLy/DeepSeek-OCR-SDK
    Copyright (c) 2025 Chengjie

A third party's client for a hosted API, under a different copyright. Wrapping
it would have meant shipping a **hosted-SaaS backend**, which the project's
first constraint forbids outright, while appearing to have wrapped the model.
Checked because ``RESEARCH.md`` has been wrong four times; found because the
summary was read rather than the licence field.

**Nothing is auto-discovered and nothing is auto-started**, inherited from
:class:`~tokenmill.backends.external.service.ServiceConverter` and worth
repeating: a converter that scanned ``localhost`` for an inference server would
be doing something nobody asked for. The address arrives as
``--extra <id>_url=http://host:8000``, a probe is a real request, and talking to
it needs ``--allow-network`` even on loopback.

**What is verified.** The HTTP behaviour, end to end, against a real local
server rather than a mock — request shape, response parsing, an error body, a
non-JSON reply, a timeout, and a refusal without an address. What is **not**
verified is that any real DeepSeek-OCR or dots.ocr deployment answers exactly
this way: no such service has been run here, and ``docs/BACKENDS.md`` says so.
The request is built to the OpenAI chat-completions shape both models' own
serving instructions use, which is a documented contract rather than a guess,
and that is the strongest claim available without a GPU.
"""

from __future__ import annotations

import base64
import mimetypes
from typing import Any, Final

from tokenmill.backends.external.service import ServiceConverter
from tokenmill.backends.heavy.base import HeavyTier
from tokenmill.core.errors import BackendFailed
from tokenmill.core.models import ConvertOptions, Source
from tokenmill.core.protocol import ConversionContext

__all__ = ["VllmOcrConverter"]

#: The OpenAI-compatible endpoint vLLM serves.
_COMPLETIONS_PATH: Final = "/v1/chat/completions"

#: vLLM answers ``/health`` with 200 once the model is loaded, which is exactly
#: the question the availability probe asks: not "is something listening" but
#: "is it ready to convert".
_HEALTH_PATH: Final = "/health"

#: Fallback media type for an image whose extension says nothing.
_DEFAULT_MEDIA_TYPE: Final = "image/png"


class VllmOcrConverter(HeavyTier, ServiceConverter):
    """A vision-language OCR model served by vLLM over an OpenAI-compatible API.

    Subclasses declare :attr:`model_name` and :attr:`prompt`; everything else —
    the request shape, the response parsing and the failure taxonomy — is here.

    Attributes:
        model_name: What to put in the request's ``model`` field. vLLM matches
            it against what it was served with, and a mismatch is a 400 with a
            useful body, so it is sent rather than omitted.
        prompt: The instruction sent with the image. Part of the adapter rather
            than a user setting, because these models are prompt-sensitive in
            ways a user cannot be expected to know and a wrong prompt looks like
            a bad model.
        max_tokens: Ceiling on the reply. A page of dense text is a few thousand
            tokens; the default is generous and finite, because a model that
            loops would otherwise hold the connection until the timeout.
    """

    health_path = _HEALTH_PATH
    model_name: str
    prompt: str
    max_tokens: int = 8192

    def call_service(
        self, source: Source, options: ConvertOptions, context: ConversionContext
    ) -> str:
        """Send the document to the model and return what it read.

        Args:
            source: The document or image.
            options: Supplies the timeout.
            context: Collects metadata.

        Returns:
            The extracted Markdown.

        Raises:
            BackendFailed: If the service answers in a shape this cannot read.
                Deliberately not "returns empty": a reply that is not a chat
                completion means the address points at something that is not
                this model, and saying so beats reporting an empty document.
        """
        data = self.read_bytes(source)
        media_type = _media_type(source)
        payload = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            # Zero, and it matters. An OCR backend that returned different text
            # on two runs of the same page would make every measurement in
            # docs/BENCHMARKS.md unreproducible.
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{media_type};base64,"
                                    f"{base64.b64encode(data).decode('ascii')}"
                                )
                            },
                        },
                        {"type": "text", "text": self.prompt},
                    ],
                }
            ],
        }

        reply = self.post_json(_COMPLETIONS_PATH, payload, timeout_s=options.timeout_s)
        context.note("model", self.model_name)
        context.note("service_kind", "vllm-openai")
        _note_usage(reply, context)
        return _first_message(reply, backend_id=self.info.id)


def _media_type(source: Source) -> str:
    """Decide the media type to label the uploaded bytes with.

    Args:
        source: The input.

    Returns:
        The source's own media type when it has one, otherwise a guess from the
        filename, otherwise PNG. The guess is safe here in a way it would not be
        elsewhere: the value only labels a data URL for a model that sniffs the
        bytes anyway.
    """
    if source.media_type:
        return source.media_type
    guessed, _ = mimetypes.guess_type(source.name)
    return guessed or _DEFAULT_MEDIA_TYPE


def _note_usage(reply: dict[str, Any], context: ConversionContext) -> None:
    """Record the service's own token accounting, labelled as the service's.

    These are the **model's** tokens in the **model's** tokenizer, which is not
    the one the user asked tokenmill for. They are worth keeping — for
    DeepSeek-OCR the ratio of vision tokens to output tokens is the whole
    optical-compression story — and they are namespaced so nobody mistakes them
    for a tokenmill measurement. The pipeline still does every count it reports.

    Args:
        reply: The decoded response.
        context: Collects the notes.
    """
    usage = reply.get("usage")
    if not isinstance(usage, dict):
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            context.note(f"service_{key}", value)


def _first_message(reply: dict[str, Any], *, backend_id: str) -> str:
    """Pull the assistant's text out of a chat-completions reply.

    Args:
        reply: The decoded response.
        backend_id: Attributed on failure.

    Returns:
        The message content.

    Raises:
        BackendFailed: If the reply is not shaped like a chat completion.
    """
    choices = reply.get("choices")
    if not isinstance(choices, list) or not choices:
        raise BackendFailed(
            "the service returned no choices; it may not be an OpenAI-compatible endpoint",
            backend_id=backend_id,
            hint="check the URL points at vLLM's /v1 API and that the model is loaded",
        )
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise BackendFailed(
            "the service's reply had no text content",
            backend_id=backend_id,
            hint="check the model name matches what the server was started with",
        )
    return content
