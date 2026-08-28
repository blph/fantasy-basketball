"""Tests for the mock draft reviewer.

Every fixture here is synthetic: invented players, invented numbers, shaped like
the two board pulls but never copied from `data/` or the sheet. The repo is
public and provider data is not ours to republish (ADR-0006).

The cases are chosen for what would silently produce a wrong review rather than
an error — a percentage averaged instead of aggregated, a snake seat off by one,
a forced pick graded as a choice.
"""

import pytest
import review_mock_draft as rv

# --- Synthetic fixtures -----------------------------------------------------
# Shapes only. Draft Board is 26 wide (A2:Z202); Board is 73 wide (A3:CA202).


def db_row(rank, tier, name, *, adjval=5.0, mygp=72, adp=None, gap=None, pos="PG"):
    row = [""] * 26
    row[rv.DB_RANK] = str(rank)
    row[rv.DB_TIER] = str(tier)
    row[rv.DB_NAME] = name
    row[rv.DB_TEAM] = "BOS"
    row[rv.DB_POS] = pos
    row[rv.DB_ADJVAL] = f"{adjval}"
    row[rv.DB_MYGP] = str(mygp)
    row[rv.DB_ADP] = "" if adp is None else str(adp)
    row[rv.DB_GAP] = "" if gap is None else str(gap)
    return row


def detail_row(name, *, gp=72, fgm=5.0, fga=10.0, ftm=2.0, fta=2.5, line=None, g=None, punt=None):
    """One Board row. `line` sets the seven counting stats, `g` the g-scores."""
    row = [""] * rv.DETAIL_WIDTH
    row[rv.COL_NAME] = name
    row[rv.COL_GP] = str(gp)
    row[rv.COL_RAW["fgm"]] = str(fgm)
    row[rv.COL_RAW["fga"]] = str(fga)
    row[rv.COL_RAW["fgp"]] = str(fgm / fga)
    row[rv.COL_RAW["ftm"]] = str(ftm)
    row[rv.COL_RAW["fta"]] = str(fta)
    row[rv.COL_RAW["ftp"]] = str(ftm / fta)
    for k, v in (line or {}).items():
        row[rv.COL_RAW[k]] = str(v)
    for i, k in enumerate(rv.GKEYS):
        row[rv.COL_G0 + i] = str((g or {}).get(k, 0.0))
    row[rv.COL_GTOT] = str(sum((g or {}).values()))
    row[rv.COL_VOR] = str(sum((g or {}).values()) + 2.0)  # replacement of -2.0
    for i, b in enumerate(rv.PUNTS):
        row[rv.COL_PUNT0 + i] = str((punt or {}).get(b, 0.0))
    return row


COUNTS = {"tpm": 2.0, "pts": 20.0, "reb": 5.0, "ast": 4.0, "stl": 1.0, "blk": 0.5, "to": 2.0}


# --- Snake order ------------------------------------------------------------


def test_snake_slots_matches_a_14_team_seat():
    """Slot 10 of 14 sits at these overall picks. An off-by-one here silently
    reviews someone else's draft."""
    assert rv.snake_slots(14, 13, 10) == [10, 19, 38, 47, 66, 75, 94, 103, 122, 131, 150, 159, 178]


def test_snake_slots_endpoints_mirror():
    assert rv.snake_slots(12, 4, 1) == [1, 24, 25, 48]
    assert rv.snake_slots(12, 4, 12) == [12, 13, 36, 37]


def test_snake_slots_rejects_a_seat_outside_the_league():
    with pytest.raises(rv.ReviewError):
        rv.snake_slots(12, 3, 13)


# --- Name normalisation -----------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Kristaps Porziņģis", "Kristaps Porzingis"),
        ("Nikola Jokić", "Nikola Jokic"),
        ("Alperen Şengün", "Alperen Sengun"),
        ("Jabari Smith Jr.", "Jabari Smith"),
        ("Trey Murphy III", "Trey Murphy"),
    ],
)
def test_norm_joins_spelling_variants(a, b):
    """A failed join drops a player from a roster without erroring."""
    assert rv.norm(a) == rv.norm(b)


def test_norm_keeps_distinct_players_distinct():
    assert rv.norm("Jalen Williams") != rv.norm("Jaylin Williams")


# --- Cell parsing -----------------------------------------------------------


def test_num_reads_the_sheets_minus_sign_and_explicit_plus():
    assert rv.num("−2.10") == pytest.approx(-2.10)
    assert rv.num("+1.93") == pytest.approx(1.93)
    assert rv.num("") is None
    assert rv.num(None) is None


# --- Team totals ------------------------------------------------------------


def test_team_fg_pct_is_makes_over_attempts_not_a_mean_of_rates():
    """The single most common way to get a 9-cat board wrong (AGENTS.md).

    A volume shooter at 50% on 20 attempts and a bench player at 100% on 1.
    Aggregating gives 11/21; averaging the rates gives 75%.
    """
    players = {
        rv.norm("Volume"): rv.Player(name="Volume", rank=1, tier=1, mygp=72),
        rv.norm("Sniper"): rv.Player(name="Sniper", rank=2, tier=1, mygp=72),
    }
    rows = [
        detail_row("Volume", fgm=10.0, fga=20.0, line=COUNTS),
        detail_row("Sniper", fgm=1.0, fga=1.0, line=COUNTS),
    ]
    rv.parse_board_detail(rows, players)

    totals = rv.team_totals(list(players), players, divisor=72.0, size=2)

    assert totals["fgp"] == pytest.approx(11.0 / 21.0)
    assert totals["fgp"] != pytest.approx(0.75)


def test_totals_scale_by_games_played():
    """Half a season contributes half the counting stats (playbook s6a)."""
    players = {rv.norm("Half"): rv.Player(name="Half", rank=1, tier=1, mygp=36)}
    rv.parse_board_detail([detail_row("Half", line=COUNTS)], players)

    totals = rv.team_totals(list(players), players, divisor=72.0, size=1)

    assert totals["pts"] == pytest.approx(10.0)  # 20.0 x 36/72


def test_short_rosters_scale_up_so_teams_stay_comparable():
    """Some drafted players fall outside the board; the rest carry the team."""
    players = {rv.norm("Only"): rv.Player(name="Only", rank=1, tier=1, mygp=72)}
    rv.parse_board_detail([detail_row("Only", line=COUNTS)], players)

    totals = rv.team_totals(["only", "unmatched-name"], players, divisor=72.0, size=2)

    assert totals["pts"] == pytest.approx(40.0)  # one matched player, scaled to two


# --- Category comparison ----------------------------------------------------


def test_turnovers_run_the_other_way():
    lo, hi = {"to": 10.0}, {"to": 20.0}
    assert rv.beats(lo, hi, "to")
    assert not rv.beats(hi, lo, "to")


# --- Category tracker -------------------------------------------------------


def _tracker_players():
    """Ten identical benchmark players, plus one roster player who trails on
    rebounds and leads on points."""
    players, rows = {}, []
    for i in range(1, 11):
        name = f"Bench {i:02d}"
        players[rv.norm(name)] = rv.Player(name=name, rank=i + 1, tier=1, mygp=72)
        rows.append(detail_row(name, line=COUNTS))
    players[rv.norm("Mine")] = rv.Player(name="Mine", rank=1, tier=1, mygp=72)
    rows.append(detail_row("Mine", line={**COUNTS, "reb": 1.0, "pts": 40.0}))
    rv.parse_board_detail(rows, players)
    return players


def test_tracker_reads_weak_strong_and_even():
    players = _tracker_players()
    bands = {"fgp": 0.005, "ftp": 0.010, "counting": 0.08}

    trace = rv.tracker_trace(["mine"], players, teams=4, bands=bands)[0]

    assert trace["reb"] == "WEAK"  # 1.0 against a benchmark of 5.0
    assert trace["pts"] == "STRONG"  # 40.0 against 20.0
    assert trace["ast"] == "EVEN"  # identical to the benchmark


def test_needs_exclude_strong_categories():
    """Playbook s10, printed on the tracker: spend on EVEN, not STRONG."""
    row = dict.fromkeys(rv.CATS, "EVEN")
    row["pts"] = "STRONG"
    row["reb"] = "WEAK"

    needs = rv.needs_from_trace(row)

    assert "pts" not in needs
    assert "reb" in needs


# --- Build detection --------------------------------------------------------


def test_detect_build_picks_the_highest_scoring_column():
    players = {rv.norm("A"): rv.Player(name="A", rank=1, tier=1)}
    rv.parse_board_detail([detail_row("A", punt={"FG%+REB": 9.0, "AST": 1.0})], players)

    ranked = rv.detect_build(["a"], players)

    assert ranked[0][0] == "FG%+REB"
    assert ranked[0][1] == pytest.approx(9.0)


# --- Marginal value ---------------------------------------------------------


def test_marginal_value_peaks_at_the_coin_flip():
    """Playbook s10: capital in a category already won is nearly as wasted as
    capital in one abandoned."""
    assert rv.marginal_value(0.50) > rv.marginal_value(0.95)
    assert rv.marginal_value(0.50) > rv.marginal_value(0.05)
    assert rv.marginal_value(0.50) == pytest.approx(1.09)


def test_marginal_value_clamps_outside_the_table():
    assert rv.marginal_value(0.0) == pytest.approx(0.31)
    assert rv.marginal_value(1.0) == pytest.approx(0.26)


def test_closest_archetype_matches_on_shape():
    name, _, dist = rv.closest_archetype([0.63] * 9)
    assert name == "Balanced"
    assert dist == pytest.approx(0.0)


# --- Grading ----------------------------------------------------------------


def test_a_forced_pick_is_not_graded_on_choice():
    """A tier of one gave the manager no decision to get wrong."""
    forced = rv.grade_pick(
        round_no=5,
        adjv_rank=1,
        n_tier=1,
        my_need=-5.0,
        best_need=5.0,
        gap=None,
        mygp=72,
        pool_avg_gp=72,
    )
    assert forced.forced
    assert forced.components["value"] == 0.0
    assert forced.components["fit"] == 0.0
    assert forced.score == pytest.approx(rv.BASE_SCORE)


def test_poor_fit_inside_a_wide_tier_is_penalised():
    graded = rv.grade_pick(
        round_no=5,
        adjv_rank=1,
        n_tier=10,
        my_need=-2.0,
        best_need=4.0,
        gap=None,
        mygp=72,
        pool_avg_gp=72,
    )
    assert graded.components["fit"] == pytest.approx(-3.5)  # capped
    assert graded.score == pytest.approx(rv.BASE_SCORE - 3.5)


def test_gap_and_availability_move_the_score_in_opposite_directions():
    cheap = rv.grade_pick(
        round_no=5,
        adjv_rank=1,
        n_tier=5,
        my_need=0.0,
        best_need=0.0,
        gap=50,
        mygp=72,
        pool_avg_gp=72,
    )
    fragile = rv.grade_pick(
        round_no=5,
        adjv_rank=1,
        n_tier=5,
        my_need=0.0,
        best_need=0.0,
        gap=None,
        mygp=50,
        pool_avg_gp=72,
    )
    assert cheap.components["market"] == pytest.approx(1.0)  # clamped
    assert fragile.components["availability"] == pytest.approx(-1.5)  # clamped
    assert cheap.score > fragile.score


def test_s8_violation_needs_both_close_value_and_better_fit():
    """s8 step 4's tiebreak only fires when value is close. A better fit a long
    way down the board is the tiebreak correctly declining to fire."""
    mine = rv.Player(name="Mine", rank=1, tier=1, adjval=5.00, g=dict.fromkeys(rv.GKEYS, 0.0))
    near = rv.Player(name="Near", rank=2, tier=1, adjval=4.95, g=dict.fromkeys(rv.GKEYS, 1.0))
    far = rv.Player(name="Far", rank=3, tier=1, adjval=1.00, g=dict.fromkeys(rv.GKEYS, 1.0))

    assert rv.s8_violated(mine, [mine, near], rv.CATS)
    assert not rv.s8_violated(mine, [mine, far], rv.CATS)


def test_rounds_one_and_two_cannot_violate_the_round_plan():
    """s9 says commit to nothing early, so a poor need-fit there is the plan."""
    p = rv.Player(name="P", rank=1, tier=1, g={**dict.fromkeys(rv.GKEYS, 0.0), "pts": 3.0})
    strong = {**dict.fromkeys(rv.CATS, "EVEN"), "pts": "STRONG"}

    assert not rv.s9_violated(1, p, strong)
    assert not rv.s9_violated(2, p, strong)
    assert rv.s9_violated(8, p, strong)  # rounds 7-10 must fill weak categories


# --- Guards -----------------------------------------------------------------


def test_replacement_mismatch_stops_the_line():
    """Every value on the board is measured against replacement. A mismatch
    means a stale pull, and nothing computed after it would mean anything."""
    players = {rv.norm("A"): rv.Player(name="A", rank=1, tier=1)}
    rv.parse_board_detail([detail_row("A", g={"pts": 1.0})], players)

    assert rv.check_replacement(players, -2.0) == pytest.approx(-2.0)
    with pytest.raises(rv.ReviewError, match="stale"):
        rv.check_replacement(players, -3.0)


def test_a_draft_board_range_with_no_players_is_an_error():
    with pytest.raises(rv.ReviewError):
        rv.parse_draft_board([["", ""] * 13])


def test_draft_log_requires_four_fields():
    with pytest.raises(rv.ReviewError, match="4 fields"):
        rv.parse_draft_log([["1", "1", "Manager"]])


def test_draft_log_skips_its_header():
    log = rv.parse_draft_log([["round", "pick", "manager", "player"], ["1", "1", "Me", "A"]])
    assert log == [(1, 1, "Me", "A")]


def test_tier_alternatives_never_leaves_the_tier():
    """The failure this whole module exists to prevent."""
    players = {
        "a": rv.Player(name="A", rank=1, tier=4, g={"pts": 1.0}),
        "b": rv.Player(name="B", rank=2, tier=4, g={"pts": 1.0}),
        "c": rv.Player(name="C", rank=3, tier=7, g={"pts": 9.0}),
    }

    shortlist = rv.tier_alternatives("a", players, taken=set())

    assert {p.name for p in shortlist} == {"A", "B"}


# --- Gap to flip ------------------------------------------------------------


def test_next_flip_measures_the_weakest_opponent_still_winning():
    """Regression: the comparison was inverted, so it reported the distance to
    sweeping a category rather than to winning one more matchup — which is not
    a decision anyone makes."""
    mine = dict.fromkeys(rv.CATS, 0.0)
    mine["reb"] = 60.0
    opponents = [
        {**dict.fromkeys(rv.CATS, 0.0), "reb": 61.0},  # the cheap flip
        {**dict.fromkeys(rv.CATS, 0.0), "reb": 90.0},  # far out of reach
    ]

    row = rv.gap_to_flip(mine, opponents)["reb"]

    assert row["won"] == 0
    assert row["next_flip"] == pytest.approx(1.0)


def test_next_flip_inverts_for_turnovers():
    """Fewer is better, so the cheapest flip is the largest count still under."""
    mine = dict.fromkeys(rv.CATS, 0.0)
    mine["to"] = 20.0
    opponents = [
        {**dict.fromkeys(rv.CATS, 0.0), "to": 19.0},  # the cheap flip
        {**dict.fromkeys(rv.CATS, 0.0), "to": 5.0},  # far out of reach
    ]

    row = rv.gap_to_flip(mine, opponents)["to"]

    assert row["won"] == 0
    assert row["next_flip"] == pytest.approx(1.0)


def test_surplus_measures_the_closest_rival_still_beaten():
    """The margin that could be given up and still keep the category."""
    mine = dict.fromkeys(rv.CATS, 0.0)
    mine["pts"] = 100.0
    opponents = [
        {**dict.fromkeys(rv.CATS, 0.0), "pts": 99.0},  # closest
        {**dict.fromkeys(rv.CATS, 0.0), "pts": 10.0},
    ]

    row = rv.gap_to_flip(mine, opponents)["pts"]

    assert row["lost"] == 0
    assert row["surplus"] == pytest.approx(1.0)


def test_rounds_one_and_two_are_exempt_from_the_fit_term():
    """Playbook s9: take best available and commit to nothing. A lopsided
    first-round pick is the plan working, not a mistake."""
    kw = dict(
        adjv_rank=1,
        n_tier=8,
        my_need=-3.0,
        best_need=5.0,
        gap=None,
        mygp=72,
        pool_avg_gp=72,
    )
    assert rv.grade_pick(round_no=1, **kw).components["fit"] == 0.0
    assert rv.grade_pick(round_no=2, **kw).components["fit"] == 0.0
    assert rv.grade_pick(round_no=3, **kw).components["fit"] < 0.0


def test_market_timing_cannot_buy_back_a_fit_failure():
    """Regression: the bonus once saturated and the score clamped at the top,
    so every pick with a large GAP graded A+ regardless of roster fit."""
    kw = dict(
        round_no=6,
        adjv_rank=1,
        n_tier=8,
        my_need=-3.0,
        best_need=3.0,
        mygp=72,
        pool_avg_gp=72,
    )
    assert rv.grade_pick(gap=200, **kw).score < 9.0


def test_domination_on_both_axes_is_penalised():
    """Higher Adjusted Value and better fit leaves no reading under which the
    pick was right."""
    mine = rv.Player(name="Mine", rank=2, tier=1, adjval=3.0, g=dict.fromkeys(rv.GKEYS, 0.0))
    better = rv.Player(name="Better", rank=1, tier=1, adjval=4.0, g=dict.fromkeys(rv.GKEYS, 1.0))
    cheaper = rv.Player(name="Cheap", rank=3, tier=1, adjval=1.0, g=dict.fromkeys(rv.GKEYS, 1.0))

    assert rv.dominated_by_tier_mate(mine, [mine, better], rv.CATS)
    assert not rv.dominated_by_tier_mate(mine, [mine, cheaper], rv.CATS)


def test_a_forced_pick_is_never_marked_dominated():
    graded = rv.grade_pick(
        round_no=6,
        adjv_rank=1,
        n_tier=1,
        my_need=-9.0,
        best_need=9.0,
        gap=None,
        mygp=72,
        pool_avg_gp=72,
        dominated=True,
    )
    assert graded.components["dominated"] == 0.0
