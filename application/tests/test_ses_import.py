"""Tests for the Specctra `.ses` routing importer:
parse → native Track/Via, unit scaling, Y-flip, padstack resolution,
per-board localization, and ingest into SmashState."""

import pathlib

import pytest

from smash import SmashState, Track, Via
from smash.validators.specctra._session import parse_session, Session
from smash.state.routing.ingest import (
    import_session, localize, ingest_session, _units_per_mm,
)

from smash.roots import git_repo_root

_SES = (git_repo_root()
        / "output" / "kicad_pcbs" / "smash_evb_snake" / "smash_evb_snake.ses")


@pytest.fixture(scope="module")
def session() -> Session:
    if not _SES.exists():
        pytest.skip(f"routed session not present: {_SES}")
    return parse_session(_SES)


class TestSessionParse:
    def test_top_level_and_routes(self, session):
        assert session.name == "smash_evb_snake"
        assert session.resolution.unit == "um"
        assert session.wiring.wires and session.wiring.vias
        # Every wire/via inherits its enclosing net name.
        assert all(w.net for w in session.wiring.wires)
        assert all(v.net for v in session.wiring.vias)

    def test_rejects_non_session(self):
        with pytest.raises(ValueError):
            parse_session('(pcb "x" (parser))')

    def test_units_per_mm(self, session):
        # (resolution um 10) → 10 sub-units/µm → 10 000 units/mm
        assert _units_per_mm(session.resolution) == 10_000.0


class TestImportConversion:
    def test_tracks_and_vias_extracted(self, session):
        pr = import_session(session)
        assert len(pr.tracks) == len(session.wiring.wires)
        assert pr.tracks and pr.vias
        assert all(isinstance(t, Track) for t in pr.tracks)
        assert all(isinstance(v, Via) for v in pr.vias)

    def test_track_width_layer_points(self, session):
        pr = import_session(session)
        t = pr.tracks[0]
        assert t.width_mm == pytest.approx(0.2)      # 2000 units / 10000
        assert t.layer in ("F.Cu", "B.Cu") or t.layer.startswith("In")
        assert len(t.path) >= 2
        assert all(len(pt) == 2 for pt in t.path)

    def test_via_padstack_resolved(self, session):
        pr = import_session(session)
        v = pr.vias[0]
        # Padstack "Via[0-1]_600:300_um": pad 0.6 mm, drill 0.3 mm, through.
        assert v.pad_diameter_mm == pytest.approx(0.6)
        assert v.drill_mm == pytest.approx(0.3)
        assert v.from_layer == "F.Cu" and v.to_layer == "B.Cu"

    def test_y_flip_to_math_y_up(self, session):
        # .ses Y is screen-y-down (negative in this file); imported Y is
        # negated → positive (math-y-up).
        raw_ys = [v.y for v in session.wiring.vias if v.y is not None]
        assert min(raw_ys) < 0                       # source is y-down
        pr = import_session(session)
        assert all(v.position_mm[1] > 0 for v in pr.vias)


class TestLocalizeAndIngest:
    def test_localize_partitions_all_items(self, session):
        pr = import_session(session)
        xs = [v.position_mm[0] for v in pr.vias]
        ys = [v.position_mm[1] for v in pr.vias]
        offsets = {"left": (min(xs), sum(ys) / len(ys)),
                   "right": (max(xs), sum(ys) / len(ys))}
        loc = localize(pr, offsets)
        # Every track + via is assigned to exactly one board.
        assert sum(len(t) for t, _ in loc.values()) == len(pr.tracks)
        assert sum(len(v) for _, v in loc.values()) == len(pr.vias)

    def test_localize_requires_offsets(self, session):
        with pytest.raises(ValueError):
            localize(import_session(session), {})

    def test_ingest_appends_and_round_trips(self, session, tmp_path):
        pr = import_session(session)
        xs = [v.position_mm[0] for v in pr.vias]
        ys = [v.position_mm[1] for v in pr.vias]
        cy = sum(ys) / len(ys)
        offsets = {"power_board": (min(xs), cy), "flight_board": (max(xs), cy)}

        s = SmashState.new()
        counts = ingest_session(s, _SES, board_offsets=offsets)
        assert set(counts) <= set(offsets)
        assert counts                                # at least one board routed
        total_v = sum(s.boards[b].vias.__len__() for b in counts)
        assert total_v == len(pr.vias)

        # Localized coords are board-local: subtracting the offset shifts
        # the panel-global position, so they differ from the panel frame.
        b0 = next(iter(counts))
        assert s.boards[b0].vias

        # Survives serialization.
        out = tmp_path / "routed.json"
        s.dump_json(out)
        s2 = SmashState.load_json(out)
        assert len(s2.boards[b0].vias) == len(s.boards[b0].vias)
        assert isinstance(s2.boards[b0].vias[0], Via)
        if s2.boards[b0].tracks:
            assert isinstance(s2.boards[b0].tracks[0], Track)
