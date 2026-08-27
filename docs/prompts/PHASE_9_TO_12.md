# Phases 9 → 12: finish it

You are working on RSD-Studio/tokenmill, an open-source token-reduction toolkit
that wraps best-in-class OSS converters behind one interface and measures what
each one actually saves. I am the project owner.

**This is the last assignment.** Phases 9, 10, 11 and 12, in that order, plus six
repairs that come first. At the end tokenmill is a released v0.1.0 with its own
benchmark data and documentation someone can learn it from. There is no Phase 13
and no follow-up prompt: whatever you do not finish, I finish or drop.

Phases 0–8 are complete and CI is green across all 25 jobs. Read §2 before you
plan, because for the first time in this project the starting position is a green
branch and that changes what you should spend your caution on.

---

## 0. Read this first, in full, before writing any code

* `PROGRESS.md` — the whole thing. Long, and it is the memory of the project.
* `docs/REVIEW_PHASES_0_8.md` — the re-evaluation at the end of the last session,
  and the shortest path to what is true today. Its defect list (D2, D6, D7,
  N1–N15, S1–S4) is your repair backlog and I have made decisions about most of
  it in §3.
* `docs/DEVELOPMENT_PLAN.md` — §1 (the architecture contract), then Phases 9
  through 12, then §4 (cross-cutting standards) and §5 (definition of done).
* `docs/ARCHITECTURE.md` — the pipeline, the isolation section Phase 7 wrote,
  the GUI section Phase 8 wrote, and the two flags on a post-processor.
* `docs/LICENSES.md` — the tiering rules and the four enforcement checks. Phase 9
  is the phase those checks were built for.
* `docs/BACKENDS.md` — the per-backend honesty document. Yours must match its
  standard: failure modes quoted from real output, each asserted by a test.
* `docs/BENCHMARKS.md` — the Units section especially. Phase 10 rewrites most of
  this page; read what it currently claims before you replace it.
* `benchmarks/README.md` — three paragraphs, and Phase 10 is where its second one
  finally becomes enforceable.
* `CONTRIBUTING.md` — "Rules that are not negotiable".

Then restate the acceptance criteria for all four phases in your own words, and
tell me your intended ordering, before you start.

---

## 1. Hard constraints — these do not bend

The same seven that have governed every phase. Each has caught something real.

1. **Open-source only.** No proprietary or hosted-only SaaS backends in the core
   product.
2. **Licence hygiene is an engineering requirement.** Permissive (MIT / Apache /
   BSD) may be imported. AGPL/GPL never — subprocess or service boundary only.
   Non-commercial weights excluded by default. Verify each licence against the
   **installed package metadata at the moment you write the code**. Phase 7 found
   `RESEARCH.md`'s "PyMuPDF4LLM: AGPL-3.0" was half the story — the package says
   `Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License`, and that
   difference broke the licence classifier in a way that would have declared the
   flagship copyleft tool importable. **Phase 9 is the phase with the most
   licence surface in the whole project**: Marker is GPL, Surya is GPL, and
   several model weights are non-commercial. Assume `RESEARCH.md` is wrong again.
3. **The core install stays light, CPU-only and conflict-free.** The ceiling is
   **250 MB** and CI enforces it on nine cells; it currently measures 140.6 MB.
   Phase 9 must not move that number at all — `heavy = []` stays empty forever.
4. **Nothing is done until it has been run and the output inspected.** Not
   "should work". Executed, output captured, result recorded. Phase 8's two worst
   bugs — an upload that completed and did nothing, and an error message clipped
   mid-sentence — were both invisible to a passing test suite and obvious in a
   screenshot.
5. **Never break what already works.** Minimal correct changes; check call sites;
   re-run the full suite, not just the new test. Breaking changes to the Phase 1
   contract need my agreement — except the one I grant in §3.3.
6. **Complete code, not sketches.** Imports, error handling, type hints,
   Google-style docstrings, and the tests, in the same change. No
   `# TODO: implement`.
7. **No fabricated evidence.** Every token-savings number either cites
   `docs/research/RESEARCH.md` with its source, or comes from our own measurement
   on our own corpus. Never invent a percentage. Never restate a vendor claim as
   fact. **Phase 10 is the phase where this constraint stops being defensive and
   becomes the product.**

Also standing:

* Do not route around the egress proxy. Record the block; do not tunnel past it.
* Do not open a pull request unless I ask.
* Stage deliberately. `git add -A` after an unrelated command has bitten this
  project twice.
* Record unverifiable items as unverified, never as quietly done.
* Report honestly. If you get something wrong and later find out, correct it in
  the open in `PROGRESS.md` rather than editing it away. The last session did
  this twice — about a start-up cost it had guessed at, and about a test that
  passed for the wrong reason. That is the standard.

---

## 2. Where you are starting from, and what is different

**CI is green.** Run 97, 25 jobs, on commit `49076d0`, and run 98 green again on
the branch head `5481bfa`. That has never been true before at the start of a
session. Verify it yourself rather than taking this paragraph's word for it — the
branch is `claude/phases-7-8-734pty` and it has not been merged to `Main` yet, so
your first job is to confirm which of the two you are cutting from and that it is
still green.

Three consequences:

**(a) A red run is now information, not noise.** For three phases a failure could
plausibly have been infrastructure. It cannot now. If you turn the branch red,
you did it, and the previous session's six-run route to green is in `PROGRESS.md`
as evidence that reading the failure is faster than re-running it.

**(b) The matrix has caught four defects a single Linux box could not**, and the
most instructive is worth repeating: a test passed on the development machine
*because* the previous session had installed Pandoc to verify a different thing.
A well-equipped machine is worse at catching that class of bug than a bare one.
So: **run the suite twice**, once with your tools and once without. Hiding
`/usr/bin/pandoc` and pointing `HOME` away from the AGPL virtualenv reproduced a
CI failure in sixty seconds. Phase 9 adds seven more optional runtimes; this
technique is going to earn its keep repeatedly.

**(c) The `compress` and `docling` jobs are gated to `workflow_dispatch` and the
Sunday schedule, and no session can dispatch one** — `POST .../dispatches`
returns `403 Resource not accessible by integration`. Two sessions have now hit
this. **I will dispatch them for you.** Ask, early, in your first report; do not
build around it and do not claim a result you did not see.

**The egress position is unchanged and re-probe it anyway.** `huggingface.co`,
`openaipublic.blob.core.windows.net` and `download.pytorch.org` are denied in the
sandbox. Locally you measure in `--tokenizer bytes`; model-token figures come out
of a CI log. **This is the central constraint on Phase 9**, whose backends are
all model downloads, and on Phase 10, whose headline numbers should be in tokens.

---

## 3. Decisions I have already made — implement these, do not re-litigate

Your last review made recommendations and raised five open questions. I am
accepting the recommendations. These are decisions now, and where one is a
breaking change this section is the sign-off constraint 5 requires.

### 3.1 — Repair `--server` before Phase 9 (defect N15). **Blocking.**

`tokenmill gui --server` binds `0.0.0.0` with no authentication, no CSRF
protection, no rate limit, and an upload endpoint that writes to disk. Your
review is right that shipping that into the phase whose backends live on other
machines is the wrong order.

**Implement the shared-token option you recommended.** A token from config or an
environment variable, required on every request when `--server` is set, refused
with 401 otherwise. Generate one and print it at startup when the user has not
set one, so the secure path is the default path rather than the diligent one.

Be precise in the docs about what this is not: no TLS, no user accounts, no
audit. It stops a machine on the same network reading your documents. Say that
plainly rather than letting "authentication" imply more.

### 3.2 — Fix D2 before Phase 10. **Blocking that phase, not Phase 9.**

Four uses of `warnings.catch_warnings`, plus `os.environ`, the stdlib root
logger's handlers and level, and loguru's activation registry. None thread-safe,
which is why the batch queue is serial and why `DEVELOPMENT_PLAN.md` §4's
"batch runs should parallelize across files" is currently not true.

The plan's own performance standard and Phase 10's harness both want
parallelism, so this is the moment. The shape you proposed is right: make the
adapters stop reaching for global state. `warnings.catch_warnings` inside a
conversion is the main offender; the gitingest logging reconfiguration is the
ugliest.

**Measure the result rather than asserting it.** A 20-file batch is 3.0 s serial
today. Publish the parallel figure beside it in `docs/BENCHMARKS.md`, and if
parallelism turns out not to help — plausible, since several backends are already
subprocess-bound — say so and keep the serial queue. An honest null result is the
more useful outcome here and this project has published several.

### 3.3 — `PostProcessor.process` takes a context (defect N2). **Approved
breaking change.**

Do it, in the shape you proposed: a new optional third parameter, with the
registry passing a context only to processors that declare they accept one. A
third-party post-processor written against the Phase 1 contract keeps working
untouched. Uglier than a clean break and it does not break anyone, which is the
trade this project has made before and should make again.

The compressor is the immediate beneficiary — it can attach its achieved ratio
instead of logging it — and Phase 10's harness wants per-processor metadata.

### 3.4 — Rename the isolation layer (defect N9).

You are right that "isolation" invites a security reading it does not deserve,
and right that renaming after Phase 9 subclasses it is expensive. Do it now,
before Phase 9's adapters land on top of it.

I am not going to pick the name — you have read the code more recently than I
have. Pick one that does not imply a sandbox, say why in `ARCHITECTURE.md`, and
keep `IsolationMode` as the enum name if that is the smaller diff; it is the
*package* and the prose that oversell.

### 3.5 — CI installs Pandoc and LibreOffice on the ubuntu cell.

Yes. You were right to flag that it changes what the matrix is for, and I am
deciding it is worth it: three backends whose conversion paths have run on
exactly one machine is the same condition the Phase 0–6 review complained about
for the whole project, and ninety seconds of `apt install` retires it.

Build the AGPL virtualenv in a step too, so `pymupdf4llm` is exercised. That
means installing an AGPL package in CI, which is fine — the licence rule is about
what tokenmill imports, and a separate virtualenv is exactly the boundary the
rule asks for. Your own environment check will need to keep ignoring it, which it
already does by construction since it audits *our* environment.

### 3.6 — Clean up uploads (N14), and finish D6, N4 and N5.

- **N14**: uploads staged by the GUI are never removed. Bound them — by age or by
  count, your choice — and say which in the docs.
- **D6**: `repomix --style json` is still unused; use it or delete the note.
- **N4**: `compare --formats` re-encodes only the first table in a document.
  Fine on the fixtures, wrong on a real report.
- **N5**: `aggressive_whitespace` has never demonstrated a benefit on this
  corpus — +0.0%, +0.0%, −0.1%. **Either find input where it earns its place and
  publish that, or delete it.** A post-processor that does nothing measurable is
  a maintenance cost and an implied claim. I would lean towards deleting it, and
  I would rather see the measurement than my lean.

### 3.7 — Leave D7, N7, N8 and S1–S4 to their phases.

N7 (single unrepeated timings) is Phase 10's, and Phase 10 must fix it — a
benchmark harness that reports one run of each cell is not a benchmark. N8
(fidelity has no metadata component) is a real gap with two independent
instances now; add the component in Phase 10 if the corpus work makes it cheap,
and say so if it does not. The rest can stay open.

---

## 4. Phase 9 — heavy backends (GPU tier, install-docs-only)

**Goal:** support the high-quality ML converters without ever putting them in our
dependency tree.

**This phase is mostly plumbing you have already built.** Phase 7's
`SubprocessConverter` (allow-list, version probe, workspace lifecycle) and
`ServiceConverter` (tested against a real HTTP server, nothing auto-discovered)
are what these adapters subclass. The pattern for a copyleft Python package in a
virtualenv of its own is established and working. Do not rebuild any of it.

**Deliverables**

* Adapters for **Marker** (GPL + RAIL weights), **MinerU**, **olmOCR**,
  **Surya** (GPL), **DeepSeek-OCR**, **dots.ocr**, **Granite-Docling** — each via
  the isolation layer, never a declared dependency.
* A `tokenmill doctor` command reporting what is installed, GPU availability,
  VRAM, and precise per-backend install instructions.
* Optional `docker/` compose files, one service per heavy backend, with the
  adapter auto-detecting a running service — *detecting one it was told about*,
  not scanning for one.
* Honest documentation of hardware needs and the RAIL/GPL licence conditions.
* **DeepSeek-OCR gets special treatment in the docs.** Its optical context
  compression is the most on-theme token-reduction story in the project. Report
  our own observed compression on our own fixtures; cite the paper's numbers as
  the paper's numbers.

**Acceptance criteria**

* Every heavy adapter degrades cleanly to "unavailable + how to install" on a
  CPU-only machine.
* `tokenmill doctor` output is accurate on the sandbox.
* At least one heavy backend verified working **if** the sandbox has a GPU; if
  not, document that it is untested and say so plainly in `PROGRESS.md`.

**Exit gate:** CPU-only degradation verified; unverified-on-hardware items
explicitly flagged, not quietly marked done.

**Things I want you to get right**

* **This sandbox has no GPU and cannot reach the model hosts.** Expect to ship
  most of this phase unverified, and expect that to be the correct outcome rather
  than a failure. Phase 6 ended amber for the same reason and was recorded
  honestly; do that again. What you *can* verify is the whole absent-runtime path,
  which is what almost every user will experience.
* **The licence surface is the largest in the project.** Marker's weights are
  RAIL, not GPL, and the two conditions differ. Jina's ReaderLM weights are
  CC-BY-NC and excluded by default. Check each one against what is actually
  published, record the tier, and let the Phase 7 checks do their job.
* **`heavy = []` stays empty.** If you find yourself adding a dependency there,
  stop and re-read `CONTRIBUTING.md` rule 1.
* **`doctor` must not lie about a GPU.** On a machine with CUDA present but no
  usable card, say that. On a Mac with MPS, say that. The command exists to stop
  someone spending an hour installing Marker on hardware that cannot run it.

---

## 5. Phase 10 — the benchmark harness

**Goal:** produce our own measured evidence — the thing no existing project has.
This is the phase the whole build has been pointing at.

**Deliverables**

* `benchmarks/` harness: corpus × backends × formats, capturing tokens under
  **multiple tokenizers**, wall time, peak memory, and failures.
* **Repeated runs.** Defect N7: every timing published so far is a single
  unrepeated run. Report a median and a spread, and state N.
* **Fidelity scoring in every cell**, not just token counts. The scorer exists;
  use it. Token savings without a fidelity axis is not a result and the harness
  must make that structurally impossible to publish.
* Reproducible: one command regenerates everything; results committed under
  `benchmarks/results/<date>/` as CSV, JSON and Markdown.
* `docs/BENCHMARKS.md` rewritten around the real data, with an explicit
  limitations section: hardware, sample size, tokenizer choice, and what could
  not be tested.

**Acceptance criteria**

* A full run completes unattended and is re-runnable by a third party.
* Results include failures and bad outputs, not just the wins.
* **Every published number traces to a committed raw result file.** This is the
  rule `benchmarks/README.md` set in Phase 0 and that the project has been unable
  to honour for ten phases — until now every figure has been "asserted by a test",
  which the page says out loud is the weaker guarantee.

**Exit gate:** a complete result set committed; `docs/BENCHMARKS.md` written with
limitations; no unsourced claim anywhere in the repository.

**Things I want you to get right**

* **The model-token columns have to come out of CI.** The sandbox cannot reach a
  tokenizer vocabulary. Design the harness so a run can be executed in CI and its
  raw results committed from there, or so a byte-unit run locally and a token-unit
  run in CI merge into one table. Do not publish a byte figure in a token column;
  the last session found the two disagree by 24 points on tabular data and do not
  even rank the formats the same way.
* **The harness treats every backend identically**, including ours-by-preference.
  A result that contradicts `RESEARCH.md` gets reported as-is with a note.
* **Publish the failures.** `corrupt.pdf` failing five ways and `scanned.pdf`
  returning nothing are results. A benchmark that reports only successful cells
  is a marketing document.
* **The most quotable line in the repository is currently
  `jsrendered.html | trafilatura | −90.7% | fidelity 0.000`.** Make sure the
  harness produces rows like that and that the report does not bury them.
* **Do not let the corpus grow to flatter the tool.** New fixtures go through
  `scripts/make_fixtures.py`, `--check` must still pass, and a fixture added
  because a backend does well on it is a thumb on the scale.

---

## 6. Phase 11 — packaging, distribution, release

**Goal:** installable and runnable by someone who has never opened a terminal.

**Deliverables**

* PyPI publish workflow (trusted publishing), version via tags, `CHANGELOG.md`
  reconciled.
* `pipx` / `uv tool install` documented as the recommended path.
* Docker image (core) and compose profiles for the heavy backends.
* Release checklist in `CONTRIBUTING.md`, and a smoke test that installs the
  built artefact in a clean container and runs one conversion.
* **A statement of what the distributed artefact contains**, which
  `docs/LICENSES.md` has owed since Phase 7. Nothing copyleft is vendored today;
  say so explicitly at the moment there is a wheel.

**Acceptance criteria**

* Clean container: install from the built wheel, run a conversion, get correct
  output.
* Docker image runs the GUI and is reachable.
* Version, changelog and tag agree.

**Exit gate:** clean-container install verified end to end; **v0.1.0 tagged**.

**Decisions for this phase**

* **PySide6 / PyInstaller is out of scope.** The plan lists it as optional and
  asks me to decide before you start: I am deciding no. It is a real maintenance
  commitment for an audience we have not confirmed exists, and `nicegui --native`
  already gives a desktop window. Record it as deferred with that reasoning.
* **Do not publish to PyPI.** Build the artefact, test it in a clean container,
  wire the workflow, and stop. I will run the publish. Tag `v0.1.0` so the
  workflow has something to fire on.

---

## 7. Phase 12 — documentation completion and the article support pack

**Goal:** the repository teaches itself, and the article has everything it needs.

**Deliverables**

* README finished: positioning, the sourced token-reduction case, the backend
  matrix, GUI screenshots, quickstart, licence tiering, and an honest comparison
  to omniparse, docling-serve and the MarkItDown GUI forks — what we do
  differently and what they do better.
* `docs/BACKENDS.md` complete: observed failure modes for **every** backend.
* `docs/ADDING_A_BACKEND.md` with a complete working example a contributor can
  copy, covering all four entry point groups and both isolation modes.
* `docs/FAQ.md`: which backend for which format, why is X unavailable, GPU or
  not, **is my data sent anywhere (no)**, licence questions.
* **Article support pack** (`docs/article/`): the benchmark tables as
  copy-paste-ready Markdown, chart-generation scripts, a **claims file mapping
  every factual statement to its source** (ours or `RESEARCH.md`), and a
  "surprising findings" note.
* Final `PROGRESS.md` pass: everything reconciled, deferred work listed with
  reasons.

**Exit gate:** a reader unfamiliar with the project can install it, convert a
file, add a backend, and reproduce the benchmark using only the docs.

**Things I want you to get right**

* **The claims file is the deliverable I care most about.** Every number in the
  README and on the benchmarks page, mapped to the run or the citation it came
  from. If a claim cannot be mapped, it comes out.
* **The "surprising findings" note writes itself from this project's history** and
  is the most valuable thing the article can carry. Candidates already in the
  record: the cheapest backend destroying the table on four of eleven fixtures; a
  −90.7% reduction at fidelity 0.000; TOON's published 42.6% measuring 29.9% on
  our data; a byte figure overstating a token saving by 24 points; `keyvalue`
  being 16% smaller than JSON and more expensive; `aggressive_whitespace` saving
  nothing; chunking *costing* 1.8%.
* **Do not oversell the isolation layer.** It is a licence and language boundary
  with no sandboxing, and the FAQ is exactly where someone will assume otherwise.

---

## 8. The traps — things that will bite you

Each cost real time in a previous phase.

1. **A green suite on one machine has verified less than its pass count.** Run it
   twice — with your tools and without. Phase 9 adds seven optional runtimes and
   this is the phase where that technique pays for itself.
2. **`filterwarnings = ["error"]` is in force.** Phase 2 lost a round to
   onnxruntime, Phase 4 to pathspec, Phase 7 to `PackageMetadata.__getitem__`
   being deprecated — where **mypy pushed towards the deprecated API** and only
   the matrix caught it. Use `warnings_as_conversion_warnings` for a warning the
   user can act on and a scoped filter for a library's internal churn.
3. **Verify licences from installed metadata at the moment you write the code.**
   Phase 9 has the most licence surface in the project and `RESEARCH.md` has been
   wrong or incomplete four times now.
4. **Never `shell=True`.** Assume every subprocess argument is hostile.
5. **New fixtures go through the generator.** `--check` reports 24 files
   byte-for-byte. Never drop files into `tests/fixtures/` by hand.
6. **The sandbox cannot reach `huggingface.co`, `openaipublic.blob.core.windows.net`
   or `download.pytorch.org`.** Re-probe at the start rather than assuming.
7. **When you add a backend behind an extra, add the extra to the CI jobs that
   need it** — *all* of them. Phase 8 added `gui` to the test and coverage jobs
   and not to the types job, and CI failed one job of 25 with the whole matrix
   green.
8. **`compare` must not become a leaderboard**, and Phase 10's report must not
   either. Rows stay in preference order and fidelity sits beside tokens.
9. **The repository is public.** No credentials, no internal hostnames, no
   tokens — including in the fixture corpus, in any screenshot, and in the
   `--server` token you generate.
10. **Watch the CI run after each push.** It works, and a red branch caught early
    is ten minutes instead of a session.

---

## 9. Then: stop, and report

After Phase 12's exit gate:

* Write `docs/REVIEW_PHASES_0_12.md`, superseding `REVIEW_PHASES_0_8.md` and
  keeping it in the repository — its defect numbering is referenced everywhere.
* Cover every acceptance criterion across all thirteen phases, the defects you
  closed, the ones still open, and the ones you introduced.
* **The final corpus table**: every fixture, every backend, tokens beside
  fidelity, with a model-token column, and now with the harness's raw results
  behind it rather than a hand-run script.
* A frank assessment of what tokenmill is and is not good at, written for someone
  deciding whether to use it.
* Anything you did not get to, and what it would cost.

Then stop. This is the last phase.

---

## 10. Definition of done, per phase

```
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=tokenmill
uv run python scripts/make_fixtures.py --check
```

All green, **plus a green CI run on the branch**, plus:

* The sandbox-verification commands from the plan for that phase, run, with the
  output **pasted** into `PROGRESS.md` — not summarised.
* `docs/BACKENDS.md` updated where a backend's behaviour changed, with a new
  section per heavy backend documenting what it destroys, a test asserting each
  documented failure, and a message saying what to update when upstream fixes it.
* `docs/BENCHMARKS.md` updated with every new measurement, its unit stated, and a
  fidelity figure beside every token figure.
* `PROGRESS.md` updated: status at a glance, verification log with captured
  output, backend and post-processor status tables, decisions, deferred work, and
  any new open questions.
* `CHANGELOG.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/ADDING_A_BACKEND.md`
  and `docs/LICENSES.md` updated where the change touches them.
* Commits pushed. Coherent commits — one logical change each.

---

## 11. Git — one branch

All of it on a single branch, cut from `Main` (capital M — the CI triggers and
the changelog URLs account for that). Not one per phase. If your harness assigns
its own branch name, use that one branch for everything.

Push as you go; the container is ephemeral and unpushed work is lost work. Tag
`v0.1.0` in Phase 11. Do not open a pull request and do not publish to PyPI —
report to me when you stop and I will merge and release.

---

## 12. Ask me when it matters

If two readings would produce materially different work, ask — with the options
and your recommendation, not an open question. The likely candidates:

1. **Dispatching the `compress` and `docling` jobs.** You cannot; I can. Ask
   early, in your first report, and tell me exactly what to run against which
   branch.
2. **Whether a heavy backend is worth wrapping at all** if it turns out you can
   verify nothing about it. Seven adapters that all report "unavailable, install
   it yourself" may be six too many. If the honest answer after building one is
   that the rest add documentation and no capability, say so and stop at the ones
   that earn it — I would rather have three real adapters and a good `doctor`
   than seven stubs.
3. **What to do if D2 turns out to be bigger than it looks.** If unpicking the
   global state is a week rather than a day, tell me before you start Phase 10
   rather than half-finishing it. A serial harness that works beats a parallel one
   that does not.

Everything else, use your judgement and write down what you decided and why.

**Order is priority order.** The repairs, then 9, 10, 11, 12. If you run short of
room, a complete and CI-green Phase 10 with the benchmark data committed is worth
more than partial work on 11 and 12 — that data is the thing this project exists
to produce and the only part nobody else has. Say what you did not get to.
