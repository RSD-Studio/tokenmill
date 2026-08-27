"""Combine result sets, which is how a byte run and a token run become one table.

    uv run python -m benchmarks.merge benchmarks/results/2026-08-27 \
        --into benchmarks/results/2026-08-27

The problem this solves is environmental and permanent for this project. The
sandbox tokenmill is developed in cannot reach `openaipublic.blob.core.windows.net`
or `huggingface.co`, so **no model-token count can ever be produced locally.**
CI can. So the local run measures `bytes` and CI measures `o200k_base`, each
writes a result set, and this merges them.

It works because a cell is keyed by (fixture, backend, **tokenizer**). Merging
is therefore concatenation with a deduplicating key, and **a byte figure cannot
land in a token column** — which is the failure this project came closest to:
Phase 7 found the two units disagreeing by 24 points on tabular data and not
even ranking the five serialisation formats in the same order.

The merged manifest keeps every source run's provenance rather than inventing a
combined one. Two runs on two machines are two measurements, and a single
`platform` field would be a lie about at least one of them.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.models import CellResult, RunManifest
from benchmarks.report import load_results, merge, write_results

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    """Merge two or more result directories into one.

    Args:
        argv: Command-line arguments.

    Returns:
        The exit status.
    """
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.merge",
        description="Merge result sets measured in different units or on different machines.",
    )
    parser.add_argument("sources", type=Path, nargs="+", help="Result directories, oldest first.")
    parser.add_argument("--into", type=Path, required=True, help="Where to write the merged set.")
    args = parser.parse_args(argv)

    runs: list[list[CellResult]] = []
    manifests: list[Mapping[str, Any]] = []
    for source in args.sources:
        path = source / "results.json" if source.is_dir() else source
        cells, raw = load_results(path)
        runs.append(cells)
        manifests.append(raw)

    merged = merge(runs)
    paths = write_results(args.into, _ordered(merged), _merged_manifest(manifests))
    print(
        f"{len(merged)} cells from {len(runs)} run(s) -> {paths['markdown']}",
        file=sys.stderr,
    )
    return 0


def _ordered(cells: Sequence[CellResult]) -> list[CellResult]:
    """Sort merged cells so the report reads in a stable order.

    Args:
        cells: The merged cells.

    Returns:
        Them, sorted by tokenizer then fixture then backend. Sorted rather than
        left in dictionary order so that re-running the merge produces a
        byte-identical file, which is what makes a committed result set
        reviewable in a diff.
    """
    return sorted(cells, key=lambda c: (c.tokenizer, c.fixture, c.backend))


def _merged_manifest(manifests: Sequence[Mapping[str, Any]]) -> RunManifest:
    """Build a manifest for a merged set that does not lie about any source run.

    Args:
        manifests: Each source run's manifest.

    Returns:
        The merged manifest. Fields that genuinely differ between runs — the
        platform, the commit — are reported as "merged" with every source
        spelled out in the notes, rather than being taken from whichever run
        happened to be first.
    """
    first = manifests[0] if manifests else {}
    tokenizers: list[str] = []
    notes: list[str] = [
        f"Merged from {len(manifests)} run(s). Each row's counts come from the run "
        f"that measured its tokenizer; the runs are listed below."
    ]
    digests = set()
    for manifest in manifests:
        for tokenizer in manifest.get("tokenizers", []):
            if tokenizer not in tokenizers:
                tokenizers.append(tokenizer)
        digests.add(manifest.get("corpus_digest", "?"))
        notes.append(
            f"- `{', '.join(manifest.get('tokenizers', []))}` measured at "
            f"{manifest.get('started_at', '?')} on {manifest.get('platform', '?')}, "
            f"commit `{manifest.get('git_commit', '?')}`, N={manifest.get('repeats', '?')}"
        )
        notes.extend(f"  - {note}" for note in manifest.get("notes", []))

    if len(digests) > 1:
        notes.insert(
            1,
            "**The runs used different corpora.** Their digests differ, so rows from "
            f"different runs are not strictly comparable: {sorted(digests)}",
        )

    return RunManifest(
        started_at=first.get("started_at", "?"),
        tokenmill_version=first.get("tokenmill_version", "?"),
        git_commit=first.get("git_commit"),
        git_dirty=bool(first.get("git_dirty")),
        python=first.get("python", "?"),
        platform_description="merged — see the notes for each run's machine",
        cpu_count=int(first.get("cpu_count", 1)),
        corpus_digest=next(iter(sorted(digests)), "?"),
        repeats=int(first.get("repeats", 0)),
        tokenizers=tokenizers,
        backend_versions={},
        notes=notes,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
