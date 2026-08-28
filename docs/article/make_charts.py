"""Draw the article's charts from the committed benchmark results.

    uv run --with matplotlib python docs/article/make_charts.py

**matplotlib is deliberately not a dependency of this project.** The core
install is capped at 250 MB and guarded by CI, and a plotting library that only
an article needs has no business in it. `uv run --with matplotlib` puts it in a
throwaway environment for the length of the command; nothing is added to
`pyproject.toml`.

Three charts, each drawing exactly one claim from `FINDINGS.md`:

* ``cost-vs-fidelity.png`` — one panel per fixture, output size against
  fidelity for every backend given that identical file. The slope of each panel
  is the finding: documents slope up and web pages slope down (finding 1).
* ``the-empty-win.png`` — reduction against fidelity, with the largest saving
  in the corpus sitting at zero fidelity (finding 2).
* ``twocolumn.png`` — five backends within 0.47% on size and 0.44 apart on
  fidelity (finding 4).

Nothing here invents a number: every value is read out of `results.json`, and
the subtitle of each chart names the run it came from, so a chart separated from
this repository still says what it is.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

__all__ = ["main"]

#: The run these charts describe.
DEFAULT_RUN: Final = Path(__file__).resolve().parents[2] / "benchmarks" / "results" / "2026-08-27"

#: Where the images go.
DEFAULT_OUT: Final = Path(__file__).resolve().parent / "charts"


def _load(run: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read a result set.

    Args:
        run: The results directory.

    Returns:
        Its cells and its manifest.
    """
    payload = json.loads((run / "results.json").read_text(encoding="utf-8"))
    return payload["results"], payload["manifest"]


def _provenance(manifest: dict[str, Any]) -> str:
    """One line saying what a chart is a picture of.

    A chart travels away from its repository, so it has to carry this.

    Args:
        manifest: The run's provenance.

    Returns:
        The caption.
    """
    return (
        f"tokenmill {manifest['tokenmill_version']} · commit {manifest['git_commit'][:7]} · "
        f"corpus {manifest['corpus_digest']} · counts in UTF-8 bytes, NOT model tokens"
    )


def _cost_vs_fidelity(rows: Sequence[dict[str, Any]], manifest: dict[str, Any], out: Path) -> Path:
    """Draw finding 1: two regimes pointing in opposite directions.

    **One panel per fixture, deliberately.** The first version of this chart put
    every scored cell on one pair of axes, and it was quietly misleading: a
    2,854-byte web page and a 481-byte table are not comparable sizes, so
    pooling them produced a cloud whose shape came from the fixtures rather than
    from the backends. The comparison that means anything is *within* a file,
    where every backend was handed the identical input — so each panel is one
    file, and the slope of each panel is the finding.

    Args:
        rows: Every cell.
        manifest: The run's provenance.
        out: Directory to write into.

    Returns:
        The path written.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels: list[tuple[str, str, list[dict[str, Any]]]] = []
    for fixture, kind in (
        ("tables.pdf", "document"),
        ("twocolumn.pdf", "document"),
        ("report.docx", "document"),
        ("article.html", "web page"),
        ("boilerplate.html", "web page"),
        ("jsrendered.html", "web page"),
    ):
        cells = [
            r for r in rows if r["fixture"] == fixture and r["ok"] and r["fidelity"] is not None
        ]
        if len(cells) >= 3:
            panels.append((fixture, kind, sorted(cells, key=lambda r: r["tokens_after"])))

    figure, axes_grid = plt.subplots(2, 3, figsize=(13, 7.5))
    for axes, (fixture, kind, cells) in zip(axes_grid.flat, panels, strict=False):
        colour = "#d62728" if kind == "web page" else "#1f77b4"
        sizes = [r["tokens_after"] for r in cells]
        scores = [r["fidelity"] for r in cells]
        axes.plot(sizes, scores, marker="o", color=colour, linewidth=1.4, markersize=8)
        # Labels alternate above and below the line. Several panels have four
        # backends inside a 20-byte span, where every label on the same side
        # renders as one illegible smear.
        for index, row in enumerate(cells):
            above = index % 2 == 0
            axes.annotate(
                row["backend"],
                xy=(row["tokens_after"], row["fidelity"]),
                xytext=(0, 9 if above else -16),
                textcoords="offset points",
                fontsize=7,
                ha="center",
                va="bottom" if above else "top",
            )

        # Three outcomes, not two. The first version of this chart labelled
        # every non-rising panel "the cheap one is better", which is a claim it
        # was making about `article.html` and `jsrendered.html` — where every
        # backend scores identically and neither is better than the other. A
        # flat panel is a real and different result and now says so.
        spread = max(scores) - min(scores)
        if spread < 0.01:
            direction = "→ every backend scores the same"
            title_colour = "#555555"
        elif scores[-1] > scores[0]:
            direction = "↗ pay more, get more"
            title_colour = colour
        else:
            direction = "↘ the cheap one is better"
            title_colour = colour
        axes.set_title(f"{fixture}\n{direction}", fontsize=10, color=title_colour)
        axes.set_ylim(-0.22, 1.25)
        # Room for a label on the leftmost and rightmost points, which sit on
        # the panel edge and were being clipped in half.
        axes.margins(x=0.18)
        axes.grid(alpha=0.25, linewidth=0.5)
        axes.tick_params(labelsize=8)
        axes.set_xlabel("output bytes", fontsize=8)
        axes.set_ylabel("fidelity", fontsize=8)

    figure.suptitle(
        "Same file, every backend that claims it: "
        "cheaper is not worse, and it is not better either",
        fontsize=12,
    )
    figure.text(0.5, 0.012, _provenance(manifest), ha="center", fontsize=7, color="#555555")
    figure.tight_layout(rect=(0, 0.03, 1, 0.95))

    path = out / "cost-vs-fidelity.png"
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


def _the_empty_win(rows: Sequence[dict[str, Any]], manifest: dict[str, Any], out: Path) -> Path:
    """Draw finding 2: the biggest saving in the corpus is worth nothing.

    Args:
        rows: Every cell.
        manifest: The run's provenance.
        out: Directory to write into.

    Returns:
        The path written.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scored = [
        r for r in rows if r["ok"] and r["fidelity"] is not None and r.get("reduction") is not None
    ]
    scored.sort(key=lambda r: r["reduction"], reverse=True)

    figure, axes = plt.subplots(figsize=(9, max(4.0, 0.34 * len(scored))))
    labels = [f"{r['fixture']} · {r['backend']}" for r in scored]
    savings = [r["reduction"] * 100 for r in scored]
    colours = ["#d62728" if r["fidelity"] < 0.2 else "#1f77b4" for r in scored]

    positions = range(len(scored))
    axes.barh(list(positions), savings, color=colours)
    axes.set_yticks(list(positions))
    axes.set_yticklabels(labels, fontsize=8)
    axes.invert_yaxis()
    axes.set_xlabel("reduction (%) — bigger is 'better', which is the problem")
    axes.set_title("The largest saving in the corpus extracted nothing")

    for index, row in enumerate(scored):
        axes.text(
            row["reduction"] * 100 + 0.8,
            index,
            f"fidelity {row['fidelity']:.3f}",
            va="center",
            fontsize=7,
            color="#d62728" if row["fidelity"] < 0.2 else "#333333",
        )

    # `structured.md` through pandoc GROWS by 9.5%, so the axis has to reach
    # left of zero. Clipping it at zero would have hidden the one cell in the
    # corpus where conversion costs more than it saves.
    axes.set_xlim(min(0.0, min(savings) * 1.6), max(savings) * 1.30)
    axes.axvline(0, color="#333333", linewidth=0.8)
    axes.grid(axis="x", alpha=0.25, linewidth=0.5)

    # The four `scanned.pdf` cells that succeed with an empty string belong on
    # this chart and cannot be on it: a PDF has no comparable before-count, so
    # they have no reduction to plot. Saying so is better than a reader
    # concluding the chart is the whole story.
    figure.text(
        0.5,
        0.028,
        "Not shown: four scanned.pdf cells also succeeded with an empty string. "
        "A PDF has no before-count, so they have no reduction to plot.",
        ha="center",
        fontsize=7,
        color="#333333",
    )
    figure.text(0.5, 0.008, _provenance(manifest), ha="center", fontsize=7, color="#555555")
    figure.tight_layout(rect=(0, 0.045, 1, 1))

    path = out / "the-empty-win.png"
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


def _twocolumn(rows: Sequence[dict[str, Any]], manifest: dict[str, Any], out: Path) -> Path:
    """Draw finding 4: a five-way tie on cost that is nothing of the sort.

    Args:
        rows: Every cell.
        manifest: The run's provenance.
        out: Directory to write into.

    Returns:
        The path written.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cells = sorted(
        (r for r in rows if r["fixture"] == "twocolumn.pdf" and r["ok"]),
        key=lambda r: r["fidelity"] or 0,
    )
    names = [r["backend"] for r in cells]
    sizes = [r["tokens_after"] for r in cells]
    scores = [r["fidelity"] for r in cells]

    figure, (left, right) = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
    positions = range(len(cells))

    left.barh(list(positions), sizes, color="#7f7f7f")
    left.set_yticks(list(positions))
    left.set_yticklabels(names)
    left.invert_yaxis()
    # The point of the chart is that this axis is almost flat, which only shows
    # if it does not start at zero. Stated on the axis so it cannot mislead.
    left.set_xlim(min(sizes) - 30, max(sizes) + 30)
    left.set_xlabel("output size (bytes) — note the truncated axis")
    left.set_title(f"a {(max(sizes) / min(sizes) - 1) * 100:.2f}% spread")

    right.barh(list(positions), scores, color="#1f77b4")
    right.set_xlim(0, 1.05)
    right.set_xlabel("fidelity")
    right.set_title(f"a {max(scores) - min(scores):.3f} spread")
    for index, score in enumerate(scores):
        right.text(score + 0.02, index, f"{score:.3f}", va="center", fontsize=9)

    figure.suptitle("twocolumn.pdf: the same file, five backends, one useful column")
    figure.text(0.5, 0.012, _provenance(manifest), ha="center", fontsize=7, color="#555555")
    figure.tight_layout(rect=(0, 0.04, 1, 0.96))

    path = out / "twocolumn.png"
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """Draw every chart.

    Args:
        argv: Command-line arguments.

    Returns:
        The exit status, or 2 when matplotlib is not installed — with the
        command that would fix it, rather than a traceback.
    """
    parser = argparse.ArgumentParser(description="Draw the article's charts.")
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print(
            "matplotlib is not installed, and it is deliberately not a dependency "
            "of this project.\nRun:  uv run --with matplotlib python "
            "docs/article/make_charts.py"
        )
        return 2

    rows, manifest = _load(args.run)
    args.out.mkdir(parents=True, exist_ok=True)
    for draw in (_cost_vs_fidelity, _the_empty_win, _twocolumn):
        print(f"wrote {draw(rows, manifest, args.out)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
