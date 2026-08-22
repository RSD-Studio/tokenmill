# Backends

**Status:** current as of Phase 4. Every backend described here exists and is
installed by `pip install tokenmill` or one of its extras.

This is the document that keeps the project honest about the tools it wraps.
Every failure mode below was **observed on our own fixture corpus** and is
quoted from real output — none of it is inferred from a README or a benchmark
someone else ran. Where a backend is bad at something, this page says so, and
`tests/integration/test_document_backends.py` asserts it, so that when an
upstream release fixes it the test fails and this page gets corrected rather
than quietly becoming a lie about a tool that has since improved.

`CONTRIBUTING.md` rule 5 is what this page implements: *a wrapper that hides a
bad converter is worse than no wrapper*.

---

## The corpus these observations come from

`tests/fixtures/`, built by `scripts/make_fixtures.py`. Nothing is downloaded;
every file is generated, so the observations are reproducible by anyone.

| Fixture | What it is for |
|---|---|
| `simple.pdf` | Baseline digital PDF, 2 pages, four section headings |
| `tables.pdf` | One 7×5 grid — header plus six rows, **35 cells** |
| `twocolumn.pdf` | Two columns, with `ORDERMARK 01`…`12` encoding correct reading order |
| `scanned.pdf` | `simple.pdf` rasterised: **no text layer at all**, by design |
| `corrupt.pdf` | Truncated: keeps `%PDF-`, has no `%%EOF` |
| `report.docx` | Title + five H1 + four H2, bullet list, numbered list with one nested item, 4×3 table |
| `unicode.docx` | Ten scripts including RTL, CJK, a ZWJ emoji family and a flag |
| `deck.pptx` | Five slides, speaker notes on four of them |
| `data.xlsx` | Three named sheets, one `AVERAGE` formula |
| `article.html` | The clean article: the extraction baseline, no boilerplate |
| `boilerplate.html` | The same article body wrapped in nav, ads, banners and a footer. 12,481 bytes, 4,902 characters of visible text |
| `jsrendered.html` | A page whose article is inserted by a script. Parsers see a placeholder; a browser sees the article |
| `sample_repo/` | A real git repository: 9 tracked files across `src/`, `tests/`, `docs/`, a binary blob, and a `.gitignore`d `secrets.env` whose sentinel string must never reach a model |

---

## At a glance

| Backend | Install | License | Tier | Best at | Worst at |
|---|---|---|---|---|---|
| [`pdfplumber`](#pdfplumber) | core | MIT | permissive | PDF tables | multi-column reading order |
| [`pypdf`](#pypdf) | core | BSD-3-Clause | permissive | reading order, tiny footprint | no tables, no headings |
| [`markitdown`](#markitdown) | `documents` | MIT | permissive | breadth; PPTX speaker notes | PDF layout, DOCX title |
| [`kreuzberg`](#kreuzberg) | `documents` | MIT | permissive | speed, reading order, heading inference | destroys PDF tables, drops lists |
| [`docling`](#docling) | `docling` | MIT | permissive | document structure | 5.2 GB; PDF needs a model download |
| [`trafilatura`](#trafilatura) | core | Apache-2.0 | permissive | extracting an article from a web page | short pages; it silently stops extracting |
| [`readability`](#readability) | `web` | Apache-2.0 | permissive | a second, independent extraction | pages that are mostly links |
| [`crawl4ai`](#crawl4ai) | `crawl4ai` | Apache-2.0 | permissive | pages that need JavaScript | weak extraction; refuses small SPA shells; 677 MB |
| [`gitingest`](#gitingest) | `repo` | MIT | permissive | packing a repository with no external runtime | pulls a web-service stack; reconfigures host logging |
| [`repomix`](#repomix) | binary | MIT | permissive | the category leader's output | needs Node; npx downloads it per run |
| [`code2prompt`](#code2prompt) | binary | MIT | permissive | speed on a large tree | needs a Rust toolchain to install |

Every licence above was read from the **installed package metadata** at the
moment its adapter was written, not taken from `docs/research/RESEARCH.md`. All
five are permissive, so all five may be imported into the tokenmill process.
A licence audit of docling's full 122-package resolution found **no GPL or AGPL
anywhere in the tree**.

### Which one runs by default

`tokenmill.core.preferences` ranks backends per format. The reasoning is in that
module and the evidence is below.

| Format | Order (best first) | Why |
|---|---|---|
| `pdf` | pdfplumber → kreuzberg → markitdown → pypdf → docling | Tables first, then reading order. docling last: its PDF path downloads models. |
| `docx` | docling → markitdown → kreuzberg | Only docling nests the whole hierarchy correctly. |
| `pptx` | markitdown → docling → kreuzberg | Only markitdown keeps speaker notes. |
| `xlsx` | markitdown → kreuzberg → docling | docling drops the sheet names. |
| `csv` | kreuzberg → markitdown → docling | kreuzberg renders a Markdown table. |
| `html` | trafilatura → readability → markdownify_html → markitdown → kreuzberg → docling → crawl4ai | Extraction first; the whole-page converter next; the browser last so auto-selection never starts one. |
| `url` | crawl4ai only | Every other web backend is handed the page the pipeline already fetched. |
| `repo` | gitingest → repomix → code2prompt | The one that needs no external runtime first. The other two are reachable by name. |

A backend the map does not name keeps its own declared priority, so a
third-party backend can outrank all of these without anyone editing core.

---

## `pdfplumber`

**Install:** core — `pip install tokenmill`
**License:** MIT (verified against installed metadata, 0.11.10)
**Upstream:** <https://github.com/jsvine/pdfplumber>
**Formats:** `pdf`

### What it is good at

**Tables, and this is the only backend in the tier that gets them right.** On
`tables.pdf` it recovers all 35 cells, in the right rows, with the right header:

```
| Backend | License | Runtime | Tables | Pages/sec |
| --- | --- | --- | --- | --- |
| markitdown | MIT | CPU | weak | 12.0 |
| docling | MIT | CPU | strong | 0.8 |
| pdfplumber | MIT | CPU | good | 3.4 |
| pypdf | BSD-3 | CPU | none | 18.5 |
| pymupdf4llm | AGPL-3.0 | CPU | good | 11.1 |
| marker | GPL-3.0 | GPU | strong | 1.9 |
```

The adapter does more than call `extract_tables`. `extract_text` alone renders a
table as loose words on lines, so the adapter walks each page's detected tables
top to bottom and splices a rendered Markdown table into the position the grid
occupies, keeping the surrounding prose in document order. The introduction
above the table and the footnote below it both stay where they belong.

It is also fast and light: pure Python over `pdfminer.six` and `pypdfium2`,
wheels on every platform in the CI matrix, no system binary.

### Observed failure modes

**Multi-column reading order is wrong.** pdfplumber has no layout model and
reads a page in scan-line order. On `twocolumn.pdf` the `ORDERMARK` sentinels
come out interleaved:

```
ORDERMARK 01  08  02  09  03  10  04  11  05  12  06  07
```

and the text itself reads as nonsense that is nevertheless fluent, which is what
makes it dangerous:

```
Two Column Reading boilerplate, because it is pure cost. Keep the
structure, because it is load-bearing. And measure
Order both the token count and whether the answer is still
```

Because nothing about that output announces itself as broken, **the adapter
looks for a column gutter and warns**:

```
warning:  twocolumn.pdf looks multi-column on page(s) 1. pdfplumber has no layout
model and reads a page in scan-line order, so the columns are very likely
interleaved in this output. This is a heuristic, not a certainty — check the
text, and try --backend pypdf or --backend kreuzberg, which read columns in order
```

The detector measures the widest gap between adjacent word centres. It is
calibrated against the corpus and the thresholds sit in a real gap in the data:

| Page | Largest gutter | Verdict |
|---|---|---|
| `simple.pdf` p1 | 10.8 pt (1.8% of width) | single column |
| `simple.pdf` p2 | 9.4 pt (1.5%) | single column |
| `tables.pdf` p1 | 23.9 pt (3.9%) | single column, despite a 5-column table |
| `twocolumn.pdf` p1 | 37.8 pt (6.2%) | **two columns** |

It is a heuristic, it says so, and it changes nothing about the extraction — it
only tells the user the one thing they could not otherwise have known.

**No heading detection.** A PDF has no heading structure, and pdfplumber does
not try to infer any. `simple.pdf`'s section titles come out as plain lines.
Kreuzberg does infer headings; pdfplumber does not.

**A scanned PDF yields nothing.** `scanned.pdf` returns an empty document. The
adapter warns rather than exiting 0 in silence:

```
warning:  scanned.pdf converted to an empty document: pdfplumber found no text
layer across 2 page(s), which is what a scanned or image-only PDF looks like.
Extracting text from page images needs OCR, which tokenmill does not ship yet.
The conversion succeeded; there was simply nothing to extract.
```

OCR is Phase 9.

**A truncated PDF fails, cleanly.** `corrupt.pdf` raises
`PdfminerException: Unexpected EOF`, which the adapter maps to `CorruptSource`.

---

## `pypdf`

**Install:** core — `pip install tokenmill`
**License:** BSD-3-Clause (verified against installed metadata, 6.16.1)
**Upstream:** <https://github.com/py-pdf/pypdf>
**Formats:** `pdf`

### What it is good at

**Reading order.** On `twocolumn.pdf` it emits `ORDERMARK 01` through
`ORDERMARK 12` in ascending order, where pdfplumber interleaves them and
MarkItDown starts at 08.

Be precise about why, because it is not a promise pypdf makes: it walks the
page's text objects in the order the PDF's content stream lists them. That
matches visual order for documents produced by a layout engine that fills frames
in sequence — which covers most real PDFs, and our fixture — and will not match
for a generator that emits its content stream out of order.

It is also the smallest thing here: zero required dependencies on Python 3.11+,
which makes it the backend that still works when everything heavier has failed.
It is the last member of the PDF fallback chain for exactly that reason.

### Observed failure modes

**No tables.** On `tables.pdf` the grid comes back one cell per line:

```
Backend
License
Runtime
Tables
Pages/sec
markitdown
MIT
```

Every value survives as text; the shape does not. Use `pdfplumber` when the
shape carries the meaning.

**No headings.** Same as pdfplumber — a PDF has no heading structure and pypdf
does not infer one.

**A scanned PDF yields nothing**, with the same warning as pdfplumber.

**A truncated PDF** raises `PdfStreamError: Stream has ended unexpectedly`,
mapped to `CorruptSource`. pypdf also logs `WARNING pypdf._reader: EOF marker
not found` on the way.

**Password-protected PDFs.** Files "encrypted" only to set permission flags open
with an empty password; the adapter does that and warns that the flags were
ignored. A file needing a real password raises `CorruptSource` saying so, rather
than returning a blank document.

---

## `markitdown`

**Install:** `pip install "tokenmill[documents]"`
**License:** MIT (verified against installed metadata, 0.1.7)
**Upstream:** <https://github.com/microsoft/markitdown>
**Formats:** `pdf`, `docx`, `pptx`, `xlsx`, `xls`, `csv`, `json`, `jsonl`,
`ipynb`, `epub`, `msg`, `zip`, `html`, `htm`, `jpg`, `jpeg`, `png`, `wav`,
`mp3`, `m4a`

Plugins are disabled (`enable_plugins=False`). A backend whose output depends on
which third-party MarkItDown plugins happen to be installed could not be
described truthfully on this page.

### What it is good at

**Breadth.** It converts more formats than anything else in the tier. Reach for
it when the question is "can tokenmill open this at all".

**PPTX speaker notes — it is the only backend that keeps them.** All four notes
in `deck.pptx` come through:

```
<!-- Slide number: 2 -->
# Where Your Tokens Go
Navigation
Advertising
Cookie banners
The article you wanted

### Notes:
Open by asking the room to guess the split. It is always worse than they think.
```

**XLSX sheets, named.** One Markdown table per sheet under a heading naming it —
`## backends`, `## corpus`, `## totals` — with the numbers unaltered (`12.0`
stays `12.0`, where kreuzberg coerces it to `12`).

**Unicode.** All ten scripts in `unicode.docx` round-trip, ZWJ family sequence
and regional-indicator flag included.

**DOCX lists.** Both list types keep their markers: `* Strip navigation` and
`1. Keep headings`.

### Observed failure modes

**The PDF table header is mis-split.** On `tables.pdf` it does emit a Markdown
table, but the header row merges two columns and invents an empty one:

```
| Backend     | License  | Runtime | Tables Pages/sec |      |
| ----------- | -------- | ------- | ---------------- | ---- |
| markitdown  | MIT      | CPU     | weak             | 12.0 |
```

The six data rows are correct. So 30 of the 35 cells land in the right shape and
five do not — which is worse than useless if a consumer trusts the header.

**Multi-column reading order is wrong, and differently wrong from pdfplumber.**
On `twocolumn.pdf` it emits the second column first:

```
ORDERMARK 08  09  10  11  12  01  02  03  04  05  06  07
```

**The DOCX title is demoted to body text.** `report.docx`'s Title paragraph
becomes an ordinary line; the H1s become `#` and the H2s `##`. The hierarchy is
internally consistent but one level shallower than the document, and the title
is no longer a heading at all. docling keeps it.

**The DOCX table gets a spurious empty header row:**

```
|  |  |  |
| --- | --- | --- |
| Stage | Tokens | Delta |
| source | 16180 | - |
```

mammoth does not mark the first row as a header, so MarkItDown emits an empty
one above the real one. The real header is now a data row.

**A nested list item is flattened.** `report.docx`'s sub-item becomes `4.` in
the parent numbering, where the source has it one level down. docling restarts
it as a nested `1.`.

**Images and audio need external binaries.** MarkItDown shells out to
`exiftool` (images) and `exiftool` + `ffmpeg` (audio). Without them it returns
an **empty string and no error at all** — a silent success producing nothing.
The adapter checks `PATH` and says which binary is missing:

```
warning:  MarkItDown uses exiftool for png files and it is not on PATH; expect
little or no content. Install exiftool, or use a backend that does not need it
```

**It warns at import on some platforms.** MarkItDown pulls in `magika`, which
pulls in `onnxruntime`, which warns `Unsupported Windows version (2025server)`
the moment it loads. Under `-W error` that would fail the conversion outright,
so the adapter captures warnings raised during the import and passes them to the
user as conversion warnings instead — non-fatal, still visible.

**A scanned PDF yields nothing**, with a warning. **A truncated PDF** raises
`FileConversionException`, mapped into the taxonomy.

---

## `kreuzberg`

**Install:** `pip install "tokenmill[documents]"`
**License:** MIT (verified against installed metadata, 4.10.2)
**Upstream:** <https://github.com/Goldziher/kreuzberg>
**Formats:** `pdf`, `docx`, `pptx`, `xlsx`, `csv`, `tsv`, `rtf`, `eml`, `json`,
`xml`, `html`, `htm`, `xhtml`

Pinned `>=4.0,<5`: `RESEARCH.md` records that the successor "Xberg" v1 line moved
to Elastic-2.0 while the v4 line stayed MIT, and a resolver must not be able to
change our licence position by picking up a new major.

OCR and caching are both switched off explicitly. OCR is Phase 9, and a
converter whose behaviour depends on whether a Tesseract binary happens to be
installed could not be described on this page; caching is off because a
converter that writes to a cache directory behind the user's back makes a second
run of the same command unreproducible.

### What it is good at

**Speed and weight.** A Rust core with — as of 4.10.2 — **no required Python
dependencies at all**. It converts `report.docx` in about 30 ms where MarkItDown
takes about 790 ms.

**Reading order.** `twocolumn.pdf` comes out `ORDERMARK 01`…`12` in order.

**Heading inference on PDFs.** It emits `# Why Your Context Window Is Mostly
Navigation Menus` for `simple.pdf`, a document that has no heading structure at
all. No other backend in the tier tries.

**Tabular text.** `.csv`, `.tsv` and `.xlsx` all render as Markdown tables, with
XLSX sheets under headings naming them.

### Observed failure modes

**It destroys PDF tables.** This is the disqualifying one, and it is why
pdfplumber leads the PDF ranking. `tables.pdf` comes back as a heading followed
by one run-on paragraph:

```
## Backend License Runtime Tables Pages/sec

markitdown MIT CPU weak 12.0 docling MIT CPU strong 0.8 pdfplumber MIT CPU good
3.4 pypdf BSD-3 CPU none 18.5 pymupdf4llm AGPL-3.0 CPU good 11.1 marker GPL-3.0
GPU strong 1.9
```

Nothing is lost as *text*. Everything that made it a table is gone.

**It drops PPTX speaker notes.** All four notes in `deck.pptx` are absent. Only
MarkItDown keeps them.

**It loses both DOCX list types.** `report.docx`'s bullet and numbered items
survive as prose with no markers at all.

**It collides the DOCX title with the H1s.** Both come out as `#`, so the
document's top level and its sections are indistinguishable:

```
# Context Efficiency Report
# Where the tokens actually go
## Where the tokens actually go: detail
```

**It coerces numbers.** `data.xlsx`'s `12.0` comes back as `12`.

**A scanned PDF yields nothing**, with a warning. **A truncated PDF** raises
`ParsingError: Invalid PDF: PdfiumLibraryInternalError`, mapped to
`CorruptSource`.

**Its shipped type information is wrong.** `OutputFormat` is defined inside an
`if not TYPE_CHECKING:` block, so a type checker cannot see it, and
`disable_ocr` is missing from the `ExtractionConfig` stub although the real
initialiser accepts it. The adapter carries two narrow `type: ignore`s for this,
and `warn_unused_ignores` is on, so mypy will say when upstream fixes it.

---

## `docling`

**Install:** `pip install "tokenmill[docling]"`
**License:** MIT (verified against installed metadata, 2.121.0; `docling-core`,
`docling-parse`, `docling-ibm-models` and `docling-slim` likewise)
**Upstream:** <https://github.com/docling-project/docling>
**Formats:** `pdf`, `docx`, `pptx`, `xlsx`, `html`, `htm`, `xhtml`, `csv`,
`adoc`, `asciidoc`, `odt`, `ods`, `odp`

### Read this before installing it

`pip install docling` resolves to **122 packages and about 5.2 GB**, PyTorch and
the CUDA runtime among them. That is why it has its own extra, why it is
imported lazily, and why the `clean-core-install` CI job exists.

**Its PDF path downloads models; its Office paths do not.** This distinction
decides everything about how the backend behaves:

* DOCX, PPTX, XLSX, HTML, CSV and the OpenDocument formats go through direct
  parsers. They work fully offline, immediately, with no model.
* PDF needs the DocLayNet layout model and TableFormer, fetched from
  `huggingface.co` on first use and cached afterwards.

Because of that, docling is ranked **first for DOCX and last for PDF**.
Auto-selecting it for a PDF would start a several-hundred-megabyte download
inside a command the user thought was local. Ask for it by name instead:

```console
$ tokenmill convert report.pdf --backend docling
```

OCR is disabled. Docling's default PDF pipeline enables RapidOCR, which fetches
its own weights from `modelscope.cn` — a third host, and a second surprise
download.

### What it is good at

**Document structure, and it is the only backend here that gets the whole thing
right at once.** On `report.docx`:

```
# Context Efficiency Report
## Where the tokens actually go
### Where the tokens actually go: detail
- Strip navigation
1. Keep headings
1. Nested detail under the last item
| Stage          |   Tokens | Delta   |
|----------------|----------|---------|
| source         |    16180 | -       |
```

Three correct heading levels with the title at the top, both list types with
their markers, the sub-list restarted as a nested list rather than flattened,
and a real table header row. MarkItDown loses the title and the header row;
Kreuzberg loses the lists and collides the title with the H1s.

**Unicode.** All ten scripts in `unicode.docx` round-trip.

### Observed failure modes

**It drops PPTX speaker notes.** Same as kreuzberg; only MarkItDown keeps them.

**It drops XLSX sheet names.** `data.xlsx` comes back as three unlabelled
tables. The rows are correct and the sheets are indistinguishable, so a reader
cannot tell which table is `backends` and which is `corpus`.

**It reads its own deprecated fields.** Docling's PDF pipeline reads
`generate_table_images`, and pydantic raises a `DeprecationWarning` about it.
Under `-W error` that fails the conversion, so the adapter filters that one
message around the convert call. Nothing a user can act on.

**With no route to `huggingface.co`, PDF conversion fails** — cleanly, with an
actionable message rather than an `httpx.ProxyError` traceback:

```
error: docling could not reach the network while converting tables.pdf:
ProxyError: 403 Forbidden: caused by ProxyError: 403 Forbidden
hint:  this backend downloads a model or vocabulary on first use; run it once on
a networked machine, or choose a backend that needs no download
```

### Verification status

**The Office paths were run and their output read.** DOCX, PPTX, XLSX and the
unicode fixture all converted through the real pipeline, and the structure above
is quoted from that output.

**The PDF path is implemented but unverified.** The development sandbox's egress
proxy denies `huggingface.co`, so the layout models cannot be fetched there. The
failure path above *is* verified — that is what the sandbox produces. The
success path is not, and `PROGRESS.md` records it as unverified rather than
done. `tests/integration/test_document_backends.py::TestDoclingOnPdf` covers it
behind the `heavy` marker, and the manual-dispatch `docling` CI job runs it.

---

## `trafilatura`

**Install:** core — `pip install tokenmill`
**License:** Apache-2.0 (verified against installed metadata, 2.2.0)
**Upstream:** <https://github.com/adbar/trafilatura>
**Formats:** `html`, `htm`, `xhtml`

The default for a web page since Phase 3, and the backend the project's central
claim is measured with.

### What it is good at

**Removing the website and keeping the article.** On `boilerplate.html` it
removes **all six** of the corpus manifest's
`boilerplate_markers_must_be_absent` — the cookie banner, both advertisement
slots, the trending rail, the newsletter block and the footer copyright — while
keeping all six headings at the right level, all seven article paragraphs, and
the 7×5 summary table as a real Markdown table:

```
# Why Your Context Window Is Mostly Navigation Menus

A short look at where context windows actually go.

## Where the tokens actually go
...
## Summary table

| Backend | License | Runtime | Tables | Pages/sec |
|---|---|---|---|---|
| markitdown | MIT | CPU | weak | 12.0 |
```

12,481 bytes in, 2,854 out: **−77.1%**, in UTF-8 bytes. See
[`BENCHMARKS.md`](BENCHMARKS.md) for what that figure does and does not claim.

**It keeps structure while stripping furniture**, which is the combination
`RESEARCH.md` Category 7's rule for this repository asks for — "keep structure,
strip boilerplate", citing arXiv:2407.05750 measuring +8–33% F1 when layout
survives. An extractor that took the headings with the navigation would be
buying a better percentage with worse answers.

### Observed failure modes

**A short page gets no extraction at all, and does not say so.** Trafilatura's
`MIN_EXTRACTED_SIZE` is 250 characters. Below it, the main algorithm yields
nothing and a baseline extractor returns the page's raw text instead — with no
Markdown structure and with the navigation still in it. On a four-element page:

```
$ tokenmill convert small.html --backend trafilatura --tokenizer bytes
Nav
Title
Body text here.
```

No `# Title`, and `Nav` survives. So a short page gets neither of the two things
this backend is for, silently. This is why the CLI's own tests pin
`--backend markdownify_html`: their sample page is far under the threshold.
Asserted by
`test_a_short_page_loses_its_structure_and_keeps_its_navigation`, with
`test_a_long_enough_page_does_get_structure_and_does_lose_the_navigation` as
the contrast so the claim stays bounded.

**A heading outside the detected content region is dropped, not demoted.** An
`<h1>` that sits next to the navigation rather than inside the article is
treated as page furniture and removed with it.

**A page with no text at all is a failure, not an empty document.** Deliberate,
and the opposite of how the document tier treats a scanned PDF. A scanned PDF has
nothing for *anyone* to extract, so the backends warn and return empty. A page
trafilatura declined is a page another backend can convert in full, so failing
hands it to the chain:

```
$ tokenmill convert scriptonly.html --tokenizer bytes
attempts: trafilatura (failed) -> markdownify_html
warning:  backend 'trafilatura' failed and tokenmill fell back to the next one:
trafilatura found no main content in scriptonly.html; the page may be a link
directory, a search results page, or otherwise not an article
```

**A correction, recorded because it was written down wrongly first.** The first
version of this page said trafilatura declines a page of nothing but links. It
does not — it extracts the link text. That claim came from reasoning about what
an extractor probably does rather than from running one. The failure modes above
are what running it actually produced.

### Configuration worth knowing about

**Its own fallbacks are switched off.** Trafilatura calls out to readability and
justext when its primary algorithm is unsure, which would make this backend's
output depend on which *other* extractors happen to be installed — the same
objection that made MarkItDown run with plugins disabled. A backend whose output
depends on the environment cannot be described truthfully on this page.
tokenmill's own chain does that job visibly instead, through
`ConversionResult.attempts`.

**Links are kept.** A documentation page whose references have been deleted has
lost information. Stripping them is available deliberately, through
`--links strip`.

### A licence note in its dependency tree

trafilatura itself is Apache-2.0. `courlan`, which it requires, requires `tld`,
which is tri-licensed `MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later`. That is a
disjunction — the recipient chooses — and tokenmill takes MPL-1.1. See
[`LICENSES.md`](LICENSES.md); it is not a GPL dependency, and the explanation is
there so that grepping the tree for "GPL" finds an answer rather than an alarm.

---

## `readability`

**Install:** `pip install "tokenmill[web]"`
**License:** Apache-2.0 (verified against installed metadata, readability-lxml 0.8.4.1)
**Upstream:** <https://github.com/buriy/python-readability>
**Formats:** `html`, `htm`, `xhtml`

The Python port of the arc90/Mozilla algorithm behind Firefox's Reader View. It
returns cleaned HTML, which this adapter converts to Markdown with markdownify.

### What it is good at

**The same job as trafilatura, by an unrelated algorithm.** On
`boilerplate.html` it also removes all six boilerplate markers and keeps the
article, the headings and the table. It exists in the chain so that a page
trafilatura declines outright gets a second opinion rather than falling straight
through to the whole-page converter.

**It restores the title the algorithm discards.** readability drops the page
header, title included. The adapter puts back the title readability itself
identified — not one invented here — because a document with no title is harder
to use.

### The claim this page does not make

The obvious thing to write is that readability trades precision for recall,
which is the algorithm's general reputation. **On our fixture it does no such
thing.** Its output is byte-identical to trafilatura's apart from the spacing
inside the table's separator row (`| --- |` against `|---|`) — 2,864 characters
against 2,854.

That was written the other way round first, from reputation rather than
measurement, and corrected after running both. One fixture is not a benchmark,
so no general claim about their relative quality appears anywhere in this
repository; Phase 10's harness over a real corpus is what could support one.
`test_it_agrees_with_trafilatura_almost_exactly_on_this_page` fails if an
upstream release makes them diverge, so this section gets corrected rather than
quietly becoming false.

### Observed failure modes

**Pages that are mostly links.** The scoring is about text density and link
density, so a link directory is the shape it handles worst. It returns an empty
result rather than raising, which this adapter turns into a failure so the chain
continues.

---

## `crawl4ai`

**Install:** `pip install "tokenmill[crawl4ai]"`, **then** `playwright install chromium`
**License:** Apache-2.0 (verified against installed metadata, 0.9.2; Playwright 1.62.0 Apache-2.0)
**Upstream:** <https://github.com/unclecode/crawl4ai>
**Formats:** `html`, `htm`, `xhtml`, `url`

### Read this before installing it

`pip install crawl4ai` resolves to **94 packages and 677 MB**, measured, before
Playwright downloads a browser on top. A licence audit of all 94 found no GPL, no
AGPL and no PyTorch. It is far short of docling's 5.2 GB and far past what
belongs in a core install, so it gets its own extra — the same treatment and the
same reason.

Three constraints follow from a browser being more than a fetch:

- **It is never auto-selected.** Ranked last for every format it claims. Ask for
  it by name.
- **It requires `--allow-network`, even on a local file.** A browser executes
  whatever scripts the page carries and loads whatever they ask for, from
  anywhere. Rendering a saved HTML file can therefore reach the network, and the
  guarantee that converting a local file does not is worth more than the
  convenience.
- **Installing the package is not enough.** A missing browser is reported as an
  actionable failure with the command that fixes it.

### What it is good at

**Pages that do not exist until JavaScript runs**, which is the whole of its
contribution. On `tests/fixtures/jsrendered.html` — whose article is inserted by
a script, and whose sentinel is assembled from two halves at run time so it
appears nowhere in the file's bytes:

```
$ tokenmill convert tests/fixtures/jsrendered.html --backend crawl4ai --allow-network
# The Article That Only Exists After Hydration
This paragraph is inserted by a script and is present in no response body...
The sentinel RSD-TOKENMILL-RENDERED-9317 appears exactly once in the rendered
document and never in the source...
```

trafilatura on the same file returns the placeholder and nothing else. Both are
asserted, so the pair is the proof rather than the claim.

### Observed failure modes

**Its extraction is measurably weaker than trafilatura's.** The pruning filter
scores blocks by text and link density rather than identifying an article, so a
prose-heavy advertisement scores like prose. On `boilerplate.html` it leaves
**three of the six** markers where trafilatura leaves none:

```
Accept all cookies
SPONSORED: Cut your cloud bill by 40%
Subscribe to our newsletter
```

12,481 → 3,394 bytes, −72.8%, against trafilatura's −77.1%. Headings and the
table survive, so it is not destroying structure to get there — it simply keeps
furniture. Asserted by name, so an upstream improvement fails the test and this
paragraph gets corrected.

**It refuses small client-rendered pages as anti-bot blocking.** Its detector
inspects the **un-rendered** response body and rejects any page under 5,000
bytes whose body holds fewer than 50 characters of visible text:

```
error: crawl4ai could not render file:///.../spa.html: Blocked by anti-bot
protection: Structural: minimal_text on small page (1297 bytes, 18 chars visible)
```

A small single-page-application shell is exactly that. **So the one class of
page a browser-driving backend is uniquely able to handle is the class its own
guard rejects.** tokenmill cannot fix this from outside and surfaces it as a
typed, printable failure; the chain then offers the page to a backend that can
at least return the shell. `tests/fixtures/jsrendered.html` carries a
full-sentence placeholder specifically to stay above the threshold, with a test
on the fixture so nobody shortens it back.

**It skips the browser for `file://` URLs unless told not to.** Found by running
it: crawl4ai routes local files around the browser entirely unless
`process_in_browser` is set, so the adapter was returning a parse of the
response body while claiming to render. The adapter now sets it. Worth knowing
if you drive crawl4ai directly.

---

## `gitingest`

**Install:** `pip install "tokenmill[repo]"`
**License:** MIT (verified against installed metadata, 0.3.1)
**Upstream:** <https://github.com/coderamp-labs/gitingest>
**Formats:** `repo`

The default for a repository, because it is importable: no Node, no Rust, no
binary to find. `RESEARCH.md` Category 5 reaches the same conclusion — *"gitingest
is the best Python-native fit"*.

### What it is good at

**Packing a repository into one document with a tree and every file's contents**,
and doing it in half a second on our fixture. On `tests/fixtures/sample_repo` it
packs **7 of the 9 tracked files**:

```
Directory structure:
└── sample_repo/
    ├── README.md
    ├── pyproject.toml
    ├── docs/
    │   └── design.md
    ├── src/
    │   └── widgetlib/
    │       ├── __init__.py
    │       ├── core.py
    │       └── utils.py
    └── tests/
        └── test_core.py

================================================
FILE: README.md
================================================
# widgetlib
```

The two it leaves out are correct: `assets/logo.bin` is binary, and `.gitignore`
is a dot file. The `.gitignore`d `secrets.env` never appears at all — the
property the fixture exists to check, asserted in both directions so that
`--no-gitignore` is proven to actually let it through.

### Observed failure modes

All four were found by running it as a *library*, which is a different thing from
running it as a CLI, and none of them is about repositories.

**It validates `$GITHUB_TOKEN` before looking at the source.** `resolve_token`
falls back to the environment variable and checks its *format* unconditionally,
so a placeholder token — which CI systems and development sandboxes export
routinely — fails a purely local pack:

```
gitingest.utils.exceptions.InvalidGitHubTokenError: Invalid GitHub token format.
```

The adapter hides the variable for the duration of the call. tokenmill clones
through `git`, which uses the user's normal credential helper, so gitingest is
only ever handed a local path and has no use for a token.

**It reconfigures the host process's logging.** Importing it installs a loguru
`InterceptHandler` on the standard library's **root** logger and sets that
logger's level to `0`. Measured:

```
root handlers before: []                    level 30
root handlers after:  ['InterceptHandler']  level 0
```

Every record tokenmill logs — and every record an application embedding
tokenmill logs — is rerouted, and previously-suppressed INFO starts appearing.
The adapter snapshots and restores both.

**It logs its own progress at INFO**, eight lines per pack. Silenced with
`logger.disable("gitingest")`, which is scoped to that package.

**Its ignore rules go through pathspec's deprecated `gitwildmatch` factory**, and
that DeprecationWarning is fatal under `filterwarnings = ["error"]`. Filtered by
message, the same treatment docling's internal deprecation gets: a library's own
deprecation churn is not something a user can act on.

### Why it is in an extra rather than the core install

The plan's §1.6 lists it in `core`. It requires **starlette, pydantic, httpx and
loguru** — the stack from the FastAPI app gitingest also ships — which is 14
packages and about 10 MB on every `pip install tokenmill` for a feature most
users of a document converter never touch. Nothing there breaches rule 1; it
would simply have been weight nobody asked for.

---

## `repomix`

**Install:** `npm install -g repomix` (or let `npx` fetch it with `--allow-network`)
**License:** MIT — runs out of process, so its licence never touches ours
**Upstream:** <https://github.com/yamadashy/repomix>
**Formats:** `repo` — **subprocess isolation**

The category leader by adoption — ~26.8k stars against gitingest's ~15.3k — and
TypeScript, so it is a child process.

### What it is good at

**The most complete pack of the three.** It includes 8 files where gitingest and
code2prompt include 7, and its preamble explains its own format to whatever
reads it. It sorts files by git change frequency, so the code that moves most
ends up nearest the end of the context.

Its secret scanning is left **on**: a packing tool that helps a user paste their
AWS keys into a model is worse than one that is slightly slower.

### Observed failure modes

**Without a local install, every run is a download.** `npx` fetches the package
on first use, which is a network call inside a command that looks local. So the
adapter requires `--allow-network` when it has to go through `npx`, and does not
when `repomix` is on `PATH`:

```
$ tokenmill repo ./project --backend repomix
error: repomix is not installed, and running it through npx would download it
hint:  install Node.js, then either 'npm install -g repomix' (recommended: no
download per run) or pass --allow-network to let npx fetch it each time
```

**Its own `--token-budget` does not truncate.** It *fails* with a non-zero exit
when the pack is too big. tokenmill's `--token-budget` truncates and reports what
it dropped, in the run's own tokenizer, identically across all three engines —
the two are not the same feature and this adapter does not pass ours through as
theirs.

**It is the slowest of the three** through `npx`: about 1.1 s against
code2prompt's 0.1 s and gitingest's 0.5 s on our fixture, before the first-run
download.

---

## `code2prompt`

**Install:** `cargo install code2prompt` (needs a Rust toolchain)
**License:** MIT — runs out of process
**Upstream:** <https://github.com/mufeedvh/code2prompt>
**Formats:** `repo` — **subprocess isolation**

### What it is good at

**Speed.** 103 ms on our fixture against gitingest's 564 ms and repomix's 1,082
ms — it is Rust and it shows. It also produces the smallest pack of the three
(2,246 characters against 2,862 and 3,978), because its per-file framing is
lighter.

### Observed failure modes

**There is no wheel and no npm package.** Installing it compiles it, which needs
a Rust toolchain and a few minutes, and that is why it ranks last — not quality.
A user without one gets the command that fixes it, and gitingest packs their
repository meanwhile.

**Its section format is not what a reader of repomix's would guess.** It marks a
file with a backtick-quoted path and a colon, not `## File:`:

```
`README.md`:

```md
# widgetlib
```
```

tokenmill's first parser assumed the repomix form, and the adapter reported it
honestly rather than silently claiming the repository had no files:

```
warning:  code2prompt's Markdown format was not recognised, so the token budget
and the per-directory breakdown could not be applied. The pack itself is
complete and unmodified; this is a tokenmill parsing problem
```

That warning is the reason this was found in minutes rather than shipping as a
budget that quietly did nothing. It is still there, and it is what will catch the
next upstream format change.

---

## What every repository backend shares

These are tokenmill's, not any tool's, and they behave identically across all
three — which is the point of wrapping them at all.

**A budget that genuinely caps the output.** Whole files only, in the tool's own
emission order, never partial — half a module is worse than none, because a model
cannot tell the rest was cut. Measured on our fixture: a 1,200-byte cap produces
a 999-byte document.

**Truncation is never silent.** Every dropped file is named with what it would
have cost, in a warning, in the metadata, and **in the document itself** — the
document is the part that travels to a model, and that reader cannot ask why a
file is missing.

**The note degrades before the content does.** A file that fits is never evicted
to make room for a longer explanation of the files that did not. The full table
appears when it fits and a one-line note when it does not; the complete list is
always in the result's metadata.

**A per-directory breakdown**, on `--tree-tokens`, rolled up through every
ancestor so it answers a question about a subtree:

```
| directory     | bytes | share | files |
| ---           | ---   | ---   | ---   |
| src           | 1,425 | 54.6% | 3     |
| src/widgetlib | 1,425 | 54.6% | 3     |
| .             | 528   | 20.2% | 2     |
| tests         | 348   | 13.3% | 1     |
| docs          | 310   | 11.9% | 1     |
```

**A shallow clone for a remote URL**, removed on every exit path including
failure. `ext::` and `file://` are refused at two layers, because `ext::` makes
git execute an arbitrary command.

---

## Failure modes every backend in this tier shares

**A scanned PDF produces an empty document.** `scanned.pdf` has no text layer by
design and every backend here returns nothing for it. All of them warn; none of
them fails. Reading text off page images needs OCR, which is Phase 9.

**None of them does OCR.** Not pdfplumber, not pypdf, not MarkItDown without a
plugin, not Kreuzberg with OCR disabled, not docling with OCR disabled.

**A binary source has no "before" count, so none is printed.** Nobody hands a
model the bytes of a `.docx`, so counting them produces a figure that cannot be
subtracted from anything. A document conversion reports what the output costs
and reports the input as the size it is:

```
tokens:   3,494  (o200k_base)
size:     37.4 KiB in, no comparable before
```

There is deliberately no warning about this — it is the normal shape of a
document conversion, and a disclaimer on every one of them would train users to
skim past the block where the warnings that *do* matter live.

The before/after pair keeps its meaning where both sides really are text a model
could be given: raw HTML against extracted Markdown in Phase 3, and compression
in Phase 6. The comparison that matters for a document is between *backends* on
the same file — `tokenmill compare`, Phase 5.

---

## When the preferred backend cannot run

Selection returns a chain, not a single winner, and the pipeline walks it. Two
things can move it along:

**The preferred backend is not installed.** It is filtered out before ranking.
With MarkItDown uninstalled, `report.docx` converts through kreuzberg instead:

```console
$ uv pip uninstall markitdown
$ tokenmill convert tests/fixtures/report.docx --tokenizer bytes
source:   report.docx
backend:  kreuzberg
```

**The preferred backend fails on this particular file.** The next one gets a
turn, and the result says so:

```
attempts: markdownify_html (failed) -> markitdown
warning:  backend 'markdownify_html' failed and tokenmill fell back to the next
one: empty.html is empty
```

When every candidate fails, the error names them all:

```
error: corrupt.pdf could not be parsed: PdfStreamError: Stream has ended unexpectedly
hint:  every backend that handles this source failed: pdfplumber, kreuzberg,
markitdown, pypdf
```

An explicit `--backend` never falls back — a measurement attributed to a
converter the user did not choose is worse than an error — and `--no-fallback`
turns the chain off entirely.

---

## What is not here yet

| Backend | Why | Phase |
|---|---|---|
| llmlingua2 | Prompt compression | 6 |
| pymupdf4llm (AGPL), pandoc (GPL), libreoffice | Need the isolation layer; **never imported** | 7 |
| tesseract, paddleocr | OCR — the answer to every "empty document" warning above | 9 |
| marker, mineru, olmocr, surya, deepseek-ocr | GPU tier, out of process | 9 |
