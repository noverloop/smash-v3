"""Tests for the board-local XYZ system: Z datum from the fitted buildup
and the routing→3D resolvers in smash.state.geometry3d."""

import pathlib

import pytest

from smash import (
    Board, Track, Via, Zone, SmashState, Chip, Footprint, Pad, Placement,
    track_polyline_3d, via_segment_3d, zone_polygon_3d,
    pad_xyz, chip_body_3d, board_solder, chip_underfill,
    copper_on_layer, stack_height_mm,
)
from smash.state.routing.ingest import import_session

from smash.roots import git_repo_root

_SES = (git_repo_root()
        / "output" / "kicad_pcbs" / "smash_evb_snake" / "smash_evb_snake.ses")


@pytest.fixture
def board():
    return Board("flight_board").set_fitted_stackup()


class TestZDatum:
    def test_bottom_is_zero_datum(self, board):
        # B.Cu sits at the bottom: centre ≈ half its foil, tol ≈ 0
        z, tol = board.layer_z_mm("B.Cu")
        assert z == pytest.approx(0.00875, abs=1e-4)   # 17.5 µm / 2
        assert tol == pytest.approx(0.0, abs=1e-9)

    def test_top_near_stack_height(self, board):
        z_top = board.layer_span_mm("F.Cu")[1]
        assert z_top == pytest.approx(2.205, abs=1e-3)
        assert stack_height_mm(board) == pytest.approx(2.205, abs=1e-3)

    def test_monotonic_and_tol_grows_upward(self, board):
        zb, tb = board.layer_z_mm("B.Cu")
        zf, tf = board.layer_z_mm("F.Cu")
        assert zb < zf                       # bottom below top
        assert tf > tb                       # more layers below F.Cu → larger RSS
        assert tf > 0

    def test_embedded_cap_gap(self, board):
        # In1↔In2 are adjacent copper either side of the 50 µm thin core:
        # centre-to-centre = 17.5 + 50 + 17.5 = 85 µm
        z1 = board.layer_z_mm("In1.Cu")[0]
        z2 = board.layer_z_mm("In2.Cu")[0]
        assert abs(z1 - z2) == pytest.approx(0.085, abs=1e-3)

    def test_unknown_layer_raises(self, board):
        with pytest.raises(KeyError):
            board.layer_z_mm("In99.Cu")


class TestResolvers:
    def test_track_polyline_constant_z(self, board):
        board.tracks.append(Track(net="N", layer="In3.Cu", width_mm=0.2,
                                  path=[(0, 0), (1, 1), (2, 0)]))
        pts = track_polyline_3d(board, board.tracks[0])
        zs = {round(z, 9) for _, _, z in pts}
        assert len(zs) == 1                                  # all on one layer
        assert pts[0][:2] == (0, 0)
        assert zs.pop() == pytest.approx(board.layer_z_mm("In3.Cu")[0])

    def test_via_segment_spans_full_thickness(self, board):
        v = Via(net="G", position_mm=(2, 3), drill_mm=0.3, pad_diameter_mm=0.6,
                from_layer="F.Cu", to_layer="B.Cu")
        (xt, yt, zt), (xb, yb, zb) = via_segment_3d(board, v)
        assert (xt, yt) == (2, 3) and (xb, yb) == (2, 3)
        assert zb == pytest.approx(0.0, abs=1e-6)
        assert zt == pytest.approx(stack_height_mm(board), abs=1e-6)

    def test_zone_polygon_at_layer_z(self, board):
        zn = Zone(net="G", layer="In1.Cu", outline_mm=[(0, 0), (5, 0), (5, 5)])
        poly = zone_polygon_3d(board, zn)
        assert len(poly) == 3
        assert all(z == pytest.approx(board.layer_z_mm("In1.Cu")[0])
                   for _, _, z in poly)


class TestCopperOnLayer:
    def test_groups_and_via_passthrough(self, board):
        board.tracks.append(Track(net="N", layer="In3.Cu", width_mm=0.2,
                                  path=[(0, 0), (1, 0)]))
        board.zones.append(Zone(net="G", layer="In1.Cu",
                               outline_mm=[(0, 0), (1, 0), (1, 1)]))
        board.vias.append(Via(net="G", position_mm=(0, 0), drill_mm=0.3,
                             pad_diameter_mm=0.6, from_layer="F.Cu",
                             to_layer="B.Cu"))
        on_in3 = copper_on_layer(board, "In3.Cu")
        assert len(on_in3["tracks"]) == 1 and on_in3["zones"] == []
        assert len(on_in3["vias"]) == 1            # through-via passes In3
        on_in1 = copper_on_layer(board, "In1.Cu")
        assert on_in1["tracks"] == [] and len(on_in1["zones"]) == 1

    @pytest.mark.skipif(not _SES.exists(), reason="routed session not present")
    def test_buckets_imported_ses(self, board):
        pr = import_session(_SES)
        board.tracks, board.vias = pr.tracks, pr.vias
        # routed copper lands on F.Cu and B.Cu
        assert copper_on_layer(board, "F.Cu")["tracks"]
        assert copper_on_layer(board, "B.Cu")["tracks"]


class TestPadChipResolvers:
    def _chip(self, **kw):
        fp = Footprint(name="BGA", pads=[Pad(num="A1", position_mm=(1.0, 0.0),
                                            size_mm=(0.3, 0.3))],
                       size_mm=(5.0, 5.0), height_mm=1.2)
        return Chip(ref="U1", footprint=fp, **kw), fp

    def test_pad_top_rotation(self, board):
        c, fp = self._chip()
        pl = Placement(position_mm=(10.0, 20.0), rotation_deg=90.0,
                       item=c, face="top", locked=False)
        x, y, z = pad_xyz(board, pl, fp.pads[0])
        # pad (1,0) rotated +90° → (0,1), translated to (10,20)
        assert (round(x, 6), round(y, 6)) == (10.0, 21.0)
        assert z == pytest.approx(board.layer_z_mm("F.Cu")[0])

    def test_pad_bottom_mirrors_x_and_uses_b_cu(self, board):
        c, fp = self._chip()
        pl = Placement(position_mm=(10.0, 20.0), rotation_deg=0.0,
                       item=c, face="bottom", locked=False)
        x, y, z = pad_xyz(board, pl, fp.pads[0])
        assert (round(x, 6), round(y, 6)) == (9.0, 20.0)      # x mirrored: 1→-1
        assert z == pytest.approx(board.layer_z_mm("B.Cu")[0])

    def test_chip_body_faces(self, board):
        c, _ = self._chip()
        top = chip_body_3d(board, Placement((0, 0), 0.0, c, "top", False))
        assert top["size_mm"] == (5.0, 5.0) and top["height_mm"] == 1.2
        assert top["base_z_mm"] == pytest.approx(board.thickness_mm)   # on top surface
        bot = chip_body_3d(board, Placement((0, 0), 0.0, c, "bottom", False))
        assert bot["base_z_mm"] == pytest.approx(-1.2)                 # hangs below z=0

    def test_board_solder_default_and_override(self, board):
        assert board_solder(board).name == "SAC305"          # profile default
        board.solder = "Sn63Pb37"
        s = board_solder(board)
        assert s.name == "Sn63Pb37" and s.leaded is True

    def test_chip_underfill_resolution(self):
        c, _ = self._chip(underfill="Loctite Eccobond UF1173")
        uf = chip_underfill(c)
        # Eccobond UF1173 flex modulus (DMA @ 25 °C, per the datasheet
        # in Research/LOCTITE-ECCOBOND-UF-1173.pdf p.8).
        assert uf is not None and uf.youngs_modulus_gpa == pytest.approx(5.9)
        # a plain chip has none
        plain, _ = self._chip()
        assert chip_underfill(plain) is None


class TestToleranceRoundTrip:
    def test_thickness_tol_survives_serialization(self, tmp_path):
        s = SmashState.new()
        s.boards["flight_board"] = Board("flight_board").set_fitted_stackup()
        out = tmp_path / "s.json"
        s.dump_json(out)
        fb = SmashState.load_json(out).boards["flight_board"]
        # inner foil carries its tolerance; thin core carries its own
        in3 = fb.layer("In3.Cu")
        assert in3.thickness_tol_um > 0
        assert in3.dielectric_below.thickness_tol_um >= 0
        # and the Z datum still computes after reload
        assert fb.layer_z_mm("F.Cu")[1] > 0
