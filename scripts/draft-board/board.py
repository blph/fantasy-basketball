#!/usr/bin/env python3
"""The local draft board, for agents: one call per question, compact output, pinned state.

    python3 scripts/draft-board/board.py new
    python3 scripts/draft-board/board.py board --available --top 20
    python3 scripts/draft-board/board.py mine "Player Name" --pick 7 --show board,tracker
    python3 scripts/draft-board/board.py player "Name" "Other Name" --full

Reads the snapshot `build_data.py` writes beside `Data.gs` and never the sheet. Every
number is the engine's (`board_engine.py`), which mirrors the sheet's draft-day formulas;
this file only resolves names, keeps the draft state and prints.

The draft state is pinned to one snapshot by date and digest. A rebuilt or missing
snapshot stops every command with exit 4 rather than letting ticks land on a board they
were not made against. `rebase` moves the pin -- after `verify.py --local` passes, and
never during a live draft.

Exit codes: 0 ok, 2 usage, 3 name resolution, 4 integrity.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import board_engine as E  # noqa: E402
import board_names as N  # noqa: E402
import board_snapshot as BS  # noqa: E402
import board_state as ST  # noqa: E402

DEFAULT_ROOT = BS.ROOT
EXIT_OK, EXIT_USAGE, EXIT_NAME, EXIT_INTEGRITY = 0, 2, 3, 4
STATE_NAME = "draft-state.json"

#: The categories a tracker row exists for. Turnovers are weighted zero in DURANT H2H and
#: have no row, so there is nothing to concede.
CAT_LABELS = ("FG%", "FT%", "3PM", "PTS", "REB", "AST", "STL", "BLK")

DEFAULT_FIELDS = ("rank", "tier", "rnd", "name", "team", "pos", "inj", "value", "gap",
                  "left_at_pos")
COMPACT_FIELDS = ("rank", "tier", "rnd", "name", "team", "pos", "inj", "value", "gone",
                  "mine", "pick", "adp", "gap", "gp", "my_gp", "gp_flag", "gp_warn", "xrank",
                  "in_pool", "strengths", "weaknesses", "best_build", "notes")
ECHO = ("cmd", "name", "team", "rank", "gone", "mine", "pick", "detail")
KV = ("field", "value")

#: `--show board` prints the available board, this deep. The whole 200 rows after every
#: pick is the Playwright cost this CLI exists to avoid.
SHOW_TOP = 30

#: Hand-column command -> state field.
HAND = {"gp": "my_gp", "xrank": "xrank", "gp1": "gp1", "gp2": "gp2", "gp3": "gp3"}

#: Command -> runner for everything that is not a read. Each block of runners below
#: registers itself, so the parser can declare the whole CLI surface in one place.
RUNNERS: dict = {}

EPILOG = (
    "Output is provider data: it prints player rows from the local board. Never paste it "
    "into docs/ or tests/, and never commit it; there is deliberately no option to write it "
    "to a file. Exit codes: 0 ok, 2 usage, 3 name resolution, 4 integrity."
)


class Fail(Exception):
    """Stop the command with an exit code and a one-line reason on stderr."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def warn(message: str) -> None:
    print(f"board: {message}", file=sys.stderr)


# --- argument types ---------------------------------------------------------------------


def parse_sort(text: str) -> dict:
    """`bmp-alt:durh` in any case, or the sheet's own label `BMP-ALT · DURH`."""
    parts = [p.strip() for p in text.replace("·", ":").split(":")]
    if len(parts) == 2 and parts[0].upper() in BS.SOURCES and parts[1].lower() in BS.KINDS:
        return {"source": parts[0].upper(), "kind": parts[1].lower()}
    raise argparse.ArgumentTypeError(
        f"{text!r} is not SOURCE:KIND (SOURCE one of {', '.join(BS.SOURCES)}; "
        f"KIND one of {', '.join(BS.KINDS)})"
    )


def parse_cat(text: str) -> str:
    """`fg`, `fg%` or `FG%` -> `FG%`. Turnovers are refused: they have no tracker row."""
    token = text.strip().upper()
    if token in ("TO", "TOV", "TOS"):
        raise argparse.ArgumentTypeError(
            "TO cannot be conceded: turnovers are weighted zero and have no tracker row"
        )
    for cat in CAT_LABELS:
        if token in (cat, cat.rstrip("%")):
            return cat
    raise argparse.ArgumentTypeError(f"{text!r} is not one of {', '.join(CAT_LABELS)}")


def parse_show(text: str) -> list[str]:
    views = [v.strip().lower() for v in text.split(",") if v.strip()]
    bad = [v for v in views if v not in ("board", "tracker")]
    if bad or not views:
        raise argparse.ArgumentTypeError(f"--show takes board and/or tracker, not {text!r}")
    return views


def _int_at_least(low: int):
    def parse(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
        if value < low:
            raise argparse.ArgumentTypeError(f"{value} is below {low}")
        return value

    return parse


# --- output -----------------------------------------------------------------------------


def cell(value) -> str:
    """One TSV cell. Tabs and newlines are escaped, so a note can never split a row."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else ""
    if isinstance(value, float):
        return str(round(value, 4))
    return (str(value).replace("\\", "\\\\").replace("\t", "\\t")
            .replace("\n", "\\n").replace("\r", "\\r"))


def render(args, ctx: dict, sections: list[tuple[str, tuple, list[list]]]) -> None:
    """Print one context and every section, as TSV or as one JSON object."""
    if getattr(args, "json", False):
        payload: dict = {"context": ctx}
        for name, header, rows in sections:
            if header == KV:
                payload[name] = {r[0]: r[1] for r in rows}
            else:
                payload[name] = [dict(zip(header, r, strict=True)) for r in rows]
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    words = []
    for k, v in ctx.items():
        text = ("yes" if v else "no") if isinstance(v, bool) else cell(v)
        words.append(f"{k}={text.replace(' ', '_') or '-'}")
    print("# " + " ".join(words))
    for i, (name, header, rows) in enumerate(sections):
        if i:
            print()
            print(f"# {name}")
        print("\t".join(header))
        for row in rows:
            print("\t".join(cell(v) for v in row))


def context(snap: dict, state: dict, sort: dict, *, what_if: bool = False,
            pinned: bool = True) -> dict:
    players = state["players"].values()
    return {
        "sort": E.sort_key(sort), "what_if": what_if,
        "snapshot": snap["meta"]["generated"], "digest": snap["meta"]["digest"][:12],
        "state": "pinned" if pinned else "none",
        "mine": sum(1 for p in players if p.get("mine")),
        "gone": sum(1 for p in players if p.get("gone")),
        "offboard": len(state["offboard"]),
    }


# --- state and snapshot -----------------------------------------------------------------


def state_path(args, root: Path) -> Path:
    """The state file: `root/draft-state.json`, or `--state`, which must sit under root.

    A relative `--state` is taken under root, so a mock draft is `--state mock1.json`.
    """
    base = root.resolve()
    raw = getattr(args, "state", None)
    if raw is None:
        return base / STATE_NAME
    path = Path(raw).expanduser()
    path = (path if path.is_absolute() else base / path).resolve()
    if path == base or not path.is_relative_to(base):
        raise Fail(EXIT_USAGE, f"--state must be a file under {root}, not {raw}")
    if (BS.FILENAME.match(path.name) or path.name.endswith(".bak.json")
            or path.name.endswith(".lock")):
        raise Fail(EXIT_USAGE, f"--state must not name a snapshot, backup or lock file, "
                                f"not {raw}")
    return path


def load_snapshot(path: Path) -> dict:
    if not path.exists():
        raise Fail(EXIT_INTEGRITY, f"snapshot {path.name} is missing; rebuild it with "
                                   "build_data.py or restore it")
    return BS.load(path)


def open_pinned(root: Path, path: Path, *, required: bool) -> tuple[dict, dict, bool]:
    """(state, snapshot, pinned). Without a state file, reads see the newest snapshot unticked."""
    if not path.exists():
        if required:
            raise Fail(EXIT_INTEGRITY, f"no draft state at {path.name}; run `board.py new`")
        newest = BS.newest(root)
        if newest is None:
            raise Fail(EXIT_INTEGRITY, f"no snapshot under {root}; run build_data.py")
        snap = load_snapshot(newest)
        warn("no draft state: reading the newest snapshot with nothing ticked "
             "(`board.py new` starts one)")
        return ST.new_state(snap), snap, False
    state = ST.load(path)
    snap = load_snapshot(BS.path_for(root, state["snapshot"]["date"]))
    ST.check_pin(state, snap)
    return state, snap, True


def newer_snapshot(root: Path, snap: dict) -> str:
    dates = BS.list_dates(root)
    return dates[-1] if dates and dates[-1] > snap["meta"]["generated"] else ""


def pick_report(snap: dict, state: dict) -> tuple[list[int], dict[int, list[str]]]:
    """Pick numbers missing below the highest logged, and numbers logged more than once."""
    names = {p["key"]: p["name"] for p in snap["players"]}
    picks: dict[int, list[str]] = {}
    for key, entry in state["players"].items():
        if entry.get("pick") is not None:
            picks.setdefault(entry["pick"], []).append(entry.get("name") or names.get(key, key))
    for entry in state["offboard"]:
        if entry.get("pick") is not None:
            picks.setdefault(entry["pick"], []).append(entry["name"])
    if not picks:
        return [], {}
    gaps = [n for n in range(1, max(picks) + 1) if n not in picks]
    dups = {n: sorted(v) for n, v in sorted(picks.items()) if len(v) > 1}
    return gaps, dups


def _gaps_text(gaps: list[int]) -> str:
    return ",".join(str(n) for n in gaps)


def _dups_text(dups: dict[int, list[str]]) -> str:
    return "; ".join(f"{n}: {' / '.join(v)}" for n, v in dups.items())


# --- views ------------------------------------------------------------------------------


def field_value(row: dict, field: str, sort: dict, state: dict):
    if field == "value":
        return row["values"][E.sort_key(sort)]
    if field == "pick":
        return state["players"].get(row["key"], {}).get("pick")
    if field in row and not isinstance(row[field], dict):
        return row[field]
    if field in row["values"]:
        return row["values"][field]
    head, _, rest = field.partition(":")
    block = {"rank": "ranks", "tag": "tags", "disagree": "disagree"}.get(head)
    if block and rest in row[block]:
        return row[block][rest]
    raise Fail(EXIT_USAGE, f"unknown field {field!r}")


def board_section(snap, state, sort, *, available=False, mine=False, top=None, pos=None,
                  tier=None, fields=DEFAULT_FIELDS, name="board"):
    rows = E.board_rows(snap, state, snap["settings"], sort)
    for f in fields:
        field_value(rows[0], f, sort, state)   # an unknown field fails before any output
    picked = [r for r in rows
              if (not available or not r["gone"]) and (not mine or r["mine"])
              and (pos is None or pos.upper() in r["pos"].upper())
              and (tier is None or r["tier"] == tier)]
    if top is not None:
        picked = picked[:top]
    return (name, tuple(fields), [[field_value(r, f, sort, state) for f in fields]
                                  for r in picked])


def tracker_sections(snap, state, sort, ctx):
    t = E.tracker(snap, state, snap["settings"], sort)
    ctx.update({"players_ticked": t["n"], "benchmark": t["benchmark"], "cutoff": t["cutoff"],
                "offboard_uncounted": t["offboard_mine"]})
    if t["offboard_mine"]:
        warn(f"{t['offboard_mine']} of your picks are off-board and not counted by the tracker")
    head = ("cat", "my_team", "avg_team", "z", "win", "read", "conceded", "flag")
    cats = [[c[h] for h in head] for c in t["cats"]]
    roster = [[r["rank"], r["name"], r["pos"]] for r in t["roster"]]
    return [("tracker", head, cats), ("roster", ("rank", "name", "pos"), roster)]


def show_sections(args, snap, state, ctx):
    sections = []
    views = getattr(args, "show", None) or []
    if "board" in views:
        sections.append(board_section(snap, state, state["applied_sort"], available=True,
                                      top=SHOW_TOP))
    if "tracker" in views:
        sections.extend(tracker_sections(snap, state, state["applied_sort"], ctx))
    return sections


def resolve_all(snap: dict, names: list[str], *, write: bool, team: str | None) -> list[dict]:
    """Every name or nothing: one failure reports them all and exits 3."""
    found, errors = [], []
    for name in names:
        try:
            found.append(N.resolve(snap, name, write=write, team=team))
        except N.ResolveError as exc:
            errors.append(exc)
    if errors:
        _name_failure(errors, len(names), write)
    return found


def _name_failure(errors: list[N.ResolveError], total: int, write: bool):
    for exc in errors:
        warn(str(exc))
        if exc.suggestions:
            warn("  did you mean: " + "; ".join(exc.suggestions))
    raise Fail(EXIT_NAME, f"{len(errors)} of {total} name(s) unresolved; nothing was "
                          + ("written" if write else "printed"))


# --- reads ------------------------------------------------------------------------------


def cmd_status(args, root, path, snap, state, pinned):
    gaps, dups = pick_report(snap, state)
    players = state["players"].values()
    rows = [
        ["state", path.name if pinned else "none"],
        ["snapshot_date", snap["meta"]["generated"]],
        ["digest", snap["meta"]["digest"]],
        ["newer_snapshot", newer_snapshot(root, snap)],
        ["applied_sort", E.sort_key(state["applied_sort"])],
        ["mine", sum(1 for p in players if p.get("mine"))],
        ["gone", sum(1 for p in players if p.get("gone"))],
        ["offboard", len(state["offboard"])],
        ["offboard_mine", sum(1 for o in state["offboard"] if o.get("mine"))],
        ["conceded", ",".join(state["conceded"])],
        ["events", len(state["events"])],
        ["pick_gaps", _gaps_text(gaps)],
        ["pick_duplicates", _dups_text(dups)],
    ] + [[k, v] for k, v in snap["settings"].items()]
    return [("status", KV, rows)], context(snap, state, state["applied_sort"], pinned=pinned)


def cmd_board(args, root, path, snap, state, pinned):
    sort = args.sort or state["applied_sort"]
    fields = tuple(f.strip() for f in args.fields.split(",")) if args.fields else DEFAULT_FIELDS
    section = board_section(snap, state, sort, available=args.available, mine=args.mine,
                            top=args.top, pos=args.pos, tier=args.tier, fields=fields)
    ctx = context(snap, state, sort, what_if=args.sort is not None, pinned=pinned)
    return [section], ctx


def cmd_player(args, root, path, snap, state, pinned):
    sort = state["applied_sort"]
    found = resolve_all(snap, args.names, write=False, team=args.team)
    by_key = {r["key"]: r for r in E.board_rows(snap, state, snap["settings"], sort)}
    fields = list(COMPACT_FIELDS)
    if args.full:
        keys = [f"{s}:{k}" for s in BS.SOURCES for k in BS.KINDS]
        fields += [f for k in keys for f in (k, f"rank:{k}", f"tag:{k}", f"disagree:{k}")]
        fields += [f"dh:{c}" for c in snap["cat_labels"]] + [f"d:{c}" for c in snap["cat_labels"]]
        fields += [f for b in snap["punt_builds"] for f in (b["key"], f"rank:{b['key']}")]
    rows = []
    for p in found:
        row, out = by_key[p["key"]], []
        applied = p["values"][sort["source"]]
        for f in fields:
            head, _, rest = f.partition(":")
            if head in ("dh", "d") and rest in applied[head]:
                out.append(applied[head][rest])
            elif f in p["punts"]:
                out.append(p["punts"][f]["score"])
            elif head == "rank" and rest in p["punts"]:
                out.append(p["punts"][rest]["rank"])
            else:
                out.append(field_value(row, f, sort, state))
        rows.append(out)
    return [("player", tuple(fields), rows)], context(snap, state, sort, pinned=pinned)


def cmd_tracker(args, root, path, snap, state, pinned):
    ctx = context(snap, state, state["applied_sort"], pinned=pinned)
    return tracker_sections(snap, state, state["applied_sort"], ctx), ctx


def cmd_punts(args, root, path, snap, state, pinned):
    builds = snap["punt_builds"]
    if args.build:
        want = args.build.strip().lower()
        builds = [b for b in builds if want in (b["key"].lower(), b["label"].lower())]
        if not builds:
            raise Fail(EXIT_USAGE, f"unknown build {args.build!r}; one of "
                       + ", ".join(f"{b['key']} ({b['label']})" for b in snap["punt_builds"]))
    top = args.top or (40 if args.build else 10)
    data = E.punts(snap, top=top)
    head = ("build", "rank", "name", "score", "adp", "gap")
    rows = [[b["key"], r["rank"], r["name"], r["score"], r["adp"], r["gap"]]
            for b in builds for r in data[b["key"]][:top]]
    return [("punts", head, rows)], context(snap, state, state["applied_sort"], pinned=pinned)


def cmd_check(args, root, path, snap, state, pinned):
    c = E.checks(snap, state)
    gaps, dups = pick_report(snap, state)
    recomputed = BS.digest(snap) == snap["meta"]["digest"]
    failures = []
    for k in ("names_aligned", "rows_aligned"):
        if c[k] != "aligned":
            failures.append(f"{k} reads {c[k]!r}")
    if c["board_rows"] != len(snap["players"]) or c["board_rows"] != snap["meta"]["board_rows"]:
        failures.append(f"board_rows {c['board_rows']} != {len(snap['players'])} players")
    if not recomputed:
        failures.append("the snapshot digest does not recompute")
    rows = [[k, v] for k, v in c.items()] + [
        ["digest_recomputes", "yes" if recomputed else "no"],
        ["state", f"version {state['version']}, pinned" if pinned else "none"],
        ["offboard", len(state["offboard"])],
        ["pick_gaps", _gaps_text(gaps)],
        ["pick_duplicates", _dups_text(dups)],
    ]
    if dups:
        warn(f"pick number(s) logged twice: {_dups_text(dups)}")
    for f in failures:
        warn(f"check failed: {f}")
    ctx = context(snap, state, state["applied_sort"], pinned=pinned)
    return [("check", KV, rows)], ctx, (EXIT_INTEGRITY if failures else EXIT_OK)


READS = {"status": cmd_status, "board": cmd_board, "player": cmd_player,
         "tracker": cmd_tracker, "punts": cmd_punts, "check": cmd_check}


# --- writes -----------------------------------------------------------------------------


def _offboard_index(offboard: list[dict], name: str) -> int | None:
    key = N.key_of(name)
    for i, entry in enumerate(offboard):
        if N.key_of(entry["name"]) == key:
            return i
    return None


def apply_pick(args, snap, state):
    """`gone` and `mine`. Every name is resolved and every refusal found before any change."""
    if args.pick is not None and (args.undo or len(args.names) > 1):
        raise Fail(EXIT_USAGE, "--pick takes exactly one name and no --undo")
    targets, errors, seen = [], [], set()
    for name in args.names:
        try:
            player = N.resolve(snap, name, write=True, team=args.team)
            if args.offboard:
                warn(f"--offboard ignored for '{name}': it is on the board")
            target = ("board", player, player["key"])
        except N.ResolveError as exc:
            if not N.key_of(name):
                # No letters to match on at all: never a real off-board pick, on any
                # combination of --undo/--offboard, so it cannot fall through below.
                errors.append(exc)
                continue
            if args.undo:
                if _offboard_index(state["offboard"], name) is None:
                    errors.append(exc)
                    continue
            elif N.on_board(snap, name):
                errors.append(exc)
                continue
            elif N.near_match(snap, name) and not args.offboard:
                errors.append(N.ResolveError(
                    f"{exc}; pass --offboard if '{name}' really is off the board",
                    exc.suggestions))
                continue
            target = ("offboard", name, "offboard:" + N.key_of(name))
        if target[2] not in seen:
            seen.add(target[2])
            targets.append(target)
    if errors:
        _name_failure(errors, len(args.names), True)

    changes: dict = {}
    offboard = [dict(o) for o in state["offboard"]]
    refused, removed = [], set()
    for kind, target, _ in targets:
        if kind == "board":
            base = f"players.{target['key']}."
            mine = ST.get_path(state, base + "mine")
            if not args.undo:
                changes[base + "gone"] = True
                if args.cmd == "mine":
                    changes[base + "mine"] = True
                if args.pick is not None:
                    changes[base + "pick"] = args.pick
            elif args.cmd == "mine":
                changes[base + "mine"] = False
            elif mine and not args.force:
                refused.append(target["name"])
            else:
                # A forced `gone --undo` on a MINE player clears mine, gone and pick
                # together: MINE-without-GONE is never a state this CLI produces.
                changes[base + "gone"] = False
                changes[base + "pick"] = None
                if mine:
                    changes[base + "mine"] = False
            continue
        i = _offboard_index(offboard, target)
        if not args.undo:
            if i is None:
                offboard.append({"name": target, "pick": args.pick, "mine": args.cmd == "mine"})
                warn(f"'{target}' is not on the board: recorded off-board, "
                     "and the tracker does not count it")
            else:
                offboard[i]["mine"] = offboard[i]["mine"] or args.cmd == "mine"
                if args.pick is not None:
                    offboard[i]["pick"] = args.pick
        elif args.cmd == "mine":
            offboard[i]["mine"] = False
        elif offboard[i]["mine"] and not args.force:
            refused.append(target)
        else:
            removed.add(i)
    if refused:
        raise Fail(EXIT_USAGE, "refusing `gone --undo` on your own pick(s): "
                   + ", ".join(refused) + " -- `mine --undo` first, or pass --force")
    offboard = [o for i, o in enumerate(offboard) if i not in removed]
    if offboard != state["offboard"]:
        changes["offboard"] = offboard
    echo = [(kind, target) for kind, target, _ in targets]
    return changes, echo, ""


def apply_concede(args, snap, state):
    current = set(state["conceded"])
    wanted = current - set(args.cats) if args.undo else current | set(args.cats)
    conceded = [c for c in snap["cat_labels"] if c in wanted]
    return {"conceded": conceded}, [], ",".join(conceded)


def apply_sort(args, snap, state):
    return {"applied_sort": args.spec}, [], E.sort_key(args.spec)


def apply_note(args, snap, state):
    player = resolve_all(snap, [args.name], write=True, team=args.team)[0]
    text = " ".join(args.text)
    return {f"players.{player['key']}.notes": text}, [("board", player)], text


def apply_hand(args, snap, state):
    if args.clear == (args.value is not None):
        raise Fail(EXIT_USAGE, f"`{args.cmd}` takes a number or --clear, not both or neither")
    if args.cmd == "xrank" and args.value == 0:
        raise Fail(EXIT_USAGE, "xrank starts at 1")
    player = resolve_all(snap, [args.name], write=True, team=args.team)[0]
    value = None if args.clear else args.value
    detail = f"{args.cmd}=" + ("cleared" if value is None else str(value))
    return {f"players.{player['key']}.{HAND[args.cmd]}": value}, [("board", player)], detail


WRITES = {"gone": apply_pick, "mine": apply_pick, "concede": apply_concede, "sort": apply_sort,
          "note": apply_note, **dict.fromkeys(HAND, apply_hand)}


def run_write(args, argv, root, path):
    with ST.locked(path):
        state, snap, _ = open_pinned(root, path, required=True)
        changes, echo, detail = WRITES[args.cmd](args, snap, state)
        names = {p["key"]: p["name"] for p in snap["players"]}
        before = {p: ST.get_path(state, p) for p in changes}
        for p, value in changes.items():
            ST.set_path(state, p, value)
        for p in changes:
            if p.startswith("players."):
                key = p.split(".", 2)[1]
                if key in state["players"]:
                    state["players"][key]["name"] = names[key]
        after = {p: ST.get_path(state, p) for p in changes}
        if before == after:
            warn("no change")
        else:
            ST.record(state, args.cmd, argv, before, after)
            ST.save(path, state)
        pick = getattr(args, "pick", None)
        if pick is not None:
            _, dups = pick_report(snap, state)
            if len(dups.get(pick, [])) > 1:
                warn(f"pick {pick} is already recorded for another player")
    ranks = {r["key"]: r["rank"]
             for r in E.board_rows(snap, state, snap["settings"], state["applied_sort"])}
    rows = []
    for kind, target in echo:
        if kind == "board":
            base = f"players.{target['key']}."
            flags = [ST.get_path(state, base + f) for f in ("gone", "mine", "pick")]
            rows.append([args.cmd, target["name"], target["team"], ranks[target["key"]],
                         *flags, detail])
        else:
            i = _offboard_index(state["offboard"], target)
            o = state["offboard"][i] if i is not None else {"pick": None, "mine": False}
            rows.append([args.cmd, target, "", "off-board", i is not None, o["mine"],
                         o["pick"], detail])
    if not echo:
        rows.append([args.cmd, "", "", "", None, None, None, detail])
    ctx = context(snap, state, state["applied_sort"])
    return [("result", ECHO, rows)] + show_sections(args, snap, state, ctx), ctx


def run_undo(args, argv, root, path):
    with ST.locked(path):
        state, snap, _ = open_pinned(root, path, required=True)
        event = ST.undo(state)
        ST.save(path, state)
    detail = f"{event['cmd']} ({event['ts']}): " + " ".join(event["args"])
    ctx = context(snap, state, state["applied_sort"])
    rows = [["undo", "", "", "", None, None, None, detail]]
    return [("result", ECHO, rows)] + show_sections(args, snap, state, ctx), ctx


RUNNERS.update(dict.fromkeys(WRITES, run_write), undo=run_undo)


# --- new and rebase ---------------------------------------------------------------------


def _is_empty(state: dict) -> bool:
    return (not state["players"] and not state["conceded"] and not state["offboard"]
            and state["applied_sort"] == E.DEFAULT_SORT
            and all(e["cmd"] == "new" for e in state["events"]))


def run_new(args, argv, root, path):
    with ST.locked(path):
        newest = BS.newest(root)
        if newest is None:
            raise Fail(EXIT_INTEGRITY, f"no snapshot under {root}; run build_data.py")
        snap = BS.load(newest)
        if path.exists():
            try:
                empty = _is_empty(ST.load(path))
            except ST.StateError:
                if not args.force:
                    raise
                empty = False
            if not empty and not args.force:
                raise Fail(EXIT_USAGE, f"{path.name} already holds a draft; "
                                       "`new --force` backs it up and starts over")
            warn(f"backed up the old state to {ST.backup(path).name}")
        state = ST.new_state(snap)
        ST.record(state, "new", argv, {}, {"snapshot": state["snapshot"]})
        ST.save(path, state)
    detail = f"pinned {snap['meta']['generated']} {snap['meta']['digest'][:12]}"
    ctx = context(snap, state, state["applied_sort"])
    return [("result", ECHO, [["new", "", "", "", None, None, None, detail]])], ctx


def run_rebase(args, argv, root, path):
    """Move the pin to the newest snapshot. Deliberately skips the pin check: it is the fix."""
    head = ("change", "name", "detail")
    with ST.locked(path):
        if not path.exists():
            raise Fail(EXIT_INTEGRITY, f"no draft state at {path.name}; run `board.py new`")
        state = ST.load(path)
        newest = BS.newest(root)
        if newest is None:
            raise Fail(EXIT_INTEGRITY, f"no snapshot under {root}; run build_data.py")
        new = BS.load(newest)
        pin = dict(state["snapshot"])
        target = {"date": new["meta"]["generated"], "digest": new["meta"]["digest"]}
        if pin == target:
            ctx = context(new, state, state["applied_sort"])
            rows = [["unchanged", "", f"already pinned to {target['date']}"]]
            return [("rebase", head, rows)], ctx
        on_new = {p["key"]: p for p in new["players"]}
        lost = sorted(e.get("name") or k for k, e in state["players"].items()
                      if k not in on_new and e.get("mine"))
        if lost:
            raise Fail(EXIT_INTEGRITY, f"MINE player(s) not on the {target['date']} board: "
                       + ", ".join(lost) + "; a pick of yours is never moved off-board by a "
                       "rebase -- settle it by hand, then rebase")
        old = None
        try:
            candidate = BS.load(BS.path_for(root, pin["date"]))
            if candidate["meta"]["digest"] == pin["digest"]:
                old = candidate
        except (BS.SnapshotError, OSError):
            old = None
        bak = ST.backup(path)
        before = {"snapshot": pin, "offboard": [dict(o) for o in state["offboard"]]}
        after: dict = {}
        rows, reported = [], set()
        for key, entry in list(state["players"].items()):
            if key in on_new:
                continue
            name = entry.get("name") or key
            if entry.get("gone"):
                state["offboard"].append({"name": name, "pick": entry.get("pick"), "mine": False})
                rows.append(["dropped", name, "was GONE; moved to offboard"])
            else:
                rows.append(["dropped", name, "hand columns discarded"])
                warn(f"'{name}' left the board; its hand columns are discarded")
            blank = ST.defaults(key)
            for field, value in entry.items():
                if field != "name":
                    before[f"players.{key}.{field}"] = value
                    after[f"players.{key}.{field}"] = blank[field]
            del state["players"][key]
            reported.add(key)
        if old is None:
            warn("the pinned snapshot is missing or was rebuilt; added and moved players "
                 "cannot be reported")
        else:
            sort = state["applied_sort"]
            was = {old["players"][i]["key"]: n for n, i in enumerate(E.order(old, sort), 1)}
            now = {new["players"][i]["key"]: n for n, i in enumerate(E.order(new, sort), 1)}
            names = {p["key"]: p["name"] for p in old["players"] + new["players"]}
            for key in now:
                if key not in was:
                    rows.append(["added", names[key], f"rank {now[key]}"])
                elif was[key] != now[key]:
                    rows.append(["moved", names[key], f"{was[key]} -> {now[key]}"])
            for key in was:
                if key not in now and key not in reported:
                    rows.append(["dropped", names[key], ""])
        state["snapshot"] = target
        after.update({"snapshot": target, "offboard": [dict(o) for o in state["offboard"]]})
        ST.check_pin(state, new)
        ST.record(state, "rebase", argv, before, after)
        ST.save(path, state)
    rows.insert(0, ["pinned", "", f"{pin['date']} -> {target['date']}; backup {bak.name}"])
    return [("rebase", head, rows)], context(new, state, state["applied_sort"])


RUNNERS.update(new=run_new, rebase=run_rebase)


# --- parser -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    # SUPPRESS, so a global flag given before the command survives the subparser's parse
    # and the same flag may also be given after it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state", default=argparse.SUPPRESS,
                        help=f"draft state file under the board root (default {STATE_NAME}; "
                             "a relative path is taken under the root)")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="one JSON object instead of TSV")
    show = argparse.ArgumentParser(add_help=False)
    show.add_argument("--show", type=parse_show, default=[],
                      help=f"after the write, also print board (available, top {SHOW_TOP}) "
                           "and/or tracker, e.g. --show board,tracker")

    ap = argparse.ArgumentParser(prog="board.py", description=__doc__, epilog=EPILOG,
                                 parents=[common],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def add(name, help_text, *parents):
        return sub.add_parser(name, help=help_text, description=help_text, epilog=EPILOG,
                              parents=[common, *parents])

    add("status", "pin, newer snapshot, applied sort, counts, settings, pick gaps")
    p = add("board", "Draft Board rows in order")
    p.add_argument("--sort", type=parse_sort, help="what-if sort S:K; the state is not changed")
    p.add_argument("--available", action="store_true", help="only players not GONE")
    p.add_argument("--mine", action="store_true", help="only MINE players")
    p.add_argument("--top", type=_int_at_least(1), help="first N rows after filters")
    p.add_argument("--pos", help="position substring: G matches PG, SG and G")
    p.add_argument("--tier", type=_int_at_least(1))
    p.add_argument("--fields", help="comma-separated: row fields, value, pick, S:K, "
                                    "rank:S:K, tag:S:K, disagree:S:K")
    p = add("player", "one row per name; all names resolve or nothing prints")
    p.add_argument("names", nargs="+", metavar="NAME")
    p.add_argument("--full", action="store_true",
                   help="add all nine values, tags, disagreement, dh/d and punts")
    p.add_argument("--team", help="break a tie between candidates (either team spelling)")
    add("tracker", "category rows, players ticked, My roster, off-board count")
    p = add("punts", "punt-build rankings")
    p.add_argument("build", nargs="?", metavar="BUILD", help="key (pFt) or label (Punt FT%%)")
    p.add_argument("--top", type=_int_at_least(1),
                   help="rows per build (default 40 for one build, 10 for all)")
    add("check", "sanity checks and state integrity; the only read that exits non-zero")

    for name, text in (("gone", "tick GONE"), ("mine", "tick MINE and GONE")):
        p = add(name, text, show)
        p.add_argument("names", nargs="+", metavar="NAME")
        p.add_argument("--undo", action="store_true",
                       help="clear GONE" if name == "gone" else "clear MINE only")
        if name == "gone":
            p.add_argument("--force", action="store_true",
                           help="allow --undo on a MINE player")
        else:
            p.set_defaults(force=False)
        p.add_argument("--pick", type=_int_at_least(1), help="overall pick number (one name)")
        p.add_argument("--team", help="break a tie between candidates (either team spelling)")
        p.add_argument("--offboard", action="store_true",
                       help="file a name with a near board match off-board anyway")
    p = add("concede", "tick Punted on the tracker", show)
    p.add_argument("cats", nargs="+", type=parse_cat, metavar="CAT")
    p.add_argument("--undo", action="store_true")
    p = add("sort", "set the applied sort, e.g. bmp-alt:durh or 'BMP · DURH'", show)
    p.add_argument("spec", type=parse_sort, metavar="S:K")
    p = add("note", "set a player's note (empty text clears it)", show)
    p.add_argument("name", metavar="NAME")
    p.add_argument("text", nargs="+", metavar="TEXT")
    p.add_argument("--team")
    for name in HAND:
        p = add(name, f"set {HAND[name]}; --clear returns it to blank"
                + (" (My GP then equals projected GP)" if name == "gp" else ""), show)
        p.add_argument("name", metavar="NAME")
        p.add_argument("value", nargs="?", type=_int_at_least(0), metavar="N")
        p.add_argument("--clear", action="store_true")
        p.add_argument("--team")
    add("undo", "revert the last edit (never new or rebase)", show)
    p = add("new", "empty state pinned to the newest snapshot")
    p.add_argument("--force", action="store_true", help="back up and replace a non-empty state")
    add("rebase", "move the pin to the newest snapshot; never during a live draft, and only "
                  "after verify.py --local passes")
    return ap


def main(argv: list[str] | None = None, root: Path = DEFAULT_ROOT) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    root = Path(root)
    try:
        path = state_path(args, root)
        if args.cmd in READS:
            state, snap, pinned = open_pinned(root, path, required=False)
            newer = newer_snapshot(root, snap)
            if newer and args.cmd != "status":
                warn(f"note: snapshot {newer} is newer than the pinned one; rebase only after "
                     "verify.py --local passes, never mid-draft")
            sections, ctx, *code = READS[args.cmd](args, root, path, snap, state, pinned)
        else:
            sections, ctx, *code = RUNNERS[args.cmd](args, argv, root, path)
    except Fail as exc:
        warn(str(exc))
        return exc.code
    except ST.UndoError as exc:
        warn(str(exc))
        return EXIT_USAGE
    except (ST.StateError, BS.SnapshotError) as exc:
        warn(str(exc))
        return EXIT_INTEGRITY
    render(args, ctx, sections)
    return code[0] if code else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
