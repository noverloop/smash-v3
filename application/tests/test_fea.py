"""Smoke + unit tests for the CalculiX pipeline.

The CCX subprocess test is skipped if no ccx binary is found, so the
suite runs cleanly on CI without CalculiX installed."""
import pathlib

import pytest

from smash.sim.fea import (
    CCX_BINARY_DEFAULT, find_ccx_binary,
    write_ccx_inp, parse_frd, CCXDeck,
)
from smash.sim.fea.ccx_writer import (
    CCXMaterial, CCXElementSet, CCXBoundary, CCXBodyLoad, CCXStep,
    ELEMENT_TYPE_LINEAR_HEX,
)


# Skip the subprocess test if CalculiX isn't installed.
_HAS_CCX = CCX_BINARY_DEFAULT is not None
_CCX_REASON = ("CalculiX binary not found; install via "
               "`brew install calculix-ccx` or set CCX_BIN")


def _cube_deck(magnitude=9.81) -> CCXDeck:
    """An 8-node hex cube under body force, clamped at x=0."""
    L = 10e-3
    nodes = [
        (1, 0, 0, 0), (2, L, 0, 0), (3, L, L, 0), (4, 0, L, 0),
        (5, 0, 0, L), (6, L, 0, L), (7, L, L, L), (8, 0, L, L),
    ]
    return CCXDeck(
        job_name="cube",
        node_coords=nodes,
        elements=[(1, ELEMENT_TYPE_LINEAR_HEX,
                    [1, 2, 3, 4, 5, 6, 7, 8])],
        element_sets=[CCXElementSet(name="ESET", element_ids=[1],
                                     material_name="FR4")],
        node_sets={"FIXED": [1, 4, 5, 8]},
        materials=[CCXMaterial(name="FR4", youngs_modulus_pa=20e9,
                                poisson_ratio=0.30,
                                density_kg_m3=1850.0)],
        boundaries=[CCXBoundary(nset_name="FIXED",
                                 dof_first=1, dof_last=3)],
        steps=[CCXStep(name="g", static=True,
                       body_loads=[CCXBodyLoad(
                           elset_name="ESET",
                           magnitude_m_per_s2=magnitude,
                           direction=(0, 0, -1))])],
    )


class TestCCXWriter:
    def test_writes_inp_with_required_cards(self, tmp_path):
        deck = _cube_deck()
        out = tmp_path / "cube.inp"
        path = write_ccx_inp(deck, out)
        text = pathlib.Path(path).read_text()
        # Every CCX deck needs these card kinds.
        for card in ("*NODE", "*ELEMENT", "*MATERIAL", "*ELASTIC",
                     "*DENSITY", "*SOLID SECTION", "*BOUNDARY",
                     "*STEP", "*STATIC", "*DLOAD", "*END STEP"):
            assert card in text, f"missing card {card!r}"

    def test_node_set_names_emit(self, tmp_path):
        deck = _cube_deck()
        path = write_ccx_inp(deck, tmp_path / "cube.inp")
        text = pathlib.Path(path).read_text()
        assert "*NSET, NSET=FIXED" in text

    def test_dynamic_step_emits_explicit_card(self, tmp_path):
        deck = _cube_deck()
        deck.steps[0].static = False
        deck.steps[0].dynamic_t_total_s = 0.01
        path = write_ccx_inp(deck, tmp_path / "cube.inp")
        text = pathlib.Path(path).read_text()
        assert "*DYNAMIC, EXPLICIT" in text
        assert "*STATIC" not in text


class TestCCXBinarySearch:
    def test_finder_returns_path_or_none(self):
        # The finder must return a string path or None; never crash.
        p = find_ccx_binary()
        assert p is None or isinstance(p, str)
        if p:
            assert pathlib.Path(p).exists()


@pytest.mark.skipif(not _HAS_CCX, reason=_CCX_REASON)
class TestCCXEndToEnd:
    """Round-trips a tiny deck through ccx_2.23 + the .frd parser."""

    def test_cube_under_gravity_runs_cleanly(self, tmp_path):
        from smash.sim.fea import run_ccx
        deck = _cube_deck(magnitude=9.81)
        inp = write_ccx_inp(deck, tmp_path / "cube.inp")
        res = run_ccx(inp, check=True)
        assert res.return_code == 0
        assert res.frd_path is not None
        r = parse_frd(res.frd_path)
        # 8 nodes, displacement field has 3 components.
        assert len(r.nodes) == 8
        disp = r.displacements()
        assert disp is not None
        assert disp.component_names == ["D1", "D2", "D3"]
        # Clamped face (nodes 1, 4, 5, 8) sees zero displacement.
        for nid in (1, 4, 5, 8):
            ux, uy, uz = disp.values_by_node[nid]
            assert abs(ux) + abs(uy) + abs(uz) < 1e-15
        # Free face (nodes 2, 3, 6, 7) sees nonzero deflection.
        assert abs(disp.values_by_node[2][2]) > 1e-12

    def test_stress_field_carries_six_components(self, tmp_path):
        from smash.sim.fea import run_ccx
        deck = _cube_deck()
        inp = write_ccx_inp(deck, tmp_path / "cube.inp")
        res = run_ccx(inp, check=True)
        r = parse_frd(res.frd_path)
        s = r.stresses()
        assert s is not None
        # CCX stress in Voigt order: SXX, SYY, SZZ, SXY, SYZ, SZX.
        assert s.component_names == ["SXX", "SYY", "SZZ",
                                      "SXY", "SYZ", "SZX"]
        assert len(s.values_by_node) == 8


class TestSurfaceAndTie:
    def test_node_surface_emits_type_node_card(self, tmp_path):
        from smash.sim.fea.ccx_writer import CCXSurface, CCXTie
        deck = _cube_deck()
        deck.surfaces = [CCXSurface(name="S_BOT", kind="node",
                                     nset_name="FIXED")]
        path = write_ccx_inp(deck, tmp_path / "cube.inp")
        text = pathlib.Path(path).read_text()
        assert "*SURFACE, NAME=S_BOT, TYPE=NODE" in text
        assert "FIXED" in text

    def test_element_surface_emits_face_id(self, tmp_path):
        from smash.sim.fea.ccx_writer import CCXSurface
        deck = _cube_deck()
        deck.surfaces = [CCXSurface(name="S_TOP", kind="element",
                                     element_faces=[("ESET", "S2")])]
        path = write_ccx_inp(deck, tmp_path / "cube.inp")
        text = pathlib.Path(path).read_text()
        assert "*SURFACE, NAME=S_TOP, TYPE=ELEMENT" in text
        assert "ESET, S2" in text

    def test_tie_card_emits_with_adjust_no(self, tmp_path):
        from smash.sim.fea.ccx_writer import CCXSurface, CCXTie
        deck = _cube_deck()
        deck.surfaces = [
            CCXSurface(name="S_M", kind="element",
                        element_faces=[("ESET", "S2")]),
            CCXSurface(name="S_S", kind="node", nset_name="FIXED"),
        ]
        deck.ties = [CCXTie(name="T1", slave_surface="S_S",
                             master_surface="S_M")]
        path = write_ccx_inp(deck, tmp_path / "cube.inp")
        text = pathlib.Path(path).read_text()
        assert "*TIE, NAME=T1, ADJUST=NO" in text
        assert "S_S, S_M" in text


class TestReport:
    """Phase D: report module maps CCX stresses to chip pad node sets
    and emits per-chip verdicts. Uses synthetic FRD/mesh to avoid the
    full design-build round trip."""

    def _synthetic_setup(self):
        from smash.sim.fea.frd_parser import FRDResult, FRDField
        from smash.sim.fea.mesh import BoardMesh, MeshElement
        from smash.state import Board
        b = Board("power_board").set_fitted_stackup()
        # One chip's pad-proxy node set with 4 nodes; FRD provides
        # a stress at each. Real placement isn't needed since the
        # report walks chip_placements then mesh.node_sets directly.
        from smash.state import Chip, Footprint, Pad, Placement
        fp = Footprint(name="X", pads=[Pad(num="1", position_mm=(0, 0),
                                            size_mm=(0.3, 0.3))],
                       size_mm=(2.0, 2.0), height_mm=1.0)
        c = Chip(ref="U_TEST", manf_pn="X", footprint=fp)
        b.chip_placements = [Placement(position_mm=(0, 0),
                                        rotation_deg=0, item=c)]
        mesh = BoardMesh(
            board_name="power_board",
            node_coords=[(1, 0, 0, 0), (2, 1e-3, 0, 0),
                          (3, 1e-3, 1e-3, 0), (4, 0, 1e-3, 0)],
            elements=[],
            element_sets={},
            node_sets={"CHIP_PAD_U_TEST": [1, 2, 3, 4]},
            z_layer_records=[],
        )
        # Synthetic FRD: 4 nodes, one has σ_zz = -20 MPa, σ_yz = 5 MPa.
        # σ_vm ≈ √((20)² + 3·(5²)) = √(400 + 75) ≈ 21.8 MPa.
        stress_field = FRDField(
            label="STRESS", step_number=1, total_time=1.0,
            component_names=["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"],
            values_by_node={
                1: (0, 0, 0, 0, 0, 0),
                2: (0, 0, 0, 0, 0, 0),
                3: (0, 0, -20e6, 0, 5e6, 0),  # the worst
                4: (0, 0, 0, 0, 0, 0),
            },
        )
        frd = FRDResult(
            fields=[stress_field],
            nodes={1: (0, 0, 0), 2: (1e-3, 0, 0),
                    3: (1e-3, 1e-3, 0), 4: (0, 1e-3, 0)},
            job_name="synthetic",
        )
        return frd, mesh, b

    def test_evaluate_chip_verdicts_picks_worst_pad_node(self):
        from smash.sim.fea import evaluate_chip_verdicts
        from smash import default_fab_profile
        frd, mesh, b = self._synthetic_setup()
        result = evaluate_chip_verdicts(frd, mesh, b,
                                         fab=default_fab_profile())
        assert len(result.chips) == 1
        v = result.chips[0]
        assert v.ref == "U_TEST"
        assert v.pad_node_id == 3
        # σ_vm = √((20)² + 3·(5)²) = √475 ≈ 21.79 MPa
        assert 21.0 < v.sigma_vm_mpa < 22.5
        # Tensile principal: σ_zz = -20 is compressive, but σ_yz = 5
        # gives a positive eigenvalue ≈ 5 MPa.
        assert v.sigma_tension_mpa >= 0
        assert v.binding_mode in ("shear", "tension", "vm")

    def test_write_report_emits_md_and_json(self, tmp_path):
        from smash.sim.fea import evaluate_chip_verdicts, write_report
        from smash import default_fab_profile
        frd, mesh, b = self._synthetic_setup()
        result = evaluate_chip_verdicts(frd, mesh, b,
                                         fab=default_fab_profile())
        s = write_report(result, tmp_path, platform_label="testplat")
        md = (tmp_path / "report.md").read_text()
        js = (tmp_path / "report.json").read_text()
        assert "U_TEST" in md
        assert "testplat" in md
        assert s["n_chips"] == 1
        # JSON round-trips
        import json
        d = json.loads(js)
        assert d["board"] == "power_board"
        assert d["chips"][0]["ref"] == "U_TEST"


class TestStycastPotting:
    """Phase B: mesh.include_potting=True emits Stycast 2651MM fill
    elements above F.Cu. Shares bottom-face nodes with F.Cu so the
    potting block is automatically bonded to the board."""

    @pytest.fixture
    def panel_radar(self):
        # Lazy import: only the FEA suite needs the full design build.
        import sys, pathlib as _pl
        REPO = _pl.Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(REPO))
        import generate_maximalist_system as gen
        from smash import Design
        from smash.layout.boards.smash_evb_v1 import build_panel
        from smash.layout.placer import place_design
        d = Design()
        gen._prime_power_rails(d)
        gen.build_radar_module(d)
        d.apply_default_underfill()
        panel, boards = build_panel()
        gen.build_spacers(d, boards)
        place_design(d, panel, boards)
        return d, boards["radar_module"]

    def test_potting_emits_stycast_fill_elset(self, panel_radar):
        from smash.sim.fea.mesh import build_board_mesh
        _, b = panel_radar
        m = build_board_mesh(b, xy_element_mm=1.5,
                              include_chip_blocks=True,
                              include_potting=True)
        assert "STYCAST_FILL" in m.element_sets
        assert len(m.element_sets["STYCAST_FILL"]) > 0

    def test_potting_skips_chip_body_volume_not_just_xy(self, panel_radar):
        """No Stycast element's xyz centroid lies inside any chip body
        AABB — the chip block + UF brick already occupy that volume.
        Stycast ABOVE a chip (xy inside, but z above the chip's top
        face) IS retained, so the chip-top tie has a face to project
        onto (Phase F)."""
        from smash.sim.fea.mesh import (
            build_board_mesh, _chip_blocks_xyz_aabb, _xyz_in_chip_body,
            UNDERFILL_THICKNESS_MM_DEFAULT,
        )
        _, b = panel_radar
        m = build_board_mesh(b, xy_element_mm=1.5,
                              include_chip_blocks=True,
                              include_potting=True)
        # Same z anchor the mesh uses: total stackup thickness.
        z_top_board_mm = sum(
            (z_hi - z_lo) for (z_lo, z_hi, _) in m.z_layer_records
        )
        aabbs = _chip_blocks_xyz_aabb(
            b, z_top_board_mm=z_top_board_mm,
            underfill_thickness_mm=UNDERFILL_THICKNESS_MM_DEFAULT,
        )
        for eid in m.element_sets["STYCAST_FILL"]:
            elem = next(e for e in m.elements if e.eid == eid)
            cx, cy, cz = elem.centroid_xyz_mm
            assert not _xyz_in_chip_body(cx, cy, cz, aabbs), (
                f"Stycast element {eid} centroid ({cx:.2f}, {cy:.2f},"
                f" {cz:.2f}) lies inside a chip body"
            )

    def test_potting_shares_fcu_nodes(self, panel_radar):
        """Bottom face of every STYCAST_FILL cell at z=z_top_board
        ships an EXISTING F.Cu node (shared-node bonding) — verify by
        checking that some STYCAST_FILL cell's lowest node is in the
        FCU_TOP node set."""
        from smash.sim.fea.mesh import build_board_mesh
        _, b = panel_radar
        m = build_board_mesh(b, xy_element_mm=1.5,
                              include_chip_blocks=True,
                              include_potting=True)
        fcu_top = set(m.node_sets["FCU_TOP"])
        # Coords lookup so we can identify the lowest-z node of each cell.
        z_lookup = {nid: zm for (nid, _, _, zm) in m.node_coords}
        n_shared = 0
        for eid in m.element_sets["STYCAST_FILL"][:50]:    # sample
            elem = next(e for e in m.elements if e.eid == eid)
            lowest = min(elem.nodes, key=lambda n: z_lookup[n])
            if lowest in fcu_top:
                n_shared += 1
        assert n_shared > 0, "no Stycast cell shares F.Cu nodes"
