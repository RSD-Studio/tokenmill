# Review: Phases 0 through 8

**Date:** 2026-08-27. **Reviewer:** the session that built Phases 7 and 8.
**Supersedes:** [`REVIEW_PHASES_0_6.md`](REVIEW_PHASES_0_6.md), which stays in
the repository — its defect numbering is referenced everywhere, and a superseded
review that disappears is one nobody can check.

Same caveat as its two predecessors, and it applies as hard as ever: **I built
the work being reviewed.** Where I judge it the judgement is worth less than the
evidence beside it. Every claim below names the command or the CI run that
produced it, or is marked unverified.

---

## 1. Verdict first

**CI run 97 on this branch is green across all 25 jobs**, which is the first
time a review here could open with that sentence.

**This is also the first review written with a working CI matrix**, and that changes
what the rest of this document is worth. The previous review's opening complaint
was that nothing had been verified anywhere but one Linux box. Nine cells now
run on every push, and they found things — real ones, twice, in this session
alone, in code that was green locally.

**Three results matter more than the rest.**

**1. The project's central claim is finally in the unit the claim is about.**
Defect D3 has been open since Phase 3. From CI run 85's log:

```
BENCHMARK boilerplate.html trafilatura o200k_base: 3716 -> 629 tokens (0.8307 reduction)
```

**83.1% in real `o200k_base` tokens**, inside `RESEARCH.md`'s 70–90% band. Not
computed here, not estimated, read out of captured output.

**2. The byte figures this project has published for six phases are
optimistic, and now we know by how much.** From run 89, on the `tables.pdf`
table: CSV saves 60.2% of JSON's *bytes* and **36.0%** of its *tokens*. TOON
saves 55.8% and **29.9%**. Neither GetCrux's "~56% fewer tokens" nor the TOON
repository's own "42.6%" reproduces on our data in its own unit.

And the two units do not even rank the five formats in the same order:
`keyvalue` is 16% smaller than JSON in bytes and 1.8% *more expensive* in
tokens. **A byte figure is not a token figure**, and this is the first hard
evidence of it on our own corpus rather than a caveat on a page.

**3. The AGPL tool was worth its isolation, and it is not close.** PyMuPDF4LLM
runs in a separate interpreter, is never imported, and is **the most faithful
backend in the corpus on all three scorable PDFs** — 1.000, 0.848 and 0.972,
that last against 0.667 for the next best.

**Two things are wrong**, and neither is what the last review was worried about:

1. **Phase 6 is still amber and I could not change that.** The compressor's
   success path has still never executed. A CI job that would close it is added
   and is **itself unverified**: dispatching a workflow returns 403 for this
   integration, as it did for the previous session, so only the owner or the
   Sunday schedule can run it.
2. **The process-global state that defect D2 tracks now costs a feature.** The
   batch queue runs one conversion at a time because `Pipeline.run` cannot
   safely go on a thread pool. That is a correct decision and a real limitation,
   and it is the first time D2 has cost something a user can see.

**Recommendation: yes, start Phase 9** — with one repair first. See §7.

---

## 2. Acceptance criteria

### Phase 7 — isolation and licence enforcement

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 7.1 | A copyleft backend works via subprocess and is never imported | ✅ verified | `pymupdf4llm` converts `tables.pdf`; `sys.modules` afterwards contains none of `fitz`, `pymupdf`, `pymupdf4llm` |
| 7.2 | The licence test catches a deliberately introduced violation | ✅ **verified by watching it fail** | A real `import pymupdf4llm` inside `pypdf_pdf.py` failed **three** independent checks; reverted |
| 7.3 | Subprocess timeout and cleanup verified, including on the failure path | ✅ verified | Four tests: success, backend raises, child exits non-zero, and timeout — each asserting the workspace is gone |
| 7.4 | Every registered backend declares a licence tier | ✅ verified | Asserted over the registry |
| 7.5 | `docs/LICENSES.md` completed | ✅ verified | Tiering rules, the four enforcement checks, and what the layer is **not** |
| 7.6 | *(gate)* Licence isolation suite green in CI | ✅ verified | 21 tests |

**6 of 6.** The optional HTTP service mode is also built and tested against a
real local server, with no service backend registered — asserted, so that stays
deliberate.

### Phase 8 — the GUI

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 8.1 | Every core CLI capability reachable from the GUI | ✅ verified | 35 tests through `gui/api.py`, one class per panel |
| 8.2 | A 20-file batch runs with a responsive UI and correct aggregate totals | ✅ verified | 3.0 s; caller's thread polled 362 times while it ran; totals checked against manual summation |
| 8.3 | Backend failure surfaces as a readable, actionable message | ✅ verified, **after a fix** | The first version clipped it in a table cell; see §5 N10 |
| 8.4 | Works with only the core extra installed | ✅ verified | 16 backends listed, 7 unavailable and every one carrying a hint; `tokenmill gui` prints the install command, not a traceback |
| 8.5 | *(gate)* Batch run completed and inspected | ✅ verified | Inspected in the browser, not only in a test |
| 8.6 | *(gate)* Screenshots captured | ✅ verified | `docs/images/`, five panels |
| 8.7 | *(gate)* Core-only install renders correctly | ✅ verified | Against a real core-only virtualenv |
| 8.8 | The GUI may only call the public library API | ✅ verified | Asserted over the **import graph**, not as a habit |

**8 of 8.**

**Running total across nine phases: 46 verified, 1 partial, 4 unverified,
0 failed.** Every unverified item is Phase 6's, and every one of them traces to
`huggingface.co` being denied at this sandbox's egress proxy.

---

## 3. The whole corpus, tokens beside fidelity

Every installed backend against every fixture it claims, through the default
post-processor chain, `--tokenizer bytes`, 2026-08-27. Sorted cheapest-first
**within** each fixture, which is the only place sorting by size is safe —
because the fidelity column is right there.

| Fixture | Backend | Bytes | Change | Fidelity |
|---|---|---|---|---|
| `article.html` | `trafilatura` | 2,854 | −19.8% | 1.000 |
| `article.html` | `markitdown` | 2,864 | −19.6% | 1.000 |
| `article.html` | `readability` | 2,864 | −19.6% | 1.000 |
| `article.html` | `markdownify_html` | 2,916 | −18.1% | 1.000 |
| `article.html` | `kreuzberg` | 3,063 | −14.0% | 1.000 |
| `article.html` | `pandoc` | 3,072 | −13.7% | 1.000 |
| `boilerplate.html` | `trafilatura` | 2,854 | −77.1% | 1.000 |
| `boilerplate.html` | `readability` | 2,864 | −77.1% | 1.000 |
| `boilerplate.html` | `kreuzberg` | 6,120 | −51.0% | 0.750 |
| `boilerplate.html` | `markitdown` | 6,713 | −46.2% | 0.750 |
| `boilerplate.html` | `markdownify_html` | 6,802 | −45.5% | 0.750 |
| `boilerplate.html` | `pandoc` | 7,346 | −41.1% | 0.750 |
| `jsrendered.html` | `markitdown` | 140 | −90.7% | 0.000 |
| `jsrendered.html` | `trafilatura` | 140 | −90.7% | 0.000 |
| `jsrendered.html` | `markdownify_html` | 165 | −89.1% | 0.000 |
| `jsrendered.html` | `readability` | 167 | −89.0% | 0.000 |
| `jsrendered.html` | `kreuzberg` | 180 | −88.1% | 0.000 |
| `jsrendered.html` | `pandoc` | 225 | −85.1% | 0.000 |
| `corrupt.pdf` | `kreuzberg` | **fail** | — | n/a |
| `corrupt.pdf` | `markitdown` | **fail** | — | n/a |
| `corrupt.pdf` | `pdfplumber` | **fail** | — | n/a |
| `corrupt.pdf` | `pymupdf4llm` | **fail** | — | n/a |
| `corrupt.pdf` | `pypdf` | **fail** | — | n/a |
| `scanned.pdf` | `kreuzberg` | 0 | — | 0.000 |
| `scanned.pdf` | `markitdown` | 0 | — | 0.000 |
| `scanned.pdf` | `pdfplumber` | 0 | — | 0.000 |
| `scanned.pdf` | `pypdf` | 0 | — | 0.000 |
| `scanned.pdf` | `pymupdf4llm` | **fail** | — | n/a |
| `simple.pdf` | `pdfplumber` | 2,370 | — | 0.500 |
| `simple.pdf` | `kreuzberg` | 2,371 | — | 0.900 |
| `simple.pdf` | `pypdf` | 2,371 | — | 0.500 |
| `simple.pdf` | `markitdown` | 2,377 | — | 0.500 |
| `simple.pdf` | `pymupdf4llm` | 2,410 | — | 1.000 |
| `tables.pdf` | `kreuzberg` | 466 | — | 0.500 |
| `tables.pdf` | `pypdf` | 481 | — | 0.333 |
| `tables.pdf` | `pymupdf4llm` | 553 | — | 0.848 |
| `tables.pdf` | `pdfplumber` | 599 | — | 0.667 |
| `tables.pdf` | `markitdown` | 769 | — | 0.606 |
| `twocolumn.pdf` | `pdfplumber` | 4,050 | — | 0.528 |
| `twocolumn.pdf` | `pypdf` | 4,050 | — | 0.667 |
| `twocolumn.pdf` | `kreuzberg` | 4,061 | — | 0.667 |
| `twocolumn.pdf` | `markitdown` | 4,062 | — | 0.528 |
| `twocolumn.pdf` | `pymupdf4llm` | 4,069 | — | 0.972 |
| `report.docx` | `libreoffice` | 3,418 | — | 0.375 |
| `report.docx` | `kreuzberg` | 3,472 | — | 0.614 |
| `report.docx` | `markitdown` | 3,494 | — | 0.841 |
| `report.docx` | `pandoc` | 3,567 | — | 0.841 |
| `unicode.docx` | `libreoffice` | 1,274 | — | 0.500 |
| `unicode.docx` | `markitdown` | 1,312 | — | 0.955 |
| `unicode.docx` | `kreuzberg` | 1,314 | — | 1.000 |
| `unicode.docx` | `pandoc` | 1,327 | — | 1.000 |
| `deck.pptx` | `kreuzberg` | 398 | — | 1.000 |
| `deck.pptx` | `markitdown` | 753 | — | 1.000 |
| `deck.pptx` | `libreoffice` | **fail** | — | n/a |
| `data.xlsx` | `kreuzberg` | 664 | — | 1.000 |
| `data.xlsx` | `markitdown` | 675 | — | 0.667 |
| `data.xlsx` | `libreoffice` | **fail** | — | n/a |
| `structured.md` | `plaintext` | 1,466 | −0.2% | 1.000 |
| `structured.md` | `pandoc` | 1,609 | +9.5% | 0.977 |
| `long_context.md` | `pandoc` | 79,255 | −0.0% | n/a |
| `long_context.md` | `plaintext` | 79,255 | −0.0% | n/a |
| `sample_repo` | `gitingest` | 2,944 | — | 1.000 |
| `sample_repo` | `repomix` | 3,978 | — | 1.000 |

`docling`, `crawl4ai` and `code2prompt` are not installed here and have no rows.
`repomix` needs `--allow-network`, because `npx` downloads it; its row is with
that passed.

### What this table says that the last one could not

**The AGPL tool is the best PDF converter in the corpus, on every PDF.**

| Fixture | `pymupdf4llm` | next best | by |
|---|---|---|---|
| `simple.pdf` | **1.000** | kreuzberg 0.900 | +0.100 |
| `tables.pdf` | **0.848** | pdfplumber 0.667 | +0.181 |
| `twocolumn.pdf` | **0.972** | kreuzberg / pypdf 0.667 | **+0.305** |

`twocolumn.pdf` is the striking one. Multi-column reading order has been this
project's worst-served case since Phase 2 — every Python backend either
interleaves the columns or loses the layout, and 0.667 was the ceiling.
PyMuPDF4LLM scores 0.972 and costs 19 bytes more than the cheapest.

**That is the answer to "is it worth its isolation": yes, decisively.** It costs
a separate virtualenv, an AGPL boundary and ~1.7 s of interpreter start-up per
conversion, and it buys the only PDF backend here that reads a two-column page
properly.

**LibreOffice is the clearest illustration of the project's thesis to date.**

| Backend | `report.docx` bytes | Fidelity |
|---|---|---|
| **`libreoffice`** | **3,418** (cheapest) | **0.375** (worst) |
| `kreuzberg` | 3,472 | 0.614 |
| `markitdown` | 3,494 | **0.841** |
| `pandoc` | 3,567 | 0.841 |

The cheapest output and the worst, in the same row. A benchmark sorted by size
recommends the converter that threw away every heading and every table.

**The `jsrendered.html` row still does the job it was built for.** Six backends,
−85% to −91%, fidelity **0.000** for all six. The largest reductions in the
corpus, achieved by losing every word of the article.

---

## 4. Defects from the previous review

| # | Severity | Status |
|---|---|---|
| **D2** | medium | ⚠️ **Open, and it now costs a feature.** See below |
| **D3** | medium | ✅ **CLOSED.** The `o200k_base` figure is published, from a CI log, with the run named |
| **D4** | medium | ✅ **CLOSED.** 140.6 MB measured, a 250 MB ceiling set, and CI enforces it on nine cells |
| **D6** | medium | ⚠️ Open, untouched. `repomix --style json` is still unused |
| **D7** | low | ⚠️ Open, untouched |
| **N1** | medium | ⚠️ **Open.** Phase 6's success path has still never run; the job that would fix it is added and unverified |
| **N2** | medium | ⚠️ **Open, and now a live cost.** See below and §7 |
| **N3** | low | ✅ **CLOSED.** One pipe-table parser, with the strictness difference as an argument |
| **N4** | low | ⚠️ Open, untouched |
| **N5** | low | ⚠️ Open. `aggressive_whitespace` still has no demonstrated benefit |
| **N6** | low | ✅ **CLOSED.** `in_default_chain` is the mechanism; `destructive` is honest again |
| **N7** | low | ⚠️ Open. Timings are still single unrepeated runs |
| **N8** | low | ⚠️ **Open, with a second independent instance.** See below |
| **S1–S4** | suspicion | ⚠️ Unproven, untouched |

### D2 — the count did not rise, and it started costing something

No new process-global state was added. What changed is that Phase 8 needed to
run conversions concurrently and **could not**.

`warnings.catch_warnings` saves and restores a module-global filter list. Two
threads inside it interleave their save and restore, and the loser leaves the
process holding the other's filters — which under `filterwarnings = ["error"]`
turns a warning that should have been forwarded as a `ConversionWarning` into a
raised exception in an unrelated conversion. The gitingest adapter is worse: it
reconfigures the root logger's handlers and level.

So the batch queue is one worker thread and conversions are serialised. The
acceptance criterion asks for a responsive interface rather than for
parallelism, so it is met — but batch throughput is now bounded by a defect
rather than by the work, and that is a new fact about D2 that the last review
could not have.

**Fixing D2 properly is what unlocks parallelism**, and it is now the
highest-value item on the list.

### N8 — a second instance, found the same way

`docs/BACKENDS.md` recorded that `strip_frontmatter` scores 1.000 while deleting
a title. Phase 7 found the identical shape in a backend: Pandoc's DOCX reader
treats a Title-styled paragraph as document *metadata* and discards it, so
`report.docx` came back with "Context Efficiency Report" simply missing.

**Fidelity scored 0.841 with the title and 0.841 without it.** The metric has no
component for metadata loss, so nothing measured the decision; `--standalone`
was chosen on principle and a test now guards it. Two independent instances is
enough to say the gap is structural rather than incidental.

---

## 5. New defects

| # | Severity | Defect |
|---|---|---|
| **N9** | medium | **The isolation layer is not a sandbox, and the word "isolation" invites the opposite reading.** No resource limits, no filesystem confinement, no network namespace: a tool run through it has the user's access. Documented in three places on purpose, and still a name that oversells what it does |
| **N10** | low | **A failed backend's message was clipped in the comparison table**, losing exactly the actionable half. Found by looking at a screenshot, not by a test. Fixed; failures now render in their own wrapped block |
| **N11** | low | **The batch aggregate ratio was wrong**, summing `after` over every item and `before` over only some. Reported the corpus at **−16.7%** — a batch that appeared to have grown. Fixed, and the fix is a test |
| **N12** | low | **Two tests asserted environment-dependent answers**, passed here and failed in CI. `compare`'s verdict test read "most faithful" over whatever was installed; the Pandoc test asserted a format error that availability checking pre-empts. Both fixed; both were the same mistake |
| **N13** | low | **`ui.select` options cannot be mutated live**, so the compare file chooser is rebuilt instead. A NiceGUI wrinkle, worked around rather than understood |
| **N14** | low | **The GUI stages uploads under `~/.cache/tokenmill/uploads` and never cleans them.** A long-running `--server` instance accumulates every file anyone ever dropped on it |
| **N15** | low | **`tokenmill gui --server` has no authentication of any kind.** It warns at startup, which is not the same as being safe. Anyone who can reach the port can convert files and read the results |

**N15 deserves the loudest note.** The plan asks for `--server` for LAN and
headless use, and it exists. It binds `0.0.0.0`, has no login, no CSRF
protection and no rate limit, and the upload endpoint writes to disk. The
warning printed at startup is the only mitigation. Before anyone runs this
anywhere but a trusted network, that needs to be a real answer.

---

## 6. What CI actually caught, and what it says about the last three phases

Worth writing down, because it is the single biggest change to how this project
knows anything.

| Run | What it found | Would one Linux box have found it? |
|---|---|---|
| 87 | `npx repomix@latest` exceeding a 120 s conversion budget on Windows | **No.** Cold npm on Windows; 6.8 s here |
| 89 | The byte/token orderings disagree, and by how much | **No.** Needs a tokenizer this sandbox cannot reach |
| 90 | `PackageMetadata.__getitem__` deprecation under `-W error` on py3.12/3.13 | **No.** Passes on 3.11 |
| 90 | A test asserting a format error that availability pre-empts | **No.** Passed here *because* I had installed Pandoc to verify the adapter |

**Four for four.** The last three phases were declared complete on a green suite
that had run on one machine, and the first four CI runs against this session's
work found four defects that machine could not see. Phases 3, 4, 5 and the
fidelity slice have never had that scrutiny applied retrospectively — they are
green now, but they were written under the same blindness.

**The most uncomfortable one is run 90's Pandoc test.** It passed *because* of
something I did to verify a different thing: installing Pandoc so the adapter
could be exercised made a test that should have failed pass. A development
machine that is well-equipped for verification is, for that reason, worse at
catching this class of bug than a bare one.

---

## 7. Should Phase 9 start?

**Yes**, and the ground for it is better prepared than for any previous phase.
One repair first, and it is not large.

### Repair first

**N15 — `--server` has no authentication.** Phase 9 is the GPU tier, and the
realistic deployment for a GPU backend is *a machine that is not the user's
laptop*, reached over a network. The service adapter mode Phase 7 built assumes
exactly that. Shipping `--server` with no auth into a phase whose whole point is
remote machines is the wrong order. A shared token in a header would do; it is
an hour.

### Then Phase 9, and here is why it is ready

Phase 7 built the two things Phase 9 needs and proved both:

- **`SubprocessConverter`** with an allow-list, version probing and a workspace
  that survives the failure path. Marker and Surya are GPL; the mechanism that
  keeps them out of this process exists and has been watched catching a
  violation.
- **`ServiceConverter`**, tested against a real HTTP server, with nothing
  auto-discovered and nothing auto-started. A `docling-serve` or a Marker
  container is a subclass and a `BackendInfo`.
- **The pattern for a copyleft Python package in an environment of its own** is
  established and working, which is exactly the shape MinerU and olmOCR need.

And `compare` plus the fidelity scorer mean every heavy backend arrives with a
number rather than a claim. PyMuPDF4LLM's 0.972 on `twocolumn.pdf` is the
benchmark Marker now has to beat.

### What I would not do yet

**Do not fix D2 as part of Phase 9.** It is the highest-value item on the defect
list and it is a refactor of four adapters' warning handling, not a phase.
Doing it inside a phase that adds seven backends would mean two large changes
landing in one place.

---

## 8. What I would tell the next session

- **Run the suite twice: once with your tools installed and once without.**
  Hiding `/usr/bin/pandoc` reproduced a CI failure in sixty seconds that I had
  otherwise have waited ten minutes for. A well-equipped machine hides a whole
  class of bug.
- **Read the metadata, then read it again.** `RESEARCH.md` says PyMuPDF4LLM is
  AGPL-3.0. The package says `Dual Licensed - GNU AFFERO GPL 3.0 or Artifex
  Commercial License`, and that difference broke the licence classifier in a way
  that would have declared the flagship copyleft tool importable.
- **Look at the running thing.** Two of this session's defects — a clipped error
  message and an upload that completed and did nothing — were invisible to the
  test suite and obvious in a screenshot.
- **The unflattering measurement is still the useful one.** TOON saving 29.9%
  rather than the published 42.6% is the most valuable number in this document,
  and the byte figure that flattered it sat on the benchmarks page for four
  phases looking like confirmation.
