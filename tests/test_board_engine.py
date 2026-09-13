"""The local engine against hand-computed boards.

Every snapshot here comes from tests/board_fixtures.py: invented names and invented numbers.
Real snapshots are provider data and this repository is public (ADR-0006), so nothing under
data/draft-board/ is ever read or copied into a test. Where a hand computation needs a
column to be flat -- a zero profile, a constant attempt count -- the test sets it.
"""

from __future__ import annotations

import ast
import math
import random
from decimal import Decimal
from pathlib import Path

import board_engine as E
import pytest
from board_snapshot import PUNT_BUILDS, SOURCES

from board_fixtures import CATS, make_snapshot, set_values, tick


def rows_for(snap, state=None, sort=None, row_order=None):
    state = state or E.empty_state()
    return E.board_rows(snap, state, snap["settings"], sort or E.DEFAULT_SORT, row_order)


# ------------------------------------------------------------ order, rank, round

class TestOrderAndRank:
    def test_sort_key_and_empty_state(self):
        assert E.sort_key({"source": "BMP-ALT", "kind": "zsh"}) == "BMP-ALT:zsh"
        state = E.empty_state()
        assert state == {"players": {}, "conceded": [], "offboard": [],
                         "applied_sort": {"source": "BMP", "kind": "durh"}}
        state["applied_sort"]["kind"] = "zsc"
        assert E.DEFAULT_SORT == {"source": "BMP", "kind": "durh"}

    def test_player_state_fills_defaults_and_inserts_nothing(self):
        state = E.empty_state()
        assert E.player_state(state, "nobody") == {
            "name": "", "gone": False, "mine": False, "pick": None, "notes": "",
            "my_gp": None, "xrank": None, "gp1": None, "gp2": None, "gp3": None}
        assert state["players"] == {}
        state["players"]["somebody"] = {"gone": True}
        got = E.player_state(state, "somebody")
        assert got["gone"] is True and got["mine"] is False

    def test_order_is_value_descending_with_ties_on_board_row(self):
        snap = make_snapshot(n=5)
        set_values(snap, "BMP", "durh", [5.0, 7.0, 7.0, 3.0, 7.0])
        assert E.order(snap, E.DEFAULT_SORT) == [1, 2, 4, 0, 3]

    def test_rank_is_the_position_when_the_display_is_sorted(self):
        snap = make_snapshot(n=5)
        set_values(snap, "BMP", "durh", [5.0, 7.0, 7.0, 3.0, 7.0])
        rows = rows_for(snap)
        assert [r["row"] for r in rows] == [1, 2, 4, 0, 3]
        assert [r["rank"] for r in rows] == [1, 2, 3, 4, 5]
        assert [r["sel"] for r in rows] == [7.0, 7.0, 7.0, 5.0, 3.0]

    def test_rank_follows_rank_plus_countif_on_an_unsorted_display(self):
        snap = make_snapshot(n=4)
        set_values(snap, "BMP", "durh", [1.0, 3.0, 2.0, 3.0])
        rows = rows_for(snap, row_order=[0, 1, 2, 3])
        # RANK counts strictly greater values; the COUNTIF counts equal ones from the top.
        assert [r["rank"] for r in rows] == [4, 1, 3, 2]

    def test_round_divides_by_the_settings_team_count(self):
        snap = make_snapshot(n=9, settings={"teams": 4})
        assert [r["rnd"] for r in rows_for(snap)] == [1, 1, 1, 1, 2, 2, 2, 2, 3]

    def test_a_non_bmp_sort_orders_by_that_value(self):
        snap = make_snapshot(n=4)
        set_values(snap, "HBP", "zsh", [1.0, 4.0, 2.0, 3.0])
        rows = rows_for(snap, sort={"source": "HBP", "kind": "zsh"})
        assert [r["row"] for r in rows] == [1, 3, 2, 0]
        assert [r["sel"] for r in rows] == [4.0, 3.0, 2.0, 1.0]

    def test_bad_sort_and_bad_row_order_are_refused(self):
        snap = make_snapshot(n=3)
        with pytest.raises(ValueError):
            E.order(snap, {"source": "ESPN", "kind": "durh"})
        with pytest.raises(ValueError):
            rows_for(snap, row_order=[0, 0, 1])


# ------------------------------------------------------------------------- tiers

def sheet_tier_columns(sel, tier_mult):
    """buildDraftTab's four tier columns, computed by the sheet's own cell arithmetic.

    Written independently of the engine: sheet rows, ROW(), and INDEX offsets into
    $drop$4:$drop$203, exactly as the formula text reads. Needs a full 200-row board.
    """
    hdr, r0, pool_rows = 3, 4, 200
    assert len(sel) == pool_rows
    drop_cell = {r0 + i: (None if i == 0 else sel[i - 1] - sel[i]) for i in range(pool_rows)}
    out = {"drop": [None], "med": [None], "brk": [""], "tier": [1], "window": [None]}
    for i in range(1, pool_rows):
        row = r0 + i
        first = max(1, row - (hdr + 7))            # INDEX(drops, MAX(1, ROW()-10))
        last = min(pool_rows, row + (7 - hdr))     # INDEX(drops, MIN(200, ROW()+4))
        cells = [drop_cell[k + hdr] for k in range(first, last + 1)]
        nums = sorted(c for c in cells if c is not None)
        mid = len(nums) // 2
        med = nums[mid] if len(nums) % 2 else (nums[mid - 1] + nums[mid]) / 2
        drop = drop_cell[row]
        brk = "" if med <= 0 else ("BREAK" if drop > tier_mult * med else "")
        out["drop"].append(drop)
        out["med"].append(med)
        out["brk"].append(brk)
        out["tier"].append(out["tier"][-1] + 1 if brk == "BREAK" else out["tier"][-1])
        out["window"].append((first + hdr - r0, last + hdr - r0))
    return out


class TestTiers:
    def test_first_row_is_tier_one_with_blank_drop_median_and_break(self):
        row = rows_for(make_snapshot(n=3))[0]
        assert (row["tier"], row["drop"], row["med"], row["brk"]) == (1, None, None, "")

    def test_hand_computed_small_board(self):
        snap = make_snapshot(n=6)
        set_values(snap, "BMP", "durh", [10.0, 9.0, 8.5, 8.0, 7.9, 4.0])
        rows = rows_for(snap)
        # Every window spans the whole board: drops 1, .5, .5, ~.1, ~3.9 -> median .5.
        assert [r["med"] for r in rows] == [None, 0.5, 0.5, 0.5, 0.5, 0.5]
        # A drop of exactly 1.0 is not greater than 2 x 0.5; 3.9 is.
        assert [r["brk"] for r in rows] == ["", "", "", "", "", "BREAK"]
        assert [r["tier"] for r in rows] == [1, 1, 1, 1, 1, 2]

    def test_an_even_window_averages_the_middle_two(self):
        snap = make_snapshot(n=5)
        set_values(snap, "BMP", "durh", [4.0, 3.0, 2.5, 2.25, 0.0])
        rows = rows_for(snap)
        # drops 1, .5, .25, 2.25 -> (0.5 + 1.0) / 2
        assert rows[4]["med"] == 0.75
        assert [r["brk"] for r in rows] == ["", "", "", "", "BREAK"]

    def test_a_median_at_or_below_zero_never_breaks(self):
        snap = make_snapshot(n=5)
        set_values(snap, "BMP", "durh", [5.0, 5.0, 5.0, 5.0, 1.0])
        rows = rows_for(snap)
        assert rows[4]["drop"] == 4.0 and rows[4]["med"] == 0.0
        assert [r["tier"] for r in rows] == [1, 1, 1, 1, 1]

    def test_the_break_compares_binary_floats_not_decimals(self):
        vals = [1.0, 0.9, 0.8, 0.6]
        snap = make_snapshot(n=4)
        set_values(snap, "BMP", "durh", vals)
        rows = rows_for(snap)
        dec = [Decimal(str(v)) for v in vals]
        drops = sorted(dec[i - 1] - dec[i] for i in range(1, 4))
        assert dec[2] - dec[3] == 2 * drops[1]          # in decimal: equal, so no break
        assert rows[3]["brk"] == "BREAK"                 # in binary floats: greater
        assert rows[3]["drop"] > 2.0 * rows[3]["med"]

    def test_window_and_every_tier_column_match_the_sheet_arithmetic(self):
        rng = random.Random(20260912)
        vals, v = [], 60.0
        for _ in range(200):
            vals.append(round(v, 4))
            v -= rng.choice([0.01, 0.02, 0.05, 0.1, 0.3, 0.7, 1.5])
        snap = make_snapshot(n=200)
        set_values(snap, "BMP", "durh", vals)
        rows = rows_for(snap)
        sheet = sheet_tier_columns([r["sel"] for r in rows], 2.0)
        for i in range(1, 8):
            assert sheet["window"][i] == (0, i + 7)
        for i in range(193, 200):
            assert sheet["window"][i] == (i - 7, 199)
        assert [r["drop"] for r in rows] == sheet["drop"]
        assert [r["med"] for r in rows] == sheet["med"]
        assert [r["brk"] for r in rows] == sheet["brk"]
        assert [r["tier"] for r in rows] == sheet["tier"]
        assert "BREAK" in sheet["brk"]

    def test_tiers_ignore_gone(self):
        snap = make_snapshot(n=6)
        set_values(snap, "BMP", "durh", [10.0, 9.0, 8.5, 8.0, 7.9, 4.0])
        state = E.empty_state()
        for i in range(4):
            tick(state, snap, i, gone=True)
        assert [r["tier"] for r in rows_for(snap, state)] == [1, 1, 1, 1, 1, 2]


# ----------------------------------------------------------------- per-row columns

class TestRowFields:
    def test_identity_and_hand_columns_are_carried(self):
        snap = make_snapshot(n=3)
        snap["players"][1].update(team="BBB", pos="SF,PF", inj="HIGH")
        state = E.empty_state()
        tick(state, snap, 1, gone=True, mine=True, notes="a note", xrank=7)
        row = rows_for(snap, state)[1]
        assert (row["key"], row["name"]) == (snap["players"][1]["key"], snap["players"][1]["name"])
        assert (row["team"], row["pos"], row["inj"]) == ("BBB", "SF,PF", "HIGH")
        assert (row["gone"], row["mine"], row["notes"], row["xrank"]) == (True, True, "a note", 7)
        assert set(row) == {
            "row", "key", "name", "team", "pos", "inj", "gone", "mine", "rank", "tier", "rnd",
            "sel", "drop", "med", "brk", "gap", "adp", "xrank", "notes", "gp", "my_gp",
            "gp_flag", "gp_warn", "best_build", "strengths", "weaknesses", "left_at_pos",
            "in_pool", "values", "ranks", "tags", "disagree"}

    def test_gap_is_adp_minus_rank_and_blank_without_adp(self):
        snap = make_snapshot(n=3)
        snap["players"][0]["adp"] = 4.5
        snap["players"][1]["adp"] = 2.0
        snap["players"][2]["adp"] = None
        rows = rows_for(snap)
        assert rows[0]["gap"] == 3.5
        assert rows[1]["gap"] == 0.0
        assert rows[2]["gap"] is None and rows[2]["adp"] is None

    def test_best_build_names_the_first_minimum_and_the_margin(self):
        snap = make_snapshot(n=12)
        p = snap["players"][9]                       # BMP DURH rank 10
        for b, rank in zip(PUNT_BUILDS, [7, 4, 4, 12, 11, 10, 9, 8, 13], strict=True):
            p["punts"][b[0]]["rank"] = rank
        assert rows_for(snap)[9]["best_build"] == "FG%  +6"

    def test_best_build_is_a_dash_when_no_build_beats_the_base_rank(self):
        snap = make_snapshot(n=12)
        p = snap["players"][9]
        for b in PUNT_BUILDS:
            p["punts"][b[0]]["rank"] = 10 if b[0] == "pAst" else 11
        assert rows_for(snap)[9]["best_build"] == "—"

    def test_best_build_is_a_dash_without_punt_ranks(self):
        snap = make_snapshot(n=3)
        snap["players"][2]["punts"] = {}
        assert rows_for(snap)[2]["best_build"] == "—"

    def test_best_build_reads_bmp_whatever_the_sort(self):
        snap = make_snapshot(n=12)
        p = snap["players"][9]
        p["punts"]["pTriple"]["rank"] = 1
        rows = rows_for(snap, sort={"source": "HBP", "kind": "zsc"})
        assert rows[9]["best_build"] == "FG/FT/TO  +9"

    def test_strengths_and_weaknesses_band_the_applied_sources_d(self):
        snap = make_snapshot(n=3)
        for p in snap["players"]:                    # a flat profile, then the cases
            for src in SOURCES:
                p["values"][src]["d"] = dict.fromkeys(CATS, 0.0)
        hbp = snap["players"][0]["values"]["HBP"]["d"]
        hbp.update({"FG%": 1.0, "3PM": 2.0, "PTS": 1.5, "REB": -1.0, "BLK": -0.99})
        snap["players"][0]["values"]["BMP"]["d"]["AST"] = 3.0
        state = E.empty_state()
        state["conceded"] = ["3PM"]
        rows = rows_for(snap, state, sort={"source": "HBP", "kind": "durh"})
        assert rows[0]["strengths"] == "▲ FG%, PTS"
        assert rows[0]["weaknesses"] == "▼ REB"
        assert (rows[1]["strengths"], rows[1]["weaknesses"]) == ("—", "—")
        assert rows_for(snap)[0]["strengths"] == "▲ AST"

    def test_tags_values_ranks_and_disagreement(self):
        snap = make_snapshot(n=20, settings={"disagree_gap": 15})    # the league's gap
        snap["players"][0]["values"]["HBP"]["zsc"]["rank"] = 16      # board #1, HBP #16
        snap["players"][19]["values"]["HBP"]["durh"]["rank"] = 5     # board #20, HBP #5
        snap["players"][18]["values"]["BMP-ALT"]["zsh"]["rank"] = 5  # board #19: gap 14
        rows = rows_for(snap)
        assert rows[0]["tags"]["BMP:durh"] == "#1 FG%"
        assert rows[0]["tags"]["HBP:zsh"] == "#1 3PM"
        assert rows[0]["tags"]["HBP:zsc"] == "#16"
        alt_zsc = snap["players"][0]["values"]["BMP-ALT"]["zsc"]["v"]
        assert rows[0]["values"]["BMP-ALT:zsc"] == alt_zsc
        assert rows[0]["ranks"]["HBP:zsc"] == 16
        assert len(rows[0]["values"]) == len(rows[0]["tags"]) == len(rows[0]["disagree"]) == 9
        assert rows[0]["disagree"]["HBP:zsc"] == "lower"
        assert rows[19]["disagree"]["HBP:durh"] == "higher"
        assert rows[18]["disagree"]["BMP-ALT:zsh"] is None
        assert rows[5]["disagree"]["BMP:durh"] is None

    def test_gp_flag_and_warning(self):
        snap = make_snapshot(n=6)
        for p, gp in zip(snap["players"], [70, 70, 70, 67, 74, 75], strict=True):
            p["hbp_raw"]["gp"] = gp
        state = E.empty_state()
        tick(state, snap, 0, my_gp=59)
        tick(state, snap, 1, my_gp=60)
        rows = rows_for(snap, state)
        assert [r["my_gp"] for r in rows] == [59, 60, 70, 67, 74, 75]
        assert [r["gp_flag"] for r in rows] == ["CHECK", "", "", "", "", ""]
        assert [r["gp_warn"] for r in rows] == [True, True, True, False, True, False]

    def test_in_pool_is_bmp_durh_rank_within_q(self):
        snap = make_snapshot(n=8, settings={"q": 5})
        rows = rows_for(snap, sort={"source": "HBP", "kind": "durh"})
        assert [r["in_pool"] for r in rows] == [True] * 5 + [False] * 3

    def test_left_at_pos_matches_eligibility_both_ways(self):
        snap = make_snapshot(n=10)
        positions = ["PG", "SG", "PG,SG", "G", "SF", "PF", "F", "C", "PF,C", ""]
        for p, pos in zip(snap["players"], positions, strict=True):
            p["pos"] = pos
        rows = rows_for(snap)
        assert all(r["tier"] == 1 for r in rows)
        # PG: PG, PG,SG. SF: SF alone. G: every guard. F: every forward. PF,C: PF, C, PF,C.
        # Blank: an empty pattern matches all ten.
        assert [r["left_at_pos"] for r in rows] == [2, 2, 3, 4, 1, 2, 4, 2, 3, 10]

    def test_left_at_pos_counts_mine_but_not_gone(self):
        snap = make_snapshot(n=4)
        for p in snap["players"]:
            p["pos"] = "C"
        state = E.empty_state()
        tick(state, snap, 0, mine=True)
        tick(state, snap, 1, mine=True, gone=True)
        tick(state, snap, 2, gone=True)
        assert [r["left_at_pos"] for r in rows_for(snap, state)] == [2, 2, 2, 2]

    def test_left_at_pos_stays_inside_the_tier(self):
        snap = make_snapshot(n=5)
        set_values(snap, "BMP", "durh", [10.0, 9.9, 9.8, 5.0, 4.9])
        for p in snap["players"]:
            p["pos"] = "C"
        rows = rows_for(snap)
        assert [r["tier"] for r in rows] == [1, 1, 1, 2, 2]
        assert [r["left_at_pos"] for r in rows] == [3, 3, 3, 2, 2]


# -------------------------------------------------------------- category tracker

def tracker_for(snap, state, sort=None):
    return E.tracker(snap, state, snap["settings"], sort or E.DEFAULT_SORT)


def cat(result, label):
    return next(c for c in result["cats"] if c["cat"] == label)


class TestTracker:
    def test_normal_cdf_known_values(self):
        assert E.normal_cdf(0.0) == 0.5
        assert math.isclose(E.normal_cdf(1.959963984540054), 0.975, abs_tol=1e-12)
        assert math.isclose(E.normal_cdf(-1.0), 0.15865525393145707, abs_tol=1e-15)

    def test_no_ticks_blanks_every_number_but_a_conceded_read(self):
        snap = make_snapshot(n=5)
        state = E.empty_state()
        state["conceded"] = ["FT%"]
        got = tracker_for(snap, state)
        assert (got["n"], got["cutoff"], got["benchmark"], got["roster"]) == (0, 0, "by_rank", [])
        for c in got["cats"]:
            assert (c["my_team"], c["avg_team"], c["z"], c["win"]) == (None, None, None, None)
        assert cat(got, "FT%")["read"] == "— PUNTED" and cat(got, "FT%")["conceded"] is True
        assert cat(got, "FG%")["read"] == "" and cat(got, "FG%")["conceded"] is False

    def test_hand_computed_categories(self):
        snap = make_snapshot(n=20, settings={"teams": 2, "roster": 3})    # q = 6
        snap["deriv"]["k_tracker"].update({"REB": 0.5, "AST": math.sqrt(2)})
        made = [(10.0, 20.0), (4.0, 10.0), (6.0, 12.0), (5.0, 10.0), (3.0, 8.0)]
        pts = [20.0, 10.0, 16.0, 12.0, 8.0]
        dh = {"PTS": [1.0, 0.5, 0.75, -0.25, 0.25], "REB": [0.0, 0.0, 1.5, 0.0, 1.5],
              "AST": [0.0, 0.0, 1.0, 0.0, 0.0], "STL": [0.0, 0.0, -1.0, 0.0, 0.0]}
        for i in range(5):
            p = snap["players"][i]
            p["hbp_raw"].update(fgm=made[i][0], fga=made[i][1], pts=pts[i])
            for label, column in dh.items():
                p["values"]["BMP"]["dh"][label] = column[i]
        state = E.empty_state()
        state["conceded"] = ["3PM"]
        tick(state, snap, 2, mine=True, gone=True)
        tick(state, snap, 4, mine=True)
        got = tracker_for(snap, state)
        assert (got["n"], got["cutoff"]) == (2, 4)             # min(6, 2 x 2)
        assert cat(got, "PTS")["my_team"] == 24.0
        assert cat(got, "PTS")["avg_team"] == 29.0             # mean(20, 10, 16, 12) x 2
        assert cat(got, "FG%")["my_team"] == 9.0 / 20.0
        assert cat(got, "FG%")["avg_team"] == 25.0 / 52.0
        assert cat(got, "PTS")["z"] == 0.0 and cat(got, "PTS")["win"] == 0.5
        assert cat(got, "PTS")["read"] == "● CONTESTED"
        assert math.isclose(cat(got, "REB")["z"], 2.25 / math.sqrt(2), abs_tol=1e-15)
        assert math.isclose(cat(got, "REB")["win"], 0.786837228307796, abs_tol=1e-12)
        assert cat(got, "REB")["read"] == "■ BANKED"
        assert math.isclose(cat(got, "AST")["win"], 0.691462461274013, abs_tol=1e-12)
        assert cat(got, "AST")["read"] == "▲ STRONG"
        assert math.isclose(cat(got, "STL")["win"], 0.36183680491588155, abs_tol=1e-12)
        assert cat(got, "STL")["read"] == "▼ WEAK"
        assert cat(got, "3PM")["z"] is not None and cat(got, "3PM")["read"] == "— PUNTED"
        assert got["roster"] == [
            {"rank": 3, "name": snap["players"][2]["name"], "pos": snap["players"][2]["pos"]},
            {"rank": 5, "name": snap["players"][4]["name"], "pos": snap["players"][4]["pos"]}]

    def test_benchmark_is_capped_at_q_and_ignores_gone(self):
        snap = make_snapshot(n=20, settings={"teams": 4, "roster": 2})    # q = 8
        for i, p in enumerate(snap["players"]):
            p["hbp_raw"]["pts"] = float(i + 1)
        state = E.empty_state()
        for i in (0, 10, 19):
            tick(state, snap, i, mine=True)
        for i in (8, 9, 11):
            tick(state, snap, i, gone=True)
        got = tracker_for(snap, state)
        assert got["cutoff"] == 8                              # not 4 x 3 = 12
        assert cat(got, "PTS")["avg_team"] == 4.5 * 3          # ranks 1..8, GONE or not

    def test_zero_attempts_is_flagged_not_divided(self):
        snap = make_snapshot(n=4)
        for p in snap["players"]:
            p["hbp_raw"].update(ftm=2.0, fta=2.5)
        snap["players"][3]["hbp_raw"].update(ftm=0.0, fta=0.0)
        state = E.empty_state()
        tick(state, snap, 3, mine=True)
        got = tracker_for(snap, state)
        ft = cat(got, "FT%")
        assert (ft["my_team"], ft["flag"]) == (None, "no_attempts")
        assert ft["avg_team"] == 0.8 and ft["z"] is not None
        assert cat(got, "FG%")["flag"] is None

    def test_a_non_bmp_sort_uses_hbp_raw_and_that_sources_dh(self):
        snap = make_snapshot(n=20, settings={"teams": 2, "roster": 10})   # q = 20
        set_values(snap, "BMP-ALT", "durh", [float(i) for i in range(20)])
        for i, p in enumerate(snap["players"]):
            p["hbp_raw"]["pts"] = float(i + 1)
        snap["players"][19]["values"]["BMP-ALT"]["dh"]["REB"] = 2.0
        snap["players"][18]["values"]["BMP-ALT"]["dh"]["REB"] = 1.0
        snap["players"][19]["values"]["BMP"]["dh"]["REB"] = -5.0
        state = E.empty_state()
        tick(state, snap, 19, mine=True)
        got = tracker_for(snap, state, sort={"source": "BMP-ALT", "kind": "durh"})
        assert (got["n"], got["cutoff"]) == (1, 2)
        assert cat(got, "PTS")["my_team"] == 20.0
        assert cat(got, "PTS")["avg_team"] == 19.5             # the BMP-ALT top two
        assert cat(got, "REB")["z"] == 0.5

    def test_off_board_picks_are_reported_not_counted(self):
        snap = make_snapshot(n=6)
        state = E.empty_state()
        tick(state, snap, 5, mine=True)
        tick(state, snap, 1, mine=True)
        state["offboard"] = [{"name": "Zed Offboard", "pick": 150, "mine": True},
                             {"name": "Yan Offboard", "pick": 151, "mine": False}]
        got = tracker_for(snap, state)
        assert got["n"] == 2 and got["offboard_mine"] == 1
        assert [r["rank"] for r in got["roster"]] == [2, 6]

    def test_rows_can_be_passed_in(self):
        snap = make_snapshot(n=6)
        state = E.empty_state()
        tick(state, snap, 2, mine=True)
        rows = rows_for(snap, state, row_order=[5, 4, 3, 2, 1, 0])
        got = E.tracker(snap, state, snap["settings"], E.DEFAULT_SORT, rows=rows)
        assert got["roster"][0]["rank"] == 3                   # RANK+COUNTIF, not position


# --------------------------------------------- punts, sanity checks, import boundary

class TestPunts:
    def test_sorted_by_gap_with_null_adp_last_and_ties_in_board_order(self):
        n = 50
        snap = make_snapshot(n=n)
        ties = [3, 17, 25, 41, 44]
        nulls = [0, 20, 33, 49]
        lows = {7: -2.0, 12: 5.0, 30: 0.0}
        highs = [i for i in range(n) if i not in ties and i not in nulls and i not in lows]
        assert len(highs) == 38
        gaps = {i: 100.0 - k for k, i in enumerate(reversed(highs))}
        gaps.update({i: 10.0 for i in ties})
        gaps.update(lows)
        for i, p in enumerate(snap["players"]):
            rank = n - i
            p["punts"]["pFt"] = {"score": 0.5 + i, "rank": rank}
            p["adp"] = None if i in nulls else rank + gaps[i]
        name = [p["name"] for p in snap["players"]]

        top = E.punts(snap)["pFt"]
        assert len(top) == 40
        assert [e["name"] for e in top[:38]] == [name[i] for i in reversed(highs)]
        assert [e["name"] for e in top[38:]] == [name[3], name[17]]

        full = E.punts(snap, top=n)["pFt"]
        assert [e["name"] for e in full[38:43]] == [name[i] for i in ties]
        assert [e["gap"] for e in full[43:46]] == [5.0, 0.0, -2.0]
        assert [e["name"] for e in full[46:]] == [name[i] for i in nulls]
        assert all(e["gap"] is None and e["adp"] is None for e in full[46:])
        assert full[0] == {"rank": n - highs[-1], "name": name[highs[-1]],
                           "score": 0.5 + highs[-1], "adp": n - highs[-1] + 100.0,
                           "gap": 100.0}

    def test_a_player_without_a_build_rank_is_filtered_out(self):
        snap = make_snapshot(n=4)
        snap["players"][1]["punts"] = {}
        del snap["players"][2]["punts"]["pBlk"]
        got = E.punts(snap)
        assert list(got) == [k for k, _ in PUNT_BUILDS]
        assert len(got["pFt"]) == 3 and len(got["pBlk"]) == 2


class TestChecks:
    def test_counts_and_strings(self):
        snap = make_snapshot(n=6)
        for p, inj in zip(snap["players"], ["EXTREME", "HIGH", "MED", "LOW", "LOW", "?"],
                          strict=True):
            p["inj"] = inj
        for p in snap["players"]:
            p["adp"] = 10.0
        snap["players"][1]["adp"] = None
        snap["players"][4]["adp"] = None
        state = E.empty_state()
        tick(state, snap, 0, mine=True)
        tick(state, snap, 5, mine=True, gone=True)
        state["offboard"] = [{"name": "Zed Offboard", "pick": 99, "mine": True}]
        assert E.checks(snap, state) == {
            "names_aligned": "aligned", "rows_aligned": "aligned", "board_rows": 6,
            "mine": 2, "adp_coverage": "4 of 6", "generated": "2026-01-01",
            "digest": snap["meta"]["digest"],
            "injuries": "1 EXTREME / 1 HIGH / 1 MED / 2 LOW — 1 UNGRADED"}
        snap["players"][5]["inj"] = "LOW"
        assert E.checks(snap, state)["injuries"] == "1 EXTREME / 1 HIGH / 1 MED / 3 LOW"

    def test_structural_faults_read_misaligned(self):
        snap = make_snapshot(n=4)
        state = E.empty_state()
        snap["players"][1]["row"], snap["players"][2]["row"] = 2, 1
        assert E.checks(snap, state)["names_aligned"].startswith("MISALIGNED — ")
        snap = make_snapshot(n=4)
        del snap["players"][3]["values"]["HBP"]
        assert E.checks(snap, state)["names_aligned"].startswith("MISALIGNED — ")
        snap = make_snapshot(n=4)
        snap["meta"]["board_rows"] = 5
        assert E.checks(snap, state)["rows_aligned"].startswith("MISALIGNED — ")
        snap = make_snapshot(n=4)
        snap["players"][3]["key"] = snap["players"][0]["key"]
        assert E.checks(snap, state)["rows_aligned"].startswith("MISALIGNED — ")


def test_the_engine_imports_nothing_that_can_value_a_player():
    path = Path(E.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported == {"__future__", "math", "re", "board_snapshot"}
    assert not imported & {"bbm_reference", "board_values", "sources", "build_data"}
