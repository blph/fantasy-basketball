#!/usr/bin/env python3
"""Check the sheet's numbers against an independent implementation.

ADR-0008 claimed the board had been verified "against an independent Python
implementation" that was never committed, which made its central correctness
claim impossible to re-run. This is that implementation, kept.

Reads the gitignored `Data.gs`, recomputes everything from `valuation.py`, and
prints the pool constants and agreement counts. Paste the sheet's own Settings
values in with --sheet to diff them.

Output is deliberately aggregate: counts, constants and rank movements, never a
player row. This repository is public and the export is not ours to republish.

    python3 verify.py                          # recompute and print constants
    python3 verify.py --sheet sheet_vals.json  # diff against the live sheet
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gen_data import COLS  # noqa: E402  — the file that writes the order owns it
from valuation import (  # noqa: E402
    CATEGORIES,
    Player,
    adjusted_value,
    build_pool,
    converge_pool,
    g_total,
    punt_total,
    replacement,
    z_total,
)

# Defaults mirror the Settings tab. Q comes from config/league.yaml: 12 x 13.
DEFAULTS = {"teams": 12, "roster": 13, "min_gp": 25, "gp_divisor": 72, "punt_weight": 0.25}


def load_players(path: Path) -> list[Player]:
    """Parse `var PLAYERS = [...]` out of the generated Data.gs."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"var PLAYERS\s*=\s*(\[.*?\]);", text, re.S)
    if not m:
        raise SystemExit(f"{path}: no `var PLAYERS = [...]` found")
    # gen_data.py writes a trailing comma after the last row, which is legal in
    # JavaScript and not in JSON.
    rows = json.loads(re.sub(r",(\s*])", r"\1", m.group(1)))

    players = []
    for i, row in enumerate(rows):
        if len(row) != len(COLS):
            raise SystemExit(f"row {i}: {len(row)} columns, expected {len(COLS)}")
        d = dict(zip(COLS, row, strict=True))
        players.append(Player(
            seed=int(d["seed"]), name=d["name"], gp=float(d["gp"]),
            **{k: float(d[k]) for k in
               ("fgm", "fga", "fgp", "ftm", "fta", "ftp",
                "tpm", "pts", "reb", "ast", "stl", "blk", "to")},
        ))
    return players


def agree(a: float, b: float, places: int = 4) -> bool:
    return round(a, places) == round(b, places)


def constants(players: list[Player], pool, q: int) -> dict[str, float]:
    """The seven Settings values the sheet computes and this file re-derives."""
    return {
        "POOL_FG_PCT": pool.fg_pct, "POOL_FT_PCT": pool.ft_pct,
        "POOL_AVG_FGA": pool.avg_fga, "POOL_AVG_FTA": pool.avg_fta,
        "SD_FG_IMPACT": pool.sd_fg_impact, "SD_FT_IMPACT": pool.sd_ft_impact,
        "REPLACEMENT": replacement(players, pool, q),
    }


def explain_mismatch(players: list[Player], q: int, args, sheet: dict) -> str:
    """Name the likeliest cause before the operator concludes the board is wrong.

    A converged pool and a single-pass pool are different 156-player sets, so
    every constant differs between them. That is the *expected* reading when
    `Re-seed pool from current ranks` has not been run to convergence -- and it
    looks identical to a genuine break unless someone says so. Re-run against
    the other pool and, if that one agrees, report which.
    """
    other_converged = args.no_converge
    try:
        if other_converged:
            pool, _ = converge_pool(players, q, DEFAULTS["min_gp"], DEFAULTS["gp_divisor"])
        else:
            pool = build_pool(players, q, DEFAULTS["min_gp"])
    except ValueError as e:
        return f"  (could not build the comparison pool: {e})"

    other = constants(players, pool, q)
    still_bad = sum(
        1 for k, v in other.items() if k in sheet and not agree(v, float(sheet[k]))
    )
    label = "converged" if other_converged else "single-pass"
    ran = "single-pass" if other_converged else "converged"
    if still_bad:
        return (
            f"  Also checked a {label} pool: {still_bad} still disagree.\n"
            "  So this is not a convergence difference. Suspect the export or the sheet."
        )
    return (
        f"  But ALL of them agree against a {label} pool.\n"
        f"  This ran against a {ran} pool, so the board is very likely correct and its\n"
        "  pool simply has not settled. Run `Re-seed pool from current ranks` until\n"
        "  In Pool stops moving, then re-run this."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=str(Path(__file__).parent / "Data.gs"))
    ap.add_argument("--sheet", help="JSON of the sheet's Settings values, to diff against")
    ap.add_argument("--punt-weight", type=float, default=DEFAULTS["punt_weight"])
    ap.add_argument("--no-converge", action="store_true",
                    help="single pass from the provider seed, without iterating the pool")
    args = ap.parse_args()

    path = Path(args.data)
    if not path.exists():
        print(f"{path} not found. Generate it first:\n"
              f"  python3 gen_data.py data/player_data/player_data_MMDD.md", file=sys.stderr)
        return 2

    players = load_players(path)
    q = DEFAULTS["teams"] * DEFAULTS["roster"]

    # The sheet's numbers come from a converged pool -- `Re-seed pool from
    # current ranks` run until the membership stops moving. Comparing against a
    # single pass would report a disagreement that is not one.
    if args.no_converge:
        pool, passes = build_pool(players, q, DEFAULTS["min_gp"]), 1
    else:
        pool, passes = converge_pool(players, q, DEFAULTS["min_gp"], DEFAULTS["gp_divisor"])

    print(f"players parsed      {len(players)}")
    print(f"pool passes         {passes}"
          + ("  (single pass, --no-converge)" if args.no_converge else "  (settled)"))
    print(f"pool size (Q)       {q}  ({DEFAULTS['teams']} teams x {DEFAULTS['roster']} spots)")
    print(f"players in pool     {len(pool.members)}")
    shortfall = q - len(pool.members)
    why = (f"  ({shortfall} seeded below MIN_GP={DEFAULTS['min_gp']})"
           if shortfall else "  (exactly Q)")
    print(f"pool shortfall      {shortfall}{why}")

    print("\nPOOL CONSTANTS")
    consts = constants(players, pool, q)
    for k, v in consts.items():
        print(f"  {k:<16} {v:.6f}")

    # The board's own sanity checks, recomputed here so a failure shows up even
    # if nobody opens the sheet.
    print("\nSANITY")
    ztot_pool = sum(z_total(p, pool) for p in pool.members)
    print(f"  Z-total across pool   {ztot_pool:+.4f}  (should be ~0)")
    mean_pts = sum(p.pts for p in pool.members) / len(pool.members)
    gate = "SEASON TOTALS — STOP" if mean_pts > 100 else "per-game, safe"
    print(f"  per-game gate         {mean_pts:.2f} mean PTS — {gate}")

    # A hard punt must reproduce the plain G total once nothing is dropped, and
    # punt_weight=1 must reproduce it too. Both are cheap self-checks.
    probe = pool.members[0]
    assert agree(punt_total(probe, pool, [], 0.0), g_total(probe, pool), 9)
    assert agree(punt_total(probe, pool, ["ft"], 1.0), g_total(probe, pool), 9)
    print(f"  punt identities       ok (punt_weight={args.punt_weight})")

    # Adjusted Value must never promote a below-replacement player.
    repl = consts["REPLACEMENT"]
    inversions = 0
    for p in players:
        vor = g_total(p, pool) - repl
        if vor < 0 and adjusted_value(vor, p.gp, DEFAULTS["gp_divisor"]) > vor:
            inversions += 1
    print(f"  GP inversions         {inversions}  (must be 0)")

    if args.sheet:
        print("\nDIFF vs SHEET")
        sheet = json.loads(Path(args.sheet).read_text())
        bad = 0
        for k, v in consts.items():
            if k not in sheet:
                continue
            other = float(sheet[k])
            ok = agree(v, other)
            bad += 0 if ok else 1
            verdict = "agree" if ok else "DIFFER"
            print(f"  {k:<16} {verdict}  py={v:.6f} sheet={other:.6f}")
        if bad:
            print(f"\n{bad} constant(s) disagree to 4 decimal places.")
            print(explain_mismatch(players, q, args, sheet))
            return 1
        print("\nAll compared constants agree to 4 decimal places.")

    print(f"\ncategories valued: {', '.join(CATEGORIES)}")
    return 1 if inversions else 0


if __name__ == "__main__":
    raise SystemExit(main())
