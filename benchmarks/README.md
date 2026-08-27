# Benchmarks

The harness that runs a corpus × backends × tokenizers matrix and records, for
every cell: token counts, wall time, peak memory, failures, **and a fidelity
score against hand-labelled ground truth**.

The fidelity axis is the point. **Token savings without a fidelity measurement
is not a result — a converter that emits an empty string scores a 100%
reduction.** Four cells in the committed run do exactly that, and the report
gives them their own section rather than a place in the table.

Every number published in `docs/BENCHMARKS.md` or the README must trace back to
a committed raw result file here.

## Running it

```
uv run python -m benchmarks.run --out benchmarks/results/$(date +%F) --repeats 5 --allow-network
```

Takes about 100 seconds on four cores with the core, `documents`, `web` and
`repo` extras installed. It never raises on a failing backend: a failure is a
row.

| Flag | What it does |
|---|---|
| `--out` | Where to write. Required. Conventionally a dated directory. |
| `--repeats` | Timed runs per cell after a discarded warm-up. Default 5. |
| `--tokenizer` | Repeatable. Default `bytes`. See "Two units" below. |
| `--backend` | Repeatable. Restricts the matrix, for a quick check. |
| `--allow-network` | Lets backends fetch. Off by default; `repomix` needs it, because `npx` downloads it. |
| `--timeout` | Per-conversion budget in seconds. Default 300. |

Exit status is **0 even when cells failed** — the run succeeded in measuring
that the backend fails. It is 1 only when a whole *unit* produced no count from
any successful cell, which means the tokenizer would not load and the run
measured nothing it was asked for.

## What each file is

| File | For |
|---|---|
| `report.md` | Reading. Fixture table, failures, empties, wall time and memory. |
| `results.csv` | A spreadsheet. One row per cell, flat. |
| `results.json` | Every individual repeat, every fidelity component, every warning. |
| `manifest.json` | Provenance: commit, dirty flag, corpus digest, platform, backend versions, and notes on what this environment could not measure. |

`manifest.json` is what makes a result set checkable rather than merely
published. The corpus digest covers every fixture byte, so a run against an
edited corpus is visibly a different measurement.

## Two units, and why they cannot be mixed

A cell is keyed by (fixture, backend, **tokenizer**). That is not incidental.

The environment tokenmill is developed in denies every tokenizer vocabulary host
at an egress proxy, so **a local run can only count UTF-8 bytes**. CI can reach
`o200k_base`. A byte figure is not a token figure — on this project's own
tabular data the two disagreed by 24 points and did not even rank the five
serialisation formats in the same order.

So the two runs are merged rather than averaged:

```
uv run python -m benchmarks.merge <byte-run> <token-run> --into <byte-run>
```

Because the tokenizer is part of the key, merging is concatenation with a
deduplicating key and **a byte figure can never land in a token column**. The
merged manifest keeps every source run's provenance instead of inventing a
combined one: two runs on two machines are two measurements, and a single
`platform` field would be a lie about at least one of them.

The token half comes from `.github/workflows/benchmark.yml`, manual dispatch
only. Until someone dispatches it, the committed results are bytes.

## Rules the harness enforces rather than documents

- **The matrix is not curated.** For each corpus item the registry is asked
  which installed backends claim its format, and every one of them runs.
  Choosing the list by hand is how a benchmark quietly stops including the
  backend that does badly.
- **`check_report()` refuses to render a token column with no fidelity column
  beside it.** It raises rather than writing the file.
- **Nothing is parallelised during a run.** A wall-clock measurement taken while
  three other conversions compete for four cores measures the scheduler.
- **Rows are in registry preference order, never sorted by size.** On
  `tables.pdf` the smallest output is the one that dropped the table; a
  leaderboard would rank the destruction.
- **`None` is not zero.** A fidelity component with no ground truth for that
  fixture is excluded from the mean, and the report prints how many components
  were scored beside every score.

## Results

| Run | Unit | Cells | Notes |
|---|---|---|---|
| [`2026-08-27`](results/2026-08-27/) | `bytes` | 63 (8 failed, 4 empty) | The first full set. Commit `09c1d2e`, corpus `cd2d48ccf99bddb4`. No GPU, so no OCR backend took part. |

`docs/BENCHMARKS.md` reads this data, and its
[Limitations](../docs/BENCHMARKS.md#limitations-read-before-quoting-any-of-this)
section is not optional reading.
