"""Pin that the analysis measures what the board values, over the board's pool.

Two ways this could go quietly wrong and both are what the module exists to
prevent: measuring FG%/FT% as rates instead of volume-weighted impact, and
measuring all 200 export rows instead of the pool the z-scores are built over.

Synthetic players throughout (ADR-0006).
"""

from __future__ import annotations

import numpy as np
import pytest
from category_series import LOWER_IS_BETTER, QUANTUM, label, series
from valuation import CATEGORIES, Player, build_pool, fg_impact, ft_impact


def make(seed: int, name: str, **over) -> Player:
    """A baseline player, with makes *derived* from attempts and rate.

    The pool rate is the aggregate `sum(makes)/sum(attempts)`, so the impact
    column only sums to zero when each player's own rate agrees with his makes
    and attempts. Passing all three independently breaks that identity in the
    fixture and would make a real regression indistinguishable from a typo. The
    live export does break it, slightly, because the provider rounds its rates --
    that residual is pinned in `test_valuation.py`, not here.
    """
    base = dict(
        gp=70.0, fga=12.0, fgp=0.500, fta=4.0, ftp=0.750,
        tpm=1.5, pts=16.0, reb=5.0, ast=3.0, stl=1.0, blk=0.5, to=2.0,
    )
    base.update(over)
    base["fgm"] = base["fga"] * base["fgp"]
    base["ftm"] = base["fta"] * base["ftp"]
    return Player(seed=seed, name=name, **base)


@pytest.fixture
def pool_and_players():
    """Six players, two of them outside the pool -- one by seed, one by GP."""
    # Every counting stat has to vary across the pool: build_pool refuses to
    # standardise a category whose members are all identical, and rightly so.
    players = [
        make(1, "Ambrose Quill", fga=18.0, fgp=0.560, fta=7.0, ftp=0.880,
             tpm=2.6, pts=27.0, reb=9.0, ast=6.0, stl=1.7, blk=2.4, to=3.4),
        make(2, "Bertram Vole", fga=14.0, fgp=0.470, fta=5.0, ftp=0.640,
             tpm=0.4, pts=18.0, reb=7.5, ast=2.1, stl=0.8, blk=0.2, to=2.6),
        make(3, "Cordelia Frost", fga=10.0, fgp=0.520, fta=2.0, ftp=0.910,
             tpm=2.1, pts=12.0, reb=3.2, ast=4.4, stl=1.3, blk=1.1, to=1.5),
        make(4, "Dorian Peake", fga=8.0, fgp=0.430, fta=3.0, ftp=0.700,
             tpm=1.0, pts=9.5, reb=4.1, ast=1.6, stl=0.6, blk=0.3, to=1.1),
        make(5, "Evadne Marsh", fga=12.0, fgp=0.500, fta=4.0, ftp=0.750, gp=10.0),
        make(9, "Fenwick Lowe", fga=13.0, fgp=0.505, fta=4.5, ftp=0.760),
    ]
    return build_pool(players, q=5, min_gp=25), players


class TestSeries:
    def test_it_returns_all_nine_categories(self, pool_and_players):
        pool, _ = pool_and_players
        assert set(series(pool)) == set(CATEGORIES)

    def test_fg_and_ft_are_impact_and_not_the_rate(self, pool_and_players):
        """The whole point. A bare rate here would be silently wrong (AGENTS.md)."""
        pool, _ = pool_and_players
        s = series(pool)
        assert s["fg"] == pytest.approx(
            [fg_impact(p, pool) for p in pool.members], abs=1e-12
        )
        assert s["ft"] == pytest.approx(
            [ft_impact(p, pool) for p in pool.members], abs=1e-12
        )

    def test_the_fg_series_is_not_the_fg_rate(self, pool_and_players):
        """Guards the specific regression: impact and rate are different columns."""
        pool, _ = pool_and_players
        assert not np.allclose(series(pool)["fg"], [p.fgp for p in pool.members])

    def test_the_impact_columns_sum_to_zero_over_the_pool(self, pool_and_players):
        """The identity that lets the board divide by SD with no centring term.

        Exact here because these fixtures carry exact rates; the real export
        rounds its rates and leaves a small residual instead.
        """
        pool, _ = pool_and_players
        assert series(pool)["fg"].sum() == pytest.approx(0.0, abs=1e-9)
        assert series(pool)["ft"].sum() == pytest.approx(0.0, abs=1e-9)

    def test_it_covers_the_pool_and_not_every_ranked_player(self, pool_and_players):
        """Seed 9 is outside Q and Evadne is under MIN_GP; neither is measured."""
        pool, players = pool_and_players
        assert len(series(pool)["pts"]) == len(pool.members) == 4
        assert len(players) == 6

    def test_counting_stats_come_through_as_reported(self, pool_and_players):
        """TO is measured as reported. The valuation inverts it; this does not."""
        pool, _ = pool_and_players
        assert series(pool)["to"] == pytest.approx([p.to for p in pool.members], abs=1e-12)


class TestMetadata:
    def test_every_category_declares_a_quantum(self):
        assert set(QUANTUM) == set(CATEGORIES)

    def test_the_impacts_have_no_reporting_grid(self):
        """They are constructions, so there is no floor for players to pile on."""
        assert QUANTUM["fg"] is None and QUANTUM["ft"] is None

    def test_the_counting_stats_are_on_the_providers_tenth(self):
        assert all(QUANTUM[c] == 0.1 for c in CATEGORIES if c not in ("fg", "ft"))

    def test_only_turnovers_are_lower_is_better(self):
        assert LOWER_IS_BETTER == {"to"}

    def test_the_percentage_labels_say_they_are_impact(self):
        """A chart titled "FG%" over impact values would misread as a rate."""
        assert label("fg") == "FG% impact"
        assert label("ft") == "FT% impact"
        assert label("blk") == "BLK"
