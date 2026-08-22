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
| 0–99 | Structural repair, before anything reads the text | *(none yet)* |
| 100–199 | Whitespace and normalisation | `normalize_whitespace` (100) |
| 200–399 | Content reduction: links, images, boilerplate | `links` (200) |
| 400–699 | Reformatting: tables, headings, serialisation | *(Phase 5)* |
| 700–899 | Chunking | *(Phase 5)* |
| 900–999 | Compression | *(Phase 6)* |

An explicit `--post a,b,c` runs **in the order the user gave**, overriding
declared order, because somebody naming a chain by hand means that sequence.

### Destructive is a structural property

A post-processor that can lose information the user might have wanted sets
`destructive = True`, and `default_chain()` is built by excluding them. The
default pipeline therefore *cannot* damage a document — not by convention, by
construction.

`normalize_whitespace` earns its non-destructive claim literally: it leaves
fenced code blocks entirely alone, and it preserves Markdown hard line breaks
(two trailing spaces before another line of text) rather than stripping them.
Stripping those would quietly change how a document renders, and a
"non-destructive" step that quietly changes rendering is not one.

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

## Isolation (design now, implementation in Phase 7)

Nothing in Phase 1 runs out of process, but the model is already in place so
that Phase 7 adds an implementation rather than a concept:

- `IsolationMode` is `IN_PROCESS`, `SUBPROCESS` or `SERVICE`.
- `BackendInfo` refuses the illegal combination (non-permissive + in-process) at
  construction time, and the registry refuses it again at registration.
- The conformance suite asserts, for every installed backend, that a
  non-permissive licence implies out-of-process isolation. A copyleft adapter
  added in any later phase is caught by a test that already exists.
- `BackendFailed` already carries a `stderr` field, which is what a subprocess
  backend needs to report a failure usefully.

Phase 7 adds `SubprocessConverter`: binary discovery, version probe, argument
construction as a list (never `shell=True`), timeout and kill, temp-file
lifecycle, and stderr capture.

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

## What Phases 2 and 3 deliberately do not include

Left out rather than stubbed, per `CONTRIBUTING.md` rule 6:

- **OCR.** Every backend here returns an empty document for a scanned PDF, and
  every one of them warns about it. Reading text off page images is Phase 9.
- **A layout model for multi-column PDFs.** pdfplumber interleaves columns and
  the adapter warns when it detects a gutter, but detecting is as far as it
  goes; reordering a page is a layout engine, not an adapter.

- ~~**URL fetching.**~~ **Done in Phase 3**, in the pipeline — see above.
- **Repository ingestion.** `SourceKind.REPO` exists; no backend claims it.
  Phase 4.
- **A shared `SubprocessConverter`.** `IsolationMode.SUBPROCESS`,
  `LicenseTier.COPYLEFT` and `BackendFailed.stderr` all exist and are enforced,
  but binary discovery, version probing and the sandboxing policy are Phase 7.
- **Conditional or authenticated fetching.** No cookies, no headers beyond the
  user agent, no ETag or caching. A page behind a login is not fetchable, and
  saying so beats a half-implemented credential story.
- **Formats beyond Markdown and text.** `OutputFormat` has two members. CSV,
  TOON and JSON encoders are Phase 5.
- **Cost estimation.** The plan puts it in the token layer with user-supplied
  rates only. No rates, no estimate, so it is not here.
- **Reference-style link handling.** `links` handles inline links and images and
  leaves reference links intact rather than mangling them. Phase 5.
