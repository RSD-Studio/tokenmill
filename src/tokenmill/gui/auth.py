"""The shared token that guards ``tokenmill gui --server``.

**Read this first, because the name "authentication" promises more than this
delivers.** What is here stops a machine on the same network opening your
tokenmill instance, converting files with it and reading the results. That is
the actual exposure defect N15 recorded, and this closes it.

It is **not**:

* **TLS.** There is no encryption. The token, the documents you convert and the
  Markdown that comes back all cross the network in clear text, and anybody who
  can see the traffic can take the token and use it. Put an HTTPS reverse proxy
  in front of it, or use an SSH tunnel, if the network is not one you trust with
  the documents themselves.
* **User accounts.** One token, shared by everyone who has it. There is no
  identity, so there is nothing to attribute an action to and nothing to revoke
  for one person.
* **An audit trail.** Nothing records who converted what.
* **A rate limit.** A caller with the token can queue as much work as it likes.

**The secure path is the default path.** When no token is configured, one is
generated and printed at start-up with the URL to open. There is no way to run
``--server`` without a token, because "it warns you" is what Phase 8 shipped and
it is not the same thing as being safe.

**How a token is presented**, in the order they are checked:

1. ``Authorization: Bearer <token>`` — for scripts and reverse proxies.
2. ``X-Tokenmill-Token: <token>`` — the same thing where an ``Authorization``
   header is already spoken for.
3. A ``tokenmill_server_token`` cookie — how a browser carries it after the
   first page load, and the only mechanism that works for the WebSocket the
   interface runs on.
4. ``?token=<token>`` in the query string — how the token gets *into* the
   browser at all. A browser typing a URL cannot set a header, so the printed
   URL carries the token and the response sets the cookie.

The query-string route has a real cost and it is stated rather than hidden: the
token lands in browser history, and in the access log of any proxy in between.
That is the price of a URL somebody can paste, and with no TLS it is not the
weakest link.

Comparison is :func:`hmac.compare_digest`, so a caller cannot learn the token a
character at a time from response timing. That is cheap and it is the one attack
a shared-secret check invites.
"""

from __future__ import annotations

import hmac
import logging
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any, Final
from urllib.parse import parse_qs

__all__ = [
    "COOKIE_NAME",
    "QUERY_PARAM",
    "SERVER_TOKEN_ENV",
    "ServerToken",
    "ServerTokenGuard",
    "resolve_server_token",
]

_log = logging.getLogger(__name__)

#: Environment variable holding a token chosen by the operator.
#:
#: This is the *name* of a variable, not a secret. Bandit's S105 heuristic sees
#: "TOKEN" in an assigned string and cannot tell the difference.
SERVER_TOKEN_ENV: Final = "TOKENMILL_SERVER_TOKEN"  # noqa: S105 - a variable name

#: Cookie the guard sets once a token has been presented in the query string.
COOKIE_NAME: Final = "tokenmill_server_token"

#: Query-string key that carries the token on a first page load.
QUERY_PARAM: Final = "token"

#: Header holding a bare token, for callers whose ``Authorization`` header is
#: already spoken for by something in front of us.
_TOKEN_HEADER: Final = b"x-tokenmill-token"

#: Bytes of randomness in a generated token. 32 bytes is 256 bits, rendered as
#: 43 URL-safe characters — long enough that guessing is not a strategy and
#: short enough to paste.
_GENERATED_BYTES: Final = 32

#: The shortest token this will accept from an operator. Not a strength
#: estimate: it is a guard against `--token ""` or a shell variable that
#: expanded to nothing, which would otherwise disable the check silently.
_MINIMUM_LENGTH: Final = 8

#: What an unauthenticated caller gets. Deliberately says how to authenticate,
#: because the common case is a person who has the token and did not paste the
#: whole URL — not an attacker, who learns nothing from this that the existence
#: of a 401 did not already tell them.
_DENIED_BODY: Final = (
    b"<!doctype html><meta charset=utf-8><title>tokenmill</title>"
    b"<h1>401 Unauthorized</h1>"
    b"<p>This tokenmill instance is running with <code>--server</code> and "
    b"requires the shared token it printed at start-up.</p>"
    b"<p>Open the URL it printed, which looks like "
    b"<code>http://host:8080/?token=&hellip;</code>, or send the token as "
    b"<code>Authorization: Bearer &hellip;</code>.</p>"
)


@dataclass(frozen=True, slots=True)
class ServerToken:
    """The token this instance will accept, and where it came from.

    Attributes:
        value: The secret itself.
        origin: How it was obtained — ``"--token"``, ``"$TOKENMILL_SERVER_TOKEN"``,
            ``"config file"`` or ``"generated"``. Printed at start-up so an
            operator who is surprised by the value knows where to change it.
    """

    value: str
    origin: str

    @property
    def generated(self) -> bool:
        """Whether this token was made up here rather than configured.

        Returns:
            True when it was generated, which is when it has to be printed —
            nobody else knows it.
        """
        return self.origin == "generated"


def resolve_server_token(
    explicit: str | None = None,
    *,
    configured: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ServerToken:
    """Decide which token this instance accepts.

    The layering matches :mod:`tokenmill.core.config`: an explicit flag beats
    the environment, which beats the config file. Where none of the three
    supplies one, a fresh token is generated — there is no fourth option in
    which the check is skipped.

    Args:
        explicit: A token given on the command line.
        configured: A token from the config file.
        environ: The environment to read; the real one when omitted.

    Returns:
        The token and its origin.

    Raises:
        ValueError: If a supplied token is shorter than eight characters, which
            catches an empty shell variable rather than accepting it and
            leaving the instance effectively open.
    """
    import os

    env = environ if environ is not None else os.environ
    candidates = (
        (explicit, "--token"),
        (env.get(SERVER_TOKEN_ENV), f"${SERVER_TOKEN_ENV}"),
        (configured, "config file"),
    )
    for raw, origin in candidates:
        if raw is None:
            continue
        value = raw.strip()
        if len(value) < _MINIMUM_LENGTH:
            msg = (
                f"the server token from {origin} is {len(value)} characters; "
                f"at least {_MINIMUM_LENGTH} are required. An empty or missing "
                f"value here would leave --server open to the network, so it is "
                f"refused rather than accepted"
            )
            raise ValueError(msg)
        return ServerToken(value=value, origin=origin)
    return ServerToken(value=secrets.token_urlsafe(_GENERATED_BYTES), origin="generated")


class ServerTokenGuard:
    """ASGI middleware refusing any request that does not carry the token.

    Written against raw ASGI rather than Starlette's ``BaseHTTPMiddleware`` for
    one reason that matters: the interface runs over a **WebSocket**, and a
    guard that only saw HTTP would leave the channel every conversion actually
    travels on unauthenticated. A raw middleware sees ``http`` and ``websocket``
    scopes alike.

    Attributes:
        app: The application being wrapped.
        token: The secret to compare against.
    """

    def __init__(self, app: Any, token: str) -> None:
        """Wrap an ASGI application.

        Args:
            app: The application to guard.
            token: The token every request must present.

        Raises:
            ValueError: If the token is empty. A guard with an empty secret
                would compare every request against nothing.
        """
        if not token:
            msg = "ServerTokenGuard needs a non-empty token"
            raise ValueError(msg)
        self.app = app
        self.token = token

    async def __call__(
        self,
        scope: Mapping[str, Any],
        receive: Callable[[], Awaitable[Mapping[str, Any]]],
        send: Callable[[Mapping[str, Any]], Awaitable[None]],
    ) -> None:
        """Check the token, then pass the request on or refuse it.

        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        kind = scope.get("type")
        if kind not in {"http", "websocket"}:
            # `lifespan`, and anything a future ASGI version adds. Not a
            # request, so there is nothing to authenticate and refusing it
            # would break start-up.
            await self.app(scope, receive, send)
            return

        presented, from_query = self._presented(scope)
        if presented is None or not hmac.compare_digest(presented, self.token):
            _log.warning(
                "refused an unauthenticated %s request to %s from %s",
                kind,
                scope.get("path", "?"),
                (scope.get("client") or ("?",))[0],
            )
            await self._refuse(kind, send)
            return

        if from_query and kind == "http":
            await self.app(scope, receive, self._sets_cookie(send))
            return
        await self.app(scope, receive, send)

    def _presented(self, scope: Mapping[str, Any]) -> tuple[str | None, bool]:
        """Extract the token a caller offered, wherever it put it.

        Args:
            scope: The ASGI connection scope.

        Returns:
            The token, and whether it arrived in the query string — which is
            what decides whether the response should set a cookie.
        """
        headers: dict[bytes, bytes] = {}
        for key, value in scope.get("headers") or ():
            # Last-wins, matching how a server would fold repeats. Only
            # single-valued headers are read here.
            headers[bytes(key).lower()] = bytes(value)

        authorization = headers.get(b"authorization", b"").decode("latin-1")
        scheme, _, rest = authorization.partition(" ")
        if scheme.lower() == "bearer" and rest.strip():
            return rest.strip(), False

        direct = headers.get(_TOKEN_HEADER, b"").decode("latin-1").strip()
        if direct:
            return direct, False

        cookies = SimpleCookie()
        cookies.load(headers.get(b"cookie", b"").decode("latin-1"))
        morsel = cookies.get(COOKIE_NAME)
        if morsel is not None and morsel.value:
            return morsel.value, False

        query = parse_qs(bytes(scope.get("query_string") or b"").decode("latin-1"))
        values = query.get(QUERY_PARAM) or []
        if values and values[0]:
            return values[0], True

        return None, False

    def _sets_cookie(
        self, send: Callable[[Mapping[str, Any]], Awaitable[None]]
    ) -> Callable[[Mapping[str, Any]], Awaitable[None]]:
        """Wrap ``send`` so the response carries the token as a cookie.

        Without this the token would have to be in the query string of every
        subsequent request — every stylesheet, every WebSocket upgrade — which
        is both impossible for the browser to arrange and worse if it were.

        ``HttpOnly`` so page scripts cannot read it back out; ``SameSite=Lax``
        so another site cannot make an authenticated request on the user's
        behalf, which is this instance's CSRF answer. **Not** ``Secure``,
        because there is no TLS to attach it to and a ``Secure`` cookie over
        plain HTTP is simply discarded.

        Args:
            send: The original send channel.

        Returns:
            A send channel that adds the cookie to the response start.
        """

        async def wrapped(message: Mapping[str, Any]) -> None:
            if message.get("type") != "http.response.start":
                await send(message)
                return
            cookie = (f"{COOKIE_NAME}={self.token}; Path=/; HttpOnly; SameSite=Lax").encode(
                "latin-1"
            )
            headers = [*(message.get("headers") or ()), (b"set-cookie", cookie)]
            await send({**message, "headers": headers})

        return wrapped

    @staticmethod
    async def _refuse(kind: str, send: Callable[[Mapping[str, Any]], Awaitable[None]]) -> None:
        """Turn the caller away.

        Args:
            kind: ``"http"`` or ``"websocket"``.
            send: The ASGI send channel.
        """
        if kind == "websocket":
            # An unaccepted WebSocket must be closed, not answered: sending an
            # HTTP response on a websocket scope is a protocol error and some
            # servers raise on it.
            await send({"type": "websocket.close", "code": 1008})
            return
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", str(len(_DENIED_BODY)).encode("ascii")),
                    # Names the scheme a caller should use, which is what a 401
                    # is required to do. No realm: there is no user to prompt
                    # for, and a browser popping a basic-auth dialog here would
                    # ask for a username that does not exist.
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _DENIED_BODY})
