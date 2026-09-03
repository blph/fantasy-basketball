"""The injury-risk rubric, and the gates that stop a wrong tier looking like a right one.

Every fixture here is synthetic (ADR-0006): invented players, invented injuries, invented
URLs. Nothing in this file came off a real injury report.

The tier is the whole point of the column, so the tests are about what moves it: recency,
the difference between a recurring problem and a freak one, and the two places the score
is overridden outright.
"""

import json

import injury_risk as IR
import pytest


def event(**over):
    """A minimal valid event. Override one key to isolate one term."""
    e = {
        "season": "2025-26",
        "date": "2026-01-15",
        "body_part": "left ankle",
        "diagnosis": "ankle sprain",
        "kind": "joint",
        "mechanism": "acute",
        "games_missed": 10,
        "surgery": "none",
        "lower_body": True,
        "sources": [
            {
                "url": "https://example.invalid/a",
                "publisher": "Example",
                "author": None,
                "date": "2026-01-16",
            }
        ],
    }
    e.update(over)
    return e


def record(**over):
    """A durable 27-year-old wing with nothing wrong. The LOW baseline."""
    r = {
        "key": "quinnhollowaymarsh",
        "name": "Quinn Holloway-Marsh",
        "as_of": "2026-09-02",
        "age": 27,
        "pos_group": "wing",
        "gp": {"2025-26": 79, "2024-25": 78, "2023-24": 80, "2022-23": 77},
        "events": [],
        "sources": [{"url": "https://example.invalid/quinn", "publisher": "Example",
                     "date": "2026-09-01"}],
        "load_management": False,
        "open_status": "healthy",
        "expert_reads": [],
        "suggested_tier": "LOW",
        "rationale": "no games lost to injury in four seasons",
        "confidence": "high",
        "coverage": "full",
    }
    r.update(over)
    return r


# ------------------------------------------------------------------ the baseline


def test_durable_player_is_low():
    assert IR.tier(record()) == "LOW"


def test_score_breaks_out_every_term():
    s = IR.score(record())
    assert s["total"] == 0
    assert (s["surgery"], s["chronic"], s["age"], s["position"]) == (0, 0, 0, 0)


def test_games_played_or_missed_never_moves_the_score():
    """The whole point of this rubric: injury history only, never durability."""
    durable = record(events=[])
    same_history_different_workload = record(
        events=[event(season="2025-26", games_missed=55)]
    )
    # A single acute event with a large games_missed count changes nothing about the
    # score -- only surgery/chronic/age/position terms do, and this event sets none of
    # them (mechanism is the default "acute", surgery "none").
    assert IR.score(durable)["total"] == IR.score(same_history_different_workload)["total"]


# ------------------------------------------------------------------ freak events


def test_a_freak_event_never_counts_toward_recurrence():
    """Two freak events on one body part are not a chronic problem."""
    r = record(
        events=[
            event(
                season="2025-26", body_part="face", kind="bone", mechanism="freak", lower_body=False
            ),
            event(
                season="2024-25", body_part="face", kind="bone", mechanism="freak", lower_body=False
            ),
        ]
    )
    assert IR.chronic_points(r)[0] == 0


# ------------------------------------------------------------------ recurrence


def test_the_same_joint_across_two_seasons_scores_chronic():
    r = record(
        events=[
            event(season="2025-26", body_part="left knee"),
            event(season="2024-25", body_part="left knee"),
        ]
    )
    pts, part = IR.chronic_points(r)
    assert (pts, part) == (IR.CHRONIC_TWO, "knee")


def test_three_seasons_scores_higher_than_two():
    two = record(events=[event(season=s, body_part="knee") for s in ("2025-26", "2024-25")])
    three = record(
        events=[event(season=s, body_part="knee") for s in ("2025-26", "2024-25", "2023-24")]
    )
    assert IR.chronic_points(three)[0] > IR.chronic_points(two)[0]


def test_left_and_right_group_to_one_joint():
    """Both sides of one joint failing is the same signal as one side failing twice."""
    r = record(
        events=[
            event(season="2025-26", body_part="left hamstring", kind="soft_tissue"),
            event(season="2024-25", body_part="right hamstring", kind="soft_tissue"),
        ]
    )
    assert IR.chronic_points(r) == (IR.CHRONIC_TWO + IR.SOFT_TISSUE_BONUS, "hamstring")


def test_a_compound_description_still_groups_with_a_plain_one():
    """"leg/ankle" and "ankle/calf/knee" describe the same recurring ankle problem."""
    r = record(
        events=[
            event(season="2025-26", body_part="left knee"),
            event(season="2024-25", body_part="right leg/ankle"),
            event(season="2023-24", body_part="ankle/calf/knee"),
        ]
    )
    pts, part = IR.chronic_points(r)
    assert pts == IR.CHRONIC_THREE
    assert part == "knee"


def test_a_third_event_can_bridge_two_that_do_not_directly_overlap():
    """Ankle links knee and calf into one cluster even though knee and calf never touch."""
    r = record(
        events=[
            event(season="2025-26", body_part="knee"),
            event(season="2024-25", body_part="ankle/knee"),
            event(season="2023-24", body_part="calf/ankle"),
        ]
    )
    pts, _part = IR.chronic_points(r)
    assert pts == IR.CHRONIC_THREE


def test_two_different_old_injuries_do_not_collapse_into_one():
    """Both events are dated only to "older" but are two distinct occurrences."""
    r = record(
        events=[
            event(season="older", date="2018-02", body_part="knee", surgery="major"),
            event(season="older", date="2020-06", body_part="knee", surgery="major"),
        ]
    )
    assert IR.chronic_points(r)[0] == IR.CHRONIC_TWO


def test_two_strains_in_one_season_still_count_as_recurrence():
    """A re-strain ten weeks later is the single most literal case of "recurring"."""
    r = record(
        events=[
            event(season="2025-26", date="2026-02-05", body_part="left hamstring",
                  kind="soft_tissue"),
            event(season="2025-26", date="2026-04-02", body_part="left hamstring",
                  kind="soft_tissue"),
        ]
    )
    assert IR.chronic_points(r) == (IR.CHRONIC_TWO + IR.SOFT_TISSUE_BONUS, "hamstring")


def test_the_same_undated_old_injury_reported_twice_does_not_double_count():
    """No date on either -- they disambiguate by position, so this is still one event."""
    r = record(events=[event(season="older", date=None, body_part="knee", surgery="major")])
    assert IR.chronic_points(r)[0] == 0  # one occurrence is not a recurrence


def test_soft_tissue_recurrence_scores_above_joint_recurrence():
    soft = record(
        events=[
            event(season=s, body_part="hamstring", kind="soft_tissue")
            for s in ("2025-26", "2024-25")
        ]
    )
    joint = record(
        events=[event(season=s, body_part="ankle", kind="joint") for s in ("2025-26", "2024-25")]
    )
    assert IR.chronic_points(soft)[0] > IR.chronic_points(joint)[0]


def test_one_season_alone_is_not_chronic():
    r = record(events=[event(season="2025-26"), event(season="2025-26")])
    assert IR.chronic_points(r)[0] == 0


# ------------------------------------------------------------------ surgery


def test_surgery_takes_the_worst_not_the_sum():
    """A repair and the clean-up that follows it are one problem, not two."""
    r = record(
        events=[
            event(season="2025-26", body_part="knee", surgery="major"),
            event(season="2024-25", body_part="knee", surgery="major"),
            event(season="2024-25", body_part="knee", surgery="minor"),
        ]
    )
    assert IR.surgery_points(r) == IR.MAJOR_LOWER


def test_an_old_major_surgery_counts_for_less():
    recent = record(events=[event(season="2025-26", surgery="major")])
    old = record(events=[event(season="2023-24", surgery="major")])
    assert IR.surgery_points(recent) > IR.surgery_points(old)


def test_a_career_spanning_major_surgery_still_scores_something():
    """The schema tells an agent to report an "older" event only when it is a major
    surgery or an established pattern -- exactly the case this term must not zero out."""
    ancient = record(events=[event(season="older", date="2018-02", surgery="major")])
    assert IR.surgery_points(ancient) > 0
    assert IR.surgery_points(ancient) == IR.surgery_points(
        record(events=[event(season="2023-24", surgery="major")])
    )


def test_upper_body_surgery_counts_for_less_than_lower():
    lower = record(events=[event(season="2025-26", surgery="major", lower_body=True)])
    upper = record(
        events=[event(season="2025-26", surgery="major", lower_body=False, body_part="shoulder")]
    )
    assert IR.surgery_points(lower) > IR.surgery_points(upper)


# ------------------------------------------------------------------ overrides


def test_major_lower_body_surgery_inside_twelve_months_forces_high():
    """Whatever else the record says. An Achilles in March is not a MED."""
    r = record(
        age=24,
        pos_group="big",
        events=[
            event(
                season="2025-26",
                date="2026-03-01",
                body_part="achilles",
                kind="tendon",
                surgery="major",
                games_missed=2,
            )
        ],
    )
    s = IR.score(r)
    assert s["total"] < IR.CUT_HIGH
    assert s["tier"] == "HIGH"
    assert "12 months" in s["reason"]


def test_an_old_major_surgery_does_not_trigger_the_override():
    r = record(
        events=[event(season="2022-23", date="2023-03-01", surgery="major", games_missed=None)]
    )
    assert IR.score(r)["tier"] != "HIGH"


def test_coverage_none_is_unknown_not_low():
    """A blank would read as LOW. `?` cannot be mistaken for a tier."""
    r = record(coverage="none", events=[], suggested_tier="LOW")
    assert IR.tier(r) == IR.UNKNOWN


def test_coverage_none_beats_a_high_score():
    r = record(
        coverage="none",
        events=[event(season=s, surgery="major", date=f"{s[:4]}-06-01")
                for s in ("2023-24", "2022-23")],
    )
    assert IR.tier(r) == IR.UNKNOWN


def test_thin_coverage_caps_at_med():
    """A scored HIGH is capped, whatever combination of terms reached it."""
    r = record(
        coverage="thin",
        pos_group="guard",
        events=[event(season=s, body_part="hamstring", kind="soft_tissue")
                for s in ("2025-26", "2024-25", "2023-24")],
    )
    assert IR.score(r)["total"] >= IR.CUT_HIGH
    assert IR.tier(r) == "MED"


def test_thin_coverage_does_not_cap_the_surgery_override():
    """Thin reporting on a known Achilles repair is still an Achilles repair."""
    r = record(
        coverage="thin",
        events=[
            event(
                season="2025-26",
                date="2026-04-01",
                body_part="achilles",
                kind="tendon",
                surgery="major",
            )
        ],
    )
    assert IR.tier(r) == "HIGH"


# ------------------------------------------------------------------ age, position


def test_age_and_guard_terms_apply():
    assert IR.age_points(record(age=35)) == 2
    assert IR.age_points(record(age=32)) == 1
    assert IR.age_points(record(age=30)) == 0
    assert IR.age_points(record(age=None)) == 0
    assert IR.position_points(record(pos_group="guard")) == 1
    assert IR.position_points(record(pos_group="big")) == 0


# ------------------------------------------------------------------ missing data


def test_a_rookie_with_no_nba_history_is_not_penalised():
    r = record(events=[], age=19, coverage="full")
    assert IR.tier(r) == "LOW"


def test_a_games_missed_count_on_an_event_is_descriptive_only():
    """It shows up in the report; it never moves the score."""
    lots_missed = record(events=[event(season="2025-26", games_missed=60)])
    none_missed = record(events=[event(season="2025-26", games_missed=0)])
    assert IR.score(lots_missed)["total"] == IR.score(none_missed)["total"]


# ------------------------------------------------------------------ validation


def test_a_record_with_no_source_anywhere_is_rejected():
    """No citation anywhere is a guess, and a guess is what this column cannot carry."""
    r = record(sources=None, events=[event(sources=[])])
    with pytest.raises(IR.InjuryDataError, match="no source URL"):
        IR.validate_record(r)


def test_a_source_without_a_url_is_rejected():
    r = record(sources=None, events=[event(sources=[{"publisher": "Example"}])])
    with pytest.raises(IR.InjuryDataError, match="missing a url"):
        IR.validate_record(r)


def test_a_record_level_source_alone_satisfies_the_citation_requirement():
    """The lean method cites once per player, not once per event."""
    r = record(
        sources=[{"url": "https://example.invalid/history", "publisher": "Example",
                  "date": "2026-09-01"}],
        events=[event(sources=None)],
    )
    IR.validate_record(r)  # must not raise


def test_a_record_level_source_without_a_url_is_rejected():
    r = record(sources=[{"publisher": "Example"}], events=[])
    with pytest.raises(IR.InjuryDataError, match="missing a url"):
        IR.validate_record(r)


def test_the_original_per_event_shape_still_passes():
    """The 61 records researched under the old, stricter brief must remain valid."""
    r = record(events=[event()])  # event() defaults to a cited source
    IR.validate_record(r)


def test_a_clean_record_with_zero_events_needs_no_citation():
    """"No injuries found" asserts no event fact to fabricate; nothing to cite."""
    r = record(sources=None, events=[])
    IR.validate_record(r)  # must not raise


@pytest.mark.parametrize(
    "field,bad",
    [
        ("coverage", "unknown"),
        ("suggested_tier", "MEDIUM"),
        ("pos_group", "centre"),
    ],
)
def test_a_bad_enum_is_rejected(field, bad):
    with pytest.raises(IR.InjuryDataError, match=field):
        IR.validate_record(record(**{field: bad}))


@pytest.mark.parametrize(
    "field,bad", [("mechanism", "wear"), ("surgery", "yes"), ("kind", "muscle")]
)
def test_a_bad_event_enum_is_rejected(field, bad):
    with pytest.raises(IR.InjuryDataError, match=field):
        IR.validate_record(record(events=[event(**{field: bad})]))


def test_an_impossible_games_count_is_rejected():
    with pytest.raises(IR.InjuryDataError, match="games count"):
        IR.validate_record(record(gp={"2025-26": 95}))
    with pytest.raises(IR.InjuryDataError, match="games count"):
        IR.validate_record(record(events=[event(games_missed=200)]))


def test_a_key_that_disagrees_with_its_filename_is_rejected():
    with pytest.raises(IR.InjuryDataError, match="does not match"):
        IR.validate_record(record(), key="someoneelse")


def test_a_null_games_missed_is_allowed():
    IR.validate_record(record(events=[event(games_missed=None)]))


# ------------------------------------------------------------------ the file


def blob(**players):
    return {"schema": IR.SCHEMA, "generated": "2026-09-02", "players": players}


def test_load_round_trips(tmp_path):
    p = tmp_path / "injury_risk.json"
    p.write_text(json.dumps(blob(quinnhollowaymarsh=record())))
    assert IR.load(p)["players"]["quinnhollowaymarsh"]["name"] == "Quinn Holloway-Marsh"


def test_an_old_schema_is_refused(tmp_path):
    p = tmp_path / "injury_risk.json"
    p.write_text(json.dumps({"schema": 0, "players": {}}))
    with pytest.raises(IR.InjuryDataError, match="schema"):
        IR.load(p)


def test_a_missing_file_is_an_error_not_an_empty_board(tmp_path):
    with pytest.raises(IR.InjuryDataError, match="no injury research"):
        IR.load(tmp_path / "nope.json")


def test_tiers_for_reports_missing_and_unused():
    board = [
        {"key": "quinnhollowaymarsh", "name": "Quinn Holloway-Marsh"},
        {"key": "rafaeldunsmore", "name": "Rafael Dunsmore"},
    ]
    data = blob(
        quinnhollowaymarsh=record(),
        obiadeyemipark=record(key="obiadeyemipark", name="Obi Adeyemi-Park"),
    )
    tiers, missing, unused = IR.tiers_for(board, data)
    assert tiers == ["LOW", IR.UNKNOWN]
    assert missing == ["Rafael Dunsmore"]
    assert unused == ["obiadeyemipark"]


def test_every_tier_is_a_legal_cell_value():
    board = [{"key": "quinnhollowaymarsh", "name": "Quinn Holloway-Marsh"}]
    tiers, _m, _u = IR.tiers_for(board, blob(quinnhollowaymarsh=record()))
    assert set(tiers) <= IR.VALID_CELL


# ------------------------------------------------------------------ merge


def test_merge_rejects_a_broken_checkpoint_and_keeps_the_rest(tmp_path):
    (tmp_path / "quinnhollowaymarsh.json").write_text(json.dumps(record()))
    (tmp_path / "rafaeldunsmore.json").write_text("{not json")
    (tmp_path / "obiadeyemipark.json").write_text(
        json.dumps(record(key="obiadeyemipark", name="Obi Adeyemi-Park", coverage="bogus"))
    )
    data, bad = IR.merge(tmp_path, "2026-09-02")
    assert list(data["players"]) == ["quinnhollowaymarsh"]
    assert len(bad) == 2
    assert any("rafaeldunsmore" in b for b in bad)
    assert any("obiadeyemipark" in b for b in bad)


def test_merge_sorts_by_key(tmp_path):
    for k in ("zaneothelaurier", "abelnkemdirim", "manuelochsenreiter"):
        (tmp_path / f"{k}.json").write_text(json.dumps(record(key=k, name=k.title())))
    data, bad = IR.merge(tmp_path)
    assert bad == []
    assert list(data["players"]) == sorted(data["players"])


# ------------------------------------------------------------------ report


def test_report_groups_by_tier_and_names_a_disagreement():
    data = blob(
        quinnhollowaymarsh=record(),
        rafaeldunsmore=record(
            key="rafaeldunsmore",
            name="Rafael Dunsmore",
            age=35,
            pos_group="guard",
            gp={"2025-26": 40, "2024-25": 45},
            events=[event(season=s, body_part="knee") for s in ("2025-26", "2024-25")],
            suggested_tier="MED",
        ),
    )
    text = IR.render_report(data)
    assert "## HIGH (1)" in text
    assert "## LOW (1)" in text
    assert "Rafael Dunsmore" in text
    assert "Researcher said MED, rubric says HIGH" in text
    assert "Do not hand-edit" in text
