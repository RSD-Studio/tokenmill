"""The benchmark harness: our own measured evidence, in files anyone can check.

`benchmarks/README.md` set the rule in Phase 0 and this package is what finally
makes it satisfiable:

> every number published in `docs/BENCHMARKS.md` or the README must trace back
> to a committed raw result file here.

Every figure this project has published so far was instead "asserted by a test",
which that page says out loud is the weaker guarantee. A test proves the number
was true when the test was written. A committed result file says which commit,
which corpus, which machine, how many repeats, and what the other four repeats
measured.

Four modules:

* `models` — what one cell records, and why each field is shaped as it is.
* `memory` — peak memory measured honestly, or reported as unavailable.
* `harness` — the runner: warm-up, repeats, fidelity, failures.
* `report` — CSV, JSON and Markdown, and the function that **refuses** to
  publish a token column without a fidelity column beside it.

`python -m benchmarks.run --out benchmarks/results/<date>` regenerates
everything; `python -m benchmarks.merge` combines a local byte-unit run with a
CI model-token run.
"""

from __future__ import annotations

__all__: list[str] = []
