# Licences

**Status:** current as of Phase 3. This page was a dead link from
[`CONTRIBUTING.md`](../CONTRIBUTING.md) rule 2 for three phases — the rule that
the whole project's licence position rests on pointed at a file that did not
exist. Creating it here, small and accurate, beats either leaving the link
broken or waiting for the full Phase 7 enforcement work.

Phase 7 owns *enforcement* — the isolation layer, the subprocess boundary and
the automated licence checks. This page owns the *record*: what tokenmill is
licensed as, what it actually pulls in, and the one dependency in the tree whose
licence needs a sentence of explanation.

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

**`repomix` and `code2prompt` run out of process even though their licences do
not require it.** MIT would permit importing them; they are subprocess backends
because they are TypeScript and Rust, not because of their licences. Recorded
because the isolation column would otherwise imply a licence constraint that is
not there — and because it means Phase 7's enforcement work has two backends to
practise on that carry no risk if it gets something wrong.

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
| PyMuPDF4LLM | AGPL-3.0 | Phase 7, subprocess only. Never imported. |
| Firecrawl (core) | AGPL-3.0 | Not wrapped. Appendix-only per `RESEARCH.md`. |
| Pandoc | GPL-2.0+ | Phase 7, subprocess only. |
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

## What Phase 7 still owes this page

- A `SubprocessConverter` base with binary discovery, sandboxing and an
  allow-list, so a copyleft tool can be wrapped at all.
- An automated licence check in CI, so this page is verified rather than
  maintained by hand. Today it is maintained by hand, and that is a known
  weakness: it is accurate as of the audits above and will drift.
- A statement of what tokenmill's *distributed artefact* contains, which
  matters at Phase 11 when there is a wheel on PyPI.
