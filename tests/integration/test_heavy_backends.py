"""The GPU tier, and an honest account of what can be tested without a GPU.

**Nothing here converts a document with a heavy backend.** This machine has no
GPU and cannot reach the host the model weights live on, so no Marker, MinerU,
Surya, olmOCR, DeepSeek-OCR or dots.ocr conversion has ever been performed by
this code. `PROGRESS.md` records that as the phase's headline rather than as a
footnote.

What *can* be tested is more than nothing, and it is the part almost every user
will actually experience:

* **The absent-runtime path.** Every adapter reports itself unavailable with the
  exact commands that would install it, and never claims to be available.
* **Argument construction**, against a stub executable that records what it was
  called with. A wrong flag is the failure mode that would waste somebody's
  afternoon after a 5 GB download, and it does not need a GPU to catch.
* **Output reading**, against directories laid out the way each tool lays them
  out.
* **The HTTP path** for the two service backends, end to end against a real
  local server — the same technique `tests/unit/test_service_backend.py` uses,
  because a pattern proved against a mock proves only that the mock matches.
* **The licence tiering**, which is the largest surface in the project and the
  one `docs/research/RESEARCH.md` got wrong twice more in this phase.

The stub executable deserves a note. It is a real script on disk, made
executable, that writes a Markdown file and records its `argv` — not a patched
`subprocess.run`. Patching would test that the adapter calls a function; a real
child process tests that the arguments survive quoting, that the workspace
exists when the tool looks for it, and that the output is found where the tool
put it. Those are the three things that actually break.
"""

from __future__ import annotations

import json
import stat
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from tokenmill.backends.heavy.base import HeavyTier
from tokenmill.backends.heavy.deepseek_ocr import DeepSeekOcrConverter
from tokenmill.backends.heavy.dots_ocr import DotsOcrConverter
from tokenmill.backends.heavy.marker import MarkerConverter
from tokenmill.backends.heavy.mineru import MinerUConverter
from tokenmill.backends.heavy.olmocr import OlmOcrConverter
from tokenmill.backends.heavy.surya import SuryaConverter
from tokenmill.core.errors import BackendFailed, NetworkRequired
from tokenmill.core.models import (
    AvailabilityStatus,
    ConvertOptions,
    IsolationMode,
    LicenseTier,
    Source,
)
from tokenmill.core.protocol import ConversionContext

pytestmark = pytest.mark.integration

#: Every subprocess adapter in the tier.
COMMAND_BACKENDS = [MarkerConverter, SuryaConverter, MinerUConverter, OlmOcrConverter]

#: Every service adapter in the tier.
SERVICE_BACKENDS = [DeepSeekOcrConverter, DotsOcrConverter]

#: All of them.
ALL_BACKENDS = [*COMMAND_BACKENDS, *SERVICE_BACKENDS]

NETWORKED = ConvertOptions(tokenizer="bytes", allow_network=True)


class TestTheAbsentRuntimeCase:
    """What a CPU-only machine sees, which is almost every machine.

    These always run. They are the phase's acceptance criterion — "every heavy
    adapter degrades cleanly to unavailable + how to install on a CPU-only
    machine" — and they are the only part of it this environment can prove.
    """

    @pytest.mark.parametrize("factory", ALL_BACKENDS, ids=lambda f: f.info.id)
    def test_it_is_either_available_or_says_how_to_get_it(self, factory: Any) -> None:
        availability = factory().is_available()

        if availability:
            return
        assert availability.status in {
            AvailabilityStatus.MISSING_BINARY,
            AvailabilityStatus.UNSUPPORTED,
        }
        assert availability.hint, f"{factory.info.id} is unavailable with no instruction"

    @pytest.mark.parametrize("factory", COMMAND_BACKENDS, ids=lambda f: f.info.id)
    def test_the_hint_names_a_virtual_environment_and_a_pip_install(self, factory: Any) -> None:
        """Not "install marker" — the two commands that actually work.

        Every one of these pulls PyTorch, so `pip install` into the user's
        current environment is the wrong advice and would break whatever else
        is in it.
        """
        hint = factory().is_available().hint or ""

        assert "venv" in hint
        assert "pip install" in hint

    @pytest.mark.parametrize("factory", SERVICE_BACKENDS, ids=lambda f: f.info.id)
    def test_a_service_backend_names_the_extra_that_configures_it(self, factory: Any) -> None:
        converter = factory()
        hint = converter.is_available().hint or ""

        assert f"{converter.info.id}_url" in hint

    @pytest.mark.parametrize("factory", ALL_BACKENDS, ids=lambda f: f.info.id)
    def test_it_never_declares_in_process_isolation(self, factory: Any) -> None:
        """`heavy = []` stays empty, and this is the structural half of that."""
        assert factory.info.isolation is not IsolationMode.IN_PROCESS

    @pytest.mark.parametrize("factory", ALL_BACKENDS, ids=lambda f: f.info.id)
    def test_it_declares_that_it_needs_a_gpu(self, factory: Any) -> None:
        assert factory.info.requires_gpu

    @pytest.mark.parametrize("factory", ALL_BACKENDS, ids=lambda f: f.info.id)
    def test_it_ranks_below_every_light_backend(self, factory: Any) -> None:
        """Auto-selection must never reach for a 5 GB download.

        The same rule `core/preferences.py` already applies to docling: a
        backend that would start a multi-gigabyte fetch has to be asked for by
        name.
        """
        assert factory.info.priority <= 1

    @pytest.mark.parametrize("factory", ALL_BACKENDS, ids=lambda f: f.info.id)
    def test_the_weights_licence_is_recorded_as_unverified(self, factory: Any) -> None:
        """Honesty, asserted.

        Not one weights licence in this tier has been read from an artefact,
        because the host they live on is denied at this environment's egress
        proxy. If somebody verifies one, this test tells them to say so here.
        """
        converter = factory()
        assert isinstance(converter, HeavyTier)
        assert converter.weights_licence is None, (
            f"{factory.info.id} now claims a verified weights licence. If that "
            f"was verified against a real model card, record where in "
            f"docs/LICENSES.md and update this test; if it was assumed, remove it"
        )


class TestTheLicenceSurface:
    """The largest licence surface in the project, and RESEARCH.md was wrong twice."""

    def test_marker_is_apache_not_gpl(self) -> None:
        """Read from the wheel's own bundled licence file, not from RESEARCH.md.

        `marker_pdf-2.0.0.dist-info/licenses/LICENSE` is 11,358 bytes of actual
        Apache 2.0 text.

        The plan and RESEARCH.md both say GPL-3.0, which was true of the
        versions they surveyed.
        """
        assert MarkerConverter.info.license == "Apache-2.0"
        assert MarkerConverter.info.license_tier is LicenseTier.PERMISSIVE

    def test_surya_is_apache_not_gpl(self) -> None:
        assert SuryaConverter.info.license == "Apache-2.0"
        assert SuryaConverter.info.license_tier is LicenseTier.PERMISSIVE

    def test_a_permissive_heavy_backend_still_runs_out_of_process(self) -> None:
        """Rule 1, not rule 2, and the distinction is worth keeping visible.

        Marker and Surya could legally be imported. Importing them would put
        PyTorch in tokenmill's dependency tree, which is what actually forbids
        it — the same shape as LibreOffice, which is permissive and out of
        process because it is C++.
        """
        for factory in (MarkerConverter, SuryaConverter):
            assert factory.info.license_tier is LicenseTier.PERMISSIVE
            assert factory.info.isolation is IsolationMode.SUBPROCESS

    def test_mineru_is_restricted_rather_than_permissive(self) -> None:
        """The backend that made a fourth tier necessary."""
        assert MinerUConverter.info.license_tier is LicenseTier.RESTRICTED
        assert "LicenseRef" in MinerUConverter.info.license

    def test_mineru_warns_about_the_obligation_it_puts_on_the_user(self) -> None:
        """Clause 2 binds whoever runs it, and this is the moment to say so.

        `tokenmill gui --server` is an online service. An operator converting
        documents through MinerU behind it owes an attribution notice, and
        tokenmill would otherwise be the reason nobody told them.
        """
        converter = MinerUConverter()
        context = ConversionContext()
        options = ConvertOptions(tokenizer="bytes", allow_network=True)

        with pytest.raises(Exception, match=r"not installed|not available|mineru"):
            converter._convert(  # the warning is attached before the run
                Source.from_text("x", name="a.pdf"), options, context
            )

        notice = next((w for w in context.warnings if "LicenseRef-MinerU" in w), "")
        assert notice, context.warnings
        # The two obligations, and the sentence that makes the first one
        # concrete for a tokenmill user. Asserted on meaning rather than on one
        # keyword, so rewording the notice cannot silently drop a term.
        assert "online service" in notice
        assert "commercial licence" in notice
        assert "--server" in notice


class TestModelDownloadsNeedPermission:
    """A multi-gigabyte fetch inside a command that looked local.

    The same rule the repomix adapter applies to `npx`, for the same reason.
    """

    @pytest.mark.parametrize("factory", COMMAND_BACKENDS, ids=lambda f: f.info.id)
    def test_it_refuses_without_allow_network(self, factory: Any, tmp_path: Path) -> None:
        converter = factory()
        stub = _stub_command(tmp_path, factory.info.id, writes_markdown=True)
        options = ConvertOptions(tokenizer="bytes", extra={f"{factory.info.id}_python": str(stub)})

        with pytest.raises(NetworkRequired, match="weights"):
            converter._convert(Source.from_path(_a_pdf(tmp_path)), options, ConversionContext())

    def test_the_refusal_says_what_to_do(self, tmp_path: Path) -> None:
        converter = MarkerConverter()
        stub = _stub_command(tmp_path, "marker", writes_markdown=True)
        options = ConvertOptions(tokenizer="bytes", extra={"marker_python": str(stub)})

        with pytest.raises(NetworkRequired) as caught:
            converter._convert(Source.from_path(_a_pdf(tmp_path)), options, ConversionContext())

        assert "--allow-network" in (caught.value.hint or "")


@pytest.mark.skipif(sys.platform == "win32", reason="the stub is a POSIX shell script")
class TestTheArgumentsAndTheOutput:
    """Against a real child process, not a patched `subprocess.run`.

    A patched call proves the adapter called a function. A real script proves
    the arguments survived, the workspace existed when the tool looked for it,
    and the output was found where the tool put it — which are the three things
    that break.
    """

    @pytest.mark.parametrize("factory", COMMAND_BACKENDS, ids=lambda f: f.info.id)
    def test_it_passes_the_source_and_an_output_directory(
        self, factory: Any, tmp_path: Path
    ) -> None:
        converter = factory()
        stub = _stub_command(tmp_path, factory.info.id, writes_markdown=True)
        source = _a_pdf(tmp_path)
        options = NETWORKED.with_(extra={f"{factory.info.id}_python": str(stub)})

        text = converter._convert(Source.from_path(source), options, ConversionContext())

        recorded = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
        assert str(source) in recorded, f"{factory.info.id} did not pass the source path"
        assert any("out" in arg for arg in recorded), (
            f"{factory.info.id} did not pass an output directory"
        )
        assert "converted by the stub" in text

    @pytest.mark.parametrize("factory", COMMAND_BACKENDS, ids=lambda f: f.info.id)
    def test_writing_no_output_is_a_failure_with_the_tools_stderr(
        self, factory: Any, tmp_path: Path
    ) -> None:
        """How every one of these signals failure: no file, exit code zero.

        Marker and MinerU both exit 0 after failing to load a model, which is
        the LibreOffice lesson repeating in a new tier.
        """
        converter = factory()
        stub = _stub_command(tmp_path, factory.info.id, writes_markdown=False)
        options = NETWORKED.with_(extra={f"{factory.info.id}_python": str(stub)})

        with pytest.raises(BackendFailed, match="wrote no Markdown"):
            converter._convert(Source.from_path(_a_pdf(tmp_path)), options, ConversionContext())

    def test_the_workspace_is_removed_even_when_the_tool_fails(self, tmp_path: Path) -> None:
        converter = MarkerConverter()
        stub = _stub_command(tmp_path, "marker", writes_markdown=False)
        options = NETWORKED.with_(extra={"marker_python": str(stub)})

        with pytest.raises(BackendFailed):
            converter._convert(Source.from_path(_a_pdf(tmp_path)), options, ConversionContext())

        import tempfile

        leaked = list(Path(tempfile.gettempdir()).glob("tokenmill-marker-*"))
        assert leaked == [], f"the workspace leaked: {leaked}"


# --------------------------------------------------------------------- service


class _VllmHandler(BaseHTTPRequestHandler):
    """A vLLM-shaped OpenAI-compatible endpoint that records what it was sent."""

    received: ClassVar[dict[str, Any]] = {}
    mode: ClassVar[str] = "ok"

    def log_message(self, *args: object) -> None:
        """Silence the default stderr logging."""

    def do_GET(self) -> None:
        """Answer the readiness probe."""
        if _VllmHandler.mode == "down":
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self) -> None:
        """Answer a chat-completions request."""
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        _VllmHandler.received = json.loads(body)

        if _VllmHandler.mode == "notachat":
            payload: dict[str, Any] = {"detail": "this is not an OpenAI endpoint"}
        else:
            payload = {
                "choices": [{"message": {"content": "# Page one\n\nRead by the model.\n"}}],
                "usage": {"prompt_tokens": 256, "completion_tokens": 41, "total_tokens": 297},
            }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())


@pytest.fixture
def vllm() -> Iterator[str]:
    """Run a vLLM-shaped service on a real socket for one test.

    Yields:
        Its base URL.
    """
    _VllmHandler.mode = "ok"
    _VllmHandler.received = {}
    server = HTTPServer(("127.0.0.1", 0), _VllmHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class TestTheServiceBackendsAgainstARealServer:
    """The one part of this tier that is genuinely exercised end to end."""

    @pytest.mark.parametrize("factory", SERVICE_BACKENDS, ids=lambda f: f.info.id)
    def test_it_converts_through_a_real_http_service(
        self, factory: Any, vllm: str, tmp_path: Path
    ) -> None:
        converter = factory()
        image = tmp_path / "page.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n not really a png")
        options = NETWORKED.with_(extra={converter.url_option: vllm})

        result = converter.convert(Source.from_path(image), options)

        assert "Read by the model" in result.text
        assert result.metadata["model"] == converter.model_name
        assert result.metadata["service_kind"] == "vllm-openai"

    def test_the_request_is_an_openai_chat_completion_with_the_image_inline(
        self, vllm: str, tmp_path: Path
    ) -> None:
        """The contract both models' serving instructions document."""
        converter = DeepSeekOcrConverter()
        image = tmp_path / "page.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n bytes")
        options = NETWORKED.with_(extra={converter.url_option: vllm})

        converter.convert(Source.from_path(image), options)

        sent = _VllmHandler.received
        assert sent["model"] == "deepseek-ai/DeepSeek-OCR"
        assert sent["temperature"] == 0, (
            "a non-zero temperature would make every measurement taken through "
            "this backend unreproducible"
        )
        content = sent["messages"][0]["content"]
        assert content[0]["type"] == "image_url"
        assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
        assert content[1]["text"] == converter.prompt

    def test_the_services_own_token_counts_are_recorded_and_namespaced(
        self, vllm: str, tmp_path: Path
    ) -> None:
        """The optical-compression measurement, when somebody finally runs it.

        These are the *model's* tokens in the *model's* tokenizer, and the
        `service_` prefix is what stops them being read as a tokenmill
        measurement. For DeepSeek-OCR the ratio between them is the whole
        story the paper tells.
        """
        converter = DeepSeekOcrConverter()
        image = tmp_path / "page.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n bytes")
        options = NETWORKED.with_(extra={converter.url_option: vllm})

        result = converter.convert(Source.from_path(image), options)

        assert result.metadata["service_prompt_tokens"] == 256
        assert result.metadata["service_completion_tokens"] == 41
        assert not any(key in result.metadata for key in ("prompt_tokens", "tokens"))

    def test_talking_to_it_needs_allow_network_even_on_localhost(
        self, vllm: str, tmp_path: Path
    ) -> None:
        converter = DotsOcrConverter()
        image = tmp_path / "page.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n bytes")
        options = ConvertOptions(tokenizer="bytes", extra={converter.url_option: vllm})

        with pytest.raises(NetworkRequired):
            converter.convert(Source.from_path(image), options)

    def test_a_reply_that_is_not_a_chat_completion_is_a_clear_failure(
        self, vllm: str, tmp_path: Path
    ) -> None:
        """Pointing at the wrong server is the likely mistake, so it gets a message.

        Reporting an empty document here would send the user looking at their
        image; saying "this may not be an OpenAI-compatible endpoint" sends them
        to their URL, which is where the problem is.
        """
        converter = DeepSeekOcrConverter()
        image = tmp_path / "page.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n bytes")
        options = NETWORKED.with_(extra={converter.url_option: vllm})
        _VllmHandler.mode = "notachat"

        with pytest.raises(BackendFailed, match="no choices"):
            converter.convert(Source.from_path(image), options)


# ----------------------------------------------------------------- test helpers


def _a_pdf(tmp_path: Path) -> Path:
    """Write a file for an adapter to be handed.

    Its content does not matter: the stub never reads it.

    Args:
        tmp_path: The test's directory.

    Returns:
        The path.
    """
    path = tmp_path / "input.pdf"
    path.write_bytes(b"%PDF-1.4 not really\n")
    return path


def _stub_command(tmp_path: Path, name: str, *, writes_markdown: bool) -> Path:
    """Write an executable that records its arguments and optionally produces output.

    A real script rather than a patched `subprocess.run`, for the reason in the
    class docstring. It finds the output directory the way the adapters pass it
    — as the argument that ends in `out` — rather than being told, so a change
    to how an adapter passes it shows up here as a failure.

    Args:
        tmp_path: Where to write it.
        name: A label, used in the produced Markdown.
        writes_markdown: Whether to produce output at all. False reproduces the
            failure mode every one of these tools really has: exit zero, write
            nothing.

    Returns:
        The executable's path.
    """
    script = tmp_path / f"stub-{name}"
    record = tmp_path / "argv.json"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"json.dump(sys.argv[1:], open({str(record)!r}, 'w'))\n"
        "outdir = next((a for a in sys.argv[1:] "
        "if os.path.isdir(a) and os.path.basename(a) == 'out'), None)\n"
        f"if {writes_markdown!r} and outdir:\n"
        "    os.makedirs(os.path.join(outdir, 'input'), exist_ok=True)\n"
        "    open(os.path.join(outdir, 'input', 'input.md'), 'w').write("
        f"'# {name}\\n\\nconverted by the stub.\\n')\n"
        "sys.stderr.write('stub finished\\n')\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    # A moment for the filesystem, on the rare platform where an exec of a
    # just-written script races the write.
    time.sleep(0.01)
    return script


@pytest.fixture
def compose() -> Any:
    """Parse `docker/compose.heavy.yml`.

    Returns:
        The decoded document.
    """
    yaml = pytest.importorskip(
        "yaml",
        reason=(
            "PyYAML is a transitive dev dependency (via pre-commit) rather than a "
            "declared one, so this skips rather than failing where it is absent"
        ),
    )
    path = Path(__file__).resolve().parents[2] / "docker" / "compose.heavy.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class TestTheComposeFilesMatchTheAdapters:
    """The compose files and the service adapters must not drift apart.

    Neither has ever been run against the other — no GPU here, and the model
    host is denied — so the one thing that *can* be checked is that they agree
    with each other: the health path the adapter probes is the one the compose
    file's health check uses, and the ports the README tells people to pass are
    the ports the services publish.

    A documentation file and an adapter that disagree is the failure this
    catches, and it is the likeliest one: the compose file is the part nobody
    runs while developing.
    """

    def test_every_service_is_behind_a_profile(self, compose: Any) -> None:
        """`docker compose up` with no profile must start nothing.

        Six containers that each want a GPU, started because somebody typed
        `up`, is a rude default.
        """
        for name, service in compose["services"].items():
            assert service.get("profiles"), f"{name} would start on a bare `up`"

    def test_the_health_check_uses_the_path_the_adapter_probes(self, compose: Any) -> None:
        """Healthy in Compose and available in tokenmill must mean the same thing."""
        probed = {c.health_path for c in (DeepSeekOcrConverter(), DotsOcrConverter())}
        assert probed == {"/health"}

        for name, service in compose["services"].items():
            test = " ".join(service["healthcheck"]["test"])
            assert "/health" in test, f"{name}'s health check does not probe /health"

    def test_the_services_match_the_registered_service_backends(self, compose: Any) -> None:
        """A compose service with no adapter, or the reverse, is a dead end."""
        services = set(compose["services"])
        expected = {"deepseek-ocr", "dots-ocr"}

        assert services == expected, (
            f"the compose file defines {sorted(services)} and the registered "
            f"service backends are {sorted(expected)}; one of them has moved"
        )

    def test_each_service_reserves_a_gpu(self, compose: Any) -> None:
        for name, service in compose["services"].items():
            devices = service["deploy"]["resources"]["reservations"]["devices"]
            assert any(d.get("driver") == "nvidia" for d in devices), (
                f"{name} does not reserve a GPU, so it would start on CPU and hang"
            )
