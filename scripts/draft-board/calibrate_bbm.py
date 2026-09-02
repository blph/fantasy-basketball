#!/usr/bin/env python3
"""Recover Basketball Monster's standardisation constants from their published columns.

    python3 scripts/draft-board/calibrate_bbm.py --source BMP --date 2026-09-10
    python3 scripts/draft-board/calibrate_bbm.py --source BMP-ALT --date 2026-09-10
    python3 scripts/draft-board/calibrate_bbm.py --source BMP --date 2026-09-10 --from-file

Their per-category values are z-scores, so they are linear in the stat and the constants
fall straight out of a regression -- fit their published `pV` against our own per-game
points and the slope is 1/sd, the intercept is -mean/sd. That is worth doing because we
cannot derive those constants ourselves: their means agree with a top-156 pool to about
half a percent, their SDs only to one to three, and searching every pool size from 60 to
509 finds the means wanting N around 156 while the SDs want anything from 85 to 318. No
pool fits both moments, and this reproduces using their own published stat lines, so it is
not our data (ADR-0021, reverse-engineering doc III.2).

Nothing here is a constant and nothing is written into source. The recovered numbers are a
property of the projection set they were fitted to, so they are refitted on every refresh
and written beside the export they belong to, paired by date.

The x side of every regression is OUR export, not the per-game columns on their page. That
is what makes the constants correct for the numbers the pipeline actually feeds them, and
it sidesteps their two-decimal display rounding entirely -- only the value columns are
scraped.

Standard library only (AGENTS.md: a runtime dependency needs an ADR). Every fit is a 2x2 or
3x3 normal-equation solve plus a bounded grid.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bbm"))

import bbm_constants as BC  # noqa: E402
import sources as S  # noqa: E402
from bbm_reference import (  # noqa: E402
    CATEGORIES,
    COUNTING,
    LAMBDAS_BBM_2026_27_JOSH,
    PERCENTAGE,
    build_durant_pool,
    build_pool,
    per_game,
    yeo_johnson,
)

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "player_data"

#: Our label -> (their ProjectionSourceControl value, their name for it).
SOURCES = {"BMP": ("17329", "Josh"), "BMP-ALT": ("1", "Bonus")}

PROJECTIONS_URL = "https://basketballmonster.com/projections.aspx"
SESSION = "fantasy"

#: Their column header for each category, per layer. DURANT prefixes a D.
PLAIN_COL = {c: c for c in CATEGORIES}
DURANT_COL = {c: "D" + c for c in CATEGORIES}

#: Pool size for the diagnostic comparison only -- teams x roster spots. It has no bearing
#: on the recovered constants, which is the whole point of recovering them.
Q = 156

#: Refuse to write a fit worse than this. These are TOLERANCES, not measurements: they sit
#: well above the two-decimal display floor a clean fit lands on (~0.004) and well below
#: anything a truncated or misjoined scrape produces. The DURANT percentage gate is loose
#: deliberately -- their percentage input is a known unresolved item (doc III.1) and must
#: never block a refresh.
GATES = {
    ("plain", "counting"): 0.020,
    ("plain", "percentage"): 0.030,
    ("durant", "counting"): 0.030,
    ("durant", "percentage"): 0.050,
}

#: Smallest scrape worth fitting. Below this a three-parameter fit still succeeds and still
#: returns different constants, with nothing to see.
MIN_ROWS = 150

#: Share of scraped ids that may fail to join before the pairing is treated as broken.
MAX_UNJOINED = 0.10

#: Robust sigmas past the median residual at which a player is treated as inconsistent
#: rather than noisy. Eight is a conventional outlier cut and it sits an order of magnitude
#: above the quantisation scatter: on a clean pairing the median player misses their
#: published column by 0.018 and the very worst by 0.055, while a player whose stat line
#: has actually changed misses by 0.2 to 0.5. The threshold itself is computed from the
#: data (median + 8 * 1.4826 * MAD), never typed in.
OUTLIER_SIGMAS = 8.0

#: Above this share of inconsistent players the export is not drifting, it is the wrong
#: file or the wrong date, and rejecting outliers would paper over that.
MAX_INCONSISTENT = 0.15

KIND = ({c: "counting" for _, c, _ in COUNTING}
        | {c: "percentage" for _, _, c in PERCENTAGE})
STAT_KEY = {c: k for k, c, _ in COUNTING}
SIGN = {c: s for _, c, s in COUNTING}
PCT_KEYS = {c: (made, att) for made, att, c in PERCENTAGE}


class CalibrationError(Exception):
    """The scrape or the fit is not good enough to write."""


# --------------------------------------------------------------------------------------
# Scraping
# --------------------------------------------------------------------------------------

_JS_SOURCE_STATE = """
() => { const s = document.querySelector('select[name=ProjectionSourceControl]');
        return s ? s.value : 'NO_SELECT'; }
"""

_JS_SET_SOURCE = """
() => { const s = document.querySelector('select[name=ProjectionSourceControl]');
        if (!s) return 'NO_SELECT';
        if (s.value === '%(sid)s') return 'ALREADY';
        s.value = '%(sid)s';
        s.dispatchEvent(new Event('change', {bubbles: true}));
        __doPostBack('ProjectionSourceControl', '', s.form);
        return 'POSTED'; }
"""

_JS_SET_FILTER = """
() => { const s = document.querySelector('select[name=PlayerFilterControl]');
        if (!s) return 'NO_SELECT';
        const o = [...s.options].find(x => /Only Top Players/i.test(x.text));
        if (!o) return 'NO_OPTION';
        if (s.value === o.value) return 'ALREADY';
        s.value = o.value;
        __doPostBack('PlayerFilterControl', '', s.form);
        return 'POSTED'; }
"""

# Table 0 is the projections grid. The player id comes from the row's playerinfo link --
# joining on a name would reintroduce exactly the ambiguity sources.py exists to remove.
_JS_SCRAPE = """
() => { const t = document.querySelectorAll('table')[0];
        if (!t) return 'NO_TABLE';
        const clean = s => s.replace(/\\s+/g, ' ').trim();
        const out = [];
        for (const r of t.rows) {
          const a = r.querySelector('a[href*="playerinfo.aspx?i="]');
          const m = a ? /i=(\\d+)/.exec(a.getAttribute('href')) : null;
          out.push([m ? m[1] : ''].concat([...r.cells].map(c => clean(c.innerText))).join('\\t'));
        }
        return out.join('\\n'); }
"""


def _run(*args: str, timeout: int = 180) -> str:
    """Run playwright-cli against the signed-in profile and return its raw output."""
    proc = subprocess.run(
        ["playwright-cli", f"-s={SESSION}", *args],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise CalibrationError(
            f"playwright-cli {args[0]} failed:\n{proc.stderr.strip()[:400]}"
        )
    return proc.stdout


def _pw(js: str, timeout: int = 180) -> str:
    """Evaluate JS in the current tab and return what it produced."""
    out = _run("eval", js, timeout=timeout)
    m = re.search(r"### Result\n(.*?)\n### Ran Playwright", out, re.S)
    if not m:
        raise CalibrationError(f"unexpected playwright-cli output:\n{out[:400]}")
    return json.loads(m.group(1).strip())


TAB = re.compile(r"^- (\d+): (?:\(current\) )?\[.*?\]\((.*?)\)\s*$", re.M)


def _focus_projections() -> None:
    """Put their projections page in the current tab without disturbing anything else.

    The `fantasy` profile is the same one the draft sheet is driven through, and a bare
    `goto` navigates whichever tab happens to be current -- which is usually the sheet. So
    find or open a Basketball Monster tab first, and only then navigate.

    The navigate is not optional. Their source selector posts back through ASP.NET, and a
    tab that has been sitting since an earlier postback carries a viewstate stale enough
    that the next one redirects to the home page instead of switching source -- which looks
    like a login failure and is not one.
    """
    for num, url in TAB.findall(_run("tab-list")):
        if "basketballmonster.com" in url:
            _run("tab-select", num)
            break
    else:
        _run("tab-new", PROJECTIONS_URL)
    _run("goto", PROJECTIONS_URL)
    time.sleep(2)


def _settle(want: str, tries: int = 20, pause: float = 1.0) -> None:
    """Wait for an ASP.NET postback to land. The source select reloads the whole page."""
    for _ in range(tries):
        state = _pw(_JS_SOURCE_STATE)
        if state == want:
            return
        time.sleep(pause)
    raise CalibrationError(
        f"the projections page never settled on source {want} (it reports {state!r}). "
        f"'NO_SELECT' means the postback bounced off the projections page -- usually a "
        f"stale viewstate or a signed-out session. Open the page in the `fantasy` profile, "
        f"check you are signed in, and retry."
    )


def scrape(source: str) -> str:
    """Drive the signed-in browser profile to their projections page and pull table 0.

    Uses the same `playwright-cli -s=fantasy` profile the sheet workflow uses, so it needs
    no extra credential and sees the page exactly as the subscriber does.
    """
    sid, name = SOURCES[source]
    _focus_projections()
    state = _pw(_JS_SOURCE_STATE)
    if state == "NO_SELECT":
        raise CalibrationError(
            "the projections page has no source selector, which means it served the "
            "sign-in page. Open it in the `fantasy` profile and sign in, then retry."
        )
    print(f"  switching to {name} Projections (source {sid})")
    _pw(_JS_SET_SOURCE % {"sid": sid})
    _settle(sid)
    _pw(_JS_SET_FILTER)
    time.sleep(2)
    text = _pw(_JS_SCRAPE)
    if text == "NO_TABLE":
        raise CalibrationError("no projections table on the page after the postback")
    return text


def parse_published(text: str) -> tuple[dict[int, dict[str, float]], int]:
    """Their scraped grid -> {player_id: {column: value}}. Returns (rows, skipped).

    Their export repeats its header roughly every dozen players and formats large numbers
    with thousands separators; both are dropped or stripped here rather than left to
    surprise a downstream float().
    """
    lines = [ln.split("\t") for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise CalibrationError("the scrape is empty")
    header = lines[0][1:]
    idx = {h: i + 1 for i, h in enumerate(header)}
    needed = set(PLAIN_COL.values()) | set(DURANT_COL.values())
    missing = needed - set(idx)
    if missing:
        raise CalibrationError(
            f"their table is missing {', '.join(sorted(missing))}. Turn the value columns "
            f"back on under 'Edit Display Columns' on the projections page."
        )

    out: dict[int, dict[str, float]] = {}
    skipped = 0
    for cells in lines[1:]:
        if not cells[0].isdigit():
            skipped += 1          # a repeated header row, or a row with no player link
            continue
        row = {}
        for col in needed:
            i = idx[col]
            raw = cells[i].replace(",", "") if i < len(cells) else ""
            try:
                row[col] = float(raw)
            except ValueError:
                row = {}
                break
        if row:
            out[int(cells[0])] = row
        else:
            skipped += 1
    return out, skipped


# --------------------------------------------------------------------------------------
# Least squares, stdlib
# --------------------------------------------------------------------------------------

def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting. `a` is square and small."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-14:
            raise CalibrationError("the normal equations are singular -- degenerate input")
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r == c:
                continue
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def _fit(xs: list[list[float]], ys: list[float]) -> tuple[list[float], float, float]:
    """OLS of y on the columns of `xs` plus an intercept. Returns (coeffs, rmse, max)."""
    n = len(ys)
    cols = [list(c) for c in xs] + [[1.0] * n]
    p = len(cols)
    a = [[sum(cols[i][k] * cols[j][k] for k in range(n)) for j in range(p)]
         for i in range(p)]
    b = [sum(cols[i][k] * ys[k] for k in range(n)) for i in range(p)]
    coef = _solve(a, b)
    res = [ys[k] - sum(coef[i] * cols[i][k] for i in range(p)) for k in range(n)]
    return coef, math.sqrt(sum(r * r for r in res) / n), max(abs(r) for r in res)


#: Grid points per axis per refinement pass, and how many passes. Four passes over 21
#: points shrink the bracket by 10x each time, so a span of 1.0 resolves to about 1e-5 in
#: under two thousand evaluations. A single fine grid over the whole span would need a
#: hundred thousand, which is the difference between a refresh step and a coffee break.
GRID_POINTS = 21
GRID_PASSES = 4


def _grid(lo: float, hi: float, n: int = GRID_POINTS):
    step = (hi - lo) / (n - 1)
    return [lo + i * step for i in range(n)]


def _refine(brackets: list[tuple[float, float]], objective):
    """Coordinate grid search with a bracket that shrinks around the winner each pass.

    `objective` takes one value per bracket and returns (cost, payload); a cost of None
    marks a degenerate point. Returns (best_point, cost, payload), all None if every point
    was degenerate. Callers check `_near` themselves to decide whether the winner is a real
    optimum or the edge of a badly chosen bracket.
    """
    spans = [hi - lo for lo, hi in brackets]
    best = None
    for _ in range(GRID_PASSES):
        axes = [_grid(lo, hi) for lo, hi in brackets]
        best = None
        for point in _product(axes):
            cost, payload = objective(*point)
            if cost is not None and (best is None or cost < best[0]):
                best = (cost, list(point), payload)
        if best is None:
            return None, None, None
        # Two grid steps either side of the winner, so the next pass cannot step over it.
        brackets = [(c - 2 * s / (GRID_POINTS - 1), c + 2 * s / (GRID_POINTS - 1))
                    for c, s in zip(best[1], spans, strict=True)]
        spans = [hi - lo for lo, hi in brackets]
    return best[1], best[0], best[2]


def _product(axes: list[list[float]]):
    if len(axes) == 1:
        for a in axes[0]:
            yield (a,)
        return
    for a in axes[0]:
        for rest in _product(axes[1:]):
            yield (a, *rest)


# --------------------------------------------------------------------------------------
# The four estimators
# --------------------------------------------------------------------------------------

def fit_counting_plain(cat: str, xs: list[float], ys: list[float]) -> dict:
    """z = sign * (x - mean) / sd, so a straight line in x."""
    (slope, icpt), rmse, mx = _fit([xs], ys)
    if abs(slope) < 1e-12:
        raise CalibrationError(f"{cat}: no slope, the published column does not track the stat")
    sd = SIGN[cat] / slope
    if sd <= 0:
        raise CalibrationError(
            f"{cat}: recovered sd={sd:.4f}. A negative spread means the sign convention is "
            f"inverted relative to their column, so the fit is meaningless."
        )
    return {"mean": -icpt / slope, "sd": sd, "rmse": rmse, "max_resid": mx}


def fit_counting_durant(cat: str, xs: list[float], ys: list[float], seed: float,
                        span: float = 0.5) -> dict:
    """Fit lambda and the constants together: z = sign * (YJ(x, lam) - mean) / sd.

    The objective is the residual against THEIR published column, not maximum likelihood.
    That distinction is the point -- MLE on the same pool gives +0.065 for points against
    their +0.415 (doc III.1), while regressing on their own output recovers them to three
    decimals. Do not "fix" this back to fit_lambda.

    The bracket is the seed plus or minus `span`, widened once if the winner lands on the
    edge. A hardcoded [-4, 4] sweep would be both slower and less honest about what is
    being assumed.
    """
    def objective(lam):
        (slope, icpt), rmse, mx = _fit([[yeo_johnson(x, lam) for x in xs]], ys)
        if abs(slope) < 1e-12:
            return None, None
        return rmse, (slope, icpt, mx)

    for attempt in range(2):
        lo = max(-BC.LAM_LIMIT, seed - span)
        hi = min(BC.LAM_LIMIT, seed + span)
        point, rmse, payload = _refine([(lo, hi)], objective)
        if point is None:
            raise CalibrationError(f"{cat}: no usable lambda in [{lo:.2f}, {hi:.2f}]")
        if not _near(point[0], lo, hi) or attempt:
            break
        span *= 3

    if _near(point[0], lo, hi):
        raise CalibrationError(
            f"{cat}: lambda {point[0]:.4f} sits on the edge of [{lo:.2f}, {hi:.2f}] even "
            f"after widening, so it is a bracket artefact rather than a measurement."
        )
    slope, icpt, mx = payload
    sd = SIGN[cat] / slope
    if sd <= 0:
        raise CalibrationError(f"{cat}: recovered sd={sd:.4f} on the DURANT layer")
    return {"mean": -icpt / slope, "sd": sd, "lam": point[0], "rmse": rmse, "max_resid": mx}


def _near(x: float, lo: float, hi: float) -> bool:
    """Did the winner never leave the boundary of its bracket?"""
    tol = (hi - lo) / (GRID_POINTS - 1)
    return x - lo < tol or hi - x < tol


def fit_pct_plain(cat: str, made: list[float], att: list[float], ys: list[float]) -> dict:
    """z = (made - att*rate - mean) / sd, linear in makes and attempts jointly.

    Three unknowns, two regressors and an intercept, so the pool rate is identified rather
    than assumed -- which matters, because their rate is not our pool's rate.
    """
    (a, b, c), rmse, mx = _fit([made, att], ys)
    if abs(a) < 1e-12:
        raise CalibrationError(f"{cat}: no dependence on makes")
    sd = 1 / a
    if sd <= 0:
        raise CalibrationError(f"{cat}: recovered sd={sd:.4f}")
    return {"mean": -c / a, "sd": sd, "rate": -b / a, "rmse": rmse, "max_resid": mx}


def fit_pct_durant(cat: str, made: list[float], att: list[float], ys: list[float],
                   rate_seed: float, lam_seed: float) -> dict:
    """The impact is transformed, so the rate no longer falls out of a linear fit.

    Search the rate and lambda together, then solve the linear part exactly. The rate
    bracket is centred on the rate the plain-z fit already recovered from the same data --
    derived, not typed -- because the two layers use rates that are close but, on their
    numbers, not equal.

    Their percentage input is not quite our impact column: the Spearman against it is 0.998
    rather than 1.0 (doc III.1). So this residual stays above the display floor whatever is
    fitted. That is a known open item, not a failure of the search.
    """
    r_span, l_span = 0.10, 0.5
    for attempt in range(2):
        rlo, rhi = rate_seed - r_span, rate_seed + r_span
        llo = max(-BC.LAM_LIMIT, lam_seed - l_span)
        lhi = min(BC.LAM_LIMIT, lam_seed + l_span)

        def objective(rate, lam):
            xs = [yeo_johnson(made[i] - att[i] * rate, lam) for i in range(len(ys))]
            (a, b), rmse, mx = _fit([xs], ys)
            if abs(a) < 1e-12:
                return None, None
            return rmse, (a, b, mx)

        point, rmse, payload = _refine([(rlo, rhi), (llo, lhi)], objective)
        if point is None:
            raise CalibrationError(f"{cat}: no usable (rate, lambda) pair")
        edge = _near(point[0], rlo, rhi) or _near(point[1], llo, lhi)
        if not edge or attempt:
            break
        r_span, l_span = r_span * 3, l_span * 3

    if edge:
        raise CalibrationError(
            f"{cat}: (rate {point[0]:.4f}, lambda {point[1]:.4f}) sits on the edge of its "
            f"search bracket even after widening -- a bracket artefact, not a measurement."
        )
    a, b, mx = payload
    sd = 1 / a
    if sd <= 0:
        raise CalibrationError(f"{cat}: recovered sd={sd:.4f} on the DURANT layer")
    return {"mean": -b / a, "sd": sd, "rate": point[0], "lam": point[1],
            "rmse": rmse, "max_resid": mx}


# --------------------------------------------------------------------------------------
# Putting it together
# --------------------------------------------------------------------------------------

def consistent_players(rates: dict, published: dict, keys: list) -> tuple[list, list]:
    """Split the joined players into those whose stat line matches what was valued.

    A published value is exactly linear in the stat, so one player whose export row has
    since been revised does not merely mispredict itself -- it tilts the regression and
    corrupts constants that are then applied to every player in the universe. Basketball
    Monster revises between exports, so this is ordinary rather than exceptional.

    Fit each plain-z category once over everyone, take each player's worst residual across
    the nine, and cut at a threshold derived from the spread of those residuals. On a clean
    pairing nothing is rejected; on a drifted one the handful of genuinely changed rows are.

    Returns (kept, rejected), both lists of player keys, rejected worst-first.
    """
    worst = dict.fromkeys(keys, 0.0)
    for cat in CATEGORIES:
        ys = [published[k][PLAIN_COL[cat]] for k in keys]
        if KIND[cat] == "counting":
            xs = [rates[k][STAT_KEY[cat]] for k in keys]
            (slope, icpt), _, _ = _fit([xs], ys)
            pred = [slope * x + icpt for x in xs]
        else:
            mk, ak = PCT_KEYS[cat]
            made = [rates[k][mk] for k in keys]
            att = [rates[k][ak] for k in keys]
            (a, b, c), _, _ = _fit([made, att], ys)
            pred = [a * made[i] + b * att[i] + c for i in range(len(keys))]
        for i, k in enumerate(keys):
            worst[k] = max(worst[k], abs(ys[i] - pred[i]))

    vals = sorted(worst.values())
    med = st.median(vals)
    mad = st.median([abs(v - med) for v in vals])
    # 1.4826 turns a MAD into a standard-deviation estimate for normally-scattered noise.
    limit = med + OUTLIER_SIGMAS * 1.4826 * mad
    kept = [k for k in keys if worst[k] <= limit]
    rejected = sorted((k for k in keys if worst[k] > limit),
                      key=lambda k: -worst[k])
    return kept, rejected


def calibrate(rates: dict, published: dict, keys: list,
              seeds: dict) -> tuple[dict, dict, dict]:
    """Fit both layers over `keys`. Returns (params, lambdas, fit report)."""
    plain, durant, lambdas, report = {}, {}, {}, {"plain": {}, "durant": {}}

    for cat in CATEGORIES:
        yp = [published[k][PLAIN_COL[cat]] for k in keys]
        yd = [published[k][DURANT_COL[cat]] for k in keys]
        if KIND[cat] == "counting":
            xs = [rates[k][STAT_KEY[cat]] for k in keys]
            p = fit_counting_plain(cat, xs, yp)
            d = fit_counting_durant(cat, xs, yd, seeds[cat])
            plain[cat] = {"kind": "counting", "mean": p["mean"], "sd": p["sd"]}
        else:
            mk, ak = PCT_KEYS[cat]
            made = [rates[k][mk] for k in keys]
            att = [rates[k][ak] for k in keys]
            p = fit_pct_plain(cat, made, att, yp)
            d = fit_pct_durant(cat, made, att, yd, p["rate"], seeds[cat])
            plain[cat] = {"kind": "percentage", "mean": p["mean"], "sd": p["sd"],
                          "rate": p["rate"]}
        durant[cat] = {k: v for k, v in d.items() if k in ("mean", "sd", "rate")}
        durant[cat]["kind"] = KIND[cat]
        lambdas[cat] = d["lam"]
        for layer, fit in (("plain", p), ("durant", d)):
            report[layer][cat] = {"rmse": round(fit["rmse"], 5),
                                  "max_resid": round(fit["max_resid"], 5),
                                  "n": len(keys)}
    return {"plain": plain, "durant": durant}, lambdas, report


def check_gates(report: dict, force: bool) -> list[str]:
    bad = []
    for layer in ("plain", "durant"):
        for cat, fit in report[layer].items():
            gate = GATES[(layer, KIND[cat])]
            if fit["rmse"] > gate:
                bad.append(f"{layer}.{cat} rmse {fit['rmse']:.4f} > {gate:.3f}")
    if bad and not force:
        raise CalibrationError(
            "the fit is outside tolerance, so the scrape is probably bad or their columns "
            "have changed:\n  " + "\n  ".join(bad)
            + "\nRead the per-category table above before reaching for --force."
        )
    return bad


def derived_gap(rates: dict, params: dict, lambdas: dict) -> dict:
    """What our own top-Q pool would say, against what was recovered.

    The mean gap is reported as a percentage of THEIR standard deviation, not of their
    mean. The two percentage impacts are centred near zero by construction, so a percentage
    of the mean there is a division by almost nothing -- it reads as a catastrophe on the
    two categories that are actually fine. Per SD is meaningful for all nine and comparable
    across them: it is how far our notion of "average" sits from theirs, in the units the
    values are expressed in.
    """
    if len(rates) <= Q:
        return {}
    _, ours_plain = build_pool(rates, Q)
    _, ours_dur = build_durant_pool(rates, Q, lambdas)
    out = {}
    for layer, ours in (("plain", ours_plain), ("durant", ours_dur)):
        out[layer] = {}
        for cat in CATEGORIES:
            spec = params[layer][cat]
            out[layer][cat] = {
                "mean": 100 * (ours[cat]["mean"] - spec["mean"]) / spec["sd"],
                "sd": 100 * (ours[cat]["sd"] - spec["sd"]) / spec["sd"],
            }
    return out


def report_table(params: dict, lambdas: dict, seeds: dict, fit: dict, gap: dict) -> None:
    for layer, title in (("plain", "PLAIN Z"), ("durant", "DURANT")):
        print(f"\n{title}")
        print(f"  {'cat':6} {'mean':>10} {'sd':>9} {'rate':>8} {'lam':>8} "
              f"{'dmean%sd':>9} {'dsd%':>7} {'rmse':>7} {'max':>7}")
        for cat in CATEGORIES:
            spec = params[layer][cat]
            g = gap.get(layer, {}).get(cat, {})
            rate = f"{spec['rate']:8.4f}" if "rate" in spec else " " * 8
            lam = f"{lambdas[cat]:8.4f}" if layer == "durant" else " " * 8
            dm = f"{g['mean']:+9.2f}" if g.get("mean") is not None else " " * 9
            ds = f"{g['sd']:+7.2f}" if g.get("sd") is not None else " " * 7
            f = fit[layer][cat]
            print(f"  {cat:6} {spec['mean']:10.4f} {spec['sd']:9.4f} {rate} {lam} "
                  f"{dm} {ds} {f['rmse']:7.4f} {f['max_resid']:7.4f}")
    print("\n  dmean%sd / dsd%: how far our OWN top-156 pool sits from what was")
    print("  recovered -- the mean gap in percent of their SD, the SD gap in percent.")
    print("  A few percent either way is normal and is exactly why the constants are")
    print("  borrowed (ADR-0021). Anything wilder means the scrape or the join is bad.")
    drift = [f"{c} {lambdas[c]:+.4f} vs seed {seeds[c]:+.4f}"
             for c in CATEGORIES
             if KIND[c] == "counting" and abs(lambdas[c] - seeds[c]) > BC.LAM_DRIFT_WARN]
    if drift:
        print("\n  LAMBDA DRIFT -- they may have retuned their transform:")
        for d in drift:
            print(f"    {d}")
    # The two percentage lambdas are fitted jointly with the pool rate and trade off
    # against it along a ridge, so they wander between refreshes without meaning anything.
    # Alarming on them would train the reader to ignore the alarm.
    wander = [f"{c} {lambdas[c]:+.4f} (seed {seeds[c]:+.4f})"
              for c in CATEGORIES
              if KIND[c] == "percentage" and abs(lambdas[c] - seeds[c]) > BC.LAM_DRIFT_WARN]
    if wander:
        print("\n  Percentage lambdas moved: " + "; ".join(wander))
        print("  Expected. They are fitted jointly with the pool rate and are not")
        print("  separately identified -- doc III.1. Not a signal about their method.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, choices=sorted(SOURCES))
    ap.add_argument("--date", required=True, help="the export date to fit against")
    ap.add_argument("--from-file", action="store_true",
                    help="refit from the saved scrape instead of driving the browser")
    ap.add_argument("--dry-run", action="store_true", help="report and write nothing")
    ap.add_argument("--force", action="store_true", help="write despite a gate failure")
    args = ap.parse_args()

    export = DATA / f"{args.source} Projections - {args.date}.csv"
    if not export.exists():
        raise SystemExit(f"No export at {export}. Nothing to calibrate against.")
    tsv = DATA / f"BBM Published - {args.source} - {args.date}.tsv"
    out = DATA / f"{args.source} Constants - {args.date}.json"

    print(f"{args.source} ({SOURCES[args.source][1]} Projections)  export {args.date}")

    if args.from_file:
        if not tsv.exists():
            raise SystemExit(f"No saved scrape at {tsv}. Drop --from-file to fetch one.")
        text = tsv.read_text(encoding="utf-8")
        print(f"  reading the saved scrape at {tsv.name}")
    else:
        text = scrape(args.source)
        if not args.dry_run:
            tsv.write_text(text, encoding="utf-8")
        print(f"  scraped {len(text.splitlines())} lines")

    published, skipped = parse_published(text)
    if len(published) < MIN_ROWS:
        raise SystemExit(
            f"only {len(published)} usable rows (skipped {skipped}). A three-parameter fit "
            f"on a truncated set still succeeds and still returns different constants, so "
            f"this is refused rather than fitted."
        )

    vendor = S.load_vendor(export)
    rates = {pid: r for pid, p in vendor.items() if (r := per_game(p))}
    joined = set(rates) & set(published)
    unjoined = len(published) - len(joined)
    if unjoined > MAX_UNJOINED * len(published):
        raise SystemExit(
            f"{unjoined} of {len(published)} scraped players have no row in {export.name}. "
            f"That is what a fresh scrape paired with a stale export looks like; re-export "
            f"before calibrating."
        )
    print(f"  {len(joined)} players joined on player_id "
          f"({unjoined} unjoined, {skipped} non-player rows skipped)")

    kept, rejected = consistent_players(rates, published, sorted(joined))
    if len(rejected) > MAX_INCONSISTENT * len(joined):
        raise SystemExit(
            f"{len(rejected)} of {len(joined)} players have a stat line that cannot be "
            f"reconciled with the value beside it. That is not drift, it is the wrong "
            f"export or the wrong date -- re-export {args.source} and retry."
        )
    if rejected:
        print(f"  {len(rejected)} players dropped from the fit: their stat line no longer "
              f"matches the one\n  Basketball Monster valued, so they would tilt every "
              f"constant. Re-export to score them right:")
        for k in rejected[:10]:
            print(f"    {vendor[k]['name']}")
        if len(rejected) > 10:
            print(f"    ... and {len(rejected) - 10} more")

    params, lambdas, fit = calibrate(rates, published, kept, LAMBDAS_BBM_2026_27_JOSH)
    report_table(params, lambdas, LAMBDAS_BBM_2026_27_JOSH, fit,
                 derived_gap(rates, params, lambdas))

    failures = check_gates(fit, args.force)
    print("\n  " + ("FORCED past: " + "; ".join(failures) if failures
                    else "all 18 fits within tolerance"))

    blob = BC.dump(
        params, lambdas, source=args.source, export_date=args.date,
        bbm_source_id=int(SOURCES[args.source][0]),
        fitted_at=dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        fitted_from=tsv.name, players_fitted=len(kept), fit=fit,
    )
    # Read it straight back, so a file that cannot be loaded is never left on disk.
    BC.parse(blob, source=args.source, export_date=args.date)

    if args.dry_run:
        print(f"\n--dry-run: nothing written (would go to {out.name}).")
        return 0
    out.write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CalibrationError as exc:
        raise SystemExit(f"calibration failed: {exc}") from None
