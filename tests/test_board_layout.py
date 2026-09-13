"""The committed sheet layout, which Python reads instead of keeping its own column map.

`harness.js --write-layout` derives it from Build.gs's maps and the header cells the mock
build wrote, and `node harness.js` fails when it is stale. These tests pin the other side:
that it carries everything the local verifier and the engine look up, that its letters and
indices agree, and that it holds labels and addresses only -- it is committed to a public
repository, so a number that looks like a stat has no business in it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import board_settings
import board_snapshot
import board_values as BV

DIR = Path(__file__).resolve().parents[1] / "scripts" / "draft-board"
TEXT = (DIR / "board_layout.json").read_text(encoding="utf-8")
LAYOUT = json.loads(TEXT)
BUILD_GS = (DIR / "Build.gs").read_text(encoding="utf-8")
COLUMN_TABS = ("Draft Board", "Board", "BMP", "HBP", "BMP-ALT")
A1 = re.compile(r"^[A-Z]{1,3}[1-9]\d*$")
PREFIX = {"BMP": "bmp", "HBP": "hbp", "BMP-ALT": "alt"}


def letter(n: int) -> str:
    """Build.gs's a1col, for checking the letters it wrote."""
    s = ""
    while n > 0:
        n, m = divmod(n - 1, 26)
        s = chr(65 + m) + s
    return s


def draft_keys() -> set[str]:
    keys = {"rank", "tier", "round", "player", "team", "pos", "inj", "drafted", "mine", "sel",
            "drop", "med", "brk", "projGp", "myGp", "gpFlag", "adp", "xrank", "gap", "best",
            "strengths", "weaknesses", "posLeft", "notes", "hFgm", "hFga", "hFtm", "hFta", "h3",
            "hPts", "hReb", "hAst", "hStl", "hBlk", "rowCheck"}
    for src in board_snapshot.SOURCES:
        for kind in board_snapshot.KINDS:
            keys |= {f"{PREFIX[src]}{kind.capitalize()}", f"{PREFIX[src]}{kind.capitalize()}Tag",
                     f"rank:{src}:{kind}"}
    for cat in BV.CAT_LABELS:
        keys |= {f"dh:{cat}", f"d:{cat}"}
    return keys


def test_top_level_shape():
    assert LAYOUT["version"] == 1
    assert LAYOUT["generated_by"] == "node scripts/draft-board/harness.js --write-layout"
    assert (LAYOUT["header_row"], LAYOUT["first_row"], LAYOUT["last_row"]) == (3, 4, 203)
    assert list(LAYOUT["tabs"]) == ["Draft Board", "Board", "BMP", "HBP", "BMP-ALT", "Settings",
                                    "Category Tracker", "Punts"]
    assert TEXT.endswith("}\n") and TEXT == json.dumps(LAYOUT, indent=2, ensure_ascii=False) + "\n"


def test_draft_board_carries_exactly_the_columns_verify_and_the_engine_read():
    assert set(LAYOUT["tabs"]["Draft Board"]["columns"]) == draft_keys()


def test_board_and_calculation_tabs_carry_the_columns_that_are_read():
    board = set(LAYOUT["tabs"]["Board"]["columns"])
    assert {"player", "gp", "gp1", "gp2", "gp3", "myGp", "gpCheck", "adp", "xrank", "injuries",
            "notes"} <= board
    for src in board_snapshot.SOURCES:
        calc = set(LAYOUT["tabs"][src]["columns"])
        assert {"player", "durh", "durhRank", "durhDrop", "zsh", "zshRank", "zshDrop", "zsc",
                "zscRank", "adp"} <= calc
        assert {f"dh:{c}" for c in BV.CAT_LABELS} <= calc
        assert {f"pr:{k}" for k, _ in board_snapshot.PUNT_BUILDS} <= calc


def test_letters_agree_with_indices_and_every_column_appears_once():
    for tab in COLUMN_TABS:
        cols = LAYOUT["tabs"][tab]["columns"]
        indices = [c["index"] for c in cols.values()]
        assert sorted(indices) == list(range(1, len(indices) + 1)), tab
        assert indices == sorted(indices), f"{tab} is not written in column order"
        for key, c in cols.items():
            assert c["letter"] == letter(c["index"]), f"{tab} {key}"


def test_settings_cells_cover_every_sheet_key_and_the_stamp():
    s = LAYOUT["tabs"]["Settings"]
    want = set(board_settings.SHEET_KEYS) | {"q", "sort_by", "names_aligned", "rows_aligned",
                                             "board_rows", "mine", "adp_coverage", "generated",
                                             "injuries", "digest"}
    assert set(s["cells"]) == want
    assert set(s["cell_labels"]) == want
    assert s["cell_labels"]["digest"]["text"] == "Data digest"
    assert all(A1.match(a) for a in s["cells"].values())
    assert list(s["weights"]) == list(BV.CAT_LABELS) == list(s["tracker_constants"])
    for cat, block in s["tracker_constants"].items():
        rows = {re.sub(r"^[A-Z]+", "", a) for a in block.values()}
        assert set(block) == {"k", "w", "K", "slope"} and len(rows) == 1, cat


def test_input_cells_are_the_cells_the_named_ranges_point_at():
    s, names = LAYOUT["tabs"]["Settings"]["cells"], LAYOUT["named_ranges"]
    for key in board_settings.SHEET_KEYS + ("q", "sort_by"):
        assert names[key.upper()] == f"Settings!{s[key]}", key


def test_tracker_has_eight_category_rows_above_the_roster():
    t = LAYOUT["tabs"]["Category Tracker"]
    last_cat = t["first_cat_row"] + len(BV.CAT_LABELS) - 1
    assert t["header_row"] == t["first_cat_row"] - 1
    assert last_cat - t["first_cat_row"] + 1 == 8
    assert last_cat < t["roster_header_row"] < t["roster_first_row"]
    assert set(t["columns"]) == set(t["column_labels"])
    assert len(set(t["columns"].values())) == len(t["columns"])
    assert A1.match(t["players_ticked"])


def test_punt_blocks_follow_the_snapshot_order_and_do_not_overlap():
    p = LAYOUT["tabs"]["Punts"]
    assert [b["key"] for b in p["blocks"]] == [k for k, _ in board_snapshot.PUNT_BUILDS]
    firsts = [b["first_col"] for b in p["blocks"]]
    assert all(b - a == p["block_width"] for a, b in zip(firsts, firsts[1:], strict=False))
    assert all(0 <= c["offset"] < p["block_width"] for c in p["columns"].values())
    assert p["header_row"] == p["first_row"] - 1 and p["rows"] > 0


def test_named_ranges_are_addresses_on_known_tabs():
    shape = re.compile(r"^(?:'([^']+)'|([A-Za-z0-9_]+))!([A-Z]+[1-9]\d*)(?::([A-Z]+[1-9]\d*))?$")
    for name, address in LAYOUT["named_ranges"].items():
        m = shape.match(address)
        assert m, f"{name}: {address}"
        assert (m.group(1) or m.group(2)) in LAYOUT["tabs"], name


def test_it_holds_labels_and_addresses_only():
    # No decimal anywhere: a number with a fractional part in this file would be a stat.
    assert not re.search(r"\d\.\d", TEXT)
    labels = []
    for tab in COLUMN_TABS:
        labels += [c["label"] for c in LAYOUT["tabs"][tab]["columns"].values()]
    labels += [c["text"] for c in LAYOUT["tabs"]["Settings"]["cell_labels"].values()]
    t = LAYOUT["tabs"]["Category Tracker"]
    labels += list(t["column_labels"].values()) + list(t["roster_labels"].values())
    labels += [c["label"] for c in LAYOUT["tabs"]["Punts"]["columns"].values()]
    # Every word of every label is written somewhere in Build.gs. A player name would not be.
    for label in labels:
        for word in label.split():
            assert word in BUILD_GS, f"label word {word!r} does not come from Build.gs"
