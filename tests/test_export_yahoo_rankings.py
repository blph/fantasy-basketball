"""Tests for the Yahoo rankings exporter.

Every fixture here is synthetic: invented players, invented numbers, shaped like
the Draft Board range but never copied from it. The repo is public and provider
data is not ours to republish (ADR-0006).
"""

import csv
import datetime
import importlib.util
import re
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "scripts" / "draft-board" / "export_yahoo_rankings.py"
_spec = importlib.util.spec_from_file_location("export_yahoo_rankings", _SRC)
assert _spec and _spec.loader
export = importlib.util.module_from_spec(_spec)
sys.modules["export_yahoo_rankings"] = export
_spec.loader.exec_module(export)


def board_rows(n, team="BOS", pos="PG"):
    """n synthetic Draft Board rows: [#, TIER, Player, Team, Pos]."""
    return [[str(i), "1", f"Player {i:03d}", team, pos] for i in range(1, n + 1)]


def test_header_and_shape(tmp_path):
    src = tmp_path / "raw.csv"
    with src.open("w", newline="") as fh:
        csv.writer(fh).writerows(board_rows(5))
    out = tmp_path / "yahoo.csv"

    export.main([str(src), "-o", str(out), "--limit", "5"])

    lines = out.read_text().splitlines()
    assert lines[0] == "rank,name,team,position"
    assert lines[1] == "1,Player 001,BOS,PG"
    assert len(lines) == 6


@pytest.mark.parametrize(
    ("provider", "yahoo"),
    [("GS", "GSW"), ("NO", "NOP"), ("NY", "NYK"), ("SA", "SAS"), ("BOS", "BOS")],
)
def test_team_remap(provider, yahoo):
    assert export.normalize_team(provider) == yahoo


def test_unknown_team_is_an_error():
    with pytest.raises(export.ExportError, match="unrecognised team code"):
        export.normalize_team("ZZZ")


def test_unknown_team_reports_the_sheet_row():
    rows = board_rows(3)
    rows[1][3] = "XYZ"
    with pytest.raises(export.ExportError, match="sheet row 4"):
        export.convert(rows, limit=3)


@pytest.mark.parametrize(
    ("eligible", "primary"),
    [("SG,SF,PF", "SG"), ("PF,C", "PF"), ("C", "C"), ("PG, SG", "PG")],
)
def test_primary_position(eligible, primary):
    assert export.primary_position(eligible) == primary


def test_multi_position_stays_one_field(tmp_path):
    src = tmp_path / "raw.csv"
    with src.open("w", newline="") as fh:
        csv.writer(fh).writerows(board_rows(2, pos="SG,SF,PF"))
    out = tmp_path / "yahoo.csv"

    export.main([str(src), "-o", str(out), "--limit", "2"])

    for line in out.read_text().splitlines():
        assert line.count(",") == 3, line


def test_rank_is_renumbered_across_a_gap():
    """A blank or #N/A in column A must not punch a hole in the exported ranks."""
    rows = board_rows(4)
    rows[1][0] = ""
    rows[2][0] = "#N/A"

    assert [r[0] for r in export.convert(rows, limit=4)] == [1, 2, 3, 4]


def test_blank_rows_are_skipped():
    rows = board_rows(3) + [["", "", "", "", ""]] * 5

    assert len(export.convert(rows, limit=3)) == 3


def test_limit_truncates():
    got = export.convert(board_rows(200), limit=156)

    assert len(got) == 156
    assert got[-1][1] == "Player 156"


def test_short_input_fails_loudly():
    with pytest.raises(export.ExportError, match="only 10 players"):
        export.convert(board_rows(10), limit=156)


def test_wrong_column_count_fails():
    rows = board_rows(2)
    rows[1] = rows[1][:4]
    with pytest.raises(export.ExportError, match="expected 5 columns, got 4"):
        export.convert(rows, limit=2)


def test_missing_name_fails():
    rows = board_rows(2)
    rows[1][2] = ""
    with pytest.raises(export.ExportError, match="no player name"):
        export.convert(rows, limit=2)


# --- default output path ----------------------------------------------------


def test_default_path_is_dated_and_under_data_exports():
    path = export.default_output_path(datetime.date(2026, 8, 27))

    assert path.parent == _SRC.parents[2] / "data" / "exports"
    assert path.name == "yahoo-rankings-2026-27-0827.csv"


def test_default_path_shape_is_season_plus_mmdd():
    """Guards the convention itself, not one hard-coded date."""
    name = export.default_output_path().name

    assert re.fullmatch(r"yahoo-rankings-\d{4}-\d{2}-\d{4}\.csv", name), name


def test_default_path_ignores_the_cwd(tmp_path, monkeypatch):
    """It must resolve off the repo root, or running from /tmp writes to /tmp."""
    monkeypatch.chdir(tmp_path)

    path = export.default_output_path(datetime.date(2026, 8, 27))

    assert tmp_path not in path.parents
    assert path.is_absolute()


def test_main_without_out_uses_the_default_path(tmp_path, monkeypatch):
    src = tmp_path / "raw.csv"
    with src.open("w", newline="") as fh:
        csv.writer(fh).writerows(board_rows(3))
    target = tmp_path / "exports" / "yahoo-rankings-2026-27-0827.csv"
    monkeypatch.setattr(export, "default_output_path", lambda: target)

    written = export.main([str(src), "--limit", "3"])

    assert written == target
    assert target.read_text().splitlines()[0] == "rank,name,team,position"


def test_main_creates_a_missing_output_directory(tmp_path):
    src = tmp_path / "raw.csv"
    with src.open("w", newline="") as fh:
        csv.writer(fh).writerows(board_rows(2))
    out = tmp_path / "does" / "not" / "exist" / "yahoo.csv"

    export.main([str(src), "-o", str(out), "--limit", "2"])

    assert out.exists()
