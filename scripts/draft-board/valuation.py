"""The playbook's valuation, in Python.

A second implementation of what `Build.gs` writes into the sheet, kept
deliberately independent of it: this file is derived from
`docs/references/fantasy-basketball-draft-playbook.md`, which AGENTS.md names as
the specification, not from the spreadsheet formulas. Two implementations that
agree are evidence; one implementation checking itself is not.

`verify.py` runs this against the real export and diffs it against the sheet.
`tests/test_valuation.py` runs it against hand-authored synthetic players.

Contains no player data and no I/O.
"""

from __future__ import annotations

import statistics as st
from dataclasses import dataclass

# Rosenof, arXiv 2307.02188 Table 8, 2022-23, normalised to AST = 1.00. The
# ordering is reliable; the second decimal is not, least of all on the two
# percentage rows, whose reported variances carry one significant figure.
MULTIPLIERS = {
    "fg": 0.75, "ft": 0.77, "tpm": 0.96, "pts": 0.87, "reb": 0.92,
    "ast": 1.00, "stl": 0.59, "blk": 0.91, "to": 0.83,
}
COUNTING = ["tpm", "pts", "reb", "ast", "stl", "blk", "to"]
CATEGORIES = ["fg", "ft", *COUNTING]


@dataclass
class Player:
    """One projected per-game line. Field names match the Board's columns."""

    seed: int
    name: str
    gp: float
    fgm: float
    fga: float
    fgp: float
    ftm: float
    fta: float
    ftp: float
    tpm: float
    pts: float
    reb: float
    ast: float
    stl: float
    blk: float
    to: float


@dataclass
class Pool:
    """The eight constants every value on the board is measured against."""

    members: list[Player]
    mean: dict[str, float]
    sd: dict[str, float]
    fg_pct: float
    ft_pct: float
    avg_fga: float
    avg_fta: float
    sd_fg_impact: float
    sd_ft_impact: float


def in_pool(p: Player, q: int, min_gp: float) -> bool:
    """Pool membership keys off the static seed rank, not a live value.

    "The top Q by value" is circular — you need values to know who they are.
    Seeding from the provider's rank breaks the circle; `reseedPool` iterates it.
    """
    return p.seed <= q and p.gp >= min_gp


def fg_impact(p: Player, pool: Pool) -> float:
    """A shooting edge is worth what volume makes it worth.

    Valuing FG% as a bare rate counts a 3-shot night the same as an 18-shot one.
    The pool rate is the aggregate — total makes over total attempts — which is
    what makes the mean of this column identically zero over the pool, and hence
    what makes dividing by its SD a proper z-score with no centring term.
    """
    return (p.fga / pool.avg_fga) * (p.fgp - pool.fg_pct)


def ft_impact(p: Player, pool: Pool) -> float:
    return (p.fta / pool.avg_fta) * (p.ftp - pool.ft_pct)


def build_pool(players: list[Player], q: int, min_gp: float) -> Pool:
    members = [p for p in players if in_pool(p, q, min_gp)]
    if len(members) < 2:
        raise ValueError(f"pool has {len(members)} members; need at least 2")

    mean, sd = {}, {}
    for c in COUNTING:
        vals = [getattr(p, c) for p in members]
        mean[c] = st.fmean(vals)
        sd[c] = st.stdev(vals)

    pool = Pool(
        members=members, mean=mean, sd=sd,
        fg_pct=sum(p.fgm for p in members) / sum(p.fga for p in members),
        ft_pct=sum(p.ftm for p in members) / sum(p.fta for p in members),
        avg_fga=st.fmean([p.fga for p in members]),
        avg_fta=st.fmean([p.fta for p in members]),
        sd_fg_impact=0.0, sd_ft_impact=0.0,
    )
    pool.sd_fg_impact = st.stdev([fg_impact(p, pool) for p in members])
    pool.sd_ft_impact = st.stdev([ft_impact(p, pool) for p in members])
    return pool


def z_scores(p: Player, pool: Pool) -> dict[str, float]:
    z = {
        "fg": fg_impact(p, pool) / pool.sd_fg_impact,
        "ft": ft_impact(p, pool) / pool.sd_ft_impact,
    }
    for c in COUNTING:
        # Turnovers count against, so that one subtraction runs the other way.
        z[c] = ((pool.mean[c] - p.to) / pool.sd[c] if c == "to"
                else (getattr(p, c) - pool.mean[c]) / pool.sd[c])
    return z


def g_scores(p: Player, pool: Pool) -> dict[str, float]:
    """Z discounted by how much each category swings week to week.

    An edge in a stable category converts to wins more reliably than the same
    edge in a volatile one, so steals count roughly half and assists count full.
    """
    return {c: v * MULTIPLIERS[c] for c, v in z_scores(p, pool).items()}


def z_total(p: Player, pool: Pool) -> float:
    return sum(z_scores(p, pool).values())


def g_total(p: Player, pool: Pool) -> float:
    return sum(g_scores(p, pool).values())


def replacement(players: list[Player], pool: Pool, q: int) -> float:
    """The G-score of the last player who gets drafted at all."""
    totals = sorted((g_total(p, pool) for p in players), reverse=True)
    if len(totals) < q:
        raise ValueError(f"{len(totals)} players ranked, need {q}")
    return totals[q - 1]


def punt_total(p: Player, pool: Pool, drop: list[str], punt_weight: float) -> float:
    """G total with the punted categories discounted rather than deleted.

    `punt_weight` is what a punted category retains: 0.0 is a hard punt and
    reproduces the board's original behaviour exactly. See ADR-0009.
    """
    g = g_scores(p, pool)
    return sum(v * (punt_weight if c in drop else 1.0) for c, v in g.items())


def adjusted_value(vor: float, my_gp: float, gp_divisor: float) -> float:
    """VOR discounted for availability, and never inflated by it.

    Multiplying a negative VOR by GP/72 moves it toward zero, i.e. UP the board,
    which would rank the less available of two equal players higher. The board
    carries 200 rows against a pool of 156, so those rows exist. Floor at 1.
    """
    return vor * (1.0 if vor < 0 else my_gp / gp_divisor)
