"""The pipeline entrypoint: date resolution, re-ranking, emission, and the change report.

Fixtures are synthetic (ADR-0006). These tests cover the wiring between the adapters and
the sheet, not the valuation -- that is tests/test_board_values.py.
"""

import json
import re

import bbm_constants as BC
import bbm_reference as B
import board_values as BV
import build_data as BD
import pytest
import sources as S

from test_sources import hbp_200, made_up_name, vendor_file, vendor_row


def write_constants(directory, label, date, rates, q=20, shift=0.0, stretch=1.0):
    """A synthetic fit beside a synthetic export.

    Derived from the fixture's own pool and then nudged, so the file is a plausible set of
    borrowed constants rather than a copy of what the pipeline would have computed anyway.
    Nothing here is Basketball Monster's; see ADR-0006.
    """
    _, plain = B.build_pool(rates, q)
    _, durant = B.build_durant_pool(rates, q, B.LAMBDAS_BBM_2026_27_JOSH)
    for block in (plain, durant):
        for spec in block.values():
            spec["mean"] += shift * spec["sd"]
            spec["sd"] *= stretch
    blob = BC.dump(
        {"plain": plain, "durant": durant}, dict(B.LAMBDAS_BBM_2026_27_JOSH),
        source=label, export_date=date, bbm_source_id=0,
        fitted_at="2026-01-01T00:00:00Z", fitted_from="synthetic",
        players_fitted=len(rates), fit={},
    )
    path = directory / f"{label} Constants - {date}.json"
    path.write_text(json.dumps(blob), encoding="utf-8")
    return path


@pytest.fixture
def projection_set(tmp_path, monkeypatch):
    """A complete, same-dated set: three exports and a fit for each vendor."""
    names = [made_up_name(i) for i in range(200)]
    monkeypatch.setattr(BD, "DATA", tmp_path)
    hbp_200(tmp_path, names)
    rows = [vendor_row(100 + i, *n.split(" ", 1), fgm=400 + i * 3, threes=60 + i,
                       ftm=150 + i * 2, games=60 + i % 20) for i, n in enumerate(names)]
    for label in ("BMP", "BMP-ALT"):
        path = tmp_path / f"{label} Projections - 2026-01-01.csv"
        vendor_file(tmp_path, rows, path.name)
        rates = {k: r for k, v in S.load_vendor(path).items() if (r := B.per_game(v))}
        write_constants(tmp_path, label, "2026-01-01", rates, shift=0.05, stretch=1.03)
    return tmp_path, names


class TestFindSet:
    def test_finds_the_newest_complete_set(self, projection_set):
        tmp_path, names = projection_set
        # A newer but incomplete set must not win: two thirds of a refresh is not a refresh.
        vendor_file(tmp_path, [vendor_row(1, "Lone", "Vendor")],
                    "BMP Projections - 2026-06-01.csv")
        date, paths = BD.find_set(None)
        assert date == "2026-01-01"
        assert set(paths) == set(BD.SET_FILES)

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

    def test_ranks_the_value_the_sheet_will_see(self):
        # Two values that differ below the rounding, ordered against each other. The sheet
        # is given both as 0.5001 and ranks them with its own RANK() over what it was
        # given, so ranking full precision here puts a #2 next to the higher number.
        rows = [
            {"durh": 0.50011, "zsh": 0.0, "zsc": 0.0},
            {"durh": 0.50014, "zsh": 0.0, "zsc": 0.0},
        ]
        BD.rerank(rows)
        assert [r["durh_rank"] for r in rows] == [1, 2], (
            "rows that round to the same displayed value must rank in board order, "
            "not on precision the sheet was never given"
        )


class TestEmit:
    def _emit(self, projection_set):
        tmp_path, names = projection_set
        date, paths = BD.find_set(None)
        board, vendors, constants, report = BD.load(paths)
        scored = BD.score(board, vendors, constants)
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

    def test_every_rank_is_the_rank_of_the_value_shipped_beside_it(self, projection_set):
        # The sheet's own # column ranks the number it was given, so the number it was
        # given has to be the number we ranked. Ranking full precision and shipping four
        # decimals put 21 rows across the nine columns one place out from the value next
        # to them -- deep-tier pairs, and a # that does not mean what it says.
        text, board, _ = self._emit(projection_set)
        for src, rows in self._block(text, "VALUES").items():
            for vcol, rcol in ((0, 1), (3, 4), (6, 7)):
                order = sorted(range(len(rows)), key=lambda i: (-rows[i][vcol], i))
                want = {i: place for place, i in enumerate(order, start=1)}
                assert [rows[i][rcol] for i in range(len(rows))] == [
                    want[i] for i in range(len(rows))
                ], (src, vcol)

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
