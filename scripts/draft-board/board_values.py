#!/usr/bin/env python3
"""The nine values the board ranks on: three valuations across three projections.

    ZSC   Basketball Monster's `Value`. Nine z-scores, turnovers inverted, percentages by
          attempt-weighted impact, averaged over nine. No weights, no drops.
    ZSH   The H2H weighting and the minus-one rule applied to UNTRANSFORMED z.
    DURH  Basketball Monster's DURANT H2H: Yeo-Johnson, standardise, weight, drop the
          worst live category, average the seven survivors.

ZSC averages nine and the other two average seven, so their magnitudes are not comparable
across value types even for the same player. Only ranks are.

Each value gets its own pool. The pool is the top Q by that value, and the three values
rank a different order, so they select different top-Qs and therefore different
standardisation constants. Sharing one pool would leave two of the three values subtly off
their own definition.

The math lives in scripts/bbm/bbm_reference.py, which is validated against Basketball
Monster's published numbers. Nothing here reimplements it.
"""

from __future__ import annotations

import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bbm"))

from bbm_reference import (  # noqa: E402
    CATEGORIES,
    H2H_WEIGHTS,
    LAMBDAS_BBM_2026_27_JOSH,
    build_durant_pool,
    build_pool,
    build_z_h2h_pool,
    category_values,
    durant_category_values,
    durant_params,
    value,
    weighted_drop_one,
    z_h2h,
)

#: The eight categories the board displays, in the sheet's own order. Turnovers are absent
#: because DURANT H2H prices them at zero -- a DH turnover column is identically 0.0 for
#: every player, so it can never clear a band or move a team's total.
#:
#: This order is load-bearing three times over: the tracker's rows, the Punted checkbox
#: range, and the Category profile's label array are all matched against it positionally.
#: The harness asserts it. Keep it in step with Build.gs CAT_LABELS.
CAT_ORDER = ("fg%V", "ft%V", "3V", "pV", "rV", "aV", "sV", "bV")
CAT_LABELS = ("FG%", "FT%", "3PM", "PTS", "REB", "AST", "STL", "BLK")

#: Rosenof Table 8, 2022-23, via docs/references/category-tracker-z-thresholds.md.
#: k prices a whole known roster against a whole random one: P(win) = phi(Z_team * k).
K_ROSENOF = {
    "aV": 0.632, "3V": 0.587, "rV": 0.558, "bV": 0.551,
    "pV": 0.516, "ft%V": 0.466, "fg%V": 0.343, "sV": 0.328,
}


def tracker_k(weights=None) -> dict[str, float]:
    """The k the tracker needs when it is fed WEIGHTED DURANT H2H values.

    Rosenof's k assumes a unit-variance z. `durant_category_values` standardises to SD 1
    over the pool and the H2H weight is a pure scalar, so a weighted column's SD is exactly
    its weight, and Z_team measured in DH units is exactly w times Z_team in z units.

        K = k / w

    is therefore exact rather than fitted. Getting this backwards -- or skipping it --
    understates every win probability, and nothing in the sheet would look wrong.
    """
    w = weights or H2H_WEIGHTS
    return {c: K_ROSENOF[c] / w[c] for c in CAT_ORDER}


def _rank(scores: dict[str, float]) -> dict[str, int]:
    """Dense 1-based rank, best first. Ties break on the key so a rebuild is reproducible."""
    order = sorted(scores, key=lambda k: (-scores[k], str(k)))
    return {k: i + 1 for i, k in enumerate(order)}


def _seed(rates: dict) -> list:
    """A deterministic pool seed: minutes descending, then key.

    The fixed point is stable but not unique -- different seeds land on pools differing by
    a boundary player or two. Pinning the seed is what makes two runs of the pipeline
    produce byte-identical output.
    """
    return sorted(rates, key=lambda k: (-rates[k]["minutes"], str(k)))


def score_source(rates: dict, q: int, lambdas=None, weights=None) -> dict:
    """Every value, rank, dropped category and per-category number for one projection.

    `rates` maps a player key to a per-game mapping. Returns a dict carrying the three
    pools' constants and, per player, everything the sheet displays.
    """
    lambdas = lambdas or LAMBDAS_BBM_2026_27_JOSH
    weights = weights or H2H_WEIGHTS
    seed = _seed(rates)

    zsc_pool, zsc_params = build_pool(rates, q, seed_order=seed)
    zsh_pool, zsh_params = build_z_h2h_pool(rates, q, weights, seed_order=seed)
    dur_pool, dur_params = build_durant_pool(rates, q, lambdas, seed_order=seed)

    players = {}
    for key, r in rates.items():
        zsc = value(r, zsc_params)
        zsh, zsh_drop = z_h2h(r, zsh_params, weights)
        dcv = durant_category_values(r, dur_params)
        durh, durh_drop = weighted_drop_one(dcv, weights)
        players[key] = {
            "zsc": zsc,
            "zsh": zsh, "zsh_drop": zsh_drop,
            "durh": durh, "durh_drop": durh_drop,
            # Weighted, as displayed. The tracker absorbs the weight into K.
            "dh": {c: dcv[c] * weights[c] for c in CAT_ORDER},
            # Unweighted, so the Category profile can threshold one band across all eight.
            "d": {c: dcv[c] for c in CAT_ORDER},
            "z": category_values(r, zsc_params),
        }

    for field in ("zsc", "zsh", "durh"):
        ranks = _rank({k: p[field] for k, p in players.items()})
        for k, p in players.items():
            p[f"{field}_rank"] = ranks[k]

    return {
        "players": players,
        "pools": {
            "zsc": _pool_report(zsc_pool, zsc_params, rates),
            "zsh": _pool_report(zsh_pool, zsh_params, rates),
            "durant": _pool_report(dur_pool, dur_params, rates),
        },
        "universe": len(rates),
        # How far the two pools disagree. A big divergence means the value you sort by
        # changes who "average" is, which is worth seeing rather than assuming.
        "pool_overlap": len(set(zsc_pool) & set(dur_pool)),
    }


def _pool_report(pool: list, params: dict, rates: dict) -> dict:
    """The constants a reader needs to audit a value without rerunning the pipeline."""
    out = {"size": len(pool)}
    for c in CATEGORIES:
        spec = params[c]
        out[c] = {"mean": round(spec["mean"], 6), "sd": round(spec["sd"], 6)}
        if spec["kind"] == "percentage":
            out[c]["rate"] = round(spec["rate"], 6)
    gp = [rates[k]["games"] for k in pool]
    out["gp_min"] = min(gp)
    out["gp_median"] = st.median(gp)
    # ADR-0011 retired the MIN_GP pool gate. The concern it named is real, so it stays
    # visible as a diagnostic: if this ever climbs past a handful, revisit on evidence.
    out["gp_under_25"] = sum(1 for g in gp if g < 25)
    return out


def durant_h2h_punt(rates: dict, q: int, drop: tuple[str, ...], punt_weight: float,
                    lambdas=None, weights=None) -> dict[str, float]:
    """DURH for a punt build: discount the punted categories, then re-derive the pool.

    Basketball Monster's mechanism (spec section I.9), and it differs from the board's old
    one in the step that matters. Discounting BEFORE standardising changes who is in the
    top Q, which changes every mean and SD -- so a punt is not a local edit to one column,
    it moves the whole field. Subtracting a discounted category after the fact, as the
    sheet used to, holds the pool still and gets a different answer.

    Two distinct multipliers are in play and conflating them is the easy mistake:

        punt scale   applies to the standardised category value, for the punted
                     categories only, and takes part in POOL SELECTION
        H2H weights  turn DURANT into DURANT H2H, and never affect pool selection

    So the pool iterates on the punt-scaled DURANT score -- the same metric the unpunted
    pool iterates on -- and only then is the H2H rule applied. That is what makes a punt
    weight of 1.0 reproduce the unpunted value exactly, which is the identity that proves
    the two paths have not drifted apart.

    The denominator does not shrink: punting lowers everyone rather than redistributing.
    """
    lambdas = lambdas or LAMBDAS_BBM_2026_27_JOSH
    weights = weights or H2H_WEIGHTS
    scale = {c: (punt_weight if c in drop else 1.0) for c in CATEGORIES}

    def scaled(rate, params):
        vals = durant_category_values(rate, params)
        return {c: vals[c] * scale[c] for c in CATEGORIES}

    def durant_score(vals):
        """Drop the worst of the nine, average the eight survivors -- the pool's metric."""
        worst = min(CATEGORIES, key=lambda c: vals[c])
        return sum(vals[c] for c in CATEGORIES if c != worst) / (len(CATEGORIES) - 1)

    def params_for(members):
        return durant_params([rates[k] for k in members], lambdas)

    pool = _seed(rates)[:q]
    for _ in range(50):
        params = params_for(pool)
        scored = sorted(rates, key=lambda k: (-durant_score(scaled(rates[k], params)), str(k)))
        if scored[:q] == pool:
            break
        pool = scored[:q]

    params = params_for(pool)
    return {k: weighted_drop_one(scaled(r, params), weights)[0] for k, r in rates.items()}


def profile_calibration(players: dict, ranked: list, bands=(0.85, 1.0, 1.15)) -> dict:
    """How many strengths and weaknesses each band names, over the drafted pool.

    ADR-0013 chose the current band by measuring exactly this, so a change of basis has to
    be re-measured the same way rather than inheriting the number.
    """
    out = {}
    for band in bands:
        flags = nolabel = 0
        for k in ranked:
            d = players[k]["d"]
            s = [c for c in CAT_ORDER if d[c] >= band]
            w = [c for c in CAT_ORDER if d[c] <= -band]
            flags += len(s) + len(w)
            nolabel += not (s or w)
        out[band] = {
            "flags_per_player": round(flags / len(ranked), 2),
            "pct_unlabelled": round(100 * nolabel / len(ranked)),
        }
    return out


def durant_vs_z_slopes(players: dict, ranked: list) -> dict[str, float]:
    """Least-squares slope of each DURANT column on its plain-z column, over the pool.

    Both have unit SD by construction, so the transform reshapes without rescaling and
    every slope should sit just under 1. It is the diagnostic for how far the Yeo-Johnson
    layer moves each category -- blocks most, threes least.
    """
    out = {}
    for c in CAT_ORDER:
        xs = [players[k]["z"][c] for k in ranked]
        ys = [players[k]["d"][c] for k in ranked]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
        den = sum((x - mx) ** 2 for x in xs)
        out[c] = round(num / den, 4) if den else math.nan
    return out
