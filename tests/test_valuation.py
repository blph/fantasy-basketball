"""The valuation math, checked against hand-authored synthetic players.

Every player here is invented. Nothing in this file comes from a provider export
(ADR-0006), and the numbers are chosen to make one property visible at a time
rather than to look like a real NBA season.
"""

import pytest
from valuation import (
    MULTIPLIERS,
    Player,
    adjusted_value,
    build_pool,
    converge_pool,
    fg_impact,
    g_scores,
    g_total,
    punt_total,
    replacement,
    z_scores,
    z_total,
)

Q = 6
MIN_GP = 25


def make(seed, name, **over):
    """A deliberately flat baseline; each test perturbs one thing.

    Rates are derived from makes and attempts rather than passed in, so the
    identity the impact column depends on holds exactly. A provider that rounds
    its rate independently breaks that; `test_rounded_rates_leave_a_residual`
    covers what happens then.
    """
    base = dict(
        gp=70.0, fgm=5.0, fga=10.0, ftm=2.0, fta=2.5,
        tpm=2.0, pts=15.0, reb=5.0, ast=4.0, stl=1.0, blk=0.5, to=2.0,
    )
    base.update(over)
    base.setdefault("fgp", base["fgm"] / base["fga"])
    base.setdefault("ftp", base["ftm"] / base["fta"])
    return Player(seed=seed, name=name, **base)


@pytest.fixture
def pool_and_players():
    """Six in-pool players with enough spread to give every category an SD."""
    players = [
        make(1, "Ada Vance", pts=24.0, reb=8.0, ast=7.0, stl=1.8, blk=1.2,
             to=3.4, fgm=9.0, fga=17.0),
        make(2, "Bo Ferrant", pts=20.0, reb=4.0, ast=9.0, stl=1.5, blk=0.3,
             to=3.0, ftm=5.0, fta=5.5),
        make(3, "Cyd Molnar", pts=12.0, reb=11.0, ast=1.5, stl=0.6, blk=2.4,
             to=1.6, fgm=5.5, fga=8.5, ftm=1.2, fta=2.6),
        make(4, "Dee Okonkwo", pts=17.0, reb=6.0, ast=3.0, stl=1.1, blk=0.7,
             to=2.2, tpm=3.4),
        make(5, "Efe Larsson", pts=9.0, reb=3.0, ast=2.0, stl=0.9, blk=0.2,
             to=1.1, tpm=1.2),
        make(6, "Fia Brennan", pts=14.0, reb=7.0, ast=5.0, stl=1.3, blk=0.9, to=2.6),
    ]
    return build_pool(players, Q, MIN_GP), players


def test_pool_rate_is_aggregate_not_average_of_rates(pool_and_players):
    """The trap: averaging percentages counts a 3-shot night like an 18-shot one."""
    pool, players = pool_and_players
    naive = sum(p.fgp for p in players) / len(players)
    assert pool.fg_pct != pytest.approx(naive)
    assert pool.fg_pct == pytest.approx(
        sum(p.fgm for p in players) / sum(p.fga for p in players)
    )


def test_impact_column_has_mean_exactly_zero(pool_and_players):
    """Why the board can skip mean-centring the percentage z-scores.

    Because the pool rate is the attempt-weighted aggregate, the impact column
    sums to zero identically. Divide by its SD and you already have a z-score.
    """
    pool, players = pool_and_players
    assert sum(fg_impact(p, pool) for p in players) == pytest.approx(0.0, abs=1e-9)


def test_rounded_rates_leave_a_residual(pool_and_players):
    """The one caveat on the zero-mean identity, pinned so it stays known.

    The identity holds because the pool rate is total makes over total attempts.
    If a provider publishes a rate rounded independently of its own makes and
    attempts, the column no longer nets to zero. The residual is small and the
    board tolerates it, but it is not nothing, and it is why the Settings
    Z-total sanity check reads "approximately 0" rather than "0".
    """
    pool, _ = pool_and_players
    rounded = [
        make(1, "Ada Vance", fgm=9.0, fga=17.0, fgp=0.529),  # 9/17 = 0.5294...
        make(2, "Bo Ferrant", fgm=5.5, fga=8.5, fgp=0.647),  # 5.5/8.5 = 0.6470...
    ]
    residual = sum(fg_impact(p, pool) for p in rounded)
    exact = sum(fg_impact(make(p.seed, p.name, fgm=p.fgm, fga=p.fga), pool) for p in rounded)
    assert residual != pytest.approx(exact, abs=1e-12)
    assert abs(residual - exact) < 0.05  # small, but real


def test_percentage_value_scales_with_volume(pool_and_players):
    """Same shooting edge, more attempts, more value."""
    pool, _ = pool_and_players
    low = make(1, "Gil Ashworth", fgm=3.0, fga=5.0)
    high = make(1, "Hana Ibori", fgm=12.0, fga=20.0)
    assert fg_impact(high, pool) > fg_impact(low, pool) > 0


def test_turnovers_invert(pool_and_players):
    """Fewer turnovers is better, and the flip happens exactly once."""
    pool, _ = pool_and_players
    careful = make(1, "Ivo Renn", to=0.5)
    loose = make(1, "Jae Pulliam", to=5.0)
    assert z_scores(careful, pool)["to"] > z_scores(loose, pool)["to"]


def test_steals_are_discounted_hardest(pool_and_players):
    """The headline G-score effect: a steals edge converts to wins least often."""
    pool, _ = pool_and_players
    assert MULTIPLIERS["stl"] == min(MULTIPLIERS.values())
    assert MULTIPLIERS["ast"] == max(MULTIPLIERS.values())

    specialist = make(1, "Kit Vasquez", stl=3.0)
    z, g = z_scores(specialist, pool), g_scores(specialist, pool)
    assert g["stl"] < z["stl"]  # discounted, because it is noisy
    assert g["stl"] == pytest.approx(z["stl"] * MULTIPLIERS["stl"])


def test_z_total_over_pool_sums_to_zero(pool_and_players):
    """z is measured against the pool, so the pool nets out."""
    pool, players = pool_and_players
    assert sum(z_total(p, pool) for p in players) == pytest.approx(0.0, abs=1e-9)


def test_replacement_is_the_last_drafted_player(pool_and_players):
    pool, players = pool_and_players
    totals = sorted((g_total(p, pool) for p in players), reverse=True)
    assert replacement(players, pool, Q) == pytest.approx(totals[Q - 1])
    assert replacement(players, pool, 1) == pytest.approx(max(totals))


class TestAdjustedValue:
    """Availability may discount a player and must never promote one."""

    def test_above_replacement_scales_linearly(self):
        assert adjusted_value(2.0, 36.0, 72.0) == pytest.approx(1.0)
        assert adjusted_value(2.0, 72.0, 72.0) == pytest.approx(2.0)

    def test_missing_games_costs_value(self):
        durable = adjusted_value(1.0, 74.0, 72.0)
        fragile = adjusted_value(1.0, 41.0, 72.0)
        assert durable > fragile

    def test_below_replacement_does_not_invert(self):
        """The defect this floor exists to prevent.

        Two equally bad players; the one who plays less must not sort higher.
        Without the floor, -0.35 x 41/72 = -0.199 beats -0.35 x 74/72 = -0.360.
        """
        available = adjusted_value(-0.35, 74.0, 72.0)
        fragile = adjusted_value(-0.35, 41.0, 72.0)
        assert fragile <= available
        assert fragile == pytest.approx(-0.35)

    def test_unfloored_form_would_have_inverted(self):
        """Pin the old behaviour so nobody reintroduces it."""
        old = lambda vor, gp: vor * gp / 72.0  # noqa: E731
        assert old(-0.35, 41.0) > old(-0.35, 74.0)


class TestPunts:
    def test_weight_zero_is_a_hard_punt(self, pool_and_players):
        """PUNT_WEIGHT = 0 reproduces the board's original behaviour exactly."""
        pool, _ = pool_and_players
        p = make(1, "Lena Ostrow", ftm=1.0, fta=4.0)
        hard = punt_total(p, pool, ["ft"], 0.0)
        assert hard == pytest.approx(g_total(p, pool) - g_scores(p, pool)["ft"])

    def test_weight_one_changes_nothing(self, pool_and_players):
        pool, _ = pool_and_players
        p = make(1, "Mo Delacroix")
        assert punt_total(p, pool, ["ft"], 1.0) == pytest.approx(g_total(p, pool))

    def test_soft_punt_still_separates_bad_from_neutral(self, pool_and_players):
        """Why soft-punting is the better default in Each Category.

        A hard punt rates an actively terrible free-throw shooter identically to
        a neutral one, because both contribute zero. They are not the same bet:
        the weeks you win a punted category by accident are pure profit.
        """
        pool, _ = pool_and_players
        awful = make(1, "Nils Baptiste", ftm=1.0, fta=4.0)
        neutral = make(1, "Ode Marchetti", ftm=2.0, fta=2.5)

        hard_gap = punt_total(neutral, pool, ["ft"], 0.0) - punt_total(awful, pool, ["ft"], 0.0)
        soft_gap = punt_total(neutral, pool, ["ft"], 0.25) - punt_total(awful, pool, ["ft"], 0.25)
        assert hard_gap == pytest.approx(0.0, abs=1e-9)
        assert soft_gap > 0.0

    def test_multi_category_punt_drops_every_named_term(self, pool_and_players):
        pool, _ = pool_and_players
        p = make(1, "Pia Renwick")
        g = g_scores(p, pool)
        got = punt_total(p, pool, ["fg", "ft", "to"], 0.0)
        assert got == pytest.approx(g_total(p, pool) - g["fg"] - g["ft"] - g["to"])


class TestConvergence:
    """The pool is "the top Q by value", which needs values to know who they are.

    Seeding from the provider's rank breaks that circle for one pass; re-seeding
    from the result and repeating closes it.
    """

    def _mixed(self):
        """Eight players whose provider rank disagrees with their actual value.

        The seed order is deliberately wrong so the first pass picks a different
        four than the settled answer does.
        """
        specs = [
            (1, "Rui Castellan", dict(pts=6.0, reb=2.0, ast=1.0, tpm=0.4, stl=0.3,
                                      blk=0.1, to=0.8, fgm=2.0, fga=6.0, ftm=1.0, fta=1.6)),
            (2, "Sami Delacroix", dict(pts=7.0, reb=2.5, ast=1.5, tpm=0.9, stl=0.5,
                                       blk=0.2, to=1.1, fgm=3.0, fga=7.0, ftm=1.4, fta=2.0)),
            (3, "Tomas Belghazi", dict(pts=8.0, reb=3.0, ast=2.0, tpm=1.3, stl=0.6,
                                       blk=0.4, to=1.4, fgm=3.5, fga=9.0, ftm=1.8, fta=2.9)),
            (4, "Ute Fairbairn", dict(pts=9.0, reb=3.5, ast=2.5, tpm=1.7, stl=0.8,
                                      blk=0.6, to=1.7, fgm=4.0, fga=8.0, ftm=2.2, fta=2.6)),
            (5, "Vero Anand", dict(pts=26.0, reb=11.0, ast=8.0, tpm=3.1, stl=1.7,
                                   blk=1.4, to=3.6, fgm=10.0, fga=18.0, ftm=5.5, fta=6.2)),
            (6, "Wen Oyelaran", dict(pts=24.0, reb=10.0, ast=7.0, tpm=2.8, stl=1.5,
                                     blk=1.1, to=3.2, fgm=9.0, fga=17.0, ftm=4.8, fta=7.1)),
            (7, "Xan Petrosyan", dict(pts=22.0, reb=9.5, ast=6.5, tpm=2.4, stl=1.3,
                                      blk=0.9, to=2.9, fgm=8.5, fga=16.0, ftm=4.0, fta=4.7)),
            (8, "Yara Nakashima", dict(pts=21.0, reb=9.0, ast=6.0, tpm=2.1, stl=1.1,
                                       blk=0.8, to=2.6, fgm=8.0, fga=15.0, ftm=3.6, fta=5.5)),
        ]
        return [make(seed, name, **kw) for seed, name, kw in specs]

    def test_it_settles_and_reports_the_pass_count(self):
        pool, passes = converge_pool(self._mixed(), 4, MIN_GP)
        assert len(pool.members) == 4
        assert passes >= 2  # a first pass, then at least one confirming it

    def test_it_finds_the_actually_best_players(self):
        """The four strongest end up in the pool despite being seeded last."""
        pool, _ = converge_pool(self._mixed(), 4, MIN_GP)
        assert {m.name for m in pool.members} == {
            "Vero Anand", "Wen Oyelaran", "Xan Petrosyan", "Yara Nakashima"
        }

    def test_a_single_pass_gets_it_wrong(self):
        """Why the loop exists: one pass just trusts the provider's ordering."""
        players = self._mixed()
        first = build_pool(players, 4, MIN_GP)
        assert {m.name for m in first.members} != {
            "Vero Anand", "Wen Oyelaran", "Xan Petrosyan", "Yara Nakashima"
        }

    def test_it_is_idempotent_once_settled(self):
        """Running it again on a converged set changes nothing."""
        players = self._mixed()
        pool_a, _ = converge_pool(players, 4, MIN_GP)
        pool_b, passes_b = converge_pool(players, 4, MIN_GP)
        assert {m.name for m in pool_a.members} == {m.name for m in pool_b.members}
        assert pool_a.fg_pct == pytest.approx(pool_b.fg_pct)
        assert passes_b >= 2

    def test_it_raises_rather_than_silently_capping(self):
        """A pool that will not settle is a finding, not something to truncate."""
        with pytest.raises(ValueError, match="did not settle"):
            converge_pool(self._mixed(), 4, MIN_GP, max_passes=1)


def test_a_pool_with_no_shooting_spread_says_so():
    """The degenerate case fails with a sentence, not a ZeroDivisionError."""
    flat = [make(i, f"Clone {i}") for i in range(1, 6)]
    with pytest.raises(ValueError, match="zero spread"):
        build_pool(flat, 4, MIN_GP)


def test_min_gp_gate_excludes_from_the_pool():
    """A player below MIN_GP does not vote on what "average" means."""
    players = [
        make(i, f"Player {i}", fgm=3.0 + i, fga=8.0 + i, ftm=1.0 + i * 0.4, fta=2.0 + i * 0.5,
             pts=10.0 + i, reb=3.0 + i * 0.5, ast=2.0 + i * 0.3, tpm=1.0 + i * 0.2,
             stl=0.5 + i * 0.1, blk=0.3 + i * 0.2, to=1.0 + i * 0.3)
        for i in range(1, 6)
    ]
    players.append(make(6, "Quin Alvarado", gp=10.0, pts=99.0))
    pool = build_pool(players, Q, MIN_GP)
    assert len(pool.members) == 5
    assert all(m.name != "Quin Alvarado" for m in pool.members)
