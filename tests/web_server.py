"""A real HTTP server on loopback, for testing the fetcher against.

The fetcher is the one part of tokenmill that opens a socket, so it is the one
part that cannot be tested by asserting no socket was opened. Mocking
:mod:`urllib` would test the mock: redirect chains, ``robots.txt``, chunked
reads, charset headers and status handling all live *inside* urllib, and a
double replaces exactly the code under test.

So the tests drive a real server, in-process, on ``127.0.0.1``. It speaks real
HTTP over a real socket and needs no network beyond loopback, which means these
tests run in an air-gapped sandbox and in CI alike. The genuinely-remote path —
fetching a public URL — is separately covered by ``network``-marked tests, which
are skipped by default and say so.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

__all__ = ["Route", "ServedSite", "serve"]


@dataclass(frozen=True, slots=True)
class Route:
    """One canned response.

    Attributes:
        body: The bytes to send.
        status: The HTTP status code.
        content_type: The ``Content-Type`` header, or ``None`` to omit it.
        location: A ``Location`` header, for redirect responses.
        delay_s: Seconds to stall before responding, for timeout tests.
    """

    body: bytes = b""
    status: int = 200
    content_type: str | None = "text/html; charset=utf-8"
    location: str | None = None
    delay_s: float = 0.0


@dataclass
class ServedSite:
    """A running loopback server and the record of what it was asked for.

    Attributes:
        base_url: The origin, e.g. ``http://127.0.0.1:54321``.
        routes: Path to response.
        requests: Every path requested, in order.
        user_agents: The ``User-Agent`` of every request, in order.
    """

    base_url: str
    routes: dict[str, Route]
    requests: list[str] = field(default_factory=list)
    user_agents: list[str] = field(default_factory=list)

    def url(self, path: str = "/") -> str:
        """Return an absolute URL for a path on this server.

        Args:
            path: The path, with a leading slash.

        Returns:
            The absolute URL.
        """
        return f"{self.base_url}{path}"


@contextmanager
def serve(routes: dict[str, Route]) -> Iterator[ServedSite]:
    """Run a loopback HTTP server for the duration of the block.

    Args:
        routes: Path to canned response. A path that is not present answers
            404, so a test can assert on a missing page without declaring one.

    Yields:
        The running site, including the log of what was requested.
    """
    site = ServedSite(base_url="", routes=routes)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # BaseHTTPRequestHandler dispatches to this exact name
            site.requests.append(self.path)
            site.user_agents.append(self.headers.get("User-Agent", ""))
            route = site.routes.get(self.path)
            if route is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if route.delay_s:
                time.sleep(route.delay_s)
            self.send_response(route.status)
            if route.content_type is not None:
                self.send_header("Content-Type", route.content_type)
            if route.location is not None:
                self.send_header("Location", route.location)
            self.send_header("Content-Length", str(len(route.body)))
            self.end_headers()
            self.wfile.write(route.body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base signature
            """Stay quiet; a test run should not print an access log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    site.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
