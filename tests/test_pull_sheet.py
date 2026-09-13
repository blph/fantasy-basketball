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
    """A gviz table for range `r`, every cell filled with a value of the range's type."""
    value = {"number": 1.0, "string": "x", "boolean": True}[r["type"]]
    count = r["rows"] if rows is None else rows
    return {"status": "ok", "cols": [PS.col_letter(i + 1) for i in range(r["cols"])],
            "rows": [[{"v": value, "f": None}] * r["cols"] for _ in range(count)]}


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
        # gviz trims only trailing empty rows, and the last row it returns is never empty.
        r = {"name": "Board!T4:T7", "sheet": "Board", "range": "T4:T7", "type": "number",
             "rows": 4, "cols": 1, "min_cells": 0}
        raw = {r["name"]: {"status": "ok", "cols": ["T"],
                           "rows": [[{"v": 1.0, "f": "1"}], [None]]}}
        with pytest.raises(PS.PullError, match="truncated"):
            PS.assemble(raw, [r], "live", "t")
        raw[r["name"]]["rows"] = [[None], [{"v": 2.0, "f": "2"}]]
        cells = PS.assemble(raw, [r], "live", "t")["ranges"][r["name"]]["cells"]
        assert cells == [[None], [{"v": 2.0, "f": "2"}], [None], [None]]


class TestEvalAndOutput:
    def test_build_eval_fetches_every_range_at_once_with_the_auth_header(self):
        ranges = PS.plan_ranges(LAYOUT)
        fn = PS.build_eval(FAKE_ID, ranges)
        assert fn.startswith("async () =>") and "Promise.all" in fn
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


def test_the_layout_path_is_the_committed_file():
    assert PS.LAYOUT == Path(PS.__file__).resolve().parent / "board_layout.json"
