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

import board_engine
import board_snapshot
import board_state
import pytest

import board_fixtures

_SRC = Path(__file__).resolve().parents[1] / "scripts" / "draft-board" / "export_yahoo_rankings.py"
_spec = importlib.util.spec_from_file_location("export_yahoo_rankings", _SRC)
assert _spec and _spec.loader
export = importlib.util.module_from_spec(_spec)
sys.modules["export_yahoo_rankings"] = export
_spec.loader.exec_module(export)


def board_rows(n, team="BOS", pos="PG"):
    """n synthetic Draft Board rows: [#, TIER, RND, Player, Tm, Pos, INJ].

    Seven columns, matching the range the exporter fetches. RND and INJ carry no
    information the export needs; they are here because they sit between the columns
    that do, and getting their positions wrong is precisely the failure this shape
    check exists to catch.
    """
    return [[str(i), "1", f"R{(i - 1) // 12 + 1}", f"Player {i:03d}", team, pos, ""]
            for i in range(1, n + 1)]


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
    rows[1][export.COL_TEAM] = "XYZ"
    # Data starts at row 4 now that row 1 is the control strip, so the second row of the
    # fetched range is sheet row 5.
    with pytest.raises(export.ExportError, match="sheet row 5"):
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
    # A short row is how an outdated pull range arrives: it must fail rather than read
    # the wrong columns, because every column past Player would be off by one.
    rows = board_rows(2)
    rows[1] = rows[1][:export.RANGE_WIDTH - 1]
    with pytest.raises(export.ExportError,
                       match=f"expected {export.RANGE_WIDTH} columns, "
                             f"got {export.RANGE_WIDTH - 1}"):
        export.convert(rows, limit=2)


def test_missing_name_fails():
    rows = board_rows(2)
    rows[1][export.COL_PLAYER] = ""
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


# --- --local ----------------------------------------------------------------
# One synthetic snapshot from tests/board_fixtures.py, written under tmp_path. Every team is
# set to a provider code Yahoo spells differently, so the remap runs on the local path too.


def local_board(root):
    snap = board_fixtures.make_snapshot()
    for p in snap["players"]:
        p["team"] = "GS"
    snap["meta"]["digest"] = board_snapshot.digest(snap)
    path = board_snapshot.path_for(root, snap["meta"]["generated"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(board_snapshot.dumps(snap), encoding="utf-8")
    return snap, path


def write_state(root, snap, sort, ticked_key=None):
    state = board_state.new_state(snap)
    state["applied_sort"] = sort
    if ticked_key:
        state["players"][ticked_key] = {
            **board_engine.player_state(state, ticked_key),
            "gone": True,
            "mine": True,
        }
    board_state.save(root / "draft-state.json", state)


@pytest.fixture
def local(tmp_path, monkeypatch):
    root = tmp_path / "draft-board"
    snap, path = local_board(root)
    monkeypatch.setattr(export, "LOCAL_ROOT", root)
    return root, snap, path


def test_local_and_csv_paths_write_identical_bytes(tmp_path, local):
    root, snap, _ = local
    n = str(len(snap["players"]))
    raw = tmp_path / "raw.csv"
    with raw.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(export.rows_from_local(snap, board_engine.DEFAULT_SORT))
    via_csv, via_local = tmp_path / "csv.csv", tmp_path / "local.csv"

    export.main([str(raw), "-o", str(via_csv), "--limit", n])
    export.main(["--local", "-o", str(via_local), "--limit", n])

    assert via_local.read_bytes() == via_csv.read_bytes()
    assert via_local.read_text().splitlines()[1].split(",")[2] == "GSW"


def test_local_rows_follow_the_applied_value_not_the_board_row(local):
    """Checked against the snapshot directly, not through the engine's own order()."""
    _, snap, _ = local
    sort = {"source": "HBP", "kind": "zsh"}

    rows = export.rows_from_local(snap, sort)

    expected = sorted(snap["players"], key=lambda p: (-p["values"]["HBP"]["zsh"]["v"], p["row"]))
    assert [r[export.COL_PLAYER] for r in rows] == [p["name"] for p in expected]
    assert [r[0] for r in rows] == [str(i) for i in range(1, len(rows) + 1)]
    assert {len(r) for r in rows} == {export.RANGE_WIDTH}


def test_sort_flag_beats_the_state_file(tmp_path, local, capsys):
    root, snap, _ = local
    write_state(root, snap, {"source": "HBP", "kind": "zsc"})
    out = tmp_path / "y.csv"

    export.main(["--local", "--sort", "bmp-alt:DURH", "-o", str(out), "--limit", "5"])

    assert "sorted by BMP-ALT:durh" in capsys.readouterr().err
    want = export.rows_from_local(snap, {"source": "BMP-ALT", "kind": "durh"})
    assert out.read_text().splitlines()[1].split(",")[1] == want[0][export.COL_PLAYER]


def test_state_file_sort_beats_the_default(tmp_path, local, capsys):
    root, snap, _ = local
    write_state(root, snap, {"source": "HBP", "kind": "zsc"})

    export.main(["--local", "-o", str(tmp_path / "y.csv"), "--limit", "5"])

    assert "sorted by HBP:zsc" in capsys.readouterr().err


def test_default_sort_without_a_state_file(tmp_path, local, capsys):
    _, snap, _ = local

    export.main(["--local", "-o", str(tmp_path / "y.csv"), "--limit", "5"])

    err = capsys.readouterr().err
    assert "sorted by BMP:durh" in err
    assert f"local board {snap['meta']['generated']} digest {snap['meta']['digest'][:12]}" in err


def test_ticks_do_not_change_the_export(tmp_path, local):
    root, snap, _ = local
    sort = {"source": "BMP", "kind": "durh"}
    top = export.rows_from_local(snap, sort)[0][export.COL_PLAYER]
    key = next(p["key"] for p in snap["players"] if p["name"] == top)
    untouched, ticked = tmp_path / "a.csv", tmp_path / "b.csv"

    export.main(["--local", "-o", str(untouched), "--limit", "5"])
    write_state(root, snap, sort, ticked_key=key)
    export.main(["--local", "-o", str(ticked), "--limit", "5"])

    assert ticked.read_bytes() == untouched.read_bytes()


def test_snapshot_flag_pins_an_older_board(tmp_path, local, capsys):
    root, _, path = local
    newer = board_fixtures.make_snapshot(date="2026-01-02")
    for p in newer["players"]:
        p["team"] = "GS"
    newer["meta"]["digest"] = board_snapshot.digest(newer)
    board_snapshot.path_for(root, "2026-01-02").write_text(board_snapshot.dumps(newer), "utf-8")

    export.main(["--local", "--snapshot", str(path), "-o", str(tmp_path / "y.csv"), "--limit", "5"])

    assert "local board 2026-01-01" in capsys.readouterr().err


def test_local_with_a_csv_is_a_usage_error(tmp_path, local, capsys):
    with pytest.raises(SystemExit) as exc:
        export.main(["--local", str(tmp_path / "raw.csv")])

    assert exc.value.code == 2
    assert "--local" in capsys.readouterr().err


def test_sort_without_local_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as exc:
        export.main([str(tmp_path / "raw.csv"), "--sort", "BMP:durh"])

    assert exc.value.code == 2


def test_no_snapshot_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "LOCAL_ROOT", tmp_path / "empty")

    with pytest.raises(export.ExportError, match="no local board .* run build_data.py"):
        export.main(["--local", "-o", str(tmp_path / "y.csv")])


def test_an_unknown_sort_names_the_choices(tmp_path, local):
    with pytest.raises(export.ExportError, match="expected SOURCE:KIND"):
        export.main(["--local", "--sort", "ESPN:durh", "-o", str(tmp_path / "y.csv")])


def test_a_tampered_snapshot_is_refused(tmp_path, local):
    _, _, path = local
    path.write_text(path.read_text("utf-8").replace('"GS"', '"BOS"', 1), "utf-8")

    with pytest.raises(export.ExportError, match=re.escape(path.name)):
        export.main(["--local", "-o", str(tmp_path / "y.csv"), "--limit", "5"])
