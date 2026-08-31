"""Tests for the Basketball Monster reference implementation.

All fixtures are hand-authored and synthetic. No provider data appears here, and none may
be added: this repository is public (ADR-0006). Expected values are computed by hand in
the test, not copied from a run of the code under test.
"""

import math
import statistics as st
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "bbm"))

import bbm_reference as B  # noqa: E402


def projection(games=70, minutes=2100, points=1400, threes=140, rebounds=350,
               assists=280, steals=70, blocks=35, turnovers=140,
               fg_made=520, fg_att=1100, ft_made=220, ft_att=280):
    return dict(games=games, minutes=minutes, points=points, threes=threes,
                rebounds=rebounds, assists=assists, steals=steals, blocks=blocks,
                turnovers=turnovers, fg_made=fg_made, fg_att=fg_att,
                ft_made=ft_made, ft_att=ft_att)


# --- step 1: per-game -------------------------------------------------------------

def test_per_game_divides_every_total_by_games():
    r = B.per_game(projection(games=50, points=1000, blocks=25))
    assert r["points"] == 20.0
    assert r["blocks"] == 0.5
    assert r["games"] == 50


def test_zero_games_is_excluded_not_divided():
    assert B.per_game(projection(games=0)) is None


def test_makes_and_attempts_are_kept_separate():
    r = B.per_game(projection(games=100, fg_made=500, fg_att=1000))
    assert r["fg_made"] == 5.0 and r["fg_att"] == 10.0


# --- step 2: the pool -------------------------------------------------------------

def test_counting_params_use_population_sd():
    pool = [{"points": 10.0, "threes": 0, "rebounds": 0, "assists": 0, "steals": 0,
             "blocks": 0, "turnovers": 0, "fg_made": 1, "fg_att": 2, "ft_made": 1,
             "ft_att": 2},
            {"points": 20.0, "threes": 0, "rebounds": 0, "assists": 0, "steals": 0,
             "blocks": 0, "turnovers": 0, "fg_made": 1, "fg_att": 2, "ft_made": 1,
             "ft_att": 2}]
    p = B.pool_params(pool)
    assert p["pV"]["mean"] == 15.0
    assert p["pV"]["sd"] == pytest.approx(st.pstdev([10.0, 20.0]))   # 5.0, not 7.07


def test_pool_percentage_rate_is_attempt_weighted_not_a_mean_of_rates():
    # 90% on 2 attempts and 40% on 8. Simple mean of rates = 65%.
    # Attempt-weighted = (1.8 + 3.2) / 10 = 50%.
    pool = [dict(points=0, threes=0, rebounds=0, assists=0, steals=0, blocks=0,
                 turnovers=0, fg_made=1.8, fg_att=2.0, ft_made=0, ft_att=1),
            dict(points=0, threes=0, rebounds=0, assists=0, steals=0, blocks=0,
                 turnovers=0, fg_made=3.2, fg_att=8.0, ft_made=0, ft_att=1)]
    p = B.pool_params(pool)
    assert p["fg%V"]["rate"] == pytest.approx(0.50)
    assert p["fg%V"]["rate"] != pytest.approx(0.65)


# --- step 3: the nine values ------------------------------------------------------

def _flat_params(mean, sd, rate=0.5, imean=0.0, isd=1.0):
    p = {}
    for key, name, sign in B.COUNTING:
        p[name] = {"kind": "counting", "key": key, "sign": sign, "mean": mean, "sd": sd}
    for made, att, name in B.PERCENTAGE:
        p[name] = {"kind": "percentage", "made": made, "att": att, "rate": rate,
                   "sign": +1, "mean": imean, "sd": isd}
    return p


def test_counting_value_is_a_plain_z_score():
    rates = {k: 0.0 for k in ("points", "threes", "rebounds", "assists", "steals",
                              "blocks", "turnovers", "fg_made", "fg_att",
                              "ft_made", "ft_att")}
    rates["points"] = 25.0
    v = B.category_values(rates, _flat_params(mean=15.0, sd=5.0))
    assert v["pV"] == pytest.approx((25.0 - 15.0) / 5.0)


def test_turnovers_are_inverted_and_nothing_else_is():
    base = {k: 0.0 for k in ("points", "threes", "rebounds", "assists", "steals",
                             "blocks", "turnovers", "fg_made", "fg_att",
                             "ft_made", "ft_att")}
    high_to = dict(base, turnovers=10.0)
    low_to = dict(base, turnovers=0.0)
    p = _flat_params(mean=5.0, sd=1.0)
    assert B.category_values(high_to, p)["toV"] < B.category_values(low_to, p)["toV"]
    high_pts = dict(base, points=10.0)
    assert B.category_values(high_pts, p)["pV"] > B.category_values(base, p)["pV"]


def test_percentage_value_is_volume_weighted_not_a_bare_rate():
    """80% on 4 attempts and 80% on 10 are not the same asset."""
    p = _flat_params(mean=0, sd=1, rate=0.50, imean=0.0, isd=1.0)
    base = {k: 0.0 for k in ("points", "threes", "rebounds", "assists", "steals",
                             "blocks", "turnovers", "fg_made", "fg_att")}
    low = dict(base, ft_att=4.0, ft_made=3.2)     # impact 3.2 - 2.0 = 1.2
    high = dict(base, ft_att=10.0, ft_made=8.0)   # impact 8.0 - 5.0 = 3.0
    assert B.category_values(low, p)["ft%V"] == pytest.approx(1.2)
    assert B.category_values(high, p)["ft%V"] == pytest.approx(3.0)


def test_shooting_exactly_pool_average_scores_zero_at_any_volume():
    p = _flat_params(mean=0, sd=1, rate=0.50, imean=0.0, isd=1.0)
    base = {k: 0.0 for k in ("points", "threes", "rebounds", "assists", "steals",
                             "blocks", "turnovers", "fg_made", "fg_att")}
    for att in (2.0, 20.0):
        r = dict(base, ft_att=att, ft_made=att * 0.50)
        assert B.category_values(r, p)["ft%V"] == pytest.approx(0.0)


def test_below_average_on_high_volume_hurts_more_than_on_low_volume():
    p = _flat_params(mean=0, sd=1, rate=0.50, imean=0.0, isd=1.0)
    base = {k: 0.0 for k in ("points", "threes", "rebounds", "assists", "steals",
                             "blocks", "turnovers", "fg_made", "fg_att")}
    low = dict(base, ft_att=2.0, ft_made=0.8)     # 40% on 2  -> -0.2
    high = dict(base, ft_att=20.0, ft_made=8.0)   # 40% on 20 -> -2.0
    assert B.category_values(high, p)["ft%V"] < B.category_values(low, p)["ft%V"]


# --- step 4: Value, Rank, Round ---------------------------------------------------

def test_value_is_the_mean_of_nine_not_the_sum():
    rates = {k: 0.0 for k in ("points", "threes", "rebounds", "assists", "steals",
                              "blocks", "turnovers", "fg_made", "fg_att",
                              "ft_made", "ft_att")}
    rates["points"] = 24.0
    p = _flat_params(mean=15.0, sd=3.0)   # pV = 3.0, the other eight are 0 or -5
    vals = B.category_values(rates, p)
    assert B.value(rates, p) == pytest.approx(sum(vals[c] for c in B.CATEGORIES) / 9)


def test_round_is_ceil_rank_over_teams():
    scores = {f"p{i}": -i for i in range(30)}
    rr = B.rank_and_round(scores, teams=12)
    assert rr["p0"] == (1, 1)
    assert rr["p11"] == (12, 1)
    assert rr["p12"] == (13, 2)
    assert rr["p24"] == (25, 3)


# --- the pool fixed point ---------------------------------------------------------

def test_build_pool_returns_q_players_and_converges():
    players = {}
    for i in range(40):
        players[f"p{i}"] = B.per_game(projection(points=700 + 40 * i, blocks=10 + i))
    pool, params = B.build_pool(players, q=20)
    assert len(pool) == 20
    again, _ = B.build_pool(players, q=20, seed_order=pool)
    assert set(again) == set(pool)          # already a fixed point


def test_pool_excludes_the_weakest_players():
    players = {}
    for i in range(30):
        players[f"p{i}"] = B.per_game(projection(points=100 * (i + 1)))
    pool, _ = B.build_pool(players, q=10)
    assert "p29" in pool and "p0" not in pool


# --- Yeo-Johnson -------------------------------------------------------------------

def test_yeo_johnson_lambda_one_is_the_identity_shifted():
    for x in (-3.0, 0.0, 2.5):
        assert B.yeo_johnson(x, 1.0) == pytest.approx(x)


def test_yeo_johnson_lambda_zero_is_a_log_on_the_positive_side():
    assert B.yeo_johnson(3.0, 0.0) == pytest.approx(math.log(4.0))


def test_yeo_johnson_is_monotone_increasing():
    for lam in (-1.7, 0.0, 0.5, 1.5):
        xs = [0.0, 0.5, 1.0, 3.0, 10.0]
        t = [B.yeo_johnson(x, lam) for x in xs]
        assert all(a < b for a, b in zip(t, t[1:], strict=False)), lam


def test_fit_lambda_recovers_a_known_transform():
    """Data built to be normal after a known lambda should fit back to roughly that lambda."""
    lam_true = 0.5
    normalish = [-1.6, -1.0, -0.6, -0.3, 0.0, 0.3, 0.6, 1.0, 1.6]
    # invert Yeo-Johnson at lam=0.5 to construct the raw scale
    raw = [((z * lam_true) + 1) ** (1 / lam_true) - 1 for z in normalish]
    assert B.fit_lambda(raw) == pytest.approx(lam_true, abs=0.35)


# --- DURANT ------------------------------------------------------------------------

def _durant_pool(n=40):
    players = {}
    for i in range(n):
        players[f"p{i}"] = B.per_game(projection(
            points=700 + 30 * i, blocks=5 + 2 * i, threes=40 + 5 * i,
            turnovers=200 - 2 * i, assists=100 + 8 * i))
    return players


def test_durant_drops_the_players_own_worst_category():
    players = _durant_pool()
    pool, params = B.build_durant_pool(players, 20, B.LAMBDAS_BBM_2026_27_JOSH)
    for key in list(players)[:5]:
        vals = B.durant_category_values(players[key], params)
        score, dropped = B.durant(players[key], params)
        assert dropped == min(B.CATEGORIES, key=lambda c: vals[c])
        kept = [vals[c] for c in B.CATEGORIES if c != dropped]
        assert score == pytest.approx(sum(kept) / 8)


def test_durant_h2h_zeroes_turnovers_and_averages_seven():
    players = _durant_pool()
    pool, params = B.build_durant_pool(players, 20, B.LAMBDAS_BBM_2026_27_JOSH)
    key = list(players)[3]
    score, dropped = B.durant_h2h(players[key], params)
    assert dropped != "toV"                          # turnovers never the named drop
    vals = B.durant_category_values(players[key], params)
    weighted = {c: vals[c] * B.H2H_WEIGHTS[c] for c in B.CATEGORIES}
    live = [c for c in B.CATEGORIES if B.H2H_WEIGHTS[c] != 0]
    kept = [weighted[c] for c in live if c != dropped]
    assert len(kept) == 7
    assert score == pytest.approx(sum(kept) / 7)


def test_h2h_weights_discount_the_right_categories():
    assert B.H2H_WEIGHTS["toV"] == 0.0
    assert B.H2H_WEIGHTS["pV"] == 1.0
    for c in ("3V", "sV", "bV", "fg%V", "ft%V"):
        assert B.H2H_WEIGHTS[c] == 0.60
    assert B.H2H_WEIGHTS["rV"] > B.H2H_WEIGHTS["aV"] > B.H2H_WEIGHTS["sV"]


# --- punt weights ------------------------------------------------------------------

def test_punt_weight_scales_only_the_punted_category():
    rates = B.per_game(projection())
    p = _flat_params(mean=10.0, sd=2.0)
    base = B.category_values(rates, p)
    punted = B.category_values(rates, p, punt_weights={"toV": 0.5})
    assert punted["toV"] == pytest.approx(base["toV"] * 0.5)
    for c in B.CATEGORIES:
        if c != "toV":
            assert punted[c] == pytest.approx(base[c])


def test_punt_denominator_stays_at_nine():
    rates = B.per_game(projection())
    p = _flat_params(mean=10.0, sd=2.0)
    punted = B.category_values(rates, p, punt_weights={"toV": 0.0})
    assert B.value(rates, p, punt_weights={"toV": 0.0}) == pytest.approx(
        sum(punted[c] for c in B.CATEGORIES) / 9)


# --- the input helpers -------------------------------------------------------------

def test_from_components_does_not_double_count_threes():
    """field_goals already includes threes: 400 FG of which 100 are threes, plus 150 FT."""
    row = {"games": 70, "minutes": 2100, "field_goals": 400, "threes": 100,
           "free_throws": 150, "offensive_rebounds": 100, "defensive_rebounds": 250,
           "assists": 200, "steals": 60, "blocks": 30, "turnovers": 120,
           "field_goals_attempted": 900, "free_throws_attempted": 180}
    proj = B.from_components(row)
    # 300 twos = 600, 100 threes = 300, 150 free throws = 150 -> 1050
    assert proj["points"] == 1050
    assert proj["rebounds"] == 350


def test_from_totals_with_percentages_rebuilds_makes():
    row = {"g": 70, "min": 2100, "pts": 1400, "3": 140, "reb": 350, "ast": 280,
           "stl": 70, "blk": 35, "to": 140, "fga": 1000, "fg%": 0.5,
           "fta": 200, "ft%": 0.8}
    proj = B.from_totals_with_percentages(row)
    assert proj["fg_made"] == pytest.approx(500.0)
    assert proj["ft_made"] == pytest.approx(160.0)
    assert proj["points"] == 1400          # taken directly, not derived
