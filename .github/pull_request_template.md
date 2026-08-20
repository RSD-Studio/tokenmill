## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Phase

<!-- Which development-plan phase does this belong to? -->

## Verification

<!--
Paste the REAL output. "Should work" is not verification; a zero exit code is
not verification either, because a converter that returns an empty string
exits 0. Read the output you produced and say whether it is correct.
-->

```
$ uv run ruff check . && uv run ruff format --check .
$ uv run mypy
$ uv run pytest -q --cov=tokenmill
```

**Output inspected:** <!-- What did you actually read, and was it right? -->

## Checklist

- [ ] Full suite green locally, not just the new test
- [ ] `pip install .` with no extras still works (no heavy dep leaked into core)
- [ ] Any new backend imports lazily and degrades to "unavailable" when its dep is absent
- [ ] Any new backend declares its licence, and no copyleft package is imported in-process
- [ ] Every number added to code or docs is sourced or measured — none invented
- [ ] Docs updated in this change (README / ARCHITECTURE / BACKENDS as applicable)
- [ ] `PROGRESS.md` updated
- [ ] No stubs, no `TODO: implement`
