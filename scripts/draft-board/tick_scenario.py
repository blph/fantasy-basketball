#!/usr/bin/env python3
"""The tick scenario on a copy of the draft board, as one command.

    python3 scripts/draft-board/tick_scenario.py --sheet-id ID --allow-consent

Ticks drive most of what board_engine.py re-implements, and the owner's sheet cannot be used to
exercise them, so this copies the live sheet, drives the copy through `playwright-cli -s=fantasy
run-code`, and after every step downloads the copy (pull_sheet.pull) and runs the full
`verify.py --local` comparison in process. Every cell is checked at every step. The copy is
deleted at the end, pass or fail.

Steps: copy; untick anything inherited (Space, never Delete); a. MINE 8 then 14 (the tracker's
cap); b. GONE on ten spread rows, two of them MINE; c. one punted category, then two; d. a new
Sort by and Rebuild & re-sort (the copy's first script run, so Google asks to authorise it);
e. a hand value (GP Y-1) and two swapped Board names on clean rows, then Refresh data -- the
reordering path. Verify compares My GP on every row, so its pass is the C1 check; the hand value
must stay on its player. It goes in GP Y-1 because the Name Box cannot reach My GP on this sheet:
Board W and Z sit in hidden columns, and the Name Box lands on the next visible one.

`--allow-consent` is the owner's approval, given before the run, to click Allow on the copy's
authorisation screen. Without it the run stops at step d (exit 5). The scenario only runs when
`Build.gs` or `board_engine.py` changed since the last passing run (or with `--force`).

Output is one line per step. Never a sheet id, a title or a player name: the pulls are provider
data and stay under data/draft-board/pulls/, gitignored.
Exit: 0 pass or not needed, 1 a step failed, 2 usage, 5 consent not allowed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import board_snapshot as BS  # noqa: E402
import pull_sheet as PS  # noqa: E402
import verify_local as VL  # noqa: E402

WATCHED = ("scripts/draft-board/Build.gs", "scripts/draft-board/board_engine.py")
LAST = BS.ROOT / "pulls" / "last-scenario"
GONE_ROWS = (5, 9, 25, 40, 60, 80, 100, 130, 160, 190)  # 5 and 9 are MINE too
NEW_SORT = "HBP · DURH"
OVERRIDE = 50


class StepFailed(Exception):
    pass


class NeedsConsent(Exception):
    pass


# ------------------------------------------------------------------ pure helpers (tested)

def needed(repo: Path, last: Path) -> bool:
    """True unless a passing run is recorded and nothing it covers changed since."""
    if not last.exists():
        return True
    sha = last.read_text(encoding="utf-8").strip()
    diff = subprocess.run(["git", "diff", "--name-only", sha, "--", *WATCHED], cwd=repo,
                          capture_output=True, text=True)
    return diff.returncode != 0 or bool(diff.stdout.strip())


def counts(sheet: VL._Pull, layout: dict) -> dict:
    d, t = layout["tabs"]["Draft Board"]["columns"], layout["tabs"]["Category Tracker"]
    rows = range(layout["first_row"], layout["last_row"] + 1)
    ncat = len(layout["tabs"]["Settings"]["weights"])

    def ticked(sheet_name: str, col: int, row_numbers) -> int:
        return sum(VL._v(sheet.cell(sheet_name, col, r)) is True for r in row_numbers)

    cats = range(t["first_cat_row"], t["first_cat_row"] + ncat)
    return {"mine": ticked("Draft Board", d["mine"]["index"], rows),
            "gone": ticked("Draft Board", d["drafted"]["index"], rows),
            "punted": ticked("Category Tracker", t["columns"]["punted"], cats)}


def ticked_cells(sheet: VL._Pull, layout: dict) -> list[tuple[str, str]]:
    """(tab, A1) of every tick the copy inherited."""
    d, t = layout["tabs"]["Draft Board"]["columns"], layout["tabs"]["Category Tracker"]
    out = [("Draft Board", f"{d[k]['letter']}{r}")
           for k in ("drafted", "mine") for r in range(layout["first_row"], layout["last_row"] + 1)
           if VL._v(sheet.cell("Draft Board", d[k]["index"], r)) is True]
    col = t["columns"]["punted"]
    for i in range(len(layout["tabs"]["Settings"]["weights"])):
        if VL._v(sheet.cell("Category Tracker", col, t["first_cat_row"] + i)) is True:
            out.append(("Category Tracker", f"{PS.col_letter(col)}{t['first_cat_row'] + i}"))
    return out


def clean_rows(sheet: VL._Pull, layout: dict) -> tuple[int, str, int, str, int]:
    """Two Board rows to swap and one to override, none carrying a tick, note or hand value.

    The Draft Board points at fixed Board rows (I1), so a swapped name beside a tick would move
    the tick onto another player and verify, which reads ticks back as truth, would still pass.
    """
    first, last = layout["first_row"], layout["last_row"]
    d, b = layout["tabs"]["Draft Board"]["columns"], layout["tabs"]["Board"]["columns"]
    draft = lambda k, r: sheet.cell("Draft Board", d[k]["index"], r)  # noqa: E731
    board = lambda k, r: sheet.cell("Board", b[k]["index"], r)  # noqa: E731
    touched = set()
    for r in range(first, last + 1):
        gp, my = VL._num(draft("projGp", r)), VL._num(draft("myGp", r))
        if (VL._v(draft("drafted", r)) is True or VL._v(draft("mine", r)) is True
                or VL._text(draft("notes", r)) or VL._v(draft("xrank", r)) is not None
                or gp is None or my is None or abs(gp - my) > 1e-9):
            touched.add(VL._text(draft("player", r)))
    clean = [(r, VL._text(board("player", r))) for r in range(first, last + 1)
             if VL._text(board("player", r)) and VL._text(board("player", r)) not in touched
             and not VL._text(board("notes", r))
             and all(VL._v(board(k, r)) is None for k in ("gp1", "gp2", "gp3", "xrank"))]
    if len(clean) < 3:
        raise StepFailed("fewer than three clean Board rows")
    (ra, na), (rb, nb), (ro, _) = clean[-1], clean[-2], clean[-3]
    return ra, na, rb, nb, ro


# ------------------------------------------------------------------ the browser

class Browser:
    """Runs one Playwright snippet at a time against the copy's tab, found by its id."""

    def __init__(self, sheet_id: str):
        self.live_id, self.copy_id, self.title = sheet_id, None, None

    def run(self, body: str, **args) -> dict:
        code = ("async page => { const A = " + json.dumps(args) + ";"
                " const pages = page.context().pages();"
                " const copy = A.copy ? pages.find(p => p.url().includes(A.copy)) : null;"
                " const live = pages.find(p => p.url().includes(A.live));"
                " const nameBox = async (p, tab, a1) => {"
                "   await p.locator('.docs-sheet-tab-name',"
                "     {hasText: new RegExp('^' + tab + '$')}).first().click();"
                "   await p.waitForTimeout(800);"
                "   const nb = p.locator('#t-name-box'); await nb.click(); await nb.fill(a1);"
                "   await nb.press('Enter'); await p.waitForTimeout(500); };"
                " const menu = async (p, top, item) => {"
                "   await p.locator('#docs-menubar .menu-button',"
                "     {hasText: new RegExp('^' + top + '$')}).click();"
                "   await p.locator('.goog-menuitem:visible', {hasText: item}).first().click(); };"
                + body + " }")
        proc = subprocess.run(["playwright-cli", f"-s={PS.SESSION}", "run-code", code],
                              cwd=PS.REPO, capture_output=True, text=True)
        try:
            if proc.returncode:
                raise PS.PullError(proc.stderr.strip()[-300:] or proc.stdout.strip()[-300:])
            return PS.extract(proc.stdout)
        except PS.PullError as e:
            msg = str(e)
            typed = [x for v in args.values() if isinstance(v, list) for row in v
                     for x in (row if isinstance(row, list | tuple) else [row])
                     if isinstance(x, str) and len(x) > 2]
            for secret in filter(None, (self.live_id, self.copy_id, self.title, *typed)):
                msg = msg.replace(secret, "<redacted>")
            raise StepFailed(f"browser: {msg[-300:]}") from None

    def make_copy(self) -> None:
        got = self.run(
            "await menu(live, 'File', 'Make a copy');"
            " const btn = live.getByRole('button', {name: 'Make a copy'});"
            " const [np] = await Promise.all(["
            " page.context().waitForEvent('page', {timeout: 60000}),"
            " btn.click()]);"
            " await np.waitForURL(/\\/spreadsheets\\/d\\//, {timeout: 60000});"
            " await np.locator('#t-name-box').waitFor({timeout: 90000});"
            " return JSON.stringify({id: np.url().split('/d/')[1].split('/')[0],"
            " title: (await np.title()).replace(/ - Google Sheets$/, '')});",
            live=self.live_id)
        if not got.get("title", "").startswith("Copy of ") or got.get("id") == self.live_id:
            raise StepFailed("the new tab is not a copy")
        self.copy_id, self.title = got["id"], got["title"]

    def toggle(self, cells: list[tuple[str, str]]) -> None:
        """Space on each cell or range: ticks an unticked checkbox, unticks a ticked one."""
        self.run("for (const [tab, a1] of A.cells) { await nameBox(copy, tab, a1);"
                 " await copy.keyboard.press('Space'); await copy.waitForTimeout(200); }"
                 " return '{}';", copy=self.copy_id, live=self.live_id, cells=cells)

    def type_into(self, entries: list[tuple[str, str, str]]) -> None:
        self.run("for (const [tab, a1, text] of A.entries) { await nameBox(copy, tab, a1);"
                 " await copy.keyboard.type(text); await copy.keyboard.press('Enter');"
                 " await copy.waitForTimeout(300); } return '{}';",
                 copy=self.copy_id, live=self.live_id, entries=entries)

    def draft_menu(self, item: str, done: str, allow: bool) -> None:
        """Run a Draft Board menu item and wait for its completion toast, authorising once."""
        got = self.run(
            "const bar = () => copy.locator('#docs-menubar .menu-button',"
            " {hasText: /^Draft Board$/});"
            " try { await bar().waitFor({timeout: 60000}); } catch (e) {"
            "   await copy.reload(); await copy.locator('#t-name-box').waitFor({timeout: 90000});"
            "   await bar().waitFor({timeout: 90000}); }"
            " await menu(copy, 'Draft Board', A.item);"
            " const doneText = copy.getByText(new RegExp(A.done)).first();"
            " const auth = copy.getByText('Authorization required').first();"
            " const first = await Promise.race(["
            " doneText.waitFor({timeout: 300000}).then(() => 'done', () => 'timeout'),"
            " auth.waitFor({timeout: 300000}).then(() => 'auth', () => 'timeout')]);"
            " if (first === 'timeout') throw new Error('the menu action never finished');"
            " if (first === 'done') return JSON.stringify({ok: true});"
            " if (!A.allow) return JSON.stringify({consent: true});"
            " const [pop] = await Promise.all(["
            " page.context().waitForEvent('page', {timeout: 60000}),"
            " copy.getByRole('button', {name: /^(OK|Continue|Review permissions)$/})"
            ".first().click()]);"
            " await pop.waitForLoadState('domcontentloaded');"
            " const allow = pop.getByRole('button', {name: /^(Allow|Continue)$/}).first();"
            " const account = pop.locator('[data-identifier]').first();"
            " const advanced = pop.getByText('Advanced', {exact: true}).first();"
            " const seen = async (loc) => loc.isVisible().catch(() => false);"
            " for (let k = 0; k < 60 && !(await seen(allow)); k++) {"
            "   if (await seen(account)) { await account.click(); await pop.waitForTimeout(2000); }"
            "   else if (await seen(advanced)) { await advanced.click();"
            "     await pop.getByText(/^Go to .*\\(unsafe\\)$/).first().click();"
            "     await pop.waitForTimeout(2000); }"
            "   else await pop.waitForTimeout(1000); }"
            " const all = pop.getByText('Select all', {exact: true}).first();"
            " if (await seen(all)) { await all.click(); await pop.waitForTimeout(500); }"
            " await allow.click({timeout: 30000});"
            " await pop.waitForEvent('close', {timeout: 60000}).catch(() => {});"
            " await doneText.waitFor({timeout: 300000});"
            " return JSON.stringify({ok: true, authorised: true});",
            copy=self.copy_id, live=self.live_id, item=item, done=done, allow=allow)
        if got.get("consent"):
            raise NeedsConsent()

    def delete_copy(self) -> None:
        """Trash the copy, then Delete forever on that one id in Drive's Trash, proving each stage
        from the file's own page. By id, never by title: an older copy can share the title."""
        got = self.run(
            "for (const p of page.context().pages()) if (p.url().includes(A.copy)) await p.close();"
            " const edit = 'https://docs.google.com/spreadsheets/d/' + A.copy + '/edit';"
            " const state = async () => { const c = await page.context().newPage();"
            "   await c.goto(edit); await c.waitForTimeout(8000);"
            "   const trashed = await c.getByText('File is in trash').count();"
            "   const opens = await c.locator('#t-name-box').count();"
            "   return {c, trashed, opens}; };"
            " let s = await state();"
            " for (let k = 0; k < 3 && s.opens && !s.trashed; k++) {"
            "   await s.c.keyboard.press('Escape');"
            "   await menu(s.c, 'File', /Move to (trash|bin)/); await s.c.waitForTimeout(2500);"
            "   const ok = s.c.getByRole('button', {name: /^Move to (trash|bin)$/});"
            "   if (await ok.count()) await ok.first().click();"
            "   await s.c.waitForTimeout(5000); await s.c.close(); s = await state(); }"
            " await s.c.close();"
            " const t = await page.context().newPage();"
            " for (let k = 0; k < 2 && s.opens; k++) {"
            "   await t.goto('https://drive.google.com/drive/trash');"
            "   const row = t.locator('[data-id=\"' + A.copy + '\"]').first();"
            "   for (let w = 0; w < 18 && !(await row.count()); w++) {"
            "     await t.waitForTimeout(10000); if (!(await row.count())) await t.reload(); }"
            "   if (await row.count()) { await row.click({button: 'right'});"
            "     await t.getByRole('menuitem', {name: /^Delete forever$/}).first().click();"
            "     await t.waitForTimeout(1500);"
            "     const b = t.getByRole('button', {name: /^Delete forever$/});"
            "     if (await b.count()) await b.first().click();"
            "     await t.waitForTimeout(5000); }"
            "   s = await state(); await s.c.close(); }"
            " await t.close();"
            " return JSON.stringify({trashed: s.trashed, opens: s.opens});",
            copy=self.copy_id, live=self.live_id)
        if got.get("opens") or got.get("trashed"):
            raise StepFailed(f"the copy still exists after deletion ({got})")


# ------------------------------------------------------------------ the scenario

class Scenario:
    def __init__(self, browser: Browser, layout: dict, snapshot: dict):
        self.b, self.layout, self.snapshot = browser, layout, snapshot
        self.sheet: VL._Pull | None = None

    def check(self, step: str, expect: dict | None = None, tries: int = 6,
              verify: bool = True) -> VL._Pull:
        """Pull and verify; retry while the copy has not saved the expected counts yet."""
        out: dict = {}
        got: dict = {}
        started = time.monotonic()
        for attempt in range(tries):
            started = time.monotonic()
            _, out = PS.pull(self.b.copy_id, "copy", self.layout)
            sheet = VL._Pull(out)
            got = counts(sheet, self.layout)
            if expect is None or all(got[k] == v for k, v in expect.items()):
                break
            if attempt == tries - 1:
                raise StepFailed(f"step {step}: counts {got}, expected {expect} -- "
                                 "a checkbox did not toggle (is its checkbox rule missing?)")
            time.sleep(1.5)
        # Mid-step e the Board's names are swapped on purpose, which the comparable check
        # refuses by design; that pull only proves the edits landed.
        code, lines = VL.diff_local(self.snapshot, out, self.layout) if verify else (0, [])
        print(f"step {step:<10} mine={got['mine']:<3} gone={got['gone']:<3} "
              f"punted={got['punted']}  pull {time.monotonic() - started:.1f}s  verify exit {code}",
              flush=True)
        if code != 0:
            raise StepFailed("\n".join(f"  {ln}" for ln in lines if not ln.startswith("ok"))[:1500])
        self.sheet = sheet
        return sheet

    def run(self, allow: bool) -> None:
        L, d = self.layout, self.layout["tabs"]["Draft Board"]["columns"]
        t = L["tabs"]["Category Tracker"]
        punt = PS.col_letter(t["columns"]["punted"])
        first = L["first_row"]

        sheet = self.check("copy")
        inherited = ticked_cells(sheet, L)
        if inherited:
            self.b.toggle(inherited)
        self.check("cleared", {"mine": 0, "gone": 0, "punted": 0})

        mine = d["mine"]["letter"]
        self.b.toggle([("Draft Board", f"{mine}{first}:{mine}{first + 7}")])
        self.check("a mine 8", {"mine": 8})
        self.b.toggle([("Draft Board", f"{mine}{first + 8}:{mine}{first + 13}")])
        self.check("a mine 14", {"mine": 14})

        self.b.toggle([("Draft Board", f"{d['drafted']['letter']}{r}") for r in GONE_ROWS])
        self.check("b gone 10", {"gone": 10, "mine": 14})

        self.b.toggle([("Category Tracker", f"{punt}{t['first_cat_row']}")])
        self.check("c punt 1", {"punted": 1})
        self.b.toggle([("Category Tracker", f"{punt}{t['first_cat_row'] + 3}")])
        self.check("c punt 2", {"punted": 2})

        self.b.type_into([("Draft Board", f"{d['drafted']['letter']}1", NEW_SORT)])
        self.b.draft_menu("Rebuild & re-sort", "^Sorted by ", allow)
        sheet = self.check("d re-sort", {"mine": 14, "gone": 10, "punted": 2})

        ra, na, rb, nb, ro = clean_rows(sheet, L)
        b = L["tabs"]["Board"]["columns"]
        entries = [("Board", f"{b['player']['letter']}{ra}", nb),
                   ("Board", f"{b['player']['letter']}{rb}", na),
                   ("Board", f"{b['gp1']['letter']}{ro}", str(OVERRIDE))]
        self.b.type_into(entries)
        for attempt in (1, 2):
            typed = self.check("e typed", {"mine": 14, "gone": 10, "punted": 2}, verify=False)
            landed = (VL._text(typed.cell("Board", b["player"]["index"], ra)) == nb,
                      VL._text(typed.cell("Board", b["player"]["index"], rb)) == na,
                      VL._num(typed.cell("Board", b["gp1"]["index"], ro)) == OVERRIDE)
            if all(landed):
                break
            if attempt == 2:
                raise StepFailed(f"step e: the Board edits did not land before Refresh "
                                 f"(swap a, swap b, override) = {landed}")
            self.b.type_into([e for e, ok in zip(entries, landed, strict=True) if not ok])
        self.b.draft_menu("Refresh data", "Calculation tabs rewritten", allow)
        sheet = self.check("e refresh", {"mine": 14, "gone": 10, "punted": 2})
        if VL._num(sheet.cell("Board", b["gp1"]["index"], ro)) != OVERRIDE:
            raise StepFailed("step e: the hand value did not stay on its player's row")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet-id", help="the live sheet to copy instead of .env DRAFT_SHEET_ID")
    ap.add_argument("--allow-consent", action="store_true",
                    help="the owner approved clicking Allow on the copy's authorisation screen")
    ap.add_argument("--force", action="store_true", help="run even if nothing covered changed")
    args = ap.parse_args(argv)
    if not args.force and not needed(PS.REPO, LAST):
        print("scenario not needed: Build.gs and board_engine.py unchanged since the last pass")
        return 0
    try:
        sheet_id = args.sheet_id or PS.read_sheet_id(PS.ENV)
        layout = json.loads(PS.LAYOUT.read_text(encoding="utf-8"))
        snapshot = BS.load(BS.newest(BS.ROOT))
    except (ValueError, BS.SnapshotError, TypeError) as e:
        print(f"scenario: {e}", file=sys.stderr)
        return 2

    started, browser = time.monotonic(), Browser(sheet_id)
    code = 0
    try:
        browser.make_copy()
        Scenario(browser, layout, snapshot).run(args.allow_consent)
    except NeedsConsent:
        print("scenario stopped at step d: needs --allow-consent (ask the owner first)")
        code = 5
    except (StepFailed, PS.PullError) as e:
        print(f"scenario FAILED: {e}".replace(sheet_id, "<sheet id>"))
        code = 1
    finally:
        if browser.copy_id:
            for attempt in (1, 2):
                try:
                    browser.delete_copy()
                    break
                except StepFailed as e:
                    if attempt == 2:
                        print(f"copy NOT deleted: {e} -- delete it by hand before anything else")
                        code = code or 1
    if code == 0:
        LAST.parent.mkdir(parents=True, exist_ok=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PS.REPO, capture_output=True,
                              text=True).stdout.strip()
        LAST.write_text(head + "\n", encoding="utf-8")
        print(f"scenario ok: every step verify exit 0, hand value kept, copy deleted, "
              f"{time.monotonic() - started:.0f}s")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
