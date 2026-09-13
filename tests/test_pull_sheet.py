"""pull_sheet.py, with no browser: a synthetic xlsx built in memory, canned playwright-cli output.

Every cell here is invented. The sheet id is a made-up token, short enough that it cannot be
mistaken for a real one.
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pull_sheet as PS
import pytest

LAYOUT = json.loads(PS.LAYOUT.read_text(encoding="utf-8"))
FAKE_ID = "fake-sheet-id"
ENV_KEY = "DRAFT_SHEET_ID"
GENERATED = f"Settings!{LAYOUT['tabs']['Settings']['cells']['generated']}"


def by_name(ranges: list[dict]) -> dict[str, dict]:
    return {r["name"]: r for r in ranges}


def xlsx(cells: dict[tuple[str, str], tuple[str | None, str]],
         shared: tuple[str, ...] = ()) -> bytes:
    """A minimal workbook. `cells` maps (sheet, A1) to (xlsx cell type, stored text)."""
    sheets = sorted({s for s, _ in cells})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(f'<sheet name="{escape(s)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
                      for i, s in enumerate(sheets))
            + "</sheets></workbook>"))
        z.writestr("xl/_rels/workbook.xml.rels", (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i + 1}" Target="worksheets/sheet{i + 1}.xml"/>'
                      for i in range(len(sheets)))
            + "</Relationships>"))
        if shared:
            z.writestr("xl/sharedStrings.xml", (
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                + "".join(f"<si><t>{escape(t)}</t></si>" for t in shared) + "</sst>"))
        for i, s in enumerate(sheets):
            body = []
            for (sheet, a1), (t, text) in cells.items():
                if sheet != s:
                    continue
                if t == "inlineStr":
                    body.append(f'<c r="{a1}" t="inlineStr"><is><t>{escape(text)}</t></is></c>')
                else:
                    attr = f' t="{t}"' if t else ""
                    body.append(f'<c r="{a1}"{attr}><v>{escape(text)}</v></c>')
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", (
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData><row>" + "".join(body) + "</row></sheetData></worksheet>"))
    return buf.getvalue()


def full_workbook() -> bytes:
    """Every planned cell filled with a value of its range's type; every tab present."""
    kind = {"number": (None, "1"), "string": ("inlineStr", "x"), "boolean": ("b", "1")}
    cells = {}
    for r in PS.plan_ranges(LAYOUT):
        c1, r1, c2, r2 = PS.parse_a1(r["range"])
        for col in range(c1, c2 + 1):
            for row in range(r1, r2 + 1):
                cells[(r["sheet"], f"{PS.col_letter(col)}{row}")] = kind[r["type"]]
    cells[("Settings", GENERATED.split("!")[1])] = (None, "46053")  # a date serial
    for tab in LAYOUT["tabs"]:
        cells.setdefault((tab, "ZZ1"), (None, "0"))
    return xlsx(cells)


def stdout_for(payload: dict) -> str:
    """What playwright-cli prints: the snippet's return value as a JSON-quoted string."""
    return ("### Result\n" + json.dumps(json.dumps(payload)) + "\n"
            "### Ran Playwright code\n```js\nawait page.request.get('x');\n```\n")


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


class TestReadXlsx:
    def test_every_cell_type_is_read_as_the_pull_file_stores_it(self):
        data = xlsx({("T", "A1"): ("s", "1"), ("T", "B1"): ("inlineStr", "in"),
                     ("T", "C1"): ("str", "formula text"), ("T", "D1"): ("b", "1"),
                     ("T", "E1"): ("b", "0"), ("T", "F1"): ("e", "#REF!"),
                     ("T", "G1"): (None, "3"), ("T", "H1"): (None, "0.25"),
                     ("T", "AA2"): (None, "1E-3"), ("T", "I1"): ("str", "")},
                    shared=("zero", "one"))
        sheets, grid = PS.read_xlsx(data)
        assert sheets == {"T"}
        assert grid[("T", 1, 1)] == {"v": "one", "f": None}
        assert grid[("T", 2, 1)] == {"v": "in", "f": None}
        assert grid[("T", 3, 1)] == {"v": "formula text", "f": None}
        assert grid[("T", 4, 1)] == {"v": True, "f": None}
        assert grid[("T", 5, 1)] == {"v": False, "f": None}
        assert grid[("T", 6, 1)] == {"v": None, "f": "#REF!"}
        assert grid[("T", 7, 1)] == {"v": 3, "f": None}
        assert grid[("T", 8, 1)] == {"v": 0.25, "f": None}
        assert grid[("T", 27, 2)] == {"v": 0.001, "f": None}
        assert grid[("T", 9, 1)] is None

    def test_a_download_that_is_not_a_zip_is_refused_with_the_sign_in_hint(self):
        with pytest.raises(PS.PullError, match="signed in"):
            PS.read_xlsx(b"<html>Sign in</html>")

    def test_a_broken_zip_is_refused(self):
        with pytest.raises(PS.PullError, match="could not be read"):
            PS.read_xlsx(b"PK\x03\x04 not really a zip")


class TestAssemble:
    def test_blank_cells_stay_blank_and_blank_checkboxes_read_false(self):
        r_num = {"name": "T!A1:A2", "sheet": "T", "range": "A1:A2", "type": "number",
                 "rows": 2, "cols": 1, "min_cells": 1}
        r_box = {"name": "T!B1:B2", "sheet": "T", "range": "B1:B2", "type": "boolean",
                 "rows": 2, "cols": 1, "min_cells": 2}
        sheets, grid = PS.read_xlsx(xlsx({("T", "A1"): (None, "5"), ("T", "B1"): ("b", "1")}))
        pull = PS.assemble(sheets, grid, [r_num, r_box], "live", "t")
        assert pull["ranges"]["T!A1:A2"]["cells"] == [[{"v": 5, "f": None}], [None]]
        assert pull["ranges"]["T!B1:B2"]["cells"] == [[{"v": True, "f": None}],
                                                      [{"v": False, "f": None}]]

    def test_a_date_serial_becomes_an_iso_string(self):
        r = {"name": "T!B2", "sheet": "T", "range": "B2", "type": "string", "rows": 1,
             "cols": 1, "min_cells": 1}
        sheets, grid = PS.read_xlsx(xlsx({("T", "B2"): (None, "46053")}))
        pull = PS.assemble(sheets, grid, [r], "live", "t", dates=frozenset({"T!B2"}))
        assert pull["ranges"]["T!B2"]["cells"] == [[{"v": "2026-01-31", "f": None}]]

    def test_too_few_filled_cells_refuses_the_pull(self):
        r = {"name": "T!A1:A3", "sheet": "T", "range": "A1:A3", "type": "number",
             "rows": 3, "cols": 1, "min_cells": 3}
        sheets, grid = PS.read_xlsx(xlsx({("T", "A1"): (None, "1"), ("T", "A2"): (None, "2")}))
        with pytest.raises(PS.PullError, match="T!A1:A3: 2 filled cells, at least 3"):
            PS.assemble(sheets, grid, [r], "live", "t")

    def test_a_missing_tab_refuses_the_pull(self):
        r = {"name": "Gone!A1", "sheet": "Gone", "range": "A1", "type": "number",
             "rows": 1, "cols": 1, "min_cells": 0}
        sheets, grid = PS.read_xlsx(xlsx({("T", "A1"): (None, "1")}))
        with pytest.raises(PS.PullError, match="no 'Gone' tab"):
            PS.assemble(sheets, grid, [r], "live", "t")


class TestCodeAndOutput:
    def test_build_code_downloads_the_xlsx_export_through_the_page_request_context(self):
        code = PS.build_code(FAKE_ID)
        assert code.startswith("async page =>")
        assert "page.request.get(" in code
        assert f"/spreadsheets/d/{FAKE_ID}/export?format=xlsx" in code

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
    def fake_run(self, monkeypatch, returncode=0, status=200, data=None):
        calls = []
        body = full_workbook() if data is None else data

        def run(cmd, cwd, capture_output, text):
            calls.append((cmd, cwd))
            payload = {"status": status, "type": "x", "b64": base64.b64encode(body).decode()}
            return subprocess.CompletedProcess(cmd, returncode, stdout_for(payload), "boom")

        monkeypatch.setattr(PS.subprocess, "run", run)
        return calls

    def test_writes_one_pull_under_root(self, tmp_path, monkeypatch, capsys):
        calls = self.fake_run(monkeypatch)
        assert PS.main(["--sheet-id", FAKE_ID, "--label", "copy"], root=tmp_path) == 0
        (cmd, cwd), = calls
        assert cmd[:3] == ["playwright-cli", "-s=fantasy", "run-code"] and FAKE_ID in cmd[3]
        assert cwd == PS.REPO
        out, = (tmp_path / "pulls").iterdir()
        assert out.name.endswith(" copy.json")
        pull = json.loads(out.read_text(encoding="utf-8"))
        assert pull["label"] == "copy" and pull["sig_digits"] == 10
        assert set(pull["ranges"]) == {r["name"] for r in PS.plan_ranges(LAYOUT)}
        assert pull["ranges"][GENERATED]["cells"] == [[{"v": "2026-01-31", "f": None}]]
        assert FAKE_ID not in capsys.readouterr().out

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

    @pytest.mark.parametrize("kwargs", [{"returncode": 1}, {"status": 403},
                                        {"data": b"<html>Sign in</html>"}])
    def test_a_failed_download_writes_nothing_and_never_prints_the_id(self, tmp_path,
                                                                     monkeypatch, capsys,
                                                                     kwargs):
        self.fake_run(monkeypatch, **kwargs)
        assert PS.main(["--sheet-id", FAKE_ID], root=tmp_path) == 1
        assert not (tmp_path / "pulls").exists()
        assert FAKE_ID not in capsys.readouterr().err

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
