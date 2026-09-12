"""Recovering standardisation constants from published value columns.

The test that matters here is the round trip: generate value columns from constants that
are deliberately NOT the pool's own and NOT the module's seed, round them to two decimals
the way Basketball Monster's page does, and fit them back. A fitter that only works when
the answer happens to match the pool -- or that quietly returns its seed -- is not
recovering anything, and that is precisely the failure that would leave the board looking
calibrated while it drifted (ADR-0021).

Fixtures are synthetic (ADR-0006). Nothing here is Basketball Monster's data: the
"published" columns are computed from invented players and invented constants.
"""

import math

import bbm_reference as B
import calibrate_bbm as C
import pytest

from test_board_values import spread

PUBLISHED_PLACES = 2


def invented_params(pool, seed=0.0):
    """Constants unlike anything this pool would produce, and unlike the module's seed.

    Shifted by a third of an SD and stretched by a tenth -- far larger than the 1-3% gap
    the real bug turned on, so a fitter that ignored its inputs could not pass by accident.
    """
    _, plain = B.build_pool(pool, 20)
    _, durant = B.build_durant_pool(pool, 20, B.LAMBDAS_BBM_2026_27_JOSH)
    for i, block in enumerate((plain, durant)):
        for j, spec in enumerate(block.values()):
            wobble = 0.06 * math.sin(seed + i * 1.7 + j * 0.9)
            spec["mean"] += (0.33 + wobble) * spec["sd"]
            spec["sd"] *= 1.10 + wobble
    return plain, durant


def invented_lambdas(seed=0.0):
    return {c: round(B.LAMBDAS_BBM_2026_27_JOSH[c] + 0.18 * math.cos(seed + i * 1.3), 4)
            for i, c in enumerate(B.CATEGORIES)}


def publish(pool, plain, durant, lambdas):
    """What their page would show for these players under these constants."""
    for spec in durant.values():
        spec["lam"] = lambdas[spec_name(durant, spec)]
    out = {}
    for k, r in pool.items():
        row = {}
        for cat, v in B.category_values(r, plain).items():
            row[C.PLAIN_COL[cat]] = round(v, PUBLISHED_PLACES)
        for cat, v in B.durant_category_values(r, durant).items():
            row[C.DURANT_COL[cat]] = round(v, PUBLISHED_PLACES)
        out[k] = row
    return out


def spec_name(block, spec):
    return next(c for c, s in block.items() if s is spec)


class TestRoundTrip:
    @pytest.mark.parametrize("seed", [0.0, 2.1])
    def test_it_recovers_constants_it_did_not_derive(self, seed):
        pool = spread(120)
        plain, durant = invented_params(pool, seed)
        lambdas = invented_lambdas(seed)
        published = publish(pool, plain, durant, lambdas)

        params, got_lam, _ = C.calibrate(pool, published, sorted(pool),
                                         B.LAMBDAS_BBM_2026_27_JOSH)

        for cat in B.CATEGORIES:
            assert params["plain"][cat]["mean"] == pytest.approx(
                plain[cat]["mean"], abs=0.02 * plain[cat]["sd"])
            assert params["plain"][cat]["sd"] == pytest.approx(plain[cat]["sd"], rel=0.02)
            assert params["durant"][cat]["sd"] == pytest.approx(durant[cat]["sd"], rel=0.05)
            assert got_lam[cat] == pytest.approx(lambdas[cat], abs=0.05)

    def test_it_recovers_the_pool_rate_which_is_not_the_pools_own(self):
        # The percentage rate is identified by the fit rather than assumed. It has to be:
        # Basketball Monster's rate is not the attempt-weighted rate of these projections.
        pool = spread(120)
        plain, durant = invented_params(pool)
        lambdas = invented_lambdas()
        published = publish(pool, plain, durant, lambdas)
        params, _, _ = C.calibrate(pool, published, sorted(pool),
                                   B.LAMBDAS_BBM_2026_27_JOSH)
        for cat in ("fg%V", "ft%V"):
            assert params["plain"][cat]["rate"] == pytest.approx(plain[cat]["rate"], abs=0.01)

    def test_the_constants_move_when_the_projections_do(self):
        # The property the whole design rests on: a refresh must produce a refresh. A
        # fitter that returned its seed, or cached, would pass every test above.
        base = spread(120)
        plain, durant = invented_params(base)
        lambdas = invented_lambdas()
        first, _, _ = C.calibrate(base, publish(base, plain, durant, lambdas),
                                  sorted(base), B.LAMBDAS_BBM_2026_27_JOSH)

        moved = {k: dict(r, points=r["points"] * 1.15, rebounds=r["rebounds"] * 0.9)
                 for k, r in base.items()}
        plain2, durant2 = invented_params(moved)
        second, _, _ = C.calibrate(moved, publish(moved, plain2, durant2, lambdas),
                                   sorted(moved), B.LAMBDAS_BBM_2026_27_JOSH)

        assert second["plain"]["pV"]["mean"] > first["plain"]["pV"]["mean"] * 1.1
        assert second["plain"]["rV"]["mean"] < first["plain"]["rV"]["mean"] * 0.95


class TestOutlierRejection:
    def test_a_clean_pairing_rejects_nobody(self):
        pool = spread(120)
        plain, durant = invented_params(pool)
        published = publish(pool, plain, durant, invented_lambdas())
        kept, rejected = C.consistent_players(pool, published, sorted(pool))
        assert rejected == []
        assert len(kept) == len(pool)

    def test_a_player_whose_stat_line_has_changed_is_dropped(self):
        # Basketball Monster revises between exports. One stale row does not merely
        # mispredict itself: it tilts the regression and corrupts constants applied to
        # every player in the universe.
        pool = spread(120)
        plain, durant = invented_params(pool)
        published = publish(pool, plain, durant, invented_lambdas())
        stale = dict(pool)
        stale["p042"] = dict(pool["p042"], points=pool["p042"]["points"] + 9,
                             rebounds=pool["p042"]["rebounds"] + 4)
        kept, rejected = C.consistent_players(stale, published, sorted(stale))
        assert rejected == ["p042"]
        assert "p042" not in kept

    def test_dropping_the_stale_row_restores_the_constants(self):
        pool = spread(120)
        plain, durant = invented_params(pool)
        published = publish(pool, plain, durant, invented_lambdas())
        stale = dict(pool)
        stale["p042"] = dict(pool["p042"], points=pool["p042"]["points"] + 9)
        kept, _ = C.consistent_players(stale, published, sorted(stale))
        clean, _, _ = C.calibrate(stale, published, kept, B.LAMBDAS_BBM_2026_27_JOSH)
        assert clean["plain"]["pV"]["sd"] == pytest.approx(plain["pV"]["sd"], rel=0.02)


class TestParsePublished:
    def _tsv(self, rows):
        header = ["", *C.PLAIN_COL.values(), *C.DURANT_COL.values()]
        return "\n".join(["\t".join(header)] + ["\t".join(r) for r in rows])

    def _row(self, pid, v="1.0"):
        return [pid] + [v] * (len(C.PLAIN_COL) + len(C.DURANT_COL))

    def test_repeated_header_rows_are_dropped(self):
        # Their export repeats its header roughly every dozen players.
        header = ["", *C.PLAIN_COL.values(), *C.DURANT_COL.values()]
        text = self._tsv([self._row("7"), header, self._row("9")])
        out, skipped = C.parse_published(text)
        assert set(out) == {7, 9}
        assert skipped == 1

    def test_thousands_separators_are_stripped(self):
        out, _ = C.parse_published(self._tsv([self._row("7", "1,234.5")]))
        assert out[7]["pV"] == 1234.5

    def test_a_table_without_the_value_columns_says_which_are_missing(self):
        text = "\tName\tpV\n1\tX\t0.5"
        with pytest.raises(C.CalibrationError, match="Edit Display Columns"):
            C.parse_published(text)

    def test_an_empty_scrape_is_an_error_not_an_empty_fit(self):
        with pytest.raises(C.CalibrationError, match="empty"):
            C.parse_published("")
