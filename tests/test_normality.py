"""Pin the shape measurements, and the reading the report puts on them.

The report's central claim is that moment-based tests miss structure that matters
and flag structure that does not. That claim is only worth making if the code can
demonstrate it on samples whose answer is known in advance, which is what
`outlier_clusters` and `skewed_unimodal` are for -- one multimodal sample the
bimodality coefficient calls unimodal, and one unimodal sample it calls bimodal.

Samples are constructed, not sampled from the export. No player data (ADR-0006).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from normality import (
    CRITICAL_BANDWIDTH_TIER_D,
    MIN_DISTINCT_FOR_CONTINUOUS_TEST,
    analyse,
    assign_tier,
    bimodality_coefficient,
    count_modes,
    critical_bandwidth,
    ecdf_vs_normal,
    floor_mass,
    kurt_se,
    silverman_bandwidth,
    skew_se,
)


@pytest.fixture
def symmetric() -> np.ndarray:
    """A clean bell, built by inverting the Normal CDF on an even grid.

    Deterministic, so a failure is a real change and never a reseed.
    """
    from scipy import stats

    q = (np.arange(1, 201) - 0.5) / 200
    return stats.norm.ppf(q)


@pytest.fixture
def outlier_clusters() -> np.ndarray:
    """A body with a small detached group at each end: the shape BC cannot see.

    The clusters are symmetric, so skew stays at 0, and they are far enough out to
    drive excess kurtosis up near +10. BC divides by that kurtosis, so a genuinely
    multimodal sample reads ~0.08 -- far *below* the 0.555 flag, i.e. "unimodal".
    This is FT% impact's failure mode in miniature.
    """
    from scipy import stats

    body = stats.norm.ppf((np.arange(1, 189) - 0.5) / 188)
    return np.concatenate([body, np.full(6, -10.0), np.full(6, 10.0)])


@pytest.fixture
def skewed_unimodal() -> np.ndarray:
    """Plain right skew with light tails: the shape BC flags when it should not.

    Squaring a uniform gives skew ~0.64 with excess kurtosis ~-0.85. The negative
    kurtosis shrinks BC's denominator, so it reads ~0.64 -- above the flag -- for
    a distribution with exactly one mode. REB does this on the real pool.
    """
    q = (np.arange(1, 201) - 0.5) / 200
    return q**2.0


@pytest.fixture
def left_bounded() -> np.ndarray:
    """Exponential quantiles: right-skewed against a hard floor, like BLK.

    For an exponential the mean equals the SD, so "one SD below the mean" lands on
    the boundary and almost nothing can sit below it. That is why BLK's empirical
    mass at z = -1 is a few percent where a Normal promises 15.9%.
    """
    q = (np.arange(1, 201) - 0.5) / 200
    return -np.log(1 - q)


@pytest.fixture
def floored() -> np.ndarray:
    """A quarter of the sample piled on zero, the rest fanning right."""
    return np.concatenate([np.zeros(50), np.linspace(0.2, 4.0, 150)])


class TestStandardErrors:
    def test_skew_se_matches_the_closed_form(self):
        n = 156
        assert skew_se(n) == pytest.approx(
            math.sqrt(6 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3))), abs=1e-12
        )

    def test_the_asymptotic_shortcut_is_close_but_not_equal(self):
        """sqrt(6/n) is the n->infinity limit and runs ~1% wide at this n.

        Worth pinning because the gap is small: it rules out the tempting story
        that Jarque-Bera and D'Agostino-Pearson disagree because of their standard
        errors. They do not. JB is excluded for its chi-square null, not this.
        """
        exact, asymptotic = skew_se(156), math.sqrt(6 / 156)
        assert exact < asymptotic
        assert asymptotic / exact == pytest.approx(1.0, abs=0.02)

    def test_kurt_se_matches_the_closed_form(self):
        n = 156
        expected = math.sqrt(4 * (n**2 - 1) * skew_se(n) ** 2 / ((n - 3) * (n + 5)))
        assert kurt_se(n) == pytest.approx(expected, abs=1e-12)


class TestBimodalityCoefficientIsWrongInBothDirections:
    """The report's headline, pinned so nobody 'simplifies' these away.

    BC is a deterministic function of skew and kurtosis. These two tests assert
    NEGATIVE results on purpose: if someone later turns BC into a working
    detector, both should fail and make them justify it.
    """

    def test_it_reads_unimodal_on_a_sample_that_plainly_is_not(self, outlier_clusters):
        assert bimodality_coefficient(outlier_clusters) < 0.555

    def test_the_density_does_see_that_sample(self, outlier_clusters):
        assert count_modes(outlier_clusters, silverman_bandwidth(outlier_clusters)) > 1
        crit = critical_bandwidth(outlier_clusters)
        assert crit is not None and crit > CRITICAL_BANDWIDTH_TIER_D

    def test_it_reads_bimodal_on_plain_right_skew(self, skewed_unimodal):
        assert bimodality_coefficient(skewed_unimodal) > 0.555

    def test_the_density_calls_that_sample_unimodal(self, skewed_unimodal):
        assert count_modes(skewed_unimodal, silverman_bandwidth(skewed_unimodal)) == 1
        assert critical_bandwidth(skewed_unimodal) is None

    def test_a_normal_sample_reports_no_critical_bandwidth(self, symmetric):
        assert critical_bandwidth(symmetric) is None


class TestFloorMass:
    def test_a_floor_cluster_is_measured(self, floored):
        """One quantum above the minimum is inside the floor, so 0.0 and 0.1 count."""
        assert floor_mass(floored, 0.1) == pytest.approx(50 / 200, abs=1e-9)

    def test_a_continuous_column_has_no_floor(self, symmetric):
        """Without a reporting grid there is no floor to pile on."""
        assert floor_mass(symmetric, None) == 0.0


class TestEcdfVsNormal:
    def test_a_normal_sample_sits_close_to_its_own_cdf(self, symmetric):
        ks_max, _ = ecdf_vs_normal(symmetric)
        assert ks_max < 0.02

    def test_the_ecdf_at_minus_one_is_near_the_textbook_share(self, symmetric):
        _, at_z = ecdf_vs_normal(symmetric)
        assert at_z[-1.0] == pytest.approx(0.159, abs=0.02)

    def test_a_left_bounded_sample_is_far_below_the_textbook_share(self, left_bounded):
        """The measurement that earns its place: BLK's real failure looks like this.

        A Normal promises 15.9% of the pool below z = -1. Against a hard floor
        almost nobody is there, so every "he is a standard deviation below
        average" reading in that category is quoting a probability that does
        not exist.
        """
        _, at_z = ecdf_vs_normal(left_bounded)
        assert at_z[-1.0] < 0.05

    def test_a_flat_sample_is_refused_rather_than_divided_by_zero(self):
        with pytest.raises(ValueError, match="zero spread"):
            ecdf_vs_normal(np.full(50, 3.0))


class TestTierRubric:
    """The thresholds are the report's verdict. Editing one must fail a test."""

    NORMAL = dict(skew=0.0, kurt=0.0, ks_max=0.0, crit_bw=None, floor=0.0, distinct=100)

    def test_a_clean_sample_is_tier_a(self):
        assert assign_tier(**self.NORMAL)[0] == "A"

    @pytest.mark.parametrize(
        "field,value,tier",
        [
            ("skew", 0.49, "A"), ("skew", 0.5, "B"), ("skew", 0.99, "B"), ("skew", 1.0, "C"),
            ("kurt", 0.99, "A"), ("kurt", 1.0, "B"), ("kurt", 1.99, "B"), ("kurt", 2.0, "C"),
            ("ks_max", 0.049, "A"), ("ks_max", 0.05, "B"),
            ("ks_max", 0.099, "B"), ("ks_max", 0.10, "C"),
        ],
    )
    def test_each_threshold_sits_exactly_where_it_is_documented(self, field, value, tier):
        assert assign_tier(**{**self.NORMAL, field: value})[0] == tier

    def test_a_surviving_second_mode_is_tier_d_however_good_the_moments(self):
        """D is not a worse C. It says mean and SD do not describe the population."""
        tier, reason = assign_tier(**{**self.NORMAL, "crit_bw": 1.51})
        assert tier == "D"
        assert "second mode" in reason

    def test_a_second_mode_that_smooths_away_is_not_tier_d(self):
        assert assign_tier(**{**self.NORMAL, "crit_bw": 1.49})[0] == "A"

    def test_a_heavy_floor_is_tier_d(self):
        tier, reason = assign_tier(**{**self.NORMAL, "floor": 0.101})
        assert tier == "D"
        assert "floor" in reason

    def test_too_few_distinct_values_is_tier_d_and_says_so(self):
        """STL fails on discreteness, not shape. The reason must not read as skew."""
        tier, reason = assign_tier(
            **{**self.NORMAL, "distinct": MIN_DISTINCT_FOR_CONTINUOUS_TEST - 1}
        )
        assert tier == "D"
        assert "discreteness" in reason

    def test_the_distinct_gate_is_inclusive_at_its_documented_value(self):
        at_gate = {**self.NORMAL, "distinct": MIN_DISTINCT_FOR_CONTINUOUS_TEST}
        assert assign_tier(**at_gate)[0] == "A"


class TestAnalyse:
    def test_a_normal_sample_comes_back_tier_a(self, symmetric):
        assert analyse("synthetic", symmetric).tier == "A"

    def test_a_multimodal_sample_comes_back_tier_d(self, outlier_clusters):
        r = analyse("synthetic", outlier_clusters)
        assert r.tier == "D"
        assert r.kde_modes > 1
        assert r.bimodality_coefficient < 0.555  # and BC still says otherwise

    def test_sqrt_w_stands_in_for_the_qq_correlation(self, symmetric):
        """Filliben's r is omitted because it is this number. Keep them tied."""
        r = analyse("synthetic", symmetric)
        assert r.sqrt_w == pytest.approx(math.sqrt(r.shapiro_w), abs=1e-12)

    def test_a_discrete_column_is_flagged_as_invalid_for_continuous_tests(self):
        values = np.repeat(np.arange(1, 11) / 10.0, 20)  # 10 distinct values, n=200
        assert not analyse("synthetic", values, quantum=0.1).continuous_test_valid

    def test_too_small_a_sample_is_refused_rather_than_answered(self):
        with pytest.raises(ValueError, match="too few"):
            analyse("synthetic", np.arange(10, dtype=float))
