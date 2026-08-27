# `tokenfold` — Development Plan

**Version:** 1.0 · **Date:** 2026-08-19 · **Audience:** Claude Code (implementer)

This document defines the complete build sequence. It is paired with `RESEARCH.md`,
which supplies the tool catalog, licenses, and evidence base. Where this plan names
a tool, `RESEARCH.md` explains why it was chosen and what its constraints are.

---

## 0. Product definition

### What it is

A Python-native application — GUI and CLI over a shared library — that wraps
open-source converters for four input domains behind one interface and reports
token savings for every conversion.

| Domain | Input | Output |
|---|---|---|
| Documents | PDF, DOCX, PPTX, XLSX, EPUB, images, audio, email, CSV/JSON/XML, ZIP | Markdown |
| Web | URL or saved HTML | Boilerplate-stripped Markdown |
| Code | Local repo path or Git URL | Single prompt-ready file |
| Text | Raw prompt/context | Compressed text (opt-in) |

### The three things that differentiate it

1. **All four domains in one place.** Every existing OSS project covers one.
2. **Token measurement is first-class.** Before/after counts on every conversion,
   with a selectable tokenizer, plus a comparison mode that runs one input through
   several backends and shows the token/quality tradeoff side by side.
3. **A real plugin architecture.** Backends are swappable, third parties can add
   one with `pip install`, and license tier is visible metadata.

### Non-goals (say no to these explicitly)

- Not a RAG framework, vector store, or agent runtime.
- Not a hosted service. Local-first; a self-hosted server mode is a bonus, not the point.
- Not a wrapper around proprietary APIs.
- Not an OCR model trainer.

### Naming

Working name `tokenfold`; package `tokenfold`, CLI `tokenfold`, GUI `tokenfold gui`.
Verify availability in Phase 0. If taken, propose alternatives and get owner sign-off
before the first commit — renaming after Phase 2 is expensive.

---

## 1. Architecture contract

Every phase builds against this. Define it in Phase 1 and treat changes to it as
breaking changes requiring owner sign-off.

### 1.1 Core data model

```
Source          — what the user gave us: file path | bytes+mime | URL | repo ref | raw text
ConversionResult— text, format, token counts before/after, backend id, duration,
                  warnings, structured metadata (page count, tables found, etc.)
BackendInfo     — id, display name, domains, input formats, output formats, license,
                  license tier, install extra, requires_gpu, requires_network,
                  requires_binary, isolation mode, upstream URL
TokenCount      — value + tokenizer id (never a bare int; the tokenizer is part of
                  the number's meaning)
```

`ConversionResult` is immutable and always carries enough provenance to reproduce it.

### 1.2 The backend protocol

```python
class Converter(Protocol):
    info: BackendInfo

    def is_available(self) -> Availability:
        ...
        # Present / MissingDependency(list) / MissingBinary(name) / Unsupported(reason)
        # Never raises. Cheap. Cached per process.

    def supports(self, source: Source) -> bool: ...

    def convert(self, source: Source, options: ConvertOptions) -> ConversionResult:
        ...
        # Raises only ConversionError subclasses.
```

Rules:

- **Optional imports only.** A backend module must import at module load without its
  heavy dependency present; the real import happens inside `convert()` or behind a
  lazy accessor. A missing dependency degrades to "unavailable and greyed out,"
  never an ImportError at startup.
- **AGPL/GPL and non-Python backends run out of process.** They subclass a
  `SubprocessConverter` base that handles binary discovery, argument building,
  timeout, stdout/stderr capture, and temp-file cleanup.
- **Registration via entry points** (`tokenfold.backends`) so third-party plugins
  work with a plain `pip install`. Built-ins register through the same mechanism —
  no special-casing.

### 1.3 Pipeline

```
Source → [Converter] → raw Markdown → [PostProcessor chain] → final text
                                          ↓
                                    TokenMeter (before / after / per stage)
```

Post-processors are also plugins, ordered and individually toggleable: whitespace
normalization, boilerplate stripping, image/link handling, heading normalization,
table reformatting (Markdown ↔ CSV ↔ TOON), chunking, prompt compression.

### 1.4 Error taxonomy

`ConversionError` base, with `UnsupportedFormat`, `BackendUnavailable`,
`BackendFailed(stderr)`, `Timeout`, `CorruptSource`, `NetworkRequired`. The GUI maps
each to a distinct, actionable message. Never let a raw traceback reach the UI.

### 1.5 Repository layout

```
tokenfold/
├── src/tokenfold/
│   ├── core/          models, protocol, registry, errors, pipeline, config
│   ├── tokens/        tokenizer adapters, TokenMeter, cost estimation
│   ├── backends/
│   │   ├── documents/ markitdown, docling, pdfplumber, pypdf, kreuzberg, pandoc…
│   │   ├── web/       trafilatura, markdownify, readability, crawl4ai
│   │   ├── repo/      gitingest, repomix, code2prompt
│   │   ├── compress/  llmlingua2, selective_context
│   │   └── isolated/  subprocess base + AGPL/GPL adapters
│   ├── post/          post-processors (clean, chunk, reformat, compress)
│   ├── formats/       markdown / csv / toon / json encoders
│   ├── cli/           typer app
│   └── gui/           nicegui + fastapi
├── tests/{unit,integration,fixtures}
├── benchmarks/        harness, corpus manifest, results
├── docs/
├── scripts/
├── PROGRESS.md
└── pyproject.toml
```

### 1.6 Dependency tiering

| Group | Contents | Rule |
|---|---|---|
| `core` (default) | tiktoken, markdownify, trafilatura, pypdf, pdfplumber, gitingest, chonkie, typer, pydantic | Pure Python, CPU, no system binary, permissive license |
| `documents` | markitdown, kreuzberg | Light-ish, still CPU |
| `docling` | docling | Pulls PyTorch — separate group so `core` stays light |
| `web` | crawl4ai + playwright | Browser download required |
| `compress` | llmlingua, transformers | CPU-feasible |
| `ocr` | pytesseract, paddleocr | Needs system binary/models |
| `heavy` | marker, mineru, olmocr, surya | GPU; **install docs only, never a hard dep** |
| `dev` | pytest, ruff, mypy, coverage, hypothesis | — |

`pip install tokenfold` must succeed on a clean machine with no compiler, no GPU,
and no network beyond PyPI, in under a minute.

---

## 2. Phases

Each phase: **Goal → Deliverables → Acceptance criteria → Sandbox verification →
Risks → Exit gate.** A phase ends only when its exit gate is observed to pass in the
sandbox and `PROGRESS.md` is updated.

---

### Phase 0 — Scaffolding and toolchain

**Goal:** a repo that installs, lints, type-checks, tests, and documents itself,
containing zero product logic.

**Deliverables**
- `pyproject.toml` (hatchling or setuptools), `src/` layout, `requires-python >=3.11`,
  dependency groups from §1.6 declared but mostly empty.
- `uv`-based workflow; lockfile committed.
- Ruff (lint + format), mypy (strict on `src/core`), pytest + pytest-cov, pre-commit.
- GitHub Actions: matrix over Python 3.11/3.12/3.13 × ubuntu/macos/windows; jobs for
  lint, type, test, and a "clean core install" job that installs *only* the default
  extra and imports the package.
- `LICENSE` (Apache-2.0 recommended — permissive, patent grant, matches the
  ecosystem we wrap), `README.md` skeleton, `CONTRIBUTING.md`, `CHANGELOG.md`,
  issue/PR templates.
- `PROGRESS.md` initialized with the full phase table.
- `docs/DEVELOPMENT_PLAN.md` and `docs/research/RESEARCH.md` committed as-is.
- `scripts/make_fixtures.py` generating the synthetic test corpus (see §3).
- One trivial passing test so CI is green from commit one.

**Acceptance criteria**
- Clean clone → `uv sync` → all checks pass.
- `python -c "import tokenfold; print(tokenfold.__version__)"` works with only core deps.
- Fixture script produces every fixture file deterministically.

**Sandbox verification**
```bash
uv venv && uv sync --extra dev
uv run ruff check . && uv run ruff format --check .
uv run mypy src/
uv run pytest -q
uv run python scripts/make_fixtures.py && ls -la tests/fixtures/
uv run python -c "import tokenfold, sys; print(tokenfold.__version__, sys.version)"
```

**Risks** — Windows path/encoding issues surface late if CI is Linux-only; include
Windows in the matrix from day one.

**Exit gate:** all commands above green, fixtures generated and visually inspected,
name availability confirmed, `PROGRESS.md` written.

---

### Phase 1 — Core architecture

**Goal:** the plugin system and token measurement working end to end, proven by two
deliberately trivial backends.

**Deliverables**
- `core/models.py` — `Source`, `ConversionResult`, `BackendInfo`, `TokenCount`,
  `ConvertOptions`, `Availability` (pydantic v2 / dataclasses, fully typed).
- `core/protocol.py` — the `Converter` protocol + `BaseConverter` with shared
  behavior (timing, warning collection, result assembly).
- `core/registry.py` — entry-point discovery, lookup by id/domain/format,
  availability filtering, backend auto-selection (best available backend for a
  given source, with an explicit, documented preference order).
- `core/errors.py` — the taxonomy from §1.4.
- `core/pipeline.py` — converter + ordered post-processors + measurement.
- `core/config.py` — layered config (defaults → config file → env → CLI flags).
- `tokens/` — tiktoken adapter, HuggingFace adapter (lazy), `TokenMeter` producing
  per-stage counts, optional cost estimation with user-supplied rates only.
- `post/base.py` + two real post-processors: whitespace normalization, and
  Markdown-link/image handling.
- Two reference backends: `plaintext` (read a .txt/.md, pass through) and
  `markdownify_html` (HTML string → Markdown). Both permissive, both trivial —
  their job is to prove the architecture.
- `cli/` — `tokenfold convert`, `tokenfold backends`, `tokenfold tokens`.
- Tests: registry discovery, availability degradation (simulate a missing dep),
  protocol conformance test that every registered backend must pass, token counting
  golden tests, pipeline ordering, error mapping.
- `docs/ARCHITECTURE.md` and `docs/ADDING_A_BACKEND.md` written now, while the
  design is fresh.

**Acceptance criteria**
- A backend can be added by dropping a module + entry point, with no core edits.
- Registry lists backends with correct availability when a dep is absent.
- Token counts match a hand-verified tiktoken result on a known string.
- `tokenfold convert tests/fixtures/boilerplate.html` returns Markdown and a real
  before/after count.

**Sandbox verification**
```bash
uv run pytest -q tests/unit
uv run tokenfold backends --all            # shows availability + license per backend
uv run tokenfold convert tests/fixtures/boilerplate.html --tokenizer o200k_base
uv run tokenfold tokens tests/fixtures/boilerplate.html
# then: read the emitted Markdown; confirm nav/ads gone, article text intact
```

**Risks** — Over-engineering. Keep the protocol small; resist adding hooks nobody
needs yet. Also: entry-point discovery is slow if it scans everything — cache it.

**Exit gate:** protocol-conformance test passes for both reference backends; a
deliberately broken backend is reported as unavailable rather than crashing the CLI;
architecture docs committed.

---

### Phase 2 — Document backends (light tier)

**Goal:** real document conversion, CPU-only, permissive licenses.

**Deliverables**
- Adapters: **MarkItDown** (breadth: Office, images, audio, ZIP), **pdfplumber**
  and **pypdf** (light digital PDF), **Kreuzberg v4** (unified light extraction).
- **Docling** adapter behind the `docling` extra (best table fidelity in the
  permissive tier; pulls PyTorch, so it must be optional and lazily imported).
- Format→backend preference map with documented rationale, plus a fallback chain:
  if the preferred backend fails or is unavailable, try the next and record which
  one actually ran in `ConversionResult`.
- Per-backend integration tests, marked `@pytest.mark.requires("markitdown")` and
  auto-skipped when the dep is absent.
- Golden-file tests: fixture → expected Markdown structure (assert on headings,
  table presence, and ordering — not byte equality, which is too brittle).
- `docs/BACKENDS.md` sections for each, including **observed** failure modes.

**Acceptance criteria**
- Every fixture format converts through at least one backend.
- Table-bearing PDF: at least one backend preserves the table as a Markdown table —
  verify by reading the output.
- Fallback chain demonstrably works when the primary backend is uninstalled.

**Sandbox verification**
```bash
uv sync --extra documents --extra dev
for f in tests/fixtures/*.{pdf,docx,pptx,xlsx}; do uv run tokenfold convert "$f" -o /tmp/out; done
uv run tokenfold convert tests/fixtures/tables.pdf --backend pdfplumber
uv run tokenfold convert tests/fixtures/tables.pdf --backend docling   # compare
uv run pytest -q tests/integration -m "not heavy"
```
Then **read `/tmp/out/*.md`** — headings, list nesting, table integrity, token deltas.

**Risks** — Docling's PyTorch dependency leaking into core; a resolver conflict
between MarkItDown and Kreuzberg. Test the clean-core install job on every commit.

**Exit gate:** all fixture documents convert; the table check passes on inspection;
no core-install regression.

---

### Phase 3 — Web backends

**Goal:** URL or HTML in, clean Markdown out, with the boilerplate-stripping win
measured.

**Deliverables**
- Adapters: **Trafilatura** (primary — best extraction quality), **markdownify**
  (raw conversion), **readability** (fallback), **Crawl4AI** behind the `web` extra
  for JS-rendered pages.
- URL fetching with a sane user agent, timeout, redirect limit, size cap, and
  `robots.txt` respect (default on, overridable with an explicit flag).
- Offline mode: convert saved HTML with zero network calls, enforced and tested.
- A "boilerplate reduction" metric: raw-HTML tokens vs extracted-Markdown tokens,
  surfaced in the result.

**Acceptance criteria**
- Saved fixture page with heavy nav/ads: reduction lands in the same order of
  magnitude as the published figures in `RESEARCH.md` (~70–90%). If ours differs
  wildly, investigate before reporting — don't just publish the number.
- No network access occurs when converting a local HTML file (assert this in a test).

**Sandbox verification**
```bash
uv run tokenfold convert tests/fixtures/boilerplate.html --backend trafilatura --show-stages
uv run tokenfold convert tests/fixtures/boilerplate.html --backend markdownify --show-stages
uv run tokenfold convert https://example.com --backend trafilatura   # if network allowed
uv run pytest -q tests/integration/test_web.py
```

**Risks** — Playwright/Crawl4AI browser downloads in CI (gate behind a marker and
skip by default). Live-URL tests are flaky — keep them opt-in.

**Exit gate:** measured reduction on the fixture recorded in `PROGRESS.md` and
`docs/BENCHMARKS.md`; offline guarantee test passes.

---

### Phase 4 — Repository backends

**Goal:** point at a repo, get one prompt-ready file with token accounting.

**Deliverables**
- **gitingest** adapter (native Python import — the primary).
- **Repomix** and **code2prompt** adapters via `SubprocessConverter` (Node/Rust
  tools), with graceful "binary not found → install hint" behavior.
- Shared options: include/exclude globs, `.gitignore` respect, max file size,
  binary-file skip, token budget with a documented truncation strategy, per-directory
  token breakdown ("which folder is eating my context").
- Local path and remote Git URL support (shallow clone into a temp dir, cleaned up).

**Acceptance criteria**
- Fixture repo produces a single file with a directory tree and file contents.
- Token budget flag genuinely caps output, and what got dropped is reported.
- Missing `npx`/`repomix` yields a clear message, not a traceback.

**Sandbox verification**
```bash
uv run tokenfold repo tests/fixtures/sample_repo --backend gitingest --token-budget 5000
uv run tokenfold repo tests/fixtures/sample_repo --backend repomix    # expect graceful failure if Node absent
uv run tokenfold repo tests/fixtures/sample_repo --tree-tokens        # per-dir breakdown
uv run pytest -q tests/integration/test_repo.py
```

**Risks** — Subprocess argument injection with user-supplied paths; always use list
args, never `shell=True`. Temp-dir cleanup on failure paths.

**Exit gate:** all three adapters behave correctly whether or not their runtime is
installed; budget truncation verified by inspecting output.

---

### Phase 5 — Post-processing, formats, and measurement depth

**Goal:** the token-reduction toolkit proper — the layer that makes this more than a
converter aggregator.

**Deliverables**
- Post-processors: aggressive whitespace/boilerplate cleanup, heading
  normalization, image handling (drop / alt-text-only / keep), link handling
  (inline / reference / strip), duplicate-block removal, front-matter stripping.
- `formats/`: Markdown table ↔ CSV ↔ TOON ↔ JSON ↔ key-value encoders, so a user can
  test which serialization is cheapest *for their data*.
- **Chonkie** integration for chunking with token-aware sizes.
- `TokenMeter` extended to per-stage reporting: source → converted → each
  post-processor → final, so the user sees where savings actually came from.
- A `compare` command: one input, N backends and/or N formats, output a table of
  tokens + timing, optionally writing each variant to disk for eyeballing.

**Acceptance criteria**
- Per-stage token report is arithmetically consistent and matches direct tokenizer
  counts on each intermediate.
- TOON/CSV encoders round-trip tabular data losslessly (property-based tests).
- The docs are honest: **structure-preserving beats maximal stripping** for model
  accuracy, and format savings carry accuracy tradeoffs — state this in
  `docs/BENCHMARKS.md` with the `RESEARCH.md` sources, and default to conservative
  post-processing.

**Sandbox verification**
```bash
# Amended in Phase 7 (owner's decision, 2026-08-26). This line originally read
# `convert tests/fixtures/tables.pdf --format toon --show-stages`, and that
# command is deliberately not implemented. TOON encodes the JSON data model; a
# prose document is not that, so a whole-document TOON would be a shape nobody
# can read. The encoders re-serialise a *table*, which is what all of
# RESEARCH.md Category 7's evidence is about, and `compare --formats` is the
# equivalent. `OutputFormat` keeps its two members.
uv run tokenfold convert tests/fixtures/tables.pdf --show-stages
uv run tokenfold compare tests/fixtures/tables.pdf --formats markdown,csv,toon,json
uv run tokenfold compare tests/fixtures/report.docx --backends markitdown,docling,kreuzberg
uv run tokenfold compare tests/fixtures/data.xlsx --formats markdown,csv,toon,json
uv run pytest -q tests/unit/test_formats.py tests/unit/test_post.py
```

**Risks** — Over-aggressive defaults silently destroying document structure. Every
destructive post-processor is opt-in, and the GUI shows a diff.

**Exit gate:** `compare` produces a correct table verified against manual counts;
round-trip property tests pass.

---

### Phase 6 — Prompt compression (optional tier)

**Goal:** the advanced, off-by-default token reducer.

**Deliverables**
- **LLMLingua-2** adapter (CPU-feasible, MIT) behind the `compress` extra; model
  download handled explicitly with a size warning and a cache path.
- Optional Selective Context adapter.
- Compression exposed as a post-processor with a target ratio, and always reporting
  both the achieved ratio and a similarity/retention indicator.
- **Prominent warnings** in docs, CLI, and GUI: compression suits redundant RAG
  context, can degrade reasoning-heavy prompts, and must be evaluated on the user's
  own task. Default off.

**Acceptance criteria**
- Achieves a measurable ratio on a long fixture context and reports it accurately.
- First-run model download is explicit, resumable, and skippable; nothing downloads
  silently at import.
- Fully offline once cached.

**Sandbox verification**
```bash
uv sync --extra compress
uv run tokenfold compress tests/fixtures/long_context.md --ratio 0.5 --show-stages
uv run python -c "..."   # assert no network calls after cache warm
uv run pytest -q tests/integration/test_compress.py -m compress
```

**Risks** — Model download size and CI time; mark these tests optional. Transformers
version conflicts with Docling — this is exactly why they're separate extras.

**Exit gate:** ratio verified against direct token counts; offline-after-cache proven.

---

### Phase 7 — Isolation layer and license enforcement

**Goal:** make AGPL/GPL and non-Python tools usable without contaminating the
codebase, as a first-class, tested mechanism.

**Deliverables**
- `backends/isolated/` — hardened `SubprocessConverter`: binary discovery, version
  probe, argument construction, timeout + kill, temp-file lifecycle, stderr capture
  into `BackendFailed`, no `shell=True` anywhere.
- Adapters via subprocess: **PyMuPDF4LLM** (AGPL), **Pandoc** (GPL),
  **LibreOffice headless** (MPL), each with an install-hint message.
- An optional HTTP-service adapter mode (talk to a `docling-serve`-style container),
  proving the pattern for Phase 9's GPU backends.
- **License enforcement in code:** a test that asserts no AGPL/GPL package is
  importable from our process namespace, and that every registered backend declares
  a license tier. Fail CI if a copyleft package appears in a non-isolated adapter's
  imports.
- `docs/LICENSES.md` completed with the tiering rules and reasoning.

**Acceptance criteria**
- A copyleft backend works via subprocess and is never imported.
- The license test catches a deliberately introduced violation (write that test
  case and confirm it fails as intended, then revert).
- Subprocess timeout and cleanup verified, including on the failure path.

**Sandbox verification**
```bash
uv run tokenfold convert tests/fixtures/tables.pdf --backend pymupdf4llm
uv run tokenfold backends --show-licenses
uv run pytest -q tests/unit/test_license_isolation.py tests/unit/test_subprocess.py
uv run python -c "import sys, tokenfold; assert 'fitz' not in sys.modules"
```

**Risks** — Subprocess overhead per file makes batch slow; add a batch/persistent
mode if measurement shows it matters (measure first).

**Exit gate:** license isolation test suite green; at least one copyleft backend
functioning purely out of process.

---

### Phase 8 — GUI (FastAPI + NiceGUI)

**Goal:** the product a non-programmer can actually use.

**Stack decision (from `RESEARCH.md`):** NiceGUI over a FastAPI backend. Rationale
to record in `docs/ARCHITECTURE.md`: event-driven rather than Streamlit's
full-script-rerun model (which fights live batch progress and streaming token
counters); FastAPI in-process means the same app can expose an API and orchestrate
subprocess/service backends; NiceGUI `native` mode gives a desktop window without
leaving Python. A PySide6 shell remains a Phase 11 option for offline distribution.

**Deliverables**
- Layout: source panel (drag-and-drop files/folders, URL box, repo picker, text
  paste) · backend selector showing availability + license + CPU/GPU badge ·
  options panel (post-processors, format, tokenizer) · results panel.
- **The token panel is the centerpiece:** before → after, delta, percentage,
  per-stage breakdown, and optional cost estimate with user-supplied rates.
- Batch queue: multi-file, per-item status, cancel, resume, per-file and aggregate
  totals, background execution that never blocks the UI.
- Preview with rendered-Markdown / raw-source toggle and a before/after diff.
- Comparison view: one input, several backends, results side by side with tokens,
  timing, and output — the feature that sells the project.
- Export: single file, batch to folder, ZIP, copy-to-clipboard.
- Settings: tokenizer default, cache location, backend preference order, network
  policy, theme.
- Graceful degradation: unavailable backends greyed out with an install hint, never
  hidden and never crashing.
- `tokenfold gui` launches it; `--server` for LAN/headless use.

**Acceptance criteria**
- Every core CLI capability is reachable from the GUI.
- A 20-file batch runs with a responsive UI and correct aggregate totals.
- Backend failure surfaces as a readable, actionable message.
- Works with only the `core` extra installed (most backends simply show unavailable).

**Sandbox verification**
```bash
uv run tokenfold gui --port 8080 &
curl -sf localhost:8080 >/dev/null && echo "UI up"
uv run pytest -q tests/integration/test_gui_api.py   # exercise the FastAPI layer
# manual: drop the fixture folder in, run a batch, screenshot for the README
```
Test the API layer programmatically; use headless browser tests (Playwright) only
for the few flows worth the maintenance cost.

**Risks** — GUI logic creeping into the UI layer. Enforce: the GUI may only call
the public library API. A test that drives every GUI action through that same API
keeps the boundary honest.

**Exit gate:** batch run completed and inspected; screenshots captured for docs;
core-only install renders correctly.

---

### Phase 9 — Heavy backends (GPU tier, install-docs-only)

**Goal:** support the high-quality ML converters without ever putting them in our
dependency tree.

**Deliverables**
- Adapters for **Marker** (GPL + RAIL weights), **MinerU**, **olmOCR**, **Surya**
  (GPL), **DeepSeek-OCR**, **dots.ocr**, **Granite-Docling** — each via the isolation
  layer (separate venv, subprocess, or container HTTP), never a declared dependency.
- A `tokenfold doctor` command reporting what's installed, GPU availability, VRAM,
  and precise install instructions per backend.
- Optional `docker/` compose files, one service per heavy backend, with the adapter
  auto-detecting a running service.
- Honest documentation of hardware needs and the RAIL/GPL license conditions.
- **DeepSeek-OCR gets special treatment in the docs** — its optical context
  compression is the most on-theme token-reduction story in the whole project.
  Report our own observed compression on our own fixtures, cite the paper's numbers
  as the paper's numbers.

**Acceptance criteria**
- Every heavy adapter degrades cleanly to "unavailable + how to install" on a
  CPU-only machine.
- `tokenfold doctor` output is accurate on the sandbox.
- At least one heavy backend verified working if the sandbox has a GPU; if not,
  document that it is untested and say so plainly in `PROGRESS.md`.

**Sandbox verification**
```bash
uv run tokenfold doctor
uv run tokenfold backends --tier heavy
uv run pytest -q -m heavy   # expected: skipped without GPU, and that's a pass
```

**Risks** — Untestable in a CPU sandbox. Do not claim these work if you haven't run
them. Record them as "implemented, unverified — needs GPU" in `PROGRESS.md`.

**Exit gate:** CPU-only degradation verified; unverified-on-hardware items explicitly
flagged, not quietly marked done.

---

### Phase 10 — Benchmark harness (the article's original data)

**Goal:** produce our own measured evidence — the thing no existing project has.

**Deliverables**
- `benchmarks/` harness: run a corpus × backends × formats matrix, capture tokens
  (multiple tokenizers), wall time, peak memory, and failures.
- **Corpus**: synthetic and permissively-licensed material only, described in a
  manifest with provenance for each item. Categories: digital PDF, scanned PDF,
  two-column academic-style PDF, table-heavy report, DOCX with deep structure,
  PPTX, XLSX, boilerplate-heavy HTML, a code repo.
- **Fidelity scoring, not just token counts** — this is what makes the benchmark
  credible. Hand-labeled ground truth per item plus automated checks: heading
  hierarchy preserved, table cells recovered, reading order correct, content
  recall vs ground truth. Token savings without a fidelity axis is a meaningless
  metric and the article must not present it as one.
- Reproducible: `make benchmark` regenerates everything; results as CSV + JSON +
  Markdown tables committed under `benchmarks/results/<date>/`.
- `docs/BENCHMARKS.md` with method, corpus, results, and an explicit limitations
  section (hardware, sample size, tokenizer choice, what we could not test).

**Acceptance criteria**
- Full run completes unattended and is re-runnable by a third party.
- Results include failures and bad outputs, not just the wins.
- Every published number traces to a committed raw result file.

**Sandbox verification**
```bash
uv run python -m benchmarks.run --corpus benchmarks/corpus --out benchmarks/results/$(date +%F)
uv run python -m benchmarks.report benchmarks/results/$(date +%F)
uv run pytest -q tests/unit/test_benchmark_harness.py
```

**Risks** — The temptation to make our tool look good. The harness treats every
backend identically, and a result that contradicts `RESEARCH.md` gets reported as-is
with a note, not buried.

**Exit gate:** a complete result set committed; `docs/BENCHMARKS.md` written with
limitations; no unsourced claim anywhere in the repo.

---

### Phase 11 — Packaging, distribution, release

**Goal:** installable and runnable by someone who has never opened a terminal.

**Deliverables**
- PyPI publish workflow (trusted publishing), version via tags, `CHANGELOG.md`.
- `pipx`/`uv tool install` documented as the recommended path.
- Docker image (core) and compose profiles for heavy backends.
- Optional: PySide6 desktop shell + PyInstaller one-file builds for Windows/macOS/
  Linux, if owner wants offline distribution to non-technical users. Decide with the
  owner before starting — it's a meaningful maintenance commitment.
- Release checklist in `CONTRIBUTING.md`; smoke test that installs the published
  artifact in a clean container and runs one conversion.

**Acceptance criteria**
- Clean container: install from the built wheel, run a conversion, get correct output.
- Docker image runs the GUI and is reachable.
- Version, changelog, and tag agree.

**Sandbox verification**
```bash
uv build && ls dist/
docker run --rm -v "$PWD:/w" -w /w python:3.12-slim bash -c \
  "pip install dist/*.whl && tokenfold convert tests/fixtures/sample.docx"
docker build -t tokenfold . && docker run --rm -p 8080:8080 tokenfold gui --server
```

**Exit gate:** clean-container install verified end to end; v0.1.0 tagged.

---

### Phase 12 — Documentation completion and article support pack

**Goal:** the repo teaches itself, and the article has everything it needs.

**Deliverables**
- README finished: positioning, the sourced token-reduction case, backend matrix,
  GUI screenshots, quickstart, license tiering, comparison to existing projects
  (omniparse, docling-serve, MarkItDown GUI forks) and what we do differently.
- `docs/BACKENDS.md` complete with observed failure modes for every backend.
- `docs/ADDING_A_BACKEND.md` with a complete working example a contributor can copy.
- `docs/FAQ.md`: which backend for which format, why is X unavailable, GPU or not,
  is my data sent anywhere (no), license questions.
- **Article support pack** (`docs/article/`): the benchmark tables as
  copy-paste-ready Markdown, chart-generation scripts, a claims file mapping every
  factual statement to its source (ours or `RESEARCH.md`), and a
  "surprising findings" note from what we actually observed.
- Final `PROGRESS.md` pass: everything reconciled, deferred work listed with reasons.

**Exit gate:** a reader unfamiliar with the project can install it, convert a file,
add a backend, and reproduce the benchmark using only the docs.

---

## 3. Test fixtures (build in Phase 0)

Generate, never download copyrighted material. `scripts/make_fixtures.py` produces:

| Fixture | Purpose |
|---|---|
| `simple.pdf` | Baseline digital PDF |
| `tables.pdf` | Table fidelity |
| `twocolumn.pdf` | Reading order |
| `scanned.pdf` | Rasterized version of `simple.pdf` for the OCR path |
| `report.docx` | Nested headings, lists, footnotes |
| `deck.pptx` | Slides + speaker notes |
| `data.xlsx` | Multi-sheet tabular |
| `boilerplate.html` | Heavy nav/ads/scripts around a real article body |
| `article.html` | Clean article, extraction baseline |
| `long_context.md` | ~20k tokens of redundant prose for compression tests |
| `sample_repo/` | Small git repo: code, README, binary file, `.gitignore`, nested dirs |
| `unicode.docx` | Urdu/Arabic/CJK/emoji — encoding regressions |
| `corrupt.pdf` | Truncated file — error-path testing |

Each fixture needs a ground-truth companion (expected headings, table cell count,
article word count) so tests assert on structure, not brittle byte equality.

---

## 4. Cross-cutting standards

**Testing.** Unit tests for core logic (fast, no I/O, always run). Integration tests
per backend, marked and auto-skipped when the dep is missing. Golden-structure tests
for conversion output. Property tests for format round-trips. A protocol-conformance
suite every backend must pass. Coverage target ≥85% on `src/tokenfold/core` and
`src/tokenfold/tokens`; adapters can be lower where they're thin wrappers.

**Code style.** Ruff-enforced. Full type hints; mypy strict on `core`/`tokens`.
Google-style docstrings on every public symbol. No bare `except`. No mutable default
args. Logging via `logging`, never `print` outside the CLI presentation layer.

**Security.** Never `shell=True`. Validate and normalize all user paths. Cap file
sizes and subprocess runtime. Treat every input document as hostile — several
backends shell out to binaries. Default-deny on network; URL fetching is explicit.
Never log full document contents at INFO.

**Performance.** Measure before optimizing. Batch runs should parallelize across
files (process pool for subprocess backends, thread pool for I/O-bound). Cache
availability probes and tokenizer instances. Stream large files rather than loading
whole.

**Git.** Conventional commits. One phase ≈ one PR-sized branch, or clean sequential
commits on main for a solo build. Tag each completed phase (`phase-3-complete`) so
the owner can diff progress.

---

## 5. Definition of Done (applies to every phase)

A phase is done when **all** of these hold:

1. Code complete — no stubs, no TODO-to-implement, tests written alongside.
2. Full suite green in the sandbox: ruff, mypy, pytest, plus the clean-core-install check.
3. The phase's smoke scenario executed **and its output read and judged correct** —
   not just a zero exit code.
4. Docs updated in the same change: architecture, backends, README as applicable.
5. `PROGRESS.md` updated: phase table, verification log entry with real command
   output, backend status table, decisions, open questions.
6. Nothing previously working is broken — verified by the full suite, not assumed.
7. Anything implemented but unverifiable in this environment (GPU backends) is
   explicitly flagged as unverified rather than marked complete.
8. Committed and tagged.

---

## 6. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Dependency conflicts (torch/transformers/pydantic/numpy) | High | Strict extras tiering; no heavy pins in core; clean-core CI job on every commit |
| Copyleft contamination | High (legal) | Subprocess-only isolation + an enforcement test in CI |
| Ecosystem churn (repos move, licenses change) | Medium | Verify at implementation time; record corrections in PROGRESS.md Decisions |
| Scope creep into RAG/agent territory | Medium | Non-goals in §0; check every new idea against them |
| Untestable GPU backends | Medium | Mark unverified honestly; ship CPU-first |
| Over-aggressive post-processing damaging output | Medium | Destructive steps opt-in; diff view in GUI; conservative defaults |
| Benchmark bias | Medium (credibility) | Identical treatment per backend; publish failures; commit raw data |
| GUI logic leaking out of the library | Low | GUI calls only the public API; enforced by test |

---

## 7. Suggested sequencing for a solo build

Phases 0–2 give a genuinely useful CLI. Phases 3–5 make it distinctive. Phase 8 makes
it adoptable. Phase 10 makes the article worth writing. If time is short, a defensible
v0.1 is **Phases 0–5 + 7 + 8**, with 6, 9, 10 following. Do not ship publicly without
Phase 7 — the license isolation is not optional.
