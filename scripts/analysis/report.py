"""Render the normality findings as markdown.

All formatting, no measurement: every number here comes from `normality.py` or
`implications.py`. Kept separate so the statistics can be tested without parsing
prose, which is the same split `valuation.py` and `verify.py` already use.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from category_series import label  # noqa: E402
from implications import (  # noqa: E402
    NORMAL_TAIL,
    ROSTER_SIZE,
    SIMULATION_DRAWS,
    SIMULATION_SEED,
    band_yield,
    board_ranking,
    crossings,
    rank_int_z_table,
    rank_movement,
    team_total_moments,
)
from normality import MIN_DISTINCT_FOR_CONTINUOUS_TEST, TIER_A, TIER_B  # noqa: E402
from valuation import CATEGORIES  # noqa: E402

TIER_MEANING = {
    "A": "normal enough — no action",
    "B": "skewed but usable — document",
    "C": "materially non-normal — never read the z as a probability",
    "D": "wrong shape for a z — ranking holds, distances are not calibrated",
}


def cell(value) -> str:
    """One table cell, with pipes escaped.

    `|skew|` and `max |ECDF-Φ|` are natural ways to write these quantities and
    both silently split a markdown row into extra columns. Escaping here means no
    caller has to remember.
    """
    return str(value).replace("|", "\\|")


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(cell(h) for h in headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def p(value: float) -> str:
    """p-values, floored where the source table floors them."""
    if value < 0.001:
        return "<0.001"
    if value <= 0.010:
        return "<=0.010"
    return f"{value:.3f}"


def render(result, values, stats, other, other_stats, export_name: str) -> str:
    pool, players, q = result.pool, result.players, result.q
    this_pool = "converged" if result.converged else "single-pass"
    that_pool = "single-pass" if result.converged else "converged"

    tt = team_total_moments(values)
    yields = band_yield(pool)
    baseline = board_ranking(players, pool, q)
    transformed = board_ranking(players, pool, q, z_table=rank_int_z_table(players, pool))
    move = rank_movement(baseline, transformed)
    cross = crossings(baseline, transformed, q)

    tier_changes = [
        f"{label(c)} ({other_stats[c].tier} -> {stats[c].tier})"
        for c in CATEGORIES if other_stats[c].tier != stats[c].tier
    ]

    L = []
    w = L.append

    w("# Category distribution normality — 2026-27 draft pool\n")
    w(f"- Source: `{export_name}`")
    w(f"- Population: the **{this_pool} rostered pool**, n = {result.n} "
      f"(seed <= {q} and GP >= {result.min_gp:g}; settled in {result.passes} pass"
      f"{'es' if result.passes != 1 else ''}; shortfall {result.shortfall})")
    w("- Measured: the nine series the board standardises, i.e. FG% and FT% as "
      "**volume-weighted impact**, not as rates")
    w(f"- Simulation seed: `{SIMULATION_SEED}` ({SIMULATION_DRAWS:,} draws of a "
      f"{ROSTER_SIZE}-man roster)")
    w("- Regenerate: `python3 scripts/analysis/category_distributions.py`\n")

    w("---\n")
    w("## The finding\n")
    w("Not that the nine categories fail a normality test — they all do, and at this "
      "sample size that says almost nothing. It is that **the tests which detect "
      "non-normality and the properties that actually cost the board something "
      "disagree, in both directions.**\n")
    w("- **3PM passes every moment test and is genuinely the best-behaved category "
      "here** (skew "
      f"{stats['tpm'].skew:+.2f}, and the smallest gap from Normal of the nine at "
      f"{stats['tpm'].ks_max:.3f}). The bimodality an earlier chart appeared to show "
      f"was {stats['tpm'].distinct} distinct reported values drawn into 22 bins — an "
      "artifact of the binning, now fixed.")
    w(f"- **STL fails on discreteness, not shape**: {stats['stl'].distinct} distinct "
      "values across the pool. No standard normality test can tell you that, and "
      "Shapiro-Wilk will happily return a number built on the provider's rounding grid.")
    w("- **The category that measurably costs the board something is BLK**, and the "
      "measurement that finds it is not a p-value: at z = -1 the pool holds "
      f"**{yields['blk']['weak_share']:.1%}** of its players where a Normal promises "
      f"{NORMAL_TAIL:.1%}. That is "
      f"{yields['blk']['weak']} players, not the ~25 the band implies.\n")

    w("## How to read this\n")
    w("Five things constrain every number below.\n")
    w("1. **The pool is a selected sample, not a random one.** It is the top "
      f"{q} by adjusted value with GP >= {result.min_gp:g}, and the selection runs on all "
      "nine categories jointly. Truncation *creates* skew: \"PTS skews "
      f"{stats['pts'].skew:+.2f}\" is a fact about a right-truncated draw, not about NBA "
      "scoring. It is also why these nine tests are not independent of each other.")
    w("2. **Turnovers are shown as reported, where higher is worse.** The valuation "
      f"inverts them, so TO's skew as *valued* is {-stats['to'].skew:+.2f}, not "
      f"{stats['to'].skew:+.2f}.")
    w("3. **FG% and FT% impact are constructions, not observations.** They are "
      "pool-dependent by definition, and their shape is partly the shape of attempts.")
    w("4. **The impact columns should sum to zero and do not, quite.** The provider "
      "rounds its rates to three decimals independently of makes and attempts, leaving "
      f"a residual of {result.fg_residual:+.4f} (FG) and {result.ft_residual:+.4f} (FT) "
      "across the pool. Small enough not to move a skew statistic; printed so this "
      "agrees with the sheet's own \"should be ~0\" cell rather than claiming a cleaner "
      "number.")
    w("5. **p-values are uncorrected, deliberately.** A multiplicity correction controls "
      "false discoveries when screening. Nothing here is screening — every category is "
      "expected to reject, and correcting would make rejection *harder*, biasing the "
      "analysis toward the \"normal enough\" conclusion that most needs guarding "
      "against. The tier rubric is the reading; the p-values are context.\n")

    w("## Verdicts\n")
    w(f"Tiers key off effect size and the gap from Normal. No p-value reaches the "
      f"verdict: at n = {result.n} every category rejects Shapiro-Wilk, so a p-value "
      f"separates none of them.\n")
    w(table(
        ["Category", "Tier", "Skew (z)", "Excess kurt (z)", "max |ECDF-Φ|", "Reason"],
        [[
            label(c), s.tier,
            f"{s.skew:+.2f} ({s.skew_z:+.1f})",
            f"{s.kurt:+.2f} ({s.kurt_z:+.1f})",
            f"{s.ks_max:.3f}",
            s.tier_reason,
        ] for c in CATEGORIES for s in [stats[c]]],
    ))
    w("")
    for t in "ABCD":
        holders = [label(c) for c in CATEGORIES if stats[c].tier == t]
        w(f"- **{t}** — {TIER_MEANING[t]}: {', '.join(holders) if holders else '_none_'}")
    w("")
    w("The thresholds, and why they sit there:\n")
    w(table(
        ["Tier", "Criterion"],
        [
            ["A", f"|skew| < {TIER_A['skew']} **and** |excess kurt| < "
                  f"{TIER_A['kurt']} **and** max|ECDF-Φ| < {TIER_A['ks']} — "
                  "Bulmer's approximately-symmetric band"],
            ["B", f"|skew| < {TIER_B['skew']} **and** |excess kurt| < "
                  f"{TIER_B['kurt']} **and** max|ECDF-Φ| < {TIER_B['ks']} — "
                  "Kline's looser band"],
            ["C", "any of those exceeded"],
            ["D", "a second mode surviving 1.5x Silverman's bandwidth, **or** >10% of "
                  f"the pool on the floor, **or** fewer than "
                  f"{MIN_DISTINCT_FOR_CONTINUOUS_TEST} distinct values"],
        ],
    ))
    w("")
    w("D is not a worse C. It says the mean and SD do not describe the population at "
      "all, so the z still orders players correctly but the *distance* between them "
      "is not a quantity to reason with.\n")

    w("## Descriptives\n")
    w(table(
        ["Category", "n", "Mean", "SD", "Median", "IQR", "5th pct", "95th pct",
         "Distinct values"],
        [[
            label(c), s.n, f"{s.mean:+.3f}", f"{s.sd:.3f}", f"{s.median:+.3f}",
            f"{s.iqr:.3f}", f"{s.p05:+.3f}", f"{s.p95:+.3f}", s.distinct,
        ] for c in CATEGORIES for s in [stats[c]]],
    ))
    w("")

    w("## The test battery\n")
    w(table(
        ["Category", "Shapiro-Wilk W", "√W (Q-Q r)", "SW p", "D'Agostino K²", "K² p",
         "Anderson-Darling A²", "AD p", "Valid?"],
        [[
            label(c), f"{s.shapiro_w:.3f}", f"{s.sqrt_w:.3f}", p(s.shapiro_p),
            f"{s.dagostino_k2:.1f}", p(s.dagostino_p), f"{s.anderson_a2:.2f}",
            p(s.anderson_p),
            "yes" if s.continuous_test_valid else f"**no — {s.distinct} values**",
        ] for c in CATEGORIES for s in [stats[c]]],
    ))
    w("")
    invalid = [label(c) for c in CATEGORIES if not stats[c].continuous_test_valid]
    w(f"**Validity gate.** Shapiro-Wilk and Anderson-Darling assume a continuous "
      f"distribution. {', '.join(invalid)} carry fewer than "
      f"{MIN_DISTINCT_FOR_CONTINUOUS_TEST} distinct values across the pool, so with "
      "roughly ten players sharing each value those two statistics are measuring the "
      "provider's 0.1 reporting grid rather than the shape of the pool. SciPy issues no "
      "warning. Their rows are printed for completeness and should not be compared "
      "against the continuous columns.\n")
    w("**K² is not a third opinion.** D'Agostino-Pearson is exactly "
      "`z_skew² + z_kurt²` — a function of two columns already in the verdict table. "
      "It is here because it decomposes into quantities that can be interpreted, which "
      "W cannot.\n")

    w("### What is deliberately not here\n")
    w(table(
        ["Omitted", "Why"],
        [
            ["Jarque-Bera", "Reads the same two moments as K² but refers them to a "
                            "chi-square(2) null it approaches only asymptotically, and "
                            "slowly. In the low hundreds its p-values are the "
                            "known-miscalibrated ones. A third column restating K² less "
                            "accurately is not a second opinion."],
            ["Filliben's Q-Q r", "To within rounding it *is* √W, already shown."],
            ["Holm-Bonferroni", "See point 5 above — correcting biases toward "
                                "\"normal enough\"."],
            ["Hartigan's dip test", "Not in SciPy; a correct implementation needs the "
                                    "convex minorant plus a bootstrap null. Hand-rolling "
                                    "an unvalidated statistical test into a repo whose "
                                    "first priority is that a wrong number looking right "
                                    "beats no number is the wrong trade — and it would "
                                    "change no verdict here, because the critical "
                                    "bandwidth already separates the multimodal "
                                    "categories cleanly."],
        ],
    ))
    w("")

    w("## What the moments cannot see\n")
    w("The bimodality coefficient is a deterministic function of skew and kurtosis, so "
      "it can only ever repeat what those two already say. On this pool it is wrong in "
      "**both** directions — which is the point of showing it.\n")
    w(table(
        ["Category", "BC", "BC says", "KDE modes", "Second mode survives to",
         "Real structure?"],
        [[
            label(c), f"{s.bimodality_coefficient:.3f}",
            "bimodal" if s.bimodality_coefficient > 0.555 else "unimodal",
            s.kde_modes,
            f"{s.critical_bandwidth:.2f}x" if s.critical_bandwidth else "single mode",
            ("**yes**" if s.critical_bandwidth and s.critical_bandwidth > 1.5
             else "no — dies under mild smoothing" if s.critical_bandwidth else "no"),
        ] for c in CATEGORIES for s in [stats[c]]],
    ))
    w("")
    w(f"BC reads {stats['ft'].bimodality_coefficient:.3f} on FT% impact and "
      f"{stats['blk'].bimodality_coefficient:.3f} on BLK — both *below* its flag, i.e. "
      "\"unimodal\" — and those are precisely the two categories whose second mode "
      f"survives {stats['ft'].critical_bandwidth:.2f}x and "
      f"{stats['blk'].critical_bandwidth:.2f}x Silverman's bandwidth. It then reads "
      f"{stats['reb'].bimodality_coefficient:.3f} on REB, *above* the flag, for a "
      "category with exactly one mode. Heavy tails push BC down; light tails push it "
      "up; neither has anything to do with how many modes there are.\n")
    w("The critical bandwidth is the honest measurement: the smallest smoothing at which "
      "the density goes unimodal, as a multiple of Silverman's rule of thumb. A bump "
      "needing twice that to erase is structure, not sampling noise.\n")

    w("## The measurement that matters\n")
    w("A p-value cannot say how wrong a z-score is. This can: the share of the pool that "
      "actually sits below each z, against what a Normal promises.\n")
    w(table(
        ["Category", "z <= -2", "z <= -1", "z <= +1", "z <= +2", "max gap"],
        [[label(c)] + [f"{s.ecdf_at_z[z]:.1%}" for z in (-2.0, -1.0, 1.0, 2.0)]
         + [f"{s.ks_max:.3f}"] for c in CATEGORIES for s in [stats[c]]],
    ))
    w("")
    w(f"A Normal says {NORMAL_TAIL:.1%} below z = -1, 2.3% below z = -2, "
      f"{1 - NORMAL_TAIL:.1%} below z = +1.\n")
    w(f"**BLK is the outlier.** {stats['blk'].ecdf_at_z[-1.0]:.1%} of the pool sits at or "
      "below one SD under the mean, against 15.9% promised. Blocks are bounded at zero "
      "and the pool's mean is barely one SD above that bound, so the left tail the "
      "z-score prices largely cannot exist. Every \"a standard deviation below average "
      "in blocks\" reading in that category is quoting a probability with no population "
      "behind it.\n")

    w("## Does any of it matter?\n")
    w("Categories are settled on a 13-man roster's total, not on one player, and summing "
      "pulls a total toward Normal however skewed the parts are. That is the argument "
      "ADR-0014 rests on. It had never been computed — only asserted. It holds:\n")
    w(table(
        ["Category", "Player skew", "Team-total skew", "Player kurt", "Team-total kurt"],
        [[
            label(c), f"{tt[c]['player_skew']:+.2f}", f"{tt[c]['team_skew']:+.2f}",
            f"{tt[c]['player_kurt']:+.2f}", f"{tt[c]['team_kurt']:+.2f}",
        ] for c in CATEGORIES],
    ))
    w("")
    w(f"{ROSTER_SIZE} players drawn without replacement, {SIMULATION_DRAWS:,} draws, seed "
      f"`{SIMULATION_SEED}`. Without replacement because a roster cannot hold the same "
      "player twice; that induces slight negative dependence, so the real flattening is "
      "at least this good. The two impacts are summed as if roster-additive, which is an "
      "approximation — a team's FG% is its own attempt-weighted aggregate — but the "
      "direction is unaffected.\n")
    w(f"Every category lands inside the approximately-symmetric band at roster level. "
      f"BLK goes {tt['blk']['player_skew']:+.2f} -> {tt['blk']['team_skew']:+.2f} and FT% "
      f"impact {tt['ft']['player_skew']:+.2f} -> {tt['ft']['team_skew']:+.2f}. **The "
      "non-normality is real at the player level and mostly gone by the level decisions "
      "are made at.**\n")

    w("## Where it does bite: the ±1.00 band\n")
    w("`CATEGORY_BAND` names a player strong or weak at one SD. If the category were "
      f"Normal that would name about {NORMAL_TAIL:.1%} of the pool on each side.\n")
    w(table(
        ["Category", "Strong", "Strong %", "Weak", "Weak %"],
        [[
            label(c), y["strong"], f"{y['strong_share']:.1%}",
            y["weak"], f"{y['weak_share']:.1%}",
        ] for c in CATEGORIES for y in [yields[c]]],
    ))
    w("")
    w("The strong side is well calibrated — ADR-0013 tuned it there. The weak side on "
      f"blocks is not: **{yields['blk']['weak']} players**, "
      f"{yields['blk']['weak_share']:.1%}, against the ~25 the band implies. ADR-0013 "
      "already records this as a known limitation in the words \"roughly five players\"; "
      "this is that limitation with a derivation behind it.\n")
    w("**The band should be read as a yield, not as a probability.** That is a "
      "documentation change, not a math change, and it is the one place the board is "
      "genuinely mis-calibrated today.\n")

    w("## The counterfactual: what forcing them Gaussian would cost\n")
    w("Rank-based inverse normal (Blom), fitted per category over all ranked players, "
      "then the board rebuilt from it. The baseline is `valuation.py`'s own ordering, "
      "reproduced exactly before the transform is applied.\n")
    w(table(
        ["Measure", "Value"],
        [
            ["Spearman vs the current board", f"{move['spearman']:.4f}"],
            ["Mean absolute movement", f"{move['mean_places']:.1f} places"],
            ["Largest single move", f"{move['max_places']:.0f} places"],
            ["Players moving 10+ places", f"{move['moved_10_plus']} of {len(baseline)}"],
            ["…of those, inside the top 50", str(move["moved_10_plus_in_top_50"])],
            [f"Players crossing the drafted-{q} line", str(cross)],
        ],
    ))
    w("")
    w("ADR-0014 rejected Yeo-Johnson at 18.6 mean places as \"not marginal\". This is "
      f"{move['mean_places']:.1f} — cheaper, but for a strictly more destructive "
      "transform: rank-INT maps every category onto an identical Gaussian, so the gap "
      "between the best blocker and the second best collapses to the gap between the top "
      "two order statistics of a standard Normal, whether he blocks 3.8 or 2.1. In a "
      "category league you win blocks with blocks.\n")
    w("There is a structural cost the movement figures do not show. **Rank-INT destroys "
      "the mean-zero identity of the impact columns.** They sum to zero over the pool "
      "only because the pool rate is the attempt-weighted aggregate; that is why the "
      "board divides by SD with no centring term, it is pinned by "
      "`tests/test_valuation.py`, and it is a live `Build.gs` formula. Transform the "
      "column and every one of those needs a centring term, an ADR superseding 0012 and "
      "0014 in part, and a sheet rebuild.\n")

    w("## Recommendation\n")
    w("**Accept and document. Change nothing in the valuation.**\n")
    w("1. **Do not transform.** ADR-0014 declined already; the team-total simulation "
      "above is the evidence it asserted without deriving. The flattening is real and "
      "large.")
    w("2. **Do not winsorize.** At n = "
      f"{result.n} a 99th-percentile cap touches about 1.5 players per tail, and it "
      "changes the SD, which changes every z in that category — a global edit to fix two "
      "rows. On FT% impact the low tail *is* the signal: a poor free-throw shooter on "
      "high volume genuinely loses you the category, and capping him deletes exactly what "
      "the volume weighting exists to price.")
    w("3. **Re-read the ±1.00 band as a yield target rather than an SD**, and say so "
      "wherever the Category profile column is documented. Costs no code.")
    w("4. **Add a post-refresh falsifier.** Re-run this after each export and check no "
      "category has changed tier. A tier change means the pool's composition moved, which "
      "is a real signal; nothing would notice it today.")
    w("5. **Route bounded, win-probability-based saturation to its own ADR.** ADR-0014 "
      "explicitly leaves it open, it needs no distributional assumption, and it is the "
      "one alternative these measurements strengthen. It should not be smuggled in "
      "through a normality report.\n")

    w("## Robustness: does the pool choice change anything?\n")
    w(f"The live sheet has never had its re-seed action run, so it currently holds the "
      f"{that_pool} pool. Running the same battery over both:\n")
    w(table(
        ["Category", f"Tier ({this_pool})", f"Tier ({that_pool})",
         f"Skew ({this_pool})", f"Skew ({that_pool})"],
        [[
            label(c), stats[c].tier, other_stats[c].tier,
            f"{stats[c].skew:+.2f}", f"{other_stats[c].skew:+.2f}",
        ] for c in CATEGORIES],
    ))
    w("")
    if tier_changes:
        w(f"**{len(tier_changes)} of the nine change tier between the two pools, "
          f"{that_pool} -> {this_pool}: {', '.join(tier_changes)}.** Everything else is "
          "robust. That is a reason to run the re-seed, not a reason to distrust either "
          "number — but any claim about those categories has to name which pool it means.")
    else:
        w("**No verdict changes between the two pools.** Everything below is robust to "
          "whether the re-seed has been run.")
    w("")
    overlap = len(set(baseline[:q]) & {p_.name for p_ in other.pool.members})
    w(f"The two pools share {overlap} of {q} members.\n")

    w("## Reconciliation with what the repo already says\n")
    w("`docs/references/basketball-monster-durant.md` quotes pool moments in two places "
      "and they do not match each other, because they are measured over two different "
      "pools without saying so: BLK skew **+1.53** in the Lloyd section (single-pass) "
      "and **+1.60** in the DURANT section (converged). ADR-0014, which is Accepted and "
      "must not be edited, carries the single-pass pair.\n")
    w(f"This report's figures are the **{this_pool}** pool: BLK "
      f"{stats['blk'].skew:+.2f} / {stats['blk'].kurt:+.2f}, FT% impact "
      f"{stats['ft'].skew:+.2f} / {stats['ft'].kurt:+.2f}. The "
      f"{that_pool} pair is in the robustness table above. Neither is wrong; they answer "
      "different questions. Until now nothing in the repository computed a skew, so "
      "every such figure in the docs was produced ad hoc and could not be re-derived — "
      "which is how two pools ended up quoted in one document.\n")

    w("---\n")
    w("Charts accompany this file in the same folder, one per category, each with the "
      "Normal the z-score assumes drawn over it.\n")
    return "\n".join(L) + "\n"
