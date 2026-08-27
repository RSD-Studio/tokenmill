"""The NiceGUI interface. Layout and event handlers, and nothing else.

**Every action in this file goes through `tokenmill.gui.api`.** That is the
mitigation `docs/DEVELOPMENT_PLAN.md` names for this phase's stated risk — *GUI
logic creeping into the UI layer* — and it is checkable rather than aspirational:
`tests/integration/test_gui_api.py` drives the whole feature set through that
same surface with no browser involved, and
`tests/unit/test_gui_boundary.py` asserts this module imports nothing from
`tokenmill.core`, `tokenmill.post` or `tokenmill.backends` at all.

So the only things below are: build a widget, read a widget, call `api`, render
what came back.

**Why NiceGUI**, recorded here and in `docs/ARCHITECTURE.md` because the plan
asks for the rationale to be written down:

* **Event-driven, not Streamlit's re-run-the-script model.** A batch queue that
  updates twenty rows as they finish, and a token counter that moves while a
  conversion runs, both fight a framework that re-executes the whole script on
  every interaction. `BatchRunner` calls back on its worker thread and the row
  updates; nothing re-runs.
* **FastAPI in-process.** The same application can expose an HTTP API and
  orchestrate the subprocess and service backends Phase 7 added, without a
  second server.
* **`native` mode is a desktop window without leaving Python.** A PySide6 shell
  remains a Phase 11 option for offline distribution.

**Threading.** NiceGUI's event loop and the batch worker are different threads.
Every UI update from the worker goes through the timer in
:meth:`_BatchPanel.attach` rather than touching widgets directly, because a
NiceGUI element mutated off the loop updates nothing on some browsers and
raises on others. Polling a snapshot is duller than pushing and it is correct.
"""

from __future__ import annotations

import contextlib
from dataclasses import replace
from pathlib import Path
from typing import Any

from nicegui import app as nicegui_app
from nicegui import ui

from tokenmill.gui import api
from tokenmill.gui.batch import BatchRunner, ItemState

__all__ = ["build", "run"]

#: Where an uploaded file is staged. Inside the user's own temp area; removed
#: when the process exits.
_UPLOADS = Path.home() / ".cache" / "tokenmill" / "uploads"

#: How often the batch panel re-reads the runner's state, in seconds.
_REFRESH_S = 0.2

#: Colours for the licence badge. Copyleft is called out because a user should
#: know when what they are running is isolated for a licence reason.
_TIER_COLOUR = {
    "permissive": "green",
    "copyleft": "orange",
    "non-commercial": "red",
}


class _State:
    """Everything the interface is currently showing.

    A plain object rather than module globals so that two browser tabs do not
    share one selection.

    Attributes:
        sources: Paths the user has added.
        text: Pasted text, when that is the source.
        url: A URL, when that is the source.
        tokenizer: The selected tokenizer id.
        backend: The pinned backend, or ``None`` to auto-select.
        post_processors: The chosen chain, or ``None`` for the default.
        allow_network: Whether backends may reach the network.
        corpus: Where to look for ground truth, when scoring fidelity.
        rate: The user's own cost per million tokens.
        currency: The user's own label for their units.
        last: The most recent single-conversion summary.
        runner: The batch in flight, if any.
    """

    def __init__(self) -> None:
        """Start with nothing selected and sensible defaults."""
        self.sources: list[Path] = []
        self.text: str = ""
        self.url: str = ""
        self.tokenizer: str = "o200k_base"
        self.backend: str | None = None
        self.post_processors: list[str] | None = None
        self.allow_network: bool = False
        self.corpus: Path | None = None
        self.rate: float = 0.0
        self.currency: str = "$"
        self.last: api.ConversionSummary | None = None
        self.runner: BatchRunner | None = None

    def request_for(self, source: Any) -> api.ConversionRequest:
        """Build a conversion request from the current selections.

        Args:
            source: The input to convert.

        Returns:
            The request.
        """
        return api.ConversionRequest(
            source=source,
            tokenizer=self.tokenizer,
            backend=self.backend,
            post_processors=tuple(self.post_processors) if self.post_processors else None,
            allow_network=self.allow_network,
            corpus=self.corpus,
        )


def _fmt(value: int | None) -> str:
    """Render a token count, or ``n/a`` when there is none.

    ``None`` is not zero, and the fidelity work exists because rendering it as
    zero is how a destroyed document scores as a perfect saving.

    Args:
        value: The count.

    Returns:
        The rendered value.
    """
    return "n/a" if value is None else f"{value:,}"


def _reduction_text(value: float | None) -> str:
    """Render a saving the way a user reads it: positive means smaller.

    Args:
        value: The ratio, where positive is a saving.

    Returns:
        The rendered value.
    """
    if value is None:
        return "n/a"
    # U+2212 MINUS SIGN rather than a hyphen: this is rendered text a person
    # reads, not source anyone greps, and a hyphen beside a percentage is a
    # typographic wart at the size this is displayed at.
    return f"\N{MINUS SIGN}{value:.1%}" if value >= 0 else f"+{-value:.1%}"


def _fidelity_text(value: float | None) -> str:
    """Render a fidelity score, or ``n/a`` when there is no ground truth.

    Args:
        value: The score.

    Returns:
        The rendered value.
    """
    return "n/a" if value is None else f"{value:.3f}"


def build(state: _State | None = None) -> None:
    """Construct the whole interface on the current NiceGUI page.

    Args:
        state: The page's state; a fresh one is made when omitted.
    """
    st = state if state is not None else _State()
    _UPLOADS.mkdir(parents=True, exist_ok=True)

    ui.dark_mode().bind_value_from(nicegui_app.storage.user, "dark", lambda v: bool(v))

    with ui.header().classes("items-center justify-between"):
        ui.label("tokenmill").classes("text-2xl font-bold")
        ui.label("wraps best-in-class OSS converters and measures what each one saves").classes(
            "text-sm opacity-70"
        )
        ui.switch("Dark").on_value_change(
            lambda e: nicegui_app.storage.user.update({"dark": e.value})
        )

    with ui.tabs().classes("w-full") as tabs:
        convert_tab = ui.tab("Convert")
        batch_tab = ui.tab("Batch")
        compare_tab = ui.tab("Compare")
        backends_tab = ui.tab("Backends")
        settings_tab = ui.tab("Settings")

    with ui.tab_panels(tabs, value=convert_tab).classes("w-full"):
        with ui.tab_panel(convert_tab):
            _ConvertPanel(st).build()
        with ui.tab_panel(batch_tab):
            _BatchPanel(st).build()
        with ui.tab_panel(compare_tab):
            _ComparePanel(st).build()
        with ui.tab_panel(backends_tab):
            _backends_panel()
        with ui.tab_panel(settings_tab):
            _settings_panel(st)


# --------------------------------------------------------------------- convert


class _ConvertPanel:
    """The single-conversion view: source, options, tokens, preview."""

    def __init__(self, state: _State) -> None:
        """Hold the page state.

        Args:
            state: The page's state.
        """
        self.state = state
        self.result_area: Any = None
        self.token_area: Any = None

    def build(self) -> None:
        """Lay out the panel."""
        with ui.row().classes("w-full gap-4 no-wrap"):
            with ui.column().classes("w-1/3 gap-2"):
                self._source_panel()
                self._options_panel()
            with ui.column().classes("w-2/3 gap-2"):
                self.token_area = ui.column().classes("w-full")
                self.result_area = ui.column().classes("w-full")
                with self.token_area:
                    ui.label("No conversion yet.").classes("opacity-60")

    def _source_panel(self) -> None:
        """Drag-and-drop, a URL box and a text area."""
        with ui.card().classes("w-full"):
            ui.label("Source").classes("text-lg font-semibold")
            ui.upload(
                on_upload=self._on_upload,
                multiple=True,
                auto_upload=True,
                label="Drop files here",
            ).classes("w-full")
            ui.input("URL", placeholder="https://example.com/article").bind_value(
                self.state, "url"
            ).classes("w-full")
            ui.textarea("or paste text").bind_value(self.state, "text").classes("w-full")
            self.file_list = ui.column().classes("w-full text-sm")
            ui.button("Convert", on_click=self._on_convert).props("color=primary")

    def _options_panel(self) -> None:
        """Tokenizer, backend and post-processor selection."""
        with ui.card().classes("w-full"):
            ui.label("Options").classes("text-lg font-semibold")
            ui.select(
                list(api.tokenizer_choices()), label="Tokenizer", value=self.state.tokenizer
            ).bind_value(self.state, "tokenizer").classes("w-full")

            choices = api.backend_choices()
            options: dict[str | None, str] = {None: "auto-select"}
            for choice in choices:
                label = f"{choice.name} ({choice.license})"
                if not choice.available:
                    label += "  — unavailable"
                options[choice.id] = label
            ui.select(options, label="Backend", value=None).bind_value(
                self.state, "backend"
            ).classes("w-full")

            ui.label("Post-processing").classes("text-sm font-semibold mt-2")
            for processor in api.post_processor_choices():
                with ui.row().classes("items-center gap-2"):
                    ui.checkbox(
                        processor.id,
                        value=processor.in_default_chain,
                        on_change=lambda e, pid=processor.id: self._toggle_post(pid, e.value),
                    )
                    if processor.destructive:
                        ui.badge("destructive", color="orange").props("outline")
                ui.label(processor.description).classes("text-xs opacity-60 ml-8")

            ui.switch("Allow backends to use the network").bind_value(self.state, "allow_network")

    def _toggle_post(self, processor_id: str, enabled: bool) -> None:
        """Add or remove one post-processor from the chain.

        Args:
            processor_id: Which one.
            enabled: Whether it should run.
        """
        current = self.state.post_processors
        if current is None:
            current = [p.id for p in api.post_processor_choices() if p.in_default_chain]
        chain = [p for p in current if p != processor_id]
        if enabled:
            chain = [p.id for p in api.post_processor_choices() if p.id in {*chain, processor_id}]
        self.state.post_processors = chain

    async def _on_upload(self, event: Any) -> None:
        """Stage an uploaded file and remember it.

        The event carries a ``file`` with an **async** ``read()``; the shape was
        got wrong first time (``event.name`` / ``event.content.read()``), which
        the running server reported as an `AttributeError` and the interface
        showed as an upload that completed and did nothing. Read out of the
        installed `nicegui.elements.upload_files.FileUpload` rather than guessed
        at a second time.

        Args:
            event: NiceGUI's upload event.
        """
        # The browser sends the base name only, and a hostile one can still be
        # `../../etc/passwd`. Path().name strips every separator on both
        # platforms, so the write cannot escape the staging directory.
        safe = Path(event.file.name).name or "upload"
        target = _UPLOADS / safe
        target.write_bytes(await event.file.read())
        self.state.sources.append(target)
        self._render_files()

    def _render_files(self) -> None:
        """Redraw the list of staged files."""
        self.file_list.clear()
        with self.file_list:
            for path in self.state.sources:
                ui.label(f"• {path.name}")

    def _on_convert(self) -> None:
        """Convert whatever the user has given us."""
        from tokenmill.core.models import Source

        if self.state.sources:
            source = Source.from_path(self.state.sources[-1])
        elif self.state.url.strip():
            source = Source.from_url(self.state.url.strip())
        elif self.state.text.strip():
            source = Source.from_text(self.state.text)
        else:
            ui.notify("Add a file, a URL or some text first", type="warning")
            return

        summary = api.convert(self.state.request_for(source))
        self.state.last = summary
        self._render(summary)

    def _render(self, summary: api.ConversionSummary) -> None:
        """Draw the token panel and the preview.

        Args:
            summary: What to show.
        """
        self.token_area.clear()
        self.result_area.clear()

        if not summary.ok:
            with self.token_area, ui.card().classes("w-full bg-red-100 dark:bg-red-900"):
                ui.label("Conversion failed").classes("text-lg font-semibold")
                ui.label(summary.error or "").classes("text-sm")
                if summary.error_hint:
                    ui.label(f"Try: {summary.error_hint}").classes("text-sm italic")
            return

        with self.token_area, ui.card().classes("w-full"):
            ui.label("Tokens").classes("text-lg font-semibold")
            with ui.row().classes("items-baseline gap-6"):
                _stat("before", _fmt(summary.tokens_before))
                ui.label("→").classes("text-2xl opacity-50")
                _stat("after", _fmt(summary.tokens_after))
                _stat("change", _reduction_text(summary.reduction_ratio))
                _stat("fidelity", _fidelity_text(summary.fidelity))
            ui.label(
                f"counts in {summary.tokenizer_id or 'no tokenizer'} · "
                f"{summary.backend_id} · {summary.duration_ms} ms"
            ).classes("text-xs opacity-60")

            if self.state.rate > 0 and summary.tokens_after is not None:
                estimate = api.estimate_cost(
                    summary.tokens_after, self.state.rate, self.state.currency
                )
                ui.label(
                    f"At your rate of {estimate.currency}{estimate.rate_per_million:g} per "
                    f"million: {estimate.currency}{estimate.cost:.4f}"
                ).classes("text-sm")

            if summary.stages:
                ui.label("Per stage").classes("text-sm font-semibold mt-2")
                ui.table(
                    columns=[
                        {"name": "stage", "label": "stage", "field": "stage", "align": "left"},
                        {"name": "tokens", "label": "tokens", "field": "tokens"},
                        {"name": "delta", "label": "change", "field": "delta"},
                    ],
                    rows=[
                        {
                            "stage": row.name,
                            "tokens": f"{row.tokens:,}",
                            "delta": "—" if row.delta is None else f"{row.delta:+,}",
                        }
                        for row in summary.stages
                    ],
                ).classes("w-full")

            for warning in summary.warnings:
                ui.label(f"⚠ {warning}").classes("text-sm text-orange-700 dark:text-orange-300")

        with self.result_area, ui.card().classes("w-full"):
            with ui.row().classes("items-center justify-between w-full"):
                ui.label("Output").classes("text-lg font-semibold")
                with ui.row().classes("gap-2"):
                    ui.button(
                        "Copy",
                        on_click=lambda: ui.clipboard.write(summary.text),
                    ).props("flat")
                    ui.button("Download", on_click=lambda: _download(summary)).props("flat")
            with ui.tabs() as view:
                rendered = ui.tab("Rendered")
                raw = ui.tab("Raw")
            with ui.tab_panels(view, value=rendered).classes("w-full"):
                with ui.tab_panel(rendered):
                    ui.markdown(summary.text)
                with ui.tab_panel(raw):
                    ui.code(summary.text).classes("w-full")


def _stat(label: str, value: str) -> None:
    """Draw one big number with a small caption.

    Args:
        label: The caption.
        value: The number.
    """
    with ui.column().classes("gap-0 items-center"):
        ui.label(value).classes("text-2xl font-bold")
        ui.label(label).classes("text-xs opacity-60")


def _download(summary: api.ConversionSummary) -> None:
    """Send one conversion's text to the browser.

    Args:
        summary: What to send.
    """
    suffix = "md" if summary.output_format == "markdown" else "txt"
    ui.download.content(summary.text.encode("utf-8"), f"{summary.source_name}.{suffix}")


# ----------------------------------------------------------------------- batch


class _BatchPanel:
    """The queue view: per-item status, cancel, and aggregate totals."""

    def __init__(self, state: _State) -> None:
        """Hold the page state.

        Args:
            state: The page's state.
        """
        self.state = state
        self.rows: Any = None
        self.totals_area: Any = None

    def build(self) -> None:
        """Lay out the panel and start the refresh timer."""
        with ui.card().classes("w-full"):
            ui.label("Batch").classes("text-lg font-semibold")
            ui.label(
                "Conversions run one at a time on a background thread. The interface "
                "stays live; see the batch module for why they are not parallel."
            ).classes("text-xs opacity-60")
            with ui.row().classes("gap-2"):
                ui.button("Run the staged files", on_click=self._start).props("color=primary")
                ui.button("Cancel queued", on_click=self._cancel).props("flat color=negative")
            self.totals_area = ui.row().classes("gap-6 items-baseline")
            self.rows = ui.column().classes("w-full")
        ui.timer(_REFRESH_S, self._refresh)

    def _start(self) -> None:
        """Queue every staged file and begin."""
        from tokenmill.core.models import Source

        if not self.state.sources:
            ui.notify("Stage some files on the Convert tab first", type="warning")
            return
        template = self.state.request_for(Source.from_path(self.state.sources[0]))
        requests = tuple(
            replace(template, source=Source.from_path(path)) for path in self.state.sources
        )
        self.state.runner = BatchRunner(requests)
        self.state.runner.start()

    def _cancel(self) -> None:
        """Cancel the queued items; the running one finishes."""
        if self.state.runner is not None:
            self.state.runner.cancel()
            ui.notify("Queued items cancelled; the running one will finish", type="info")

    def _refresh(self) -> None:
        """Re-read the runner's state and redraw.

        Polled from the NiceGUI event loop rather than pushed from the worker
        thread: a NiceGUI element mutated off the loop updates nothing on some
        browsers and raises on others.
        """
        runner = self.state.runner
        if runner is None:
            return

        totals = runner.totals
        self.totals_area.clear()
        with self.totals_area:
            _stat("done", f"{totals.done}/{totals.total}")
            _stat("failed", str(totals.failed))
            _stat("cancelled", str(totals.cancelled))
            _stat("output", _fmt(totals.tokens_produced))
            _stat("saving", _reduction_text(totals.reduction_ratio))
            ui.label(
                f"over the {totals.comparable} item(s) with a comparable before-count"
            ).classes("text-xs opacity-60")

        self.rows.clear()
        colours = {
            ItemState.DONE: "text-green-700 dark:text-green-300",
            ItemState.FAILED: "text-red-700 dark:text-red-300",
            ItemState.RUNNING: "font-semibold",
            ItemState.CANCELLED: "opacity-50",
            ItemState.QUEUED: "opacity-60",
        }
        with self.rows:
            for item in runner.items:
                with ui.row().classes("w-full items-center gap-4"):
                    ui.label(item.name).classes(f"w-1/3 {colours[item.state]}")
                    ui.label(item.state.value).classes("w-24 text-xs")
                    summary = item.summary
                    if summary is not None and summary.ok:
                        ui.label(_fmt(summary.tokens_after)).classes("w-24 text-right")
                        ui.label(_fidelity_text(summary.fidelity)).classes("w-20 text-right")
                    elif summary is not None:
                        ui.label(summary.error or "").classes("text-xs text-red-600")


# --------------------------------------------------------------------- compare


class _ComparePanel:
    """One input, several backends, tokens and fidelity side by side."""

    def __init__(self, state: _State) -> None:
        """Hold the page state.

        Args:
            state: The page's state.
        """
        self.state = state
        self.area: Any = None
        self.chooser: Any = None
        self.choice: Any = None
        self._shown: list[str] = []

    def build(self) -> None:
        """Lay out the panel."""
        with ui.card().classes("w-full"):
            ui.label("Compare backends").classes("text-lg font-semibold")
            ui.label(
                "Rows stay in preference order and are never sorted by size. On "
                "tables.pdf the cheapest backend is the one that destroys the table."
            ).classes("text-xs opacity-60")
            self.chooser = ui.column().classes("w-full gap-1")
            ui.timer(1.0, self._sync_chooser)
            self.area = ui.column().classes("w-full")

    def _sync_chooser(self) -> None:
        """Rebuild the file chooser when the staged files change.

        Rebuilt rather than mutated. An explicit choice is needed at all because
        uploads arrive concurrently, so "the last staged file" is whichever
        finished first — not the one the user pointed at.
        """
        names = [p.name for p in self.state.sources]
        if names == self._shown:
            return
        self._shown = names
        self.chooser.clear()
        with self.chooser:
            if not names:
                ui.label("Stage a file on the Convert tab first.").classes("text-sm opacity-60")
                return
            self.choice = ui.radio(names, value=names[0]).props("inline")
            ui.button("Compare", on_click=self._run).props("color=primary")

    def _run(self) -> None:
        """Run the comparison across every available backend for the source."""
        from tokenmill.core.models import Source

        chosen = getattr(self.choice, "value", None)
        path = next((p for p in self.state.sources if p.name == chosen), None)
        if path is None:
            ui.notify("Stage a file on the Convert tab first", type="warning")
            return

        source = Source.from_path(path)
        request = self.state.request_for(source)
        candidates = [
            choice.id
            for choice in api.backend_choices()
            if choice.available and _claims(choice, source)
        ]
        comparison = api.compare_across_backends(request, candidates)

        self.area.clear()
        with self.area:
            ui.table(
                columns=[
                    {"name": "backend", "label": "backend", "field": "backend", "align": "left"},
                    {"name": "tokens", "label": "tokens", "field": "tokens"},
                    {"name": "fidelity", "label": "fidelity", "field": "fidelity"},
                    {"name": "time", "label": "time", "field": "time"},
                ],
                # No `sortable`, deliberately. `docs/ARCHITECTURE.md` explains
                # why compare is not sorted by size, and a sortable size column
                # would hand the user back the mistake the whole design avoids.
                rows=[
                    {
                        "backend": row.backend_id,
                        "tokens": _fmt(row.tokens.value if row.tokens else None),
                        "fidelity": _fidelity_text(row.fidelity.overall if row.fidelity else None),
                        "time": _duration_text(row),
                    }
                    for row in comparison.rows
                ],
            ).classes("w-full")

            # Failures get their own wrapped block rather than a table cell.
            # The first version put the message in the `time` column, where the
            # table clipped it mid-sentence: LibreOffice's "install the component
            # packages too: 'apt install libreoffic…" lost exactly the half a
            # user needs. A message that cannot be read is not actionable, and
            # actionable is the acceptance criterion.
            for row in comparison.rows:
                if row.ok:
                    continue
                with ui.column().classes("w-full gap-0 pl-4 mt-2 border-l-4 border-red-400"):
                    ui.label(f"{row.backend_id} failed").classes("text-sm font-semibold")
                    ui.label(str(row.error or "")).classes("text-xs opacity-80 whitespace-normal")
            cheapest = comparison.cheapest
            faithful = comparison.most_faithful
            if cheapest is not None and faithful is not None and cheapest is not faithful:
                ui.label(
                    f"The cheapest backend ({cheapest.backend_id}) is NOT the most "
                    f"faithful ({faithful.backend_id}). A token saving without a "
                    f"fidelity number is not a result."
                ).classes("text-sm font-semibold text-orange-700 dark:text-orange-300")


def _duration_text(row: Any) -> str:
    """Render a comparison row's timing, or its error when it failed.

    Args:
        row: A :class:`~tokenmill.core.compare.ComparisonRow`.

    Returns:
        The rendered value.
    """
    if not row.ok:
        # Just the word. The message goes in its own wrapped block under the
        # table: a table cell clips it, and a clipped message loses exactly the
        # half that says what to do.
        return "failed"
    if row.duration_s is None:
        return "n/a"
    return f"{int(row.duration_s * 1000)} ms"


def _claims(choice: api.BackendChoice, source: Any) -> bool:
    """Whether a backend handles this source's format.

    Args:
        choice: The backend.
        source: The input.

    Returns:
        True when it claims the format.
    """
    from tokenmill.core.registry import default_registry

    with contextlib.suppress(KeyError):
        return default_registry().get(choice.id).supports(source)
    return False


# -------------------------------------------------------------------- backends


def _backends_panel() -> None:
    """List every backend with its licence, isolation and availability."""
    with ui.card().classes("w-full"):
        ui.label("Backends").classes("text-lg font-semibold")
        ui.label(
            "Unavailable backends are shown greyed out with what to install, never hidden."
        ).classes("text-xs opacity-60")
        for choice in api.backend_choices():
            classes = "w-full items-center gap-3" + ("" if choice.available else " opacity-50")
            with ui.row().classes(classes):
                ui.label(choice.name).classes("w-40 font-semibold")
                ui.badge(choice.badge, color="blue").props("outline")
                ui.badge(
                    choice.license_tier.value,
                    color=_TIER_COLOUR.get(choice.license_tier.value, "grey"),
                ).props("outline")
                ui.label(choice.license).classes("w-40 text-xs")
                if choice.isolated:
                    ui.badge(choice.isolation.value, color="purple").props("outline")
                ui.label(choice.status).classes("text-xs")
            if not choice.available and choice.hint:
                ui.label(f"→ {choice.hint}").classes("text-xs italic ml-40 opacity-70")


# -------------------------------------------------------------------- settings


def _settings_panel(state: _State) -> None:
    """Tokenizer default, corpus location, network policy and cost rates."""
    with ui.card().classes("w-full"):
        ui.label("Settings").classes("text-lg font-semibold")
        ui.select(
            list(api.tokenizer_choices()), label="Default tokenizer", value=state.tokenizer
        ).bind_value(state, "tokenizer").classes("w-full")
        ui.input(
            "Ground-truth corpus (for fidelity scoring)",
            placeholder="tests/fixtures",
            on_change=lambda e: setattr(state, "corpus", Path(e.value) if e.value else None),
        ).classes("w-full")
        ui.switch("Allow backends to use the network").bind_value(state, "allow_network")

    with ui.card().classes("w-full"):
        ui.label("Cost estimate").classes("text-lg font-semibold")
        ui.label(
            "tokenmill ships no price table and never will: prices change, and a "
            "stale one here would be a confident lie about your bill. Type your "
            "own rate and this multiplies."
        ).classes("text-xs opacity-60")
        ui.number("Cost per million tokens", value=0.0, format="%.4f").bind_value(
            state, "rate"
        ).classes("w-full")
        ui.input("Currency symbol", value="$").bind_value(state, "currency").classes("w-40")


# ------------------------------------------------------------------- launching


def run(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    server: bool = False,
    native: bool = False,
    show: bool = True,
    reload: bool = False,
) -> None:
    """Start the interface.

    Args:
        host: Address to bind. Ignored when ``server`` is set.
        port: Port to listen on.
        server: Bind ``0.0.0.0`` for LAN or headless use. **Off by default**:
            binding every interface is a decision about somebody's network and
            it should be typed, not defaulted into.
        native: Open a desktop window instead of a browser tab.
        show: Open a browser.
        reload: Reload on source changes. Development only.
    """
    ui.page("/")(lambda: build())
    ui.run(
        host="0.0.0.0" if server else host,  # noqa: S104 - opt-in, documented above
        port=port,
        title="tokenmill",
        native=native,
        show=show and not server,
        reload=reload,
        storage_secret="tokenmill-local",  # noqa: S106 - a local UI preference key
    )
