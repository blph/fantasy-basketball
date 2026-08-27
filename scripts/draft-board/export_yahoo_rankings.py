#!/usr/bin/env python3
"""Turn the Draft Board tab into a CSV Yahoo's "Import Rankings" box will accept.

Yahoo wants `rank,name,team,position`, one player per line, and matches on the
name column; team and position are cosmetic. Three things have to be reconciled
between what the sheet holds and what Yahoo reads:

  - Team codes are the provider's, not Yahoo's. Four differ (GS, NO, NY, SA).
  - `Pos` is comma-separated multi-eligibility ("SG,SF,PF"), which collides with
    the CSV delimiter. Only the primary position survives.
  - Below replacement level, Adjusted Value inverts and the board's tail is
    ordered by fragility rather than value (methodology review, finding F9), so
    the export stops at the drafted pool.

Input is the raw `Draft Board!A3:E202` range, five columns wide, as fetched by
the playwright-cli step in docs/draft-board/build-and-maintenance.md.

Output lands in `data/exports/`, dated, beside the provider exports that fed the
board. Provider data in, provider data out — `data/` and `*.csv` are both
gitignored and the pre-commit hook blocks them. Never commit the output.
"""

import argparse
import csv
import datetime
import sys
from pathlib import Path

# Transcribed from config/league.yaml (`league.season`). Kept as a constant
# rather than parsed: pyyaml is not a declared dependency and a runtime dep needs
# an ADR. Build.gs transcribes the league settings the same way.
SEASON = "2026-27"

# The repo root, from this file's location rather than the cwd, so the default
# output path is the same wherever the script is run from.
REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_DIR = REPO_ROOT / "data" / "exports"

# 12 teams x 13 roster spots. Past this the board's ordering is not trustworthy
# (finding F9): VOR goes negative, and scaling a negative by GP/72 < 1 moves it
# toward zero, i.e. up. Nothing sub-replacement can outrank an above-replacement
# player, so ranks 1..DRAFTED_POOL are unaffected — but the tail is scrambled.
DRAFTED_POOL = 156

# Hashtag Basketball abbreviations that Yahoo spells differently. Everything else
# passes through untouched.
TEAM_FIXUPS = {
    "GS": "GSW",
    "NO": "NOP",
    "NY": "NYK",
    "SA": "SAS",
}

YAHOO_TEAMS = {
    "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHO", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
}

# Column offsets within the fetched A3:E202 range: A=#, B=TIER, C=Player,
# D=Team, E=Pos. The board's own rank in column A is read for validation only —
# the exported rank is re-derived from row order.
COL_PLAYER = 2
COL_TEAM = 3
COL_POS = 4
RANGE_WIDTH = 5


class ExportError(Exception):
    """The input does not look like the Draft Board range."""


def normalize_team(code: str) -> str:
    """Map a provider team code onto Yahoo's. An unknown code is an error."""
    team = TEAM_FIXUPS.get(code, code)
    if team not in YAHOO_TEAMS:
        raise ExportError(f"unrecognised team code {code!r} (mapped to {team!r})")
    return team


def primary_position(pos: str) -> str:
    """Take the first of a player's eligible positions.

    Yahoo matches on name and treats position as optional, so collapsing
    "SG,SF,PF" to "SG" loses nothing functional and keeps the field free of the
    delimiter.
    """
    return pos.split(",")[0].strip()


def convert(rows, limit=DRAFTED_POOL):
    """Yield Yahoo rows from the raw Draft Board range.

    Rank is renumbered from row order rather than copied from column A: row
    order *is* the Adjusted Value order, so a blank or an #N/A in column A
    cannot punch a hole in the sequence.
    """
    out = []
    for lineno, row in enumerate(rows, start=3):  # sheet row numbers, for errors
        if not any(cell.strip() for cell in row):
            continue  # trailing blank row in the 200-row grid
        if len(row) != RANGE_WIDTH:
            raise ExportError(
                f"sheet row {lineno}: expected {RANGE_WIDTH} columns, got {len(row)}"
            )
        name = row[COL_PLAYER].strip()
        if not name:
            raise ExportError(f"sheet row {lineno}: no player name")
        try:
            team = normalize_team(row[COL_TEAM].strip())
        except ExportError as exc:
            raise ExportError(f"sheet row {lineno}: {exc}") from exc
        out.append([len(out) + 1, name, team, primary_position(row[COL_POS].strip())])
        if len(out) == limit:
            break

    if len(out) < limit:
        raise ExportError(
            f"only {len(out)} players in the input, needed {limit} — "
            "was the fetched range short?"
        )
    return out


def default_output_path(today=None):
    """Where an export lands when no path is given.

    Dated MMDD, matching the `player_data_MMDD.md` convention the provider
    exports already use in `data/`. One file per export rather than one per
    season: the board moves on every refresh, and keeping them apart is what
    lets you diff two boards or recover the rankings you actually drafted from.
    """
    stamp = (today or datetime.date.today()).strftime("%m%d")
    return EXPORT_DIR / f"yahoo-rankings-{SEASON}-{stamp}.csv"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Turn the Draft Board tab into a CSV Yahoo's Import Rankings accepts."
    )
    ap.add_argument(
        "src",
        nargs="?",
        default="-",
        help="raw Draft Board!A3:E202 CSV, or - for stdin (default: -)",
    )
    ap.add_argument(
        "-o",
        "--out",
        default=None,
        help="where to write the Yahoo CSV (default: data/exports/, dated)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=DRAFTED_POOL,
        help=f"how many players to export (default: {DRAFTED_POOL}, the drafted pool)",
    )
    args = ap.parse_args(argv)

    src = sys.stdin if args.src == "-" else open(args.src, encoding="utf-8", newline="")
    try:
        rows = convert(list(csv.reader(src)), limit=args.limit)
    finally:
        if src is not sys.stdin:
            src.close()

    out = Path(args.out) if args.out else default_output_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "name", "team", "position"])
        w.writerows(rows)

    print(f"wrote {len(rows)} players to {out}", file=sys.stderr)
    return out


if __name__ == "__main__":
    try:
        main()
    except ExportError as exc:
        sys.exit(f"export_yahoo_rankings: {exc}")
