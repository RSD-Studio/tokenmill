"""The URL fetcher, against a real HTTP server on loopback.

Every assertion here is made against real sockets, real headers and real
redirect handling — see ``tests/web_server.py`` for why a mock would have
tested the mock rather than the fetcher.
"""

from __future__ import annotations

import pytest

from tests.web_server import Route, serve
from tokenmill.backends.web.fetch import (
    DEFAULT_USER_AGENT,
    fetch_url,
    format_for_media_type,
    user_agent_for,
)
from tokenmill.core.errors import BackendFailed, CorruptSource, NetworkRequired, Timeout
from tokenmill.core.models import ConvertOptions, SourceKind

PAGE = b"<html><body><h1>Title</h1><p>Body text.</p></body></html>"

#: robots.txt is consulted before every fetch, so most tests serve one that
#: allows everything. Tests about robots serve something else on purpose.
ALLOW_ALL = Route(body=b"User-agent: *\nAllow: /\n", content_type="text/plain")

OPTS = ConvertOptions(tokenizer="bytes")


@pytest.fixture(autouse=True)
def _no_proxy_for_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep loopback requests off any proxy the environment configures.

    Development sandboxes and CI runners both set ``HTTP(S)_PROXY``. A test
    server on 127.0.0.1 must be reached directly, or these tests measure the
    proxy's behaviour instead of ours.
    """
    monkeypatch.setenv("no_proxy", "*")
    monkeypatch.setenv("NO_PROXY", "*")


class TestASuccessfulFetch:
    def test_it_returns_the_body_as_a_readable_source(self) -> None:
        with serve({"/": Route(body=PAGE), "/robots.txt": ALLOW_ALL}) as site:
            result = fetch_url(site.url("/"), OPTS)

        assert result.source.read_bytes() == PAGE
        assert result.status == 200
        assert result.byte_count == len(PAGE)

    def test_the_fetched_source_has_readable_bytes_so_it_can_be_measured(self) -> None:
        """The reason the pipeline fetches rather than letting a backend do it.

        An unfetched URL source has no before-count. A fetched one does, and
        that is what makes "this page got smaller" a measurement.
        """
        with serve({"/": Route(body=PAGE), "/robots.txt": ALLOW_ALL}) as site:
            result = fetch_url(site.url("/"), OPTS)

        assert result.source.kind is SourceKind.BYTES
        assert result.source.read_text() == PAGE.decode()

    def test_the_url_survives_as_the_display_name_and_the_provenance(self) -> None:
        with serve({"/page": Route(body=PAGE), "/robots.txt": ALLOW_ALL}) as site:
            url = site.url("/page")
            result = fetch_url(url, OPTS)

        assert result.source.name == url
        assert result.source.url == url

    def test_it_identifies_itself_by_name_and_version(self) -> None:
        """An agent that hides behind a browser string cannot be asked to stop."""
        with serve({"/": Route(body=PAGE), "/robots.txt": ALLOW_ALL}) as site:
            fetch_url(site.url("/"), OPTS)
            agents = list(site.user_agents)

        assert agents
        assert all(agent == DEFAULT_USER_AGENT for agent in agents)
        assert "tokenmill/" in DEFAULT_USER_AGENT
        assert "github.com/RSD-Studio/tokenmill" in DEFAULT_USER_AGENT

    def test_a_user_agent_override_is_sent_instead(self) -> None:
        with serve({"/": Route(body=PAGE), "/robots.txt": ALLOW_ALL}) as site:
            fetch_url(site.url("/"), OPTS.with_(user_agent="acme-crawler/1.0"))
            agents = list(site.user_agents)

        assert agents == ["acme-crawler/1.0", "acme-crawler/1.0"]

    def test_the_user_agent_helper_prefers_the_override(self) -> None:
        assert user_agent_for(OPTS) == DEFAULT_USER_AGENT
        assert user_agent_for(OPTS.with_(user_agent="x")) == "x"


class TestFormatDetection:
    def test_the_content_type_decides_the_format(self) -> None:
        """A URL frequently carries no usable extension at all."""
        with serve(
            {
                "/blog/post": Route(body=PAGE, content_type="text/html; charset=utf-8"),
                "/robots.txt": ALLOW_ALL,
            }
        ) as site:
            result = fetch_url(site.url("/blog/post"), OPTS)

        assert result.source.format == "html"
        assert result.media_type == "text/html"

    def test_a_pdf_url_becomes_a_pdf_source_so_the_pdf_backends_claim_it(self) -> None:
        with serve(
            {
                "/paper": Route(body=b"%PDF-1.4\n", content_type="application/pdf"),
                "/robots.txt": ALLOW_ALL,
            }
        ) as site:
            result = fetch_url(site.url("/paper"), OPTS)

        assert result.source.format == "pdf"

    def test_an_unknown_media_type_falls_back_to_the_url_extension(self) -> None:
        assert format_for_media_type("application/octet-stream", "http://h/a/b.csv") == "csv"

    def test_an_unlabelled_response_with_no_extension_is_assumed_to_be_html(self) -> None:
        assert format_for_media_type(None, "http://example.com/about") == "html"

    def test_a_long_path_segment_is_not_mistaken_for_an_extension(self) -> None:
        assert format_for_media_type(None, "http://example.com/a.verylongthing") == "html"


class TestRedirects:
    def test_a_redirect_is_followed_and_the_final_url_is_reported(self) -> None:
        with serve(
            {
                "/a": Route(status=302, location="/b", body=b""),
                "/b": Route(body=PAGE),
                "/robots.txt": ALLOW_ALL,
            }
        ) as site:
            result = fetch_url(site.url("/a"), OPTS)

        assert result.source.read_bytes() == PAGE
        assert result.final_url.endswith("/b")
        assert result.redirects == 1

    def test_a_chain_longer_than_the_limit_is_refused(self) -> None:
        routes = {f"/{n}": Route(status=302, location=f"/{n + 1}", body=b"") for n in range(10)}
        routes["/robots.txt"] = ALLOW_ALL
        with serve(routes) as site, pytest.raises(BackendFailed, match="redirect"):
            fetch_url(site.url("/0"), OPTS.with_(max_redirects=2))

    def test_zero_redirects_means_none_are_followed(self) -> None:
        with (
            serve(
                {
                    "/a": Route(status=302, location="/b", body=b""),
                    "/b": Route(body=PAGE),
                    "/robots.txt": ALLOW_ALL,
                }
            ) as site,
            pytest.raises(BackendFailed),
        ):
            fetch_url(site.url("/a"), OPTS.with_(max_redirects=0))


class TestTheSizeCap:
    def test_a_response_over_the_cap_is_refused_rather_than_buffered(self) -> None:
        big = b"x" * 5000
        with (
            serve({"/": Route(body=big), "/robots.txt": ALLOW_ALL}) as site,
            pytest.raises(CorruptSource, match="larger than"),
        ):
            fetch_url(site.url("/"), OPTS.with_(max_bytes=1000))

    def test_a_response_of_exactly_the_cap_is_accepted(self) -> None:
        """Off-by-one on a limit is how a valid input starts being rejected."""
        body = b"y" * 1000
        with serve({"/": Route(body=body), "/robots.txt": ALLOW_ALL}) as site:
            result = fetch_url(site.url("/"), OPTS.with_(max_bytes=1000))

        assert result.byte_count == 1000


class TestRobotsTxt:
    def test_a_disallowed_url_is_refused_with_a_way_forward(self) -> None:
        robots = Route(body=b"User-agent: *\nDisallow: /private\n", content_type="text/plain")
        with (
            serve({"/private/x": Route(body=PAGE), "/robots.txt": robots}) as site,
            pytest.raises(NetworkRequired) as excinfo,
        ):
            fetch_url(site.url("/private/x"), OPTS)

        assert "robots.txt" in excinfo.value.message
        assert excinfo.value.hint is not None
        assert "--ignore-robots" in excinfo.value.hint

    def test_the_page_itself_is_never_requested_when_robots_disallows_it(self) -> None:
        """A refusal that still fetched the page would be theatre."""
        robots = Route(body=b"User-agent: *\nDisallow: /\n", content_type="text/plain")
        with serve({"/x": Route(body=PAGE), "/robots.txt": robots}) as site:
            with pytest.raises(NetworkRequired):
                fetch_url(site.url("/x"), OPTS)
            requested = list(site.requests)

        assert requested == ["/robots.txt"]

    def test_ignoring_robots_fetches_the_page_anyway(self) -> None:
        robots = Route(body=b"User-agent: *\nDisallow: /\n", content_type="text/plain")
        with serve({"/x": Route(body=PAGE), "/robots.txt": robots}) as site:
            result = fetch_url(site.url("/x"), OPTS.with_(respect_robots=False))

        assert result.source.read_bytes() == PAGE

    def test_ignoring_robots_does_not_even_request_the_file(self) -> None:
        robots = Route(body=b"User-agent: *\nDisallow: /\n", content_type="text/plain")
        with serve({"/x": Route(body=PAGE), "/robots.txt": robots}) as site:
            fetch_url(site.url("/x"), OPTS.with_(respect_robots=False))
            requested = list(site.requests)

        assert requested == ["/x"]

    def test_a_missing_robots_file_allows_the_fetch(self) -> None:
        """A site that serves no robots.txt has expressed no preference."""
        with serve({"/x": Route(body=PAGE)}) as site:
            result = fetch_url(site.url("/x"), OPTS)

        assert result.source.read_bytes() == PAGE

    def test_a_rule_naming_our_agent_specifically_is_obeyed(self) -> None:
        robots = Route(
            body=b"User-agent: tokenmill\nDisallow: /\n\nUser-agent: *\nAllow: /\n",
            content_type="text/plain",
        )
        with (
            serve({"/x": Route(body=PAGE), "/robots.txt": robots}) as site,
            pytest.raises(NetworkRequired),
        ):
            fetch_url(site.url("/x"), OPTS.with_(user_agent="tokenmill"))


class TestFailures:
    def test_an_error_status_is_reported_as_the_status_it_was(self) -> None:
        with (
            serve({"/robots.txt": ALLOW_ALL}) as site,
            pytest.raises(BackendFailed, match="HTTP 404"),
        ):
            fetch_url(site.url("/missing"), OPTS)

    def test_a_server_error_is_reported_too(self) -> None:
        routes = {"/x": Route(status=500, body=b"nope"), "/robots.txt": ALLOW_ALL}
        with serve(routes) as site, pytest.raises(BackendFailed, match="HTTP 500"):
            fetch_url(site.url("/x"), OPTS)

    def test_a_slow_response_times_out(self) -> None:
        with (
            serve({"/slow": Route(body=PAGE, delay_s=2.0), "/robots.txt": ALLOW_ALL}) as site,
            pytest.raises(Timeout),
        ):
            fetch_url(site.url("/slow"), OPTS.with_(timeout_s=0.25))

    def test_an_unreachable_host_is_a_message_rather_than_a_traceback(self) -> None:
        with serve({"/robots.txt": ALLOW_ALL}) as site:
            port = int(site.base_url.rsplit(":", 1)[1])
        # The server is closed now, so nothing is listening on that port.
        with pytest.raises(BackendFailed, match="could not fetch"):
            fetch_url(f"http://127.0.0.1:{port}/x", OPTS.with_(respect_robots=False))


class TestFetchingCanBeSwitchedOff:
    def test_offline_refuses_before_opening_a_socket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``--offline`` must refuse, not fetch and then discard."""
        import socket

        def refuse(*_args: object, **_kwargs: object) -> object:
            msg = "fetch=False must not open a socket"
            raise AssertionError(msg)

        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)

        with pytest.raises(NetworkRequired, match="disabled"):
            fetch_url("http://127.0.0.1:1/x", OPTS.with_(fetch=False))


class TestCharsets:
    def test_a_non_utf8_page_is_transcoded_and_the_change_is_reported(self) -> None:
        body = "Café Münster".encode("latin-1")
        with serve(
            {
                "/x": Route(body=body, content_type="text/html; charset=iso-8859-1"),
                "/robots.txt": ALLOW_ALL,
            }
        ) as site:
            result = fetch_url(site.url("/x"), OPTS)

        assert result.source.read_bytes().decode("utf-8") == "Café Münster"
        assert result.declared_charset == "iso-8859-1"
        assert any("re-encoded to UTF-8" in w for w in result.warnings)

    def test_an_unknown_charset_label_keeps_the_bytes_rather_than_failing(self) -> None:
        with serve(
            {
                "/x": Route(body=PAGE, content_type="text/html; charset=not-a-real-charset"),
                "/robots.txt": ALLOW_ALL,
            }
        ) as site:
            result = fetch_url(site.url("/x"), OPTS)

        assert result.source.read_bytes() == PAGE
        assert result.warnings == ()
