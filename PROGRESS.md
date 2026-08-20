# Progress

_Last updated: 2026-08-20 by Claude Code_

## Status at a glance

| Phase | Name | Status | Exit gate |
|-------|------|--------|-----------|
| 0 | Scaffolding and toolchain | ✅ Complete | passed 2026-08-20 |
| 1 | Core architecture | ✅ Complete | passed 2026-08-20 |
| 2 | Document backends (light tier) | ⬜ Not started | — |
| 3 | Web backends | ⬜ Not started | — |
| 4 | Repository backends | ⬜ Not started | — |
| 5 | Post-processing, formats, measurement depth | ⬜ Not started | — |
| 6 | Prompt compression (optional tier) | ⬜ Not started | — |
| 7 | Isolation layer and license enforcement | ⬜ Not started | — |
| 8 | GUI (FastAPI + NiceGUI) | ⬜ Not started | — |
| 9 | Heavy backends (GPU tier, install-docs-only) | ⬜ Not started | — |
| 10 | Benchmark harness | ⬜ Not started | — |
| 11 | Packaging, distribution, release | ⬜ Not started | — |
| 12 | Documentation completion and article support pack | ⬜ Not started | — |

## Current phase: 1 — Core architecture (complete)

**Goal:** the plugin system and token measurement working end to end, proven by
two deliberately trivial backends.

**Phase 1's content ends at commit `e18b3d8`** (the commit after it records only
this SHA). Tags cannot be pushed from these sessions — see Deferred work.

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
| 3 | Token counts match a hand-verified tiktoken result on a known string | ❌ **Not verified anywhere yet.** `openaipublic.blob.core.windows.net` is still denied by the sandbox proxy, so no real BPE vocabulary can be loaded here. The assertions live in `tests/unit/test_tokens_network.py` behind the `network` marker and have **never been executed** — and, as the follow-up entry in the verification log records, neither had CI. CI is now fixed and has a blocking `tokenizers` job that runs them; **the first green run of that job is what will close this criterion.** |
| 4 | `tokenmill convert tests/fixtures/boilerplate.html` returns Markdown and a real before/after count | ⚠️ **Partly observed.** Markdown: yes, read and judged correct. A real before/after count: yes with `--tokenizer bytes` (12,481 → 6,802 UTF-8 bytes, −45.5%); **not** with `o200k_base`, which cannot load here. Byte counts are not token counts. |
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

## Backend status

Two backends exist and are wired, tested and verified. The rest are the planned
set, with licences taken from `docs/research/RESEARCH.md` and **not yet
independently re-verified**. Licences get checked at the moment each adapter is
implemented, and corrections are recorded under Decisions.

The Phase 1 licences below were verified against the installed package metadata
during the exit gate, not taken on trust: markdownify reports `MIT License`
(v1.2.3), tiktoken `MIT License`, typer `MIT`.

| Backend | Domain | License (per RESEARCH.md, unverified) | Tier | Wired | Tested | Notes |
|---------|--------|---------------------------------------|------|-------|--------|-------|
| plaintext | text | Apache-2.0 (ours) | core | ✅ | ✅ | Phase 1 reference backend. Passes text/Markdown through; warns on non-UTF-8 input |
| markdownify_html | web | MIT **(verified v1.2.3)** | core | ✅ | ✅ | Phase 1 reference backend. Converts markup faithfully; **does not strip boilerplate** — that is Phase 3 |
| markitdown | documents | MIT | documents | ❌ | ❌ | Phase 2; breadth, weak PDF layout |
| pdfplumber | documents | MIT | core | ❌ | ❌ | Phase 2 |
| pypdf | documents | BSD-3 | core | ❌ | ❌ | Phase 2 |
| kreuzberg | documents | MIT (v4 line only) | documents | ❌ | ❌ | Phase 2; v1 "Xberg" line is Elastic-2.0 — pin v4 |
| docling | documents | MIT | docling | ❌ | ❌ | Phase 2; pulls PyTorch, must stay out of core |
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
| `o200k_base`, `cl100k_base`, `p50k_base`, `r50k_base` | tiktoken | MIT (verified) | BPE tokens | ✅ | ⚠️ CI only | Resolution, error paths and the "unavailable" path are tested here; **no real count has ever been produced in this sandbox** |
| `hf:<model>` | HuggingFace `tokenizers` | Apache-2.0 | model tokens | ✅ | ⚠️ CI only | Behind the `tokenizers` extra. Same download constraint |
| `bytes` | ours | Apache-2.0 | **UTF-8 bytes, not model tokens** | ✅ | ✅ | Download-free. Golden vectors hand-checked |

## Decisions made

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

- **A real BPE token count has never been produced in this sandbox.** Everything
  in `tests/unit/test_tokens_network.py` is unexecuted. The expected values in
  it (for instance `"hello world"` counting as 2 tokens under `o200k_base`) are
  written from the published behaviour of those encodings and **the first CI run
  is what confirms them**. If one is wrong, the number gets corrected — not the
  assertion loosened. Blocks acceptance criterion 3; see Open question 1.
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
- **Coverage is not gated in CI, only reported.** Open question 4 from Phase 0 is
  still unanswered. `core` is at 99.4% and `tokens` at 88.5%, so a
  `--cov-fail-under` scoped to those two packages would pass today.
- **Phase tags still cannot be pushed** (`send-pack: unexpected disconnect`, as
  in Phase 0). Recording the commit SHA here instead, as instructed. Phase 0
  ended at `772d99b`; Phase 1's content ends at `e18b3d8`.

### Carried over from Phase 0

- **Real footnotes in `report.docx`.** The plan lists footnotes among that
  fixture's features. python-docx has no footnote API, and hand-writing the
  footnote XML parts is brittle enough that it is not worth it until a backend
  actually needs testing against them. The fixture uses a `Note:` paragraph
  instead. Belongs to Phase 2 if a document backend claims footnote support.
- **Windows and macOS verification.** Everything above was observed on Linux
  only — this sandbox has no other platform. The CI matrix covers
  ubuntu/macos/windows from the first commit, so the first CI run is the real
  cross-platform check. Until it goes green, treat Windows path and encoding
  behaviour as unverified.
- **Python 3.12 and 3.13 verification.** Only 3.11.15 exists locally. Same
  situation: CI is the check.
- **GitHub name availability check.** Not performable from this session (see the
  verification log). The owner controls the namespace.
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

Everything that was mine to decide has been decided and implemented; the
decisions are listed above. What remains needs access I do not have.

**Both of these are now blocking the same thing** — proving that tokenmill
counts tokens correctly. Nothing else in the project is waiting on anything.

1. **Create `main` and make it the default branch.** The repository has no
   default branch: its only branches are the three `claude/**` ones, so "Phase 0
   is complete and merged" is not yet true in git terms — there is nothing to
   have merged into. This is why CI had never run, and it will keep causing
   trouble (pull requests have no base, `CHANGELOG.md`'s `[Unreleased]` link
   points at `/commits/main` and 404s, and the Phase 11 release workflow will
   assume it).

   Suggested, from a clone:

   ```bash
   git fetch origin claude/phase-1-core-architecture
   git branch main origin/claude/phase-1-core-architecture
   git push origin main
   ```

   Then set `main` as the default branch in **Settings → General → Default
   branch**. Phases 0 and 1 are already in that history, so nothing needs
   merging retroactively.

   I have not done this myself: creating a repository's default branch changes
   how the project looks to everyone who visits it, and it needs a settings
   change I cannot make.

2. **Watch the first `tokenizers` CI job, or unblock local verification.**
   Acceptance criterion 3 is still unverified. CI is now fixed and pushing this
   branch should trigger it; the `tokenizers` job is what will finally execute
   `tests/unit/test_tokens_network.py` against a real BPE vocabulary. **If that
   job fails, the expected counts in it are mine and are wrong** — they were
   written from published encoding behaviour and never executed. Send me the
   failure and I will correct the numbers, not loosen the assertions.

   Separately, and still my recommendation: allow-listing
   `openaipublic.blob.core.windows.net` and `huggingface.co` for these sessions
   would let me verify token counting where I develop it, instead of finding out
   one round-trip later. Failing that, the cheapest unblock is to run this on
   any networked machine and send me the resulting directory:

   ```bash
   TIKTOKEN_CACHE_DIR=./tiktoken-cache python -c "
   import tiktoken
   for n in ('o200k_base', 'cl100k_base', 'p50k_base', 'r50k_base'):
       tiktoken.get_encoding(n)
   "
   ```

   It is four files, and tiktoken hash-checks them, so a corrupted copy is
   refused rather than silently miscounting. I would use it via
   `TIKTOKEN_CACHE_DIR` and **not** commit it — vendoring a vocabulary into the
   repository is still the option I would rather avoid.

### Closed

| # | Question | Outcome |
|---|---|---|
| Phase 0 #1 | Token counting unverifiable in the sandbox | Superseded by #2 above. Fallback (b) implemented and now actually works, since CI runs |
| Phase 0 #2 | Is the GitHub repository still named `tokenfold`? | Closed — it is `RSD-Studio/tokenmill`; verified over git and the API |
| Phase 0 #3 | Branch convention | Closed — `claude/phase-<n>-<slug>` canonical, harness branches mirrored. In `CONTRIBUTING.md` |
| Phase 0 #4 | Should CI gate coverage? | Closed — gated at 85% on `core` and `tokens`; passing at 96.07% |
| Phase 1 #3 | Should the `bytes` tokenizer ship? | Closed — yes, with the fencing it already has |
