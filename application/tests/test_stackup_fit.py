"""Tests for smash.state.stackup.fit — the stackup fitter, and the
derived Board.thickness_mm it feeds."""

import pytest

from smash import fit_stackup, StackupSpec, Board, default_fab_profile


class TestDefault14L:
    def test_layer_names_and_count(self):
        ly = fit_stackup(StackupSpec())
        assert len(ly) == 14
        assert [l.name for l in ly] == (
            ["F.Cu"] + [f"In{k}.Cu" for k in range(1, 13)] + ["B.Cu"])

    def test_embedded_cap_roles_and_pairing(self):
        ly = {l.name: l for l in fit_stackup(StackupSpec())}
        assert ly["In1.Cu"].role == "embedded_cap_gnd"
        assert ly["In2.Cu"].role == "embedded_cap_power"
        assert ly["In1.Cu"].paired_with == "In2.Cu"
        assert ly["In11.Cu"].paired_with == "In12.Cu"
        # the inner signal layers stay signal
        assert ly["In5.Cu"].role == "signal"

    def test_dielectric_pattern(self):
        ly = fit_stackup(StackupSpec())
        # embedded-cap gaps are 50 µm "FR4 thin"
        in1 = next(l for l in ly if l.name == "In1.Cu")
        assert in1.dielectric_below.material == "FR4 thin"
        assert in1.dielectric_below.thickness_um == 50
        # ordinary gaps are 150 µm FR4, alternating prepreg/core
        f = next(l for l in ly if l.name == "F.Cu")
        assert f.dielectric_below.material == "FR4"
        assert f.dielectric_below.thickness_um == 150
        assert f.dielectric_below.kind == "prepreg"
        # bottom layer has no dielectric below
        assert ly[-1].name == "B.Cu" and ly[-1].dielectric_below is None

    def test_core_thickness_sum(self):
        ly = fit_stackup(StackupSpec())
        cu = sum(l.thickness_um for l in ly)
        di = sum(l.dielectric_below.thickness_um
                 for l in ly if l.dielectric_below)
        # 2×17.5 + 12×35 Cu + 11×150 + 2×50 dielectric
        assert cu == pytest.approx(455.0)
        assert di == pytest.approx(1750.0)


class TestHybridVariants:
    def test_rogers_top_dielectric(self):
        ly = fit_stackup(StackupSpec(top_substrate="rogers_ro4350b_5mil"))
        d1 = next(l for l in ly if l.name == "F.Cu").dielectric_below
        assert d1.material == "RO4350B" and d1.thickness_um == 127

    def _core_mm(self, ly):
        return (sum(l.thickness_um for l in ly)
                + sum(l.dielectric_below.thickness_um
                      for l in ly if l.dielectric_below)) / 1000.0

    def test_target_thickness_is_best_effort(self):
        # Asking for a thicker board grows the fill dielectrics toward the
        # target (best-effort within the catalog + fixed 14 layers); the
        # embedded-cap thin gaps stay 50 µm.
        default_mm = self._core_mm(fit_stackup(StackupSpec()))
        ly = fit_stackup(StackupSpec(target_thickness_mm=3.0))
        in1 = next(l for l in ly if l.name == "In1.Cu")
        assert in1.dielectric_below.thickness_um == 50      # cap gap fixed
        grown = self._core_mm(ly)
        assert default_mm < grown <= 3.0 + 1e-9             # moved toward, didn't overshoot


class TestThicknessDerivation:
    def test_fitted_board_thickness(self):
        b = Board("flight_board").set_fitted_stackup()
        # 2.205 core + 0.02 masks
        assert b.thickness_mm == pytest.approx(2.225, abs=1e-6)

    def test_empty_stackup_fallback(self):
        b = Board("flight_board")               # no stackup
        assert b.thickness_mm == pytest.approx(2.226)

    def test_al_backing_adds(self):
        b = Board("camera_module", al_backing_mm=0.5).set_fitted_stackup()
        assert b.thickness_mm == pytest.approx(2.225 + 0.5, abs=1e-6)

    def test_spacer_unchanged(self):
        b = Board("spacer_x", kind="spacer")
        b.set_fitted_stackup()                  # no-op for spacers
        assert b.stackup == []
        assert b.thickness_mm == 4.0

    def test_uses_fab_profile_arg(self):
        # passing an explicit profile works (same default here)
        ly = fit_stackup(StackupSpec(), fab=default_fab_profile())
        assert len(ly) == 14
