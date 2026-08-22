# Review: Phases 0 through 4

**Date:** 2026-08-22. **Reviewer:** the session that built Phases 3 and 4.
**Scope:** everything built so far, assessed as a product rather than as a diff.

A note on who wrote this. I built two of the four phases being reviewed, so
where I judge my own work the judgement is worth less than the evidence beside
it. Every claim below either names the command that produced it or is marked
unverified. Where I found my own mistakes they are in the defects list with
everyone else's.

---

## 1. Verdict first

**tokenmill works.** Thirteen backends across four domains, one interface, and
measurement that does not flatter itself. The end-to-end run in §3 converts
every fixture in the corpus, fails correctly on the two designed to fail, and
produces numbers that survive being read rather than glanced at.

**Three things are genuinely wrong**, in descending order of how much they
should worry you:

1. **CI has not run for anyone in nine hours** and cannot be made to. Nothing in
   Phases 3 or 4 is verified on Windows, on macOS, on Python 3.12 or 3.13, or
   against a real tokenizer. That is a large unverified surface and it is
   growing with every phase.
2. **The headline figure of the whole project is unpublishable.** −77.1% is a
   byte measurement; the claim the project exists to make is about model tokens;
   the only place that number can be produced is the CI job that will not run.
3. **The `documents` extra is heavier than the `docling` decision implies.** 387
   MB for what §1.6 calls "light-ish". Nobody has looked at it since Phase 2
   flagged it.

**Recommendation: start Phase 5, but fix defect D1 first** — see §8.

---

## 2. Acceptance criteria, phase by phase

Verified means I ran something and read the output. Unverified means I could not
produce the proof, whatever my confidence.

### Phase 0 — Scaffolding

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 0.1 | Corpus generates deterministically | ✅ verified | `make_fixtures.py --check` → `OK: 23 files reproduced byte-for-byte` |
| 0.2 | Every fixture inspected, not just generated | ✅ verified | Phase 0's log, per fixture. Re-confirmed for the two files Phase 3 added |
| 0.3 | Toolchain green | ✅ verified | §6 |
| 0.4 | Clean install under a minute | ✅ verified | **11.7 s**, 41 packages, §5 |

### Phase 1 — Core architecture

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1.1 | A backend is a module plus an entry point, no core edits | ✅ verified | Phase 1 built `tokenmill-csvtable` outside the repo from the tutorial's own code. **Re-confirmed this phase**: six backends were added across Phases 3–4 and `registry.py` was not modified once |
| 1.2 | Availability correct when a dependency is absent | ✅ verified | `backends --all` on the clean install, §5: five backends greyed out, each with an install command |
| 1.3 | Token counts match hand-verified tiktoken | ⚠️ **unverified since 2026-08-22 11:14** | CI-verified through run 24; the job has not run since |
| 1.4 | `convert boilerplate.html` gives Markdown and a real before/after | ✅ verified in bytes | §3 |
| 1.5 | Protocol conformance for every backend | ✅ verified | 16 checks × 13 backends, parametrised over the installed entry points |
| 1.6 | A broken backend degrades, does not crash | ✅ verified | Subprocess test with a real `.dist-info` whose module raises |

### Phase 2 — Document backends

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 2.1 | Every fixture format converts | ✅ verified | §3 — pdf, docx, pptx, xlsx all convert |
| 2.2 | A table survives as a table | ✅ verified | pdfplumber, 35 of 35 cells |
| 2.3 | Fallback works when the primary is uninstalled | ✅ verified | Phase 2's log; the mechanism re-exercised this phase in `test_web_backends.py` |
| 2.4 | No core-install regression | ✅ verified locally | §5. **Not verified in CI on 9 cells since run 24** |
| 2.5 | Docling's PDF path | ❌ **unverified** | Implemented, failure path observed, success path never run anywhere. The weekly job that would close it has not run |

### Phase 3 — Web backends

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 3.1 | Reduction in RESEARCH.md's 70–90% order of magnitude | ⚠️ **verified in bytes, unverified in tokens** | −77.1% in UTF-8 bytes, inside the band. The band is a token claim. `test_web_tokens_network.py` asserts the token figure and prints it; it has never run |
| 3.2 | No network when converting a local file, asserted by making sockets raise | ✅ verified | `TestOfflineGuarantee` patches `socket.socket.connect` and `socket.create_connection` to raise. A second test proves `--offline` refuses *before* opening a socket |
| 3.3 | *(gate)* Reduction recorded in PROGRESS.md and BENCHMARKS.md | ✅ verified | Both, with units stated and the token figure marked unverified |
| 3.4 | *(gate)* Offline guarantee test passes | ✅ verified | §6 |

### Phase 4 — Repository backends

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 4.1 | Fixture repo gives one file with a tree and contents | ✅ verified | Output read in full. 7 of 9 tracked files; the binary blob and the `.gitignore`d secret correctly absent |
| 4.2 | The budget genuinely caps, and reports what it dropped | ✅ verified | A 1,200-byte cap produced a **999-byte** file. Measured with `wc -c`, not from the flag. Five dropped files named in a warning, in metadata, and in the document |
| 4.3 | Missing `npx`/`repomix` is a message, not a traceback | ✅ verified | Quoted in §7 (D5). Also for `code2prompt` |
| 4.4 | *(gate)* All three behave correctly with and without their runtime | ✅ verified | All three installed here — including code2prompt, which the handover expected to be uninstallable |
| 4.5 | *(gate)* Budget truncation verified by inspecting output | ✅ verified | The truncated pack was read: five files gone, tree intact, note listing each with its cost |

**Score: 17 verified, 4 unverified, 0 failed.** All four unverified items trace
to the same cause — CI cannot schedule runners.

---

## 3. The whole corpus, end to end

Every fixture through auto-selection, `--tokenizer bytes`, output read.

| Fixture | Exit | Backend | Before | After | Change | What I saw |
|---|---|---|---|---|---|---|
| `article.html` | 0 | trafilatura | 3,560 | 2,854 | −19.8% | Clean article; extraction has nothing to remove, so the saving collapses. **The control case, behaving** |
| `boilerplate.html` | 0 | trafilatura | 12,481 | 2,854 | **−77.1%** | All 6 markers gone, 6 headings kept, table intact |
| `jsrendered.html` | 0 | trafilatura | 1,512 | 140 | −90.7% | **The content is not there.** See D1 — this is the one result that alarmed me |
| `corrupt.pdf` | **1** | — | — | — | — | Correct. All four PDF backends tried and named in the hint |
| `scanned.pdf` | 0 | pdfplumber | — | 0 | — | Empty, loudly. No OCR until Phase 9 |
| `simple.pdf` | 0 | pdfplumber | — | 2,370 | — | Headings and body intact |
| `tables.pdf` | 0 | pdfplumber | — | 599 | — | 35 of 35 cells as a Markdown table |
| `twocolumn.pdf` | 0 | pdfplumber | — | 4,050 | — | Columns interleaved, **and it warns** |
| `report.docx` | 0 | markitdown | — | 3,494 | — | docling would win this if installed; it is not here |
| `unicode.docx` | 0 | markitdown | — | 1,312 | — | Ten scripts round-tripped |
| `deck.pptx` | 0 | markitdown | — | 753 | — | Speaker notes kept |
| `data.xlsx` | 0 | markitdown | — | 675 | — | One table per sheet |
| `long_context.md` | 0 | plaintext | 79,255 | 79,255 | −0.0% | Passthrough, as designed |
| `sample_repo` | 0 | gitingest | — | 2,944 | — | Tree plus 7 files; secret absent |

**What looked wrong, and what I did about it.**

`jsrendered.html` is the one that matters. A **−90.7% reduction** achieved by
losing all the content — precisely what `benchmarks/README.md` names as
disqualifying, and nothing in the output said so. I fixed it during this review
rather than only writing it down; see D1.

Two things are working exactly as intended and are worth naming because they
look like problems: `corrupt.pdf` exiting 1, and `scanned.pdf` producing nothing
with a warning. Both fixtures exist to be failed on correctly.

`report.docx` selecting markitdown rather than docling is correct — docling is
not installed in this environment, and the fallback chain did its job silently
because there was nothing to fall back *from*.

---

## 4. Cross-cutting seams

The five questions the assignment asked, each answered with a check.

### Does the fallback chain still do the right thing?

**Yes.** For `boilerplate.html` with `documents` installed:

```
trafilatura -> readability -> markdownify_html -> markitdown -> kreuzberg
```

Every web backend outranks every document backend.

### Can an installed `documents` extra change which backend converts HTML?

**No, and this is checked rather than assumed.** markitdown, kreuzberg and
docling all claim `html`; all three rank below all three web backends in
`preferences.py`, and
`test_an_installed_documents_extra_cannot_change_which_backend_converts_a_page`
asserts it. The invariant written down in Phase 2 survives Phase 3 adding three
competitors for the same format.

### Is the error taxonomy still coherent across three domains?

**Yes — and notably, it did not grow.** Phases 3 and 4 added no new error class.
Everything raised in `src/` is one of the nine in the taxonomy.

Two places tempted me to add one, and both were resolved inside the existing
vocabulary:

- A `robots.txt` disallow is `NetworkRequired`, whose docstring already said
  "network access that is unavailable **or disallowed**".
- An oversized HTTP response is `CorruptSource`, matching `BaseConverter`'s
  existing treatment of an oversized file. **This one is a slight stretch** and
  is recorded as D7: "corrupt" is not what a 60 MB page is.

One raise is outside the taxonomy: `run_tool` raises `ValueError` on an empty
argv. That is a programming error, not a user-facing one, and `BaseConverter`
would wrap it in `BackendFailed` anyway.

### Does the per-stage token report still add up?

**Yes.** For every source kind, the last measured stage equals a direct count of
the final text:

| Source | Stages | before → after | last stage == count(final text) |
|---|---|---|---|
| `boilerplate.html` | source, convert, normalize_whitespace | 12,481 → 2,854 | ✅ |
| `tables.pdf` | convert, normalize_whitespace | — → 599 | ✅ |
| `sample_repo` | convert, normalize_whitespace | — → 2,944 | ✅ |

Phase 3 and 4 introduced two new source shapes and neither broke the accounting,
because both reuse the rules Phase 2 settled: a fetched page has a real `source`
stage (which is the entire reason the pipeline fetches rather than the backends),
and a repository has none, like a binary document.

**The gap:** the per-stage report describes *pipeline* stages, and the two most
interesting Phase 3–4 numbers are not stages. Boilerplate reduction happens
inside the converter; budget truncation happens inside a repository backend.
Both are reported — in `page:`, in warnings, in metadata — but neither appears as
a row in `--show-stages`. Recorded as D8.

### Is `--json` stable and complete?

**Stable between `convert` and `repo`** — byte-identical key sets, which matters
because `repo` was written after the shape was settled. `backends` and `tokens`
have their own shapes, correctly.

Two gaps, both D9: `tokens --json` omits `reduction_ratio`-style provenance that
`convert` carries, and the `web` object is `null` for non-web conversions where a
consumer might reasonably expect it absent. Neither is wrong; both are
inconsistencies a GUI would trip on.

### Is `warnings.catch_warnings` still only a Phase 8 concern?

**It is more urgent than it was, though still not urgent.** Phase 2 recorded one
use. There are now **five distinct pieces of process-global state** manipulated
during a conversion:

| What | Where | Restored? |
|---|---|---|
| `warnings.catch_warnings` (import-time warnings) | `backends/_common.py` | ✅ |
| `warnings.catch_warnings` (docling deprecation) | `documents/docling_adapter.py` | ✅ |
| `warnings.catch_warnings` (pathspec deprecation) | `repo/gitingest_repo.py` | ✅ |
| `os.environ` (`GITHUB_TOKEN`, `GH_TOKEN`) | `repo/gitingest_repo.py` | ✅ |
| stdlib root logger handlers **and level** | `repo/gitingest_repo.py` | ✅ |
| loguru activation registry | `repo/gitingest_repo.py` | ⚠️ re-enabled unconditionally |

All are correctly restored, all are scoped to one call, and **none is
thread-safe**. Today nothing runs conversions concurrently, so the assessment is
unchanged: a Phase 8 problem. But it has grown fivefold in one phase, and the
Phase 8 batch runner cannot simply run `Pipeline.run` on a thread pool. Recorded
as D2 — the severity is in the trajectory rather than in today's behaviour.

---

## 5. Clean install, by hand

Not the CI job — that has not run. `pip install .` into a fresh venv:

```
wall time: 11.7 s
packages:  41 (plus tokenmill itself)
size:      164 MB
import tokenmill pulls in third-party modules: NONE
```

**Under a minute ✅. Zero third-party imports at `import` time ✅.**

Graceful degradation from that install:

| Attempt | Result |
|---|---|
| `convert tables.pdf` | ✅ pdfplumber, 599 bytes |
| `convert boilerplate.html` | ✅ trafilatura, −77.1% |
| `repo sample_repo` | ⚠️ error naming the `repo` extra — **this was a defect I fixed during the review**, see D5 |
| `backends --all` | ✅ 13 rows, 5 greyed out, each with an install command |

Each extra installed separately, all succeeded:

| Extra | Packages | Size | Backends it enables |
|---|---|---|---|
| `documents` | 60 | **387 MB** | markitdown, kreuzberg |
| `web` | 43 | 130 MB | readability |
| `repo` | 54 | 136 MB | gitingest |
| `tokenizers` | 53 | 159 MB | `hf:` tokenizers |
| `crawl4ai` | 94 | 677 MB | crawl4ai (+ a browser download) |
| `docling` | 122 | 5.2 GB | docling |

**The core install grew from 72 MB to 164 MB in Phase 3**, almost entirely
trafilatura's lxml. Defensible — it is the backend the project's central claim is
measured with — but it is a 2.3× increase and nobody has decided it is
acceptable. Recorded as D4.

---

## 6. Toolchain

```
uv run ruff check .          → All checks passed!
uv run ruff format --check . → 93 files already formatted
uv run mypy                  → Success: no issues found in 76 source files
uv run pytest -q             → 828 passed, 49 skipped
uv run pytest --cov          → 89% overall; core+tokens 95.13% (gate: 85%)
make_fixtures.py --check     → OK: 23 files reproduced byte-for-byte
uv run pytest -q -m browser  → 8 passed
```

10,701 lines of source, 8,093 lines of tests, 877 tests. The 49 skips are all
named and all opt-in: docling absent (10), `network` (16), `browser` (8),
`heavy` (2), crawl4ai's correct `NetworkRequired` refusal (2), and others.

---

## 7. Defects

Severity: **high** = wrong output or a wrong number reaches a user; **medium** =
degraded behaviour, missing verification, or a trap for the next phase; **low** =
inconsistency or friction.

### Fixed during this review

**D1 — high — a great reduction achieved by losing the content.**
`convert jsrendered.html` reported `1,512 -> 140 (-90.7%)`, a number that would
look excellent in a benchmark and represents near-total content loss. Nothing
said so, because from a parser's view nothing went wrong.

Fixed: web backends now warn when a page carries scripts and under 15% of its
bytes are visible text. Calibrated on the corpus (76.3% / 39.3% / 9.2%), says it
is a heuristic, names `--backend crawl4ai`. Six tests, including the
false-positive side.

**D5 — medium — a clean install gave a Node error for a Python tool.**
On core-only, `tokenmill repo ./project` fell through to repomix (which reports
itself available because `npx` exists) and failed with npx instructions, never
mentioning `pip install "tokenmill[repo]"`. Found by doing the clean-install
check by hand rather than trusting the CI job. Fixed: the hint now depends on
whether the user *chose* repomix.

### Open

**D2 — medium — five pieces of process-global state, none thread-safe.**
§4. Correctly restored, correctly scoped, and a trap for Phase 8's batch runner.
The loguru re-enable is unconditional, so an application that had deliberately
disabled gitingest's logger will find it enabled again. *Lives in
`backends/_common.py`, `documents/docling_adapter.py`, `repo/gitingest_repo.py`.*

**D3 — medium — the publishable figure is unpublishable.**
Every number in `BENCHMARKS.md` is UTF-8 bytes. The claim the project exists to
make is about model tokens. The test that produces it runs only in CI, and CI
does not run. Not a code defect — a verification one — but it is the project's
headline.

**D4 — medium — the core install is 2.3× heavier than it was.**
72 MB → 164 MB, from trafilatura's lxml. Defensible, undecided. Also: the
`documents` extra is **387 MB**, which is not what §1.6's "light-ish" implies.
Phase 2 flagged it; nobody has revisited it.

**D6 — medium — parsing three tools' output formats is brittle.**
Budgeting and the breakdown need per-file structure and no tool offers one, so
each adapter carries a regex for its tool's file header. code2prompt's was
guessed wrong on the first try. Mitigated — an unrecognised format produces a
warning and no sections, never a silent zero — but an upstream format change
still costs a release. Repomix has `--style json`; using it would remove the
guesswork for one of the three. *`backends/repo/_common.py`.*

**D7 — low — `CorruptSource` for an oversized page.**
"Corrupt" is not what a 60 MB page is. It matches `BaseConverter`'s existing
treatment of an oversized file, so it is consistent rather than right. A
`SourceTooLarge` class would be additive; I did not add one, because growing the
taxonomy per phase is the failure mode §4 was checking for.

**D8 — low — the two most interesting numbers are not pipeline stages.**
Boilerplate reduction happens inside the converter and budget truncation inside a
repository backend, so neither appears in `--show-stages`. Both are reported
elsewhere. Phase 5's "measurement depth" is where this belongs.

**D9 — low — `--json` inconsistencies.**
`tokens --json` carries less provenance than `convert --json`; the `web` object
is `null` rather than absent for non-web conversions. A GUI would notice.

### Suspicions I could not prove

**S1 — the `--include`/`--exclude` globs probably differ between the three repo
backends.** They are passed to each tool rather than applied by tokenmill, and
each has its own dialect. I tested that they work, not that they agree. Proving
it needs a fixture repository with deliberately awkward paths.

**S2 — the client-rendered heuristic (D1's fix) is calibrated on one page.**
15% separates our three fixtures cleanly. A real minified page with heavy inline
JSON could plausibly fall under it and be flagged wrongly. The warning says it is
a heuristic, which is the honest mitigation, but I have not seen it meet a real
page.

**S3 — crawl4ai is verified against exactly one browser.** Chromium 1194, via a
local playwright pin that is deliberately not in `pyproject.toml`. Whether the
adapter works against whatever `playwright install chromium` gives a user today
is untested.

**S4 — I suspect `repomix --parsable-style` changes the section format** in some
edge case involving code fences inside Markdown files, which would silently
disable budgeting for that repository. The warning would fire, so it would not be
silent — but I have not constructed the case.

---

## 8. Should Phase 5 start?

**Yes, with one thing fixed first.**

### Fix before Phase 5

**D1 is already fixed** — it was too close to the project's core promise to leave
in a list. Phase 5 is where post-processors get aggressive about stripping, and
shipping "aggressive stripping" on top of a pipeline that reports a 90% saving
for losing all the content would have compounded the exact error.

That leaves nothing that must be fixed. But one thing must be **decided**:

**Get CI running, or accept a growing unverified surface.** Four acceptance
criteria across three phases are unverified for one reason. Phase 5 adds format
encoders whose correctness is exactly the kind of thing a 9-cell matrix catches
and a Linux box does not (`TOON` and `CSV` round-tripping is where encoding and
line-ending differences live). Only you can look at the Actions billing page.

If it cannot be fixed, that is a real answer too — but then Phase 5 should
budget for the fact that **Windows, macOS, Python 3.12/3.13 and real tokenizers
are all unverified**, and `PROGRESS.md` should stop implying CI is a safety net.

### Why Phase 5 is otherwise well-placed

The seams that would have made it painful are sound. The taxonomy did not grow
under two phases of pressure. The per-stage report survived two new source
shapes. The preference invariant held against three new competitors for `html`.
`--json` is stable between the two commands that share a shape. Phase 5 extends
`TokenMeter` and adds `compare`, and both build on machinery that has now been
stress-tested by exactly the kind of change they represent.

Two Phase 5 items have groundwork already:

- **`compare`** is the natural home for the comparison this review kept wanting.
  "Which backend is best for this file" is answered ad hoc in `BACKENDS.md`; it
  should be a command. It is also the honest answer to a repository or a document
  having no before-count.
- **Per-stage measurement depth** should absorb D8.

### One piece of advice about scope

Phase 5's deliverable list contains the sentence *"the docs are honest:
structure-preserving beats maximal stripping"*. That is the phase's real risk.
Every post-processor in it can be measured as a win in tokens and a loss in
fidelity, and this project currently has **no fidelity metric** — only pass/fail
assertions. Consider bringing a small piece of Phase 10 forward: a fidelity score
that makes "this saved 20% and lost the table" expressible as a number. Without
it, Phase 5's defaults will be argued rather than measured.

---

## 9. What I would tell the next session

- **The corpus is the product's conscience.** Every real bug this phase came from
  running something against it and reading the output. Nothing came from
  reasoning about code.
- **Two claims I wrote before measuring were both wrong** — readability's
  precision/recall trade, and trafilatura's behaviour on link-heavy pages. Both
  came from a library's general reputation. The corpus disagreed with both.
- **`--tokenizer bytes` is what makes this environment workable**, and it is
  also the thing most likely to produce a dishonest document. Every byte figure
  here says it is bytes.
- **Check the failure paths of the tools you wrap, not just their outputs.** Four
  of Phase 4's defects were things gitingest does to the *process*, none visible
  in its packed output.
