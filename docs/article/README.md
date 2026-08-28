# Article support pack

Everything an article about tokenmill needs, in a form that cannot quietly drift
away from the measurements it describes.

| File | What it is |
|---|---|
| [`CLAIMS.md`](CLAIMS.md) | **Read this first.** Every claim an article could make, each labelled *Measured*, *Cited* or *Unverified*, with its source or its absence. |
| [`FINDINGS.md`](FINDINGS.md) | The five things in the data we did not expect, in descending order of how much they change what you would do. |
| [`TABLES.md`](TABLES.md) | Five tables, ready to paste. **Generated** — do not edit. |
| [`charts/`](charts/) | Three PNGs, one per finding. **Generated** — do not edit. |
| `make_tables.py`, `make_charts.py` | The generators. |

## Regenerating

```bash
uv run python docs/article/make_tables.py
uv run --with matplotlib python docs/article/make_charts.py
```

Both read `benchmarks/results/2026-08-27/results.json` and nothing else. Point
them at a newer run with `--run`.

**matplotlib is deliberately not a dependency of this project.** The core
install is capped at 250 MB and guarded by CI; a plotting library that only an
article needs has no business in it. `uv run --with matplotlib` puts it in a
throwaway environment for the length of one command.

## Why the tables and charts are generated

Retyping a number into prose is how a benchmark becomes marketing. This project
has already caught two smaller versions of it — a byte count published under a
heading that said bytes when it was a character count, and a `compare` example
in the README naming the wrong backend as most faithful for two whole phases —
and both survived review because a human had transcribed them once and nobody
re-derived them afterwards.

So: a table in this directory is a function of `results.json`, and running the
generator is the check. A test asserts the committed `TABLES.md` matches what
the generator produces from the committed data, so the two cannot drift apart
without CI noticing.

## The one rule for using any of this

**Every number in this pack is UTF-8 bytes, not model tokens**, unless it says
`o200k_base` — and only four figures in the whole project do, all of them read
out of a CI log. The environment tokenmill was built in cannot reach a tokenizer
vocabulary at all.

A byte figure is a lower bound on cost, an upper bound on saving, and **not a
reliable ordering**: on this project's own tabular data the two units disagreed
by 24 points and did not rank five serialisation formats in the same order.
Quoting a byte figure as a token saving says something we did not measure.

[`CLAIMS.md` §3](CLAIMS.md#3-claims-that-must-be-labelled-unverified) is the
full list of what has never been executed. It is longer than you would like and
that is the point of writing it down.
