You are working on RSD-Studio/tokenmill, an open-source token-reduction toolkit
that wraps best-in-class OSS converters behind one interface and measures what
each one actually saves. I am the project owner.

Your assignment is **a slice of Phase 10 (fidelity scoring), then Phase 5
(post-processing, formats, measurement depth), then Phase 6 (prompt
compression)** — in that order, in one session, on one branch. Then a
re-evaluation. Stop before Phase 7. Do not begin Phase 7's isolation layer or
licence enforcement, however tempting the adjacency.

The ordering is deliberate and it is not the plan's order. Read §3 for why.

---

## 0. Read this first, in full, before writing any code

- **`PROGRESS.md`** — the whole thing. It is long and it is the memory of the
  project: what is verified, what is merely believed, what is blocked, and every
  decision I have already made.
- **`docs/REVIEW_PHASES_0_4.md`** — the re-evaluation written at the end of the
  last session. It is the shortest path to knowing what is actually true today,
  and its defects list (D2–D9, S1–S4) is work you will otherwise rediscover.
- **`docs/DEVELOPMENT_PLAN.md`** — §1 (the architecture contract), then Phases 5,
  6, 7 and 10. Read 7 so you know exactly where your boundary is, and 10 because
  you are building a piece of it early.
- **`docs/research/RESEARCH.md`** — Categories 6 and 7 in full. Phase 5's format
  work and Phase 6's compression claims are both calibrated against it, and
  Category 7 is mostly a list of reasons to distrust the obvious number.
- **`docs/ARCHITECTURE.md`** — the pipeline, the post-processor chain, the
  `destructive` flag, why backends do not measure, and the one sanctioned
  exception Phase 4 introduced.
- **`docs/BENCHMARKS.md`** — small, partial, and the place your numbers go. Read
  its "Units" section before you write a single percentage anywhere.
- **`docs/BACKENDS.md`** — the per-backend honesty document. Yours must match its
  standard: failure modes quoted from real output, each asserted by a test.
- **`docs/ADDING_A_BACKEND.md`** — the adapter contract. Post-processors and
  tokenizers register through the same mechanism; follow it exactly.
- **`CONTRIBUTING.md`** — especially "Rules that are not negotiable".
- **`benchmarks/README.md`** — three paragraphs, and the second one is the whole
  reason the fidelity work comes first.

Then restate the acceptance criteria for all three pieces of work in your own
words before you start, so I can see we agree on what "done" means.

---

## 1. Hard constraints — these do not bend

The same seven that governed Phases 1 through 4. Each one has already caught
something real.

1. **Open-source only.** No proprietary or hosted-only SaaS backends in the core
   product.
2. **Licence hygiene is an engineering requirement.** Permissive (MIT / Apache /
   BSD) tools may be imported into our process. AGPL/GPL tools must never be
   imported — subprocess or service boundary only. Non-commercial weights are
   excluded by default. `BackendInfo.__post_init__` already refuses to construct
   a copyleft backend claiming in-process isolation; do not weaken it. **Verify
   each licence against the installed package metadata at the moment you write
   the code**, not from `RESEARCH.md` and not from this prompt. Phase 2 found
   `RESEARCH.md` wrong about a dependency count; Phase 3 found it incomplete
   about a licence tree. Assume it can be wrong again.
3. **The core install stays light, CPU-only and conflict-free.** No PyTorch, no
   CUDA, no system-binary requirement in the default `pip install tokenmill`.
   The clean-core-install CI job (9 cells) is the standing guard — do not weaken
   it. Anything heavy goes behind an extra with a lazy import. **Phase 3 already
   grew the core from 72 MB to 164 MB and nobody decided that was acceptable**
   (defect D4). Do not grow it further without telling me what it costs.
4. **Nothing is done until it has been run in the sandbox and the output
   inspected.** Not "should work". Not "looks correct". Executed, output
   captured, result recorded. A post-processor that deletes everything exits 0
   and scores a magnificent reduction — read the actual text.
5. **Never break what already works.** Minimal correct changes. Check call sites
   before modifying a module others import. After any edit re-run the full
   suite, not just the new test. The Phase 1 architecture contract is settled; a
   breaking change to it needs my agreement first. Additive changes are fine —
   document them.
6. **Complete code, not sketches.** Imports, error handling, type hints,
   Google-style docstrings, and the tests, all in the same change. No
   `# TODO: implement`, no `pass  # rest omitted`, no placeholder returning
   `None`.
7. **No fabricated evidence.** Every token-savings number in code, docs, README
   or GUI either cites `docs/research/RESEARCH.md` with its source, or comes from
   our own measurement on our own corpus. Never invent a percentage. Never
   restate a vendor marketing claim as fact. Where you cannot measure, say so and
   leave the value null. **This phase is the one where that rule is hardest to
   keep**, because format encoders and compressors produce beautiful numbers for
   free and the fidelity cost is invisible unless you go looking.

Also standing:

- Do not route around the egress proxy. Blocked hosts are an org egress policy,
  not a bug. Record the block; do not tunnel past it.
- Do not open a pull request unless I ask for one.
- **Stage deliberately.** `git add -A` after an unrelated command has bitten this
  project twice — most recently in the last session, which produced a commit
  whose message described work it did not contain and needed a correction commit
  to fix in the open.
- Record unverifiable items as unverified, never as quietly done.
- Report honestly. If you get something wrong and later find out, correct it in
  the open in `PROGRESS.md` rather than editing it away.

---

## 2. Where the project stands

Phases 0–4 are complete. Phases 0–2 are merged into `Main`. **Phases 3 and 4 are
on `claude/phase-3-4-web-and-repo`, awaiting my merge** — check whether I have
merged it and branch from whichever is current.

Built and working, as of 828 passing tests and 49 named skips:

- **Thirteen backends across four domains.** Documents: pdfplumber, pypdf,
  markitdown, kreuzberg, docling. Web: trafilatura (the default for HTML),
  readability, markdownify_html, crawl4ai. Repo: gitingest, repomix,
  code2prompt. Text: plaintext.
- **Entry-point plugin registries** for backends, post-processors and
  tokenizers. No hard-coded import list. Six backends were added last phase and
  `registry.py` was not modified once.
- **The pipeline**: `Source → converter (with fallback chain) → post-processor
  chain → final text`, with `TokenMeter` measuring every stage. Every backend
  attempt is recorded on `ConversionResult.attempts`.
- **URL fetching in the pipeline**, not in the backends — one robots/timeout/
  redirect/size policy, and the raw HTML becomes a measurable "before".
- **Repository packing** with include/exclude globs, `.gitignore` respect, a
  token budget that genuinely truncates and reports what it dropped, and a
  per-directory breakdown.
- **`tokenmill convert`, `repo`, `backends`, `tokens`.**
- **Post-processors**: `normalize_whitespace` (non-destructive, in the default
  chain) and `links` (destructive, opt-in). `PostProcessor.destructive` already
  exists and the default chain is built by excluding destructive processors.
  **That mechanism is about to carry a lot more weight than it has so far.**
- Ruff, mypy strict, `filterwarnings = ["error"]`, coverage gated at 85% on
  `core` and `tokens` (currently 95%).
- Corpus: **23 files**, byte-reproducible, generated by `scripts/make_fixtures.py`.

**Numbers you will want, all measured, all in UTF-8 bytes:**

| Fixture | Backend | Result |
|---|---|---|
| `boilerplate.html` | trafilatura | 12,481 → 2,854 (−77.1%); 41.7% of visible text removed |
| `boilerplate.html` | markdownify_html | 12,481 → 6,802 (−45.5%); **−38.7%** — it *adds* 38.7% to the page's visible text |
| `tables.pdf` | pdfplumber | 599 bytes, 35 of 35 cells as a Markdown table |
| `long_context.md` | plaintext | 79,255 chars, 12,312 words, 42 passages × 6 restatements, needle `RSD-TOKENMILL-4417` twice |
| `sample_repo` | gitingest / repomix / code2prompt | 2,862 / 3,978 / 2,246 bytes |

**Install weights, measured:** core 41 packages / 164 MB / 11.7 s;
`documents` 60 / 387 MB; `web` 43 / 130 MB; `repo` 54 / 136 MB;
`tokenizers` 53 / 159 MB; `crawl4ai` 94 / 677 MB; `docling` 122 / 5.2 GB.

Note: `docs/DEVELOPMENT_PLAN.md` was written when the project was called
`tokenfold`. Its verification snippets say `uv run tokenfold …`. The command is
`tokenmill`. Translate as you go.

---

## 3. First: the Phase 10 fidelity slice — and why it comes first

**This is a deliberate reordering of my own plan, and I want you to understand
the reason rather than just follow it.**

Phase 5's deliverable list contains post-processors that strip images, strip
links, remove duplicate blocks, normalise headings and reformat tables into
other serialisations. **Every single one of them can be measured as a win in
tokens and a loss in fidelity.** Today this project has no fidelity metric at
all — only pass/fail assertions scattered through the integration tests. If you
build Phase 5 first, its defaults get argued rather than measured, and you will
have spent a phase producing exactly the kind of number
`benchmarks/README.md` says is meaningless:

> Token savings without a fidelity measurement is not a result — a converter
> that emits an empty string scores a 100% reduction.

The last session hit this for real. `convert jsrendered.html` reported a
**−90.7% reduction** achieved by losing all the content, and nothing in the
output said so. That was caught by a human reading a table, not by a metric.
Phase 5 will produce that shape of result a dozen times.

So: build the measuring instrument, then build the things it measures.

### What to build

**A fidelity scorer** — enough of Phase 10 to make "this saved 20% and lost the
table" expressible as a number, and no more. Phase 10 proper still owns the
corpus × backends × formats matrix, wall time, peak memory and the committed
result files; **do not build those.**

Deliverables:

- A `fidelity` module (site it where Phase 10's harness will absorb it — say
  `src/tokenmill/fidelity/`, and tell me if you disagree) that scores one piece
  of converted text against ground truth, returning **a set of named component
  scores plus an overall**, never a single opaque number. A score a user cannot
  decompose is a score they cannot act on.
- Components, each of which we already assert somewhere as pass/fail and should
  now be able to state as a fraction:
  - **heading recall** — of the headings ground truth says exist, how many
    survive, at the right level;
  - **content recall** — of the sentences/paragraphs ground truth marks
    `must_contain`, how many survive;
  - **table integrity** — cells recovered as a fraction of cells expected, and
    whether they are still *in* a table rather than flattened to prose;
  - **structure retention** — list markers, code fences and link targets kept;
  - **boilerplate rejection** — of the markers ground truth says must be absent,
    how many are;
  - **reading order** — where ground truth carries ordered sentinels
    (`twocolumn.pdf`'s `ORDERMARK 01`–`12`), whether they are ascending.
- Every component returns `None` rather than a number when the ground truth for
  it does not exist for that fixture. **A missing score is not a zero and is not
  a one.** This is the same rule as `token_count: null` in `ground_truth.json`
  and it matters more here.
- Whatever `ground_truth.json` needs to support the above. It already carries
  `expected_headings`, `must_contain`, `must_not_contain`,
  `boilerplate_markers_must_be_absent`, `table_rows_including_header`,
  `table_columns` and the `ORDERMARK` sentinels. **If you need more, add it to
  `scripts/make_fixtures.py` and regenerate** — never hand-edit the corpus.
  `--check` must still report every file byte-for-byte.
- A CLI surface: `tokenmill fidelity <file> --against <fixture>` or a `--fidelity`
  flag on `convert` — your call, argue it in `PROGRESS.md`.

### Acceptance criteria

- Scoring `markdownify_html`'s output of `boilerplate.html` against ground truth
  gives a **high** content and heading recall and a **near-zero** boilerplate
  rejection — because it keeps everything, which is correct for that backend.
- Scoring `trafilatura`'s output of the same file gives high recall **and** a
  boilerplate rejection of 1.0. The two together are the number that says
  extraction worked, and neither alone is.
- Scoring `kreuzberg` on `tables.pdf` shows a table-integrity score well below
  `pdfplumber`'s, matching the failure already documented in `BACKENDS.md`
  ("the table is destroyed... one run-on paragraph").
- **Scoring an empty string scores near zero on everything.** Write this test
  first. It is the one that makes the metric worth having.
- A component with no ground truth returns `None` and the overall says which
  components it is composed of.

**Exit gate:** the scorer produces a table of every backend × every fixture it
has ground truth for, recorded in `docs/BENCHMARKS.md` next to the token
figures, so that every reduction on that page now sits beside what it cost.

---

## 4. Then: Phase 5 — post-processing, formats, measurement depth

**Goal:** the layer that makes this a token-reduction toolkit rather than a
converter aggregator.

### Deliverables

- **Post-processors**: aggressive whitespace cleanup, heading normalisation,
  image handling (drop / alt-text-only / keep), link handling (inline /
  reference / strip), duplicate-block removal, front-matter stripping.
- **`formats/`**: Markdown table ↔ CSV ↔ TOON ↔ JSON ↔ key-value encoders, so a
  user can test which serialisation is cheapest **for their data**.
- **Chonkie** integration for token-aware chunking.
- **`TokenMeter` extended to per-stage reporting** — source → converted → each
  post-processor → final, so a user sees where the saving actually came from.
- **A `compare` command**: one input, N backends and/or N formats, a table of
  tokens + timing + **fidelity**, optionally writing each variant to disk.

### Acceptance criteria

- The per-stage token report is arithmetically consistent and matches direct
  tokenizer counts on each intermediate.
- TOON/CSV encoders round-trip tabular data **losslessly**, proven with
  property-based tests (hypothesis is already a dev dependency and is currently
  unused — this is what it is for).
- Every destructive post-processor declares `destructive = True` and is
  therefore absent from the default chain. Assert this for the whole registry,
  not per processor.
- The docs are honest: **structure-preserving beats maximal stripping** for model
  accuracy, and format savings carry accuracy trade-offs. State it in
  `docs/BENCHMARKS.md` with the `RESEARCH.md` sources, and default to
  conservative post-processing.
- **`compare` produces a correct table verified against manual counts.**

### Exit gate

`compare` correct against hand-counted numbers; round-trip property tests pass;
every new post-processor scored by §3's fidelity metric and the score published.

### Things I want you to get right

- **`compare` is the answer to a question this project has been dodging.** A
  document and a repository have no before-count — the pipeline correctly
  reports one number and a size. The comparison that means something for those
  is *between backends on the same input*, and I have been writing "that is
  Phase 5's `compare`" in `PROGRESS.md` for two phases. Make it good. It should
  work on documents, web pages and repositories alike.
- **`compare` should show fidelity beside tokens or it is a machine for picking
  the worst backend.** This is the reason §3 comes first.
- Defect **D8** belongs to you: boilerplate reduction happens inside the web
  converters and budget truncation inside the repo backends, so neither appears
  as a row in `--show-stages`. "Measurement depth" is the deliverable that
  should absorb them.
- Defect **D9** belongs to you if you touch the JSON: `tokens --json` carries
  less provenance than `convert --json`, and the `web` object is `null` rather
  than absent for non-web conversions.

---

## 5. Then: Phase 6 — prompt compression

**Goal:** the advanced, off-by-default token reducer.

**Read §6 trap 2 before you plan this phase.** It is largely unverifiable in
this sandbox and it is the piece I most expect you to have to leave partly
undone. That is an acceptable outcome if it is recorded honestly; a fabricated
verification is not.

### Deliverables

- **LLMLingua-2** adapter (MIT) behind the `compress` extra, model download
  explicit, with a size warning and a cache path.
- Optional Selective Context adapter.
- Compression exposed as a **post-processor with a target ratio**, always
  reporting both the achieved ratio **and** a retention/similarity indicator.
  With §3 built, that indicator should be the fidelity score, not a new
  bespoke number.
- **Prominent warnings** in docs, CLI and GUI: compression suits redundant RAG
  context, can degrade reasoning-heavy prompts, and must be evaluated on the
  user's own task. **Default off.**

### Acceptance criteria

- Achieves a measurable ratio on `long_context.md` and reports it accurately.
- First-run model download is explicit, resumable and skippable; **nothing
  downloads silently at import**.
- Fully offline once cached.

### Exit gate

Ratio verified against direct token counts; offline-after-cache proven.

`long_context.md` was built for this: 79,255 characters, 42 passages each
restated 6 times, with the needle fact `RSD-TOKENMILL-4417` appearing exactly
twice. **A compressor that drops the needle has failed regardless of its
ratio** — that is your fidelity assertion and it needs no new ground truth.

---

## 6. The traps — things that will bite you, found the hard way

Each of these cost real time in a previous phase or was measured while writing
this handover.

**1. CI has been dead for over nine hours and 23 consecutive runs.** Runs 25
through 47 all fail 2–6 seconds after starting, every job at `runner_id: 0`, no
steps, no logs, across `ubuntu-latest`, `macos-latest` and `windows-latest`
alike. The job records are created with correct expanded matrix names and the
docling job correctly evaluates its `if:` to skipped — which proves the workflow
parses and expands, so it is not our YAML. The likeliest cause is exhausted
Actions minutes or a spending limit, and **only I can check that**. Re-check
before you rely on CI, and if it is still dead **say so plainly rather than
reporting local green as if it were CI green**. Four acceptance criteria across
three phases are already unverified for exactly this reason.

**2. Phase 6 cannot be verified in this sandbox, and the install is not what the
plan says.** Measured today, not assumed:

- `pip install llmlingua` resolves to **63 packages and 4.7 GB**, including the
  full CUDA stack (`nvidia-cublas`, `nvidia-cudnn`, `nvidia-cufft`, and the
  rest). The plan calls LLMLingua-2 "CPU-feasible", which is true of *running*
  it and not of installing it. This is the same shape as docling's 5.2 GB and
  deserves the same treatment: its own extra, lazy import, never in core.
- `huggingface.co` is **denied** at the egress proxy, so the model cannot be
  downloaded here at all.
- `download.pytorch.org` is **also denied**, so you cannot even test whether the
  CPU-only wheel index avoids the CUDA stack. On a normal machine it does; you
  cannot prove it here. Document the CPU-only index as the recommended install
  and mark it unverified.

So Phase 6's acceptance criterion "achieves a measurable ratio on a long fixture
context" is **not achievable in this environment**. Your options, and I want you
to pick one and tell me which: implement it fully with the offline, error and
refusal paths tested and the success path recorded as unverified (this is what
Phase 2 did with docling's PDF path, and it is honest); or implement less and say
so. What you must not do is imply it was run.

**3. Real model tokens are still unavailable here.**
`openaipublic.blob.core.windows.net` is denied, so `tiktoken` cannot load a
vocabulary. Every local figure is `--tokenizer bytes`, which counts UTF-8 bytes.
**A byte percentage is not a token percentage.** This matters more in Phase 5
than it has before, because the entire point of the format encoders is that
different serialisations tokenise differently — and **bytes cannot show you
that**. CSV vs JSON vs TOON will look far more similar in bytes than they are in
tokens. Measure in bytes locally to sanity-check, add `network`-marked tests that
assert the real figures, and **publish no format comparison as a token claim
until you have read it out of a green CI run.** There is already a pattern for
this in `tests/unit/test_web_tokens_network.py`, which prints its number into the
CI log so it can be quoted; copy it.

**4. `filterwarnings = ["error"]` is in force**, and Phase 6 brings
`transformers`, which is one of the noisiest libraries in the ecosystem at import
time. Phase 2 lost a CI round to onnxruntime warning about Windows; Phase 4 lost
one to pathspec's deprecation of a factory name. Use
`warnings_as_conversion_warnings` from `tokenmill.backends._common` to forward a
warning the *user* can act on, and a scoped message filter for a library's
internal deprecation churn. The distinction is drawn in
`docs/ARCHITECTURE.md`; do not blanket-suppress.

**5. There are now five pieces of process-global state manipulated during a
conversion**, and none is thread-safe: three `warnings.catch_warnings` uses,
`os.environ`, the stdlib root logger's handlers *and* level, and loguru's
activation registry. All are correctly restored today. **Do not add a sixth
without telling me.** If a post-processor or a compressor needs global state,
that is a design smell worth raising rather than absorbing — this is defect D2
and its severity is in the trajectory.

**6. `transformers` and `docling` will fight.** The plan flags it and it is why
they are separate extras. Do not put them in the same one, and check what a
combined install resolves to before you claim they coexist.

**7. Chonkie is genuinely light, unlike the rest of Phase 6's neighbourhood.**
Measured: **13 packages, 72 MB**, `chonkie` MIT, `chonkie-core` and `tokie`
`MIT OR Apache-2.0`. It pulls `numpy` and `httpx`. §1.6 lists it in core; that is
defensible on these numbers, but core has already grown 2.3× this year and it is
my call — ask me before putting it there.

**8. TOON is on PyPI twice.** Both `toon` and `toon-format` resolve. Check which
is `toon-format/toon` from `RESEARCH.md`, verify its licence from installed
metadata, and be aware `RESEARCH.md`'s own caveat: TOON's wins are real but
**narrow (uniform arrays only) and model-dependent**, and independent work finds
its accuracy collapses on non-aligned structures. Do not let the encoder ship
with a docstring that reads like the marketing page. The honest framing is in
`RESEARCH.md` Category 7 and it is unflattering.

**9. The `destructive` flag is about to matter far more than it does now.**
Today there is one destructive post-processor. Phase 5 adds five or six. The
default chain is built by *excluding* destructive processors — verify that still
holds with a test over the whole registry, and verify that a user who asks for
one gets it and is told what it did. Phase 1 already learned that a flag which
silently does nothing is worse than no flag.

**10. New fixtures go through the generator.** `tests/fixtures/sample_repo`
contains a real `.git` and a deliberately-uncommitted `secrets.env`; the corpus
is generated by `scripts/make_fixtures.py` and must stay byte-reproducible —
`--check` currently reports **23 files**. If the fidelity work or the format
encoders need new fixture content (a nested-JSON fixture for TOON's failure case
would be a good addition), add it to the generator. Never drop files into
`tests/fixtures/` by hand.

**11. `hypothesis` is a declared dev dependency and has never been used.** Phase
5's round-trip property tests are the first thing that actually needs it. If you
find you do not need it either, say so and I will drop it.

**12. Do not let `compare` become a leaderboard.** The harness rule from Phase 10
applies early: treat every backend identically, and a result that contradicts
`RESEARCH.md` gets reported as-is with a note, not buried. The temptation here is
to make our own defaults look good.

---

## 7. Then: stop, and report

After Phase 6's exit gate (or after recording honestly what could not be
verified), and before any Phase 7 work:

- Update `docs/REVIEW_PHASES_0_4.md` — or supersede it with a
  `REVIEW_PHASES_0_6.md`, your call — covering the new acceptance criteria, the
  defects you closed from its list (D2, D3, D4, D6, D7, D8, D9 and suspicions
  S1–S4 are all still open), and any new ones.
- Re-run the whole corpus end to end **through the new post-processor chain and
  the fidelity scorer**, and give me the table. That table — every fixture,
  every backend, tokens beside fidelity — is the thing this project has been
  building towards since Phase 0, and it is the first time it will be possible
  to produce it.
- A recommendation on whether Phase 7 should start, and what to repair first.

Then stop and report to me. Do not start Phase 7.

---

## 8. Definition of done, per piece of work

Before you tell me a phase is complete:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=tokenmill
uv run python scripts/make_fixtures.py --check
```

All green, plus:

- The sandbox-verification commands from the plan for that phase, run, with the
  output **pasted into `PROGRESS.md`** — not summarised, pasted.
- `docs/BACKENDS.md` updated where a backend's behaviour changed, and a new
  section per post-processor and encoder documenting what it destroys, with a
  test asserting each documented failure and a message saying what to update
  when upstream fixes it. That is the Phase 2 standard and it is not optional.
- `docs/BENCHMARKS.md` updated with every new measurement, its unit stated, and
  a fidelity figure beside every token figure.
- `PROGRESS.md` updated: status at a glance, a verification-log entry with
  captured output, backend and post-processor status tables, decisions made,
  deferred work, and any new open questions for me.
- `CHANGELOG.md`, `README.md`, `docs/ARCHITECTURE.md` and
  `docs/ADDING_A_BACKEND.md` updated where the change touches them.
- Commits pushed. Coherent commits — one logical change each, message describing
  what that commit actually does.

---

## 9. Git — one branch, and I mean one

**All of this work goes on a single branch: `claude/phase-5-6-formats-and-fidelity`.**

Cut it from the current default branch (`Main`, capital M — the CI triggers and
the changelog URLs account for that), or from `claude/phase-3-4-web-and-repo` if
I have not merged that yet. Check which is current before you start.

**Do not create a second branch.** Not per phase, not for the fidelity slice, not
for the review. Three pieces of work, one branch, sequential commits. If your
harness assigns its own branch name, use that one branch for everything and
mirror it — do not let the mirror become a place where different work lives.

Push as you go rather than in one lump at the end; the container is ephemeral and
unpushed work is lost work.

Do not open a pull request. Report to me when you stop, and I will merge.

---

## 10. Ask me when it matters

If two readings of this assignment would produce materially different work, ask —
with the options and your recommendation, not an open question. The three most
likely candidates:

- **Where the fidelity module lives**, and whether it is a CLI command or a flag.
- **Whether Chonkie goes in core** (§6 trap 7).
- **How far to take Phase 6** given that its success path cannot be executed here
  (§6 trap 2). I would rather hear "I implemented it and could not run it, here
  is exactly what is unverified" than either a fabrication or a silence.

Everything else, use your judgement and write down what you decided and why.

Do the work in the order given: fidelity, then Phase 5, then Phase 6, then the
review. **If you run short of room, the order is also the priority order** —
a complete fidelity scorer plus a complete Phase 5 is a far better outcome than
three half-finished phases, and Phase 6 is both last and least verifiable here.
Say what you did not get to. Stop before Phase 7.
