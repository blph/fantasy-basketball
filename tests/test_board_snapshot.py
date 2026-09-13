"""The local board's file format: naming, the digest, and what `load` refuses.

Fixtures are synthetic (ADR-0006): invented players and invented numbers. What a real build
writes into the snapshot is tested in tests/test_build_data.py.
"""

import json
import re
from pathlib import Path

import board_snapshot as BS
import build_data as BD
import pytest

from test_sources import made_up_name

BUILD_GS = Path(__file__).resolve().parents[1] / "scripts" / "draft-board" / "Build.gs"


def snapshot(**overrides):
    """A one-player snapshot, shaped like schema 1. Every number is invented."""
    name = made_up_name(0)
    snap = {
        "schema": 1,
        "meta": {"generated": "2026-01-01", "digest": "", "data_gs_sha256": "",
                 "sources": {"HBP": "HBP Projections - 2026-01-01.csv"}, "board_rows": 1,
                 "injuries": {"graded": 1, "missing": 0, "unused": 0}},
        "settings": {"teams": 12, "roster": 13, "q": 156},
        "deriv": {"q": 156, "band_calibration": {"1.0": {"flags_per_player": 2.5}}},
        "cat_labels": ["FG%", "FT%", "3PM", "PTS", "REB", "AST", "STL", "BLK"],
        "punt_builds": [{"key": k, "label": lab} for k, lab in BS.PUNT_BUILDS],
        "players": [{"row": 0, "key": "x", "name": name, "team": "BOS", "pos": "PG",
                     "seed": 1, "adp": None, "inj": "?",
                     "hbp_raw": {"gp": 70, "mpg": 33.0},
                     "values": {"BMP": {"durh": {"v": 0.5, "rank": 1, "drop": "FT%"}}},
                     "punts": {"pFt": {"score": 0.4, "rank": 1}}}],
    }
    snap.update(overrides)
    return snap


def sealed(snap):
    snap["meta"]["digest"] = BS.digest(snap)
    return snap


class TestNaming:
    def test_path_for_names_the_file_by_date(self, tmp_path):
        assert BS.path_for(tmp_path, "2026-01-01") == tmp_path / "board - 2026-01-01.json"

    def test_list_dates_is_ascending_and_ignores_everything_else(self, tmp_path):
        for name in ("board - 2026-03-01.json", "board - 2026-01-01.json",
                     "board - 2026-02-01.json", "draft-state.json", "board - latest.json",
                     ".board - 2026-04-01.json.abc123.tmp", "board - 2026-05-01.json.bak"):
            (tmp_path / name).write_text("{}", encoding="utf-8")
        assert BS.list_dates(tmp_path) == ["2026-01-01", "2026-02-01", "2026-03-01"]

    def test_newest_is_the_latest_date(self, tmp_path):
        for d in ("2026-02-01", "2026-01-01"):
            BS.path_for(tmp_path, d).write_text("{}", encoding="utf-8")
        assert BS.newest(tmp_path) == BS.path_for(tmp_path, "2026-02-01")

    def test_no_directory_and_an_empty_one_have_no_newest(self, tmp_path):
        assert BS.list_dates(tmp_path / "absent") == []
        assert BS.newest(tmp_path / "absent") is None
        assert BS.newest(tmp_path) is None


class TestDigest:
    def test_it_does_not_depend_on_key_order(self):
        a = snapshot()
        b = json.loads(json.dumps(a, sort_keys=True))
        b["meta"] = dict(reversed(list(b["meta"].items())))
        assert list(a) != list(b)
        assert BS.digest(a) == BS.digest(b)

    def test_it_excludes_the_two_fields_it_cannot_cover(self):
        # The digest cannot hash itself, and data_gs_sha256 hashes a file that contains it.
        a, b = snapshot(), snapshot()
        b["meta"]["digest"] = "f" * 64
        b["meta"]["data_gs_sha256"] = "e" * 64
        assert BS.digest(a) == BS.digest(b)

    @pytest.mark.parametrize("mutate", [
        lambda s: s["players"][0]["values"]["BMP"]["durh"].update(v=0.5001),
        lambda s: s["players"][0]["punts"]["pFt"].update(rank=2),
        lambda s: s["deriv"].update(q=155),
        lambda s: s["meta"].update(generated="2026-01-02"),
        lambda s: s["settings"].update(teams=10),
    ])
    def test_any_content_change_moves_it(self, mutate):
        a, b = snapshot(), snapshot()
        mutate(b)
        assert BS.digest(a) != BS.digest(b)

    def test_it_does_not_mutate_the_snapshot(self):
        s = snapshot()
        s["meta"]["digest"] = "abc"
        BS.digest(s)
        assert s["meta"]["digest"] == "abc"
        assert "data_gs_sha256" in s["meta"]

    def test_it_is_a_sha256_hex_string(self):
        assert re.fullmatch(r"[0-9a-f]{64}", BS.digest(snapshot()))


class TestDumps:
    def test_it_is_compact_one_line_and_newline_terminated(self):
        text = BS.dumps(snapshot())
        assert text.endswith("\n") and text.count("\n") == 1
        assert ", " not in text and '": ' not in text

    def test_it_keeps_non_ascii_names_as_written(self):
        s = snapshot()
        s["players"][0]["name"] = "Zoë Quillon"            # invented
        assert "Zoë Quillon" in BS.dumps(s)

    def test_it_round_trips(self):
        s = snapshot()
        assert json.loads(BS.dumps(s)) == s


class TestLoad:
    def test_a_sealed_snapshot_loads(self, tmp_path):
        path = tmp_path / "board - 2026-01-01.json"
        path.write_text(BS.dumps(sealed(snapshot())), encoding="utf-8")
        assert BS.load(path)["players"][0]["row"] == 0

    def test_a_wrong_schema_is_refused(self, tmp_path):
        path = tmp_path / "board - 2026-01-01.json"
        path.write_text(BS.dumps(sealed(snapshot(schema=2))), encoding="utf-8")
        with pytest.raises(BS.SnapshotError, match="schema"):
            BS.load(path)

    def test_a_tampered_number_is_refused(self, tmp_path):
        # A hand-edited board is a wrong number that looks right.
        s = sealed(snapshot())
        s["players"][0]["values"]["BMP"]["durh"]["v"] = 0.9
        path = tmp_path / "board - 2026-01-01.json"
        path.write_text(BS.dumps(s), encoding="utf-8")
        with pytest.raises(BS.SnapshotError, match="digest"):
            BS.load(path)

    def test_an_unsealed_snapshot_is_refused(self, tmp_path):
        path = tmp_path / "board - 2026-01-01.json"
        path.write_text(BS.dumps(snapshot()), encoding="utf-8")
        with pytest.raises(BS.SnapshotError, match="digest"):
            BS.load(path)

    def test_a_missing_file_and_a_corrupt_one_are_snapshot_errors(self, tmp_path):
        with pytest.raises(BS.SnapshotError, match="no such snapshot"):
            BS.load(tmp_path / "board - 2026-01-01.json")
        bad = tmp_path / "board - 2026-01-02.json"
        bad.write_text('{"schema": 1,', encoding="utf-8")
        with pytest.raises(BS.SnapshotError, match="not JSON"):
            BS.load(bad)
        listed = tmp_path / "board - 2026-01-03.json"
        listed.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(BS.SnapshotError, match="schema"):
            BS.load(listed)


class TestConstants:
    def test_sources_are_the_pipelines_in_its_order(self):
        assert list(BS.SOURCES) == list(BD.SOURCE_FILES)

    def test_punt_builds_match_the_pipeline_and_build_gs(self):
        assert [k for k, _ in BS.PUNT_BUILDS] == [k for k, _ in BD.PUNTS]
        text = BUILD_GS.read_text(encoding="utf-8")
        block = re.search(r"var PUNTS = \[(.*?)\];", text, re.S).group(1)
        in_gs = re.findall(r"key: '([^']+)',\s*label: '([^']+)'", block)
        assert tuple(in_gs) == BS.PUNT_BUILDS

    def test_player_fields_describe_a_players_row(self):
        assert len(BS.PLAYER_FIELDS) == 21
        assert BS.PLAYER_FIELDS[4] == "adp" and BS.PLAYER_FIELDS[20] == "inj"
        assert BS.HBP_RAW_FIELDS[0] == "gp" and BS.HBP_RAW_FIELDS[-1] == "to"
