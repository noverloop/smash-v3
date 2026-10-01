"""Tests for the trace bend-strain study + the free-span trace coupon.

The CCX end-to-end cases are skipped when no ccx binary is present, so
the suite stays green on CI. The deck-assembly and evaluator tests run
everywhere (no solver needed)."""
import math
import pathlib

import pytest

from smash.sim.fea import (
    CCX_BINARY_DEFAULT, write_ccx_inp, parse_frd,
)
from smash.sim.fea.ccx_writer import (
    CCXStep, CCXBodyLoad, CCXNodalLoad, CCXDeck, CCXMaterial,
    CCXElementSet, CCXBoundary, ELEMENT_TYPE_LINEAR_HEX,
)
from smash.sim.fea.coupon import (
    TraceCouponSpec, build_trace_coupon_deck, evaluate_coupon,
    ELEMENT_TYPE_HEX_INCOMPAT, _build_mesh,
)
from smash.sim.fea.via_coupon import (
    ViaCouponSpec, build_via_coupon_deck, evaluate_via_coupon,
)
from smash.sim.fea.trace_strain import (
    CopperAllowable, evaluate_trace_strain, _max_principal_strain,
    _vm_strain,
)

_HAS_CCX = CCX_BINARY_DEFAULT is not None
_CCX_REASON = "CalculiX binary not found"


# ── strain tensor helpers ───────────────────────────────────────────────


class TestStrainTensorMath:
    def test_uniaxial_principal_strain(self):
        # ε_xx = 1 %, all else 0 → max principal = 1 %.
        assert abs(_max_principal_strain((0.01, 0, 0, 0, 0, 0)) - 0.01) < 1e-12

    def test_principal_with_shear(self):
        # Pure in-plane shear ε_xy = 0.5 % (tensor) → principal = 0.5 %.
        e = (0.0, 0.0, 0.0, 0.005, 0.0, 0.0)
        assert abs(_max_principal_strain(e) - 0.005) < 1e-9

    def test_vm_strain_uniaxial(self):
        # Uniaxial ε with ν≈0.5-style deviatoric → ε_vm == ε for the
        # incompressible split (εyy=εzz=-ε/2).
        e = (0.01, -0.005, -0.005, 0, 0, 0)
        assert abs(_vm_strain(e) - 0.01) < 1e-6


class TestCopperAllowable:
    def test_yield_strain_is_sigma_over_E(self):
        a = CopperAllowable()
        assert abs(a.yield_strain - (70e6 / 117e9)) < 1e-9
        # ~0.06 %: copper yields very early — well below any elongation.
        assert a.yield_strain < a.elongation_min


class TestFoilDuctility:
    def test_foil_type_classification(self):
        from smash.state.fab.foil import CopperFoil
        ra = CopperFoil(weight_oz=1, thickness_um=35, foil_type="RA",
                        elongation_pct=20)
        rtf = CopperFoil(weight_oz=1, thickness_um=35, foil_type="RTF")
        ed = CopperFoil(weight_oz=1, thickness_um=35, foil_type="ED")
        # RA is the ductile sheet; RTF is a low-ROUGHNESS RF foil (ED
        # ductility), NOT a ductility upgrade — the key correction.
        assert ra.is_ductile and not ra.is_low_profile
        assert rtf.is_low_profile and not rtf.is_ductile
        assert not ed.is_ductile and not ed.is_low_profile

    def test_catalog_has_ra_foil(self):
        from smash import default_fab_profile
        ra = [f for f in default_fab_profile().foils if f.foil_type == "RA"]
        assert ra, "default catalog should offer a rolled-annealed foil"
        assert ra[0].elongation_pct >= 15

    def test_catalog_foils_carry_ncab_processed_thickness(self):
        from smash import default_fab_profile
        half = next(f for f in default_fab_profile().foils
                    if f.weight_oz == 0.5 and f.foil_type == "ED")
        # NCAB Stackups guide: 18 µm inner → 11.4 µm min after processing.
        assert abs(half.min_processed_thickness_um - 11.4) < 0.1

    def test_allowable_from_foil_rewards_ductility(self):
        from smash import default_fab_profile
        foils = default_fab_profile().foils
        ed = next(f for f in foils if f.foil_type == "ED")
        ra = next(f for f in foils if f.foil_type == "RA")
        a_ed = CopperAllowable.from_foil(ed)
        a_ra = CopperAllowable.from_foil(ra)
        assert a_ra.elongation_min > a_ed.elongation_min
        assert abs(a_ed.elongation_min - 0.03) < 1e-6   # ED → 3 % floor
        assert abs(a_ra.elongation_min - 0.06) < 1e-6   # RA → 6 % floor


# ── coupon deck assembly (no solver) ────────────────────────────────────


class TestCouponDeck:
    def test_deck_has_copper_and_bodyload(self):
        spec = TraceCouponSpec(width_mm=0.1, thickness_um=35.0, gap_mm=1.0)
        deck, mesh = build_trace_coupon_deck(
            spec, accel_m_per_s2=1000.0, direction="forward")
        assert deck.materials[0].name == "COPPER"
        assert deck.element_sets[0].name == "TRACE"
        # Every element is the incompatible-modes hex.
        assert all(e[1] == ELEMENT_TYPE_HEX_INCOMPAT for e in deck.elements)
        # Node sets + clamp BC on the lands.
        assert deck.node_sets["LANDS"]
        assert deck.node_sets["SPAN"]
        assert deck.boundaries[0].nset_name == "LANDS"
        assert (deck.boundaries[0].dof_first, deck.boundaries[0].dof_last) == (1, 3)
        bl = deck.steps[0].body_loads[0]
        assert bl.direction == (0.0, 0.0, -1.0)
        assert bl.magnitude_m_per_s2 == 1000.0

    def test_reverse_flips_body_force(self):
        spec = TraceCouponSpec()
        deck, _ = build_trace_coupon_deck(
            spec, accel_m_per_s2=1.0, direction="reverse")
        assert deck.steps[0].body_loads[0].direction == (0.0, 0.0, +1.0)

    def test_span_excludes_lands_but_includes_lips(self):
        spec = TraceCouponSpec(width_mm=0.1, thickness_um=35.0,
                               gap_mm=1.0, anchor_mm=0.3)
        mesh = _build_mesh(spec)
        # Fixed lands and the evaluated span are both non-empty, and the
        # span is a strict subset focused on the free region + lips.
        assert len(mesh.fixed_node_ids) > 0
        assert len(mesh.span_node_ids) > 0
        xs = [c[1] for c in mesh.node_coords]          # metres
        assert min(xs) == 0.0
        assert abs(max(xs) - spec.total_length_mm * 1e-3) < 1e-9

    def test_nlgeom_emits_card(self, tmp_path):
        deck, _ = build_trace_coupon_deck(
            TraceCouponSpec(), accel_m_per_s2=1.0, nlgeom=True)
        path = write_ccx_inp(deck, tmp_path / "c.inp")
        text = pathlib.Path(path).read_text()
        assert "*STEP, NLGEOM" in text
        assert ELEMENT_TYPE_HEX_INCOMPAT in text

    def test_linear_step_has_no_nlgeom(self, tmp_path):
        deck, _ = build_trace_coupon_deck(
            TraceCouponSpec(), accel_m_per_s2=1.0, nlgeom=False)
        path = write_ccx_inp(deck, tmp_path / "c.inp")
        text = pathlib.Path(path).read_text()
        assert "NLGEOM" not in text
        assert "*STATIC" in text


# ── trace bend-strain evaluator (synthetic FRD) ─────────────────────────


class TestTraceStrainEvaluator:
    def _synthetic(self, eps_xx: float):
        from smash.sim.fea.frd_parser import FRDResult, FRDField
        from smash.sim.fea.mesh import BoardMesh, MeshElement
        from smash.state import Board
        # One element in FCU_SUBSTRATE spanning 8 nodes.
        nodes = [(i + 1, (i % 2) * 1e-3, ((i // 2) % 2) * 1e-3,
                  (i // 4) * 1e-4) for i in range(8)]
        mesh = BoardMesh(
            board_name="power_board",
            node_coords=nodes,
            elements=[MeshElement(eid=1, nodes=[1, 2, 3, 4, 5, 6, 7, 8],
                                  centroid_xyz_mm=(0.5, 0.5, 0.05))],
            element_sets={"FCU_SUBSTRATE": [1]},
            node_sets={},
            z_layer_records=[],
        )
        # Strain field: node 7 carries ε_xx, the rest zero.
        field = FRDField(
            label="TOSTRAIN", step_number=1, total_time=1.0,
            component_names=["EXX", "EYY", "EZZ", "EXY", "EYZ", "EZX"],
            values_by_node={n: (0, 0, 0, 0, 0, 0) for n in range(1, 9)})
        field.values_by_node[7] = (eps_xx, 0, 0, 0, 0, 0)
        frd = FRDResult(fields=[field],
                        nodes={n: (0, 0, 0) for n in range(1, 9)},
                        job_name="syn")
        return frd, mesh, Board("power_board")

    def test_picks_worst_strain_and_margin(self):
        frd, mesh, b = self._synthetic(0.012)        # 1.2 %
        allow = CopperAllowable(elongation_min=0.03)
        res = evaluate_trace_strain(frd, mesh, b, allowable=allow)
        assert res.worst is not None
        assert res.worst.layer == "FCU_SUBSTRATE"
        assert abs(res.worst.eps_principal_max - 0.012) < 1e-9
        # margin = 1.2 % / 3 % = 0.4 → warn (≥0.5 is fail-ward; 0.4 < 0.5 → pass)
        assert abs(res.worst.margin - 0.4) < 1e-6
        assert res.worst.verdict == "pass"
        # 1.2 % exceeds yield strain → flagged as yielded.
        assert res.worst.yields is True

    def test_fail_when_strain_exceeds_floor(self):
        frd, mesh, b = self._synthetic(0.04)         # 4 % > 3 % floor
        res = evaluate_trace_strain(frd, mesh, b,
                                    allowable=CopperAllowable(elongation_min=0.03))
        assert res.worst.verdict == "fail"
        assert res.worst.margin > 1.0

    def test_missing_strain_field_raises(self):
        from smash.sim.fea.frd_parser import FRDResult
        from smash.sim.fea.mesh import BoardMesh
        from smash.state import Board
        frd = FRDResult(fields=[], nodes={}, job_name="x")
        mesh = BoardMesh("power_board", [], [], {"FCU_SUBSTRATE": [1]},
                         {}, [])
        with pytest.raises(ValueError, match="strain"):
            evaluate_trace_strain(frd, mesh, Board("power_board"))


# ── coupon end-to-end vs closed-form (needs ccx) ────────────────────────


@pytest.mark.skipif(not _HAS_CCX, reason=_CCX_REASON)
class TestCouponEndToEnd:
    def _solve(self, spec, accel, nlgeom, tmp_path):
        from smash.sim.fea import run_ccx
        deck, mesh = build_trace_coupon_deck(
            spec, accel_m_per_s2=accel, nlgeom=nlgeom)
        inp = write_ccx_inp(deck, tmp_path / "c.inp")
        res = run_ccx(inp, check=True, cwd=tmp_path)
        peak_g = accel / 9.80665
        return evaluate_coupon(parse_frd(res.frd_path), mesh, spec,
                               peak_g=peak_g)

    def test_short_span_tracks_closed_form(self, tmp_path):
        # 1 mm / 35 µm at ~47k G: small-deflection regime, so the FEA
        # von Mises should land in the neighbourhood of the fixed-fixed
        # closed form (σ = ρaL²/2t) — within a factor of ~2 on a coarse
        # mesh (vM at mid-span = half the fixed-end fibre stress).
        spec = TraceCouponSpec(width_mm=0.1, thickness_um=35.0, gap_mm=1.0)
        r = self._solve(spec, 46718 * 9.80665, nlgeom=False, tmp_path=tmp_path)
        assert r.sigma_closed_form_mpa > 0
        ratio = r.sigma_vm_mpa / r.sigma_closed_form_mpa
        assert 0.3 < ratio < 1.5, f"σ ratio {ratio} off closed form"
        # Ductile copper: nowhere near the 3 % fracture floor.
        assert r.survives and r.eps_principal < 0.005

    def test_nlgeom_relieves_long_thin_span(self, tmp_path):
        # 3 mm / 17.5 µm deflects ≫ thickness → membrane relief: NLGEOM
        # stress must be well below the linear (small-strain) value.
        spec = TraceCouponSpec(width_mm=0.1, thickness_um=17.5, gap_mm=3.0)
        lin = self._solve(spec, 46718 * 9.80665, nlgeom=False, tmp_path=tmp_path)
        nl = self._solve(spec, 46718 * 9.80665, nlgeom=True, tmp_path=tmp_path)
        assert nl.sigma_vm_mpa < 0.6 * lin.sigma_vm_mpa
        # Even the worst free span survives fracture (may sag).
        assert nl.survives


# ── via barrel coupon ───────────────────────────────────────────────────


class TestCLoadWriter:
    def test_cload_card_emits(self, tmp_path):
        deck = CCXDeck(
            job_name="cl", node_coords=[(1, 0, 0, 0), (2, 1e-3, 0, 0)],
            elements=[], element_sets=[], node_sets={"P": [1, 2]},
            materials=[], boundaries=[],
            steps=[CCXStep(name="s", static=True,
                           nodal_loads=[CCXNodalLoad(nset_name="P", dof=3,
                                                     magnitude_n=-1.5)])])
        text = pathlib.Path(write_ccx_inp(deck, tmp_path / "cl.inp")).read_text()
        assert "*CLOAD" in text
        assert "P, 3," in text


class TestViaCouponDeck:
    def test_via_deck_structure(self):
        spec = ViaCouponSpec(drill_mm=0.2, wall_um=20.0, supported_mass_g=0.1)
        deck, mesh = build_via_coupon_deck(
            spec, accel_m_per_s2=1000.0, direction="reverse")
        assert deck.materials[0].name == "COPPER"
        assert all(e[1] == ELEMENT_TYPE_LINEAR_HEX for e in deck.elements)
        for ns in ("TOP_PAD", "BOT_FIX", "BARREL"):
            assert deck.node_sets[ns], f"missing node set {ns}"
        # Reverse setback → +Z tension load on the top pad.
        nl = deck.steps[0].nodal_loads[0]
        assert nl.nset_name == "TOP_PAD" and nl.dof == 3
        assert nl.magnitude_n > 0
        # Bottom pad clamped.
        assert deck.boundaries[0].nset_name == "BOT_FIX"

    def test_barrel_area_matches_annulus(self):
        spec = ViaCouponSpec(drill_mm=0.2, wall_um=20.0)
        r_in = 0.1
        r_out = 0.1 + 0.02
        expect = math.pi * (r_out ** 2 - r_in ** 2)
        assert abs(spec.barrel_area_mm2 - expect) < 1e-9


@pytest.mark.skipif(not _HAS_CCX, reason=_CCX_REASON)
class TestViaCouponEndToEnd:
    def test_axial_stress_tracks_closed_form(self, tmp_path):
        from smash.sim.fea import run_ccx
        spec = ViaCouponSpec(drill_mm=0.2, wall_um=20.0,
                             supported_mass_g=0.01, board_thickness_mm=1.6)
        deck, mesh = build_via_coupon_deck(
            spec, accel_m_per_s2=46718 * 9.80665, direction="reverse")
        inp = write_ccx_inp(deck, tmp_path / "v.inp")
        res = run_ccx(inp, check=True, cwd=tmp_path)
        r = evaluate_via_coupon(parse_frd(res.frd_path), mesh, spec,
                                peak_g=46718, direction="reverse")
        # FEA von Mises should bracket the σ = F/(π·d·t) closed form
        # (a bit higher — it includes the pad↔barrel concentration).
        ratio = r.sigma_vm_mpa / r.sigma_closed_form_mpa
        assert 0.8 < ratio < 1.6, f"σ ratio {ratio}"
        # 10 mg on one via at 47k G overstresses a 20 µm barrel.
        assert not r.survives
