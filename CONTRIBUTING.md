# Contributing to tokenmill

Thanks for looking. tokenmill is early — see [`PROGRESS.md`](PROGRESS.md) for
what actually exists today and [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md)
for where it is going.

## Setting up

```bash
git clone https://github.com/RSD-Studio/tokenmill
cd tokenmill
uv venv
uv sync --extra dev --extra fixtures
uv run pre-commit install
uv run python scripts/make_fixtures.py
```

## The checks that must pass

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=tokenmill
uv run python scripts/make_fixtures.py --check   # corpus is reproducible
```

CI runs all of these across Python 3.11/3.12/3.13 on Linux, macOS and Windows,
plus a **clean core install** job that `pip install .` with no extras and imports
the package. That job is the guard on our central promise; if your change makes
it fail, the change is wrong, not the job.

## Rules that are not negotiable

**1. The core install stays light.** No PyTorch, no CUDA, no system-binary
requirement in the default dependency set. Anything heavy goes behind an
`optional-dependencies` group and a lazy import.

**2. Copyleft dependencies are never imported.** AGPL and GPL tools
(PyMuPDF4LLM, Marker, Surya, Pandoc, Firecrawl core, omniparse) are invoked via
subprocess or a service boundary, never `import`ed into the tokenmill process.
Every adapter declares its licence in `BackendInfo`. See
[`docs/LICENSES.md`](docs/LICENSES.md).

**3. Backends import lazily.** A backend module must import cleanly with its
heavy dependency absent. The real import happens inside `convert()`. A missing
dependency degrades to "unavailable, greyed out, here is the install command",
never an `ImportError` at startup.

**4. No unsourced numbers.** Any token-savings figure in code, docs, the README
or the GUI either cites `docs/research/RESEARCH.md` with its source, or comes
from our own benchmark harness on our own corpus. We do not restate vendor
marketing claims as fact, and we do not estimate where we can measure.

**5. Report backends honestly.** If a converter produces garbage on our
fixtures, that goes in `docs/BACKENDS.md` under failure modes. A wrapper that
hides a bad converter is worse than no wrapper.

**6. No stubs.** Modules ship complete: imports, error handling, type hints,
docstrings and tests. If something belongs in a later phase, leave it out and
note it in `PROGRESS.md` rather than committing a placeholder.

## Test fixtures

The corpus in `tests/fixtures/` is generated, never downloaded — we do not ship
copyrighted material. `scripts/make_fixtures.py` builds every file
deterministically and writes `ground_truth.json` alongside them.

Assert against **structure**, not bytes: headings present, table cell counts,
reading order, content recall. Byte equality is too brittle to be useful across
backend versions.

If you change the generator, regenerate and commit the fixtures in the same
change, and confirm `--check` still passes.

## Adding a backend

See [`docs/ADDING_A_BACKEND.md`](docs/ADDING_A_BACKEND.md) *(written in Phase 1)*.
The short version: implement the `Converter` protocol, declare a `BackendInfo`
including the licence and install extra, register an entry point in the
`tokenmill.backends` group, and add an integration test that skips cleanly when
the dependency is absent. No core edits should be needed.

## Commits and branches

Conventional commits, e.g.:

```
feat(core): add Converter protocol and registry
fix(web): keep <pre> whitespace through the markdownify adapter
docs(backends): record docling's failure mode on rotated tables
test(repo): cover gitingest token-budget truncation
chore(ci): add the clean-core-install job
```

Keep commits small and coherent, and keep the tree clean — no drive-by
reformatting mixed into a behaviour change.

## Release checklist

*(Fills out in Phase 11 when publishing exists.)*
