"""Tests for the DURANT reconstruction.

Synthetic players throughout, per AGENTS.md: invented names, invented numbers.

These test that the reconstruction does what `docs/references/basketball-monster-durant.md`
says DURANT does. They cannot test that it matches DURANT, because DURANT's
coefficients are unpublished.
"""

from __future__ import annotations

import math

import pytest
from durant import (
    LAMBDA_HI,
    LAMBDA_LO,
    LLOYD_WEIGHTS,
    MINUS_ONE_REGIMES,
    apply_minus_one,
    build_durant_pool,
    durant_scores,
    durant_total,
    fit_lambda,
    raw_values,
    yeo_johnson,
    yj_loglik,
)
from valuation import CATEGORIES, Player, build_pool


def make(seed, name, **kw):
    base = dict(
        gp=70.0, fgm=6.0, fga=13.0, fgp=0.462, ftm=3.0, fta=4.0, ftp=0.750,
        tpm=2.0, pts=17.0, reb=5.0, ast=4.0, stl=1.0, blk=0.6, to=2.0,
    )
    base.update(kw)
    return Player(seed=seed, name=name, **base)


@pytest.fixture
def pool_and_players():
    players = [
        make(1, "Ada Bell", pts=27.0, reb=11.0, ast=9.0, blk=1.4, fga=19.0, fgp=0.540),
        make(2, "Bo Chen", pts=24.0, tpm=3.6, ast=6.0, stl=1.6, fta=6.0, ftp=0.880),
        make(3, "Cy Duarte", pts=13.0, reb=10.0, blk=2.4, fgp=0.590, fga=9.0, ftp=0.560),
        make(4, "Del Frost", pts=19.0, ast=7.5, to=3.4, stl=1.9, tpm=2.8),
        make(5, "Eli Gray", pts=9.0, reb=3.0, ast=2.0, stl=0.5, blk=0.1, to=0.9),
        make(6, "Fay Hollis", pts=15.0, reb=6.5, ast=3.0, blk=0.8, tpm=1.2, fgp=0.430),
        make(7, "Gus Imai", pts=11.0, reb=4.0, ast=5.5, stl=1.2, blk=0.3, to=1.6),
        make(8, "Hana Jost", pts=21.0, reb=7.0, ast=2.5, tpm=3.1, fgp=0.470),
    ]
    return build_pool(players, q=8, min_gp=25), players


# --- the transform itself -------------------------------------------------


@pytest.mark.parametrize("x", [-4.0, -1.5, -0.3, 0.0, 0.3, 1.5, 4.0])
def test_lambda_one_is_the_identity(x):
    assert yeo_johnson(x, 1.0) == pytest.approx(x)


@pytest.mark.parametrize("lam", [-3.0, -1.0, 0.0, 1.0, 2.0, 4.0])
def test_zero_maps_to_zero(lam):
    assert yeo_johnson(0.0, lam) == pytest.approx(0.0)


def test_the_two_limiting_cases_are_logarithms():
    # lambda = 0 on the positive side, lambda = 2 on the negative side.
    assert yeo_johnson(2.0, 0.0) == pytest.approx(math.log(3.0))
    assert yeo_johnson(-2.0, 2.0) == pytest.approx(-math.log(3.0))


@pytest.mark.parametrize("lam", [-3.0, -1.0, 0.0, 0.7, 2.0, 4.0])
def test_the_transform_is_monotone(lam):
    """Order within a category must survive. A transform that reordered players
    would not be normalising the scale, it would be changing the answer."""
    xs = [-3.0, -1.0, -0.2, 0.0, 0.2, 1.0, 3.0]
    out = [yeo_johnson(x, lam) for x in xs]
    assert out == sorted(out)


def test_fitting_pulls_a_skewed_sample_toward_symmetry():
    vals = [float(i) ** 2 / 40.0 for i in range(1, 61)]  # strongly right-skewed
    lam = fit_lambda(vals)
    t = [yeo_johnson(v, lam) for v in vals]

    def skew(v):
        m = sum(v) / len(v)
        s = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
        return sum(((x - m) / s) ** 3 for x in v) / len(v)

    assert abs(skew(t)) < abs(skew(vals))
    assert LAMBDA_LO < lam < LAMBDA_HI


def test_a_symmetric_sample_needs_almost_no_transform():
    vals = [float(i) for i in range(-30, 31)]
    assert fit_lambda(vals) == pytest.approx(1.0, abs=0.35)


def test_the_fitted_lambda_beats_its_neighbours():
    """The search must actually find the maximum, not merely a plausible value."""
    vals = [float(i) ** 1.7 / 10.0 for i in range(1, 51)]
    lam = fit_lambda(vals)
    best = yj_loglik(vals, lam)
    assert best >= yj_loglik(vals, lam - 0.05)
    assert best >= yj_loglik(vals, lam + 0.05)


def test_fitting_needs_more_than_one_value():
    with pytest.raises(ValueError, match="at least 2"):
        fit_lambda([1.0])


# --- pool fitting ---------------------------------------------------------


def test_every_category_gets_a_lambda(pool_and_players):
    pool, _ = pool_and_players
    dp = build_durant_pool(pool)
    assert set(dp.lam) == set(CATEGORIES)
    assert set(dp.mean) == set(CATEGORIES)
    assert set(dp.sd) == set(CATEGORIES)


def test_transformed_scores_are_standardised_over_the_pool(pool_and_players):
    pool, _ = pool_and_players
    dp = build_durant_pool(pool)
    for c in CATEGORIES:
        vals = [durant_scores(p, pool, dp)[c] for p in pool.members]
        assert sum(vals) / len(vals) == pytest.approx(0.0, abs=1e-9)


def test_turnovers_still_invert(pool_and_players):
    """The one category where less is better, after the transform as before it."""
    pool, players = pool_and_players
    dp = build_durant_pool(pool)
    careful = min(players, key=lambda p: p.to)
    careless = max(players, key=lambda p: p.to)
    assert durant_scores(careful, pool, dp)["to"] > durant_scores(careless, pool, dp)["to"]


def test_percentages_are_scored_on_impact_not_the_bare_rate(pool_and_players):
    """Shares `valuation.fg_impact`, so volume weighting is not re-derived here."""
    pool, _ = pool_and_players
    low_volume = make(9, "Ivy Kalu", fga=3.0, fgp=0.700)
    high_volume = make(10, "Jo Lantz", fga=18.0, fgp=0.700)
    assert raw_values(high_volume, pool)["fg"] > raw_values(low_volume, pool)["fg"]


# --- the minus-one rule ---------------------------------------------------


def test_h2h_removes_the_worst_category():
    s = {"pts": 1.0, "reb": 0.5, "blk": -2.0, "ast": 0.2}
    assert "blk" not in apply_minus_one(s, "h2h")
    assert len(apply_minus_one(s, "h2h")) == 3


def test_roto_halves_the_worst_category_instead_of_dropping_it():
    s = {"pts": 1.0, "reb": 0.5, "blk": -2.0}
    out = apply_minus_one(s, "roto")
    assert out["blk"] == pytest.approx(-1.0)
    assert out["pts"] == pytest.approx(1.0)
    assert len(out) == 3


def test_durant_h2h_drops_turnovers_then_the_next_worst():
    """Turnovers go unconditionally, even when they are not the worst category."""
    s = {"pts": 1.0, "to": 0.9, "reb": 0.5, "blk": -2.0}
    out = apply_minus_one(s, "durant_h2h")
    assert "to" not in out
    assert "blk" not in out
    assert set(out) == {"pts", "reb"}


def test_durant_h2h_drops_turnovers_even_when_they_are_the_worst():
    s = {"pts": 1.0, "to": -3.0, "reb": 0.5, "blk": -2.0}
    out = apply_minus_one(s, "durant_h2h")
    assert set(out) == {"pts", "reb"}


def test_none_leaves_every_category_alone():
    s = {"pts": 1.0, "reb": 0.5, "blk": -2.0}
    assert apply_minus_one(s, "none") == s


def test_minus_one_does_not_mutate_its_input():
    s = {"pts": 1.0, "reb": 0.5, "blk": -2.0}
    apply_minus_one(s, "roto")
    assert s["blk"] == -2.0


def test_an_unknown_regime_says_so():
    with pytest.raises(ValueError, match="unknown regime"):
        apply_minus_one({"pts": 1.0}, "durant_3.0")


@pytest.mark.parametrize("regime", MINUS_ONE_REGIMES)
def test_every_documented_regime_produces_a_number(pool_and_players, regime):
    pool, players = pool_and_players
    dp = build_durant_pool(pool)
    assert isinstance(durant_total(players[0], pool, dp, regime=regime), float)


# --- totals ---------------------------------------------------------------


def test_the_minus_one_rule_can_only_help_a_player(pool_and_players):
    """Dropping your worst category cannot lower your total. If it did, the rule
    would be picking the wrong category."""
    pool, players = pool_and_players
    dp = build_durant_pool(pool)
    for p in players:
        plain = durant_total(p, pool, dp, regime="none")
        h2h = durant_total(p, pool, dp, regime="h2h")
        roto = durant_total(p, pool, dp, regime="roto")
        assert h2h >= plain - 1e-9
        assert roto >= plain - 1e-9
        assert h2h >= roto - 1e-9  # dropping beats halving


def test_weights_scale_their_category(pool_and_players):
    pool, players = pool_and_players
    dp = build_durant_pool(pool)
    flat = dict.fromkeys(CATEGORIES, 1.0)
    zeroed = {**flat, "blk": 0.0}
    p = players[2]  # the shot blocker
    with_blk = durant_total(p, pool, dp, weights=flat, regime="none")
    without = durant_total(p, pool, dp, weights=zeroed, regime="none")
    assert with_blk != pytest.approx(without)
    assert without == pytest.approx(with_blk - durant_scores(p, pool, dp)["blk"])


def test_lloyd_weights_discount_the_low_volume_categories():
    """From article 1831: threes, steals and blocks weighted down; the rest not."""
    assert LLOYD_WEIGHTS["stl"] < 1.0
    assert LLOYD_WEIGHTS["blk"] < 1.0
    assert LLOYD_WEIGHTS["tpm"] < 1.0
    assert LLOYD_WEIGHTS["pts"] == 1.0
    assert LLOYD_WEIGHTS["reb"] == 1.0
