# Licences

**Status:** complete as of Phase 7 (2026-08-26). Enforcement is now code —
`tokenmill/core/licensing.py` and `tests/unit/test_license_isolation.py` — and
this page is the reasoning behind it rather than the whole of it.

Everything here was read from an installed package's **own metadata** at the
moment it was written. Never from [`docs/research/RESEARCH.md`](research/RESEARCH.md),
never from a project's README. Phase 2 found `RESEARCH.md` wrong about a
dependency count, Phase 3 found it incomplete about a licence tree, Phase 5
found a package under a format's own GitHub organisation was a stub, and
Phase 7 found `RESEARCH.md`'s "PyMuPDF4LLM: AGPL-3.0" is only half the story
(see below). The package wins, every time.

## The tiering rules

**Four** tiers, and they are `LicenseTier` in the code rather than a convention:

| Tier | What it means | What tokenmill may do with it |
|---|---|---|
| **permissive** | MIT, Apache-2.0, BSD, ISC, PSF, MPL, LGPL | Import it into our process |
| **restricted** | BUSL, Elastic-2.0, SSPL, PolyForm, Commons Clause, any unrecognised `LicenseRef-` | **Never import.** Subprocess or service boundary only, and the obligations are the user's to read |
| **copyleft** | AGPL, GPL | **Never import.** Subprocess or service boundary only |
| **non-commercial** | CC-BY-NC, RAIL, purchase-only | Excluded by default; not wrapped |

`restricted` arrived in Phase 9 and [§ MinerU, and why there is a fourth
tier](#mineru-and-why-there-is-a-fourth-tier) explains what forced it.

**Six** rules govern how a licence string reaches a tier, and each exists
because something real would otherwise be classified wrongly:

**1. A disjunction resolves to its most permissive *available* branch.**
`A OR B` means the recipient chooses. `tld` ships
`MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later` and tokenmill takes MPL-1.1, so
it is permissive — by resolving the choice, not by being waived.

**2. A branch that must be bought is not a branch we hold.** This is the rule
Phase 7 was missing, and PyMuPDF4LLM is why. Its metadata states
`Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License`. Read as an
ordinary disjunction, the second branch looks unencumbered and the package
classifies **permissive** — the flagship copyleft tool of the whole isolation
phase, cleared for import. Nobody here has bought an Artifex licence, so the
only branch we hold is the AGPL one.

**3. A conjunction resolves to its least permissive part.** `A AND B` means both
apply. `tqdm` is `MPL-2.0 AND MIT`; both are permissive, so it is.

**4. LGPL is not copyleft for this purpose.** LGPL exists precisely to permit
use as a library without relicensing the caller, and `CONTRIBUTING.md` rule 2
names AGPL and GPL. Written down because "it contains the letters GPL" is the
reading that would otherwise be applied. Tightening this should be a decision
somebody makes, not a regex drifting, so a test asserts it.

**5. A source-available licence is not a permissive one.** BUSL-1.1,
Elastic-2.0, SSPL, PolyForm, anything carrying a Commons Clause, and anything
whose text says "additional terms" are **restricted**. Before Phase 9 every one
of them classified as permissive.

SSPL is the alarming one — it is aggressively copyleft for anything offered as a
service, and it was being treated as MIT-equivalent. Elastic-2.0 matters to this
project directly: `kreuzberg` is pinned `<5` because `RESEARCH.md` records that
its successor line moved to Elastic-2.0, and if that pin were ever removed this
classifier would have said nothing at all.

**6. An unrecognised `LicenseRef-` identifier is restricted, never permissive.**
SPDX's `LicenseRef-` prefix means, by definition, *this is not a listed
licence*. An identifier whose entire meaning is "you do not know what this is"
must not be read as "assume the friendliest one". Before Phase 9,
`LicenseRef-Anything-At-All` classified as permissive.

Checked **last**, after the copyleft, non-commercial and purchasable rules, so
`LicenseRef-Artifex-Commercial` and `LicenseRef-Proprietary` keep the sharper
answers those rules already give them.

Where `restricted` sits in the ordering is load-bearing for rule 1:
`Apache-2.0 OR BUSL-1.1` has an unconditional branch and is permissive;
`BUSL-1.1 OR AGPL-3.0` has none and resolves to restricted — fewer obligations
than the AGPL branch, and still not permissive, so the mechanism keeps it out of
this process either way.

## How enforcement actually works

Four checks, deliberately independent, because they fail in different
circumstances. All in `tests/unit/test_license_isolation.py`.

| # | Check | What it catches that the others do not |
|---|---|---|
| 1 | Every backend declares a licence and a tier, and a non-permissive one declares out-of-process isolation | An adapter lying about itself |
| 2 | No copyleft distribution is installed at all | A copyleft package arriving through a transitive requirement nobody read |
| 3 | No module in `src/tokenmill` mentions a copyleft module, **parsed rather than executed** | An adapter importing a tool that is *not installed here* — which is every CI machine |
| 4 | After a copyleft backend converts a document, its module is not in `sys.modules` | The boundary being observed rather than inferred |

Check 3 is the one that will actually catch a Phase 9 adapter written in a
hurry, and it required two design decisions:

* It reads imports **inside functions**, not only at the top of a file, because
  `CONTRIBUTING.md` rule 3 puts every heavy import inside `_convert()`. A scanner
  that only read module level would find nothing in any adapter here and pass
  forever.
* It consults `KNOWN_COPYLEFT_MODULES`, a table of module names known to belong
  to copyleft distributions whether or not those distributions are installed.
  Each entry names where its licence was read from.

**The mechanism has been seen to work.** `import pymupdf4llm` was added by hand
inside `pypdf_pdf.py`'s `_convert`, three of the four checks failed —

```
backend 'pypdf' runs in-process and imports 'pymupdf4llm', which is copyleft
src/tokenmill/backends/documents/pypdf_pdf.py imports 'pymupdf4llm'
backend 'pypdf' declares itself permissive but reaches 'pymupdf4llm', which is copyleft
```

— and the violation was reverted. Synthetic violations remain as permanent
tests. `PROGRESS.md` records the run.

**The copyleft allow-list has exactly one entry**, and adding to it costs a
paragraph on this page — a test asserts that every exempted name appears here,
and it caught the omission when `docutils` was added.

### `docutils` — the one exemption

**How it arrives:** `nicegui` → `docutils`, a direct dependency, in the `gui`
extra added in Phase 8. It is not in the core install.

**Why it is flagged:** its metadata carries no SPDX expression and three licence
classifiers:

```
License :: Public Domain
License :: OSI Approved :: BSD License
License :: OSI Approved :: GNU General Public License (GPL)
```

`classify()` joins multiple classifiers **conservatively**, as a conjunction, and
therefore reads this as copyleft. That is the right default for a licence
checker: a false positive costs a documented exemption, and a false negative
costs a licence violation. It is not the right answer here.

**Why the exemption is justified.** Reading the installed `COPYING.rst` of
docutils 0.23 rather than a summary of it: most of the project is public domain,
several files are BSD-2 or BSD-3, and the GPL applies to exactly one file —
`tools/editors/emacs/rst.el`, an Emacs editing mode. **That file is not in the
wheel.** Verified on 2026-08-26 against the installed package: no `.el` file
anywhere under `site-packages/docutils/`, and no Python file in it containing
the string "GNU General Public License".

No GPL code is installed, so none can be imported, so the rule is not breached.

**The exemption re-checks its own premise.**
`test_the_docutils_exemption_is_still_for_the_reason_claimed` re-runs both
checks against whatever version is installed. If a future docutils ships GPL
Python code, that test fails and this paragraph has to be revisited rather than
inherited — which is the failure mode of every allow-list that is written once
and trusted forever.

## Running the audit yourself

```console
$ tokenmill backends --show-licenses
...
104 installed distributions audited from their own metadata.
Every one is permissive. No AGPL or GPL package is importable from this process.
```

It exits non-zero if a copyleft package is installed.

---

## tokenmill itself

**Apache-2.0.** Permissive, with an explicit patent grant, and the licence most
of the ecosystem tokenmill wraps already uses. See [`LICENSE`](../LICENSE).

## The policy, in one paragraph

Permissive licences — MIT, Apache-2.0, BSD, ISC, PSF and the MPL family — may be
imported into the tokenmill process. **AGPL and GPL tools are never imported**:
they are invoked as a child process or reached over a service boundary, or they
are not wrapped at all. Non-commercially-licensed weights are excluded by
default.

This is not a convention that lives in prose.
`BackendInfo.__post_init__` raises `ValueError` if a backend declares a
non-permissive `license_tier` together with `IsolationMode.IN_PROCESS`, the
registry re-checks at registration, and
`tests/unit/test_protocol.py` asserts it for every backend the entry points
expose. A violating adapter cannot be constructed, let alone shipped.

## Backends and their licences

Every licence below was read from the **installed package metadata** at the
moment its adapter was written, not from `docs/research/RESEARCH.md` and not
from a project's README. Where the two disagreed, the package won and the
correction is recorded in `PROGRESS.md`.

| Backend | Version verified | Licence | Tier | Invocation |
|---|---|---|---|---|
| `plaintext` | — (ours) | Apache-2.0 | permissive | in-process |
| `markdownify_html` | markdownify 1.2.3 | MIT | permissive | in-process |
| `pdfplumber` | 0.11.10 | MIT | permissive | in-process |
| `pypdf` | 6.16.1 | BSD-3-Clause | permissive | in-process |
| `markitdown` | 0.1.7 | MIT | permissive | in-process |
| `kreuzberg` | 4.10.2 | MIT | permissive | in-process |
| `docling` | 2.121.0 | MIT | permissive | in-process |
| `trafilatura` | 2.2.0 | Apache-2.0 | permissive | in-process |
| `readability` | readability-lxml 0.8.4.1 | Apache-2.0 | permissive | in-process |
| `crawl4ai` | 0.9.2 | Apache-2.0 | permissive | in-process |
| `gitingest` | 0.3.1 | MIT | permissive | in-process |
| `repomix` | 1.18.0 | MIT | permissive | **subprocess** |
| `code2prompt` | 4.3.0 | MIT | permissive | **subprocess** |
| `pymupdf4llm` | 1.28.2 | AGPL-3.0 *or* Artifex Commercial | **copyleft** | **separate interpreter** |
| `pandoc` | 3.1.3+ds-2 | GPL-2.0-or-later | **copyleft** | **subprocess** |
| `libreoffice` | 4:24.2.7 | MPL-2.0 | permissive | **subprocess** |

**Isolation and licence are two different reasons, and this table mixes both.**
Five backends run out of process; only two of them do so because of a licence:

| Backend | Why it is out of process |
|---|---|
| `pymupdf4llm` | **Licence.** AGPL-3.0 |
| `pandoc` | **Licence.** GPL-2.0-or-later |
| `repomix` | Language. TypeScript, MIT |
| `code2prompt` | Language. Rust, MIT |
| `libreoffice` | Language. C++, MPL-2.0 |

Recorded because the isolation column would otherwise imply a licence
constraint that is not there — and because the three that are isolated for
language reasons are safe practice for the mechanism: getting the boundary
wrong on an MIT or MPL tool carries no licence risk.

### `pymupdf4llm` runs in an interpreter of its own, and that is the point

The obvious way to run a Python package out of process is
`sys.executable -c "import it; ..."`. That would be wrong here, and check 2
above is what makes it concrete: to run in *this* interpreter the AGPL package
would have to be installed in *this* environment, where anything can import it.
An AGPL package sitting in our site-packages is not isolated by the fact that we
happen not to import it today.

So it lives in an environment of its own and the adapter finds an interpreter
that has it:

```console
$ python -m venv ~/.local/share/tokenmill/pymupdf4llm
$ ~/.local/share/tokenmill/pymupdf4llm/bin/pip install pymupdf4llm
```

Two consequences worth stating:

* **It is never a tokenmill extra.** There is no `pip install "tokenmill[pymupdf4llm]"`
  and there must not be, because that would install it here.
* **The driver is a string, not a file.** The few lines that call
  `pymupdf4llm.to_markdown` are a module-level constant passed to `python -c`.
  Were they a `.py` file, this repository would contain the literal statement
  `import pymupdf4llm` and check 3 would be right to fail on it.

The file path reaches the child as `sys.argv[1]` and is never interpolated into
the source; there is no shell anywhere on the path.

### What `RESEARCH.md` got half-right

It records PyMuPDF4LLM as AGPL-3.0. The installed metadata of 1.28.2 says
`Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License`. Both halves
matter: the dual-licensing is what made the naive disjunction rule classify it
as permissive, and the AGPL half is the branch we actually hold. Neither could
have been learned from the citation.

`kreuzberg` is pinned `>=4.0,<5`. `RESEARCH.md` records that the successor
"Xberg" v1 line moved to Elastic-2.0 while the v4 line stayed MIT, and a
resolver must not be able to change our licence position by picking up a new
major version.

## Dependencies that are not simply permissive

Three, and none of them is a problem. They are listed because a licence audit
that reports only the easy answers looks like nobody checked.

### `tld` — `MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later`

**How it arrives:** `trafilatura` → `courlan` → `tld`. `courlan` requires it
unconditionally, so it is in the core install from Phase 3 onwards.

**Why it is acceptable, and it needs saying out loud because the string
contains "GPL".** That is a **disjunctive** licence: the recipient chooses one
of the three, and the obligations of the others do not apply. tokenmill takes
the **MPL-1.1** option. MPL-1.1 is file-level copyleft — it obliges us to
publish modifications to *`tld`'s own files*, and we make none — and it does not
reach into the code that uses the library the way GPL-2.0 would. It is the same
shape of obligation as `certifi`'s MPL-2.0, accepted in Phase 1 for the same
reason.

Nothing about this is a GPL dependency, and choosing the GPL option would be a
decision nobody has made. Recorded so that the next person to grep the
dependency tree for "GPL" finds the answer here rather than raising it as a
defect.

**If that ever becomes uncomfortable**, the escape is `courlan`, not
`trafilatura`: `tld` is a public-suffix lookup, and the alternatives are all
permissive. It would mean vendoring or patching a transitive dependency, which
is a real cost, so it is not worth doing on principle alone.

### `certifi` — MPL-2.0

Arrives via `requests` ← `tiktoken`, in the core install since Phase 1.
File-level copyleft: it obliges us to publish modifications to its files, and we
make none. It does not restrict distributing tokenmill under Apache-2.0.

### `pathspec` — MPL-2.0

Arrives via `gitingest` in the `repo` extra. Same reasoning as `certifi`. `tqdm`
(`MPL-2.0 AND MIT`) and `hypothesis` (MPL-2.0, development only) are the same
case again.

## Tools deliberately not wrapped in-process

These are named in `RESEARCH.md` and are useful. They are AGPL or GPL, so
`CONTRIBUTING.md` rule 2 applies: subprocess or service boundary only, and none
of them is wrapped at all yet.

| Tool | Licence | Status |
|---|---|---|
| PyMuPDF4LLM | AGPL-3.0 or Artifex Commercial | **Wrapped in Phase 7**, separate interpreter. Never imported. |
| Firecrawl (core) | AGPL-3.0 | Not wrapped. Appendix-only per `RESEARCH.md`. |
| Pandoc | GPL-2.0-or-later | **Wrapped in Phase 7**, subprocess. |
| omniparse | GPL | Not wrapped. |
| Marker | GPL-3.0 | Phase 9, out of process, GPU. |
| Surya | GPL-3.0 | Phase 9, out of process, GPU. |
| Jina ReaderLM weights | CC-BY-NC-4.0 | **Non-commercial.** Excluded by default. |
| html2text | GPL-3.0 | Not wrapped; markdownify (MIT) does the same job. |

## Audits actually performed

Each of these was run, not assumed. The command is
`importlib.metadata` over every installed distribution, reading
`License-Expression`, then the licence classifiers, then the `License` field.

| Date | Scope | Packages | Result |
|---|---|---|---|
| 2026-08-20 | Core install, no extras | 20 | No GPL, no AGPL. One MPL-2.0 (`certifi`). |
| 2026-08-21 | Full `docling` resolution | 122 | No GPL, no AGPL. `certifi` and `tqdm` MPL-2.0. |
| 2026-08-22 | Full `crawl4ai` resolution | 94 | No GPL, no AGPL, no PyTorch. Apache-2.0 throughout the crawl4ai/Playwright core. |
| 2026-08-22 | Dev environment: core + `documents` + `web` + `crawl4ai` + `dev` + `fixtures` | 154 | One flagged: `tld`, explained above. Everything else MIT, Apache-2.0, BSD, ISC, PSF or MPL. |
| 2026-08-22 | Dev environment with the `repo` extra, without `crawl4ai` | 99 | Same single flag. gitingest's tree adds `starlette`, `pydantic`, `httpx`, `loguru` and `pathspec` — BSD-3-Clause, MIT, BSD-3-Clause, MIT and MPL-2.0. |
| 2026-08-26 | Dev environment: core + `documents` + `web` + `repo` + `chunk` + `dev` + `fixtures`, **by `tokenmill backends --show-licenses`** | 104 | **Every one permissive.** `tld` resolves through its disjunction rather than by exemption. This audit now runs on every CI cell rather than being performed by hand. |

## The GPU tier (Phase 9)

The largest licence surface in the project, and the one where `RESEARCH.md` was
wrong twice more. Every entry below was read from the **published artefact** —
the wheel's `METADATA` and the licence file it bundles — on 2026-08-27, except
where it says otherwise.

| Backend | Package and version | Verified licence | Tier | `RESEARCH.md` said |
|---|---|---|---|---|
| Marker | `marker-pdf` 2.0.0 | Apache-2.0 | permissive | GPL-3.0 |
| Surya | `surya-ocr` 0.22.1 | Apache-2.0 | permissive | GPL-3.0 |
| MinerU | `mineru` 3.4.5 | `LicenseRef-MinerU-Open-Source-License` | **restricted** | AGPL-3.0 |
| olmOCR | `olmocr` 0.4.27 | Apache-2.0 | permissive | Apache-2.0 |
| DeepSeek-OCR | *no package* | MIT **as reported**, not read | permissive | — |
| dots.ocr | *no package* | MIT **as reported**, not read | permissive | — |

The last two are a weaker claim than the first four and the table says so.
DeepSeek-OCR and dots.ocr are model weights rather than Python packages, so
there is no artefact to download; both projects state MIT and this environment
cannot reach either repository to confirm it. "We read it" and "they say so" are
different claims, and this project has been caught by the second five times now.

### Two of them are permissive and still never imported

Marker and Surya relicensed from GPL to Apache between the versions `RESEARCH.md`
surveyed and today, so their **code could legally be imported**. It is not, and
the reason is `CONTRIBUTING.md` **rule 1 rather than rule 2**: importing them
would put PyTorch and a CUDA stack into tokenmill's dependency tree.

This is the same distinction `backends/external/` already keeps for LibreOffice
— permissive, out of process because it is C++ — and it is kept visible for the
same reason: the isolation column would otherwise imply a licence constraint
that is not there.

### MinerU, and why there is a fourth tier

`mineru` 3.4.5's metadata carries no SPDX-listed identifier:

```
License-Expression: LicenseRef-MinerU-Open-Source-License
License-File: LICENSE.md
```

and the bundled `LICENSE.md` reads:

> MinerU is licensed under Apache License 2.0 **and is subject to the additional
> terms below.**
>
> **1. Commercial License and Thresholds.** [...] if you and your Affiliates, on
> a consolidated basis, meet either of the following thresholds, you must obtain
> a separate commercial license [...] a. monthly active users (MAU) exceed 100
> million; or b. total monthly revenue exceeds USD 20 million.
>
> **2. Online Service Attribution Obligation.** If you provide online services
> to third parties based on MinerU, you must clearly and prominently indicate
> [...] that MinerU is used.
>
> **3. Termination.** [...] this License and all rights granted under this
> License will terminate automatically [...]

None of the three existing tiers described that:

- **Not copyleft.** Nothing obliges anyone to publish source.
- **Not non-commercial.** Commercial use is expressly allowed below the
  thresholds.
- **Not permissive**, and this is the one with a consequence a user can hit.
  **`tokenmill gui --server` is an online service.** An operator converting
  documents through MinerU behind it owes clause 2's attribution, and if
  tokenmill had called this licence permissive it would have been the reason
  nobody told them.

So the adapter warns on **every** conversion, naming both obligations and
pointing here. A licence term nobody is told about is one nobody complies with.

`RESEARCH.md`'s AGPL entry was true of the predecessor: `magic-pdf` 1.3.12 on
PyPI still reads `License: AGPL-3.0`.

### Model weights are a separate licence, and none of them is verified

An Apache-2.0 repository routinely ships weights under something else — a RAIL
licence with use restrictions, a non-commercial clause, or a bespoke agreement.
**Not one weights licence in this tier has been read**, because the host they
are published on is denied at this environment's egress proxy.

Every heavy adapter therefore records `weights_licence: unverified` on every
result it produces, `tokenmill doctor` prints *"weights licence: NOT VERIFIED.
The code's licence above is not the weights'; read the model card before relying
on it"*, and a test asserts that stays true until somebody actually verifies one.

`RESEARCH.md` reports Marker's weights as carrying use restrictions with a
revenue threshold, and Jina's ReaderLM weights as CC-BY-NC. Both are recorded
here **as reports**. The conservative rule stands meanwhile: weights reported
non-commercial are excluded by default.

### The PyPI name that is not the model

`pip install deepseek-ocr` installs a third party's SDK for a hosted API:

```
Name: deepseek-ocr
Version: 0.3.0
Summary: A simple and efficient Python SDK for DeepSeek-OCR API
License-Expression: MIT
Project-URL: Repository, https://github.com/BukeLy/DeepSeek-OCR-SDK
Copyright (c) 2025 Chengjie
```

MIT, and irrelevant: wrapping it would have shipped a **hosted-SaaS backend**,
which this project's first constraint forbids outright, while appearing to have
wrapped DeepSeek's model. A licence check alone would have waved it through —
what caught it was reading the `Summary` line.

## What the distributed artefacts contain (Phase 11)

There are four things this project distributes, and they do not all have the
same licence position. Each is stated from what is actually inside the
artefact, not from intent.

### 1. The wheel — `tokenmill-0.1.0-py3-none-any.whl`

**Apache-2.0. 96 files, 0.97 MB unpacked, all of it our own source.** No vendored
dependency, no bundled binary, no model weight. Verified by listing the archive:
91 entries under `tokenmill/` and 5 under `tokenmill-0.1.0.dist-info/`.

Installing it pulls six runtime dependencies — `typer`, `tiktoken`,
`markdownify`, `pdfplumber`, `pypdf`, `trafilatura` — which resolve to 40
packages and 141.2 MB. Every one is permissive; the audit above is the check,
and it runs on every CI cell. **Nothing copyleft is installed by
`pip install tokenmill`.**

The copyleft backends are reachable and not present. `pandoc` (GPL-2.0-or-later)
and `libreoffice` (MPL-2.0) are system binaries you install yourself;
`pymupdf4llm` (AGPL-3.0) expects an interpreter of its own. tokenmill executes
all three across a process boundary and imports none of them. A machine without
them gets an "unavailable" row and an install hint, which is the whole design.

### 2. The sdist — `tokenmill-0.1.0.tar.gz`

Same licence position, more files: it adds `tests/` (including the generated
fixture corpus), `scripts/`, `docs/`, `benchmarks/` (harness **and** the
committed results) and `docker/`. About 1.34 MB.

The fixture corpus is generated by `scripts/make_fixtures.py` from text written
for this repository. It contains no third-party document, no scraped page and
no sample from anyone else's test suite, so it carries no licence of its own
beyond this project's.

### 3. The container image, `core` target

**The wheel plus its Python dependencies on `python:3.12-slim-bookworm`.** The
Debian base carries its own licences, as every image does; nothing is added on
top of it beyond what `pip install tokenmill` would install on any machine. No
copyleft component.

### 4. The container image, `full` target — read this one

**This image contains Pandoc (GPL-2.0-or-later) and LibreOffice (MPL-2.0) as
installed programs.** Putting them in an image and handing that image to someone
is distribution, which is a different act from executing a program a user
installed themselves, and it is the only place in this project where that
distinction bites.

It remains sound because of *how* they are there: as separate executables
invoked across a process boundary, not linked into or imported by tokenmill.
tokenmill's own code stays Apache-2.0 and the GPL's terms apply to Pandoc as
they do wherever Debian ships it — including your obligation, if you
redistribute this image, to pass on the source availability Debian's packages
carry.

**If you would rather not make that distribution, build `--target core`.** It
has neither program, and the two backends simply report themselves unavailable.
Both targets are built and smoke-tested by `.github/workflows/release.yml`.

### What none of them contains

**No model weights, under any licence, in any artefact.** Not in the wheel, the
sdist or either image. The heavy tier's `weights_licence` is `None` on every
adapter — not "permissive", not "unknown-but-probably-fine", but a recorded
absence of a verified answer. `docs/BACKENDS.md` and the section above say what
is and is not known about each. Nothing downloads a weight until you install
that backend yourself and run it.

## What Phase 7 delivered, and what it still does not

Delivered:

- A `SubprocessConverter` base with binary discovery beyond `PATH`, version
  probing, an **allow-list** of every program tokenmill may launch, and a
  temp-file lifecycle that survives the timeout and failure paths.
- An automated licence check that runs on every CI cell, so this page is
  verified rather than maintained by hand. The audit table below is now a record
  of what was checked, not the checking itself.
- Three isolated adapters, one of them AGPL and demonstrated converting a
  document without ever entering `sys.modules`.

Still outstanding, and deliberately so:

- **No sandboxing.** A tool run through `backends/external/` has the same
  filesystem and network access the user does. There are no resource limits, no
  filesystem confinement and no network namespace. The boundary is a licence and
  language boundary, **not** a security boundary, and nothing in this project
  should be read as claiming otherwise.
- **No output streaming.** A child's stdout is buffered whole, so a tool that
  emits a gigabyte holds a gigabyte in memory.
- ~~**A statement of what tokenmill's distributed artefact contains.**~~
  **Done** at Phase 11 — see the next section.
