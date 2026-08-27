# Adding a backend

A backend is a Python class plus an entry point. You do not fork tokenmill, you
do not edit anything in `src/tokenmill/core/`, and you do not register anything
by hand — `pip install` is the whole installation step.

This page walks through a **complete, working** backend. Everything in it has
been built, installed and run; the verification log in
[`PROGRESS.md`](../PROGRESS.md) records the session. Copy it and change the
parts that matter.

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first if you want the reasoning behind
the contract. This page is the mechanics.

---

## The contract, in one screen

```python
class Converter(Protocol):
    info: BackendInfo

    def is_available(self) -> Availability: ...  # cheap, cached, never raises
    def supports(self, source: Source) -> bool: ...
    def convert(self, source: Source, options: ConvertOptions) -> ConversionResult: ...
```

You will almost always subclass `BaseConverter`, which implements all three and
leaves you one method to write:

```python
def _convert(self, source, options, context) -> str: ...
```

By the time it is called, availability, format support and the size limit have
been checked. You return text. **You do not count tokens** — the pipeline
measures every stage, and a backend that measured its own output would bypass
that accounting.

---

## A complete example: `csvtable`

A backend that turns a CSV file into a Markdown table. Small enough to read in
one go, real enough to exercise everything: metadata, a probe, error handling,
warnings and structured metadata.

### Layout

```
tokenmill-csvtable/
├── pyproject.toml
├── src/
│   └── tokenmill_csvtable/
│       ├── __init__.py
│       └── backend.py
└── tests/
    └── test_csvtable.py
```

### `src/tokenmill_csvtable/backend.py`

```python
"""A tokenmill backend that renders CSV files as Markdown tables."""

from __future__ import annotations

import csv
import io

from tokenmill import (
    BackendInfo,
    BaseConverter,
    ConversionContext,
    ConvertOptions,
    CorruptSource,
    Domain,
    LicenseTier,
    OutputFormat,
    Source,
)

__all__ = ["CsvTableConverter"]


class CsvTableConverter(BaseConverter):
    """Renders a CSV file as a Markdown table.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="csvtable",
        name="CSV to Markdown table",
        description="Renders a CSV file as a Markdown table, header row included.",
        domains=(Domain.DOCUMENTS,),
        input_formats=("csv", "tsv"),
        output_formats=(OutputFormat.MARKDOWN,),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/example/tokenmill-csvtable",
        install_extra=None,
        priority=20,
    )

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Render the source CSV as a Markdown table.

        Args:
            source: The CSV to convert.
            options: Unused; this backend takes no settings.
            context: Collects row and column counts, and any warning.

        Returns:
            The Markdown table.

        Raises:
            CorruptSource: If the file has no rows at all.
        """
        del options

        delimiter = "\t" if source.format == "tsv" else ","
        rows = list(csv.reader(io.StringIO(source.read_text()), delimiter=delimiter))
        rows = [row for row in rows if any(cell.strip() for cell in row)]

        if not rows:
            raise CorruptSource(
                f"{source.name} contains no rows",
                backend_id=self.info.id,
                hint="check the file is a CSV and not empty",
            )

        width = max(len(row) for row in rows)
        if any(len(row) != width for row in rows):
            # Ragged input is recoverable, so pad rather than fail — but say so,
            # because silently inventing empty cells would be worse than either.
            context.warn(
                f"{source.name} has rows of differing lengths; short rows were "
                f"padded to {width} columns"
            )
        padded = [[*row, *[""] * (width - len(row))] for row in rows]

        header, *body = padded
        lines = [
            "| " + " | ".join(_escape(cell) for cell in header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        lines.extend("| " + " | ".join(_escape(cell) for cell in row) + " |" for row in body)

        context.note("rows", len(body))
        context.note("columns", width)
        return "\n".join(lines) + "\n"


def _escape(cell: str) -> str:
    """Make a cell safe to place inside a Markdown table.

    Args:
        cell: The raw cell value.

    Returns:
        The cell with pipes escaped and newlines flattened.
    """
    return cell.replace("|", "\\|").replace("\n", " ").strip()
```

### `pyproject.toml`

The entry point is the whole registration mechanism. The group name is
`tokenmill.backends`; the entry point's name is conventionally the backend's
`id`, and its value is `module:Class`.

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "tokenmill-csvtable"
version = "0.1.0"
description = "A tokenmill backend that renders CSV as a Markdown table"
requires-python = ">=3.11"
license = "MIT"
dependencies = ["tokenmill>=0.1"]

[project.entry-points."tokenmill.backends"]
csvtable = "tokenmill_csvtable.backend:CsvTableConverter"

[tool.hatch.build.targets.wheel]
packages = ["src/tokenmill_csvtable"]
```

The entry point must resolve to a **zero-argument callable returning a
Converter**. A class satisfies that; so does a factory function, if you need one.

### Install and check

```console
$ pip install -e .
$ tokenmill backends
id                domains    license     tier        isolation   availability
----------------  ---------  ----------  ----------  ----------  ------------
csvtable          documents  MIT         permissive  in-process  available
markdownify_html  web        MIT         permissive  in-process  available
plaintext         text       Apache-2.0  permissive  in-process  available

$ tokenmill convert data.csv --tokenizer bytes
| Backend | License | Tables |
| --- | --- | --- |
| markitdown | MIT | weak |
| docling | MIT | strong |
source:   data.csv
backend:  csvtable
format:   markdown
duration: 14 ms
post:     normalize_whitespace
tokens:   62 -> 106  (+71.0%, bytes)
```

No core edit. That is the entire mechanism.

*(That output is real, and note what it says: the Markdown is 71% **larger**
than the CSV, because table pipes and separator rows cost more than commas.
tokenmill reports that as growth rather than dressing it up — this exact case is
what `RESEARCH.md` Category 7 means about serialisation-format tradeoffs, and it
is why `--tokenizer bytes` is a size measure rather than a verdict.)*

### `tests/test_csvtable.py`

```python
"""Tests for the csvtable backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenmill import ConvertOptions, CorruptSource, Source
from tokenmill_csvtable.backend import CsvTableConverter


def write(tmp_path: Path, content: str, name: str = "data.csv") -> Source:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return Source.from_path(path)


def test_it_renders_a_markdown_table(tmp_path: Path) -> None:
    result = CsvTableConverter().convert(write(tmp_path, "a,b\n1,2\n"), ConvertOptions())

    assert result.text == "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    assert result.metadata["rows"] == 1
    assert result.metadata["columns"] == 2


def test_ragged_rows_are_padded_and_reported(tmp_path: Path) -> None:
    result = CsvTableConverter().convert(write(tmp_path, "a,b,c\n1,2\n"), ConvertOptions())

    assert "| 1 | 2 |  |" in result.text
    assert any("differing lengths" in w for w in result.warnings)


def test_pipes_in_cells_are_escaped(tmp_path: Path) -> None:
    result = CsvTableConverter().convert(write(tmp_path, 'a\n"x|y"\n'), ConvertOptions())

    assert "x\\|y" in result.text


def test_an_empty_file_is_reported_as_corrupt(tmp_path: Path) -> None:
    with pytest.raises(CorruptSource, match="no rows"):
        CsvTableConverter().convert(write(tmp_path, "\n\n"), ConvertOptions())


def test_it_declares_a_permissive_licence_and_in_process_isolation() -> None:
    info = CsvTableConverter().info

    assert info.license_tier.value == "permissive"
    assert info.isolation.value == "in-process"
```

---

## Backends with a dependency

`csvtable` uses only the standard library, so it is always available. A backend
wrapping a third-party library has two extra obligations.

**Import inside `_convert`, never at module scope.** The module must import
cleanly with the dependency absent. This is `CONTRIBUTING.md` rule 3, and it is
what makes a missing dependency a greyed-out row rather than a crash at
start-up.

**Override `_probe`, and probe without importing.**

```python
import importlib.util

from tokenmill import Availability


class PdfSqueezeConverter(BaseConverter):
    info = BackendInfo(
        ...,
        install_extra="documents",
    )

    def _probe(self) -> Availability:
        """Check that pdfsqueeze is importable."""
        if importlib.util.find_spec("pdfsqueeze") is None:
            return Availability.missing_dependency(
                "pdfsqueeze", hint='pip install "tokenmill[documents]"'
            )
        return Availability.present()

    def _convert(self, source, options, context) -> str:
        import pdfsqueeze  # imported here, not above

        ...
```

`find_spec` rather than a `try: import` because the probe runs on every
`tokenmill backends` listing, and importing costs whatever the dependency costs.

**A dependency that warns at import time will fail your conversion.** Not
hypothetically: MarkItDown imports magika, which imports onnxruntime, which
warns `Unsupported Windows version` the moment it loads, and under `-W error` —
which this project's own test suite sets — that warning becomes an exception
inside your lazy import. `BaseConverter` then reports your perfectly healthy
backend as `BackendFailed`.

Suppressing it is the wrong fix; "your platform is unsupported" is worth
hearing. Wrap the import instead, and the warning reaches the user as a warning:

```python
from tokenmill.backends._common import warnings_as_conversion_warnings


def _convert(self, source, options, context) -> str:
    with warnings_as_conversion_warnings(context, activity="importing pdfsqueeze"):
        import pdfsqueeze

    ...
```

**An empty result is not a success.** A converter that returns nothing still
exits 0 and still writes a file. If yours can legitimately produce nothing —
a scanned PDF has no text layer, and every document backend here returns an
empty string for one — say so:

```python
from tokenmill.backends._common import warn_on_empty_output

warn_on_empty_output(
    text,
    source=source,
    context=context,
    reason="pdfsqueeze found no text layer, which is what a scanned PDF looks like",
)
```

---

## Where your backend ranks

`tokenmill` picks a backend per format. Selection is:

1. an explicit `--backend`, which always wins and never falls back;
2. otherwise, among backends that claim the format **and** can currently run:
   highest effective priority, then in-process before out-of-process, then by id.

Effective priority comes from the per-format map in
[`tokenmill/core/preferences.py`](../src/tokenmill/core/preferences.py), falling
back to your declared `BackendInfo.priority` when the map does not name you.
That is deliberate: **a high enough `priority` outranks everything the map
names**, so a third-party backend never needs a core edit to win a format.

```python
info = BackendInfo(
    ...,
    priority=100,  # beats every built-in for any format the map does not rank you in
)
```

If your backend belongs in the map — because it is better or worse than a
built-in at a specific format, and you can show that on the fixture corpus —
add it there with the evidence, and add the observation to `docs/BACKENDS.md`.

### Fallback

Selection returns a *chain*, and the pipeline walks it until one backend
succeeds. So your backend gets a turn when a better-ranked one is uninstalled or
fails on a particular file, and a better-ranked one gets a turn when yours
fails. Every attempt is recorded on `ConversionResult.attempts`, and a fallback
warns naming what failed — nothing about it is silent.

This is one more reason to raise a precise error: `CorruptSource` says the input
is bad, `BackendUnavailable` says you cannot run, and `BackendFailed` says you
tried and something went wrong. All three let the chain continue; all three read
differently to the user.

---

## Copyleft and non-Python tools

**AGPL and GPL code is never imported into the tokenmill process.** Not as a
style preference — as the licence position the whole project rests on. See
`CONTRIBUTING.md` rule 2 and `RESEARCH.md` Category 1–3 for which tools this
covers (PyMuPDF4LLM, Marker, Surya, Pandoc, Firecrawl core, omniparse).

The model enforces it. This raises `ValueError` at import time:

```python
BackendInfo(
    id="pymupdf4llm",
    license="AGPL-3.0",
    license_tier=LicenseTier.COPYLEFT,
    isolation=IsolationMode.IN_PROCESS,   # ValueError: must run out of process
    ...,
)
```

Such a backend declares `IsolationMode.SUBPROCESS` (or `SERVICE`) and invokes
the tool as a child process. The hardened `SubprocessConverter` base — binary
discovery, timeouts, temp-file lifecycle, stderr capture, list arguments and
never `shell=True` — lands in **Phase 7**. Until then, a subprocess backend must
build that itself; the protocol supports it, but the shared machinery is not
there yet.

The same applies to Node and Rust tools (Repomix, code2prompt): subprocess, with
`Availability.missing_binary(...)` and an install hint when the executable is not
on `PATH`.

Non-commercial weights (ReaderLM, CC-BY-NC-4.0) use
`LicenseTier.NON_COMMERCIAL`, which is likewise barred from in-process
isolation and excluded by default.

---

## What your backend is held to

Installing a backend automatically enrols it in
`tests/unit/test_protocol.py`, which parametrises over every backend the entry
points expose. It checks, among other things, that:

- the metadata is complete and the id is a lowercase token;
- it converts a real sample of a format it claims — the corpus in
  `tests/fixtures/` supplies PDF, DOCX, PPTX and XLSX, so declaring one of those
  means being exercised against a real document, not a stub. Raising
  `NetworkRequired` counts as a correct answer if your backend needs a download
  and `allow_network` is false;
- a licence and tier are declared, and a non-permissive tier implies
  out-of-process isolation;
- input formats are bare lowercase extensions — `pdf`, not `.pdf`;
- `is_available()` never raises, is cached, and offers a hint when unavailable;
- `supports()` agrees with the declared formats;
- converting an unsupported source raises inside the `ConversionError` taxonomy;
- the result carries no token counts;
- a source over `max_bytes` is refused.

Run it against your backend with:

```console
$ pytest tests/unit/test_protocol.py -v
```

---

## Checklist

- [ ] Subclasses `BaseConverter`; implements `_convert` only.
- [ ] `BackendInfo` complete, with `license`, `license_tier` and `isolation`.
- [ ] Copyleft or non-commercial? Then `SUBPROCESS` or `SERVICE`, never
      `IN_PROCESS`.
- [ ] Heavy dependency imported inside `_convert`, probed with `find_spec` in
      `_probe`.
- [ ] `Availability` failures carry a hint that says how to fix them.
- [ ] Failures raise a `ConversionError` subclass; recoverable oddities become
      `context.warn(...)`.
- [ ] Structured facts recorded with `context.note(...)`.
- [ ] Entry point declared under `[project.entry-points."tokenmill.backends"]`.
- [ ] Tests written, including the error paths.
- [ ] `pytest tests/unit/test_protocol.py` green with your backend installed.
- [ ] Import-time warnings wrapped with `warnings_as_conversion_warnings`.
- [ ] Empty output reported with `warn_on_empty_output`.
- [ ] `priority` set, or an entry in `FORMAT_PREFERENCES` with its evidence.
- [ ] If it produces poor output on some input, that goes in
      [`BACKENDS.md`](BACKENDS.md) under failure modes, **with a test that
      asserts the failure**, so a future upstream fix corrects the docs instead
      of quietly falsifying them. A wrapper that hides a bad converter is worse
      than no wrapper.

---

## Post-processors, tokenizers and table formats register the same way

Nothing here is special-cased. Four entry point groups, one mechanism:

| Group | What it registers | Protocol |
|---|---|---|
| `tokenmill.backends` | Converters | `Converter` |
| `tokenmill.postprocessors` | Post-processors | `PostProcessor` |
| `tokenmill.tokenizers` | Tokenizer providers | `TokenizerProvider` |
| `tokenmill.formats` | Table encoders | `TableEncoder` |

```toml
[project.entry-points."tokenmill.postprocessors"]
shouty = "my_package.shouty:Shouty"

[project.entry-points."tokenmill.formats"]
yaml = "my_package.yaml_table:YamlTableEncoder"
```

### Two flags, and they answer different questions

```python
class Shouty(BasePostProcessor):
    id = "shouty"
    name = "Shouty"
    description = "Upper-cases everything."
    destructive = True  # <- what it can lose; shown to the user
    in_default_chain = False  # <- whether it runs when nobody asked; the mechanism
    order = 300

    def process(self, text: str, options: ConvertOptions) -> str:
        return text.upper()
```

`default_chain()` reads **`in_default_chain` and nothing else**. `destructive`
is documentation: it is what the CLI's `post` listing and the GUI show someone
deciding whether to switch a step on, and no code branches on it.

Answer them separately:

- **`destructive`** — can this discard information the user might have wanted?
  If yes, `in_default_chain` must be `False`, and a registry-wide test in
  `tests/unit/test_post_phase5.py` enforces that implication in both directions.
- **`in_default_chain`** — should this run when the user names no chain? A step
  that loses nothing can still answer no, because it *reshapes* the document.
  `chunk` is exactly that case: it inserts markers, discards nothing, and nobody
  who did not ask for chunking should get chunk boundaries.

Until Phase 7 there was only `destructive`, and it did both jobs. That forced
`chunk` to declare itself destructive purely to stay out of the default chain —
a lie of convenience that the owner signed off splitting. If you find yourself
setting `destructive` for a reason that is not "this can lose information", you
want `in_default_chain` instead.

Pick an `order` inside the band that matches what you do; `docs/ARCHITECTURE.md`
lists them. Two post-processors sharing an order is not an error but does make
the chain depend on id ordering, so avoid it.

### If your tool is copyleft or is not Python, it runs out of process

Subclass `SubprocessConverter` rather than `BaseConverter`, declare which
allow-listed program you launch, and write one method:

```python
from tokenmill.backends.isolated.base import SubprocessConverter

class MyToolConverter(SubprocessConverter):
    info = BackendInfo(
        id="mytool",
        ...,
        license="GPL-3.0-or-later",
        license_tier=LicenseTier.COPYLEFT,   # BackendInfo refuses this
        isolation=IsolationMode.SUBPROCESS,  # with IN_PROCESS
    )
    executable = "mytool"   # must be a key of ALLOWED_EXECUTABLES

    def run_conversion(self, source, options, context, workspace) -> str:
        result = self.run(
            ["--to", "markdown", self.path_argument(source.path)],
            options=options,
            cwd=workspace,
        )
        return result.stdout
```

You get discovery, the availability probe, version probing, the timeout, and a
`workspace` directory removed on every exit path — including when your
conversion raises and when the child times out.

**Add your program to `ALLOWED_EXECUTABLES` first**, with an install hint and
the platform search paths. An executable that is not in that table cannot be
launched, and that is the point: it makes the set of programs tokenmill will
start one reviewable list rather than a claim each adapter makes about itself.

**Read the licence from the installed package, at the moment you write the
adapter.** Not from `RESEARCH.md`, not from a README. Phase 7 found
PyMuPDF4LLM's real metadata says `Dual Licensed - GNU AFFERO GPL 3.0 or Artifex
Commercial License` where `RESEARCH.md` says "AGPL-3.0" — and the difference
broke the licence classifier.

**A copyleft Python package does not go in an extra.** Installing it here makes
it importable here, which the licence tests correctly reject. Give it an
environment of its own and find an interpreter for it, as
`pymupdf4llm_pdf.py` does.

**For an HTTP service**, subclass `ServiceConverter` and write `call_service`.
Take the address from `--extra <id>_url=` and never guess at one.

### If your encoder cannot represent something, raise

A `TableEncoder` implements `encode(table)` and `decode(text)`, and the contract
is that they round-trip. Where your format genuinely cannot carry something —
JSON cannot key a row by an unnamed column — raise `TableError` rather than
dropping it silently. Where the loss is inherent and unavoidable, document it on
the encoder, as the Markdown encoder does for line breaks in cells.
