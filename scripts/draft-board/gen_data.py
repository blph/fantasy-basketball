#!/usr/bin/env python3
"""Parse the Hashtag Basketball markdown dump into a Google Apps Script data file.

Handles the two quirks in the export: header rows repeated every ~13 players,
and an R# cell that sometimes carries a second number (the rank-movement
indicator) alongside the rank itself.

Emits Data.gs — an array of arrays, one per player, in Board column order.
Provider data. Never commit the output.
"""
import re
import sys
import json
import statistics as st

SRC = sys.argv[1] if len(sys.argv) > 1 else (
    "/Users/bryanpreza/Documents/Visual Studio Code/Fantasy Basketball/"
    "data/player_data/player_data_0826.md"
)
OUT = sys.argv[2] if len(sys.argv) > 2 else "Data.gs"

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


players, problems = parse(SRC)
players.sort(key=lambda p: p[0])

# Integrity checks — a silently dropped or duplicated player is a wrong board.
ranks = [p[0] for p in players]
names = [p[1] for p in players]
assert ranks == list(range(1, len(players) + 1)), "seed ranks are not contiguous"
assert len(set(names)) == len(names), "duplicate player names"
assert not problems, f"unparsed rows: {problems}"

with open(OUT, "w", encoding="utf-8") as f:
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
print(f"wrote {OUT}: {len(players)} players, {n_adp} with ADP, {len(players)-n_adp} without")
print(f"pool GP: min {min(gp):g} max {max(gp):g} mean {st.mean(gp):.1f}")
print(f"pool avg PTS {st.mean(p[14] for p in players[:156]):.2f} (per-game gate)")
