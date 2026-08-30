"""The nine valued category series, over the pool the board standardises against.

Two things this module exists to get right.

First, FG% and FT% are **not** the rates in the export. The board values them
volume-weighted -- `(FGA / pool average FGA) x (FG% - pool FG%)` -- because a bare
rate counts a 3-shot night the same as an 18-shot one, which AGENTS.md forbids.
The impact functions are imported from `valuation.py` rather than restated, so
this file cannot drift from the sheet.

Second, the population is the **converged rostered pool**, not the 200-row export.
The z-scores are computed over that pool, so it is the pool whose shape decides
whether z-scoring is sound. The 44 rows outside it are players nobody drafts.

Reads one file. Otherwise pure.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "draft-board"))

from gen_data import COLS, load  # noqa: E402
from valuation import (  # noqa: E402
    CATEGORY_LABELS,
    COUNTING,
    Player,
    Pool,
    build_pool,
    converge_pool,
    fg_impact,
    ft_impact,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPORT = REPO_ROOT / "data" / "player_data" / "player_data_0826.md"

# Mirrors the Settings tab; Q comes from config/league.yaml (12 teams x 13 spots).
# MIN_GP is ADR-0011.
DEFAULT_Q = 156
DEFAULT_MIN_GP = 25

# The provider reports the counting stats rounded to 0.1. The two impacts are
# constructions and carry no reporting grid, hence None. Charts bin on this and
# `normality.floor_mass` measures against it.
QUANTUM = {
    "fg": None, "ft": None,
    "tpm": 0.1, "pts": 0.1, "reb": 0.1, "ast": 0.1, "stl": 0.1, "blk": 0.1, "to": 0.1,
}

# Turnovers count against us. The raw column skews positive; as valued it inverts.
LOWER_IS_BETTER = {"to"}


@dataclass(frozen=True)
class PoolResult:
    """A settled pool, plus what the report has to state about how it was built."""

    pool: Pool
    players: list[Player]
    passes: int
    q: int
    min_gp: float
    converged: bool

    @property
    def n(self) -> int:
        return len(self.pool.members)

    @property
    def shortfall(self) -> int:
        """Q minus actual membership. MIN_GP can leave the pool short of Q."""
        return self.q - self.n

    @property
    def fg_residual(self) -> float:
        """Sum of the FG impact column, which the aggregate-rate identity puts at 0.

        It is not exactly 0 because the provider rounds its rates to three decimals
        independently of makes and attempts. `tests/test_valuation.py` pins that
        residual; printing it here keeps the report agreeing with the sheet's own
        "should be ~0" sanity cell instead of asserting a cleaner number.
        """
        return float(sum(fg_impact(p, self.pool) for p in self.pool.members))

    @property
    def ft_residual(self) -> float:
        return float(sum(ft_impact(p, self.pool) for p in self.pool.members))


def load_players(path=DEFAULT_EXPORT) -> list[Player]:
    """Parse the export through the board's own reader, guards included."""
    rows = load(path)
    out = []
    for row in rows:
        d = dict(zip(COLS, row, strict=True))
        out.append(Player(
            seed=int(d["seed"]), name=d["name"], gp=float(d["gp"]),
            **{k: float(d[k]) for k in
               ("fgm", "fga", "fgp", "ftm", "fta", "ftp",
                "tpm", "pts", "reb", "ast", "stl", "blk", "to")},
        ))
    return out


def load_pool(
    path=DEFAULT_EXPORT,
    q: int = DEFAULT_Q,
    min_gp: float = DEFAULT_MIN_GP,
    converge: bool = True,
) -> PoolResult:
    """The pool the board standardises against.

    `converge=False` gives the single-pass pool. The two are different
    156-player sets, and the live sheet has never had its re-seed action run, so
    the report measures both and says whether the verdicts differ.
    """
    players = load_players(path)
    if converge:
        pool, passes = converge_pool(players, q, min_gp)
    else:
        pool, passes = build_pool(players, q, min_gp), 1
    return PoolResult(
        pool=pool, players=players, passes=passes, q=q, min_gp=min_gp, converged=converge
    )


def series(pool: Pool) -> dict[str, np.ndarray]:
    """The nine valued series, in `valuation.CATEGORIES` order, over pool members.

    fg and ft come back as impact, not as rates. Every other category is the raw
    per-game projection, including TO, which is valued inverted but measured here
    as reported -- see LOWER_IS_BETTER, and state the orientation wherever the
    sign of its skew is shown.
    """
    out = {
        "fg": np.array([fg_impact(p, pool) for p in pool.members], dtype=float),
        "ft": np.array([ft_impact(p, pool) for p in pool.members], dtype=float),
    }
    for c in COUNTING:
        out[c] = np.array([getattr(p, c) for p in pool.members], dtype=float)
    return out


def label(key: str) -> str:
    """Display name. The two impacts say so, because they are not the rates."""
    base = CATEGORY_LABELS[key]
    return f"{base} impact" if key in ("fg", "ft") else base
