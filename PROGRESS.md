# Progress

_Last updated: 2026-08-20 by Claude Code_

## Status at a glance

| Phase | Name | Status | Exit gate |
|-------|------|--------|-----------|
| 0 | Scaffolding and toolchain | ✅ Complete | passed 2026-08-20 |
| 1 | Core architecture | ⬜ Not started | — |
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

## Current phase: 0 — Scaffolding and toolchain

**Goal:** a repository that installs, lints, type-checks, tests and documents
itself, containing zero product logic.

**Done so far:**

- Verified the sandbox toolchain and recorded it (see Environment below).
- Checked name availability. `tokenfold` is **taken on PyPI**; the project was
  renamed to **`tokenmill`** with owner sign-off before the first commit. See
  Decisions.
- `pyproject.toml` — hatchling build, `src/` layout, `requires-python >=3.11`,
  the full dependency tiering from plan §1.6 declared, core deliberately empty
  at this phase.
- `src/tokenmill/__init__.py` (version only), `src/tokenmill/py.typed`.
- `LICENSE` — Apache-2.0, copyright line filled in.
- Toolchain config in `pyproject.toml`: Ruff lint (20 rule families, including
  `S` for security and `T20` to keep `print` out of the library) + Ruff format,
  mypy in `strict` mode over `src`/`scripts`/`tests`, pytest with markers and
  `filterwarnings = ["error"]`, coverage with branch tracking.
- `uv` workflow; `uv.lock` committed.
- `.pre-commit-config.yaml` — hygiene hooks, ruff check/format, mypy.
- `.github/workflows/ci.yml` — five jobs: `lint`, `types`, `test`
  (3.11/3.12/3.13 × ubuntu/macos/windows = 9 cells), `fixtures`
  (regenerates the corpus and compares SHA-256 digests), and
  `clean-core-install` (plain `pip install .`, no extras, then import the
  package from outside the source tree — 9 cells).
- `scripts/make_fixtures.py` — generates the entire synthetic corpus
  byte-reproducibly and writes `ground_truth.json` beside it.
- `tests/fixtures/` — all 13 planned fixtures generated and inspected.
- `tests/unit/test_package.py`, `tests/unit/test_fixtures.py`,
  `tests/conftest.py` — 27 tests.
- Docs: `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, issue templates, PR
  template, `benchmarks/README.md`, and the two source documents committed
  as-is at `docs/DEVELOPMENT_PLAN.md` and `docs/research/RESEARCH.md`.

**Remaining in this phase:** nothing. Exit gate passed.

**Blocked on:** nothing blocking. Two items need an owner decision before or
during Phase 1 — see Open questions 1 and 2.

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

## Backend status

No backends exist yet — Phase 0 ships zero product logic by design. The table
below is the planned set, with licences taken from `docs/research/RESEARCH.md`
and **not yet independently re-verified**. Licences get checked against the
upstream repository at the moment each adapter is implemented, and any
correction is recorded under Decisions.

| Backend | Domain | License (per RESEARCH.md, unverified) | Tier | Wired | Tested | Notes |
|---------|--------|---------------------------------------|------|-------|--------|-------|
| plaintext | text | n/a (ours) | core | ❌ | ❌ | Phase 1 reference backend |
| markdownify_html | web | MIT | core | ❌ | ❌ | Phase 1 reference backend |
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

## Decisions made

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
- **Release checklist in `CONTRIBUTING.md`.** Stubbed as "fills out in Phase 11"
  because publishing does not exist yet.

## Open questions for the owner

1. **Token counting cannot be verified in this sandbox.** The egress proxy
   denies `openaipublic.blob.core.windows.net` (tiktoken's BPE download) and
   `huggingface.co` (HF tokenizers, and every model download). Token measurement
   is the product's core value proposition, so I need one of:
   (a) those two hosts added to the sandbox allow-list;
   (b) acceptance that tokenizer behaviour is verified only in GitHub Actions,
       where the hosts are reachable, and that local runs skip those tests; or
   (c) a decision to vendor a BPE file into the repository — I would rather not,
       since it adds a licensing question and a maintenance burden.
   My recommendation is (a); failing that, (b). This does not block starting
   Phase 1 — the registry, protocol, pipeline and CLI can all be built and
   tested — but it does block *observing* a real before/after token count, which
   is exactly what Phase 1's exit gate asks for.

2. **The GitHub repository is still named `RSD-Studio/tokenfold`.** The package,
   CLI, module and docs are all `tokenmill` now. Renaming the repository on
   GitHub is a one-click operation and GitHub keeps redirects, so nothing
   breaks. Do you want to rename it to `RSD-Studio/tokenmill`? Until you do, the
   README and `pyproject.toml` URLs point at `RSD-Studio/tokenmill`, which will
   404. Say the word and I will either change the URLs back or leave them
   pointing at the new name.

3. **The working branch is `claude/tokenfold-project-setup-9m3i5o`.** I was
   instructed to push there and have done so. Confirm you want subsequent phases
   on the same branch, or tell me the branch convention you would prefer (the
   plan suggests one PR-sized branch per phase).

4. **Should CI publish coverage anywhere** (Codecov or similar), or is the
   terminal report enough? The plan sets a ≥85% target on `core` and `tokens`
   from Phase 1; I can add a hard `--cov-fail-under` gate scoped to those
   packages once they exist. Say if you want that enforced in CI rather than
   just reported.
