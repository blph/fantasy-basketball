"""The pipeline entrypoint: date resolution, re-ranking, emission, and the change report.

Fixtures are synthetic (ADR-0006). These tests cover the wiring between the adapters and
the sheet, not the valuation -- that is tests/test_board_values.py.
"""

import hashlib
import json
import re

import bbm_constants as BC
import bbm_reference as B
import board_settings
import board_snapshot as BS
import board_values as BV
import build_data as BD
import pytest
import sources as S
import verify as V

from test_sources import hbp_200, hbp_file, hbp_row, made_up_name, vendor_file, vendor_row


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


def write_injury_risk(directory, date, graded, ungraded=(), extra=()):
    """A synthetic Basketball Monster risk table beside the synthetic exports.

    Invented players and invented grades (ADR-0006). `ungraded` names appear in the file
    with a blank grade, which is how their table carries a player it has not assessed;
    `extra` names are graded but are not on the board.
    """
    tiers = ("LOW", "MED", "HIGH", "EXTREME")
    lines = ["Rank,Name,Team,Pos,Inj,Inj Risk,Status"]
    for i, name in enumerate([*graded, *extra]):
        lines.append(f"{i + 1},{name},BOS,PG,,{tiers[i % 4].lower()},")
    for name in ungraded:
        lines.append(f"{len(lines)},{name},BOS,PG,,,")
    path = directory / f"BBM Injury Risk - {date}.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def projection_set(tmp_path, monkeypatch):
    """A complete, same-dated set: three exports, a fit for each vendor, a risk table."""
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
    write_injury_risk(tmp_path, "2026-01-01", names)
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
    def _injuries(self, board, tiers=None):
        """Synthetic tiers, one per board row. Reading the real table is tested in
        test_sources.py; this is only about what `emit` does with them."""
        return {"tiers": tiers if tiers is not None else ["?"] * len(board),
                "missing": [], "unused": []}

    def _emit(self, projection_set, tiers=None):
        tmp_path, names = projection_set
        date, paths = BD.find_set(None)
        board, vendors, constants, report = BD.load(paths)
        scored = BD.score(board, vendors, constants)
        inj = self._injuries(board, tiers)
        return BD.emit(board, scored, report, date, paths, False, inj), board, names

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

    # --- the injury tier ------------------------------------------------------

    def test_every_player_row_carries_an_injury_tier(self, projection_set):
        # Position 20, because REFRESH_MAP in Build.gs pairs B.injuries with index 20. A
        # row one field short would put a stat where the sheet expects a tier.
        text, board, _ = self._emit(projection_set)
        players = self._block(text, "PLAYERS")
        assert all(len(p) == 21 for p in players)
        assert len(players) == len(board)

    def test_the_tier_lands_in_board_order(self, projection_set):
        # Row i is the same player in PLAYERS and in every VALUES block, and the tier is no
        # exception -- an off-by-one here reads as an ordinary tier for the wrong man.
        _t, board, _ = self._emit(projection_set)
        tiers = ["HIGH" if i == 0 else "LOW" for i in range(len(board))]
        text, _, _ = self._emit(projection_set, tiers)
        players = self._block(text, "PLAYERS")
        assert players[0][20] == "HIGH"
        assert {p[20] for p in players[1:]} == {"LOW"}

    def test_an_ungraded_player_emits_a_question_mark_not_a_blank(self, projection_set):
        # A blank in a risk column reads as LOW, the one reading that would cost a pick.
        text, _, _ = self._emit(projection_set)
        assert {p[20] for p in self._block(text, "PLAYERS")} == {"?"}

    def test_meta_records_injury_coverage(self, projection_set):
        text, _, _ = self._emit(projection_set)
        inj = self._block(text, "META")["injuries"]
        assert inj["graded"] + inj["missing"] == len(self._block(text, "PLAYERS"))

    # --- the digest (ADR-0022) --------------------------------------------------

    def _emit_with(self, projection_set, digest):
        date, paths = BD.find_set(None)
        board, vendors, constants, report = BD.load(paths)
        scored = BD.score(board, vendors, constants)
        return BD.emit(board, scored, report, date, paths, False, self._injuries(board),
                       digest=digest)

    def test_the_digest_is_the_only_thing_it_changes_in_data_gs(self, projection_set):
        # The sheet reads Data.gs positionally, so the local board may add one META field
        # and nothing else. Two digests, one line of difference, and that line is META.
        a = self._emit_with(projection_set, "")
        b = self._emit_with(projection_set, "f" * 64)
        la, lb = a.split("\n"), b.split("\n")
        assert len(la) == len(lb)
        differing = [i for i, (x, y) in enumerate(zip(la, lb, strict=True)) if x != y]
        assert len(differing) == 1 and la[differing[0]].startswith("var META = ")
        assert a.replace(',"digest":""}', "}") == b.replace(f',"digest":"{"f" * 64}"}}', "}")

    def test_meta_gains_the_digest_last_and_nothing_else(self, projection_set):
        meta = self._block(self._emit_with(projection_set, "abc"), "META")
        assert list(meta) == ["generated", "mixedDates", "boardRows", "sources", "injuries",
                              "digest"]
        assert meta["digest"] == "abc"
        assert self._block(self._emit(projection_set)[0], "META")["digest"] == ""


class TestLoadInjuries:
    """Board rows tiered from Basketball Monster's table. No tier is computed here."""

    def test_every_board_row_is_tiered_in_board_order(self, projection_set):
        _tmp, names = projection_set
        _date, paths = BD.find_set(None)
        board = S.load_board(paths["HBP"])
        inj = BD.load_injuries(board, paths["inj"])
        risk = S.load_injury_risk(paths["inj"])
        assert inj["tiers"] == [risk[row["key"]] for row in board]
        assert inj["missing"] == [] and inj["unused"] == []

    def test_a_board_player_they_do_not_grade_is_named_not_dropped(self, projection_set):
        # `?`, never a tier and never a blank: a blank in a risk column reads as LOW, and
        # a guessed tier is the failure this whole column was rebuilt to avoid.
        tmp_path, names = projection_set
        write_injury_risk(tmp_path, "2026-01-01", names[1:], ungraded=[names[0]])
        _date, paths = BD.find_set(None)
        board = S.load_board(paths["HBP"])
        inj = BD.load_injuries(board, paths["inj"])
        assert inj["tiers"][0] == "?"
        assert inj["missing"] == [names[0]]
        assert "?" not in inj["tiers"][1:]

    def test_a_graded_player_who_is_not_on_the_board_is_reported_unused(self, projection_set):
        tmp_path, names = projection_set
        write_injury_risk(tmp_path, "2026-01-01", names, extra=["Fictional Benchwarmer"])
        _date, paths = BD.find_set(None)
        board = S.load_board(paths["HBP"])
        inj = BD.load_injuries(board, paths["inj"])
        assert inj["missing"] == []
        assert inj["unused"] == ["fictionalbenchwarmer"]

    def test_a_malformed_table_stops_the_build(self, projection_set):
        # Validated before any scoring runs, so it fails on its own terms rather than a
        # thousand lines later inside `emit`.
        tmp_path, names = projection_set
        (tmp_path / "BBM Injury Risk - 2026-01-01.csv").write_text(
            "Rank,Name,Team,Pos,Inj,Inj Risk,Status\n1,Ardent Bellweather,BOS,PG,,severe,\n",
            encoding="utf-8")
        _date, paths = BD.find_set(None)
        board = S.load_board(paths["HBP"])
        with pytest.raises(SystemExit, match="severe"):
            BD.load_injuries(board, paths["inj"])


# --- the local board (ADR-0022) ------------------------------------------------------------


@pytest.fixture
def built(projection_set, monkeypatch):
    """`build_data.py` pointed at tmp_path: Data.gs and the local board both land there."""
    tmp_path, names = projection_set
    out = tmp_path / "Data.gs"
    root = tmp_path / "draft-board"
    monkeypatch.setattr(BD, "DEFAULT_OUT", out)
    monkeypatch.setattr(BD, "SNAPSHOT_ROOT", root)
    return tmp_path, out, root, names


def run(*argv):
    assert BD.main(list(argv)) == 0


def pair(out, root):
    return BS.load(BS.path_for(root, "2026-01-01")), V.load(out)


class TestLocalBoard:
    def test_the_default_build_writes_it_beside_data_gs(self, built):
        _tmp, out, root, _names = built
        run()
        assert out.exists()
        assert BS.list_dates(root) == ["2026-01-01"]
        assert BS.load(BS.path_for(root, "2026-01-01"))["schema"] == BS.SCHEMA

    def test_a_non_default_out_writes_no_local_board(self, built):
        # A scratch Data.gs gets no snapshot: one would sit under the real date describing
        # a board nobody deployed.
        tmp_path, out, root, _names = built
        other = tmp_path / "scratch" / "Data.gs"
        run("--out", str(other))
        assert other.exists() and not out.exists()
        assert not root.exists()

    def test_dry_run_writes_neither_file(self, built):
        _tmp, out, root, _names = built
        run("--dry-run")
        assert not out.exists() and not root.exists()

    def test_every_number_equals_data_gs(self, built):
        _tmp, out, root, _names = built
        run()
        snapshot, data = pair(out, root)
        assert V.check_snapshot(snapshot, data) == []

    def test_both_files_carry_one_digest_and_the_board_hashes_data_gs(self, built):
        _tmp, out, root, _names = built
        run()
        snapshot, data = pair(out, root)
        assert re.fullmatch(r"[0-9a-f]{64}", data["META"]["digest"])
        assert data["META"]["digest"] == snapshot["meta"]["digest"] == BS.digest(snapshot)
        assert snapshot["meta"]["data_gs_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()

    def test_players_are_keyed_on_the_join_key_in_board_order(self, built):
        _tmp, out, root, names = built
        run()
        snapshot, _data = pair(out, root)
        players = snapshot["players"]
        assert [p["row"] for p in players] == list(range(len(names)))
        assert [p["name"] for p in players] == names
        assert [p["key"] for p in players] == [S.normalise(p["name"]) for p in players]

    def test_settings_are_board_settings(self, built):
        _tmp, out, root, _names = built
        run()
        snapshot, data = pair(out, root)
        assert snapshot["settings"] == board_settings.as_dict()
        assert snapshot["deriv"] == data["DERIV"]
        # In pool: the engine compares BMP DURH rank with settings q, the sheet with DERIV.q.
        # One number, or the two boards draw the pool line in different places.
        assert snapshot["settings"]["q"] == snapshot["deriv"]["q"]

    def test_a_blank_adp_is_null_here_and_blank_in_data_gs(self, built):
        tmp_path, out, root, names = built
        hbp_file(tmp_path, [hbp_row(i + 1, n, adp="" if i == 0 else "5.0")
                            for i, n in enumerate(names)])
        run()
        snapshot, data = pair(out, root)
        assert data["PLAYERS"][0][4] == "" and snapshot["players"][0]["adp"] is None
        assert snapshot["players"][1]["adp"] == data["PLAYERS"][1][4]
        assert V.check_snapshot(snapshot, data) == []

    def test_a_same_date_rebuild_replaces_both_and_leaves_no_temp_files(self, built):
        tmp_path, out, root, _names = built
        run()
        path = BS.path_for(root, "2026-01-01")
        out.write_text("stale", encoding="utf-8")
        path.write_text("stale", encoding="utf-8")
        run()
        snapshot, data = pair(out, root)
        assert V.check_snapshot(snapshot, data) == []
        assert [p.name for p in root.iterdir()] == [path.name]
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


class TestWriteAtomic:
    def test_it_replaces_every_file_and_leaves_no_temp_files(self, tmp_path):
        a, b = tmp_path / "Data.gs", tmp_path / "board" / "board - 2026-01-01.json"
        a.write_text("old", encoding="utf-8")
        BD.write_atomic([(a, "new a\n"), (b, "new b\n")])
        assert a.read_text(encoding="utf-8") == "new a\n"
        assert b.read_text(encoding="utf-8") == "new b\n"
        assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == [
            "Data.gs", "board - 2026-01-01.json"]

    def test_a_failure_before_the_renames_changes_nothing(self, tmp_path, monkeypatch):
        # Every temp is written before anything is renamed, so a failure writing the second
        # file leaves the first target untouched and cleans up after itself.
        a, b = tmp_path / "Data.gs", tmp_path / "board - 2026-01-01.json"
        a.write_text("old", encoding="utf-8")
        real = BD.tempfile.mkstemp
        calls = []

        def failing(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(*args, **kwargs)

        monkeypatch.setattr(BD.tempfile, "mkstemp", failing)
        with pytest.raises(OSError, match="disk full"):
            BD.write_atomic([(a, "new"), (b, "new")])
        assert a.read_text(encoding="utf-8") == "old"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["Data.gs"]


class TestCheckSnapshot:
    """What verify.py reports when the two files disagree. Rows and fields, never names."""

    @pytest.fixture
    def both(self, built):
        _tmp, out, root, _names = built
        run()
        return pair(out, root)

    def test_a_changed_value_is_named_by_row_and_field(self, both):
        snapshot, data = both
        name = snapshot["players"][7]["name"]
        snapshot["players"][7]["values"]["HBP"]["zsh"]["v"] += 0.0001
        snapshot["meta"]["digest"] = BS.digest(snapshot)     # resealed: a second build
        fails = V.check_snapshot(snapshot, data)
        assert "HBP.zsh.v: 1 of 200 rows differ from Data.gs" in fails
        assert "row 7 HBP.zsh.v: snapshot and Data.gs differ" in fails
        assert any("not from the same build" in f for f in fails)
        assert not any(name in f for f in fails)

    def test_an_edited_snapshot_fails_its_own_digest(self, both):
        snapshot, data = both
        snapshot["players"][0]["punts"]["pFt"]["rank"] += 1
        fails = V.check_snapshot(snapshot, data)
        assert any("does not recompute" in f for f in fails)
        assert "punts.pFt: 1 of 200 rows differ from Data.gs" in fails

    def test_an_edited_data_gs_fails_the_text_hash(self, both):
        snapshot, data = both
        data["SHA256"] = "0" * 64
        assert any("data_gs_sha256" in f for f in V.check_snapshot(snapshot, data))

    def test_a_data_gs_from_before_the_local_board_is_reported(self, both):
        snapshot, data = both
        del data["META"]["digest"]
        assert any("predates the local board" in f for f in V.check_snapshot(snapshot, data))

    def test_null_adp_pairs_with_blank_and_nothing_else(self, both):
        snapshot, data = both
        snapshot["players"][3]["adp"] = None
        assert "adp: 1 of 200 rows differ from Data.gs" in V.check_snapshot(snapshot, data)
        data["PLAYERS"][3][4] = ""
        assert not any(f.startswith("adp") for f in V.check_snapshot(snapshot, data))

    def test_a_short_or_malformed_board_is_reported_not_raised(self, both):
        snapshot, data = both
        del snapshot["players"][5]["hbp_raw"]
        assert "row 5: the snapshot row is malformed (missing 'hbp_raw')" in (
            V.check_snapshot(snapshot, data))
        snapshot["players"].pop()
        assert any("199 players against 200" in f for f in V.check_snapshot(snapshot, data))


class TestVerifyMain:
    def test_a_named_snapshot_is_checked(self, built, capsys):
        _tmp, out, root, _names = built
        run()
        capsys.readouterr()
        path = BS.path_for(root, "2026-01-01")
        assert V.main(["--data", str(out), "--snapshot", str(path)]) == 0
        assert "local board agrees" in capsys.readouterr().out

    def test_a_snapshot_from_another_build_fails(self, built):
        _tmp, out, root, _names = built
        run()
        path = BS.path_for(root, "2026-01-01")
        snapshot = BS.load(path)
        snapshot["players"][0]["values"]["BMP"]["durh"]["v"] += 0.0001
        snapshot["meta"]["digest"] = BS.digest(snapshot)
        path.write_text(BS.dumps(snapshot), encoding="utf-8")
        assert V.main(["--data", str(out), "--snapshot", str(path)]) == 1

    def test_the_default_is_the_snapshot_this_data_gs_was_built_with(self, built, monkeypatch,
                                                                     capsys):
        _tmp, out, root, _names = built
        run()
        # A newer board from some other build must not be the one compared.
        (root / "board - 2026-02-01.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(V, "DEFAULT_DATA", out)
        monkeypatch.setattr(BS, "ROOT", root)
        capsys.readouterr()
        assert V.main([]) == 0
        printed = capsys.readouterr().out
        assert "LOCAL BOARD   board - 2026-01-01.json" in printed
        assert "a newer local board exists" in printed

    def test_no_local_board_is_skipped_with_a_note(self, built, monkeypatch, capsys):
        tmp_path, out, _root, _names = built
        run()
        monkeypatch.setattr(V, "DEFAULT_DATA", out)
        monkeypatch.setattr(BS, "ROOT", tmp_path / "empty")
        capsys.readouterr()
        assert V.main([]) == 0
        printed = capsys.readouterr().out
        assert "-- skipped" in printed and "local board agrees" not in printed

    def test_a_named_snapshot_that_does_not_exist_is_exit_2(self, built):
        tmp_path, out, _root, _names = built
        run()
        assert V.main(["--data", str(out), "--snapshot", str(tmp_path / "nope.json")]) == 2
