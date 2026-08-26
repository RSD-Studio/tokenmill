# Handover: Phase 7 (isolation and licence enforcement), then Phase 8 (GUI)

You are working on **RSD-Studio/tokenmill**, an open-source token-reduction
toolkit that wraps best-in-class OSS converters behind one interface and
measures what each one actually saves. I am the project owner.

Your assignment is **Phase 7**, then **Phase 8**, in that order, in one session,
on one branch. Then a re-evaluation. **Stop before Phase 9.** Do not begin the
GPU tier, however tempting the adjacency.

Phases 0–6 are complete and merged into `Main`. **CI is alive again** — read §2
before you plan anything, because it changes what "verified" means for the first
time in this project's history.

---

## 0. Read this first, in full, before writing any code

- **`PROGRESS.md`** — the whole thing. Long, and it is the memory of the
  project: what is verified, what is merely believed, what is blocked, and every
  decision I have already made.
- **`docs/REVIEW_PHASES_0_6.md`** — the re-evaluation at the end of the last
  session. Shortest path to what is actually true today. Its defect list (D2,
  D3, D4, D6, D7, S1–S4, N1–N8) is work you will otherwise rediscover.
- **`docs/DEVELOPMENT_PLAN.md`** — §1 (the architecture contract), then Phases
  7, 8 and 9. Read 9 so you know exactly where your boundary is.
- **`docs/ARCHITECTURE.md`** — the pipeline, the post-processor chain, the
  destructive flag, why backends do not measure, the fidelity package, the
  formats package, `compare`, and the isolation section written in Phase 1 that
  Phase 7 is finally implementing.
- **`docs/BACKENDS.md`** — the per-backend honesty document. Yours must match
  its standard: failure modes quoted from real output, each asserted by a test.
- **`docs/BENCHMARKS.md`** — read the **Units** section before you write a
  single percentage anywhere. It is about to change; see §3.
- **`docs/LICENSES.md`** — currently thin. Phase 7 completes it.
- **`docs/ADDING_A_BACKEND.md`** — the adapter contract, including the four
  entry point groups.
- **`CONTRIBUTING.md`** — especially "Rules that are not negotiable".
- **`benchmarks/README.md`** — three paragraphs, and the second one still
  governs every number you publish.

Then **restate the acceptance criteria for both phases in your own words**
before you start, so I can see we agree on what "done" means.

---

## 1. Hard constraints — these do not bend

The same seven that governed Phases 1 through 6. Each has already caught
something real.

1. **Open-source only.** No proprietary or hosted-only SaaS backends in the core
   product.
2. **Licence hygiene is an engineering requirement.** Permissive (MIT / Apache /
   BSD) tools may be imported into our process. **AGPL/GPL tools must never be
   imported — subprocess or service boundary only.** Non-commercial weights are
   excluded by default. `BackendInfo.__post_init__` already refuses to construct
   a copyleft backend claiming in-process isolation; do not weaken it.
   **Verify each licence against the installed package metadata at the moment
   you write the code**, not from `RESEARCH.md` and not from this prompt. Phase 2
   found `RESEARCH.md` wrong about a dependency count; Phase 3 found it
   incomplete about a licence tree; Phase 5 found the "official" TOON package was
   a stub whose `encode()` raised `NotImplementedError`. Assume it can be wrong
   again. **This constraint is the entire subject of Phase 7 — it stops being
   background and becomes the deliverable.**
3. **The core install stays light, CPU-only and conflict-free.** No PyTorch, no
   CUDA, no system-binary requirement in the default `pip install tokenmill`. The
   clean-core-install CI job (9 cells) is the standing guard — do not weaken it.
   Anything heavy goes behind an extra with a lazy import. Core is defect D4 and
   is still undecided; see §4.
4. **Nothing is done until it has been run and the output inspected.** Not
   "should work". Not "looks correct". Executed, output captured, result
   recorded. Two of the last session's real bugs came from reading what a
   post-processor actually emitted, and neither test suite caught them.
5. **Never break what already works.** Minimal correct changes. Check call sites
   before modifying a module others import. After any edit re-run the full suite,
   not just the new test. The Phase 1 architecture contract is settled; a
   breaking change to it needs my agreement first — **except the one I have
   already granted in §4.**
6. **Complete code, not sketches.** Imports, error handling, type hints,
   Google-style docstrings, and the tests, all in the same change. No
   `# TODO: implement`, no `pass  # rest omitted`, no placeholder returning
   `None`.
7. **No fabricated evidence.** Every token-savings number in code, docs, README
   or GUI either cites `docs/research/RESEARCH.md` with its source, or comes from
   our own measurement on our own corpus. Never invent a percentage. Never
   restate a vendor marketing claim as fact. Where you cannot measure, say so and
   leave the value null.

Also standing:

- **Do not route around the egress proxy.** Blocked hosts are an org egress
  policy, not a bug. Record the block; do not tunnel past it.
- **Do not open a pull request unless I ask for one.**
- **Stage deliberately.** `git add -A` after an unrelated command has bitten this
  project twice.
- **Record unverifiable items as unverified**, never as quietly done.
- **Report honestly.** If you get something wrong and later find out, correct it
  in the open in `PROGRESS.md` rather than editing it away. The last session had
  to do this once, about a claim in its own commit message; that is the standard.

---

## 2. What changed: CI is alive, and it immediately found things

**I made the repository public on 2026-08-26.** Actions minutes are free on
public repositories, and runs started scheduling runners for the first time since
run 24. Runs 25 through 80 never got a machine; **run 81 did.**

**This is the single biggest change to how you should work.** For three phases,
"verified" has meant "green on one Linux box". It now means what it should.
Three consequences, and you should act on all of them:

**(a) Real model tokens are available.** The `tokenizers` job passed 14 of its
16 tests in run 81, including every tiktoken one. `openaipublic.blob.core.windows.net`
is reachable **from CI** — it is still denied in the development sandbox, so
`--tokenizer bytes` remains your local unit. **Defect D3 — "the publishable
figure is unpublishable" — is now closeable, and closing it is a Phase 7 task.
See §3.**

**(b) Docling's PDF path passed.** Unverified since Phase 2, run 81's docling job
went green including the step that downloads layout models from
`huggingface.co`. Update `PROGRESS.md`, `docs/BACKENDS.md` and the backend status
table: it is verified, and say which run verified it.

**(c) CI found 24 real test failures in its first run**, all now fixed on the
branch this prompt ships with. Three were the last session's; twenty-one were
Phase 4 tests that asserted gitingest's behaviour unconditionally while the CI
job installed only the `documents` extra, so they had **never executed
anywhere**. The lesson is worth carrying: a suite that has only run on one
machine, with one set of extras, has verified less than its pass count suggests.

**One known flake, already handled, do not "fix" it again.** The blocking
`tokenizers` job hit five consecutive **HTTP 429** responses from
`huggingface.co` for `bert-base-uncased`. Anonymous Hub requests are
rate-limited per IP and runners share addresses. Only the rate-limit case skips;
any other failure still fails, and the tiktoken tests are untouched and strict.
**If you see that 429 again, it is infrastructure, not a defect.**

### Your first job, before any Phase 7 code

Confirm CI is green on `Main`, and if it is not, fix that first. A red default
branch makes every subsequent claim in this session unverifiable. Do not start
Phase 7 on a red `Main`.

---

## 3. Decisions I have already made — implement these, do not re-litigate

The last session left several open questions and recommended answers. **I am
accepting its recommendations.** They are decisions now. Where one is a breaking
change, this section is the sign-off constraint 5 requires.

**3.1 — Close defect D3 by publishing the real token figure. Do this early.**
`tests/unit/test_web_tokens_network.py` prints a line into the CI log
deliberately, of the form:

```
BENCHMARK boilerplate.html trafilatura o200k_base: <before> -> <after> tokens (<ratio> reduction)
```

Read that line out of a **green** CI run, and publish the `o200k_base` figure in
`docs/BENCHMARKS.md` beside the existing byte figure, citing the run number and
commit. The project's central claim has been unpublishable for six phases for
want of this. **Do not compute, estimate or infer it — read it out of captured
output, quote it, and say which run it came from.** The Units section stays; it
now describes two available units rather than one available and one blocked.

While you are there: the format comparison (CSV 216 / TOON 240 / markdown 332 /
keyvalue 456 / JSON 543 bytes) is bytes-only, and `RESEARCH.md`'s figures it sits
beside are tokens. **Add a `network`-marked test that measures those five
encoders in `o200k_base` and prints the numbers**, then publish those too. This
is the first time TOON's "42.6% fewer tokens" claim can be checked against our
own data in the unit the claim is made in.

**3.2 — Rename the default-chain mechanism. This is the breaking change, and it
is approved.** `PostProcessor.destructive` currently carries two meanings: "can
lose information" and "changes the document's shape". `chunk` loses nothing and
is flagged only to stay out of the default chain, which is a lie of convenience.

Introduce **`in_default_chain: bool`** as the mechanism `default_chain()` reads,
and keep `destructive` as honest documentation of what a processor can lose.
Update all eight processors, `docs/ARCHITECTURE.md`, `docs/ADDING_A_BACKEND.md`
and the registry-wide test. The invariant to preserve, stated over the whole
registry rather than per processor: **the default chain must still be exactly
`normalize_whitespace`.**

**3.3 — `--format toon` stays unimplemented. Amend the plan, not the code.**
`DEVELOPMENT_PLAN.md`'s Phase 5 verification snippet says
`convert tables.pdf --format toon`. TOON encodes the JSON data model and a prose
document is not that; the encoders re-serialise a **table**, which is what all of
`RESEARCH.md` Category 7's evidence is about. Correct that line in the plan and
note it in `PROGRESS.md`. `OutputFormat` keeps its two members.

**3.4 — Merge the two Markdown table parsers before you write Phase 7 code.**
`fidelity/markdown.py` and `formats/markdown_table.py` both parse pipe tables
with deliberately different strictness. One module, a strictness flag, one set of
tests. About an hour, and the right time is before a third one appears.

**3.5 — Decide the core install weight explicitly (defect D4).** Core grew 2.3×
in Phase 3 and nobody signed it off. Measure it in CI — the clean-core-install
job already reports what it pulled in — and write the number and a stated ceiling
into `docs/BENCHMARKS.md`. If you believe the ceiling should be different from
what you measure, say so and give the number; do not leave it undecided a fourth
time.

**3.6 — Leave D6, D7 and S1–S4 open.** None blocks Phase 7. Do not spend the
session on them.

**3.7 — Consider a `compress` CI job, and tell me what it would cost.** Phase 6's
success path has never run, purely because the sandbox cannot reach
`huggingface.co`. **CI can.** A manual-dispatch and weekly job, gated like the
docling one, could produce the first compression ratio this project has ever had
and close the largest verification hole in the repository. Before adding it,
measure what it costs — the install is 63 packages and about 4.7 GB, and the
runner has a disk budget the docling job already has a "Free disk space" step
for. **If it fits, add it and record the ratio. If it does not, say so with the
numbers and leave Phase 6 amber.** Either answer is fine; silence is not.

---

## 4. Phase 7 — isolation layer and licence enforcement

**Goal:** make AGPL/GPL and non-Python tools usable without contaminating the
codebase, as a first-class, tested mechanism. The plan says do not ship publicly
without this, and the repository is now public.

### Deliverables

- **`backends/isolated/`** — a hardened `SubprocessConverter`: binary discovery,
  version probe, argument construction, timeout and kill, temp-file lifecycle,
  stderr captured into `BackendFailed`, and **no `shell=True` anywhere**.
- **Adapters via subprocess:** **PyMuPDF4LLM** (AGPL), **Pandoc** (GPL),
  **LibreOffice headless** (MPL), each with an install-hint message.
- **An optional HTTP-service adapter mode** (talk to a `docling-serve`-style
  container), proving the pattern for Phase 9's GPU backends.
- **Licence enforcement in code:** a test asserting that no AGPL/GPL package is
  importable from our process namespace, and that every registered backend
  declares a licence tier. **CI fails if a copyleft package appears in a
  non-isolated adapter's imports.**
- **`docs/LICENSES.md` completed** with the tiering rules and the reasoning.

### Acceptance criteria

- A copyleft backend works via subprocess and is **never imported**.
- **The licence test catches a deliberately introduced violation.** Write that
  test case, confirm it fails as intended, then revert the violation. A test
  that has never been seen to fail has not been shown to work.
- Subprocess timeout and cleanup verified, **including on the failure path**.

### Exit gate

Licence isolation test suite green in CI; at least one copyleft backend
functioning purely out of process.

### Things I want you to get right

- **Write the enforcement test first.** It is the phase. Let the adapters follow
  it. A licence isolation mechanism that was never seen to catch anything is
  indistinguishable from one that does not work.
- **`tokenmill.backends._subprocess` already exists** and is deliberately sited
  one level above the tiers so Phase 7 can absorb it without a third rewrite of
  the call sites. `PROGRESS.md` lists exactly what it does not do: sandboxing,
  binary discovery beyond `PATH`, version probing, an allow-list, streaming.
  That list is your specification.
- **`repomix` and `code2prompt` are out of process because they are TypeScript
  and Rust, not because of their licences.** Both are MIT. That makes them safe
  practice: getting the isolation wrong on them carries no licence risk.
- **Version probing matters more than it looks.** tokenmill cannot currently say
  which Repomix produced a given pack, so a subprocess backend's provenance is
  weaker than a Python backend's. That is the gap that most affects reproducing a
  measurement, and Phase 10 will need it.
- **Every new backend arrives with a fidelity score.** `tokenmill compare` exists
  now. `docs/REVIEW_PHASES_0_6.md` §3 has a corpus table with tokens beside
  fidelity for every installed backend; each adapter you add gets a row in it on
  the day it lands. PyMuPDF4LLM against pdfplumber on `tables.pdf` is the
  comparison that will tell you whether the AGPL tool is worth its isolation.
- **Expect the platform matrix to bite.** Pandoc and LibreOffice are system
  binaries with different names, paths and exit codes on three operating systems.
  This is the first phase written with a working 9-cell matrix; use it, and mark
  a backend unavailable rather than guessing at a path.

---

## 5. Phase 8 — GUI (FastAPI + NiceGUI)

**Goal:** the product a non-programmer can actually use.

**Stack decision, already made in `RESEARCH.md` and the plan:** NiceGUI over a
FastAPI backend. Record the rationale in `docs/ARCHITECTURE.md`: event-driven
rather than Streamlit's full-script-rerun model (which fights live batch progress
and streaming token counters); FastAPI in-process means the same app can expose
an API and orchestrate subprocess and service backends; NiceGUI `native` mode
gives a desktop window without leaving Python. A PySide6 shell remains a Phase 11
option.

### Deliverables

- **Layout:** source panel (drag-and-drop files/folders, URL box, repo picker,
  text paste) · backend selector showing availability, licence and a CPU/GPU
  badge · options panel (post-processors, format, tokenizer) · results panel.
- **The token panel is the centrepiece:** before → after, delta, percentage,
  per-stage breakdown, and an optional cost estimate **with user-supplied rates
  only**.
- **Batch queue:** multi-file, per-item status, cancel, resume, per-file and
  aggregate totals, background execution that never blocks the UI.
- **Preview** with rendered-Markdown / raw-source toggle and a before/after diff.
- **Comparison view:** one input, several backends side by side with tokens,
  timing and output. `core/compare.py` already does this; the GUI renders it.
  **Show fidelity beside tokens**, or it is a machine for picking the worst
  backend.
- **Export:** single file, batch to folder, ZIP, copy-to-clipboard.
- **Settings:** tokenizer default, cache location, backend preference order,
  network policy, theme.
- **Graceful degradation:** unavailable backends greyed out with an install hint,
  never hidden and never crashing.
- **`tokenmill gui`** launches it; `--server` for LAN/headless use.

### Acceptance criteria

- Every core CLI capability is reachable from the GUI.
- A **20-file batch** runs with a responsive UI and correct aggregate totals.
- Backend failure surfaces as a readable, actionable message.
- **Works with only the `core` extra installed** (most backends simply show
  unavailable).

### Exit gate

Batch run completed and inspected; screenshots captured for the docs; core-only
install renders correctly.

### Things I want you to get right

- **The GUI may only call the public library API.** A test that drives every GUI
  action through that same API keeps the boundary honest. This is the phase's
  named risk and the plan is explicit about it.
- **Test the API layer programmatically.** Use headless browser tests
  (Playwright) only for the few flows worth the maintenance cost. A browser is
  already available in the sandbox — Chromium 1194, via the crawl4ai work.
- **The batch runner is where five pieces of process-global state come due.**
  Defect D2: three `warnings.catch_warnings` uses, `os.environ`, the stdlib root
  logger's handlers and level, and loguru's activation registry — plus a fourth
  `catch_warnings` the compressor added. **None is thread-safe.** You cannot
  simply run `Pipeline.run` on a thread pool. Read `docs/REVIEW_PHASES_0_6.md`
  §4 before you design the queue, and if a process pool is the answer, say so and
  measure the cost.
- **A post-processor cannot warn or attach metadata** (defect N2).
  `process(text, options) -> str` is the whole contract, where a backend gets a
  `ConversionContext`. The GUI will want a post-processor to be able to say
  something. Fixing it is a breaking change to the Phase 1 contract: **propose
  it, do not do it unilaterally.**
- **Cost estimation takes rates from the user and never ships a rate table.**
  Prices change and a stale one in our repo becomes a lie. No rates, no estimate.

---

## 6. The traps — things that will bite you

Each cost real time in a previous phase, or was found while writing this.

1. **A green suite on one machine has verified less than its pass count.** CI's
   first working run found 21 tests that had never executed anywhere. When you
   add a backend behind an extra, add the extra to the CI test job too, or its
   tests silently skip on all nine cells.
2. **`filterwarnings = ["error"]` is in force.** Phase 2 lost a CI round to
   onnxruntime warning about Windows; Phase 4 lost one to pathspec's deprecation
   of a factory name. Use `warnings_as_conversion_warnings` from
   `tokenmill.backends._common` to forward a warning the user can act on, and a
   scoped message filter for a library's internal deprecation churn. The
   distinction is drawn in `docs/ARCHITECTURE.md`; **do not blanket-suppress.**
3. **Do not add a sixth kind of process-global state without telling me.** The
   count is in `docs/REVIEW_PHASES_0_6.md` §4 and its trajectory is defect D2.
   The last session avoided `HF_HUB_OFFLINE` by passing `local_files_only`
   through a config dict instead; that is the standard to hold.
4. **Never `shell=True`.** Phase 7 is the phase where this stops being advice.
   `ext::` in a git URL makes git execute an arbitrary command, which Phase 4
   already had to refuse at two layers; assume every subprocess argument is
   hostile.
5. **Verify licences from installed metadata at the moment you write the code.**
   Phase 5 found the package under the TOON format's own GitHub organisation was
   a stub. Phase 6 read llmlingua's licence out of the wheel's `METADATA` and
   bundled `LICENSE` rather than installing 4.7 GB. Both are acceptable; a
   `RESEARCH.md` citation is not.
6. **New fixtures go through the generator.** `scripts/make_fixtures.py` builds
   the corpus and `--check` currently reports **24 files** byte-for-byte.
   `tests/fixtures/sample_repo` contains a real `.git` and a
   deliberately-uncommitted `secrets.env`. **Never drop files into
   `tests/fixtures/` by hand.**
7. **The sandbox still cannot reach `huggingface.co`,
   `openaipublic.blob.core.windows.net` or `download.pytorch.org`.** CI can.
   Locally you measure in `--tokenizer bytes`; the model-token figures come out of
   a CI log. Re-probe at the start of the session rather than assuming either way.
8. **`compare` must not become a leaderboard.** Rows stay in preference order and
   fidelity sits beside tokens. On `tables.pdf` the cheapest backend is the one
   that destroys the table. The GUI must not undo that by sorting the comparison
   view by size.
9. **The repository is public now.** Anything you commit is visible immediately.
   No credentials, no internal hostnames, no tokens — including in the fixture
   corpus and in any GUI screenshot you capture for the docs.

---

## 7. Then: stop, and report

After Phase 8's exit gate, and **before any Phase 9 work**:

- **Write `docs/REVIEW_PHASES_0_8.md`**, superseding `REVIEW_PHASES_0_6.md` and
  keeping it in the repository — its defect numbering is referenced everywhere,
  and a superseded review that disappears is one nobody can check.
- Cover the new acceptance criteria, the defects you closed (D2, D3, D4, N1–N8
  are all still open or partly open), and any new ones **including the ones you
  introduce**.
- **Re-run the whole corpus end to end and give me the table** — every fixture,
  every backend, tokens beside fidelity, **now with a model-token column**. That
  table is the thing this project has been building towards, and this is the
  first time it can carry the unit the claim is actually about.
- A recommendation on whether Phase 9 should start, and what to repair first.

Then stop and report to me. **Do not start Phase 9.**

---

## 8. Definition of done, per phase

Before you tell me a phase is complete:

```
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=tokenmill
uv run python scripts/make_fixtures.py --check
```

All green, **plus a green CI run on the branch** — that is now available and is
no longer an excuse. Plus:

- The sandbox-verification commands from the plan for that phase, run, with the
  output **pasted** into `PROGRESS.md` — not summarised, pasted.
- `docs/BACKENDS.md` updated where a backend's behaviour changed, and **a new
  section per isolated backend** documenting what it destroys, with a test
  asserting each documented failure and a message saying what to update when
  upstream fixes it. That is the Phase 2 standard and it is not optional.
- `docs/BENCHMARKS.md` updated with every new measurement, its **unit stated**,
  and a fidelity figure beside every token figure.
- `docs/LICENSES.md` completed (Phase 7).
- `PROGRESS.md` updated: status at a glance, a verification-log entry with
  captured output, backend and post-processor status tables, decisions made,
  deferred work, and any new open questions for me.
- `CHANGELOG.md`, `README.md`, `docs/ARCHITECTURE.md` and
  `docs/ADDING_A_BACKEND.md` updated where the change touches them.
- Commits pushed. Coherent commits — one logical change each, message describing
  what that commit actually does.

---

## 9. Git — one branch, and I mean one

All of this work goes on **a single branch**, cut from the current default branch
(`Main`, capital M — the CI triggers and the changelog URLs account for that).

**Do not create a second branch.** Not per phase, not for the review. Two pieces
of work, one branch, sequential commits. If your harness assigns its own branch
name, use that one branch for everything.

Push as you go rather than in one lump at the end; the container is ephemeral and
unpushed work is lost work. **Watch the CI run after each push** — it works now,
and a red branch caught early is ten minutes instead of a session.

**Do not open a pull request.** Report to me when you stop, and I will merge.

---

## 10. Ask me when it matters

If two readings of this assignment would produce materially different work,
**ask** — with the options and your recommendation, not an open question. The
three most likely candidates:

1. **Whether the `compress` CI job fits the runner's disk budget** (§3.7), and if
   not, what you propose instead.
2. **Whether `PostProcessor.process` should take a context** (defect N2). It is a
   breaking change to the Phase 1 contract and Phase 8 is what makes it hurt.
   Propose; do not act.
3. **How far the HTTP-service adapter mode should go.** The plan calls it
   optional and says it proves the pattern for Phase 9. If it is turning into a
   phase of its own, stop and tell me.

Everything else, use your judgement and write down what you decided and why.

Do the work in the order given: **Phase 7, then Phase 8, then the review.** If
you run short of room, the order is also the priority order — a complete,
tested, CI-green Phase 7 is a far better outcome than two half-finished phases.
Say what you did not get to. **Stop before Phase 9.**
