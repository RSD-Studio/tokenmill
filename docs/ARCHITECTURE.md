# Architecture

**Status:** current as of Phase 2. Everything described here exists and is
tested; nothing below is a plan. Where a later phase changes something, that is
called out explicitly.

This document is the reasoning behind the design, recorded while it was fresh.
The contract itself — the types, the protocol, the taxonomy — is
[`docs/DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md) §1, and changes to it are
breaking changes requiring the owner's agreement.

---

## The shape of the thing

tokenmill is a library with a CLI on top. The library does all the work; the CLI
parses arguments, calls the library and formats what comes back. The Phase 8 GUI
will do exactly the same, which is what keeps the boundary honest — if a
capability is not reachable from the public API, no surface gets it.

```
                       ┌──────────────┐   ┌──────────────┐
                       │  CLI (typer) │   │  GUI (P8)    │
                       └──────┬───────┘   └──────┬───────┘
                              └────────┬─────────┘
                                       │  public API: tokenmill.convert(...)
                              ┌────────▼─────────┐
                              │     Pipeline     │
                              └────────┬─────────┘
             ┌─────────────────────────┼─────────────────────────┐
             │                         │                         │
      ┌──────▼───────┐        ┌────────▼────────┐       ┌────────▼────────┐
      │   Registry   │        │ PostProcessor   │       │    Tokenizer    │
      │  (backends)  │        │    Registry     │       │    Registry     │
      └──────┬───────┘        └────────┬────────┘       └────────┬────────┘
             │                         │                         │
   entry points:              entry points:             entry points:
   tokenmill.backends         tokenmill.postprocessors  tokenmill.tokenizers
             │                         │                         │
   ┌─────────┴─────────┐     ┌─────────┴────────┐      ┌─────────┴────────┐
   │ plaintext         │     │ normalize_       │      │ tiktoken         │
   │ markdownify_html  │     │   whitespace     │      │ hf     (lazy)    │
   │ pdfplumber        │     │ links            │      │ units  (bytes)   │
   │ pypdf             │     │                  │      │                  │
   │ markitdown (opt)  │     │                  │      │                  │
   │ kreuzberg  (opt)  │     │                  │      │                  │
   │ docling    (opt)  │     │                  │      │                  │
   │ …third-party…     │     │                  │      │                  │
   └───────────────────┘     └──────────────────┘      └──────────────────┘
```

Three registries, one mechanism. Backends, post-processors and tokenizers are
all plugins found through entry point groups, and the built-ins register through
the same groups a third party would use. There is no hard-coded import list
anywhere in the codebase. That is not tidiness for its own sake: it is the only
way "you can add a backend without touching core" can be *true* rather than
aspirational, and `tests/unit/test_registry.py` asserts it by registering a
backend the package has never heard of.

---

## The data model

`src/tokenmill/core/models.py`. Every type is a **frozen dataclass**.

### Why dataclasses and not pydantic

The plan allowed either. Dataclasses won for one concrete reason: `import
tokenmill` then pulls in nothing but the standard library, which is what makes
the `clean-core-install` CI job meaningful and keeps CLI start-up fast. Pydantic
would buy validation at trust boundaries, and tokenmill has none — this is a
library API called by our own CLI and GUI, not a request parser. When Phase 8
adds an HTTP surface that does have a trust boundary, pydantic models belong
*there*, at that boundary, not in the core model.

### Why frozen

A `ConversionResult` is a record of something that already happened, and it
carries enough provenance to reproduce it: which backend ran, which
post-processors ran in which order, which tokenizer measured it, how long it
took. Mutating one after the fact would make that provenance a lie.

### `TokenCount`, and why there is no bare int

```python
TokenCount(value=4102, tokenizer_id="o200k_base")
```

"4,102 tokens" is not a fact. The same text is a different number under
`o200k_base` than under `cl100k_base`, so a count without its tokenizer cannot
be compared with anything. Binding the two together makes the incomparable
impossible to compare by accident: `TokenMeter.delta` returns `None` when asked
to subtract counts from different tokenizers, rather than returning a number
that looks like an answer.

The same instinct runs through the rest of the model. `reduction_ratio` is
`None` — never `0.0` — when the input was empty or a count is missing, and it
goes *negative* when a conversion made the text bigger, because that is a real
outcome and clamping it would hide a genuine regression.

### `Availability`

Not a boolean. A backend that cannot run has a reason (`missing dependency`,
`missing binary`, `unsupported`, `broken`), the names of what was looked for,
and a hint saying how to fix it. The CLI prints the reason; the GUI will render
the hint as the call to action. A bare `False` would force every surface to
reinvent that explanation.

### Licence as enforced metadata

`BackendInfo` carries `license`, `license_tier` and `isolation`, and
`__post_init__` **raises** if a copyleft or non-commercial backend claims
`IsolationMode.IN_PROCESS`. `CONTRIBUTING.md` rule 2 says AGPL/GPL code is never
imported into our process; putting the check in the constructor means a
violating adapter cannot be *built*, let alone registered. The registry re-checks
at registration in case a plugin assembles its metadata by some other route.
Phase 7 adds the import-level enforcement suite on top of this.

---

## The backend protocol

`src/tokenmill/core/protocol.py`. Three methods:

```python
class Converter(Protocol):
    info: BackendInfo

    def is_available(self) -> Availability: ...
    def supports(self, source: Source) -> bool: ...
    def convert(self, source: Source, options: ConvertOptions) -> ConversionResult: ...
```

It is three methods on purpose. The protocol is the single most expensive thing
here to change once third parties implement it, so every hook nobody needs yet —
streaming, progress callbacks, batching — has been deliberately left out. They
can be added later; they cannot be removed later.

### `BaseConverter` carries the shared behaviour

An adapter author implements one method, `_convert`. By the time it is called,
`BaseConverter` has already checked availability, checked format support and
enforced the size limit, and it will time the call, collect warnings and
metadata from the `ConversionContext`, and assemble the result.

Crucially it also guarantees the error contract: anything a backend raises that
is not a `ConversionError` gets wrapped in `BackendFailed`. A backend with a bug
still reaches the user as a typed, printable error rather than a traceback out
of the CLI.

### Availability probes are cheap, cached, and never raise

`tokenmill backends` probes every backend on every invocation, and the Phase 8
GUI will repaint the list far more often than that. So probes check for a module
with `importlib.util.find_spec` or an executable on `PATH` — never a real import,
which costs whatever the dependency costs. Results are cached per instance, and
the registry holds one instance per process.

A probe that raises is caught and reported as `Availability.broken(...)`. A
probe is a question, and a question should not be able to crash the program.

### Backends do not measure

A `ConversionResult` coming out of a backend has `tokens_before is None`. The
pipeline fills the counts in. This means an adapter author never has to know a
tokenizer exists, and — more importantly — no backend can report a number that
bypasses the per-stage accounting. The conformance suite asserts it.

---

## Discovery, and why it is cached

Entry point discovery means *importing every registered plugin*. With a dozen
backends installed that is the dominant cost of CLI start-up, and the plan flags
it as a risk. So:

- Each registry defers its scan until the first lookup, not to import time.
- The scan runs once per registry; `default_registry()` holds one per process.
- Availability probes are cached per backend instance, so repeated listings cost
  one probe each rather than one per call.

The pipeline builds all three registries once and reuses them for the whole run.

### Broken plugins degrade, they do not propagate

A plugin whose entry point raises on import is caught, recorded as a
`BrokenBackend` with its error text, and surfaced as a backend whose availability
is `broken`. It appears in `tokenmill backends --all` as a row saying it failed
to load, and asking for it by name gives `BackendUnavailable` carrying the load
error.

This is Phase 1's exit gate, and the reasoning is worth stating: the failure is
in somebody else's code, and the cost of propagating it is that one bad
third-party plugin removes every other backend from the program. Hiding it
instead is no better — then the user cannot work out why the backend they
installed never appeared. Recording and reporting it is the only option that
leaves the user able to act.

### Selection order, and why it is per format

An explicitly requested `--backend` always wins. If it cannot run, that is an
error, not an invitation to substitute something else: silently converting with
a different backend than the user asked for would make the resulting measurement
unattributable, which defeats the point of measuring.

Otherwise, among backends that claim the source's format *and* can currently run:

1. highest **effective** priority (see below);
2. in-process before out-of-process, because a subprocess costs more;
3. by id, so the outcome is deterministic rather than dependent on entry point
   iteration order.

Phase 1 had one candidate per format, so "highest declared `priority`" was
enough. Phase 2 broke that. Five document backends overlap heavily — four
convert PDFs, three convert every Office format — and *best* turns out to be a
different backend for each format. MarkItDown is the right choice for `.pptx`
(the only one that keeps speaker notes) and the wrong one for `.docx` (it demotes
the title to body text). A single global integer cannot say both.

So `src/tokenmill/core/preferences.py` holds a **per-format map**, and effective
priority is:

```python
FORMAT_PREFERENCES.get(source_format, {}).get(backend_id, info.priority)
```

A number in the map **replaces** the backend's declared priority for that one
format. A backend the map does not mention keeps its own. Three properties
follow, and all three were the point:

- **The map is a default, not a gate.** A third-party PDF backend declaring
  `priority=100` outranks everything we ship, without editing core. That keeps
  the "add a backend without touching core" promise true.
- **Ranking is not filtering.** Availability is applied first, so an
  uninstalled backend never reaches the ordering.
- **Every number is evidence.** Each entry cites an observation on our own
  fixture corpus, `docs/BACKENDS.md` quotes the output it came from, and
  `tests/unit/test_preferences.py` asserts the map is well formed — every id it
  names exists, and every backend it ranks for a format actually claims that
  format.

When nothing available claims the format, the error distinguishes "no backend
handles this" from "a backend handles it but is not installed" — those need
different actions from the user.

### The fallback chain

`Registry.candidates()` returns the whole ordered chain; `select()` is now just
its head. The pipeline walks the chain until one backend succeeds. This is the
same mechanism as the preference map rather than a second one: uninstall the
preferred backend and it drops out of the ordering; leave it installed and let
it fail on a particular file and the pipeline moves on.

Two rules stop that becoming a way to hide failures.

**Every attempt is recorded.** `ConversionResult.attempts` carries a
`BackendAttempt` per backend tried, and each failure also attaches a warning
naming the backend and its error. A conversion that quietly came from the third
choice would otherwise look exactly like one the preferred backend handled, and
the measurement would be attributed to a converter that never ran. The CLI
prints an `attempts:` line only when a fallback actually happened.

**An explicit `--backend` never falls back.** Its chain is one long. `--no-fallback`
turns the chain off for auto-selection too, for anyone who would rather see the
preferred backend's error than a substitute's output.

When every candidate fails, the *last* error is re-raised — its class, its
`__cause__` and its traceback are all worth keeping — with its hint amended to
name everything that was tried.

### A binary document has no "before", so it is not given one

Phase 2 first shipped a number that was arithmetically fine and semantically
empty: converting a `.docx` reported `68,190 -> 3,494`, where the first figure
was the zip archive's own bytes decoded as text. Nobody hands a model the bytes
of a `.docx`, so that figure cannot be subtracted from anything and the
percentage between the two was not a saving.

The first fix printed it with a warning. That was honest and wrong, for a reason
worth recording: **it spent the warning budget.** Phase 2's other warnings —
an empty document from a scanned PDF, interleaved columns, a missing `exiftool`
— are ones a user must act on. Attaching a disclaimer to *every* document
conversion trains people to skim the block those live in. A number that needs an
apology under it is a number that should not be the headline.

So the shape of the report now depends on the kind of source:

| Source | Headline |
|---|---|
| text — `.html`, `.md`, `.txt`, a URL | `tokens: 12,481 -> 6,802 (-45.5%)` |
| binary — `.pdf`, `.docx`, `.pptx`, `.xlsx` | `tokens: 3,494` plus `size: 37.4 KiB in, no comparable before` |

Three things follow, and each was a deliberate choice:

- **There is no `source` stage for a binary input**, rather than an unmeasured
  one. If the source stage merely had no token count, `tokens_before` would fall
  through to the *first measured* stage — the converter's own output — and
  "before" would silently come to mean "after conversion". That is a worse lie
  than reporting nothing, and `Pipeline.run` guards against it explicitly.
- **The shape changes, not the meaning.** One number instead of two is visibly
  different at a glance. Keeping the two-number shape while quietly changing
  what the pair means would be the real trap.
- **The size is reported as a size**, in bytes, in binary units. It is a true
  fact about the input and it is not pretending to be a token count.

The comparison that *is* meaningful for a document is between backends on the
same file — `tokenmill compare`, Phase 5. The before/after pair keeps its full
meaning where both sides really are text a model could be given: raw HTML
against extracted Markdown in Phase 3, and compression in Phase 6.

---

## Fetching happens in the pipeline, not in the backends

`src/tokenmill/backends/web/fetch.py`, called from `Pipeline.run`.

A URL source is retrieved once, before any converter sees it, and what the
converters receive is bytes. Three things follow, and the third is the reason.

**One policy point.** The user agent, the timeout, the redirect limit, the byte
cap and `robots.txt` are decided in one function. Four web backends cannot end
up obeying four different sets of rules, and there is exactly one place that can
open a socket — which is what makes "converting a local file makes no network
call" provable rather than asserted.

**One fetch.** Walking a fallback chain would otherwise re-download the page for
each candidate.

**A real before-count.** This is the load-bearing one. The downloaded HTML
becomes an ordinary readable source, so the `source` stage measures it, and
"12,481 bytes of HTML became 2,854 bytes of Markdown" is a measurement. A
backend that fetched privately would leave the pipeline with nothing to compare
against, and the headline number would be an assertion about a quantity nobody
counted.

It also means the *response* decides the format rather than the URL.
`https://example.com/blog/post` is an HTML page whose path ends in `post`, and a
URL serving `application/pdf` routes to the PDF backends — `Source.format_hint`
carries that decision.

### The one backend that is exempt, and why only one kind can be

A converter declaring `BackendInfo.fetches_urls` is handed the raw URL. Exactly
one does: `crawl4ai`, which drives a browser so the page's JavaScript runs.
That cannot be done to a response somebody already saved, so for that backend
the fetch *is* the contribution.

Such a backend is never auto-selected. It has to be named, and naming it is what
skips the pre-fetch. Launching a browser inside a command a user thought was a
download is the same mistake as starting a several-hundred-megabyte model
download, which the preference map already settled for docling's PDF path.

### `fetch` and `allow_network` are two permissions, not one

`ConvertOptions.fetch` defaults to **true**; `allow_network` defaults to
**false**. That looks inconsistent until you see what each authorises.

Naming a URL *is* the request to fetch that URL. Refusing to do the thing the
user typed, pending a second flag, is not a security posture — it is an
obstacle. So `fetch` permits **one retrieval of the address the user supplied**,
and nothing else.

`allow_network` governs everything a backend might reach for on its own
initiative: a layout model, a tokenizer vocabulary, a browser loading whatever
subresources a page asks for. That stays default-deny, and the guarantee it
protects — a local conversion never reaches out — is unchanged, because a local
file never enters the fetch path at all.

`--offline` sets `fetch` to false, which makes tokenmill refuse the retrieval
rather than perform it. A test asserts it refuses *before* opening a socket,
because fetching and then discarding would satisfy the letter of it and none of
the point.

### Two numbers for a web page, deliberately not one

`tokens_before → tokens_after` counts everything that went away: tags, scripts,
styles **and** page furniture. A web backend additionally records
`boilerplate_reduction`: the share of the page's *visible text* it discarded,
measured against a tag-stripped, script-free rendering of the same page.

They answer different questions, and on our fixture they disagree usefully.
`markdownify_html` removes 45.5% of the file's bytes and discards **no** text at
all — its boilerplate figure is *negative*, because Markdown bullets, link
targets and table pipes cost characters. `trafilatura` removes 77.1% of the
bytes and 41.7% of the text.

A converter cannot score well on both by accident, and reporting either as the
other is precisely the misattribution `RESEARCH.md` Category 7 is about: *"the
savings come overwhelmingly from stripping nav/ads/scripts, not from markdown
syntax itself."* Keeping them apart in the data model is how the CLI, the JSON
output and the Phase 8 GUI all stay honest about it without each having to
remember to be.

## Repository packing: three engines, one set of promises

`src/tokenmill/backends/repo/`.

gitingest is a Python import, Repomix is a Node program and code2prompt is a
Rust binary. What makes them one product rather than three CLIs behind a shared
prefix is that everything a *user* controls is tokenmill's, not the tool's: the
same globs, the same `.gitignore` respect, the same budget, the same
per-directory breakdown, the same clone-and-clean-up for a remote URL. Each
adapter translates those into its own tool's flags and parses the result back
into per-file sections.

### The one place a backend may consult a tokenizer

The rule elsewhere is absolute: backends convert, the pipeline measures. A token
budget bends it, and the line is worth stating precisely.

**A backend may consult a tokenizer to obey a limit the user set. It may never
report a count.** The budget is an *input constraint*, like `max_bytes` — it
changes what the converter emits — and the pipeline still does every piece of
reporting measurement. The conformance suite's assertion that a result carries
no token counts applies to repository backends exactly as it does to the others,
and a test checks it.

The budget's unit follows the run's tokenizer, so `--token-budget 5000
--tokenizer bytes` caps at 5,000 UTF-8 bytes and `--tokenizer o200k_base` caps at
5,000 model tokens. That is what makes the flag honest on a machine that cannot
download a vocabulary. When no tokenizer loads at all, the budget is **not
silently ignored**: the conversion warns that it could not be applied and emits
everything, because a cap that quietly did nothing is worse than no cap — the
user believes the output is bounded.

### The truncation strategy, and why the note degrades before the content

Three rules. The preamble — the summary and the directory tree — is always kept,
because it is the only thing telling a reader which files are missing. Files are
kept in the order the tool emitted them, since each tool orders deliberately and
re-sorting would substitute tokenmill's judgement for the one the user chose an
engine for. And **a file is never partially included**: half a module is worse
than none, because a model cannot tell the rest was cut and will reason happily
about a class whose methods have vanished.

The fourth rule is the one that took three attempts. The truncation note is part
of the output, so it counts against the budget — but **a file that fits is never
evicted to make room for a longer explanation of the files that did not.** The
full table appears when it fits and a one-line note when it does not; the
complete list is always in the result's metadata, so shortening the prose loses
nothing.

Both wrong versions are recorded in the code, because they are instructive. The
first appended the note after computing the budget and emitted 1,482 bytes
against a 1,200-byte cap — a cap exceeded by the explanation of the cap. The
second dropped files to make room, and since each drop adds a row to the note it
emptied the pack chasing a note that grew faster than the content shrank.

### Parsing a third-party tool's output, and admitting when it fails

Budgeting and the breakdown both need per-file structure, and none of the three
tools offers one. So each adapter carries a regular expression for its own tool's
file header, anchored to the start of a line so that a matching string *inside* a
file cannot fake one.

That is brittle by nature, and the design point is what happens when it breaks:
**an unrecognised format produces no sections, and the adapter says so.**

```
warning:  code2prompt's Markdown format was not recognised, so the token budget
and the per-directory breakdown could not be applied. The pack itself is
complete and unmodified; this is a tokenmill parsing problem
```

The alternative — reporting a file count of zero — would read as an empty
repository and would let a budget silently do nothing. This is not hypothetical:
code2prompt's format was guessed from repomix's and was wrong, and that warning
is what surfaced it in minutes.

### Running out of process, before Phase 7 owns it

`IsolationMode.SUBPROCESS` and `BackendFailed.stderr` have existed since Phase 1;
the hardened `SubprocessConverter` is Phase 7. `tokenmill.backends._subprocess`
is the minimum Phase 4 needs, sited one level above the tiers so Phase 7 can
absorb it: PATH lookup, list arguments with `shell=False`, a timeout, captured
output, and every failure mapped into the taxonomy.

What it does **not** do is as important, and is listed in its docstring and in
`PROGRESS.md`: no sandboxing, no binary allow-list, no version probing, no
streaming. The allow-list is the one that matters for Phase 7's real job —
enforcing that a copyleft tool *actually* stays out of this process needs a
checked list of what may be invoked, not an adapter's declaration that it
behaves.

Note that these two backends run out of process because they are TypeScript and
Rust, **not** because of their licences: both are MIT and could legally be
imported if they were Python. That makes them useful practice for Phase 7, since
getting the boundary wrong on them carries no licence risk.

## The pipeline

`src/tokenmill/core/pipeline.py`.

```
Source ──▶ [Converter] ──▶ raw text ──▶ [PostProcessor chain] ──▶ final text
   │                          │                   │                    │
   └──────────────────────────┴───────────────────┴────────────────────┘
                                      │
                                 TokenMeter
                    source · convert · each post-processor · final
```

Every stage is measured as the text leaves it. `tokens_before` and
`tokens_after` are the first and last stages that were actually counted, so a
partially-measured run still reports a comparable pair rather than a number
measured against nothing.

### Measurement failure is not conversion failure

This one was found by running the code, not by designing it. `NetworkRequired`
is a `ConversionError` — correctly, per the plan's taxonomy — so the first
version aborted the entire conversion when tiktoken could not reach its CDN.

That is the wrong behaviour. On an air-gapped machine *every* tokenizer in the
core install is unloadable, and the user would get an error where a converted
document should have been. Now `TokenMeter` catches the failure, every count
comes back `None`, one warning explains why, character counts stay exact, and the
Markdown is returned.

The alternative — estimating — is the one thing this project will not do.
`ground_truth.json` set the precedent in Phase 0 by recording `token_count:
null` rather than a characters-over-four guess, and the same rule holds
everywhere: **a number we did not measure is not reported as a number.**

### Post-processor ordering

Each post-processor declares an `order`; the chain runs in ascending order so
the outcome does not depend on discovery order. Reserved ranges:

| Range | Purpose | Phase 1 occupants |
|---|---|---|
| 0–99 | Structural repair, before anything reads the text | `strip_frontmatter` (50) |
| 100–199 | Whitespace and normalisation | `normalize_whitespace` (100), `aggressive_whitespace` (150) |
| 200–399 | Content reduction: links, images, boilerplate | `links` (200), `dedupe_blocks` (250) |
| 400–699 | Reformatting: tables, headings, serialisation | `normalize_headings` (400) |
| 700–899 | Chunking | `chunk` (700) |
| 900–999 | Compression | `compress` (900) |

An explicit `--post a,b,c` runs **in the order the user gave**, overriding
declared order, because somebody naming a chain by hand means that sequence.

### Two flags: one is the mechanism, one is the description

A post-processor declares `in_default_chain`, and `default_chain()` is built
from exactly that. It separately declares `destructive` — whether it can lose
information the user might have wanted — which is shown to the user and is
never branched on.

The default pipeline still *cannot* damage a document — by construction, not by
convention. `default_chain()` reads both flags: a processor runs by default only
if it declares `in_default_chain` **and** is not destructive. The second half is
redundant against a correctly declared processor and is kept precisely so that
splitting the flag did not weaken anything, including for a third-party plugin
written against the old contract that sets `destructive = True` and knows
nothing about the new field.

A processor declaring both is a contradiction rather than a preference, so
`tests/unit/test_post_phase5.py` asserts the implication over the whole registry
from both ends and it fails loudly instead of being quietly resolved.

`normalize_whitespace` earns its non-destructive claim literally: it leaves
fenced code blocks entirely alone, and it preserves Markdown hard line breaks
(two trailing spaces before another line of text) rather than stripping them.
Stripping those would quietly change how a document renders, and a
"non-destructive" step that quietly changes rendering is not one.

Phase 5 made this load-bearing in a way it was not before. Phase 1 shipped one
destructive post-processor; there are now eight processors in total, and the
default chain is still exactly `normalize_whitespace`. The risk is not that one
of the eight is wrong — it is that the ninth forgets, so the invariant is
asserted **over the whole registry** rather than per processor.

**Why the split happened, and what `chunk` proved.** `chunk` deletes nothing; it
inserts chunk markers. Under the single flag it had to declare itself
destructive anyway, because that was the only mechanism keeping a processor out
of the default chain — so the flag carried two meanings at once, "can lose
information" and "changes the document's shape", and for `chunk` the first was
simply false. Phase 7 split them on the owner's sign-off: `chunk` now declares
`destructive = False` and `in_default_chain = False`, both true, which the old
contract could not express.

This is a breaking change to the Phase 1 post-processor contract, made with the
owner's sign-off. A third-party post-processor written against the old contract
keeps working unchanged: it sets `destructive = True`, and `default_chain()`
reads that too, so it stays out exactly as it did before.
`docs/ADDING_A_BACKEND.md` carries the migration note.

---

## The token layer

`src/tokenmill/tokens/`. Providers are registered, not individual tokenizers —
one `tiktoken` provider serves `o200k_base`, `cl100k_base`, `p50k_base` and
`r50k_base`, so there is no entry point per encoding. Ids resolve either bare
(`o200k_base`) or prefixed (`tiktoken:o200k_base`, `hf:bert-base-uncased`).

Resolution never loads a vocabulary. Constructing a tokenizer is free; the
download happens at the first `count()`. So an unavailable tokenizer still
resolves and then fails at the point of use with a precise, actionable error,
rather than failing early with a vague one.

### The `bytes` tokenizer, and why it exists

Both real tokenizer families fetch their vocabulary over the network:
tiktoken from `openaipublic.blob.core.windows.net`, HuggingFace from
`huggingface.co`. Where neither host is reachable, a user has a converter and no
measurement at all — which is most of the point of the tool.

`bytes` counts UTF-8 bytes. That is a fact about the text: exact, deterministic,
needing nothing but the standard library. It is **not** a model tokenizer, and
the code says so rather than implying it:

- `TokenizerInfo.is_model_tokenizer` is `False`;
- its unit is spelled out as `UTF-8 bytes`, and the CLI prints that as the column
  heading;
- `tokenmill tokens --tokenizer bytes` prints an explicit note that the number
  must not be quoted as a token count;
- it is never the default. `o200k_base` is.

Use it to see whether a conversion or a post-processor made the text smaller.
Do not use it to predict what a model will charge.

---

## Fidelity: the other half of every measurement

`src/tokenmill/fidelity/`. Brought forward from Phase 10 ahead of Phase 5,
because Phase 5 adds post-processors that each strip something and Phase 6 adds
a compressor that strips a great deal. Every one of them can be measured as a
win in tokens, and the cost is invisible unless something goes looking.

The package is deliberately *outside* the pipeline. It takes text and ground
truth and returns a score; it never runs a conversion, never consults a
tokenizer, and nothing in `core/` imports it. That keeps the rule in "Backends
do not measure" intact in both directions — the pipeline measures cost, the
fidelity package measures loss, and neither can quietly become the other.

### Why never one number

A `FidelityScore` is six named components plus an unweighted mean that carries
the names of the components it was built from. Three decisions, each of which
had an obvious alternative:

**Decomposable, because a score you cannot decompose is a score you cannot act
on.** "0.62" tells nobody whether to change backend, change post-processors or
accept the loss. "Headings 1.00, tables 0.00" tells them exactly.

**Unweighted, because a weighting would encode an opinion this project does not
have.** Whether a lost table matters more than a lost heading depends on the
document and the task. The user with the document owns that judgement.

**The overall names its components, because an overall built from two of them is
not comparable with one built from five** — and a reader who cannot see which is
which will compare them anyway.

### `None` is not zero, and this is where it matters most

A component whose ground truth does not exist for a fixture scores `None`.
`long_context.md` has no table: scoring its table integrity 0.0 claims a table
was destroyed, and 1.0 claims one survived. Both are false statements about a
document with no table in it.

This is the same rule `ground_truth.json` set in Phase 0 by recording
`token_count: null` rather than a characters-over-four guess, and the same one
`TokenMeter` follows when no tokenizer loads. It matters more here because a
fidelity score is a *judgement*, and a judgement invented from absent evidence
is worse than a missing one.

### The empty document, which is why the package exists

`benchmarks/README.md` states the failure: *a converter that emits an empty
string scores a 100% reduction*. The arithmetic reproduces it one level up. An
empty string contains no boilerplate, so `boilerplate_rejection` scores it
**1.0** — the instrument built to catch a destroyed document credits it with
perfect extraction.

So a document with no non-whitespace content scores 0.0 on every component that
has ground truth, and says so in the detail. It is an explicit special case
rather than an emergent property, because it needed to be: no arrangement of
fractions produces it on its own.

The general form of the same trap is handled by reporting, not by arithmetic.
**Recall and rejection are a pair**, always reported together. `markdownify_html`
keeps the whole page and scores high recall with zero rejection; a converter
that emitted only the cookie banner would score the reverse. Neither number
alone says extraction worked.

### Reading structure back out of Markdown

`fidelity/markdown.py` is a small strict reader, not a CommonMark parser: ATX
and setext headings, GFM pipe tables, list markers, fenced code blocks and both
link forms. A full parser would be a dependency in the core install, and rule 1
is not worth spending on a measurement module.

Two rules in it are load-bearing:

**Fenced code blocks are opaque.** A `#` inside a fence is a comment in
somebody's shell script and a `|` is a pipe operator. Counting either would make
a backend that emits more code score as though it emitted more structure.

**A pipe table needs its delimiter row.** A converter that flattens a table into
prose sometimes leaves the pipes behind, and counting those as a surviving table
would score the documented failure as a success.

## Serialisation formats

`src/tokenmill/formats/`. Markdown, CSV, JSON, TOON and key-value encoders for
one thing: a table. `RESEARCH.md` Category 7 says the same data costs very
different amounts depending on how it is serialised, and that the differences
are large, narrow, and easy to overstate — so a user should be able to measure
it **on their own data**, which is what `compare --formats` is for.

### Cells are strings, and every encoder is exactly lossless

A Markdown table lifted out of a PDF contains text: `9.99` in a price column is
four characters a converter read off a page, not a float. An encoder that
"helpfully" emitted it as a JSON number would not round-trip — `05` comes back
as `5` and `1e-6` as `1e-06`.

So a cell is written as a native number, boolean or null **exactly when doing so
renders back to the identical string**, and as a quoted string otherwise. The
test is not "does it look numeric" but "does rendering the parsed value
reproduce the original characters", which is strictly stronger.

That rule is also what keeps the comparison honest. Without it, JSON and TOON
would quote every number that CSV writes bare, and CSV would win the comparison
by two characters per numeric cell that no real application ever spends.

### Where a format cannot represent something, it says so

JSON, TOON and key-value key each row by column name, so a table with unnamed or
repeated columns cannot be encoded without silently dropping a column. They
raise. MarkItDown really does emit `report.docx`'s table with three unnamed
columns, so this is the first table many users will try.

Markdown's two losses — a line break in a cell, and leading or trailing
whitespace — are GFM's limits, not this encoder's, and are documented rather
than fixed with a non-standard escape that no other tool could read.

## `compare`, and why it is not sorted by size

`src/tokenmill/core/compare.py`. A document and a repository have no
before-count, so `convert` correctly reports one number and a size. The
comparison that means something for those inputs is between backends on the same
input.

**Rows stay in the registry's preference order.** Sorting by tokens is a
leaderboard, and a leaderboard on this data rewards whichever converter
destroyed the most — the one that emits an empty string wins by a distance. The
cheapest and the most faithful rows are named underneath instead, and when they
differ the report says so outright.

**A fidelity score sits beside every token count.** Where no ground truth
exists, the report says the comparison cannot say what any of these savings cost
rather than leaving a blank that reads like a pass. Ground truth is detected
only for a target that actually lives inside the corpus directory: matching on
filename alone would score somebody's own `tables.pdf` against ours and produce
a plausible number that means nothing.

**Fallback is forced off.** A row headed `pypdf` that pdfplumber actually
produced would make the whole table a lie. A backend that fails gets a row
saying so, because a backend that cannot read the file is a result.

## Error taxonomy

`src/tokenmill/core/errors.py`.

```
TokenmillError
├── ConfigError
├── TokenizerError
│   ├── TokenizerNotFound
│   └── TokenizerUnavailable
└── ConversionError
    ├── UnsupportedFormat      no available backend claims this source
    ├── BackendUnavailable     the backend exists but cannot run
    ├── BackendFailed          it ran and failed (carries stderr, for Phase 7)
    ├── Timeout                exceeded its time budget
    ├── CorruptSource          damaged, truncated, or over the size limit
    └── NetworkRequired        needs network access it does not have
```

`ConversionError` and its six subclasses are exactly the taxonomy the plan
names. `TokenmillError`, `ConfigError` and `TokenizerError` sit alongside so a
caller can catch everything this library raises with one `except` without also
swallowing unrelated exceptions.

Every error carries an optional `hint`: the install command, the config flag,
the thing to do next. The CLI prints it on its own line. The point of a closed
taxonomy is that each class maps to exactly one actionable message, and no raw
traceback ever reaches a user.

Note that `NetworkRequired` is raised by the tokenizer adapters as well as by
backends. It is genuinely the right error — the operation needs the network —
and `TokenMeter` catches it explicitly for the reason given above.

---

## The external boundary, and what it is not

`src/tokenmill/backends/external/`. Phase 1 designed the model, Phase 7
implemented it, Phase 9 builds the GPU tier on it.

**Two different reasons put a backend out of process**, and conflating them is
the mistake this package's docstring exists to prevent:

- **Licence.** AGPL and GPL tools are never imported (`CONTRIBUTING.md` rule 2).
  `pymupdf4llm` and `pandoc`.
- **Language.** A C++ application or a Node program cannot be imported at any
  price. `libreoffice`, `repomix`, `code2prompt` — all permissive, and their
  running out of process carries no licence meaning at all.

The second group is useful practice: getting the boundary wrong on an MIT tool
costs a bug, not a licence problem.

### Why the package is called `external` (defect N9)

It was `backends/isolated/` until Phase 9. "Isolation" is the word an operating
system uses for *containment*, and this layer contains nothing: no resource
limits, no filesystem confinement, no network namespace. A tool launched through
it runs with exactly the access the user has. The name invited a security
reading it does not deserve, and the evidence that it did is that three
documents had each grown a paragraph explaining what the layer is *not*.

`external` says the true thing — the converter runs outside this process — and
claims nothing about safety, so the apologetic paragraph is no longer load
bearing. It was renamed before the Phase 9 adapters landed on top of it, because
renaming afterwards costs seven more subclasses.

**`IsolationMode` and `BackendInfo.isolation` did not change.** Their values —
`in-process`, `subprocess`, `service` — already name a *mechanism* rather than a
protection, they are printed by `tokenmill backends` and carried in `--json`
output that somebody may already parse, and renaming a field of the Phase 1
contract is a breaking change with no user-visible gain. The package and the
prose were what oversold; those are what changed.

### What enforces it

- `IsolationMode` is `IN_PROCESS`, `SUBPROCESS` or `SERVICE`.
- `BackendInfo.__post_init__` refuses the illegal combination (non-permissive +
  in-process) at construction, and the registry refuses it again at
  registration. A violating adapter cannot be built.
- `core/licensing.py` reads every installed distribution's own metadata and
  classifies it, and `tests/unit/test_license_isolation.py` makes four
  independent checks — declaration, environment, **static imports** and runtime
  `sys.modules`. The static one is the load-bearing one, because it works on a
  machine where the copyleft package was never installed, which is every machine
  CI runs on. `docs/LICENSES.md` has the reasoning.

### `SubprocessConverter`

Binary discovery beyond `PATH` (the macOS LibreOffice bundle is never on it), a
version probe recorded as provenance, an **allow-list** of every program
tokenmill may launch, list arguments with `shell=False` always, timeout and
kill, and a workspace removed on every exit path including timeout and failure.

The allow-list is what makes the boundary *enforced* rather than declared:
without one, "this AGPL tool runs out of process" is a claim an adapter makes about
itself. With one, the set of programs tokenmill will start is a single
reviewable table, and an adapter naming anything else fails before the process
starts.

### `ServiceConverter`

The HTTP mode, and the pattern Phase 9's GPU backends subclass. Nothing is
auto-discovered and nothing is auto-started: a service backend is unavailable
until the user says where it is, because a converter that probes localhost on a
range of ports is doing something nobody asked for. A probe is a real request,
so "available" means it answered. Talking to it needs `--allow-network` even on
loopback. stdlib `urllib` only, so a service adapter is not what drags an HTTP
client into the core install.

No service backend is registered, and a test asserts that stays true: a row for
a container nobody is running is a permanently-unavailable backend in every
user's listing.

### What the external boundary is not

**It is not a security boundary.** No sandboxing, no resource limits, no
filesystem confinement, no network namespace. A tool run through it has the same
access the user does. It is a licence and language boundary, and no document in
this repository should be read as claiming more. Output is also buffered whole
rather than streamed. Both are recorded in `PROGRESS.md` under deferred work.

---

## Compression, and the state it does not add

`src/tokenmill/post/compress.py`. Last in the chain at order 900, because
compressing and then stripping would spend model time on text about to be
deleted.

Two decisions here are about *not* doing the obvious thing.

**The offline switch is not an environment variable.** The natural way to make
`transformers` work from cache only is `HF_HUB_OFFLINE=1`. That would have been
a **sixth** piece of process-global state manipulated during a conversion, on
top of the five this document already records — and the trajectory of that
count is defect D2. llmlingua passes `model_config` straight through to
`from_pretrained`, so `local_files_only` rides in the call instead. A test
asserts the environment is unchanged.

**`trust_remote_code` is off.** llmlingua defaults it to true. On a downloaded
model that means executing code from a model repository, which is not something
a document converter should do by default for a token classifier that does not
need it.

**A post-processor has no channel for warnings or metadata.** `process(text,
options) -> str` is the whole contract — unlike a backend, which gets a
`ConversionContext`. So the compressor logs rather than warning, and reports its
ratio through the per-stage measurement the pipeline already does rather than
attaching it to the result. That is a real gap and `PROGRESS.md` records it:
Phase 8's GUI will want a post-processor to be able to say something.

## The graphical interface

`src/tokenmill/gui/`. Three modules, and the split is the phase's stated risk
mitigation rather than tidiness: `api.py` is every action the interface can
perform, `batch.py` is the queue, `app.py` is layout and event handlers and
nothing else.

### Why NiceGUI

The plan's stack decision, and the reasoning it asked to have recorded:

- **Event-driven, not Streamlit's full-script-rerun model.** A batch queue that
  updates twenty rows as they finish, and a token counter that moves while a
  conversion runs, both fight a framework that re-executes the whole script on
  every interaction.
- **FastAPI in-process.** The same application can expose an HTTP API and
  orchestrate the subprocess and service backends Phase 7 added, without a
  second server. `api.py` is already shaped as that API.
- **`native` mode is a desktop window without leaving Python.** A PySide6 shell
  remains a Phase 11 option for offline distribution.

MIT, verified from installed metadata (3.16.0). Its tree brings `docutils`,
which is the single entry on the copyleft allow-list; `docs/LICENSES.md`
explains why and a test re-checks the premise.

### The GUI may only call the public library API

The plan names this phase's risk as *GUI logic creeping into the UI layer*. A
rule in a docstring is a habit, so `tests/unit/test_gui_boundary.py` asserts it
over the **import graph**: `app.py` may reach `gui.api`, `gui.batch`,
`core.models` (constructing a `Source` is how input enters the system) and
`core.registry` (one `supports()` question). Not `core.pipeline`, not
`backends`, not `post`, not `fidelity`.

The consequence worth stating: `api.py` imports no UI toolkit, so its 35 tests
run on a core-only install and on every CI cell, rather than only where a
browser happens to be.

### The batch queue runs one conversion at a time, and that is defect D2

`Pipeline.run` touches process-global state that is not thread-safe — four uses
of `warnings.catch_warnings`, plus `os.environ`, the root logger's handlers and
level, and loguru's activation registry. `catch_warnings` saves and restores a
*module-global* filter list, so two threads inside it interleave their save and
restore and the loser leaves the process with the other's filters. Under
`filterwarnings = ["error"]` that turns a forwarded warning into a raised
exception somewhere else entirely.

So there is one worker thread and conversions are serialised. The interface
stays responsive because the work is off the event loop; correctness holds
because only one conversion touches the global state at a time.

A process pool would be safe *and* parallel, and is deliberately not used yet:
`ConversionResult` would cross a pickle boundary carrying the whole converted
text, and child-process lifecycle would be a sixth kind of global concern in a
project already tracking that count as a defect. **Fixing D2 is what unlocks
parallelism**, and until then batch throughput is bounded by a defect rather
than by the work.

### `None` is not zero, in the one place users see it most

A binary document has no comparable before-count, so the token panel renders
`n/a` and the batch aggregate counts it separately. Getting this wrong produced
a real bug: summing `tokens_after` over every item while summing `tokens_before`
over only the ones that had one reported a 20-file batch at **−16.7%**, a batch
that appeared to have grown. `BatchTotals` now carries `comparable` and
`tokens_produced` so the two questions — "what did this cost" and "what did it
save" — have separate answers.

---

## Security posture

Every input document is treated as hostile — several backends will hand
documents to C libraries or external binaries.

- **Default-deny on the network.** `ConvertOptions.allow_network` is `False`.
  Converting a local file makes no network call, and
  `tests/integration/test_reference_backends.py` enforces that by making
  `socket.connect` raise for the duration of a conversion.
- **Size cap.** `max_bytes` defaults to 256 MiB and is checked before a backend
  sees the source.
- **Path normalisation.** `Source.from_path` resolves, so backends never see a
  relative path and `..` cannot escape somewhere unexpected.
- **Lenient decoding, loud reporting.** Undecodable bytes become U+FFFD rather
  than an exception, and the backend attaches a warning saying so — a converter
  should report a mangled character, not abort, but it must not measure mojibake
  silently.

### `gui --server` and its shared token

`src/tokenmill/gui/auth.py`. Defect N15: Phase 8 shipped `--server` binding
`0.0.0.0` with no authentication, printing a warning and calling that a
mitigation. It is not one.

Every request now carries a token — `Authorization: Bearer`, an
`X-Tokenmill-Token` header, a `tokenmill_server_token` cookie, or `?token=` on
the first page load, which is how the token reaches a browser at all and which
sets the cookie for everything after. Comparison is `hmac.compare_digest`.
Without a token: `401` for HTTP, and a `1008` close for a WebSocket, because
answering a WebSocket scope with an HTTP response is a protocol error.

**The guard is raw ASGI, not a Starlette middleware, and that is the load-
bearing decision.** The interface runs over a WebSocket; a guard that saw only
`http` would leave the channel every conversion actually travels on wide open.
A raw middleware sees both scopes. Verified against a running server: `403` on
the WebSocket handshake without the cookie, `101` with it.

**When no token is configured, one is generated and printed** with the URL to
paste. There is no way to run `--server` without one. `--token` beats
`$TOKENMILL_SERVER_TOKEN` beats the config file's `server_token`, matching the
layering in `core/config.py`, and a token under eight characters is *refused*
rather than accepted — an empty shell variable would otherwise disable the check
in silence.

**What it is not**, stated in the module, the CLI's start-up message and the
README rather than left to be inferred: not TLS, not user accounts, not an audit
trail, not a rate limit. It stops a machine on the same network reading your
documents. The cookie is deliberately **not** `Secure`, because there is no TLS
to attach it to and a `Secure` cookie over plain HTTP is discarded — the
appearance of safety costing the actual feature. `SameSite=Lax` is the CSRF
answer.

### Staged uploads are bounded

Defect N14. Phase 8 wrote every uploaded file to `~/.cache/tokenmill/uploads`
and removed none of them, so a long-running `--server` accumulated everything
anybody had ever dropped on it.

`api.prune_uploads()` applies **both** bounds: anything older than 24 hours
goes, then the oldest go until at most 200 files remain. Either alone leaves a
hole — an age bound lets a burst fill a disk inside the window, a count bound
keeps yesterday's documents on an idle server forever, and the second of those
is the privacy half of the same defect. It runs after each upload and again when
a page is built, so a server that is loaded and then left alone still sheds.

Staging lives in `gui/api.py` rather than in `app.py` because it is testable
logic, which is the rule the whole GUI layer is built on. That is how a test
found the hole in the name sanitiser: `Path("..").name` is `".."`, not the empty
string, so taking the base name alone resolved to the *parent* directory.

---

## Third-party libraries that misbehave, and where that is handled

Wrapping five libraries turned up three failures that had nothing to do with any
document, and all three would have reached users as broken conversions. They are
handled in `backends/documents/_common.py` rather than in each adapter, because
they are the same problem wearing different hats.

**A library that warns at import time must not fail a conversion.** MarkItDown
imports magika, which imports onnxruntime, which warns `Unsupported Windows
version` the moment it loads. Under `-W error` — which this project's own test
suite sets, and which applications embedding tokenmill may too — that warning
became an exception inside the lazy import, and `BaseConverter` reported a
perfectly healthy converter as `BackendFailed`. Suppressing it would be the
wrong fix: "your platform is unsupported" is exactly the kind of thing a user
should hear. So `warnings_as_conversion_warnings` captures warnings raised
during a third-party import and hands them to the user as conversion warnings —
non-fatal, still visible, attributed to what raised them.

The exception is a library's *internal* deprecation churn, which a user cannot
act on: Docling's PDF pipeline reads its own deprecated field, and that one
message is filtered around the convert call rather than forwarded.

**Five exception hierarchies, one taxonomy.** `classify_failure` maps whatever a
library raises onto `CorruptSource`, `NetworkRequired` or `BackendFailed`, so a
truncated PDF reads the same way from all four PDF backends even though they
raise four unrelated types. It walks the `__cause__` chain, because these
libraries routinely wrap the informative exception inside a bland one. Anything
it does not recognise stays `BackendFailed` — guessing harder would mean telling
a user their file is damaged when the fault is in the converter.

**An empty conversion is not a success.** `warn_on_empty_output` exists because
exiting 0 with an empty file looks identical to working. `scanned.pdf` has no
text layer by design and every backend in this tier returns nothing for it.

Note that `warnings.catch_warnings` manipulates global state and is not
thread-safe. Nothing runs conversions concurrently today; the Phase 8 batch
runner will have to account for it, and `PROGRESS.md` records that.

## What Phases 2, 3 and 4 deliberately do not include

Left out rather than stubbed, per `CONTRIBUTING.md` rule 6:

- **OCR.** Every backend here returns an empty document for a scanned PDF, and
  every one of them warns about it. Reading text off page images is Phase 9.
- **A layout model for multi-column PDFs.** pdfplumber interleaves columns and
  the adapter warns when it detects a gutter, but detecting is as far as it
  goes; reordering a page is a layout engine, not an adapter.

- ~~**URL fetching.**~~ **Done in Phase 3**, in the pipeline — see above.
- ~~**Repository ingestion.**~~ **Done in Phase 4** — see above.
- **A hardened `SubprocessConverter`.** `tokenmill.backends._subprocess` is the
  minimum Phase 4 needed. Binary discovery beyond `PATH`, version probing, an
  allow-list and the sandboxing policy are Phase 7.
- **Conditional or authenticated fetching.** No cookies, no headers beyond the
  user agent, no ETag or caching. A page behind a login is not fetchable, and
  saying so beats a half-implemented credential story.
- ~~**Formats beyond Markdown and text.**~~ **Done in Phase 5** — see
  "Serialisation formats" above. Note that `OutputFormat` still has two members:
  the encoders re-serialise a *table*, which is what `RESEARCH.md`'s evidence is
  about, rather than becoming whole-document output formats.
- **Cost estimation.** The plan puts it in the token layer with user-supplied
  rates only. No rates, no estimate, so it is not here.
- ~~**Reference-style link handling.**~~ **Done in Phase 5**: `--links
  reference` moves targets into a definition list. Autolinks and bare URLs in
  prose are still left alone, deliberately — deciding where a bare URL ends
  differs between Markdown flavours and guessing wrong corrupts the sentence.
