# Benchmarks

Empty until Phase 10. This directory will hold the harness that runs a
corpus × backends × formats matrix and records, for every cell: token counts
under several tokenizers, wall time, peak memory, failures, **and a fidelity
score against hand-labelled ground truth**.

The fidelity axis is the point. Token savings without a fidelity measurement is
not a result — a converter that emits an empty string scores a 100% reduction.

Results are committed under `benchmarks/results/<date>/` as CSV, JSON and
Markdown, and every number published in `docs/BENCHMARKS.md` or the README must
trace back to a committed raw result file here.
