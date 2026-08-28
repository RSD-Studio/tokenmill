# FAQ

Questions a reader actually has, answered without marketing. Where the honest
answer is "we don't know" or "that doesn't work", it says so.

---

## What is this, in one sentence?

A single interface over other people's converters — MarkItDown, Docling,
trafilatura, gitingest, pandoc and a dozen more — that reports what every
conversion cost in tokens and what it lost, so you can pick one on evidence.

## Does it convert anything itself?

**No.** tokenmill contains no parser. Every backend is somebody else's library
or program, wrapped behind one contract. The value is the wrapping, the
measurement and the licence hygiene, not the conversion.

## Why would I want a token count? I can just look at the file size.

You can, and for a while we thought that was close enough. It is not. On this
project's own tabular data, CSV saves **60.2% of JSON's bytes and 36.0% of its
tokens** — a 24-point gap — and the two units do not even rank five
serialisation formats in the same order. `keyvalue` is 16% *smaller* than JSON
in bytes and 1.8% *more expensive* in tokens, because its repeated field labels
are cheap in characters and expensive in BPE.

## So all your numbers are in tokens?

**No, and this is the biggest caveat in the project.** The committed benchmark
matrix is in **UTF-8 bytes**. The environment tokenmill was built in denies
every tokenizer vocabulary host at an egress proxy, so no model-token count
could be produced locally at all. `.github/workflows/benchmark.yml` produces the
token figures on a GitHub runner and merges them in on the tokenizer key — it is
written, its failure path is tested, and it **has never been dispatched**.

Four token figures exist in this repository and all four were read out of a CI
log. They are labelled `o200k_base` wherever they appear.

## What is "fidelity" and why is it next to every number?

Because a converter that emits an empty string scores a 100% reduction, and
**four cells in our own benchmark do exactly that**. `scanned.pdf` has no text
layer; `pdfplumber`, `kreuzberg`, `markitdown` and `pypdf` all return
successfully with nothing, at a perfect saving and 0.000 fidelity. The largest
single reduction in the whole corpus — −90.7% on `jsrendered.html` — is also a
cell that extracted nothing.

Fidelity scores six components against hand-labelled ground truth: heading
recall, content recall, table integrity, structure retention, boilerplate
rejection and reading order. `n/a` is never zero — a component with no ground
truth for that fixture did not apply, which is a different statement from
scoring badly, and the report always prints how many components were scored.

## Does fidelity mean a model will answer better?

**No.** It measures structural survival against an answer key. Whether a model
*answers questions better* from one output than another is a question this
project has no apparatus to ask, and nothing here should be read as though it
did.

## Which backend should I use?

It depends on the document, which is the entire reason `tokenmill compare`
exists. But two patterns held across our corpus:

- **For documents, paying more buys fidelity.** `pymupdf4llm` beat every other
  PDF backend on every scorable PDF, at 103–234× the wall time and ~300 MiB.
- **For web pages, it does not.** `trafilatura` and `readability` were both the
  cheapest *and* the most faithful. The aggressive extractor is free.

And a warning: **the cheapest output on a document is routinely the one that
dropped the table.** On `tables.pdf`, `pypdf` gives 481 bytes at fidelity 0.333
and `pymupdf4llm` gives 553 at 0.848. The extra 15% *is* the table.

## Why is `libreoffice` in the default preference order if it scores worst?

Because it converts formats nothing else in the core install will —
`.doc`, `.odt`, `.rtf`, legacy `.xls` and `.ppt`. Its value is coverage, not
quality, and since Phase 10 `docs/BACKENDS.md` says so with the table that
proves it. If a better backend claims your format, tokenmill will pick that one.

## Can I use it without installing anything heavy?

Yes. The core install is **141.2 MB across 40 packages**, pure Python or
wheel-shipping, permissively licensed, CPU-only, with no system binary. CI
enforces a 250 MB ceiling on nine OS/Python cells *and* on the built wheel. If a
heavy dependency ever leaks into core, the build goes red.

`heavy = []` in `pyproject.toml` is empty and stays empty: the GPU tier is
adapters, never dependencies.

## Do the GPU backends work?

**Unknown. Not one of them has ever converted a document.** Six are implemented
— `marker`, `surya`, `mineru`, `olmocr`, `deepseek_ocr`, `dots_ocr` — on a
machine with no GPU that cannot reach the host the weights live on.

What *is* verified is the path you take if you have no GPU either: each reports
itself unavailable with the exact commands that would change that, and
`tokenmill doctor` distinguishes "no GPU" from "the driver is installed and no
device answered", which is what a container started without `--gpus` looks like.

## Can it OCR a scanned PDF?

**Not today.** Every OCR path in this project runs through the GPU tier, and
none of those has been demonstrated. There is no CPU OCR engine wrapped.
`scanned.pdf` is in the corpus precisely so that this gap is visible rather than
implied: four backends "succeed" on it and produce nothing.

## Does it use an LLM?

No. Nothing here calls a model. Prompt compression uses LLMLingua-2, which is a
local model, and it is **off by default and should stay off until you measure
it on your own data** — and its success path has never executed anywhere,
because the model lives on a denied host.

## Is my data sent anywhere?

No. Every backend runs locally. Two things reach the network and both are
explicit:

- A tokenizer vocabulary download, once, cached afterwards. Use
  `--tokenizer bytes` to avoid it entirely.
- Anything you point at a URL, or a service backend you configured yourself
  with an address. `--allow-network` is required for both, **even for
  `localhost`**, because talking to a service is a network call whichever
  interface it is on.

tokenmill never starts a container, never probes for one, and never discovers a
service. If you did not give it an address, it has none.

## Is `gui --server` safe to expose?

**It is safe for one specific thing and nothing else.** It binds every interface
and requires a shared token on every request — generated and printed with the
URL when you have not set one, so the secure path is the default path. That
stops another machine on your network converting your documents and reading the
results.

There is **no TLS, no user accounts and no audit trail.** Put HTTPS in front of
it, or tunnel over SSH, if the network is not one you would trust with the
documents themselves.

## You run pandoc and PyMuPDF4LLM. Aren't those GPL and AGPL?

Yes, and they are **never imported**. Both run as separate programs across a
process boundary — pandoc as a system binary, PyMuPDF4LLM in an interpreter of
its own — which is execution rather than linking, and which keeps tokenmill's
own Apache-2.0 licence intact. Four independent checks enforce it, including one
that has been watched catching a deliberately introduced violation.

`tokenmill backends --show-licenses` audits your environment.
[`docs/LICENSES.md`](LICENSES.md) has the reasoning and, since Phase 11, a
statement of exactly what each distributed artefact contains.

## Is the isolation layer a sandbox?

**No, and it is important not to read it as one.** A tool run out of process has
the same filesystem and network access you do. There are no resource limits, no
filesystem confinement and no network namespace. It is a **licence and language
boundary**, not a security boundary. That is why it is called `backends/external/`
rather than anything with "sandbox" in the name.

## Can I add my own backend?

Yes — through the same entry point group the built-in ones use. There is no
hard-coded list. [`docs/ADDING_A_BACKEND.md`](ADDING_A_BACKEND.md) is the guide,
and it is written against the real contract rather than a simplified one.

## How trustworthy are your benchmark numbers?

Every number traces to a committed raw result file, and one command regenerates
the lot. That is the strong part.

The weak parts, stated together:

- **UTF-8 bytes, not model tokens.** See above.
- **A 15-file synthetic corpus.** Generated by `scripts/make_fixtures.py` and
  reproducible byte-for-byte. That is what makes them checkable and exactly why
  they are not representative — the two properties are the same property. These
  are not "PDF backend" results; they are results on five specific PDFs.
- **One machine, N=5.** Wall time does not transfer; the *ratios* are the
  durable part.
- **Memory figures are lower bounds** — sampled every 5 ms, so a peak between
  samples is missed.

[`docs/BENCHMARKS.md`'s Limitations section](BENCHMARKS.md#limitations-read-before-quoting-any-of-this)
has all seven, and
[`docs/article/CLAIMS.md`](article/CLAIMS.md) labels every claim in the project
Measured, Cited or Unverified.

## Is it on PyPI?

Not yet. The artefacts are built, checked with `twine --strict`, installed and
exercised on nine OS/Python cells, and tagged. Publishing is a separate manual
step that has not been run.

## Why is it called tokenmill?

The first name was `tokenfold`, which is taken on PyPI by an unrelated,
actively published token-compression project — so `pip install tokenfold` could
never have been ours. Renamed before the first commit.
