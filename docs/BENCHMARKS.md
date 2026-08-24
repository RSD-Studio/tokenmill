# Benchmarks

**Status: partial, and deliberately so.** This page starts at Phase 3 because
Phase 3's exit gate names it. The full harness — a corpus × backends × formats
matrix with wall time, peak memory and a **fidelity score against hand-labelled
ground truth** — is Phase 10, and `README.md` is right that this page is a Phase
10 deliverable. Creating it now, small, means the numbers that exist have
somewhere honest to live from the start instead of accumulating in commit
messages.

Every number here comes from running tokenmill on the generated corpus in
`tests/fixtures/`. Nothing is quoted from a vendor page. Where a figure could
not be produced in the environment that wrote this, it says so and is left
absent rather than estimated.

---

## The rule this page follows

[`benchmarks/README.md`](../benchmarks/README.md) sets it: *every number
published here must trace back to a committed raw result file*. Phase 10 builds
the harness that writes those files. Until it exists, this page carries only
numbers that are **asserted by a test in the repository**, and names the test.
That is a weaker guarantee than a committed result file and a stronger one than
a number in prose, and it is the best available before the harness lands.

The other rule, from `benchmarks/README.md` and worth repeating at the top of
any page of token savings:

> Token savings without a fidelity measurement is not a result — a converter
> that emits an empty string scores a 100% reduction.

Every reduction below is therefore reported next to what survived it.

## Units: read this before quoting anything

Two different measurements appear on this page and they are **not
interchangeable**.

| Unit | What it is | Where it comes from |
|---|---|---|
| **UTF-8 bytes** | A fact about the text. Exact, deterministic, needs no download. | `--tokenizer bytes`. Reproducible anywhere, including offline. |
| **`o200k_base` tokens** | What a model would actually be charged. | `--tokenizer o200k_base`. Needs tiktoken's vocabulary, which is a download. |

The development sandbox these adapters were written in cannot reach either
tokenizer vocabulary host — `openaipublic.blob.core.windows.net` and
`huggingface.co` are both denied by an egress policy, re-probed and still denied
on 2026-08-22. **So every figure below is in bytes**, and the figures the
literature quotes are in tokens.

They are close for English prose and they are different claims. A byte
percentage is not published as a token percentage anywhere in this repository.

## Web extraction — `boilerplate.html`

The fixture: `article.html`'s body wrapped in a cookie banner, a five-section
navigation menu repeated in the footer, two advertisement slots, a newsletter
modal, a trending rail, a social rail and two inline scripts. 12,481 bytes, of
which 4,902 characters are text a reader would see.

Measured 2026-08-22, `--tokenizer bytes`, output read rather than inferred.

| Backend | Output bytes | Byte reduction | Page text removed | Boilerplate markers left | Headings kept | Table |
|---|---|---|---|---|---|---|
| `trafilatura` | 2,854 | **−77.1%** | 41.7% | **0 of 6** | 6 of 6 | preserved |
| `readability` | 2,864 | −77.1% | 41.6% | 0 of 6 | 6 of 6 | preserved |
| `crawl4ai` | 3,394 | −72.8% | 30.8% | **3 of 6** | 6 of 6 | preserved |
| `markdownify_html` | 6,802 | −45.5% | **none; +38.7% added** | 6 of 6 | 6 of 6 | preserved |

Asserted by `tests/integration/test_web_backends.py` and
`tests/integration/test_reference_backends.py`.

### How to read that table

**The two percentage columns answer different questions, and confusing them is
the single most common error in this subject.**

*Byte reduction* counts everything that went away: HTML tags, scripts, styles
**and** page furniture. *Page text removed* counts only the share of the page's
visible text that was discarded — the navigation, the banners, the footer.

`markdownify_html` is the case that makes the distinction concrete. It removes
45.5% of the file's bytes and **zero** boilerplate: every navigation link,
the cookie banner and the footer are all still in its output, and a test asserts
they are. Its page-text figure is *negative* — it emits 38.7% more characters
than the page had visible text, because Markdown bullets, link targets and table
pipes cost something. A converter cannot score well on both columns by accident.

This is exactly the misattribution `docs/research/RESEARCH.md` Category 7
describes: *"The savings come overwhelmingly from stripping nav/ads/scripts, not
from markdown syntax itself."* On this fixture, markup removal buys 45.5% and
extraction buys a further 31.6 points on top.

### Against the published figures

`RESEARCH.md` Category 7 collects three independent measurements of HTML against
extracted Markdown:

- Cloudflare's own announcement post: 16,180 → 3,150 tokens, **−80%**;
- community testing of Cloudflare's docs: 9,541 → 1,678 tokens, **−82%**;
- FormatArc's committed benchmark: **~−70%** (−67% to −87% across reports).

Ours is **−77.1% in bytes**, inside that band and unremarkable within it. That
is the Phase 3 acceptance criterion met, in the only unit this environment can
produce.

**The `o200k_base` figure is unverified.** It is asserted by
`tests/unit/test_web_tokens_network.py`, which is `network`-marked, runs in the
blocking `tokenizers` CI job, and prints the measured number into the CI log so
it can be read out. **No token percentage will be written on this page until a
green CI run has printed one.** As of 2026-08-22 CI cannot schedule runners at
all, so that has not happened.

### The control, and the honest limit

`article.html` is the same article with nothing wrapped around it. Extraction
has almost nothing to remove there, and the saving collapses. A page that is
already mostly prose gets a small reduction and occasionally a regression, which
is `RESEARCH.md`'s own point about when this win does *not* appear.

A single synthetic fixture is not a benchmark. Its ratio of boilerplate to
article is a choice the fixture generator made, and a real news page carries
proportionally more furniture than this one does. **Do not quote −77.1% as a
general claim about the web.** It is what tokenmill does to this file. Phase 10's
corpus is what could support a general claim.

## Fidelity — what each reduction cost

**Added 2026-08-24**, when the Phase 10 fidelity scorer was brought forward
ahead of Phase 5. Every token figure on this page now has a fidelity figure
beside it, which is what `benchmarks/README.md` asks for:

> Token savings without a fidelity measurement is not a result — a converter
> that emits an empty string scores a 100% reduction.

### How to read a fidelity score

Six components, each scored against `tests/fixtures/ground_truth.json`, plus an
**unweighted mean of the components that scored**. Three rules make the numbers
readable:

- **`n/a` is not zero.** A component whose ground truth does not exist for a
  fixture scores `n/a`. `long_context.md` has no table, so scoring its table
  integrity 0.0 would claim a table was destroyed and 1.0 would claim one
  survived. Both are false statements about a document with no table in it.
- **An overall is only comparable with another built from the same
  components.** Every score names them, and so does every row below.
- **Recall and rejection are a pair.** Neither says extraction worked on its
  own. A converter that emitted only the cookie banner would score perfect
  boilerplate rejection.

### The whole corpus, tokens beside fidelity

Every installed backend against every fixture it claims, `--tokenizer bytes`,
2026-08-24. Produced by converting each fixture and scoring the output with
`tokenmill fidelity`. **Bytes, not model tokens** — see Units above.

| Fixture | Backend | Output bytes | Byte change | Fidelity | Components scored |
|---|---|---|---|---|---|
| `article.html` | `trafilatura` | 2,854 | −19.8% | 1.000 | head, content, table |
| `article.html` | `readability` | 2,864 | −19.6% | 1.000 | head, content, table |
| `article.html` | `markdownify_html` | 2,916 | −18.1% | 1.000 | head, content, table |
| `article.html` | `markitdown` | 2,864 | −19.6% | 1.000 | head, content, table |
| `article.html` | `kreuzberg` | 3,063 | −14.0% | 1.000 | head, content, table |
| `boilerplate.html` | `trafilatura` | 2,854 | **−77.1%** | **1.000** | head, content, table, boiler |
| `boilerplate.html` | `readability` | 2,864 | −77.1% | 1.000 | head, content, table, boiler |
| `boilerplate.html` | `kreuzberg` | 6,120 | −51.0% | 0.750 | head, content, table, boiler |
| `boilerplate.html` | `markitdown` | 6,713 | −46.2% | 0.750 | head, content, table, boiler |
| `boilerplate.html` | `markdownify_html` | 6,802 | −45.5% | 0.750 | head, content, table, boiler |
| `jsrendered.html` | `markitdown` | 140 | **−90.7%** | **0.000** | head, content, boiler |
| `jsrendered.html` | `trafilatura` | 140 | **−90.7%** | **0.000** | head, content, boiler |
| `jsrendered.html` | `markdownify_html` | 165 | −89.1% | 0.000 | head, content, boiler |
| `jsrendered.html` | `readability` | 167 | −89.0% | 0.000 | head, content, boiler |
| `jsrendered.html` | `kreuzberg` | 180 | −88.1% | 0.000 | head, content, boiler |
| `simple.pdf` | `kreuzberg` | 2,371 | — | 0.900 | head, content |
| `simple.pdf` | `pdfplumber` | 2,370 | — | 0.500 | head, content |
| `simple.pdf` | `pypdf` | 2,371 | — | 0.500 | head, content |
| `simple.pdf` | `markitdown` | 2,377 | — | 0.500 | head, content |
| `tables.pdf` | `pdfplumber` | 599 | — | 0.667 | head, content, table |
| `tables.pdf` | `markitdown` | 769 | — | 0.606 | head, content, table |
| `tables.pdf` | `kreuzberg` | 466 | — | 0.500 | head, content, table |
| `tables.pdf` | `pypdf` | 481 | — | 0.333 | head, content, table |
| `twocolumn.pdf` | `kreuzberg` | 4,061 | — | 0.667 | head, content, order |
| `twocolumn.pdf` | `pypdf` | 4,050 | — | 0.667 | head, content, order |
| `twocolumn.pdf` | `pdfplumber` | 4,050 | — | 0.528 | head, content, order |
| `twocolumn.pdf` | `markitdown` | 4,062 | — | 0.528 | head, content, order |
| `scanned.pdf` | all four | 0 | — | **0.000** | head, content |
| `report.docx` | `markitdown` | 3,494 | — | 0.841 | head, content, table, struct |
| `report.docx` | `kreuzberg` | 3,472 | — | 0.614 | head, content, table, struct |
| `unicode.docx` | `kreuzberg` | 1,314 | — | 1.000 | head, content |
| `unicode.docx` | `markitdown` | 1,312 | — | 0.955 | head, content |
| `deck.pptx` | `markitdown` | 753 | — | 1.000 | content |
| `deck.pptx` | `kreuzberg` | 398 | — | 1.000 | content |
| `data.xlsx` | `kreuzberg` | 664 | — | 1.000 | content |
| `data.xlsx` | `markitdown` | 675 | — | 0.667 | content |
| `sample_repo` | `gitingest` | 2,944 | — | 1.000 | content, boiler |
| `long_context.md` | `plaintext` | 79,255 | −0.0% | n/a | none |

`crawl4ai`, `docling`, `repomix` and `code2prompt` are not installed in the
environment that produced this table and have no rows. A dash in *Byte change*
means the source is a binary document or a repository, which has no comparable
before-count — see "A binary document has no before" in `docs/ARCHITECTURE.md`.

### The row that justifies the whole exercise

**`jsrendered.html` produces the largest reduction in the corpus, −90.7%, at a
fidelity of 0.000.**

The page's article is inserted by a script, so every parser-based backend gets a
placeholder and reports having saved 90% of the bytes. It saved them by losing
all of the content. That is the failure `benchmarks/README.md` names, and it is
the exact result that would have looked like the best number on this page.

The last session caught it by reading a table, and fixed the symptom: web
backends now warn when a page looks client-rendered (defect D1). A warning is
not a number, and this page is made of numbers. Now the number contradicts
itself in place.

### What the score caught that prose already said

Every one of these was already written in `docs/BACKENDS.md` as an observed
failure mode. They are now measurements, which means an upstream release that
fixes one will move a number rather than quietly making a sentence untrue.

| Claim in `BACKENDS.md` | Now reads |
|---|---|
| Kreuzberg flattens `tables.pdf` into "one run-on paragraph" | table integrity **0.00** vs pdfplumber's **1.00** |
| pypdf recovers no tables | table integrity **0.00** on `tables.pdf` |
| pdfplumber interleaves two-column pages | reading order **0.58**; pypdf and kreuzberg both **1.00** |
| Kreuzberg infers headings from PDFs | heading recall **0.80** on `simple.pdf`; every other backend **0.00** |
| Kreuzberg drops DOCX lists | structure retention **0.00** on `report.docx`; markitdown **1.00** |
| MarkItDown demotes the DOCX title | heading recall **0.36** on `report.docx` |
| MarkItDown mis-splits the PDF table header | table integrity **0.82** on `tables.pdf` |
| Every backend returns nothing for `scanned.pdf` | fidelity **0.000**, four for four |

One result was *not* in `BACKENDS.md` and came out of building the score:

- **MarkItDown escapes Markdown syntax inside XLSX cell values.** `data.xlsx`
  has a row labelled `backend_count`; MarkItDown emits it as `backend\_count`.
  That is defensible Markdown — a bare underscore can open emphasis — but it
  means a literal search of the output for the cell's own value fails, which is
  what content recall does and what a RAG pipeline would do. Kreuzberg emits it
  unescaped and scores 1.000 against MarkItDown's 0.667.

MarkItDown's blank header row on `report.docx` also showed up while the scorer
was being built, and it was **already** in `BACKENDS.md` under that backend's
failure modes. It is recorded here because it forced a rule — blank cells do not
count as recovered cells — not because it was a new finding.

### The limits of this table

- **It is bytes, not model tokens.** Both columns. See Units.
- **Fidelity is measured against a synthetic corpus of fourteen fixtures**, all
  generated by `scripts/make_fixtures.py`. It measures whether a converter
  recovers what *these* documents contain.
- **The components are unweighted.** Whether a lost table matters more than a
  lost heading depends on the document and the task, and this project does not
  have an opinion to encode.
- **A high overall is not a licence to skip reading the output.** Every number
  above was produced alongside output that was read.
- **This is not the Phase 10 harness.** These figures are reproduced by running
  the commands above, not read out of a committed result file; the key rows are
  asserted by `tests/integration/test_fidelity_backends.py`. Phase 10 replaces
  this with committed raw results, wall time and peak memory.

## Document conversion — `tables.pdf`

Measured 2026-08-21, `--tokenizer bytes`.

| Backend | Output bytes | Byte reduction | Table cells recovered |
|---|---|---|---|
| `pdfplumber` | 599 | −78.6% | **35 of 35**, as a Markdown table |
| `kreuzberg` | — | — | 0; the grid becomes one run-on paragraph |

Asserted by `tests/integration/test_document_backends.py`.

The fidelity column is the point. A backend that flattened the table would score
a *better* reduction while destroying the data that made the file worth
converting.

## Repository packing — `tests/fixtures/sample_repo`

Nine tracked files across `src/`, `tests/`, `docs/`, plus a binary blob and a
`.gitignore`d `secrets.env`. Measured 2026-08-22, `--tokenizer bytes`, all three
runtimes installed.

| Backend | Files packed | Output bytes | Wall time | Secret leaked |
|---|---|---|---|---|
| `gitingest` | 7 | 2,862 | 564 ms | no |
| `repomix` | 8 | 3,978 | 1,082 ms | no |
| `code2prompt` | 7 | 2,246 | 103 ms | no |

Asserted by `tests/integration/test_repo_backends.py`. The wall times are from
this development sandbox on a warm cache and are indicative only — repomix's
figure excludes the first-run `npx` download entirely, which dominates it.

**There is no "reduction" column, deliberately.** A repository has no
before-count: nobody hands a model the raw bytes of a directory, so there is
nothing to subtract from, and the pipeline reports no `tokens_before` for one.
The honest figure is what the pack *costs*, which is what the table shows. The
comparison that means something here is between engines on the same repository,
and that is Phase 5's `compare`.

The **fidelity column is the "secret leaked" one**, and it is the only one that
could disqualify a backend outright. All three respect `.gitignore` by default,
and a test asserts the sentinel in `secrets.env` reaches none of their output —
in both directions, since `--no-gitignore` is separately proven to let it
through, which is what shows the default is doing something.

### The token budget

| Cap | Emitted | Files dropped |
|---|---|---|
| none | 2,944 bytes | 0 |
| 5,000 bytes | 2,944 bytes | 0 (the whole pack fits) |
| 1,200 bytes | **999 bytes** | 5, each named |

Measured by reading the file, not by trusting the flag. The emitted figure
includes the truncation note, which is the part an earlier version got wrong —
see `docs/BACKENDS.md`.

## Post-processing — what each step saves, and what it costs

**Measured 2026-08-24** on `tests/fixtures/structured.md`, `--tokenizer bytes`,
each post-processor run alone and scored by `tokenmill fidelity` against the
same file's ground truth.

| Post-processor | Bytes | Change | Fidelity | What moved |
|---|---|---|---|---|
| *(source)* | 1,469 | — | 1.000 | — |
| `normalize_whitespace` **(default)** | 1,466 | −0.2% | **1.000** | nothing measurable |
| `strip_frontmatter` | 1,383 | −5.9% | 1.000 | see the caveat below |
| `aggressive_whitespace` | 1,464 | −0.3% | 1.000 | hard breaks, padding |
| `dedupe_blocks` | 1,302 | **−11.4%** | **1.000** | one genuinely repeated paragraph |
| `normalize_headings` | 1,465 | −0.3% | **0.750** | every heading re-ranked |
| `links --links reference` | 1,477 | **+0.5%** | 1.000 | targets moved to definitions |
| `links --images alt --links strip` | 1,390 | −5.4% | 0.955 | 3 link targets gone |
| **all destructive processors** | 1,128 | **−23.2%** | **0.705** | — |

### Four things in that table worth reading twice

**`dedupe_blocks` is the only large saving that costs nothing measurable.**
−11.4% at fidelity 1.000, because the block it removed was a genuine verbatim
repeat. It is still destructive and still off by default: a repeat can be
deliberate, and no metric can tell the difference.

**`links --links reference` makes the document bigger.** +0.5%, because no
target in that fixture appears twice, so every URL still costs its full length
*and* gains a `[n]` label. Reference mode saves only when a target repeats. It
is in the toolkit because a user should be able to measure that on their own
document, not because it is a win.

**`normalize_headings` scores 0.750 while deleting nothing.** Every heading is
still there; they are all one rank different from the source, and the ground
truth records the source's levels. The score's detail line says so —
`0 of 3 headings recovered at the expected level; 3 present as headings at a
different level` — which is a different statement from three headings having
vanished, and the scorer distinguishes them for exactly this case.

**`strip_frontmatter` scores 1.000 and that is a limit of the metric, not a
clean bill of health.** It removed a title, a tag list and a draft flag, and no
component tracks front matter. A fidelity score of 1.000 means *nothing ground
truth asked about was lost*, which is not the same as *nothing was lost*.

### On real converter output, the whitespace processors do almost nothing

| Fixture | Backend | Base | `aggressive_whitespace` | `dedupe_blocks` |
|---|---|---|---|---|
| `twocolumn.pdf` | `pdfplumber` | 4,050 | 4,050 (+0.0%) | 4,050 (+0.0%) |
| `report.docx` | `markitdown` | 3,494 | 3,491 (−0.1%) | 3,205 (**−8.3%**) |
| `boilerplate.html` | `markdownify_html` | 6,802 | 6,802 (+0.0%) | 6,802 (+0.0%) |

This is reported because it is unflattering and because it is the useful
finding. **`aggressive_whitespace` is close to worthless on this corpus**: the
converters already emit tidy Markdown and `normalize_whitespace` runs before it,
so there is almost no padding left to remove. It earns its place on
hand-written or scraped input, not on output from the backends here — and the
honest recommendation is to measure it on your own documents before enabling it.

`dedupe_blocks` finds real redundancy where real redundancy exists
(`report.docx` repeats a "detail" paragraph per section) and correctly finds
none where there is none.

## Serialisation formats — the same table, five ways

**Measured 2026-08-24**, `--tokenizer bytes`, the 6×5 table from `tables.pdf` as
recovered by `pdfplumber`. Every figure below equals `wc -c` on the file
`tokenmill compare --write` produced, and a test asserts that equality.

| Format | Bytes | vs cheapest | vs JSON |
|---|---|---|---|
| `csv` | **216** | base | **−60%** |
| `toon` | 240 | +11% | **−56%** |
| `markdown` | 332 | +54% | −39% |
| `keyvalue` | 456 | +111% | −16% |
| `json` | 543 | +151% | base |

Reproduce with:

```console
$ tokenmill compare tests/fixtures/tables.pdf --backends pdfplumber \
      --formats markdown,csv,toon,json,keyvalue --tokenizer bytes
```

### How these compare to the published figures

`RESEARCH.md` Category 7 collects the defensible measurements. Ours land beside
them, in bytes:

| Claim | Source | Ours (bytes) |
|---|---|---|
| CSV uses ~56% fewer tokens than JSON | GetCrux, 10,000 tabular questions | **−60%** |
| TOON uses 42.6% fewer tokens than JSON | the TOON repo's own benchmark | **−56%** |
| TOON uses 22% fewer than JSON on aligned data | Matveev, arXiv:2603.03306 | −56% |

**Do not read that as confirmation.** Three reasons, and all three matter:

1. **These are bytes.** The published figures are model tokens. A byte
   percentage is not a token percentage — see Units at the top of this page.
2. **One 6×5 table is not a corpus.** TOON's advantage comes from declaring the
   field names once instead of per row, so it *grows* with row count and
   vanishes at one row. A wider or shallower table moves this number a lot.
3. **The comparison is only fair because of a rule that had to be built.** A
   cell is written as a bare number exactly when that renders back to the
   identical string, so `9.99` is a number in JSON and TOON while `05` stays a
   quoted string in both. Without that rule, JSON and TOON would quote what CSV
   writes bare and CSV would have won on a technicality.

### The trade-off these numbers do not show

Cheapest is not best, and `RESEARCH.md` Category 7 is unusually clear about it:

- **CSV is cheapest here and scored among the *weakest* on comprehension** in
  ImprovingAgents' eleven-format test (~44.3%) — while GetCrux measured it as
  both cheaper *and* more accurate than JSON. The two results disagree, and the
  honest summary is that format effect is task- and model-dependent.
- **Key-value is the most expensive format on this page and topped that same
  eleven-format test** at ~60.7% accuracy, about 16 points ahead of CSV. It is
  in the toolkit for that reason.
- **TOON's wins are narrow.** Matveev (arXiv:2603.03306) finds that as structure
  moves from aligned to non-aligned, *"TOON performance collapses"* — 0%
  one-shot accuracy on a nested company case. tokenmill's encoder implements the
  aligned tabular form only and refuses the rest, which is the shape the
  evidence supports.
- **Stripping structure entirely saves a little more and costs accuracy.** "LLMs
  Understand Layout" (arXiv:2407.05750) measures **+8–33% F1** when layout is
  preserved.

**The rule this project follows, from `RESEARCH.md` Category 7: keep structure,
strip boilerplate.** That is why the default post-processing chain is exactly
one non-destructive step, why every format encoder is lossless, and why the
cheapest option is never the recommended one on any page here.

## What is not measured yet, and why

- **Model tokens for anything.** See "Units" above. CI-only until the egress
  policy changes.
- **Wall time and peak memory.** Recorded ad hoc in `PROGRESS.md`; not
  systematically, and the numbers in this sandbox would not transfer.
- ~~**Fidelity as a score.**~~ **Done**, ahead of Phase 5 — see "Fidelity" above.
  What remains for Phase 10 is the harness around it: wall time, peak memory and
  committed raw result files.
- ~~**Serialisation formats.**~~ **Done** — see "Serialisation formats" above.
  What is still not measured is any of it **in model tokens**, which is the unit
  the published comparisons use and the one this environment cannot produce.
- **Accuracy.** Every trade-off named on this page is cited from
  `RESEARCH.md`, not measured here. tokenmill measures cost and fidelity to
  ground truth; whether a model answers better from CSV or from key-value is a
  question this project does not have the apparatus to answer, and it should
  not be read as though it did.
