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

## What is not measured yet, and why

- **Model tokens for anything.** See "Units" above. CI-only until the egress
  policy changes.
- **Wall time and peak memory.** Recorded ad hoc in `PROGRESS.md`; not
  systematically, and the numbers in this sandbox would not transfer.
- **Fidelity as a score.** Today fidelity is a set of pass/fail assertions —
  markers absent, headings present, cells recovered. Turning that into a number
  comparable across backends is Phase 10.
- **Serialisation formats.** CSV, TOON and JSON encoders are Phase 5, so there
  is nothing to compare yet. `RESEARCH.md` Category 7's warning applies in
  advance: format savings carry accuracy trade-offs, TOON's wins are narrow and
  model-dependent, and structure-preserving beats maximal stripping for accuracy
  (arXiv:2407.05750 measures +8–33% F1 when layout survives). tokenmill's default
  post-processing is conservative for that reason.
