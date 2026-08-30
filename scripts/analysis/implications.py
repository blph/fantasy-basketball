"""What the shape of a category actually costs the board.

A normality verdict on its own is inert -- everybody already expects basketball
counting stats to skew. These three measurements turn it into something to act on
or dismiss:

  `team_total_moments`  categories are won on 13-man team totals, not on one
                        player, and summing flattens skew. This is the evidence
                        ADR-0014 rests on and asserts without deriving.
  `band_yield`          how many players the +/-1.00 Category band actually names,
                        against the 15.9% a Normal promises. Where those disagree
                        is where the board is mis-calibrated today.
  `rank_int_movement`   what forcing every category Gaussian would cost, in
                        places moved on the board -- the units a decision gets
                        made in.

`board_ranking` is built so that passing no transform reproduces `valuation.py`'s
own ordering exactly. The counterfactual is only worth reading if the baseline it
is measured against is the real board, so `main` asserts that before using it.

Pure functions. No I/O.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "draft-board"))

from valuation import (  # noqa: E402
    CATEGORIES,
    COUNTING,
    MULTIPLIERS,
    Player,
    Pool,
    adjusted_value,
    fg_impact,
    ft_impact,
    z_scores,
)

DEFAULT_GP_DIVISOR = 72.0
ROSTER_SIZE = 13
SIMULATION_DRAWS = 20_000

# Fixed so the report's numbers are reproducible. `basketball-monster-durant.md`
# quotes simulation figures that cannot be re-obtained because no seed was
# recorded; that is the failure this constant exists to avoid.
SIMULATION_SEED = 20260830

# Share of a Normal below -1 SD and above +1 SD. What the +/-1.00 band promises.
NORMAL_TAIL = 0.158655


def board_ranking(
    players: list[Player],
    pool: Pool,
    q: int,
    gp_divisor: float = DEFAULT_GP_DIVISOR,
    z_table: dict[str, dict[str, float]] | None = None,
) -> list[str]:
    """Player names in the board's Adjusted Value order.

    `z_table` maps player name -> per-category z, replacing `valuation.z_scores`.
    Passing None reproduces the board exactly, which is what makes a counterfactual
    measurable against it.
    """
    def g_total(p: Player) -> float:
        z = z_table[p.name] if z_table is not None else z_scores(p, pool)
        return sum(z[c] * MULTIPLIERS[c] for c in CATEGORIES)

    totals = {p.name: g_total(p) for p in players}
    repl = sorted(totals.values(), reverse=True)[q - 1]
    ranked = sorted(
        players, key=lambda p: -adjusted_value(totals[p.name] - repl, p.gp, gp_divisor)
    )
    return [p.name for p in ranked]


def blom_normal_scores(values: np.ndarray) -> np.ndarray:
    """Rank-based inverse normal transform. Ties share their average rank.

    Blom's offset (3/8) is the conventional choice for a Normal fit. The result is
    Gaussian by construction, which is exactly the objection to it: every category
    comes out with the same shape, so the gap between the best blocker and the
    second best becomes the gap between the top two order statistics of a standard
    Normal, whatever the underlying block totals were.
    """
    n = len(values)
    ranks = stats.rankdata(values, method="average")
    return stats.norm.ppf((ranks - 3.0 / 8.0) / (n + 1.0 / 4.0))


def rank_int_z_table(players: list[Player], pool: Pool) -> dict[str, dict[str, float]]:
    """Per-category z with every category forced Gaussian, over all ranked players."""
    columns = {
        "fg": np.array([fg_impact(p, pool) for p in players]),
        "ft": np.array([ft_impact(p, pool) for p in players]),
    }
    for c in COUNTING:
        raw = np.array([getattr(p, c) for p in players], dtype=float)
        columns[c] = -raw if c == "to" else raw  # turnovers count against

    scored = {c: blom_normal_scores(v) for c, v in columns.items()}
    return {p.name: {c: float(scored[c][i]) for c in CATEGORIES} for i, p in enumerate(players)}


def rank_movement(before: list[str], after: list[str]) -> dict[str, float]:
    """How far the board moves between two orderings, in places."""
    pos_before = {n: i for i, n in enumerate(before)}
    moves = np.array([abs(pos_before[n] - i) for i, n in enumerate(after)], dtype=float)
    rho = float(stats.spearmanr(
        [pos_before[n] for n in after], list(range(len(after)))
    ).statistic)
    return {
        "spearman": rho,
        "mean_places": float(moves.mean()),
        "max_places": float(moves.max()),
        "moved_10_plus": int(np.count_nonzero(moves >= 10)),
        "moved_10_plus_in_top_50": int(
            np.count_nonzero([abs(pos_before[n] - i) >= 10 for i, n in enumerate(after[:50])])
        ),
    }


def crossings(before: list[str], after: list[str], q: int) -> int:
    """How many players cross the drafted/undrafted line between two orderings."""
    return len(set(before[:q]) ^ set(after[:q])) // 2


def team_total_moments(
    values: dict[str, np.ndarray],
    roster: int = ROSTER_SIZE,
    draws: int = SIMULATION_DRAWS,
    seed: int = SIMULATION_SEED,
) -> dict[str, dict[str, float]]:
    """Skew and excess kurtosis of a random 13-man roster's category totals.

    Categories are settled on the sum of a roster, not on one player, and summing
    independent draws pulls the total toward Normal however skewed the parts are.
    Whether that flattening is enough is the whole question ADR-0014 turns on, and
    it was never computed -- only argued.

    Drawn without replacement, because a roster cannot hold the same player twice,
    and that is mildly conservative: it induces slight negative dependence, so the
    real flattening is at least this good.

    The two impact columns are summed as if roster-additive, which they are not
    exactly -- a team's FG% is its own attempt-weighted aggregate. The caveat is in
    `basketball-monster-durant.md`; the direction of the result is unaffected.
    """
    rng = np.random.default_rng(seed)
    n = len(next(iter(values.values())))
    idx = np.array([rng.choice(n, size=roster, replace=False) for _ in range(draws)])

    out = {}
    for c, v in values.items():
        totals = v[idx].sum(axis=1)
        out[c] = {
            "player_skew": float(stats.skew(v, bias=False)),
            "player_kurt": float(stats.kurtosis(v, bias=False)),
            "team_skew": float(stats.skew(totals, bias=False)),
            "team_kurt": float(stats.kurtosis(totals, bias=False)),
        }
    return out


def band_yield(pool: Pool, band: float = 1.00) -> dict[str, dict[str, float]]:
    """How many pool players the Category band actually names, strong and weak.

    ADR-0013 calibrated the band on the strong side and recorded the weak side on
    blocks as a known limitation. This measures both, so "known limitation" gets a
    number: where `weak_share` falls far below the Normal's 15.9%, the band is
    promising a population that does not exist.
    """
    zs = [z_scores(p, pool) for p in pool.members]
    n = len(zs)
    out = {}
    for c in CATEGORIES:
        col = np.array([z[c] for z in zs])
        strong = int(np.count_nonzero(col >= band))
        weak = int(np.count_nonzero(col <= -band))
        out[c] = {
            "strong": strong, "weak": weak,
            "strong_share": strong / n, "weak_share": weak / n,
        }
    return out
