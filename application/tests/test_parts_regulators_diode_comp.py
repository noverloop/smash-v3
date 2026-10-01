"""Verify the regulator + diode + comparator factories transcribe
their ground-truth.

Covers:
  - MCP1640CT-I/CHY  (Microchip boost, SOT-23-6)
  - LMR10510XMFE/NOPB (TI buck, SOT-23-5)
  - TPS61085PW       (TI boost, TSSOP-8)
  - TPS61175PWPR     (TI boost, HTSSOP-14+EP)
  - MBRS340T3G       (onsemi Schottky 3 A, SMC)
  - MBRS540T3G       (onsemi Schottky 5 A, SMC)
  - LMV331IDBVR      (TI comparator, SOT-23-5)
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design, Footprint
from smash.parts import (
    add_mcp1640ct_i_chy, add_lmr10510xmfe_nopb,
    add_tps61085pw, add_tps61175pwpr,
    add_mbrs340t3g, add_mbrs540t3g, add_lmv331idbvr,
)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "application/src/smash/parts/sources"


# ─── artifact-presence parametrized for all 6 parts ──────────────────────

ARTIFACTS = {
    "MCP1640CT-I_CHY": [
        "MCP1640-family.pdf",
        "LIB_MCP1640CT-I_CHY.samacsys.zip",
        "MCP1640CT-I_CHY.kicad_sym",
        "SOT95P270X145-6N.kicad_mod",
        "MCP1640CT-I_CHY.stp",
        "pinmap.txt", "part_info.txt",
    ],
    "LMR10510XMFE_NOPB": [
        "LMR10510.pdf",
        "LIB_LMR10510XMFE_NOPB.samacsys.zip",
        "LMR10510XMFE_NOPB.kicad_sym",
        "SOT95P280X145-5N.kicad_mod",
        "LMR10510XMFE_NOPB.stp",
        "pinmap.txt", "part_info.txt",
    ],
    "TPS61085PW": [
        "TPS61085.pdf",
        "LIB_TPS61085PW.samacsys.zip",
        "TPS61085PW.kicad_sym",
        "SOP65P490X110-8N.kicad_mod",
        "TPS61085PW.stp",
        "pinmap.txt", "part_info.txt",
    ],
    "TPS61175PWPR": [
        "TPS61175.pdf",
        "LIB_TPS61175PWPR.samacsys.zip",
        "TPS61175PWPR.kicad_sym",
        "SOP65P640X120-15N.kicad_mod",
        "TPS61175PWPR.stp",
        "pinmap.txt", "part_info.txt",
    ],
    "MBRS340T3G": [
        "MBRS340T3G.pdf",
        "LIB_MBRS340T3G.samacsys.zip",
        "MBRS340T3G.kicad_sym",
        "DIOM8059X261N.kicad_mod",
        "MBRS340T3G.stp",
        "pinmap.txt", "part_info.txt",
    ],
    "MBRS540T3G": [
        "MBRS540T3G.pdf",
        "LIB_MBRS540T3G.samacsys.zip",
        "MBRS540T3G.kicad_sym",
        "DIOM7958X256N.kicad_mod",
        "MBRS540T3G.stp",
        "pinmap.txt", "part_info.txt",
    ],
    "LMV331IDBVR": [
        "LMV331-LMV393-LMV339-family.pdf",
        "LIB_LMV331IDBVR.samacsys.zip",
        "LMV331IDBVR.kicad_sym",
        "SOT95P280X145-5N.kicad_mod",
        "LMV331IDBVR.stp",
        "pinmap.txt", "part_info.txt",
    ],
}


@pytest.mark.parametrize("part,files", [(p, f) for p, fs in ARTIFACTS.items() for f in fs])
def test_artifact_present(part, files):
    assert (SRC / part / files).is_file(), f"missing: {SRC / part / files}"


# ─── MCP1640CT-I/CHY ─────────────────────────────────────────────────────

class TestMCP1640CT:
    def setup_method(self):
        self.q = add_mcp1640ct_i_chy(Design(), ref="U1")

    def test_identity(self):
        assert self.q.manf == "Microchip"
        assert self.q.manf_pn == "MCP1640CT-I/CHY"

    def test_voltage_rating(self):
        # DS p1 abs max: 6.5 V on EN/VFB/VIN/VSW/VOUT
        assert self.q.voltage_rating_v == 6.5

    def test_temp_range_ambient(self):
        # DS p1: T_A with power -40 to +85 °C
        assert self.q.temp_range_c == (-40, 85)

    def test_tj_max(self):
        assert self.q.tj_max_c == 125.0

    def test_pin_layout(self):
        # Pinmap: 1=SW, 2=GND, 3=EN, 4=VFB, 5=VOUT, 6=VIN
        layout = {"1": "SW", "2": "GND", "3": "EN",
                  "4": "VFB", "5": "VOUT", "6": "VIN"}
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_footprint_sot23_6(self):
        fp = self.q.footprint
        assert fp.name == "SOT95P270X145-6N"
        assert fp.package_class == "SOT-23-6"
        assert len(fp.pads) == 6

    @pytest.mark.parametrize("substring", [
        "0.65 V", "PFM/PWM", "MCP1640CT-I/CHY", "5002H",  # source-of-truth caveat
        "true disconnect", "ESD HBM",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


# ─── LMR10510XMFE/NOPB ───────────────────────────────────────────────────

class TestLMR10510:
    def setup_method(self):
        self.q = add_lmr10510xmfe_nopb(Design(), ref="U2")

    def test_identity(self):
        assert self.q.manf == "Texas Instruments"
        assert self.q.manf_pn == "LMR10510XMFE/NOPB"

    def test_electrical(self):
        assert self.q.voltage_rating_v == 7.0
        assert self.q.i_rms_a == 1.0           # 1 A buck output
        assert self.q.tj_max_c == 150.0

    def test_pin_layout(self):
        layout = {"1": "SW", "2": "GND", "3": "FB", "4": "EN", "5": "VIN"}
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_footprint_sot23_5(self):
        fp = self.q.footprint
        assert fp.name == "SOT95P280X145-5N"
        assert fp.package_class == "SOT-23-5"
        assert len(fp.pads) == 5

    def test_3d_model_resolves(self):
        assert (REPO_ROOT / self.q.footprint.model_3d_path).is_file()


# ─── TPS61085PW ──────────────────────────────────────────────────────────

class TestTPS61085:
    def setup_method(self):
        self.q = add_tps61085pw(Design(), ref="U3")

    def test_electrical(self):
        # DS abs max: SW pin 20 V; i_rms = 2 A switch
        assert self.q.voltage_rating_v == 20.0
        assert self.q.i_rms_a == 2.0

    def test_temp_range_tj(self):
        # Datasheet p3: T_J operating -40 to +150 °C
        assert self.q.temp_range_c == (-40, 150)

    def test_pin_layout_tssop8(self):
        layout = {
            "1": "COMP", "2": "FB",   "3": "EN",   "4": "PGND",
            "5": "SW",   "6": "IN",   "7": "FREQ", "8": "SS",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_in_alias_vin(self):
        # Pin 6 datasheet name "IN"; alias VIN for ergonomic lookup
        assert self.q.pin("VIN").num == "6"

    def test_footprint_tssop8(self):
        fp = self.q.footprint
        assert fp.name == "SOP65P490X110-8N"
        assert fp.pitch_mm == pytest.approx(0.65)
        assert len(fp.pads) == 8


# ─── TPS61175PWPR ────────────────────────────────────────────────────────

class TestTPS61175:
    def setup_method(self):
        self.q = add_tps61175pwpr(Design(), ref="U4")

    def test_electrical(self):
        # DS p4 abs max: SW pin 40 V; switch limit 3.8 A typ
        assert self.q.voltage_rating_v == 40.0
        assert self.q.i_rms_a == 3.8

    def test_thermal_pad(self):
        # R_θJC(bottom) = 5.8 — used for thermal pad sink
        assert self.q.rth_jc_cw == 5.8
        assert self.q.rth_ja_cw == 45.2

    def test_15_pins_including_ep(self):
        # 14 functional + EP = 15
        assert len(self.q.pins) == 15
        assert self.q.pin("15").name == "EP"
        assert self.q.pin("EP").type == "ground"

    def test_nc_pin_carries_caveat(self):
        # DS p3-4: "Reserved pin. Must connect this pin to ground."
        nc = self.q.pin("11")
        assert nc.name == "NC"
        assert nc.type == "nc"
        assert "must connect" in (nc.note or "").lower()

    def test_dual_sw_pins(self):
        # Pins 1 and 2 are both SW (paralleled internally)
        assert self.q.pin("1").name == "SW_1"
        assert self.q.pin("2").name == "SW_2"

    def test_triple_pgnd_pins(self):
        # Pins 12, 13, 14 are all power ground
        for n in ("12", "13", "14"):
            assert self.q.pin(n).name.startswith("PGND")
            assert self.q.pin(n).type == "ground"

    def test_footprint_htssop14(self):
        fp = self.q.footprint
        assert fp.name == "SOP65P640X120-15N"
        assert fp.pitch_mm == pytest.approx(0.65)
        assert len(fp.pads) == 15
        # Exposed-pad geometry — the SamacSys mod draws the EP with a
        # 90° rotation and (size 2.31 2.46): effective 2.46 wide × 2.31
        # tall, baked into the model (the Pad has no rotation field).
        ep = fp.pad("15")
        assert ep.size_mm == pytest.approx((2.46, 2.31))


# ─── MBRS340T3G ──────────────────────────────────────────────────────────

class TestMBRS340T3G:
    def setup_method(self):
        self.q = add_mbrs340t3g(Design(), ref="D1")

    def test_identity(self):
        assert self.q.manf == "onsemi"
        assert self.q.manf_pn == "MBRS340T3G"

    def test_ratings(self):
        # DS p2: V_RRM=40, I_F(AV)=3 A @ 110 °C
        assert self.q.voltage_rating_v == 40.0
        assert self.q.i_rms_a == 3.0

    def test_weight_g_from_datasheet(self):
        # DS p1 Mechanical Characteristics: "Weight: 217 mg (Approximately)"
        # This is one of the very few cases where the datasheet states weight.
        assert self.q.weight_g == 0.217

    def test_body_material_from_datasheet(self):
        # DS p1: "Case: Epoxy, Molded, Epoxy Meets UL 94 V-0"
        assert "epoxy" in (self.q.body_material or "").lower()
        assert "UL 94" in (self.q.body_material or "")

    def test_temp_range_tj(self):
        assert self.q.temp_range_c == (-65, 150)

    def test_compliance(self):
        s = self.q.standards
        assert "RoHS" in s
        assert "MSL 1" in s
        assert any("UL 94 V-0" in x for x in s)
        assert any("HBM Class 3B" in x for x in s)

    def test_pin_layout(self):
        # Pinmap: 1=K (cathode, on the polarity-band side), 2=A
        assert self.q.pin("1").name == "K"
        assert "Cathode" in self.q.pin("1").aliases
        assert self.q.pin("2").name == "A"
        assert "Anode" in self.q.pin("2").aliases

    def test_footprint_smc(self):
        fp = self.q.footprint
        assert fp.name == "DIOM8059X261N"
        assert fp.package_class == "SMC (DO-214AB)"
        assert len(fp.pads) == 2
        # Big pads — 2.25 × 3.15 mm
        for pad in fp.pads:
            assert pad.size_mm == pytest.approx((2.25, 3.15))

    @pytest.mark.parametrize("substring", [
        "MBRS320T3G", "MBRS330T3G", "SBRS8340T3G",  # variant references
        "AEC-Q101", "ISO 7637", "epoxy",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


# ─── MBRS540T3G ──────────────────────────────────────────────────────────

class TestMBRS540T3G:
    def setup_method(self):
        self.q = add_mbrs540t3g(Design(), ref="D1")

    def test_identity(self):
        assert self.q.manf == "onsemi"
        assert self.q.manf_pn == "MBRS540T3G"

    def test_ratings(self):
        # DS p1: V_RRM=40 V, I_F(AV)=5 A — the 5 A sibling of the MBRS340.
        assert self.q.voltage_rating_v == 40.0
        assert self.q.i_rms_a == 5.0

    def test_weight_g_from_datasheet(self):
        # DS p1 Mechanical Characteristics: "Weight: 217 mg (Approximately)"
        assert self.q.weight_g == 0.217

    def test_body_material_from_datasheet(self):
        assert "epoxy" in (self.q.body_material or "").lower()
        assert "UL 94" in (self.q.body_material or "")

    def test_temp_range_tj(self):
        assert self.q.temp_range_c == (-65, 150)

    def test_compliance(self):
        s = self.q.standards
        assert "RoHS" in s
        assert "MSL 1" in s
        assert any("UL 94 V-0" in x for x in s)

    def test_pin_layout(self):
        # Pinmap: 1=K (cathode, on the polarity-band side), 2=A
        assert self.q.pin("1").name == "K"
        assert "Cathode" in self.q.pin("1").aliases
        assert self.q.pin("2").name == "A"
        assert "Anode" in self.q.pin("2").aliases

    def test_footprint_smc(self):
        fp = self.q.footprint
        assert fp.name == "DIOM7958X256N"
        assert fp.package_class == "SMC (DO-214AB)"
        assert len(fp.pads) == 2
        # Big SMC pads — 2.0 × 3.05 mm
        for pad in fp.pads:
            assert pad.size_mm == pytest.approx((2.0, 3.05))

    @pytest.mark.parametrize("substring", [
        "MBRS340",            # 3 A sibling it supersedes on the USB-OR path
        "BAT_PROT", "Q_ISO",  # the depot-power application it was sized for (eFuse removed 2026-06)
        "NRVBS540T3G", "AEC-Q101",  # automotive equivalent
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


# ─── LMV331IDBVR ─────────────────────────────────────────────────────────

class TestLMV331:
    def setup_method(self):
        self.q = add_lmv331idbvr(Design(), ref="U5")

    def test_identity(self):
        assert self.q.manf == "Texas Instruments"
        assert self.q.manf_pn == "LMV331IDBVR"

    def test_supply_ratings(self):
        # DS p4: V_CC abs max 5.5 V
        assert self.q.voltage_rating_v == 5.5
        # Caller decides nominal — factory leaves it None
        assert self.q.vcc_nominal_v is None

    def test_temp_range(self):
        # DS p4: T_A recommended -40 to +125 °C
        assert self.q.temp_range_c == (-40, 125)
        assert self.q.tj_max_c == 150.0

    def test_pin_layout(self):
        # Pinmap.txt: 1=1INP, 2=GND, 3=1INM, 4=OUT, 5=VCCP
        layout = {"1": "1INP", "2": "GND", "3": "1INM",
                  "4": "OUT",  "5": "VCCP"}
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_input_aliases(self):
        # Caller ergonomics — alias lookup should resolve
        assert self.q.pin("IN+").num == "1"
        assert self.q.pin("IN-").num == "3"

    def test_output_pin_open_drain_note(self):
        out = self.q.pin("OUT")
        assert out.type == "output"
        assert "open-drain" in (out.note or "").lower()

    def test_vccp_alias(self):
        assert self.q.pin("VCC").num == "5"
        assert self.q.pin("V+").num == "5"

    def test_footprint_sot23_5(self):
        fp = self.q.footprint
        assert fp.name == "SOT95P280X145-5N"
        assert len(fp.pads) == 5

    def test_3d_model_resolves(self):
        # LMV331 STEP must point to its own model, NOT the LMR10510 STEP
        # (both use the same SOT-23-5 footprint but different chips).
        assert "LMV331IDBVR" in self.q.footprint.model_3d_path
        assert (REPO_ROOT / self.q.footprint.model_3d_path).is_file()

    @pytest.mark.parametrize("substring", [
        "LMV393", "LMV339",            # family variants
        "open-drain", "pull-up",       # output convention
        "V_CC supply voltage       : 5.5 V",
        "HBM (ANSI/ESDA",              # ESD spec citation
        "CDM (JESD22-C101)",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


# ─── shared invariants across this batch ─────────────────────────────────

ALL_FACTORIES = [
    add_mcp1640ct_i_chy,
    add_lmr10510xmfe_nopb,
    add_tps61085pw,
    add_tps61175pwpr,
    add_mbrs340t3g,
    add_lmv331idbvr,
]


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_each_factory_validates_clean(factory):
    """Every factory should pass all registered Design validators when
    its chip is added with at least one wired net (otherwise the
    floating-chip validator would fire)."""
    d = Design()
    chip = factory(d, ref="U_TEST")
    # Wire every pin to a unique-ish net so the floating-chip validator
    # doesn't fire. Use a stable per-pin net naming.
    from _helpers import wire_chip_synthetically
    wire_chip_synthetically(d, chip)
    errors = [i for i in d.validate() if i.severity == "error"]
    assert errors == [], f"{factory.__name__}: {errors}"


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
