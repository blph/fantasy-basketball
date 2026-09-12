"""Basketball Monster's valuation, reimplemented from scratch.

A standalone reference implementation of the method reverse-engineered in
docs/references/basketball-monster-projections-reverse-engineering.md.

It needs no Basketball Monster access and no particular file format. Feed it any set of
projected season totals -- theirs, ours, ESPN's, hand-written -- and it produces the nine
category values, Value, Rank, DURANT and DURANT H2H.

Standard library only, so it adds no runtime dependency (see AGENTS.md).

Input contract
--------------
A "projection" is a mapping with these keys, all **season totals** except `games`:

    games, minutes, points, threes, rebounds, assists, steals, blocks, turnovers,
    fg_made, fg_att, ft_made, ft_att

Anything else on the mapping is ignored, so you can carry an id or a name alongside.
`helpers` below build this shape from the two layouts you are likely to meet.

Nothing here is specific to a season or a provider except the named constants at the
bottom, which are Basketball Monster's own fitted values and are labelled as such.
"""

from __future__ import annotations

import math
import statistics as st

# --------------------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------------------

#: The seven counting categories: (key on the per-game mapping, output name, sign).
#: Turnovers carry -1 because fewer is better; nothing else is inverted.
COUNTING = (
    ("points", "pV", +1),
    ("threes", "3V", +1),
    ("rebounds", "rV", +1),
    ("assists", "aV", +1),
    ("steals", "sV", +1),
    ("blocks", "bV", +1),
    ("turnovers", "toV", -1),
)

#: The two percentage categories: (makes key, attempts key, output name).
PERCENTAGE = (
    ("fg_made", "fg_att", "fg%V"),
    ("ft_made", "ft_att", "ft%V"),
)

#: All nine output names, in Basketball Monster's display order.
CATEGORIES = ("pV", "3V", "rV", "aV", "sV", "bV", "fg%V", "ft%V", "toV")


# --------------------------------------------------------------------------------------
# Step 1 -- per-game rates
# --------------------------------------------------------------------------------------

def per_game(projection):
    """Season totals -> per-game rates. Returns None for a player projected zero games.

    Every rate is total / games. Makes and attempts are kept separate rather than
    collapsed to a percentage, because the percentage categories are volume-weighted and
    a bare rate throws away the volume (see `category_values`).
    """
    g = float(projection["games"])
    if g <= 0:
        return None
    keys = (
        "minutes", "points", "threes", "rebounds", "assists", "steals", "blocks",
        "turnovers", "fg_made", "fg_att", "ft_made", "ft_att",
    )
    rates = {k: float(projection[k]) / g for k in keys}
    rates["games"] = g
    return rates


# --------------------------------------------------------------------------------------
# Step 2 -- the pool
# --------------------------------------------------------------------------------------

def pool_params(pool):
    """Standardisation constants from a pool of per-game mappings.

    Counting categories get the pool mean and **population** standard deviation (divide by
    n, not n-1).

    Percentage categories are different in two ways that both matter. The pool rate is
    **attempt-weighted** -- sum(makes) / sum(attempts) over the pool, not the average of
    the players' percentages; on a real pool those differ by about seven tenths of a
    point. And what gets standardised is the *impact*, `makes - attempts * pool_rate`,
    which is makes above what a pool-average shooter would get on the same attempts.
    """
    n = len(pool)
    if n == 0:
        raise ValueError("empty pool")
    params = {}
    for key, name, sign in COUNTING:
        xs = [p[key] for p in pool]
        params[name] = {
            "kind": "counting", "key": key, "sign": sign,
            "mean": sum(xs) / n, "sd": st.pstdev(xs),
        }
    for made, att, name in PERCENTAGE:
        total_att = sum(p[att] for p in pool)
        if total_att <= 0:
            raise ValueError(f"pool has no {att}")
        rate = sum(p[made] for p in pool) / total_att
        impacts = [p[made] - p[att] * rate for p in pool]
        params[name] = {
            "kind": "percentage", "made": made, "att": att, "rate": rate, "sign": +1,
            "mean": sum(impacts) / n, "sd": st.pstdev(impacts),
        }
    return params


def build_pool(rates, q, seed_order=None, max_iter=50):
    """Find the top-`q` pool, iterating to a fixed point.

    The definition is circular -- you need values to pick the pool and the pool to compute
    the values -- so start from any sensible ordering and repeat until membership stops
    changing. In practice this converges in one to three rounds.

    `rates` maps player key -> per-game mapping. `q` is teams x roster spots: the number
    of players who actually get drafted, and the group everyone is measured against.
    Returns (pool_keys, params).
    """
    keys = list(rates)
    if q > len(keys):
        raise ValueError(f"q={q} exceeds {len(keys)} players")
    if seed_order is None:
        # Any starting order works. Minutes is a decent, assumption-free seed.
        seed_order = sorted(keys, key=lambda k: -rates[k]["minutes"])
    pool = list(seed_order[:q])
    for _ in range(max_iter):
        params = pool_params([rates[k] for k in pool])
        scored = sorted(keys, key=lambda k: -value(rates[k], params))
        nxt = scored[:q]
        if nxt == pool:
            break
        pool = nxt
    return pool, pool_params([rates[k] for k in pool])


# --------------------------------------------------------------------------------------
# Step 3 -- the nine category values
# --------------------------------------------------------------------------------------

def category_values(rates, params, punt_weights=None):
    """The nine category values for one player.

    `punt_weights` optionally maps a category name to a multiplier. A weight of 0 removes
    the category's contribution entirely; 0.5 halves it. Note that the weight scales the
    standardised value, and that `value` still divides by nine regardless -- punting
    lowers everyone rather than redistributing.
    """
    out = {}
    for name in CATEGORIES:
        spec = params[name]
        if spec["kind"] == "counting":
            raw = rates[spec["key"]]
        else:
            raw = rates[spec["made"]] - rates[spec["att"]] * spec["rate"]
        # A category with no spread in the pool cannot separate anyone: score it flat
        # rather than dividing by zero. Happens on tiny or degenerate pools.
        z = 0.0 if spec["sd"] == 0 else spec["sign"] * (raw - spec["mean"]) / spec["sd"]
        if punt_weights:
            z *= punt_weights.get(name, 1.0)
        out[name] = z
    return out


def value(rates, params, punt_weights=None):
    """Value: the arithmetic **mean** of the nine category values.

    The mean, not the sum. A uniform division by nine reorders nothing, but it means every
    magnitude here is one ninth of the comparable figure on a board that sums.
    """
    vals = category_values(rates, params, punt_weights)
    return sum(vals[c] for c in CATEGORIES) / 9


def rank_and_round(scores, teams):
    """scores: {key: value}. Returns {key: (rank, round)}, rank 1 = best.

    Round is ceil(rank / teams) -- it reads league size, nothing more.
    """
    order = sorted(scores, key=lambda k: -scores[k])
    return {k: (i + 1, math.ceil((i + 1) / teams)) for i, k in enumerate(order)}


# --------------------------------------------------------------------------------------
# Yeo-Johnson
# --------------------------------------------------------------------------------------

def yeo_johnson(x, lam):
    """The Yeo-Johnson power transform. lam == 1 is the identity (shifted); lam == 0 is a log.

    Defined for negative x too, which is why it is used here rather than Box-Cox: the
    percentage impacts go both ways.
    """
    if x >= 0:
        return ((x + 1) ** lam - 1) / lam if abs(lam) > 1e-12 else math.log(x + 1)
    if abs(2 - lam) > 1e-12:
        return -(((-x + 1) ** (2 - lam) - 1) / (2 - lam))
    return -math.log(-x + 1)


def fit_lambda(xs, lo=-4.0, hi=4.0, iterations=200):
    """Maximum-likelihood Yeo-Johnson lambda for one category, by golden-section search.

    Use this to derive your own lambdas for a new season or a new projection set. It will
    NOT reproduce Basketball Monster's published lambdas -- see LAMBDAS_BBM_2026_27_JOSH
    and the note beside it.
    """
    inv = (math.sqrt(5) - 1) / 2

    def loglik(lam):
        t = [yeo_johnson(x, lam) for x in xs]
        var = st.pvariance(t)
        if var <= 0:
            return -math.inf
        n = len(t)
        jac = sum(math.copysign(math.log(abs(x) + 1), x) for x in xs)
        return -n / 2 * math.log(var) + (lam - 1) * jac

    for _ in range(iterations):
        a, b = hi - inv * (hi - lo), lo + inv * (hi - lo)
        if loglik(a) < loglik(b):
            lo = a
        else:
            hi = b
    return (lo + hi) / 2


# --------------------------------------------------------------------------------------
# DURANT
# --------------------------------------------------------------------------------------

def durant_params(pool, lambdas):
    """Standardisation constants for the DURANT layer: transform first, then standardise."""
    n = len(pool)
    params = {}
    for key, name, sign in COUNTING:
        t = [yeo_johnson(p[key], lambdas[name]) for p in pool]
        params[name] = {
            "kind": "counting", "key": key, "sign": sign, "lam": lambdas[name],
            "mean": sum(t) / n, "sd": st.pstdev(t),
        }
    for made, att, name in PERCENTAGE:
        total_att = sum(p[att] for p in pool)
        rate = sum(p[made] for p in pool) / total_att
        t = [yeo_johnson(p[made] - p[att] * rate, lambdas[name]) for p in pool]
        params[name] = {
            "kind": "percentage", "made": made, "att": att, "rate": rate, "sign": +1,
            "lam": lambdas[name], "mean": sum(t) / n, "sd": st.pstdev(t),
        }
    return params


def durant_category_values(rates, params):
    """The nine DURANT category values: Yeo-Johnson, then standardise."""
    out = {}
    for name in CATEGORIES:
        spec = params[name]
        if spec["kind"] == "counting":
            raw = rates[spec["key"]]
        else:
            raw = rates[spec["made"]] - rates[spec["att"]] * spec["rate"]
        t = yeo_johnson(raw, spec["lam"])
        out[name] = 0.0 if spec["sd"] == 0 else spec["sign"] * (t - spec["mean"]) / spec["sd"]
    return out


def durant(rates, params):
    """DURANT: drop the player's single worst category, average the eight that survive.

    All nine carry equal weight before the drop. Returns (score, dropped_category).
    """
    vals = durant_category_values(rates, params)
    worst = min(CATEGORIES, key=lambda c: vals[c])
    kept = [vals[c] for c in CATEGORIES if c != worst]
    return sum(kept) / len(kept), worst


def weighted_drop_one(vals, weights):
    """Weight the categories, drop the worst of those still live, average the survivors.

    A category weighted 0 is not merely discounted, it is removed: it takes no part in the
    "worst" comparison and does not sit in the denominator. That is how DURANT H2H drops
    turnovers, and it is why this is shared rather than written twice -- ZSH applies the
    same rule to untransformed z, and the two must agree on what "drop one" means or the
    difference between them stops being the transform.

    `vals` maps category -> standardised value. Returns (score, dropped_category).
    """
    live = [c for c in CATEGORIES if weights[c] != 0]
    if len(live) < 2:
        raise ValueError("weighted_drop_one needs at least two live categories")
    weighted = {c: vals[c] * weights[c] for c in live}
    worst = min(live, key=lambda c: weighted[c])
    kept = [weighted[c] for c in live if c != worst]
    return sum(kept) / len(kept), worst


def durant_h2h(rates, params, weights=None):
    """DURANT H2H: weight the categories, drop turnovers, drop the worst of the rest.

    Turnovers carry weight 0 in H2H_WEIGHTS -- that is *how* they are removed, rather than
    by a special case here. Averages the seven survivors. Returns (score, dropped).
    """
    if weights is None:
        weights = H2H_WEIGHTS
    # Hoisted deliberately. Called inside the dict comprehension this recomputed all nine
    # category values nine times per player, inside the pool iteration, for three sources
    # and ten punt builds -- the pipeline's hot loop.
    vals = durant_category_values(rates, params)
    return weighted_drop_one(vals, weights)


def z_h2h(rates, params, weights=None, punt_weights=None):
    """ZSH: the H2H weighting and the minus-one rule applied to UNTRANSFORMED z.

    Same shape as `durant_h2h` with the Yeo-Johnson layer removed, so the pair isolates
    what the transform is worth: any difference between a player's ZSH and DURH rank is
    the transform's doing and nothing else. Returns (score, dropped).
    """
    if weights is None:
        weights = H2H_WEIGHTS
    return weighted_drop_one(category_values(rates, params, punt_weights), weights)


def build_z_h2h_pool(rates, q, weights=None, seed_order=None, max_iter=50):
    """The ZSH pool, iterated to a fixed point on the ZSH score.

    ZSH ranks a different order than Value does, so it selects a different top-q and
    therefore different standardisation constants. Reusing the Value pool would leave the
    values subtly off their own definition.
    """
    keys = list(rates)
    if q > len(keys):
        raise ValueError(f"q={q} exceeds {len(keys)} players")
    if seed_order is None:
        seed_order = sorted(keys, key=lambda k: -rates[k]["minutes"])
    pool = list(seed_order[:q])
    for _ in range(max_iter):
        params = pool_params([rates[k] for k in pool])
        scored = sorted(keys, key=lambda k: -z_h2h(rates[k], params, weights)[0])
        nxt = scored[:q]
        if nxt == pool:
            break
        pool = nxt
    return pool, pool_params([rates[k] for k in pool])


def build_durant_pool(rates, q, lambdas, seed_order=None, max_iter=50):
    """The DURANT pool, iterated to a fixed point on the DURANT score."""
    keys = list(rates)
    if seed_order is None:
        seed_order = sorted(keys, key=lambda k: -rates[k]["minutes"])
    pool = list(seed_order[:q])
    for _ in range(max_iter):
        params = durant_params([rates[k] for k in pool], lambdas)
        scored = sorted(keys, key=lambda k: -durant(rates[k], params)[0])
        nxt = scored[:q]
        if nxt == pool:
            break
        pool = nxt
    return pool, durant_params([rates[k] for k in pool], lambdas)


# --------------------------------------------------------------------------------------
# Basketball Monster's own fitted constants
# --------------------------------------------------------------------------------------
# These are measurements of one provider's one season, not universal truths. They are what
# you need to reproduce Basketball Monster's published 2026-27 numbers; they are not what
# you need to apply the method to your own projections. For that, fit your own with
# `fit_lambda` and derive your own pool with `build_pool`.
#
# The *pool* constants are recoverable the same way the lambdas were, and for the draft board
# they have to be: no pool of the projection set reproduces both their means and their SDs, so
# `build_pool` cannot reproduce their published values however it is tuned. See
# scripts/draft-board/calibrate_bbm.py and ADR-0021.

#: Pool size: teams x roster spots. 12 x 13 for this league.
Q = 156

#: Yeo-Johnson lambdas recovered from Basketball Monster's published DURANT columns,
#: 2026-27, Josh Projections source. The same values hold for their Bonus source, so the
#: `_JOSH` suffix understates the scope; renaming would touch six call sites for nothing.
#:
#: Fitting these by maximum likelihood on the same pool gets every direction right but not
#: the values (blocks -1.38 against -1.69, points +0.07 against +0.42), so Basketball
#: Monster's lambdas come from a different objective, a different pool, or hand-tuning.
#: Use them to reproduce their numbers; use `fit_lambda` to build your own.
#:
#: **These are no longer what the draft board computes with.** They are the search seed and
#: the drift reference for `calibrate_bbm.py`, which refits a lambda per source on every
#: refresh against their published columns (ADR-0021). A frozen lambda has exactly the
#: problem a frozen pool constant had: Basketball Monster retunes it and nothing shows.
LAMBDAS_BBM_2026_27_JOSH = {
    "pV": 0.4151, "3V": 1.0166, "rV": -0.4381, "aV": 0.0065, "sV": -0.3513,
    "bV": -1.6863, "toV": -0.1778, "fg%V": 0.1727, "ft%V": 1.5038,
}

#: DURANT H2H category weights, recovered exactly (every intercept below 0.0005).
#: Turnovers at zero is how H2H "removes" them.
H2H_WEIGHTS = {
    "pV": 1.00, "rV": 0.94, "aV": 0.75,
    "3V": 0.60, "sV": 0.60, "bV": 0.60, "fg%V": 0.60, "ft%V": 0.60,
    "toV": 0.00,
}


# --------------------------------------------------------------------------------------
# Helpers for the two input layouts you are likely to meet
# --------------------------------------------------------------------------------------

def from_components(row, get=float):
    """Build a projection from a row carrying makes and attempts directly.

    Points are 2 * field_goals + threes + free_throws because **field goals already
    include three-pointers**. Counting a made three as three points *plus* a two-point
    field goal is the most common way to get this silently wrong.
    """
    fgm = get(row["field_goals"])
    return {
        "games": get(row["games"]),
        "minutes": get(row["minutes"]),
        "points": 2 * fgm + get(row["threes"]) + get(row["free_throws"]),
        "threes": get(row["threes"]),
        "rebounds": get(row["offensive_rebounds"]) + get(row["defensive_rebounds"]),
        "assists": get(row["assists"]),
        "steals": get(row["steals"]),
        "blocks": get(row["blocks"]),
        "turnovers": get(row["turnovers"]),
        "fg_made": fgm,
        "fg_att": get(row["field_goals_attempted"]),
        "ft_made": get(row["free_throws"]),
        "ft_att": get(row["free_throws_attempted"]),
    }


def from_totals_with_percentages(row, get=float):
    """Build a projection from a row carrying points and rebounds directly, plus rates.

    Makes are reconstructed as `percentage * attempts`, which carries about half a make of
    rounding error when the percentage is published to three decimals.
    """
    fga, fta = get(row["fga"]), get(row["fta"])
    return {
        "games": get(row["g"]),
        "minutes": get(row["min"]),
        "points": get(row["pts"]),
        "threes": get(row["3"]),
        "rebounds": get(row["reb"]),
        "assists": get(row["ast"]),
        "steals": get(row["stl"]),
        "blocks": get(row["blk"]),
        "turnovers": get(row["to"]),
        "fg_made": get(row["fg%"]) * fga,
        "fg_att": fga,
        "ft_made": get(row["ft%"]) * fta,
        "ft_att": fta,
    }
