#!/usr/bin/env python3
"""Parse the Hashtag Basketball markdown dump into a Google Apps Script data file.

Handles the two quirks in the export: header rows repeated every ~13 players,
and an R# cell that sometimes carries a second number (the rank-movement
indicator) alongside the rank itself.

Emits Data.gs — an array of arrays, one per player, in Board column order.
Provider data. Never commit the output.

This is the repository's only reader of the provider export. `verify.py` and the
analysis scripts consume `parse` and `check` rather than re-implementing them: a
second parser that disagrees with this one produces two internally consistent
boards that differ, which is the hardest kind of wrong to see.

Importing this module must stay free of side effects. It previously read
`sys.argv` and wrote its output at import time, so `import gen_data` under pytest
parsed nothing and wrote a file named `-q`.

    python3 gen_data.py [export.md] [Data.gs]
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "data" / "player_data" / "player_data_0826.md"
DEFAULT_OUT = "Data.gs"

# Column order of a parsed row. The Board's columns A-D, AZ, F-T in sheet order;
# `verify.py` imports this rather than restating it.
COLS = ["seed", "name", "team", "pos", "adp", "gp", "mpg", "fgm", "fga", "fgp",
        "ftm", "fta", "ftp", "tpm", "pts", "reb", "ast", "stl", "blk", "to"]

# The integrity guards, by name, so a caller can say which one tripped.
CHECKS = ("contiguous", "duplicate", "unparsed")

PCT = re.compile(r"([\d.]+)\(([\d.]+)/([\d.]+)\)")


def is_separator(line: str) -> bool:
    body = line.strip().strip("|").replace("|", "").replace(" ", "")
    return bool(body) and set(body) <= set(":-")


def cell_text(cell: str) -> str:
    """Strip a markdown link wrapper, if there is one."""
    m = re.match(r"\[([^\]]+)\]\(", cell)
    return m.group(1).strip() if m else cell.strip()


def parse(path):
    players, problems = [], []
    for lineno, raw in enumerate(open(path, encoding="utf-8"), 1):
        if not raw.startswith("|"):
            continue
        if "PLAYER" in raw or is_separator(raw):
            continue  # repeated header / separator
        c = [x.strip() for x in raw.strip().strip("|").split("|")]
        if len(c) != 17:
            problems.append((lineno, f"expected 17 columns, got {len(c)}", c[:3]))
            continue

        rank_m = re.match(r"(\d+)", c[0])          # "18 38" -> 18
        fg, ft = PCT.fullmatch(c[7]), PCT.fullmatch(c[8])
        if not (rank_m and fg and ft):
            problems.append((lineno, "unparseable rank or pct", c[:3]))
            continue

        adp = c[2].strip()
        players.append([
            int(rank_m.group(1)),                  # seed rank
            cell_text(c[1]),                       # player
            c[4],                                  # team
            c[3],                                  # pos
            float(adp) if re.fullmatch(r"[\d.]+", adp) else "",
            float(c[5]), float(c[6]),              # gp, mpg
            float(fg.group(2)), float(fg.group(3)), float(fg.group(1)),   # fgm fga fg%
            float(ft.group(2)), float(ft.group(3)), float(ft.group(1)),   # ftm fta ft%
            float(c[9]), float(c[10]), float(c[11]), float(c[12]),        # 3pm pts reb ast
            float(c[13]), float(c[14]), float(c[15]),                     # stl blk to
        ])
    return players, problems


def check(players: list[list], problems: list[tuple] | None = None) -> list[str]:
    """Name every way this export would make a wrong board, rather than the first.

    A silently dropped or duplicated player shifts every seed rank below it, which
    moves the pool boundary, which moves all eight pool constants — and the board
    still computes. Callers that skip this get that failure with no symptom.

    Returns complaints; empty means clean. Each string starts with its CHECKS name.
    """
    complaints = []
    ranks = [p[0] for p in players]
    names = [p[1] for p in players]
    if ranks != list(range(1, len(players) + 1)):
        complaints.append(f"contiguous: seed ranks are not 1..{len(players)}")
    if len(set(names)) != len(names):
        dupes = sorted({n for n in names if names.count(n) > 1})
        complaints.append(f"duplicate: {len(dupes)} player name(s) appear more than once")
    if problems:
        complaints.append(f"unparsed: {len(problems)} row(s) — {problems[:3]}")
    return complaints


def load(path) -> list[list]:
    """Parse, sort by seed, and refuse to return anything that fails `check`."""
    players, problems = parse(path)
    players.sort(key=lambda p: p[0])
    complaints = check(players, problems)
    if complaints:
        raise SystemExit(f"{path}: " + "; ".join(complaints))
    return players


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    src = args[0] if args else DEFAULT_SRC
    out = args[1] if len(args) > 1 else DEFAULT_OUT

    players = load(src)
    with open(out, "w", encoding="utf-8") as f:
        f.write("// Generated from Hashtag Basketball export. Provider data - do not commit.\n")
        f.write(f"// {len(players)} players. Column order matches Board columns A-D, AZ, F-T.\n")
        f.write("// [rank, player, team, pos, adp, gp, mpg, fgm, fga, fgpct,\n")
        f.write("//  ftm, fta, ftpct, tpm, pts, reb, ast, stl, blk, to]\n")
        f.write("var PLAYERS = [\n")
        for p in players:
            f.write("  " + json.dumps(p) + ",\n")
        f.write("];\n")

    n_adp = sum(1 for p in players if p[4] != "")
    gp = [p[5] for p in players[:156]]
    print(f"wrote {out}: {len(players)} players, {n_adp} with ADP, {len(players) - n_adp} without")
    print(f"pool GP: min {min(gp):g} max {max(gp):g} mean {st.mean(gp):.1f}")
    print(f"pool avg PTS {st.mean(p[14] for p in players[:156]):.2f} (per-game gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
