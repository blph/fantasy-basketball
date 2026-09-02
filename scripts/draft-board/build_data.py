#!/usr/bin/env python3
"""Turn three projection exports into Data.gs, the sheet's only input.

    python3 scripts/draft-board/build_data.py               # newest complete set
    python3 scripts/draft-board/build_data.py --date 2026-09-10
    python3 scripts/draft-board/build_data.py --dry-run     # report, write nothing

Every number the board ranks on is computed here and written to the sheet as a value. The
sheet keeps the formulas that have to react on the clock -- ranks, tiers, rounds, the
category profile, the tracker, the checkboxes -- and nothing else.

Output is aggregate by design: counts, constants and rank movements, never a player row.
This repository is public and the exports are not ours to republish.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bbm"))

import bbm_constants as BC  # noqa: E402
import board_values as BV  # noqa: E402
import sources as S  # noqa: E402
from bbm_reference import H2H_WEIGHTS, LAMBDAS_BBM_2026_27_JOSH, per_game  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "player_data"
DEFAULT_OUT = REPO / "scripts" / "draft-board" / "Data.gs"

TEAMS, ROSTER = 12, 13
Q = TEAMS * ROSTER

#: Decimal places every value is written to. `rerank` ranks the rounded value for the same
#: reason: the sheet ranks what it can see, so what it can see is what we rank.
VALUE_PLACES = 4

#: label -> filename stem. The board's display order, which is also SOURCES in Build.gs.
SOURCE_FILES = {
    "BMP": "BMP Projections",
    "HBP": "HBP Projections",
    "BMP-ALT": "BMP-ALT Projections",
}

#: The two Basketball Monster sources are standardised against constants recovered from
#: their own published columns rather than derived from a pool of ours, because no pool
#: reproduces both their means and their SDs (ADR-0021). The constants move whenever the
#: projections do, so they are part of the dated set rather than part of the source: a
#: build refuses to run without a same-dated fit for each vendor, and `find_set` will not
#: even resolve a date that has no fit. Hashtag has no published counterpart and keeps its
#: own derived pool.
CONSTANT_FILES = {
    "BMP": "BMP Constants",
    "BMP-ALT": "BMP-ALT Constants",
}

#: Everything a complete set needs, as {key: (stem, extension)}.
SET_FILES = ({lab: (stem, "csv") for lab, stem in SOURCE_FILES.items()}
             | {f"{lab}:const": (stem, "json") for lab, stem in CONSTANT_FILES.items()})

#: The nine builds the board ships (ADR-0010), as DURANT H2H category keys.
PUNTS = [
    ("pFt", ("ft%V",)), ("pFg", ("fg%V",)), ("pAst", ("aV",)),
    ("p3", ("3V",)), ("pBlk", ("bV",)),
    ("pFgReb", ("fg%V", "rV")), ("pAstStl", ("aV", "sV")),
    ("pPtsFt", ("pV", "ft%V")), ("pTriple", ("fg%V", "ft%V", "toV")),
]
PUNT_WEIGHT = 0.25

DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def find_set(date: str | None) -> tuple[str, dict[str, Path]]:
    """Locate one complete, same-dated set: three exports and the two vendor fits.

    Refuses a partial or mixed-date set unless forced. Scoring a fresh vendor file against
    a two-week-old Hashtag file produces a board that is wrong everywhere and looks wrong
    nowhere, which is the one failure mode worth a hard stop. A constants file paired with
    the wrong export is the same failure at one remove, so the fits are resolved here
    alongside the exports rather than checked afterwards.
    """
    available: dict[str, dict[str, Path]] = {}
    for key, (stem, ext) in SET_FILES.items():
        for path in DATA.glob(f"{stem} - *.{ext}"):
            m = DATE.search(path.name)
            if m:
                available.setdefault(m.group(1), {})[key] = path

    if not available:
        raise SystemExit(f"No projection exports found in {DATA}. Expected e.g. "
                         f"'{SOURCE_FILES['HBP']} - YYYY-MM-DD.csv'.")

    if date:
        found = available.get(date, {})
    else:
        complete = [d for d, s in sorted(available.items(), reverse=True)
                    if len(s) == len(SET_FILES)]
        if not complete:
            newest = max(available)
            missing = set(SET_FILES) - set(available[newest])
            raise SystemExit(
                f"No complete set. Newest is {newest}, missing: {', '.join(sorted(missing))}."
                f"\nDates present: {', '.join(sorted(available, reverse=True))}"
                + _calibrate_hint(missing, newest)
            )
        date, found = complete[0], available[complete[0]]

    missing = set(SET_FILES) - set(found)
    if missing:
        raise SystemExit(f"{date}: missing {', '.join(sorted(missing))}. "
                         f"All three sources are required; HBP supplies the board's rows."
                         + _calibrate_hint(missing, date))
    return date, found


def _calibrate_hint(missing: set[str], date: str) -> str:
    """Name the command that produces a missing fit, rather than just the filename."""
    labs = sorted(k.split(":")[0] for k in missing if k.endswith(":const"))
    if not labs:
        return ""
    return "\n\nRecover the missing constants first:\n" + "\n".join(
        f"  python3 scripts/draft-board/calibrate_bbm.py --source {lab} --date {date}"
        for lab in labs
    )


def load(paths: dict[str, Path]) -> tuple[list[dict], dict[str, dict], dict, dict]:
    board = S.load_board(paths["HBP"])
    vendors = {lab: S.load_vendor(paths[lab]) for lab in ("BMP", "BMP-ALT")}
    report = S.join(board, vendors)
    for row in board:
        for lab, players in vendors.items():
            if players[row["ids"][lab]]["games"] <= 0:
                raise S.SourceError(f"{lab}: {row['name']} is projected zero games")

    # Each fit is paired to its OWN source's export date, so a mixed-date set still has to
    # have been calibrated against the files it is being scored with.
    constants = {}
    for lab in CONSTANT_FILES:
        export_date = DATE.search(paths[lab].name).group(1)
        try:
            constants[lab] = BC.load(paths[f"{lab}:const"],
                                     source=lab, export_date=export_date)
        except BC.ConstantsError as exc:
            raise SystemExit(str(exc)) from None
    return board, vendors, constants, report


def rerank(rows: list[dict]) -> None:
    """Re-rank the board's rows against each other, in place.

    The pools are computed over each source's full universe -- ~510 players for the
    vendors -- which is what makes the values right. But a rank drawn from that universe
    is not comparable to anything on the board: it arrives with gaps, and a player the
    vendor rates 240th would carry a tag reading "#240" beside a board that stops at 200.

    Every consumer compares these ranks against the board's own rank column: the tag, the
    disagreement highlight, the punt gap. So the displayed rank is a rank among the 200
    players actually on the board. Ties break on the existing order, which is stable.

    Rank the value as it will be WRITTEN, not as it was computed. The sheet only ever sees
    `round(v, VALUE_PLACES)`, and its own `#` column ranks that rounded number; ranking full
    precision here made the two disagree by one wherever a rounding tie fell between two
    players -- 21 rows across the nine columns on the 2026-09-10 data, every one of them a
    rank sitting next to a value that did not imply it.
    """
    for field in ("durh", "zsh", "zsc"):
        order = sorted(range(len(rows)),
                       key=lambda i: (-round(rows[i][field], VALUE_PLACES), i))
        for place, i in enumerate(order, start=1):
            rows[i] = dict(rows[i], **{f"{field}_rank": place})


def score(board: list[dict], vendors: dict[str, dict],
          constants: dict[str, dict]) -> dict[str, dict]:
    """Score every source over its own universe, then narrow to the board's 200 rows.

    Each source's pool is drawn from that source's own full player list -- ~510 for the
    vendors, 200 for Hashtag, which publishes only its top 200. That asymmetry is real:
    Hashtag's pool is a truncated candidate set. It is reported on Settings rather than
    hidden, because it is the kind of thing that quietly explains a disagreement later.

    The vendors are standardised against Basketball Monster's own recovered constants and
    Hashtag against a pool of its own (ADR-0021), so the two are on different bases. That
    is reported on Settings too, and it is a second reason -- on top of the different
    pools -- that magnitudes are not comparable across sources. Ranks are.
    """
    out = {}

    hbp_rates = {r["key"]: dict(r["rates"]) for r in board}
    out["HBP"] = BV.score_source(hbp_rates, Q)
    out["HBP"]["lambdas"] = dict(LAMBDAS_BBM_2026_27_JOSH)
    out["HBP"]["by_row"] = [out["HBP"]["players"][r["key"]] for r in board]
    rerank(out["HBP"]["by_row"])

    for lab, players in vendors.items():
        rates = {pid: per_game(p) for pid, p in players.items()}
        rates = {k: v for k, v in rates.items() if v}
        c = constants[lab]
        res = BV.score_source(rates, Q, lambdas=c["lambdas"], params=c)
        res["lambdas"] = c["lambdas"]
        res["calibration"] = c["meta"]
        res["by_row"] = [res["players"][r["ids"][lab]] for r in board]
        rerank(res["by_row"])
        res["punts"] = {}
        if lab == "BMP":
            for key, drop in PUNTS:
                scores = BV.durant_h2h_punt(rates, Q, drop, PUNT_WEIGHT,
                                            lambdas=c["lambdas"], params=c["durant"])
                # Ranked among the board's 200, for the same reason as `rerank`.
                on_board = [scores[r["ids"][lab]] for r in board]
                order = sorted(range(len(on_board)), key=lambda i: (-on_board[i], i))
                place = {}
                for slot, i in enumerate(order, start=1):
                    place[i] = slot
                res["punts"][key] = [
                    (round(on_board[i], 4), place[i]) for i in range(len(board))
                ]
        out[lab] = res
    return out


def change_report(board: list[dict], scored: dict, previous: Path) -> list[str]:
    """What moved since the last generation. Names only, never a stat line."""
    lines = []
    prev_names, prev_ranks = _read_previous(previous)
    now = [r["name"] for r in board]

    if prev_names is None:
        lines.append("No previous Data.gs -- this is a first generation.")
    else:
        added = [n for n in now if n not in set(prev_names)]
        dropped = [n for n in prev_names if n not in set(now)]
        lines.append(f"Players added: {len(added)}" + (f" -- {', '.join(added)}" if added else ""))
        lines.append(f"Players dropped: {len(dropped)}"
                     + (f" -- {', '.join(dropped)}" if dropped else ""))
        if set(now) != set(prev_names) or now != prev_names:
            lines.append("Row order changed: the refresh will take the REORDER path "
                         "and re-key every hand edit by player name.")

    for lab in ("BMP", "HBP", "BMP-ALT"):
        rows = scored[lab]["by_row"]
        movers = 0
        if prev_ranks and lab in prev_ranks:
            old = prev_ranks[lab]
            for r, p in zip(board, rows, strict=True):
                if r["name"] in old and abs(old[r["name"]] - p["durh_rank"]) >= 25:
                    movers += 1
        top = sorted(range(len(rows)), key=lambda i: rows[i]["durh_rank"])[:50]
        lines.append(f"{lab}: DURH top-50 spans ranks "
                     f"{min(rows[i]['durh_rank'] for i in top)}-"
                     f"{max(rows[i]['durh_rank'] for i in top)}"
                     + (f", {movers} players moved 25+ places" if prev_ranks else ""))
    return lines


def _read_previous(path: Path):
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8")
    m = re.search(r"var PLAYERS\s*=\s*(\[.*?\]);", text, re.S)
    if not m:
        return None, None
    rows = json.loads(re.sub(r",(\s*])", r"\1", m.group(1)))
    names = [r[1] for r in rows]
    ranks = {}
    v = re.search(r"var VALUES\s*=\s*(\{.*?\});\n", text, re.S)
    if v:
        try:
            blocks = json.loads(re.sub(r",(\s*[\]}])", r"\1", v.group(1)))
            for lab, block in blocks.items():
                ranks[lab] = {names[i]: row[1] for i, row in enumerate(block) if i < len(names)}
        except (ValueError, IndexError):
            ranks = {}
    return names, ranks


def emit(board, scored, report, date, paths, mixed) -> str:
    """Render Data.gs. Row i means the same player in PLAYERS and in every VALUES block."""
    def j(o):
        return json.dumps(o, separators=(",", ":"))

    players = []
    for r in board:
        rt = r["rates"]
        fgp = rt["fg_made"] / rt["fg_att"] if rt["fg_att"] else 0.0
        ftp = rt["ft_made"] / rt["ft_att"] if rt["ft_att"] else 0.0
        players.append([
            r["seed"], r["name"], r["team"], r["pos"], r["adp"] if r["adp"] is not None else "",
            round(rt["games"]), round(rt["minutes"], 1),
            round(rt["fg_made"], 1), round(rt["fg_att"], 1), round(fgp, 3),
            round(rt["ft_made"], 1), round(rt["ft_att"], 1), round(ftp, 3),
            round(rt["threes"], 1), round(rt["points"], 1), round(rt["rebounds"], 1),
            round(rt["assists"], 1), round(rt["steals"], 1), round(rt["blocks"], 1),
            round(rt["turnovers"], 1),
        ])

    def label(cat):
        return BV.CAT_LABELS[BV.CAT_ORDER.index(cat)]

    values = {}
    for lab in ("BMP", "HBP", "BMP-ALT"):
        rows = []
        for p in scored[lab]["by_row"]:
            rows.append(
                [round(p["durh"], VALUE_PLACES), p["durh_rank"], label(p["durh_drop"]),
                 round(p["zsh"], VALUE_PLACES), p["zsh_rank"], label(p["zsh_drop"]),
                 round(p["zsc"], VALUE_PLACES), p["zsc_rank"]]
                + [round(p["dh"][c], VALUE_PLACES) for c in BV.CAT_ORDER]
                + [round(p["d"][c], VALUE_PLACES) for c in BV.CAT_ORDER]
                + [round(p["z"][c], VALUE_PLACES) for c in BV.CAT_ORDER]
            )
        values[lab] = rows

    ranked = sorted(scored["BMP"]["players"],
                    key=lambda k: scored["BMP"]["players"][k]["durh_rank"])[:Q]
    deriv = {
        "q": Q, "teams": TEAMS, "roster": ROSTER,
        "weights": {label(c): H2H_WEIGHTS[c] for c in BV.CAT_ORDER},
        # Per source. The vendors' lambdas are refitted against Basketball Monster's own
        # published columns on every refresh, so there is no single board-wide lambda any
        # more; Hashtag has nothing to refit against and keeps the module's seed.
        "lambdas": {lab: {label(c): round(scored[lab]["lambdas"][c], 6)
                          for c in BV.CAT_ORDER} for lab in values},
        "basis": {lab: scored[lab]["basis"] for lab in values},
        "calibration": {lab: scored[lab]["calibration"]
                        for lab in values if "calibration" in scored[lab]},
        "k_rosenof": {label(c): BV.K_ROSENOF[c] for c in BV.CAT_ORDER},
        "k_tracker": {label(c): round(v, 4) for c, v in BV.tracker_k().items()},
        "slopes": {label(c): v for c, v in
                   BV.durant_vs_z_slopes(scored["BMP"]["players"], ranked).items()},
        "band_calibration": BV.profile_calibration(scored["BMP"]["players"], ranked),
        "pools": {lab: scored[lab]["pools"] for lab in values},
        "universe": {lab: scored[lab]["universe"] for lab in values},
        "pool_overlap": {lab: scored[lab]["pool_overlap"] for lab in values},
        "punt_weight": PUNT_WEIGHT,
        "join": report,
    }

    punts = dict(scored["BMP"]["punts"])

    meta = {"generated": date, "mixedDates": mixed, "boardRows": len(board),
            "sources": {k: v.name for k, v in paths.items()}}

    head = (
        "// GENERATED by scripts/draft-board/build_data.py -- do not edit by hand.\n"
        "// Provider data: gitignored, never committed (ADR-0006).\n"
        f"// Projections dated {date}"
        + ("  *** MIXED DATES -- see META.mixedDates ***" if mixed else "")
        + "\n//\n"
        "// Row i is the same player in PLAYERS and in every VALUES block. That ordering is\n"
        "// the contract the whole sheet rests on; Build.gs never re-sorts either one.\n\n"
    )
    return (
        head
        + f"var META = {j(meta)};\n\n"
        + "// [seed, player, team, pos, adp, gp, mpg, fgm, fga, fgpct, ftm, fta, ftpct,\n"
          "//  tpm, pts, reb, ast, stl, blk, to]\n"
        + f"var PLAYERS = {j(players)};\n\n"
        + "// [durh, durhRank, durhDrop, zsh, zshRank, zshDrop, zsc, zscRank,\n"
          "//  dh x8 (weighted), d x8 (unweighted), z x8]   in CAT_LABELS order\n"
        + f"var VALUES = {j(values)};\n\n"
        + "// BMP only. Per build: [score, rank] per board row.\n"
        + f"var PUNT_VALUES = {j(punts)};\n\n"
        + f"var DERIV = {j(deriv)};\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="YYYY-MM-DD; defaults to the newest complete set")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true", help="report and write nothing")
    ap.add_argument("--allow-mixed-dates", action="store_true",
                    help="score sources carrying different dates (stamped into META)")
    args = ap.parse_args()

    date, paths = find_set(args.date)
    dates = {DATE.search(p.name).group(1) for p in paths.values()}
    mixed = len(dates) > 1
    if mixed and not args.allow_mixed_dates:
        raise SystemExit(f"Mixed dates {sorted(dates)}. Re-export so all three match, or pass "
                         "--allow-mixed-dates to score them anyway.")

    print(f"Projections dated {date}" + (f"  (MIXED: {sorted(dates)})" if mixed else ""))
    board, vendors, constants, report = load(paths)
    print(f"  board rows {len(board)}; " + "; ".join(f"{k} {v[0]}" for k, v in report.items()))
    for lab, c in constants.items():
        print(f"  {lab}: constants recovered from Basketball Monster on "
              f"{c['meta']['fitted_at']}, {c['meta']['players_fitted']} players")
        for w in c["warnings"]:
            print(f"    note: {w}")

    scored = score(board, vendors, constants)
    for lab in ("BMP", "HBP", "BMP-ALT"):
        s = scored[lab]
        print(f"  {lab}: universe {s['universe']}, {s['basis']} constants, ZSC/DURANT pool "
              f"overlap {s['pool_overlap']}/{Q}, pool GP min "
              f"{s['pools']['durant']['gp_min']:.0f}")

    print("\nChange report")
    for line in change_report(board, scored, args.out):
        print(f"  {line}")

    text = emit(board, scored, report, date, paths, mixed)
    if args.dry_run:
        print(f"\n--dry-run: nothing written ({len(text):,} bytes would go to {args.out}).")
        return 0
    args.out.write_text(text, encoding="utf-8")
    print(f"\nWrote {args.out} ({len(text):,} bytes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
