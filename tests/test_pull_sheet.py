"""pull_sheet.py, with no browser: a canned gviz response and canned playwright-cli output.

Every table here is invented. The sheet id is a made-up token, short enough that it cannot be
mistaken for a real one.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pull_sheet as PS
import pytest

LAYOUT = json.loads(PS.LAYOUT.read_text(encoding="utf-8"))
FAKE_ID = "fake-sheet-id"
ENV_KEY = "DRAFT_SHEET_ID"


def by_name(ranges: list[dict]) -> dict[str, dict]:
    return {r["name"]: r for r in ranges}


def filled(r: dict, rows: int | None = None) -> dict:
    """A gviz table for range `r`, every cell filled with a value of the range's type.

    A range with an anchor is answered the way gviz actually answers a `tq=select` request:
    the target columns in order, then the anchor's own always-filled column tacked on last --
    `r["select"]` already lists both, in that order.
    """
    value = {"number": 1.0, "string": "x", "boolean": True}[r["type"]]
    count = r["rows"] if rows is None else rows
    if r.get("anchor"):
        cols = r["select"]
        row = [{"v": value, "f": None}] * r["cols"] + [{"v": "Anchor", "f": None}]
    else:
        cols = [PS.col_letter(i + 1) for i in range(r["cols"])]
        row = [{"v": value, "f": None}] * r["cols"]
    return {"status": "ok", "cols": cols, "rows": [row for _ in range(count)]}


def canned(ranges: list[dict]) -> dict:
    return {r["name"]: filled(r) for r in ranges}


def stdout_for(payload: dict) -> str:
    """What playwright-cli prints: the eval's return value as a JSON-quoted string."""
    return ("### Result\n" + json.dumps(json.dumps(payload)) + "\n"
            "### Ran Playwright code\n```js\nawait page.evaluate('() => 1');\n```\n")


class TestPlan:
    def test_every_range_is_one_type_with_a_consistent_size(self):
        ranges = PS.plan_ranges(LAYOUT)
        assert len({r["name"] for r in ranges}) == len(ranges)
        for r in ranges:
            assert r["type"] in {"string", "number", "boolean"}
            c1, r1, c2, r2 = PS.parse_a1(r["range"])
            assert (r["rows"], r["cols"]) == (r2 - r1 + 1, c2 - c1 + 1)
            assert 0 <= r["min_cells"] <= r["rows"] * r["cols"]
            assert r["name"] == f"{r['sheet']}!{r['range']}"

    def test_settings_b4_to_b11_is_split_by_type(self):
        ranges = by_name(PS.plan_ranges(LAYOUT))
        assert {"Settings!B4:B6", "Settings!B7:B8", "Settings!B9:B11"} <= set(ranges)
        assert ranges["Settings!B7:B8"]["type"] == "string"
        assert ranges["Settings!B4:B6"]["type"] == "number"

    def test_the_stamp_cells_are_pulled_alone(self):
        ranges = by_name(PS.plan_ranges(LAYOUT))
        cells = LAYOUT["tabs"]["Settings"]["cells"]
        for key in ("generated", "digest"):
            assert f"Settings!{cells[key]}" in ranges

    def test_every_draft_board_column_is_in_exactly_one_data_range(self):
        cols = LAYOUT["tabs"]["Draft Board"]["columns"]
        seen = []
        for r in PS.plan_ranges(LAYOUT):
            c1, r1, c2, r2 = PS.parse_a1(r["range"])
            if r["sheet"] == "Draft Board" and r1 == LAYOUT["first_row"]:
                assert r2 == LAYOUT["last_row"]
                seen += list(range(c1, c2 + 1))
        assert sorted(seen) == sorted(c["index"] for c in cols.values())

    def test_gone_and_mine_are_a_boolean_range(self):
        cols = LAYOUT["tabs"]["Draft Board"]["columns"]
        a1 = (f"{cols['drafted']['letter']}{LAYOUT['first_row']}:"
              f"{cols['mine']['letter']}{LAYOUT['last_row']}")
        assert by_name(PS.plan_ranges(LAYOUT))[f"Draft Board!{a1}"]["type"] == "boolean"

    def test_a_column_nobody_typed_stops_the_plan(self):
        layout = json.loads(json.dumps(LAYOUT))
        layout["tabs"]["Draft Board"]["columns"]["brandNew"] = {"index": 99, "letter": "CU",
                                                                "label": "New"}
        with pytest.raises(ValueError, match="brandNew"):
            PS.plan_ranges(layout)

    def test_a_range_that_can_go_fully_blank_carries_the_player_anchor(self):
        # Break (AE) is a single optional column: every row can legitimately be blank there,
        # exactly the shape gviz drops from the middle of a reply, not only the end.
        ranges = by_name(PS.plan_ranges(LAYOUT))
        cols = LAYOUT["tabs"]["Draft Board"]["columns"]
        letter, first, last = cols["brk"]["letter"], LAYOUT["first_row"], LAYOUT["last_row"]
        a1 = f"{letter}{first}:{letter}{last}"
        r = ranges[f"Draft Board!{a1}"]
        assert r["anchor"] == cols["player"]["index"]
        assert r["select"] == [cols["brk"]["letter"], cols["player"]["letter"]]
        assert r["fetch_range"] != r["range"]

    def test_the_range_already_holding_the_anchor_column_needs_no_anchor(self):
        ranges = by_name(PS.plan_ranges(LAYOUT))
        cols = LAYOUT["tabs"]["Draft Board"]["columns"]
        a1 = (f"{cols['player']['letter']}{LAYOUT['first_row']}:"
              f"{cols['inj']['letter']}{LAYOUT['last_row']}")
        assert "anchor" not in ranges[f"Draft Board!{a1}"]

    def test_a_board_hand_column_range_carries_the_player_anchor(self):
        ranges = by_name(PS.plan_ranges(LAYOUT))
        cols = LAYOUT["tabs"]["Board"]["columns"]
        a1 = (f"{cols['gp1']['letter']}{LAYOUT['first_row']}:"
              f"{cols['myGp']['letter']}{LAYOUT['last_row']}")
        assert ranges[f"Board!{a1}"]["anchor"] == cols["player"]["index"]

    def test_a_punted_category_range_carries_the_cat_anchor(self):
        # Only eight rows, and Punted can legitimately be blank on every one of them.
        ranges = by_name(PS.plan_ranges(LAYOUT))
        t = LAYOUT["tabs"]["Category Tracker"]
        col = PS.col_letter(t["columns"]["punted"])
        r1 = t["first_cat_row"]
        r2 = r1 + len(LAYOUT["tabs"]["Settings"]["weights"]) - 1
        r = ranges[f"Category Tracker!{col}{r1}:{col}{r2}"]
        assert r["anchor"] == t["columns"]["cat"]

    def test_the_my_roster_spill_and_punts_blocks_keep_no_anchor(self):
        # Both are packed from the top: a short reply there can only be the natural tail,
        # never a gap in the middle, so today's trailing-only handling still applies.
        for r in PS.plan_ranges(LAYOUT):
            if r["sheet"] == "Category Tracker" and r["range"].startswith(
                    f"B{LAYOUT['tabs']['Category Tracker']['roster_first_row']}"):
                assert "anchor" not in r
            if r["sheet"] == "Punts":
                assert "anchor" not in r


class TestAssemble:
    def test_trailing_rows_gviz_left_off_are_padded_back(self):
        ranges = PS.plan_ranges(LAYOUT)
        raw = canned(ranges)
        roster = next(r for r in ranges if r["name"].startswith("Category Tracker!B22"))
        raw[roster["name"]] = filled(roster, rows=2)
        pull = PS.assemble(raw, ranges, "live", "2026-01-01T00:00:00+00:00")
        cells = pull["ranges"][roster["name"]]["cells"]
        assert len(cells) == roster["rows"] and all(len(row) == roster["cols"] for row in cells)
        assert cells[1][0] == {"v": "x", "f": None} and cells[2] == [None] * roster["cols"]

    def test_a_date_cell_becomes_an_iso_string(self):
        ranges = PS.plan_ranges(LAYOUT)
        raw = canned(ranges)
        name = f"Settings!{LAYOUT['tabs']['Settings']['cells']['generated']}"
        raw[name] = {"status": "ok", "cols": ["B"],
                     "rows": [[{"v": "Date(2026,0,31)", "f": "1/31/2026"}]]}
        pull = PS.assemble(raw, ranges, "live", "2026-01-01T00:00:00+00:00")
        assert pull["ranges"][name]["cells"] == [[{"v": "2026-01-31", "f": "1/31/2026"}]]

    def test_too_few_filled_cells_refuses_the_pull(self):
        ranges = PS.plan_ranges(LAYOUT)
        raw = canned(ranges)
        raw["Settings!B4:B6"]["rows"] = raw["Settings!B4:B6"]["rows"][:2]
        with pytest.raises(PS.PullError, match="Settings!B4:B6: 2 filled cells, at least 3"):
            PS.assemble(raw, ranges, "live", "2026-01-01T00:00:00+00:00")

    def test_a_refused_request_names_the_reason(self):
        ranges = PS.plan_ranges(LAYOUT)
        raw = canned(ranges)
        raw[ranges[0]["name"]] = {"status": "error", "errors": [{"reason": "access_denied"}]}
        with pytest.raises(PS.PullError, match="access_denied"):
            PS.assemble(raw, ranges, "live", "2026-01-01T00:00:00+00:00")

    def test_a_dropped_column_is_placed_by_its_id(self):
        r = {"name": "Board!T4:V5", "sheet": "Board", "range": "T4:V5", "type": "number",
             "rows": 2, "cols": 3, "min_cells": 0}
        raw = {r["name"]: {"status": "ok", "cols": ["T", "V"],
                           "rows": [[{"v": 1.0, "f": "1"}, {"v": 3.0, "f": "3"}]]}}
        cells = PS.assemble(raw, [r], "live", "t")["ranges"][r["name"]]["cells"]
        assert cells == [[{"v": 1.0, "f": "1"}, None, {"v": 3.0, "f": "3"}], [None, None, None]]

    def test_a_short_reply_that_ends_on_an_empty_row_is_refused(self):
        # A sparse range (min_cells 0) cannot count its way to safety, so its shape is checked:
        # an unanchored range fills from the top, so the last row it returns is never empty.
        r = {"name": "Board!T4:T7", "sheet": "Board", "range": "T4:T7", "type": "number",
             "rows": 4, "cols": 1, "min_cells": 0}
        raw = {r["name"]: {"status": "ok", "cols": ["T"],
                           "rows": [[{"v": 1.0, "f": "1"}], [None]]}}
        with pytest.raises(PS.PullError, match="truncated"):
            PS.assemble(raw, [r], "live", "t")
        raw[r["name"]]["rows"] = [[None], [{"v": 2.0, "f": "2"}]]
        cells = PS.assemble(raw, [r], "live", "t")["ranges"][r["name"]]["cells"]
        assert cells == [[None], [{"v": 2.0, "f": "2"}], [None], [None]]

    def test_an_interior_omission_is_silently_misplaced_without_an_anchor(self):
        # RED against aac328f: a target row can go blank anywhere in the range, not only at
        # the end, but the only shape check available without an anchor is "does the reply
        # end on a blank row". Here the SECOND row is the one gviz dropped (unknowable from
        # this reply alone) and the actual last row is real data, so the old check cannot see
        # it: it accepts the short reply and shifts every later row up by one, exactly the
        # live AE (Break) and AI:AK (ADP/XRank/GAP) failures this branch fixes for the ranges
        # that now carry an anchor.
        r = {"name": "Draft Board!AE4:AE9", "sheet": "Draft Board", "range": "AE4:AE9",
             "type": "string", "rows": 6, "cols": 1, "min_cells": 0}
        raw = {r["name"]: {"status": "ok", "cols": ["AE"],
                           "rows": [[{"v": "BREAK", "f": None}]] * 5}}
        cells = PS.assemble(raw, [r], "live", "t")["ranges"][r["name"]]["cells"]
        # The bug: five real rows packed at the top and the padding at the bottom, even though
        # the true gap (row index 1, by construction) is nowhere in this grid.
        assert cells == [[{"v": "BREAK", "f": None}]] * 5 + [[None]]


class TestAnchoring:
    """§4's fix for interior omission: an always-filled column rides along so gviz cannot
    drop a row, and its own cell is stripped back out before the pull file is written.

    Every test here fails against aac328f: `_range()` takes no `anchor` argument there, and
    `assemble()` has no anchor-stripping step, so a two-column reply for a one-column target
    either misplaces the anchor's cell into the grid or is rejected as "columns do not fit
    the range" -- neither of which is "keep the row, drop the anchor".
    """

    def test_an_interior_all_empty_target_row_is_kept_when_the_anchor_is_present(self):
        r = PS._range("Board", 20, 4, 20, 7, "number", 0, anchor=2)
        assert r["select"] == ["T", "B"]
        raw = {r["name"]: {"status": "ok", "cols": ["T", "B"],
                           "rows": [[{"v": 1.0, "f": "1"}, {"v": "Alice", "f": None}],
                                    [None, {"v": "Bob", "f": None}],
                                    [{"v": 3.0, "f": "3"}, {"v": "Cara", "f": None}],
                                    [None, {"v": "Dee", "f": None}]]}}
        cells = PS.assemble(raw, [r], "live", "t")["ranges"][r["name"]]["cells"]
        # Row index 1 ("Bob") is genuinely blank in the target column, but the anchor's
        # presence kept gviz from dropping the row, so it lands at its real position -- not
        # shifted up to take row 2's place.
        assert cells == [[{"v": 1.0, "f": "1"}], [None], [{"v": 3.0, "f": "3"}], [None]]

    def test_the_anchor_column_never_reaches_the_pull_file(self):
        r = PS._range("Board", 20, 4, 20, 5, "number", 0, anchor=2)
        raw = {r["name"]: {"status": "ok", "cols": ["T", "B"],
                           "rows": [[{"v": 1.0, "f": "1"}, {"v": "Alice", "f": None}],
                                    [{"v": 2.0, "f": "2"}, {"v": "Bob", "f": None}]]}}
        cells = PS.assemble(raw, [r], "live", "t")["ranges"][r["name"]]["cells"]
        assert cells == [[{"v": 1.0, "f": "1"}], [{"v": 2.0, "f": "2"}]]
        assert all(len(row) == 1 for row in cells)

    def test_a_reply_missing_a_planned_row_even_with_the_anchor_is_refused(self):
        r = PS._range("Board", 20, 4, 20, 7, "number", 0, anchor=2)
        raw = {r["name"]: {"status": "ok", "cols": ["T", "B"],
                           "rows": [[{"v": 1.0, "f": "1"}, {"v": "Alice", "f": None}],
                                    [None, {"v": "Bob", "f": None}],
                                    [{"v": 3.0, "f": "3"}, {"v": "Cara", "f": None}]]}}  # 3 of 4
        with pytest.raises(PS.PullError, match="3 of 4 rows came back with the anchor present"):
            PS.assemble(raw, [r], "live", "t")

    def test_a_reply_missing_the_anchor_column_itself_is_refused(self):
        r = PS._range("Board", 20, 4, 20, 5, "number", 0, anchor=2)
        raw = {r["name"]: {"status": "ok", "cols": ["T"],
                           "rows": [[{"v": 1.0, "f": "1"}], [{"v": 2.0, "f": "2"}]]}}
        with pytest.raises(PS.PullError, match="anchor column is missing"):
            PS.assemble(raw, [r], "live", "t")

    def test_the_select_clause_backtick_quotes_every_column(self):
        # Live evidence: gviz's query language is case-insensitive and a bare `BY` parses as
        # the `by` keyword (as in `group by`), refusing `invalid_query` -- and BY is a real
        # Draft Board column letter (rank:BMP-ALT:zsc, index 77). Quoting every letter, not
        # only the ones that collide today, is what makes this safe against the next one.
        assert PS.col_letter(77) == "BY"
        r = PS._range("Draft Board", 76, 4, 77, 5, "number", 0, anchor=4)
        fn = PS.build_eval(FAKE_ID, [r])
        assert json.dumps("`BX`,`BY`,`D`") in fn


class TestBooleanBlanks:
    def test_a_blank_cell_in_a_boolean_range_assembles_as_false_and_is_not_refused(self):
        r = {"name": "Draft Board!H4:I5", "sheet": "Draft Board", "range": "H4:I5",
             "type": "boolean", "rows": 2, "cols": 2, "min_cells": 4}
        raw = {r["name"]: {"status": "ok", "cols": ["H", "I"],
                           "rows": [[None, {"v": True, "f": "TRUE"}], [None, None]]}}
        cells = PS.assemble(raw, [r], "live", "t")["ranges"][r["name"]]["cells"]
        assert cells == [[{"v": False, "f": None}, {"v": True, "f": "TRUE"}],
                          [{"v": False, "f": None}, {"v": False, "f": None}]]

    def test_a_number_range_with_a_missing_cell_is_still_refused(self):
        r = {"name": "Board!Y4:Y5", "sheet": "Board", "range": "Y4:Y5", "type": "number",
             "rows": 2, "cols": 1, "min_cells": 2}
        raw = {r["name"]: {"status": "ok", "cols": ["Y"],
                           "rows": [[{"v": 1.0, "f": "1"}], [None]]}}
        with pytest.raises(PS.PullError, match="1 filled cells, at least 2"):
            PS.assemble(raw, [r], "live", "t")


class TestEvalAndOutput:
    def test_build_eval_fetches_every_range_with_the_auth_header(self):
        ranges = PS.plan_ranges(LAYOUT)
        fn = PS.build_eval(FAKE_ID, ranges)
        assert fn.startswith("async () =>")
        assert "'X-DataSource-Auth': 'true'" in fn and "credentials: 'include'" in fn
        assert f"/spreadsheets/d/{FAKE_ID}/gviz/tq?tqx=out:json&headers=0" in fn
        for r in ranges:
            assert json.dumps(r["name"], ensure_ascii=False) in fn

    def test_extract_reads_the_json_quoted_result(self):
        assert PS.extract(stdout_for({"a": {"status": "ok"}})) == {"a": {"status": "ok"}}

    def test_extract_refuses_output_with_no_result(self):
        with pytest.raises(PS.PullError, match="Result"):
            PS.extract("### Page\n- title: sign in\n")
        with pytest.raises(PS.PullError, match="error"):
            PS.extract("### Error\nTarget page closed\n")

    def test_sheet_id_comes_from_env(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(f"# local only\nOTHER=1\n{ENV_KEY} = '{FAKE_ID}'\n", encoding="utf-8")
        assert PS.read_sheet_id(env) == FAKE_ID
        env.write_text(f"{ENV_KEY}=\n", encoding="utf-8")
        with pytest.raises(ValueError, match=ENV_KEY):
            PS.read_sheet_id(env)
        with pytest.raises(ValueError, match=ENV_KEY):
            PS.read_sheet_id(tmp_path / "missing.env")


class TestSequentialFetch:
    """Defect #2: firing all ~94 fetches with Promise.all made exactly one come back non-JSON
    on 5+ consecutive live attempts, at a different index each run, and the resulting
    SyntaxError killed the whole eval without saying which range failed. Sequential, the
    same plan succeeded live.
    """

    def test_the_eval_has_no_promise_all_and_awaits_each_fetch_in_turn(self):
        ranges = PS.plan_ranges(LAYOUT)
        fn = PS.build_eval(FAKE_ID, ranges)
        assert "Promise.all" not in fn
        assert "for (const p of plan)" in fn and "await one(p)" in fn

    def test_a_structured_error_from_one_range_exits_1_naming_the_range(self, tmp_path,
                                                                        monkeypatch, capsys):
        ranges = PS.plan_ranges(LAYOUT)
        bad_range = ranges[5]["name"]
        payload = {"error": True, "range": bad_range, "reason": "invalid_json"}

        def run(cmd, cwd, capture_output, text):
            return subprocess.CompletedProcess(cmd, 0, stdout_for(payload), "")

        monkeypatch.setattr(PS.subprocess, "run", run)
        assert PS.main(["--sheet-id", FAKE_ID], root=tmp_path) == 1
        err = capsys.readouterr().err
        assert bad_range in err and "invalid_json" in err
        assert FAKE_ID not in err
        assert not (tmp_path / "pulls").exists()


class TestMain:
    def fake_run(self, monkeypatch, returncode=0):
        calls = []

        def run(cmd, cwd, capture_output, text):
            calls.append((cmd, cwd))
            payload = canned(PS.plan_ranges(LAYOUT))
            return subprocess.CompletedProcess(cmd, returncode, stdout_for(payload), "boom")

        monkeypatch.setattr(PS.subprocess, "run", run)
        return calls

    def test_writes_one_pull_under_root(self, tmp_path, monkeypatch):
        calls = self.fake_run(monkeypatch)
        assert PS.main(["--sheet-id", FAKE_ID, "--label", "copy"], root=tmp_path) == 0
        (cmd, cwd), = calls
        assert cmd[:3] == ["playwright-cli", "-s=fantasy", "eval"] and FAKE_ID in cmd[3]
        assert cwd == PS.REPO
        out, = (tmp_path / "pulls").iterdir()
        assert out.name.endswith(" copy.json")
        pull = json.loads(out.read_text(encoding="utf-8"))
        assert pull["label"] == "copy"
        assert set(pull["ranges"]) == {r["name"] for r in PS.plan_ranges(LAYOUT)}

    def test_the_env_id_is_used_without_the_flag(self, tmp_path, monkeypatch):
        calls = self.fake_run(monkeypatch)
        env = tmp_path / ".env"
        env.write_text(f"{ENV_KEY}={FAKE_ID}\n", encoding="utf-8")
        monkeypatch.setattr(PS, "ENV", env)
        assert PS.main([], root=tmp_path) == 0
        assert FAKE_ID in calls[0][0][3]
        assert next((tmp_path / "pulls").iterdir()).name.endswith(" live.json")

    def test_no_sheet_id_is_a_usage_error(self, tmp_path, monkeypatch):
        self.fake_run(monkeypatch)
        monkeypatch.setattr(PS, "ENV", tmp_path / "absent.env")
        assert PS.main([], root=tmp_path) == 2
        assert not (tmp_path / "pulls").exists()

    def test_a_failed_browser_call_writes_nothing(self, tmp_path, monkeypatch):
        self.fake_run(monkeypatch, returncode=1)
        assert PS.main(["--sheet-id", FAKE_ID], root=tmp_path) == 1
        assert not (tmp_path / "pulls").exists()

    def test_an_unknown_layout_column_is_a_refused_pull_not_a_traceback(self, tmp_path,
                                                                        monkeypatch):
        self.fake_run(monkeypatch)
        layout = json.loads(json.dumps(LAYOUT))
        layout["tabs"]["Draft Board"]["columns"]["brandNew"] = {"index": 99, "letter": "CU",
                                                                "label": "New"}
        bad_layout = tmp_path / "layout.json"
        bad_layout.write_text(json.dumps(layout), encoding="utf-8")
        assert PS.main(["--sheet-id", FAKE_ID, "--layout", str(bad_layout)], root=tmp_path) == 1
        assert not (tmp_path / "pulls").exists()

    def test_a_missing_playwright_cli_is_a_browser_failure_not_a_traceback(self, tmp_path,
                                                                           monkeypatch):
        def run(cmd, cwd, capture_output, text):
            raise FileNotFoundError("playwright-cli")

        monkeypatch.setattr(PS.subprocess, "run", run)
        assert PS.main(["--sheet-id", FAKE_ID], root=tmp_path) == 1
        assert not (tmp_path / "pulls").exists()


def test_the_layout_path_is_the_committed_file():
    assert PS.LAYOUT == Path(PS.__file__).resolve().parent / "board_layout.json"
