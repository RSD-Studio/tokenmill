# Review: Phases 0–12

**Supersedes [`REVIEW_PHASES_0_8.md`](REVIEW_PHASES_0_8.md)**, which stays in the
repository for the same reason its predecessor did: a review is a record of what
a session could see, and deleting it would hide how the picture changed.

Written at the end of the final session. There is no Phase 13.

---

## 1. Verdict first

**tokenmill does what it says, on the corpus it says, in the unit it says — and
the unit is not the one the project is about.**

The architecture holds. Twenty-two backends register through one contract with
no hard-coded list; the copyleft ones have never entered the process and four
independent checks say so; the core install is 141.2 MB against a ceiling CI
enforces on nine cells and on the built wheel. A 63-cell benchmark is committed
with its raw data, its manifest, and one command that regenerates it. Every
number in every document traces to that file or to a named test, and a script
checked that rather than a human.

**The gap is that the whole matrix is counted in UTF-8 bytes.** The project
exists to report token costs. The environment it was built in denies every
tokenizer vocabulary host, so it cannot count tokens at all, and the workflow
that would fix that has never been dispatched. Four token figures exist in the
repository, all from CI logs, none of them from the matrix. This is disclosed in
the README's first screen, in `BENCHMARKS.md`'s first limitation, in the
generated tables' header, and in `CLAIMS.md` — which is the right response, and
is not the same as it being fixed.

**Two other things are implemented and undemonstrated.** No GPU backend has ever
converted a document. Prompt compression's success path has never executed. Both
for the same reason: a denied host.

**What I would tell someone deciding whether to use it:** the CLI, the library
and the GUI work, on formats the tests exercise, on three platforms and three
Pythons. The measurement machinery is real and the honesty machinery around it
is unusually good. Do not quote a saving from this repository as a *token*
saving, and do not assume any OCR path works.

---

## 2. Acceptance criteria, phase by phase

### The six repairs (plus four found on the way)

| # | What was asked | Status |
|---|---|---|
| §3.1 / N15 | Shared-token auth for `gui --server`, generated when unset | ✅ `ServerTokenGuard`, raw ASGI, guards HTTP **and** WebSocket. 23 tests. Docs state precisely what it is not: no TLS, no accounts, no audit |
| §3.2 / D2 | Fix process-global state, then measure parallel vs serial | ✅ Fixed with `GLOBAL_STATE_LOCK`. **The measurement is a null result on the headline workload** and is published first: 0.91× in-process, 3.12× subprocess |
| §3.3 / N2 | Optional context parameter on `PostProcessor.process` | ✅ Registry passes it only to processors that declare it. The base class deliberately keeps two parameters — widening in a subclass is legal, narrowing is not, and trying it produced narrowing-override errors in nine files |
| §3.4 / N9 | Rename the isolation layer; keep `IsolationMode` if smaller | ✅ `backends/isolated/` → `backends/external/`. Enum name kept. `ARCHITECTURE.md` says why |
| §3.5 | CI installs Pandoc, LibreOffice and the AGPL venv on ubuntu | ✅ On both the `test` and `coverage` cells |
| §3.6 | N14 bounded uploads; D6 `--style json`; N4 all tables; N5 measure or delete | ✅ All four. **N5 reversed by measurement** — see §4 |
| R0 | *(not asked; found on arrival)* LibreOffice reported available on an install that could not convert | ✅ Probe now checks the component registry. Verified in both directions |

### Phase 9 — the GPU tier

| Criterion | Status |
|---|---|
| Six backends, out of process, install-docs-only | ✅ `marker`, `surya`, `mineru`, `olmocr`, `deepseek_ocr`, `dots_ocr` |
| `heavy = []` stays empty; core weight does not move | ✅ 141.2 MB / 40 packages. The 0.6 MB rise over Phase 8's 140.6 is our own new source |
| Licences verified from installed metadata | ✅ And `RESEARCH.md` was wrong twice more. Marker and Surya are Apache-2.0, not GPL-3.0; MinerU is `LicenseRef-MinerU`, needing a fourth tier |
| `tokenmill doctor` | ✅ Distinguishes "no GPU" from "driver present, no device answered" |
| **A heavy backend converting a document** | ❌ **Never. Not once.** No GPU, weight host denied |

### Phase 10 — the benchmark harness

| Criterion | Status |
|---|---|
| A full run completes unattended, re-runnable by a third party | ✅ One command, ~100 s. The sdist now carries the harness *and* the results, which it did not |
| A complete result set committed | ✅ 63 cells, four files, manifest with commit / digest / platform / versions |
| Fidelity beside every token count | ✅ Enforced: `check_report()` raises rather than rendering a token column without one |
| Failures and empties are results, not omissions | ✅ Own sections. 8 failures, 4 empty successes |
| N=5, not one unrepeated run *(defect N7)* | ✅ Warm-up discarded, five timed, median and spread published |
| `docs/BENCHMARKS.md` written with limitations | ✅ Seven of them, linked from the first screen |
| No unsourced claim anywhere in the repository | ✅ Checked by script over every `(fixture, backend, number)` triple. Four corrections |
| **Model-token columns from CI** | ❌ **Workflow written, tested against its failure path, never dispatched** |

### Phase 11 — packaging and release

| Criterion | Status |
|---|---|
| Build sdist and wheel | ✅ `twine check --strict` passes on both |
| Test in a clean container | ✅ Clean venv, **no source tree**, imports, lists backends, converts end to end, 141.2 MB |
| Wire the publish workflow, do not publish | ✅ Trusted publishing, manual dispatch only, in a GitHub Environment a tag push cannot reach |
| `pipx` / `uv tool install` docs | ✅ |
| Docker image + compose profiles | 🟨 **Written, never built** — no Docker daemon here. CI builds both targets and makes both system-binary backends convert; that job has not run |
| Release checklist in `CONTRIBUTING.md` | ✅ Commands, not intentions |
| `docs/LICENSES.md` on what the artefact contains | ✅ Four artefacts, each stated separately, including that no model weights are in any of them |
| **Tag `v0.1.0`** | ❌ **Created locally; the push is refused with HTTP 403.** This integration can write the branch and not a tag ref |
| PySide6 / PyInstaller | ⏸️ Deferred on instruction, recorded so the plan and the repository do not disagree silently |

### Phase 12 — documentation and article pack

| Criterion | Status |
|---|---|
| README: positioning, sourced case, backend matrix, screenshots, quickstart, licence tiering | ✅ Status block rewritten from "Phase 2"; five screenshots embedded with captions checked against the images |
| Honest comparison to omniparse / docling-serve / MarkItDown GUI forks | ✅ A table, plus the honest version of both the pitch and the caveat |
| `docs/BACKENDS.md` completion | ✅ GPU tier in the glance table; the stale "not here yet" list replaced with the one real gap (no CPU OCR) |
| `docs/ADDING_A_BACKEND.md` | ✅ Existed since Phase 5; unchanged and still correct |
| `docs/FAQ.md` | ✅ Including the questions whose answer is "we don't know" |
| `docs/article/` with a claims file | ✅ Every claim labelled Measured / Cited / **Unverified**. Tables and charts generated, with a test that they match the data |
| Final `PROGRESS.md` pass | ✅ |

---

## 3. The whole corpus

Commit `e8a2065`, corpus digest `cd2d48ccf99bddb4`, Linux/x86-64, Python
3.11.15, 4 cores, N=5. **UTF-8 bytes, not model tokens.**

| Fixture | Backend | Bytes out | Change | Fidelity | Scored | Median | Added RSS |
|---|---|---|---|---|---|---|---|
| `article.html` | `trafilatura` | 2,854 | −19.8% | 1.000 | 3 | 4 ms | 0 MiB |
| `article.html` | `readability` | 2,864 | −19.6% | 1.000 | 3 | 8 ms | 0 MiB |
| `article.html` | `markdownify_html` | 2,916 | −18.1% | 1.000 | 3 | 5 ms | 0 MiB |
| `article.html` | `markitdown` | 2,864 | −19.6% | 1.000 | 3 | 38 ms | 8 MiB |
| `article.html` | `kreuzberg` | 3,063 | −14.0% | 1.000 | 3 | 1 ms | 0 MiB |
| `article.html` | `pandoc` | 3,072 | −13.7% | 1.000 | 3 | 56 ms | 108 MiB |
| `boilerplate.html` | `trafilatura` | 2,854 | −77.1% | 1.000 | 4 | 10 ms | 0 MiB |
| `boilerplate.html` | `readability` | 2,864 | −77.1% | 1.000 | 4 | 19 ms | 0 MiB |
| `boilerplate.html` | `markdownify_html` | 6,802 | −45.5% | 0.750 | 4 | 21 ms | 0 MiB |
| `boilerplate.html` | `markitdown` | 6,713 | −46.2% | 0.750 | 4 | 49 ms | 10 MiB |
| `boilerplate.html` | `kreuzberg` | 6,120 | −51.0% | 0.750 | 4 | 2 ms | 0 MiB |
| `boilerplate.html` | `pandoc` | 7,346 | −41.1% | 0.750 | 4 | 76 ms | 111 MiB |
| `corrupt.pdf` | `pdfplumber` | **fail** | — | n/a | 0 | — | — |
| `corrupt.pdf` | `kreuzberg` | **fail** | — | n/a | 0 | — | — |
| `corrupt.pdf` | `markitdown` | **fail** | — | n/a | 0 | — | — |
| `corrupt.pdf` | `pypdf` | **fail** | — | n/a | 0 | — | — |
| `corrupt.pdf` | `pymupdf4llm` | **fail** | — | n/a | 0 | — | — |
| `data.xlsx` | `markitdown` | 675 | — | 0.667 | 1 | 54 ms | 10 MiB |
| `data.xlsx` | `kreuzberg` | 664 | — | 1.000 | 1 | 3 ms | 0 MiB |
| `data.xlsx` | `libreoffice` | **fail** | — | n/a | 0 | — | — |
| `deck.pptx` | `markitdown` | 753 | — | 1.000 | 1 | 54 ms | 0 MiB |
| `deck.pptx` | `kreuzberg` | 398 | — | 1.000 | 1 | 3 ms | 0 MiB |
| `deck.pptx` | `libreoffice` | **fail** | — | n/a | 0 | — | — |
| `jsrendered.html` | `trafilatura` | 140 | −90.7% | 0.000 | 3 | 2 ms | 0 MiB |
| `jsrendered.html` | `readability` | 167 | −89.0% | 0.000 | 3 | 2 ms | 0 MiB |
| `jsrendered.html` | `markdownify_html` | 165 | −89.1% | 0.000 | 3 | 1 ms | 0 MiB |
| `jsrendered.html` | `markitdown` | 140 | −90.7% | 0.000 | 3 | 35 ms | 0 MiB |
| `jsrendered.html` | `kreuzberg` | 180 | −88.1% | 0.000 | 3 | 0 ms | 0 MiB |
| `jsrendered.html` | `pandoc` | 225 | −85.1% | 0.000 | 3 | 15 ms | 28 MiB |
| `long_context.md` | `plaintext` | 79,255 | −0.0% | n/a | 0 | 1 ms | 0 MiB |
| `long_context.md` | `pandoc` | 79,255 | −0.0% | n/a | 0 | 237 ms | 123 MiB |
| `report.docx` | `markitdown` | 3,494 | — | 0.841 | 4 | 346 ms | 0 MiB |
| `report.docx` | `kreuzberg` | 3,472 | — | 0.614 | 4 | 7 ms | 0 MiB |
| `report.docx` | `pandoc` | 3,567 | — | 0.841 | 4 | 167 ms | 125 MiB |
| `report.docx` | `libreoffice` | 3,418 | — | 0.375 | 4 | 1,466 ms | 263 MiB |
| `scanned.pdf` | `pdfplumber` | 0 **(empty)** | — | 0.000 | 2 | 3 ms | 0 MiB |
| `scanned.pdf` | `kreuzberg` | 0 **(empty)** | — | 0.000 | 2 | 5 ms | 0 MiB |
| `scanned.pdf` | `markitdown` | 0 **(empty)** | — | 0.000 | 2 | 37 ms | 0 MiB |
| `scanned.pdf` | `pypdf` | 0 **(empty)** | — | 0.000 | 2 | 2 ms | 0 MiB |
| `scanned.pdf` | `pymupdf4llm` | **fail** | — | n/a | 0 | — | — |
| `simple.pdf` | `pdfplumber` | 2,370 | — | 0.500 | 2 | 79 ms | 0 MiB |
| `simple.pdf` | `kreuzberg` | 2,371 | — | 0.900 | 2 | 15 ms | 0 MiB |
| `simple.pdf` | `markitdown` | 2,377 | — | 0.500 | 2 | 135 ms | 0 MiB |
| `simple.pdf` | `pypdf` | 2,371 | — | 0.500 | 2 | 9 ms | 0 MiB |
| `simple.pdf` | `pymupdf4llm` | 2,410 | — | 1.000 | 2 | 1,152 ms | 322 MiB |
| `structured.md` | `plaintext` | 1,466 | −0.2% | 1.000 | 4 | 0 ms | 0 MiB |
| `structured.md` | `pandoc` | 1,609 | +9.5% | 0.977 | 4 | 35 ms | 64 MiB |
| `tables.pdf` | `pdfplumber` | 599 | — | 0.667 | 3 | 26 ms | 0 MiB |
| `tables.pdf` | `kreuzberg` | 466 | — | 0.500 | 3 | 9 ms | 0 MiB |
| `tables.pdf` | `markitdown` | 769 | — | 0.606 | 3 | 50 ms | 0 MiB |
| `tables.pdf` | `pypdf` | 481 | — | 0.333 | 3 | 5 ms | 0 MiB |
| `tables.pdf` | `pymupdf4llm` | 553 | — | 0.848 | 3 | 1,168 ms | 280 MiB |
| `twocolumn.pdf` | `pdfplumber` | 4,050 | — | 0.528 | 3 | 151 ms | 0 MiB |
| `twocolumn.pdf` | `kreuzberg` | 4,061 | — | 0.667 | 3 | 24 ms | 0 MiB |
| `twocolumn.pdf` | `markitdown` | 4,062 | — | 0.528 | 3 | 311 ms | 0 MiB |
| `twocolumn.pdf` | `pypdf` | 4,050 | — | 0.667 | 3 | 13 ms | 0 MiB |
| `twocolumn.pdf` | `pymupdf4llm` | 4,069 | — | 0.972 | 3 | 1,316 ms | 282 MiB |
| `unicode.docx` | `markitdown` | 1,312 | — | 0.955 | 2 | 322 ms | 0 MiB |
| `unicode.docx` | `kreuzberg` | 1,314 | — | 1.000 | 2 | 7 ms | 0 MiB |
| `unicode.docx` | `pandoc` | 1,327 | — | 1.000 | 2 | 167 ms | 124 MiB |
| `unicode.docx` | `libreoffice` | 1,274 | — | 0.500 | 2 | 1,446 ms | 263 MiB |
| `sample_repo` | `gitingest` | 2,944 | — | 1.000 | 2 | 271 ms | 0 MiB |
| `sample_repo` | `repomix` | 3,786 | — | 1.000 | 2 | 1,518 ms | 279 MiB |

`repomix` reports no version because it runs through `npx`, which the adapter
invokes without a separate `--version` probe. The report prints `—` rather than
guessing.

### What this table says that no earlier one could

**Two opposite regimes.** On documents the cheap output is the unfaithful one —
`pypdf` gives 481 bytes at 0.333 on `tables.pdf` against `pymupdf4llm`'s 553 at
0.848. On web pages the cheap output is the *better* one — `trafilatura` gives
2,854 at 1.000 on `boilerplate.html` against `pandoc`'s 7,346 at 0.750. A PDF
extractor recovers structure the format discarded, so less work means less
structure; a web extractor discards structure the format kept, so less work
means keeping more of it.

**The project was built on the first half of that and the second half is new.**

**The cost column cannot see the difference that matters.** `twocolumn.pdf`:
five backends inside a 0.47% size spread and 0.444 apart on fidelity.

**The largest saving in the corpus extracted nothing.** `jsrendered.html`,
−90.7%, fidelity 0.000, six backends between −85.1% and −90.7%.

**`libreoffice` is last on every axis it can be measured on**, and it is in the
default preference order. Kept for format coverage, which `BACKENDS.md` now
says in as many words with the table beside it.

---

## 4. Defects: closed, open, introduced

### Closed this session

| # | What it was | How it closed |
|---|---|---|
| **D2** | Process-global state mutated without a lock, which had cost the GUI its parallelism | `GLOBAL_STATE_LOCK`, then measured. The tests initially **passed without the lock** — at CPython's 5 ms switch interval the races never reproduce — so a `preemptive` fixture sets it to 1 µs, after which two of three go red when the lock is removed. The third is weak and the docstring says which |
| **D4** | Core weight unsigned-off | Ceiling set at 250 MB, enforced on nine cells *and* on the built wheel |
| **D6** | `repomix --style json` unused | **It was a correctness bug, not tidiness.** The Markdown splitter matched a `## File:` marker inside a *quoted* document, so a repository containing one reported a file that does not exist |
| **N2** | `PostProcessor.process` had no context | Optional third parameter, passed only to processors that declare it |
| **N4** | `compare --formats` showed one table | All tables |
| **N5** | `aggressive_whitespace` had no demonstrated benefit | **Reversed by measurement.** Judged on three cells it was worthless; across fifty it saves 18.3% on `tables.pdf`/`markitdown` at unchanged fidelity, because MarkItDown pads its table columns. Ten of fifty save something |
| **N7** | Every timing was one unrepeated run | N=5 with a discarded warm-up, median and spread |
| **N9** | "Isolation" oversold what it does | Renamed to `external` |
| **N14** | Uploads accumulated forever | Bounded by age and count. Writing the sanitiser found that `Path("..").name` returns `".."`, not `""` — the naive version would have written to the parent directory |
| **N15** | `gui --server` had no authentication | Shared token, generated when unset |

### Open, and honestly so

| # | What it is | Why it is still open |
|---|---|---|
| **D3′** | **No model-token figure for the matrix** | The environment cannot reach a vocabulary host. The workflow exists and needs a dispatch |
| **N1** | Prompt compression's success path has never run | Same host, same reason |
| **D7** | *(carried, low)* | Not reached |
| **N8** | Fidelity has no component for metadata loss | Two independent instances found; the metric is structural and a third component would be a design change, not a fix |
| **N13** | `ui.select` options cannot be mutated live | Worked around rather than understood. Still true |
| **S1–S4** | Suspicions from the Phase 6 review | Never proven or disproven |
| **—** | **No CPU OCR engine is wrapped** | The largest coverage gap in the project. `scanned.pdf` has no backend that can read it |

### Introduced this session, and found

Every one of these was in code I wrote, and none was caught by a failing test.
All five benchmark ones were caught by **reading the output**.

| # | What it was | How it surfaced |
|---|---|---|
| **1** | `allow_network` inferred from `bool(extra)` — a coincidence that happened to be right for service backends | Re-reading the code while adding a flag |
| **2** | Manifest recorded thirteen `null` versions under a field documented as "the version of every backend that took part" | Reading `manifest.json` |
| **3** | The memory column climbed 50 → 253 → 345 → 375 MiB **in row order**, because a process-tree peak inherits every earlier import | Reading `report.md` and noticing the order was the giveaway |
| **4** | The repository fixture was silently unscored — manifest key `sample_repo/`, lookup `sample_repo` — printing `n/a`, which is what an honestly unscorable fixture also prints | Cross-checking the new results against what `BENCHMARKS.md` already said. `resolve_fixture` had handled this since Phase 5 |
| **5** | `git_dirty` was always true, so the flag said nothing. Fixing it took **two attempts**: the first parsed porcelain by column and `_git` strips its output, so the first line arrived one character short | Reading the manifest again after the "fix" |
| **6** | A 19.8% saving printed as `+19.8%`, which reads as growth — the exact mirror of the Phase 1 sign bug | Reading the first generated report |
| **7** | The GUI's batch caption said "one at a time" for a whole phase after Phase 9 gave it a four-worker pool | Reading a screenshot while writing the README |
| **8** | The README's `compare` example named `pdfplumber` as most faithful, wrong since Phase 7 when `pymupdf4llm` arrived at 0.848 | Running the command instead of trusting the block |
| **9** | The first cost-vs-fidelity chart pooled every cell onto one pair of axes, so its shape came from the fixtures rather than the backends; and its slope label claimed "the cheap one is better" on two panels where every backend scores identically | Looking at the rendered PNG |
| **10** | A stray `uv run` inherited the fixture directory as its working directory and created a `.venv` and `uv.lock` **inside the corpus** | `ls`. Removed; `make_fixtures.py --check` confirms 24 files byte-for-byte, and the committed benchmark predates it |

**The pattern is worth stating plainly: nine of ten were found by looking at
output, not by a test.** The test suite is 1,552 tests and green, and it did not
catch a single one of them, because every one was a case of the code doing
exactly what it was told.

---

## 5. What I would tell whoever picks this up

**Dispatch three workflows.** They are the difference between "implemented" and
"works", and none can be run from here:

1. **`Benchmark (model tokens)`** → the token half of every table in the
   project. Actions → Benchmark → Run workflow, branch
   `phases-9-12-repairs-0d9f1n`, `commit: true`.
2. **`CI` → the `compress` and `docling` jobs** → Phase 6's success path and
   Docling's PDF path, both of which have never executed anywhere.
3. **`Release`** → builds both container images and runs the nine-cell wheel
   matrix. Needs the `v0.1.0` tag, which this session could not push.

**Do not trust a green suite as evidence that a document is right.** This
session's evidence is ten to one against. The things that caught real problems
were: running the command in the README, reading the generated report, looking
at the rendered image, and diffing new numbers against what an old document
claimed.

**The unit discipline is the thing worth preserving.** Cells are keyed by
tokenizer so a byte figure cannot land under a token heading; the run exits
non-zero if a unit produced no counts; the tables carry their unit in a
blockquote at the top. That machinery exists because Phase 7 found the two units
disagreeing by 24 points and ranking five formats differently, and it is the
part of this project most likely to be quietly removed by someone who finds it
inconvenient.

**Wrap a CPU OCR engine.** It is the one gap where the project promises
something structurally and delivers nothing: every OCR path goes through a GPU
tier that has never run, and the corpus contains a fixture specifically to make
that visible.

**Read `docs/article/CLAIMS.md` before writing anything public.** Six items in
its unverified section are things a reasonable person would assume work.
