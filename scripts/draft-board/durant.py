"""A reconstruction of Basketball Monster's DURANT, from its published description.

DURANT is Josh Lloyd's head-to-head valuation. Its structure is documented in
`docs/references/basketball-monster-durant.md`; its coefficients are not, and
Lloyd says so outright ("I'm not going to tell you exactly what it is"). So this
is a *reconstruction*, not a reimplementation, and nothing here should be
presented as matching his numbers.

What is sourced, and built here:

  * a Yeo-Johnson power transform per category, then standardisation, which is
    the mechanism Lloyd names on 22 Apr 2026;
  * fixed category weights that ignore the user's punt settings;
  * the "minus one" rule, in all three regimes BBM's own tooltips document;
  * per-game throughout, with no availability term.

What is sourced and *not* built, because no public description exists:

  * the real category weights (the defaults here are Lloyd's pre-DURANT hand
    weights, from article 1831 -- a different, earlier method);
  * "availability of stats off waiver wires";
  * "correlation between numbers".

Reads the same `Pool` that `valuation.py` builds, so the pool, the percentage
impacts and the turnover convention are shared rather than forked.

Contains no player data and no I/O.
"""

from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass, field

from valuation import (
    CATEGORIES,
    COUNTING,
    Player,
    Pool,
    fg_impact,
    ft_impact,
)

# Lloyd's hand weights from article 1831 (Aug 2022), which describe the *manual*
# method DURANT later automated -- not DURANT's own weights, which are withheld.
# Kept as the default so the reconstruction starts from something he published
# rather than something invented here.
LLOYD_WEIGHTS = {
    "fg": 1.0, "ft": 0.85, "tpm": 0.8, "pts": 1.0, "reb": 1.0,
    "ast": 1.0, "stl": 0.7, "blk": 0.7, "to": 1.0,
}

# Yeo-Johnson is unbounded in lambda but degenerate far from 1. SciPy searches
# [-2, 2] by default, which is far too narrow here: the percentage impacts are
# small signed numbers clustered near zero, and on a real pool FG% impact peaks
# around lambda = -6.9. A [-5, 5] bracket pinned it at the edge and silently
# returned the wrong transform. `pinned` still reports any fit that reaches the
# boundary, because a pinned lambda is an extrapolation, not a fit.
LAMBDA_LO, LAMBDA_HI = -15.0, 15.0

MINUS_ONE_REGIMES = ("none", "roto", "h2h", "durant_h2h")


def yeo_johnson(x: float, lam: float) -> float:
    """The Yeo-Johnson power transform.

    Box-Cox extended to handle zero and negative values, which 9-cat needs: the
    percentage impacts are signed, and blocks and steals sit on a floor of zero.
    """
    if x >= 0:
        if lam == 0.0:
            return math.log1p(x)
        return ((x + 1.0) ** lam - 1.0) / lam
    if lam == 2.0:
        return -math.log1p(-x)
    return -(((-x + 1.0) ** (2.0 - lam) - 1.0) / (2.0 - lam))


def yj_loglik(values: list[float], lam: float) -> float:
    """Profile log-likelihood of `lam`, up to a constant.

    The Jacobian term is what stops the fit from simply shrinking everything:
    without it, larger |lam| would always look better.
    """
    t = [yeo_johnson(v, lam) for v in values]
    n = len(t)
    mean = st.fmean(t)
    var = sum((v - mean) ** 2 for v in t) / n
    if var <= 0.0:
        return -math.inf
    jacobian = sum(math.copysign(1.0, v) * math.log1p(abs(v)) for v in values)
    return -0.5 * n * math.log(var) + (lam - 1.0) * jacobian


def fit_lambda(values: list[float], tol: float = 1e-6) -> float:
    """Maximum-likelihood `lam`, by golden-section search.

    The profile likelihood is smooth and unimodal in practice. A coarse scan
    first, because golden section needs a bracket that actually contains the
    maximum and the percentage impacts can peak near an edge.
    """
    if len(values) < 2:
        raise ValueError(f"need at least 2 values to fit lambda, got {len(values)}")

    grid = [LAMBDA_LO + i * (LAMBDA_HI - LAMBDA_LO) / 120.0 for i in range(121)]
    best = max(grid, key=lambda t: yj_loglik(values, t))
    lo = max(LAMBDA_LO, best - (LAMBDA_HI - LAMBDA_LO) / 120.0)
    hi = min(LAMBDA_HI, best + (LAMBDA_HI - LAMBDA_LO) / 120.0)

    invphi = (math.sqrt(5.0) - 1.0) / 2.0
    c, d = hi - invphi * (hi - lo), lo + invphi * (hi - lo)
    while hi - lo > tol:
        if yj_loglik(values, c) > yj_loglik(values, d):
            hi, d = d, c
            c = hi - invphi * (hi - lo)
        else:
            lo, c = c, d
            d = lo + invphi * (hi - lo)
    return (lo + hi) / 2.0


def raw_values(p: Player, pool: Pool) -> dict[str, float]:
    """The quantity each category is scored on, before any transform.

    Percentages use the same volume-weighted impact `valuation.py` uses, so the
    two implementations disagree about the transform and nothing else.

    Turnovers stay in their natural direction here -- high is bad -- because the
    transform is fitted to the shape of the raw statistic. The sign flip happens
    after standardising, in `durant_scores`.
    """
    v = {"fg": fg_impact(p, pool), "ft": ft_impact(p, pool)}
    for c in COUNTING:
        v[c] = getattr(p, c)
    return v


@dataclass
class DurantPool:
    """Per-category transform parameters, fitted once over the pool."""

    lam: dict[str, float] = field(default_factory=dict)
    mean: dict[str, float] = field(default_factory=dict)
    sd: dict[str, float] = field(default_factory=dict)
    pinned: list[str] = field(default_factory=list)


def build_durant_pool(pool: Pool) -> DurantPool:
    """Fit Yeo-Johnson per category over the rostered pool, then standardise.

    Records which categories fit against the search boundary. A pinned lambda
    means the likelihood never turned over inside the bracket, so the transform
    is an extrapolation rather than a fit -- worth surfacing, not swallowing.
    """
    dp = DurantPool()
    for c in CATEGORIES:
        vals = [raw_values(p, pool)[c] for p in pool.members]
        lam = fit_lambda(vals)
        t = [yeo_johnson(v, lam) for v in vals]
        sd = st.stdev(t)
        if sd == 0.0:
            raise ValueError(
                f"zero spread in {c} after the Yeo-Johnson transform; "
                "it cannot be standardised"
            )
        dp.lam[c], dp.mean[c], dp.sd[c] = lam, st.fmean(t), sd
        if abs(lam - LAMBDA_LO) < 1e-3 or abs(lam - LAMBDA_HI) < 1e-3:
            dp.pinned.append(c)
    return dp


def durant_scores(p: Player, pool: Pool, dp: DurantPool) -> dict[str, float]:
    """Standardised, transformed per-category scores. Turnovers inverted."""
    raw = raw_values(p, pool)
    out = {}
    for c in CATEGORIES:
        z = (yeo_johnson(raw[c], dp.lam[c]) - dp.mean[c]) / dp.sd[c]
        out[c] = -z if c == "to" else z
    return out


def apply_minus_one(
    scores: dict[str, float], regime: str = "h2h"
) -> dict[str, float]:
    """The "minus one" rule, in the three regimes BBM's tooltips document.

    An automatic, per-player punt: whichever category a player is worst in stops
    counting against him. Structurally the opposite of our own board, which
    makes you pick a build and then values everyone against it.

    Which category counts as "worst" is an inference -- the lowest score after
    weighting is the reading taken here, and BBM does not say.
    """
    if regime not in MINUS_ONE_REGIMES:
        raise ValueError(f"unknown regime {regime!r}; expected one of {MINUS_ONE_REGIMES}")
    if regime == "none":
        return dict(scores)

    s = dict(scores)
    if regime == "durant_h2h":
        # Turnovers go first, unconditionally, then the next-worst.
        s.pop("to", None)
        if s:
            s.pop(min(s, key=lambda c: s[c]), None)
        return s

    worst = min(s, key=lambda c: s[c])
    if regime == "h2h":
        s.pop(worst)
    else:  # roto
        s[worst] *= 0.5
    return s


def durant_total(
    p: Player,
    pool: Pool,
    dp: DurantPool,
    weights: dict[str, float] | None = None,
    regime: str = "h2h",
) -> float:
    """One player's DURANT-style value.

    Summed, not averaged. BBM displays the mean of its nine category values; a
    uniform divisor cannot reorder anyone, and summing keeps this on the same
    scale as `G TOTAL` so the two are directly comparable.
    """
    w = LLOYD_WEIGHTS if weights is None else weights
    weighted = {c: v * w.get(c, 1.0) for c, v in durant_scores(p, pool, dp).items()}
    return sum(apply_minus_one(weighted, regime).values())
