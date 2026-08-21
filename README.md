# tokenmill

**One interface over the best open-source document, web, repo and prompt converters — with honest before/after token accounting.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

> **Status: Phase 2 — document backends.** Real document conversion works:
> PDF, DOCX, PPTX and XLSX to Markdown through five adapters, with a per-format
> preference map and a fallback chain that records which backend actually ran.
> Web and repository backends arrive in Phases 3–4, and the GUI in Phase 8. The
> suite is green on Linux, macOS and Windows across Python 3.11/3.12/3.13, and
> token counting is verified against real tiktoken and HuggingFace vocabularies
> in CI. See [`PROGRESS.md`](PROGRESS.md) for exactly where things stand,
> including which claims are CI-verified rather than locally observed, and
> [`docs/BACKENDS.md`](docs/BACKENDS.md) for what each backend gets *wrong* on
> our own fixtures. Nothing below is claimed to work until `PROGRESS.md` records
> a verification run for it.

---

## What it will be

Four input domains, one output pipeline, one measurement:

| Domain | Input | Output |
|---|---|---|
| Documents | PDF, DOCX, PPTX, XLSX, EPUB, images, audio, email, CSV/JSON/XML, ZIP | Markdown |
| Web | URL or saved HTML | Boilerplate-stripped Markdown |
| Code | Local repo path or Git URL | A single prompt-ready file |
| Text | Raw prompt or context | Compressed text (opt-in, off by default) |

Every conversion reports **tokens before → tokens after** under a tokenizer you
choose. That measurement is the product, not a side feature.

### Why this and not one of the existing tools

Every good open-source converter covers exactly one domain. MarkItDown and
Docling do documents. Trafilatura does web pages. gitingest and Repomix do
repositories. LLMLingua does prompts. No project unifies all four behind one
interface with before/after token metering and a `pip install`-able plugin
architecture — that gap is what tokenmill is for.

## Why token reduction is worth measuring

These are the numbers we consider well-supported today. They come from
[`docs/research/RESEARCH.md`](docs/research/RESEARCH.md), which cites its
sources. **They are other people's measurements, not ours.** Our own numbers
land in [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) from Phase 10, produced by
the harness in `benchmarks/` on the corpus in `tests/fixtures/`.

- **Boilerplate removal is the big win, ~70–90% on real web pages.** Cloudflare
  measured one of its own blog posts at 16,180 tokens as HTML versus 3,150 as
  Markdown (−80%); community testing of a Cloudflare docs page found 9,541 →
  1,678 (−82%); FormatArc's committed benchmark measures ~70% (−67% to −87%).
  *The saving comes overwhelmingly from stripping nav, ads and scripts — not
  from Markdown syntax itself.*
- **Serialisation format can cut tabular tokens 22–56%, with accuracy
  tradeoffs.** GetCrux measured CSV using ~56% fewer tokens than JSON; the TOON
  benchmark reports 42.6% fewer tokens than JSON at comparable accuracy on
  uniform arrays, while independent work (Matveev, arXiv:2603.03306) shows TOON
  collapsing on non-aligned nested data. Format effects are task- and
  model-dependent; measure on **your** data.
- **Prompt compression: 2–5× with LLMLingua-2, up to 20× with LLMLingua at
  <2% quality loss on RAG-style context** (Microsoft Research, EMNLP'23,
  arXiv:2310.05736). It suits redundant retrieval context and can hurt
  reasoning-heavy prompts. Off by default, and it will stay that way.
- **Keep structure, strip boilerplate.** "LLMs Understand Layout"
  (arXiv:2407.05750) reports +8–33% F1 when layout is preserved. Stripping
  Markdown syntax saves a little more and costs meaning, so tokenmill's
  destructive post-processors are opt-in.

We will not restate vendor marketing percentages as fact anywhere in this
repository. Every number in the docs either carries its source or comes from our
own committed raw results.

## Install

*(Not yet published to PyPI — that is Phase 11. Until then, install from a
clone.)*

```bash
pip install tokenmill              # core: pure Python, CPU-only, no system binary
```

```bash
pip install "tokenmill[documents]"   # + MarkItDown and Kreuzberg: Office, mail, archives
pip install "tokenmill[docling]"     # + Docling: best structure fidelity, ~5.2 GB, pulls PyTorch
```

The core install is pure Python or wheel-shipping, permissively licensed, and
takes about a second. It includes the two light PDF readers. No PyTorch, no
CUDA, no system binary. A CI job installs with no extras on every commit, on
nine OS/Python combinations, and fails the build if that ever stops being true.

## Quickstart

```console
$ tokenmill backends
id                domains    license       tier        isolation   availability
----------------  ---------  ------------  ----------  ----------  ------------
kreuzberg         documents  MIT           permissive  in-process  available
markdownify_html  web        MIT           permissive  in-process  available
markitdown        documents  MIT           permissive  in-process  available
pdfplumber        documents  MIT           permissive  in-process  available
plaintext         text       Apache-2.0    permissive  in-process  available
pypdf             documents  BSD-3-Clause  permissive  in-process  available

$ tokenmill convert report.pdf --tokenizer bytes -o report.md --show-stages
wrote report.md
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

warning:  tables.pdf is a binary format, so the before-count is its own bytes
decoded as text, not text any model would be given. The after-count is real; the
percentage between them is not a token saving
```

That transcript is real output on `tests/fixtures/tables.pdf`, measured with
`--tokenizer bytes` because the machine it was run on cannot reach tiktoken's
vocabulary host. **It is a byte count, not a token count**, and — as the warning
says — the "before" figure is the PDF's own bytes, which is not text any model
would be given. `--tokenizer o200k_base` is the default and gives real BPE
counts wherever that host is reachable.

The Markdown that came out has the fixture's 7×5 table intact, all 35 cells:

```markdown
| Backend | License | Runtime | Tables | Pages/sec |
| --- | --- | --- | --- | --- |
| markitdown | MIT | CPU | weak | 12.0 |
| docling | MIT | CPU | strong | 0.8 |
...
```

### Choosing a backend

tokenmill picks one per format, and tells you which it used. Override it when
you know better — `docs/BACKENDS.md` says when you might:

```console
$ tokenmill convert twocolumn.pdf --backend pypdf     # correct multi-column reading order
$ tokenmill convert report.docx --backend docling     # best heading and list fidelity
$ tokenmill convert deck.pptx                         # markitdown: the only one that keeps speaker notes
```

If the preferred backend is not installed, or fails on that particular file, the
next one gets a turn — and the result says so rather than quietly attributing
the measurement to a converter that never ran:

```console
$ tokenmill convert page.html --tokenizer bytes
source:   page.html
backend:  markitdown
attempts: markdownify_html (failed) -> markitdown

warning:  backend 'markdownify_html' failed and tokenmill fell back to the next
one: page.html is empty
```

`--no-fallback` turns that off. An explicit `--backend` never falls back.

Converted text goes to **stdout**, the report to **stderr**, so
`tokenmill convert page.html > page.md` writes exactly the Markdown.

```console
$ tokenmill tokens page.html                 # count without converting
$ tokenmill tokens --text "how many?"        # count a literal string
$ tokenmill tokens --list                    # what tokenizers are available
$ tokenmill convert page.html --json         # machine-readable, counts null if unmeasured
```

From Python:

```python
from tokenmill import ConvertOptions, Source, convert

result = convert(Source.from_path("page.html"), ConvertOptions(tokenizer="o200k_base"))
print(result.text)
print(result.tokens_before, "->", result.tokens_after)
```

`tokens_before` and `tokens_after` are `None` when no tokenizer could be loaded —
on an air-gapped machine, for instance, where a BPE vocabulary cannot be
downloaded. The conversion still succeeds and a warning says why. **tokenmill
never substitutes an estimate for a measurement.**

## Backends

Every licence below was verified against the **installed package metadata** when
its adapter was written, not taken from a README.

| Backend | Domain | Licence | Install | Best at | Status |
|---|---|---|---|---|---|
| `plaintext` | text | Apache-2.0 (ours) | core | passing text through | ✅ Phase 1 |
| `markdownify_html` | web | MIT | core | faithful HTML markup | ✅ Phase 1 |
| `pdfplumber` | documents | MIT | core | **PDF tables** — all 35 cells of our fixture | ✅ Phase 2 |
| `pypdf` | documents | BSD-3-Clause | core | multi-column reading order; tiny | ✅ Phase 2 |
| `markitdown` | documents | MIT | `documents` | breadth; **PPTX speaker notes** | ✅ Phase 2 |
| `kreuzberg` | documents | MIT | `documents` | speed; reading order; heading inference | ✅ Phase 2 |
| `docling` | documents | MIT | `docling` | **document structure** — headings, lists, table headers | ⚠️ Phase 2 — Office paths verified, **PDF path unverified** |
| trafilatura, readability, crawl4ai | web | Apache-2.0 / MIT | core, `web` | boilerplate extraction | Phase 3 |
| gitingest, repomix, code2prompt | repo | MIT | core, subprocess | repository ingestion | Phase 4 |
| llmlingua2 | compress | MIT | `compress` | prompt compression | Phase 6 |
| pymupdf4llm, pandoc, libreoffice | documents | **AGPL-3.0 / GPL-2.0+ / MPL-2.0** | isolated | — | Phase 7 — **subprocess only, never imported** |
| marker, mineru, olmocr, surya, deepseek-ocr | documents | GPL-3.0 / varies | install docs only | GPU tier | Phase 9 |

**What Phase 2 does not do.** None of these backends does OCR, so a scanned PDF
converts to an empty document — loudly, with a warning, never silently. That is
Phase 9. And `markdownify_html` converts HTML markup faithfully without stripping
boilerplate; the 70–90% reductions cited above are Trafilatura's job in Phase 3.

[`docs/BACKENDS.md`](docs/BACKENDS.md) documents what each backend gets **wrong**
on our fixtures, quoted from real output: pdfplumber interleaving two-column
pages, MarkItDown mis-splitting a PDF table header, Kreuzberg flattening a table
into prose. Every one of those failure modes is asserted by a test, so if an
upstream release fixes one the test fails and the documentation gets corrected.

## Tokenizers

| Id | Provider | Counts | Needs |
|---|---|---|---|
| `o200k_base` *(default)*, `cl100k_base`, `p50k_base`, `r50k_base` | tiktoken (MIT) | BPE tokens | downloads its vocabulary on first use |
| `hf:<model>` | HuggingFace `tokenizers` (Apache-2.0) | model tokens | `pip install "tokenmill[tokenizers]"`, downloads on first use |
| `bytes` | ours | **UTF-8 bytes, not model tokens** | nothing |

`bytes` exists for air-gapped machines, where no vocabulary can be downloaded
and the alternative is no measurement at all. It counts a real thing exactly,
but it is not a model tokenizer and tokenmill will not let you forget it: the
CLI prints its unit as `UTF-8 bytes` and warns that the number must not be
quoted as a token count.

### Working offline

tiktoken and HuggingFace both fetch their vocabulary the first time you use
them. On a machine that cannot reach `openaipublic.blob.core.windows.net`, warm
tiktoken's cache somewhere that can and copy it across:

```bash
# on a networked machine
TIKTOKEN_CACHE_DIR=./tiktoken-cache python -c "
import tiktoken
for name in ('o200k_base', 'cl100k_base'):
    tiktoken.get_encoding(name)
"

# then, on the offline machine
export TIKTOKEN_CACHE_DIR=/path/to/tiktoken-cache
tokenmill tokens page.html --tokenizer o200k_base
```

The cache is keyed by a SHA-1 of the download URL, and tiktoken verifies the
contents against an expected hash before use — a wrong or truncated file is
deleted and refused rather than used, so an offline cache cannot silently
produce wrong counts. (Verified: see the `PROGRESS.md` verification log.)

For HuggingFace tokenizers, point `HF_HOME` at a warmed cache and set
`HF_HUB_OFFLINE=1`.

If no tokenizer can be loaded at all, `tokenmill convert` still produces the
document with its counts marked unavailable and a warning explaining why.
`tokenmill tokens` exits non-zero, because counting is that command's entire
job.

The core install must stay light. Everything heavy lives behind extras:

| Extra | Contents | Why it is optional |
|---|---|---|
| *(default)* | tokenizers, light converters, CLI | Pure Python, CPU, permissive licences |
| `documents` | MarkItDown, Kreuzberg | Light-ish, still CPU-only; pulls pandas, lxml and onnxruntime |
| `docling` | Docling | **122 packages, about 5.2 GB**, pulls PyTorch and the CUDA runtime — kept out of core deliberately |
| `web` | Crawl4AI + Playwright | Requires a browser download |
| `compress` | LLMLingua-2, transformers | Requires a model download |
| `ocr` | pytesseract, PaddleOCR | Requires a system binary or model weights |
| `gui` | NiceGUI + FastAPI | Only needed for `tokenmill gui` |
| `heavy` | *(intentionally empty)* | Marker, MinerU, olmOCR, Surya run **out of process**; they are documented, never depended on |

## Licence tiering

Licence hygiene is an engineering constraint here, not a footnote. Every backend
adapter declares its licence, and the CLI and GUI show it.

| Tier | Rule |
|---|---|
| **Permissive** (MIT/Apache/BSD) | May be imported directly into the tokenmill process |
| **Copyleft** (AGPL/GPL — PyMuPDF4LLM, Marker, Surya, Pandoc, Firecrawl core) | **Never imported.** Invoked only via subprocess or a service boundary |
| **Non-commercial weights** (e.g. ReaderLM, CC-BY-NC-4.0) | Excluded by default; opt-in flag with a visible warning |

A CI test asserts that no copyleft package is importable from our process
namespace. See [`docs/LICENSES.md`](docs/LICENSES.md) (Phase 7).

tokenmill itself is Apache-2.0.

## Development

```bash
uv venv
uv sync --extra dev --extra fixtures --extra documents

uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=tokenmill

uv run python scripts/make_fixtures.py          # build the synthetic test corpus
uv run python scripts/make_fixtures.py --check  # prove it is reproducible
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Documentation

| Document | Contents |
|---|---|
| [`PROGRESS.md`](PROGRESS.md) | Living project state, verification log, decisions, open questions |
| [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md) | The phased build plan |
| [`docs/research/RESEARCH.md`](docs/research/RESEARCH.md) | The landscape survey this project is built on |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed, in Keep a Changelog format |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Plugin/adapter design, data model, pipeline, error taxonomy |
| [`docs/BACKENDS.md`](docs/BACKENDS.md) | Per-backend reference, including observed failure modes |
| [`docs/ADDING_A_BACKEND.md`](docs/ADDING_A_BACKEND.md) | Contributor tutorial with a complete working example |
| `docs/LICENSES.md` | Tiering rules and isolation rationale *(Phase 7)* |
| `docs/BENCHMARKS.md` | Our own measured results *(Phase 10)* |

## Non-goals

Not a RAG framework, vector store or agent runtime. Not a hosted service. Not a
wrapper around proprietary APIs. Not an OCR model trainer.

## Licence

Apache-2.0 — see [`LICENSE`](LICENSE).
