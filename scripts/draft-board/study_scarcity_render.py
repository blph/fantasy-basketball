"""Render the scarcity counts as one self-contained HTML page.

The study asks a shape question -- which categories thin out early and which stay
available all thirteen rounds -- so the report is built around making shape, not
magnitude, the first thing the eye catches.

Four decisions, each of which is a way to draw a plausible wrong picture:

  - **One y domain everywhere, 0..12.** A round holds `teams` players, so twelve is
    the structural ceiling of every curve and every panel. Rescaling a panel to its
    own maximum is the classic small-multiples mistake: it makes a category with one
    player per round look exactly like one with eight, and the whole finding is the
    difference between those two.

  - **Rounds are bands, not instants.** A round is twelve picks long. Every x sits at
    a band centre, so the point on the line and the stacked bar for that round share
    one position and the reader can read them as the same fact twice.

  - **The eight curves are drawn twice, at two jobs.** Together, in the headline
    chart, they answer "which dies first". Alone in a panel, with the other seven
    ghosted behind in a neutral, they answer "and how does this one compare" -- the
    emphasis form, where colour identifies one series and the rest recede.

  - **Colour is the palette's, not ours.** Eight validated categorical slots, assigned
    to `labels` in the board's own order and never by rank, so a category keeps its
    hue across the chart, the panels and the table. Three light-mode slots sit below
    3:1 on the page surface; the relief is that every value is also reachable from a
    direct label and from the summary table, so nothing is gated on seeing a hue.

Everything is inline. No network request of any kind, no JavaScript: the hover
emphasis is `:has()` in CSS, which degrades to a static page where it is unsupported.
The only input is the `result` dict -- importing the study itself would be circular,
and every derived fact here is recomputed from the counts.
"""

from __future__ import annotations

from html import escape

#: Structural ceiling of the y domain. A round holds `teams` players and a player is
#: counted at most once per category, so no count can exceed the round's size.
Y_MAX = 12

#: The validated categorical palette, in slot order. Light and dark are the same eight
#: hues stepped for their own surface, not an automatic flip. Assigned to categories in
#: the board's label order -- a fixed mapping, so filtering or re-sorting never repaints.
SERIES_LIGHT = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#4a3aa7", "#e34948",
)
SERIES_DARK = (
    "#3987e5", "#d95926", "#199e70", "#c98500",
    "#d55181", "#008300", "#9085e9", "#e66767",
)

# Headline chart geometry, in viewBox units.
HL_W, HL_H = 1000.0, 520.0
HL_BOX = (52.0, 34.0, 796.0, 434.0)  # x, y, width, height of the plot area

# Panel geometry, in viewBox units.
PN_W, PN_H = 264.0, 166.0
PN_BOX = (22.0, 10.0, 234.0, 132.0)


class _Frame:
    """The pixel box of one plot, and the two maps onto it.

    `cx` places a round at its band centre rather than at a tick, because a round is a
    span of twelve picks. `cy` is fixed to 0..`Y_MAX` for every frame in the document;
    it deliberately takes no data, so no caller can accidentally give a panel its own
    scale.
    """

    def __init__(self, x: float, y: float, w: float, h: float, n: int) -> None:
        self.x0, self.y0, self.w, self.h = x, y, w, h
        self.n = max(int(n), 1)
        self.band = self.w / self.n

    @property
    def x1(self) -> float:
        return self.x0 + self.w

    @property
    def y1(self) -> float:
        return self.y0 + self.h

    def cx(self, i: int) -> float:
        return self.x0 + (i + 0.5) * self.band

    def cy(self, v: float) -> float:
        return self.y0 + self.h * (1.0 - float(v) / Y_MAX)


def _num(v: float) -> str:
    """A coordinate with its trailing noise trimmed, so the markup stays readable."""
    s = f"{float(v):.2f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _css_str(v: str) -> str:
    """A CSS string literal body. Attribute selectors carry category names verbatim."""
    return v.replace("\\", "\\\\").replace('"', '\\"')


def _points(frame: _Frame, values: list[int]) -> str:
    """A polyline `points` list over one category's per-round counts."""
    return " ".join(f"{_num(frame.cx(i))},{_num(frame.cy(v))}" for i, v in enumerate(values))


def _bar_path(x: float, y: float, w: float, h: float, r: float) -> str:
    """A bar rounded at the data end and square at the baseline.

    The rounded cap marks where the value stops. Squaring the foot keeps the whole
    stack sitting on one baseline, which is what makes heights comparable by eye.
    """
    r = max(0.0, min(r, w / 2.0, h))
    return (
        f"M{_num(x)},{_num(y + h)} V{_num(y + r)} "
        f"Q{_num(x)},{_num(y)} {_num(x + r)},{_num(y)} "
        f"H{_num(x + w - r)} Q{_num(x + w)},{_num(y)} {_num(x + w)},{_num(y + r)} "
        f"V{_num(y + h)} Z"
    )


def _spread(targets: list[float], lo: float, hi: float, gap: float) -> list[float]:
    """Vertical positions for end labels that want to sit on top of each other.

    Several curves converge on zero at the right edge, so their natural label
    positions collide. Four ordered passes -- push down, pull the overflow back,
    push up, clamp -- separate them by at least `gap` while preserving their order,
    which is what keeps a label next to its own line. A leader line then re-attaches
    each label to the point it was moved away from.
    """
    if not targets:
        return []
    order = sorted(range(len(targets)), key=lambda i: targets[i])
    pos = [targets[i] for i in order]
    for k in range(1, len(pos)):
        pos[k] = max(pos[k], pos[k - 1] + gap)
    overshoot = pos[-1] - hi
    if overshoot > 0:
        pos = [p - overshoot for p in pos]
    for k in range(len(pos) - 2, -1, -1):
        pos[k] = min(pos[k], pos[k + 1] - gap)
    if pos[0] < lo:
        pos[0] = lo
        for k in range(1, len(pos)):
            pos[k] = max(pos[k], pos[k - 1] + gap)
    out = [0.0] * len(targets)
    for slot, i in enumerate(order):
        out[i] = pos[slot]
    return out


def _facts(result: dict) -> dict[str, dict[str, int | None]]:
    """Per-category summary figures, recomputed here rather than imported.

    `last` is the deepest round still holding one, which is not the round the count
    first hits zero -- a category can go quiet for a round and come back, and reading
    the first zero would report it as gone three rounds early.
    """
    rounds = list(result["rounds"])
    out: dict[str, dict[str, int | None]] = {}
    for cat in result["labels"]:
        c = result["counts"][cat]
        total = list(c["total"])
        held = [r for r, v in zip(rounds, total, strict=True) if v > 0]
        best = max(total) if total else 0
        peak = next((r for r, v in zip(rounds, total, strict=True) if v == best), None)
        out[cat] = {
            "pool": sum(total),
            "primary": sum(c["primary"]),
            "secondary": sum(c["secondary"]),
            "last": held[-1] if held else None,
            "peak": peak if best > 0 else None,
            "peak_n": best,
        }
    return out


#: Everything that does not depend on the data. Every colour here is a token, because
#: the dark block below redefines all of them and a literal would survive the swap.
_BASE_CSS = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  font-size:16px;line-height:1.5;-webkit-font-smoothing:antialiased}
.doc{max-width:1180px;margin:0 auto;padding:0 16px 72px}
@media (min-width:900px){.doc{padding:0 32px 88px}}

.masthead{padding:54px 0 24px;border-bottom:2px solid var(--ink)}
h1{margin:0;font-size:clamp(2rem,1.2rem+2.6vw,3.15rem);font-weight:600;
  letter-spacing:-0.022em;line-height:1.04;text-wrap:balance}
.standfirst{margin:16px 0 0;max-width:64ch;font-size:1.0625rem;line-height:1.55;
  color:var(--ink-2)}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,max-content));
  gap:14px 34px;margin:28px 0 0;padding:0}
.meta div{margin:0}
.meta dt{font-size:0.75rem;color:var(--muted);line-height:1.3}
.meta dd{margin:2px 0 0;font-size:0.9375rem;font-variant-numeric:tabular-nums;
  color:var(--ink)}

.sec{padding:40px 0 0}
.sec+.sec{margin-top:44px;padding-top:36px;border-top:1px solid var(--rule)}
h2{margin:0;font-size:1.1875rem;font-weight:600;letter-spacing:-0.01em}
.lede{margin:8px 0 22px;max-width:70ch;font-size:0.9375rem;line-height:1.6;
  color:var(--ink-2)}

.plot-wrap{overflow-x:auto;overscroll-behavior-x:contain;background:var(--surface);
  border:1px solid var(--hair);border-radius:4px;padding:10px 6px}
.plot-wrap svg{display:block;width:100%;min-width:700px;height:auto}
.scroll-hint{display:none}
@media (max-width:790px){.scroll-hint{display:block;margin:9px 0 0;
  font-size:0.75rem;color:var(--ink-2)}}
.plot-wrap svg text{font-family:inherit}

.panels{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;
  background:var(--hair);border:1px solid var(--hair);border-radius:4px;
  overflow:hidden}
@media (max-width:1040px){.panels{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.panels{grid-template-columns:1fr}}
.panel{margin:0;background:var(--surface);padding:13px 13px 8px}
.panel:focus-visible{outline:2px solid var(--ink);outline-offset:-2px}
.panel svg{display:block;width:100%;height:auto;margin-top:2px}
.panel svg text{font-family:inherit}
.panel-head{display:flex;align-items:center;gap:8px}
.key{width:14px;height:3px;border-radius:2px;flex:0 0 auto}
.panel-name{font-weight:600;font-size:0.9375rem}
.panel-pool{margin-left:auto;font-size:0.9375rem;font-variant-numeric:tabular-nums}
.panel-sub{margin:3px 0 0;font-size:0.75rem;line-height:1.35;color:var(--muted)}

.tbl-wrap{overflow-x:auto;border:1px solid var(--hair);border-radius:4px;
  background:var(--surface)}
table{border-collapse:separate;border-spacing:0;width:100%;
  font-size:0.875rem;font-variant-numeric:tabular-nums}
caption{caption-side:top;text-align:left;padding:12px 12px 10px;font-size:0.8125rem;
  color:var(--muted)}
th,td{padding:7px 7px;text-align:right;white-space:nowrap}
thead th{font-weight:500;font-size:0.75rem;color:var(--muted);
  border-bottom:1px solid var(--rule)}
tbody td{border-bottom:1px solid var(--hair)}
tbody tr:last-child td{border-bottom:0}
th.cat,td.cat{position:sticky;left:0;z-index:1;text-align:left;
  background:var(--surface);border-right:1px solid var(--hair);padding-left:12px}
td.cat{font-weight:500}
.cat-inner{display:flex;align-items:center;gap:8px}
td.heat{background-color:rgb(var(--heat)/var(--a,0));
  box-shadow:inset -1px 0 0 var(--surface)}
td.zero{color:var(--muted)}
td.pool{font-weight:600;border-left:1px solid var(--rule)}
td.last{color:var(--ink-2)}
tbody tr:hover td.cat{box-shadow:inset 3px 0 0 var(--ink)}

.ramp{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:14px 0 0;
  font-size:0.75rem;color:var(--ink-2)}
.ramp ol{display:flex;gap:2px;margin:0;padding:0;list-style:none}
.ramp li{width:22px;height:10px;border-radius:1px;
  box-shadow:inset 0 0 0 1px var(--hair);
  background-color:rgb(var(--heat)/var(--a))}

.colophon{margin-top:46px;padding-top:20px;border-top:1px solid var(--rule);
  max-width:72ch;font-size:0.8125rem;line-height:1.6;color:var(--ink-2)}
.colophon p{margin:0 0 9px}

[data-series]{transition:opacity 140ms ease}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
@media print{
  body{background:#fff}
  .panel,.panels,.tbl-wrap{break-inside:avoid}
  .plot-wrap{overflow:visible}
  .plot-wrap svg{min-width:0}
}
@media (forced-colors:active){
  td.heat{background-color:transparent;forced-color-adjust:none}
  .key,.ramp li{forced-color-adjust:none}
}
"""


def _slot(table: tuple[str, ...], i: int) -> str:
    """Slot `i`'s hue, or a neutral past the eighth.

    Eight is the palette's ceiling. A ninth hue, generated or reused, is not
    distinguishable from one already on the chart under colour-vision deficiency, so a
    board that ever profiles more than eight categories has to fold its tail rather
    than borrow a colour. Until it does, the extras render neutral -- visibly
    unassigned, rather than quietly impersonating another category.
    """
    return table[i] if i < len(table) else "var(--ghost)"


def _tokens(labels: list[str]) -> str:
    """The two token scopes: page defaults, then the dark surface's own steps.

    The dark column is the same eight hues re-stepped for a dark surface, not an
    inverted light palette -- a hue that clears 3:1 on paper is usually too dark
    against ink, and vice versa.
    """
    light = "".join(f"--s{i}:{_slot(SERIES_LIGHT, i)};" for i in range(len(labels)))
    dark = "".join(f"--s{i}:{_slot(SERIES_DARK, i)};" for i in range(len(labels)))
    return (
        ":root{color-scheme:light;"
        "--plane:#eceff2;--surface:#fbfcfd;--sunken:#f4f6f8;"
        "--ink:#16202a;--ink-2:#4c5a67;--muted:#5f6c79;"
        "--grid:#e3e8ec;--rule:#ccd4db;--hair:#dee4e9;--ghost:#94a4b1;"
        "--wash:22 32 42;--heat:28 92 171;"
        + light
        + "}\n"
        "@media (prefers-color-scheme:dark){:root{color-scheme:dark;"
        "--plane:#090c0f;--surface:#12181e;--sunken:#182028;"
        "--ink:#eaf1f6;--ink-2:#a7b4c0;--muted:#7c8a96;"
        "--grid:#222c34;--rule:#34414b;--hair:#1f272e;--ghost:#6c7c8a;"
        "--wash:234 241 246;--heat:87 157 235;"
        + dark
        + "}}\n"
    )


def _emphasis_css(labels: list[str]) -> str:
    """Hover and keyboard emphasis, in CSS alone.

    Pointing at a category anywhere -- its line, its panel, its table row -- recedes
    the other seven in the headline chart. `:has()` keeps this out of JavaScript, so
    a browser without it simply shows the undimmed chart rather than a broken one.
    """
    out = []
    for cat in labels:
        sel = _css_str(cat)
        out.append(
            f'.doc:has([data-cat="{sel}"]:hover) [data-series]:not([data-series="{sel}"]),'
            f'.doc:has([data-cat="{sel}"]:focus-visible)'
            f' [data-series]:not([data-series="{sel}"])'
            "{opacity:0.14}"
        )
    return "\n".join(out) + "\n"


#: Alpha floor and span of the table's heat ramp. The ceiling is deliberately short of
#: a saturated fill: capped here, one ink colour clears 4.5:1 over every step in both
#: themes, so no cell needs its text recoloured and no value is readable by hue alone.
_HEAT_FLOOR, _HEAT_SPAN = 0.06, 0.49


def _heat_alpha(v: int) -> float:
    return 0.0 if v <= 0 else _HEAT_FLOOR + _HEAT_SPAN * (min(v, Y_MAX) / Y_MAX)


def _svg_axes(frame: _Frame, rounds: list[int], y_ticks: list[int],
              x_ticks: list[int], font: float) -> str:
    """Gridlines, baseline and tick labels -- solid hairlines, one step off the surface.

    The `Y_MAX` line is drawn a shade stronger than the rest: it is not a gridline but
    the ceiling of the domain, the round drafted out entirely, and a reader who cannot
    see where that sits cannot tell "deep" from "everyone".
    """
    out = ['<g class="axes" shape-rendering="crispEdges">']
    for t in y_ticks:
        y = _num(frame.cy(t))
        tone = "var(--rule)" if t in (0, Y_MAX) else "var(--grid)"
        out.append(
            f'<line x1="{_num(frame.x0)}" y1="{y}" x2="{_num(frame.x1)}" y2="{y}" '
            f'style="stroke:{tone}" stroke-width="1"/>'
        )
    out.append("</g>")
    lab = f'<g class="ticks" style="fill:var(--muted)" font-size="{_num(font)}">'
    out.append(lab)
    for t in y_ticks:
        out.append(
            f'<text x="{_num(frame.x0 - font * 0.55)}" y="{_num(frame.cy(t) + font * 0.34)}" '
            f'text-anchor="end">{t}</text>'
        )
    for r in x_ticks:
        i = rounds.index(r)
        out.append(
            f'<text x="{_num(frame.cx(i))}" y="{_num(frame.y1 + font * 1.5)}" '
            f'text-anchor="middle">{r}</text>'
        )
    out.append("</g>")
    return "".join(out)


def _line_chart(result: dict, facts: dict) -> str:
    """The headline: eight totals on one pair of axes, each labelled at its own end.

    A key off to the side would make the reader carry eight colours in their head while
    reading the shapes. The labels ride the lines instead; where the curves converge on
    zero at the right edge `_spread` separates them and a leader line puts each one back
    on its own end point, so no label ever claims a curve it does not belong to.
    """
    labels, rounds = list(result["labels"]), list(result["rounds"])
    fr = _Frame(*HL_BOX, len(rounds))
    key_x, name_x, val_x = fr.x1 + 22, fr.x1 + 42, HL_W - 10
    y_ticks = list(range(0, Y_MAX + 1, 2))

    out = [
        f'<svg viewBox="0 0 {_num(HL_W)} {_num(HL_H)}" role="img" '
        'aria-label="Players per round carrying each category as a strength">',
        "<title>Players per round carrying each category as a strength</title>",
        _svg_axes(fr, rounds, y_ticks, rounds, 13.0),
        f'<text x="{_num(fr.x0 + 3)}" y="{_num(fr.y0 - 11)}" font-size="12" '
        f'style="fill:var(--muted)">{Y_MAX} is the whole round</text>',
        f'<text x="{_num(val_x)}" y="{_num(fr.y0 - 11)}" text-anchor="end" font-size="12" '
        'style="fill:var(--muted)">In the pool</text>',
        f'<text x="{_num(fr.x0 + fr.w / 2)}" y="{_num(HL_H - 8)}" text-anchor="middle" '
        'font-size="12.5" style="fill:var(--ink-2)">Round</text>',
        f'<text transform="rotate(-90 15 {_num(fr.y0 + fr.h / 2)})" x="15" '
        f'y="{_num(fr.y0 + fr.h / 2)}" text-anchor="middle" font-size="12.5" '
        'style="fill:var(--ink-2)">Players in the round with the strength</text>',
    ]

    wanted = [fr.cy(result["counts"][c]["total"][-1]) for c in labels]
    placed = _spread(wanted, fr.y0 + 6.0, fr.y1 + 6.0, 17.5)

    for i, cat in enumerate(labels):
        total = list(result["counts"][cat]["total"])
        hue, name = f"var(--s{i})", escape(str(cat))
        attr = escape(str(cat), quote=True)
        ex, ey, ly = fr.cx(len(total) - 1), fr.cy(total[-1]), placed[i]
        pts = _points(fr, total)
        out.append(f'<g data-series="{attr}" data-cat="{attr}">')
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="transparent" '
            'stroke-width="18" pointer-events="stroke"/>'
        )
        out.append(
            f'<polyline points="{pts}" fill="none" style="stroke:var(--surface)" '
            'stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        out.append(
            f'<polyline points="{pts}" fill="none" style="stroke:{hue}" '
            'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        if abs(ly - ey) > 1.5:
            out.append(
                f'<polyline points="{_num(ex + 7)},{_num(ey)} {_num(ex + 17)},{_num(ey)} '
                f'{_num(key_x - 7)},{_num(ly)} {_num(key_x - 2)},{_num(ly)}" fill="none" '
                'style="stroke:var(--muted)" stroke-width="1" opacity="0.6"/>'
            )
        out.append(
            f'<circle cx="{_num(ex)}" cy="{_num(ey)}" r="4" style="fill:{hue};'
            'stroke:var(--surface)" stroke-width="2"/>'
        )
        out.append(
            f'<line x1="{_num(key_x)}" y1="{_num(ly)}" x2="{_num(key_x + 14)}" y2="{_num(ly)}" '
            f'style="stroke:{hue}" stroke-width="3" stroke-linecap="round"/>'
        )
        out.append(
            f'<text x="{_num(name_x)}" y="{_num(ly + 5)}" font-size="15" font-weight="600" '
            f'style="fill:var(--ink)">{name}</text>'
        )
        out.append(
            f'<text x="{_num(val_x)}" y="{_num(ly + 5)}" font-size="13" text-anchor="end" '
            f'style="fill:var(--muted)">{facts[cat]["pool"]}</text>'
        )
        out.append("</g>")
    out.append("</svg>")
    return "".join(out)


def _stack(frame: _Frame, i: int, primary: int, secondary: int, hue: str) -> str:
    """One round's bar: primary from the baseline, secondary stacked above it.

    The two segments are separated by a 2px gap in the surface colour rather than by a
    stroke, so nothing but data carries ink. Only the top of the stack is rounded --
    that cap is where the total stops, and the total is what the line above also plots.
    """
    if primary <= 0 and secondary <= 0:
        return ""
    w = min(9.0, frame.band * 0.46)
    x, base = frame.cx(i) - w / 2.0, frame.y1
    y_p, y_t = frame.cy(primary), frame.cy(primary + secondary)
    both = primary > 0 and secondary > 0
    out = []
    if secondary > 0:
        h = (y_p - 1.0 if both else base) - y_t
        if h > 0.4:
            out.append(
                f'<path d="{_bar_path(x, y_t, w, h, 3.0)}" style="fill:{hue}" '
                'fill-opacity="0.34"/>'
            )
    if primary > 0:
        top = y_p + 1.0 if both else y_p
        h = base - top
        if h > 0.4:
            d = _bar_path(x, top, w, h, 0.0 if both else 3.0)
            out.append(f'<path d="{d}" style="fill:{hue}"/>')
    return "".join(out)


def _panel(result: dict, facts: dict, cat: str, i: int) -> str:
    """One category alone, with the other seven ghosted behind it.

    Emphasis, not eight more colours: the ghosts are a single neutral, so the panel says
    "this one, against the rest" rather than restating the headline chart in miniature.
    The wash past the last round that still holds a player is the finding drawn rather
    than written -- the part of the draft where this category is simply not on the board.
    """
    labels, rounds = list(result["labels"]), list(result["rounds"])
    fr = _Frame(*PN_BOX, len(rounds))
    counts, hue = result["counts"], f"var(--s{i})"
    name, attr = escape(str(cat)), escape(str(cat), quote=True)
    f = facts[cat]
    mid = rounds[len(rounds) // 2]
    x_ticks = sorted({rounds[0], mid, rounds[-1]})

    svg = [
        f'<svg viewBox="0 0 {_num(PN_W)} {_num(PN_H)}" role="img" '
        f'aria-label="{attr} strengths per round, primary and secondary">',
        f"<title>{name} per round</title>",
        _svg_axes(fr, rounds, [0, Y_MAX // 2, Y_MAX], x_ticks, 9.0),
    ]
    last = f["last"]
    if last is not None and last < rounds[-1]:
        gx = fr.cx(rounds.index(last)) + fr.band / 2.0
        svg.append(
            f'<rect x="{_num(gx)}" y="{_num(fr.y0)}" width="{_num(fr.x1 - gx)}" '
            f'height="{_num(fr.h)}" fill="rgb(var(--wash)/0.055)"/>'
            f'<line x1="{_num(gx)}" y1="{_num(fr.y0)}" x2="{_num(gx)}" y2="{_num(fr.y1)}" '
            'style="stroke:var(--rule)" stroke-width="1" shape-rendering="crispEdges"/>'
        )
    ghosts = [
        f'<polyline points="{_points(fr, counts[o]["total"])}" fill="none" '
        'style="stroke:var(--ghost)" stroke-width="1.2" stroke-linejoin="round"/>'
        for o in labels if o != cat
    ]
    svg.append(f'<g opacity="0.22">{"".join(ghosts)}</g>')
    svg.extend(
        _stack(fr, k, counts[cat]["primary"][k], counts[cat]["secondary"][k], hue)
        for k in range(len(rounds))
    )
    pts = _points(fr, counts[cat]["total"])
    svg.append(
        f'<polyline points="{pts}" fill="none" style="stroke:var(--surface)" '
        'stroke-width="4.5" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<polyline points="{pts}" fill="none" style="stroke:{hue}" stroke-width="2.2" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
    )
    svg.append("</svg>")

    if f["pool"]:
        sub = (f'{f["primary"]} primary, {f["secondary"]} secondary. '
               f'Last in round {f["last"]}.')
    else:
        sub = "None in the pool."
    return (
        f'<figure class="panel" data-cat="{attr}" tabindex="0">'
        f'<figcaption class="panel-head">'
        f'<span class="key" style="background:{hue}"></span>'
        f'<span class="panel-name">{name}</span>'
        f'<span class="panel-pool">{f["pool"]}</span></figcaption>'
        f'<p class="panel-sub">{escape(sub)}</p>'
        f'{"".join(svg)}</figure>'
    )


def _table(result: dict, facts: dict) -> str:
    """The same counts as numbers, tinted so the eye can find where a row thins out.

    This is also the report's relief channel: three of the light-mode series colours sit
    below 3:1 on the page surface, and the rule for those is that every value stays
    reachable without them. Here it is, in ink.
    """
    labels, rounds = list(result["labels"]), list(result["rounds"])
    head = "".join(f'<th scope="col">{r}</th>' for r in rounds)
    rows = []
    for i, cat in enumerate(labels):
        total = result["counts"][cat]["total"]
        cells = []
        for v in total:
            cls = "heat zero" if v == 0 else "heat"
            cells.append(f'<td class="{cls}" style="--a:{_num(_heat_alpha(v))}">{v}</td>')
        last = facts[cat]["last"]
        rows.append(
            f'<tr data-cat="{escape(str(cat), quote=True)}">'
            f'<th scope="row" class="cat"><span class="cat-inner">'
            f'<span class="key" style="background:var(--s{i})"></span>'
            f"{escape(str(cat))}</span></th>"
            f'{"".join(cells)}'
            f'<td class="pool">{facts[cat]["pool"]}</td>'
            f'<td class="last">{last if last is not None else "&mdash;"}</td></tr>'
        )
    swatches = "".join(
        f'<li style="--a:{_num(_heat_alpha(v))}"></li>' for v in range(0, Y_MAX + 1, 3)
    )
    return (
        '<div class="tbl-wrap"><table>'
        "<caption>Players per round carrying the category as a primary or secondary "
        "strength.</caption><thead><tr>"
        '<th scope="col" class="cat">Category</th>'
        f"{head}"
        '<th scope="col">Pool</th><th scope="col">Last</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        f'<div class="ramp"><span>0</span><ol>{swatches}</ol>'
        f"<span>{Y_MAX}</span><span>players in the round with the strength</span>"
        "</div>"
    )


def _standfirst(result: dict, facts: dict) -> str:
    """The finding in one sentence, read off the counts rather than written in.

    Nothing here is a constant. The categories named are whichever ones the data puts
    at the extremes, so the sentence stays true if the board, the source or the bands
    change underneath it.
    """
    m = result["meta"]
    live = [c for c in result["labels"] if facts[c]["pool"] > 0]
    opening = (
        f'{m["teams"]} picks to a round, {m["rounds"]} rounds, {m["pool"]} players. '
    )
    if not live:
        return opening + "No player in that pool clears either band."
    deepest = max(live, key=lambda c: (facts[c]["last"] or 0, facts[c]["pool"]))
    earliest = min(live, key=lambda c: (facts[c]["last"] or 0, facts[c]["pool"]))
    if deepest == earliest:
        body = f'{earliest} is spent after round {facts[earliest]["last"]}.'
    else:
        body = (
            f'{earliest} is spent after round {facts[earliest]["last"]}, while '
            f'{deepest} still turns one up in round {facts[deepest]["last"]}.'
        )
    late = [c for c in live if (facts[c]["peak"] or 0) >= 3 and facts[c]["peak_n"] >= 2]
    if late:
        top = max(late, key=lambda c: (facts[c]["peak"], facts[c]["peak_n"]))
        body += f' {top} peaks in round {facts[top]["peak"]}, not round 1.'
    return opening + body


def _masthead(result: dict, facts: dict) -> str:
    """Title, the one-sentence reading, and the provenance of the numbers below it."""
    m = result["meta"]
    items = [
        ("Board", str(m["generated"])),
        ("Source", str(m["source"])),
        ("Digest", str(m["digest"])),
        ("Pool", f'{m["pool"]} ({m["teams"]} × {m["rounds"]})'),
        ("Primary band", f'≥ {float(m["band"]):.2f}'),
        ("Secondary band", f'{float(m["band_sec"]):.2f} to {float(m["band"]):.2f}'),
    ]
    meta = "".join(
        f"<div><dt>{escape(k)}</dt><dd>{escape(v)}</dd></div>" for k, v in items
    )
    return (
        '<header class="masthead"><h1>Category scarcity by round</h1>'
        f'<p class="standfirst">{escape(_standfirst(result, facts))}</p>'
        f'<dl class="meta">{meta}</dl></header>'
    )


def _colophon(result: dict) -> str:
    """What a count is, and what this page is not allowed to contain."""
    m = result["meta"]
    band, band_sec = float(m["band"]), float(m["band_sec"])
    one = (
        f'A count is one player whose {m["source"]} score in that category clears a '
        f"band: {band:.2f} for a primary strength, {band_sec:.2f} for a secondary one. "
        "Most players clear it somewhere, and many clear it more than once, so the "
        f'eight curves add up to well over the {m["pool"]} players in the pool.'
    )
    two = (
        f'Ranks past {m["pool"]} are not counted. The pool is {m["rounds"]} full rounds '
        f'of {m["teams"]}, so every round shares one denominator and the curves compare '
        "end to end. Counts only, with no names, no values and no ranks, from board "
        f'{m["generated"]} at digest {m["digest"]}.'
    )
    return f'<footer class="colophon"><p>{escape(one)}</p><p>{escape(two)}</p></footer>'



#: The reading section. Two cards, a rule between them on wide screens, stacked below.
_READING_CSS = """
.reading{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;
  background:var(--hair);border:1px solid var(--hair);border-radius:4px;
  overflow:hidden;margin:0 0 22px}
@media (max-width:720px){.reading{grid-template-columns:1fr}}
.rd{background:var(--surface);padding:16px 18px 18px;margin:0}
.rd h3{margin:0;font-size:0.9375rem;font-weight:600;letter-spacing:-0.005em}
.rd .rd-sub{margin:2px 0 12px;font-size:0.75rem;color:var(--muted);line-height:1.35}
.rd ul{margin:0;padding:0;list-style:none}
.rd li{display:flex;align-items:baseline;gap:9px;padding:6px 0;
  border-top:1px solid var(--hair);font-size:0.875rem;line-height:1.45}
.rd li:first-child{border-top:0}
.rd .key{width:14px;height:3px;border-radius:2px;flex:0 0 auto;
  position:relative;top:-3px}
.rd .rd-cat{font-weight:600;flex:0 0 auto;min-width:3.1em}
.rd .rd-txt{color:var(--ink-2);font-variant-numeric:tabular-nums}
.upshot{margin:0;max-width:74ch;font-size:0.9375rem;line-height:1.6;color:var(--ink-2)}
.upshot strong{color:var(--ink);font-weight:600}
"""


def _join(names: list[str]) -> str:
    """"A", "A and B", "A, B and C" -- a list that reads as a sentence."""
    if len(names) <= 1:
        return names[0] if names else ""
    return f'{", ".join(names[:-1])} and {names[-1]}'


def _reading(result: dict, facts: dict) -> str:
    """Which categories to buy early, derived from the shape of the curves.

    The split is the one the data makes rather than one chosen in advance: a category
    that never reaches the final round is one the board stops offering, and a category
    still turning players up in the last third is one that can be bought late. Every
    figure here is computed, so a rebuilt board rewrites this section rather than
    leaving a stale claim behind.
    """
    labels = list(result["labels"])
    m = result["meta"]
    n = int(m["rounds"])
    tail = max(1, n // 3)
    t0 = n - tail + 1
    counts = result["counts"]
    late = {c: sum(counts[c]["total"][t0 - 1:]) for c in labels}

    gone = sorted((c for c in labels if facts[c]["last"] is not None
                   and int(facts[c]["last"]) < n), key=lambda c: int(facts[c]["last"]))
    stays = sorted((c for c in labels if c not in gone), key=lambda c: -late[c])
    pools = [int(facts[c]["pool"]) for c in labels]

    def row(cat: str, text: str) -> str:
        i = labels.index(cat)
        return (f'<li><span class="key" style="background:var(--s{i})"></span>'
                f'<span class="rd-cat">{escape(cat)}</span>'
                f'<span class="rd-txt">{escape(text)}</span></li>')

    early_rows = "".join(
        row(c, f'last seen in round {facts[c]["last"]}; {late[c]} left in rounds {t0}-{n}')
        for c in gone)
    late_rows = "".join(
        row(c, f'{late[c]} in rounds {t0}-{n}; peaks in round {facts[c]["peak"]}')
        for c in stays)

    lead = (
        f"Supply is close to even: each category names between {min(pools)} and "
        f"{max(pools)} of the {m['pool']} players in the pool. What separates them is "
        "when that supply arrives, and that is a draft-order question rather than a "
        "ranking one."
    )

    flat = [c for c in labels if facts[c]["peak"] == 1
            and int(facts[c]["peak_n"]) == int(m["teams"])]
    opener = ""
    if flat:
        c = flat[0]
        opener = (
            f"{c} starts at {m['teams']} of {m['teams']} — every player in round one "
            f"carries it, so it separates nobody — and the board stops offering it "
            f"after round {facts[c]['last']}. "
        )

    upshot = (
        opener
        + "The picks worth spending early are the ones on categories that run out, not "
        "the ones that feel scarce. "
        + (f"<strong>{escape(_join(gone))}</strong> thin out before the draft ends; "
           if gone else "")
        + (f"<strong>{escape(_join(stays[:3]))}</strong> are still arriving in the "
           f"last {tail} rounds. " if stays else "")
        + "A pick spent early on a category that keeps coming buys something that was "
        f"available in round {t0}."
    )

    none_row = '<li><span class="rd-txt">None.</span></li>'
    return (
        '<section class="sec"><h2>What to buy early</h2>'
        f'<p class="lede">{escape(lead)}</p>'
        '<div class="reading">'
        '<div class="rd"><h3>Runs out</h3>'
        f'<p class="rd-sub">Never reaches round {n}. Take these while they are there.</p>'
        f'<ul>{early_rows or none_row}</ul></div>'
        '<div class="rd"><h3>Keeps coming</h3>'
        f'<p class="rd-sub">Still turning players up in round {n}. These can wait.</p>'
        f'<ul>{late_rows or none_row}</ul></div>'
        '</div>'
        f'<p class="upshot">{upshot}</p>'
        "</section>"
    )


def render(result: dict) -> str:
    """The whole report as one HTML document."""
    labels = list(result["labels"])
    facts = _facts(result)
    m = result["meta"]
    css = _tokens(labels) + _BASE_CSS + _READING_CSS + _emphasis_css(labels)
    panels = "".join(_panel(result, facts, c, i) for i, c in enumerate(labels))
    title = f'Category scarcity by round — {m["source"]}, board {m["generated"]}'
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{css}</style>\n</head>\n<body>\n"
        '<div class="doc">\n'
        f"{_masthead(result, facts)}\n"
        '<section class="sec"><h2>Where each category runs out</h2>'
        '<p class="lede">One line per category, counting the players in each round of '
        f'{m["teams"]} who carry it as a strength. Shape is the whole reading: a line '
        "that falls to the axis is a category the draft stops offering, and a line that "
        "stays flat is one that will still be there when you want it.</p>"
        f'<div class="plot-wrap">{_line_chart(result, facts)}</div>'
        '<p class="scroll-hint">Scroll the chart sideways to reach the labels.</p>'
        "</section>\n"
        '<section class="sec"><h2>Category by category</h2>'
        f'<p class="lede">The same eight curves, one at a time, every panel on the same '
        f"0 to {Y_MAX} scale so a thin category cannot borrow the look of a deep one. "
        "The bar beneath each point splits that round into primary strengths and the "
        "lighter secondary ones; the other seven categories run faintly behind for "
        "scale; the wash covers the rounds after the last one that still holds a "
        "player.</p>"
        f'<div class="panels">{panels}</div></section>\n'
        '<section class="sec"><h2>The counts in full</h2>'
        '<p class="lede">Every number in the charts above, with the round each category '
        "is last seen in.</p>"
        f"{_table(result, facts)}</section>\n"
        f"{_reading(result, facts)}\n"
        f"{_colophon(result)}\n"
        "</div>\n</body>\n</html>\n"
    )
