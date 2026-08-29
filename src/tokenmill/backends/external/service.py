r"""Reaching a converter over HTTP instead of running it.

The third isolation mode, and the only one that does not need the tool on this
machine at all. ``SUBPROCESS`` needs it installed alongside us; ``SERVICE``
does not, and that is the whole point for Phase 9: Marker,
MinerU, olmOCR and Surya want a GPU, several gigabytes of weights and a
dependency tree that must never touch ours. Running them in a container and
talking to them over HTTP is how they become usable without being installed.

This module is the **pattern**, proved on a `docling-serve`-shaped API, rather
than a wrapper for every heavy backend. The plan calls it optional and says it
exists to show Phase 9 the shape; ``§10`` of the assignment asked to be told if
it started turning into a phase of its own, and it deliberately has not. What is
here is what a Phase 9 adapter subclasses:

* **Nothing is auto-discovered and nothing is auto-started.** A service backend
  is unavailable unless the user says where it is, because a converter that
  probes ``localhost`` on a range of ports is doing something the user did not
  ask for. The address comes from ``--extra <id>_url=...``.
* **A probe is a real request.** "Available" means the service answered, not
  that a URL was configured. One short request, cached per process, with the
  same honesty rule the PyMuPDF4LLM probe has: an address that does not answer
  is *unavailable with a hint*, never available-then-failing.
* **The network permission is the user's.** A service backend needs
  ``--allow-network``, and refuses with
  :class:`~tokenmill.core.errors.NetworkRequired` without it, exactly as the
  ``npx`` path in the repomix adapter does. That a service happens to be on
  ``localhost`` does not make talking to it not a network call.
* **stdlib only.** ``urllib.request``, not ``httpx``. The core install stays
  light (rule 1), and a service adapter must not be the thing that drags an HTTP
  client into it.

**No service backend is registered.** This class has no entry point, and that is
deliberate rather than unfinished: registering a backend for a container nobody
is running would put a permanently-unavailable row in ``tokenmill backends`` for
every user. Phase 9 registers the concrete ones, against real services, with
real measurements. ``tests/unit/test_service_backend.py`` exercises this against
a real local HTTP server rather than a mock, so the pattern is executed rather
than asserted.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from abc import abstractmethod
from pathlib import Path
from typing import Any, Final

from tokenmill.core.errors import BackendFailed, NetworkRequired, Timeout
from tokenmill.core.models import Availability, ConvertOptions, Source
from tokenmill.core.protocol import BaseConverter, ConversionContext

__all__ = ["ServiceConverter"]

#: How long a probe may take. Short: this runs while a user waits for a backend
#: listing, and a service that cannot answer in three seconds is not one a
#: conversion should be queued against either.
_PROBE_TIMEOUT_S: Final = 3.0

#: Sent so an operator reading their service's logs can see who called.
_USER_AGENT: Final = "tokenmill (+https://github.com/RSD-Studio/tokenmill)"


class ServiceConverter(BaseConverter):
    """A backend that converts by asking an HTTP service to do it.

    Subclasses declare :attr:`health_path` and implement :meth:`build_request`
    and :meth:`read_response`. Everything else — the address, the probe, the
    network permission, timeouts and the mapping of failures into the taxonomy —
    is here.

    Attributes:
        health_path: Path appended to the base URL for the availability probe.
    """

    health_path: str = "/health"

    def __init__(self) -> None:
        """Initialise the availability cache."""
        super().__init__()
        self._base_url: str | None = None

    # ------------------------------------------------------------------ address

    @property
    def url_option(self) -> str:
        """The ``--extra`` key that carries this service's address.

        Returns:
            ``<backend id>_url``, so ``--extra docling_serve_url=http://...``.
        """
        return f"{self.info.id}_url"

    def base_url(self, options: ConvertOptions | None = None) -> str | None:
        """Return the configured service address.

        Args:
            options: May carry the address in ``extra``. When omitted, only a
                previously configured address is returned — which is why
                :meth:`_probe` reports "not configured" rather than guessing.

        Returns:
            The base URL with any trailing slash removed, or ``None``.
        """
        if options is not None:
            value = options.extra.get(self.url_option)
            if isinstance(value, str) and value.strip():
                self._base_url = self._validated(value.strip().rstrip("/"))
        return self._base_url

    def _validated(self, url: str) -> str:
        """Check a configured address before anything is ever fetched from it.

        Checked here, where the address is accepted, rather than at each request:
        the availability probe fetches too, and a ``file://`` address would
        otherwise turn a health check into a local file read.

        Args:
            url: The configured address.

        Returns:
            The same address.

        Raises:
            BackendFailed: If it is not http or https.
        """
        scheme = urllib.parse.urlparse(url).scheme.lower()
        if scheme not in {"http", "https"}:
            raise BackendFailed(
                f"refusing to use {url!r} as a service address: only http and https are allowed",
                backend_id=self.info.id,
                hint="a file:// or gopher:// address here would read local files",
            )
        return url

    def _probe(self) -> Availability:
        """Report availability by asking the service whether it is there.

        Returns:
            Present when a configured address answered. Unsupported, with the
            option to set, when no address is configured — because "you have not
            told me where it is" is a different problem from "it is not running",
            and a user needs to be told which.
        """
        url = self.base_url()
        if url is None:
            return Availability.unsupported(
                f"no address configured for the {self.info.name} service",
                hint=(
                    f"start the service and pass --extra {self.url_option}=http://localhost:5001 "
                    f"(and --allow-network, since talking to it is a network call)"
                ),
            )

        try:
            self._request(f"{url}{self.health_path}", timeout_s=_PROBE_TIMEOUT_S)
        except Exception:
            return Availability.unsupported(
                f"the {self.info.name} service at {url} did not answer",
                hint=f"check it is running: curl {url}{self.health_path}",
            )
        return Availability.present()

    # ------------------------------------------------------------------ request

    def _request(
        self,
        url: str,
        *,
        timeout_s: float,
        payload: bytes | None = None,
        content_type: str | None = None,
    ) -> bytes:
        """Make one HTTP request and return the body.

        Args:
            url: The absolute URL.
            timeout_s: Wall-clock budget.
            payload: A request body, which makes this a POST.
            content_type: The body's media type.

        Returns:
            The response body.

        Raises:
            Timeout: If the service does not answer in time.
            BackendFailed: On any other transport or protocol failure, carrying
                whatever the service said, because a service's error body is
                usually the only useful thing about the failure.
        """
        headers = {"User-Agent": _USER_AGENT}
        if content_type is not None:
            headers["Content-Type"] = content_type

        request = urllib.request.Request(  # noqa: S310 - http(s) only, checked below
            url, data=payload, headers=headers, method="POST" if payload else "GET"
        )
        if request.type not in {"http", "https"}:
            # Belt to _validated's braces: that checks the configured base, this
            # checks the URL actually being opened, so a subclass that builds a
            # path cannot construct its way past it.
            raise BackendFailed(
                f"refusing to fetch {url!r}: only http and https are allowed",
                backend_id=self.info.id,
                hint="a file:// or gopher:// URL here would read local files",
            )

        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
                return bytes(response.read())
        except TimeoutError as exc:
            raise Timeout(
                f"the {self.info.name} service did not answer within {timeout_s:g}s",
                backend_id=self.info.id,
                hint="raise --timeout, or give the service more resources",
            ) from exc
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:2000]
            raise BackendFailed(
                f"the {self.info.name} service returned HTTP {exc.code}",
                backend_id=self.info.id,
                stderr=body,
                hint="check the service's own logs; the response body is attached",
            ) from exc
        except urllib.error.URLError as exc:
            raise BackendFailed(
                f"could not reach the {self.info.name} service: {exc.reason}",
                backend_id=self.info.id,
                hint=f"check it is running and that --extra {self.url_option} is right",
            ) from exc

    def post_json(self, path: str, body: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
        """POST a JSON document and decode the JSON reply.

        Args:
            path: Appended to the base URL.
            body: The request document.
            timeout_s: Wall-clock budget.

        Returns:
            The decoded reply.

        Raises:
            BackendFailed: If no address is configured, or the reply is not JSON.
        """
        url = self.base_url()
        if url is None:
            raise BackendFailed(
                f"no address configured for the {self.info.name} service",
                backend_id=self.info.id,
                hint=f"pass --extra {self.url_option}=http://localhost:5001",
            )

        raw = self._request(
            f"{url}{path}",
            timeout_s=timeout_s,
            payload=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise BackendFailed(
                f"the {self.info.name} service did not return JSON",
                backend_id=self.info.id,
                stderr=raw.decode("utf-8", errors="replace")[:2000],
            ) from exc
        if not isinstance(decoded, dict):
            raise BackendFailed(
                f"the {self.info.name} service returned {type(decoded).__name__}, not an object",
                backend_id=self.info.id,
            )
        return decoded

    # ------------------------------------------------------------------ convert

    def convert(self, source: Source, options: ConvertOptions) -> Any:
        """Read the service address from the options, then convert as usual.

        Overridden for an ordering reason that only shows up here.
        :meth:`~tokenmill.core.protocol.BaseConverter.convert` checks
        availability *first*, and for a service backend availability depends on
        an address that arrives **with the options** — so the base's check would
        always run against an unconfigured backend and refuse a conversion the
        user had configured correctly. Found by running it.

        Args:
            source: The input to convert.
            options: Carries the service address in ``extra``.

        Returns:
            The conversion result.

        Raises:
            ConversionError: As the base class does.
        """
        if self.base_url(options) is not None:
            # A newly configured address invalidates a probe taken without one.
            self._availability = None
        return super().convert(source, options)

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Convert by asking the service, once the permissions are satisfied.

        Args:
            source: The input to convert.
            options: Supplies the address, the timeout and the network permission.
            context: Collects metadata and warnings.

        Returns:
            The converted text.

        Raises:
            NetworkRequired: If network access has not been permitted. Talking to
                a service is a network call whether or not it is on localhost.
            BackendFailed: If no address is configured, or the service fails.
        """
        url = self.base_url(options)
        if url is None:
            raise BackendFailed(
                f"no address configured for the {self.info.name} service",
                backend_id=self.info.id,
                hint=f"pass --extra {self.url_option}=http://localhost:5001",
            )
        if not options.allow_network:
            raise NetworkRequired(
                f"{self.info.id} converts by calling a service at {url}",
                backend_id=self.info.id,
                hint="pass --allow-network, or choose a backend that runs locally",
            )

        context.note("service_url", url)
        context.note("isolation", self.info.isolation.value)
        return self.call_service(source, options, context)

    @abstractmethod
    def call_service(
        self, source: Source, options: ConvertOptions, context: ConversionContext
    ) -> str:
        """Ask the service to convert the source.

        The only method a service adapter has to write. By the time it is called
        the address is configured, network access is permitted, and availability,
        format support and size have all been checked.

        Args:
            source: The input to convert.
            options: How to convert it.
            context: Collects warnings and metadata.

        Returns:
            The converted text.

        Raises:
            ConversionError: On any failure.
        """

    @staticmethod
    def read_bytes(source: Source) -> bytes:
        """Return the source's bytes, however it was given.

        Args:
            source: The input.

        Returns:
            Its content.

        Raises:
            BackendFailed: If the source carries neither bytes nor a readable
                path.
        """
        if source.data is not None:
            return source.data
        if source.path is not None:
            return Path(source.path).read_bytes()
        msg = "a service backend needs bytes or a file to send"
        raise BackendFailed(msg, backend_id="service")
