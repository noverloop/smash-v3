"""Tests for smash.export.layered_step — per-layer STEP + JSON manifest."""
import json
import pathlib
import pytest

cq = pytest.importorskip("cadquery")

from smash import default_fab_profile
from smash.state import Board
from smash.state.routing.via import Via
from smash.export.layered_step import (
    LayerBody,
    SOLDERMASK_EPSILON_R,
    SOLDERMASK_LOSS_TANGENT,
    build_layered_board_assembly,
    write_layered_board_step,
)


@pytest.fixture
def fab():
    return default_fab_profile()


@pytest.fixture
def flight_board(fab):
    """A real rigid-tile geometry with a fitted 14L FR4 stackup."""
    return Board("flight_board").set_fitted_stackup()


@pytest.fixture
def rogers_tile(fab):
    """Synthetic rigid tile with an EXPLICIT Rogers top + no Al backing, to
    exercise the dielectric-material variation path in the layered-STEP walk.

    NOTE: the real radar_module is now plain FR4 — the 77 GHz SIW launches
    couple into the machined Al waveguide block above the tile, not the
    laminate, so Rogers was dropped. This fixture forces Rogers purely to
    cover the non-FR4 dielectric emission code; it is not the radar's config."""
    return Board("radar_module",
                 top_substrate="rogers_ro4350b_5mil").set_fitted_stackup()


# ── assembly walk ──────────────────────────────────────────────────────


class TestBuildAssembly:
    def test_returns_assembly_and_layer_records(self, flight_board, fab):
        asm, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        assert isinstance(asm, cq.Assembly)
        assert all(isinstance(l, LayerBody) for l in layers)
        # A 14L FR4 board → 14 Cu + 13 dielectrics + 2 soldermask
        # (top + bottom LPSM) = 29 bodies.
        cu = [l for l in layers if l.role == "copper"]
        diel = [l for l in layers if l.role == "dielectric"]
        mask = [l for l in layers if l.role == "soldermask"]
        assert len(cu) == 14
        assert len(diel) == 13
        assert len(mask) == 2

    def test_copper_layers_in_order(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        cu = [l for l in layers if l.role == "copper"]
        # Walking bottom-up: B.Cu, In12, In11, …, In1, F.Cu.
        assert cu[0].name.endswith(".B.Cu")
        assert cu[-1].name.endswith(".F.Cu")

    def test_z_extent_matches_total_thickness(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        # The total extent now matches `Board.thickness_mm` exactly —
        # the soldermask layers (10 µm top + 10 µm bottom from
        # `MASK_FINISH_MM`) are included in the layered walk.
        z_lo = min(l.z_min_mm for l in layers)
        z_hi = max(l.z_max_mm for l in layers)
        total = z_hi - z_lo
        assert total == pytest.approx(flight_board.thickness_mm, abs=1e-3)

    def test_layers_are_contiguous(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        # Each layer's z_min should match the previous one's z_max.
        for prev, cur in zip(layers, layers[1:]):
            assert prev.z_max_mm == pytest.approx(cur.z_min_mm, abs=1e-9)

    def test_rogers_top_emits_rogers_dielectric(self, rogers_tile, fab):
        # Mechanism test: a tile with an explicit Rogers top substrate must
        # surface a Rogers/RO4350 dielectric in the layered walk. (The real
        # radar_module is FR4 now — see the rogers_tile fixture note.)
        _, layers = build_layered_board_assembly(
            rogers_tile, fab=fab, with_components=False)
        materials = {l.material for l in layers if l.role == "dielectric"}
        assert any("Rogers" in m or "RO4350" in m for m in materials), \
            f"expected Rogers in {materials}"

    def test_al_backing_when_set(self, fab):
        b = Board("camera_module", al_backing_mm=0.5).set_fitted_stackup()
        _, layers = build_layered_board_assembly(b, fab=fab,
                                                  with_components=False)
        metals = [l for l in layers if l.role == "metal_backing"]
        assert len(metals) == 1
        assert metals[0].material == "aluminium"
        assert metals[0].thickness_mm == pytest.approx(0.5)

    def test_no_al_backing_when_zero(self, fab):
        # radar_module currently has no tile-Al backing — should yield
        # zero metal_backing bodies.
        b = Board("radar_module",
                  top_substrate="rogers_ro4350b_5mil").set_fitted_stackup()
        _, layers = build_layered_board_assembly(b, fab=fab,
                                                  with_components=False)
        assert not any(l.role == "metal_backing" for l in layers)


class TestCuCoinInsert:
    """A board carrying a CuCoinInsert should emit a coin Cu prism with
    matching material props, AND have its overlapping FR4/Cu layers
    pocket-cut so the coin slots into a hole rather than overlapping."""

    @pytest.fixture
    def coin_board(self, fab):
        from smash.state import CuCoinInsert
        b = Board("radar_module",
                  top_substrate="rogers_ro4350b_5mil",
                  copper_layers=20).set_fitted_stackup()
        b.cu_coin_inserts = [CuCoinInsert(
            position_mm=(0.0, 0.0),
            length_mm=20.0, width_mm=20.0,
            ladder_length_mm=16.0, ladder_width_mm=16.0,
            thickness_mm=3.0, z_top_mm=3.15,
            flange_thickness_mm=0.5,
            corner_chamfer_radius_mm=5.0,
            kind="T",
        )]
        return b

    def test_coin_emitted_as_cu_prism(self, coin_board, fab):
        _, layers = build_layered_board_assembly(
            coin_board, fab=fab, with_components=False)
        coins = [l for l in layers if l.role == "cu_coin"]
        assert len(coins) == 1
        coin_layer = coins[0]
        # Material + key EM/mech constants present.
        assert coin_layer.material == "copper"
        assert coin_layer.conductivity_s_m and coin_layer.conductivity_s_m > 1e7
        assert coin_layer.density_kg_m3 == pytest.approx(8960.0, abs=10)
        assert coin_layer.thickness_mm == pytest.approx(3.0)
        # Note carries the NCAB symbol summary for the solver consumer.
        assert "NCAB" in (coin_layer.note or "")
        assert "shortcut" in (coin_layer.note or "")

    def test_coin_z_range_inside_board(self, coin_board, fab):
        _, layers = build_layered_board_assembly(
            coin_board, fab=fab, with_components=False)
        coin = next(l for l in layers if l.role == "cu_coin")
        # The coin must sit between B.Cu and F.Cu (board's z extent).
        cu_layers = [l for l in layers if l.role == "copper"]
        z_lo = min(l.z_min_mm for l in cu_layers)
        z_hi = max(l.z_max_mm for l in cu_layers)
        assert z_lo <= coin.z_min_mm < coin.z_max_mm <= z_hi + 0.05

    def test_no_coin_emitted_when_board_has_none(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        assert not any(l.role == "cu_coin" for l in layers)


class TestMaterialPropertiesPopulated:
    def test_copper_carries_conductivity(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        cu = next(l for l in layers if l.role == "copper")
        assert cu.conductivity_s_m is not None
        assert cu.conductivity_s_m > 1e7        # bulk-Cu order of magnitude

    def test_dielectric_carries_epsilon(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        diel = next(l for l in layers if l.role == "dielectric")
        assert diel.epsilon_r is not None
        assert diel.epsilon_r > 1.0

    def test_copper_carries_mechanical(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        cu = next(l for l in layers if l.role == "copper")
        assert cu.youngs_modulus_gpa is not None
        assert cu.density_kg_m3 is not None
        # Bulk Cu density 8960 kg/m³ — fab profile defaults match.
        assert cu.density_kg_m3 == pytest.approx(8960.0, abs=10)


# ── writer + JSON manifest ────────────────────────────────────────────


class TestWriteLayered:
    def test_writes_step_and_json(self, tmp_path, flight_board, fab):
        out = tmp_path / "flight_layered.step"
        r = write_layered_board_step(flight_board, out, fab=fab,
                                       with_components=False)
        step_p = pathlib.Path(r["output_step_path"])
        json_p = pathlib.Path(r["output_json_path"])
        assert step_p.exists() and step_p.stat().st_size > 1000
        assert json_p.exists() and json_p.stat().st_size > 100

    def test_json_round_trip(self, tmp_path, flight_board, fab):
        out = tmp_path / "flight_layered.step"
        write_layered_board_step(flight_board, out, fab=fab,
                                  with_components=False)
        manifest = json.loads((tmp_path / "flight_layered.json").read_text())
        assert manifest["board"] == "flight_board"
        assert manifest["layer_count"] == len(manifest["bodies"])
        # Every body has the required keys.
        for body in manifest["bodies"]:
            for k in ("name", "role", "material", "thickness_mm",
                      "z_min_mm", "z_max_mm"):
                assert k in body, f"missing {k!r} in {body['name']}"

    def test_summary_dict_counts(self, tmp_path, flight_board, fab):
        out = tmp_path / "flight_layered"
        r = write_layered_board_step(flight_board, out, fab=fab,
                                       with_components=False)
        assert r["n_copper"] == 14
        assert r["n_dielectric"] == 13
        assert r["n_soldermask"] == 2     # top + bottom LPSM
        assert r["n_via_barrel"] == 0     # no routing on this board
        assert r["n_metal"] == 0
        assert r["n_chip"] == 0
        assert r["n_bodies"] == (r["n_copper"] + r["n_dielectric"]
                                  + r["n_soldermask"])

    def test_explicit_no_al_backing_flag(self, tmp_path, fab):
        b = Board("camera_module", al_backing_mm=0.5).set_fitted_stackup()
        out = tmp_path / "cam_layered"
        r = write_layered_board_step(b, out, fab=fab,
                                       with_components=False,
                                       with_al_backing=False)
        assert r["n_metal"] == 0


# ── soldermask ────────────────────────────────────────────────────────


class TestSoldermask:
    def test_top_and_bottom_mask_emitted(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        masks = [l for l in layers if l.role == "soldermask"]
        assert len(masks) == 2
        names = {m.name for m in masks}
        assert any(n.endswith(".soldermask_top") for n in names)
        assert any(n.endswith(".soldermask_bottom") for n in names)

    def test_mask_thickness_matches_mask_finish(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        masks = [l for l in layers if l.role == "soldermask"]
        per_side = flight_board.MASK_FINISH_MM / 2.0
        for m in masks:
            assert m.thickness_mm == pytest.approx(per_side)

    def test_mask_em_properties_set(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        m = next(l for l in layers if l.role == "soldermask")
        assert m.epsilon_r == SOLDERMASK_EPSILON_R
        assert m.loss_tangent == SOLDERMASK_LOSS_TANGENT
        assert m.material == "LPSM"

    def test_bottom_mask_sits_below_b_cu(self, flight_board, fab):
        """LPSM coats the outside of B.Cu — z(bottom mask) < z(B.Cu)."""
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        b_cu = next(l for l in layers if l.name.endswith(".B.Cu"))
        bot_mask = next(l for l in layers
                        if l.name.endswith(".soldermask_bottom"))
        assert bot_mask.z_max_mm == pytest.approx(b_cu.z_min_mm)

    def test_top_mask_sits_above_f_cu(self, flight_board, fab):
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        f_cu = next(l for l in layers if l.name.endswith(".F.Cu"))
        top_mask = next(l for l in layers
                        if l.name.endswith(".soldermask_top"))
        assert top_mask.z_min_mm == pytest.approx(f_cu.z_max_mm)


# ── via barrels ───────────────────────────────────────────────────────


class TestViaBarrels:
    def test_no_vias_no_barrels(self, flight_board, fab):
        # Real boards have empty Board.vias until .ses is imported.
        flight_board.vias = []
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        assert not any(l.role == "via_barrel" for l in layers)

    def test_through_via_spans_full_stack(self, flight_board, fab):
        flight_board.vias = [Via(
            net="GND", position_mm=(0, 0), drill_mm=0.3,
            pad_diameter_mm=0.6,
            from_layer="F.Cu", to_layer="B.Cu",
            kind="stitching",
        )]
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        barrels = [l for l in layers if l.role == "via_barrel"]
        assert len(barrels) == 1
        b = barrels[0]
        b_cu = next(l for l in layers if l.name.endswith(".B.Cu"))
        f_cu = next(l for l in layers if l.name.endswith(".F.Cu"))
        # Barrel spans from below B.Cu to above F.Cu (encompasses
        # the full Cu stack).
        assert b.z_min_mm == pytest.approx(b_cu.z_min_mm)
        assert b.z_max_mm == pytest.approx(f_cu.z_max_mm)

    def test_buried_via_partial_span(self, flight_board, fab):
        """A via from In3 to In8 spans only the middle of the stack."""
        flight_board.vias = [Via(
            net="X", position_mm=(2, 2), drill_mm=0.2,
            pad_diameter_mm=0.4,
            from_layer="In3.Cu", to_layer="In8.Cu",
        )]
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        b = next(l for l in layers if l.role == "via_barrel")
        # Less than total stack thickness.
        full_extent = (max(l.z_max_mm for l in layers)
                       - min(l.z_min_mm for l in layers))
        assert b.thickness_mm < full_extent
        assert b.thickness_mm > 0

    def test_unknown_layer_skipped(self, flight_board, fab):
        """Via referencing a layer not in the stackup is silently dropped."""
        flight_board.vias = [
            Via(net="GND", position_mm=(0, 0), drill_mm=0.3,
                pad_diameter_mm=0.6,
                from_layer="In99.Cu", to_layer="B.Cu"),
        ]
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        assert not any(l.role == "via_barrel" for l in layers)

    def test_via_marked_as_copper(self, flight_board, fab):
        flight_board.vias = [Via(
            net="GND", position_mm=(0, 0), drill_mm=0.3,
            pad_diameter_mm=0.6,
            from_layer="F.Cu", to_layer="B.Cu",
        )]
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        b = next(l for l in layers if l.role == "via_barrel")
        assert b.material == "copper"
        assert b.conductivity_s_m is not None
        assert b.conductivity_s_m > 1e7


# ── mask openings over pads ───────────────────────────────────────────


class TestMaskOpenings:
    @pytest.fixture
    def board_with_top_chip(self, fab):
        """A board with one top-face chip whose footprint has 4 pads —
        small enough to count manually."""
        from smash.state import Chip, Footprint
        from smash.state.pad import Pad
        from smash.state.topology.placement import Placement
        b = Board("flight_board").set_fitted_stackup()
        fp = Footprint(
            name="QFN4", package_class="QFN",
            pads=[
                Pad(num="1", position_mm=(-1, 0), size_mm=(0.5, 0.3),
                    shape="rect", layer="F.Cu"),
                Pad(num="2", position_mm=(1, 0), size_mm=(0.5, 0.3),
                    shape="rect", layer="F.Cu"),
                Pad(num="3", position_mm=(0, -1), size_mm=(0.3, 0.5),
                    shape="rect", layer="F.Cu"),
                Pad(num="4", position_mm=(0, 1), size_mm=(0.3, 0.5),
                    shape="rect", layer="F.Cu"),
            ],
        )
        chip = Chip(ref="U1", manf_pn="X", footprint=fp)
        b.chip_placements.append(Placement(
            position_mm=(5, 5), rotation_deg=0.0, item=chip,
            face="top", locked=False))
        return b

    def test_openings_counted_in_note(self, board_with_top_chip, fab):
        _, layers = build_layered_board_assembly(
            board_with_top_chip, fab=fab, with_components=False)
        top_mask = next(l for l in layers
                        if l.name.endswith(".soldermask_top"))
        assert "4 pad openings cut" in top_mask.note

    def test_no_pads_on_face_no_openings(self, board_with_top_chip, fab):
        _, layers = build_layered_board_assembly(
            board_with_top_chip, fab=fab, with_components=False)
        # No bottom-face chips → bottom mask has 0 openings.
        bot_mask = next(l for l in layers
                        if l.name.endswith(".soldermask_bottom"))
        assert "0 pad openings cut" in bot_mask.note

    def test_real_radar_module_openings(self, fab):
        """Smoke test against the actual radar tile: pads on F.Cu from
        the AWR2944, LDOs, decoupling caps etc. should produce many
        openings."""
        b = Board("radar_module",
                  top_substrate="rogers_ro4350b_5mil").set_fitted_stackup()
        # No placements in this synthetic — zero openings is fine.
        _, layers = build_layered_board_assembly(
            b, fab=fab, with_components=False)
        top_mask = next(l for l in layers
                        if l.name.endswith(".soldermask_top"))
        assert "0 pad openings cut" in top_mask.note


# ── routing-driven Cu pattern ─────────────────────────────────────────


class TestCuPattern:
    def test_no_routing_falls_back_to_full_disc(self, flight_board, fab):
        """Without any tracks / zones / pads on a layer, the Cu pattern
        falls back to a full disc — flagged in the note so a solver
        knows it's the conservative approximation."""
        _, layers = build_layered_board_assembly(
            flight_board, fab=fab, with_components=False)
        cu_layers = [l for l in layers if l.role == "copper"]
        for l in cu_layers:
            assert "unrouted" in l.note

    def test_track_emitted_as_pattern(self, fab):
        from smash.state import Track
        b = Board("flight_board").set_fitted_stackup()
        b.tracks.append(Track(net="X", layer="F.Cu", width_mm=0.2,
                                path=[(0, 0), (1, 0)]))
        _, layers = build_layered_board_assembly(
            b, fab=fab, with_components=False)
        f_cu = next(l for l in layers if l.name.endswith(".F.Cu"))
        assert "etched pattern" in f_cu.note
        assert "1 track segments" in f_cu.note

    def test_zone_emitted_as_pattern(self, fab):
        from smash.state import Zone
        b = Board("flight_board").set_fitted_stackup()
        b.zones.append(Zone(net="GND", layer="In3.Cu",
                              outline_mm=[(0, 0), (5, 0), (5, 5), (0, 5)]))
        _, layers = build_layered_board_assembly(
            b, fab=fab, with_components=False)
        in3 = next(l for l in layers if l.name.endswith(".In3.Cu"))
        assert "1 zones" in in3.note

    def test_pads_emit_on_outer_layers(self, fab):
        """Even without tracks or zones, pads on F.Cu still produce an
        etched-pattern note (and the disc fallback is NOT applied)."""
        from smash.state import Chip, Footprint
        from smash.state.pad import Pad
        from smash.state.topology.placement import Placement
        b = Board("flight_board").set_fitted_stackup()
        fp = Footprint(name="P", pads=[
            Pad(num="1", position_mm=(0, 0), size_mm=(0.3, 0.3),
                shape="rect", layer="F.Cu"),
        ])
        c = Chip(ref="U1", manf_pn="X", footprint=fp)
        b.chip_placements.append(Placement(
            position_mm=(0, 0), rotation_deg=0.0, item=c,
            face="top", locked=False))
        _, layers = build_layered_board_assembly(
            b, fab=fab, with_components=False)
        f_cu = next(l for l in layers if l.name.endswith(".F.Cu"))
        assert "1 pads" in f_cu.note
        b_cu = next(l for l in layers if l.name.endswith(".B.Cu"))
        assert "unrouted" in b_cu.note    # no pads on bottom

    def test_inner_layers_skip_pads(self, fab):
        """Pads attach to outer Cu only — inner layers should never
        report pad-driven features."""
        from smash.state import Chip, Footprint
        from smash.state.pad import Pad
        from smash.state.topology.placement import Placement
        b = Board("flight_board").set_fitted_stackup()
        fp = Footprint(name="P", pads=[
            Pad(num="1", position_mm=(0, 0), size_mm=(0.3, 0.3),
                shape="rect", layer="F.Cu"),
        ])
        c = Chip(ref="U1", manf_pn="X", footprint=fp)
        b.chip_placements.append(Placement(
            position_mm=(0, 0), rotation_deg=0.0, item=c,
            face="top", locked=False))
        _, layers = build_layered_board_assembly(
            b, fab=fab, with_components=False)
        # Pick a random inner Cu layer
        in5 = next(l for l in layers if l.name.endswith(".In5.Cu"))
        assert "unrouted" in in5.note
