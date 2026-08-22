# Progress

_Last updated: 2026-08-22 by Claude Code_

## Status at a glance

| Phase | Name | Status | Exit gate |
|-------|------|--------|-----------|
| 0 | Scaffolding and toolchain | ✅ Complete | passed 2026-08-20 |
| 1 | Core architecture | ✅ Complete | passed 2026-08-20 |
| 2 | Document backends (light tier) | ✅ Complete, merged to `Main` | passed 2026-08-21 |
| 3 | Web backends | ⬜ Not started — assigned, see `docs/prompts/PHASE_3_AND_4.md` | — |
| 4 | Repository backends | ⬜ Not started — assigned, see `docs/prompts/PHASE_3_AND_4.md` | — |
| 5 | Post-processing, formats, measurement depth | ⬜ Not started | — |
| 6 | Prompt compression (optional tier) | ⬜ Not started | — |
| 7 | Isolation layer and license enforcement | ⬜ Not started | — |
| 8 | GUI (FastAPI + NiceGUI) | ⬜ Not started | — |
| 9 | Heavy backends (GPU tier, install-docs-only) | ⬜ Not started | — |
| 10 | Benchmark harness | ⬜ Not started | — |
| 11 | Packaging, distribution, release | ⬜ Not started | — |
| 12 | Documentation completion and article support pack | ⬜ Not started | — |

## Current phase: 2 — Document backends (complete)

**Goal:** real document conversion, CPU-only, permissive licences.

**Phase 2's content ends at commit `a9d36be`.** The first commit proven
green across all 23 CI jobs was **`2e675f5`** (run 12), after three real
failures on run 11 that none of the local checks could have caught — see the
verification log.

**Built:**

- `backends/documents/` — five adapters, plus `_common.py` holding the
  behaviour all five must share.
  - `pdfplumber` (MIT, **core**) — the only backend in the tier that recovers a
    bordered PDF table as a Markdown table. Splices rendered tables into the
    page text in document order; warns when a page looks multi-column.
  - `pypdf` (BSD-3-Clause, **core**) — plain text, correct multi-column reading
    order, no required dependencies. The last-resort member of the PDF chain.
  - `markitdown` (MIT, `documents`) — breadth; the only backend that keeps PPTX
    speaker notes.
  - `kreuzberg` (MIT, `documents`, pinned `<5`) — Rust core, fast, good reading
    order, infers headings from PDFs.
  - `docling` (MIT, `docling`) — best document structure; lazily imported
    because it resolves to 122 packages and about 5.2 GB.
- `core/preferences.py` — the per-format backend ranking, with the evidence for
  every number recorded beside it.
- `core/registry.py` — `candidates()` returns the ordered chain; `select()` is
  its head; ordering is now per format.
- `core/pipeline.py` — walks the chain, records every `BackendAttempt`, warns
  on a fallback, and warns that a binary source's before-count is not a token
  saving.
- `core/models.py` — `BackendAttempt`, `ConversionResult.attempts`,
  `ConvertOptions.fallback` (all additive).
- `cli/` — `--no-fallback`, an `attempts:` line when a fallback happened, the
  chain in `--json`.
- `tests/conftest.py` — the `@pytest.mark.requires("markitdown")` mechanism the
  plan asks for.
- `docs/BACKENDS.md` — a section per backend, with observed failure modes
  quoted from real output.
- 542 tests passing locally (537 without docling installed), 23 skipped.

**Acceptance criteria, one by one:**

| # | Criterion | Result |
|---|---|---|
| 1 | Every fixture format converts through at least one backend | ✅ **Observed.** pdf, docx, pptx, xlsx all converted and the Markdown read. Command output in the verification log. |
| 2 | Table-bearing PDF: at least one backend preserves the table as a Markdown table, verified by reading the output | ✅ **Observed.** pdfplumber recovers all **35 cells** of `tables.pdf` as a real Markdown table, header row correct, first column in the right order, spliced between the introduction and the footnote. Read, not inferred from exit code. |
| 3 | Fallback chain demonstrably works when the primary backend is uninstalled | ✅ **Observed.** Uninstalled markitdown; `report.docx` and `deck.pptx` converted through kreuzberg instead. Also observed for the *failure* path: an empty HTML file fails `markdownify_html` and falls through to `markitdown`, with `attempts: markdownify_html (failed) -> markitdown` in the report. |
| 4 | No core-install regression | ✅ **Verified in CI**, all nine cells (3 OS × 3 Python). Docling stays behind its extra with a lazy import; `import tokenmill` still pulls in zero third-party modules. |

**What Phase 2 does *not* do**, so nobody reads more into it than is there:

- **No OCR.** `scanned.pdf` has no text layer and *every* backend here returns
  an empty document for it. All of them warn; none of them fails. Phase 9.
- **No layout model.** pdfplumber interleaves two-column pages. The adapter
  detects a column gutter and warns, which is as far as an adapter should go —
  reordering a page is a layout engine.
- **Docling's PDF path is unverified.** See below.

**Blocked on:** nothing. Two items need an owner decision — Open questions 1
and 2.

## Previous phase: 1 — Core architecture (complete)

**Goal:** the plugin system and token measurement working end to end, proven by
two deliberately trivial backends.

**Phase 1's code and docs end at commit `e18b3d8`.** The exit gate was only
genuinely proven later: CI had never run, and the first green run across all
23 jobs — every platform, every Python version, and real tokenizers — was at
**`3aa6e59`**, which is the commit to treat as Phase 1 complete. It has stayed
green since. Tags cannot be pushed from these sessions — see Deferred work.

**Built:**

- `core/models.py` — `Source`, `ConvertOptions`, `ConversionResult`,
  `BackendInfo`, `TokenCount`, `StageCount`, `Availability` and the enums, all
  frozen dataclasses. Licence policy enforced in `BackendInfo.__post_init__`.
- `core/errors.py` — the plan's §1.4 taxonomy, plus `TokenizerError` and
  `ConfigError` under a common `TokenmillError` root. Every error carries an
  optional actionable hint.
- `core/protocol.py` — the three-method `Converter` protocol and
  `BaseConverter` (availability caching, size guard, timing, warning
  collection, error wrapping).
- `core/registry.py` — cached entry-point discovery, lookup by id/domain/format,
  availability filtering, documented deterministic selection order, and broken
  plugins degraded to unavailable rather than propagated.
- `core/pipeline.py` — converter, ordered post-processor chain, per-stage
  measurement.
- `core/config.py` — defaults → TOML file → `TOKENMILL_*` env → CLI flags.
- `tokens/` — tiktoken adapter, HuggingFace adapter (lazy, behind the new
  `tokenizers` extra), a download-free `bytes` unit counter, a provider registry,
  and `TokenMeter`.
- `post/` — `PostProcessor` protocol, registry and chain ordering, plus
  `normalize_whitespace` (non-destructive, default) and `links` (destructive,
  opt-in).
- `backends/` — `plaintext` and `markdownify_html`.
- `cli/` — `tokenmill convert`, `backends`, `tokens`.
- 325 tests passing, 11 skipped (all `network`-marked). 95% coverage overall;
  `core` 99.4%, `tokens` 88.5% by statement, both over the plan's 85% target.
- `docs/ARCHITECTURE.md` and `docs/ADDING_A_BACKEND.md` written, README,
  CHANGELOG and CONTRIBUTING updated.

**Acceptance criteria, one by one:**

| # | Criterion | Result |
|---|---|---|
| 1 | A backend can be added by dropping in a module + entry point, no core edits | ✅ **Observed.** Built a separate distribution (`tokenmill-csvtable`) outside the repo, straight from the code blocks in `ADDING_A_BACKEND.md`, installed it, and it appeared in `tokenmill backends` and converted a file. No tokenmill file was touched. |
| 2 | Registry lists backends with correct availability when a dep is absent | ✅ **Observed.** Unit-tested against a backend whose probe reports a missing dependency, and end-to-end at the CLI with a plugin that raises on import. |
| 3 | Token counts match a hand-verified tiktoken result on a known string | ✅ **Verified in CI** (run 3, commit `3aa6e59`, `11 passed`). `"hello world"` is **2 tokens** under `o200k_base`, as written. Still not reproducible in this sandbox — the proxy denies tiktoken's vocabulary host — so it is CI-verified rather than locally observed, and the CI job that proves it is blocking so it cannot quietly stop running. |
| 4 | `tokenmill convert tests/fixtures/boilerplate.html` returns Markdown and a real before/after count | ✅ **Met.** Markdown: observed here, read and judged correct. Before/after in UTF-8 bytes: observed here (12,481 → 6,802, −45.5%). Before/after in **real `o200k_base` tokens**: verified in CI by `test_converting_the_boilerplate_fixture_reports_a_real_reduction`, which asserts both counts carry the `o200k_base` id and that the reduction is a genuine fraction. |
| 5 | *(exit gate)* Protocol-conformance test passes for both reference backends | ✅ **Observed.** 16 conformance checks per backend, parametrised over the installed entry points rather than a hard-coded list. |
| 6 | *(exit gate)* A deliberately broken backend is reported as unavailable rather than crashing the CLI | ✅ **Observed.** Installed a real `.dist-info` whose entry point raises `ImportError`; the CLI listed it as "failed to load", kept working, and exited 0. |
| 7 | *(exit gate)* Architecture docs committed | ✅ Both written and committed. |

**What Phase 1 does *not* do**, so nobody reads more into it than is there:

`markdownify_html` converts HTML markup faithfully. It does **not** strip
boilerplate — after conversion the cookie banner, the five-section nav, both
ad slots, the trending rail and the footer are all still present, and a test
asserts they are. The 45.5% reduction it achieves on `boilerplate.html` is
markup, script and style characters going away. It is **not** evidence for the
70–90% boilerplate-removal figures in `RESEARCH.md` Category 7; that is a
different operation and it arrives with Trafilatura in Phase 3.

**Blocked on:** nothing. Three items need an owner decision — Open questions 1,
2 and 3.

## Environment

Verified in the sandbox on 2026-08-20:

| Thing | Found |
|---|---|
| OS | Ubuntu 24.04.4 LTS, Linux 6.18.5, x86_64, 4 cores, 15 GiB RAM |
| Python | 3.11.15 (`/usr/local/bin/python3`) — only 3.11 present locally |
| uv | 0.8.17 |
| git | 2.43.0 |
| node | v22.22.2 (relevant later: Repomix is a Node tool) |
| GPU | none — CPU only. Phase 9 heavy backends will be **unverifiable** here |
| Network | via a policy-enforcing egress proxy; **not** unrestricted (see below) |

**Network restrictions found.** Outbound HTTPS goes through an allow-listing
proxy. Reachable: `pypi.org`, `files.pythonhosted.org`,
`raw.githubusercontent.com`. **Denied with 403 at the proxy:**

- `openaipublic.blob.core.windows.net` — this is where **tiktoken downloads its
  BPE files from**, so `tiktoken.get_encoding("o200k_base")` fails in this
  sandbox.
- `huggingface.co` — so HuggingFace tokenizers and any model download also fail.

Nothing in Phase 0 depends on either, so the gate is unaffected. Phase 1 does:
token counting is the product's core feature. This is Open question 1. I did not
route around the denial (e.g. by fetching the same BPE file from a GitHub
mirror), because that is an organisation egress policy, not a bug.

**Re-probed at the start of Phase 1 (2026-08-20): both hosts are still denied**,
with the gateway itself logging the 403s. See the verification log entry
"Blocked-host re-probe". The Phase 1 token layer was designed around this — the
arithmetic is testable offline, and everything needing a real vocabulary is
behind the `network` marker.

**Re-probed again at the start of Phase 2 (2026-08-21): still denied**, both of
them, unchanged. Phase 2 added a third consequence, which was probed rather than
assumed: **Docling downloads its layout models from `huggingface.co`**, so its
PDF path cannot run here either. Its Office paths turn out not to need any
model and do run — see the verification log.

**One more environment defect, found by running things.** This container's
`/dev/null` is not a device. It is a 48-byte regular file containing a shell
start-up error message (`/bin/bash: line 1: unalias: unsetenv: not found`).
`scripts/make_fixtures.py` isolated git's config with
`GIT_CONFIG_GLOBAL=os.devnull`, and git refused it —
`fatal: bad config line 1 in file /dev/null` — which broke fixture
regeneration for a reason with nothing to do with fixtures. I could not repair
the device node (the sandbox denies `mknod` and `truncate` on it, reasonably),
so the generator now points git's config lookup at a path that does not exist,
which reads as an empty config on every platform. `--check` still reports 22
files reproduced byte-for-byte, so the corpus is unchanged. **Worth flagging to
the owner**: anything else in these sessions that writes to `/dev/null`
expecting it to discard is instead appending to a file.

## Verification log

Append-only. One entry per verification run.

### 2026-08-20 — Name availability check

- Command: `curl -s https://pypi.org/pypi/tokenfold/json` (plus 60 candidate
  names probed the same way)
- Result: **`tokenfold` is TAKEN on PyPI.** Live project, version 0.4.0, last
  uploaded 2026-08-15, summary *"Token-compression toolkit for LLM payloads
  (Python binding over the tokenfold-core Rust crate)"*, Apache-2.0, 7 releases
  since 2026-07-14, upstream `snchimata/tokenfold`; its README also claims the
  npm package `tokenfold` and the crate `tokenfold-core`. It is in **our exact
  niche**, so `pip install tokenfold` could never have been ours.
- Command: `curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/<name>/json`
- Result: free on PyPI — `tokenmill`, `tokensmith`, `tokenpare`, `tokenwring`,
  `contextmill`, `markfold`, `slimdoc`, `tokenforge`, and others. Taken —
  `tokenpress`, `tokenlens`, `tokenwise`, `tokentrim`, `tokenbudget`,
  `tokenscope`, `tokencut`, `leanctx`, `contextforge`, `ctxforge`.
- Command: `curl -s -o /dev/null -w "%{http_code}" https://registry.npmjs.org/<name>`
- Result: `tokenmill` 404 (free), `tokenpare` 404, `tokenwring` 404,
  `tokensmith` 200 (taken).
- Note: GitHub name availability could **not** be checked programmatically —
  this session's GitHub API access is scoped to the project repository, and
  unauthenticated `github.com` requests are blocked by the proxy. The owner
  controls the `RSD-Studio` namespace, so this is not a practical constraint.
- Verdict: rename required. Owner chose `tokenmill`.

### 2026-08-20 — Phase 0 exit gate

Run from a freshly recreated virtualenv (`rm -rf .venv && uv venv && uv sync
--extra dev --extra fixtures`).

- Command: `uv run ruff check .`
- Result: `All checks passed!`

- Command: `uv run ruff format --check .`
- Result: `15 files already formatted`

- Command: `uv run mypy src/`
- Result: `Success: no issues found in 1 source file`

- Command: `uv run mypy` (strict, over `src` + `scripts` + `tests`)
- Result: `Success: no issues found in 5 source files`

- Command: `uv run pytest -q --cov=tokenmill`
- Result:
  ```
  ...........................                                              [100%]
  Name                        Stmts   Miss Branch BrPart  Cover
  -------------------------------------------------------------
  src/tokenmill/__init__.py       3      0      0      0   100%
  -------------------------------------------------------------
  TOTAL                           3      0      0      0   100%
  27 passed in 0.23s
  ```
  (Coverage is 100% of 3 statements because Phase 0 ships no product logic. The
  meaningful work is in the 27 tests, which validate the corpus.)

- Command: `uv run python scripts/make_fixtures.py`
- Result: `Done: 23 files`, all 13 planned fixtures built.

- Command: `uv run python scripts/make_fixtures.py --check`
- Result: `OK: 23 files reproduced byte-for-byte`

- Command: `uv run python -c "import tokenmill, sys; print(tokenmill.__version__, sys.version)"`
- Result: `0.0.0 3.11.15 (main, Mar  3 2026, 09:26:23) [GCC 13.3.0]`

- Command: `uv pip install .` into an empty throwaway venv (no extras), then
  import from outside the source tree
- Result: `version: 0.0.0`, and `uv pip list` shows exactly one package —
  `tokenmill 0.0.0`. Wall time **0.49 s**, comfortably inside the plan's
  "under a minute on a clean machine" requirement. Nothing else was pulled in,
  which is the whole point of the core tier.

**Fixtures inspected, not merely generated:**

- `simple.pdf` — 2 pages, 3,420 bytes. Text extracted via pypdfium2: title plus
  `Introduction` / `Method` / `Results` / `Discussion` headings all present,
  body prose intact across the page break. Correct.
- `tables.pdf` — 1 page. All 35 table cells (7 rows × 5 columns) extracted in
  row order, header row included. Correct.
- `twocolumn.pdf` — 1 page, 2 frames. Extracted text contains `ORDERMARK 01`
  through `ORDERMARK 12` **in ascending order**, confirming the sentinels encode
  a checkable reading order rather than being interleaved by scan line. Correct.
- `scanned.pdf` — 2 pages, 81 KB. Text extraction returns **0 characters on both
  pages**, i.e. no text layer, which is what the OCR path needs. Page 1 rendered
  to PNG and viewed: fully legible, correctly laid out. Correct.
- `corrupt.pdf` — 1,140 bytes, retains the `%PDF-` magic, no `%%EOF` trailer.
  Correct for error-path testing.
- `report.docx` — inspected via python-docx: `Title`, five `Heading 1`, four
  `Heading 2`, three `List Bullet`, three `List Number`, one `List Number 2`
  (nested), and one 4×3 `Table Grid`. Correct.
- `unicode.docx` — all ten scripts round-tripped intact when read back: Urdu,
  Arabic, Chinese, Japanese, Korean, Russian, Hindi, Greek, emoji (including a
  ZWJ family sequence and a regional-indicator flag) and mathematical symbols.
  Correct.
- `deck.pptx` — 5 slides. Titles, bullet levels (0 and 1) and speaker notes on
  4 of 5 slides all read back correctly; slide 5 is deliberately title-less.
  Correct.
- `data.xlsx` — 3 sheets read back with expected dimensions
  (`backends` 7×5, `corpus` 5×4, `totals` 4×2) and the `=AVERAGE(backends!E2:E7)`
  formula preserved. Correct.
- `article.html` / `boilerplate.html` — 3,560 vs 12,481 bytes, a 3.5× ratio. The
  article body is byte-identical between them; the difference is entirely
  cookie banner, five-section nav (repeated in the footer), two ad slots, a
  newsletter modal, a trending rail, a social rail and two inline scripts. A
  test asserts every `<p>` in the clean file appears verbatim in the noisy one.
  This pairing is what makes the Phase 3 measurement attributable.
- `long_context.md` — 79,255 characters, 12,312 words, 42 passages × 6
  restatements, with the needle fact `RSD-TOKENMILL-4417` appearing exactly
  twice. Correct.
- `sample_repo/` — real git repository, `main` branch, one commit with pinned
  author/committer dates so the commit hash is stable. 8 tracked files across
  `src/`, `tests/`, `docs/`, `assets/`, plus a `.gitignore`d `secrets.env`
  holding a sentinel string that repo-ingestion backends must never leak.
  Verified that deleting `.git` and letting the pytest fixture rebuild it
  reproduces exactly the commit hash recorded in `ground_truth.json`, and that
  a simulated fresh clone contains the files rather than an empty directory.

**Verdict: PASS**

**Bugs found and fixed during verification** (each was caught by running things,
not by reading them):

1. `data.xlsx` was not reproducible — openpyxl overwrites `dcterms:modified`
   with the save time regardless of what is set on `workbook.properties`. Fixed
   by rewriting the date fields inside `docProps/core.xml` during OOXML
   normalisation.
2. `boilerplate.html` used the `&copy;` entity, so the boilerplate marker
   `© 2026 Example Media Group` was not literally present in the source. Caught
   by `test_boilerplate_html_wraps_the_same_article`. Fixed by emitting the
   literal character, so the marker is checkable in raw HTML and in extracted
   Markdown alike.
3. pytest collected `tests/fixtures/sample_repo/tests/test_core.py` and failed
   at import. The fixture repo is *data*, not our test suite; now excluded from
   pytest, mypy and ruff.
4. The first version of the "core install pulls in nothing" test compared
   against `sys.stdlib_module_names` and tripped on coverage's `sitecustomize`.
   Rewritten to compare a before/after `sys.modules` delta, which is what the
   test actually means.
5. A comment beginning `# noqa justification: ...` was parsed by ruff as a
   blanket `noqa` directive. Reworded.
6. **`sample_repo/` was committed as a gitlink.** Because it is a real git
   repository, `git add` stored a submodule reference (mode 160000) instead of
   the files, so a fresh clone would have received an *empty* `sample_repo/` and
   every Phase 4 repo-backend test would have silently skipped. Caught by
   inspecting `git status` output rather than trusting the commit. A
   `.gitignore` entry does not help — git treats a nested `.git` as a submodule
   boundary before consulting ignore rules. Fixed by committing the working
   files only and materialising `.git` on demand (see Decisions), and a
   regression test now asserts no mode-160000 entry exists under
   `tests/fixtures/`. The test was confirmed to fail against the bad state
   before the fix was applied.

### 2026-08-20 — Blocked-host re-probe (start of Phase 1)

Re-probed the two hosts Phase 0 found denied, as instructed, before designing
the token layer.

- Command: `curl -sS -o /dev/null -w '%{http_code}\n' --max-time 25 "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"`
- Result: `curl: (56) CONNECT tunnel failed, response 403`
- Command: `curl -sS -o /dev/null -w '%{http_code}\n' --max-time 25 "https://huggingface.co/gpt2/resolve/main/tokenizer.json"`
- Result: `curl: (56) CONNECT tunnel failed, response 403`
- Command: `curl -sS "$HTTPS_PROXY/__agentproxy/status"`
- Result: both denials logged by the gateway itself —
  `{"kind":"connect_rejected","detail":"gateway answered 403 to CONNECT (policy denial or upstream failure)","host":"openaipublic.blob.core.windows.net:443"}`
  and the same for `huggingface.co:443`.
- Also confirmed reachable: `pypi.org` (200), `files.pythonhosted.org` (200),
  `raw.githubusercontent.com` (301).

**Verdict: still blocked, unchanged from Phase 0.** Proceeded on the owner's
fallback (b): the token layer is designed so its arithmetic is testable without
a download, and every test that needs a real BPE vocabulary is behind the
`network` marker. I did not route around the denial.

### 2026-08-20 — Phase 1 exit gate

Run from a freshly recreated virtualenv (`rm -rf .venv && uv venv && uv sync
--extra dev --extra fixtures`).

- Command: `uv run ruff check .`
- Result: `All checks passed!`

- Command: `uv run ruff format --check .`
- Result: `57 files already formatted`

- Command: `uv run mypy` (strict, over `src` + `scripts` + `tests`)
- Result: `Success: no issues found in 44 source files`

- Command: `uv run python scripts/make_fixtures.py --check`
- Result: `OK: 23 files reproduced byte-for-byte`

- Command: `uv run pytest -q --cov=tokenmill`
- Result: `325 passed, 11 skipped in 4.74s`, `TOTAL 1363 stmts, 66 miss, 95%`.
  The 11 skips are the whole of `tests/unit/test_tokens_network.py`, reported as
  `needs real network access (a tokenizer vocabulary download); run with -m network`.
  Per-package statement coverage, against the plan's ≥85% target on `core` and
  `tokens`:

  | Package | Covered | Coverage |
  |---|---|---|
  | `core` | 621/625 | **99.4%** |
  | `tokens` | 216/244 | **88.5%** |
  | `post` | 196/202 | 97.0% |
  | `cli` | 198/219 | 90.4% |
  | `backends` | 46/53 | 86.8% |

  `tokens` is the lowest of the two targets because `tiktoken_adapter.py`
  (58%) and `hf_adapter.py` (76%) contain the vocabulary-loading paths that
  cannot run here. Those lines are exactly what the `network`-marked tests
  cover, so the figure should rise in CI.

**Smoke scenario, exactly as the plan specifies it:**

- Command: `uv run tokenmill backends --all`
- Result:
  ```
  id                domains  license     tier        isolation   availability
  ----------------  -------  ----------  ----------  ----------  ------------
  markdownify_html  web      MIT         permissive  in-process  available
  plaintext         text     Apache-2.0  permissive  in-process  available
  ```

- Command: `uv run tokenmill convert tests/fixtures/boilerplate.html --tokenizer o200k_base`
- Result: **exit 0**, Markdown on stdout, and on stderr:
  ```
  source:   boilerplate.html
  backend:  markdownify_html
  format:   markdown
  duration: 564 ms
  post:     normalize_whitespace
  tokens:   not measured — see warnings below

  warning:  token counting unavailable (could not load the 'o200k_base'
  vocabulary: ProxyError: HTTPSConnectionPool(host='openaipublic.blob.core.windows.net',
  port=443): Max retries exceeded with url: /encodings/o200k_base.tiktoken
  (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection
  failed: 403 Forbidden'))) (tiktoken downloads its vocabulary on first use; set
  TIKTOKEN_CACHE_DIR to a directory populated on a networked machine to use it
  offline)); character counts are exact
  ```
  This is the designed behaviour, not a failure: the document is produced, the
  count is honestly absent, and the warning says exactly why.

- Command: `uv run tokenmill tokens tests/fixtures/boilerplate.html`
- Result: **exit 1**:
  ```
  error: could not load the 'o200k_base' vocabulary: ProxyError: ... 403 Forbidden
  hint:  tiktoken downloads its vocabulary on first use; set TIKTOKEN_CACHE_DIR
         to a directory populated on a networked machine to use it offline
  ```
  Also designed: counting is this command's entire job, so it must fail rather
  than print nothing useful.

**The same two commands with the download-free tokenizer**, so the measurement
path itself could be observed end to end:

- Command: `uv run tokenmill convert tests/fixtures/boilerplate.html --tokenizer bytes --show-stages -o /tmp/bp.md`
- Result:
  ```
  source:   boilerplate.html
  backend:  markdownify_html
  format:   markdown
  duration: 90 ms
  post:     normalize_whitespace
  tokens:   12,481 -> 6,802  (-45.5%, bytes)

  stage                 chars   tokens  change
  --------------------  ------  ------  ------
  source                12,472  12,481  -
  convert               6,800   6,809   -45.4%
  normalize_whitespace  6,793   6,802   -0.1%
  ```

- Command: `uv run tokenmill tokens tests/fixtures/boilerplate.html --tokenizer bytes`
- Result:
  ```
  source            characters  UTF-8 bytes  tokenizer
  ----------------  ----------  -----------  ---------
  boilerplate.html  12,472      12,481       bytes
  note:  'bytes' counts UTF-8 bytes, not model tokens; do not quote this as a token count
  ```

**These are byte counts, not token counts.** They demonstrate that the registry,
the pipeline, the post-processor chain, `TokenMeter`, the per-stage accounting
and the CLI's rendering all work together on real input. They say nothing about
what a model would charge.

**The emitted Markdown, read rather than assumed** (`/tmp/bp.md`, 6,793 chars):

- **Headings — correct.** ATX throughout: `# Why Your Context Window Is Mostly
  Navigation Menus`, then `## Where the tokens actually go`, `## The
  misattributed win`, `## When extraction does not help`, `## A rule worth
  remembering`, `## Summary table`, and the sidebar `### Trending right now` /
  `### Subscribe to our newsletter`. All six of the manifest's
  `expected_headings` are present at the right level.
- **Article body — intact.** All seven paragraphs present and complete, prose
  unbroken. Both of the manifest's `must_contain` sentences survive.
- **Table — preserved.** The 7×5 summary table came through as a real Markdown
  table, header row, separator row and all six data rows, `markitdown` through
  `marker`, with the licence and pages/sec columns aligned to the right rows.
- **Scripts and styles — gone.** No `<script`, no `gtag(`, no `function`
  anywhere in the output. No HTML tags of any kind survive.
- **Nav and ads — still there, and that is correct for this backend.** Grepped
  for each of the manifest's `boilerplate_markers_must_be_absent` and found every
  one: `847 partners`, `Accept all cookies`, `SPONSORED` (×2),
  `Trending right now`, `Subscribe to our newsletter`,
  `© 2026 Example Media Group`, `Crosswords` (×2 — nav and footer). The
  five-section navigation menu is reproduced as a nested bullet list.

  This is the honest answer to "did the nav and ads go?": **no.**
  `markdownify_html` is a markup converter, not an extractor. Removing that
  furniture is Trafilatura's job in Phase 3. An integration test now asserts the
  markers are still present, so when Phase 3 lands, the difference is measurable
  rather than asserted.

- **Did the token count change plausibly?** Yes, and for the checkable reason.
  12,481 → 6,802 bytes is −45.5%, and the drop happens almost entirely at the
  `convert` stage (−45.4%), with whitespace normalisation adding −0.1%. Running
  the clean `article.html` — which shares a byte-identical body with the noisy
  file but carries far less markup — through the same backend gives only −18.1%.
  Same body, same converter, less markup, less saving. That is what confirms the
  reduction is markup removal rather than anything else, and it is the same point
  `RESEARCH.md` Category 7 makes about misattributing the win to Markdown syntax.

**Exit gate item: a deliberately broken backend.**

Installed a real distribution — a `brokenmill-0.1.0.dist-info` with an
`entry_points.txt` registering `brokenmill = brokenmill:BrokenConverter`, where
importing `brokenmill` raises `ImportError` — onto `PYTHONPATH`, which is the
path a user's broken `pip install` actually takes.

- Command: `PYTHONPATH=<plugin> uv run tokenmill backends --all`
- Result: **exit 0**
  ```
  WARNING tokenmill.core.registry: backend plugin 'brokenmill' failed to load: No module named 'definitely_not_installed'
  id                domains  license     tier        isolation   availability
  ----------------  -------  ----------  ----------  ----------  ---------------------------------------------------------
  markdownify_html  web      MIT         permissive  in-process  available
  plaintext         text     Apache-2.0  permissive  in-process  available
  brokenmill        ?        ?           ?           ?           failed to load: ImportError: No module named 'definitely_not_installed'
  ```

- Command: `PYTHONPATH=<plugin> uv run tokenmill convert tests/fixtures/boilerplate.html --tokenizer bytes`
- Result: **exit 0**, `tokens: 12,481 -> 6,802 (-45.5%, bytes)` — the working
  backends are entirely unaffected.

- Command: `PYTHONPATH=<plugin> uv run tokenmill convert ... --backend brokenmill`
- Result: **exit 1**, `error: backend 'brokenmill' failed to load: ImportError:
  No module named 'definitely_not_installed'` with the hint
  `this backend's plugin failed to load; report it to its author`. No traceback.

**Exit gate item: adding a backend with no core edits.**

Built `tokenmill-csvtable` outside the repository **by extracting the code blocks
from `docs/ADDING_A_BACKEND.md`**, so what was tested is literally what the
tutorial says.

- Command: `uv pip install --no-deps <path>/tokenmill-csvtable` then `uv run tokenmill backends`
- Result:
  ```
  id                domains    license     tier        isolation   availability
  ----------------  ---------  ----------  ----------  ----------  ------------
  csvtable          documents  MIT         permissive  in-process  available
  markdownify_html  web        MIT         permissive  in-process  available
  plaintext         text       Apache-2.0  permissive  in-process  available
  ```
- Command: `tokenmill convert data.csv --tokenizer bytes`
- Result: a correct Markdown table, `backend: csvtable`,
  `tokens: 62 -> 106 (+71.0%, bytes)`.
- Command: `pytest tests/` (the tutorial's own test file)
- Result: `5 passed`
- Command: `pytest tests/unit/test_protocol.py -q`
- Result: `49 passed, 3 skipped` — the conformance suite picked the third-party
  backend up automatically, applying 16 checks to it without anyone adding it to
  a list. (The 3 skips were "no plausible sample for csvtable"; CSV and TSV
  samples have since been added to the suite, and it is now `52 passed`.)

**No tokenmill source file was modified at any point.** That is acceptance
criterion 1, observed rather than argued.

**Clean core install** (the standing guard):

- Command: `uv pip install <repo>` into an empty throwaway venv, no extras
- Result: **0.99 s**, 19 dependencies plus `tokenmill 0.1.0`. Import from
  outside the source tree: `0.1.0 3.11.15`. `tokenmill backends` runs from the
  clean install.
- Licence audit of what it pulled in, read from the installed metadata rather
  than from memory: Apache-2.0 (`requests`, `regex`), BSD (`Pygments`, `idna`),
  ISC (`shellingham`), PSF (`typing_extensions`), **MPL-2.0 (`certifi`)**, MIT
  (everything else — `tiktoken`, `typer`, `markdownify`, `beautifulsoup4`,
  `soupsieve`, `rich`, `markdown-it-py`, `mdurl`, `urllib3`,
  `charset-normalizer`, `six`, `annotated-doc`). **No AGPL and no GPL.** See
  Decisions for the `certifi` note.
- Command: `uv run python -c "import sys; before=set(sys.modules); import tokenmill; ..."`
- Result: `import tokenmill` pulls in **zero** third-party modules, unchanged
  from Phase 0 despite the package now having a real public API.

**Verdict: PASS on the exit gate**, with acceptance criterion 3 explicitly
**unverified in this environment** and criterion 4 met only in bytes, not in
model tokens. Both are recorded above rather than glossed.

**Bugs found and fixed during verification** (each found by running something,
not by reading it):

1. **A tokenizer that could not load aborted the entire conversion.**
   `NetworkRequired` is a `ConversionError` — correctly, per plan §1.4 — so the
   first working version of the pipeline propagated it and `tokenmill convert
   --tokenizer o200k_base` exited 1 with no document. On an air-gapped machine
   that is every conversion. Fixed by separating measurement failure from
   conversion failure in `TokenMeter`; the document is returned, counts are
   `None`, and one warning explains why. Covered by
   `test_pipeline.py::TestMeasurementFailureIsNotConversionFailure`.
2. **A conversion that made a document larger was reported as a saving.**
   Running the `ADDING_A_BACKEND.md` example backend produced a Markdown table
   larger than its CSV input — 62 → 106 bytes — and the CLI printed `-71.0%`,
   which reads as a 71% reduction. Exactly the class of misleading number
   `CONTRIBUTING.md` rule 4 exists to prevent. The percentage now follows the
   count: growth prints as `+71.0%`. Four tests added.
3. **`tests/fixtures/sample_repo/secrets.env` was never in the repository.** The
   fixture repo's own `.gitignore` lists it, and git applies nested ignore files
   to the outer repository too, so it was silently excluded from the Phase 0
   commit. Phase 0 recorded a PASS because the file existed locally at the time;
   on this fresh clone `test_sample_repo_hides_a_secret_that_ingestion_must_not_leak`
   failed immediately. Same class of problem as the uncommittable `.git`
   directory, and fixed the same way: materialised on demand. Fixed in
   `2eced0d`, before any Phase 1 code was written.
4. **The `network`, `heavy` and `compress` markers were registered but never
   deselected.** A plain `pytest` run was attempting real vocabulary downloads
   and taking 6+ seconds to fail. They are now skipped unless the run asks for
   them with `-m`, and they report as skips rather than being deselected, so it
   stays visible that they exist and did not run.
5. Several test expectations of mine were wrong rather than the code: three
   trailing spaces before a text line *is* a Markdown hard break and is correctly
   preserved; `"one"` becomes two pieces after the normaliser appends its
   trailing newline; and `Source.from_text(..., name="a.txt")` has format `text`,
   not `txt`, so tests probing format handling must use real files. Corrected the
   tests, not the behaviour.

### 2026-08-20 — Post-Phase-1 follow-up: CI, and a correction

The owner accepted the recommendations from the open questions. Implementing
them meant checking that the thing several of them lean on — CI — actually
works. It did not.

**Finding: `.github/workflows/ci.yml` had never run, not once.**

- Query: GitHub Actions `list_workflows` for `RSD-Studio/tokenmill`
- Result: `total_count: 1`, and the one workflow is
  `dynamic/dependabot/update-graph`. **Our CI workflow was not registered with
  Actions at all.**
- Query: `list_workflow_runs`
- Result: `total_count: 1` — a single Dependabot dependency-graph run on
  2026-08-20. No lint, no types, no test, no `clean-core-install` run has ever
  happened.
- Query: `list_branches`
- Result: `claude/phase-1-core-architecture`,
  `claude/tokenfold-project-setup-9m3i5o`, `claude/tokenmill-phase-1-pr3rd7`.
  **There is no `main` branch.**
- Cause: the workflow triggered on `push` to `main` and on `pull_request`.
  `main` does not exist and no pull request has been opened, so neither trigger
  could ever fire. A workflow that never fires is never registered, which is why
  it did not even appear in the workflow list.

**Correction to the Phase 1 exit-gate entry above.** That entry records
acceptance criterion 3 (token counts match a hand-verified tiktoken result) as
"not verified here — CI only". That was wrong in the second half: CI had never
run, so those assertions were verified *nowhere*. Worse, the `test` job runs a
plain `pytest`, which **skips** `network`-marked tests, so even a working CI
would not have executed them. The criterion's status is unchanged — still
unverified — but the reason was misstated and is corrected here rather than
edited away.

**Fixes applied:**

- `on.push.branches` now includes `claude/**`, so CI runs on the branches work
  actually happens on rather than only on a branch that does not exist.
- New **`tokenizers` job**, running `uv run pytest -q -m network -rs` with the
  `tokenizers` extra. This is the only place real token counting is verified, so
  it is a blocking job, not an advisory one.
- New **`coverage` job**, enforcing the plan's ≥85% target on `core` and
  `tokens` specifically.

- Command: `uv run python -c "import yaml; yaml.safe_load(...)"`
- Result: valid YAML; triggers
  `{'push': {'branches': ['main', 'claude/**']}, 'pull_request': None, 'workflow_dispatch': None}`;
  jobs `['lint', 'types', 'test', 'coverage', 'tokenizers', 'fixtures', 'clean-core-install']`.

- Command: `uv run pytest -q --cov=tokenmill.core --cov=tokenmill.tokens --cov-fail-under=85`
- Result: `Required test coverage of 85% reached. Total coverage: 96.07%`,
  `325 passed, 11 skipped`. The gate passes today, so it locks in the current
  standard rather than demanding new work.

### 2026-08-20 — tiktoken's offline cache, verified

Checked before documenting it, rather than after.

- Read `tiktoken/load.py` in the installed package: `read_file_cached` consults
  `TIKTOKEN_CACHE_DIR`, then `DATA_GYM_CACHE_DIR`, then
  `<tempdir>/data-gym-cache`, keyed by `sha1(url)`, **before** attempting any
  download. Cache keys for our four encodings, computed and recorded so the
  instructions can be checked: `o200k_base` →
  `fb374d419588a4632f3f557e76b4b70aebbca790`, `cl100k_base` →
  `9b5ad71b2ce5302211f9c61530b329a4922fc6a4`, `p50k_base` →
  `ec7223a39ce59f226a68acc30dc1af2788490e15`, `r50k_base` →
  `0ea1e91bbb3a60f729a8dc8f777fd2fc07cd8df4`.

- Command: `TIKTOKEN_CACHE_DIR=<empty dir> uv run tokenmill tokens --text "hello world" -t o200k_base`
- Result: the usual 403 network error — an empty cache correctly falls through
  to the download rather than failing in some other way.

- Command: wrote a junk file to the exact `o200k_base` cache key, then re-ran
  the same command
- Result: **the junk was refused and deleted.** Same 403 error, and the cache
  directory was empty afterwards (`0 file(s)`). tiktoken hash-checks cached
  content before use, so a wrong or truncated cache **cannot silently produce
  wrong token counts**. That is the property that makes recommending the offline
  cache safe, and it is now verified rather than assumed.

### 2026-08-20 — Repository name confirmed

Phase 0 left open whether the GitHub repository had been renamed from
`tokenfold`.

- Command: `git ls-remote --heads https://github.com/RSD-Studio/tokenmill`
- Result: succeeds, returning the three branches.
- Query: GitHub API `list_branches` for owner `RSD-Studio`, repo `tokenmill`
- Result: succeeds.

**The repository is `RSD-Studio/tokenmill`.** The URLs in `pyproject.toml` and
the README are correct. Phase 0's Open question 2 is closed.

### 2026-08-20 — First CI runs: five failures, then all green

The CI trigger fix meant the workflow finally ran. It failed, in exactly the
three places Phases 0 and 1 had flagged as unverified, and none of the three
could have been caught in this sandbox.

**Run 1 (`0cfca94`) — 18 jobs green, 5 red.**

| Job | Result |
|---|---|
| Lint and format, Type check, Coverage gate | ✅ |
| Test — ubuntu ×3, macOS ×3 | ✅ |
| Clean core install — 9 cells (3 OS × 3 Python) | ✅ |
| **Test — windows ×3** | ❌ |
| **Fixture corpus is reproducible** | ❌ |
| **Real tokenizers (network)** | ❌ |

1. **Windows, all three Python versions**, one test each:
   `test_sample_repo_is_a_real_git_repo_with_a_pinned_commit`, `324 passed,
   1 failed`. The rebuilt fixture repo landed on `7d690e6cdcae...` instead of
   the recorded `fc5ce61ac784...`. Cause: git's `core.autocrlf` defaults to true
   on Windows, so checkout rewrote LF to CRLF inside `tests/fixtures/`. Different
   bytes, different tree, different commit — and the corpus was not
   byte-reproducible on Windows either, which is the claim `--check` exists to
   enforce. Fixed with a `.gitattributes` marking `tests/fixtures/** -text`: the
   corpus is data, and git must not rewrite it on any platform. Rule order
   matters — later patterns win, so `* text=auto` comes first and the exception
   after.
   **Note that only that one test failed.** All 324 others passed on Windows,
   including every piece of Phase 1.

2. **Fixture reproducibility**: `MISMATCH sample_repo/secrets.env:
   committed=None regenerated=b99b52de...`. `--check` compares the regenerated
   corpus against the committed one, and `secrets.env` is deliberately never
   committed. So it is absent from every fresh clone by design and the
   comparison reported a mismatch on all of them. The same root cause as the
   test failure fixed in `2eced0d`, surfacing in a second place that only a
   clone which has never run the generator could reveal. `--check` now excludes
   the uncommittable files; the reported count drops from 23 to 22 for that
   reason.

3. **Real tokenizers**: `1 failed, 10 passed`.
   `test_the_same_text_counts_differently_under_different_encodings` failed with
   `assert 8 != 8` — I had asserted that "Tokenisation is not a universal
   constant." counts differently under `o200k_base` and `r50k_base`, and it does
   not. **The result was right and my test was wrong**, which is what I said
   would happen to these numbers if any of them were wrong, and what I said I
   would do about it. Two encodings agreeing on one short ASCII sentence is a
   coincidence, not a contradiction. The test now samples five kinds of text
   (English prose, Chinese, Python source, emoji, a very long word) and asserts
   that **at least one** differs — the property that actually holds. The
   expectation was corrected; the assertion was not loosened.

   **The other ten passed**, including the two that matter most:
   - `test_a_known_string_counts_as_expected_under_o200k_base` — `"hello world"`
     is **2 tokens** under `o200k_base`. That is acceptance criterion 3, and the
     number I wrote from published behaviour without being able to run it was
     correct.
   - `test_converting_the_boilerplate_fixture_reports_a_real_reduction` — the
     full pipeline on `boilerplate.html` produces before and after counts that
     both carry the `o200k_base` id, with the after strictly smaller. That is
     acceptance criterion 4 in real model tokens rather than bytes.

**Run 3 (`3aa6e59`) — all 23 jobs green.**

- `Real tokenizers (network)`: `uv run pytest -q -m network -rs` →
  **`11 passed, 325 deselected in 3.56s`**
- `Fixture corpus is reproducible`: **`OK: 22 files reproduced byte-for-byte`**
- `Test`: green on **ubuntu, macOS and Windows × Python 3.11, 3.12 and 3.13** —
  nine cells
- `Clean core install`: green on the same nine cells
- `Coverage gate (core and tokens)`, `Lint and format`, `Type check`: green

**What this closes.** Three things Phase 0 recorded as deferred-because-
unverifiable are now verified: Windows behaviour, macOS behaviour, and Python
3.12/3.13. So is acceptance criterion 3, which had been unverified since the
phase began. The sandbox still cannot reach either tokenizer host, so token
counting remains CI-verified rather than locally observed — but it is now
verified by a blocking job that cannot silently stop running.

**Verdict: PASS.** Phase 1 is green on every platform and Python version in the
matrix, and its central claim is proven against a real tokenizer.

### 2026-08-21 — Blocked-host re-probe (start of Phase 2)

Re-probed both hosts before designing anything, as instructed.

- Command: `curl -sS -o /dev/null -w '%{http_code}\n' --max-time 25 "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"`
- Result: `curl: (56) CONNECT tunnel failed, response 403`
- Command: `curl -sS -o /dev/null -w '%{http_code}\n' --max-time 25 "https://huggingface.co/gpt2/resolve/main/tokenizer.json"`
- Result: `curl: (56) CONNECT tunnel failed, response 403`
- Command: same against `https://pypi.org/simple/`
- Result: `200`

**Verdict: unchanged from Phases 0 and 1.** Every local number below is
`--tokenizer bytes`, i.e. UTF-8 bytes, and is labelled as such.

### 2026-08-21 — Can Docling run here? (probed in the first ten minutes)

The plan puts Docling behind its own extra because it pulls PyTorch. Before
designing the adapter I installed it and tried to use it, rather than assuming
either that it would work or that it would not.

- Command: `uv pip install docling` into a throwaway venv
- Result: succeeded. **122 packages, 5.2 GB**, including `torch 2.13.0`,
  `torchvision`, `triton` and 43 `nvidia-*` CUDA packages. This is the
  measurement behind "Docling must stay behind its own extra".
- Licence audit of all 122, read from installed metadata: `docling`,
  `docling-core`, `docling-slim`, `docling-parse`, `docling-ibm-models` all
  **MIT**; `transformers` Apache-2.0; `rapidocr` Apache-2.0. **No GPL and no
  AGPL anywhere in the tree.** The only non-MIT/Apache/BSD entries are
  `certifi` and `tqdm`, both MPL-2.0, both already accepted in Phase 1.

- Command: `DocumentConverter().convert('tests/fixtures/tables.pdf')`
- Result: **failed**, and not where I expected. Docling's default PDF pipeline
  enables RapidOCR, which tried to fetch weights from a *third* host:
  ```
  [RapidOCR] Initiating download: https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/torch/PP-OCRv6/det/PP-OCRv6_det_small.pth
  [RapidOCR] Download failed
  rapidocr.utils.download_file.DownloadFileException
  ```
- Command: same with `PdfPipelineOptions(do_ocr=False)`
- Result: **failed**, now at the layer it really needs:
  `httpx.ProxyError: 403 Forbidden` — the DocLayNet layout model and
  TableFormer, from `huggingface.co`.

- Command: `DocumentConverter().convert(...)` on `report.docx`, `deck.pptx`,
  `data.xlsx` and `unicode.docx`
- Result: **all four succeeded, fully offline, in under a second each.**

**This is the finding that shaped the adapter.** Docling's Office formats go
through direct parsers and need no model; only its PDF path downloads anything.
So the adapter disables OCR, and `core/preferences.py` ranks docling **first for
DOCX and last for PDF** — auto-selecting it for a PDF would begin a
several-hundred-megabyte download inside a command the user believed was local.

### 2026-08-21 — Phase 2 exit gate

Run from a virtualenv synced with `uv sync --extra dev --extra fixtures --extra
documents`.

- Command: `uv run ruff check .`
- Result: `All checks passed!`

- Command: `uv run ruff format --check .`
- Result: `87 files already formatted`

- Command: `uv run mypy` (strict, over `src` + `scripts` + `tests`)
- Result: `Success: no issues found in 56 source files`

- Command: `uv run pytest -q --cov=tokenmill`
- Result: `542 passed, 23 skipped`, `TOTAL 1802 stmts, 92%`. Per-package
  statement coverage against the plan's >=85% target on `core` and `tokens`:

  | Package | Coverage |
  |---|---|
  | `core` | **99%** (`pipeline`, `registry`, `preferences` all 100%) |
  | `tokens` | **88.5%** |
  | `backends/documents` | 74% — the docling adapter is 35% here because docling is not installed in this venv |

- Command: `uv run python scripts/make_fixtures.py --check`
- Result: `OK: 22 files reproduced byte-for-byte`

- Command: `uv run pytest -q tests/integration -m "not heavy"`
- Result: `74 passed, 6 skipped, 2 deselected` — the 6 skips are the docling
  Office tests, reported as `needs the optional dependency 'docling'`.

**Smoke scenario, exactly as the plan specifies it.**

- Command: `uv run tokenmill backends --all`
- Result:
  ```
  id                domains    license       tier        isolation   availability
  ----------------  ---------  ------------  ----------  ----------  ---------------------------
  docling           documents  MIT           permissive  in-process  missing dependency: docling
  kreuzberg         documents  MIT           permissive  in-process  available
  markdownify_html  web        MIT           permissive  in-process  available
  markitdown        documents  MIT           permissive  in-process  available
  pdfplumber        documents  MIT           permissive  in-process  available
  plaintext         text       Apache-2.0    permissive  in-process  available
  pypdf             documents  BSD-3-Clause  permissive  in-process  available
  ```

- Command: the plan's loop over every `*.pdf`, `*.docx`, `*.pptx`, `*.xlsx`
  fixture, with `--tokenizer bytes`
- Result: **eight of nine converted, exit 0. `corrupt.pdf` failed, which is
  what it is for.**

  | Fixture | Backend | bytes before → after | Notes |
  |---|---|---|---|
  | `simple.pdf` | pdfplumber | 4,753 → 2,370 | |
  | `tables.pdf` | pdfplumber | 2,795 → 599 | |
  | `twocolumn.pdf` | pdfplumber | 4,354 → 4,050 | **warned: multi-column** |
  | `scanned.pdf` | pdfplumber | 144,338 → 0 | **warned: empty document** |
  | `corrupt.pdf` | — | — | **exit 1**, all four PDF backends tried |
  | `report.docx` | markitdown | 68,190 → 3,494 | |
  | `unicode.docx` | markitdown | 67,241 → 1,312 | |
  | `deck.pptx` | markitdown | 65,725 → 753 | |
  | `data.xlsx` | markitdown | 10,524 → 675 | |

  **These are UTF-8 bytes, not tokens**, and for these binary formats the
  "before" figure is the file's own bytes decoded as text — which the CLI now
  says out loud on every one of them:
  ```
  warning:  report.docx is a binary format, so the before-count is its own bytes
  decoded as text, not text any model would be given. The after-count is real;
  the percentage between them is not a token saving
  ```

- Command: `uv run tokenmill convert tests/fixtures/corrupt.pdf --tokenizer bytes`
- Result: **exit 1**, and the fallback chain visible in the hint:
  ```
  error: corrupt.pdf could not be parsed: PdfStreamError: Stream has ended unexpectedly
  hint:  every backend that handles this source failed: pdfplumber, kreuzberg, markitdown, pypdf
  ```

- Command: `uv run tokenmill convert tests/fixtures/tables.pdf --backend pdfplumber --tokenizer bytes --show-stages`
- Result:
  ```
  source:   tables.pdf
  backend:  pdfplumber
  format:   markdown
  duration: 73 ms
  post:     normalize_whitespace
  tokens:   2,795 -> 599  (-78.6%, bytes)

  stage                 chars  tokens  change
  --------------------  -----  ------  ---------
  source                2,140  2,795   -
  convert               599    599     -78.6%
  normalize_whitespace  599    599     no change
  ```

- Command: `uv run tokenmill convert tests/fixtures/tables.pdf --backend docling --show-stages`
- Result: **exit 1**, degrading exactly as designed rather than crashing:
  ```
  error: backend 'docling' is not available: missing dependency: docling
  hint:  pip install "tokenmill[docling]"
  ```

**The emitted Markdown, read rather than assumed.**

*`tables.pdf` — the acceptance criterion.* All **35 cells** present, as a real
Markdown table, with the prose spliced around it in document order:

```
Converter Comparison
Backend characteristics
The table below is the fixture's reason for existing: a converter that flattens it into prose has lost the
data.

| Backend | License | Runtime | Tables | Pages/sec |
| --- | --- | --- | --- | --- |
| markitdown | MIT | CPU | weak | 12.0 |
| docling | MIT | CPU | strong | 0.8 |
| pdfplumber | MIT | CPU | good | 3.4 |
| pypdf | BSD-3 | CPU | none | 18.5 |
| pymupdf4llm | AGPL-3.0 | CPU | good | 11.1 |
| marker | GPL-3.0 | GPU | strong | 1.9 |

Figures are illustrative placeholders for structural testing and are not measurements of any real
backend.
```

Header row correct, first column in the right order, 7 rows × 5 columns, no
empty cells. **Criterion 2 met on inspection.**

*`twocolumn.pdf` — reading order, per backend.* Extracted every `ORDERMARK`
in output order:

| Backend | Order | Verdict |
|---|---|---|
| pypdf | `01 02 03 04 05 06 07 08 09 10 11 12` | **correct** |
| kreuzberg | `01 02 03 04 05 06 07 08 09 10 11 12` | **correct** |
| pdfplumber | `01 08 02 09 03 10 04 11 05 12 06 07` | **wrong** — columns interleaved |
| markitdown | `08 09 10 11 12 01 02 03 04 05 06 07` | **wrong** — second column first |

pdfplumber is the auto-selected PDF backend, so the default answer for this
fixture is the wrong one. Because interleaved columns still read as fluent
English, nothing in the output announces the problem — so the adapter now
detects the column gutter and warns:

```
warning:  twocolumn.pdf looks multi-column on page(s) 1. pdfplumber has no layout
model and reads a page in scan-line order, so the columns are very likely
interleaved in this output. This is a heuristic, not a certainty — check the
text, and try --backend pypdf or --backend kreuzberg, which read columns in order
```

The detector was calibrated against the corpus, not guessed: largest gap
between adjacent word centres is 10.8 pt and 9.4 pt on `simple.pdf`'s two
pages, 23.9 pt on `tables.pdf` (which has a five-column table), and 37.8 pt on
`twocolumn.pdf`. The thresholds sit in that gap. Confirmed it fires on
`twocolumn.pdf` and on neither of the others.

*`unicode.docx` — all ten scripts round-tripped*, read in full: Urdu, Arabic,
Chinese, Japanese, Korean, Russian, Hindi, Greek, the emoji line including the
ZWJ family sequence and the regional-indicator flag, and the mathematical
symbols line.

*`deck.pptx` — speaker notes kept.* All four present under `### Notes:`
headings, with all five slides and their titles.

*`report.docx` — read across all three Office backends*, headings, lists and
table compared side by side:

| | title as heading | H1 / H2 | bullets | numbered | table header |
|---|---|---|---|---|---|
| **docling** | ✅ `#` | `##` / `###` | ✅ `-` | ✅ nested restarts at `1.` | ✅ real header |
| **markitdown** | ❌ body text | `#` / `##` | ✅ `*` | ⚠️ nested flattened to `4.` | ❌ **empty header row** above the real one |
| **kreuzberg** | ✅ `#` | `#` / `##` — collides with the title | ❌ lost | ❌ lost | ✅ real header |

That comparison is why `preferences.py` ranks docling first for `docx`.

*`scanned.pdf` — empty, loudly.* Zero characters out, and:
```
warning:  scanned.pdf converted to an empty document: pdfplumber found no text
layer across 2 page(s), which is what a scanned or image-only PDF looks like.
Extracting text from page images needs OCR, which tokenmill does not ship yet.
The conversion succeeded; there was simply nothing to extract.
```

**Exit gate item: the fallback chain when the primary backend is uninstalled.**

- Command: `uv pip uninstall markitdown`, then `uv run tokenmill backends`
- Result: markitdown gone from the listing; six backends remain.
- Command: `uv run tokenmill convert tests/fixtures/report.docx --tokenizer bytes`
- Result: `backend:  kreuzberg`, `tokens: 68,190 -> 3,472 (-94.9%, bytes)`
- Command: `uv run tokenmill convert tests/fixtures/deck.pptx --tokenizer bytes`
- Result: `backend:  kreuzberg`, `tokens: 65,725 -> 398 (-99.4%, bytes)` — and
  note the smaller output, because kreuzberg drops the speaker notes markitdown
  keeps. The fallback works and it costs something, which is exactly why the
  preference order exists.
- Then `uv sync --extra documents` restored it. **Criterion 3 met.**

The *other* fallback path — installed but failing on this file — was observed
too:

- Command: `uv run tokenmill convert <an empty .html file> --tokenizer bytes`
- Result: **exit 0**, with the whole chain visible:
  ```
  backend:  markitdown
  attempts: markdownify_html (failed) -> markitdown
  warning:  backend 'markdownify_html' failed and tokenmill fell back to the next one: empty.html is empty
  warning:  empty.html converted to an empty document: MarkItDown parsed the file but found no extractable text in it.
  ```

**Exit gate item: Docling, run for real.**

Installed tokenmill into the venv that has docling and drove it through the real
pipeline, not just the library.

- Command: `tokenmill backends --all` → docling `available`
- Command: `tokenmill convert tests/fixtures/report.docx --backend docling --tokenizer bytes --show-stages`
- Result: **exit 0**, `duration: 3918 ms`, `68,190 -> 3,561 (-94.8%, bytes)`,
  and the Markdown has three correct heading levels, both lists with markers,
  the nested item nested, and a real table header row.
- Command: `tokenmill convert tests/fixtures/report.docx --tokenizer bytes`
  (auto-selection, docling installed)
- Result: `backend:  docling` — the preference map picks it for docx.
- Command: `tokenmill convert tests/fixtures/deck.pptx --tokenizer bytes`
- Result: markitdown's output (`<!-- Slide number: 1 -->`) — the map does *not*
  pick docling for pptx.
- Command: `tokenmill convert tests/fixtures/tables.pdf --tokenizer bytes`
- Result: `backend:  pdfplumber` — the map does **not** pick docling for PDF
  even with it installed, so no surprise model download.
- Command: `tokenmill convert tests/fixtures/tables.pdf --backend docling --tokenizer bytes`
- Result: **exit 1**, the blocked host reported as an actionable error rather
  than a traceback:
  ```
  error: docling could not reach the network while converting tables.pdf: ProxyError: 403 Forbidden: caused by ProxyError: 403 Forbidden
  hint:  this backend downloads a model or vocabulary on first use; run it once on a networked machine, or choose a backend that needs no download
  ```
- Command: `pytest -q` in that venv
- Result: `542 passed, 15 skipped`. The docling Office tests pass; the two PDF
  ones skip with `docling needs network access for 'pdf' and allow_network is
  False`.

**Verdict: PASS on the exit gate**, with **Docling's PDF path explicitly
unverified** — implemented, its failure path observed, its success path never
run anywhere. See Open question 1.

**Bugs found and fixed during verification** (every one found by running
something, not by reading it):

1. **Docling's PDF pipeline failed on a `DeprecationWarning` about its own
   deprecated field.** `standard_pdf_pipeline.py` reads
   `generate_table_images`, pydantic warns, and `filterwarnings = ["error"]`
   turned that into a failed conversion. Nothing tokenmill does causes it and
   nothing tokenmill can do avoids it, so the adapter filters that one message
   around the convert call. Found only because I installed docling and ran the
   suite against it.
2. **An empty HTML file stopped being reported as corrupt.** With more than one
   backend claiming `html`, `markdownify_html`'s `CorruptSource` now hands over
   to markitdown, which returns an empty document instead. That is a real
   behaviour change from Phase 1, caught by a Phase 1 test. The old test now
   pins the backend it was actually about, and a new one records the new
   pipeline behaviour — which is acceptable only because the attempt chain and
   the empty-output warning both make it visible.
3. **The preference map named backends and formats that did not exist.** I had
   ranked `ppt`, `xls` and `tsv` for backends that do not claim them.
   `test_preferences.py` caught it on the first run; the entries are gone.
4. **I claimed markitdown loses `report.docx`'s bullet markers. It does not.**
   That came from reading a filtered dump whose pattern did not match `*`. It
   keeps both list types and flattens only the *nested* item. Corrected in the
   adapter docstring, in `preferences.py`, and before it reached
   `docs/BACKENDS.md`; three tests now pin all three backends' list handling.
5. **I claimed docling keeps `data.xlsx`'s sheet names. It does not — but my
   test said it did.** A substring search for the sheet name `corpus` matched
   the cell `corpus_items` in a different sheet. The claim was right and the
   test was wrong; it now asserts on headings.
6. **Fixture regeneration was broken by the container's `/dev/null`.** See the
   Environment section.

### 2026-08-21 — CI: three red jobs, two causes, then all green

Neither cause could have been caught in this sandbox, which is the whole
argument for the CI matrix.

**Run 11 (`008f5f4`) — 20 jobs green, 3 red, 1 skipped by design.**

1. **Test — windows × py3.12 and py3.13**, 11 tests each, `523 passed, 11
   failed`. markitdown imports magika, which imports onnxruntime, which warns
   at import time:
   `UserWarning: Unsupported Windows version (2025server). ONNX Runtime supports Windows 10 and above, only.`
   Under `filterwarnings = ["error"]` that becomes an exception inside the lazy
   import, and `BaseConverter` reported a healthy converter as
   `BackendFailed`. **py3.11 on Windows passed**, and Linux and macOS passed on
   all three versions, so nothing local would ever have shown it.

   Suppressing the warning would have been the wrong fix — "your platform is
   unsupported" is worth hearing. Warnings raised while importing a backend's
   dependency are now captured and handed to the user as conversion warnings:
   non-fatal, still visible, attributed.

2. **Type check.** `numpy/__init__.pyi:737: error: Type statement is only
   supported in Python 3.12 and greater [syntax]`, then
   `errors prevented further checking` — so mypy checked *none* of our code.
   numpy arrives transitively with the `documents` extra (markitdown → magika,
   and pandas) and its stubs use 3.12 syntax while we target 3.11. Locally the
   interpreter is 3.11 and it passed; the CI runner picked 3.12.

   Reproduced locally by building a 3.12 venv (`uv venv --python 3.12`), fixed
   with a per-module skip for numpy, and **re-verified in that same 3.12 venv**
   rather than only on CI.

**Run 12 (`2e675f5`) — all 23 jobs green**, with the `docling` job skipped as
designed (`workflow_dispatch` only). **Run 13 (`88d1721`) green on the same 23,
and run 15 on the phase's final commit `15eaeda` green on all 23 as well** —
verified job by job, not from the run's summary.

- `Test`: green on ubuntu, macOS and Windows × Python 3.11/3.12/3.13 — nine
  cells, now with the `documents` extra installed, so the markitdown and
  kreuzberg integration tests actually **ran** rather than skipping.
- `Clean core install`: green on the same nine cells. **The core install
  guard survived Phase 2 adding two dependencies to it.**
- `Real tokenizers (network)`, `Coverage gate`, `Lint and format`,
  `Type check`, `Fixture corpus is reproducible`: green.

**The `docling` job has never run.** It is `workflow_dispatch`-only by design,
and I cannot trigger it — the API returns
`403 Resource not accessible by integration`, because this session's token has
no `actions: write`. That is why Docling's PDF path is recorded as unverified
rather than done. Open question 1.

### 2026-08-22 — Phase 2 follow-ups: the three open questions, closed

Phase 2 merged into `Main` as PR #4 (`0a74c8f`), and its branches were deleted.
This work is a fresh change cut from that merge, per `CONTRIBUTING.md`.

**The binary before-count is gone, and the shape of the report changed with it.**

- Command: `uv run tokenmill convert tests/fixtures/report.docx --tokenizer bytes --show-stages`
- Result:
  ```
  source:   report.docx
  backend:  markitdown
  format:   markdown
  duration: 760 ms
  post:     normalize_whitespace
  tokens:   3,494  (bytes)
  size:     37.4 KiB in, no comparable before

  stage                 chars  tokens  change
  --------------------  -----  ------  ------
  convert               3,493  3,493   -
  normalize_whitespace  3,494  3,494   +0.0%
  ```
  No percentage, no `source` row, and no warning. Compare with what Phase 2
  shipped: `tokens: 68,190 -> 3,494 (-94.9%, bytes)` plus a disclaimer.

- Command: the same on `boilerplate.html`, to prove the text path is untouched
- Result: `tokens:   12,481 -> 6,802  (-45.5%, bytes)`, with the `source` stage
  row still present and the numbers **identical to Phase 1's and Phase 2's**.
  Nothing that worked has changed.

- Command: the same on `scanned.pdf`
- Result: `tokens: 0 (bytes)`, `size: 79.2 KiB in, no comparable before`, and
  the empty-document warning. The old output claimed `144,338 -> 0 (-100.0%)`,
  a 100% saving on a conversion that produced nothing — which is the clearest
  single illustration of why the before-count had to go.

**Checks, from a venv synced with `--extra dev --extra fixtures --extra documents`:**

- `uv run ruff check .` → `All checks passed!`
- `uv run ruff format --check .` → all files formatted
- `uv run mypy` → `Success: no issues found in 56 source files`
- `uv run pytest -q` → `558 passed, 23 skipped` (up from 542; 16 new tests
  covering the new shape, `format_bytes`, and the guard against "before"
  silently becoming "after conversion")
- `uv run python scripts/make_fixtures.py --check` → `OK: 22 files reproduced
  byte-for-byte`

**Two Phase 1/2 tests changed, both deliberately:**

1. `test_a_binary_source_says_its_before_count_is_not_a_token_saving` asserted
   the warning that has been removed. Replaced with three tests asserting the
   new behaviour, including one that asserts a document conversion carries **no
   routine warning at all** — the warning budget is the point.
2. `test_a_source_with_no_before_text_says_so_instead_of_guessing` asserted a
   zero-character `source` row for an unfetchable URL. That placeholder row is
   gone: one rule now covers both ways a source can lack a comparable before.
   The warning still fires and `tokens_before` is still `None`.

### 2026-08-22 — CI cannot schedule runners, and it is not our YAML

Four consecutive runs — 25, 26, 27 and 28, across both `claude/phase-2-followups`
and `claude/tokenmill-phase-2-djouak`, on commits `38c8c52` and `e65337b` — failed
within seconds of starting. Run 24 on `Main` had succeeded 2h20m earlier on
`0a74c8f`.

The failure signature is identical in every job of every run:

```
"runner_id": 0, "runner_name": "", "runner_group_id": 0,
"status": "completed", "conclusion": "failure",
"started_at": "2026-08-22T11:14:55Z", "completed_at": "2026-08-22T11:14:57Z"
```

No `steps` array at all, no logs (the logs endpoint returns 404), and empty
check-run output. All three runner labels fail the same way — `ubuntu-latest`,
`macos-latest` and `windows-latest` — which rules out a single image being
broken.

**This is not the workflow file, and it is worth being precise about why**, since
`ci.yml` *was* modified on this branch and that is the obvious suspect:

- All 24 job records were created with their correct expanded names
  (`Test (py3.12 / windows-latest)`, `Clean core install (py3.11 / macos-latest)`
  and so on), so the YAML parsed and the matrices expanded.
- The `Docling (weekly and on demand)` job evaluated its `if:` condition and
  concluded `skipped`, correctly, on a `push` event. Expression evaluation
  therefore worked too.
- A malformed workflow fails at the *run* level with a parse error, not with 23
  individually-created jobs that each fail to acquire a runner.

The most likely cause is exhausted Actions minutes or a spending limit — this
repository has run ~28 workflows of 24 jobs each in three days, and macOS bills
at 10x and Windows at 2x. **Only the owner can check that**; these sessions
cannot call `run_workflow` or `rerun_failed_jobs` (both return 403 `Resource not
accessible by integration`).

**What is verified locally on `e65337b`**, from a venv synced with `--extra dev
--extra fixtures --extra documents`:

- `uv run pytest -q` → `558 passed, 23 skipped in 6.01s`
- `uv run ruff check .` → `All checks passed!`
- `uv run mypy` → `Success: no issues found in 56 source files`

That is local green, and it is **not** the same claim as CI green. Nothing in
this session has been proven on Windows, on macOS, on Python 3.12 or 3.13, or
against real tokenizer vocabularies, because the jobs that prove those things
never started. Recorded as unverified accordingly.

The one change made in response was to `ci.yml` itself: the weekly cron now runs
`docling` and `clean-core-install` only, with the other six jobs gated off the
schedule event. That is better design on its own terms — re-running nine
OS/Python cells weekly against a frozen lockfile proves nothing a push has not
already proved — and it also stops the schedule from making a minutes problem
worse. It is not a fix for this failure and is not offered as one.

### 2026-08-22 — Handover prompt for Phases 3 and 4

`docs/prompts/PHASE_3_AND_4.md` is the assignment for the next session: both
phases in one go, then a full re-evaluation of the app, stopping before Phase 5.

It carries the environment facts re-probed today rather than assumed, because
they have changed between phases before:

| Host / tool | Result |
|---|---|
| `pypi.org` | 200 |
| `registry.npmjs.org` | 200 — repomix is genuinely runnable here |
| `crates.io` API | 403 — code2prompt likely not installable from source |
| `example.com` | denied — no live-URL testing in this sandbox |
| `openaipublic.blob.core.windows.net` | denied |
| `huggingface.co` | denied |
| Node | v22.22.2 |
| npx | 10.9.7 |
| cargo | 1.94.1 |

And the traps that will otherwise be rediscovered the expensive way:

1. Phase 3's ~70–90% boilerplate-reduction criterion needs **real model
   tokens**, and both tokenizer hosts are denied here. The `bytes` tokenizer
   measures UTF-8 bytes, not tokens; a byte percentage is a different claim.
   Only the CI `tokenizers` job can produce the publishable figure.
2. Making trafilatura outrank `markdownify_html` for `html` breaks
   `tests/integration/test_reference_backends.py`, which asserts the current
   backend by id, `strips_boilerplate is False`, and that every marker in
   `boilerplate_markers_must_be_absent` **survives**. Those assertions get
   pinned to `--backend markdownify_html` and mirrored for trafilatura, not
   loosened.
3. Phase 4 needs subprocess adapters, but `SubprocessConverter` is a Phase 7
   deliverable. Build the minimum Phase 4 needs, sited where Phase 7 can absorb
   it, and record what Phase 7 still owes.
4. `docs/BENCHMARKS.md` does not exist, yet Phase 3's exit gate names it while
   `README.md` calls it Phase 10. Ruling: create it now, small and partial.
5. `docs/LICENSES.md` is a dead link from `CONTRIBUTING.md`.
6. CI could not schedule runners as of 11:15 UTC today — re-check before
   relying on it.

## Backend status

Two backends exist and are wired, tested and verified. The rest are the planned
set, with licences taken from `docs/research/RESEARCH.md` and **not yet
independently re-verified**. Licences get checked at the moment each adapter is
implemented, and corrections are recorded under Decisions.

The Phase 1 licences below were verified against the installed package metadata
during the exit gate, not taken on trust: markdownify reports `MIT License`
(v1.2.3), tiktoken `MIT License`, typer `MIT`.

**Where each Phase 2 backend was verified**, since that is the part that is easy
to overstate:

| Backend | Verified locally | Verified in CI | Unverified |
|---|---|---|---|
| `pdfplumber` | ✅ all four PDF fixtures, output read | ✅ 9 cells | — |
| `pypdf` | ✅ all four PDF fixtures, output read | ✅ 9 cells | — |
| `markitdown` | ✅ pdf, docx, pptx, xlsx, unicode, output read | ✅ 9 cells | — |
| `kreuzberg` | ✅ pdf, docx, pptx, xlsx, unicode, output read | ✅ 9 cells | — |
| `docling` | ✅ **Office formats only** — docx, pptx, xlsx, unicode | ❌ not in the default matrix | ⚠️ **its PDF path has never been run anywhere** |

| Backend | Domain | License | Tier | Wired | Tested | Notes |
|---------|--------|---------|------|-------|--------|-------|
| plaintext | text | Apache-2.0 (ours) | core | ✅ | ✅ | Phase 1 reference backend. Passes text/Markdown through; warns on non-UTF-8 input |
| markdownify_html | web | MIT **(verified v1.2.3)** | core | ✅ | ✅ | Phase 1 reference backend. Converts markup faithfully; **does not strip boilerplate** — that is Phase 3 |
| pdfplumber | documents | MIT **(verified 0.11.10)** | core | ✅ | ✅ | **Recovers all 35 cells of `tables.pdf`.** Interleaves multi-column pages; warns when it detects a gutter |
| pypdf | documents | BSD-3-Clause **(verified 6.16.1)** | core | ✅ | ✅ | Correct multi-column reading order. No tables, no headings |
| markitdown | documents | MIT **(verified 0.1.7)** | documents | ✅ | ✅ | **Only backend that keeps PPTX speaker notes.** Mis-splits PDF table headers; demotes the DOCX title |
| kreuzberg | documents | MIT **(verified 4.10.2)** | documents | ✅ | ✅ | Fast, correct reading order, infers PDF headings. **Flattens PDF tables into prose**; drops DOCX lists |
| docling | documents | MIT **(verified 2.121.0)** | docling | ✅ | ⚠️ | **Best structure fidelity.** Office paths verified; **PDF path unverified** — needs `huggingface.co`. 122 packages, 5.2 GB |
| trafilatura | web | Apache-2.0 | core | ❌ | ❌ | Phase 3; primary web extractor |
| markdownify | web | MIT | core | ❌ | ❌ | Phase 3 |
| readability | web | Apache-2.0 | web | ❌ | ❌ | Phase 3 fallback |
| crawl4ai | web | Apache-2.0 | web | ❌ | ❌ | Phase 3; needs a browser download |
| gitingest | repo | MIT | core | ❌ | ❌ | Phase 4; Python-native, primary |
| repomix | repo | MIT | subprocess | ❌ | ❌ | Phase 4; Node — subprocess only |
| code2prompt | repo | MIT | subprocess | ❌ | ❌ | Phase 4; Rust — subprocess only |
| llmlingua2 | compress | MIT | compress | ❌ | ❌ | Phase 6; off by default |
| pymupdf4llm | documents | **AGPL-3.0** | isolated | ❌ | ❌ | Phase 7; **never imported** |
| pandoc | documents | **GPL-2.0+** | isolated | ❌ | ❌ | Phase 7; **never imported** |
| libreoffice | documents | MPL-2.0 | isolated | ❌ | ❌ | Phase 7; subprocess |
| marker / mineru / olmocr / surya / deepseek-ocr | documents | GPL-3.0 / varies / Apache-2.0 / GPL-3.0 / varies | heavy | ❌ | ❌ | Phase 9; GPU, out of process, **unverifiable in this sandbox** |

### Post-processors

| Id | Destructive | In default chain | Order | Wired | Tested |
|---|---|---|---|---|---|
| `normalize_whitespace` | no | yes | 100 | ✅ | ✅ |
| `links` | yes | no (opt-in) | 200 | ✅ | ✅ |

### Tokenizers

| Id | Provider | Licence | Counts | Wired | Tested | Notes |
|---|---|---|---|---|---|---|
| `o200k_base`, `cl100k_base`, `p50k_base`, `r50k_base` | tiktoken | MIT (verified) | BPE tokens | ✅ | ✅ CI | Resolution, error paths and the "unavailable" path are tested locally; real counting is verified in the blocking `tokenizers` CI job. No real count has ever been produced *in this sandbox* |
| `hf:<model>` | HuggingFace `tokenizers` | Apache-2.0 | model tokens | ✅ | ✅ CI | Behind the `tokenizers` extra. Verified in CI against `bert-base-uncased` |
| `bytes` | ours | Apache-2.0 | **UTF-8 bytes, not model tokens** | ✅ | ✅ | Download-free. Golden vectors hand-checked |

## Decisions made

### Phase 2 follow-ups — the owner's answers (2026-08-22)

Phase 2 shipped and merged into `Main` (PR #4). Its three open questions are now
closed; these are the decisions and what changed.

- **A binary document gets no before-count at all.** Open question 2, closed by
  the owner accepting the recommendation. The interim behaviour — print
  `68,190 -> 3,494` with a warning saying it is not a saving — was honest and
  still wrong, for a reason worth recording: it spent the warning budget. The
  warnings that matter here (an empty document from a scanned PDF, interleaved
  columns, a missing `exiftool`) are ones a user must act on, and a disclaimer
  on *every* document conversion trains people to skim the block they live in.
  A number that needs an apology under it should not be the headline.

  So the report's **shape** now depends on the source: `tokens: 3,494` plus
  `size: 37.4 KiB in, no comparable before` for a binary document, and the
  unchanged `tokens: 12,481 -> 6,802 (-45.5%)` where both sides really are text
  a model could be given. Changing the shape is the point — one number instead
  of two is visibly different, whereas keeping the two-number shape with a
  quietly different meaning would be the real trap.

  Implementation note that is load-bearing: there is **no `source` stage** for a
  binary input rather than an unmeasured one. Had the stage merely lacked a
  token count, `tokens_before` would have fallen through to the first *measured*
  stage — the converter's own output — and "before" would have come to mean
  "after conversion". `Pipeline.run` guards against that explicitly.

  The comparison that is meaningful for a document is between backends on the
  same file. That is Phase 5's `compare`.

- **The `docling` CI job now runs weekly as well as on demand.** Open question 1.
  Recommended over granting this session's token `actions: write`: that would
  have been a standing permission increase to solve a once-per-phase need, and a
  schedule solves the recurring version instead. `RESEARCH.md`'s own closing
  caveat is that this ecosystem moves fast and versions and licences must be
  re-verified; `docs/BACKENDS.md`'s premise is that every claim is asserted by a
  test. A backend nobody exercises is a claim decaying. Sunday 04:00 UTC.

  Note that `schedule` fires on the **default branch only**, so work on a
  feature branch still needs a manual dispatch against that branch. And the rest
  of the matrix runs weekly too, which is wanted: `clean-core-install` uses
  plain `pip install .` with no lockfile, so the weekly run is the one thing
  that catches a new release of a core dependency breaking a fresh install.

- **The default branch stays `Main`, with the capital.** Open question 3, the
  owner's call. The two URLs written lowercase now say `Main`:
  `pyproject.toml`'s `Changelog` (which becomes package metadata on PyPI at
  Phase 11) and `CHANGELOG.md`'s `[Unreleased]` link. CI's push filter keeps
  both spellings — GitHub matches them case-sensitively and the cost of the
  extra entry is nothing.

### Phase 2 — document backends (2026-08-21)

- **The backend preference map is per format, not a global priority.** Phase 1's
  single `BackendInfo.priority` worked because each format had one candidate.
  With five document backends it cannot express that MarkItDown is the right
  choice for `.pptx` (the only one that keeps speaker notes) and the wrong one
  for `.docx` (it demotes the title to body text). `core/preferences.py` holds a
  per-format map whose numbers *replace* a backend's declared priority for that
  one format; a backend the map does not name keeps its own. So a third-party
  backend with a high enough priority still outranks everything we ship without
  a core edit — the map is a default, not a gate — and a test asserts every id
  it names exists and claims the format it is ranked for.

- **Docling is ranked first for DOCX and last for PDF.** Its Office paths need
  no model and it is measurably the best of the three there. Its PDF path
  downloads the DocLayNet layout model and TableFormer from `huggingface.co` on
  first use, and auto-selection must never start a several-hundred-megabyte
  download inside a command the user believed was local. It is reachable by name
  and, being last, is only tried for a PDF after both core backends have failed.
  **This one changes the product's behaviour, so say if you want it differently.**

- **A failing backend hands over to the next one, and says so.** Every attempt
  is recorded on `ConversionResult.attempts`, a fallback attaches a warning
  naming what failed, and the CLI prints an `attempts:` line. A conversion that
  quietly came from the third choice would attribute its measurement to a
  converter that never ran, which is the same failure mode Phase 1 refused when
  it decided an explicit `--backend` must never be substituted. That rule still
  holds: an explicit backend's chain is one long.

- **The last failure is re-raised rather than rebuilt.** When every candidate
  fails, the original exception is raised with only its `hint` amended to list
  what was tried. Its class, its `__cause__` and its traceback are all worth
  keeping, and a plugin's `ConversionError` subclass may not share the base
  initialiser.

- **A binary source's before-count is flagged, not removed.** Converting a
  `.docx` reports `68,190 -> 3,494`, where the first figure is the zip
  archive's bytes decoded as text. That is a true fact about the file, so it
  stays; it is not text a model would ever be given, so the pipeline warns that
  the percentage is not a token saving. **What the honest "before" for a binary
  document should be is Open question 2** — it changes the product's headline
  number, so it is not mine to settle quietly.

- **pdfplumber warns when a page looks multi-column.** It has no layout model
  and interleaves columns, and interleaved columns still read as fluent
  English — nothing in the output announces the problem. The adapter measures
  the widest gap between adjacent word centres and warns when it finds a
  gutter. The thresholds were calibrated against the corpus (10.8/9.4/23.9 pt on
  the single-column fixtures, 37.8 pt on the two-column one) and sit in the gap.
  It is a heuristic, it says so, and it changes nothing about the extraction:
  detecting is as far as an adapter should go, because reordering a page is a
  layout engine.

- **OCR is off in every backend that offers it.** Kreuzberg can drive Tesseract
  or EasyOCR and Docling enables RapidOCR by default. Both would make output
  depend on which binaries and weights happen to be present, which is not
  something `docs/BACKENDS.md` could describe truthfully, and Docling's default
  fetches from a *third* host. OCR is Phase 9. Kreuzberg's cache is off for the
  same reason: a converter that writes to a cache directory behind the user's
  back makes a second run of the same command unreproducible.

- **MarkItDown runs with plugins disabled.** It will load third-party converter
  plugins from the environment, and a backend whose output depends on what else
  is installed cannot be reported honestly.

- **A third-party library's import-time warning must not fail a conversion, but
  must not be hidden either.** Found on the Windows CI runners: onnxruntime
  (via magika, via markitdown) warns `Unsupported Windows version` on load, and
  under `-W error` that turned every MarkItDown conversion into `BackendFailed`.
  Such warnings are now captured and handed to the user as conversion warnings.
  The exception is a library's *internal* deprecation churn, which a user cannot
  act on: Docling's own deprecated-field warning is filtered instead.
  `warnings.catch_warnings` is not thread-safe — recorded under Deferred work
  for the Phase 8 batch runner.

- **`kreuzberg` is pinned `>=4.0,<5`.** `RESEARCH.md` records that the successor
  "Xberg" v1 line moved to Elastic-2.0 while the v4 line stayed MIT. A resolver
  must not be able to change our licence position by picking up a new major.

- **CI installs the `documents` extra for lint, types, test and coverage.**
  Without it mypy saw `Any` for every new adapter and checked nothing, and the
  MarkItDown and Kreuzberg integration tests skipped in CI exactly as they do
  locally — so Phase 2's adapters would have been verified nowhere. Everything
  the extra pulls is CPU-only, permissively licensed and wheel-installable on
  all three platforms. Docling stays out, which is the point of its own extra.

- **Correction to `RESEARCH.md`, verified against the packages themselves.**
  Category 1 describes Kreuzberg as "~71MB, ~20 deps". Version 4.10.2 has
  **zero** required Python dependencies — everything is optional, behind extras.
  The licence claim (MIT for the v4 line) is correct. Reality wins and is
  recorded here, per the plan's risk register.

- **`scripts/make_fixtures.py` no longer isolates git's config with
  `os.devnull`.** This container's `/dev/null` is a 48-byte regular file, and
  git refused it. A path that does not exist reads as an empty config on every
  platform and does not assume the null device behaves like a config file. The
  corpus is unchanged — `--check` still reports 22 files byte-for-byte.


### Post-Phase-1 follow-up (owner accepted the recommendations)

- **2026-08-20 — CI now runs on `claude/**` branches.** It had never run at all:
  the trigger named only `main`, which does not exist. The whole "verified in
  CI" fallback rested on a workflow that could not fire. See the verification
  log entry for the full finding and the correction it forced.
- **2026-08-20 — A blocking `tokenizers` CI job runs the `network` tests.**
  Marking those tests `network` kept the local suite fast and offline, but the
  existing `test` job runs a plain `pytest`, which skips them — so the marker
  had quietly turned "verified in CI" into "verified nowhere". The new job
  selects them explicitly. It is deliberately **not** `continue-on-error`: it is
  the only verification of the product's central feature, and an advisory job
  that goes yellow unnoticed is the same as no job.
- **2026-08-20 — Coverage is gated, not just reported.** `--cov-fail-under=85`
  scoped to `core` and `tokens`, the two packages the plan names. It passes at
  96.07% today, so it locks in the current standard rather than demanding new
  work. Closes Phase 0's Open question 4.
- **2026-08-20 — The `bytes` tokenizer ships.** Owner accepted the
  recommendation. It stays fenced exactly as built: never the default,
  `is_model_tokenizer=False`, its unit printed as `UTF-8 bytes`, and an explicit
  CLI warning against quoting it as a token count. Closes Open question 3.
- **2026-08-20 — Branch convention: `claude/phase-<n>-<slug>` is canonical.**
  The harness also assigns an auto-generated branch name per session; those are
  pushed as identical mirrors so nothing is stranded if a session ends
  unexpectedly, and can be deleted once the phase branch is merged. Recorded in
  `CONTRIBUTING.md`. Closes Open question 4 from Phase 1.
- **2026-08-20 — The repository name question is closed.** `RSD-Studio/tokenmill`
  resolves over both git and the GitHub API; the URLs in `pyproject.toml` and
  the README are correct. Closes Phase 0's Open question 2.
- **2026-08-20 — The offline tiktoken cache is a documented, verified path.**
  `TIKTOKEN_CACHE_DIR` is consulted before any download, and cached content is
  hash-checked, so a wrong cache is refused rather than used. That last property
  is what makes it safe to recommend, and it was tested rather than assumed.

- **2026-08-20 (Phase 1) — The data model is stdlib dataclasses, not pydantic.**
  The plan sanctioned either. Dataclasses win because `import tokenmill` then
  pulls in **zero** third-party modules, which keeps the `clean-core-install`
  guard meaningful and CLI start-up fast. Pydantic buys validation at trust
  boundaries and tokenmill has none — this is a library API called by our own
  CLI and GUI, not a request parser. When Phase 8 adds an HTTP surface, which
  does have a trust boundary, pydantic models belong there rather than in the
  core model. Reversible: the field sets are identical either way.
- **2026-08-20 (Phase 1) — Licence policy is enforced in the constructor, not
  documented.** `BackendInfo.__post_init__` raises if a copyleft or
  non-commercial backend declares `IsolationMode.IN_PROCESS`, and the registry
  re-checks at registration. `CONTRIBUTING.md` rule 2 is the thing the whole
  project's licence story rests on, and a rule that lives only in prose is a
  rule somebody will breach by accident. The conformance suite also asserts it
  for every installed backend, so a copyleft adapter added in any later phase is
  caught by a test that already exists.
- **2026-08-20 (Phase 1) — A measurement failure is not a conversion failure.**
  Discovered by running it: `NetworkRequired` is a `ConversionError`, so the
  first working pipeline threw away a successfully converted document when
  tiktoken could not reach its CDN. On an air-gapped machine that is every
  conversion. `TokenMeter` now absorbs the failure, counts come back `None`,
  character counts stay exact, and one warning explains it. The reverse — an
  estimate in place of a measurement — is the one thing this project will not
  do, and `ground_truth.json`'s `token_count: null` set that precedent in
  Phase 0.
- **2026-08-20 (Phase 1) — Added a `bytes` tokenizer. This one needs your
  sign-off; see Open question 3.** Both real tokenizer families download a
  vocabulary on first use, so on this machine the product had a converter and no
  measurement at all — which is most of the point of it. `bytes` counts UTF-8
  bytes: a fact about the text, exact, deterministic, needing nothing. It is
  fenced so it cannot be mistaken for a token count — `is_model_tokenizer=False`,
  its unit printed as `UTF-8 bytes`, an explicit CLI warning not to quote it as
  tokens, and it is never the default. It is what made the whole measurement path
  observable during this phase's verification.
- **2026-08-20 (Phase 1) — The CLI reports growth as growth.** A percentage in
  the summary line now follows the *count*, so `-45.5%` means 45.5% fewer and
  `+71.0%` means 71% more. The first version described everything as a
  "reduction" and printed a 71% increase as `-71.0%`. Found by running the
  documentation's own example backend, whose Markdown table is genuinely larger
  than its CSV input.
- **2026-08-20 (Phase 1) — `certifi` (MPL-2.0) is in the core install, and that
  is acceptable.** It arrives via `requests` ← `tiktoken`. MPL-2.0 is
  file-level copyleft: it obliges us to publish modifications to *its* files,
  and we make none. It is not viral the way AGPL/GPL are, and it does not
  restrict distributing tokenmill under Apache-2.0. Recorded because the licence
  audit found it and silence would have looked like nobody checked. Everything
  else in the core install is MIT, Apache-2.0, BSD, ISC or PSF; there is no AGPL
  and no GPL.
- **2026-08-20 (Phase 1) — `normalize_whitespace` preserves Markdown hard line
  breaks.** A line ending in two or more spaces before another line of text
  keeps exactly two. Stripping them saves a handful of tokens and silently
  changes how the document renders, and a post-processor advertised as
  non-destructive must not do that. markdownify's default `newline_style` is
  `spaces`, so this is a case the reference backend actually produces.
- **2026-08-20 (Phase 1) — Selection never silently substitutes a backend.** An
  explicit `--backend` that cannot run is an error. Falling back would produce a
  measurement attributed to a backend that did not make it, which defeats the
  point of measuring. The documented fallback *chain* for auto-selection is
  Phase 2, where there will be more than one candidate for a format.
- **2026-08-20 (Phase 1) — Three plugin groups, one mechanism, no special
  casing.** Backends, post-processors and tokenizers are all found through entry
  points, and the built-ins register exactly as a third party would. It costs a
  little indirection and it is the only way "add a backend without touching
  core" can be verified rather than asserted — which it now is, by installing a
  backend built from the tutorial's own code blocks.
- **2026-08-20 (Phase 1) — Opt-in test markers now skip rather than run.**
  `network`, `heavy` and `compress` were declared in Phase 0 but nothing acted
  on them, so `pytest` was attempting real downloads. They are skipped unless
  selected with `-m`, and reported as skips rather than deselected: a test that
  silently vanishes from the run is how a "verified" claim quietly stops being
  true.

- **2026-08-20 — Renamed the project from `tokenfold` to `tokenmill`.**
  `tokenfold` is taken on PyPI by a live, actively released project in the same
  niche (v0.4.0, uploaded five days ago). `pip install tokenfold` could never
  have been ours, and colliding with a same-niche competitor would confuse
  users. Owner picked `tokenmill` from `tokenmill` / `tokenpare` /
  `contextmill`; it is free on both PyPI and npm. Done before the first commit,
  as the plan requires. **The GitHub repository is still named
  `RSD-Studio/tokenfold`** — see Open question 2.
- **2026-08-20 — Apache-2.0 for the project licence.** As the plan recommends:
  permissive, includes an explicit patent grant, and matches the licence of most
  of the ecosystem we wrap.
- **2026-08-20 — `[project].dependencies` is empty at Phase 0.** Phase 0 ships
  no product logic, so it imports nothing. Each phase adds only what its code
  actually imports. This keeps the `clean-core-install` CI job meaningful from
  the first commit — right now it proves the install pulls in *exactly one*
  package.
- **2026-08-20 — `core` is also declared as an empty extra.** The real core
  dependencies live in `[project].dependencies`; the alias exists so that
  `pip install "tokenmill[core]"` and the plan's
  `uv pip install -e ".[dev,core]"` both work as written.
- **2026-08-20 — mypy `strict` over everything, not just `core`/`tokens`.** The
  plan requires strict on `core` and `tokens`; at this size there is no reason
  to be laxer elsewhere. Thin third-party adapters can get a documented
  per-module relaxation later if a library's stubs make strictness pointless.
- **2026-08-20 — Fixtures are byte-reproducible, not merely regenerable.** The
  plan asks for deterministic generation. Making it *byte*-deterministic turns
  the acceptance criterion into a hash comparison a CI job can enforce, which
  also catches accidental hand-edits of the corpus. Required rebuilding OOXML
  zips with fixed member timestamps, ReportLab's `invariant` mode, and pinned
  git author/committer dates.
- **2026-08-20 — `ground_truth.json` records no token counts.** A token count
  is meaningless without naming its tokenizer, and no tokenizer is available in
  this sandbox (see Environment). Rather than publish an estimate dressed as a
  measurement, the manifest stores exact character and word counts, sets
  `token_count: null`, and states in `token_count_note` that the ~20k-token
  target was hit with the ~4-chars-per-token rule of thumb. Real measured counts
  land in Phase 1.
- **2026-08-20 — `sample_repo/`'s `.git` directory is not committed.** Git
  stores a nested repository as a gitlink and keeps none of its contents, so
  committing it would hand every cloner an empty directory. The working files
  are committed instead, and `ensure_sample_repo_git()` materialises the
  repository on demand — from `scripts/make_fixtures.py`, or from the pytest
  `sample_repo` fixture, so a fresh clone needs no extra step. Recreation is
  deterministic because the author and committer dates are pinned: a test
  asserts the rebuilt HEAD equals the hash recorded in `ground_truth.json`.
- **2026-08-20 — The `heavy` extras group exists but stays permanently empty.**
  Marker, MinerU, olmOCR and Surya are invoked out of process. Declaring the
  group documents the tier without ever letting `pip` resolve a GPU dependency
  for us.

## Deferred / future work

### From Phase 2

- **Docling's PDF path is implemented but has never been run.** The adapter is
  complete — its failure path is verified here, cleanly reporting the blocked
  host — but the success path needs `huggingface.co`. It cannot be covered by a
  `network`-marked test "without a multi-gigabyte download": docling is 122
  packages and 5.2 GB before the models are fetched at all. The manual-dispatch
  `docling` CI job exists to run it; **I cannot trigger it** (`403 Resource not
  accessible by integration` — this session's token has no `actions: write`).
  Open question 1.
- **OCR.** Every backend in this tier returns an empty document for
  `scanned.pdf` and every one of them warns about it. That warning is the
  honest answer until Phase 9.
- **A layout model for multi-column PDFs.** pdfplumber interleaves columns; the
  adapter detects a gutter and warns, and stops there. Reordering a page is a
  layout engine, not an adapter. `pypdf` and `kreuzberg` both get our fixture
  right, and the warning points at them.
- **`warnings.catch_warnings` is not thread-safe.** Two Phase 2 adapters use it
  — one to keep an import-time warning non-fatal, one to filter Docling's
  internal deprecation. Nothing runs conversions concurrently today. The Phase 8
  batch runner, and any process-pool parallelism from `DEVELOPMENT_PLAN.md` §4,
  will have to account for it.
- **The `documents` extra pulls more than it looks like.** markitdown's Office
  converters bring pandas, lxml and mammoth, and magika brings onnxruntime and
  numpy. All CPU-only, all permissive, all wheel-installable — but it is not the
  "light-ish" the plan's §1.6 implies, and it is worth re-checking if the extra
  ever needs to shrink.
- **Backend preference is not user-configurable.** `core/preferences.py` is a
  default and `--backend` is the override, but there is no way to say "always
  prefer pypdf for PDFs" in `tokenmill.toml`. Left out rather than stubbed; it
  belongs with the Phase 8 settings panel, which needs the same thing.
- **Reference-style Markdown tables, and table reformatting.** pdfplumber's
  tables are emitted as GitHub-flavoured Markdown only. CSV/TOON/JSON encoders
  are Phase 5.


- **A real BPE token count still cannot be produced in this sandbox**, and that
  has not changed — the proxy still denies both tokenizer hosts. What has changed
  is that `tests/unit/test_tokens_network.py` now runs in CI on every push, in a
  blocking job, and passes: `"hello world"` really is 2 tokens under
  `o200k_base`. Token counting is therefore **CI-verified, not locally
  observed**, and any future work on the measurement layer inherits that
  one-round-trip feedback loop until the hosts are allow-listed.
- **Fallback chains between backends.** Phase 1 selects one backend and reports
  it. Trying the next when the preferred one fails, and recording which actually
  ran, is a Phase 2 deliverable and is not stubbed here.
- **URL fetching.** `Source.from_url` exists and validates the scheme, but no
  backend fetches anything. `robots.txt`, redirect limits, size caps and the
  offline guarantee are Phase 3. `ConvertOptions.allow_network` exists and
  defaults to `False`; the offline guarantee for *local* conversion is already
  tested by making `socket.connect` raise.
- **Repository ingestion.** `SourceKind.REPO` exists; no backend claims `repo`.
  Phase 4.
- **Output formats beyond Markdown and text.** `OutputFormat` has two members.
  CSV, TOON and JSON encoders are Phase 5, so they are absent rather than
  stubbed.
- **Cost estimation.** The plan places it in the token layer with user-supplied
  rates only. There is no rate input yet, so there is no estimate — leaving it
  out beats a function that returns `None`.
- **`SubprocessConverter`.** `IsolationMode.SUBPROCESS`, `LicenseTier.COPYLEFT`
  and `BackendFailed.stderr` all exist and are enforced, but the shared
  subprocess machinery is Phase 7. A subprocess backend written before then must
  supply its own.
- **Reference-style Markdown links.** The `links` post-processor handles inline
  links and images and deliberately leaves `[text][ref]` untouched rather than
  mangling it. Full link handling (inline / reference / strip) is a Phase 5
  deliverable.
- ~~**Coverage is not gated in CI.**~~ **Done.** Gated at 85% on `core` and
  `tokens`; the job passes at 96.07%.
- **Phase tags still cannot be pushed** (`send-pack: unexpected disconnect`, as
  in Phase 0). Recording the commit SHA here instead, as instructed. Phase 0
  ended at `772d99b`; Phase 1's content ends at `e18b3d8`, and Phase 1 was first
  proven green at `3aa6e59`. Phase 2's first all-green commit is `2e675f5`; its
  content ends at `a9d36be`.

### Carried over from Phase 0

- **Real footnotes in `report.docx`.** The plan lists footnotes among that
  fixture's features. python-docx has no footnote API, and hand-writing the
  footnote XML parts is brittle enough that it is not worth it until a backend
  actually needs testing against them. The fixture uses a `Note:` paragraph
  instead. Belongs to Phase 2 if a document backend claims footnote support.
- ~~**Windows and macOS verification.**~~ **Done.** The first CI runs happened
  during Phase 1's follow-up. Windows initially failed on line-ending
  translation inside the fixture corpus; with that fixed, the suite is green on
  ubuntu, macOS and Windows. See the verification log entry "First CI runs".
- ~~**Python 3.12 and 3.13 verification.**~~ **Done.** Green across
  3.11/3.12/3.13 on all three operating systems — nine test cells and nine
  clean-core-install cells.
- ~~**GitHub name availability check.**~~ **Done.** `RSD-Studio/tokenmill`
  resolves over both git and the GitHub API.
- **`docs/ARCHITECTURE.md`, `ADDING_A_BACKEND.md`, `LICENSES.md`, `BACKENDS.md`,
  `BENCHMARKS.md`, `FAQ.md`.** Deliberately not created as empty placeholders —
  each is written in the phase that produces the thing it documents (1, 1, 7, 2,
  10, 12 respectively). The README links to them and marks which phase each is
  due in.
- **The `phase-0-complete` tag exists locally but is not on the remote.** This
  session's git remote accepts branch refs but rejects tag pushes (`send-pack:
  unexpected disconnect`, reproduced on four attempts with backoff). The plan
  asks for a tag per completed phase so progress can be diffed. The four
  commits are all pushed; only the tag is missing. Either push it yourself from
  a normal clone (`git tag phase-0-complete 772d99b && git push origin
  phase-0-complete`) or tell me and I will drop the tagging convention in favour
  of recording each phase's commit SHA here instead.
- **Release checklist in `CONTRIBUTING.md`.** Stubbed as "fills out in Phase 11"
  because publishing does not exist yet.

## Open questions for the owner

Phase 2's three questions were answered on 2026-08-22 and the answers are
implemented; see Decisions for each, and the table below. One new question has
opened since, and it needs owner-level access rather than a decision.

**1. CI cannot schedule runners — please check the Actions billing state.**
Runs 25 through 28 all failed within seconds, every job at `runner_id: 0`, no
steps, no logs, across all three runner labels. Run 24 on `Main` succeeded 2h20m
earlier. The evidence that this is not our workflow file is in the verification
log: all 24 job records were created with correct expanded names and the
`docling` job correctly evaluated its `if:` to `skipped`, so the YAML parsed and
expressions ran. The likeliest cause is exhausted Actions minutes or a spending
limit — ~28 runs × 24 jobs in three days, with macOS billing at 10x and Windows
at 2x. These sessions cannot re-run jobs (403 `Resource not accessible by
integration`), so only you can see the billing page.

Until it is resolved, nothing is proven on Windows, macOS, Python 3.12/3.13, or
against real tokenizer vocabularies. Local green on `e65337b` is recorded and is
not the same claim.

Two things remain *pending* rather than open, in the sense that they need an
action rather than a decision:

- **Docling's PDF path is still unverified.** The weekly job will cover it from
  the next Sunday run on `Main` — assuming runners are available by then. Until
  one has run, the honest status is unchanged: implemented, its failure path
  observed here, its success path never executed anywhere.
- **A one-off dispatch would close it sooner.** Actions → CI → Run workflow.
  Tell me what it shows and I will record it.

### Closed

| # | Question | Outcome |
|---|---|---|
| Phase 0 #1 | Token counting unverifiable in the sandbox | Closed — verified in CI by a blocking job. `"hello world"` is 2 tokens under `o200k_base` |
| Phase 0 #2 | Is the GitHub repository still named `tokenfold`? | Closed — it is `RSD-Studio/tokenmill`; verified over git and the API |
| Phase 0 #3 | Branch convention | Closed — `claude/phase-<n>-<slug>` canonical, harness branches mirrored. In `CONTRIBUTING.md` |
| Phase 0 #4 | Should CI gate coverage? | Closed — gated at 85% on `core` and `tokens`; passing at 96.07% |
| Phase 1 #3 | Should the `bytes` tokenizer ship? | Closed — yes, with the fencing it already has |
| Phase 1 #4 | Branch naming | Closed — same as Phase 0 #3 |
| Phase 1 #1 | Create `main` and make it the default branch | Closed — done by the owner; `Main` exists and Phase 1 is merged into it |
| Phase 2 #1 | Docling's PDF path is unverified and I cannot dispatch the job | Closed — the job now runs weekly on `Main` as well as on demand, which needs no new token scope |
| Phase 2 #2 | What should the "before" count be for a binary document? | Closed — there is none. The headline is the output's cost; the input is reported as a size |
| Phase 2 #3 | Is the default branch's capital `Main` deliberate? | Closed — yes. The two lowercase URLs now match, and CI accepts both spellings |
