"""The draft state file: what has been ticked, pinned to the snapshot it was ticked against.

The state is keyed by board key, never by row, so a re-sort cannot move a tick onto the
wrong player -- the live sheet's I1 defect cannot happen here. It is pinned to one snapshot
by date and digest because a key's meaning is only fixed within one build: a same-date
rebuild can drop a player, and a state that silently followed it would tick holes.

Durability is the point of every function below. A draft is about 156 picks entered one
at a time under a clock; losing the file, or half-writing it, or letting two concurrent
writes race each other out of an event, costs a pick log that cannot be reconstructed.
"""

from __future__ import annotations

import copy
import datetime
import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import board_engine as E

VERSION = 1
KEYS = ("version", "snapshot", "applied_sort", "conceded", "players", "offboard", "events")

#: Commands whose effect `undo` refuses to reverse. Both replace the pin or the whole
#: state; their `.bak.json` is the way back, not an event.
IRREVERSIBLE = ("new", "rebase")


class StateError(Exception):
    """The state file is corrupt, or does not belong to the snapshot. The CLI exits 4."""


class UndoError(Exception):
    """Nothing reversible to undo. The CLI exits 2."""


def defaults(key: str) -> dict:
    """A player's untouched state, taken from the engine so both agree on the defaults."""
    return dict(E.player_state(E.empty_state(), key))


def new_state(snapshot: dict) -> dict:
    """An empty state pinned to `snapshot`."""
    state = E.empty_state()
    return {
        "version": VERSION,
        "snapshot": {"date": snapshot["meta"]["generated"], "digest": snapshot["meta"]["digest"]},
        "applied_sort": state["applied_sort"],
        "conceded": state["conceded"],
        "players": state["players"],
        "offboard": state["offboard"],
        "events": [],
    }


def load(path: Path) -> dict:
    """Read a state file, refusing anything that is not a whole version-1 state."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateError(f"{path.name}: unreadable draft state ({exc})") from exc
    if not isinstance(state, dict) or state.get("version") != VERSION:
        raise StateError(f"{path.name}: not a version-{VERSION} draft state")
    missing = [k for k in KEYS if k not in state]
    if missing:
        raise StateError(f"{path.name}: draft state is missing {', '.join(missing)}")
    return state


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path: Path, state: dict) -> None:
    """Replace the state file atomically: a reader sees the old file or the new, never half.

    The temp file sits in the target directory because `os.replace` is only atomic within
    one filesystem, and the directory is fsynced because the rename is not durable until
    its directory entry is.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(state, ensure_ascii=False, indent=1) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on `<state>.lock` for the duration of one write.

    The lock is on a sibling file, never on the state file itself: `save` replaces the
    state file's inode, so a lock held on it would be a lock on a file nobody opens again.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path.with_name(path.name + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def backup(path: Path) -> Path | None:
    """Copy the state file to `<stem>.<YYYYmmddTHHMMSS>.bak.json` beside it, durably.

    Two backups in one second get `-2`, `-3` suffixes rather than overwriting each other.
    """
    if not path.exists():
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    target = path.with_name(f"{path.stem}.{stamp}.bak.json")
    n = 2
    while target.exists():
        target = path.with_name(f"{path.stem}.{stamp}-{n}.bak.json")
        n += 1
    data = path.read_bytes()
    with target.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    _fsync_dir(path.parent)
    return target


def check_pin(state: dict, snapshot: dict) -> None:
    """Refuse a state that was not ticked against exactly this snapshot."""
    pin, meta = state["snapshot"], snapshot["meta"]
    if pin.get("date") != meta["generated"]:
        raise StateError(f"draft state is pinned to {pin.get('date')}, "
                         f"not the snapshot dated {meta['generated']}")
    if pin.get("digest") != meta["digest"]:
        raise StateError(
            f"the {meta['generated']} snapshot was rebuilt after the draft state was pinned "
            f"(digest {str(pin.get('digest'))[:12]} != {meta['digest'][:12]}); run "
            "verify.py --local, then board.py rebase"
        )
    board = {p["key"] for p in snapshot["players"]}
    stray = sorted(k for k in state["players"] if k not in board)
    if stray:
        raise StateError(f"draft state holds {len(stray)} key(s) not on the pinned board: "
                         + ", ".join(stray))


def get_path(state: dict, path: str):
    """The value at an event path: `players.<key>.<field>`, `conceded`, `applied_sort`..."""
    if path.startswith("players."):
        _, key, field = path.split(".", 2)
        entry = state["players"].get(key)
        return copy.deepcopy(entry[field] if entry else defaults(key)[field])
    return copy.deepcopy(state[path])


def set_path(state: dict, path: str, value) -> None:
    """Set an event path, pruning a player whose every hand field is back at its default."""
    if not path.startswith("players."):
        state[path] = copy.deepcopy(value)
        return
    _, key, field = path.split(".", 2)
    entry = state["players"].setdefault(key, defaults(key))
    entry[field] = copy.deepcopy(value)
    blank = defaults(key)
    if all(entry[f] == blank[f] for f in blank if f != "name"):
        del state["players"][key]


def record(state: dict, cmd: str, args: list, before: dict, after: dict) -> None:
    """Append one event. `before` and `after` map the same paths to their values."""
    state["events"].append({
        "ts": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "cmd": cmd, "args": list(args),
        "before": copy.deepcopy(before), "after": copy.deepcopy(after),
    })


def undo(state: dict) -> dict:
    """Revert the last event from its `before` values, pop it, and return it."""
    if not state["events"]:
        raise UndoError("nothing to undo")
    event = state["events"][-1]
    if event["cmd"] in IRREVERSIBLE:
        raise UndoError(f"the last event is `{event['cmd']}`, which undo does not reverse; "
                        "restore its .bak.json instead")
    for path, value in event["before"].items():
        set_path(state, path, value)
    return state["events"].pop()
