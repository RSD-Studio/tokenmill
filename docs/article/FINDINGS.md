# What surprised us

Five things the benchmark said that we did not expect, in descending order of
how much they change what you would do. Every one is checkable against
[`benchmarks/results/2026-08-27/`](../../benchmarks/results/2026-08-27/); the
numbers are in [`TABLES.md`](TABLES.md) and their provenance is in
[`CLAIMS.md`](CLAIMS.md).

---

## 1. There are two opposite regimes, and which one you are in depends on the input

This is the finding. The project was built around a thesis — *the cheapest
converter is usually the one that destroyed the most* — and the data says that
is true for documents and **backwards for web pages**.

**On PDFs, cheap and faithful are opposed.** `tables.pdf`: `pypdf` produces the
smallest useful output, 481 bytes, at fidelity 0.333. `pymupdf4llm` produces
553 at 0.848. The 15% extra is the table. Pay more, get more.

**On web pages, cheap and faithful are the same thing.** `boilerplate.html`:
`trafilatura` and `readability` produce **2,854 bytes at fidelity 1.000**, while
`pandoc` produces **7,346 at 0.750**. The expensive output is the *worse* one.
It is 2.6× the size and it scores lower, because the extra bytes are the
navigation menu and keeping the navigation menu is what costs the
`boilerplate_rejection` component.

The mechanism is obvious once stated and we did not state it in advance. A PDF
extractor's job is *recovering* structure that the format threw away, so doing
less work means having less. A web extractor's job is *discarding* structure
that the format kept, so doing less work means keeping more. Same word,
"cheaper", opposite consequences.

**What it changes:** any advice of the form "prefer the faithful backend, it is
worth the cost" is wrong for half the corpus. The right advice is: on documents,
buy fidelity; on web pages, the aggressive extractor is free.

---

## 2. The largest saving in the corpus is a cell that extracted nothing

`jsrendered.html` through `trafilatura`: **−90.7%**, the biggest reduction
anywhere in 63 cells. Fidelity **0.000**. The page's article is inserted by a
script and was never in the response, so the converter honestly reported saving
90% of bytes that were navigation and boilerplate around an empty hole.

All six HTML backends do it, at −85.1% to −90.7%, all at 0.000.

We expected this fixture to be a demonstration. We did not expect it to top the
leaderboard, and the fact that it does is a better argument for the fidelity
column than anything we wrote about it in advance. **A tool that sorted this
table by saving would recommend the empty string.**

The near miss worth admitting: `scanned.pdf` does the same thing more quietly.
Four backends "succeed" with an empty string — a 100% reduction — and only
`pymupdf4llm` calls it a failure and says to try OCR.

---

## 3. LibreOffice is last on every axis, and it is in the registry's preference order

| `report.docx` | Fidelity | Median | Added RSS |
|---|---|---|---|
| `markitdown` | 0.841 | 346 ms | 0 MiB |
| `pandoc` | 0.841 | 167 ms | 125 MiB |
| `kreuzberg` | 0.614 | 7 ms | 0 MiB |
| **`libreoffice`** | **0.375** | **1,466 ms** | **263 MiB** |

Worst fidelity, slowest, most memory, on both `.docx` fixtures. It also fails
outright on `data.xlsx` and `deck.pptx` in the benchmark container — exiting 0
having written nothing, which is the failure mode its adapter had to be hardened
against.

We had it in the preference chain because it converts formats nothing else in
the core install will, and that remains the right reason to keep it. But nobody
had put its quality and its cost in the same table before, and the honest
summary is: **LibreOffice's value here is format coverage, not conversion
quality.** `docs/BACKENDS.md` says so now.

---

## 4. Five backends produced output within half a percent of each other and were not remotely equivalent

`twocolumn.pdf`: 4,050 / 4,050 / 4,061 / 4,062 / 4,069 bytes. A **0.47%**
spread. On a size-only comparison this is a five-way tie and you would pick the
fastest.

Fidelity: 0.528, 0.528, 0.667, 0.667, **0.972**. The difference is whether the
two columns interleave — whether the output reads as two columns of prose or as
alternating half-sentences.

**The cost column cannot see this at all.** Not "sees it weakly": the ordering
it produces is uncorrelated with the thing that matters. This is the single
cleanest illustration of why the fidelity axis exists, and it came out of the
data rather than out of the design.

---

## 5. Parallelising the batch queue made the headline workload slower

Phase 9 fixed a genuine bug — process-global state mutated without a lock — and
the fix unlocked a thread pool. The obvious expectation is that four workers
beat one.

| Batch (12 files, 4 cores, median of 5) | Serial | 4 workers | |
|---|---|---|---|
| In-process backends, auto-selected | 1.13 s | 1.25 s | **0.91×** |
| `pymupdf4llm` (separate interpreter each) | 14.59 s | 9.50 s | 1.54× |
| `pandoc` + `libreoffice` (real external programs) | 11.89 s | 3.82 s | **3.12×** |

The GIL explains both ends: an in-process backend parsing a PDF holds it, so
threads contend and overlap nothing; a subprocess backend sits in `wait()` with
the GIL released, so four really do run at once.

The default is still 4, which is a judgement rather than a measurement: it costs
9% of 1.13 s on the cheapest workload and saves 8 seconds on the expensive one.
Nobody notices the first and everybody notices the second.

**Why this is in a list of surprises:** the interesting part is not the number,
it is that we published it. A performance change measured after the fact, that
turns out to be a regression on the workload we had been quoting, is exactly the
result that quietly does not get written up.

---

## What did not surprise us, and should be said anyway

- **Boilerplate is the whole web-extraction story.** `article.html` (little
  boilerplate) saves 13.7–19.8% across every backend. `boilerplate.html` saves
  41.1–77.1%. The tool did not change; the page did. Any single headline
  percentage for "converting web pages" is a statement about somebody's
  fixture.
- **The out-of-process boundary is not free**: about 250 MiB, consistently,
  across `libreoffice`, `repomix` and `pymupdf4llm`. Worth it for a licence
  boundary, worth knowing before you run four at once.
- **The two units really do disagree**, and it was measured before this run
  rather than discovered by it: 24 points between bytes and `o200k_base` on
  tabular data, and a different ranking of five serialisation formats.

## What we still cannot say

Nothing here is in model tokens; nothing here involves a GPU backend, because
none has ever run; nothing here says whether a model *answers better* from one
output than another. [`CLAIMS.md`](CLAIMS.md) §3 is the full list, and it is
long enough to be worth reading before quoting any of §1.
