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
    python3 verify.py --published bmp.tsv    # diff against Basketball Monster's own columns
    python3 verify.py --snapshot board.json  # a named local board instead of this build's own

A narrow pull (rank,name,value -- range A4:G203) checks the sorted value. A WIDE pull
(range A4:AA203) also checks all nine rank tags on all 200 rows, which is the only check
anywhere that looks at what the tags actually say. It exists because they were once wrong
on 1755 of 1800 rows while every offline gate was green: the harness compares formula
strings and never evaluates one, and this diff used to read three columns.

`--published` is the one check that compares the board to something outside it. Everything
else here verifies internal consistency, and the board was internally consistent while
every value was wrong by 0.008 and the dropped-category tag disagreed with Basketball
Monster on 15 of 234 players -- see docs/bugs/2026-09-01-durh-zsc-pool-constants.md. It
reads the scrape `calibrate_bbm.py` already saved, so the comparison is against the same
snapshot the constants were fitted to and no second browser trip is needed.

Output is deliberately aggregate: counts, constants and rank movements, never a player
row. This repository is public and the exports are not ours to republish.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bbm"))

import board_snapshot as BS  # noqa: E402
import board_values as BV  # noqa: E402
import sources as SRC  # noqa: E402
from bbm_reference import H2H_WEIGHTS  # noqa: E402

DEFAULT_DATA = Path(__file__).resolve().parent / "Data.gs"

# Column positions inside a VALUES row, as emitted by build_data.py.
V_DURH, V_DURH_RANK, V_DURH_DROP = 0, 1, 2
V_ZSH, V_ZSH_RANK, V_ZSH_DROP = 3, 4, 5
V_ZSC, V_ZSC_RANK = 6, 7
V_DH0, V_D0, V_Z0 = 8, 16, 24
V_WIDTH = 32

SOURCES = ("BMP", "HBP", "BMP-ALT")

#: Draft Board columns in a wide gviz pull, 0-based: nine identity columns, then the
#: value/tag pairs, three per source. Derived, not typed out, for the same reason Build.gs
#: derives its letters -- a shifted column must not quietly compare the wrong thing.
PULL_FIRST_VALUE = 9
#: INJ, 0-based, inside those nine identity columns: #, TIER, RND, Player, Tm, Pos, INJ.
PULL_INJ = 6
#: The injury tier's index in a PLAYERS row, and the closed set it may hold. The tiers are
#: Basketball Monster's own, so this set moves only when theirs does.
P_INJ = 20
INJ_TIERS = ("EXTREME", "HIGH", "MED", "LOW", "?")
KINDS = (("DURH", V_DURH, V_DURH_RANK, V_DURH_DROP),
         ("ZSH", V_ZSH, V_ZSH_RANK, V_ZSH_DROP),
         ("ZSC", V_ZSC, V_ZSC_RANK, None))
PULL_WIDTH = PULL_FIRST_VALUE + len(SOURCES) * len(KINDS) * 2

#: What our value columns are called on Basketball Monster's own page.
PUBLISHED = {"ZSC": ("Value", V_ZSC), "DURH": ("DUR H2H", V_DURH)}

#: Their DUR H2H cell is "1.09#13": the value, the rank, then the dropped category with no
#: separator. The category has to be anchored at the end or the rank swallows a leading 3.
PUB_TAG = re.compile(r"^(-?[\d.]+)#(\d+?)(pts|3|reb|ast|stl|blk|fg%|ft%|to)$")

#: Their abbreviation -> the label the board prints.
PUB_DROP = {"pts": "PTS", "3": "3PM", "reb": "REB", "ast": "AST",
            "stl": "STL", "blk": "BLK", "fg%": "FG%", "ft%": "FT%", "to": "TO"}

#: Tolerances, not measurements. Their columns are published to two decimals, so a perfect
#: reproduction still scatters by about 0.003; these sit above that and far below the 0.008
#: the pool-constant bug produced.
PUBLISHED_GATES = {"ZSC": (0.004, 0.020), "DURH": (0.006, 0.025)}

#: Two categories closer together than this cannot be told apart from their published
#: numbers: the columns are given to two decimals, and the two percentage categories carry
#: a residual around 0.017 that no amount of constant-fitting removes (doc III.1). A
#: dropped-category disagreement inside this band is a coin flip neither side can call, so
#: it is counted and reported but not treated as wrong.
DROP_RESOLUTION = 0.02

#: Share of matched rows that may disagree on the dropped category by MORE than the
#: resolution above. Those are real: the two categories were separable and we picked the
#: other one. A share rather than a count, because the number of near-ties scales with how
#: many rows are being compared.
MAX_MATERIAL_DROP_SHARE = 0.01


def _pull_col(src_i: int, kind_i: int) -> int:
    """The value column for a source/kind pair. The tag is the next one along."""
    return PULL_FIRST_VALUE + src_i * len(KINDS) * 2 + kind_i * 2


def load(path: Path) -> dict:
    """Parse the generated Data.gs. Trailing commas are legal in JS and not in JSON.

    `SHA256` is the hash of the text as read, for `check_snapshot`: the local board records
    the hash of the Data.gs written beside it, and only the text can answer that.
    """
    text = path.read_text(encoding="utf-8")
    out = {"SHA256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
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

    # The injury tier is a closed set. A blank would read as LOW, and anything else falls
    # through every conditional format and renders as plain text that means nothing.
    narrow = {len(p) for p in players if len(p) <= P_INJ}
    if narrow:
        fails.append(f"PLAYERS: rows {sorted(narrow)} wide carry no injury tier "
                     f"(expected at least {P_INJ + 1})")
    else:
        bad_inj = sorted({str(p[P_INJ]) for p in players} - set(INJ_TIERS))
        if bad_inj:
            fails.append(f"PLAYERS: injury tiers not in {list(INJ_TIERS)}: {bad_inj}")
        seen_inj = {str(p[P_INJ]) for p in players}
        print("  injury tiers: " + ", ".join(
            f"{sum(1 for p in players if str(p[P_INJ]) == t)} {t}"
            for t in INJ_TIERS if t in seen_inj))

    for build, rows in data["PUNT_VALUES"].items():
        if len(rows) != n:
            fails.append(f"punt {build}: {len(rows)} rows against {n} players")
    return fails


def check_snapshot(snapshot: dict, data: dict) -> list[str]:
    """The local board against the Data.gs written in the same run (ADR-0022).

    Exact equality, not a tolerance: both files are rendered from one set of rounded
    objects, so any difference at all means they are not from one build -- or one of them
    was edited afterwards. The digest checks say which: a META.digest that differs is two
    builds; a snapshot digest that does not recompute is an edited snapshot; a Data.gs hash
    that differs is an edited, or re-rendered, Data.gs.

    Failures name a board row and a field, never a player or a number. The repository is
    public and the exports are not ours to republish.
    """
    fails: list[str] = []
    meta, smeta = data["META"], snapshot.get("meta") or {}
    players, values, punts = data["PLAYERS"], data["VALUES"], data["PUNT_VALUES"]

    if snapshot.get("schema") != BS.SCHEMA:
        fails.append(f"snapshot schema is {snapshot.get('schema')!r}, expected {BS.SCHEMA}")
    if not meta.get("digest"):
        fails.append("Data.gs META carries no digest -- it predates the local board; "
                     "re-run build_data.py")
    elif meta["digest"] != smeta.get("digest"):
        fails.append("META.digest differs between Data.gs and the snapshot -- they are "
                     "not from the same build")
    if smeta.get("digest") != BS.digest(snapshot):
        fails.append("the snapshot's digest does not recompute -- it was changed after "
                     "build_data.py wrote it")
    if "SHA256" in data and data["SHA256"] != smeta.get("data_gs_sha256"):
        fails.append("Data.gs is not the text written beside this snapshot "
                     "(data_gs_sha256 differs)")

    for field, want in (("generated", meta.get("generated")), ("sources", meta.get("sources")),
                        ("board_rows", meta.get("boardRows")),
                        ("injuries", meta.get("injuries"))):
        if smeta.get(field) != want:
            fails.append(f"meta.{field} differs from Data.gs META")
    if snapshot.get("deriv") != data["DERIV"]:
        fails.append("deriv differs from Data.gs DERIV")
    settings = snapshot.get("settings") or {}
    for key in ("q", "teams", "roster"):
        if settings.get(key) != data["DERIV"].get(key):
            fails.append(f"settings.{key} differs from Data.gs DERIV.{key}")
    if snapshot.get("cat_labels") != list(BV.CAT_LABELS):
        fails.append("cat_labels are not the board's categories in CAT_LABELS order")
    if [b.get("key") for b in snapshot.get("punt_builds") or []] != list(punts):
        fails.append("punt_builds do not name Data.gs's PUNT_VALUES builds, in order")

    rows = snapshot.get("players") or []
    if len(rows) != len(players):
        fails.append(f"snapshot has {len(rows)} players against {len(players)} in Data.gs")
        return fails

    wrong: dict[str, int] = {}
    examples: list[str] = []

    def differ(i: int, field: str, got, want) -> None:
        if got != want:
            wrong[field] = wrong.get(field, 0) + 1
            if len(examples) < 5:
                examples.append(f"row {i} {field}: snapshot and Data.gs differ")

    width = len(BV.CAT_LABELS)
    for i, (p, raw) in enumerate(zip(rows, players, strict=True)):
        want = dict(zip(BS.PLAYER_FIELDS, raw, strict=False))
        try:
            differ(i, "row", p["row"], i)
            differ(i, "key", p["key"], SRC.normalise(want["name"]))
            for field in ("seed", "name", "team", "pos", "inj"):
                differ(i, field, p[field], want[field])
            # Blank in Data.gs, null here: a player the market has not priced.
            differ(i, "adp", p["adp"], None if want["adp"] == "" else want["adp"])
            for field in BS.HBP_RAW_FIELDS:
                differ(i, f"hbp_raw.{field}", p["hbp_raw"][field], want[field])
            for src in SOURCES:
                v, got = values[src][i], p["values"][src]
                for kind, (vcol, rcol, dcol) in (("durh", (V_DURH, V_DURH_RANK, V_DURH_DROP)),
                                                 ("zsh", (V_ZSH, V_ZSH_RANK, V_ZSH_DROP)),
                                                 ("zsc", (V_ZSC, V_ZSC_RANK, None))):
                    differ(i, f"{src}.{kind}.v", got[kind]["v"], v[vcol])
                    differ(i, f"{src}.{kind}.rank", got[kind]["rank"], v[rcol])
                    if dcol is not None:
                        differ(i, f"{src}.{kind}.drop", got[kind]["drop"], v[dcol])
                for block, start in (("dh", V_DH0), ("d", V_D0), ("z", V_Z0)):
                    differ(i, f"{src}.{block}", [got[block][c] for c in BV.CAT_LABELS],
                           v[start:start + width])
            for build, brows in punts.items():
                differ(i, f"punts.{build}",
                       [p["punts"][build]["score"], p["punts"][build]["rank"]], brows[i])
        except (KeyError, TypeError, IndexError) as exc:
            fails.append(f"row {i}: the snapshot row is malformed (missing {exc})")
            break

    for field in sorted(wrong):
        fails.append(f"{field}: {wrong[field]} of {len(rows)} rows differ from Data.gs")
    fails.extend(examples)
    return fails


def diff_sheet(data: dict, pull: Path, places: int = 3) -> list[str]:
    """Compare a gviz pull of the Draft Board against what Data.gs says.

    Only possible now that the sheet holds numbers rather than formulas, and it is the
    check that actually closes the loop: everything else verifies the file we generated,
    not the thing the board displays.

    A headerless CSV. Three columns (rank, player, value) checks the sorted value; a full
    A4:AA203 pull checks every value and every tag.

    Failures name the board row, never the player. The repository is public and the
    exports are not ours to republish.
    """
    rows = [r for r in csv.reader(pull.open(newline="", encoding="utf-8")) if any(r)]
    by_name = {p[1]: i for i, p in enumerate(data["PLAYERS"])}
    wide = bool(rows) and len(rows[0]) >= PULL_WIDTH
    # The board displays `places` decimals and rounds half AWAY from zero; Python rounds
    # half to even. Comparing round() to round() therefore fails on every value that lands
    # exactly on the boundary -- 1.1235 shown as 1.124, called 1.123 here. Compare the gap
    # instead: anything a correct display could produce is within half a displayed unit.
    tol = 0.5 * 10 ** -places + 1e-9
    fails, checked, tags_checked, inj_checked = [], 0, 0, 0
    wrong: dict[str, int] = {}
    examples: list[str] = []
    inj_wrong: list[str] = []

    for line, row in enumerate(rows):
        board_row = line + 4                      # data starts at sheet row 4
        if len(row) < 3:
            continue
        name = row[1 if not wide else 3].strip()
        if name not in by_name:
            fails.append(f"sheet row {board_row} holds a player that is not in Data.gs")
            continue
        i = by_name[name]

        if not wide:
            try:
                shown = float(row[2].replace("\u2212", "-").replace("+", ""))
            except ValueError:
                continue
            want = data["VALUES"]["BMP"][i][V_DURH]
            if abs(shown - want) > tol:
                fails.append(f"row {board_row}: sheet shows {shown}, Data.gs says {want}")
            checked += 1
            continue

        # The INJ cell is a formula into the Board, so this is the one check that proves
        # the mirror still resolves -- a clobbered formula shows a stale tier that looks
        # entirely ordinary, with no #REF! and no error anywhere.
        shown_inj = row[PULL_INJ].strip()
        want_inj = str(data["PLAYERS"][i][P_INJ])
        if shown_inj != want_inj:
            inj_wrong.append(f"row {board_row} INJ: sheet {shown_inj!r}, "
                             f"Data.gs {want_inj!r}")
        inj_checked += 1

        for s, src in enumerate(SOURCES):
            v = data["VALUES"][src][i]
            for k, (label, vcol, rcol, dcol) in enumerate(KINDS):
                col = _pull_col(s, k)
                try:
                    shown = float(row[col].replace("\u2212", "-").replace("+", ""))
                except ValueError:
                    continue
                if abs(shown - v[vcol]) > tol:
                    fails.append(f"row {board_row} {src} {label}: sheet shows {shown}, "
                                 f"Data.gs says {v[vcol]}")
                checked += 1

                # The tag. Both halves come from the same player's row on the same tab, so
                # a mismatch means the board is reading someone else -- which is invisible
                # in the value beside it and was, for a while, true of 195 rows in nine.
                got = row[col + 1].strip()
                want = f"#{v[rcol]} {v[dcol]}" if dcol is not None else f"#{v[rcol]}"
                if got != want:
                    key = f"{src} {label}"
                    wrong[key] = wrong.get(key, 0) + 1
                    if len(examples) < 5:
                        examples.append(f"row {board_row} {key}: shows '{got}', "
                                        f"Data.gs says '{want}'")
                tags_checked += 1

    if wide:
        # The board's own # column ranks the value it is sorted by. Exactly one of the nine
        # must therefore agree with it on every row -- and it is an equality, not an
        # approximation, because build_data.py ranks the value it rounds to.
        agree = []
        for src in SOURCES:
            for label, _v, rcol, _d in KINDS:
                if all(row[0].strip() == str(data["VALUES"][src][by_name[row[3].strip()]][rcol])
                       for row in rows if row[3].strip() in by_name):
                    agree.append(f"{src} {label}")
        if not agree:
            fails.append("the board's # column matches no source's rank on every row -- "
                         "it is sorted by something it does not display, or a rank and "
                         "the value beside it disagree")
        else:
            print(f"  # column agrees with {', '.join(agree)} on every row")

    if not checked:
        fails.append(f"{pull}: nothing comparable found -- is it a headerless pull of "
                     "rank,name,value (A4:G203) or the full board (A4:AA203)?")
    else:
        print(f"  compared {checked} values to within half of {places} decimal places")
    if wide:
        total = sum(wrong.values())
        print(f"  compared {tags_checked} rank tags: {total} wrong")
        if total:
            for key in sorted(wrong):
                fails.append(f"{key}: {wrong[key]} of {tags_checked // 9} tags wrong")
            fails.extend(examples)
        print(f"  compared {inj_checked} injury tiers: {len(inj_wrong)} wrong")
        if inj_wrong:
            fails.append(f"INJ: {len(inj_wrong)} of {inj_checked} tiers wrong -- the "
                         "Draft Board's mirror into the Board's injury column is stale "
                         "or has been overwritten with a literal")
            fails.extend(inj_wrong[:6])
    return fails


def diff_published(data: dict, tsv: Path, source: str) -> list[str]:
    """Compare our values against Basketball Monster's published columns.

    The board exists to reproduce their DURANT H2H (ADR-0015), so this is the check that
    tests the claim. It is also the only gate here that would have caught the pool-constant
    bug: every other check compares the board to the file that generated it.

    Joins on the normalised name, because Data.gs carries names and not vendor ids -- it is
    aggregate by design. Failures name a board row, never a player.
    """
    fails = []
    lines = [ln.split("\t") for ln in
             tsv.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return [f"{tsv}: empty"]
    idx = {h: i + 1 for i, h in enumerate(lines[0][1:])}
    needed = {name for name, _ in PUBLISHED.values()} | {"Name"}
    if not needed <= set(idx):
        return [f"{tsv}: missing {', '.join(sorted(needed - set(idx)))} -- is it a scrape "
                f"of the projections page?"]

    theirs = {}
    for cells in lines[1:]:
        if not cells[0].isdigit():
            continue
        theirs[SRC.normalise(cells[idx["Name"]])] = cells

    rows = data["VALUES"][source]
    names = [p[1] for p in data["PLAYERS"]]
    matched = 0
    stats = {k: [] for k in PUBLISHED}
    drop_wrong = drop_material = 0
    for i, name in enumerate(names):
        cells = theirs.get(SRC.normalise(name))
        if cells is None:
            continue
        matched += 1
        for kind, (col, vcol) in PUBLISHED.items():
            raw = cells[idx[col]]
            m = PUB_TAG.match(raw)
            try:
                stats[kind].append(abs(rows[i][vcol] - float(m.group(1) if m else raw)))
            except ValueError:
                continue
            if kind == "DURH" and m and PUB_DROP[m.group(3)] != rows[i][V_DURH_DROP]:
                drop_wrong += 1
                # Was the call actually resolvable, or were the two categories tied?
                dh = {c: rows[i][V_DH0 + j] for j, c in enumerate(BV.CAT_LABELS)}
                theirs_cat, ours_cat = PUB_DROP[m.group(3)], rows[i][V_DURH_DROP]
                if theirs_cat in dh and ours_cat in dh:
                    if abs(dh[ours_cat] - dh[theirs_cat]) > DROP_RESOLUTION:
                        drop_material += 1
                else:
                    drop_material += 1

    if not matched:
        return [f"{tsv}: no board player matched -- wrong source, or a bad scrape"]

    print(f"  {source} against Basketball Monster: {matched} of {len(names)} board rows matched")
    for kind, (mae_gate, max_gate) in PUBLISHED_GATES.items():
        d = stats[kind]
        if not d:
            fails.append(f"{source} {kind}: nothing comparable in the scrape")
            continue
        mae, worst = sum(d) / len(d), max(d)
        over = sum(1 for x in d if x > 0.01)
        print(f"    {kind:<5} MAE {mae:.4f}  max {worst:.4f}  "
              f"outside display rounding on {over} of {len(d)}")
        if mae > mae_gate:
            fails.append(f"{source} {kind}: MAE {mae:.4f} over the {mae_gate} tolerance")
        if worst > max_gate:
            fails.append(f"{source} {kind}: worst row off by {worst:.4f}, "
                         f"over the {max_gate} tolerance")
    allowed = MAX_MATERIAL_DROP_SHARE * matched
    print(f"    DURH dropped category disagrees on {drop_wrong} of {matched}, "
          f"{drop_material} of them by more than {DROP_RESOLUTION} "
          f"(the rest are ties neither side can call)")
    if drop_material > allowed:
        fails.append(f"{source} DURH: dropped category disagrees on {drop_material} rows "
                     f"where the two categories were separable, over the "
                     f"{allowed:.1f} allowed")
    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--sheet", type=Path,
                    help="a headerless gviz pull: rank,name,value (A4:G203), "
                         "or the full board (A4:AA203) to check all nine tags too")
    ap.add_argument("--published", type=Path, action="append", default=[],
                    help="a 'BBM Published - SOURCE - DATE.tsv' saved by calibrate_bbm.py; "
                         "repeatable, and the source is read from the filename")
    ap.add_argument("--snapshot", type=Path,
                    help="the local board to check against --data; defaults to the one this "
                         "Data.gs's build wrote under data/draft-board/, when present")
    args = ap.parse_args(argv)

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
    for tsv in args.published:
        m = re.match(r"BBM Published - (.+) - \d{4}-\d{2}-\d{2}\.tsv$", tsv.name)
        if not m:
            fails.append(f"{tsv.name}: cannot tell which source this is. Expected "
                         f"'BBM Published - SOURCE - YYYY-MM-DD.tsv'.")
            continue
        print(f"\nDIFF vs BASKETBALL MONSTER   {tsv.name}")
        fails += diff_published(data, tsv, m.group(1))

    if args.sheet:
        print("\nDIFF vs SHEET")
        fails += diff_sheet(data, args.sheet)

    # The local board this Data.gs's build wrote: the snapshot dated META.generated, not
    # simply the newest. Rebuilding an older date after a newer one is legitimate, and the
    # newest file would then be a different build, failing on a digest that was never
    # meant to match. Only for the default Data.gs, the one build_data.py pairs a board with.
    snap = args.snapshot
    if snap is None and args.data.resolve() == DEFAULT_DATA.resolve():
        own = BS.path_for(BS.ROOT, meta["generated"])
        if own.exists():
            snap = own
        else:
            print(f"\nLOCAL BOARD   none for {meta['generated']} under {BS.ROOT} -- skipped")
        latest = BS.newest(BS.ROOT)
        if latest is not None and latest != own:
            print(f"  note: a newer local board exists, {latest.name}")
    if snap is not None:
        print(f"\nLOCAL BOARD   {snap.name}")
        if not snap.exists():
            print(f"{snap} not found.", file=sys.stderr)
            return 2
        try:
            snapshot = json.loads(snap.read_text(encoding="utf-8"))
        except ValueError as exc:
            fails.append(f"{snap.name}: not JSON ({exc})")
        else:
            local_fails = check_snapshot(snapshot, data)
            if not local_fails:
                print(f"  every value, rank, tag and constant equals Data.gs; "
                      f"digest {meta['digest'][:12]}")
            fails += local_fails

    if fails:
        print(f"\n{len(fails)} FAILURE(S):")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("  all invariants hold" + ("; sheet agrees" if args.sheet else "")
          + ("; local board agrees" if snap is not None else ""))
    if set(H2H_WEIGHTS) - {"toV"} and deriv["punt_weight"]:
        print(f"\npunt weight {deriv['punt_weight']}, "
              f"{len(data['PUNT_VALUES'])} builds, BMP only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
