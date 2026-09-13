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
    put(pull, "Draft Board", D["drafted"]["index"], FIRST + 1, True)
    put(pull, "Category Tracker", T["columns"]["punted"], T["first_cat_row"] + 2, True)
    sheet = VL._Pull(pull)
    assert TS.counts(sheet, LAYOUT) == {"mine": 1, "gone": 1, "punted": 1}
    punt = PS.col_letter(T["columns"]["punted"])
    assert TS.ticked_cells(sheet, LAYOUT) == [
        ("Draft Board", f"{D['drafted']['letter']}{FIRST + 1}"),
        ("Draft Board", f"{D['mine']['letter']}{FIRST}"),
        ("Category Tracker", f"{punt}{T['first_cat_row'] + 2}")]


def test_clean_rows_come_from_the_bottom_and_skip_anything_touched():
    pull = blank_pull()
    put(pull, "Draft Board", D["mine"]["index"], LAST, True)            # ticked
    put(pull, "Board", B["notes"]["index"], LAST - 1, "a note")         # noted
    put(pull, "Draft Board", D["myGp"]["index"], LAST - 2, 55)          # overridden
    ra, na, rb, nb, ro = TS.clean_rows(VL._Pull(pull), LAYOUT)
    assert (ra, rb, ro) == (LAST - 3, LAST - 4, LAST - 5)
    assert (na, nb) == (f"Player {LAST - 3}", f"Player {LAST - 4}")


def test_too_few_clean_rows_stops_the_step():
    pull = blank_pull()
    for row in range(FIRST, LAST - 1):
        put(pull, "Draft Board", D["drafted"]["index"], row, True)
    with pytest.raises(TS.StepFailed, match="fewer than three"):
        TS.clean_rows(VL._Pull(pull), LAYOUT)


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
