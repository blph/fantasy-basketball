"""The local board CLI, end to end over a synthetic snapshot in tmp_path.

Every name and number is invented (tests/board_fixtures.py). `board.main` takes the root
as an argument, so nothing here reads or writes data/draft-board/.
"""

from __future__ import annotations

import json

import board
import board_names as N
import board_snapshot as BS
import board_state as ST
import pytest

from board_fixtures import make_snapshot, write_snapshot
from test_sources import made_up_name

STRANGER = "Zymurgist Oxbowquill"          # nowhere near any fixture name


def name(i: int) -> str:
    return made_up_name(i)


@pytest.fixture
def root(tmp_path):
    write_snapshot(tmp_path, make_snapshot())
    return tmp_path


@pytest.fixture
def drafting(root):
    """An empty state pinned to the fixture snapshot, written without going through `new`."""
    ST.save(root / "draft-state.json", ST.new_state(BS.load(BS.newest(root))))
    return root


def run(root, capsys, *argv):
    """(exit code, stdout, stderr). argparse's own usage errors arrive as SystemExit."""
    capsys.readouterr()
    try:
        code = board.main(list(argv), root=root)
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def state(root) -> dict:
    return json.loads((root / "draft-state.json").read_text())


def tick(root, player: str, **fields) -> None:
    """Set hand fields on a board player directly in the state file."""
    path = root / "draft-state.json"
    current = ST.load(path)
    key = N.key_of(player)
    current["players"][key] = ST.defaults(key) | {"name": player} | fields
    ST.save(path, current)


def tick_offboard(root, entry: dict) -> None:
    path = root / "draft-state.json"
    current = ST.load(path)
    current["offboard"].append(entry)
    ST.save(path, current)


def tsv(out: str) -> tuple[str, list[str], list[list[str]]]:
    """(context line, header, rows) of the first section."""
    lines = out.split("\n\n")[0].splitlines()
    return lines[0], lines[1].split("\t"), [line.split("\t") for line in lines[2:]]


# --- reads ------------------------------------------------------------------------------


def test_read_without_state_uses_the_newest_snapshot_unticked(root, capsys):
    code, out, err = run(root, capsys, "board", "--top", "3")
    ctx, header, rows = tsv(out)
    assert code == 0
    assert ctx.startswith("# sort=BMP:durh what_if=no snapshot=2026-01-01 digest=")
    assert "state=none mine=0 gone=0 offboard=0" in ctx
    assert header == list(board.DEFAULT_FIELDS)
    assert [r[3] for r in rows] == [name(0), name(1), name(2)]
    assert "no draft state" in err


def test_board_json_structure(drafting, capsys):
    code, out, _ = run(drafting, capsys, "board", "--top", "2", "--json")
    payload = json.loads(out)
    assert code == 0
    assert set(payload) == {"context", "board"}
    assert payload["context"]["state"] == "pinned"
    assert list(payload["board"][0]) == list(board.DEFAULT_FIELDS)
    assert len(payload["board"]) == 2


def test_global_flags_work_before_and_after_the_command(drafting, capsys):
    before = run(drafting, capsys, "--json", "board", "--top", "1")[1]
    after = run(drafting, capsys, "board", "--top", "1", "--json")[1]
    assert json.loads(before) == json.loads(after)


def test_what_if_sort_changes_nothing(drafting, capsys):
    saved = (drafting / "draft-state.json").read_text()
    code, out, _ = run(drafting, capsys, "board", "--sort", "HBP:zsc", "--top", "1")
    assert code == 0
    assert "sort=HBP:zsc what_if=yes" in out.splitlines()[0]
    assert (drafting / "draft-state.json").read_text() == saved


def test_board_filters(drafting, capsys):
    tick(drafting, name(0), gone=True)
    tick(drafting, name(1), gone=True)
    tick(drafting, name(2), gone=True, mine=True)
    _, out, _ = run(drafting, capsys, "board", "--available", "--top", "2")
    assert [r[3] for r in tsv(out)[2]] == [name(3), name(4)]
    _, out, _ = run(drafting, capsys, "board", "--mine")
    assert [r[3] for r in tsv(out)[2]] == [name(2)]
    _, out, _ = run(drafting, capsys, "board", "--pos", "c", "--fields", "name,pos")
    assert all("C" in r[1] for r in tsv(out)[2])


def test_unknown_field_is_usage(drafting, capsys):
    code, out, err = run(drafting, capsys, "board", "--fields", "name,nonsense")
    assert (code, out) == (2, "")
    assert "unknown field 'nonsense'" in err


def test_player_compact_and_full(drafting, capsys):
    code, out, _ = run(drafting, capsys, "player", name(5), name(1))
    _, header, rows = tsv(out)
    assert code == 0
    assert header == list(board.COMPACT_FIELDS)
    assert [r[3] for r in rows] == [name(5), name(1)]
    _, out, _ = run(drafting, capsys, "player", name(5), "--full")
    header = tsv(out)[1]
    assert {"BMP-ALT:zsc", "tag:HBP:durh", "disagree:BMP:zsh", "dh:FG%", "d:BLK",
            "pTriple", "rank:pFt"} <= set(header)


def test_player_partial_match_on_read(drafting, capsys):
    code, out, _ = run(drafting, capsys, "player", name(7).split()[1])
    assert code == 0
    assert tsv(out)[2][0][3] == name(7)


def test_player_all_or_nothing(drafting, capsys):
    code, out, err = run(drafting, capsys, "player", name(1), "Qqqq Nobody")
    assert (code, out) == (3, "")
    assert "1 of 2 name(s) unresolved; nothing was printed" in err


def test_tracker_shape(drafting, capsys):
    tick_offboard(drafting, {"name": STRANGER, "pick": None, "mine": True})
    code, out, err = run(drafting, capsys, "tracker")
    sections = out.split("\n\n")
    ctx, header, rows = tsv(out)
    assert code == 0
    assert "players_ticked=0 benchmark=by_rank" in ctx
    assert "offboard_uncounted=1" in ctx
    assert "off-board and not counted" in err
    assert header == ["cat", "my_team", "avg_team", "z", "win", "read", "conceded", "flag"]
    assert [r[0] for r in rows] == list(board.CAT_LABELS)
    assert sections[1].splitlines()[:2] == ["# roster", "rank\tname\tpos"]


def test_punts_by_key_or_label(drafting, capsys):
    _, by_key, _ = run(drafting, capsys, "punts", "pFt", "--top", "3")
    _, by_label, _ = run(drafting, capsys, "punts", "punt ft%", "--top", "3")
    assert by_key == by_label
    assert tsv(by_key)[1] == ["build", "rank", "name", "score", "adp", "gap"]
    assert len(tsv(by_key)[2]) == 3
    code, _, err = run(drafting, capsys, "punts", "pNope")
    assert code == 2 and "unknown build" in err


def test_status_and_check(drafting, capsys):
    code, out, _ = run(drafting, capsys, "status", "--json")
    status = json.loads(out)["status"]
    assert code == 0
    assert status["snapshot_date"] == "2026-01-01"
    assert status["applied_sort"] == "BMP:durh"
    assert status["teams"] == 3
    code, out, _ = run(drafting, capsys, "check", "--json")
    assert code == 0
    assert json.loads(out)["check"]["digest_recomputes"] == "yes"


def test_notes_escape_tabs_and_newlines(drafting, capsys):
    tick(drafting, name(1), notes="line one\tcol\nline two")
    _, out, _ = run(drafting, capsys, "board", "--fields", "name,notes", "--top", "2")
    assert tsv(out)[2][1] == [name(1), "line one\\tcol\\nline two"]


def test_newer_snapshot_is_noted(drafting, capsys):
    write_snapshot(drafting, make_snapshot(date="2026-01-05"))
    code, out, err = run(drafting, capsys, "board", "--top", "1")
    assert code == 0 and "snapshot 2026-01-05 is newer" in err
    _, out, _ = run(drafting, capsys, "status", "--json")
    assert json.loads(out)["status"]["newer_snapshot"] == "2026-01-05"


def test_argparse_usage_stays_2(drafting, capsys):
    assert run(drafting, capsys, "board", "--top", "zero")[0] == 2
    assert run(drafting, capsys, "nosuchcommand")[0] == 2


# --- integrity on reads -------------------------------------------------------------------


def test_state_outside_root_is_usage(drafting, capsys, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "draft-state.json"
    assert run(drafting, capsys, "status", "--state", str(outside))[0] == 2
    assert run(drafting, capsys, "status", "--state", "../escape.json")[0] == 2
    assert not outside.exists()


def test_digest_mismatch_is_integrity_on_reads(drafting, capsys):
    snap = make_snapshot()
    snap["players"][0]["values"]["BMP"]["durh"]["v"] += 1.0
    write_snapshot(drafting, snap)                     # same date, new digest
    for argv in (["status"], ["board"], ["player", name(1)], ["tracker"], ["punts"],
                 ["check"]):
        code, out, err = run(drafting, capsys, *argv)
        assert (code, out) == (4, ""), argv
        assert "rebuilt after the draft state was pinned" in err


def test_missing_snapshot_is_integrity(drafting, capsys):
    BS.path_for(drafting, "2026-01-01").unlink()
    code, _, err = run(drafting, capsys, "tracker")
    assert code == 4 and "missing" in err


def test_corrupt_state_is_integrity(drafting, capsys):
    (drafting / "draft-state.json").write_text("{half a file")
    assert run(drafting, capsys, "status")[0] == 4


def test_state_key_not_on_the_board_is_integrity(drafting, capsys):
    tick(drafting, "Zymurgist Oxbowquill", gone=True)
    code, _, err = run(drafting, capsys, "board")
    assert code == 4 and "not on the pinned board" in err


# --- writes -----------------------------------------------------------------------------


def test_mine_sets_mine_and_gone_and_echoes(drafting, capsys):
    code, out, _ = run(drafting, capsys, "mine", name(4), "--pick", "5")
    _, header, rows = tsv(out)
    assert code == 0
    assert header == list(board.ECHO)
    assert rows == [["mine", name(4), "NO", "5", "Y", "Y", "5", ""]]
    entry = state(drafting)["players"][N.key_of(name(4))]
    assert (entry["gone"], entry["mine"], entry["pick"], entry["name"]) == (True, True, 5, name(4))


def test_mine_undo_clears_mine_only(drafting, capsys):
    run(drafting, capsys, "mine", name(4), "--pick", "5")
    run(drafting, capsys, "mine", name(4), "--undo")
    entry = state(drafting)["players"][N.key_of(name(4))]
    assert (entry["gone"], entry["mine"], entry["pick"]) == (True, False, 5)


def test_gone_undo_on_mine_needs_force(drafting, capsys):
    run(drafting, capsys, "mine", name(4))
    saved = state(drafting)
    code, _, err = run(drafting, capsys, "gone", name(4), "--undo")
    assert code == 2 and "--force" in err
    assert state(drafting) == saved
    assert run(drafting, capsys, "gone", name(4), "--undo", "--force")[0] == 0
    entry = state(drafting)["players"][N.key_of(name(4))]
    assert (entry["gone"], entry["mine"]) == (False, True)


def test_gone_undo_clears_the_pick(drafting, capsys):
    run(drafting, capsys, "gone", name(3), "--pick", "2")
    run(drafting, capsys, "gone", name(3), "--undo")
    assert state(drafting)["players"] == {}


def test_write_all_or_nothing_on_one_bad_name(drafting, capsys):
    saved = state(drafting)
    code, out, err = run(drafting, capsys, "gone", name(1), name(2)[:-1], name(3))
    assert (code, out) == (3, "")
    assert "nothing was written" in err
    assert state(drafting) == saved


def test_fuzzy_name_on_write_suggests(drafting, capsys):
    code, _, err = run(drafting, capsys, "mine", name(6)[:-1])
    assert code == 3
    assert f"did you mean: {name(6)} (BOS)" in err
    assert "--offboard" in err


def test_partial_name_on_write_is_refused(drafting, capsys):
    code, _, _ = run(drafting, capsys, "gone", name(6).split()[1])
    assert code == 3
    assert state(drafting)["offboard"] == []


def test_yahoo_alias_on_write(drafting, capsys, monkeypatch):
    import sources as S

    monkeypatch.setitem(N.YAHOO_ALIASES, S.normalise("Yahoo Spelling"), N.key_of(name(9)))
    assert run(drafting, capsys, "gone", "Yahoo Spelling")[0] == 0
    assert state(drafting)["players"][N.key_of(name(9))]["gone"] is True


def test_team_breaks_a_tie(drafting, capsys, monkeypatch):
    import sources as S

    monkeypatch.setitem(N.YAHOO_ALIASES, S.normalise(name(2)), S.normalise(name(1)))
    code, _, err = run(drafting, capsys, "gone", name(2))
    assert code == 3 and "add --team" in err
    assert run(drafting, capsys, "gone", name(2), "--team", "NYK")[0] == 0
    assert list(state(drafting)["players"]) == [S.normalise(name(2))]


def test_offboard_without_a_near_match(drafting, capsys):
    code, out, err = run(drafting, capsys, "mine", STRANGER, "--pick", "14")
    assert code == 0
    assert "recorded off-board" in err
    assert tsv(out)[2] == [["mine", STRANGER, "", "off-board", "Y", "Y", "14", ""]]
    assert state(drafting)["offboard"] == [{"name": STRANGER, "pick": 14, "mine": True}]


def test_offboard_with_a_near_match_needs_the_flag(drafting, capsys):
    typo = name(6)[:-1]
    assert run(drafting, capsys, "gone", typo)[0] == 3
    assert state(drafting)["offboard"] == []
    assert run(drafting, capsys, "gone", typo, "--offboard")[0] == 0
    assert state(drafting)["offboard"] == [{"name": typo, "pick": None, "mine": False}]


def test_offboard_undo(drafting, capsys):
    run(drafting, capsys, "mine", STRANGER)
    assert run(drafting, capsys, "gone", STRANGER, "--undo")[0] == 2
    run(drafting, capsys, "mine", STRANGER, "--undo")
    assert run(drafting, capsys, "gone", STRANGER, "--undo")[0] == 0
    assert state(drafting)["offboard"] == []


def test_pick_gaps_and_duplicates_reported(drafting, capsys):
    run(drafting, capsys, "gone", name(0), "--pick", "1")
    run(drafting, capsys, "gone", name(1), "--pick", "4")
    run(drafting, capsys, "gone", STRANGER, "--pick", "4")
    _, out, _ = run(drafting, capsys, "status", "--json")
    status = json.loads(out)["status"]
    assert status["pick_gaps"] == "2,3"
    assert status["pick_duplicates"] == f"4: {' / '.join(sorted([name(1), STRANGER]))}"
    code, out, err = run(drafting, capsys, "check")
    assert code == 0
    assert "logged twice" in err


def test_pick_with_two_names_is_usage(drafting, capsys):
    assert run(drafting, capsys, "gone", name(0), name(1), "--pick", "3")[0] == 2


@pytest.mark.parametrize("token", ["fg", "fg%", "FG%", "Fg"])
def test_concede_parsing(drafting, capsys, token):
    assert run(drafting, capsys, "concede", token)[0] == 0
    assert state(drafting)["conceded"] == ["FG%"]


def test_concede_keeps_tracker_order_and_undoes(drafting, capsys):
    run(drafting, capsys, "concede", "blk", "ft")
    assert state(drafting)["conceded"] == ["FT%", "BLK"]
    run(drafting, capsys, "concede", "blk", "--undo")
    assert state(drafting)["conceded"] == ["FT%"]


@pytest.mark.parametrize("token", ["TO", "to", "tov", "xyz"])
def test_concede_rejects_turnovers_and_junk(drafting, capsys, token):
    assert run(drafting, capsys, "concede", token)[0] == 2
    assert state(drafting)["conceded"] == []


@pytest.mark.parametrize(("spec", "want"), [
    ("bmp-alt:durh", {"source": "BMP-ALT", "kind": "durh"}),
    ("HBP:ZSC", {"source": "HBP", "kind": "zsc"}),
    ("BMP · DURH", {"source": "BMP", "kind": "durh"}),
])
def test_sort_parsing(drafting, capsys, spec, want):
    assert run(drafting, capsys, "sort", spec)[0] == 0
    assert state(drafting)["applied_sort"] == want


@pytest.mark.parametrize("spec", ["bmp", "XYZ:durh", "bmp:value", "a:b:c"])
def test_sort_rejects_junk(drafting, capsys, spec):
    assert run(drafting, capsys, "sort", spec)[0] == 2


def test_hand_columns_set_and_clear(drafting, capsys):
    key = N.key_of(name(3))
    for cmd, field, value in (("gp", "my_gp", "40"), ("xrank", "xrank", "9"),
                              ("gp1", "gp1", "70"), ("gp2", "gp2", "61"), ("gp3", "gp3", "0")):
        assert run(drafting, capsys, cmd, name(3), value)[0] == 0
        assert state(drafting)["players"][key][field] == int(value)
    assert run(drafting, capsys, "gp", name(3), "--clear")[0] == 0
    assert state(drafting)["players"][key]["my_gp"] is None
    assert run(drafting, capsys, "gp", name(3))[0] == 2
    assert run(drafting, capsys, "gp", name(3), "5", "--clear")[0] == 2
    assert run(drafting, capsys, "xrank", name(3), "0")[0] == 2


def test_undo_reverts_each_reversible_command(drafting, capsys):
    empty = state(drafting)
    for argv in (["gone", name(1)], ["mine", name(2), "--pick", "3"], ["mine", STRANGER],
                 ["concede", "ft"], ["sort", "hbp:zsh"], ["note", name(1), "x"],
                 ["gp", name(1), "50"], ["xrank", name(1), "2"], ["gp1", name(1), "1"],
                 ["gp2", name(1), "2"], ["gp3", name(1), "3"]):
        assert run(drafting, capsys, *argv)[0] == 0, argv
    assert len(state(drafting)["events"]) == 11
    for _ in range(11):
        assert run(drafting, capsys, "undo")[0] == 0
    assert state(drafting) == empty
    code, _, err = run(drafting, capsys, "undo")
    assert code == 2 and "nothing to undo" in err


def test_no_change_records_no_event(drafting, capsys):
    run(drafting, capsys, "gone", name(1))
    events = len(state(drafting)["events"])
    _, _, err = run(drafting, capsys, "gone", name(1))
    assert "no change" in err
    assert len(state(drafting)["events"]) == events


def test_event_carries_before_and_after(drafting, capsys):
    run(drafting, capsys, "mine", name(1), "--pick", "2")
    event = state(drafting)["events"][-1]
    key = N.key_of(name(1))
    assert event["cmd"] == "mine"
    assert event["args"] == ["mine", name(1), "--pick", "2"]
    assert event["before"] == {f"players.{key}.gone": False, f"players.{key}.mine": False,
                               f"players.{key}.pick": None}
    assert event["after"] == {f"players.{key}.gone": True, f"players.{key}.mine": True,
                              f"players.{key}.pick": 2}


def test_show_prints_board_and_tracker_after_the_write(drafting, capsys):
    code, out, _ = run(drafting, capsys, "mine", name(0), "--show", "board,tracker")
    sections = out.split("\n\n")
    assert code == 0
    assert [s.splitlines()[0] for s in sections[1:]] == ["# board", "# tracker", "# roster"]
    assert name(0) not in sections[1]                    # the available board
    assert sections[3].splitlines()[2].split("\t")[1] == name(0)
    _, out, _ = run(drafting, capsys, "gone", name(1), "--show", "tracker", "--json")
    assert set(json.loads(out)) == {"context", "result", "tracker", "roster"}


def test_show_rejects_other_views(drafting, capsys):
    assert run(drafting, capsys, "gone", name(1), "--show", "punts")[0] == 2


def test_write_without_state_is_integrity(root, capsys):
    code, _, err = run(root, capsys, "gone", name(1))
    assert code == 4 and "board.py new" in err
    assert not (root / "draft-state.json").exists()


def test_digest_mismatch_blocks_writes(drafting, capsys):
    tick(drafting, name(1), gone=True)
    saved = state(drafting)
    snap = make_snapshot()
    snap["players"][0]["values"]["BMP"]["durh"]["v"] += 1.0
    write_snapshot(drafting, snap)
    for argv in (["gone", name(2)], ["concede", "ft"], ["undo"]):
        assert run(drafting, capsys, *argv)[0] == 4, argv
    assert state(drafting) == saved


def test_concurrent_writers_lose_no_event(drafting):
    """Twenty separate processes tick twenty players at once; every event must survive.

    Separate processes, not threads: `flock` is what is under test, and only real
    processes contend for it the way two agents would. Without the lock this loses events
    on every run.
    """
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    scripts = Path(board.__file__).resolve().parent
    names = [name(i) for i in range(15)] + [STRANGER, "Pellucid Thrumwhistle",
                                            "Grimble Vauxhenfroth", "Quothwick Ondraspell",
                                            "Brastlewood Ymirqueth"]
    code = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
            "import board; sys.exit(board.main(['mine', sys.argv[3]], root=Path(sys.argv[2])))")

    def one(player):
        return subprocess.run([sys.executable, "-c", code, str(scripts), str(drafting), player],
                              capture_output=True, text=True, timeout=60)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(one, names))

    assert [r.returncode for r in results] == [0] * 20, [r.stderr for r in results]
    final = state(drafting)
    assert len([e for e in final["events"] if e["cmd"] == "mine"]) == 20
    assert sum(1 for p in final["players"].values() if p["mine"]) == 15
    assert len(final["offboard"]) == 5


# --- new and rebase ---------------------------------------------------------------------


def test_new_starts_a_pinned_empty_state(root, capsys):
    code, out, _ = run(root, capsys, "new")
    assert code == 0
    assert tsv(out)[2][0][0] == "new"
    now = state(root)
    assert now["snapshot"]["date"] == "2026-01-01"
    assert [e["cmd"] for e in now["events"]] == ["new"]
    code, _, err = run(root, capsys, "undo")
    assert code == 2 and "`new`" in err


def test_new_refuses_a_non_empty_state_and_backs_up(drafting, capsys):
    run(drafting, capsys, "mine", name(1))
    saved = state(drafting)
    code, _, err = run(drafting, capsys, "new")
    assert code == 2 and "--force" in err
    assert state(drafting) == saved
    assert list(drafting.glob("*.bak.json")) == []

    assert run(drafting, capsys, "new", "--force")[0] == 0
    backups = list(drafting.glob("draft-state.*.bak.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text()) == saved
    assert state(drafting)["players"] == {}
    assert [e["cmd"] for e in state(drafting)["events"]] == ["new"]


def test_new_over_an_empty_state_needs_no_force(drafting, capsys):
    assert run(drafting, capsys, "new")[0] == 0
    assert len(list(drafting.glob("*.bak.json"))) == 1


def test_new_over_a_corrupt_state_needs_force(drafting, capsys):
    (drafting / "draft-state.json").write_text("{half a file")
    assert run(drafting, capsys, "new")[0] == 4
    assert run(drafting, capsys, "new", "--force")[0] == 0
    assert len(list(drafting.glob("*.bak.json"))) == 1


def test_new_without_a_snapshot_is_integrity(tmp_path, capsys):
    assert run(tmp_path, capsys, "new")[0] == 4


def test_state_under_root_is_its_own_draft(drafting, capsys):
    assert run(drafting, capsys, "new", "--state", "mock/one.json")[0] == 0
    assert run(drafting, capsys, "gone", name(1), "--state", "mock/one.json")[0] == 0
    assert state(drafting)["players"] == {}
    mock = json.loads((drafting / "mock" / "one.json").read_text())
    assert list(mock["players"]) == [N.key_of(name(1))]


def _next_board(drop: list[int]) -> dict:
    """The fixture board a day later, with the given rows replaced by new invented players."""
    names = [name(i) for i in range(15)]
    for i in drop:
        names[i] = name(40 + i)
    return make_snapshot(date="2026-01-02", names=names)


def test_rebase_moves_a_dropped_gone_player_offboard(drafting, capsys):
    run(drafting, capsys, "gone", name(3), "--pick", "7")
    run(drafting, capsys, "mine", name(5), "--pick", "8")
    write_snapshot(drafting, _next_board(drop=[3]))

    code, out, _ = run(drafting, capsys, "rebase")

    _, header, rows = tsv(out)
    assert code == 0
    assert header == ["change", "name", "detail"]
    assert ["dropped", name(3), "was GONE; moved to offboard"] in rows
    assert ["added", name(43), "rank 4"] in rows
    now = state(drafting)
    assert now["snapshot"]["date"] == "2026-01-02"
    assert now["offboard"] == [{"name": name(3), "pick": 7, "mine": False}]
    assert list(now["players"]) == [N.key_of(name(5))]
    assert len(list(drafting.glob("draft-state.*.bak.json"))) == 1
    assert run(drafting, capsys, "undo")[0] == 2
    assert run(drafting, capsys, "status")[0] == 0


def test_rebase_refuses_a_dropped_mine_player(drafting, capsys):
    run(drafting, capsys, "mine", name(3))
    saved = state(drafting)
    write_snapshot(drafting, _next_board(drop=[3]))

    code, out, err = run(drafting, capsys, "rebase")

    assert (code, out) == (4, "")
    assert name(3) in err
    assert state(drafting) == saved
    assert list(drafting.glob("*.bak.json")) == []


def test_rebase_after_a_same_date_rebuild(drafting, capsys):
    run(drafting, capsys, "gone", name(1))
    snap = make_snapshot()
    snap["players"][0]["values"]["BMP"]["durh"]["v"] += 1.0
    write_snapshot(drafting, snap)
    assert run(drafting, capsys, "status")[0] == 4

    code, _, err = run(drafting, capsys, "rebase")

    assert code == 0 and "cannot be reported" in err
    assert run(drafting, capsys, "status")[0] == 0
    assert state(drafting)["players"][N.key_of(name(1))]["gone"] is True


def test_rebase_when_already_newest_changes_nothing(drafting, capsys):
    saved = state(drafting)
    code, out, _ = run(drafting, capsys, "rebase")
    assert code == 0 and "already pinned" in out
    assert state(drafting) == saved


def test_rebase_without_state_is_integrity(root, capsys):
    assert run(root, capsys, "rebase")[0] == 4
