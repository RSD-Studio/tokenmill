"""The HTTP service isolation mode, against a real server rather than a mock.

`docs/DEVELOPMENT_PLAN.md` calls this mode optional and says it exists to prove
the pattern for Phase 9's GPU backends. A pattern proved against a mock proves
that the mock matches the code; these run a real `http.server` on a real socket,
so what is exercised is the thing Phase 9 will subclass.

The server deliberately misbehaves on request — 500s, a non-JSON body, a hang —
because the failure paths are what an adapter for a container someone else
operates will spend its life on.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from tokenmill.backends.external.service import ServiceConverter
from tokenmill.core.errors import BackendFailed, NetworkRequired, Timeout
from tokenmill.core.models import (
    BackendInfo,
    ConvertOptions,
    Domain,
    IsolationMode,
    LicenseTier,
    Source,
)
from tokenmill.core.protocol import ConversionContext

#: What the fake service should do next. Set per test.
BEHAVIOUR: dict[str, str] = {"mode": "ok"}


class _Handler(BaseHTTPRequestHandler):
    """A `docling-serve`-shaped API that can be told to misbehave."""

    def log_message(self, *args: object) -> None:
        """Silence the default stderr logging, which is noise in a test run."""

    def do_GET(self) -> None:
        """Answer the health probe."""
        if BEHAVIOUR["mode"] == "down":
            self.send_error(503, "service unavailable")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def do_POST(self) -> None:
        """Answer a conversion request according to BEHAVIOUR."""
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        mode = BEHAVIOUR["mode"]

        if mode == "slow":
            time.sleep(5)
        if mode == "error":
            self.send_error(500, "the model fell over")
            return
        if mode == "notjson":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"<html>a proxy error page</html>")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"markdown": "# Converted\n\nby the service.\n"}).encode())


@pytest.fixture
def service() -> Iterator[str]:
    """Run the fake service on a real socket for the duration of one test."""
    BEHAVIOUR["mode"] = "ok"
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class _FakeServiceConverter(ServiceConverter):
    """A concrete service backend, shaped like the Phase 9 ones will be."""

    info = BackendInfo(
        id="fake_serve",
        name="Fake Serve",
        description="A service backend that exists to exercise the pattern.",
        domains=(Domain.DOCUMENTS,),
        input_formats=("pdf", "docx"),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        isolation=IsolationMode.SERVICE,
        upstream_url="https://example.invalid",
        requires_network=True,
    )
    health_path = "/health"

    def call_service(
        self, source: Source, options: ConvertOptions, context: ConversionContext
    ) -> str:
        """Send the document and read the Markdown back."""
        reply = self.post_json(
            "/v1/convert",
            {"filename": source.name, "size": len(self.read_bytes(source))},
            timeout_s=options.timeout_s,
        )
        context.note("service_reported", sorted(reply))
        markdown = reply.get("markdown")
        if not isinstance(markdown, str):
            raise BackendFailed("the service returned no markdown field", backend_id=self.info.id)
        return markdown


@pytest.fixture
def document(tmp_path: Path) -> Source:
    """A file to send. Its content does not matter to the fake service."""
    path = tmp_path / "input.pdf"
    path.write_bytes(b"%PDF-1.4 not really\n")
    return Source.from_path(path)


NETWORKED = ConvertOptions(tokenizer="bytes", allow_network=True)


class TestTheServicePattern:
    def test_it_converts_through_a_real_http_service(self, service: str, document: Source) -> None:
        converter = _FakeServiceConverter()
        options = NETWORKED.with_(extra={converter.url_option: service})

        result = converter.convert(document, options)

        assert "Converted" in result.text
        assert result.metadata["service_url"] == service
        assert result.metadata["isolation"] == "service"

    def test_a_configured_and_answering_service_is_available(self, service: str) -> None:
        converter = _FakeServiceConverter()
        converter.base_url(NETWORKED.with_(extra={converter.url_option: service}))

        assert converter.is_available()


class TestNothingIsGuessedAt:
    def test_an_unconfigured_service_is_unavailable_and_says_what_to_set(self) -> None:
        """No port scanning, no localhost guessing.

        A converter that probed a range of ports would be doing something the
        user did not ask for, on a machine that may not be theirs.
        """
        availability = _FakeServiceConverter().is_available()

        assert not availability
        assert "fake_serve_url" in (availability.hint or "")

    def test_a_configured_but_dead_service_is_unavailable_rather_than_available(
        self, service: str
    ) -> None:
        """Available must mean it answered, not that a URL was typed."""
        converter = _FakeServiceConverter()
        converter.base_url(NETWORKED.with_(extra={converter.url_option: service}))
        BEHAVIOUR["mode"] = "down"

        availability = converter.is_available()

        assert not availability
        assert "did not answer" in (availability.reason or "")
        assert "curl" in (availability.hint or "")

    def test_the_two_kinds_of_unavailable_are_distinguishable(self, service: str) -> None:
        """Not knowing where it is, and it not running, need different fixes."""
        unconfigured = _FakeServiceConverter().is_available()

        configured = _FakeServiceConverter()
        configured.base_url(NETWORKED.with_(extra={configured.url_option: service}))
        BEHAVIOUR["mode"] = "down"
        dead = configured.is_available()

        assert (unconfigured.reason or "") != (dead.reason or "")


class TestPermissionsAndFailures:
    def test_talking_to_a_service_needs_allow_network_even_on_localhost(
        self, service: str, document: Source
    ) -> None:
        """A loopback address is still a network call.

        Same rule the repomix adapter applies to `npx`: a command the user
        believed was local must not reach the network without permission.
        """
        converter = _FakeServiceConverter()
        options = ConvertOptions(tokenizer="bytes", extra={converter.url_option: service})

        with pytest.raises(NetworkRequired) as caught:
            converter.convert(document, options)

        assert "--allow-network" in (caught.value.hint or "")

    def test_a_500_carries_the_services_own_body(self, service: str, document: Source) -> None:
        """A service's error body is usually the only useful thing about it."""
        converter = _FakeServiceConverter()
        options = NETWORKED.with_(extra={converter.url_option: service})
        converter.base_url(options)
        BEHAVIOUR["mode"] = "error"

        with pytest.raises(BackendFailed) as caught:
            converter.convert(document, options)

        assert "HTTP 500" in str(caught.value)
        assert "the model fell over" in (caught.value.stderr or "")

    def test_a_non_json_reply_is_reported_as_such_and_not_as_a_crash(
        self, service: str, document: Source
    ) -> None:
        """A proxy's HTML error page is the realistic version of this."""
        converter = _FakeServiceConverter()
        options = NETWORKED.with_(extra={converter.url_option: service})
        converter.base_url(options)
        BEHAVIOUR["mode"] = "notjson"

        with pytest.raises(BackendFailed) as caught:
            converter.convert(document, options)

        assert "did not return JSON" in str(caught.value)
        assert "proxy error page" in (caught.value.stderr or "")

    def test_a_slow_service_raises_the_taxonomys_timeout(
        self, service: str, document: Source
    ) -> None:
        converter = _FakeServiceConverter()
        options = NETWORKED.with_(extra={converter.url_option: service}, timeout_s=1.0)
        converter.base_url(options)
        BEHAVIOUR["mode"] = "slow"

        with pytest.raises(Timeout) as caught:
            converter.convert(document, options)

        assert caught.value.backend_id == "fake_serve"

    def test_a_non_http_url_is_refused_before_it_is_opened(self, document: Source) -> None:
        """`file://` here would turn a converter into a local file reader."""
        converter = _FakeServiceConverter()
        options = NETWORKED.with_(extra={converter.url_option: "file:///etc"})

        with pytest.raises(BackendFailed) as caught:
            converter.convert(document, options)

        assert "only http and https" in str(caught.value)
        assert converter.base_url() is None, "the bad address must not have been stored"


class TestNoServiceBackendIsRegistered:
    def test_the_pattern_ships_without_a_backend_using_it(self) -> None:
        """Deliberate, and worth asserting so it stays deliberate.

        Registering a backend for a container nobody is running would put a
        permanently-unavailable row in `tokenmill backends` for every user.
        Phase 9 registers the concrete ones, against real services.
        """
        from tokenmill.core.registry import Registry

        service_backends = [
            c.info.id for c in Registry() if c.info.isolation is IsolationMode.SERVICE
        ]

        assert service_backends == [], (
            f"{service_backends} are registered service backends. If Phase 9 has "
            f"started, update this test; otherwise a user is seeing a row for a "
            f"container they were never told to run"
        )
