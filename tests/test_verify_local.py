"""verify.py --local, against a sheet rendered from the engine itself.

`fake_pulls` draws what a correct sheet would display for a synthetic snapshot and draft state,
in the exact shape pull_sheet.py writes. A clean render must pass; each test then breaks one
thing the way a real sheet breaks and checks the verdict and the exit code. The render maps
Draft Board columns to engine fields on its own, not through verify_local's table, so a wrong
entry in that table fails here rather than agreeing with itself.
"""

from __future__ import annotations

import json
import math

import board_engine as ENGINE
import board_values as BV
import pull_sheet as PS
import verify
import verify_local as VL

from board_fixtures import make_snapshot, set_values, write_snapshot

LAYOUT = json.loads(PS.LAYOUT.read_text(encoding="utf-8"))
DB = "Draft Board"
PREFIX = {"bmp": "BMP", "hbp": "HBP", "alt": "BMP-ALT"}
FEEDS = {"hFgm": "fgm", "hFga": "fga", "hFtm": "ftm", "hFta": "fta", "h3": "tpm", "hPts": "pts",
         "hReb": "reb", "hAst": "ast", "hStl": "stl", "hBlk": "blk"}
FIELD = {"rank": "rank", "tier": "tier", "round": "rnd", "player": "name", "team": "team",
         "pos": "pos", "inj": "inj", "drafted": "gone", "mine": "mine", "drop": "drop",
         "med": "med", "brk": "brk", "projGp": "gp", "myGp": "my_gp", "gpFlag": "gp_flag",
         "adp": "adp", "xrank": "xrank", "gap": "gap", "best": "best_build",
         "strengths": "strengths", "weaknesses": "weaknesses", "posLeft": "left_at_pos",
         "notes": "notes"}


def draft_cell(key: str, row: dict, player: dict, sort: dict):
    if key in FIELD:
        return row[FIELD[key]]
    if key == "sel":
        return row["values"][f"{sort['source']}:{sort['kind']}"]
    if key == "rowCheck":
        return player["name"]
    if key in FEEDS:
        return player["hbp_raw"][FEEDS[key]]
    if key.startswith(("dh:", "d:")):
        block, cat = key.split(":", 1)
        return player["values"][sort["source"]][block][cat]
    if key.startswith("rank:"):
        _, src, kind = key.split(":")
        return player["values"][src][kind]["rank"]
    stem = key.removesuffix("Tag")
    block = "tags" if key.endswith("Tag") else "values"
    return row[block][f"{PREFIX[stem[:3]]}:{stem[3:].lower()}"]


def as_cell(value):
    """A value as gviz returns it: text in v, a number with its display text, "" as empty."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return {"v": value, "f": "TRUE" if value else "FALSE"}
    if isinstance(value, int | float):
        return {"v": float(value), "f": str(value)}
    return {"v": value, "f": None}


def fake_pulls(snapshot: dict, state: dict, layout: dict, settings: dict | None = None,
               row_order: list[int] | None = None) -> dict:
    """The pull file a correct sheet would produce for this snapshot, state and settings.

    `row_order` renders the Draft Board in a displayed order other than the engine's, the way
    a sheet shows it after a tie-break the engine did not make, or before a re-sort.
    """
    settings = dict(settings or snapshot["settings"])
    sort = state["applied_sort"]
    rows = ENGINE.board_rows(snapshot, state, settings, sort, row_order)
    trk = ENGINE.tracker(snapshot, state, settings, sort, rows=rows)
    chk = ENGINE.checks(snapshot, state)
    tabs, first = layout["tabs"], layout["first_row"]
    by_key = {p["key"]: p for p in snapshot["players"]}
    model: dict[tuple[str, int, int], object] = {}

    def put(sheet, col, row, value):
        model[(sheet, col, row)] = value

    def put_a1(sheet, a1, value):
        c, r, _, _ = PS.parse_a1(a1)
        put(sheet, c, r, value)

    for tab in (DB, "Board", "BMP", "HBP", "BMP-ALT"):
        for c in tabs[tab]["columns"].values():
            put(tab, c["index"], tabs[tab]["header_row"], c["label"])
    for i, row in enumerate(rows):
        for key, c in tabs[DB]["columns"].items():
            put(DB, c["index"], first + i, draft_cell(key, row, by_key[row["key"]], sort))
    bcols = tabs["Board"]["columns"]
    for i, p in enumerate(snapshot["players"]):
        st = ENGINE.player_state(state, p["key"])
        put("Board", bcols["player"]["index"], first + i, p["name"])
        put("Board", bcols["myGp"]["index"], first + i,
            p["hbp_raw"]["gp"] if st["my_gp"] is None else st["my_gp"])
        for key in ("xrank", "notes", "gp1", "gp2", "gp3"):
            put("Board", bcols[key]["index"], first + i, st[key])

    s = tabs["Settings"]
    for lab in s["cell_labels"].values():
        put_a1("Settings", lab["cell"], lab["text"])
    for key in VL.INPUT_KEYS:
        put_a1("Settings", s["cells"][key], settings[key])
    put_a1("Settings", s["cells"]["sort_by"], f"{sort['source']} · {sort['kind'].upper()}")
    for key in ("names_aligned", "rows_aligned", "board_rows", "mine", "adp_coverage",
                "generated", "injuries", "digest"):
        put_a1("Settings", s["cells"][key], chk[key])
    for cat in BV.CAT_LABELS:
        put_a1("Settings", s["weight_labels"][cat], cat)
        put_a1("Settings", s["weights"][cat], snapshot["deriv"].get("weights", {}).get(cat))
        put_a1("Settings", s["tracker_labels"][cat], cat)
        for name, block in VL.REPORTED.items():
            put_a1("Settings", s["tracker_constants"][cat][name],
                   snapshot["deriv"].get(block, {}).get(cat))

    t = tabs["Category Tracker"]
    put_a1("Category Tracker", t["players_ticked"], trk["n"])
    for key, col in t["columns"].items():
        put("Category Tracker", col, t["header_row"], t["column_labels"][key])
    for i, cat in enumerate(trk["cats"]):
        r = t["first_cat_row"] + i
        for key, field in (("cat", "cat"), ("my_team", "my_team"), ("avg_team", "avg_team"),
                           ("z", "z"), ("win", "win"), ("read", "read"),
                           ("punted", "conceded")):
            put("Category Tracker", t["columns"][key], r, cat[field])
    for key, col in t["roster_columns"].items():
        put("Category Tracker", col, t["roster_header_row"], t["roster_labels"][key])
    for j, entry in enumerate(trk["roster"]):
        for key, col in t["roster_columns"].items():
            put("Category Tracker", col, t["roster_first_row"] + j, entry[key])
    if not trk["roster"]:
        put("Category Tracker", t["roster_columns"]["rank"], t["roster_first_row"],
            "Nothing ticked yet")

    p = tabs["Punts"]
    blocks = ENGINE.punts(snapshot, top=p["rows"])
    for b in p["blocks"]:
        for col in p["columns"].values():
            put("Punts", b["first_col"] + col["offset"], p["header_row"], col["label"])
        for j, entry in enumerate(blocks[b["key"]]):
            for key, col in p["columns"].items():
                put("Punts", b["first_col"] + col["offset"], p["first_row"] + j, entry[key])

    pulls = {"pulled_at": "2026-01-01T00:00:00+00:00", "label": "copy", "ranges": {}}
    for r in PS.plan_ranges(layout):
        c1, r1, _, _ = PS.parse_a1(r["range"])
        cells = [[as_cell(model.get((r["sheet"], c1 + j, r1 + i))) for j in range(r["cols"])]
                 for i in range(r["rows"])]
        pulls["ranges"][r["name"]] = {"sheet": r["sheet"], "range": r["range"],
                                      "type": r["type"], "cells": cells}
    return pulls


def drafted_state(snapshot: dict) -> dict:
    """A draft in progress: three of mine, three gone elsewhere, one category conceded."""
    state = ENGINE.empty_state()
    order = ENGINE.order(snapshot, state["applied_sort"])
    for n, idx in enumerate(order[:6]):
        p = snapshot["players"][idx]
        st = ENGINE.player_state(state, p["key"])
        st.update(name=p["name"], gone=True, mine=n % 2 == 0)
        state["players"][p["key"]] = st
    state["conceded"] = ["FT%"]
    return state


def cell_at(pulls: dict, sheet: str, col: int, row: int) -> tuple[dict, int, int]:
    """The (range, i, j) holding a sheet cell, so a test can overwrite exactly that cell."""
    for rng in pulls["ranges"].values():
        c1, r1, c2, r2 = PS.parse_a1(rng["range"])
        if rng["sheet"] == sheet and c1 <= col <= c2 and r1 <= row <= r2:
            return rng, row - r1, col - c1
    raise KeyError((sheet, col, row))


def set_cell(pulls, sheet, col, row, value):
    rng, i, j = cell_at(pulls, sheet, col, row)
    rng["cells"][i][j] = as_cell(value)


def set_error(pulls, sheet, col, row, text):
    """Plant a gviz error cell -- `{"v": null, "f": text}`, exactly what pull_sheet.py keeps."""
    rng, i, j = cell_at(pulls, sheet, col, row)
    rng["cells"][i][j] = {"v": None, "f": text}


def draft_col(key: str) -> int:
    return LAYOUT["tabs"][DB]["columns"][key]["index"]


def settings_cell(key: str) -> tuple[int, int]:
    c, r, _, _ = PS.parse_a1(LAYOUT["tabs"]["Settings"]["cells"][key])
    return c, r


def fails(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("FAIL")]


def setup():
    snapshot = make_snapshot()
    state = drafted_state(snapshot)
    return snapshot, state, fake_pulls(snapshot, state, LAYOUT)


def test_verify_compares_exactly_the_columns_in_the_layout():
    assert VL.expected_draft_keys(BV.CAT_LABELS) == set(LAYOUT["tabs"][DB]["columns"])


def test_verify_exports_diff_local():
    assert verify.diff_local is VL.diff_local


def test_a_sheet_that_matches_the_engine_passes():
    snapshot, _, pulls = setup()
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 0, lines
    assert not fails(lines)


def test_an_empty_draft_passes_too():
    snapshot = make_snapshot()
    state = ENGINE.empty_state()
    code, lines = VL.diff_local(snapshot, fake_pulls(snapshot, state, LAYOUT), LAYOUT)
    assert code == 0, lines


def test_one_wrong_tier_fails_and_names_its_row():
    snapshot, _, pulls = setup()
    row = LAYOUT["first_row"] + 5
    rng, i, j = cell_at(pulls, DB, draft_col("tier"), row)
    set_cell(pulls, DB, draft_col("tier"), row, rng["cells"][i][j]["v"] + 1)
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    tier = [line for line in fails(lines) if "(tier)" in line]
    assert len(tier) == 1 and f"row {row}" in tier[0] and "1 cell(s)" in tier[0]


def test_one_wrong_rank_on_an_untied_row_fails():
    snapshot, _, pulls = setup()
    row = LAYOUT["first_row"] + 5
    set_cell(pulls, DB, draft_col("rank"), row, 150)
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    assert any("(rank)" in line and f"row {row}" in line for line in fails(lines))


def test_a_changed_header_is_not_comparable():
    snapshot, _, pulls = setup()
    set_cell(pulls, DB, draft_col("tier"), LAYOUT["header_row"], "TIERS")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 3 and "not running this Build.gs" in lines[0]


def test_a_different_digest_is_not_comparable():
    snapshot, _, pulls = setup()
    set_cell(pulls, "Settings", *settings_cell("digest"), "0" * 64)
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 3 and "digest" in lines[0]


def test_a_misaligned_sanity_check_is_not_comparable():
    snapshot, _, pulls = setup()
    set_cell(pulls, "Settings", *settings_cell("rows_aligned"), "MISALIGNED — stop")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 3 and "aligned" in lines[0]


def test_a_player_the_snapshot_does_not_have_is_not_comparable():
    snapshot, _, pulls = setup()
    set_cell(pulls, DB, draft_col("player"), LAYOUT["first_row"] + 2, "Nobody Known")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 3 and f"row {LAYOUT['first_row'] + 2}" in lines[0]


def test_a_pull_that_misses_a_range_is_not_comparable():
    snapshot, _, pulls = setup()
    del pulls["ranges"][next(n for n in pulls["ranges"] if n.startswith("Punts!A6"))]
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 3 and "does not cover" in lines[0]


def test_settings_that_drifted_from_the_defaults_fail_on_their_own():
    snapshot = make_snapshot()
    state = drafted_state(snapshot)
    drifted = dict(snapshot["settings"], cat_band=snapshot["settings"]["cat_band"] + 0.5)
    code, lines = VL.diff_local(snapshot, fake_pulls(snapshot, state, LAYOUT, drifted), LAYOUT)
    assert code == 1
    assert len(fails(lines)) == 1 and "Settings inputs differ" in fails(lines)[0]
    assert "cat_band" in fails(lines)[0]


def test_sort_by_out_of_step_with_the_order_is_reported_not_failed():
    snapshot, _, pulls = setup()
    set_cell(pulls, "Settings", *settings_cell("sort_by"), "HBP · ZSC")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 0, lines
    assert any(line.startswith("NOTE") and "SORT_BY" in line for line in lines)


def test_a_tie_group_whose_ranks_the_sheet_ordered_differently_still_passes():
    snapshot = make_snapshot()
    sort = ENGINE.DEFAULT_SORT
    order = ENGINE.order(snapshot, sort)
    top, second = (snapshot["players"][i] for i in order[:2])
    second["values"]["BMP"]["durh"]["v"] = top["values"]["BMP"]["durh"]["v"]
    for rank, idx in enumerate(ENGINE.order(snapshot, sort)):
        snapshot["players"][idx]["values"]["BMP"]["durh"]["rank"] = rank + 1
    state = ENGINE.empty_state()
    pulls = fake_pulls(snapshot, state, LAYOUT)
    teams = snapshot["settings"]["teams"]
    first = LAYOUT["first_row"]
    shown = ENGINE.order(snapshot, sort)
    for i, rank in ((0, 2), (1, 1)):
        p = snapshot["players"][shown[i]]
        set_cell(pulls, DB, draft_col("rank"), first + i, rank)
        set_cell(pulls, DB, draft_col("round"), first + i, math.ceil(rank / teams))
        set_cell(pulls, DB, draft_col("gap"), first + i,
                 None if p["adp"] is None else p["adp"] - rank)
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 0, lines


def test_a_wrong_tracker_read_fails():
    snapshot, _, pulls = setup()
    t = LAYOUT["tabs"]["Category Tracker"]
    set_cell(pulls, "Category Tracker", t["columns"]["read"], t["first_cat_row"] + 2,
             "■ BANKED")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1 and any("(read)" in line for line in fails(lines))


def test_a_wrong_punt_score_fails():
    snapshot, _, pulls = setup()
    p = LAYOUT["tabs"]["Punts"]
    b = p["blocks"][0]
    set_cell(pulls, "Punts", b["first_col"] + p["columns"]["score"]["offset"], p["first_row"],
             99.0)
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1 and any(line.startswith("FAIL: Punts") for line in fails(lines))


def test_output_names_no_player(tmp_path, capsys):
    snapshot = make_snapshot()
    state = drafted_state(snapshot)
    pulls = fake_pulls(snapshot, state, LAYOUT)
    first = LAYOUT["first_row"]
    set_cell(pulls, DB, draft_col("tier"), first + 3, 42)
    set_cell(pulls, DB, draft_col("team"), first + 4, "ZZZ")
    set_cell(pulls, DB, draft_col("notes"), first + 1, "a note nobody wrote")
    pull_path = tmp_path / "pull.json"
    pull_path.write_text(json.dumps(pulls), encoding="utf-8")
    snap_path = write_snapshot(tmp_path, snapshot)

    code = verify.main(["--local", str(pull_path), "--snapshot", str(snap_path)])
    out = capsys.readouterr()
    assert code == 1
    text = out.out + out.err
    assert "(tier)" in text and "(team)" in text and "(notes)" in text
    for p in snapshot["players"]:
        assert p["name"] not in text


def test_missing_inputs_are_a_usage_error(tmp_path):
    assert verify.main(["--local", str(tmp_path / "absent.json"),
                        "--snapshot", str(tmp_path / "absent-snapshot.json")]) == 2


# --- displayed order, a board whose sources disagree, and a lost hand column ------------


def swapped(order: list[int], i: int) -> list[int]:
    """`order` with displayed positions i and i + 1 exchanged: whole rows, not rank cells."""
    shown = list(order)
    shown[i], shown[i + 1] = shown[i + 1], shown[i]
    return shown


def test_two_tied_rows_shown_in_the_other_order_still_pass():
    snapshot = make_snapshot()
    sort = ENGINE.DEFAULT_SORT
    order = ENGINE.order(snapshot, sort)
    vals = [p["values"]["BMP"]["durh"]["v"] for p in snapshot["players"]]
    vals[order[4]] = vals[order[3]]
    set_values(snapshot, "BMP", "durh", vals)
    shown = swapped(ENGINE.order(snapshot, sort), 3)
    code, lines = VL.diff_local(snapshot, fake_pulls(snapshot, ENGINE.empty_state(), LAYOUT,
                                                     row_order=shown), LAYOUT)
    assert code == 0, lines
    assert any("(2 rows in tie groups)" in line for line in lines)


def test_two_untied_rows_shown_in_the_other_order_fail_by_row():
    snapshot = make_snapshot()
    shown = swapped(ENGINE.order(snapshot, ENGINE.DEFAULT_SORT), 3)
    code, lines = VL.diff_local(snapshot, fake_pulls(snapshot, ENGINE.empty_state(), LAYOUT,
                                                     row_order=shown), LAYOUT)
    assert code == 1
    moved = [line for line in fails(lines) if "out of BMP · DURH order" in line]
    assert len(moved) == 1
    assert "on 2 rows" in moved[0] and f"first at row {LAYOUT['first_row'] + 3}" in moved[0]


def varied() -> tuple[dict, dict]:
    """Sources that rank the board differently, a tie in the applied sort, ticks below the top.

    The default fixture ranks every source the same way, so its disagreement flags never fire
    and its sort never ties. Here HBP ZSH is applied, two players tie on it, HBP DURH runs the
    other way and BMP-ALT ZSC is a permutation, so the disagreement check, the tie-set path and
    the sorted-by derivation all have something to do.
    """
    snapshot = make_snapshot()
    set_values(snapshot, "HBP", "zsh", [0.3, 1.2, 0.9, 1.5, 0.9, 0.1, 1.1, 0.7, 1.4, 0.2, 0.8,
                                        1.3, 0.6, 1.0, 0.4])
    set_values(snapshot, "HBP", "durh", [float(i) for i in range(15)])
    set_values(snapshot, "BMP-ALT", "zsc", [float((i * 7) % 15) for i in range(15)])
    state = ENGINE.empty_state()
    state["applied_sort"] = {"source": "HBP", "kind": "zsh"}
    shown = ENGINE.order(snapshot, state["applied_sort"])
    for n, idx in enumerate((shown[4], shown[7], shown[9], shown[12], shown[14])):
        p = snapshot["players"][idx]
        st = ENGINE.player_state(state, p["key"])
        st.update(name=p["name"], gone=True, mine=n % 2 == 0)
        state["players"][p["key"]] = st
    key = snapshot["players"][shown[10]]["key"]
    state["players"][key] = {**ENGINE.player_state(state, key), "my_gp": 40, "xrank": 3,
                             "notes": "a note nobody wrote"}
    state["conceded"] = ["BLK"]
    return snapshot, state


def test_a_varied_board_under_a_non_default_sort_passes():
    snapshot, state = varied()
    rows = ENGINE.board_rows(snapshot, state, snapshot["settings"], state["applied_sort"])
    assert sum(1 for r in rows for flag in r["disagree"].values() if flag) > 0
    code, lines = VL.diff_local(snapshot, fake_pulls(snapshot, state, LAYOUT), LAYOUT)
    assert code == 0, lines
    assert "ok: the board is sorted by HBP · ZSH" in lines
    assert any("(2 rows in tie groups)" in line for line in lines)


def test_a_wrong_disagreement_condition_fails():
    snapshot, state = varied()
    rows = ENGINE.board_rows(snapshot, state, snapshot["settings"], state["applied_sort"])
    sel = [r["sel"] for r in rows]
    i, sk = next((i, sk) for i, r in enumerate(rows) if sel.count(r["sel"]) == 1
                 for sk, flag in r["disagree"].items() if flag)
    pulls = fake_pulls(snapshot, state, LAYOUT)
    # The source's rank now equals the rank shown, so the sheet's condition says "no
    # disagreement" on a row where the engine flags one.
    set_cell(pulls, DB, draft_col(f"rank:{sk}"), LAYOUT["first_row"] + i, rows[i]["rank"])
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    assert any(line.startswith("FAIL: disagreement") for line in fails(lines))


def test_a_board_hand_column_the_pull_lost_is_caught_by_its_draft_board_mirror():
    # Board hand columns are sparse ranges read as engine input. If one came back blank, the
    # engine would compute from "no override" -- and the Draft Board's My GP, which mirrors
    # the Board and sits in a range of always-filled columns, would then disagree with it.
    snapshot = make_snapshot()
    state = drafted_state(snapshot)
    key = snapshot["players"][4]["key"]
    state["players"][key] = {**ENGINE.player_state(state, key), "my_gp": 40}
    pulls = fake_pulls(snapshot, state, LAYOUT)
    board_my_gp = LAYOUT["tabs"]["Board"]["columns"]["myGp"]["index"]
    set_cell(pulls, "Board", board_my_gp, LAYOUT["first_row"] + 4, None)
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    assert any("(myGp)" in line for line in fails(lines))


# --- error cells never compare equal to a blank (fix round 1, finding 1) -----------------


def test_an_error_cell_in_a_blank_optional_column_fails():
    snapshot, _, pulls = setup()
    row = LAYOUT["first_row"]
    set_error(pulls, DB, draft_col("xrank"), row, "#REF!")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    assert any("(xrank)" in line and f"row {row}" in line for line in fails(lines))


def test_an_error_cell_in_a_boolean_column_fails():
    snapshot, _, pulls = setup()
    row = LAYOUT["first_row"] + 5
    set_error(pulls, DB, draft_col("mine"), row, "#REF!")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    assert any("(mine)" in line and f"row {row}" in line for line in fails(lines))


def test_a_div0_no_attempts_tracker_cell_still_passes():
    snapshot = make_snapshot()
    state = ENGINE.empty_state()
    order = ENGINE.order(snapshot, state["applied_sort"])
    p = snapshot["players"][order[0]]
    st = ENGINE.player_state(state, p["key"])
    st.update(name=p["name"], mine=True)
    state["players"][p["key"]] = st
    p["hbp_raw"] = {**p["hbp_raw"], "fga": 0.0, "fgm": 0.0}
    trk = ENGINE.tracker(snapshot, state, snapshot["settings"], state["applied_sort"])
    cat_i, cat = next((i, c) for i, c in enumerate(trk["cats"]) if c["cat"] == "FG%")
    assert cat["flag"] == "no_attempts" and cat["my_team"] is None
    pulls = fake_pulls(snapshot, state, LAYOUT)
    t = LAYOUT["tabs"]["Category Tracker"]
    row = t["first_cat_row"] + cat_i
    set_error(pulls, "Category Tracker", t["columns"]["my_team"], row, "#DIV/0!")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 0, lines


def test_a_div0_tracker_cell_without_the_no_attempts_flag_fails():
    snapshot, state, pulls = setup()
    trk = ENGINE.tracker(snapshot, state, snapshot["settings"], state["applied_sort"])
    cat_i, cat = next((i, c) for i, c in enumerate(trk["cats"]) if c["flag"] is None)
    assert cat["my_team"] is not None
    t = LAYOUT["tabs"]["Category Tracker"]
    row = t["first_cat_row"] + cat_i
    set_error(pulls, "Category Tracker", t["columns"]["my_team"], row, "#DIV/0!")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    assert any("(my_team)" in line and f"row {row}" in line for line in fails(lines))


# --- pull_sheet.py and verify.py exit cleanly on bad input (fix round 1, finding 3) -------


def test_a_non_json_pull_is_a_usage_error(tmp_path):
    snap_path = write_snapshot(tmp_path, make_snapshot())
    pull_path = tmp_path / "pull.json"
    pull_path.write_text("{not json", encoding="utf-8")
    assert VL.run_local(pull_path, snap_path) == 2


def test_a_pull_with_no_ranges_object_is_a_usage_error(tmp_path):
    snap_path = write_snapshot(tmp_path, make_snapshot())
    pull_path = tmp_path / "pull.json"
    pull_path.write_text(json.dumps({"label": "live"}), encoding="utf-8")
    assert VL.run_local(pull_path, snap_path) == 2


def test_a_missing_snapshot_with_a_present_pull_is_a_usage_error(tmp_path):
    _, _, pulls = setup()
    pull_path = tmp_path / "pull.json"
    pull_path.write_text(json.dumps(pulls), encoding="utf-8")
    assert VL.run_local(pull_path, tmp_path / "absent-snapshot.json") == 2


def test_a_pull_whose_range_is_missing_its_own_range_key_is_not_comparable():
    # Not a NotComparable this module raises on purpose -- a structurally broken pull that
    # would otherwise crash diff_local outright. KeyError/TypeError/IndexError from a pull
    # that is not pull_sheet.py's shape are reported as NOT COMPARABLE rather than a traceback.
    snapshot, _, pulls = setup()
    name = next(iter(pulls["ranges"]))
    del pulls["ranges"][name]["range"]
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 3
    assert lines[0].startswith("NOT COMPARABLE:")


# --- an error cell in a Punts sparse field never compares equal to a blank (fix round 2) -


def no_adp_punt_row(snapshot: dict, build_key: str = "pFt") -> int:
    """The sheet row, in `build_key`'s Punts block, holding the first no-ADP player."""
    entries = ENGINE.punts(snapshot, top=len(snapshot["players"]))[build_key]
    j = next(j for j, e in enumerate(entries) if e["adp"] is None)
    return LAYOUT["tabs"]["Punts"]["first_row"] + j


def test_the_clean_fake_pull_with_a_no_adp_player_still_passes():
    snapshot, _, pulls = setup()
    no_adp_punt_row(snapshot)  # raises StopIteration if this fixture ever stops having one
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 0, lines


def test_an_error_cell_in_a_no_adp_punt_row_adp_fails():
    snapshot, _, pulls = setup()
    p = LAYOUT["tabs"]["Punts"]
    b = p["blocks"][0]
    row = no_adp_punt_row(snapshot, b["key"])
    set_error(pulls, "Punts", b["first_col"] + p["columns"]["adp"]["offset"], row, "#REF!")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    assert any(line.startswith("FAIL: Punts") and "(adp)" in line and f"row {row}" in line
              for line in fails(lines))


def test_an_error_cell_in_a_no_adp_punt_row_gap_fails():
    snapshot, _, pulls = setup()
    p = LAYOUT["tabs"]["Punts"]
    b = p["blocks"][0]
    row = no_adp_punt_row(snapshot, b["key"])
    set_error(pulls, "Punts", b["first_col"] + p["columns"]["gap"]["offset"], row, "#DIV/0!")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    assert any(line.startswith("FAIL: Punts") and "(gap)" in line and f"row {row}" in line
              for line in fails(lines))


def test_an_error_cell_in_a_punt_score_fails():
    snapshot, _, pulls = setup()
    p = LAYOUT["tabs"]["Punts"]
    b = p["blocks"][0]
    row = p["first_row"]
    set_error(pulls, "Punts", b["first_col"] + p["columns"]["score"]["offset"], row, "#REF!")
    code, lines = VL.diff_local(snapshot, pulls, LAYOUT)
    assert code == 1
    assert any(line.startswith("FAIL: Punts") and "(score)" in line and f"row {row}" in line
              for line in fails(lines))
