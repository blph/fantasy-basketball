"""Synthetic local-board snapshots for the engine, CLI, verification and export tests.

Every name and number here is invented. The real snapshot is provider data and this
repository is public (ADR-0006), so nothing under data/draft-board/ is ever read or copied
into a test.

One builder for every consumer, so a field the engine reads cannot be present in one
fixture and missing from another. The board is scaled down -- 15 players and 3 teams of 4
by default -- so a test can reason about every row, but it carries every field of the
schema-1 contract, because a fixture that drops a field passes here and fails on the real
board. Within every source and kind the values fall strictly with the board row, so row i
has rank i + 1 everywhere and nothing ties unless a test makes it tie.
"""

from __future__ import annotations

import copy
from pathlib import Path

import board_engine as E
import board_settings
import board_snapshot as BS
import sources as S

from test_sources import made_up_name

CATS = ["FG%", "FT%", "3PM", "PTS", "REB", "AST", "STL", "BLK"]
TEAM_CYCLE = ["BOS", "GS", "NY", "SA", "NO", "MIA"]
POS_CYCLE = ["PG", "SG,SF", "SF,PF", "PF,C", "C", "G", "F"]
INJ_CYCLE = ["LOW", "MED", "HIGH", "EXTREME", "?"]

#: The league's settings scaled to a 15-row board: 3 teams of 4 draft 12, and a
#: disagreement gap of 3 rank places means something on 15 rows. Every other key is
#: board_settings.py's own value. A test that needs the league's numbers passes them in
#: `settings=`.
SCALED = {**board_settings.as_dict(), "teams": 3, "roster": 4, "q": 12, "disagree_gap": 3}

#: Keyword overrides `make_snapshot` accepts. Anything else is a typo in a test and raises.
OVERRIDES = ("names", "player_teams", "settings", "meta")


def _source_block(n: int, i: int, si: int, offset: float) -> dict:
    """One source's values for board row i.

    Values fall with i, so row order is rank order under every kind; `offset` and the kind
    index keep the nine value columns apart, so no two columns are the same list. The
    dropped category walks the categories by row, source and kind, which gives the tag
    tests a different label per column. The per-category blocks vary by row so strengths,
    weaknesses and the tracker's Z have something to find.
    """
    block = {}
    for ki, kind in enumerate(BS.KINDS):
        v = round(offset + (n - i) * 0.1 - ki * 0.01, 4)
        block[kind] = {"v": v, "rank": i + 1}
        if kind != "zsc":
            block[kind]["drop"] = CATS[(i + si + ki) % len(CATS)]
    for part, scale in (("dh", 0.9), ("d", 1.0), ("z", 1.1)):
        block[part] = {c: round(((i * 3 + k) % 7 - 3) * 0.5 * scale, 4)
                       for k, c in enumerate(CATS)}
    return block


def make_snapshot(n: int = 15, date: str = "2026-01-01", **overrides) -> dict:
    """A complete schema-1 snapshot dict whose digest `board_snapshot.load` accepts.

    Overrides: `names` (n names, board order), `player_teams` (n provider team codes), and
    `settings` / `meta`, merged into those dicts. A `settings` override that changes `teams`
    or `roster` without `q` rescales `q` the way the league does, and DERIV's `q`, `teams`
    and `roster` follow the settings, as build_data.py writes them. `meta.generated` is
    `date`. The digest is recomputed after every override; `write_snapshot` recomputes it
    again, so a test may edit the dict before writing it.
    """
    unknown = set(overrides) - set(OVERRIDES)
    if unknown:
        raise TypeError(f"make_snapshot: unknown override(s) {sorted(unknown)}")
    names = overrides.get("names") or [made_up_name(i) for i in range(n)]
    teams = overrides.get("player_teams") or [TEAM_CYCLE[i % len(TEAM_CYCLE)] for i in range(n)]
    if len(names) != n or len(teams) != n:
        raise ValueError("make_snapshot: names and player_teams must both have n entries")

    changed = overrides.get("settings") or {}
    settings = {**SCALED, **changed}
    if ("teams" in changed or "roster" in changed) and "q" not in changed:
        settings["q"] = settings["teams"] * settings["roster"]

    players = []
    for i, (name, team) in enumerate(zip(names, teams, strict=True)):
        gp = 60 + (i * 5) % 22
        fga, fta = 10.0 + i % 5, 3.0 + i % 4
        players.append({
            "row": i, "key": S.normalise(name), "name": name, "team": team,
            "pos": POS_CYCLE[i % len(POS_CYCLE)], "seed": i + 1,
            "adp": None if i % 6 == 5 else float(i + 1 + i % 3),
            "inj": INJ_CYCLE[i % len(INJ_CYCLE)],
            "hbp_raw": {"gp": gp, "mpg": 30.0, "fgm": round(fga * 0.47, 1), "fga": fga,
                        "fgp": 0.47, "ftm": round(fta * 0.8, 1), "fta": fta, "ftp": 0.8,
                        "tpm": 1.0 + i % 3, "pts": 20.0 - i * 0.5, "reb": 5.0 + i % 4,
                        "ast": 4.0 + i % 3, "stl": 1.0, "blk": 0.5, "to": 2.0},
            "values": {src: _source_block(n, i, si, offset)
                       for si, (src, offset) in enumerate(zip(BS.SOURCES, (0.0, 0.05, -0.05),
                                                              strict=True))},
            "punts": {key: {"score": round((n - i) * 0.08 + k * 0.001, 4), "rank": i + 1}
                      for k, (key, _label) in enumerate(BS.PUNT_BUILDS)},
        })
    meta = {"generated": date, "digest": "", "data_gs_sha256": "",
            "sources": {"HBP": f"HBP Projections - {date}.csv"}, "board_rows": n,
            "injuries": {"graded": n - n // 5, "missing": n // 5, "unused": 0}}
    meta.update(overrides.get("meta") or {})
    snapshot = {
        "schema": 1, "meta": meta, "settings": settings,
        "deriv": {"q": settings["q"], "teams": settings["teams"], "roster": settings["roster"],
                  "weights": dict.fromkeys(CATS, 1.0), "k_rosenof": dict.fromkeys(CATS, 1.0),
                  "k_tracker": dict.fromkeys(CATS, 1.0), "slopes": dict.fromkeys(CATS, 1.0),
                  "punt_weight": 0.25},
        "cat_labels": list(CATS),
        "punt_builds": [{"key": k, "label": lab} for k, lab in BS.PUNT_BUILDS],
        "players": players,
    }
    snapshot["meta"]["digest"] = BS.digest(snapshot)
    return snapshot


def write_snapshot(root: Path, snapshot: dict) -> Path:
    """Write `snapshot` where `board.py` looks for it, with a freshly computed digest."""
    snap = copy.deepcopy(snapshot)
    snap["meta"]["digest"] = BS.digest(snap)
    root.mkdir(parents=True, exist_ok=True)
    path = BS.path_for(root, snap["meta"]["generated"])
    path.write_text(BS.dumps(snap), encoding="utf-8")
    snapshot["meta"]["digest"] = snap["meta"]["digest"]
    return path


def set_values(snap: dict, source: str, kind: str, vals: list[float]) -> None:
    """Overwrite one value column and re-rank it the way build_data ranks: desc, ties on row."""
    players = snap["players"]
    for p, v in zip(players, vals, strict=True):
        p["values"][source][kind]["v"] = v
    ordered = sorted(range(len(players)),
                     key=lambda i: (-players[i]["values"][source][kind]["v"], i))
    for rank, i in enumerate(ordered, start=1):
        players[i]["values"][source][kind]["rank"] = rank


def tick(state: dict, snap: dict, i: int, **fields) -> None:
    """Set hand columns on player index `i` in an engine state, the way board.py writes them."""
    key = snap["players"][i]["key"]
    state["players"][key] = {**E.player_state(state, key), **fields}
