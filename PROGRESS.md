# Progress

_Last updated: 2026-08-27 by Claude Code_

## Status at a glance

| Phase | Name | Status | Exit gate |
|-------|------|--------|-----------|
| 0 | Scaffolding and toolchain | ✅ Complete | passed 2026-08-20 |
| 1 | Core architecture | ✅ Complete | passed 2026-08-20 |
| 2 | Document backends (light tier) | ✅ Complete, merged to `Main` | passed 2026-08-21 |
| 3 | Web backends | ✅ Complete | passed 2026-08-22 (local; CI cannot schedule runners) |
| 4 | Repository backends | ✅ Complete | passed 2026-08-22 (local; CI cannot schedule runners) |
| 5 | Post-processing, formats, measurement depth | ✅ Complete | passed 2026-08-24 (local; CI cannot schedule runners) |
| 6 | Prompt compression (optional tier) | 🟨 **Implemented; success path unverified** | ⚠️ gate NOT passed. A CI job that would close it was added on 2026-08-26 and is itself unverified: dispatching a workflow returns 403 for this integration |
| 7 | Isolation layer and license enforcement | ✅ Complete | passed 2026-08-26 |
| 8 | GUI (FastAPI + NiceGUI) | ✅ Complete | passed 2026-08-27 |
| 9 | Heavy backends (GPU tier, install-docs-only) | 🟨 **Complete; nothing run on hardware** | gate passed 2026-08-27 for the CPU-only path, which is the criterion. No heavy backend has converted a document: no GPU here, and the weight host is denied |
| 10 | Benchmark harness | 🟨 **Fidelity-scoring slice complete** (2026-08-24); the harness itself in progress | slice gate passed 2026-08-24 |
| 11 | Packaging, distribution, release | ⬜ Not started | — |
| 12 | Documentation completion and article support pack | ⬜ Not started | — |

## Current session: the repairs, then Phases 9–12

The owner's §3 decisions are implemented and each is a commit. **Ten repairs**
— nine asked for, one found on arrival — then Phase 9. Highlights, all measured
rather than argued:

1. **N5 is reversed.** `aggressive_whitespace` was to be deleted unless it could
   be shown to earn its place. Measured across all fifty backend-by-fixture
   cells rather than three, it saves **18.3% on `tables.pdf` through
   `markitdown` at unchanged fidelity** — MarkItDown pads its table columns and
   that padding is 18% of the document.
2. **D6 was a correctness bug, not a tidiness one.** A repository containing a
   document that *quotes* repomix's file marker made the adapter invent a file
   that does not exist. `--style json` removes the ambiguity.
3. **D2 is fixed and the parallelism it unlocks makes the published batch
   slower.** 0.86x on the 20-file corpus batch, 3.12x on a subprocess-backend
   batch. The GIL explains both, and the null result is published first.
4. **`RESEARCH.md` was wrong about two more licences**, and this time in the
   safe direction: Marker and Surya are Apache-2.0, not GPL-3.0. MinerU is
   neither — Apache plus a revenue threshold and an online-service attribution
   obligation, which needed a fourth `LicenseTier`.
5. **The licence classifier called SSPL, BUSL and Elastic-2.0 permissive.** Same
   shape as the Phase 7 defect, found the same way.

## Re-evaluation: `docs/REVIEW_PHASES_0_8.md`

Written at the end of the Phase 7/8 session, superseding
`docs/REVIEW_PHASES_0_6.md` (which stays in the repository, for the same reason
the one before it did). It carries the whole-corpus table, the status of every
defect, seven new ones, and a recommendation **to start Phase 9** after one
repair — `tokenmill gui --server` has no authentication, and Phase 9 is the
phase whose backends live on other machines.

**The three results that matter most**, all from this session:

1. **Defect D3 is closed.** `boilerplate.html` through `trafilatura` is
   **3,716 → 629 `o200k_base` tokens, −83.1%**, read out of CI run 85's log.
   Six phases of "we cannot say this in the unit the claim is about" ends here.
2. **The byte figures were optimistic and now we know by how much.** CSV saves
   60.2% of JSON's bytes and **36.0%** of its tokens; TOON 55.8% and **29.9%**.
   Neither published claim reproduces on our data in its own unit, and the two
   units do not even rank the formats in the same order.
3. **The AGPL tool was worth its isolation.** PyMuPDF4LLM is the most faithful
   backend in the corpus on all three scorable PDFs, and on `twocolumn.pdf` it
   scores 0.972 where the previous ceiling was 0.667.

## Previous re-evaluation: `docs/REVIEW_PHASES_0_6.md`

Written at the end of this session, superseding `docs/REVIEW_PHASES_0_4.md`
(which stays in the repository — its defect numbering is referenced everywhere,
and a superseded review that disappears is one nobody can check). It carries the
whole-corpus table with tokens beside fidelity, the status of every defect from
the previous list, eight new ones, and a recommendation **against starting
Phase 7 yet**.

## Current phase: the Phase 10 fidelity slice (complete), then 5, then 6

Phases 3 and 4 are merged into `Main` (PRs #11 and #13). The fidelity-scoring
slice of Phase 10 was built first, ahead of Phase 5, on the owner's instruction
and for the reason `docs/REVIEW_PHASES_0_4.md` §8 gives: Phase 5's
post-processors can each be measured as a win in tokens and a loss in fidelity,
and without a fidelity metric its defaults would be argued rather than measured.

**CI came back to life on 2026-08-26**, when the owner made the repository
public; the five-day runner-scheduling failure was a billing condition, not our
YAML. Its first real runs found 24 failures and then 1 more — three of them
mine, twenty-one of them latent in Phase 4 since 2026-08-22, and the last a
CI-only rendering difference in a help-text assertion. See the verification log
entry for that date. Until a run comes back green, everything below is still
local green, which is not the same claim.

## Previous phase: 2 — Document backends (complete)

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

### 2026-08-22 — Blocked-host re-probe (start of Phase 3)

Re-probed before designing anything, as instructed, and one result had changed.

| Host | Result |
|---|---|
| `pypi.org/simple/` | **200** |
| `registry.npmjs.org/repomix` | **200** |
| `raw.githubusercontent.com` | **301** |
| `index.crates.io/config.json` | **200** — *changed, see below* |
| `static.crates.io/crates/code2prompt/...` | **200** — *changed* |
| `crates.io/api/v1/crates/code2prompt` | **403** |
| `example.com` | **403 CONNECT** |
| `openaipublic.blob.core.windows.net` | **403 CONNECT** |
| `huggingface.co` | **403 CONNECT** |

Both tokenizer hosts and `example.com` are unchanged, and the gateway logs the
denials itself. Every local figure below is `--tokenizer bytes`, i.e. UTF-8
bytes, and is labelled as such.

**Correction to the handover's environment table.** It records `crates.io` as
403 and concludes "code2prompt likely not installable from source". The *API*
is 403; the **registry index and the crate download host are both 200**, and
they are what `cargo install` uses. `cargo install code2prompt` succeeded here
and produced `code2prompt 4.3.0`. All three Phase 4 runtimes are therefore
runnable in this sandbox, which is better than the handover expected.

### 2026-08-22 — Phase 3 dependency probes, before any adapter was written

Measured rather than assumed, because the plan's §1.6 tiering is a claim about
install weight and the only way to check it is to install things.

| Install | Packages | Size | Notes |
|---|---|---|---|
| core (before Phase 3) | 28 | 72 MB | baseline |
| core + `trafilatura` | 40 | 126 MB | +12 packages, +54 MB — mostly lxml |
| core + `gitingest` | 42 | 82 MB | +14 packages, +10 MB |
| `crawl4ai` alone | **94** | **677 MB** | before Playwright downloads a browser |
| (`docling`, Phase 2, for scale) | 122 | 5.2 GB | |

**A licence finding, and it is the reason this probe matters.**
`trafilatura` → `courlan` → **`tld`**, which is a *required* dependency and is
licensed `MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later`. Read from the installed
package metadata; `RESEARCH.md` records only "Trafilatura — Apache-2.0", which is
true of trafilatura and incomplete about its tree.

It is a **disjunction**: the recipient chooses one, and tokenmill takes MPL-1.1
— file-level copyleft, the same shape as the `certifi` MPL-2.0 accepted in
Phase 1, obliging us only to publish changes to `tld`'s own files, of which we
make none. **No GPL obligation is incurred and none is accepted.** Recorded in
`docs/LICENSES.md` so the next person to grep the tree for "GPL" finds the
answer rather than raising a defect. Flagged to the owner as a judgement call
that is mine to make but not mine to make silently.

A full audit of the 94-package `crawl4ai` resolution found **no GPL, no AGPL and
no PyTorch**; Crawl4AI and Playwright are both Apache-2.0.

### 2026-08-22 — Phase 3 exit gate

From a venv synced with `--extra dev --extra fixtures --extra documents --extra
web`, plus `crawl4ai` and `playwright==1.56.0` installed by hand for the browser
tests (see "Verification notes" below).

- Command: `uv run ruff check .`
- Result: `All checks passed!`

- Command: `uv run ruff format --check .`
- Result: `84 files already formatted`

- Command: `uv run mypy`
- Result: `Success: no issues found in 67 source files`

- Command: `uv run pytest -q --cov=tokenmill`
- Result: `687 passed, 38 skipped in 27.10s`, `TOTAL 2223 stmts, 90%`. The skips,
  all reported by name:
  ```
  SKIPPED [6]  needs the optional dependency 'docling'
  SKIPPED [2]  needs a GPU or a multi-gigabyte model download; run with -m heavy
  SKIPPED [8]  needs a Playwright browser download; run with -m browser
  SKIPPED [2]  crawl4ai needs network access for 'html' and allow_network is False
  SKIPPED [4]  docling is not available here
  SKIPPED [11] needs real network access (a tokenizer vocabulary download)
  SKIPPED [5]  needs real network access (a tokenizer vocabulary download)
  ```

- Command: `uv run pytest -q --cov=tokenmill.core --cov=tokenmill.tokens --cov-fail-under=85`
- Result: `Required test coverage of 85% reached. Total coverage: 94.45%`

- Command: `uv run python scripts/make_fixtures.py --check`
- Result: `OK: 23 files reproduced byte-for-byte` (22 before Phase 3; the new
  file is `jsrendered.html`)

- Command: `uv run pytest -q -m browser`
- Result: `8 passed, 717 deselected in 14.20s`

- Command: `uv run tokenmill backends --all`
- Result:
  ```
  id                domains    license       tier        isolation   availability
  ----------------  ---------  ------------  ----------  ----------  ---------------------------
  crawl4ai          web        Apache-2.0    permissive  in-process  available
  docling           documents  MIT           permissive  in-process  missing dependency: docling
  kreuzberg         documents  MIT           permissive  in-process  available
  markdownify_html  web        MIT           permissive  in-process  available
  markitdown        documents  MIT           permissive  in-process  available
  pdfplumber        documents  MIT           permissive  in-process  available
  plaintext         text       Apache-2.0    permissive  in-process  available
  pypdf             documents  BSD-3-Clause  permissive  in-process  available
  readability       web        Apache-2.0    permissive  in-process  available
  trafilatura       web        Apache-2.0    permissive  in-process  available
  ```

**The plan's sandbox-verification commands for this phase**, translated from
`tokenfold` to `tokenmill`:

- Command: `uv run tokenmill convert tests/fixtures/boilerplate.html --backend trafilatura --tokenizer bytes`
- Result:
  ```
  source:   boilerplate.html
  backend:  trafilatura
  format:   markdown
  duration: 576 ms
  post:     normalize_whitespace
  tokens:   12,481 -> 2,854  (-77.1%, bytes)
  page:     41.7% of 4,902 visible characters removed as boilerplate
  ```

- Command: the same with `--backend markdownify_html`
- Result:
  ```
  tokens:   12,481 -> 6,802  (-45.5%, bytes)
  page:     no boilerplate removed; Markdown syntax added 38.7% to 4,902 visible characters
  ```

- Command: `uv run tokenmill convert https://example.com --backend trafilatura`
- Result: **not run.** `example.com` is denied at the egress proxy with a 403
  CONNECT, as it was in the handover. The live-URL path is covered by
  `network`-marked tests and is **unverified here**. The fetcher itself is
  verified against a real HTTP server on loopback — see below.

- Command: `uv run pytest -q tests/integration/test_web_backends.py`
- Result: `23 passed, 8 skipped` (the 8 are the browser tests, opt-in)

**The measured table, all four read rather than inferred:**

| Backend | Output bytes | Byte reduction | Page text removed | Markers left | Headings | Table |
|---|---|---|---|---|---|---|
| `trafilatura` | 2,854 | **−77.1%** | 41.7% | **0 of 6** | 6 of 6 | ✅ |
| `readability` | 2,864 | −77.1% | 41.6% | 0 of 6 | 6 of 6 | ✅ |
| `crawl4ai` | 3,394 | −72.8% | 30.8% | **3 of 6** | 6 of 6 | ✅ |
| `markdownify_html` | 6,802 | −45.5% | **−38.7% (added)** | 6 of 6 | 6 of 6 | ✅ |

**The emitted Markdown, read rather than assumed** (`/tmp/tf.md`, 2,854 bytes):
the ATX title, all five `##` section headings, all seven article paragraphs
complete and unbroken, and the 7×5 summary table as a real Markdown table with
its header and separator rows. Grepped for each of the manifest's
`boilerplate_markers_must_be_absent` and found **none of the six**.

**Acceptance criteria, one by one:**

| # | Criterion | Result |
|---|---|---|
| 1 | Reduction on the heavy-boilerplate fixture in the same order of magnitude as RESEARCH.md's ~70–90% | ⚠️ **Met in bytes: −77.1%, inside the band.** In *model tokens* — the unit the published figures use — **unverified**: both tokenizer hosts are denied here. Asserted by `tests/unit/test_web_tokens_network.py`, which prints the figure for the CI log. No token percentage is published anywhere until a green run prints one. |
| 2 | No network access when converting a local HTML file, asserted by making the socket layer raise | ✅ **Observed.** `TestOfflineGuarantee` monkeypatches `socket.socket.connect` and `socket.create_connection` to raise, and converts `boilerplate.html` through auto-selection. A second test asserts `--offline` refuses a URL *before* opening a socket rather than fetching and discarding. |
| 3 | *(exit gate)* Measured reduction recorded in PROGRESS.md and docs/BENCHMARKS.md | ✅ Both, with the units stated and the token figure marked unverified. |
| 4 | *(exit gate)* Offline guarantee test passes | ✅ |

**Verification notes, so nothing here is overstated:**

- **The live-URL path has never run.** `example.com` is blocked. The fetcher is
  verified against a real `http.server` on `127.0.0.1` — 29 tests covering
  redirect chains, the redirect cap, scheme-change refusal, the byte cap at and
  over the limit, `robots.txt` allow and disallow, a disallow never requesting
  the page itself, charset transcoding, HTTP error statuses, timeouts and a
  refused connection. Real sockets, real headers, real urllib. A mock would have
  replaced the code under test, since all of that behaviour lives inside urllib.
- **crawl4ai's browser needs a version match this sandbox got by luck.**
  Playwright 1.62 wants Chromium revision 1234; the sandbox has 1194, which is
  what Playwright **1.56.0** expects. Pinning playwright to 1.56.0 locally made
  the eight browser tests runnable. That pin is *not* in `pyproject.toml` — it
  is a fact about this container, not about the project — so on a normal machine
  `playwright install chromium` is the step, and the adapter reports a missing
  browser as an actionable failure. Recorded so nobody mistakes the local pin
  for a project decision.

**Bugs found and fixed during verification**, every one by running something:

1. **crawl4ai was not using a browser at all.** Its `_crawl` routes a `file://`
   URL around the browser unless `process_in_browser` (or one of a handful of
   other flags) is set, so the adapter returned a parse of the response body
   while its docstring claimed it rendered JavaScript. Found by building
   `jsrendered.html` and getting the placeholder back. Fixed; verified by the
   fixture returning the hydrated article.
2. **The JS fixture's sentinel was in its own source.** The first version
   embedded `RSD-TOKENMILL-RENDERED-9317` whole inside the script, so "the
   sentinel is in the output" was true of a plain read of the file. The script
   now joins it from two halves at run time, and a test asserts the whole string
   appears nowhere in the bytes — otherwise the backend test passes vacuously.
3. **crawl4ai refuses small client-rendered pages.** Its anti-bot detector
   inspects the **un-rendered** body and rejects anything under 5,000 bytes with
   fewer than 50 characters of visible text as
   `Structural: minimal_text on small page`. That is a false positive on exactly
   the class of page a browser-driving backend exists for, and it made the first
   fixture unrenderable. Documented, asserted, and the fixture's placeholder is
   a full sentence so the success path stays reachable.
4. **I documented readability as trading precision for recall.** That is the
   algorithm's general reputation and it is not what happens here: its output is
   **byte-identical to trafilatura's** apart from the spacing inside the table's
   separator row. Corrected in the adapter docstring, `preferences.py`,
   `BACKENDS.md` and the test, and no general claim about their relative quality
   now appears anywhere.
5. **I wrote a test asserting trafilatura declines a page of nothing but
   links.** It does not — it extracts the link text. The claim came from
   reasoning about extractors rather than running one. The real failure modes,
   found by running it: below `MIN_EXTRACTED_SIZE` (250 characters) a baseline
   extractor runs instead, so a short page loses its Markdown structure *and*
   keeps its navigation; and a heading outside the detected content region is
   dropped rather than demoted. Both now asserted, with the contrast case.
6. **`visible_text` counted `<title>`.** A page's tab name is not text on the
   page, and including it put a string in the boilerplate denominator that
   appears nowhere in the document. `<head>` is excluded now;
   `boilerplate.html`'s visible text went 4,975 → 4,902 characters.
7. **`visible_text` fused words across element boundaries.**
   `<nav>Home</nav><p>Article</p>` counted as `HomeArticle` — one character
   short, and a word that is not on the page.
8. **A commit whose message did not match its contents.** `6120078` described
   moving the shared helpers *and* repointing the five call sites; only the move
   was staged. The result worked, because the compatibility shim re-exports
   everything, but the message claimed changes that were not in it. Corrected by
   a follow-up commit (`d0c9355`) rather than an amend, because `6120078` was
   already pushed and rewriting history hides the mistake instead of fixing it.
   This is exactly what "stage deliberately" is for and I did not do it.

### 2026-08-22 — Handover prompt for Phases 5, 6 and the fidelity slice

`docs/prompts/PHASE_5_6_AND_FIDELITY.md` is the assignment for the next session:
one branch, three pieces of work, in a deliberately non-plan order.

**The reordering, and the reason.** A slice of Phase 10 — fidelity scoring —
comes *before* Phase 5. Phase 5's post-processors strip images, links, duplicate
blocks and front matter, and reformat tables into other serialisations; every one
of them can be measured as a win in tokens and a loss in fidelity, and this
project has no fidelity metric at all. Building Phase 5 first means its defaults
get argued rather than measured, and produces exactly the number
`benchmarks/README.md` calls meaningless. The last session hit this for real: a
−90.7% reduction achieved by losing all the content, caught by a human reading a
table rather than by a metric. Build the instrument, then the things it measures.

The slice is deliberately narrow — score one output against ground truth,
component scores never a single opaque number, `None` where ground truth is
absent. Phase 10 proper still owns the corpus × backends × formats matrix, wall
time, peak memory and the committed result files.

**Environment facts measured while writing it, so they are not rediscovered:**

| Thing | Result |
|---|---|
| `pypi.org` | 200 |
| `huggingface.co` | **denied** — so LLMLingua-2's model cannot be fetched here |
| `openaipublic.blob.core.windows.net` | **denied** — still no real token counts locally |
| `download.pytorch.org` | **denied** — the CPU-only wheel index is unreachable, so even the CUDA-avoidance workaround cannot be tested |
| `pip install llmlingua` | **63 packages, 4,731 MB**, including the full CUDA stack |
| `pip install chonkie` | 13 packages, 72 MB; MIT / `MIT OR Apache-2.0`; pulls numpy and httpx |
| TOON on PyPI | both `toon` and `toon-format` resolve; which is which needs checking |

**The consequence, stated plainly in the prompt:** Phase 6's acceptance criterion
"achieves a measurable ratio on a long fixture context" is **not achievable in
this environment**. The prompt asks the next session to pick between implementing
it fully with the offline and error paths tested and the success path recorded as
unverified — the treatment docling's PDF path got in Phase 2 — or implementing
less and saying so, and forbids implying it was run.

Also corrected in advance: the plan calls LLMLingua-2 "CPU-feasible", which is
true of *running* it and not of installing it.

### 2026-08-22 — Full re-evaluation of Phases 0 through 4

`docs/REVIEW_PHASES_0_4.md`. Every acceptance criterion from Phase 0 onwards
marked verified / unverified / failed with the command that proves it, the whole
corpus run end to end with the output read, a by-hand clean-install check, the
cross-cutting seams, a licence audit, and a defects list.

**Score: 17 verified, 4 unverified, 0 failed.** All four unverified items have
the same cause — CI cannot schedule runners — and they are: real token counts
(Phase 1 #3), the 9-cell clean-install guard (Phase 2 #4), docling's PDF path
(Phase 2 #5), and Phase 3's reduction figure in model tokens rather than bytes.

**Two defects were found and fixed during the review rather than only listed.**

1. **A great reduction achieved by losing the content.** Converting
   `jsrendered.html` reported `1,512 -> 140 (-90.7%)` — a number that would look
   excellent in a benchmark and represents near-total content loss, which is
   exactly what `benchmarks/README.md` names as disqualifying. Nothing in the
   output said so, because from a parser's point of view nothing went wrong.
   Web backends now warn when a page carries scripts and under 15% of its bytes
   are visible text. Calibrated against the corpus rather than guessed — 76.3%
   for `article.html`, 39.3% for `boilerplate.html`, 9.2% for the genuinely
   client-rendered page — with six tests including the false-positive side.
2. **A clean install gave a Node error for a Python tool.** On core-only,
   `tokenmill repo ./project` fell through to repomix (which reports itself
   available because `npx` exists) and failed with npx instructions, never
   mentioning `pip install "tokenmill[repo]"`. Found by doing the clean-install
   check by hand instead of trusting the CI job that has not run.

**The clean install, measured by hand:** `pip install .` takes **11.7 s**, brings
41 packages and 164 MB, and `import tokenmill` still pulls in **zero**
third-party modules. Each extra installs cleanly and enables its backends.

**Seams checked, all sound.** The fallback chain ranks every web backend above
every document backend; an installed `documents` extra cannot change which
backend converts a page (asserted, not assumed); the error taxonomy **did not
grow** under two phases of pressure; the per-stage report still balances across
two new source shapes; `--json` is byte-identically shaped between `convert` and
`repo`.

**One seam has moved, and it is the trajectory rather than the state.**
Phase 2 recorded one use of `warnings.catch_warnings` as a Phase 8 concern.
There are now **five** distinct pieces of process-global state manipulated during
a conversion — three warning filters, `os.environ`, the stdlib root logger's
handlers *and level*, and loguru's activation registry. All correctly restored,
all scoped to one call, none thread-safe. Still a Phase 8 problem; five times
larger than when it was filed, and the Phase 8 batch runner cannot simply put
`Pipeline.run` on a thread pool.

**Recommendation: start Phase 5.** Nothing must be repaired first — the one
defect too close to the project's core promise to leave open was fixed during the
review. One thing must be *decided*: whether CI can be restored, because Phase 5
adds format encoders whose correctness is exactly what a 9-cell matrix catches
and a single Linux box does not.

The advice recorded with it: Phase 5's real risk is that every post-processor in
it can be measured as a win in tokens and a loss in fidelity, and this project
has **no fidelity metric** — only pass/fail assertions. Bringing a small piece of
Phase 10 forward would make "this saved 20% and lost the table" expressible as a
number, and without it Phase 5's defaults will be argued rather than measured.

### 2026-08-22 — CI still cannot schedule runners, nine hours on

Re-checked at the end of this session, as instructed. **Unchanged and worse than
when the handover recorded it.** Six runs on `claude/phase-3-4-web-and-repo`
(runs 37, 39, 41, 43, 45, 47) all failed, and run 47 on `145c2c9` at 20:26 UTC
has the identical signature: 24 job records created with correct expanded matrix
names, all 23 real jobs failing 2–6 seconds after starting, across
`ubuntu-latest`, `macos-latest` and `windows-latest` alike, and the
`Docling (weekly and on demand)` job correctly evaluating its `if:` to `skipped`.

That last detail is the proof it is not the workflow file: expressions evaluated,
matrices expanded, jobs were created. Runs 25 through 47 — **23 consecutive runs
over more than nine hours** — have failed this way. Run 24 on `Main` at 08:50 UTC
was the last green one.

Everything in Phases 3 and 4 is therefore **local green only**. Nothing is proven
on Windows, on macOS, on Python 3.12 or 3.13, or against a real tokenizer
vocabulary. Recorded as such throughout; see the review's §2.

### 2026-08-24 — Start-of-session probes: CI, blocked hosts, dependency weights

Run before any code was written, because three of the four answers change what
the work should be.

**CI is still dead, and it is the same failure.** Run 65 fired today on `Main`:

```
run 65  CI  completed  failure  Main  619a25c0  push  2026-08-24T06:14:33Z
  24 jobs created, correct expanded matrix names
  "Docling (weekly and on demand)"  ->  skipped   (its `if:` evaluated correctly)
  every other job: conclusion=failure, runner_id=0, runner_name="", no steps
  e.g. "Clean core install (py3.12 / ubuntu-latest)"
       created_at 06:14:33  started_at 06:14:33  completed_at 06:15:36
       runner_id: 0, runner_name: ""
```

That is the signature `docs/REVIEW_PHASES_0_4.md` recorded for runs 25-28,
unchanged, now spanning **runs 25 through 65 and more than two days**. The
workflow parses, the matrix expands, expressions evaluate; no runner is ever
assigned. Still consistent with exhausted Actions minutes or a spending limit,
and still only the owner can see that page. **Open question 1 stands.**

**Blocked hosts: all three still denied at the proxy.**

```
openaipublic.blob.core.windows.net   curl: (56) CONNECT tunnel failed, response 403
huggingface.co                       curl: (56) CONNECT tunnel failed, response 403
download.pytorch.org                 curl: (56) CONNECT tunnel failed, response 403
pypi.org                             200
```

So: no real BPE token count in this sandbox, no model download for Phase 6, and
no way to test whether the CPU-only PyTorch wheel index avoids the CUDA stack.

**Dependency weights, measured rather than restated from the handover.**

```
$ uv pip install --dry-run "tokenmill@." chonkie
  40 packages  ->  50 packages
  chonkie==1.7.0  chonkie-core==0.10.2  tokie==0.1.4  numpy==2.4.6  httpx==0.28.1

$ du -sm .../lib
  core            126 MB   40 packages
  core + chonkie  196 MB   50 packages
```

Chonkie costs **+10 packages and +70 MB** on top of core, mostly numpy. The
handover's standalone figure of 13 packages / 72 MB is consistent with this.

```
$ uv pip install --dry-run llmlingua
  63 packages, including:
  torch==2.13.0  triton==3.7.1  transformers==5.15.1
  nvidia-cublas  nvidia-cuda-cupti  nvidia-cuda-nvrtc  nvidia-cuda-runtime
  nvidia-cudnn-cu13  nvidia-cufft  nvidia-cufile  nvidia-curand
  nvidia-cusolver  nvidia-cusparse  nvidia-cusparselt-cu13  nvidia-nccl-cu13
  nvidia-nvjitlink  nvidia-nvshmem-cu13  nvidia-nvtx
```

**The handover's §6 trap 2 is confirmed independently**: `llmlingua` pulls the
entire CUDA stack. Not downloaded — 4.7 GB against a fixed disk allowance, and
the resolution is the fact that matters. The plan calling LLMLingua-2
"CPU-feasible" is true of *running* it and not of *installing* it.

**Baseline before any change:** `824 passed, 53 skipped`. Four fewer passes than
the 828 the review recorded, and the reason is environmental rather than a
regression: this container has no `crawl4ai`, `repomix` or `code2prompt`, so
four tests that ran there skip here.

### 2026-08-24 — Correction: I did add to the process-global-state count

Recorded here rather than by editing the commit message it corrects.

The Phase 6 commit (`b890ef8`) says the compressor *"adds nothing to the five
pieces of process-global state ARCHITECTURE.md already records"*. That is true
of the thing the sentence was about — no environment variable is set, because
`local_files_only` rides in llmlingua's `model_config` rather than
`HF_HUB_OFFLINE` — and **read plainly it overstates**.

`post/compress.py` uses `warnings.catch_warnings` to keep transformers'
import-time noise non-fatal under `-W error`. That is a **fourth** use of
`catch_warnings`, where `docs/REVIEW_PHASES_0_4.md` §4 counted three:

```
$ grep -rn 'catch_warnings\|os.environ\|loguru' src/tokenmill/ --include='*.py'
src/tokenmill/backends/_common.py                    catch_warnings
src/tokenmill/backends/documents/docling_adapter.py  catch_warnings
src/tokenmill/backends/repo/gitingest_repo.py        catch_warnings
src/tokenmill/post/compress.py                       catch_warnings   <- added
src/tokenmill/backends/repo/gitingest_repo.py        os.environ, root logger, loguru
src/tokenmill/backends/_subprocess.py                os.environ
src/tokenmill/core/config.py                         os.environ
```

The **kinds** of global state are unchanged, and the new use only executes when
compression runs — off by default, behind an extra. But the count went up, the
handover asked to be told before a sixth was added, and "I avoided the obvious
one" is not the same as "I added none". Defect D2 stays open and this is part of
its trajectory.

### 2026-08-24 — Phase 6: implemented, and what is and is not verified

**The headline, stated first so nobody has to look for it: the success path of
the compressor has never been executed, here or anywhere.** The LLMLingua-2
model lives on `huggingface.co`, denied at this environment's egress proxy
(re-probed at the start of this session, still `403`). No compression has been
performed by this code and **no ratio has ever been produced by it**. The owner
chose this option — implement fully, mark the success path unverified — over
implementing less.

**Acceptance criteria, honestly:**

| # | Criterion | Result |
|---|---|---|
| 1 | Achieves a measurable ratio on `long_context.md` and reports it accurately | ❌ **NOT VERIFIED — not verifiable here.** Needs the model. The reporting path is tested against a stub; the ratio itself has never existed |
| 2 | First-run download explicit, resumable, skippable; nothing downloads silently at import | ✅ **Verified**, in three parts: nothing downloads without `--allow-network` (tested); the refusal names the size, cache path and command (tested); loading all eight post-processors imports **zero** third-party modules (checked in a clean interpreter) |
| 3 | Fully offline once cached | ⚠️ **Partly.** The mechanism is `local_files_only`, and a test proves a cached model loads with it set and an uncached one refuses. **There is no cache here to demonstrate it against**, so the end-to-end claim is unverified |
| 4 | *(gate)* Ratio verified against direct token counts | ❌ **NOT VERIFIED.** Same cause |
| 5 | *(gate)* Offline-after-cache proven | ❌ **NOT PROVEN.** Same cause |

**Phase 6's exit gate is therefore not passed**, and the phase table says
🟨 rather than ✅. What exists is a complete implementation whose failure paths
are tested and whose success path is waiting on a host this environment cannot
reach.

**What *was* verified, and how.**

Licence, from the wheel's own metadata rather than from `RESEARCH.md`. The
package was deliberately not installed — see the install cost below — so the
artefact's own `METADATA` and bundled `LICENSE` are the source:

```
$ python -m pip download --no-deps llmlingua -d .
llmlingua-0.2.2-py3-none-any.whl   (30 KB)

Name: llmlingua
Version: 0.2.2
License: MIT License
Home-page: https://github.com/microsoft/LLMLingua
Requires-Dist: transformers >=4.26.0, accelerate, torch, tiktoken, nltk, numpy

llmlingua-0.2.2.dist-info/LICENSE:
    MIT License
    Copyright (c) Microsoft Corporation.
```

The install cost, confirming the handover's §6 trap 2 independently:

```
$ uv pip install --dry-run llmlingua
Resolved 63 packages, including:
  torch==2.13.0  triton==3.7.1  transformers==5.15.1
  nvidia-cublas  nvidia-cuda-cupti  nvidia-cuda-nvrtc  nvidia-cuda-runtime
  nvidia-cudnn-cu13  nvidia-cufft  nvidia-cufile  nvidia-curand
  nvidia-cusolver  nvidia-cusparse  nvidia-cusparselt-cu13  nvidia-nccl-cu13
  nvidia-nvjitlink  nvidia-nvshmem-cu13  nvidia-nvtx
```

**The CPU-only install is documented and unverified.**
`download.pytorch.org` is denied here too, so whether
`--index-url https://download.pytorch.org/whl/cpu` avoids the CUDA stack could
not be tested. It is recorded in `docs/BACKENDS.md` as the recommendation, marked
unverified.

The refusal path, run:

```
$ tokenmill convert tests/fixtures/long_context.md --compress-ratio 0.5 --tokenizer bytes
error: prompt compression needs LLMLingua, which is not installed
hint:  install it with `pip install "tokenmill[compress]"` — note that it
       resolves to 63 packages including PyTorch and the CUDA stack; see
       docs/BACKENDS.md for the CPU-only install
```

The import-time guarantee, in a clean interpreter:

```
$ python -c "import tokenmill; from tokenmill.post.base import default_post_registry; \
             default_post_registry().ids(); ..."
post-processors loaded: ('strip_frontmatter', 'normalize_whitespace',
  'aggressive_whitespace', 'links', 'dedupe_blocks', 'normalize_headings',
  'chunk', 'compress')
heavy modules imported as a side effect: NONE
third-party modules after loading every post-processor: []
```

**Three design decisions worth the owner's eye.**

**No sixth piece of process-global state.** The obvious way to force
`transformers` to load from cache only is `HF_HUB_OFFLINE=1`. That would have
been a sixth global — on top of the five `docs/ARCHITECTURE.md` records, whose
*trajectory* is defect D2 — for the duration of a conversion. llmlingua passes
`model_config` straight through to `from_pretrained`, so `local_files_only`
rides in the call instead. A test asserts `os.environ` is unchanged across a
compression. **The handover asked to be told before a sixth was added; none
was.**

**`trust_remote_code` is off, against llmlingua's default of on.** Reading its
source out of the wheel showed `trust_remote_code = model_config.get(...,
True)` — so by default a model repository can execute arbitrary code when the
model loads. LLMLingua-2's own models are token classifiers that need nothing of
the kind.

**No bespoke ratio number.** The handover asked for the retention indicator to
be the fidelity score rather than something new. It also turns out the
*achieved ratio* needs nothing new either: the pipeline already measures the
`compress` stage, so `--show-stages` reports it. Two numbers that already exist,
zero invented.

**A gap this exposed.** `PostProcessor.process(text, options) -> str` is the
whole contract — a post-processor has **no channel for warnings or metadata**,
unlike a backend with its `ConversionContext`. So the compressor logs instead of
warning, and cannot attach its own ratio to the result. Phase 8's GUI will want
this. Recorded under Deferred work.

**Selective Context: deferred, with the reason measured.**

```
$ uv pip install --dry-run "tokenmill@." selective-context
Resolved 106 packages in 501ms
 + selective-context==0.1.3      <- not 0.1.4
 + click==8.4.2
 + spacy==3.8.15
```

Its current release (0.1.4) pins `click==8.0.4`, which conflicts with the CLI's
click, so the resolver silently backs down to **0.1.3**. It also brings spacy and
needs its own model download, and its happy path is exactly as unrunnable here as
LLMLingua-2's. The plan lists it as optional; adding it would have doubled the
unverified surface for no verifiable gain.

**`compress` and `docling` resolve together — which closes nothing.**

```
$ uv pip install --dry-run llmlingua docling
Resolved 126 packages, transformers==5.15.1, torch==2.13.0
```

`DEVELOPMENT_PLAN.md` and `RESEARCH.md` both flag a transformers conflict between
them. Today's resolver finds a solution. **Neither was installed and they were
never run together**, so this records only that the resolver no longer refuses.
They stay separate extras regardless: 4.7 GB and 5.2 GB in one install is not
something to do by accident.

**Toolchain, all green:**

```
$ uv run ruff check .                     All checks passed!
$ uv run ruff format --check .            123 files already formatted
$ uv run mypy                             Success: no issues found in 103 source files
$ uv run pytest -q                        1073 passed, 53 skipped
$ uv run python scripts/make_fixtures.py --check
                                          OK: 24 files reproduced byte-for-byte
```

### 2026-08-24 — Phase 5 exit gate

**Acceptance criteria, one by one.**

| # | Criterion | Result |
|---|---|---|
| 1 | Per-stage report arithmetically consistent, matching direct counts on each intermediate | ✅ **Observed.** Every stage's `tokens` equals a direct count of that stage's text; the web decomposition below adds two intermediate rows and the arithmetic still closes |
| 2 | TOON/CSV encoders round-trip tabular data losslessly, property-based | ✅ **Observed.** `hypothesis`, 200 examples per format over cells including embedded delimiters, quotes, backslashes, `05`, `1e-6`, `true`, empty strings, control characters and emoji. **It found seven real bugs** — see below |
| 3 | Every destructive post-processor declares it and is absent from the default chain, asserted for the whole registry | ✅ **Observed.** `TestTheDestructiveContract`; the default chain is still exactly `normalize_whitespace` with six processors registered |
| 4 | Docs honest: structure-preserving beats maximal stripping, format savings carry trade-offs, cited, conservative defaults | ✅ `docs/BENCHMARKS.md` "Serialisation formats" and "Post-processing", with `RESEARCH.md` Category 7 sources and the three reasons our numbers are not confirmation of theirs |
| 5 | *(gate)* `compare` correct against manual counts | ✅ **Verified by hand** — see below |
| 6 | *(gate)* Round-trip property tests pass | ✅ 53 tests in `test_formats.py` |
| 7 | *(gate)* Every new post-processor scored by the fidelity metric and published | ✅ `docs/BENCHMARKS.md`, table of seven processors with bytes and fidelity |

**`compare` verified against `wc -c`.** Every number the command printed equals
the byte length of the file it wrote:

```
$ tokenmill compare tests/fixtures/tables.pdf --tokenizer bytes \
      --formats markdown,csv,toon,json,keyvalue --write ./variants

backend     tokens  vs best  time    fidelity
pdfplumber  599     +29%     102 ms  0.667
kreuzberg   466     base     31 ms   0.500
markitdown  769     +65%     844 ms  0.606
pypdf       481     +3%      60 ms   0.333

format    tokens  vs best  size
markdown  332     +54%     332 characters
csv       216     base     216 characters
toon      240     +11%     240 characters
json      543     +151%    543 characters
keyvalue  456     +111%    456 characters

$ for f in variants/*; do printf '%-18s %6d\n' "$(basename $f)" "$(wc -c < $f)"; done
kreuzberg.md          466
markitdown.md         769
pdfplumber.md         599
pypdf.md              481
table.csv             216
table.json            543
table.keyvalue        456
table.markdown        332
table.toon            240
```

Nine for nine. `test_the_written_variants_match_the_reported_counts` asserts it
so it stays true.

**The result the command exists to produce:**

```
cheapest:      kreuzberg (466)
most faithful: pdfplumber (0.667)
The cheapest option is NOT the most faithful one. A token saving without a
fidelity number is not a result.
```

Kreuzberg is 22% cheaper than pdfplumber on `tables.pdf` **because it destroys
the table**. Sorted by tokens, this table recommends the wrong backend; that is
why rows stay in preference order and why the verdict line exists.

**Sandbox verification from `DEVELOPMENT_PLAN.md` §Phase 5**, translated from
`tokenfold` to `tokenmill`:

```
$ tokenmill convert tests/fixtures/tables.pdf --format toon --show-stages
Usage: tokenmill convert [OPTIONS] TARGET
Error: Invalid value for '--format' / '-f': 'toon' is not one of 'markdown', 'text'.
```

**This one is a deliberate deviation from the plan and needs the owner's eye.**
The plan's snippet assumes TOON is a whole-document output format. It is not,
and cannot honestly be: TOON encodes the JSON data model, and a prose document
is not that. The encoders re-serialise a **table**, which is the only shape
`RESEARCH.md` Category 7's evidence is about. `OutputFormat` therefore still has
two members and the equivalent command is:

```
$ tokenmill compare tests/fixtures/data.xlsx --formats markdown,csv,toon,json \
      --backends markitdown --tokenizer bytes

comparing 4 serialisation(s) of a 6x5 table from data.xlsx via markitdown
counts in bytes

format    tokens  vs best  size
--------  ------  -------  --------------
markdown  332     +54%     332 characters
csv       216     base     216 characters
toon      240     +11%     240 characters
json      543     +151%    543 characters

cheapest: csv (216)
```

```
$ tokenmill compare tests/fixtures/report.docx --backends markitdown,docling,kreuzberg --tokenizer bytes

backend     tokens  vs best  time     fidelity  components
----------  ------  -------  -------  --------  --------------------------------
markitdown  3,494   +1%      1040 ms  0.841     4 scored
docling     failed  -        -        -         missing dependency: docling…
kreuzberg   3,472   base     20 ms    0.614     4 scored

cheapest:      kreuzberg (3,472)
most faithful: markitdown (0.841)
The cheapest option is NOT the most faithful one.
```

```
$ pytest -q tests/unit/test_formats.py tests/unit/test_post.py \
      tests/unit/test_post_phase5.py tests/unit/test_chunk.py tests/unit/test_compare.py
173 passed in 6.99s
```

**Defect D8 closed.** A backend can now hand an intermediate text to the
pipeline, which measures it. A web conversion decomposes:

```
stage                 chars   tokens  change
--------------------  ------  ------  ------
source                12,472  12,481  -
visible_text          4,902   4,911   -60.7%
convert               2,859   2,859   -41.8%
normalize_whitespace  2,854   2,854   -0.2%
```

and a truncated repository pack shows what the budget removed:

```
stage                 chars  tokens  change
packed                2,881  2,963   -
convert               924    1,006   -66.0%
normalize_whitespace  917    999     -0.7%
```

This does not breach "backends do not measure": the backend hands over text and
the pipeline does every count. A backend stage also cannot become
`tokens_before` — that stays the source stage or nothing — and a test asserts it.

**Defect D9 closed.** `convert --json` now carries `counts` and
`is_model_tokenizer`, so a consumer reading `"tokenizer": "bytes"` has a
machine-readable signal that these are not model tokens. The `web` object is
**absent** rather than `null` for a non-web conversion, under a written rule:
`null` means "applies here, no value", an absent key means "does not apply".
This changes `convert --json`'s shape for a document, and the test that asserted
the old behaviour was updated rather than deleted.

**hypothesis, used for the first time since Phase 0 declared it, found seven
real bugs** — all in code that passed every example test I had written:

1. `str.splitlines()` also breaks on U+0085, U+2028, U+2029, `\x0b` and `\x0c`,
   so a cell containing any of them was torn across rows. Every decoder now
   splits on LF only.
2. `str.strip()` treats U+0085 as whitespace, so a TOON cell consisting of one
   vanished when the decoder trimmed its line. TOON now quotes anything Python
   considers edge-whitespace, which is more than §7.2 requires and less than
   losing a cell.
3. A quoted key containing a colon — a column literally named `:` — broke
   key-value's line partitioning, producing a key of `"`.
4. Key-value could not tell a table with no rows from one row of empty cells;
   both decoded through the same path.
5. Markdown's decoder stripped cells, so a cell of `" "` came back as `""`.
   Documented as one of GFM's two inherent losses rather than fixed.
6. Markdown cannot carry a line break in a cell — the other inherent loss.
7. JSON's array-of-objects shape cannot carry the columns of an empty table.

The last three are format-inherent and are documented on the encoders; the first
four were fixed.

**Two bugs came from reading output rather than from tests**, which is the
pattern `docs/REVIEW_PHASES_0_4.md` §9 predicted:

- `normalize_headings` read `draft: false` as a setext heading, because a YAML
  block's closing `---` is indistinguishable from a setext underline. Front
  matter is now passed through untouched.
- Closing up skipped levels by remapping the distinct levels used is wrong. On a
  document going `##`, `####`, `###` it emits `#`, `###`, `##` — still a skip.
  It now walks the ancestor chain and emits `#`, `##`, `##`.

**Toolchain, all green:**

```
$ uv run ruff check .                     All checks passed!
$ uv run ruff format --check .            123 files already formatted
$ uv run mypy                             Success: no issues found in 101 source files
$ uv run pytest -q                        1047 passed, 53 skipped
$ uv run python scripts/make_fixtures.py --check
                                          OK: 24 files reproduced byte-for-byte
```

1,047 up from the 898 at the end of the fidelity slice: **149 new tests**,
nothing broken.

### 2026-08-24 — Phase 10 fidelity slice: exit gate

**What it is.** `src/tokenmill/fidelity/` — a scorer that takes converted text
and a fixture's ground truth and returns six named components plus an
unweighted overall that names what composed it. Not the Phase 10 harness: no
corpus matrix runner, no wall time, no peak memory, no committed result files.

**Acceptance criteria, one by one.**

| # | Criterion | Result |
|---|---|---|
| 1 | markdownify on `boilerplate.html`: high content and heading recall, near-zero boilerplate rejection | ✅ **Measured.** content 1.000, headings 1.000, boilerplate rejection **0.000** |
| 2 | trafilatura on the same: high recall, boilerplate rejection 1.0 | ✅ **Measured.** content 1.000, headings 1.000, rejection **1.000** |
| 3 | kreuzberg's table integrity on `tables.pdf` well below pdfplumber's | ✅ **Measured.** **0.000 vs 1.000** |
| 4 | An empty string scores near zero on everything | ✅ **Measured**, and it needed an explicit rule — see Decisions |
| 5 | A component with no ground truth returns `None`; the overall says what it is made of | ✅ Both, at the API, the CLI and in `--json` |
| 6 | *(gate)* A backend × fixture table in `docs/BENCHMARKS.md` beside the token figures | ✅ Written, 38 rows |

**The result the slice exists for.** Run over the whole corpus:

```
fixture             backend             bytes    change   fidelity
jsrendered.html     trafilatura         140      -90.7%   0.000
jsrendered.html     markitdown          140      -90.7%   0.000
jsrendered.html     markdownify_html    165      -89.1%   0.000
jsrendered.html     readability         167      -89.0%   0.000
jsrendered.html     kreuzberg           180      -88.1%   0.000
boilerplate.html    trafilatura         2854     -77.1%   1.000
boilerplate.html    readability         2864     -77.1%   1.000
boilerplate.html    kreuzberg           6120     -51.0%   0.750
boilerplate.html    markitdown          6713     -46.2%   0.750
boilerplate.html    markdownify_html    6802     -45.5%   0.750
```

**The largest reduction in the corpus is now paired with the worst fidelity in
the corpus.** Defect D1 added a warning for this last phase; a warning is not a
number, and `docs/BENCHMARKS.md` is made of numbers.

**The full matrix**, every installed backend against every fixture it claims,
`--tokenizer bytes`, output read:

```
article.html       trafilatura        2854     -19.8%   1.000
article.html       readability        2864     -19.6%   1.000
article.html       markdownify_html   2916     -18.1%   1.000
article.html       markitdown         2864     -19.6%   1.000
article.html       kreuzberg          3063     -14.0%   1.000
corrupt.pdf        pdfplumber         FAIL              could not be parsed: Pdfmine...
corrupt.pdf        kreuzberg          FAIL              could not be parsed: Parsing...
corrupt.pdf        markitdown         FAIL              could not be parsed: FileCon...
corrupt.pdf        pypdf              FAIL              could not be parsed: PdfStre...
data.xlsx          markitdown         675               0.667
data.xlsx          kreuzberg          664               1.000
deck.pptx          markitdown         753               1.000
deck.pptx          kreuzberg          398               1.000
long_context.md    plaintext          79255    +0.0%    n/a
report.docx        markitdown         3494              0.841
report.docx        kreuzberg          3472              0.614
sample_repo        gitingest          2944              1.000
sample_repo        repomix            FAIL              repomix is not installed...
scanned.pdf        pdfplumber         0                 0.000
scanned.pdf        kreuzberg          0                 0.000
scanned.pdf        markitdown         0                 0.000
scanned.pdf        pypdf              0                 0.000
simple.pdf         pdfplumber         2370              0.500
simple.pdf         kreuzberg          2371              0.900
simple.pdf         markitdown         2377              0.500
simple.pdf         pypdf              2371              0.500
tables.pdf         pdfplumber         599               0.667
tables.pdf         kreuzberg          466               0.500
tables.pdf         markitdown         769               0.606
tables.pdf         pypdf              481               0.333
twocolumn.pdf      pdfplumber         4050              0.528
twocolumn.pdf      kreuzberg          4061              0.667
twocolumn.pdf      markitdown         4062              0.528
twocolumn.pdf      pypdf              4050              0.667
unicode.docx       markitdown         1312              0.955
unicode.docx       kreuzberg          1314              1.000
```

**Eight claims in `docs/BACKENDS.md` are now numbers rather than sentences.**
Kreuzberg flattening `tables.pdf` reads 0.00 against pdfplumber's 1.00;
pdfplumber interleaving two-column pages reads 0.58 against pypdf's 1.00;
kreuzberg inferring PDF headings reads 0.80 on `simple.pdf` where every other
backend reads 0.00; kreuzberg dropping DOCX lists reads structure retention
0.00 against markitdown's 1.00.

**Two things the score found that were not in `BACKENDS.md`:**

- MarkItDown emits `report.docx`'s table with an **invented blank header row**
  and the real header demoted to a body row:

  ```
  |  |  |  |
  | --- | --- | --- |
  | Stage | Tokens | Delta |
  | source | 16180 | - |
  ```

  Found because the first version of the scorer counted 15 cells where ground
  truth expects 12 and capped the score at 1.0. Blank cells are now excluded
  from recovery, so it reads 12 of 12 real cells — the defect is in the shape,
  not in the data.
- **MarkItDown recovers 2 of 3 required passages from `data.xlsx`** (content
  recall 0.667) where kreuzberg recovers all three.

**The CLI, run end to end:**

```
$ tokenmill convert tests/fixtures/boilerplate.html --backend trafilatura -q |
      tokenmill fidelity - --against boilerplate.html --backend trafilatura

fidelity: boilerplate.html via trafilatura

component              score  count  detail
---------------------  -----  -----  -------------------------------------------
heading_recall         1.000  6/6    6 of 6 headings recovered as headings
content_recall         1.000  3/3    3 of 3 required passages present
table_integrity        1.000  35/35  35 of 35 expected cells came back inside 1
                                     parsed table(s); ground truth records no
                                     cell values, so this is a shape check
structure_retention    n/a    -      this fixture's ground truth names no list
                                     items, links or code fences
boilerplate_rejection  1.000  6/6    6 of 6 markers that must be absent are absent
reading_order          n/a    -      this fixture's ground truth carries no
                                     order sentinels

overall: 1.000 (unweighted mean of heading_recall, content_recall,
                table_integrity, boilerplate_rejection)
```

```
$ echo hi | tokenmill fidelity - --against nope.pdf
error: no ground truth for 'nope.pdf'
hint:  known fixtures: article.html, boilerplate.html, corrupt.pdf, data.xlsx,
       deck.pptx, jsrendered.html, long_context.md, report.docx, sample_repo/,
       scanned.pdf, simple.pdf, tables.pdf, twocolumn.pdf, unicode.docx
exit=1
```

**Corpus changes.** Two fixtures gained scorable ground truth, added to
`scripts/make_fixtures.py` and regenerated — never hand-edited. **No fixture
bytes changed**; only `ground_truth.json` differs:

```
$ uv run python scripts/make_fixtures.py && git status --short tests/fixtures/
 M tests/fixtures/ground_truth.json

$ uv run python scripts/make_fixtures.py --check
OK: 23 files reproduced byte-for-byte
```

(`generate` prints `Done: 24 files` because it counts the deliberately
uncommitted `secrets.env`; `--check` compares the 23 committed ones. Both
pre-existing, and the code says so.)

**Toolchain, all green:**

```
$ uv run ruff check .                          All checks passed!
$ uv run ruff format --check .                 102 files already formatted
$ uv run mypy                                  Success: no issues found in 83 source files
$ uv run pytest -q                             898 passed, 53 skipped in 43.75s
$ uv run pytest --cov (core+tokens)            95%   (gate: 85%)
$ uv run python scripts/make_fixtures.py --check
                                               OK: 23 files reproduced byte-for-byte
```

898 up from the 824 baseline: **74 new tests**, nothing broken.

### 2026-08-22 — Phase 4 exit gate

From a venv synced with `--extra dev --extra fixtures --extra documents --extra
web --extra repo`, with `code2prompt` built from crates.io and `repomix` reached
through `npx`.

- Command: `uv run ruff check .`
- Result: `All checks passed!`

- Command: `uv run ruff format --check .`
- Result: `93 files already formatted`

- Command: `uv run mypy`
- Result: `Success: no issues found in 76 source files`

- Command: `uv run pytest -q --cov=tokenmill`
- Result: `820 passed, 49 skipped in 41.33s`, `TOTAL 2744 stmts, 89%`

- Command: `uv run pytest -q --cov=tokenmill.core --cov=tokenmill.tokens --cov-fail-under=85`
- Result: `Required test coverage of 85% reached. Total coverage: 95.13%`

- Command: `uv run python scripts/make_fixtures.py --check`
- Result: `OK: 23 files reproduced byte-for-byte`

- Command: `uv run tokenmill backends --all`
- Result: thirteen backends, all four domains populated:
  ```
  id                domains    license       tier        isolation   availability
  ----------------  ---------  ------------  ----------  ----------  ----------------------------
  code2prompt       repo       MIT           permissive  subprocess  available
  crawl4ai          web        Apache-2.0    permissive  in-process  missing dependency: crawl4ai
  docling           documents  MIT           permissive  in-process  missing dependency: docling
  gitingest         repo       MIT           permissive  in-process  available
  kreuzberg         documents  MIT           permissive  in-process  available
  markdownify_html  web        MIT           permissive  in-process  available
  markitdown        documents  MIT           permissive  in-process  available
  pdfplumber        documents  MIT           permissive  in-process  available
  plaintext         text       Apache-2.0    permissive  in-process  available
  pypdf             documents  BSD-3-Clause  permissive  in-process  available
  readability       web        Apache-2.0    permissive  in-process  available
  repomix           repo       MIT           permissive  subprocess  available
  trafilatura       web        Apache-2.0    permissive  in-process  available
  ```

**The plan's sandbox-verification commands for this phase**, translated from
`tokenfold` to `tokenmill`:

- Command: `uv run tokenmill repo tests/fixtures/sample_repo --backend gitingest --token-budget 5000 --tokenizer bytes`
- Result: `tokens: 2,944 (bytes)`, nothing dropped — the whole pack fits inside
  5,000.

- Command: `uv run tokenmill repo tests/fixtures/sample_repo --backend repomix`
- Result: **exit 1**, degrading exactly as the criterion asks:
  ```
  error: repomix is not installed, and running it through npx would download it
  hint:  install Node.js, then either 'npm install -g repomix' (recommended: no
  download per run) or pass --allow-network to let npx fetch it each time
  ```

- Command: the same with `--allow-network`
- Result: **exit 0**, `backend: repomix`, `tokens: 3,978 (bytes)`, 8 files.

- Command: `uv run tokenmill repo tests/fixtures/sample_repo --tree-tokens --tokenizer bytes`
- Result:
  ```
  | directory     | bytes | share | files |
  | ---           | ---   | ---   | ---   |
  | src           | 1,425 | 54.6% | 3     |
  | src/widgetlib | 1,425 | 54.6% | 3     |
  | .             | 528   | 20.2% | 2     |
  | tests         | 348   | 13.3% | 1     |
  | docs          | 310   | 11.9% | 1     |
  ```

- Command: `uv run pytest -q tests/integration/test_repo_backends.py`
- Result: `36 passed in 13.27s`

**The three engines, measured on the same repository:**

| Backend | Files | Output bytes | Wall time | Secret leaked |
|---|---|---|---|---|
| `gitingest` | 7 | 2,862 | 564 ms | no |
| `repomix` | 8 | 3,978 | 1,082 ms | no |
| `code2prompt` | 7 | 2,246 | 103 ms | no |

**Acceptance criteria, one by one:**

| # | Criterion | Result |
|---|---|---|
| 1 | The fixture repo produces a single file with a directory tree and file contents | ✅ **Observed and read.** Tree with all seven packed files, then each file's contents under its header. The `.gitignore`d `secrets.env` and the binary `assets/logo.bin` are both correctly absent. |
| 2 | The token budget genuinely caps output, and what got dropped is reported | ✅ **Observed by measuring the file.** A 1,200-byte cap produced a **999-byte** document; the five dropped files are named in a warning, in `dropped_files` metadata, and in the document itself. |
| 3 | Missing `npx`/`repomix` yields a clear message, not a traceback | ✅ **Observed**, quoted above. Also for `code2prompt`, with the `cargo install` command. Both are tested with `PATH` lookups stubbed, so the absent case is covered on a machine where the tools *are* installed. |
| 4 | *(exit gate)* All three adapters behave correctly whether or not their runtime is installed | ✅ **Observed both ways**, which this sandbox could do because all three runtimes turned out to be installable here. |
| 5 | *(exit gate)* Budget truncation verified by inspecting the output | ✅ The truncated pack was read, not inferred: five files gone, tree intact, truncation note listing each dropped file with its cost. |

**Verified beyond the criteria:**

- **A real remote clone.** `example.com` and `github.com` are blocked, so a
  `git daemon` was run on `127.0.0.1:9418` serving the fixture repository.
  `tokenmill repo git://127.0.0.1:9418/demo` cloned it, packed it, and left no
  `tokenmill-repo-*` directory behind. The live-internet path is still
  unverified — the loopback one exercises every line of the same code.
- **`--no-gitignore` really does let the secret through.** Asserted deliberately.
  A `.gitignore` toggle that silently did nothing would pass every "the secret
  did not leak" test above while providing no protection at all.
- **A shell metacharacter in an argument stays data.** A test passes
  `; touch <path>; echo ` as an argument and asserts the file is not created.

**Bugs found and fixed during verification**, every one by running something:

1. **The budget did not include its own truncation note.** A 1,200-byte cap
   emitted 1,482 bytes — a cap exceeded by the explanation of the cap. Fixed,
   then fixed again: the second version dropped files to make room and, since
   each drop adds a row to the note, emptied the pack chasing a note that grew
   faster than the content shrank. The rule that works is **the note degrades
   before the content does**.
2. **The budget's file-eviction loop confused two indices.** `limit` indexed
   into the section list while `len(kept)` counted files that fit, so dropping
   "the last kept file" sometimes evicted a different one. Caught by a test with
   a small file *after* a huge one.
3. **gitingest validates `$GITHUB_TOKEN`'s format before reading the source.**
   A placeholder token — which this sandbox exports, and which CI systems export
   routinely — failed a purely local pack with `InvalidGitHubTokenError`.
4. **gitingest reconfigures the host process's logging.** Importing it installs
   a loguru `InterceptHandler` on the stdlib **root** logger and sets that
   logger's level to `0`. Measured: `[] level 30` before, `['InterceptHandler']
   level 0` after. Every record tokenmill logs — and every record an application
   embedding tokenmill logs — was being rerouted, and previously-suppressed INFO
   started appearing. Snapshotted and restored now.
5. **gitingest logs its own progress at INFO**, eight lines per pack.
6. **pathspec's deprecated `gitwildmatch` factory is fatal under `-W error`.**
   The same shape as Phase 2's onnxruntime failure, and it passed at the CLI
   while failing in the suite, because the CLI does not set `-W error`.
7. **code2prompt's section format was guessed wrong.** I assumed repomix's
   `## File:`; it uses a backtick-quoted path and a colon. The adapter's "format
   not recognised" warning surfaced it rather than a silent file count of zero,
   which is the behaviour that warning exists for.
8. **A Phase 1 CLI test asserted the `repo` domain was empty.** True until this
   phase. Repointed to assert that `--domain` filters, plus a new test covering
   the empty-listing message against a registry with no entry points.

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

### 2026-08-26 — CI is alive, and it had two rounds of real failures to report

The owner made the repository public. That fixed the runner-scheduling failure
that had stood since run 24 on 2026-08-21: a private repository on a plan with
no included Actions minutes creates jobs, expands matrices correctly, and then
fails every one of them with `runner_id: 0` and no steps — which is what 23
consecutive runs, and then every run for five days, had been doing. It was never
our YAML. **The entry for 2026-08-22 titled "CI cannot schedule runners, and it
is not our YAML" was right about the cause and is now closed.**

The immediate consequence is that Phases 3, 4, 5, 6 and the fidelity slice got
their first real CI run, and CI had five days of accumulated truth to tell.

**Round one — run 81, 24 jobs, 24 failures.** Two causes, in opposite
directions:

- **Three failures were mine, from this session.** `tests/unit/test_post_phase5.py`
  builds the expected default chain by excluding the destructive processors, and
  its exclusion set named `dedupe` and the rest but not `chunk`. It passed on my
  machine for the worst possible reason: chonkie happened to be installed here,
  so `chunk` registered and the count came out right by accident. On a runner
  without the `chunk` extra it did not. Fixed by naming the set for what it
  actually is — `NEEDS_AN_EXTRA = frozenset({"chunk", "compress"})`.
- **Twenty-one failures were Phase 4's, and had been latent since 2026-08-22.**
  `tests/integration/test_repo_backends.py` imports gitingest at module scope
  with no `requires` marker. Locally the `repo` extra was installed, so the file
  ran; in CI the `test` job installed `--extra documents` only, so the file
  errored at collection. Phase 4's exit gate was recorded as "local green only",
  which was honest, but nobody had noticed that the CI job could not have run
  these tests even if runners had been available. Fixed in both directions: a
  `requires_gitingest` marker on the five classes, and the `test` and `coverage`
  jobs now install every extra that is CPU-only, permissive and
  wheel-installable on all three platforms — `documents web repo chunk`. Before
  today that job installed `documents` alone, so the gitingest, readability and
  chonkie tests would have silently skipped on all nine cells.

**Round two — run 82, one failure, on all nine test cells and the coverage
gate.** I pushed the round-one fix saying it would make the suite green. It did
not. That was an overclaim: I had verified both install shapes locally
(`1024 passed, 102 skipped` minimal; `1073 passed, 53 skipped` with the new CI
extras) and treated local green as proof of CI green, which is precisely the
inference this project has been burned by twice.

The remaining failure was `test_the_flags_are_documented_in_help`, which asserts
that `--offline`, `--ignore-robots`, `--allow-network` and `--user-agent` appear
in `tokenmill convert --help`.

- Command: `env GITHUB_ACTIONS=true uv run pytest -q`
- Result: `1 failed, 1072 passed, 53 skipped` — **an exact reproduction of the
  CI counts**, on this machine, from one environment variable.
- Cause: `typer/rich_utils.py` line 80 sets `FORCE_TERMINAL = True` when any of
  `GITHUB_ACTIONS`, `FORCE_COLOR` or `PY_COLORS` is set, and it reads them at
  *import* time. So help text is plain on a developer's machine and colourised
  in CI. Rich's option highlighter then emits the leading dash of a long flag as
  its own span: the rendered bytes are
  `\x1b[1;36m-\x1b[0m\x1b[1;36m-offline\x1b[0m`, in which the literal
  substring `--offline` does not occur.
- The CLI is not at fault. The help genuinely documents all four flags; the
  assertion was reading styling rather than words. Fixed by stripping ANSI SGR
  sequences before the comparison, via a `plain()` helper in the test module
  that carries this explanation. Checked that the assertion still has teeth: the
  four real flags are found in the stripped text and an invented one is not.
- Because typer reads those variables at import time, an environment fixture
  would not have worked — by the time a test runs, `FORCE_TERMINAL` is already
  bound. Stripping at the assertion is the change that actually holds.

**Verified before pushing, this time with the failing environment reproduced
first:**

- `uv run ruff check .` — all checks passed
- `uv run ruff format --check .` — 126 files already formatted
- `uv run mypy` — no issues in 103 source files
- `GITHUB_ACTIONS=true uv run pytest -q` — `1073 passed, 53 skipped`
- `uv run pytest -q` — `1073 passed, 53 skipped`
- The coverage job's exact command — `Required test coverage of 85% reached.
  Total coverage: 95.42%`

**What this does not yet establish.** Everything above is still this machine.
The claim that CI is green belongs to a green run, not to a local reproduction
of a red one, however faithful. The status table's "(local; CI cannot schedule
runners)" notes stay as they are until a run comes back green, and this entry
will be extended with that run's number rather than edited to assume it.

**Round three — run 84: 21 of 24 green, and Windows tells the truth for the
first time.** Lint, types, coverage, tokenizers, fixtures and all nine
`clean-core-install` cells passed, as did every Ubuntu and macOS test cell. All
three **Windows** test cells failed, 6 tests each — failures the help-text bug
had been masking, and which no run in this project's history could have found,
because CI has never once executed the suite on Windows. Two causes, both real
product defects rather than test artefacts:

- **`npx` could not be launched, on a runner that has npx installed.**
  `shutil.which` honours `PATHEXT` and finds `npx.cmd`, so `probe_tool` reported
  the tool available; `CreateProcess` appends only `.exe`, so
  `subprocess.run(["npx", ...], shell=False)` raised `FileNotFoundError` and the
  user saw `npx is not installed or not on PATH`. The probe and the launch were
  doing two different lookups. `run_tool` now resolves `argv[0]` with
  `shutil.which` and launches the resolved path, while leaving `argv` itself
  alone for messages and provenance — "install
  `C:\Program Files\nodejs\npx.cmd`" is not a hint anyone can act on. On POSIX
  this is a no-op. **This means the repomix backend has never worked on Windows,
  since Phase 4.** Recorded as a defect that shipped, not as a test fix.
- **`--write` produced files that did not match the numbers beside them.** All
  four write sites used text mode, so Python rewrote every `\n` as `\r\n` on
  Windows: `pdfplumber.md` was 615 bytes against a reported 599.
  `docs/BENCHMARKS.md`'s standing claim is that each number in the table is the
  byte length of the file it wrote, and on Windows that claim was false. All
  four now pass `newline=""`.

**Honest limit on the second fix.** It cannot be provoked on Linux or macOS —
text mode translates nothing there — so no test in this repository can fail on
it locally. The CI Windows cells are the only place that assertion has teeth,
which is now written into the test itself rather than left implicit. The `npx`
fix is verified on POSIX only (present tool runs and keeps its bare name in
provenance; absent tool still raises `BackendUnavailable` with the actionable
hint); its Windows behaviour is asserted by CI and nowhere else.

### 2026-08-27 — The six repairs, before Phase 9

The owner's §3 decided all of them. Each is a commit, and each was run rather
than reasoned about.

**R0 — LibreOffice: an install with no filters is not an available backend.**
Not on the owner's list; found in the first ten minutes by running the suite on
a fresh container. **Six tests failed where they should have skipped**, because
this container ships `libreoffice-core` without `libreoffice-writer`, so
`soffice` is on PATH and converts nothing. Phase 7 knew about the condition and
reported it as a *conversion* failure, leaving the availability probe saying
"available" on the grounds that a filter set has no predictable path.

It has one: LibreOffice describes each document component in its configuration
registry as `writer.xcd`, `calc.xcd` and friends. The probe now looks, and only
ever downgrades on **positive** evidence — a registry directory that was found
and contains no component. An unrecognised layout keeps the old answer.

Verified in both directions, which is the strongest form available:

```console
$ uv run tokenmill backends --all | grep libre     # before apt install
libreoffice  ...  LibreOffice at /usr/bin/soffice has no document components installed
$ apt-get install -y libreoffice-writer libreoffice-calc libreoffice-impress
$ uv run tokenmill backends --all | grep libre     # after
libreoffice  documents  MPL-2.0  permissive  subprocess  available
```

This is trap 1 from the handover firing on day one: *a well-equipped machine is
worse at catching this class of bug than a bare one.*

**R1 — the boundary layer is renamed** (N9, §3.4). `backends/isolated/` becomes
`backends/external/`. The evidence that "isolation" misled is that three
documents had each grown a paragraph explaining what the layer is *not*.
`IsolationMode` and `BackendInfo.isolation` are unchanged — their values name a
mechanism rather than a protection, and renaming a Phase 1 field would be a
breaking change with no user-visible gain. Done before Phase 9 landed six more
subclasses on top.

**R2 — `gui --server` requires a shared token** (N15, §3.1). Verified against a
running server rather than asserted:

```console
$ uv run tokenmill gui --server --port 8099 --token EXAMPLE-TOKEN-NOT-A-REAL-SECRET
tokenmill gui on http://0.0.0.0:8099/?token=EXAMPLE-TOKEN-NOT-A-REAL-SECRET
server token (--token): EXAMPLE-TOKEN-NOT-A-REAL-SECRET
note:  --server binds every network interface and requires this token on every
       request. It is not TLS, not user accounts and not an audit trail: it stops
       another machine on your network reading your documents, and nothing more.

1. no token                        status=401
2. wrong token                     status=401
3. ?token=... in the URL           HTTP/1.1 200 OK
   set-cookie: tokenmill_server_token=...; Path=/; HttpOnly; SameSite=Lax
4. Authorization: Bearer ...       status=200
5. the cookie alone                status=200
6. a static asset, no token        status=401
7. websocket handshake, no token   status=403
8. websocket handshake, cookie     status=101
```

Rows 7 and 8 are the load-bearing pair. The interface runs over a WebSocket, and
a guard that saw only HTTP would have left the channel every conversion travels
on wide open — which is why the guard is raw ASGI rather than a Starlette
middleware. The token above is a deliberate placeholder; nothing real is
recorded anywhere (trap 9).

**R3 — staged uploads are bounded** (N14, §3.6). Both age (24 h) and count
(200), because either alone leaves a hole: an age bound lets a burst fill a disk
inside the window, a count bound keeps yesterday's documents on an idle server
forever. Moving staging into `gui/api.py`, where a test can drive it without a
browser, immediately found a hole in the name sanitiser: **`Path("..").name` is
`".."`, not the empty string**, so taking the base name alone resolved to the
*parent* directory.

**R4 — a post-processor can say something** (N2, §3.3). `PostProcessContext` as
an optional third parameter; the registry reads each processor's own signature
once and calls it with two arguments or three. A post-processor written against
the Phase 1 contract is called exactly as it was.

One thing was got wrong first and mypy caught it in nine files:
`BasePostProcessor.process` was given the third parameter too. That is a
*narrowing* override for every existing two-parameter subclass — undoing the
entire point. The base keeps two; a subclass widens.

**R5 — repomix asks for JSON** (D6, §3.6). Filed as "use `--style json` or
delete the note"; it turned out to be a correctness bug. The Markdown-parsing
regex can be fooled by a repository containing a document that *quotes* the file
marker, which is what a README explaining repomix packs looks like:

```console
$ # a two-file repo whose notes.md contains the line "## File: totally/made/up.py"
repomix really packed 2 files: notes.md, real.py
our splitter found 3 sections:
   -> notes.md
   -> totally/made/up.py      <- does not exist
   -> real.py
metadata file_count = 3
```

The phantom takes bytes in the per-directory breakdown and a token budget could
have "dropped" it, cutting a real file in half. `--style json` returns an exact
`{path: content}` mapping, so finding a boundary is a dictionary lookup. The
pack is rendered from it in repomix's own shape; the fixture pack is **3,786
bytes** where markdown style gave 3,978, and the 192 bytes are entirely
repomix's own boilerplate.

**R6 — `compare --formats` compares every table** (N4, §3.6). Invisible on this
corpus because `tables.pdf` has exactly one table, which is why it survived five
phases. Run on a three-table document, and the result is why the fix was worth
having: CSV is cheapest for all three, but **TOON's overhead over it varies with
shape — +36%, +40%, +12%** — so the tables genuinely do not share one answer.

**R7 — `aggressive_whitespace` earns its place, and N5 is reversed** (§3.6). The
owner leaned towards deleting it. The measurement says keep it.

The published claim, "close to worthless on this corpus", rested on three cells.
Measured across **all fifty backend-by-fixture cells the corpus has**:

```
tables.pdf       markitdown     769 ->   628   -18.34%   fidelity 0.606 -> 0.606
article.html     kreuzberg    3,063 -> 2,957    -3.46%   fidelity 1.000 -> 1.000
article.html     pandoc       3,072 -> 2,966    -3.45%   fidelity 1.000 -> 1.000
structured.md    pandoc       1,609 -> 1,571    -2.36%   fidelity 0.977 -> 0.977
boilerplate.html kreuzberg    6,120 -> 6,014    -1.73%   fidelity 0.750 -> 0.750
cells measured: 50; cells where it saved anything: 10
```

MarkItDown pads its table columns so they line up in a text editor. That
alignment is pure presentation and on `tables.pdf` it is 18% of the bytes;
collapsing it leaves a valid Markdown table, which is why fidelity does not
move. The earlier claim was not a lie — it was three cells generalised to a
corpus, and the three were ones where every backend already emits tidy Markdown.

**R8 — defect D2, and the measurement that did not flatter it** (§3.2). Every
global-state block now runs under one process-wide reentrant lock, and the
blocks were **narrowed first** — for the document and web adapters
`warnings_as_conversion_warnings` covers an *import*, which after the first
conversion is a `sys.modules` lookup.

Two of the three concurrency tests were watched going red with the lock removed:

```
E  AssertionError: assert [KeyError('TOKENMILL_D2_PROBE'), ...] == []
E    Left contains 13 more items, first extra item: KeyError('TOKENMILL_D2_PROBE')

E  assert root.handlers == before_handlers
E    Left contains 117 more items, first extra item: <NullHandler (NOTSET)>
```

`os.environ.pop(name, None)` raising `KeyError` from inside a call given a
default so it could not raise, and **117 leaked root-logger handlers from one
run**. The warning-filter test is the weak one and says so — that race appeared
once in a sweep, at a 1e-4 switch interval, and not at 1e-5 or 1e-6. At
CPython's default 5 ms interval **none of the three reproduces**, which is
exactly why this survived five phases.

**And the parallelism measurement, which is a null result on the headline
number.** 12 files, 4 cores, median of 5 runs:

```
in-process (pdfplumber, markitdown, trafilatura)   1.13s ->  1.25s   0.91x
pymupdf4llm (a separate interpreter per file)     14.59s ->  9.50s   1.54x
pandoc + libreoffice (real external programs)     11.89s ->  3.82s   3.12x
```

And the 20-file corpus batch the Phase 8 criterion used got **slower**: 2.07 s
serial, 2.40 s at four workers, **0.86x**, N=7. The GIL explains both ends — an
in-process backend parsing a PDF holds it, a subprocess backend waits with it
released. The default stays at 4 because it costs 9% of a 1.13 s batch and saves
8 seconds of an 11.9 s one, and `workers=1` restores Phase 8 exactly.

**R9 — CI installs Pandoc, LibreOffice and the AGPL environment** (§3.5).
**CI run 108 on this branch: green.** Phase 7's three out-of-process backends
had their conversion paths exercised on exactly one machine; now they run on the
ubuntu cells of the test matrix and the coverage job. Both jobs, not one — trap
7 is that mistake made once already.

### 2026-08-27 — Phase 9 exit gate

```console
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
164 files already formatted

$ uv run mypy
Success: no issues found in 138 source files

$ uv run pytest -q --cov=tokenmill
1493 passed, 85 skipped in 152.50s (0:02:32)

$ uv run python scripts/make_fixtures.py --check
OK: 24 files reproduced byte-for-byte

$ uv run tokenmill backends --tier heavy
id            domains    license                                            tier        isolation   availability
------------  ---------  -------------------------------------------------  ----------  ----------  --------------------------------------------------
deepseek_ocr  documents  MIT (reported; unverified — see docs/LICENSES.md)  permissive  service     no address configured for the DeepSeek-OCR service
dots_ocr      documents  MIT (reported; unverified — see docs/LICENSES.md)  permissive  service     no address configured for the dots.ocr service
marker        documents  Apache-2.0                                         permissive  subprocess  missing binary: marker_single
mineru        documents  LicenseRef-MinerU-Open-Source-License              restricted  subprocess  missing binary: mineru
olmocr        documents  Apache-2.0                                         permissive  subprocess  missing binary: olmocr
surya         documents  Apache-2.0                                         permissive  subprocess  missing binary: surya_ocr

$ uv run pytest -q -m heavy   # expected: skipped without a GPU, and that is a pass
=========================== short test summary info ============================
SKIPPED [2] tests/conftest.py:66: needs the optional dependency 'docling'; install it with an extra (see pyproject.toml) to run this test
2 skipped, 1576 deselected in 1.60s
```

**`tokenmill doctor` on this sandbox, which is the acceptance criterion:**

```console
tokenmill doctor

python:    3.11.15 (/home/user/tokenmill/.venv/bin/python3)
platform:  Linux 6.18.44-fc-v22 on x86_64
gpu:       none — No GPU found. Every heavy backend will be unavailable

external tools
tool         location
-----------  --------------------
pandoc       /usr/bin/pandoc
soffice      /usr/bin/soffice
node         /opt/node22/bin/node
npx          /opt/node22/bin/npx
code2prompt  not found
nvidia-smi   not found
docker       /usr/bin/docker

backends (13 of 22 available)
id                tier        needs  status
----------------  ----------  -----  ----------------------------------------------
code2prompt       permissive  cpu    missing binary: code2prompt
crawl4ai          permissive  cpu    missing dependency: crawl4ai
deepseek_ocr      permissive  gpu    no address configured for the DeepSeek-OCR se…
docling           permissive  cpu    missing dependency: docling
dots_ocr          permissive  gpu    no address configured for the dots.ocr service
gitingest         permissive  cpu    available
kreuzberg         permissive  cpu    available
libreoffice       permissive  cpu    available
markdownify_html  permissive  cpu    available
marker            permissive  gpu    missing binary: marker_single
markitdown        permissive  cpu    available
mineru            restricted  gpu    missing binary: mineru
olmocr            permissive  gpu    missing binary: olmocr
pandoc            copyleft    cpu    available
pdfplumber        permissive  cpu    available
plaintext         permissive  cpu    available
pymupdf4llm       copyleft    cpu    available
pypdf             permissive  cpu    available
readability       permissive  cpu    available
repomix           permissive  cpu    available
surya             permissive  gpu    missing binary: surya_ocr
trafilatura       permissive  cpu    available

how to install the GPU tier

  DeepSeek-OCR (deepseek_ocr) — MIT (reported; unverified — see docs/LICENSES.md)
    weights licence: NOT VERIFIED. The code's licence above is not the weights'; read the model card before relying on it.
    start the service and pass --extra deepseek_ocr_url=http://localhost:5001 (and --allow-network, since talking to it is a network call)
    note: this machine has no usable GPU, so it will be very slow or will fail at model load
    note: nothing to install locally: run the model yourself and pass --extra deepseek_ocr_url=http://host:8000

  dots.ocr (dots_ocr) — MIT (reported; unverified — see docs/LICENSES.md)
    weights licence: NOT VERIFIED. The code's licence above is not the weights'; read the model card before relying on it.
    start the service and pass --extra dots_ocr_url=http://localhost:5001 (and --allow-network, since talking to it is a network call)
    note: this machine has no usable GPU, so it will be very slow or will fail at model load
    note: nothing to install locally: run the model yourself and pass --extra dots_ocr_url=http://host:8000

  Marker (marker) — Apache-2.0
    weights licence: NOT VERIFIED. The code's licence above is not the weights'; read the model card before relying on it.
    $ python -m venv /root/.local/share/tokenmill/marker
    $ /root/.local/share/tokenmill/marker/bin/pip install marker-pdf
    note: this machine has no usable GPU, so it will be very slow or will fail at model load

  MinerU (mineru) — LicenseRef-MinerU-Open-Source-License
    weights licence: NOT VERIFIED. The code's licence above is not the weights'; read the model card before relying on it.
    $ python -m venv /root/.local/share/tokenmill/mineru
    $ /root/.local/share/tokenmill/mineru/bin/pip install 'mineru[core]'
    note: this machine has no usable GPU, so it will be very slow or will fail at model load

  olmOCR (olmocr) — Apache-2.0
    weights licence: NOT VERIFIED. The code's licence above is not the weights'; read the model card before relying on it.
    $ python -m venv /root/.local/share/tokenmill/olmocr
    $ /root/.local/share/tokenmill/olmocr/bin/pip install olmocr[gpu]
    note: this machine has no usable GPU, so it will be very slow or will fail at model load

  Surya (surya) — Apache-2.0
    weights licence: NOT VERIFIED. The code's licence above is not the weights'; read the model card before relying on it.
    $ python -m venv /root/.local/share/tokenmill/surya
    $ /root/.local/share/tokenmill/surya/bin/pip install surya-ocr
    note: this machine has no usable GPU, so it will be very slow or will fail at model load

note: No GPU. The heavy backends will install and will be too slow to use; the light tier (pdfplumber, markitdown, kreuzberg) and the external tier (pandoc, LibreOffice, PyMuPDF4LLM) are what this machine is for.
```

**Acceptance criteria, honestly:**

| # | Criterion | Result |
|---|---|---|
| 1 | Every heavy adapter degrades cleanly to "unavailable + how to install" on a CPU-only machine | ✅ **Verified.** Six adapters, each unavailable with either two install commands or the `--extra` key that configures it. Asserted over all six in `tests/integration/test_heavy_backends.py` |
| 2 | `tokenmill doctor` output is accurate on the sandbox | ✅ **Verified**, pasted above. No GPU, 13 of 22 backends available, every external tool correctly located or reported absent |
| 3 | At least one heavy backend verified working if the sandbox has a GPU; if not, say so plainly | ❌ **NOT VERIFIED — no GPU, and no route to the weights.** Said plainly here, in `backends/heavy/__init__.py`, in `docs/BACKENDS.md` and in the README |
| 4 | *(gate)* CPU-only degradation verified | ✅ |
| 5 | *(gate)* Unverified-on-hardware items explicitly flagged | ✅ Every adapter records `weights_licence: unverified`, and a test fails if one ever claims otherwise without evidence |

**Phase 9 is amber**, for the same reason Phase 6 is: the success path needs
hardware and a host this environment does not have. That is the correct outcome
rather than a failure, and the handover said so in advance.

**What was verified beyond "it is unavailable":**

- **Argument construction and output reading**, against a real stub executable
  written to disk and made executable — not a patched `subprocess.run`. A patch
  proves the adapter called a function; a child process proves the arguments
  survived, the workspace existed when the tool looked for it, and the output
  was found where the tool put it.
- **The HTTP path end to end**, against a real local server: the OpenAI
  chat-completions shape, the image inline as a `data:` URL, `temperature: 0` so
  a measurement taken through it is reproducible, the service's own token counts
  namespaced `service_*`, the refusal without `--allow-network`, and a clear
  failure when the address points at something that is not the model.
- **`doctor`'s four ways of lying about hardware**, each against a stub
  `nvidia-smi`: software-without-a-device, a driver error, an `[N/A]` VRAM
  figure, and Apple Silicon.

**The licence surface, which is the largest in the project and where
`RESEARCH.md` was wrong twice more.** Read from each published wheel:

| Backend | Package | Verified | `RESEARCH.md` said |
|---|---|---|---|
| Marker | `marker-pdf` 2.0.0 | **Apache-2.0** (11,358 bytes of Apache text bundled) | GPL-3.0 |
| Surya | `surya-ocr` 0.22.1 | **Apache-2.0** (9,135 bytes bundled) | GPL-3.0 |
| MinerU | `mineru` 3.4.5 | **`LicenseRef-MinerU-Open-Source-License`** | AGPL-3.0 |
| olmOCR | `olmocr` 0.4.27 | Apache-2.0 | Apache-2.0 |

Marker and Surya relicensed; MinerU's AGPL entry was true of its predecessor
`magic-pdf`, which still reads `License: AGPL-3.0` on PyPI. **The fourth and
fifth licence corrections in this project**, and the first in the *safe*
direction.

**A classifier defect this found, and it is the same shape as Phase 7's.**
`classify` returned **permissive** for `BUSL-1.1`, `Elastic-2.0`, `SSPL-1.0` and
every unrecognised `LicenseRef-`. SSPL is the alarming one — aggressively
copyleft for anything offered as a service, treated as MIT-equivalent. And
Elastic-2.0 matters here directly: `kreuzberg` is pinned `<5` because its
successor line moved to it, and if that pin were removed this classifier would
have said nothing.

`LicenseTier.RESTRICTED` is the fourth tier. MinerU is why: Apache-2.0 plus a
100M-MAU / USD 20M-revenue commercial threshold and an **attribution obligation
for online services** — and `tokenmill gui --server` is an online service. The
adapter warns on every conversion, because a licence term nobody is told about
is one nobody complies with.

**A trap worth recording.** `pip install deepseek-ocr` installs a *third
party's* SDK for a hosted API — "Copyright (c) 2025 Chengjie",
`BukeLy/DeepSeek-OCR-SDK` — not DeepSeek's model. Wrapping it would have shipped
a hosted-SaaS backend, which constraint 1 forbids, while appearing to have
wrapped the model. A licence check alone would have waved it through; what
caught it was reading the `Summary` line.

**`heavy = []` is still empty.** A clean core install is **40 packages, 141.2
MB** against 140.6 MB before. The 0.6 MB is this phase's own source files —
`tokenmill` itself is 2.04 MB of the total — not a dependency.

**Granite-Docling is deliberately not a backend.** It is a model reached
*through* Docling, which is already wrapped. A seventh adapter would have been a
second route to an existing backend in order to pass a different `--model` flag,
with its own row in every user's listing. Recorded rather than counted.

**Two bugs found by reading output rather than by a test**, which is this
project's recurring lesson:

1. The service adapters were not recognised as heavy, so `doctor` silently gave
   them no install instructions, no weights-licence line and no no-GPU note.
   Fixed with a `HeavyTier` marker both families inherit.
2. `if __name__ == "__main__": main()` sat halfway up `cli/main.py`, so under
   `python -m` anything defined below it did not exist. Every command worked
   because every command was above it; the first helper added below broke
   `backends --all` with a `NameError`, through `python -m` only.

### 2026-08-27 — Phases 7 and 8 exit gate

**CI run 97 on `claude/phases-7-8-734pty` (commit `49076d0`): all 25 jobs
green.** That is the branch's first fully green run and it is the one the exit
gate rests on. The route there, because the failures are the useful part:

| Run | Result | What it found |
|---|---|---|
| 88 | ✅ success | the repomix npx-timeout fix; `Main`'s red cell resolved |
| 89 | ❌ 1 job | the byte/token orderings disagree — a **finding**, not a bug |
| 90 | ❌ 11 jobs | a deprecated metadata API under `-W error`; an environment-dependent test |
| 93 | ❌ | the same two, before the fix landed |
| 94 | ❌ 1 job | Type check: the `gui` extra was on the test job and not on that one |
| 97 | ✅ **success** | — |

Pasted, not summarised.

```console
$ uv run tokenmill convert tests/fixtures/tables.pdf --backend pymupdf4llm --tokenizer bytes
Figures are illustrative placeholders for structural testing and are not measurements of any real backend.
source:   tables.pdf
backend:  pymupdf4llm
format:   markdown
duration: 1573 ms
post:     normalize_whitespace
tokens:   553  (bytes)
size:     2.1 KiB in, no comparable before

$ uv run tokenmill backends --show-licenses   # tail

138 installed distributions audited from their own metadata.
1 is not simply permissive: docutils (Public Domain AND BSD License AND GNU General Public License (GPL))

$ uv run python -c "import sys, tokenmill; assert 'fitz' not in sys.modules; print(...)"
fitz not imported

$ uv run tokenmill compare tests/fixtures/tables.pdf --backends pdfplumber,pymupdf4llm,kreuzberg --tokenizer bytes --corpus tests/fixtures
comparing tables.pdf across 3 backend(s)
counts in bytes

backend      tokens  vs best  time     fidelity  components
-----------  ------  -------  -------  --------  ----------
pdfplumber   599     +29%     101 ms   0.667     3 scored
pymupdf4llm  553     +19%     1538 ms  0.848     3 scored
kreuzberg    466     base     21 ms    0.500     3 scored

cheapest:      kreuzberg (466)
most faithful: pymupdf4llm (0.848)
The cheapest option is NOT the most faithful one. A token saving without a fidelity number is not a result.

$ uv run pytest -q tests/unit/test_license_isolation.py tests/unit/test_subprocess.py tests/unit/test_isolated.py tests/unit/test_service_backend.py
.....................................................................    [100%]
69 passed in 13.80s

$ uv run pytest -q tests/integration/test_gui_api.py tests/unit/test_gui_boundary.py
............................................                             [100%]
44 passed in 5.48s

$ curl -sf localhost:8082 >/dev/null && echo "UI up"
UI up
```

Full gate:

```console
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
147 files already formatted
$ uv run mypy
Success: no issues found in 121 source files
$ uv run pytest -q --cov=tokenmill
1252 passed, 61 skipped
$ uv run python scripts/make_fixtures.py --check
OK: 24 files reproduced byte-for-byte
```

**And the same suite with the tools taken away**, because a well-equipped
machine hides a class of bug. `/usr/bin/pandoc` and `/usr/bin/soffice` moved
aside, `HOME` pointed away from the pymupdf4llm virtualenv:

```console
$ env HOME=/tmp/fakehome uv run pytest -q
1234 passed, 79 skipped in 63.93s
```

That is how CI run 90's Pandoc failure was reproduced in a minute rather than
waited for.

### 2026-08-26 — Phase 7: the licence check catching a real violation

The acceptance criterion is that the test be *seen* to fail. A real
`import pymupdf4llm` was added inside `pypdf_pdf.py`'s `_convert` — a lazy
import inside a real in-process adapter, which is the shape rule 3 requires and
the shape a naive scanner misses. Three of the four checks failed:

```
E  AssertionError: backend 'pypdf' declares itself permissive but reaches
   'pymupdf4llm', which is copyleft
E  AssertionError: copyleft modules are imported into the tokenmill process:
E      src/tokenmill/backends/documents/pypdf_pdf.py imports 'pymupdf4llm'
E    Invoke the tool as a child process through tokenmill.backends.isolated instead
E  AssertionError: backend 'pypdf' runs in-process and imports 'pymupdf4llm',
   which is copyleft
FAILED tests/unit/test_license_isolation.py::...::test_the_declared_licence_agrees_with_the_installed_metadata
FAILED tests/unit/test_license_isolation.py::...::test_no_module_in_the_package_imports_a_known_copyleft_module
FAILED tests/unit/test_license_isolation.py::...::test_no_in_process_backend_reaches_a_copyleft_distribution
3 failed, 14 passed in 2.28s
```

Reverted; 20 passed. The synthetic violations remain as permanent tests.

### 2026-08-26 — A licence classifier defect, found by reading real metadata

`RESEARCH.md` records PyMuPDF4LLM as AGPL-3.0. The installed package (1.28.2)
says:

```
License: Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License
```

The disjunction rule took the most permissive branch, which is right for `tld`
and wrong here — the other branch has to be **bought**. Worse, the split was
case-sensitive, so the free-text "or" did not split at all and got the right
answer by luck, while the SPDX spelling of the identical licence returned
*permissive*:

```
'AGPL-3.0-only OR LicenseRef-Artifex-Commercial'  -> permissive   (WRONG)
'AGPL-3.0 OR Commercial'                          -> permissive   (WRONG)
'GPL-3.0-only OR Proprietary'                     -> permissive   (WRONG)
```

For the flagship copyleft tool the whole phase exists to isolate. Fixed both
ways. After the fix all three classify copyleft, `tld` still classifies
permissive by resolving its own disjunction, and all installed distributions
still classify as they did.

### 2026-08-27 — Phase 8: the 20-file batch, measured

```
20-file batch in 3.10s; caller polled 362 times while it ran
total=20 done=20 failed=0 cancelled=0
aggregate check: before True, after True
```

And the bug that measurement found. The first aggregate summed `tokens_after`
over every item and `tokens_before` over only the items that had one — and a
binary document has no comparable before-count. The corpus reported:

```
tokens 35020 -> 40854  ratio=-0.16659051970302685
```

A 20-file batch that appeared to have **grown by 16.7%**. It had not; the
denominator was missing four PDFs and three Office files the numerator
included. After the fix:

```
comparable=6/20  before=35020 after=14348
ratio = 0.5903  (59.0%)
tokens_produced (all items) = 40854
```

### 2026-08-26 — Start-of-session probes

```
huggingface.co                       000 (blocked)
openaipublic.blob.core.windows.net   000 (blocked)
download.pytorch.org                 000 (blocked)
registry.npmjs.org                   200
pypi.org                             200
```

Unchanged from the last three sessions. Locally available: `node`, `npx`,
`java`, `soffice`. `pandoc` was absent and was installed for Phase 7
verification, as was `libreoffice-writer` — the container had
`libreoffice-core` only, so `soffice` was on `PATH` and could convert nothing.
That is now a documented failure mode with a test.

### 2026-08-26 — Core install weight (defect D4), decided

```
core install: 140.6 MB of site-packages (ceiling 250 MB)
40 packages
```

Where it is, and it is not where you would guess: `babel` 33 MB via
`trafilatura` → `courlan`; `cryptography` 16 MB and `pillow` 21 MB via the two
PDF backends; `lxml` 12 MB via trafilatura's tree. Six direct dependencies and a
localisation library three levels down is the largest single item.

Ceiling **250 MB**, enforced on all nine `clean-core-install` cells.

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
| `docling` | ✅ **Office formats only** — docx, pptx, xlsx, unicode | ✅ **PDF path verified**, CI run 81 | — |

**Docling's PDF path is verified.** Unverified since Phase 2; CI run 81
(`workflow_dispatch` on `Main`, commit `bac4dfa7`, job 98294307563) went green
including the step that downloads layout models from `huggingface.co`:

```
Office formats (no model download needed):   6 passed, 2 skipped, 53 deselected in 10.33s
PDF path (downloads layout models):          2 passed, 1124 deselected in 22.24s
```

**Where each Phase 3 backend was verified:**

| Backend | Verified locally | Verified in CI | Unverified |
|---|---|---|---|
| `trafilatura` | ✅ both HTML fixtures, output read; failure modes reproduced | ✅ 9 cells, **and its model-token figure in run 85** | ⚠️ live URLs |
| `readability` | ✅ both HTML fixtures, output read | ✅ 9 cells | ⚠️ live URLs |
| `crawl4ai` | ✅ **rendered `jsrendered.html` in a real Chromium**; 8 browser tests pass | ❌ never in the matrix | ⚠️ live URLs; any browser but this sandbox's Chromium 1194 |
| URL fetcher | ✅ 29 tests against a real loopback HTTP server | ✅ 9 cells | ⚠️ **the live-internet path has never run** — `example.com` is blocked |

**Where each Phase 7 backend was verified:**

| Backend | Verified locally | Verified in CI | Unverified |
|---|---|---|---|
| `pymupdf4llm` | ✅ all five PDF fixtures, output read; **most faithful backend in the corpus on all three scorable PDFs**; `sys.modules` checked after conversion | ⚠️ its *absence* is verified on 9 cells; the AGPL environment is not built there | ⚠️ **it has only ever run on this container** |
| `pandoc` | ✅ docx, html, md; the dropped-title failure mode found and fixed | ⚠️ absence only | ⚠️ only this container; only 3.1.3 |
| `libreoffice` | ✅ docx, unicode.docx; the exits-zero and missing-filter failure modes reproduced | ⚠️ absence only | ⚠️ only this container; only 24.2.7 |
| `ServiceConverter` | ✅ 11 tests against a real loopback `http.server`, including 500, non-JSON and timeout | ✅ 9 cells | ⚠️ **no real service has ever been talked to** |

Being explicit about the middle column, because it is the honest weakness of
Phase 7: **CI verifies that these three backends report themselves unavailable
and skip cleanly.** It does not verify that they convert anything, because
GitHub's runners have no Pandoc, no LibreOffice and no AGPL virtualenv. Their
conversion paths have been exercised on exactly one machine — which is the
condition the previous review complained about for the whole project, now
narrowed to three backends.

Installing them in CI would fix that. It was not done here because it changes
what the matrix is for; noted as an open question.

**Where each Phase 4 backend was verified:**

| Backend | Verified locally | Verified in CI | Unverified |
|---|---|---|---|
| `gitingest` | ✅ fixture repo, output read; four library defects found and fixed | ❌ CI cannot schedule runners | ⚠️ a real GitHub clone |
| `repomix` | ✅ via `npx`, output read; the missing-runtime path too | ❌ never in the matrix | ⚠️ a locally-installed `repomix` on `PATH` |
| `code2prompt` | ✅ built from crates.io (4.3.0), output read | ❌ never in the matrix | ⚠️ any platform but Linux |
| clone + cleanup | ✅ against a `git daemon` on loopback | ❌ | ⚠️ **the live-internet path has never run** |

| Backend | Domain | License | Tier | Wired | Tested | Notes |
|---------|--------|---------|------|-------|--------|-------|
| plaintext | text | Apache-2.0 (ours) | core | ✅ | ✅ | Phase 1 reference backend. Passes text/Markdown through; warns on non-UTF-8 input |
| markdownify_html | web | MIT **(verified v1.2.3)** | core | ✅ | ✅ | Phase 1 reference backend. Converts markup faithfully; **does not strip boilerplate** — that is Phase 3 |
| pdfplumber | documents | MIT **(verified 0.11.10)** | core | ✅ | ✅ | **Recovers all 35 cells of `tables.pdf`.** Interleaves multi-column pages; warns when it detects a gutter |
| pypdf | documents | BSD-3-Clause **(verified 6.16.1)** | core | ✅ | ✅ | Correct multi-column reading order. No tables, no headings |
| markitdown | documents | MIT **(verified 0.1.7)** | documents | ✅ | ✅ | **Only backend that keeps PPTX speaker notes.** Mis-splits PDF table headers; demotes the DOCX title |
| kreuzberg | documents | MIT **(verified 4.10.2)** | documents | ✅ | ✅ | Fast, correct reading order, infers PDF headings. **Flattens PDF tables into prose**; drops DOCX lists |
| docling | documents | MIT **(verified 2.121.0)** | docling | ✅ | ⚠️ | **Best structure fidelity.** Office paths verified; **PDF path unverified** — needs `huggingface.co`. 122 packages, 5.2 GB |
| trafilatura | web | Apache-2.0 **(verified 2.2.0)** | core | ✅ | ✅ | **Removes all 6 boilerplate markers, keeps all 6 headings and the table.** −77.1% bytes on `boilerplate.html`. Below 250 chars of content it silently stops extracting |
| readability | web | Apache-2.0 **(verified 0.8.4.1)** | web | ✅ | ✅ | An independent second extraction. **Byte-identical to trafilatura on our fixture** apart from table-separator spacing |
| crawl4ai | web | Apache-2.0 **(verified 0.9.2)** | crawl4ai | ✅ | ✅ | **The only backend that renders JavaScript.** Leaves 3 of 6 markers; refuses small SPA shells as anti-bot; 94 packages, 677 MB |
| gitingest | repo | MIT **(verified 0.3.1)** | repo | ✅ | ✅ | The default for a repository: needs no external runtime. **Reconfigures the host's stdlib logging on import**; the adapter undoes it |
| repomix | repo | MIT **(verified 1.18.0)** | subprocess | ✅ | ✅ | The most complete pack (8 files vs 7). Needs Node; `npx` downloads it per run, so it requires `--allow-network` without a local install |
| code2prompt | repo | MIT **(verified 4.3.0)** | subprocess | ✅ | ✅ | **Fastest: 103 ms vs 564 and 1,082.** No wheel — `cargo install` compiles it |
| llmlingua2 | compress | MIT **(verified 0.2.2, from the wheel's METADATA and bundled LICENSE)** | compress | ✅ | ⚠️ | Phase 6, off by default. **Success path never run anywhere** — needs `huggingface.co`. Refusal, error, import-time and arithmetic paths tested. 63 packages / ~4.7 GB including the CUDA stack |
| pymupdf4llm | documents | **AGPL-3.0** | isolated | ❌ | ❌ | Phase 7; **never imported** |
| pandoc | documents | **GPL-2.0+** | isolated | ❌ | ❌ | Phase 7; **never imported** |
| libreoffice | documents | MPL-2.0 | isolated | ❌ | ❌ | Phase 7; subprocess |
| marker | documents | **Apache-2.0 (verified 2.0.0 — NOT GPL-3.0 as `RESEARCH.md` says)** | heavy | ✅ | ⚠️ | Phase 9. Absent path, argv and output reading tested; **never run**. Out of process for rule 1, not rule 2 |
| surya | documents | **Apache-2.0 (verified 0.22.1 — NOT GPL-3.0)** | heavy | ✅ | ⚠️ | Phase 9. The backend that would move `scanned.pdf` off 0.000; **never run**, so 0.000 stands |
| mineru | documents | **`LicenseRef-MinerU-Open-Source-License` (verified 3.4.5)** | heavy | ✅ | ⚠️ | Phase 9, **restricted tier**. Warns on every conversion about the attribution obligation `--server` triggers |
| olmocr | documents | Apache-2.0 **(verified 0.4.27)** | heavy | ✅ | ⚠️ | Phase 9. Genuinely needs NVIDIA — vLLM has no CPU or Metal path |
| deepseek_ocr | documents | MIT **(reported by DeepSeek; no artefact read)** | heavy | ✅ | ⚠️ | Phase 9, service. The optical-compression story; **our own ratio does not exist**. HTTP path verified against a real server |
| dots_ocr | documents | MIT **(reported; no artefact read)** | heavy | ✅ | ⚠️ | Phase 9, service. 1.7B, the smallest of them |

**Where each Phase 9 backend was verified:**

| Backend | Verified locally | Verified in CI | Unverified |
|---|---|---|---|
| `marker` | ✅ absent path; argv and output reading against a real stub executable | ✅ absence, 9 cells | ❌ **every conversion.** No GPU, no route to the weights |
| `surya` | ✅ same | ✅ absence | ❌ every conversion, including the `scanned.pdf` regression target |
| `mineru` | ✅ same, plus the licence warning | ✅ absence | ❌ every conversion |
| `olmocr` | ✅ same | ✅ absence | ❌ every conversion |
| `deepseek_ocr` | ✅ **the whole HTTP path against a real local server** — request shape, temperature 0, usage accounting, refusals, a wrong-endpoint failure | ✅ 9 cells | ❌ that a real DeepSeek-OCR deployment answers this way. **No compression ratio of ours exists** |
| `dots_ocr` | ✅ same | ✅ 9 cells | ❌ same |
| `doctor` | ✅ output read on this sandbox; four hardware-lie cases against a stub `nvidia-smi` | ✅ 9 cells | ⚠️ never run on a machine with a real GPU |

Being explicit, because it is the honest weakness of the phase: **no heavy
backend has converted a document.** What was verified is the path a user without
a GPU takes, which is almost every user, plus everything about the adapters that
does not need the model to run.

### Post-processors

| Id | Destructive | In default chain | Order | Wired | Tested | Measured on `structured.md` |
|---|---|---|---|---|---|---|
| `strip_frontmatter` | yes | no (opt-in) | 50 | ✅ | ✅ | −5.9%, fidelity 1.000 |
| `normalize_whitespace` | **no** | **yes** | 100 | ✅ | ✅ | −0.2%, fidelity 1.000 |
| `aggressive_whitespace` | yes | no (opt-in) | 150 | ✅ | ✅ | −0.3%, fidelity 1.000 |
| `links` | yes | no (opt-in) | 200 | ✅ | ✅ | −5.4% strip / **+0.5% reference**, fidelity 0.955 |
| `dedupe_blocks` | yes | no (opt-in) | 250 | ✅ | ✅ | **−11.4%, fidelity 1.000** |
| `normalize_headings` | yes | no (opt-in) | 400 | ✅ | ✅ | −0.3%, **fidelity 0.750** |
| `chunk` | **no**¹ | no (opt-in) | 700 | ✅ | ✅ | **+1.8%** on `long_context.md` |
| `compress` | yes | no (opt-in) | 900 | ✅ | ⚠️² | **never run — no ratio exists** |

¹ `chunk` loses nothing and is still out of the default chain, and since Phase 7
those are **two separate declarations**: `destructive = False` and
`in_default_chain = False`, both true, which the old single flag could not
express. `chunk` is the processor that made the case for splitting it. The
default chain is still exactly `normalize_whitespace`, and `default_chain()`
reads **both** flags so a third-party post-processor written against the Phase 1
contract still behaves as it did.

² `compress`'s refusal, error, import-time and arithmetic paths are tested; its
success path has never been executed anywhere, because the model host is denied
at this environment's egress proxy.

**The default chain is exactly `normalize_whitespace`**, and that is asserted
over the whole registry rather than per processor.

### Table formats

| Id | Licence | Lossless | Wired | Tested | `tables.pdf` (bytes) |
|---|---|---|---|---|---|
| `csv` | ours (stdlib `csv`) | ✅ | ✅ | ✅ | **216** |
| `toon` | ours, per spec 4.1 (MIT) | ✅ | ✅ | ✅ | 240 |
| `markdown` | ours | ⚠️ two GFM-inherent losses | ✅ | ✅ | 332 |
| `keyvalue` | ours | ✅ | ✅ | ✅ | 456 |
| `json` | ours (stdlib `json`) | ⚠️ empty table loses columns | ✅ | ✅ | 543 |

### Tokenizers

| Id | Provider | Licence | Counts | Wired | Tested | Notes |
|---|---|---|---|---|---|---|
| `o200k_base`, `cl100k_base`, `p50k_base`, `r50k_base` | tiktoken | MIT (verified) | BPE tokens | ✅ | ✅ CI | Resolution, error paths and the "unavailable" path are tested locally; real counting is verified in the blocking `tokenizers` CI job. No real count has ever been produced *in this sandbox* |
| `hf:<model>` | HuggingFace `tokenizers` | Apache-2.0 | model tokens | ✅ | ✅ CI | Behind the `tokenizers` extra. Verified in CI against `bert-base-uncased` |
| `bytes` | ours | Apache-2.0 | **UTF-8 bytes, not model tokens** | ✅ | ✅ | Download-free. Golden vectors hand-checked |

## Decisions made

### Phases 7 and 8 (2026-08-26/27)

- **PyMuPDF4LLM runs in a separate interpreter, not `sys.executable`.** Running
  an AGPL package out of process is only isolation if it is not also installed
  here where anything can import it — which the licence suite's environment
  check would rightly fail on. It is therefore **never a tokenmill extra**, and
  the driver that touches it is a string constant passed to `python -c` rather
  than a `.py` file, so this repository contains no `import pymupdf4llm` for the
  static scan to find.
- **A disjunctive licence branch that must be bought is not a branch we hold.**
  Found by reading PyMuPDF4LLM's real metadata. Without this rule the flagship
  copyleft tool of the whole phase classified as permissive.
- **Multiple licence classifiers are joined conservatively**, as a conjunction.
  A false positive costs a documented exemption; a false negative costs a
  licence violation. `docutils` is the one exemption and it re-checks its own
  premise.
- **The copyleft allow-list lives in `core/licensing.py`, not in a test.**
  It was in the test file first, and running `tokenmill backends --show-licenses`
  found the consequence within a minute: the CLI reported a violation and exited
  non-zero while the suite passed. A policy with two homes has two answers.
- **Pandoc gets `--standalone`**, costing 42 bytes, because without it the DOCX
  title is silently discarded. Fidelity scored 0.841 either way — the metric has
  no component for metadata loss (N8) — so the choice was made on principle and
  a test guards it.
- **The batch queue is one worker thread.** Not a preference; `Pipeline.run`
  cannot safely go on a thread pool while defect D2 stands. A process pool is
  the eventual answer and would add a sixth kind of process-global concern
  today. Recorded with the measurement that killed the argument I first reached
  for: worker start-up is 0.133 s, not the several tenths I assumed.
- **The GUI's boundary is asserted over the import graph.** `app.py` may reach
  `gui.api`, `gui.batch`, `core.models` and `core.registry`, and nothing else.
- **No rate table ships, ever.** Cost estimation takes the user's own number,
  asserted by a test on the signature rather than merely intended.
- **No service backend is registered**, and a test keeps that deliberate: a row
  for a container nobody is running is a permanently-unavailable backend in
  every user's listing.


### Phase 5 (2026-08-24)

- **The format encoders re-serialise a table, not a whole document.** The plan's
  verification snippet says `convert tables.pdf --format toon`, and that command
  is deliberately not implemented. TOON encodes the JSON data model; a prose
  document is not that, and a whole-document TOON would be a shape nobody can
  read. `OutputFormat` still has two members. **Flagged for the owner** as a
  departure from the plan's wording, though not from its intent —
  `RESEARCH.md` Category 7's evidence is entirely about tabular data.

- **TOON is implemented here rather than wrapped**, which is a departure from
  "wrap best-in-class OSS tools" and needs its reasons on the record. All three
  were checked on the day, not read out of `RESEARCH.md`:

  1. `toon-format` 0.1.0 — the package under the format's own GitHub
     organisation, shipping `py.typed` and a complete API surface — **is a
     stub**. Both entry points raise
     `NotImplementedError("TOON encoder is not yet implemented")`.
  2. `toon-py` 1.0.2 works and round-trips, but emits `users[2,]{...}` where the
     specification's own example is `users[2]{...}`. §6 makes the delimiter
     optional and comma the default, so the extra character is legal — and a
     wasted character in every array header of a format whose entire claim is
     token efficiency is the wrong thing to inherit.
  3. Lossless round-tripping is the acceptance criterion, and it can only be
     guaranteed for an encoder and decoder written as a pair.

  Also worth recording: **TOON is on PyPI more than twice.** `toon` 0.15.9 is an
  unrelated project (it needs numpy and psutil), `pytoon` is a lip-sync library,
  and `toon-py`, `python-toon` and `toon-encoder` are three separate
  third-party ports. The handover said "twice"; it is worse than that.

  Conformance to the TypeScript reference is **unverified** — it cannot be run
  here. What is verified: round-tripping under property tests, and agreement
  with the specification's own worked examples.

- **Cells are strings, and a cell is written as a bare number only when that
  renders back to the identical string.** The obvious alternative — always
  strings — is exactly lossless and would have **rigged the comparison**: JSON
  and TOON would quote every number that CSV writes bare, and CSV would win by
  two characters per numeric cell that no real application spends. The other
  alternative — type inference — is not lossless: `05` returns as `5` and
  `1e-6` as `1e-06`. The rule adopted is strictly stronger than "looks numeric"
  and keeps both properties.

- **`compare` rows are in preference order, not sorted by size.** Sorting by
  tokens is a leaderboard, and on this data a leaderboard rewards whichever
  converter destroyed the most: on `tables.pdf` the cheapest backend is the one
  that flattens the table. The cheapest and the most faithful are named
  underneath and the report states outright when they differ. Where no ground
  truth exists it says the comparison cannot answer the question rather than
  leaving a blank that reads like a pass.

- **`compare` detects ground truth only for a target inside the corpus
  directory.** Matching on filename alone would score somebody's own
  `tables.pdf` against ours and produce a plausible number that means nothing.
  There is a test for the impostor case.

- **A backend can now record an intermediate text as a stage (D8), and this
  does not weaken "backends do not measure".** The backend hands over *text*;
  the pipeline does every count. A backend still cannot report a number. The
  text is transport only — the pipeline measures it and clears the field, so a
  result never carries a second copy of the document — and a backend stage
  cannot become `tokens_before`, which stays the source stage or nothing.

- **Chonkie is in a `chunk` extra, not core.** The owner's call, asked with
  measurements rather than adjectives: +10 packages, `lib/` 126 MB → 196 MB.
  §1.6 lists it in core; so did it list gitingest, which Phase 4 moved out on
  the same argument.

- **`destructive` now carries two meanings, and that is a question for the
  owner.** It was defined as "can lose information the user might have wanted".
  `chunk` loses nothing — it inserts markers — but is marked destructive
  because that flag is the only mechanism keeping a post-processor out of the
  default chain, and a conversion that silently grew chunk boundaries would be
  exactly the surprise the flag exists to prevent. A second flag
  (`changes_shape`, or `default_chain = False`) would separate the two. I did
  not add one, because growing the vocabulary per phase is the failure mode the
  Phase 0–4 review was watching for. **Open question 2.**

- **`aggressive_whitespace` is nearly worthless on this corpus and ships
  anyway.** +0.0% on `twocolumn.pdf` and `boilerplate.html`, −0.1% on
  `report.docx`, because the backends already emit tidy Markdown and
  `normalize_whitespace` runs first. It is a Phase 5 deliverable and it is
  genuinely useful on hand-written or scraped input, so it ships with the
  measurement printed next to it in `docs/BENCHMARKS.md` rather than being
  quietly dropped or quietly oversold.

### Fidelity slice (2026-08-24)

- **The module lives in `src/tokenmill/fidelity/`, outside the pipeline.** The
  owner suggested the location and I agree with it. What is worth recording is
  that it takes text and ground truth and returns a score — it never runs a
  conversion and never consults a tokenizer, and nothing in `core/` imports it.
  That keeps "backends do not measure" intact in both directions: the pipeline
  measures cost, this measures loss, and neither can quietly become the other.
  Phase 10's harness absorbs it by calling it, not by moving it.

- **A command, not a flag on `convert`.** The owner left this to me. Three
  reasons, in order of weight:

  1. **A flag would need `--against` anyway.** `convert` runs on arbitrary
     input and ground truth exists only for corpus fixtures, so
     `convert x.html --fidelity` cannot know what to score against. Inferring
     it from the filename is the bad version: it would score a document against
     whichever fixture shares its name.
  2. **The two halves compose better as two commands.**
     `tokenmill convert … -q | tokenmill fidelity - --against …` works because
     `convert` already puts text on stdout and its report on stderr. Reading
     `-` from stdin was the whole cost of that.
  3. **Phase 5's `compare` and Phase 10's harness both want a scoring function
     they call on text they already have**, not a conversion flag. A command is
     the thin surface over that function; a flag would have been a second one.

  The cost, stated plainly: scoring `convert`'s output takes two commands
  instead of one flag. `compare` will show fidelity inline, which is where the
  one-step version actually belongs.

- **The overall is an unweighted mean, and it carries the names of its
  components.** Any weighting encodes an opinion about whether a lost table
  matters more than a lost heading, and that opinion belongs to the user with
  the document. Naming the components is not decoration: an overall built from
  two of them is not comparable with one built from five, and a reader who
  cannot see which is which will compare them anyway. `boilerplate.html` scores
  from four components and `tables.pdf` from three.

- **An empty document is an explicit special case, not an emergent property.**
  This is the one design decision I would defend hardest. The arithmetic scores
  an empty string **1.0** on boilerplate rejection, because an empty string
  genuinely contains no boilerplate — the instrument built to catch a destroyed
  document credits it with perfect extraction. That is
  `benchmarks/README.md`'s own failure, one level up. So a document with no
  non-whitespace content scores 0.0 on every component that has ground truth
  and says why in the detail. No arrangement of fractions produces that on its
  own; it had to be written down.

  The general form of the same trap is handled by reporting rather than
  arithmetic: recall and rejection are always reported together, because
  neither says extraction worked on its own.

- **`None` beats zero, and beats one.** A component whose ground truth does not
  exist for a fixture scores `None` everywhere — API, table (`n/a`) and JSON
  (`null`). `long_context.md` has no table: 0.0 claims one was destroyed and
  1.0 claims one survived. Same rule Phase 0 set with `token_count: null`.

- **A heading that came back as plain text does not count as recovered.** The
  words survived; the heading did not. `pdfplumber` emits `tables.pdf`'s
  section titles as ordinary lines and `kreuzberg` emits one of them as `#`, and
  a scorer that counted text would call those equal. The count that survived as
  text is reported in the detail, because that is the actionable half.

- **A pipe table needs its delimiter row to count as a table**, and blank cells
  do not count as recovered cells. Both rules were forced by real output: a
  flattened table sometimes leaves pipes behind, and MarkItDown invents a blank
  header row for `report.docx`.

- **Two fixtures gained ground truth rather than two new fixtures being added.**
  `jsrendered.html` and `scanned.pdf` were both unscorable, and the first is the
  fixture the whole slice is for. Adding `must_contain`, `expected_headings` and
  `must_not_contain` to the generator made both scorable without changing a
  byte of any fixture.

  One near-miss worth recording: the obvious `must_contain` phrase for
  `jsrendered.html` was "inserted by a script", which also appears in the
  *placeholder*. A backend that recovered nothing scored 0.5 for finding it. The
  phrase is now "present in no response body", which appears only in the text
  the script inserts. A ground-truth string that the failure case also satisfies
  is worse than no ground truth.

- **`scanned.pdf` now scores 0.000 rather than staying silent.** Ground truth
  describes the document, not what our converters manage. The page really does
  carry those headings; this tier cannot read them, and 0.0 is the honest
  measurement of "no OCR here". Phase 9 has a regression target that moves it.

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

### From Phases 7 and 8

- **No sandboxing in the isolation layer** (N9). No resource limits, no
  filesystem confinement, no network namespace. A tool run through it has the
  user's access. It is a licence and language boundary and nothing more, and
  three documents say so.
- **No output streaming from a child process.** stdout is buffered whole, so a
  tool emitting a gigabyte holds a gigabyte. Bounded only by the input size cap.
- **No batch parallelism**, because of defect D2. One worker thread, conversions
  serialised. Fixing D2 — making the four adapters stop reaching for
  `warnings.catch_warnings` and the root logger — is what unlocks it, and it is
  the highest-value item on the defect list.
- **Uploads are never cleaned up** (N14). `~/.cache/tokenmill/uploads` grows for
  the life of a `--server` instance.
- **`--server` has no authentication** (N15). See Open questions.
- **A persistent child for `pymupdf4llm`.** It costs ~1.6 s of interpreter
  start-up per conversion against pdfplumber's 100 ms. The plan says measure
  before adding a batch mode, and that is the measurement that would justify
  one. Phase 10.
- **No service backend is registered.** `ServiceConverter` is tested against a
  real local server and nothing subclasses it yet; Phase 9 does.


### From Phase 6

- **The compressor's success path.** Not deferred by choice — deferred by an
  egress policy. Everything needed to run it is written; it wants
  `huggingface.co` and about 4.7 GB of install. The first person who runs it
  produces the first ratio this project has ever had.
- **Selective Context.** Deferred with the measurement: 0.1.4 pins
  `click==8.0.4` against our CLI's click and a resolver silently drops to 0.1.3.
- **A post-processor cannot warn or attach metadata.**
  `process(text, options) -> str` is the whole contract, where a backend gets a
  `ConversionContext` that collects warnings and structured facts. So the
  compressor logs instead of warning, and reports its ratio only through the
  pipeline's per-stage measurement. Phase 8's GUI will want a post-processor to
  be able to say something; the fix is a context parameter, which is a breaking
  change to the Phase 1 contract and needs the owner's sign-off.
- **The exact model download size is unstated** because `huggingface.co` cannot
  be reached to measure it. The docs say "hundreds of megabytes to a few
  gigabytes" and name both model options rather than inventing a figure.
- **The CPU-only PyTorch install is unverified.** `download.pytorch.org` is
  denied here, so whether the CPU wheel index avoids the CUDA stack could not be
  tested. Documented as the recommendation, marked unverified.
- **`compress` and `docling` have never been installed together**, only
  resolved together. A resolver finding a solution is not the same as the two
  working in one process.

### From Phase 5

- **No format encoder for nested data.** The encoders take a `Table`, which is
  by construction an array of uniform flat objects. That is deliberate — it is
  the only shape `RESEARCH.md` finds TOON reliably winning on, and TOON's
  accuracy is reported as collapsing on non-aligned structures — but it means
  `compare --formats` cannot answer "how should I serialise this nested JSON".
  A `nested.json` fixture and a documented failure case would be the honest way
  to show the limit rather than only assert it.
- **`--formats` re-encodes only the first table in the converted text.** A
  document with three tables gets one compared. Fine for the fixtures; wrong for
  a real report.
- **Only the fidelity of a *table* is measured after re-encoding.** Nothing
  scores whether CSV lost the heading structure around it, because the encoders
  operate on an extracted table rather than on the document.
- **The Markdown decoder is the same job `fidelity/markdown.py` does.** Two
  small pipe-table parsers now exist, with slightly different tolerances — the
  fidelity one requires a delimiter row for a stricter reason than the format
  one does. They should probably be one module.
- **`compare` has no wall-clock rigour.** `duration_s` is one run of one
  pipeline, unrepeated and unwarmed, so the 20 ms / 1,040 ms gap between
  kreuzberg and markitdown on `report.docx` is indicative and nothing more.
  Repeats, warmup and peak memory are Phase 10's.
- **`aggressive_whitespace` has no measured case where it helps.** Every fixture
  in the corpus is either generated tidy or converted by a backend that emits
  tidy Markdown. Its value is asserted from first principles and is not
  demonstrated by anything here.

### From the fidelity slice

- **This is not the Phase 10 harness.** No corpus-matrix runner, no wall time,
  no peak memory, no committed result files under `benchmarks/results/<date>/`.
  The table in `docs/BENCHMARKS.md` was produced by running conversions and
  scoring them, and its key rows are asserted by
  `tests/integration/test_fidelity_backends.py` — which is the weaker guarantee
  `docs/BENCHMARKS.md` already says it is operating under until the harness
  lands.
- **`structure_retention` has thin coverage.** Only `report.docx` names list
  items today; no fixture names link targets or code fences, so the component
  reads `n/a` for all but one fixture. Phase 5 needs a structure-rich fixture
  for its own post-processors (front matter, images, reference links, duplicate
  blocks) and that fixture will cover this too.
- **No fidelity score for a repository beyond content recall.** `sample_repo`
  has `must_contain` and `must_not_contain` and nothing structural. Whether a
  pack preserved a directory tree is a real fidelity question and is not asked.
- **Heading level mapping assumes ground-truth level *n* is Markdown `#`×(n+1).**
  True for `report.docx`, the only fixture that records levels. A fixture whose
  ground truth started at level 1 would need the mapping to be explicit.
- **The scorer does not diff.** It answers "did this survive", not "what changed",
  so a converter that silently *added* text is invisible to it unless the
  addition happens to be a boilerplate marker. `markdownify_html` adding 38.7%
  to the page's visible text is recorded in `docs/BENCHMARKS.md` and is not a
  fidelity component.

### From Phase 4

- **`SubprocessConverter` is still Phase 7's, and this is what it owes.**
  `tokenmill.backends._subprocess` is the minimum Phase 4 needed, sited one
  level above the tiers so Phase 7 can absorb it without a third rewrite of the
  call sites. It does PATH lookup, list arguments with `shell=False`, a
  timeout, captured output, and the taxonomy mapping. It does **not** do:
  - **sandboxing** — no resource limits, no filesystem confinement, no network
    namespace. A tool run through it has the same access the user does;
  - **binary discovery beyond `PATH`** — no bundled binaries, no version
    managers, no configured search paths;
  - **version probing or pinning** — tokenmill cannot say which Repomix
    produced a given pack, so a subprocess backend's provenance is weaker than
    a Python backend's, where the package version is knowable. This is the gap
    that matters most for reproducing a measurement;
  - **an allow-list** — any adapter can name any executable. Phase 7's licence
    enforcement needs the opposite: a checked list of what may be invoked, so a
    copyleft tool's isolation is enforced rather than declared;
  - **streaming** — output is buffered whole.

  Note that `repomix` and `code2prompt` are out of process because they are
  TypeScript and Rust, **not** because of their licences: both are MIT and could
  legally be imported if they were Python. That makes them safe practice for
  Phase 7, since getting the isolation wrong on them carries no licence risk.

- **Parsing three tools' output formats is brittle by nature.** Budgeting and
  the per-directory breakdown both need per-file structure and none of the three
  tools offers one, so each adapter carries a regex for its own tool's file
  header. code2prompt's was guessed wrong on the first attempt. The mitigation
  is that an unrecognised format produces *no sections and a warning*, never a
  silent file count of zero — but a format change still costs a release.
  A better fix would be asking each tool for machine-readable output where it
  offers one (repomix has `--style json`), which is a Phase 5 or Phase 10 job.

- **A repository has no before-count, so `tokenmill repo` prints one number.**
  Nobody hands a model the raw bytes of a directory. The pipeline reports
  `tokens_before: None` and warns "no readable source text", which is the same
  path a binary document takes. The comparison that means something is between
  *engines on the same repository*, and that is Phase 5's `compare`.

- **Three more uses of process-global state, none thread-safe.** The gitingest
  adapter manipulates `os.environ` (the GitHub token), the stdlib root logger's
  handlers and level, loguru's activation registry, and `warnings.catch_warnings`
  — all for the duration of one call, all restored afterwards. Nothing runs
  conversions concurrently today. The Phase 8 batch runner and any process-pool
  parallelism must account for all of them; this is the same note Phase 2 filed
  about `warnings.catch_warnings`, and Phase 4 has made it four times larger.

- **Include and exclude globs are passed to each tool rather than applied by
  tokenmill.** So their exact semantics differ slightly between engines —
  gitingest, repomix and code2prompt each have their own glob dialect. tokenmill
  documents the intent and the tools decide the edge cases. Applying them
  ourselves would mean re-walking the tree and second-guessing three tools;
  worth revisiting only if the differences bite someone.

- **No `--dry-run` for the budget.** A user who wants to know what *would* be
  dropped has to run the pack. Cheap to add later; left out rather than stubbed.

### From Phase 3

- **The live-internet fetch path has never run.** `example.com` is denied at the
  egress proxy. The fetcher is verified against a real HTTP server on loopback
  — 29 tests covering redirects, the redirect cap, scheme-change refusal, the
  byte cap, `robots.txt` in both directions, charsets, statuses, timeouts and a
  refused connection — and the live path is `network`-marked and unverified.
- **The boilerplate reduction in real model tokens is unverified.** Asserted by
  `tests/unit/test_web_tokens_network.py`, which runs in the blocking
  `tokenizers` CI job and prints the figure for the log. No token percentage is
  published anywhere until a green run prints one, and CI cannot schedule
  runners as of today.
- **crawl4ai is verified against exactly one browser.** The sandbox's Chromium
  1194, reached by pinning playwright to 1.56.0 *locally* — a fact about this
  container, not a project decision, and deliberately not in `pyproject.toml`.
- **No conditional or authenticated fetching.** No cookies, no headers beyond
  the user agent, no ETag, no caching. A page behind a login is not fetchable,
  and saying so beats a half-implemented credential story.
- **`--tree-tokens` has no equivalent for web or document conversions.** The
  question "which part of this is eating my context" is just as good for a long
  document; it needs a different decomposition (sections rather than files) and
  belongs with Phase 5's measurement depth.

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

**Answered and implemented this session:** §3.1 (publish the token figure — done,
D3 closed), §3.2 (`in_default_chain` — done), §3.3 (`--format toon` stays
unimplemented, plan amended), §3.4 (one Markdown table parser — done), §3.5
(core ceiling — 250 MB, enforced), §3.7 (the `compress` job — added; see below).

**1. Only you can dispatch a workflow, and two things are waiting on it.**

`POST /actions/workflows/ci.yml/dispatches` returns
`403 Resource not accessible by integration` for this session, as it did for the
previous one. Two jobs are gated to `workflow_dispatch` or the Sunday schedule
and neither has run against this branch:

- **`compress`** — added this session. It is the thing that would close Phase 6,
  the largest verification hole in the repository, and it is itself unverified.
  I believe it fits: the extra is 63 packages and ~4.7 GB, and the `docling` job
  beside it installs 122 packages and ~5.2 GB with torch and passed run 81 in
  85 seconds on the same runner with the same free-disk-space step. That is
  evidence rather than certainty.
- **`docling`** — passed on `Main` in run 81, but has not run against this
  branch's changes.

Actions → CI → Run workflow, against `claude/phases-7-8-734pty`. Tell me what
they show and I will record it.

**2. `tokenmill gui --server` has no authentication. How far should that go?**

It binds `0.0.0.0`, has no login, no CSRF protection and no rate limit, and its
upload endpoint writes to disk. It prints a warning at startup and that is the
only mitigation. Nobody should run it outside a trusted network as it stands.

Phase 9 is the phase whose backends live on other machines, which makes this the
wrong thing to leave open going into it. Three options:

- **A shared token in a header**, read from config or an environment variable,
  refusing every request without it. An hour, and enough for a LAN.
- **Bind localhost only and document an SSH tunnel** as the supported remote
  story. Nothing to build, and it makes `--server` almost pointless.
- **Leave it, with the warning.** Cheapest, and I would not.

My recommendation is the first. It is not security in any strong sense — no TLS,
no user accounts — and it stops a machine on the same network converting files
and reading the results, which is the actual exposure.

**3. Should CI install Pandoc and LibreOffice?**

Phase 7's three isolated backends have had their *conversion* paths exercised on
exactly one machine — this container — because GitHub's runners have neither
tool and the AGPL virtualenv is not built there. CI verifies only that they
report themselves unavailable and skip.

That is precisely the condition the last review complained about, now narrowed
to three backends. `apt install pandoc libreoffice-writer` on the ubuntu cell
would fix two of them for about ninety seconds of install time; the AGPL one
needs a virtualenv built in a step, which is cheap but is a deliberate decision
to install an AGPL package in CI.

I did not do it because it changes what the test matrix is for — from "our code
on nine platforms" to "our code plus a system-package installation" — and that
is your call, not mine.

**4. Defect N2 — should `PostProcessor.process` take a context?**

Proposed, not done, as instructed. A post-processor cannot warn or attach
metadata: `process(text, options) -> str` is the whole contract, where a backend
gets a `ConversionContext`. The GUI made this concrete — the compressor can
report its achieved ratio only through the per-stage measurement, and a
post-processor that wanted to say "this document had no front matter to strip"
has no channel at all.

The change is `process(text, options, context) -> str`, mirroring
`_convert`. It is a breaking change to the Phase 1 contract and every
third-party post-processor. If you want it, the cheapest shape is a new optional
parameter with the registry passing a context only to processors that declare
they accept one — uglier, and it does not break anyone.

**5. What should the isolation layer be called?**

Minor and real. Defect N9: it is a licence and language boundary with **no
sandboxing** — no resource limits, no filesystem confinement, no network
namespace. "Isolation" invites the security reading, and three documents now
carry a paragraph saying it is not that. A name that did not need the paragraph
would be better, and renaming it after Phase 9 subclasses it will be expensive.

### Previously open, now closed


Phase 2's three questions were answered on 2026-08-22 and the answers are
implemented; see Decisions for each, and the table below. One new question has
opened since, and it needs owner-level access rather than a decision.

**1. CI cannot schedule runners — please check the Actions billing state.**
**Step-by-step instructions: [`docs/CI_BILLING_CHECK.md`](docs/CI_BILLING_CHECK.md).**
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

**2. `destructive` now means two things — do you want a second flag?**

The flag was defined as "can lose information the user might have wanted", and
`default_chain()` is built by excluding it. Phase 5's `chunk` post-processor
loses nothing — it inserts chunk markers — but is marked destructive anyway,
because that flag is the only mechanism that keeps a post-processor out of the
default chain, and a conversion that silently grew chunk boundaries nobody asked
for is exactly the surprise the flag exists to prevent.

So the flag now carries "can lose information" **and** "changes the document's
shape". Three options:

- **Leave it.** One flag, one meaning in practice ("not in the default chain"),
  and the docstrings explain the stretch. Cheapest, slightly dishonest naming.
- **Add `changes_shape`.** Two flags, `default_chain()` excludes either.
  Honest, and grows the vocabulary — which is the failure mode
  `docs/REVIEW_PHASES_0_4.md` §4 was watching for.
- **Rename the mechanism** to `in_default_chain: bool` and let `destructive`
  become pure documentation. Clearest, and a breaking change to the Phase 1
  post-processor contract, which needs your sign-off.

I did not pick one. My recommendation is the third, at whatever point another
non-destructive-but-reshaping processor appears; until then the first is fine
and the code says so out loud.

**3. Is `--format toon` supposed to exist?**

`DEVELOPMENT_PLAN.md`'s Phase 5 verification snippet says
`convert tests/fixtures/tables.pdf --format toon --show-stages`. That command is
deliberately not implemented: TOON encodes the JSON data model and a prose
document is not that, so a whole-document TOON would be a shape nobody can read.
The encoders re-serialise a **table**, which is what all of `RESEARCH.md`
Category 7's evidence is about, and `tokenmill compare --formats` is the
equivalent. Say if you meant something else by that line.

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
