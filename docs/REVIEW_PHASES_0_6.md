# Review: Phases 0 through 6

**Date:** 2026-08-24. **Reviewer:** the session that built the fidelity slice,
Phase 5 and Phase 6.
**Supersedes:** [`REVIEW_PHASES_0_4.md`](REVIEW_PHASES_0_4.md), which stays in
the repository because its defect numbering is referenced everywhere and
because a superseded review that disappears is a review nobody can check.

The same caveat as last time, and it applies harder: **I built all three pieces
of work being reviewed.** Where I judge my own work the judgement is worth less
than the evidence beside it. Every claim below names the command that produced
it or is marked unverified, and the defects I introduced are in the list with
everyone else's.

---

## 1. Verdict first

**tokenmill can now state what a token saving cost, and it says so in the same
row as the saving.** That was the project's stated purpose and until this
session it was not possible. The instrument exists, the things it measures
exist, and the numbers are published beside the ones they qualify.

**The single most important result in the repository** is one line of the
corpus table in §3:

| Fixture | Backend | Bytes | Change | Fidelity |
|---|---|---|---|---|
| `jsrendered.html` | `trafilatura` | 140 | **−90.7%** | **0.000** |

The largest reduction in the corpus, achieved by losing every word of the
article. Before this session that row read `−90.7%` and nothing else, and it
would have been the best-looking number on the benchmarks page.

**Three things are wrong**, in descending order of how much they should worry
you:

1. **CI has still never run.** Runs 25 through **76** now — more than two days —
   including the eleven runs this session's own commits triggered. Nothing in
   any of this work is verified on Windows, macOS, Python 3.12/3.13, or against
   a real tokenizer. **That surface has roughly doubled this session.**
2. **Phase 6's exit gate is not passed and cannot be here.** The compressor is
   implemented and its success path has never been executed anywhere. That was
   your explicit choice between two options and it is recorded honestly, but it
   is a real hole and it is the first phase to end amber.
3. **Every number this project publishes is still in bytes.** Defect D3, made
   worse in scope: the format comparison is now also bytes-only, and the
   published figures it is set beside (CSV −56%, TOON −42.6%) are token
   figures.

**Recommendation: do not start Phase 7 yet.** See §6 — there is one thing to
decide and one small thing to repair first, and neither is Phase 7.

---

## 2. Acceptance criteria

### The Phase 10 fidelity slice

| # | Criterion | Status | Evidence |
|---|---|---|---|
| F.1 | markdownify on `boilerplate.html`: high recall, near-zero boilerplate rejection | ✅ verified | content 1.000, headings 1.000, rejection **0.000** |
| F.2 | trafilatura on the same: high recall, rejection 1.0 | ✅ verified | 1.000 / 1.000 / **1.000** |
| F.3 | kreuzberg's table integrity well below pdfplumber's on `tables.pdf` | ✅ verified | **0.000 vs 1.000** |
| F.4 | An empty string scores near zero on everything | ✅ verified | 0.0 on every scored component; needed an explicit rule, see §5 N-note |
| F.5 | A component with no ground truth returns `None`; the overall names its components | ✅ verified | API, `n/a` in the table, `null` in JSON |
| F.6 | *(gate)* Backend × fixture table in `BENCHMARKS.md` beside the token figures | ✅ verified | 38 rows |

**6 of 6.**

### Phase 5

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 5.1 | Per-stage report arithmetically consistent | ✅ verified | Each stage equals a direct count; two new intermediate rows and it still closes |
| 5.2 | TOON/CSV round-trip losslessly, property-based | ✅ verified | 200 examples/format; **found 7 real bugs** |
| 5.3 | Every destructive post-processor declares it and is out of the default chain, asserted registry-wide | ✅ verified | Default chain is still exactly `normalize_whitespace`, with **eight** processors registered |
| 5.4 | Docs honest about structure vs stripping, cited, conservative defaults | ✅ verified | `BENCHMARKS.md`, with three stated reasons our numbers are not confirmation of the published ones |
| 5.5 | *(gate)* `compare` correct against manual counts | ✅ verified | **9 of 9 against `wc -c`**, and a test asserts it |
| 5.6 | *(gate)* Round-trip property tests pass | ✅ verified | 53 tests |
| 5.7 | *(gate)* Every new post-processor scored by the fidelity metric and published | ✅ verified | Seven processors, bytes and fidelity |

**7 of 7.** One deviation from the plan's wording, flagged rather than absorbed:
`--format toon` is deliberately not implemented (§5, Open question 3).

### Phase 6

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 6.1 | Achieves a measurable ratio on a long fixture and reports it accurately | ❌ **not verified, not verifiable here** | Needs `huggingface.co`. **No ratio has ever been produced by this code** |
| 6.2 | First-run download explicit, resumable, skippable; nothing downloads at import | ✅ verified | Refusal names size, cache path and command; loading all eight post-processors imports **zero** third-party modules |
| 6.3 | Fully offline once cached | ⚠️ **partly** | The `local_files_only` mechanism is tested both ways; there is no cache here to demonstrate against |
| 6.4 | *(gate)* Ratio verified against direct token counts | ❌ **not verified** | Same cause |
| 6.5 | *(gate)* Offline-after-cache proven | ❌ **not proven** | Same cause |

**2 verified, 1 partial, 2 not verifiable. Phase 6's gate is not passed.**

**Running total across all seven phases: 32 verified, 1 partial, 6 unverified,
0 failed.** Every unverified item traces to one of two causes — CI cannot
schedule runners, or a host is denied at the egress proxy.

---

## 3. The whole corpus, tokens beside fidelity

Every installed backend against every fixture it claims, through the current
default post-processor chain, `--tokenizer bytes`, 2026-08-24. **This is the
table the project has been building towards since Phase 0**, and it is the
first time it has been possible to produce it.

| Fixture | Backend | Bytes | Change | Fidelity |
|---|---|---|---|---|
| `article.html` | `trafilatura` | 2,854 | −19.8% | 1.000 |
| `article.html` | `readability` | 2,864 | −19.6% | 1.000 |
| `article.html` | `markitdown` | 2,864 | −19.6% | 1.000 |
| `article.html` | `markdownify_html` | 2,916 | −18.1% | 1.000 |
| `article.html` | `kreuzberg` | 3,063 | −14.0% | 1.000 |
| `boilerplate.html` | `trafilatura` | 2,854 | **−77.1%** | **1.000** |
| `boilerplate.html` | `readability` | 2,864 | −77.1% | 1.000 |
| `boilerplate.html` | `kreuzberg` | 6,120 | −51.0% | 0.750 |
| `boilerplate.html` | `markitdown` | 6,713 | −46.2% | 0.750 |
| `boilerplate.html` | `markdownify_html` | 6,802 | −45.5% | 0.750 |
| `jsrendered.html` | `trafilatura` | 140 | **−90.7%** | **0.000** |
| `jsrendered.html` | `markitdown` | 140 | **−90.7%** | **0.000** |
| `jsrendered.html` | `markdownify_html` | 165 | −89.1% | 0.000 |
| `jsrendered.html` | `readability` | 167 | −89.0% | 0.000 |
| `jsrendered.html` | `kreuzberg` | 180 | −88.1% | 0.000 |
| `corrupt.pdf` | all four | **fail** | — | — |
| `scanned.pdf` | all four | 0 | — | **0.000** |
| `simple.pdf` | `kreuzberg` | 2,371 | — | **0.900** |
| `simple.pdf` | `pdfplumber` | 2,370 | — | 0.500 |
| `simple.pdf` | `pypdf` | 2,371 | — | 0.500 |
| `simple.pdf` | `markitdown` | 2,377 | — | 0.500 |
| `tables.pdf` | `pdfplumber` | 599 | — | **0.667** |
| `tables.pdf` | `markitdown` | 769 | — | 0.606 |
| `tables.pdf` | `kreuzberg` | **466** | — | 0.500 |
| `tables.pdf` | `pypdf` | 481 | — | **0.333** |
| `twocolumn.pdf` | `kreuzberg` | 4,061 | — | **0.667** |
| `twocolumn.pdf` | `pypdf` | 4,050 | — | **0.667** |
| `twocolumn.pdf` | `pdfplumber` | 4,050 | — | 0.528 |
| `twocolumn.pdf` | `markitdown` | 4,062 | — | 0.528 |
| `report.docx` | `markitdown` | 3,494 | — | **0.841** |
| `report.docx` | `kreuzberg` | 3,472 | — | 0.614 |
| `unicode.docx` | `kreuzberg` | 1,314 | — | **1.000** |
| `unicode.docx` | `markitdown` | 1,312 | — | 0.955 |
| `deck.pptx` | `markitdown` | 753 | — | 1.000 |
| `deck.pptx` | `kreuzberg` | 398 | — | 1.000 |
| `data.xlsx` | `kreuzberg` | 664 | — | **1.000** |
| `data.xlsx` | `markitdown` | 675 | — | 0.667 |
| `structured.md` | `plaintext` | 1,466 | −0.2% | 1.000 |
| `long_context.md` | `plaintext` | 79,255 | +0.0% | n/a |
| `sample_repo` | `gitingest` | 2,944 | — | 1.000 |
| `sample_repo` | `repomix` | **fail** | — | — |

`crawl4ai`, `docling` and `code2prompt` are not installed here and have no rows.
`repomix` needs `npx` and is absent from this container.

### What this table says that no previous table could

**On four of the eleven scorable fixtures, the cheapest backend is not the best
one.** `tables.pdf` is the clearest: kreuzberg is 22% cheaper than pdfplumber
and gets there by destroying the table. A benchmark sorted by size would have
recommended it.

**Two fixtures show the cheapest option also being the best** —
`boilerplate.html` (trafilatura wins both) and `sample_repo`. Those are real
wins and the table lets you tell them apart from the other kind.

**Fidelity is not a proxy for size.** `unicode.docx` and `deck.pptx` score 1.000
across every backend that handles them; the differences there are real but
invisible to this metric, which is a limit of the ground truth, not a verdict.

---

## 4. Defects from the previous review

| # | Severity | Status |
|---|---|---|
| **D1** | high | ✅ **Closed and strengthened.** Was fixed with a warning last session; it is now also a **number**: `jsrendered.html` scores 0.000 in the published table |
| **D2** | medium | ⚠️ **Open, and I made it slightly worse.** See below |
| **D3** | medium | ⚠️ **Open, and wider.** Every new figure is also in bytes |
| **D4** | medium | ⚠️ **Open, but no longer growing.** Core did not grow this session |
| **D6** | medium | ⚠️ **Open, untouched.** `repomix --style json` is still unused |
| **D7** | low | ⚠️ **Open, untouched** |
| **D8** | low | ✅ **Closed** |
| **D9** | low | ✅ **Closed** |
| **S1** | suspicion | ⚠️ Unproven, untouched |
| **S2** | suspicion | ⚠️ Unproven, but now has a second independent signal |
| **S3** | suspicion | ⚠️ Unproven, untouched |
| **S4** | suspicion | ⚠️ Unproven, untouched |

### D2 — I said I added no process-global state, and that was not quite right

**This is a correction to my own commit message**, made here rather than by
editing it away.

The Phase 6 commit says the compressor *"adds nothing to the five pieces of
process-global state ARCHITECTURE.md already records"*. That is true of the
thing it was about — no environment variable is set, because `local_files_only`
rides in llmlingua's `model_config` instead of `HF_HUB_OFFLINE` — and **read
plainly it overstates**. The compressor uses `warnings.catch_warnings` to keep
transformers' import-time noise non-fatal under `-W error`, which is a
**fourth** use of `catch_warnings` where the previous review counted three:

```
src/tokenmill/backends/_common.py                  catch_warnings
src/tokenmill/backends/documents/docling_adapter.py catch_warnings
src/tokenmill/backends/repo/gitingest_repo.py      catch_warnings
src/tokenmill/post/compress.py                     catch_warnings   <- new
src/tokenmill/backends/repo/gitingest_repo.py      os.environ, root logger, loguru
```

The **kinds** of global state are unchanged, and the new use only executes when
compression runs, which is off by default and behind an extra. But the count
went up and the handover asked to be told. Consider it told.

### D3 — the unpublishable figure, now with more company

Nothing here changed for the better. The format comparison — the most
quotable-looking thing added this session — is bytes, and the published figures
it sits beside are tokens. `BENCHMARKS.md` states that three times on the page
and refuses to draw the conclusion, which is the best available mitigation and
is not a fix.

### D4 — open, and at least no longer growing

Core did not grow. Chonkie went into a `chunk` extra on your decision, with the
measurement (+10 packages, `lib/` 126 MB → 196 MB) rather than an adjective.

**One correction to the previous review's numbers**, which matters because they
get quoted: it recorded core as **164 MB**. Measured today, the same install is
**126 MB of `lib/`** and **196 MB of whole virtualenv**. Those are two different
measurements of two different things, taken two days apart with different
dependency versions. **Neither is wrong; they are not comparable**, and
`BENCHMARKS.md` should say which is meant before either is quoted again.

---

## 5. New defects

| # | Severity | Defect |
|---|---|---|
| **N1** | medium | **Phase 6's success path has never run.** Not a code defect — a verification hole, and the largest one in the repository. Everything about compression is written and untested where it matters |
| **N2** | medium | **A post-processor cannot warn or attach metadata.** `process(text, options) -> str` is the whole contract, where a backend gets a `ConversionContext`. The compressor logs instead of warning and cannot attach its own ratio. Phase 8's GUI will want this; fixing it is a breaking change to the Phase 1 contract |
| **N3** | low | **Two Markdown table parsers now exist** — `fidelity/markdown.py` and `formats/markdown_table.py` — with deliberately different strictness. They should probably be one module with a strictness flag |
| **N4** | low | **`compare --formats` re-encodes only the first table** in the converted text. Fine on the fixtures, wrong on a real report |
| **N5** | low | **`aggressive_whitespace` has no demonstrated benefit.** +0.0% on two fixtures, −0.1% on the third. It ships with that printed next to it, which is honest, but nothing in the corpus shows it earning its place |
| **N6** | low | **`destructive` means two things now.** See Open question 2 |
| **N7** | low | **`compare`'s timings are single unrepeated runs.** The 20 ms vs 1,040 ms gap on `report.docx` is indicative and nothing more. Phase 10 owns this |
| **N8** | low | **Fidelity has no component for metadata loss.** `strip_frontmatter` scores 1.000 while deleting a title, tags and a draft flag. `BENCHMARKS.md` says so explicitly, which is mitigation rather than a fix |

**A note on F.4, because it is the design decision I would defend hardest.**
The empty-document rule is an explicit special case, not an emergent property.
The arithmetic scores an empty string **1.0** on boilerplate rejection — it
genuinely contains no boilerplate — so the instrument built to catch a destroyed
document would have credited it with perfect extraction. No arrangement of
fractions produces the right answer; it had to be written down.

---

## 6. Should Phase 7 start?

**Not yet.** Phase 7 is licence isolation, and it is the one phase the plan says
must not be skipped before a public release. It deserves a clean run at, and
there are two things in front of it.

### Decide first (yours, not mine)

**1. CI, again, and now urgently.** Runs 25–76. This session roughly doubled
the unverified surface: five post-processors, five encoders, a comparison
command, a chunker and a compressor, none of them ever run on Windows, macOS,
Python 3.12/3.13, or against a real tokenizer. The format encoders are exactly
the kind of code a 9-cell matrix catches and a single Linux box does not —
line endings, `str.strip()` semantics, filesystem encodings. **hypothesis found
seven real bugs in that code on one platform.** I would not want to guess what
three platforms would find.

Phase 7 adds subprocess isolation, which is *more* platform-sensitive than
anything here, not less. Starting it with CI dead is choosing to write the most
OS-dependent code in the project with the OS matrix switched off.

**2. Open question 2 — what `destructive` means.** Three options are in
`PROGRESS.md` with a recommendation. It is a ten-minute decision that gets
harder the more post-processors exist.

### Repair first (small, and mine)

**N3, the two Markdown table parsers.** An hour's work to merge them, and the
right time is before a third one appears.

Nothing else. **D2, D3, D4, D6, D7 and S1–S4 should all stay open** — none
blocks Phase 7, and closing D3 needs the egress policy to change rather than
code.

### Why Phase 7 is otherwise well-placed

The seams it needs are in better shape than they were:

- **The taxonomy still has not grown.** Three phases of pressure, including a
  compressor and five encoders, and everything raised in `src/` is still one of
  the nine classes. `formats` deliberately raises `ValueError` rather than
  adding a tenth.
- **The plugin mechanism took a fourth entry point group without a special
  case.** `tokenmill.formats` works exactly like the other three.
- **`compare` gives Phase 7 the thing it needs to prove itself.** "A copyleft
  backend works via subprocess and is never imported" becomes checkable *and*
  comparable: run PyMuPDF4LLM against pdfplumber on `tables.pdf` and read
  tokens and fidelity in the same row.
- **The fidelity scorer means Phase 7's adapters arrive with a number.** Every
  backend added from here on can be placed in §3's table on the day it lands.

### One piece of advice about scope

Phase 7's deliverable list contains *"a test that asserts no AGPL/GPL package is
importable from our process namespace"*. That test is the phase. Write it first,
watch it fail against a deliberately introduced violation, and let the adapters
follow it — because a licence isolation mechanism that was never seen to catch
anything is indistinguishable from one that does not work.

---

## 7. What I would tell the next session

- **Read the output, then read it again.** Two of this session's real bugs came
  from looking at what a post-processor actually emitted — `draft: false`
  becoming a heading, and a heading remap that still skipped a level. Neither
  test suite caught them because both produced perfectly plausible output.
- **`hypothesis` earns its keep immediately.** Seven bugs on first use, all in
  code with passing example tests. Four were Unicode edge cases no one would
  think to write by hand. If you add an encoder, property-test it before you
  write a single example.
- **The unflattering measurement is the useful one.**
  `aggressive_whitespace` saving 0.0%, reference links *costing* 0.5%, chunking
  *costing* 1.8% — those are the numbers that tell a user something. The ones
  that look good mostly confirm what the docs already claimed.
- **A number that needs an apology under it should not be the headline.** That
  was Phase 2's lesson about binary documents and it applies to fidelity scores
  too: `strip_frontmatter` scores 1.000 and deleted the title.
