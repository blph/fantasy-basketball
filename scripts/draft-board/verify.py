#!/usr/bin/env python3
"""Check Data.gs, and optionally the live sheet, against a recomputation.

ADR-0008 claimed the board had been verified "against an independent Python
implementation" that was never committed, which made its central correctness claim
impossible to re-run. This is that check, kept, and moved onto the new method.

The board no longer computes its values in the sheet, so what needs verifying changed
shape. The questions now are: does Data.gs hold what it claims to hold, are the invariants
the sheet depends on actually true of it, and does the sheet still show what was written
to it.

    python3 verify.py                        # recompute and print constants
    python3 verify.py --sheet pull.csv       # diff against a gviz pull of the board

Output is deliberately aggregate: counts, constants and rank movements, never a player
row. This repository is public and the exports are not ours to republish.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bbm"))

import board_values as BV  # noqa: E402
from bbm_reference import H2H_WEIGHTS  # noqa: E402

DEFAULT_DATA = Path(__file__).resolve().parent / "Data.gs"

# Column positions inside a VALUES row, as emitted by build_data.py.
V_DURH, V_DURH_RANK, V_DURH_DROP = 0, 1, 2
V_ZSH, V_ZSH_RANK, V_ZSH_DROP = 3, 4, 5
V_ZSC, V_ZSC_RANK = 6, 7
V_DH0, V_D0, V_Z0 = 8, 16, 24
V_WIDTH = 32

SOURCES = ("BMP", "HBP", "BMP-ALT")


def load(path: Path) -> dict:
    """Parse the generated Data.gs. Trailing commas are legal in JS and not in JSON."""
    text = path.read_text(encoding="utf-8")
    out = {}
    for name in ("META", "PLAYERS", "VALUES", "PUNT_VALUES", "DERIV"):
        m = re.search(rf"var {name}\s*=\s*(.*?);\n", text, re.S)
        if not m:
            raise SystemExit(f"{path}: no `var {name} = ...` found")
        out[name] = json.loads(re.sub(r",(\s*[\]}])", r"\1", m.group(1)))
    return out


def check(data: dict) -> list[str]:
    """The invariants the sheet rests on. Returns a list of failures."""
    fails = []
    players, values, deriv = data["PLAYERS"], data["VALUES"], data["DERIV"]
    n = len(players)

    # Row i is the same player in PLAYERS and in every VALUES block. Every cross-sheet
    # reference on the Draft Board assumes it, and nothing in Sheets would notice a drift.
    for src in SOURCES:
        if src not in values:
            fails.append(f"VALUES is missing {src}")
            continue
        if len(values[src]) != n:
            fails.append(f"{src}: {len(values[src])} value rows against {n} players")
        widths = {len(r) for r in values[src]}
        if widths != {V_WIDTH}:
            fails.append(f"{src}: value rows are {sorted(widths)} wide, expected {V_WIDTH}")

    # Ranks must be a permutation of 1..n. A duplicate or a gap means two players sort
    # into one slot, and the board would show it as a tie that is not one.
    for src in SOURCES:
        for label, col in (("DURH", V_DURH_RANK), ("ZSH", V_ZSH_RANK), ("ZSC", V_ZSC_RANK)):
            ranks = sorted(r[col] for r in values[src])
            if ranks != list(range(1, n + 1)):
                fails.append(f"{src} {label}: ranks are not a permutation of 1..{n}")

    # The dropped category must be one the board actually displays, and never turnovers --
    # DURANT H2H prices those at zero, so it cannot drop them.
    for src in SOURCES:
        for label, col in (("DURH", V_DURH_DROP), ("ZSH", V_ZSH_DROP)):
            bad = {r[col] for r in values[src]} - set(BV.CAT_LABELS)
            if bad:
                fails.append(f"{src} {label}: dropped categories not on the board: {sorted(bad)}")

    # The weighted column is the unweighted one times its weight. This is the identity the
    # tracker's K = k / w correction rests on; if it fails, every win probability is wrong.
    for src in SOURCES:
        for i, cat in enumerate(BV.CAT_LABELS):
            w = deriv["weights"][cat]
            worst = max(abs(r[V_DH0 + i] - r[V_D0 + i] * w) for r in values[src])
            if worst > 5e-4:
                fails.append(f"{src} {cat}: weighted and unweighted values differ by {worst:.5f}")

    # K = k / w, exactly. Neither skipped nor applied twice.
    for cat in BV.CAT_LABELS:
        got = deriv["k_tracker"][cat] * deriv["weights"][cat]
        if abs(got - deriv["k_rosenof"][cat]) > 5e-4:
            fails.append(f"{cat}: K x w = {got:.4f}, but Rosenof's k is {deriv['k_rosenof'][cat]}")

    # A value sorted descending must have its rank ascending.
    for src in SOURCES:
        for label, vcol, rcol in (("DURH", V_DURH, V_DURH_RANK),
                                  ("ZSH", V_ZSH, V_ZSH_RANK),
                                  ("ZSC", V_ZSC, V_ZSC_RANK)):
            ordered = sorted(values[src], key=lambda r: r[rcol])
            if any(a[vcol] < b[vcol] - 1e-9 for a, b in zip(ordered, ordered[1:], strict=False)):
                fails.append(f"{src} {label}: rank order disagrees with value order")

    # ADP is blank or a number, never zero standing in for blank.
    if any(p[4] == 0 for p in players):
        fails.append("PLAYERS: an ADP is 0, which the board reads as 'first off the draft board'")

    for build, rows in data["PUNT_VALUES"].items():
        if len(rows) != n:
            fails.append(f"punt {build}: {len(rows)} rows against {n} players")
    return fails


def diff_sheet(data: dict, pull: Path, places: int = 3) -> list[str]:
    """Compare a gviz pull of the Draft Board against what Data.gs says.

    Only possible now that the sheet holds numbers rather than formulas, and it is the
    check that actually closes the loop: everything else verifies the file we generated,
    not the thing the board displays.

    Expects a headerless CSV of rank, player, and the value the board is sorted by.
    """
    rows = [r for r in csv.reader(pull.open(newline="", encoding="utf-8")) if any(r)]
    by_name = {p[1]: i for i, p in enumerate(data["PLAYERS"])}
    fails, checked = [], 0
    for row in rows:
        if len(row) < 3:
            continue
        name = row[1].strip()
        if name not in by_name:
            fails.append(f"sheet row '{name}' is not in Data.gs")
            continue
        try:
            shown = float(row[2].replace("−", "-").replace("+", ""))
        except ValueError:
            continue
        want = data["VALUES"]["BMP"][by_name[name]][V_DURH]
        if round(shown, places) != round(want, places):
            fails.append(f"{name}: sheet shows {shown}, Data.gs says {want}")
        checked += 1
    if not checked:
        fails.append(f"{pull}: nothing comparable found -- "
                     "is it a headerless rank,name,value pull?")
    else:
        print(f"  compared {checked} rows to {places} decimal places")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--sheet", type=Path, help="a gviz pull of the board: rank,name,value")
    args = ap.parse_args()

    if not args.data.exists():
        print(f"{args.data} not found. Generate it first:\n"
              f"  python3 scripts/draft-board/build_data.py", file=sys.stderr)
        return 2

    data = load(args.data)
    meta, deriv = data["META"], data["DERIV"]

    print(f"generated           {meta['generated']}"
          + ("   *** MIXED DATES ***" if meta.get("mixedDates") else ""))
    print(f"board rows          {len(data['PLAYERS'])}")
    print(f"pool size (Q)       {deriv['q']}  ({deriv['teams']} teams x {deriv['roster']} spots)")

    print("\nUNIVERSE AND POOL")
    for src in SOURCES:
        pool = deriv["pools"][src]["durant"]
        print(f"  {src:<8} universe {deriv['universe'][src]:>4}   "
              f"ZSC/DURANT overlap {deriv['pool_overlap'][src]:>3}/{deriv['q']}   "
              f"pool GP min {pool['gp_min']:>3.0f} median {pool['gp_median']:>3.0f}   "
              f"under 25 GP {pool['gp_under_25']}")
    print("  Hashtag publishes only its top 200, so its pool is drawn from a truncated")
    print("  candidate set. The vendors' pools are drawn from their full lists.")

    print("\nTRACKER CONSTANTS   K = k / w, exact")
    print(f"  {'cat':<5} {'k':>7} {'w':>6} {'K':>8} {'D-on-z slope':>13}")
    for cat in BV.CAT_LABELS:
        print(f"  {cat:<5} {deriv['k_rosenof'][cat]:>7.3f} {deriv['weights'][cat]:>6.2f} "
              f"{deriv['k_tracker'][cat]:>8.4f} {deriv['slopes'][cat]:>13.4f}")

    print("\nCATEGORY PROFILE BAND   on the unweighted DURANT basis")
    for band, stats in sorted(deriv["band_calibration"].items(), key=lambda kv: float(kv[0])):
        print(f"  {float(band):.2f}   {stats['flags_per_player']:.2f} flags/player, "
              f"{stats['pct_unlabelled']}% with no label")
    print("  ADR-0013 chose the current band at ~2.6 flags/player and ~9% unlabelled.")

    print("\nINVARIANTS")
    fails = check(data)
    if args.sheet:
        print("\nDIFF vs SHEET")
        fails += diff_sheet(data, args.sheet)

    if fails:
        print(f"\n{len(fails)} FAILURE(S):")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("  all invariants hold" + ("; sheet agrees" if args.sheet else ""))
    if set(H2H_WEIGHTS) - {"toV"} and deriv["punt_weight"]:
        print(f"\npunt weight {deriv['punt_weight']}, "
              f"{len(data['PUNT_VALUES'])} builds, BMP only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
