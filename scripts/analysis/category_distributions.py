"""Chart and characterise the nine scoring categories the board standardises on.

Writes nine histograms and a normality report into one dated folder under
`data/exports/`, from one pool, in one invocation. Splitting the charts from the
report would converge the pool twice and let a caption disagree with the table
printed beside it.

Two things this deliberately does not do. It does not plot FG% and FT% as rates:
the board values them volume-weighted, and a bare rate counts a 3-shot night like
an 18-shot one (AGENTS.md). And it does not describe all 200 rows in the export:
the z-scores are computed over the rostered pool, so the pool is the population
whose shape decides whether z-scoring is sound.

Output is regenerable and lands in gitignored `data/`. The committed companion is
`docs/reviews/2026-08-30-category-distribution-normality.md`, which carries the
argument and no raw player figures (ADR-0006).

    python3 scripts/analysis/category_distributions.py
    python3 scripts/analysis/category_distributions.py --no-converge
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import StrMethodFormatter  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from category_series import (  # noqa: E402
    DEFAULT_EXPORT,
    DEFAULT_MIN_GP,
    DEFAULT_Q,
    LOWER_IS_BETTER,
    QUANTUM,
    REPO_ROOT,
    label,
    load_pool,
    series,
)
from normality import Normality, analyse  # noqa: E402
from report import render  # noqa: E402
from valuation import CATEGORIES  # noqa: E402

# Slot 1 of the reference categorical palette, on the light chart surface.
SERIES = "#2a78d6"
NORMAL_LINE = "#e34948"
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#8a8880"
GRID = "#e3e2dd"

# Filename slug, axis label, axis tick format, summary-stat format. Ticks stay
# coarse so the axis reads cleanly; the mean/median line carries the extra digit,
# because 48.9% and 47.4% would round to the same tick label.
CHARTS = {
    "fg": ("fg-impact", "FG% impact (volume-weighted)", "{x:+.2f}", "{x:+.3f}"),
    "ft": ("ft-impact", "FT% impact (volume-weighted)", "{x:+.2f}", "{x:+.3f}"),
    "tpm": ("3pm", "Three-pointers made per game", "{x:.1f}", "{x:.2f}"),
    "pts": ("pts", "Points per game", "{x:.0f}", "{x:.1f}"),
    "reb": ("reb", "Rebounds per game", "{x:.0f}", "{x:.1f}"),
    "ast": ("ast", "Assists per game", "{x:.0f}", "{x:.1f}"),
    "stl": ("stl", "Steals per game", "{x:.1f}", "{x:.2f}"),
    "blk": ("blk", "Blocks per game", "{x:.1f}", "{x:.2f}"),
    "to": ("to", "Turnovers per game", "{x:.1f}", "{x:.2f}"),
}

# Charts written by an earlier version of this script, from bare rates over all
# 200 rows. The output folder is gitignored, so nothing else would ever catch
# them, and a reader opening the folder would find both stories side by side.
SUPERSEDED = ("fg-pct.png", "ft-pct.png")

# Below this many distinct values, snapping bin edges to whole quanta draws more
# bars than the column has values and the histogram grows teeth that look like
# structure. 3PM has 39 distinct values across the pool; binned at two quanta it
# reads as bimodal and is not.
MIN_DISTINCT_FOR_QUANTUM_FLOOR = 45


def bin_edges(values: np.ndarray, quantum: float | None) -> np.ndarray:
    """Freedman-Diaconis edges, snapped to the source grid when there is one.

    On a quantised column the bin width is rounded to a whole number of quanta and
    the edges are offset by half a quantum, so every bin holds the same number of
    reportable values and each reported value sits in exactly one bin. Without
    that, a 0.117-wide bin over 0.1-grid data alternates between catching one
    value and two, and the histogram grows teeth.

    The two-quantum floor exists because at one quantum every bar is a single
    reported value, which plots the provider's rounding rather than the pool. It
    is lifted for low-cardinality columns, where it causes the very artifact the
    snapping is meant to remove.
    """
    edges = np.histogram_bin_edges(values, bins="fd")
    if len(edges) - 1 > 30:  # keep the shape readable at n~156
        edges = np.histogram_bin_edges(values, bins=20)
    if quantum is None:
        return edges

    distinct = len(np.unique(np.round(values, 9)))
    floor = 2 if distinct >= MIN_DISTINCT_FOR_QUANTUM_FLOOR else 1
    width = max(floor, round((edges[1] - edges[0]) / quantum)) * quantum
    lo = values.min() - quantum / 2
    count = int(np.ceil((values.max() + quantum / 2 - lo) / width))
    return lo + width * np.arange(count + 1)


def plot_category(values: np.ndarray, stats: Normality, key: str, out_path: Path, source: str):
    slug, axis_label, tick_fmt, stat_fmt = CHARTS[key]
    fig, ax = plt.subplots(figsize=(7.2, 4.5), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    bins = bin_edges(values, QUANTUM[key])
    counts, _, _ = ax.hist(
        values, bins=list(bins), color=SERIES, edgecolor=SURFACE, linewidth=1.6, zorder=3
    )

    # The Normal the z-score assumes, drawn to the same area as the bars. Where it
    # misses, the z is mispricing that part of the pool.
    grid = np.linspace(bins[0], bins[-1], 400)
    density = np.exp(-0.5 * ((grid - stats.mean) / stats.sd) ** 2) / (
        stats.sd * np.sqrt(2 * np.pi)
    )
    ax.plot(
        grid, density * len(values) * (bins[1] - bins[0]),
        color=NORMAL_LINE, linewidth=1.8, zorder=5,
        label="Normal the z-score assumes",
    )
    ax.set_ylim(0, max(float(np.max(counts)), float(density.max() * len(values) * (
        bins[1] - bins[0]))) * 1.22)

    ax.axvline(stats.median, color=TEXT_SECONDARY, linewidth=1.5, linestyle=(0, (4, 3)), zorder=4)
    ax.annotate(
        f"median {stat_fmt.format(x=stats.median)}",
        xy=(stats.median, 1.0), xycoords=("data", "axes fraction"),
        xytext=(6, -10), textcoords="offset points",
        color=TEXT_SECONDARY, fontsize=9, ha="left", va="top",
    )

    direction = "lower is better" if key in LOWER_IS_BETTER else "higher is better"
    ax.set_title(
        f"{label(key)} — tier {stats.tier}",
        color=TEXT_PRIMARY, fontsize=15, fontweight="bold", loc="left", pad=26,
    )
    ax.annotate(
        f"{stats.n} in pool  ·  skew {stats.skew:+.2f}  ·  excess kurtosis "
        f"{stats.kurt:+.2f}  ·  {direction}",
        xy=(0, 1.0), xycoords="axes fraction", xytext=(0, 10), textcoords="offset points",
        color=TEXT_SECONDARY, fontsize=10, ha="left", va="bottom",
    )

    ax.set_xlabel(axis_label, color=TEXT_SECONDARY, fontsize=10, labelpad=8)
    ax.set_ylabel("Players", color=TEXT_SECONDARY, fontsize=10, labelpad=8)
    ax.xaxis.set_major_formatter(StrMethodFormatter(tick_fmt))
    # Sit the legend over the empty corner: a right-skewed column piles its bars
    # on the left, a left-skewed one on the right. Otherwise it lands on the
    # median label, which is what FT% impact did.
    ax.legend(
        loc="upper left" if stats.skew < 0 else "upper right", frameon=False, fontsize=9,
        labelcolor=TEXT_SECONDARY, handlelength=1.6,
    )

    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9, length=0)

    fig.text(0.015, 0.015, source, color=TEXT_MUTED, fontsize=8, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, facecolor=SURFACE)
    plt.close(fig)
    return slug


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", nargs="?", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--outdir", type=Path, default=None)
    parser.add_argument("-q", "--pool-size", type=int, default=DEFAULT_Q)
    parser.add_argument("--min-gp", type=float, default=DEFAULT_MIN_GP)
    parser.add_argument(
        "--no-converge", action="store_true",
        help="single-pass pool, as the live sheet currently holds it",
    )
    args = parser.parse_args()

    if not args.export.exists():
        raise SystemExit(f"export not found: {args.export}")

    stamp = args.export.stem.replace("player_data_", "")
    outdir = args.outdir or REPO_ROOT / "data" / "exports" / f"category_distributions_{stamp}"
    outdir.mkdir(parents=True, exist_ok=True)

    result = load_pool(args.export, args.pool_size, args.min_gp, converge=not args.no_converge)
    values = series(result.pool)
    stats = {k: analyse(k, values[k], QUANTUM[k]) for k in CATEGORIES}

    # The same battery over the pool the live sheet actually holds, so the report
    # can say whether the verdicts depend on a re-seed that has never been run.
    other = load_pool(args.export, args.pool_size, args.min_gp, converge=args.no_converge)
    other_values = series(other.pool)
    other_stats = {k: analyse(k, other_values[k], QUANTUM[k]) for k in CATEGORIES}

    how = "converged" if result.converged else "single-pass"
    source = f"Source: {args.export.name} — pool of {result.n}, {how}"
    for key in CATEGORIES:
        slug = plot_category(values[key], stats[key], key, outdir / f"{CHARTS[key][0]}.png", source)
        s = stats[key]
        print(f"  {label(key):<12} tier {s.tier}  skew {s.skew:+6.2f}  -> {slug}.png")

    for stale in SUPERSEDED:
        if (outdir / stale).exists():
            (outdir / stale).unlink()
            print(f"  removed superseded {stale}")

    report_path = outdir / "normality-report.md"
    report_path.write_text(
        render(result, values, stats, other, other_stats, args.export.name),
        encoding="utf-8",
    )
    print(f"\n{len(CATEGORIES)} charts + normality-report.md in {outdir.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
