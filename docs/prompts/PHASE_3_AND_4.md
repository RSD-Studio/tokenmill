# Session prompt — Phases 3 and 4, then stop and re-evaluate the whole app

Paste everything below the rule into a fresh session. It is written to be
self-contained: the new session should need nothing from the Phase 2
conversation except the repository itself.

---

You are working on **`RSD-Studio/tokenmill`**, an open-source token-reduction
toolkit that wraps best-in-class OSS converters behind one interface and
measures what each one actually saves. I am the project owner.

Your assignment is **Phase 3 (Web backends) and Phase 4 (Repository
backends), in one go**, and then a **full re-evaluation and test of the
complete application**. **Stop before Phase 5.** Do not begin Phase 5's
post-processors, format encoders or `compare` command, however tempting the
adjacency.

## 0. Read this first, in full, before writing any code

- `PROGRESS.md` — the whole thing. It is long and it is the memory of the
  project: what is verified, what is merely believed, what is blocked, and
  every decision I have already made.
- `docs/DEVELOPMENT_PLAN.md` — §1 (the architecture contract), then Phases 3,
  4 and 5. Read 5 so you know exactly where your boundary is.
- `docs/research/RESEARCH.md` — Phase 3's acceptance criterion is calibrated
  against the published figures in here. Read the web-extraction and
  repository-packing sections.
- `docs/ARCHITECTURE.md` — how `Registry`, `Pipeline`, `TokenMeter` and the
  fallback chain fit together.
- `docs/ADDING_A_BACKEND.md` — the adapter contract. Follow it exactly.
- `docs/BACKENDS.md` — the per-backend honesty document Phase 2 established.
  Yours must match its standard: failure modes quoted from real output.
- `CONTRIBUTING.md` — especially "Rules that are not negotiable".

Then **restate the acceptance criteria for both phases in your own words**
before you start, so I can see we agree on what "done" means.

## 1. Hard constraints — these do not bend

These are the same seven that governed Phases 1 and 2. They are not
boilerplate; each one has already caught something real.

1. **Open-source only.** No proprietary or hosted-only SaaS backends in the
   core product.

2. **License hygiene is an engineering requirement.** Permissive (MIT /
   Apache / BSD) tools may be imported into our process. AGPL/GPL tools
   (Firecrawl core, omniparse, Pandoc, PyMuPDF4LLM, Marker, Surya) must
   **never** be imported — subprocess or service boundary only.
   Non-commercial weights are excluded by default.
   `BackendInfo.__post_init__` already refuses to construct a copyleft
   backend that claims in-process isolation; do not weaken that. **Verify
   each licence against the installed package metadata at the moment you
   write the adapter, not from `RESEARCH.md` alone.** Phase 2 found
   `RESEARCH.md` wrong about a dependency count; assume it can be wrong
   about a licence.

3. **The core install stays light, CPU-only and conflict-free.** No PyTorch,
   no CUDA, no system-binary requirement in the default `pip install
   tokenmill`. The `clean-core-install` CI job (9 cells) is the standing
   guard — do not weaken it. Anything heavy goes behind an extra with a lazy
   import.

4. **Nothing is done until it has been run in the sandbox and the output
   inspected.** Not "should work". Not "looks correct". Executed, output
   captured, result recorded. A converter that returns an empty string exits
   0 — read the actual Markdown.

5. **Never break what already works.** Minimal correct changes. Check call
   sites before modifying a module others import. After any edit re-run the
   *full* suite, not just the new test. The Phase 1 architecture contract is
   settled; a breaking change to it needs my agreement first. Additive
   changes are fine — document them.

6. **Complete code, not sketches.** Imports, error handling, type hints,
   Google-style docstrings, and the tests, all in the same change. No
   `# TODO: implement`, no `pass  # rest omitted`, no placeholder returning
   `None`.

7. **No fabricated evidence.** Every token-savings number in code, docs,
   README or GUI either cites `docs/research/RESEARCH.md` with its source, or
   comes from our own measurement on our own corpus. Never invent a
   percentage. Never restate a vendor marketing claim as fact. Where you
   cannot measure, say so and leave the value null. **This bit us in Phase 1
   — plausible token counts were written into a README draft without being
   measured.** If a number is not in captured output, it does not go in a
   document.

Also standing:

- **Do not route around the egress proxy.** Blocked hosts are an org egress
  policy, not a bug. Record the block; do not tunnel past it.
- **Do not open a pull request** unless I ask for one.
- **Stage deliberately.** `git add -A` after an unrelated command has bitten
  this project before — a commit whose message described one change while
  carrying three.
- **Record unverifiable items as `unverified`**, never as quietly done.
- **Report honestly.** If you get something wrong and later find out, correct
  it in the open in `PROGRESS.md` rather than editing it away.

## 2. Where the project stands

Phases 0, 1 and 2 are complete and merged into `Main` (PR #4, `0a74c8f`).
Post-merge follow-ups are on `claude/phase-2-followups`; **check whether that
has been merged into `Main` and branch from whichever is current.**

Built and working:

- Entry-point plugin registries (`tokenmill.backends`,
  `tokenmill.postprocessors`, `tokenmill.tokenizers`). No hard-coded import
  list — a new backend is a new entry point.
- `Converter` protocol and `BaseConverter`, which handles availability
  caching, the size guard, timing and error wrapping. Adapters implement only
  `_convert`.
- Per-format backend preference map in `src/tokenmill/core/preferences.py`.
  `effective_priority(info, source_format)` overrides a backend's declared
  priority per format.
- Fallback chain: `Registry.candidates()` returns an ordered chain,
  `Pipeline` walks it, and every attempt is recorded as a `BackendAttempt` on
  the result.
- Error taxonomy: `ConversionError` → `UnsupportedFormat`,
  `BackendUnavailable`, `BackendFailed`, `Timeout`, `CorruptSource`,
  `NetworkRequired`.
- Shared adapter plumbing in
  `src/tokenmill/backends/documents/_common.py`: `probe_module`,
  `source_as_file`, `classify_failure`, `warn_on_empty_output`,
  `missing_binary_note`, `render_markdown_table`,
  `warnings_as_conversion_warnings`. **Read this module before writing your
  adapters — most of what you need already exists, and `classify_failure` is
  where a new library's exception hierarchy gets mapped onto the taxonomy.**
- Document backends: pdfplumber, pypdf, markitdown, kreuzberg, docling
  (behind the `docling` extra).
- One web backend already exists:
  `src/tokenmill/backends/web/markdownify_html.py`. It is the current
  `html` default.
- CLI: `tokenmill convert`, `tokenmill backends`, `tokenmill tokens`.
  `convert` already accepts an `http(s)` target and builds a
  `Source(kind=URL)` — nothing fetches it yet. `SourceKind.REPO` already
  exists in the model and is likewise unused.
- 558 tests pass, 23 skip (docling, network, heavy). Coverage gate at 85% on
  core and tokens. Ruff, mypy strict, `filterwarnings = ["error"]`.

Note: `docs/DEVELOPMENT_PLAN.md` was written when the project was called
`tokenfold`. Its sandbox-verification snippets say `uv run tokenfold …`. **The
command is `tokenmill`.** Translate as you go.

## 3. Phase 3 — Web backends

**Goal:** URL or HTML in, clean Markdown out, with the boilerplate-stripping
win measured.

**Deliverables**

- Adapters: **Trafilatura** (primary — best extraction quality),
  **markdownify** (raw conversion — already exists as `markdownify_html`),
  **readability** (fallback), **Crawl4AI** behind the `web` extra for
  JS-rendered pages.
- URL fetching with a sane user agent, timeout, redirect limit, size cap, and
  `robots.txt` respect (default on, overridable with an explicit flag).
- Offline mode: convert saved HTML with **zero** network calls, enforced and
  tested.
- A "boilerplate reduction" metric: raw-HTML tokens vs extracted-Markdown
  tokens, surfaced in the result.

**Acceptance criteria**

- `tests/fixtures/boilerplate.html` (12,481 bytes, heavy nav/ads): reduction
  lands in the same order of magnitude as the published figures in
  `RESEARCH.md` (~70–90%). **If ours differs wildly, investigate before
  reporting — do not just publish the number.**
- No network access occurs when converting a local HTML file. Assert this in
  a test — actually assert it, by making the socket layer raise, not by
  observing that nothing appeared to happen.

**Exit gate:** measured reduction on the fixture recorded in `PROGRESS.md`
and in `docs/BENCHMARKS.md`; offline guarantee test passes.

## 4. Phase 4 — Repository backends

**Goal:** point at a repo, get one prompt-ready file with token accounting.

**Deliverables**

- **gitingest** adapter (native Python import — the primary).
- **Repomix** (Node) and **code2prompt** (Rust) adapters via subprocess, with
  graceful "binary not found → install hint" behaviour.
- Shared options: include/exclude globs, `.gitignore` respect, max file size,
  binary-file skip, token budget with a documented truncation strategy, and a
  per-directory token breakdown ("which folder is eating my context").
- Local path and remote Git URL support (shallow clone into a temp dir,
  cleaned up on every path including failure).

**Acceptance criteria**

- `tests/fixtures/sample_repo` produces a single file with a directory tree
  and file contents.
- The token budget flag genuinely caps output, **and what got dropped is
  reported.** A silent truncation is a bug.
- Missing `npx` / `repomix` yields a clear message, not a traceback.

**Exit gate:** all three adapters behave correctly whether or not their
runtime is installed; budget truncation verified by inspecting the output,
not by trusting the flag.

**Risk called out in the plan, and I mean it:** subprocess argument injection
with user-supplied paths. Always list args. Never `shell=True`. A repository
path is attacker-controlled input the moment someone runs tokenmill on a
checkout they did not write.

## 5. The traps — things that will bite you, found the hard way

These are specific, and each one cost real time in Phase 2 or was identified
while planning this handover.

1. **Phase 3's ~70–90% criterion needs real model tokens, and this sandbox
   cannot produce them.** `openaipublic.blob.core.windows.net` and
   `huggingface.co` are both denied by the egress proxy (re-probed and still
   denied on 2026-08-22). The `bytes` tokenizer counts UTF-8 bytes, not model
   tokens, and a percentage measured in bytes is **not** the same claim as a
   percentage measured in `o200k_base`. The only place real tokens exist is
   the CI `tokenizers` job. So: measure in bytes locally to sanity-check the
   order of magnitude, add a `network`-marked test that asserts the real
   figure, and **do not publish a percentage in any document until you have
   read it out of a green CI run.** Until then it is `unverified` with the
   byte figure stated as a byte figure.

2. **Ranking trafilatura above `markdownify_html` for `html` will break
   `tests/integration/test_reference_backends.py`.** That file asserts
   `boilerplate_result.backend_id == "markdownify_html"`, that
   `metadata["strips_boilerplate"] is False`, and — in
   `test_the_boilerplate_survives_because_this_backend_does_not_extract` —
   that every marker in the corpus's
   `boilerplate_markers_must_be_absent` list *is still present*, because the
   raw backend is a markup converter and stripping is not its job. That test's
   own docstring says: *"Phase 3's trafilatura adapter is what strips these.
   If a future change makes them disappear here, that is a behaviour change
   worth noticing."* You are that change.

   So these are not "broken tests to fix quietly". Decide deliberately which
   backend should win `html`; pin the existing assertions to
   `--backend markdownify_html`; and write the mirror-image test for
   trafilatura, asserting those same markers are now **absent**. That list in
   `ground_truth.json` is named for what the extractor is supposed to achieve
   — use it as the acceptance test, not just as documentation. Phase 2 hit
   the identical shape of this problem with empty HTML and `CorruptSource`,
   and the right fix was to pin the old test and add a new one, never to
   loosen the old one.

3. **`SubprocessConverter` is a Phase 7 deliverable and does not exist.**
   Phase 4 needs subprocess adapters anyway. Do not build the full hardened
   Phase 7 base (binary discovery, version probing, sandboxing policy) — that
   is out of scope and I do not want it half-built. Build the minimum honest
   thing Phase 4 needs, put it somewhere Phase 7 can absorb it, and write
   down in `PROGRESS.md` exactly what Phase 7 still owes. If you think this
   ordering is wrong, say so before you build, not after.

4. **`docs/BENCHMARKS.md` does not exist**, but Phase 3's exit gate names it —
   while `README.md` lists it as a Phase 10 deliverable. That is a genuine
   conflict in my own plan. My ruling: **create it now**, small, and let it
   grow. It holds measured numbers with provenance from the start; Phase 10
   fills it out from the full harness. Note in it that it is partial.
   `benchmarks/README.md` already states the rule that every published number
   must trace back to a committed raw result file — honour that.

5. **`docs/LICENSES.md` is a dead link.** `CONTRIBUTING.md` links to it as
   though it exists; it does not, and `README.md` calls it Phase 7. You are
   adding backends with licences to declare. Either create a minimal
   `docs/LICENSES.md` now or fix the link — do not leave a broken link in the
   contributor path. Tell me which you did.

6. **CI could not schedule runners as of 2026-08-22 11:15 UTC.** Runs 25
   through 28 all failed within seconds with every job at `runner_id: 0`, no
   runner name, no steps and no logs. The job *records* were created with
   correct names and the `docling` job correctly evaluated its `if:` to
   `skipped`, which proves the workflow parses and expands — nothing was
   wrong with the YAML. Run 24 on `Main` succeeded 2h20m earlier. The likely
   cause is exhausted Actions minutes or a spending limit; I am the only one
   who can check that. **Re-check CI status before you rely on it**, and if it
   is still dead, say so plainly rather than reporting local green as if it
   were CI green.

7. **Verified environment facts, 2026-08-22, this sandbox** (re-probe rather
   than assume — they have changed between phases before):

   | Host / tool | Result |
   |---|---|
   | `pypi.org` | 200 — trafilatura, readability, gitingest installable |
   | `registry.npmjs.org` | 200 — **repomix is genuinely runnable here** |
   | `crates.io` API | 403 — code2prompt likely not installable from source |
   | `example.com` | denied — **no live-URL testing in this sandbox** |
   | `openaipublic.blob.core.windows.net` | denied |
   | `huggingface.co` | denied |
   | Node | v22.22.2 |
   | npx | 10.9.7 |
   | cargo | 1.94.1 |

   Because live URLs are unreachable here, the URL-fetching layer must be
   tested against a local HTTP server you start in-process, plus
   `network`-marked tests for the real thing. "I could not test the fetcher"
   is not acceptable; "the fetcher is tested against a loopback server and
   the live path is `network`-marked and unverified here" is.

8. **`filterwarnings = ["error"]` is in force.** A third-party library that
   warns at import time will fail your conversion. Phase 2 lost a CI round to
   `onnxruntime` warning about Windows at import. Use
   `warnings_as_conversion_warnings` — forward the warning to the user, do
   not suppress it.

9. **Crawl4AI pulls Playwright and a browser download.** That is exactly the
   shape of thing rule 3 exists to keep out of the core. Behind the `web`
   extra, lazily imported, marker-gated in tests, skipped by default in CI.
   Check what `pip install crawl4ai` actually resolves to before you commit
   to it — Phase 2 measured `docling` at 122 packages and 5.2 GB, and that
   measurement changed where it got ranked.

10. **`tests/fixtures/sample_repo` contains a real `.git` directory and a
    deliberately-uncommitted `secrets.env`.** The corpus is generated by
    `scripts/make_fixtures.py` and must stay byte-reproducible —
    `uv run python scripts/make_fixtures.py --check` reports 22 files. If
    Phase 4 needs new fixture content, add it to the generator; never drop
    files into `tests/fixtures/` by hand. And note that `secrets.env` being
    absent from a fresh clone is by design: it is what a `.gitignore`-respect
    test should be checking against.

## 6. Then: stop, and re-evaluate the complete app

**After Phase 4's exit gate and before any Phase 5 work**, do a full
re-evaluation of tokenmill as a product, not as a diff. This is a deliverable
in its own right, not a victory lap. I want to know what we have actually
built across four phases, and what is quietly wrong.

Produce `docs/REVIEW_PHASES_0_4.md` covering:

1. **Every acceptance criterion from Phases 0 through 4**, each marked
   `verified` / `unverified` / `failed`, each with the evidence — the command
   run and the output that proves it. A criterion whose proof you cannot
   produce is `unverified`, even if you are confident.

2. **An end-to-end run over the whole fixture corpus** — every fixture,
   through auto-selection, with the output read. Not a smoke test: a table of
   what each fixture produced, which backend won, what the token figures
   were, and what looked wrong. Include the failures — `scanned.pdf` and
   `corrupt.pdf` are in the corpus precisely to be failed on correctly.

3. **A clean-install check by hand**, not just in CI: fresh venv,
   `pip install .`, no extras, import the package, run `tokenmill backends`,
   confirm the graceful-degradation story is real and the install is light.
   Then the same with each extra.

4. **The cross-cutting seams**, which are where four phases of independent
   work go wrong:
   - Does the fallback chain still do the right thing now that web and repo
     backends are in the registry? Can an installed `documents` extra change
     which backend converts an HTML page? (It must not — that invariant is
     already written down in `preferences.py`.)
   - Is the error taxonomy still coherent across three domains, or has each
     phase quietly added its own vocabulary?
   - Does the per-stage token report still add up now that repo packing and
     boilerplate reduction produce stages Phase 1 never imagined?
   - Is `--json` output stable and complete for every command?
   - The `warnings.catch_warnings` thread-safety note recorded in
     `PROGRESS.md` — is it still just a Phase 8 concern, or has something
     since made it urgent?

5. **A licence audit of everything now installed**, across all extras, read
   from installed package metadata. Not from `RESEARCH.md`, not from memory.
   Phase 2 audited all 122 packages of the docling tree and found no GPL; do
   the equivalent for what Phases 3 and 4 added.

6. **An honest defects list.** Everything you found and did not fix, with
   severity and where it lives. Include things you suspect but cannot prove,
   labelled as suspicions.

7. **A recommendation on whether Phase 5 should start** — and if something
   should be repaired first, say what and why. I would rather hear "fix this
   before Phase 5" than discover it in Phase 7.

Then **stop and report to me.** Do not start Phase 5.

## 7. Definition of done, per phase

Before you tell me a phase is complete:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=tokenmill
uv run python scripts/make_fixtures.py --check
```

All green, plus:

- The sandbox-verification commands from the plan for that phase, run, with
  the **output pasted into `PROGRESS.md`** — not summarised, pasted.
- `docs/BACKENDS.md` updated with a section per new backend, failure modes
  quoted from real output, and **a test asserting each documented failure**
  with a message saying what to update when upstream fixes it. That is the
  Phase 2 standard and it is not optional.
- `PROGRESS.md` updated: status at a glance, a verification-log entry with
  captured output, backend status table, decisions made, deferred work, and
  any new open questions for me.
- `CHANGELOG.md`, `README.md`, `docs/ARCHITECTURE.md` and
  `docs/ADDING_A_BACKEND.md` updated where the change touches them.
- Commits pushed. Coherent commits — one logical change each, message
  describing what that commit actually does.

## 8. Git

Work on **`claude/phase-3-4-web-and-repo`**, cut from the current `Main` (the
default branch is `Main`, capital M — the CI triggers and the changelog URLs
already account for that). Mirror to whatever branch your harness assigns.
Push as you go rather than in one lump at the end; the container is ephemeral
and unpushed work is lost work.

**Do not open a pull request.** Report to me when you stop, and I will merge.

## 9. Ask me when it matters

If two readings of this assignment would produce materially different work,
ask — with the options and your recommendation, not an open question. Trap 3
(the `SubprocessConverter` ordering) is the most likely candidate. Everything
else, use your judgement and write down what you decided and why.

Do the work in the order given. Phase 3, then Phase 4, then the review. Stop
before Phase 5.
