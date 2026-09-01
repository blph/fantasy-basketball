#!/usr/bin/env python3
"""Read the three projection exports and join them into one player set.

Three providers, three shapes, no shared identifier between the two vendors:

    HBP   Hashtag Basketball   per game, 200 rows, carries team / position / ADP
    BMP   Basketball Monster   season totals, ~570 rows, `player_id`, no team or position
    BMP-ALT                    the same schema, Basketball Monster's second source

HBP is the spine. It decides which 200 players are on the board and supplies every
identity column; the two vendor files supply stat lines only. BMP and BMP-ALT share an id
space so they join on `player_id`; HBP has no id at all, so it joins on a normalised name
plus an explicit alias table.

Every failure here is loud. An unresolved player is an error and never a skipped row
(AGENTS.md), because a silently dropped player is a hole in the board that looks exactly
like a player nobody rates.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

# Percentages arrive from Hashtag as a rate, a newline, then makes and attempts:
# "0.573\n(10.5/18.3)". The makes and attempts are the point -- a bare rate throws away
# the volume, and the percentage categories are volume-weighted.
PCT = re.compile(r"([\d.]+)\s*\(([\d.]+)/([\d.]+)\)", re.S)

# `R#` occasionally carries a second number (rank movement): "18 38" means rank 18.
LEADING_INT = re.compile(r"(\d+)")

SUFFIX = re.compile(r"\b(?:Jr|Sr|II|III|IV|V)\.?\b", re.I)

#: Hashtag's spelling -> Basketball Monster's, for players the normaliser cannot reconcile
#: because the two vendors disagree on the name itself rather than on its punctuation.
#: Keep this as short as the data allows: every entry is a place where we have asserted
#: two rows are the same person. An alias that no longer matches anything is reported as
#: unused rather than raising -- a player dropping out of Hashtag's top 200 is ordinary,
#: and an alias that is genuinely broken already surfaces as `UnresolvedPlayer`.
ALIASES = {
    "cameronjohnson": "camjohnson",
    "herbertjones": "herbjones",
}

BOARD_ROWS = 200


class SourceError(Exception):
    """A projection export is not what the board requires."""


class UnresolvedPlayer(SourceError):
    """A player on the board does not appear in one of the vendor files."""


class AmbiguousName(SourceError):
    """Two players in one source normalise to the same key."""


def normalise(name: str) -> str:
    """A join key: strip accents, suffixes, punctuation and case, then apply aliases.

    Jokic and Jokic, Porzingis and Porzingis, Jaren Jackson Jr. and Jaren Jackson all have
    to land on one key. NFKD splits a letter from its combining marks so the marks can be
    dropped without a per-character table.
    """
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in folded if not unicodedata.combining(c))
    ascii_only = ascii_only.encode("ascii", "ignore").decode()
    key = re.sub(r"[^a-z]", "", SUFFIX.sub("", ascii_only).lower())
    return ALIASES.get(key, key)


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_vendor(path: Path) -> dict[int, dict]:
    """A Basketball Monster export -> {player_id: season-total projection}.

    Rows projected zero games are dropped rather than rated. They cannot be scored, and
    leaving them in drags every pool mean toward zero.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bbm"))
    from bbm_reference import from_components  # noqa: E402

    out: dict[int, dict] = {}
    names: dict[str, str] = {}
    for row in _rows(path):
        if float(row["games"]) <= 0:
            continue
        pid = int(row["player_id"])
        proj = from_components(row)
        full = f"{row['first_name']} {row['last_name']}".strip()
        proj["name"] = full
        proj["player_id"] = pid
        key = normalise(full)
        if key in names and names[key] != full:
            raise AmbiguousName(
                f"{path.name}: '{full}' and '{names[key]}' both normalise to '{key}'"
            )
        names[key] = full
        out[pid] = proj
    if not out:
        raise SourceError(f"{path.name}: no players with a positive game count")
    return out


def load_board(path: Path) -> list[dict]:
    """The Hashtag export -> the 200 board rows, in the provider's own rank order.

    The file repeats its header roughly every thirteen players and embeds newlines inside
    the quoted percentage fields, so neither the line count nor a line-based parser gives
    the row count. `csv` handles the quoting; the header rows are dropped by requiring a
    numeric `R#`.
    """
    out = []
    for row in _rows(path):
        rank = LEADING_INT.match((row.get("R#") or "").strip())
        if not rank:
            continue  # a repeated header row
        gp = float(row["GP"])
        fg = PCT.match(row["FG%"].strip())
        ft = PCT.match(row["FT%"].strip())
        if not fg or not ft:
            raise SourceError(
                f"{path.name}: row {rank.group(1)} has an unparsable "
                f"percentage: FG={row['FG%']!r} FT={row['FT%']!r}"
            )
        name = row["PLAYER"].strip()
        adp = (row.get("ADP") or "").strip()
        out.append(
            {
                "seed": int(rank.group(1)),
                "name": name,
                "key": normalise(name),
                "team": row["TEAM"].strip(),
                "pos": row["POS"].strip(),
                # Blank, never zero: a player the market has not priced is not a player
                # the market prices at the very top.
                "adp": float(adp) if adp else None,
                # Already per game, so it goes straight in. Multiplying by games only to
                # divide again would add a rounding round-trip for nothing.
                "rates": {
                    "games": gp,
                    "minutes": float(row["MPG"]),
                    "points": float(row["PTS"]),
                    "threes": float(row["3PM"]),
                    "rebounds": float(row["TREB"]),
                    "assists": float(row["AST"]),
                    "steals": float(row["STL"]),
                    "blocks": float(row["BLK"]),
                    "turnovers": float(row["TO"]),
                    "fg_made": float(fg.group(2)),
                    "fg_att": float(fg.group(3)),
                    "ft_made": float(ft.group(2)),
                    "ft_att": float(ft.group(3)),
                },
            }
        )

    if len(out) != BOARD_ROWS:
        raise SourceError(f"{path.name}: {len(out)} players, the board is built for {BOARD_ROWS}")
    seeds = [p["seed"] for p in out]
    if seeds != list(range(1, BOARD_ROWS + 1)):
        raise SourceError(f"{path.name}: R# is not contiguous 1..{BOARD_ROWS}")
    keys = {}
    for p in out:
        if p["key"] in keys:
            raise AmbiguousName(f"{path.name}: '{p['name']}' and '{keys[p['key']]}' collide")
        keys[p["key"]] = p["name"]
    return out


def join(board: list[dict], vendors: dict[str, dict[int, dict]]) -> dict[str, list[str]]:
    """Attach each vendor's id to every board row. Returns a per-vendor report.

    Mutates `board`, setting `row["ids"][vendor]`. Raises rather than returning partial
    coverage: a board row with no stat line in one source would render as a blank value
    column, which reads as "this player is bad" instead of "this player is missing".
    """
    report: dict[str, list[str]] = {}
    used_aliases: set[str] = set()

    for label, players in vendors.items():
        by_key: dict[str, int] = {}
        for pid, proj in players.items():
            by_key[normalise(proj["name"])] = pid

        missing, matched = [], 0
        for row in board:
            row.setdefault("ids", {})
            pid = by_key.get(row["key"])
            if pid is None:
                missing.append(row["name"])
                continue
            row["ids"][label] = pid
            matched += 1
            if row["key"] in ALIASES.values():
                used_aliases.add(row["key"])

        if missing:
            raise UnresolvedPlayer(
                f"{label}: {len(missing)} board players have no stat line "
                f"-- add an alias in sources.ALIASES: {', '.join(sorted(missing))}"
            )
        report[label] = [f"{matched}/{len(board)} matched"]

    stale = sorted(set(ALIASES.values()) - used_aliases)
    if stale:
        report["aliases"] = [
            f"{len(stale)} unused: {', '.join(stale)} -- review if they stay unused, "
            "an alias nobody needs is one that can start matching the wrong player"
        ]
    return report
