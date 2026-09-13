"""The draft state file: pin, atomic save, lock, backups, events and undo."""

from __future__ import annotations

import json

import board_engine as E
import board_state as ST
import pytest

from board_fixtures import make_snapshot


@pytest.fixture
def snap():
    return make_snapshot()


def test_new_state_is_the_engine_empty_state_plus_a_pin(snap):
    state = ST.new_state(snap)
    empty = E.empty_state()
    assert state["version"] == ST.VERSION
    assert state["snapshot"] == {"date": "2026-01-01", "digest": snap["meta"]["digest"]}
    for key in empty:
        assert state[key] == empty[key]
    assert state["events"] == []


def test_save_then_load_round_trips_and_leaves_no_temp(tmp_path, snap):
    path = tmp_path / "draft-state.json"
    state = ST.new_state(snap)
    ST.save(path, state)
    assert ST.load(path) == state
    assert [p.name for p in tmp_path.iterdir()] == ["draft-state.json"]


@pytest.mark.parametrize("text", ["{not json", "[]", '{"version": 2}', '{"version": 1}'])
def test_load_refuses_a_corrupt_state(tmp_path, text):
    path = tmp_path / "draft-state.json"
    path.write_text(text)
    with pytest.raises(ST.StateError):
        ST.load(path)


def test_check_pin_passes_on_its_own_snapshot(snap):
    ST.check_pin(ST.new_state(snap), snap)


def test_check_pin_refuses_another_date(snap):
    other = make_snapshot(date="2026-01-02")
    with pytest.raises(ST.StateError, match="pinned to 2026-01-01"):
        ST.check_pin(ST.new_state(snap), other)


def test_check_pin_refuses_a_rebuilt_snapshot(snap):
    state = ST.new_state(snap)
    snap["players"][0]["values"]["BMP"]["durh"]["v"] += 1.0
    import board_snapshot as BS

    snap["meta"]["digest"] = BS.digest(snap)
    with pytest.raises(ST.StateError, match="rebuilt after the draft state was pinned"):
        ST.check_pin(state, snap)


def test_check_pin_refuses_a_key_not_on_the_board(snap):
    state = ST.new_state(snap)
    state["players"]["nosuchplayer"] = ST.defaults("nosuchplayer") | {"gone": True}
    with pytest.raises(ST.StateError, match="not on the pinned board"):
        ST.check_pin(state, snap)


def test_undo_reverts_the_last_event_and_prunes_a_blank_player(snap):
    state = ST.new_state(snap)
    key = snap["players"][0]["key"]
    before = {f"players.{key}.gone": False, f"players.{key}.mine": False}
    after = {f"players.{key}.gone": True, f"players.{key}.mine": True}
    for path, value in after.items():
        ST.set_path(state, path, value)
    ST.record(state, "mine", ["x"], before, after)
    assert state["players"][key]["mine"] is True

    event = ST.undo(state)

    assert event["cmd"] == "mine"
    assert state["players"] == {}
    assert state["events"] == []


def test_undo_restores_whole_values(snap):
    state = ST.new_state(snap)
    ST.set_path(state, "conceded", ["FT%"])
    ST.record(state, "concede", ["ft"], {"conceded": []}, {"conceded": ["FT%"]})
    ST.undo(state)
    assert state["conceded"] == []


@pytest.mark.parametrize("cmd", ["new", "rebase"])
def test_undo_refuses_new_and_rebase(snap, cmd):
    state = ST.new_state(snap)
    ST.record(state, cmd, [], {}, {})
    with pytest.raises(ST.UndoError, match=f"`{cmd}`"):
        ST.undo(state)
    assert len(state["events"]) == 1


def test_undo_with_no_events(snap):
    with pytest.raises(ST.UndoError, match="nothing to undo"):
        ST.undo(ST.new_state(snap))


def test_backup_copies_and_never_overwrites(tmp_path, snap):
    path = tmp_path / "draft-state.json"
    assert ST.backup(path) is None
    ST.save(path, ST.new_state(snap))
    first, second = ST.backup(path), ST.backup(path)
    assert first != second
    for bak in (first, second):
        assert bak.name.startswith("draft-state.") and bak.name.endswith(".bak.json")
        assert json.loads(bak.read_text()) == ST.load(path)


def test_locked_uses_a_sibling_lock_file(tmp_path):
    path = tmp_path / "draft-state.json"
    with ST.locked(path):
        assert (tmp_path / "draft-state.json.lock").exists()
        assert not path.exists()
