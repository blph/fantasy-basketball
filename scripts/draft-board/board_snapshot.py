"""The local draft board: one JSON snapshot per build, written beside Data.gs.

`build_data.py` writes it in the same run, from the same objects, as the Data.gs the sheet
runs on, and stamps one digest into both (ADR-0022). That shared digest is the whole sync
mechanism: the local board is never pulled from the sheet, and the sheet is never fed from
it. A snapshot and a Data.gs that disagree on the digest are not the same board, and
nothing downstream is allowed to pretend otherwise.

It is written for agents, not for people, and agents do not open it: at 200 players across
three sources of named fields it is well past 100k tokens, which is also why it is written
compact rather than pretty-printed. Code reads it through `load`, which refuses a file whose
digest does not recompute.

Provider data, exactly as Data.gs is. It lives under data/draft-board/, which is gitignored
and blocked by check-no-data.sh, and it is never committed (ADR-0006).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "draft-board"
SCHEMA = 1

#: Display order, which is also SOURCES in Build.gs and SOURCE_FILES in build_data.py.
SOURCES = ("BMP", "HBP", "BMP-ALT")
KINDS = ("durh", "zsh", "zsc")

#: Build.gs PUNTS, in its order. The keys are build_data.PUNTS's; a test holds all three
#: lists to one another.
PUNT_BUILDS = (("pFt", "Punt FT%"), ("pFg", "Punt FG%"), ("pAst", "Punt AST"), ("p3", "Punt 3PM"),
               ("pBlk", "Punt BLK"), ("pFgReb", "Punt FG%+REB"), ("pAstStl", "Punt AST+STL"),
               ("pPtsFt", "Punt PTS+FT%"), ("pTriple", "Punt FG/FT/TO"))

#: A Data.gs PLAYERS row, by position. Data.gs is positional because the sheet reads it by
#: index (REFRESH_MAP); the snapshot is named because agents read it by field. One tuple
#: shared by the writer and the checker, so the two cannot disagree about which is which.
PLAYER_FIELDS = ("seed", "name", "team", "pos", "adp", "gp", "mpg", "fgm", "fga", "fgp",
                 "ftm", "fta", "ftp", "tpm", "pts", "reb", "ast", "stl", "blk", "to", "inj")

#: The raw line every calculation tab carries -- always Hashtag's, whatever the projection,
#: which is why it is named for its source.
HBP_RAW_FIELDS = PLAYER_FIELDS[5:20]

#: Meta fields the digest cannot cover: one is the digest, the other hashes a file that
#: contains it.
UNHASHED = ("digest", "data_gs_sha256")

FILENAME = re.compile(r"^board - (\d{4}-\d{2}-\d{2})\.json$")


class SnapshotError(Exception):
    """A snapshot that is missing, unreadable, of another schema, or not what its digest says."""


def path_for(root: Path, date: str) -> Path:
    return root / f"board - {date}.json"


def list_dates(root: Path) -> list[str]:
    """Every snapshot date under `root`, oldest first. Temp files and state files never match."""
    if not root.is_dir():
        return []
    return sorted(m.group(1) for p in root.iterdir() if (m := FILENAME.match(p.name)))


def newest(root: Path) -> Path | None:
    dates = list_dates(root)
    return path_for(root, dates[-1]) if dates else None


def digest(snapshot: dict) -> str:
    """sha256 over a canonical serialisation of everything but the two unhashable fields.

    Canonical means sorted keys and fixed separators, so the digest is a property of the
    content and not of the order a dict happened to be built in.
    """
    body = dict(snapshot)
    body["meta"] = {k: v for k, v in (snapshot.get("meta") or {}).items() if k not in UNHASHED}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def dumps(snapshot: dict) -> str:
    """Compact, one line. Nobody reads this file by eye; an agent reads it through the CLI."""
    return json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False) + "\n"


def load(path: Path) -> dict:
    """Read a snapshot, refusing anything that is not exactly what its build wrote.

    A digest that does not recompute means the file was edited after it was written, and a
    hand-edited board is a wrong number that looks right.
    """
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SnapshotError(f"{path}: no such snapshot. build_data.py writes one when --out "
                            "is the default Data.gs.") from None
    except ValueError as exc:
        raise SnapshotError(f"{path}: not JSON ({exc})") from None
    if not isinstance(snapshot, dict) or snapshot.get("schema") != SCHEMA:
        got = snapshot.get("schema") if isinstance(snapshot, dict) else type(snapshot).__name__
        raise SnapshotError(f"{path}: schema {got!r}, this code reads schema {SCHEMA}")
    recorded = (snapshot.get("meta") or {}).get("digest")
    if not recorded or recorded != digest(snapshot):
        raise SnapshotError(f"{path}: the digest does not recompute -- the file was changed "
                            "after build_data.py wrote it. Rebuild; never hand-edit it.")
    return snapshot
