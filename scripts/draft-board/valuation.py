"""The playbook's valuation, in Python.

**This is no longer what the board runs on.** ADR-0015 moved the board to Basketball
Monster's DURANT H2H, which lives in `scripts/bbm/bbm_reference.py` and is assembled by
`board_values.py`. Nothing here feeds the sheet any more.

It is kept, unchanged, for two reasons. `docs/roadmap.md` has Phase 2 inheriting it rather
than starting over, and it remains the only executable statement of the model in
`docs/references/fantasy-basketball-draft-playbook.md` — the z-score, the G-score
volatility discount, value over replacement, and the games-played scaling. That model is
the record of how the board was reasoned about before the Basketball Monster research, and
deleting it would lose the reasoning along with the code.

Read it as history, not as the current specification. In particular it uses a sample
standard deviation where `bbm_reference.py` uses a population one, deliberately left
alone: the two now compute different quantities, so making their standard deviations agree
would not make their answers agree.

`tests/test_valuation.py` runs it against hand-authored synthetic players.

Contains no player data and no I/O.
"""

from __future__ import annotations

import statistics as st
from collections.abc import Iterable
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

# Display labels, in CATEGORIES order. Mirrors CAT_LABELS in Build.gs, which the
# sheet lines up elementwise against its z block.
CATEGORY_LABELS = {
    "fg": "FG%", "ft": "FT%", "tpm": "3PM", "pts": "PTS", "reb": "REB",
    "ast": "AST", "stl": "STL", "blk": "BLK", "to": "TO",
}

# One standard deviation from the pool mean. See ADR-0013 for the calibration:
# at 1.00 every category names 20-27 specialists and 91% of the top 156 get a
# label, which is the yield that makes the column readable on the clock.
CATEGORY_BAND = 1.00


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

    # Standardising divides by each category's spread, so a zero anywhere is
    # fatal. Say which category and why, rather than dividing by it and raising
    # ZeroDivisionError three frames deeper with no clue which one it was.
    flat = [c for c in COUNTING if sd[c] == 0]
    flat += [n for n, v in (("FG% impact", pool.sd_fg_impact),
                            ("FT% impact", pool.sd_ft_impact)) if v == 0]
    if flat:
        raise ValueError(
            f"zero spread across {len(members)} pool members in: {', '.join(flat)}. "
            "Every member is identical there, so it cannot be standardised"
        )
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


def strength_labels(
    p: Player,
    pool: Pool,
    band: float = CATEGORY_BAND,
    punted: Iterable[str] = (),
) -> tuple[list[str], list[str]]:
    """The categories this player is strong and weak in, as display labels.

    The Draft Board's `Category profile` column, recomputed independently of the
    sheet. Strong is `z >= band`, weak is `z <= -band`, both against the rostered
    pool rather than the league at large -- a stricter reference than the same
    number quoted by public z-score tables, which is why the sheet keeps the band
    in Settings rather than hardcoding it.

    Built on z and deliberately not on g. The g multipliers discount a category
    by its week-to-week volatility, which prices an edge; adjusted value has
    already applied that. This asks the prior question -- does he have an edge at
    all -- and it is the same quantity the category tracker measures. Reusing g
    here applies the discount twice and all but silences the volatile categories:
    steals at 0.59 leave nine strong players in the entire pool.

    Turnovers arrive already sign-flipped from `z_scores`, so a low-turnover
    player lands in `strong` with no special case here.

    `punted` names categories to omit from both lists, matching the tracker's
    Punted checkboxes.
    """
    z = z_scores(p, pool)
    skip = set(punted)
    strong = [CATEGORY_LABELS[c] for c in CATEGORIES
              if c not in skip and z[c] >= band]
    weak = [CATEGORY_LABELS[c] for c in CATEGORIES
            if c not in skip and z[c] <= -band]
    return strong, weak


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


def converge_pool(
    players: list[Player],
    q: int,
    min_gp: float,
    gp_divisor: float = 72.0,
    max_passes: int = 10,
) -> tuple[Pool, int]:
    """Iterate the pool until membership stops changing.

    The pool is "the top Q by value", but you need values to know who those are.
    Seeding from the provider's rank breaks the circle for one pass; re-seeding
    from the resulting ranks and repeating closes it. The sheet does this as a
    menu action (`reseedPool`), one pass per invocation.

    Returns the settled pool and the number of passes it took. Raises if it does
    not settle -- a pool that oscillates is a real finding, not something to
    paper over with a pass limit.
    """
    seeds = {p.name: p.seed for p in players}
    previous: set[str] | None = None

    for pass_no in range(1, max_passes + 1):
        for p in players:
            p.seed = seeds[p.name]
        pool = build_pool(players, q, min_gp)
        members = {p.name for p in pool.members}
        if members == previous:
            return pool, pass_no
        previous = members

        # Re-seed from this pass's adjusted ranks, exactly as the sheet does.
        repl = replacement(players, pool, q)
        ranked = sorted(
            players,
            key=lambda p: -adjusted_value(g_total(p, pool) - repl, p.gp, gp_divisor),
        )
        seeds = {p.name: i + 1 for i, p in enumerate(ranked)}

    raise ValueError(f"pool did not settle in {max_passes} passes")


def adjusted_value(vor: float, my_gp: float, gp_divisor: float) -> float:
    """VOR discounted for availability, and never inflated by it.

    Multiplying a negative VOR by GP/72 moves it toward zero, i.e. UP the board,
    which would rank the less available of two equal players higher. The board
    carries 200 rows against a pool of 156, so those rows exist. Floor at 1.
    """
    return vor * (1.0 if vor < 0 else my_gp / gp_divisor)
