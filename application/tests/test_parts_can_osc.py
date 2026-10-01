"""Verify the TCAN1042GVDQ1 CAN PHY + DSC1001CI5-008.0000 MEMS osc
factories transcribe their ground-truth.
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design
from smash.parts import add_tcan1042gvdq1, add_dsc1001ci5_008_0000


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "application/src/smash/parts/sources"


# ─── artifact presence ───────────────────────────────────────────────────

ARTIFACTS = {
    "TCAN1042GVDQ1": [
        "TCAN1042-family.pdf",
        "LIB_TCAN1042GVDQ1.samacsys.zip",
        "TCAN1042GVDQ1.kicad_sym",
        "SOIC127P600X175-8N.kicad_mod",
        "TCAN1042GVDQ1.stp",
        "pinmap.txt", "part_info.txt",
    ],
    "DSC1001CI5-008.0000": [
        "DSC1001-family.pdf",
        "LIB_DSC1001CI5-008.0000.samacsys.zip",
        "DSC1001CI5-008_0000.kicad_sym",
        "DSC1001CI50080000.kicad_mod",
        "DSC1001CI5-008.0000.stp",
        "pinmap.txt", "part_info.txt",
    ],
}


@pytest.mark.parametrize("part,fname",
                         [(p, f) for p, files in ARTIFACTS.items() for f in files])
def test_artifact_present(part, fname):
    assert (SRC / part / fname).is_file()


# ─── TCAN1042GVDQ1 ───────────────────────────────────────────────────────

class TestTCAN1042:
    def setup_method(self):
        self.q = add_tcan1042gvdq1(Design(), ref="U1")

    def test_identity(self):
        assert self.q.manf == "Texas Instruments"
        assert self.q.manf_pn == "TCAN1042GVDQ1"

    def test_voltage_rating(self):
        # VCC/VIO abs max = 7 V
        assert self.q.voltage_rating_v == 7.0

    def test_temp_range_tj(self):
        # T_J operating range -55 to +150 °C
        assert self.q.temp_range_c == (-55, 150)
        assert self.q.tj_max_c == 150.0

    def test_standards(self):
        s = self.q.standards
        assert "ISO 11898-2:2016" in s
        assert "AEC-Q100 Grade 1" in s
        assert any("HBM Class 3A" in x for x in s)
        assert any("16 kV" in x for x in s)         # IEC ESD survival on CANH/CANL

    def test_pin_layout_soic8(self):
        layout = {
            "1": "TXD",  "2": "GND", "3": "VCC", "4": "RXD",
            "5": "VIO",  "6": "CANL", "7": "CANH", "8": "STB",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_vio_is_power_pin_with_note(self):
        vio = self.q.pin("VIO")
        assert vio.type == "power"
        assert "I/O level-shifting" in (vio.note or "")
        assert "V-suffix" in (vio.note or "")

    def test_stb_pin_warns_no_float(self):
        stb = self.q.pin("STB")
        assert "must not float" in (stb.note or "").lower()

    def test_canh_canl_differential_note(self):
        for n in ("CANH", "CANL"):
            assert "differential" in (self.q.pin(n).note or "").lower()

    def test_footprint(self):
        fp = self.q.footprint
        assert fp.name == "SOIC127P600X175-8N"
        assert fp.package_class == "SOIC-8"
        assert fp.pitch_mm == pytest.approx(1.27)
        assert len(fp.pads) == 8

    @pytest.mark.parametrize("substring", [
        "TCAN1042HG-Q1",                # H + G variant in family list
        "TCAN1042HGV-Q1",               # all 4 attributes combined
        "5 Mbps",
        "ISO 11898-2:2016",
        "±58 V",
        "120 Ω",                        # CAN termination
        "Driver dominant time-out",
        "Thermal shutdown",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


# ─── DSC1001CI5-008.0000 ─────────────────────────────────────────────────

class TestDSC1001CI5_008:
    def setup_method(self):
        self.q = add_dsc1001ci5_008_0000(Design(), ref="Y1")

    def test_identity(self):
        assert self.q.manf == "Microchip"
        assert self.q.manf_pn == "DSC1001CI5-008.0000"

    def test_frequency(self):
        # 8 MHz output
        assert self.q.clock_freq_hz == 8.0e6

    def test_tolerance_25ppm(self):
        # The "I" code in CI5 = ±25 ppm
        assert self.q.tolerance_pct == pytest.approx(0.0025)

    def test_temp_range_industrial(self):
        # "C" code = Industrial -40..+85 °C (per the trim convention).
        # Note: datasheet uses I=Industrial, but Microchip's order-code
        # convention here uses "C" for Industrial. We trust the SamacSys
        # part_info.txt which says "Industrial". (Verify in TODO.md.)
        assert self.q.temp_range_c == (-40, 85)

    def test_supply(self):
        # 1.7-3.6 V — recommended operating range
        # Operating current ~6.3 mA worst case @ 8 MHz, 1.8 V
        assert self.q.i_rms_a == pytest.approx(0.0063, rel=0.1)

    def test_pin_layout(self):
        layout = {
            "1": "STANDBY#", "2": "GND", "3": "OUT", "4": "VDD",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_standby_alias(self):
        # Caller ergonomics
        assert self.q.pin("STANDBY").num == "1"
        assert self.q.pin("OE#").num == "1"

    def test_vdd_alias(self):
        assert self.q.pin("V_DD").num == "4"

    def test_footprint_cdfn4(self):
        fp = self.q.footprint
        assert fp.name == "DSC1001CI50080000"
        assert fp.package_class == "CDFN-4 (2.5×2.0)"
        assert len(fp.pads) == 4
        assert fp.size_mm == (2.5, 2.0)
        assert fp.height_mm == pytest.approx(0.85)

    def test_standards(self):
        s = self.q.standards
        assert "RoHS" in s
        assert "AEC-Q100" in s
        assert any("MIL-STD-883" in x for x in s)
        assert any("HBM 4 kV" in x for x in s)

    @pytest.mark.parametrize("substring", [
        "MEMS", "1 MHz to 150 MHz",
        "DSC1003", "DSC1004",
        "drop-in",
        "AEC-Q100",
    ])
    def test_note(self, substring):
        # Note: 'drop-in' is lowercase in our note; datasheet says
        # '"Drop-In" Replacement' with quotes & capitalisation
        assert substring.lower() in (self.q.note or "").lower()


# ─── shared invariants ───────────────────────────────────────────────────

ALL_FACTORIES = [add_tcan1042gvdq1, add_dsc1001ci5_008_0000]


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_each_factory_datasheet_resolves(factory):
    d = Design()
    c = factory(d, ref="U1")
    assert (REPO_ROOT / c.datasheet).is_file()


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_each_factory_3d_model_resolves(factory):
    d = Design()
    c = factory(d, ref="U1")
    assert (REPO_ROOT / c.footprint.model_3d_path).is_file()


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_each_factory_pin_pad_correspondence(factory):
    d = Design()
    c = factory(d, ref="U1")
    pad_nums = {p.num for p in c.footprint.pads}
    pin_nums = {p.num for p in c.pins}
    assert pin_nums == pad_nums, f"{factory.__name__}: mismatch"


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_each_factory_validates_clean(factory):
    d = Design()
    chip = factory(d, ref="U_TEST")
    from _helpers import wire_chip_synthetically
    wire_chip_synthetically(d, chip)
    errors = [i for i in d.validate() if i.severity == "error"]
    assert errors == [], f"{factory.__name__}: {errors}"
