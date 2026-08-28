# Claims, and what backs each one

**Every factual claim an article about tokenmill could make, with its evidence
or its absence.** Written so that a reader who wants to check one has somewhere
to look, and so that a writer who wants to make one that is not here knows they
are on their own.

Three provenance labels are used, and they are not interchangeable:

| Label | Means |
|---|---|
| **Measured** | Produced by this project's own code on this project's own corpus, and the raw result file is committed. Re-runnable. |
| **Cited** | Somebody else's measurement. The source is named. **Not ours, and not verified by us.** |
| **Unverified** | Something this project believes, implements, or is designed around, that **has never been executed anywhere**. Say so if you use it, or do not use it. |

The line that matters: **a Measured claim in this repository is in UTF-8 bytes,
not model tokens**, unless it explicitly says `o200k_base`. Only four token
figures exist in this whole project and all four came out of a CI log.

---

## 1. Claims about tokenmill's own measurements

### 1.1 "Stripping boilerplate from a web page saves about 77% of its bytes, at no loss of fidelity"

**Measured.** `boilerplate.html`, 12,481 → 2,854 bytes through `trafilatura`
(−77.1%), fidelity 1.000 across four scored components. `readability` gets
−77.1% at 1.000 too.
Source: `benchmarks/results/2026-08-27/results.json`. Table 1.

**The qualifier that must travel with it:** `boilerplate.html` is a *synthetic*
page built to have a lot of boilerplate. On `article.html`, which has little,
the same backend saves 19.8%. The saving is a property of the page, not of the
tool, and quoting 77% as a general figure would be dishonest.

### 1.2 "The backends that strip the most boilerplate are also the most faithful"

**Measured, and it is the finding most likely to surprise a reader.** On
`boilerplate.html`: `trafilatura` and `readability` reach fidelity **1.000** at
−77%, while `markdownify_html`, `markitdown`, `kreuzberg` and `pandoc` sit at
**0.750** at −41% to −51%. The four cheaper-scoring backends keep the
navigation, which costs them the `boilerplate_rejection` component.

**This is the opposite of the PDF result in 1.3, and both are true.** See
[`FINDINGS.md`](FINDINGS.md) §1.

### 1.3 "On PDFs, the cheapest output is routinely the least faithful"

**Measured.** On `tables.pdf`, `pypdf` emits 481 bytes at fidelity 0.333 and
`pymupdf4llm` emits 553 at 0.848. The extra 15% is the table.
Table 2.

### 1.4 "The most faithful PDF backend costs 100–230× the wall time"

**Measured, on three PDFs, on one machine.** `pymupdf4llm` against `pypdf`:
234× on `tables.pdf`, 133× on `simple.pdf`, 103× on `twocolumn.pdf`, medians of
five repeats. It also adds 280–322 MiB of resident memory where `pypdf` adds
nothing measurable.

**Qualifier:** wall time does not transfer between machines and these are 4
cores of one container. The *ratio* is the durable part; the milliseconds are
not.

### 1.5 "A reduction figure without a fidelity figure is worthless, and we can show you"

**Measured, twice over.**

- Four cells on `scanned.pdf` succeed with an empty string: a **100% reduction
  at 0.000 fidelity**. Table 3.
- All six HTML backends reduce `jsrendered.html` by **85.1% to 90.7% at 0.000
  fidelity**, because the page's content is assembled in the browser and was
  never in the response. **The largest single reduction in the corpus is a cell
  that extracted nothing.**

### 1.6 "Five backends can produce output within 0.5% of each other and differ by 0.44 in fidelity"

**Measured.** `twocolumn.pdf`: 4,050 / 4,050 / 4,061 / 4,062 / 4,069 bytes — a
0.47% spread — at fidelities 0.528, 0.528, 0.667, 0.667, 0.972. A cost-only
leaderboard calls this a five-way tie. Table 2.

### 1.7 "Running a converter out of process costs about 250 MiB"

**Measured, and read the spread.** `libreoffice` 263 MiB on both its cells,
`repomix` 279 MiB, `pymupdf4llm` 280–322 MiB. `pandoc` ranges 28–125 MiB across
seven cells against inputs from 1.5 kB to 79 kB. Table 4.

**Qualifier:** sampled every 5 ms, so every figure is a lower bound; a peak
between samples is missed.

### 1.8 "gitingest produces 22% less output than repomix, six times faster"

**Measured, at equal measured fidelity** — both score 1.000 on the two
components a packed repository has. 2,944 against 3,786 bytes; 271 ms against
1,518 ms; 0 MiB against 279 MiB. Table 5.

**Qualifier, and it matters:** two of six components is all this corpus can
score for a repository. `repomix`'s extra 842 bytes are a directory tree and
per-file metadata that nothing in the fidelity score rewards and that may be
worth paying for. This measurement cannot say whether they are.

### 1.9 "Parallelising a batch of conversions can make it slower"

**Measured.** 12 files, 4 cores, medians of five: in-process backends 1.13 s
serial → 1.25 s at four workers (**0.91×**); `pandoc` + `libreoffice` 11.89 s →
3.82 s (**3.12×**). The GIL explains both ends. `src/tokenmill/gui/batch.py`
carries the table and the reasoning.

### 1.10 "A byte count is not a token count, and we measured the gap"

**Measured in CI, in real `o200k_base` tokens.** On the 6×5 table from
`tables.pdf`: CSV saves 60.2% of JSON's **bytes** and 36.0% of its **tokens** —
a 24-point gap. TOON: 55.8% against 29.9%. And the two units do not rank the
five formats in the same order: `keyvalue` is 16% smaller than JSON in bytes and
1.8% *more expensive* in tokens.
Source: CI run 89, commit `78f7615`, asserted by
`tests/unit/test_formats_tokens_network.py`.

### 1.11 "A core install is 141 MB"

**Measured.** 40 packages, 141.2 MB of `site-packages`, from the built wheel
into a clean virtualenv. CI enforces a 250 MB ceiling on nine OS/Python cells.

### 1.12 "The whitespace post-processor saves 18% on one real cell"

**Measured, and the measurement reversed a decision.** `aggressive_whitespace`
was to be deleted unless it could justify itself. Across all fifty
backend-by-fixture cells it saves **18.3% on `tables.pdf` through `markitdown`
at unchanged fidelity** (0.606 → 0.606), because MarkItDown pads its table
columns. Ten of fifty cells save something; forty save nothing.

---

## 2. Claims about the wider field — other people's numbers

Every one of these is **Cited, not Measured**. They come from
`docs/research/RESEARCH.md`, which names its sources. Do not restate any of them
as tokenmill's finding.

| Claim | Source |
|---|---|
| Boilerplate removal saves ~70–90% on real web pages | Cloudflare measured a blog post at 16,180 tokens as HTML vs 3,150 as Markdown (−80%); community testing of a Cloudflare docs page found 9,541 → 1,678 (−82%); FormatArc's committed benchmark measures ~70% (−67% to −87%) |
| CSV uses ~56% fewer tokens than JSON for tabular data | GetCrux |
| TOON uses 42.6% fewer tokens than JSON at comparable accuracy on uniform arrays | the TOON benchmark |
| TOON collapses on non-aligned nested data | Matveev, arXiv:2603.03306 |
| LLMLingua-2 compresses 2–5×, LLMLingua up to 20× at <2% quality loss on RAG-style context | Microsoft Research, EMNLP'23, arXiv:2310.05736 |
| Preserving layout improves F1 by 8–33% | "LLMs Understand Layout", arXiv:2407.05750 |

**Our own equivalent of the first row**, so a reader can see one measured
against one cited: `boilerplate.html` through `trafilatura` is **−83.1% in real
`o200k_base` tokens** (3,716 → 629), read out of CI run 85. Inside the cited
band, on our own synthetic page.

---

## 3. Claims that must be labelled unverified

**These have never run. Anywhere.** If an article implies otherwise it is
wrong, and the repository will contradict it.

### 3.1 No model-token figure exists for the benchmark matrix

The 63-cell run is in **UTF-8 bytes**. The environment tokenmill was built in
denies `openaipublic.blob.core.windows.net` and `huggingface.co` at an egress
proxy — re-probed 2026-08-27, still `403 Forbidden`. The workflow that would
produce token figures (`.github/workflows/benchmark.yml`) is written, tested
against its own failure path, and **has never been dispatched**.

### 3.2 No GPU backend has ever converted a document

Six are implemented — `marker`, `surya`, `mineru`, `olmocr`, `deepseek_ocr`,
`dots_ocr` — and not one has produced output. No GPU on the build machine and
the weight host is denied. What *is* verified is the path a machine without a
GPU takes: each reports itself unavailable with the exact commands that would
change that, and `tokenmill doctor` distinguishes "no GPU" from "the driver is
installed and no device answered".

**Consequently there is no OCR row anywhere in the benchmark**, which also means
`scanned.pdf` — the one fixture that needs OCR — has no backend in the matrix
that can do anything with it.

### 3.3 Prompt compression's success path has never executed

The LLMLingua-2 model lives on a denied host. The refusal, error and arithmetic
paths are tested; **no compression ratio has ever been produced by this code.**

### 3.4 Neither container image has been built

There is no Docker daemon in the build environment. The `Dockerfile` is
unverified beyond its build stage.

### 3.5 Nothing has been published to PyPI

By instruction and by design.

### 3.6 Model weight licences are not verified

Every heavy adapter records `weights_licence = None` — a recorded *absence of a
verified answer*, not a claim that the weights are permissive. A model's code
licence and its weights licence are frequently different documents.

---

## 4. Things that would be reasonable to assume and are not true

- **tokenmill is not a converter.** It writes no parser. Every backend is
  somebody else's library or program, wrapped.
- **The corpus is not real documents.** Fifteen files generated by
  `scripts/make_fixtures.py`, reproducible byte-for-byte. That is what makes the
  numbers checkable and it is exactly why they are not representative. The two
  properties are the same property.
- **Fidelity is not accuracy.** It scores heading recall, content recall, table
  integrity, structure retention, boilerplate rejection and reading order
  against hand-labelled ground truth. Whether a model *answers better* from one
  output than another is a question this project has no apparatus to ask.
- **The isolation layer is not a sandbox.** A tool run out of process has the
  same filesystem and network access you do. It is a licence and language
  boundary. `docs/LICENSES.md` says this in as many words.
- **`gui --server`'s token is not authentication.** No TLS, no user accounts, no
  audit trail. It stops another machine on your LAN reading your documents. That
  is all it does.
