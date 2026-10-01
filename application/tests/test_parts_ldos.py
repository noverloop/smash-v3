"""Verify LDO factories transcribe ground-truth faithfully.

Covers:
  - LDL112PV33R + LDL112PV18R (1.2 A LDO, DFN6 3x3, V_OUT=3.3/1.8 V)
  - STLQ020J30R (200 mA LDO, Flip-Chip 4, V_OUT=3.0 V)
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design, Footprint
from smash.parts import add_ldl112pv33r, add_ldl112pv18r, add_stlq020j30r


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "application/src/smash/parts/sources"


# ─── LDL112PV33R + LDL112PV18R (shared base) ─────────────────────────────

class TestLDL112Artifacts:
    @pytest.mark.parametrize("variant", ["LDL112PV33R", "LDL112PV18R"])
    @pytest.mark.parametrize("filename", [
        "LDL112.pdf",
        "LIB_{V}.samacsys.zip",
        "{V}.kicad_sym",
        "SON95P300X300X100-7N-D.kicad_mod",
        "{V}.stp",
        "pinmap.txt",
        "part_info.txt",
    ])
    def test_artifact_present(self, variant, filename):
        p = SRC / variant / filename.format(V=variant)
        assert p.is_file(), f"missing: {p}"


class _LDL112SharedTests:
    """Tests that should pass for BOTH PV33R and PV18R. Subclasses
    set self.q + self.vout_v in setup_method."""

    def test_manf(self):
        assert self.q.manf == "STMicroelectronics"

    def test_datasheet_resolves(self):
        assert (REPO_ROOT / self.q.datasheet).is_file()

    def test_package(self):
        assert self.q.package == "DFN-6 (3x3)"
        assert self.q.height_mm == pytest.approx(1.00)
        assert self.q.size_mm == (3.0, 3.0)

    def test_thermal(self):
        # DS-LDL112 p5 Table 3 (DFN6 3x3)
        assert self.q.rth_ja_cw == 55.0
        assert self.q.rth_jc_cw == 10.0
        assert self.q.tj_max_c == 125.0

    def test_temp_range(self):
        # DS-LDL112 p5: T_OP = -40 to +125 °C
        assert self.q.temp_range_c == (-40, 125)

    def test_electrical(self):
        assert self.q.voltage_rating_v == 7.0      # VIN abs max
        assert self.q.i_rms_a == 1.2               # IOUT guaranteed
        assert self.q.power_rating_w is None       # "internally limited"
        assert self.q.vcc_nominal_v == self.vout_v

    def test_pin_count(self):
        # 6 functional pins + 1 exposed pad = 7
        assert len(self.q.pins) == 7

    def test_pin_layout(self):
        # Common across both variants — pins 1, 2, 4, 6, 7 always identical
        assert self.q.pin("1").name == "EN"
        assert self.q.pin("2").name == "GND"
        assert self.q.pin("4").name == "VOUT"
        assert self.q.pin("6").name == "VIN"
        assert self.q.pin("7").name == "EP"
        # Exposed pad must be tied to GND per datasheet p3 Table 1
        assert self.q.pin("7").type == "ground"

    def test_footprint_pads(self):
        fp = self.q.footprint
        assert isinstance(fp, Footprint)
        assert fp.name == "SON95P300X300X100-7N-D"
        assert fp.source == "samacsys"
        assert len(fp.pads) == 7
        # Exposed thermal pad
        ep = fp.pad("7")
        assert ep.size_mm == pytest.approx((1.75, 2.5))

    def test_pin_pad_correspondence(self):
        pad_nums = {p.num for p in self.q.footprint.pads}
        pin_nums = {p.num for p in self.q.pins}
        assert pin_nums == pad_nums

    def test_validators_pass(self):
        d = Design()
        # add_*_to_design needs a fresh Design — call the factory again
        q = self.factory(d, ref="U1")
        d.add_power_net("VIN_RAIL", voltage_v=5.0).connect(q.pin("VIN"))
        d.add_power_net(f"VOUT_RAIL", voltage_v=self.vout_v).connect(q.pin("VOUT"))
        d.add_signal_net("LDO_EN").connect(q.pin("EN"))
        d.add_ground_net("GND").connect_all(
            [q.pin("GND"), q.pin("EP")]
        )
        errors = [i for i in d.validate() if i.severity == "error"]
        assert errors == []


class TestLDL112PV33R(_LDL112SharedTests):
    factory = staticmethod(add_ldl112pv33r)
    vout_v = 3.3

    def setup_method(self):
        self.d = Design()
        self.q = add_ldl112pv33r(self.d, ref="U1")

    def test_manf_pn(self):
        assert self.q.manf_pn == "LDL112PV33R"

    def test_pin3_named_NC_per_datasheet(self):
        # ST DS10321 Figure 3 (fixed-variant pin diagram) labels pin 3
        # as "NC" on the fixed PV33R. SamacSys's family symbol shows
        # the adjustable-variant "ADJ" label — we expose that as alias
        # so SamacSys-imported KiCad schematics still resolve.
        assert self.q.pin("3").name == "NC"
        assert "ADJ" in self.q.pin("3").aliases
        assert self.q.pin("3").type == "nc"

    def test_pin5_is_nc(self):
        assert self.q.pin("5").name == "NC"
        assert self.q.pin("5").type == "nc"

    @pytest.mark.parametrize("substring", [
        "1.2 A low quiescent current LDO",
        "300 mV typ at 1 A",
        "35 µA typ",
        "165 °C",
        "Mouser PN     : 511-LDL112PV33R",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


class TestLDL112PV18R(_LDL112SharedTests):
    factory = staticmethod(add_ldl112pv18r)
    vout_v = 1.8

    def setup_method(self):
        self.d = Design()
        self.q = add_ldl112pv18r(self.d, ref="U1")

    def test_manf_pn(self):
        assert self.q.manf_pn == "LDL112PV18R"

    def test_pin3_named_NC_per_datasheet(self):
        # Datasheet name primary, SamacSys NC_1 in aliases.
        assert self.q.pin("3").name == "NC"
        assert "NC_1" in self.q.pin("3").aliases
        assert self.q.pin("3").type == "nc"

    def test_pin5_named_NC_per_datasheet(self):
        assert self.q.pin("5").name == "NC"
        assert "NC_2" in self.q.pin("5").aliases
        assert self.q.pin("5").type == "nc"

    @pytest.mark.parametrize("substring", [
        "1.2 A low quiescent current LDO",
        "300 mV typ at 1 A",
        "Mouser PN     : 511-LDL112PV18R",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


# ─── STLQ020J30R ─────────────────────────────────────────────────────────

class TestSTLQ020J30RArtifacts:
    @pytest.mark.parametrize("filename", [
        "STLQ020.pdf",
        "LIB_STLQ020J30R.samacsys.zip",
        "STLQ020J30R.kicad_sym",
        "BGA4C40P2X2_77X77X61.kicad_mod",
        "STLQ020J30R.stp",
        "pinmap.txt",
        "part_info.txt",
    ])
    def test_artifact_present(self, filename):
        assert (SRC / "STLQ020J30R" / filename).is_file()


class TestSTLQ020J30R:
    def setup_method(self):
        self.d = Design()
        self.q = add_stlq020j30r(self.d, ref="U1")

    def test_identity(self):
        assert self.q.manf == "STMicroelectronics"
        assert self.q.manf_pn == "STLQ020J30R"

    def test_datasheet_resolves(self):
        assert (REPO_ROOT / self.q.datasheet).is_file()

    def test_voltage_output(self):
        # J30R is the 3.0 V variant per p20 Table 9
        assert self.q.vcc_nominal_v == 3.0
        # VIN max
        assert self.q.voltage_rating_v == 7.0
        # IOUT max
        assert self.q.i_rms_a == 0.200

    def test_package(self):
        assert self.q.package == "Flip-Chip 4 (DSBGA-4)"
        assert self.q.size_mm == (0.77, 0.77)
        assert self.q.height_mm == pytest.approx(0.61)

    def test_thermal(self):
        # DS-STLQ020 p5 Table 3, Flip-Chip 4 only lists R_thJA = 180
        assert self.q.rth_ja_cw == 180.0
        assert self.q.rth_jc_cw is None
        assert self.q.tj_max_c == 150.0

    def test_pin_layout_bga(self):
        # DS-STLQ020 p3 Table 1, Flip-Chip 4 column
        assert self.q.pin("A1").name == "VIN"
        assert self.q.pin("A2").name == "VOUT"
        assert self.q.pin("B1").name == "EN"
        assert self.q.pin("B2").name == "GND"

    def test_esd_standards(self):
        s = self.q.standards
        assert any("HBM" in x and "2000" in x for x in s)
        assert any("CDM" in x and "500" in x for x in s)

    def test_footprint_bga(self):
        fp = self.q.footprint
        assert fp.name == "BGA4C40P2X2_77X77X61"
        assert fp.source == "samacsys"
        assert fp.pitch_mm == pytest.approx(0.40)
        # All 4 balls
        assert len(fp.pads) == 4
        # Pads are round (BGA balls)
        assert all(p.shape == "round" for p in fp.pads)
        # Exact positions per .kicad_mod, y negated into the model's
        # math-y-up frame (row A is the TOP row: +y in the model).
        expected = {
            "A1": (-0.20, +0.20),
            "A2": (+0.20, +0.20),
            "B1": (-0.20, -0.20),
            "B2": (+0.20, -0.20),
        }
        for pad in fp.pads:
            assert pad.position_mm == pytest.approx(expected[pad.num])
            assert pad.size_mm == pytest.approx((0.208, 0.208))

    def test_pin_pad_correspondence(self):
        pad_nums = {p.num for p in self.q.footprint.pads}
        pin_nums = {p.num for p in self.q.pins}
        assert pin_nums == pad_nums == {"A1", "A2", "B1", "B2"}

    @pytest.mark.parametrize("substring", [
        "M7",                          # marking
        "300 nA typ",                  # ultra-low Iq
        "Flip-Chip 4",
        "STLQ020M33R",                 # the hallucinated-PN warning
        "STLQ020J33R",                 # the 3.3 V switch-to alternative
        "Mouser PN     : 511-STLQ020J30R",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")

    @pytest.mark.parametrize("field", [
        "fab_country", "currency", "price_1pc", "weight_g",
        "body_material", "lead_material", "rth_jc_cw",
    ])
    def test_field_unset(self, field):
        assert getattr(self.q, field) is None

    def test_validators_pass(self):
        d = Design()
        q = add_stlq020j30r(d, ref="U1")
        d.add_power_net("VIN", voltage_v=3.7).connect(q.pin("VIN"))
        d.add_power_net("V3V0", voltage_v=3.0).connect(q.pin("VOUT"))
        d.add_signal_net("EN").connect(q.pin("EN"))
        d.add_ground_net("GND").connect(q.pin("GND"))
        errors = [i for i in d.validate() if i.severity == "error"]
        assert errors == []
