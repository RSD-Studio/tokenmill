# Contributing to tokenmill

Thanks for looking. tokenmill is early — see [`PROGRESS.md`](PROGRESS.md) for
what actually exists today and [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md)
for where it is going.

## Setting up

```bash
git clone https://github.com/RSD-Studio/tokenmill
cd tokenmill
uv venv
uv sync --extra dev --extra fixtures --extra documents
uv run pre-commit install
uv run python scripts/make_fixtures.py
```

`--extra documents` is worth having locally: without it the MarkItDown and
Kreuzberg integration tests skip, and mypy sees `Any` for their adapters. The
`docling` extra is deliberately not in that line — it resolves to 122 packages
and about 5.2 GB.

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
uv run pytest -q -m heavy      # GPU or multi-gigabyte model downloads (docling's PDF path, Phase 9)
uv run pytest -q -m compress   # the compress extra plus a model (Phase 6)
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
   `tokenmill.backends.documents._common` so the warning reaches the user as a
   warning rather than as a broken backend. Likewise, an empty result is not a
   success: say so with `warn_on_empty_output`.

Post-processors and tokenizers work the same way, through the
`tokenmill.postprocessors` and `tokenmill.tokenizers` groups. A post-processor
that can discard information the user might have wanted must set
`destructive = True`; the default chain is built by excluding those, so it
cannot damage a document.

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

*(Fills out in Phase 11 when publishing exists.)*
