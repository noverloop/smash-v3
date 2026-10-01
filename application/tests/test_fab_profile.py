"""Unit tests for smash.state.fab — FabProfile catalog, queries, DRC
checks, and JSON round-trip."""

import pytest

from smash import FabProfile, default_fab_profile
from smash.state.fab import (
    Laminate, CopperFoil, MetalInsert, FabTolerances, DesignRules,
    Solder, Adhesive,
)


class TestDefaultProfile:
    def test_shape(self):
        p = default_fab_profile()
        # hybrid: more than one dielectric material in the catalog
        assert len(p.materials()) >= 2
        assert "FR4" in p.materials() and "RO4350B" in p.materials()
        # metal inserts present (backing + coin)
        assert p.metal_options and any(m.role == "backing" for m in p.metal_options)
        assert p.supports_hybrid is True
        assert p.max_layers >= 16

    def test_round_trip(self):
        p = default_fab_profile()
        p2 = FabProfile.from_dict(p.to_dict())
        assert p2.to_dict() == p.to_dict()
        # nested objects rehydrate to their types
        assert isinstance(p2.laminates[0], Laminate)
        assert isinstance(p2.foils[0], CopperFoil)
        assert isinstance(p2.metal_options[0], MetalInsert)
        assert isinstance(p2.solders[0], Solder)
        assert isinstance(p2.adhesives[0], Adhesive)
        assert isinstance(p2.rules, DesignRules)
        assert isinstance(p2.tolerances, FabTolerances)


class TestAssemblyMaterials:
    def test_solder_catalog_and_default(self):
        p = default_fab_profile()
        assert {s.name for s in p.solders} >= {"SAC305", "Sn63Pb37"}
        assert p.default_solder.name == "SAC305"           # first = board paste
        assert p.solder("Sn63Pb37").leaded is True
        assert p.solder("nope") is None

    def test_underfill_catalog(self):
        p = default_fab_profile()
        uf = p.adhesive("Loctite Eccobond UF1173")
        assert uf is not None and uf.role == "underfill"
        assert uf.youngs_modulus_gpa and uf.cte_ppm_k and uf.tg_c

    def test_solder_constants_present(self):
        s = default_fab_profile().solder("SAC305")
        assert s.melting_c and s.thermal_w_mk and s.shear_strength_mpa
        assert s.cte_ppm_k and s.youngs_modulus_gpa
        # poisson_ratio drives the bend-sim shear modulus G = E/(2(1+ν));
        # if the catalog didn't carry it the sim would have to fall back
        # to a hardcoded SAC305 default. Both default solders must have it.
        assert s.poisson_ratio and 0.30 < s.poisson_ratio < 0.50
        assert default_fab_profile().solder("Sn63Pb37").poisson_ratio

    def test_multi_alloy_capability(self):
        p = default_fab_profile()
        assert p.supports_multi_alloy is True               # selective/hand/step
        reflow_only = FabProfile(name="x", solder_processes=["reflow"])
        assert reflow_only.supports_multi_alloy is False

    def test_tolerances_first_class(self):
        p = default_fab_profile()
        assert p.tolerances.finished_thickness_pct > 0
        assert all(l.thickness_tol_um > 0 for l in p.laminates)

    def test_siw_special_copper(self):
        p = default_fab_profile()
        rf = p.rf_foils()
        assert rf, "expected at least one low-profile SIW/mmWave foil"
        f = rf[0]
        assert f.is_low_profile and f.foil_type == "HVLP"
        assert f.roughness_rz_um is not None and f.roughness_rz_um <= 2.0
        assert f.conductivity_s_m is not None
        # standard ED foils are NOT selected as RF-grade
        assert all(not (g.foil_type == "ED") or g not in rf for g in p.foils)

    def test_foil_rf_fields_round_trip(self):
        p = default_fab_profile()
        f = FabProfile.from_dict(p.to_dict()).rf_foils()[0]
        assert f.foil_type == "HVLP" and f.roughness_rz_um == 1.5


class TestCatalogQueries:
    def test_cores_prepregs_split(self):
        p = default_fab_profile()
        assert all(l.kind == "core" for l in p.cores())
        assert all(l.kind == "prepreg" for l in p.prepregs())
        assert p.cores() and p.prepregs()

    def test_nearest_dielectric(self):
        p = default_fab_profile()
        nd = p.nearest_dielectric(150, material="FR4", kind="core")
        assert nd.material == "FR4" and nd.thickness_um == 150

    def test_nearest_dielectric_empty_raises(self):
        p = default_fab_profile()
        with pytest.raises(ValueError):
            p.nearest_dielectric(150, material="UNOBTAINIUM")

    def test_combine_to_thickness_within_tol(self):
        p = default_fab_profile()
        combo = p.combine_to_thickness(2226, tol_um=60, material="FR4")
        total = sum(l.thickness_um for l in combo)
        assert abs(total - 2226) <= 60
        assert all(isinstance(l, Laminate) for l in combo)

    def test_laminate_to_dielectric_reuse(self):
        p = default_fab_profile()
        di = p.nearest_dielectric(150, material="FR4", kind="core").to_dielectric()
        assert di.material == "FR4" and di.thickness_um == 150
        assert di.epsilon_r == 4.5


class TestDRCChecks:
    def test_trace(self):
        p = default_fab_profile()
        assert p.check_trace(0.20) == []
        assert [i.rule for i in p.check_trace(0.10)] == ["min_trace"]

    def test_via_ok_and_bad(self):
        p = default_fab_profile()
        assert p.check_via(0.6, 0.3) == []          # pad 0.6, drill 0.3, annular 0.15
        bad = {i.rule for i in p.check_via(0.30, 0.30)}  # zero annular, sub-min Ø
        assert "min_annular_ring" in bad and "min_via_diameter" in bad

    def test_aspect(self):
        p = default_fab_profile()
        assert p.check_aspect(2.0, 0.3) == []        # 6.7:1 < 10:1
        assert [i.rule for i in p.check_aspect(2.0, 0.15)] == ["max_aspect_ratio"]
