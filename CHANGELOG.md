# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

[Unreleased]: https://github.com/RSD-Studio/tokenmill/commits/main
