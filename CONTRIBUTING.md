# Contributing to tokenmill

Thanks for looking. tokenmill is early — see [`PROGRESS.md`](PROGRESS.md) for
what actually exists today and [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md)
for where it is going.

## Setting up

```bash
git clone https://github.com/RSD-Studio/tokenmill
cd tokenmill
uv venv
uv sync --extra dev --extra fixtures --extra documents --extra web --extra repo
uv run pre-commit install
uv run python scripts/make_fixtures.py
```

`--extra documents`, `--extra web` and `--extra repo` are worth having locally:
without them the MarkItDown, Kreuzberg, readability and gitingest integration
tests skip, and mypy sees `Any` for their adapters.

Two extras are deliberately not in that line. `docling` resolves to 122 packages
and about 5.2 GB; `crawl4ai` to 94 packages and 677 MB, plus a browser download.

Repomix and code2prompt are external programs rather than Python packages, so
no extra installs them. Their tests skip cleanly when the binary is absent —
which is itself a Phase 4 acceptance criterion, so the *absent* case has tests
that always run:

```bash
npm install -g repomix        # or let npx fetch it with --allow-network
cargo install code2prompt     # needs a Rust toolchain
```

## The checks that must pass

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=tokenmill
uv run python scripts/make_fixtures.py --check   # corpus is reproducible
```

Some tests are opt-in because they need something the machine may not have.
They report as skips, not silence:

```bash
uv run pytest -q -m network    # real tokenizer vocabulary downloads
uv run pytest -q -m heavy      # GPU or multi-gigabyte model downloads (docling's PDF path)
uv run pytest -q -m compress   # the compress extra plus a model (Phase 6)
uv run pytest -q -m browser    # drives a real Chromium (crawl4ai, Phase 3)
```

A test that needs an optional dependency declares it and skips cleanly without
one:

```python
@pytest.mark.requires("markitdown")
def test_it_keeps_the_speaker_notes(...): ...
```

Run with `-rs` to see every skip and its reason. A test that quietly vanishes
from the run is how a "verified" claim stops being true without anyone
noticing.

CI runs all of these across Python 3.11/3.12/3.13 on Linux, macOS and Windows,
plus a **clean core install** job that `pip install .` with no extras and imports
the package. That job is the guard on our central promise; if your change makes
it fail, the change is wrong, not the job.

## Rules that are not negotiable

**1. The core install stays light.** No PyTorch, no CUDA, no system-binary
requirement in the default dependency set. Anything heavy goes behind an
`optional-dependencies` group and a lazy import.

**2. Copyleft dependencies are never imported.** AGPL and GPL tools
(PyMuPDF4LLM, Pandoc, Firecrawl core, omniparse) are invoked via subprocess or a
service boundary, never `import`ed into the tokenmill process. So are
**source-available** ones — MinerU's licence is Apache-2.0 plus a revenue
threshold and an attribution obligation, which is its own tier. Every adapter
declares its licence in `BackendInfo`. See
[`docs/LICENSES.md`](docs/LICENSES.md).

Note that rule 1 and rule 2 are separate, and some backends are out of process
for the *first* reason. Marker and Surya are Apache-2.0 as of `marker-pdf` 2.0.0
and `surya-ocr` 0.22.1 — verified from the wheels, against what `RESEARCH.md`
says — so importing them would be legal. It would also put PyTorch in the
dependency tree, which rule 1 forbids. LibreOffice is the same shape for a third
reason: it is C++.

**3. Backends import lazily.** A backend module must import cleanly with its
heavy dependency absent. The real import happens inside `convert()`. A missing
dependency degrades to "unavailable, greyed out, here is the install command",
never an `ImportError` at startup.

**4. No unsourced numbers.** Any token-savings figure in code, docs, the README
or the GUI either cites `docs/research/RESEARCH.md` with its source, or comes
from our own benchmark harness on our own corpus. We do not restate vendor
marketing claims as fact, and we do not estimate where we can measure.

**5. Report backends honestly.** If a converter produces garbage on our
fixtures, that goes in [`docs/BACKENDS.md`](docs/BACKENDS.md) under failure
modes, quoted from real output. A wrapper that hides a bad converter is worse
than no wrapper.

Write a test for the failure too. Every claim in `docs/BACKENDS.md` — Kreuzberg
flattening a PDF table into prose, MarkItDown mis-splitting a header row — is
asserted in `tests/integration/test_document_backends.py`, with a message
saying what to update. When an upstream release fixes one, the test fails and
the documentation gets corrected rather than quietly becoming a lie about a tool
that has since improved.

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

[`docs/ADDING_A_BACKEND.md`](docs/ADDING_A_BACKEND.md) has the full tutorial with
a complete, working example you can copy. The short version:

1. **Subclass `BaseConverter`** and implement one method:

   ```python
   def _convert(self, source, options, context) -> str: ...
   ```

   Availability, format support and the size limit have already been checked by
   the time it runs. Return text. **Do not count tokens** — the pipeline
   measures every stage, and a backend that measured its own output would
   bypass that accounting.

2. **Declare a `BackendInfo`** with `license`, `license_tier`, `isolation` and
   `install_extra`. The licence fields are enforced, not decorative: a copyleft
   or non-commercial backend claiming `IsolationMode.IN_PROCESS` raises at
   construction (rule 2 above).

3. **Import the dependency inside `_convert`**, never at module scope, and
   override `_probe` to check for it with `importlib.util.find_spec` — not a
   real import, because the probe runs on every `tokenmill backends` listing
   (rule 3 above). Return `Availability.missing_dependency(..., hint=...)` when
   it is absent, so the user gets an install command rather than a mystery.

4. **Register an entry point** and nothing else:

   ```toml
   [project.entry-points."tokenmill.backends"]
   yourbackend = "your_package.backend:YourConverter"
   ```

   No core edits. If your change needs one, that is a bug in the registry and
   worth raising as an issue.

5. **Raise inside the taxonomy.** `ConversionError` subclasses only, from
   [`tokenmill/core/errors.py`](src/tokenmill/core/errors.py). Recoverable
   oddities go to `context.warn(...)` instead; structured facts (page count,
   tables found) go to `context.note(...)`.

6. **Write the tests**, including error paths, and mark integration tests so
   they skip cleanly when the dependency is absent. Installing your backend
   automatically enrols it in the conformance suite:

   ```bash
   uv run pytest tests/unit/test_protocol.py -v
   ```

   That suite parametrises over every backend the entry points expose, so it
   checks yours the moment it is installed.

7. **Say where your backend should rank.** If your backend competes with an
   existing one for a format, and it is better or worse at that format for a
   reason you can demonstrate on the corpus, add it to
   `FORMAT_PREFERENCES` in [`tokenmill/core/preferences.py`](src/tokenmill/core/preferences.py)
   with the evidence. A backend the map does not mention keeps its own declared
   `priority`, and a high enough `priority` outranks everything the map names —
   so a third-party backend never *needs* a core edit, and the map stays a
   default rather than a gate.

8. **Do not let a dependency's noise become your failure.** A library that warns
   at import time will fail a conversion under `-W error`. Use
   `warnings_as_conversion_warnings` from
   `tokenmill.backends._common` so the warning reaches the user as a
   warning rather than as a broken backend. Likewise, an empty result is not a
   success: say so with `warn_on_empty_output`.

Post-processors and tokenizers work the same way, through the
`tokenmill.postprocessors` and `tokenmill.tokenizers` groups. A post-processor
that can discard information the user might have wanted must set
`destructive = True`; the default chain is built by excluding those, so it
cannot damage a document.

A post-processor that wants to warn the user, or to attach a structured fact to
the result, adds an **optional** third parameter:

```python
def process(self, text, options, context=None) -> str:
    if context is not None:
        context.warn("there was no front matter to strip")
        context.note("removed_lines", 0)
    return text
```

The registry reads your signature and calls you with two arguments or three
accordingly, so a post-processor written against the original two-parameter
contract keeps working untouched — including one that subclasses
`BasePostProcessor`, whose declaration deliberately stays at two parameters.

## Design decisions

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) records why the architecture is
the way it is — why the data model is dataclasses rather than pydantic, why the
protocol is only three methods, why discovery is cached, why a broken plugin
degrades instead of propagating, and why a measurement failure never becomes a
conversion failure. Read it before proposing a change to the contract; changes
to it are breaking changes needing the owner's agreement.

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

**One branch per phase**, named `claude/phase-<n>-<slug>` — for example
`claude/phase-1-core-architecture`. That is the canonical branch for a phase and
the one to review and merge.

Sessions run by the Claude Code harness are also assigned an auto-generated
branch name (`claude/tokenmill-phase-1-pr3rd7` and the like). Those are pushed
as mirrors of the canonical branch so no work is stranded if a session ends
unexpectedly; they carry identical commits and can be deleted once the phase
branch is merged.

CI runs on every push to `main` and to any `claude/**` branch, and on every pull
request.

Each completed phase records its final commit SHA in `PROGRESS.md`. The plan
asks for a git tag per phase; these sessions cannot push tag refs, so the SHA is
the substitute.

## Release checklist

Commands, not intentions. Everything up to the tag is reversible; everything
after it is not, and the workflow is built around that asymmetry.

### Before the tag

```bash
# 1. Everything green, from a clean tree.
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest -q

# 2. The corpus is the one the generator makes.
uv run python scripts/make_fixtures.py --check      # "OK: 24 files reproduced byte-for-byte"

# 3. The benchmark data matches the code that produced it.
uv run python -m benchmarks.run --out benchmarks/results/$(date +%F) --repeats 5 --allow-network
#    Check the manifest says `"git_dirty": false`. If it does not, something
#    outside benchmarks/results/ is uncommitted and the run is a measurement of
#    an unrecorded tree.

# 4. The version is set in ONE place. hatchling reads it from the source.
grep '__version__' src/tokenmill/__init__.py

# 5. CHANGELOG.md has a `## [x.y.z] - YYYY-MM-DD` section. The release
#    workflow lifts the notes straight out of it; no section, no notes.

# 6. Build and check the way PyPI will.
uv build
uv tool run --from twine twine check --strict dist/*

# 7. Install the WHEEL somewhere with no source tree and make it convert.
#    A source tree in the working directory is exactly how a packaging bug
#    hides: `import tokenmill` finds `src/` and passes.
python -m venv /tmp/relcheck
/tmp/relcheck/bin/pip install dist/tokenmill-*.whl
cd /tmp && /tmp/relcheck/bin/tokenmill --version && /tmp/relcheck/bin/tokenmill backends
```

CI does steps 6 and 7 for you across nine OS/Python cells, and builds both
container targets, but do step 7 by hand once anyway. It is the step that
catches the mistakes the others cannot.

### The tag

```bash
git tag -a v0.1.0 -m "tokenmill 0.1.0"
git push origin v0.1.0
```

That fires `.github/workflows/release.yml`, which builds, verifies, builds both
container images, and **drafts** a GitHub Release with the artefacts attached.
It does not publish anything.

### Publishing, which is a separate act

**A version number is spent the moment PyPI accepts it.** There is no
republishing and no undo, which is why a tag push cannot reach the publish job.

```
Actions -> Release -> Run workflow
  publish:    true
  repository: testpypi        # then, having installed from there, pypi
```

Then install from TestPyPI in a clean environment and convert something before
running it again against `pypi`.

**One-time setup on PyPI, before the first publish.** Publishing uses trusted
publishing (OIDC), so no API token is stored in this repository and there is
nothing to leak or rotate. On PyPI: *Your projects -> tokenmill -> Manage ->
Publishing -> Add a new publisher*, GitHub, owner `RSD-Studio`, repository
`tokenmill`, workflow `release.yml`, environment `pypi` (and the same again for
`testpypi` on test.pypi.org). Until that exists the publish job fails at the
credential exchange, having published nothing — which is the correct failure.

### After

- Publish the drafted GitHub Release once you have read its notes.
- Open a new `## [Unreleased]` section in `CHANGELOG.md`.
- Bump `__version__` for the next cycle.
