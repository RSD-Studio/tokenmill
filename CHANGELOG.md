# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Phase 7 — isolation layer and licence enforcement

- **Licence enforcement is code, not a convention.**
  `tokenmill.core.licensing` reads every installed distribution's own metadata
  and classifies it; `tests/unit/test_license_isolation.py` makes four
  independent checks — that every backend declares a tier, that no copyleft
  distribution is installed, that no module in the package *mentions* a
  copyleft module (parsed, not executed, and seeing imports inside functions),
  and that after a copyleft backend converts a document its module is not in
  `sys.modules`.
- **The check has been seen to catch a real violation.** `import pymupdf4llm`
  added by hand inside a real in-process adapter failed three of the four
  checks; the output is in `PROGRESS.md` and the violation was reverted.
- **`tokenmill backends --show-licenses`** audits the environment and exits
  non-zero if a copyleft package is installed.
- **`SubprocessConverter`** — binary discovery beyond `PATH`, version probing
  recorded as provenance, an allow-list of every program tokenmill may launch,
  and a workspace removed on every exit path including timeout and failure.
- **`ServiceConverter`** — the HTTP mode, proved against a real local server.
  No service backend is registered; Phase 9 registers the concrete ones.
- **Three isolated backends:**
  - `pymupdf4llm` (AGPL-3.0) in a **separate interpreter**, never installed
    alongside tokenmill. On `tables.pdf` it is both cheaper than pdfplumber
    (553 vs 599 bytes) and the most faithful backend in the corpus (0.848).
  - `pandoc` (GPL-2.0-or-later) for EPUB, LaTeX, RST, Org and thirty more.
  - `libreoffice` (MPL-2.0, isolated only because it is C++) for the legacy
    `.doc` / `.xls` / `.ppt` formats.
- **`docs/LICENSES.md` completed** with the tiering rules and the reasoning.

### Fixed

- **A licence classifier defect, found by reading real metadata.** PyMuPDF4LLM
  states `Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License`.
  The disjunction rule took the most permissive branch — correct for `tld`,
  wrong for a branch that must be *bought* — and split on a case-sensitive
  `OR`, so the SPDX spelling of that licence classified as **permissive**. Both
  fixed, with regression tests.
- **Repomix timed out on Windows CI.** `options.timeout_s` is a conversion
  budget and the `npx` launcher was spending it on an npm install first. The
  fetch now has its own allowance.
- **A corrupt PDF through an isolated backend** reported
  `Traceback (most recent call last):` as its error message. Now `CorruptSource`
  with the informative last line, matching the other PDF backends.

### Changed

- **`PostProcessor.in_default_chain` replaces `destructive` as the mechanism**
  (breaking, with owner sign-off). `destructive` is now honest documentation of
  what a step can lose, and `chunk` declares `destructive = False` and
  `in_default_chain = False` — both true, which the old single flag could not
  express. `default_chain()` reads **both**, so a third-party post-processor
  written against the Phase 1 contract still behaves exactly as it did.
- **One pipe-table parser** (defect N3). `fidelity/markdown.py` and
  `formats/markdown_table.py` had separate scanners; they are now one
  `scan_tables` with the strictness difference expressed as `unescape=`.
- **`docs/BENCHMARKS.md` publishes model-token figures** for the first time,
  read out of captured CI logs. See below.

### Measured

- **The headline figure, in the unit the claim is about** (defect D3, open
  since Phase 3, now closed). `boilerplate.html` through `trafilatura`:
  **3,716 → 629 `o200k_base` tokens, −83.1%**, inside `RESEARCH.md`'s 70–90%
  band. From CI run 85.
- **The byte proxy is optimistic, and by a lot.** On the `tables.pdf` table,
  CSV saves 60.2% of JSON's *bytes* and **36.0%** of its *tokens*; TOON saves
  55.8% and **29.9%**. Neither GetCrux's ~56% nor the TOON repository's 42.6%
  reproduces on our data in its own unit. From CI run 89.
- **The two units do not even rank the formats in the same order.** `keyvalue`
  is 16% smaller than JSON in bytes and 1.8% *more expensive* in tokens.

#### Phase 6 — prompt compression (optional tier, off by default)

> **The success path has never been executed anywhere.** The LLMLingua-2 model
> lives on `huggingface.co`, which the development environment denies at the
> egress proxy. No compression has been run by this code and no ratio has been
> produced by it. The refusal, error, import-time and arithmetic paths are
> tested; the happy path is **unverified**. This is the posture Phase 2 took
> with docling's PDF path.

- **`compress` post-processor** (order 900, destructive, off by default) wrapping
  LLMLingua-2 behind a `compress` extra. MIT, verified from the wheel's own
  METADATA and bundled LICENSE.
- **Nothing downloads without `--allow-network`.** The model loads with
  `local_files_only` and the refusal names the size, the cache path and the exact
  command. **No environment variable is set** — the switch rides in llmlingua's
  `model_config` — so this adds nothing to the five pieces of process-global
  state `docs/ARCHITECTURE.md` records.
- **`trust_remote_code` is off**, against llmlingua's default of on, which lets a
  model repository execute arbitrary code on load.
- **Nothing is imported at module load**: loading all eight post-processors pulls
  in zero third-party modules.
- **No bespoke ratio number.** The achieved ratio is the `compress` row in
  `--show-stages`; the retention indicator is `tokenmill fidelity`.
- **An empty result raises** rather than reporting a 100% saving.
- **`--compress-ratio` and `--compress-model`** on `tokenmill convert`.
- **Selective Context is deferred**, with the measurement: its 0.1.4 release pins
  `click==8.0.4`, conflicting with the CLI, and a resolver silently backs down to
  0.1.3.

#### Phase 5 — post-processing, formats, and measurement depth

- **Five more post-processors**, every one destructive and off by default:
  `strip_frontmatter` (50), `aggressive_whitespace` (150), `dedupe_blocks` (250),
  `normalize_headings` (400), `chunk` (700). `links` gains `--links reference`.
  **The default chain is still exactly `normalize_whitespace`**, asserted over
  the whole registry rather than per processor.
- **`tokenmill.formats`** — Markdown, CSV, JSON, TOON and key-value table
  encoders, registered through a `tokenmill.formats` entry point group. Every
  one round-trips losslessly, proven with property tests.
- **TOON implemented against the specification** (Working Draft 4.1, MIT) rather
  than wrapped: `toon-format` 0.1.0 on PyPI is a stub whose `encode()` raises
  `NotImplementedError`, and `toon-py` 1.0.2 emits a redundant delimiter in
  every array header. Conformance to the TypeScript reference is unverified.
- **`tokenmill compare`** — one input, several backends or serialisations, with
  tokens, timing and **fidelity** in the same row. Works on documents, web pages
  and repositories. Rows stay in preference order; the cheapest and the most
  faithful are both named, and when they differ the report says so.
- **Chonkie chunking** behind a `chunk` extra, with sizes in the run's own unit.
- **A reduction that happens inside a backend is now a stage** (defect D8):
  `source → visible_text → convert` decomposes a web conversion's −77.1% into
  markup removal and boilerplate removal, and a truncated repository pack shows
  `packed → convert`.
- **`tests/fixtures/structured.md`**, generated: front matter, skipped heading
  levels, lists, a code fence, inline and reference links, an image, a duplicated
  block and a table.
- **hypothesis put to work for the first time** since Phase 0 declared it. It
  found seven real bugs on its first outing, all fixed and each with a named
  test.

### Fixed

- **Defect D9** — `convert --json` now carries `counts` and
  `is_model_tokenizer`, so a consumer reading `"tokenizer": "bytes"` has a
  machine-readable signal that these are not model tokens. The `web` object is
  now **absent** for a non-web conversion rather than `null`: `null` means
  "applies here, no value", an absent key means "does not apply". This changes
  the shape of `convert --json` for a document.
- **MarkItDown escapes Markdown syntax inside XLSX cell values**, so
  `backend_count` comes back as `backend\_count` and a literal search fails.
  Documented in `docs/BACKENDS.md` and asserted by a test.

#### Fidelity scoring (a Phase 10 slice, brought forward ahead of Phase 5)

- **`tokenmill.fidelity`** — scores converted text against a fixture's
  hand-labelled ground truth as six named components plus an unweighted overall
  that names what composed it: heading recall, content recall, table integrity,
  structure retention, boilerplate rejection and reading order.
- **A component with no ground truth scores `None`, never zero and never one.**
  `long_context.md` has no table, so scoring its table integrity either way
  would be a false statement about a document with no table in it. Same rule
  `ground_truth.json` already followed for `token_count`.
- **An empty document scores zero on every component that applies**, including
  boilerplate rejection. The arithmetic alone would score it 1.0 there — an
  empty string genuinely contains no boilerplate — which is the failure
  `benchmarks/README.md` names, reappearing inside the instrument built to
  catch it.
- **`tokenmill fidelity FILE --against FIXTURE`**, reading `-` for stdin so it
  pipes from `convert`. `--json` carries `null` for a component that did not
  apply, so a consumer can tell "not measured" from "measured as zero".
- **Scorable ground truth for `jsrendered.html` and `scanned.pdf`**, added to
  `scripts/make_fixtures.py` and regenerated. Neither could be scored before,
  and `jsrendered.html` is the fixture the whole exercise is for: it produces
  the largest reduction in the corpus, −90.7%, at a fidelity of **0.000**.
- **A fidelity figure beside every token figure** in `docs/BENCHMARKS.md`,
  covering every installed backend against every fixture it claims.
- **Eight failure modes documented in `docs/BACKENDS.md` are now numbers** —
  Kreuzberg flattening a PDF table reads as table integrity 0.00 against
  pdfplumber's 1.00; pdfplumber interleaving two-column pages reads as reading
  order 0.58 against pypdf's 1.00.

#### Phase 4 — repository backends

- **Three repository backends**, one set of options over three runtimes:
  - `gitingest` (MIT, `repo`) — Python-native, so it needs no external tool and
    is what a repository auto-selects. Packs 7 of the fixture's 9 tracked files,
    correctly skipping the binary blob and never emitting the `.gitignore`d
    secret.
  - `repomix` (MIT, Node, **subprocess**) — the category leader; the most
    complete pack of the three at 8 files.
  - `code2prompt` (MIT, Rust, **subprocess**) — the fastest, at 103 ms against
    564 and 1,082 on our fixture.
- **`tokenmill repo`**, a new command. `https://github.com/owner/project` is a
  web page to `convert` and a repository to `repo`, and only the command the
  user typed distinguishes them. Flags: `--include`, `--exclude`,
  `--token-budget`, `--tree-tokens`, `--max-file-size`, `--no-gitignore`,
  `--branch`, `--allow-network`.
- **A token budget that genuinely caps the output.** Whole files only, in the
  tool's own emission order, never partial. Measured: a 1,200-byte cap produces
  a 999-byte document, and **every dropped file is named** — in a warning, in the
  metadata, and in the document itself, because the document is the part that
  reaches a model.
- **A per-directory token breakdown** on `--tree-tokens`, rolled up through
  every ancestor so it answers a question about a subtree.
- **Shallow cloning of a remote Git URL** into a temporary directory removed on
  every exit path including failure. `ext::` and `file://` are refused at two
  layers, since `ext::` makes git execute an arbitrary command.
- **`tokenmill.backends._subprocess`** — the minimum runner Phase 4 needs: list
  arguments, never `shell=True`, timeouts, captured stderr on the exception, and
  a path beginning with `-` refused rather than passed. **Phase 7 replaces it**;
  what it deliberately does not do is listed in its docstring and in
  `PROGRESS.md`.

### Fixed

#### Found by the Phase 0–4 review

- **A conversion could report a large saving for losing the content.**
  `convert jsrendered.html` reported `1,512 -> 140 (-90.7%)`, a number that would
  look excellent in a benchmark and represented near-total content loss — the
  case `benchmarks/README.md` names as disqualifying. Web backends now warn when
  a page carries scripts and under 15% of its bytes are visible text, calibrated
  against the corpus and explicitly labelled a heuristic.
- **A clean install gave a Node error for a Python tool.** With no extras,
  `tokenmill repo ./project` fell through to repomix and failed with npx
  instructions, never mentioning `pip install "tokenmill[repo]"`.

#### Phase 4 — gitingest's behaviour as a library

Four things it does to the process that imports it, all found by running it:

- It validated `$GITHUB_TOKEN`'s *format* before looking at the source, so a
  placeholder token failed a purely **local** pack with
  `InvalidGitHubTokenError`.
- **It installed a loguru handler on the stdlib root logger and set that
  logger's level to 0**, rerouting every record tokenmill and any embedding
  application logs, and un-suppressing INFO. Snapshotted and restored now.
- It logged its own progress at INFO, eight lines per pack.
- Its ignore rules go through pathspec's deprecated `gitwildmatch` factory,
  whose `DeprecationWarning` is fatal under `filterwarnings = ["error"]`.

#### Phase 3 — web backends

- **Three web backends**, licences verified against the installed package
  metadata:
  - `trafilatura` (Apache-2.0, **core**) — extracts a page's article and
    discards the website around it. On `boilerplate.html` it removes **all six**
    of the corpus manifest's boilerplate markers while keeping all six headings,
    all seven article paragraphs and the 7×5 table: 12,481 → 2,854 bytes,
    **−77.1%**, inside `RESEARCH.md`'s published 70–90% band.
  - `readability` (Apache-2.0, `web`) — the Firefox Reader View algorithm, as a
    second independent opinion when trafilatura declines a page.
  - `crawl4ai` (Apache-2.0, `crawl4ai`) — drives a real Chromium so a page's
    JavaScript runs. The only backend that can convert a client-rendered page,
    and measurably the weakest extractor of the three.
- **URL fetching**, in the pipeline rather than in each backend, with a user
  agent naming tokenmill and its repository, a timeout, a bounded redirect chain
  that refuses to leave `http(s)`, a byte cap, and `robots.txt` respect that is
  on by default. Standard-library `urllib`, so the core install gains no
  dependency for it.
- **A boilerplate metric that cannot be confused with the token saving.** A web
  backend records what share of the page's *visible text* it discarded, next to
  the byte or token reduction, which counts markup removal too. `markdownify_html`
  scores **−38.7%** on it — it discards no text and adds Markdown syntax — while
  removing 45.5% of the file's bytes. Reporting one as the other is the
  misattribution `RESEARCH.md` Category 7 describes.
- **`tests/fixtures/jsrendered.html`** — a page whose article is inserted by a
  script, with a sentinel the script assembles from two halves so it appears
  nowhere in the file's bytes. It is what makes "crawl4ai renders JavaScript"
  checkable rather than asserted.
- **New CLI flags** on `convert`: `--offline`, `--ignore-robots`,
  `--allow-network`, `--user-agent`, `--max-redirects`. A `page:` line in the
  report and a `web` object in `--json`.
- **New `browser` test marker**, opt-in like `network` and `heavy`, so the
  default suite stays offline and CI never downloads a browser.
- **[`docs/LICENSES.md`](docs/LICENSES.md)** — created. `CONTRIBUTING.md` rule 2
  had linked to it for three phases and it did not exist.
- **[`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)** — created, partial, and explicit
  that its figures are in UTF-8 bytes rather than model tokens.

### Changed

#### Phase 3

- **`trafilatura` is now the default backend for HTML**, ahead of
  `markdownify_html`. This changes what `tokenmill convert page.html` produces:
  an extracted article instead of the whole page converted faithfully. Ask for
  the old behaviour with `--backend markdownify_html`, which remains the right
  choice when you want the entire page.
- **The shared adapter helpers moved** from
  `tokenmill.backends.documents._common` to `tokenmill.backends._common`, since
  web and repository adapters need them too. The old path re-exports everything
  and is tested, so no existing import breaks.
- **Additive model changes**: `Source.format_hint`, `Source.from_fetched`,
  `Source.from_git`; `ConvertOptions.fetch`, `respect_robots`, `max_redirects`,
  `user_agent`; `BackendInfo.fetches_urls`. `fetch` is deliberately separate
  from `allow_network` — naming a URL is the request to fetch *that URL*, while
  `allow_network` stays default-deny and governs what a backend reaches for on
  its own.

#### Phase 2 — document backends (light tier)

- **Five document backends**, each with its licence verified against the
  installed package metadata rather than taken from a README:
  - `pdfplumber` (MIT, **core**) — digital PDFs with their tables intact. It
    splices rendered Markdown tables into the page text in document order, which
    is what recovers all 35 cells of the `tables.pdf` fixture.
  - `pypdf` (BSD-3-Clause, **core**) — plain text with correct multi-column
    reading order, and no required dependencies of its own.
  - `markitdown` (MIT, `documents`) — the broadest converter in the tier, and
    the only one that keeps PPTX speaker notes.
  - `kreuzberg` (MIT, `documents`, pinned `<5`) — a Rust core with no required
    Python dependencies; fast, good reading order, infers headings from PDFs.
  - `docling` (MIT, `docling`) — the best document structure in the permissive
    tier. Behind its own extra and lazily imported: it resolves to 122 packages
    and about 5.2 GB.
- **A per-format backend preference map** (`tokenmill.core.preferences`). A
  single global priority could not express that MarkItDown is right for `.pptx`
  and wrong for `.docx`, so ranking is per format. A number in the map replaces
  a backend's declared priority for that one format; a backend the map does not
  name keeps its own, so a third-party backend can still outrank the built-ins
  without editing core. Every number cites an observation on our own corpus.
- **A fallback chain.** `Registry.candidates()` returns the ordered chain rather
  than one winner, and the pipeline walks it until one backend succeeds. Every
  attempt is recorded on `ConversionResult.attempts`, and a fallback attaches a
  warning naming the backend that failed — a conversion that quietly came from
  the third choice would attribute the measurement to a converter that never
  ran. An explicit `--backend` never falls back.
- **`--no-fallback`** on `tokenmill convert`, and an `attempts:` line in the
  report whenever a fallback actually happened. The full chain is always in
  `--json`.
- **`@pytest.mark.requires("markitdown")`**, which skips a test cleanly and
  *visibly* when an optional dependency is absent.
- **[`docs/BACKENDS.md`](docs/BACKENDS.md)** — a section per backend covering
  what it is good at, what it is bad at, its licence and install extra, and its
  observed failure modes quoted from real output on our own fixtures.

### Changed

- **A binary document reports what its output costs, not a fake saving.**
  Converting a `.docx` used to report `68,190 -> 3,494`, where the first figure
  was the zip archive's own bytes decoded as text. Nobody hands a model the
  bytes of a `.docx`, so that number cannot be subtracted from anything. There
  is now no before-count and no percentage for a binary source — the headline is
  the output's cost and the input is reported as a size:

  ```
  tokens:   3,494  (o200k_base)
  size:     37.4 KiB in, no comparable before
  ```

  `ConversionResult` gains `source_bytes`; `tokens_before` is `None` and there is
  no `source` stage, so "before" cannot silently come to mean "after
  conversion". The before/after pair is unchanged where both sides really are
  text a model could be given. An interim version of this printed the old number
  with a warning attached; that was dropped because a disclaimer on every
  document conversion devalues the warnings a user must not ignore.
- **Every document backend warns when it produces an empty document.** A scanned
  PDF has no text layer and all five return nothing for it; an empty conversion
  exits 0 and looks exactly like success. OCR is Phase 9.
- **The pdfplumber adapter warns when a page looks multi-column.** It has no
  layout model and interleaves columns, and interleaved columns still read as
  fluent prose — so the adapter looks for a column gutter and says which pages
  are affected and which backends read columns in order. Thresholds calibrated
  against the corpus.
- **CI now installs the `documents` extra** for the lint, type-check, test and
  coverage jobs. Without it mypy saw `Any` for every new adapter and the
  MarkItDown and Kreuzberg integration tests skipped, so Phase 2's adapters
  would have been verified nowhere. A new `docling` job runs weekly and on
  manual dispatch, never on a push — it re-verifies a backend whose upstream
  moves fast, rather than only closing today's gap.
- **The protocol-conformance suite now uses the real fixture corpus.** It built
  text samples only, so a backend claiming `pdf` or `docx` skipped three checks
  for want of a sample. It also treats `NetworkRequired` as a correct answer
  from a backend that needs a model download while `allow_network` is false.

### Fixed

- **A third-party library warning at import time no longer fails a conversion.**
  MarkItDown imports magika, which imports onnxruntime, which warns
  `Unsupported Windows version` on load; under `-W error` that turned every
  MarkItDown conversion on Windows into `BackendFailed`. Such warnings are now
  captured and handed to the user as conversion warnings — non-fatal, still
  visible.
- **mypy no longer stops before checking our code on Python 3.12+.** numpy
  arrives transitively with the `documents` extra and its stubs use 3.12-only
  syntax while we target 3.11.
- **Fixture generation no longer depends on the null device.** It isolated git's
  config with `GIT_CONFIG_GLOBAL=os.devnull`; a path that does not exist reads
  as an empty config on every platform and does not assume the null device
  behaves like a config file.

#### Phase 1 — core architecture

- **The plugin system.** Backends, post-processors and tokenizers are all
  discovered through entry point groups (`tokenmill.backends`,
  `tokenmill.postprocessors`, `tokenmill.tokenizers`). The built-ins register
  through the same groups a third party would use; there is no hard-coded import
  list anywhere. Adding a backend needs no change to tokenmill itself.
- **The data model** (`tokenmill.core.models`): `Source`, `ConvertOptions`,
  `ConversionResult`, `BackendInfo`, `TokenCount`, `StageCount` and
  `Availability`, all frozen dataclasses. A `TokenCount` always carries the
  tokenizer that produced it, because a count without one cannot be compared
  with anything.
- **The `Converter` protocol and `BaseConverter`**, which handle availability
  caching, the input size guard, timing, warning collection and the guarantee
  that only `ConversionError` subclasses escape a conversion.
- **The backend registry**, with cached entry point discovery, availability
  filtering, and a documented deterministic selection order. A plugin that fails
  to load is reported as an unavailable backend rather than taking the process
  down with it.
- **The error taxonomy** (`tokenmill.core.errors`): `ConversionError` with
  `UnsupportedFormat`, `BackendUnavailable`, `BackendFailed`, `Timeout`,
  `CorruptSource` and `NetworkRequired`, plus `TokenizerError` and
  `ConfigError`. Every error carries an optional actionable hint; no traceback
  reaches the user.
- **The conversion pipeline**, measuring the text as it leaves every stage, so a
  user sees which step made a document cheaper rather than only that it got
  cheaper.
- **Layered configuration**: defaults, then a TOML file, then `TOKENMILL_*`
  environment variables, then CLI flags. Unknown settings are rejected rather
  than ignored.
- **The token layer**: tiktoken (`o200k_base` and friends), HuggingFace
  (`hf:<model>`, behind the new `tokenizers` extra), and `bytes` — a
  download-free UTF-8 byte counter for air-gapped machines, explicitly labelled
  as not a model tokenizer. `TokenMeter` refuses to subtract counts made with
  different tokenizers.
- **Two post-processors**: `normalize_whitespace` (non-destructive, runs by
  default, leaves fenced code and Markdown hard line breaks intact) and `links`
  (destructive, opt-in, flattens or removes links and images).
- **Two reference backends**: `plaintext` and `markdownify_html`, both
  permissive, both deliberately trivial. Their job is to prove the architecture.
- **The CLI**: `tokenmill convert`, `tokenmill backends` and `tokenmill tokens`.
  Converted text goes to stdout and the report to stderr, so output pipes
  cleanly. `backends` shows licence, tier, isolation and availability per
  backend.
- **Documentation**: `docs/ARCHITECTURE.md` (design and the reasoning behind it)
  and `docs/ADDING_A_BACKEND.md` (a contributor tutorial with a complete example
  that has been built, installed and run).
- Core dependencies: `typer`, `tiktoken` and `markdownify`, all MIT. The clean
  core install is 19 packages, about a second, no PyTorch and no system binary.
- CI `coverage` job enforcing the plan's ≥85% target on `core` and `tokens`
  (currently 96.07%), and a `tokenizers` job that runs the `network`-marked
  tests against real tiktoken and HuggingFace vocabularies.
- Documented offline tokenizer use via `TIKTOKEN_CACHE_DIR` and `HF_HOME`,
  including the verified property that tiktoken hash-checks cached data, so a
  wrong cache is refused rather than silently miscounting.
- A branch convention in `CONTRIBUTING.md`: `claude/phase-<n>-<slug>` per phase.

#### Phase 0 — scaffolding

- Repository scaffolding: `src/` layout, `pyproject.toml` with the dependency
  tiering from the development plan, Apache-2.0 licence.
- Toolchain: uv workflow with a committed lockfile, Ruff (lint + format), mypy
  in strict mode, pytest with coverage, pre-commit hooks.
- GitHub Actions: lint, type-check, and test across Python 3.11/3.12/3.13 on
  Linux, macOS and Windows; a fixture-reproducibility job; and a clean core
  install job that installs with no extras and imports the package.
- `scripts/make_fixtures.py`, which generates the whole synthetic test corpus
  byte-reproducibly and emits a `ground_truth.json` manifest beside it.
- Test corpus: `simple.pdf`, `tables.pdf`, `twocolumn.pdf`, `scanned.pdf`,
  `corrupt.pdf`, `report.docx`, `unicode.docx`, `deck.pptx`, `data.xlsx`,
  `article.html`, `boilerplate.html`, `long_context.md`, `sample_repo/`.
- Project documentation: README, contributing guide, this changelog, issue and
  pull-request templates, and the development plan and research survey committed
  under `docs/`.

### Fixed

- **CI had never run.** The workflow triggered only on pushes to `main` and on
  pull requests; the repository has no `main` branch and no pull request has
  been opened, so it never fired and was never even registered with GitHub
  Actions. It now also runs on `claude/**` branches.
- **The `network`-marked tests were not run anywhere.** They are skipped locally
  by design, but the CI `test` job runs a plain `pytest`, which skips them too —
  so the tests covering real token counting, the product's central feature, were
  executed by nobody. A blocking `tokenizers` job now runs them explicitly.
- **The test corpus was not byte-reproducible on Windows.** Git's
  `core.autocrlf` rewrote LF to CRLF inside `tests/fixtures/` on checkout, which
  changed the fixtures' digests and made the sample repository rebuild to a
  different commit hash. A `.gitattributes` now marks the corpus `-text`, since
  it is data rather than source. Caught by the first Windows CI job that ever
  ran.
- **`make_fixtures.py --check` compared files that are never committed.**
  `sample_repo/secrets.env` is deliberately excluded from the repository, so
  `--check` reported a mismatch on every fresh clone. It is now excluded from
  the comparison.
- `tokenmill convert` reported a conversion that made a document **larger** as
  though it were a saving — a 62→106 byte increase printed as `-71.0%`. The
  percentage now follows the count, so growth shows as `+71.0%`. Found by
  running the `docs/ADDING_A_BACKEND.md` example backend, whose Markdown table
  is genuinely larger than its CSV input.
- A failure to load a tokenizer aborted the whole conversion, because
  `NetworkRequired` is a `ConversionError`. On a machine that cannot reach
  tiktoken's vocabulary host that meant an error where a converted document
  should have been. Measurement failure is now separated from conversion
  failure: the document is returned, counts are `null`, and a warning says why.
- `tests/fixtures/sample_repo/secrets.env` was never committed — the fixture
  repo's own `.gitignore` hides it from the outer repository too — so
  `test_sample_repo_hides_a_secret_that_ingestion_must_not_leak` failed on any
  fresh clone. It is now materialised on demand, like the fixture's `.git`.
- The `network`, `heavy` and `compress` pytest markers were registered in
  Phase 0 but nothing deselected them, so a plain `pytest` run attempted real
  network downloads. They are now skipped unless the run selects them with
  `-m`.
- The `sample_repo` fixture was being committed as a gitlink, which would have
  left clones with an empty directory. Its working files are now committed and
  its `.git` directory is materialised on demand; a regression test guards it.

### Changed

- Project renamed from `tokenfold` to `tokenmill` before the first commit: the
  name `tokenfold` is taken on PyPI by an unrelated, actively published
  token-compression project, so `pip install tokenfold` could never have been
  ours. See `PROGRESS.md` under Decisions.

[Unreleased]: https://github.com/RSD-Studio/tokenmill/commits/Main
