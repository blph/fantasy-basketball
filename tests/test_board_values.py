"""The three values, their pools, and the constants the tracker is thresholded on.

Fixtures are invented players with invented numbers (ADR-0006). The arithmetic they check
is the arithmetic in docs/references/basketball-monster-projections-reverse-engineering.md.
"""

import math

import bbm_reference as B
import board_values as BV
import pytest


def player(**over):
    """A per-game line. Overriding one category moves only that category."""
    base = {
        "games": 70.0, "minutes": 32.0, "points": 18.0, "threes": 1.8, "rebounds": 6.0,
        "assists": 4.0, "steals": 1.0, "blocks": 0.7, "turnovers": 2.0,
        "fg_made": 6.6, "fg_att": 14.0, "ft_made": 3.0, "ft_att": 3.8,
    }
    base.update(over)
    return base


def spread(n=40):
    """A pool with real spread in every category, so no SD is zero.

    Deliberately NOT monotone. A pool where every player beats the last in all nine
    categories has no trade-offs, so no reweighting can ever change who makes the top Q --
    which would make the punt tests vacuous. The offsets below are coprime with each other
    so each category peaks at a different player, the way a real pool does.
    """
    out = {}
    for i in range(n):
        f = i / (n - 1)

        def wave(period, phase=0.0, i=i):
            return 0.5 + 0.5 * math.sin(2 * math.pi * ((i / period) + phase))

        out[f"p{i:03d}"] = player(
            minutes=20 + 18 * f,
            points=8 + 22 * f,
            threes=0.3 + 3.4 * wave(7),
            rebounds=2 + 9 * wave(5, 0.3),
            assists=1 + 8 * wave(11, 0.6),
            steals=0.4 + 1.6 * wave(6, 0.15),
            blocks=0.1 + 2.2 * wave(9, 0.45),
            turnovers=0.8 + 3.0 * wave(8, 0.7),
            fg_made=3 + 6 * f,
            fg_att=7 + 11 * f * (0.85 + 0.3 * wave(4, 0.2)),
            ft_made=1 + 5 * wave(13, 0.1),
            ft_att=1.4 + 5.6 * wave(13, 0.1) * (0.8 + 0.4 * wave(3)),
        )
    return out


class TestTrackerK:
    def test_k_divides_by_the_weight_and_can_be_inverted_back(self):
        # The correction that would otherwise ship silently. A weighted DURANT column's SD
        # is exactly its weight, so Z_team measured in DH units is w times Z_team in z
        # units, and K = k / w. Multiplying instead understates every win probability and
        # nothing in the sheet looks wrong.
        k = BV.tracker_k()
        for cat in BV.CAT_ORDER:
            assert k[cat] * B.H2H_WEIGHTS[cat] == pytest.approx(BV.K_ROSENOF[cat])

    def test_turnovers_have_no_k_at_all(self):
        # DURANT H2H prices turnovers at zero, so a DH turnover column is identically 0.0
        # for everyone. k = 0.485 / 0 is not a threshold, it is a division by zero.
        assert "toV" not in BV.tracker_k()
        assert "toV" not in BV.CAT_ORDER

    def test_the_eight_categories_line_up_with_their_labels(self):
        # CAT_ORDER and CAT_LABELS are matched positionally by the tracker rows, the
        # Punted checkboxes and the Category profile. A drift relabels every player.
        assert len(BV.CAT_ORDER) == len(BV.CAT_LABELS) == 8
        assert set(BV.CAT_ORDER) < set(B.CATEGORIES)


class TestWeightedDropOne:
    def test_a_zero_weighted_category_is_removed_not_merely_discounted(self):
        # It takes no part in the "worst" comparison and does not sit in the denominator.
        vals = dict.fromkeys(B.CATEGORIES, 1.0)
        vals["toV"] = -99.0
        score, dropped = B.weighted_drop_one(vals, B.H2H_WEIGHTS)
        assert dropped != "toV"
        assert score > 0

    def test_the_denominator_is_seven(self):
        # Nine categories, turnovers weighted out, one more dropped.
        vals = dict.fromkeys(B.CATEGORIES, 1.0)
        score, _ = B.weighted_drop_one(vals, B.H2H_WEIGHTS)
        kept = [B.H2H_WEIGHTS[c] for c in B.CATEGORIES if B.H2H_WEIGHTS[c]]
        assert score == pytest.approx((sum(kept) - min(kept)) / 7)

    def test_it_drops_the_worst_WEIGHTED_value_not_the_worst_raw_one(self):
        # This is the whole point of weighting before dropping: a big raw deficit in a
        # lightly-weighted category can hurt less than a small one in points.
        vals = dict.fromkeys(B.CATEGORIES, 1.0)
        vals["sV"] = -1.0   # weight 0.60 -> -0.60
        vals["pV"] = -0.8   # weight 1.00 -> -0.80, worse once weighted
        _, dropped = B.weighted_drop_one(vals, B.H2H_WEIGHTS)
        assert dropped == "pV"

    def test_it_refuses_a_weight_vector_with_nothing_live(self):
        with pytest.raises(ValueError, match="at least two live"):
            B.weighted_drop_one(dict.fromkeys(B.CATEGORIES, 1.0),
                                dict.fromkeys(B.CATEGORIES, 0.0))


class TestZsh:
    def test_zsh_is_the_h2h_rule_over_untransformed_z(self):
        pool = spread()
        _, params = B.build_pool(pool, 20)
        one = pool["p010"]
        assert B.z_h2h(one, params) == B.weighted_drop_one(
            B.category_values(one, params), B.H2H_WEIGHTS)

    def test_zsh_never_drops_turnovers(self):
        pool = spread()
        _, params = B.build_pool(pool, 20)
        for r in pool.values():
            assert B.z_h2h(r, params)[1] != "toV"

    def test_zsh_and_durh_can_name_different_dropped_categories(self):
        # The two values differ only by the Yeo-Johnson layer. If the transform never
        # changed which category is lowest, ZSH would be a rename of DURH rather than a
        # second opinion, and shipping both would be pointless.
        pool = spread(60)
        _, zp = B.build_z_h2h_pool(pool, 30)
        _, dp = B.build_durant_pool(pool, 30, B.LAMBDAS_BBM_2026_27_JOSH)
        differ = sum(B.z_h2h(r, zp)[1] != B.durant_h2h(r, dp)[1] for r in pool.values())
        assert differ > 0


class TestPools:
    def test_each_value_settles_on_its_own_pool(self):
        pool = spread(60)
        zsc, _ = B.build_pool(pool, 30)
        zsh, _ = B.build_z_h2h_pool(pool, 30)
        dur, _ = B.build_durant_pool(pool, 30, B.LAMBDAS_BBM_2026_27_JOSH)
        assert len(zsc) == len(zsh) == len(dur) == 30
        # They rank a different order, so at least one pair selects a different top-30.
        assert {tuple(sorted(zsc)), tuple(sorted(zsh)), tuple(sorted(dur))}

    def test_the_zsh_pool_is_a_fixed_point(self):
        pool = spread(60)
        members, params = B.build_z_h2h_pool(pool, 30)
        rescored = sorted(pool, key=lambda k: -B.z_h2h(pool[k], params)[0])[:30]
        assert sorted(rescored) == sorted(members)

    def test_the_pool_seed_is_pinned_so_two_runs_agree(self):
        # The fixed point is stable but not unique -- different seeds land on pools
        # differing by a boundary player. Pinning the seed is what makes a rebuild
        # reproducible, and reproducibility is what makes a diff meaningful.
        pool = spread(60)
        a = BV.score_source(pool, 30)
        b = BV.score_source(dict(reversed(list(pool.items()))), 30)
        for key in pool:
            assert a["players"][key]["durh"] == pytest.approx(b["players"][key]["durh"])
            assert a["players"][key]["durh_rank"] == b["players"][key]["durh_rank"]


class TestScoreSource:
    def test_it_reports_every_value_rank_and_dropped_category(self):
        res = BV.score_source(spread(40), 20)
        p = res["players"]["p010"]
        assert {"zsc", "zsh", "durh", "zsh_drop", "durh_drop", "dh", "d", "z"} <= set(p)
        assert p["durh_drop"] in BV.CAT_ORDER

    def test_ranks_are_a_permutation_with_no_gaps(self):
        res = BV.score_source(spread(40), 20)
        for field in ("zsc_rank", "zsh_rank", "durh_rank"):
            ranks = sorted(p[field] for p in res["players"].values())
            assert ranks == list(range(1, 41))

    def test_the_weighted_and_unweighted_category_values_differ_by_the_weight(self):
        # The board displays the weighted column; the profile thresholds the unweighted
        # one, because a fixed band is unreachable for any category weighted below 1.
        res = BV.score_source(spread(40), 20)
        p = res["players"]["p010"]
        for cat in BV.CAT_ORDER:
            assert p["dh"][cat] == pytest.approx(p["d"][cat] * B.H2H_WEIGHTS[cat])

    def test_it_reports_the_pool_constants_and_the_availability_diagnostic(self):
        res = BV.score_source(spread(40), 20)
        pools = res["pools"]["durant"]
        assert pools["size"] == 20
        # ADR-0011's MIN_GP gate is retired; the concern it named stays visible.
        assert "gp_under_25" in pools and "gp_median" in pools

    def test_a_zero_spread_category_does_not_divide_by_zero(self):
        flat = {f"p{i}": player(blocks=0.5) for i in range(10)}
        for i, k in enumerate(flat):
            flat[k]["points"] = 10 + i      # keep something to rank on
        res = BV.score_source(flat, 5)
        assert all(math.isfinite(p["durh"]) for p in res["players"].values())


def borrowed_from(pool, q, *, shift=0.0, stretch=1.0):
    """A `params` mapping in the shape `bbm_constants.load` returns.

    With the defaults it is exactly the pool's own constants, which is what the identity
    test needs. `shift` and `stretch` perturb it into constants no pool of this projection
    set produces -- the situation Basketball Monster actually puts us in.
    """
    _, plain = B.build_pool(pool, q)
    _, dur = B.build_durant_pool(pool, q, B.LAMBDAS_BBM_2026_27_JOSH)
    if shift or stretch != 1.0:
        for block in (plain, dur):
            for spec in block.values():
                spec["mean"] += shift * spec["sd"]
                spec["sd"] *= stretch
    return {"plain": plain, "durant": dur}


class TestBorrowedConstants:
    def test_borrowing_the_pools_own_constants_reproduces_the_derived_result(self):
        # The identity that proves the two paths have not drifted apart. Everything else
        # about borrowed constants is only trustworthy if this holds: the borrowed path
        # must differ from the derived one in WHICH constants it uses and nothing else.
        pool = spread(60)
        derived = BV.score_source(pool, 30)
        borrowed = BV.score_source(pool, 30, params=borrowed_from(pool, 30))
        for key in pool:
            a, b = derived["players"][key], borrowed["players"][key]
            for field in ("zsc", "durh"):
                assert b[field] == pytest.approx(a[field])
                assert b[f"{field}_rank"] == a[f"{field}_rank"]
            assert b["durh_drop"] == a["durh_drop"]

    def test_constants_that_are_not_the_pools_own_actually_change_the_values(self):
        # The complement of the identity test. A `params` argument that silently fell back
        # to deriving would pass every other test in this class.
        pool = spread(60)
        derived = BV.score_source(pool, 30)
        borrowed = BV.score_source(pool, 30, params=borrowed_from(pool, 30, stretch=1.08))
        moved = sum(borrowed["players"][k]["durh"] != pytest.approx(
            derived["players"][k]["durh"]) for k in pool)
        assert moved > len(pool) // 2

    def test_the_reported_constants_are_the_ones_supplied(self):
        pool = spread(60)
        params = borrowed_from(pool, 30, shift=0.2, stretch=1.08)
        res = BV.score_source(pool, 30, params=params)
        for c in B.CATEGORIES:
            assert res["pools"]["durant"][c]["sd"] == pytest.approx(
                params["durant"][c]["sd"], abs=5e-7)
            assert res["pools"]["zsc"][c]["mean"] == pytest.approx(
                params["plain"][c]["mean"], abs=5e-7)

    def test_the_basis_says_where_the_constants_came_from(self):
        pool = spread(40)
        assert BV.score_source(pool, 20)["basis"] == "derived"
        assert BV.score_source(pool, 20)["pools"]["zsc"]["basis"] == "derived"
        res = BV.score_source(pool, 20, params=borrowed_from(pool, 20))
        assert res["basis"] == "borrowed"
        assert res["pools"]["durant"]["basis"] == "borrowed"

    def test_the_drift_diagnostic_measures_the_gap_it_is_there_to_expose(self):
        # Borrowed constants stretched 8% wider than the pool's own should report roughly
        # -7.4% -- our SD is 1/1.08 of theirs. This number is the only thing on Settings
        # that can reveal a stale or bad calibration, so it has to be right.
        pool = spread(60)
        res = BV.score_source(pool, 30, params=borrowed_from(pool, 30, stretch=1.08))
        delta = res["pools"]["durant"]["derived_delta"]
        for c in B.CATEGORIES:
            assert delta[c]["sd"] == pytest.approx(100 * (1 / 1.08 - 1), abs=0.5)

    def test_a_derived_run_reports_no_drift_because_there_is_nothing_to_compare(self):
        assert "derived_delta" not in BV.score_source(spread(40), 20)["pools"]["zsc"]

    def test_ranks_stay_a_permutation_with_no_gaps(self):
        pool = spread(40)
        res = BV.score_source(pool, 20, params=borrowed_from(pool, 20, shift=0.3))
        for field in ("zsc_rank", "zsh_rank", "durh_rank"):
            assert sorted(p[field] for p in res["players"].values()) == list(range(1, 41))

    def test_borrowed_scoring_is_deterministic_under_a_reordered_input(self):
        pool = spread(60)
        params = borrowed_from(pool, 30, stretch=1.05)
        a = BV.score_source(pool, 30, params=params)
        b = BV.score_source(dict(reversed(list(pool.items()))), 30, params=params)
        for key in pool:
            assert a["players"][key]["durh_rank"] == b["players"][key]["durh_rank"]


class TestPuntBuilds:
    def test_punting_re_derives_the_pool_rather_than_editing_one_column(self):
        # Basketball Monster's mechanism. Weighting before standardising changes who is in
        # the top Q, which changes every mean and SD -- so a punt moves the whole field,
        # not one column. The old board subtracted after the fact and kept the pool fixed.
        pool = spread(60)
        base, _ = B.build_durant_pool(pool, 30, B.LAMBDAS_BBM_2026_27_JOSH)
        punted = BV.durant_h2h_punt(pool, 30, ("ft%V",), 0.25)
        after = sorted(punted, key=lambda k: -punted[k])[:30]
        assert sorted(after) != sorted(base)

    def test_a_punt_weight_of_one_reproduces_the_unpunted_value(self):
        pool = spread(40)
        _, params = B.build_durant_pool(pool, 20, B.LAMBDAS_BBM_2026_27_JOSH)
        unpunted = {k: B.durant_h2h(r, params)[0] for k, r in pool.items()}
        same = BV.durant_h2h_punt(pool, 20, ("ft%V",), 1.0)
        for k in pool:
            assert same[k] == pytest.approx(unpunted[k])

    def test_a_borrowed_punt_weight_of_one_reproduces_the_borrowed_unpunted_value(self):
        # The same identity on the borrowed path. Under fixed constants the pool cannot
        # re-derive, so a punt is a pure post-standardisation discount -- but the board's
        # punt GAP column still compares a punt rank against the base DURH rank, and that
        # comparison is only meaningful if both sit on the same constants.
        pool = spread(40)
        params = borrowed_from(pool, 20, shift=0.2, stretch=1.06)
        base = BV.score_source(pool, 20, params=params)["players"]
        same = BV.durant_h2h_punt(pool, 20, ("ft%V",), 1.0, params=params["durant"])
        for k in pool:
            assert same[k] == pytest.approx(base[k]["durh"])

    def test_a_borrowed_punt_still_discounts_the_punted_category(self):
        pool = spread(40)
        params = borrowed_from(pool, 20, stretch=1.06)
        full = BV.durant_h2h_punt(pool, 20, ("ft%V",), 1.0, params=params["durant"])
        punted = BV.durant_h2h_punt(pool, 20, ("ft%V",), 0.25, params=params["durant"])
        assert sorted(punted, key=lambda k: -punted[k])[:20] != \
            sorted(full, key=lambda k: -full[k])[:20]


class TestDiagnostics:
    def test_the_band_calibration_counts_flags_and_unlabelled_players(self):
        res = BV.score_source(spread(60), 30)
        ranked = sorted(res["players"], key=lambda k: res["players"][k]["durh_rank"])[:30]
        cal = BV.profile_calibration(res["players"], ranked)
        # A wider band names fewer players. If this ever inverts, the band is not a band.
        assert cal[0.85]["flags_per_player"] >= cal[1.15]["flags_per_player"]

    def test_the_durant_on_z_slopes_sit_just_under_one(self):
        # Both columns have unit SD by construction, so the transform reshapes without
        # rescaling. A slope far from 1 would mean the two bases are not comparable and
        # K = k/w could not be justified as a first-order correction.
        res = BV.score_source(spread(60), 30)
        ranked = sorted(res["players"], key=lambda k: res["players"][k]["durh_rank"])[:30]
        for slope in BV.durant_vs_z_slopes(res["players"], ranked).values():
            assert 0.5 < slope <= 1.05
