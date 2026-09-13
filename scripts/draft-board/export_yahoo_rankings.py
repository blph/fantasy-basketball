#!/usr/bin/env python3
"""Turn the Draft Board tab into a CSV Yahoo's "Import Rankings" box will accept.

Yahoo wants `rank,name,team,position`, one player per line, and matches on the
name column; team and position are cosmetic. Three things have to be reconciled
between what the sheet holds and what Yahoo reads:

  - Team codes are the provider's, not Yahoo's. Four differ (GS, NO, NY, SA).
  - `Pos` is comma-separated multi-eligibility ("SG,SF,PF"), which collides with
    the CSV delimiter. Only the primary position survives.
  - Only the drafted pool is exported. Past Q the ordering carries no
    information worth importing: everyone there is below replacement, the gaps
    between them are inside the noise of the projection, and the tail is where
    the three sources disagree most.

Input is the raw `Draft Board!A4:G203` range, seven columns wide, as fetched by
the playwright-cli step in docs/draft-board/build-and-maintenance.md. That range
moved when the control strip was added (data now starts at row 4) and when Round
and Injuries were inserted — an old A3:E202 pull silently yields the wrong
columns rather than failing, which is why the header check below is strict.

`--local` reads the local board snapshot instead (ADR-0022): the same seven columns laid
out by board_engine.py and handed to the same converter, so the two paths cannot drift.
It needs no pull, and it has no stale window between a refresh and a re-sort, because
the order is computed from the applied sort rather than read off rows that have not moved.

Output lands in `data/exports/`, dated, beside the provider exports that fed the
board. Provider data in, provider data out — `data/` and `*.csv` are both
gitignored and the pre-commit hook blocks them. Never commit the output.
"""

import argparse
import csv
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import board_engine  # noqa: E402
import board_settings as BSET  # noqa: E402
import board_snapshot  # noqa: E402
import board_state  # noqa: E402

# `league.season` from config/league.yaml, by way of board_settings.py, which transcribes
# it (pyyaml is not a declared dependency) and is tested against the file.
SEASON = BSET.SEASON

# The repo root, from this file's location rather than the cwd, so the default
# output path is the same wherever the script is run from.
REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_DIR = REPO_ROOT / "data" / "exports"

# Q, teams x roster spots -- everyone who actually gets drafted. Nothing below
# this is worth importing: the values there are all sub-replacement and separated
# by less than the disagreement between the three projections.
DRAFTED_POOL = BSET.Q

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

# Column offsets within the fetched A4:G203 range: A=#, B=TIER, C=RND, D=Player,
# E=Tm, F=Pos, G=INJ. The board's own rank in column A is read for validation
# only -- the exported rank is re-derived from row order.
#
# These are positions in the D map (Build.gs), zero-indexed from the start of the
# fetched range. If a column is inserted ahead of Player, the pull silently
# yields team names in the name column, so the shape check is not optional.
COL_PLAYER = 3
COL_TEAM = 4
COL_POS = 5
RANGE_WIDTH = 7


# Where --local looks for the snapshot and the draft state. A module attribute so tests can
# point it at tmp_path.
LOCAL_ROOT = board_snapshot.ROOT


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
    # Sheet row numbers, so an error names a cell you can go and look at. Data starts at
    # row 4: row 1 is the control strip, 2 the block headers, 3 the column headers.
    for lineno, row in enumerate(rows, start=4):
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


def parse_sort(text):
    """`bmp-alt:DURH` -> {"source": "BMP-ALT", "kind": "durh"}, as board.py stores a sort."""
    source, sep, kind = text.partition(":")
    sources = {s.upper(): s for s in board_snapshot.SOURCES}
    if not sep or source.upper() not in sources or kind.lower() not in board_snapshot.KINDS:
        raise ExportError(
            f"--sort {text!r}: expected SOURCE:KIND, SOURCE one of "
            f"{', '.join(board_snapshot.SOURCES)} and KIND one of {', '.join(board_snapshot.KINDS)}"
        )
    return {"source": sources[source.upper()], "kind": kind.lower()}


def rows_from_local(snapshot, applied_sort):
    """The Draft Board range as the local engine lays it out, ready for `convert()`.

    Seven cells per row in the pull's order -- #, TIER, RND, Player, Tm, Pos, INJ -- so the
    local path and the sheet path meet at the same converter and cannot drift apart. Ticks
    play no part: rank and tier run over all 200 rows whatever is GONE, exactly as on the
    sheet, so an empty state is the whole input.
    """
    rows = board_engine.board_rows(
        snapshot, board_engine.empty_state(), snapshot["settings"], applied_sort
    )
    return [
        [str(r["rank"]), str(r["tier"]), f"R{r['rnd']}", r["name"], r["team"], r["pos"], r["inj"]]
        for r in sorted(rows, key=lambda r: r["rank"])
    ]


def local_sort(root, override):
    """--sort, else the live draft state's applied sort, else the board's default.

    The state file is read for its sort alone. It is what the draft is being run on, so an
    export taken mid-draft ranks the way the board in use does.
    """
    if override:
        return parse_sort(override)
    state_path = root / "draft-state.json"
    if state_path.exists():
        try:
            return dict(board_state.load(state_path)["applied_sort"])
        except board_state.StateError as exc:
            raise ExportError(f"{state_path}: {exc}") from exc
    return dict(board_engine.DEFAULT_SORT)


def local_rows(snapshot_path, sort_text, root):
    """Pin a snapshot, say which one on stderr, and lay out its board."""
    path = Path(snapshot_path) if snapshot_path else board_snapshot.newest(root)
    if path is None:
        raise ExportError(f"no local board under {root} -- run build_data.py first")
    try:
        snapshot = board_snapshot.load(path)
    except (OSError, board_snapshot.SnapshotError) as exc:
        raise ExportError(f"{path}: {exc}") from exc
    sort = local_sort(root, sort_text)
    meta = snapshot["meta"]
    print(
        f"local board {meta['generated']} digest {meta['digest'][:12]}, "
        f"sorted by {board_engine.sort_key(sort)}",
        file=sys.stderr,
    )
    return rows_from_local(snapshot, sort)


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
        help="raw Draft Board!A4:G203 CSV, or - for stdin (default: -)",
    )
    ap.add_argument(
        "--local",
        action="store_true",
        help="export the local board snapshot instead of a sheet pull (ignores GONE/MINE)",
    )
    ap.add_argument(
        "--snapshot",
        default=None,
        help="with --local: the snapshot to export (default: newest in data/draft-board/)",
    )
    ap.add_argument(
        "--sort",
        default=None,
        metavar="S:K",
        help="with --local: order by SOURCE:KIND, e.g. BMP-ALT:durh "
        "(default: the draft state's applied sort, else BMP:durh)",
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
    if args.local and args.src != "-":
        ap.error("--local reads the local snapshot; give it no CSV")
    if not args.local and (args.snapshot or args.sort):
        ap.error("--snapshot and --sort need --local")

    if args.local:
        rows = convert(local_rows(args.snapshot, args.sort, LOCAL_ROOT), limit=args.limit)
    else:
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
