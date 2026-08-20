# The Open-Source Document / Web / Code / Prompt → Token-Efficient Text Landscape (August 2026)

## TL;DR
- **A single Python-native GUI wrapping the best open-source converters is a genuinely under-served niche worth building** — but success hinges on one architectural decision: isolate the heavy ML backends (Marker, MinerU, the VLMs) from a light pure-Python core, or you will drown in PyTorch/transformers/pydantic version conflicts.
- **Build the core as a plugin/adapter registry**: a light, always-installed MIT/Apache tier (MarkItDown, Docling, pdfplumber, Trafilatura, gitingest, Chonkie, tiktoken, LLMLingua-2, a TOON encoder) plus optional GPU "extras" and subprocess/Docker isolation for AGPL/GPL and Node/Rust tools. For the UI, choose **NiceGUI + FastAPI** (with an optional PySide6 desktop shell later), not Streamlit or Gradio.
- **Ground the repo's value claim in real numbers, not folklore.** "Markdown saves tokens" is mostly *boilerplate removal* (70–90% on real web/office docs), while *serialization format* choice for tabular data (CSV/TOON/Markdown-KV) can cut tokens 22–56% but with real, model-dependent accuracy tradeoffs. The strongest original contribution you can make is a reproducible benchmark of N converters on one messy corpus, measuring **both tokens and fidelity** — nobody has done this across all four input domains.

## Key Findings

**1. The decisive axis for a GUI wrapper is Python-API availability and dependency weight, not raw quality.** Tools split cleanly into (a) pure-Python / system-binary and cheap to bundle, and (b) PyTorch/CUDA VLM-based and expensive. You want the former in the core and the latter behind an extras install.

**2. License is a first-class engineering constraint for a bundled repo.**
- *Permissive (MIT/Apache — safe to import and bundle, commercial-friendly):* MarkItDown, Docling, PyMuPDF (base), Kreuzberg v4, Trafilatura, markdownify, Crawl4AI, pypdf, pdfplumber, pdfminer.six, olmOCR, Tesseract, PaddleOCR, dots.ocr, GOT-OCR2, Granite-Docling, LLMLingua, Repomix, gitingest, code2prompt, Chonkie, TOON, tiktoken.
- *Copyleft/viral (self-hostable but must be isolated via subprocess, not imported):* PyMuPDF/PyMuPDF4LLM (AGPL-3.0), Marker (GPL-3.0 code + RAIL weights), Surya (GPL-3.0), Firecrawl core (AGPL-3.0), omniparse (GPL-3.0), Pandoc (GPL-2.0+).
- *Watch for relicenses/edge cases:* MinerU relicensed to a more permissive license in v3.1.0 (was AGPL-3.0); the newer Kreuzberg→Xberg v1 line moved to Elastic-2.0 (v4 remains MIT); ReaderLM weights are **CC-BY-NC-4.0 (non-commercial)**.

**3. The token-efficiency evidence is real but frequently misstated in tool marketing.** The reliable, measured claims are documented in the Category 7 section below; treat vendor blog percentages skeptically and prefer the arXiv/benchmark numbers.

**4. No existing OSS project unifies all four input domains** (documents + web + code repos + prompt compression) behind one interface with before/after token measurement and a swappable-backend plugin architecture. That is precisely your differentiation.

## Details

### Category 1 — General document → Markdown converters

**Microsoft MarkItDown** — `github.com/microsoft/markitdown` — MIT, Python, ~80k+ stars. Importable library (`MarkItDown().convert()`) plus an MCP server. Converts PDF, DOCX, PPTX, XLSX, HTML, images, audio, CSV/JSON/XML, ZIP, and YouTube URLs. Light install (~250MB with all extras; no PyTorch for basic use), CPU-only, offline for most formats (image/audio OCR needs a plugin or LLM). **Weakness:** poor PDF layout/heading fidelity — it ranked near the bottom of the OpenDataLoader benchmark (~0.589 overall vs Docling's ~0.882, with a heading-hierarchy score of 0.000). Best-in-class *breadth*; excellent for Office formats. Note: it spawns external binaries (exiftool/ffmpeg), a security consideration with untrusted files.

**IBM Docling** — `github.com/docling-project/docling` — MIT, Python, ~61k stars, hosted by the LF AI & Data Foundation. Importable library + CLI + `docling-serve` API. Its unified, lossless **DoclingDocument** model exports Markdown/HTML/JSON/DocTags. Parses PDF, DOCX, PPTX, XLSX, HTML, EPUB, images, audio (ASR), and email. Uses a DocLayNet layout model + TableFormer, with an optional Granite-Docling-258M VLM (Apache-2.0). Heavier (~1GB, ~88 deps, PyTorch) but runs CPU-only acceptably. **Best table fidelity in the permissive-license tier** (~88% F1).

**Unstructured (OSS library)** — Apache-2.0 core, Python. Feature-rich but heavy; some capabilities (e.g. image extraction from Office docs) are paywalled in the hosted tier. Good ecosystem integration, dependency-heavy.

**Pandoc** — system binary (Haskell), GPL-2.0+. Universal converter (60+ formats), excellent for DOCX/LaTeX/EPUB→MD but not LLM-optimized and weak on PDF. Wrap via `pypandoc` or subprocess. Best as a fallback/utility.

**Apache Tika** — Apache-2.0, Java (JVM sidecar). Broad format detection/extraction; Python via the `tika` client. Operationally heavy.

**Kreuzberg / Xberg** — `github.com/Goldziher/kreuzberg` — MIT (v4 line); the newer Xberg v1 line is Elastic-2.0. Python with a Rust core + bindings, ~5.8k stars. Lightweight (~71MB, ~20 deps), CPU-only, async, built on Pandoc/PDFium/Tesseract. The author's own `goldziher/python-text-extraction-libs-benchmarks` (94 real-world documents) is a useful, reproducible primary source for your own benchmark.

**Extractous** — Apache-2.0, Rust core + Python bindings. Fast, lightweight, Tika-like coverage without the JVM.

**LibreOffice headless** (MPL-2.0), **python-docx/python-pptx/openpyxl** (MIT/BSD) — subprocess-wrappable Office handling and low-level building blocks for custom/fallback converters.

### Category 2 — PDF-specific extraction

**PyMuPDF4LLM** — `github.com/pymupdf/pymupdf4llm` — **AGPL-3.0** (commercial license via Artifex), Python. Wraps the MuPDF C engine; the fastest option (~0.09 sec/page), CPU-only, no GPU. `pymupdf4llm.to_markdown()`. Now ships a GNN-based Layout feature. Excellent on well-structured digital PDFs, weaker on scanned. **The AGPL license is the catch — isolate via subprocess.**

**pdfplumber** (MIT), **pypdf** (BSD), **pdfminer.six** (MIT) — pure-Python, light, CPU-only, ideal light-core members. pdfplumber has strong table extraction; no layout ML.

**Marker** — `github.com/datalab-to/marker` — **GPL-3.0** code + modified OpenRAIL-M weights (free under $2M revenue), Python, PyTorch/GPU. Excellent layout/math/table quality (~76 on olmOCR-bench; Marker 2 higher). `pip install marker-pdf`. GPU strongly recommended. Optional paid Datalab cloud runs the newer **Chandra** VLM (Apache-2.0). Heavy — extras-only backend.

**MinerU** — `github.com/opendatalab/mineru` — relicensed to a more permissive license in v3.1.0 (previously AGPL-3.0), Python. Most-starred PDF tool. Fastest on GPU (~0.21 sec/page), strong tables (0.873), strong CJK, broad hardware support (NVIDIA/AMD/Ascend/Cambricon/etc.). v3.1.0 adds native DOCX/PPTX/XLSX and the MinerU2.5-Pro VLM. No macOS. Heavy — extras backend.

**GROBID** — Apache-2.0, Java (Docker, ~20GB image). Scientific-paper-specific (TEI XML, references/citations). Niche but best-in-class for academic metadata.

**Nougat** (Meta, MIT code) — academic-PDF→Markdown VLM (equations/tables); largely superseded by olmOCR/Marker but still used. PyTorch/GPU.

**OpenDataLoader-PDF** — Apache-2.0, CPU-only, emits bounding boxes for every element, hybrid mode with docling; led a 2026 accuracy benchmark (0.907 hybrid). A strong permissive, high-accuracy, CPU option worth including.

**PaddleOCR / PP-StructureV3** (Apache-2.0), **docTR** (Apache-2.0), **table-transformer** (MIT), **Surya** (GPL-3.0) — layout/table/OCR building blocks.

### Category 3 — OCR & VLM document-to-Markdown

The 2025–2026 wave outputs Markdown/HTML directly. **Hardware note:** the VLMs below effectively need a GPU (8–24GB) for usable speed; classical engines (Tesseract, PaddleOCR, docTR, EasyOCR) run CPU-only.

**olmOCR 2** (AI2) — `github.com/allenai/olmocr` — Apache-2.0, 7B VLM, fully open (weights + data + code). ~82.4 on olmOCR-bench. Outputs Markdown + HTML tables + LaTeX. ~$200 per 1M pages on one H100. GPU required.

**DeepSeek-OCR** — `github.com/deepseek-ai/DeepSeek-OCR` — **the on-theme model**, and the single strongest "token reduction" story to feature. It performs "contexts optical compression": rendering text as an image and encoding it into a small set of vision tokens (7–20× fewer than text tokens). Per the paper (Wei, Sun & Li, arXiv:2510.18234, Oct 21 2025): *"when the number of text tokens is within 10 times that of vision tokens (i.e., a compression ratio <10×), the model can achieve decoding (OCR) precision of 97%. Even at a compression ratio of 20×, the OCR accuracy still remains at about 60%."* It directly supports the prompt "Convert the document to markdown." MoE 3B / 570M-active decoder. GPU.

**Surya** — `github.com/datalab-to/surya` — GPL-3.0, ~650M single VLM (layout + OCR + tables), 90+ languages, ~83% olmOCR-bench. GPU-friendly and small.

**Tesseract** (Apache-2.0), **PaddleOCR** (Apache-2.0), **EasyOCR** (Apache-2.0) — classical, CPU-friendly, no Markdown structure.

**dots.ocr** (MIT, ~1.7–3B, multilingual layout, strong tables), **GOT-OCR2.0** (Apache-2.0, ~580M, math/formula), **Nanonets-OCR2-3B** (structured markdown + semantic tagging), **Granite-Docling-258M** (Apache-2.0, ultra-compact VLM anchoring Docling), **PaddleOCR-VL** (~0.9B, 100+ languages), **MonkeyOCR**, and **Qwen-VL/InternVL** parsers round out the open-weight field.

### Category 4 — HTML / web → Markdown

**Trafilatura** — `github.com/adbar/trafilatura` — Apache-2.0, Python. Best-in-class content extraction (F1 ~0.945 on the ScrapingHub benchmark). `extract(output_format='markdown')`. Pure Python, CPU, offline on already-fetched HTML. Light-core member.

**html2text** (GPL-3.0) and **markdownify** (MIT) — simple HTML→MD converters; prefer markdownify for permissive licensing.

**Readability** (python-readability / readabilipy) — content extraction in the Firefox Reader View lineage.

**Crawl4AI** — `github.com/unclecode/crawl4ai` — Apache-2.0, Python. LLM-focused, Playwright-based, outputs "fit_markdown" via BM25/pruning filters, handles JS. Heavier (browser) but the best OSS Firecrawl alternative.

**Firecrawl (self-hosted)** — AGPL-3.0 core; self-hostable but the cloud tier has more features. Appendix-only for a bundled repo.

**Jina reader-lm / ReaderLM-v2** — open-**weight** small models (0.5B/1.5B; v2 is 1.5B with 512K context, HTML→MD/JSON) — but the weights are **CC-BY-NC-4.0 (non-commercial)**. Flag this clearly; do not bundle for commercial use.

**Resiliparse** (Apache-2.0), **newspaper3k/newspaper4k** (MIT/Apache), **Defuddle** (MIT), **htmlrag** — supporting extractors.

### Category 5 — Code repo → single prompt-ready file
*(Verified from live GitHub repos, August 19, 2026. Star counts are GitHub's rounded display values.)*

| Tool | URL | License | Lang | Stars | Python API? | Token counting? |
|---|---|---|---|---|---|---|
| **Repomix** | yamadashy/repomix | MIT | TypeScript | ~26.8k | No (Node CLI+lib; subprocess it) | Yes (o200k/cl100k; `--token-count-tree`, `--token-budget`) |
| **gitingest** | coderamp-labs/gitingest | MIT | Python | ~15.3k | **Yes** (`from gitingest import ingest`) | Yes (tiktoken) |
| **code2prompt** | mufeedvh/code2prompt | MIT | Rust | ~7.4k | Yes (`code2prompt-rs` SDK) | Yes |
| **GPT Repository Loader** | mpoon/gpt-repository-loader | MIT | Python | ~3.0k | CLI-only (single script) | No |
| **files-to-prompt** | simonw/files-to-prompt | Apache-2.0 | Python | ~2.8k | CLI-focused | No |
| **yek** | bodo-run/yek | MIT | Rust | ~2.4k (approx.) | No (Rust CLI) | Yes (token size limits) |
| **ai-digest** | khromov/ai-digest | MIT | TypeScript | ~679 | JS lib (not Python) | Yes (GPT+Claude stats) |

**Practical takeaway:** **gitingest** is the best Python-native fit (importable, tiktoken counts); **Repomix** is the category leader (wrap via subprocess); **code2prompt** offers a Python SDK over its Rust core.

### Category 6 — Prompt / context compression (the "optional advanced" family)

**LLMLingua / LongLLMLingua / LLMLingua-2** — `github.com/microsoft/LLMLingua` — MIT, Python, ~6.2k stars, importable (`PromptCompressor`). Microsoft Research's own project page and papers give the measured numbers:
- **LLMLingua** (Jiang et al., EMNLP'23, arXiv:2310.05736): *"achieves up to 20x compression with minimal performance loss"* — under ~2% quality drop on CoQA/HotpotQA/TriviaQA. Perplexity-based; needs a small LLM (e.g. Llama-2-7B), so wants a GPU.
- **LongLLMLingua**: per Microsoft Research, *"a 17.1% performance improvement with 4x compression"* on long-context tasks by filtering noise.
- **LLMLingua-2**: a BERT-level token-classification model (XLM-RoBERTa/mBERT) distilled from GPT-4, *"offering 3x-6x faster performance"* at 2–5× compression, task-agnostic. **CPU-feasible** — the right default for a wrapper.

**Selective Context** — established the field; per NeuralTrust's guide, it *"achieved 50% context reduction while maintaining comparable performance: only 0.023 degradation in BERTScore."*

**PCToolkit**, **EFPC**, extractive/semantic summarizers, and LLM "rewrite shorter" pipelines are supporting options. **Caveat:** prompt compression works best on redundant RAG context; it is not universally safe and can hurt reasoning tasks. Ship it as "optional advanced," off by default.

### Category 7 — Token counting & serialization-format efficiency (grounding the core value claim)

**Token counters:** **tiktoken** (MIT, OpenAI BPE) and **HuggingFace tokenizers** (Apache-2.0) — both light, importable, and essential for the before/after UI.

**The measured serialization evidence** (cite these; they are the reliable ones):
- **Markdown vs HTML — the biggest, best-supported win.** Cloudflare's "Introducing Markdown for Agents" (Feb 12, 2026) reports its own announcement blog post at *"16,180 tokens when served as HTML but only 3,150 tokens as markdown — an 80% reduction,"* and community testing of Cloudflare's docs page found *"Raw HTML: 9,541 tokens. Cleaned markdown: 1,678 tokens. That's an 82% reduction."* FormatArc's committed benchmark measures ~70% (−67 to −87% across reports). **The savings come overwhelmingly from stripping nav/ads/scripts, not from markdown syntax itself.**
- **CSV vs JSON:** GetCrux measured CSV using ~56% fewer tokens than JSON (Claude 3.5, 10,000 tabular questions) *and* higher accuracy — yet ImprovingAgents' 11-format test found CSV/JSONL among the *weakest* on comprehension (~44.3%). Format effect is task- and model-dependent.
- **TOON (Token-Oriented Object Notation)** — MIT (`toon-format/toon`). The official benchmark: *"TOON achieves 72.2% accuracy (vs JSON's 71.4%) while using 42.6% fewer tokens"* across 244 retrieval questions on 4 models (CSV is excluded from that track because it supports only flat tabular data). Independent work (Matveev, arXiv:2603.03306, Feb 2026) shows the ceiling: in the aligned "users" case *"TOON achieved 90.5% one-shot accuracy while using 22% fewer tokens than plain JSON,"* but *"As structure moves from Aligned to Non-Aligned, TOON performance collapses… the accuracy of 1-shot is 0%"* for a nested company case. **TOON's wins are real but narrow (uniform arrays) and model-dependent.**
- **Markdown-KV** ("key: value"): topped an 11-format test at ~60.7% accuracy, ~16 points ahead of CSV, but used more tokens.
- **Nested data (JSON/YAML/XML/Markdown):** Markdown most token-efficient (34–38% fewer than JSON, ~10% fewer than YAML); XML worst (~80% more than Markdown).
- **Counter-evidence on accuracy:** multiple papers (Tam et al.; ToolScan) find structured/token-optimized formats can *degrade* reasoning; McMillan's 9,649-trial study found format doesn't significantly change aggregate SQL-generation accuracy. And arXiv:2603.03306 finds plain JSON *generation* still most accurate despite TOON's input-side savings.
- **Stripping markdown syntax entirely** saves a little more but loses heading/list/code structure that carries meaning: "LLMs Understand Layout" (arXiv:2407.05750) shows +8–33% F1 when layout is preserved. **Net rule for the repo: keep structure, strip boilerplate.**

Tokenizer choice changes every one of these answers — always measure with the target model's tokenizer.

### Category 8 — Adjacent / supporting utilities worth wrapping
- **Chunkers:** Chonkie (`chonkie-inc/chonkie`, MIT, Python; token/sentence/semantic/recursive/SDPM/late/neural; minimal core, extras for heavy features, tiktoken/HF tokenizers). LangChain/LlamaIndex splitters; semchunk (MIT, pure Python, fast); semantic-text-splitter.
- **Table extractors:** camelot (MIT), tabula-py (MIT, needs Java), img2table (MIT).
- **Audio/video → transcript:** whisper.cpp (MIT), faster-whisper (MIT); MarkItDown and Docling already do ASR.
- **Figure captioning:** Florence-2, BLIP.
- **Boilerplate/whitespace strippers & dedup:** regex + remark/strip-markdown patterns.
- **EPUB/email/archive:** handled by MarkItDown/Docling.

### Existing projects (competitive landscape)
- **omniparse** (adithya-s-k) — GPL-3.0, Gradio UI + FastAPI + Docker, ~20 file types, uses Marker/Surya/Florence-2/Whisper, T4 GPU, Linux-only server. The closest existing "unified GUI," but GPL + Marker's commercial-license caveat limit adoption.
- **MegaParse** (QuivrHQ) — permissive-ish, no-loss parser for PDF/DOCX/PPTX, optional Vision (GPT-4o/Claude).
- **docling-serve** — MIT, official Docling REST API + optional UI (Docker/Podman, CPU variant). A good model for your subprocess/service pattern.
- **unstructured-api** — Apache-2.0, self-hostable API.
- **kotaemon**, **open-parse**, **extract-thinker** (wraps docling + markitdown) — RAG/parsing frameworks, not GUIs.
- **MarkItDown GUI forks** (many): `imadreamerboy/markitdown-gui` (PySide6 + QML, drag-drop, batch queue, OCR, PyInstaller packaging — the most polished, and proof PySide6 can distribute this well); `RafalekS/MarkItDown_GUI` (PyQt6, multi-converter fallback incl. marker + pandoc); `NNOUU`, `superdale007`, `YamithR` (Tkinter/.deb).

**The gap:** every existing tool is either a single-backend GUI (the MarkItDown forks) or a single-domain server (omniparse, docling-serve). None unify documents + web + code repos + prompt compression behind one interface with before/after token metering and a pip-installable plugin architecture.

## Recommendations

### Stage 1 — Ship a light, CPU-only, MIT/Apache core first (fastest path to a usable, conflict-free repo)
Bundle only tools that import cleanly with no PyTorch and no viral licenses:
1. **MarkItDown** (Office/breadth) — MIT
2. **Docling** (PDF tables + unified doc model; PyTorch but CPU-OK) — MIT
3. **pdfplumber + pypdf** (light digital-PDF fallback) — MIT/BSD
4. **Trafilatura** + **markdownify** (web/HTML→MD) — Apache/MIT
5. **Crawl4AI** (JS pages) — Apache
6. **gitingest** (repo→text, Python-native) — MIT
7. **Chonkie** (chunking) — MIT
8. **tiktoken + HF tokenizers** (the before/after token meter) — MIT/Apache
9. **Tesseract via pytesseract** (CPU OCR fallback) — Apache
10. **LLMLingua-2** (CPU-feasible prompt compression) — MIT
11. **TOON encoder** (serialization option for tabular data) — MIT
12. **Kreuzberg v4** (light unified extraction) — MIT

This set gives near-complete format coverage with essentially no dependency conflicts and a clean commercial license story.

### Stage 2 — Add GPU/heavy backends behind a separate extras install, isolated
`Marker` (GPL), `MinerU`, `olmOCR`, `DeepSeek-OCR`, `Surya` (GPL), `dots.ocr`, `PaddleOCR-VL`, `Granite-Docling`, `PyMuPDF4LLM` (AGPL — subprocess), `Repomix`/`code2prompt` (Node/Rust — subprocess), `LLMLingua v1` (GPU). ReaderLM-v2 only if you accept its non-commercial license.

**Dependency-conflict strategy** (these libraries fight over torch, transformers, pydantic, onnxruntime, numpy):
- `extras_require` groups: `[core]`, `[pdf-ml]`, `[ocr-vlm]`, `[web]`, `[compress]`, `[repo]`.
- Guard every backend import in try/except; each declares its own deps and fails gracefully (grey-out in the UI) if missing.
- **Subprocess isolation** for all CLI/Node/Rust/AGPL/GPL tools (Repomix, code2prompt, PyMuPDF4LLM, Pandoc, LibreOffice, Marker) — call the binary, parse stdout. This also sidesteps AGPL/GPL linking concerns.
- **Per-backend Docker images** (or `uv`-managed separate venvs) for the GPU VLMs; talk to them over a local HTTP/socket, mirroring `docling-serve`.
- Use **`uv`** for fast, reproducible resolution; pin torch/transformers only inside the heavy extras, never in `[core]`.

### GUI architecture — recommendation with reasoning
Judged on bundling for non-technical users, batch + drag-drop, before/after token display, plugin backends, and cross-platform packaging:
- **Primary: NiceGUI + a FastAPI backend.** Event-driven (unlike Streamlit's full-script-rerun model, which fights batch progress bars and live token counters), FastAPI-based so the same process can expose an API *and* orchestrate subprocess/Docker backends, good drag-drop/file handling, packageable to a desktop window via `native` mode, MIT-licensed. Its declarative, event-driven style maps well onto your WPF background.
- **Secondary (for the most native, offline, one-file distribution to non-technical users): PySide6** — the polished `imadreamerboy/markitdown-gui` fork proves PySide6 + PyInstaller distributes this class of app well. More UI code, heavier packaging, but the best offline desktop story.
- **Streamlit/Gradio:** great only for a quick Hugging Face Space *demo*. Streamlit's rerun model is wrong for a multi-backend batch app; Gradio is built for single-model demos, not a plugin registry.
- **Electron/Tauri:** overkill and pulls you off the Python-native path.

**Verdict:** build the core as **FastAPI + NiceGUI** for the cross-platform/self-host story; optionally add a **PySide6** desktop shell later if offline distribution to non-technical users becomes the priority.

### Suggested plugin/adapter pattern
Define a common protocol so every converter is a swappable backend:
```python
class Converter(Protocol):
    name: str
    supported_inputs: set[str]      # extensions / mime types / "url" / "repo"
    license: str
    requires: list[str]             # optional deps
    def is_available(self) -> bool: # checks deps present
    def convert(self, source, options) -> ConversionResult
    # ConversionResult: .markdown, .tokens_before, .tokens_after, .warnings, .backend
```
Register backends via entry points so third parties add plugins with `pip install`. Each adapter wraps one tool (import or subprocess). The GUI calls `is_available()` to show/grey-out backends; a shared `TokenMeter` (tiktoken/HF) computes before/after for every conversion. This delivers swappable backends, graceful degradation, and an extension story none of the existing tools have.

### Article angles
- **Genuinely novel/under-covered:** (1) a reproducible, cross-domain benchmark of N converters on ONE messy corpus measuring **both tokens and fidelity** (unaddressed across all four domains); (2) DeepSeek-OCR's "optical context compression" as a token-reduction story; (3) an honest debunk of "markdown magically saves tokens" (it's boilerplate removal + structure, and format choice carries accuracy tradeoffs).
- **Original data to produce:** run a 20–50-item corpus (scanned PDF, multi-column academic paper, table-heavy report, DOCX, HTML page, a code repo) through 8–10 backends; report tokens (tiktoken o200k), a fidelity score (against hand-labeled ground truth or olmOCR-bench-style unit tests), speed, and CPU-vs-GPU feasibility. Publish the harness (model it on `goldziher/python-text-extraction-libs-benchmarks`).
- **Strongest evidence-backed claims for the article:** "Stripping boilerplate and converting to Markdown cuts input tokens ~70–90% on real web/office documents (Cloudflare measured 80–82%)" — well supported; "For tabular data, CSV/TOON cut tokens ~22–56% but can reduce accuracy, so measure per model" — well supported with counter-evidence; "LLMLingua-2 gives 2–5× prompt compression with 3–6× faster inference, and LLMLingua up to 20× with <2% loss on RAG-style context" — paper-backed. **Avoid unqualified "format X is always best" claims.**

## Caveats
- **This ecosystem moves fast.** Star counts, versions, and especially licenses (MinerU's v3.1.0 relicense, the Kreuzberg→Xberg Elastic-2.0 shift, Marker's RAIL weights, ReaderLM's CC-BY-NC) are current as of August 2026 and should be re-verified before you ship.
- **Many "token savings" figures come from tool marketing pages and are unmeasured.** The arXiv/benchmark numbers cited here (Cloudflare, GetCrux, the TOON repo, Matveev arXiv:2603.03306, Microsoft LLMLingua, NeuralTrust) are the defensible ones. TOON's official accuracy wins diverge from independent tests and apply mainly to uniform arrays.
- **License nuance is critical for a bundled repo.** AGPL (PyMuPDF4LLM, Firecrawl) and GPL (Marker, Surya, omniparse, Pandoc) contaminate if linked/imported — subprocess isolation is the safe pattern. ReaderLM weights are non-commercial. Verify before distributing.
- **VLM/OCR models need a GPU for practical speed.** The genuinely CPU-only viable tools are the classical engines (Tesseract/PaddleOCR/docTR), pdfplumber/pypdf, PyMuPDF4LLM, Docling (slow but works), Trafilatura/markdownify, and LLMLingua-2. Set user expectations accordingly in the README.