# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- The `sample_repo` fixture was being committed as a gitlink, which would have
  left clones with an empty directory. Its working files are now committed and
  its `.git` directory is materialised on demand; a regression test guards it.

### Changed

- Project renamed from `tokenfold` to `tokenmill` before the first commit: the
  name `tokenfold` is taken on PyPI by an unrelated, actively published
  token-compression project, so `pip install tokenfold` could never have been
  ours. See `PROGRESS.md` under Decisions.

[Unreleased]: https://github.com/RSD-Studio/tokenmill/commits/main
