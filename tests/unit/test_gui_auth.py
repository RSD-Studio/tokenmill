"""The `--server` shared token, driven as ASGI rather than described.

Defect N15. Phase 8 shipped `tokenmill gui --server` binding `0.0.0.0` with no
authentication of any kind, warning at start-up and calling that a mitigation.
The owner's §3.1 decided the repair: a shared token required on every request,
generated and printed when the operator has not set one, so the secure path is
the default path.

These tests drive the guard the way a server does — an ASGI scope in, ASGI
messages out — because the two things most likely to be wrong are both
protocol-level. A guard that only saw `http` would leave the **WebSocket** the
whole interface runs on unauthenticated, and a refused WebSocket answered with
an HTTP response is a protocol error some servers raise on. Neither is visible
to a test that calls a helper function.

No NiceGUI here on purpose: the module under test imports none, so these run on
every cell of the matrix rather than only where the `gui` extra is installed.
For the same reason the coroutines are driven with `asyncio.run` rather than
with an async-test plugin: `anyio` arrives with the `gui` extra, and a test that
needed it would silently stop running on the cells that matter most.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from typing import Any

import pytest

from tokenmill.gui.auth import (
    COOKIE_NAME,
    QUERY_PARAM,
    SERVER_TOKEN_ENV,
    ServerTokenGuard,
    resolve_server_token,
)

TOKEN = "a-shared-token-long-enough-to-pass"  # noqa: S105 - a test fixture


async def _ok_app(
    scope: Mapping[str, Any],
    receive: Any,
    send: Any,
) -> None:
    """A minimal ASGI application that says yes to everything.

    Args:
        scope: The connection scope.
        receive: Unused.
        send: The send channel.
    """
    del receive
    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"the interface"})


class _Capture:
    """Collects what an application sent, so a test can assert on it."""

    def __init__(self) -> None:
        self.messages: list[Mapping[str, Any]] = []

    async def __call__(self, message: Mapping[str, Any]) -> None:
        """Record one ASGI message.

        Args:
            message: The message.
        """
        self.messages.append(message)

    @property
    def status(self) -> int | None:
        """The HTTP status, if there was one.

        Returns:
            The status code, or ``None``.
        """
        for message in self.messages:
            if message["type"] == "http.response.start":
                return int(message["status"])
        return None

    @property
    def set_cookies(self) -> list[str]:
        """Every ``Set-Cookie`` header value the response carried.

        Returns:
            The values, decoded.
        """
        out: list[str] = []
        for message in self.messages:
            if message["type"] != "http.response.start":
                continue
            out.extend(
                bytes(value).decode("latin-1")
                for key, value in message.get("headers") or ()
                if bytes(key).lower() == b"set-cookie"
            )
        return out

    @property
    def types(self) -> list[str]:
        """The message types, in order.

        Returns:
            The types.
        """
        return [str(m["type"]) for m in self.messages]


async def _receive() -> Mapping[str, Any]:
    """Stand in for the ASGI receive channel; nothing here reads a body.

    Returns:
        A disconnect message.
    """
    return {"type": "http.disconnect"}


def _call(
    guard: ServerTokenGuard,
    *,
    kind: str = "http",
    headers: list[tuple[bytes, bytes]] | None = None,
    query: bytes = b"",
) -> _Capture:
    """Send one request through the guard and return what came back.

    Args:
        guard: The middleware under test.
        kind: ``"http"``, ``"websocket"`` or ``"lifespan"``.
        headers: Raw ASGI headers.
        query: The raw query string.

    Returns:
        What came back.
    """
    capture = _Capture()
    scope = {
        "type": kind,
        "path": "/",
        "headers": headers or [],
        "query_string": query,
        "client": ("192.0.2.7", 51234),
    }
    asyncio.run(guard(scope, _receive, capture))
    return capture


@pytest.fixture
def guard() -> ServerTokenGuard:
    """A guard wrapping the yes-to-everything application.

    Returns:
        The middleware.
    """
    return ServerTokenGuard(_ok_app, TOKEN)


class TestResolvingTheToken:
    """Where the secret comes from, and that there is no way to have none."""

    def test_an_explicit_token_wins(self) -> None:
        secret = resolve_server_token(
            "from-the-command-line",
            configured="from-the-file",
            environ={SERVER_TOKEN_ENV: "from-the-environment"},
        )

        assert secret.value == "from-the-command-line"
        assert secret.origin == "--token"
        assert not secret.generated

    def test_the_environment_beats_the_config_file(self) -> None:
        secret = resolve_server_token(
            configured="from-the-file", environ={SERVER_TOKEN_ENV: "from-the-environment"}
        )

        assert secret.value == "from-the-environment"

    def test_the_config_file_is_used_when_nothing_else_supplies_one(self) -> None:
        secret = resolve_server_token(configured="from-the-file", environ={})

        assert secret.value == "from-the-file"
        assert secret.origin == "config file"

    def test_with_nothing_configured_a_token_is_generated_and_marked_as_such(self) -> None:
        """The secure path is the default path, not the diligent one."""
        secret = resolve_server_token(environ={})

        assert secret.generated
        assert len(secret.value) >= 32
        # URL-safe, because it is printed inside a URL for the user to paste.
        assert re.fullmatch(r"[A-Za-z0-9_-]+", secret.value)

    def test_two_generated_tokens_differ(self) -> None:
        first = resolve_server_token(environ={})
        second = resolve_server_token(environ={})

        assert first.value != second.value

    @pytest.mark.parametrize("supplied", ["", "   ", "short"])
    def test_a_too_short_token_is_refused_rather_than_accepted(self, supplied: str) -> None:
        """`--token ""` or an unset shell variable must not silently open it.

        This is the failure mode that would matter: an operator who thinks they
        configured a token, a variable that expanded to nothing, and an instance
        on the LAN comparing every request against an empty string.
        """
        with pytest.raises(ValueError, match="characters"):
            resolve_server_token(supplied, environ={})


class TestTheGuardRefusesWhatItShould:
    def test_a_request_with_no_token_is_401(self, guard: ServerTokenGuard) -> None:
        result = _call(guard)

        assert result.status == 401
        assert result.types == ["http.response.start", "http.response.body"]

    def test_a_request_with_the_wrong_token_is_401(self, guard: ServerTokenGuard) -> None:
        result = _call(guard, headers=[(b"authorization", b"Bearer wrong-token-entirely")])

        assert result.status == 401

    def test_a_prefix_of_the_token_is_not_enough(self, guard: ServerTokenGuard) -> None:
        """The obvious way to get this wrong is `startswith`."""
        result = _call(guard, headers=[(b"authorization", f"Bearer {TOKEN[:10]}".encode())])

        assert result.status == 401

    def test_the_refusal_says_how_to_authenticate(self, guard: ServerTokenGuard) -> None:
        result = _call(guard)

        body = b"".join(
            bytes(m.get("body") or b"")
            for m in result.messages
            if m["type"] == "http.response.body"
        )
        assert b"token=" in body
        assert b"Bearer" in body
        # And does not leak the secret to somebody who did not have it.
        assert TOKEN.encode() not in body

    def test_the_refusal_names_the_scheme_in_a_header(self, guard: ServerTokenGuard) -> None:
        result = _call(guard)

        headers = {
            bytes(k).lower(): bytes(v)
            for m in result.messages
            if m["type"] == "http.response.start"
            for k, v in m["headers"]
        }
        assert headers[b"www-authenticate"] == b"Bearer"

    def test_an_unauthenticated_websocket_is_closed_not_answered(
        self, guard: ServerTokenGuard
    ) -> None:
        """The channel every conversion travels on is guarded too.

        And it is refused in the WebSocket protocol's own terms: sending an
        HTTP response on a websocket scope is a protocol error, and a guard that
        did it would fail on the server rather than on the attacker.
        """
        result = _call(guard, kind="websocket")

        assert result.types == ["websocket.close"]
        assert result.messages[0]["code"] == 1008


class TestTheGuardAdmitsWhatItShould:
    def test_a_bearer_token_is_accepted(self, guard: ServerTokenGuard) -> None:
        result = _call(guard, headers=[(b"authorization", f"Bearer {TOKEN}".encode())])

        assert result.status == 200

    def test_the_bare_header_is_accepted(self, guard: ServerTokenGuard) -> None:
        result = _call(guard, headers=[(b"x-tokenmill-token", TOKEN.encode())])

        assert result.status == 200

    def test_a_cookie_is_accepted(self, guard: ServerTokenGuard) -> None:
        result = _call(guard, headers=[(b"cookie", f"{COOKIE_NAME}={TOKEN}".encode())])

        assert result.status == 200

    def test_a_websocket_with_the_cookie_is_accepted(self, guard: ServerTokenGuard) -> None:
        result = _call(
            guard, kind="websocket", headers=[(b"cookie", f"{COOKIE_NAME}={TOKEN}".encode())]
        )

        assert result.types == ["websocket.accept"]

    def test_the_query_string_is_accepted_and_sets_the_cookie(
        self, guard: ServerTokenGuard
    ) -> None:
        """This is the whole usability story, so it is asserted end to end.

        A browser cannot be told to send a header, so the token arrives in the
        URL once and becomes a cookie. Without the cookie every stylesheet and
        the WebSocket upgrade would be refused and the interface would load as
        a blank page — which is exactly the class of bug Phase 8 shipped and a
        screenshot caught.
        """
        result = _call(guard, query=f"{QUERY_PARAM}={TOKEN}".encode())

        assert result.status == 200
        assert len(result.set_cookies) == 1
        cookie = result.set_cookies[0]
        assert cookie.startswith(f"{COOKIE_NAME}={TOKEN};")
        assert "HttpOnly" in cookie
        assert "SameSite=Lax" in cookie

    def test_no_cookie_is_set_when_the_token_came_from_a_header(
        self, guard: ServerTokenGuard
    ) -> None:
        """A scripted caller has no use for a cookie and should not be given one."""
        result = _call(guard, headers=[(b"authorization", f"Bearer {TOKEN}".encode())])

        assert result.set_cookies == []

    def test_the_cookie_is_not_marked_secure(self, guard: ServerTokenGuard) -> None:
        """Deliberate, and worth a test so nobody 'fixes' it.

        There is no TLS here. A `Secure` cookie is discarded by the browser over
        plain HTTP, so setting it would silently break every request after the
        first — the appearance of security costing the actual feature.
        """
        result = _call(guard, query=f"{QUERY_PARAM}={TOKEN}".encode())

        assert "Secure" not in result.set_cookies[0]

    def test_lifespan_passes_through(self, guard: ServerTokenGuard) -> None:
        """Start-up is not a request. Refusing it would break the server."""
        del guard
        seen: list[str] = []

        async def lifespan_app(scope: Mapping[str, Any], receive: Any, send: Any) -> None:
            del receive, send
            seen.append(str(scope["type"]))

        asyncio.run(
            ServerTokenGuard(lifespan_app, TOKEN)({"type": "lifespan"}, _receive, _Capture())
        )

        assert seen == ["lifespan"]


class TestTheGuardCannotBeBuiltOpen:
    def test_an_empty_token_is_refused(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ServerTokenGuard(_ok_app, "")
