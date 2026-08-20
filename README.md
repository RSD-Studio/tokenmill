# tokenmill

**One interface over the best open-source document, web, repo and prompt converters — with honest before/after token accounting.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

> **Status: Phase 0 — scaffolding.** The repository installs, lints, type-checks,
> tests and generates its test corpus. It contains **no conversion logic yet**;
> the CLI and GUI arrive in Phases 1 and 8. See [`PROGRESS.md`](PROGRESS.md) for
> exactly where things stand and [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md)
> for the full build sequence. Nothing below is claimed to work until `PROGRESS.md`
> records a verification run for it.

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

*(Not yet published — Phase 11. These are the intended commands.)*

```bash
pip install tokenmill              # core: pure Python, CPU-only, no system binary
```

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
uv run mypy src/
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
| `docs/ARCHITECTURE.md` | Plugin/adapter design *(Phase 1)* |
| `docs/BACKENDS.md` | Per-backend reference, including observed failure modes *(Phase 2+)* |
| `docs/ADDING_A_BACKEND.md` | Contributor tutorial *(Phase 1)* |
| `docs/LICENSES.md` | Tiering rules and isolation rationale *(Phase 7)* |
| `docs/BENCHMARKS.md` | Our own measured results *(Phase 10)* |

## Non-goals

Not a RAG framework, vector store or agent runtime. Not a hosted service. Not a
wrapper around proprietary APIs. Not an OCR model trainer.

## Licence

Apache-2.0 — see [`LICENSE`](LICENSE).
