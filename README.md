# tokenmill

**One interface over the best open-source document, web, repo and prompt converters — with honest before/after token accounting.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

> **Status: Phase 1 — core architecture.** The plugin system, the conversion
> pipeline and the token measurement layer work end to end, proven by two
> deliberately trivial backends (`plaintext` and `markdownify_html`). Real
> document, web and repository backends arrive in Phases 2–4, and the GUI in
> Phase 8. See [`PROGRESS.md`](PROGRESS.md) for exactly where things stand,
> including what has been verified and what has only been verified in CI.
> Nothing below is claimed to work until `PROGRESS.md` records a verification
> run for it.

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

The core install pulls in 19 packages, all pure Python or wheel-shipping, all
permissively licensed, and takes about a second. No PyTorch, no CUDA, no system
binary. A CI job installs with no extras on every commit and fails the build if
that ever stops being true.

## Quickstart

```console
$ tokenmill backends
id                domains  license     tier        isolation   availability
----------------  -------  ----------  ----------  ----------  ------------
markdownify_html  web      MIT         permissive  in-process  available
plaintext         text     Apache-2.0  permissive  in-process  available

$ tokenmill convert page.html --tokenizer bytes -o page.md --show-stages
wrote page.md
source:   page.html
backend:  markdownify_html
format:   markdown
duration: 83 ms
post:     normalize_whitespace
tokens:   12,481 -> 6,802  (-45.5%, bytes)

stage                 chars   tokens  change
--------------------  ------  ------  ------
source                12,472  12,481  -
convert               6,800   6,809   -45.4%
normalize_whitespace  6,793   6,802   -0.1%
```

That transcript is real output on `tests/fixtures/boilerplate.html`, measured
with `--tokenizer bytes` because the machine it was run on cannot reach
tiktoken's vocabulary host. **It is a byte count, not a token count**, and the
45.5% is markup removal — script, style and tag characters — not boilerplate
extraction. `--tokenizer o200k_base` is the default and gives real BPE token
counts wherever that host is reachable.

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

| Backend | Domain | Licence | Tier | Install | Status |
|---|---|---|---|---|---|
| `plaintext` | text | Apache-2.0 (ours) | permissive, in-process | core | ✅ Phase 1 |
| `markdownify_html` | web | MIT | permissive, in-process | core | ✅ Phase 1 |
| markitdown, pdfplumber, pypdf, kreuzberg, docling | documents | MIT / BSD-3 | permissive | `documents`, `docling` | Phase 2 |
| trafilatura, markdownify, readability, crawl4ai | web | Apache-2.0 / MIT | permissive | core, `web` | Phase 3 |
| gitingest, repomix, code2prompt | repo | MIT | permissive; Node/Rust via subprocess | core, subprocess | Phase 4 |
| llmlingua2 | compress | MIT | permissive | `compress` | Phase 6 |
| pymupdf4llm, pandoc, libreoffice | documents | **AGPL-3.0 / GPL-2.0+ / MPL-2.0** | **copyleft — subprocess only, never imported** | isolated | Phase 7 |
| marker, mineru, olmocr, surya, deepseek-ocr | documents | GPL-3.0 / varies | GPU, out of process | install docs only | Phase 9 |

`markdownify_html` converts HTML markup faithfully; it does **not** strip
boilerplate. Navigation, cookie banners and advertisements survive it.
Boilerplate removal — and with it the 70–90% reductions cited above — is
Trafilatura's job and arrives in Phase 3. See
[`PROGRESS.md`](PROGRESS.md) for the measured Phase 1 numbers and what they do
and do not show.

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
| `documents` | MarkItDown, Kreuzberg | Light-ish, still CPU-only |
| `docling` | Docling | Pulls PyTorch — kept out of core deliberately |
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
uv sync --extra dev --extra fixtures

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
| `docs/BACKENDS.md` | Per-backend reference, including observed failure modes *(Phase 2+)* |
| [`docs/ADDING_A_BACKEND.md`](docs/ADDING_A_BACKEND.md) | Contributor tutorial with a complete working example |
| `docs/LICENSES.md` | Tiering rules and isolation rationale *(Phase 7)* |
| `docs/BENCHMARKS.md` | Our own measured results *(Phase 10)* |

## Non-goals

Not a RAG framework, vector store or agent runtime. Not a hosted service. Not a
wrapper around proprietary APIs. Not an OCR model trainer.

## Licence

Apache-2.0 — see [`LICENSE`](LICENSE).
