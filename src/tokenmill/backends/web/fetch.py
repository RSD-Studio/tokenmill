"""Retrieving a page, once, under one policy.

Every web backend needs the same thing from the network and needs it to behave
the same way, so none of them does it. The pipeline calls :func:`fetch_url`
before a URL source reaches a converter, and hands the converters bytes.

That arrangement buys three things worth having:

* **One policy point.** The user agent, the timeout, the redirect limit, the
  size cap and ``robots.txt`` are decided here and nowhere else, so trafilatura
  and readability cannot end up obeying different rules.
* **A real before-count.** The raw HTML becomes a
  :class:`~tokenmill.core.models.Source` with readable bytes, so the pipeline
  measures it as the ``source`` stage. That is what makes "12,481 bytes of HTML
  became 2,859 bytes of Markdown" a measurement rather than an assertion — a
  backend that fetched privately would leave nothing to compare against.
* **The offline guarantee in one place.** Converting a local file never calls
  this module at all, so there is exactly one function that can open a socket
  and a test can prove the rest never do.

**Nothing here is a general-purpose HTTP client.** It is the standard library's
:mod:`urllib.request`, chosen so the core install gains no dependency for it,
wrapped in the smallest amount of policy that makes an unattended fetch safe:
a bounded read, a bounded redirect chain, an explicit identity, and a refusal to
follow a redirect out of ``http(s)``.

**On ``robots.txt``.** It is consulted by default and a disallow is a refusal,
not a warning. A tool that fetches pages on a user's behalf and ignores the
site's stated preference is a tool that gets its user's address blocked.
``--ignore-robots`` exists because a user fetching their own site has every
right to, but they have to say so.
"""

from __future__ import annotations

import email.message
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from http.client import HTTPResponse
from typing import ClassVar, Final

from tokenmill import __version__
from tokenmill.core.errors import (
    BackendFailed,
    CorruptSource,
    NetworkRequired,
    Timeout,
)
from tokenmill.core.models import ConvertOptions, Source

__all__ = [
    "DEFAULT_USER_AGENT",
    "FetchResult",
    "fetch_url",
    "format_for_media_type",
    "user_agent_for",
]

_log = logging.getLogger(__name__)

#: How tokenmill identifies itself. A real name and a real address: a server
#: operator who wants to block us, rate-limit us or get in touch can, and an
#: agent that hides behind a browser string is an agent that cannot be asked to
#: stop.
DEFAULT_USER_AGENT: Final = f"tokenmill/{__version__} (+https://github.com/RSD-Studio/tokenmill)"

#: Media types we know how to name as a tokenmill format. A response whose type
#: is absent from this map keeps whatever the URL's own extension suggested,
#: which is how an unusual but correctly-named file still finds its backend.
_MEDIA_TYPE_FORMATS: Final[dict[str, str]] = {
    "text/html": "html",
    "application/xhtml+xml": "xhtml",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/csv": "csv",
    "text/tab-separated-values": "tsv",
    "application/pdf": "pdf",
    "application/json": "json",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/rtf": "rtf",
    "text/rtf": "rtf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}

#: Read this much at a time. Small enough that the size cap stops a hostile
#: response early rather than after it has been buffered.
_CHUNK: Final = 64 * 1024


@dataclass(frozen=True, slots=True)
class FetchResult:
    """What one successful retrieval produced.

    Attributes:
        source: The fetched content, ready to convert and to measure.
        final_url: Where the response actually came from, after redirects.
        status: The HTTP status code.
        media_type: The response's media type, parameters stripped.
        declared_charset: The charset the server named, if any. Recorded
            because :attr:`source` has been transcoded to UTF-8 and the
            original encoding is otherwise lost.
        byte_count: How many bytes were received.
        redirects: How many redirects were followed.
        warnings: Non-fatal observations for the user.
    """

    source: Source
    final_url: str
    status: int
    media_type: str | None
    declared_charset: str | None
    byte_count: int
    redirects: int
    warnings: tuple[str, ...] = ()


def user_agent_for(options: ConvertOptions) -> str:
    """Return the ``User-Agent`` this run should send.

    Args:
        options: Supplies an override, if the user set one.

    Returns:
        The user agent string.
    """
    return options.user_agent or DEFAULT_USER_AGENT


def format_for_media_type(media_type: str | None, url: str) -> str:
    """Decide which tokenmill format a fetched response should be matched as.

    The response's own ``Content-Type`` is trusted ahead of the URL, because a
    URL frequently carries no usable extension at all —
    ``https://example.com/blog/post`` is an HTML page whose path ends in
    ``post`` — and because a server describing its own bytes is better evidence
    than a path.

    Args:
        media_type: The response media type, parameters already stripped.
        url: The address, used as the fallback when the media type is unknown.

    Returns:
        A format token such as ``html`` or ``pdf``. Falls back to the URL
        path's extension, and finally to ``html``, which is what the
        overwhelming majority of unlabelled web responses are.
    """
    if media_type is not None:
        known = _MEDIA_TYPE_FORMATS.get(media_type.lower())
        if known is not None:
            return known

    path = urllib.parse.urlsplit(url).path
    _, _, tail = path.rpartition("/")
    _, dot, extension = tail.rpartition(".")
    if dot and extension and extension.isalnum() and len(extension) <= 5:
        return extension.lower()
    return "html"


class _BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follows redirects up to a limit, and never out of ``http(s)``.

    urllib's own handler already caps the chain, but at its number rather than
    ours, and it will happily follow a redirect to any scheme its openers know.
    Both are worth taking control of: an unbounded chain is a denial of service
    and a scheme change is how a fetch turns into reading a local file.
    """

    #: urllib caps the chain at ten of its own accord, which would quietly
    #: override a larger ``--max-redirects``. The ceiling is raised here and the
    #: real limit is enforced per instance below, so the number the user asked
    #: for is the number that applies.
    max_redirections: ClassVar[int] = 64

    def __init__(self, limit: int) -> None:
        """Initialise the handler.

        Args:
            limit: The most redirects to follow.
        """
        self.limit = min(max(0, limit), self.max_redirections)
        self.followed = 0

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: email.message.Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Build the follow-up request for a redirect, or refuse it.

        Args:
            req: The request that was redirected.
            fp: The response body, unused.
            code: The redirect status code.
            msg: The status message.
            headers: The response headers.
            newurl: Where the server is pointing us.

        Returns:
            The next request, or ``None`` to stop following.

        Raises:
            urllib.error.HTTPError: If the redirect leaves ``http(s)``, or if
                the chain is longer than the limit.
        """
        scheme = urllib.parse.urlsplit(newurl).scheme.lower()
        if scheme not in {"http", "https"}:
            raise urllib.error.HTTPError(
                newurl, code, f"refusing to follow a redirect to {scheme!r}", headers, None
            )
        self.followed += 1
        if self.followed > self.limit:
            raise urllib.error.HTTPError(
                newurl, code, f"more than {self.limit} redirects", headers, None
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)  # type: ignore[arg-type]


def fetch_url(url: str, options: ConvertOptions) -> FetchResult:
    """Retrieve a URL under tokenmill's fetch policy.

    Args:
        url: The ``http`` or ``https`` address to retrieve.
        options: Supplies the fetch permission, the robots policy, the user
            agent, the redirect limit, the timeout and the size cap.

    Returns:
        The fetched content and everything worth recording about the retrieval.

    Raises:
        NetworkRequired: If fetching is switched off, or ``robots.txt``
            disallows this URL for our user agent.
        Timeout: If the request exceeds ``options.timeout_s``.
        CorruptSource: If the response is larger than ``options.max_bytes``.
        BackendFailed: If the server answers with an error status, or the
            connection fails.
    """
    if not options.fetch:
        raise NetworkRequired(
            f"fetching {url} is disabled",
            hint="drop --offline to let tokenmill retrieve the address you gave it",
        )

    agent = user_agent_for(options)
    warnings: list[str] = []

    if options.respect_robots:
        _enforce_robots(url, agent, options)

    request = urllib.request.Request(  # noqa: S310 - the scheme is checked below
        url,
        headers={
            "User-Agent": agent,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "identity",
        },
    )
    if request.type not in {"http", "https"}:
        msg = f"unsupported URL scheme: {url!r} (expected http:// or https://)"
        raise BackendFailed(msg)

    redirects = _BoundedRedirectHandler(options.max_redirects)
    opener = urllib.request.build_opener(redirects)

    try:
        with opener.open(request, timeout=options.timeout_s) as response:
            data, truncated = _read_capped(response, options.max_bytes)
            status = int(response.status)
            final_url = str(response.geturl())
            media_type, charset = _content_type(response)
    except urllib.error.HTTPError as exc:
        raise BackendFailed(
            f"fetching {url} returned HTTP {exc.code} {exc.reason}",
            hint="check the address, and that the page is reachable without signing in",
        ) from exc
    except TimeoutError as exc:
        raise Timeout(
            f"fetching {url} took longer than {options.timeout_s:g}s",
            hint="raise --timeout, or the site may simply be slow",
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        # socket.timeout is an alias of TimeoutError on 3.10+, so the branch
        # above catches it; everything else here is a genuine connection
        # failure, including a proxy refusing the CONNECT.
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.timeout):  # pragma: no cover - platform dependent
            raise Timeout(f"fetching {url} timed out", hint="raise --timeout") from exc
        raise BackendFailed(
            f"could not fetch {url}: {type(exc).__name__}: {reason}",
            hint="check the address, your network, and any proxy your environment sets",
        ) from exc

    if truncated:
        raise CorruptSource(
            f"{url} is larger than the {options.max_bytes}-byte limit",
            hint="raise --max-bytes if the page is genuinely meant to be this large",
        )

    body, transcoded_from = _as_utf8(data, charset)
    if transcoded_from is not None:
        warnings.append(
            f"{url} was served as {transcoded_from} and has been re-encoded to UTF-8; "
            f"character counts are of the UTF-8 form"
        )
    if final_url != url:
        _log.debug("fetch of %s ended at %s", url, final_url)

    source = Source.from_fetched(
        url,
        body,
        media_type=media_type,
        format_hint=format_for_media_type(media_type, final_url),
    )
    return FetchResult(
        source=source,
        final_url=final_url,
        status=status,
        media_type=media_type,
        declared_charset=charset,
        byte_count=len(data),
        redirects=redirects.followed,
        warnings=tuple(warnings),
    )


def _enforce_robots(url: str, agent: str, options: ConvertOptions) -> None:
    """Refuse the fetch when the origin's ``robots.txt`` disallows it.

    An unreachable or unparseable ``robots.txt`` allows the fetch, which is the
    long-standing convention: a site that cannot serve the file has not
    expressed a preference, and treating silence as a prohibition would make
    tokenmill unusable against most of the web.

    Args:
        url: The address about to be fetched.
        agent: The user agent the rules are evaluated against.
        options: Supplies the timeout.

    Raises:
        NetworkRequired: If the rules disallow this URL for this agent.
    """
    parts = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)

    request = urllib.request.Request(  # noqa: S310 - scheme comes from a validated URL
        robots_url, headers={"User-Agent": agent}
    )
    try:
        with urllib.request.urlopen(request, timeout=options.timeout_s) as response:  # noqa: S310
            raw = response.read(_CHUNK).decode("utf-8", errors="replace")
    except Exception as exc:
        # Every failure mode is the same answer: no stated preference.
        _log.debug("robots.txt for %s unavailable (%s); allowing", parts.netloc, exc)
        return

    parser.parse(raw.splitlines())
    if not parser.can_fetch(agent, url):
        raise NetworkRequired(
            f"{parts.netloc}'s robots.txt disallows {url} for {agent!r}",
            hint=(
                "pass --ignore-robots to fetch it anyway, which is yours to decide "
                "for a site you control"
            ),
        )


def _read_capped(response: HTTPResponse, limit: int) -> tuple[bytes, bool]:
    """Read a response body, stopping one byte past the limit.

    Reading to the cap **plus one** is what makes the cap detectable: a body of
    exactly ``limit`` bytes is fine, and anything longer is known to be longer
    without buffering all of it.

    Args:
        response: The open response.
        limit: The most bytes to accept.

    Returns:
        The body, and whether it exceeded the limit.
    """
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        chunk = response.read(min(_CHUNK, limit - total + 1))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks), total > limit


def _content_type(response: HTTPResponse) -> tuple[str | None, str | None]:
    """Split a response's ``Content-Type`` into a media type and a charset.

    Args:
        response: The open response.

    Returns:
        The lowercase media type and the declared charset, either of which may
        be ``None``.
    """
    header = response.headers.get("Content-Type")
    if not header:
        return None, None
    message = email.message.Message()
    message["Content-Type"] = header
    media_type = message.get_content_type()
    charset = message.get_param("charset")
    return media_type.lower(), str(charset).lower() if charset else None


def _as_utf8(data: bytes, charset: str | None) -> tuple[bytes, str | None]:
    """Return the body as UTF-8, transcoding it if the server declared otherwise.

    The pipeline's before-count decodes the source as strict UTF-8 and treats a
    failure as "this is a binary document with no comparable before". A page
    served as ``windows-1252`` would fall into that branch and silently lose its
    before-count, so it is converted here instead, once, with the original
    encoding recorded.

    Args:
        data: The raw body.
        charset: The charset the server declared, if any.

    Returns:
        The body as UTF-8 bytes, and the encoding it was converted from, or
        ``None`` when no conversion happened.
    """
    if charset is None or charset.replace("_", "-") in {"utf-8", "utf8"}:
        return data, None
    try:
        return data.decode(charset).encode("utf-8"), charset
    except (LookupError, UnicodeDecodeError):
        # An unknown or wrong charset label is common enough that failing the
        # conversion over it would be the wrong call. The bytes are kept as
        # they came and the page is decoded leniently downstream.
        return data, None
