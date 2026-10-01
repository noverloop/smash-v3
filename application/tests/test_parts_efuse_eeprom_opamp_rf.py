"""Verify the eFuse + EEPROM + op-amp + RF-switch factories transcribe
their ground-truth.

Covers:
  - TPS25940AQRVCTQ1   (TI automotive eFuse, WQFN-20)
  - M24C01-RMN6TP      (ST 1-Kbit I²C EEPROM, SO8N)
  - AD8603AUJZ-R2      (ADI precision op-amp, TSOT-5)
  - BGS12WN6E6327XTSA1 (Infineon 9 GHz SPDT RF switch)
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design
from smash.parts import (
    add_tps25940aqrvctq1,
    add_tps259621ddar,
    add_m24c01_rmn6tp,
    add_ad8603aujz_r2_single_supply,
    add_bgs12wn6e6327xtsa1,
)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "application/src/smash/parts/sources"


# ─── artifact presence ───────────────────────────────────────────────────

ARTIFACTS = {
    "TPS25940AQRVCTQ1": [
        "TPS25940.pdf", "LIB_TPS25940AQRVCTQ1.samacsys.zip",
        "TPS25940AQRVCTQ1.kicad_sym", "QFN50P300X400X80-21N.kicad_mod",
        "TPS25940AQRVCTQ1.stp", "pinmap.txt", "part_info.txt",
    ],
    "TPS259621DDAR": [
        "TPS2596-family.pdf", "LIB_TPS259621DDAR.samacsys.zip",
        "TPS259621DDAR.kicad_sym", "SOIC127P600X170-9N.kicad_mod",
        "TPS259621DDAR.stp", "pinmap.txt", "part_info.txt",
    ],
    "M24C01-RMN6TP": [
        "M24C01-family.pdf", "LIB_M24C01-RMN6TP.samacsys.zip",
        "M24C01-RMN6TP.kicad_sym", "SOIC127P600X175-8N.kicad_mod",
        "M24C01-RMN6TP.stp", "pinmap.txt", "part_info.txt",
    ],
    "AD8603AUJZ-R2": [
        "AD8603-AD8607-AD8609-family.pdf",
        "LIB_AD8603AUJZ-R2.samacsys.zip",
        "AD8603AUJZ-R2.kicad_sym", "SOT95P280X100-5N.kicad_mod",
        "AD8603AUJZ-R2.stp", "pinmap.txt", "part_info.txt",
    ],
    "BGS12WN6E6327XTSA1": [
        "BGS12WN6.pdf", "LIB_BGS12WN6E6327XTSA1.samacsys.zip",
        "BGS12WN6E6327XTSA1.kicad_sym", "BGS12WN6E6327XTSA1.kicad_mod",
        "BGS12WN6E6327XTSA1.stp", "pinmap.txt", "part_info.txt",
    ],
}


@pytest.mark.parametrize("part,fname",
                         [(p, f) for p, files in ARTIFACTS.items() for f in files])
def test_artifact_present(part, fname):
    assert (SRC / part / fname).is_file()


# ─── TPS25940AQRVCTQ1 ────────────────────────────────────────────────────

class TestTPS25940:
    def setup_method(self):
        self.q = add_tps25940aqrvctq1(Design(), ref="U1")

    def test_identity(self):
        assert self.q.manf == "Texas Instruments"
        assert self.q.manf_pn == "TPS25940AQRVCTQ1"

    def test_electrical(self):
        # Abs max VIN/OUT = 20 V; I_MAX continuous = 4.78 A
        assert self.q.voltage_rating_v == 20.0
        assert self.q.i_rms_a == pytest.approx(4.78)
        assert self.q.tj_max_c == 150.0

    def test_temp_range_aec_q100_g1(self):
        # AEC-Q100 grade 1 = -40 to +125 °C ambient
        assert self.q.temp_range_c == (-40, 125)

    def test_standards(self):
        s = self.q.standards
        assert "AEC-Q100 Grade 1" in s
        assert any("HBM Classification Level 2" in x for x in s)
        assert any("CDM Classification Level C5" in x for x in s)

    def test_21_pins(self):
        assert len(self.q.pins) == 21

    def test_out_paralleled(self):
        # Pins 4-8 are all OUT; check they're paralleled
        for n in ("4", "5", "6", "7", "8"):
            assert self.q.pin(n).name.startswith("OUT")
            assert self.q.pin(n).type == "power"
        # Pin 4 carries the parallel-soldering note
        assert "paralleled" in (self.q.pin("4").note or "").lower()

    def test_in_paralleled(self):
        for n in ("9", "10", "11", "12", "13"):
            assert self.q.pin(n).name.startswith("IN")
            assert self.q.pin(n).type == "power"

    def test_ep_is_ground(self):
        ep = self.q.pin("21")
        assert ep.name == "EP"
        assert ep.type == "ground"
        assert "GND" in (ep.note or "")

    def test_flt_pin_bar_notation(self):
        # Datasheet name is /FLT (active-low). pinmap encodes "F\\L\\T\\"
        flt = self.q.pin("20")
        assert flt.name == "F\\L\\T\\"
        # Aliases for ergonomic lookup
        assert self.q.pin("FLT").num == "20"
        assert self.q.pin("/FLT").num == "20"

    def test_footprint(self):
        fp = self.q.footprint
        assert fp.name == "QFN50P300X400X80-21N"
        assert fp.package_class == "WQFN-20"
        assert fp.pitch_mm == pytest.approx(0.5)
        assert len(fp.pads) == 21
        # EP geometry
        ep = fp.pad("21")
        assert ep.size_mm == pytest.approx((1.7, 2.7))


# ─── TPS259621DDAR ───────────────────────────────────────────────────────

class TestTPS259621:
    def setup_method(self):
        self.q = add_tps259621ddar(Design(), ref="U1B")

    def test_identity(self):
        assert self.q.manf == "Texas Instruments"
        assert self.q.manf_pn == "TPS259621DDAR"

    def test_electrical(self):
        # V_IN abs max 21 V (22 V @ T_A=25 °C — we store the steady value)
        assert self.q.voltage_rating_v == 21.0
        # I_LIM max 2 A
        assert self.q.i_rms_a == 2.0
        assert self.q.tj_max_c == 125.0

    def test_temp_range_industrial(self):
        # T_J operating -40 to +125 °C
        assert self.q.temp_range_c == (-40, 125)

    def test_9_pins_with_ep(self):
        # 8 functional + EP = 9
        assert len(self.q.pins) == 9
        ep = self.q.pin("9")
        assert ep.type == "ground"
        assert "thermal pad" in (ep.note or "").lower()

    def test_pin_layout(self):
        layout = {
            "1": "GND_1",   "2": "DVDT",       "3": "EN_UVLO",
            "4": "IN",      "5": "OUT",        "6": "F\\L\\T\\",
            "7": "ILM",     "8": "OVLO_OVCSEL","9": "GND_2",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_flt_bar_notation_aliases(self):
        # Active-low fault output — KiCad bar notation in the name,
        # ergonomic aliases for callers
        assert self.q.pin("FLT").num == "6"
        assert self.q.pin("/FLT").num == "6"
        assert self.q.pin("FLTb").num == "6"
        assert self.q.pin("6").type == "output"
        assert "open-drain" in (self.q.pin("6").note or "").lower()

    def test_ovlo_ovcsel_dual_purpose_aliases(self):
        # Pin 8 serves OVCSEL on TPS25962x (this part) and OVLO on
        # TPS25963x. Both alias names should resolve to pin 8.
        assert self.q.pin("OVCSEL").num == "8"
        assert self.q.pin("OVLO").num == "8"
        assert "Must NOT float" in (self.q.pin("8").note or "")

    def test_standards(self):
        s = self.q.standards
        assert any("IEC 61000-4-4" in x for x in s)

    def test_footprint(self):
        fp = self.q.footprint
        assert fp.name == "SOIC127P600X170-9N"
        assert fp.package_class == "SOIC-8 (DDA, with EP)"
        assert len(fp.pads) == 9
        # Exposed-pad geometry
        ep = fp.pad("9")
        assert ep.size_mm == pytest.approx((2.4, 3.1))

    @pytest.mark.parametrize("substring", [
        "TPS259620", "TPS259630", "TPS259631",   # family siblings
        "auto-retry", "latch-off",
        "89 mΩ",
        "3.8/5.7/13.8 V",                        # the 3 clamp levels (slash form)
    ])
    def test_note(self, substring):
        assert substring.lower() in (self.q.note or "").lower()


# ─── M24C01-RMN6TP ───────────────────────────────────────────────────────

class TestM24C01:
    def setup_method(self):
        self.q = add_m24c01_rmn6tp(Design(), ref="U2")

    def test_identity(self):
        assert self.q.manf == "STMicroelectronics"
        assert self.q.manf_pn == "M24C01-RMN6TP"

    def test_memory_capacity(self):
        # 1 Kbit = 1024 bits
        assert self.q.memory_capacity_bits == 1024

    def test_temp_range_industrial(self):
        assert self.q.temp_range_c == (-40, 85)

    def test_pin_layout(self):
        layout = {
            "1": "E0", "2": "E1", "3": "E2", "4": "VSS",
            "5": "SDA", "6": "SCL", "7": "W\\C\\", "8": "VCC",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_wc_bar_notation_aliases(self):
        # SamacSys uses bar-notation for active-low signals
        wc = self.q.pin("7")
        assert wc.name == "W\\C\\"
        assert self.q.pin("WC").num == "7"
        assert self.q.pin("/WC").num == "7"
        assert self.q.pin("WC#").num == "7"
        assert "active-low" in (wc.note or "").lower()

    def test_vss_alias_gnd(self):
        # Datasheet uses VSS; designers often expect GND
        assert self.q.pin("GND").num == "4"

    def test_compliance(self):
        s = self.q.standards
        assert "RoHS" in s
        assert "Halogen-Free" in s
        assert "ECOPACK2" in s

    def test_footprint_so8n(self):
        fp = self.q.footprint
        assert fp.name == "SOIC127P600X175-8N"
        assert fp.package_class == "SO8N (SOIC-8)"


# ─── AD8603AUJZ-R2 ───────────────────────────────────────────────────────

class TestAD8603:
    def setup_method(self):
        self.q = add_ad8603aujz_r2_single_supply(Design(), ref="U3")

    def test_identity(self):
        assert self.q.manf == "Analog Devices"
        assert self.q.manf_pn == "AD8603AUJZ-R2"

    def test_temp_range(self):
        # Ordering Guide: -40 to +125 °C for AUJZ variant
        assert self.q.temp_range_c == (-40, 125)

    def test_package_tsot5(self):
        # TSOT-5 = thinner profile than DBV SOT-23-5 (1.0 vs 1.45 mm)
        assert self.q.package == "TSOT-5 (UJ-5)"
        assert self.q.height_mm == pytest.approx(1.0)
        assert self.q.size_mm == (2.9, 1.6)

    def test_pin_layout(self):
        # Datasheet Figure 1 (5-Lead TSOT, UJ suffix)
        layout = {
            "1": "OUT", "2": "V-", "3": "+IN",
            "4": "-IN", "5": "V+",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_input_aliases(self):
        # Ergonomic lookups
        assert self.q.pin("IN+").num == "3"
        assert self.q.pin("IN-").num == "4"
        assert self.q.pin("VINP").num == "3"
        assert self.q.pin("VINN").num == "4"

    def test_supply_aliases(self):
        # V+ still aliased VCC/VDD (no ambiguity — positive rail in
        # both single- and dual-supply modes).
        assert self.q.pin("VCC").num == "5"
        assert self.q.pin("VDD").num == "5"
        # V- in single-supply variant is typed as ground; the "VEE"
        # alias only exists on the dual-supply variant.
        # The "GND" alias is intentionally removed — the supply mode
        # is encoded in the factory choice, not in pin aliases.
        from smash.parts import add_ad8603aujz_r2_dual_supply
        from smash.state import Design
        dual = add_ad8603aujz_r2_dual_supply(Design(), ref="U_DUAL")
        assert dual.pin("VEE").num == "2"
        assert dual.pin("2").type == "power"
        assert self.q.pin("2").type == "ground"

    def test_pinmap_extraction_caveat_in_note(self):
        # The note must document the "PIN" vs "+IN" pinmap.txt issue
        assert "PIN" in (self.q.note or "")
        assert "+IN" in (self.q.note or "")

    def test_research_filename_caveat_in_note(self):
        # Research/ holds AD8603ARJZ-R2.pdf (labelling typo) but we
        # use AD8603AUJZ-R2 per SamacSys
        assert "AD8603ARJZ-R2" in (self.q.note or "")
        assert "Rev D" in (self.q.note or "")

    def test_footprint_sot95p280x100_5n(self):
        # IPC name distinguishes TSOT (X100 = 1.0 mm height) from
        # SOT-23 DBV (X145 = 1.45 mm height)
        fp = self.q.footprint
        assert fp.name == "SOT95P280X100-5N"
        assert fp.height_mm == pytest.approx(1.0)
        assert len(fp.pads) == 5


# ─── BGS12WN6E6327XTSA1 ──────────────────────────────────────────────────

class TestBGS12:
    def setup_method(self):
        self.q = add_bgs12wn6e6327xtsa1(Design(), ref="U4")

    def test_identity(self):
        assert self.q.manf == "Infineon"
        assert self.q.manf_pn == "BGS12WN6E6327XTSA1"

    def test_package_tiny(self):
        # PG-TSNP-6-10, 0.7 × 1.1 × 0.375 mm — one of the smallest
        # SPDT RF switches in the industry
        assert self.q.height_mm == pytest.approx(0.375)
        assert self.q.size_mm == (1.1, 0.7)

    def test_thermal(self):
        # R_thJS = 70 K/W per datasheet (junction-to-solder)
        assert self.q.rth_jc_cw == 70.0
        assert self.q.tj_max_c == 125.0

    def test_pin_layout(self):
        layout = {
            "1": "RF2", "2": "GND", "3": "RF1",
            "4": "VDD", "5": "RFIN", "6": "CTRL",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_rf_pins_no_dc_warning(self):
        # RFIN has the "No DC allowed" caveat
        rfin = self.q.pin("RFIN")
        assert "no dc" in (rfin.note or "").lower()

    def test_standards(self):
        s = self.q.standards
        assert "RoHS" in s
        assert "WEEE" in s
        assert any("JEDEC47" in x for x in s)
        assert any("8 kV" in x for x in s)        # ESD with 27 nH shunt

    def test_footprint(self):
        fp = self.q.footprint
        assert fp.name == "BGS12WN6E6327XTSA1"
        assert fp.package_class == "PG-TSNP-6-10"
        assert fp.pitch_mm == pytest.approx(0.4)
        assert len(fp.pads) == 6

    @pytest.mark.parametrize("substring", [
        "0.05 GHz to 9 GHz",
        "30 dBm",
        "WLAN", "Bluetooth", "UWB",
        "BGS12WN6 E6329",                 # sibling variant in same datasheet
        "No DC voltages allowed on RF ports",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


# ─── shared invariants ───────────────────────────────────────────────────

ALL_FACTORIES = [
    add_tps25940aqrvctq1, add_tps259621ddar,
    add_m24c01_rmn6tp,
    add_ad8603aujz_r2_single_supply, add_bgs12wn6e6327xtsa1,
]


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
