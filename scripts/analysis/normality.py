"""How normal is a category, and does the answer matter for a z-score.

Standardising a category assumes it is roughly Normal. When it is not, the z still
*ranks* players correctly -- it is monotone -- but the *distance* between two
players stops being calibrated, and reading a z as a probability starts lying.
That is the distinction every measurement here is built around.

Two deliberate omissions, because a battery of tests that all read the same two
moments looks like corroboration and is not:

  Jarque-Bera reads the same skew and kurtosis as D'Agostino-Pearson but refers
  them to a chi-square(2) null that it approaches only asymptotically, and slowly.
  In the low hundreds its p-values are the known-miscalibrated ones. It would add
  a third column that restates K2 less accurately, not a second opinion.

  Filliben's Q-Q correlation is, to within rounding, the square root of
  Shapiro-Wilk's W. Reporting both is reporting one number twice, so `sqrt_w`
  carries the intuitive reading instead.

The bimodality coefficient IS computed, and is meant to be read as a negative
result. BC is a deterministic function of skew and kurtosis, so it cannot see
anything those two do not already show. On our own pool it is wrong in both
directions: it reads below its 0.555 flag for the two categories whose second
mode survives heavy smoothing, and above it for a plainly unimodal right-skewed
one. `kde_modes` and `critical_bandwidth` are what actually find a second mode.

Pure functions over a 1-D sample. No I/O, no formatting, no player data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

# Below this many distinct values, a continuity-assuming test (Shapiro-Wilk,
# Anderson-Darling) is measuring the provider's 0.1 rounding grid rather than the
# shape of the pool. STL carries 16 distinct values across 156 players.
MIN_DISTINCT_FOR_CONTINUOUS_TEST = 30

# Conventional "approximately Normal" bands. Bulmer's rule of thumb calls |G1|
# below 0.5 approximately symmetric; Kline's looser |G1|<1, |G2|<2 is the tier
# below. The KS thresholds are stated in the unit a reader can act on: 0.05 is
# "no player's percentile is misplaced by more than 5 points".
TIER_A = {"skew": 0.5, "kurt": 1.0, "ks": 0.05}
TIER_B = {"skew": 1.0, "kurt": 2.0, "ks": 0.10}

# A second mode that survives this multiple of Silverman's bandwidth is real
# structure rather than sampling noise.
CRITICAL_BANDWIDTH_TIER_D = 1.5
FLOOR_MASS_TIER_D = 0.10

# Stephens (1974) critical values for Anderson-Darling against a Normal with both
# parameters estimated, in the order scipy returns them.
AD_SIGNIFICANCE = (15.0, 10.0, 5.0, 2.5, 1.0)


def anderson_darling(values: np.ndarray) -> tuple[float, float]:
    """A-squared and its p-value, across the SciPy 1.17 signature change.

    From 1.17 `anderson` wants an explicit `method`, and passing one swaps the
    critical-value table on the result for a `pvalue`. Older SciPy has no such
    keyword at all. Ask for the p-value, and fall back to interpolating the
    Stephens table by hand when the keyword is rejected -- the two agree, because
    `method="interpolate"` is that same table.
    """
    try:
        r = stats.anderson(values, dist="norm", method="interpolate")
        return float(r.statistic), float(r.pvalue)
    except TypeError:
        r = stats.anderson(values, dist="norm")
        crit = np.asarray(r.critical_values, dtype=float)
        # significance_level runs 15 -> 1 as the criticals rise; np.interp needs
        # both ascending, so reverse the pair.
        levels = np.asarray(r.significance_level, dtype=float)[::-1] / 100.0
        p = float(np.interp(float(r.statistic), crit[::-1], levels))
        return float(r.statistic), p


@dataclass(frozen=True)
class Normality:
    """Every measurement for one category, and the tier they add up to."""

    name: str
    n: int
    mean: float
    sd: float
    median: float
    iqr: float
    p05: float
    p95: float
    minimum: float
    maximum: float

    skew: float
    skew_se: float
    kurt: float
    kurt_se: float

    shapiro_w: float
    shapiro_p: float
    sqrt_w: float
    dagostino_k2: float
    dagostino_p: float
    anderson_a2: float
    anderson_p: float

    ks_max: float
    ecdf_at_z: dict[float, float]

    distinct: int
    floor_mass: float
    kde_modes: int
    critical_bandwidth: float | None
    bimodality_coefficient: float

    tier: str
    tier_reason: str

    @property
    def skew_z(self) -> float:
        return self.skew / self.skew_se

    @property
    def kurt_z(self) -> float:
        return self.kurt / self.kurt_se

    @property
    def continuous_test_valid(self) -> bool:
        return self.distinct >= MIN_DISTINCT_FOR_CONTINUOUS_TEST


def skew_se(n: int) -> float:
    """Exact finite-sample SE of G1, per Cramer.

    The textbook sqrt(6/n) is the n->infinity limit and runs about 1% wide at
    n=156 -- small, but it is free to be exact, and the z's built on it are what
    the report shows instead of p-values.
    """
    return math.sqrt(6 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3)))


def kurt_se(n: int) -> float:
    """Exact finite-sample SE of G2, which needs the G1 SE first."""
    return math.sqrt(4 * (n**2 - 1) * skew_se(n) ** 2 / ((n - 3) * (n + 5)))


def ecdf_vs_normal(values: np.ndarray, z_points=(-2.0, -1.0, 1.0, 2.0)) -> tuple[float, dict]:
    """How far the empirical distribution sits from the Normal the z-score assumes.

    This is the only measurement here expressed in a unit that maps to a decision:
    a value of 0.127 means some player's percentile is misplaced by 12.7 points.
    A p-value cannot say that, which is why the verdict tiers key off this and the
    two moments rather than off any test.
    """
    mean, sd = float(values.mean()), float(values.std(ddof=1))
    if sd == 0:
        raise ValueError("zero spread: every value identical")
    ordered = np.sort(values)
    n = len(ordered)
    theoretical = stats.norm.cdf((ordered - mean) / sd)
    # Compare against both edges of each ECDF step, else the max is understated.
    upper = np.arange(1, n + 1) / n
    lower = np.arange(0, n) / n
    ks_max = float(np.max(np.maximum(upper - theoretical, theoretical - lower)))

    at_z = {}
    for z in z_points:
        cut = mean + z * sd
        at_z[z] = float(np.count_nonzero(values <= cut) / n)
    return ks_max, at_z


def _kde(values: np.ndarray, h: float, grid: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * ((grid[:, None] - values[None, :]) / h) ** 2).sum(axis=1)


def silverman_bandwidth(values: np.ndarray) -> float:
    return 1.06 * float(values.std(ddof=1)) * len(values) ** -0.2


def count_modes(values: np.ndarray, h: float, grid_size: int = 2048) -> int:
    sd = float(values.std(ddof=1))
    grid = np.linspace(values.min() - 3 * sd, values.max() + 3 * sd, grid_size)
    d = _kde(values, h, grid)
    return int(np.count_nonzero((d[1:-1] > d[:-2]) & (d[1:-1] > d[2:])))


def critical_bandwidth(values: np.ndarray, max_multiple: float = 8.0) -> float | None:
    """The smallest bandwidth at which the density goes unimodal, over Silverman's.

    This replaces Hartigan's dip test, which is not in scipy and whose correct
    implementation needs a convex minorant plus a bootstrap null -- too much
    unvalidated statistics to put in a repository whose first priority is that a
    wrong number that looks right is worse than no number. The critical bandwidth
    answers the same question by construction: a bump that needs twice Silverman's
    smoothing to erase is not a sampling accident.

    None when the density is already unimodal at Silverman's bandwidth.
    """
    h = silverman_bandwidth(values)
    if count_modes(values, h) <= 1:
        return None
    lo, hi = 1.0, max_multiple
    for _ in range(40):
        mid = (lo + hi) / 2
        if count_modes(values, h * mid) > 1:
            lo = mid
        else:
            hi = mid
    return hi


def bimodality_coefficient(values: np.ndarray) -> float:
    """Sarle's BC. Reported so the report can show that it does not work here.

    BC = (g1^2 + 1) / (g2 + correction) reads only skew and kurtosis, so it is
    blind to any structure those two miss. Above 0.555 is the conventional flag.
    """
    n = len(values)
    g1 = float(stats.skew(values, bias=False))
    g2 = float(stats.kurtosis(values, bias=False))
    return (g1**2 + 1) / (g2 + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))


def floor_mass(values: np.ndarray, quantum: float | None) -> float:
    """Share of the pool piled within one reporting quantum of the minimum.

    A floor cluster is the mechanism behind most of the skew in the counting
    stats: players who simply do not do the thing. Zero when the column is
    continuous and has no reporting grid.
    """
    if quantum is None:
        return 0.0
    return float(np.count_nonzero(values <= values.min() + quantum) / len(values))


def assign_tier(
    skew: float,
    kurt: float,
    ks_max: float,
    crit_bw: float | None,
    floor: float,
    distinct: int,
) -> tuple[str, str]:
    """Effect size decides the verdict. No p-value reaches this function.

    At n=156 every one of the nine categories rejects Shapiro-Wilk, so a
    p-value separates none of them. These thresholds do.

    D is checked first and is not a worse C: it means the mean and SD do not
    describe the population at all, either because a second mode survives real
    smoothing, because the pool piles on a floor, or because the column is too
    discrete for a continuous test to mean anything.
    """
    if crit_bw is not None and crit_bw > CRITICAL_BANDWIDTH_TIER_D:
        return "D", f"second mode survives {crit_bw:.2f}x Silverman"
    if floor > FLOOR_MASS_TIER_D:
        return "D", f"{floor:.1%} of the pool sits on the floor"
    if distinct < MIN_DISTINCT_FOR_CONTINUOUS_TEST:
        return "D", f"only {distinct} distinct values — discreteness, not shape"
    if abs(skew) < TIER_A["skew"] and abs(kurt) < TIER_A["kurt"] and ks_max < TIER_A["ks"]:
        return "A", "within the conventional approximately-Normal band"
    if abs(skew) < TIER_B["skew"] and abs(kurt) < TIER_B["kurt"] and ks_max < TIER_B["ks"]:
        return "B", "skewed but usable; tail z's run optimistic"
    reasons = []
    if abs(skew) >= TIER_B["skew"]:
        reasons.append(f"|skew| {abs(skew):.2f}")
    if abs(kurt) >= TIER_B["kurt"]:
        reasons.append(f"|excess kurtosis| {abs(kurt):.2f}")
    if ks_max >= TIER_B["ks"]:
        reasons.append(f"percentile off by {ks_max:.1%}")
    return "C", ", ".join(reasons)


def analyse(name: str, values: np.ndarray, quantum: float | None = None) -> Normality:
    """Every measurement for one category, and the tier they add up to."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n < 20:
        raise ValueError(f"{name}: {n} observations is too few to say anything about shape")

    g1 = float(stats.skew(values, bias=False))
    g2 = float(stats.kurtosis(values, bias=False))
    w, w_p = stats.shapiro(values)
    k2, k2_p = stats.normaltest(values)
    a2, a2_p = anderson_darling(values)
    ks_max, at_z = ecdf_vs_normal(values)
    distinct = len(np.unique(np.round(values, 9)))
    floor = floor_mass(values, quantum)
    crit_bw = critical_bandwidth(values)
    tier, reason = assign_tier(g1, g2, ks_max, crit_bw, floor, distinct)

    q1, q3 = np.percentile(values, [25, 75])
    return Normality(
        name=name, n=n,
        mean=float(values.mean()), sd=float(values.std(ddof=1)),
        median=float(np.median(values)), iqr=float(q3 - q1),
        p05=float(np.percentile(values, 5)), p95=float(np.percentile(values, 95)),
        minimum=float(values.min()), maximum=float(values.max()),
        skew=g1, skew_se=skew_se(n), kurt=g2, kurt_se=kurt_se(n),
        shapiro_w=float(w), shapiro_p=float(w_p), sqrt_w=math.sqrt(float(w)),
        dagostino_k2=float(k2), dagostino_p=float(k2_p),
        anderson_a2=a2, anderson_p=a2_p,
        ks_max=ks_max, ecdf_at_z=at_z,
        distinct=distinct, floor_mass=floor,
        kde_modes=count_modes(values, silverman_bandwidth(values)),
        critical_bandwidth=crit_bw,
        bimodality_coefficient=bimodality_coefficient(values),
        tier=tier, tier_reason=reason,
    )
