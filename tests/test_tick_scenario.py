"""tick_scenario.py's pure parts, with no browser: the run gate, tick counts and the row picker.

Every pull here is synthetic: planned ranges from the committed layout, filled with invented
names and numbers.
"""

from __future__ import annotations

import json
import subprocess

import pull_sheet as PS
import pytest
import tick_scenario as TS
import verify_local as VL

LAYOUT = json.loads(PS.LAYOUT.read_text(encoding="utf-8"))
FIRST, LAST = LAYOUT["first_row"], LAYOUT["last_row"]
D = LAYOUT["tabs"]["Draft Board"]["columns"]
B = LAYOUT["tabs"]["Board"]["columns"]
T = LAYOUT["tabs"]["Category Tracker"]


def blank_pull() -> dict:
    """Every planned cell empty, then every row a clean invented player with My GP = GP."""
    ranges = {}
    for r in PS.plan_ranges(LAYOUT):
        empty = {"v": False, "f": None} if r["type"] == "boolean" else None
        ranges[r["name"]] = {"sheet": r["sheet"], "range": r["range"], "type": r["type"],
                             "cells": [[empty] * r["cols"] for _ in range(r["rows"])]}
    pull = {"ranges": ranges}
    for row in range(FIRST, LAST + 1):
        put(pull, "Draft Board", D["player"]["index"], row, f"Player {row}")
        put(pull, "Board", B["player"]["index"], row, f"Player {row}")
        put(pull, "Draft Board", D["projGp"]["index"], row, 70)
        put(pull, "Draft Board", D["myGp"]["index"], row, 70)
    return pull


def put(pull: dict, sheet: str, col: int, row: int, value) -> None:
    for rng in pull["ranges"].values():
        c1, r1, c2, r2 = PS.parse_a1(rng["range"])
        if rng["sheet"] == sheet and c1 <= col <= c2 and r1 <= row <= r2:
            rng["cells"][row - r1][col - c1] = {"v": value, "f": None}
            return
    raise AssertionError(f"{sheet} col {col} row {row} is not in any planned range")


def test_counts_and_inherited_ticks():
    pull = blank_pull()
    put(pull, "Draft Board", D["mine"]["index"], FIRST, True)
    put(pull, "Draft Board", D["cmp"]["index"], FIRST + 1, True)
    put(pull, "Category Tracker", T["columns"]["punted"], T["first_cat_row"] + 2, True)
    sheet = VL._Pull(pull)
    assert TS.counts(sheet, LAYOUT) == {"mine": 1, "cmp": 1, "punted": 1, "slots": 0,
                                        "clear": 0}
    punt = PS.col_letter(T["columns"]["punted"])
    assert TS.ticked_cells(sheet, LAYOUT) == [
        ("Draft Board", f"{D['cmp']['letter']}{FIRST + 1}"),
        ("Draft Board", f"{D['mine']['letter']}{FIRST}"),
        ("Category Tracker", f"{punt}{T['first_cat_row'] + 2}")]


C = T["compare"]


def test_filled_slots_and_a_stuck_clear_box_are_counted():
    pull = blank_pull()
    for s in C["slots"][:2]:
        put(pull, "Category Tracker", s["index"], C["slot_row"], "Player 9")
    col, row, _, _ = PS.parse_a1(C["clear"])
    put(pull, "Category Tracker", col, row, True)
    got = TS.counts(VL._Pull(pull), LAYOUT)
    assert (got["slots"], got["clear"]) == (2, 1)


def test_the_cmp_rows_straddle_mine_and_overflow_the_panel():
    # Two of them sit on rows step a ticks MINE, so the panel sees six and shows five.
    mine = set(range(FIRST, FIRST + 14))
    assert len(TS.CMP_ROWS) == 8 and len(mine.intersection(TS.CMP_ROWS)) == 2
    assert len(set(TS.CMP_ROWS) - mine) > len(C["slots"])
    assert not set(TS.CLEAR_ROWS) & (mine | set(TS.CMP_ROWS) | {TS.MINE_ROW})


def test_clean_rows_come_from_the_bottom_and_skip_anything_touched():
    pull = blank_pull()
    put(pull, "Draft Board", D["mine"]["index"], LAST, True)            # ticked
    put(pull, "Board", B["notes"]["index"], LAST - 1, "a note")         # noted
    put(pull, "Draft Board", D["myGp"]["index"], LAST - 2, 55)          # overridden
    ra, na, rb, nb = TS.clean_rows(VL._Pull(pull), LAYOUT)
    assert (ra, rb) == (LAST - 3, LAST - 4)
    assert (na, nb) == (f"Player {LAST - 3}", f"Player {LAST - 4}")


def test_too_few_clean_rows_stops_the_step():
    pull = blank_pull()
    for row in range(FIRST, LAST):
        put(pull, "Draft Board", D["cmp"]["index"], row, True)
    with pytest.raises(TS.StepFailed, match="fewer than two"):
        TS.clean_rows(VL._Pull(pull), LAYOUT)


def put_settings(pull: dict, key: str, value) -> None:
    c, r, _, _ = PS.parse_a1(LAYOUT["tabs"]["Settings"]["cells"][key])
    put(pull, "Settings", c, r, value)


def test_a_sort_that_never_reached_sort_by_fails_step_d():
    want = "Source · KIND"
    pull = blank_pull()
    put_settings(pull, "sort_by", "Other · KIND")
    lines = ["ok: the board is sorted by Other · KIND"]
    assert "SORT_BY reads" in TS.sort_applied(VL._Pull(pull), LAYOUT, lines, want)

    put_settings(pull, "sort_by", want)                      # set, but never re-sorted
    assert "not sorted by it" in TS.sort_applied(VL._Pull(pull), LAYOUT, lines, want)
    assert TS.sort_applied(VL._Pull(pull), LAYOUT, [f"ok: the board is sorted by {want}"],
                           want) is None


def test_a_hand_value_kept_by_row_position_fails_step_e():
    # Typed on row a while it showed "Player b"; Refresh put the names back in order.
    a, b = LAST - 1, LAST
    owner, other = f"Player {a + 1}", f"Player {a}"          # rows a+1 == b and a
    pull = blank_pull()
    put(pull, "Board", B["gp1"]["index"], a, 50)             # left where it was typed
    assert "did not follow" in TS.hand_value_followed(VL._Pull(pull), LAYOUT, owner, other, 50)

    pull = blank_pull()
    put(pull, "Board", B["gp1"]["index"], b, 50)             # followed its player
    assert TS.hand_value_followed(VL._Pull(pull), LAYOUT, owner, other, 50) is None

    put(pull, "Board", B["gp1"]["index"], a, 50)             # followed, and also left behind
    assert "also left" in TS.hand_value_followed(VL._Pull(pull), LAYOUT, owner, other, 50)
    assert "no longer" in TS.hand_value_followed(VL._Pull(pull), LAYOUT, "Nobody", other, 50)


@pytest.mark.parametrize("got", [{"id": "copy-id", "error": "the copy never finished loading"},
                                 {"id": "copy-id", "title": "Not a copy"}])
def test_a_copy_that_fails_after_it_exists_is_still_recorded_for_deletion(got):
    browser = TS.Browser("live-id")
    browser.run = lambda body, **args: got
    with pytest.raises(TS.StepFailed):
        browser.make_copy()
    assert browser.copy_id == "copy-id"


def test_the_live_sheet_is_never_recorded_as_the_copy():
    browser = TS.Browser("live-id")
    browser.run = lambda body, **args: {"id": "live-id", "title": "Copy of x"}
    with pytest.raises(TS.StepFailed, match="not a copy"):
        browser.make_copy()
    assert browser.copy_id is None


def test_the_run_gate(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    watched = tmp_path / TS.WATCHED[0]
    watched.parent.mkdir(parents=True)
    watched.write_text("one\n")
    (tmp_path / "other.txt").write_text("x\n")
    git("add", ".")
    git("commit", "-qm", "c1")
    last = tmp_path / "last-scenario"
    assert TS.needed(tmp_path, last)                       # never passed
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True,
                         text=True).stdout.strip()
    last.write_text(sha + "\n")
    assert not TS.needed(tmp_path, last)                   # nothing changed
    (tmp_path / "other.txt").write_text("y\n")
    assert not TS.needed(tmp_path, last)                   # an unwatched change
    watched.write_text("two\n")
    assert TS.needed(tmp_path, last)                       # a watched change, uncommitted
    last.write_text("0000000000000000000000000000000000000000\n")
    assert TS.needed(tmp_path, last)                       # an unknown sha


FP = {"tick": "aaaa", "rebuild": "bbbb"}


def stamp(last, sha="deadbeef", **over):
    last.write_text(json.dumps({"sha": sha, **FP, **over}), encoding="utf-8")


class TestTier:
    """The gate returns how much of the scenario a change can actually affect (ADR-0025).

    A width, a colour or a README row moves neither hash, and the browser is never opened.
    """

    def test_a_first_run_proves_everything(self, tmp_path):
        assert TS.tier_needed(tmp_path, tmp_path / "none", FP, engine_changed=False) == "full"

    def test_nothing_moved_skips_entirely(self, tmp_path):
        last = tmp_path / "last"
        stamp(last)
        assert TS.tier_needed(tmp_path, last, FP, engine_changed=False) == "none"

    def test_a_tick_formula_runs_the_tick_tier(self, tmp_path):
        last = tmp_path / "last"
        stamp(last, tick="zzzz")
        assert TS.tier_needed(tmp_path, last, FP, engine_changed=False) == "ticks"

    def test_a_rebuild_formula_runs_everything(self, tmp_path):
        last = tmp_path / "last"
        stamp(last, rebuild="zzzz")
        assert TS.tier_needed(tmp_path, last, FP, engine_changed=False) == "full"

    def test_the_python_mirror_changing_runs_the_tick_tier(self, tmp_path):
        # board_engine.py is not in the sheet, so no hash moves -- but the mirror is what
        # the scenario compares against at every tick state.
        last = tmp_path / "last"
        stamp(last)
        assert TS.tier_needed(tmp_path, last, FP, engine_changed=True) == "ticks"

    def test_a_stamp_from_before_the_fingerprint_proves_everything(self, tmp_path):
        last = tmp_path / "last"
        last.write_text("deadbeef\n", encoding="utf-8")       # the old plain-sha format
        assert TS.tier_needed(tmp_path, last, FP, engine_changed=False) == "full"
