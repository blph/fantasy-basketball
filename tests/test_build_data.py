"""The pipeline entrypoint: date resolution, re-ranking, emission, and the change report.

Fixtures are synthetic (ADR-0006). These tests cover the wiring between the adapters and
the sheet, not the valuation -- that is tests/test_board_values.py.
"""

import json
import re

import board_values as BV
import build_data as BD
import pytest

from test_sources import hbp_200, made_up_name, vendor_file, vendor_row


@pytest.fixture
def projection_set(tmp_path, monkeypatch):
    """One complete, same-dated set of three exports in a throwaway data directory."""
    names = [made_up_name(i) for i in range(200)]
    monkeypatch.setattr(BD, "DATA", tmp_path)
    hbp_200(tmp_path, names)
    (tmp_path / "HBP Projections - 2026-01-01.csv").rename(
        tmp_path / "HBP Projections - 2026-01-01.csv")
    rows = [vendor_row(100 + i, *n.split(" ", 1), fgm=400 + i * 3, threes=60 + i,
                       ftm=150 + i * 2, games=60 + i % 20) for i, n in enumerate(names)]
    vendor_file(tmp_path, rows, "BMP Projections - 2026-01-01.csv")
    vendor_file(tmp_path, rows, "BMP-ALT Projections - 2026-01-01.csv")
    return tmp_path, names


class TestFindSet:
    def test_finds_the_newest_complete_set(self, projection_set):
        tmp_path, names = projection_set
        # A newer but incomplete set must not win: two thirds of a refresh is not a refresh.
        vendor_file(tmp_path, [vendor_row(1, "Lone", "Vendor")],
                    "BMP Projections - 2026-06-01.csv")
        date, paths = BD.find_set(None)
        assert date == "2026-01-01"
        assert set(paths) == {"BMP", "HBP", "BMP-ALT"}

    def test_an_explicit_date_that_is_incomplete_is_an_error(self, projection_set):
        tmp_path, _ = projection_set
        vendor_file(tmp_path, [vendor_row(1, "Lone", "Vendor")],
                    "BMP Projections - 2026-06-01.csv")
        with pytest.raises(SystemExit, match="missing"):
            BD.find_set("2026-06-01")

    def test_no_complete_set_names_what_is_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(BD, "DATA", tmp_path)
        vendor_file(tmp_path, [vendor_row(1, "Lone", "Vendor")],
                    "BMP Projections - 2026-06-01.csv")
        with pytest.raises(SystemExit, match="HBP"):
            BD.find_set(None)

    def test_an_empty_directory_says_what_it_expected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(BD, "DATA", tmp_path)
        with pytest.raises(SystemExit, match="No projection exports"):
            BD.find_set(None)


class TestRerank:
    def test_ranks_the_board_rows_against_each_other(self):
        # The pools are built over the vendor's full ~510-player universe, so a rank taken
        # from there arrives with gaps and is not comparable to the board's own rank
        # column -- which is exactly what the tag and the disagreement highlight compare
        # it against.
        rows = [
            {"durh": 0.1, "zsh": 0.1, "zsc": 0.1, "durh_rank": 41},
            {"durh": 0.9, "zsh": 0.9, "zsc": 0.9, "durh_rank": 7},
            {"durh": 0.5, "zsh": 0.5, "zsc": 0.5, "durh_rank": 19},
        ]
        BD.rerank(rows)
        assert [r["durh_rank"] for r in rows] == [3, 1, 2]
        assert sorted(r["zsc_rank"] for r in rows) == [1, 2, 3]

    def test_every_rank_is_a_permutation_with_no_gaps(self):
        rows = [{"durh": i * 0.01, "zsh": -i * 0.01, "zsc": (i % 7) * 0.01} for i in range(50)]
        BD.rerank(rows)
        for field in ("durh_rank", "zsh_rank", "zsc_rank"):
            assert sorted(r[field] for r in rows) == list(range(1, 51))


class TestEmit:
    def _emit(self, projection_set):
        tmp_path, names = projection_set
        date, paths = BD.find_set(None)
        board, vendors, report = BD.load(paths)
        scored = BD.score(board, vendors)
        return BD.emit(board, scored, report, date, paths, False), board, names

    def _block(self, text, name):
        m = re.search(rf"var {name}\s*=\s*(.*?);\n", text, re.S)
        return json.loads(re.sub(r",(\s*[\]}])", r"\1", m.group(1)))

    def test_one_row_per_player_in_every_block(self, projection_set):
        text, board, _ = self._emit(projection_set)
        assert len(self._block(text, "PLAYERS")) == len(board)
        for src, rows in self._block(text, "VALUES").items():
            assert len(rows) == len(board), src

    def test_row_order_is_the_same_in_players_and_every_values_block(self, projection_set):
        # The contract the whole sheet rests on: row i means the same player everywhere.
        text, board, _ = self._emit(projection_set)
        players = self._block(text, "PLAYERS")
        assert [p[1] for p in players] == [r["name"] for r in board]

    def test_ranks_are_a_permutation_of_the_board_rows(self, projection_set):
        text, board, _ = self._emit(projection_set)
        for src, rows in self._block(text, "VALUES").items():
            for col in (1, 4, 7):     # durh, zsh, zsc rank positions
                assert sorted(r[col] for r in rows) == list(range(1, len(board) + 1)), (src, col)

    def test_the_dropped_category_is_never_turnovers(self, projection_set):
        # DURANT H2H weights turnovers at zero, which is how it removes them. A build that
        # dropped TO would mean the weight vector had been lost somewhere.
        text, _, _ = self._emit(projection_set)
        for rows in self._block(text, "VALUES").values():
            assert "TO" not in {r[2] for r in rows} | {r[5] for r in rows}

    def test_the_weighted_column_is_the_unweighted_one_times_its_weight(self, projection_set):
        text, _, _ = self._emit(projection_set)
        deriv = self._block(text, "DERIV")
        for rows in self._block(text, "VALUES").values():
            for r in rows:
                for i, cat in enumerate(BV.CAT_LABELS):
                    assert r[8 + i] == pytest.approx(r[16 + i] * deriv["weights"][cat], abs=5e-4)

    def test_blank_adp_is_emitted_blank_not_zero(self, projection_set):
        text, _, _ = self._emit(projection_set)
        assert all(p[4] != 0 for p in self._block(text, "PLAYERS"))

    def test_it_is_deterministic(self, projection_set):
        # Two runs must be byte-identical, or a diff of the change report means nothing.
        a, _, _ = self._emit(projection_set)
        b, _, _ = self._emit(projection_set)
        assert a == b

    def test_deriv_carries_the_k_derivation_and_it_inverts(self, projection_set):
        text, _, _ = self._emit(projection_set)
        d = self._block(text, "DERIV")
        for cat, k in d["k_tracker"].items():
            assert k * d["weights"][cat] == pytest.approx(d["k_rosenof"][cat], abs=5e-4)
