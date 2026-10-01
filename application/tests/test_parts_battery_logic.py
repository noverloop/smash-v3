"""Tests for the TLM-1520HPM/S Battery factory + SN74LVC1G08DBVR AND-gate
factory + the just-completed AS4C512M16D3LC datasheet wiring."""

from __future__ import annotations

import pathlib

import pytest

from smash import Design
from smash.parts import (
    add_tlm_1520hpms,
    add_sn74lvc1g08dbvr,
    add_as4c512m16d3lc_12bin,
)


REPO = pathlib.Path(__file__).resolve().parents[2]


# ─── Tadiran TLM-1520HPM/S ──────────────────────────────────────────────

class TestTLM_1520:
    def setup_method(self):
        self.d = Design()
        self.bat = add_tlm_1520hpms(self.d, ref="BT1")

    def test_added_to_design_batteries(self):
        # Battery, not Chip
        assert self.d.battery_by_ref("BT1") is self.bat
        assert self.d.chip_by_ref("BT1") is None

    def test_chemistry(self):
        assert "Li-MnO" in self.bat.chemistry

    def test_electrical_specs(self):
        # Datasheet §2.2
        assert self.bat.capacity_mah == 125.0
        assert self.bat.nominal_voltage_v == 4.0
        assert self.bat.ocv_min_v == 3.95
        assert self.bat.ocv_max_v == 4.07
        assert self.bat.ccv_min_v == 3.88
        assert self.bat.i_continuous_a == 1.75
        assert self.bat.i_pulse_a == 3.75
        assert self.bat.pulse_duration_s == 1.0
        assert self.bat.impedance_mohm == 100.0

    def test_mechanical(self):
        # Datasheet §2.1
        assert self.bat.size_mm == (14.8, 21.0)
        assert self.bat.weight_g == 9.0

    def test_temp_range(self):
        # Datasheet §2.3
        assert self.bat.temp_range_c == (-40, 85)

    def test_hazmat(self):
        # Lithium-metal primary cell — UN3090 transport class
        assert self.bat.hazmat_class == "UN3090"
        assert "UN 38.3" in self.bat.standards

    def test_pack_config(self):
        # Smash uses 3 in parallel
        assert self.bat.pack_count == 3
        assert self.bat.pack_config == "3P"

    def test_pins_solder_tab(self):
        # Two-terminal cell — "+" and "−" solder tabs
        assert self.bat.pin("1").name == "+"
        assert self.bat.pin("2").name == "-"
        # Aliases for ergonomic lookup
        assert self.bat.pin("VBAT").num == "1"
        assert self.bat.pin("GND").num == "2"

    def test_no_footprint(self):
        # The cell doesn't have its own footprint — it mates to power_board's
        # CellAttach_3x2_TLM1520 pad cluster via solder tabs
        assert self.bat.footprint is None

    def test_datasheet_resolves(self):
        assert (REPO / self.bat.datasheet).is_file()

    def test_fab_country_israel(self):
        # Tadiran is Israeli — important sourcing data point
        assert self.bat.fab_country == "IL"

    @pytest.mark.parametrize("substring", [
        "5.25 A",                        # 3P continuous
        "11.25 A",                       # 3P pulse
        "TLM-1550",                      # predecessor reference
        "Storage characteristic",        # the §2.4 capacity-loss model
    ])
    def test_note(self, substring):
        assert substring in (self.bat.note or "")


# ─── SN74LVC1G08DBVR — single AND gate ──────────────────────────────────

class TestSN74LVC1G08:
    def setup_method(self):
        self.d = Design()
        self.q = add_sn74lvc1g08dbvr(self.d, ref="U_AND")

    def test_identity(self):
        assert self.q.manf == "Texas Instruments"
        assert self.q.manf_pn == "SN74LVC1G08DBVR"

    def test_supply(self):
        assert self.q.voltage_rating_v == 6.5
        # 5-V V_CC supported per datasheet; 3.3 V is the typical Smash rail
        assert self.q.vcc_nominal_v == 3.3

    def test_5_pins(self):
        assert len(self.q.pins) == 5

    def test_pin_layout(self):
        # Per SamacSys KiCad sym
        layout = {"1": "A", "2": "B", "3": "GND", "4": "Y", "5": "VCC"}
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_pin_types_set(self):
        assert self.q.pin("A").type == "input"
        assert self.q.pin("B").type == "input"
        assert self.q.pin("Y").type == "output"
        assert self.q.pin("VCC").type == "power"
        assert self.q.pin("GND").type == "ground"

    def test_standards(self):
        s = self.q.standards
        assert any("HBM" in x and "2000" in x for x in s)
        assert any("CDM" in x and "1000" in x for x in s)
        assert any("Latch-up" in x for x in s)

    @pytest.mark.parametrize("substring", [
        "ACTIVATE_CONFIRM",
        "ACTIVATE_SET",
        "COMP_OUT",
        "unforgeable",
        "launch confirmation",   # firmware interlock now; note keeps the rationale
        "1.65 V to 5.5 V",
    ])
    def test_note(self, substring):
        # Note documents the design-intent role on flight_board
        assert substring in (self.q.note or "")

    def test_datasheet_resolves(self):
        assert (REPO / self.q.datasheet).is_file()


# ─── AS4C512M16D3LC datasheet now in place ──────────────────────────────

def test_as4c_datasheet_now_present():
    """The AS4C DDR3 datasheet was logged as missing in TODO §4b — it's
    now in the repo. Confirm the factory's datasheet field resolves."""
    d = Design()
    c = add_as4c512m16d3lc_12bin(d, ref="U_DDR3")
    assert c.datasheet is not None
    assert (REPO / c.datasheet).is_file()


# ─── LP5907 family ──────────────────────────────────────────────────────

from smash.parts import add_lp5907mfx_1_2_nopb, add_lp5907mfx_2_8_nopb


@pytest.mark.parametrize("factory,vout,manf_pn", [
    (add_lp5907mfx_1_2_nopb, 1.2, "LP5907MFX-1.2/NOPB"),
    (add_lp5907mfx_2_8_nopb, 2.8, "LP5907MFX-2.8/NOPB"),
])
class TestLP5907:
    def test_identity(self, factory, vout, manf_pn):
        c = factory(Design(), ref="U1")
        assert c.manf == "Texas Instruments"
        assert c.manf_pn == manf_pn
        assert c.vcc_nominal_v == vout

    def test_pins_5_layout(self, factory, vout, manf_pn):
        c = factory(Design(), ref="U1")
        layout = {"1": "IN", "2": "GND", "3": "EN", "4": "N/C", "5": "OUT"}
        for num, name in layout.items():
            assert c.pin(num).name == name

    def test_en_pin_warns_no_float(self, factory, vout, manf_pn):
        c = factory(Design(), ref="U1")
        en = c.pin("EN")
        assert en.type == "input"
        assert "do not leave floating" in (en.note or "").lower()

    def test_shared_package_and_footprint(self, factory, vout, manf_pn):
        # Both -1.2 and -2.8 use the same SOT-23-5 (DBV) footprint
        c = factory(Design(), ref="U1")
        assert c.package == "SOT-23-5 (DBV)"
        assert c.footprint.name == "SOT95P280X145-5N"
        assert c.height_mm == pytest.approx(1.45)

    def test_temp_range_industrial(self, factory, vout, manf_pn):
        c = factory(Design(), ref="U1")
        assert c.temp_range_c == (-40, 125)

    def test_current_250mA(self, factory, vout, manf_pn):
        c = factory(Design(), ref="U1")
        assert c.i_rms_a == 0.250

    def test_datasheet_resolves(self, factory, vout, manf_pn):
        c = factory(Design(), ref="U1")
        assert (REPO / c.datasheet).is_file()


def test_lp5907_pair_share_datasheet():
    """The whole LP5907 family is one datasheet; both factories should
    reference the same family doc (one copy per part-source directory)."""
    a = add_lp5907mfx_1_2_nopb(Design(), ref="U1")
    b = add_lp5907mfx_2_8_nopb(Design(), ref="U2")
    # Different paths (per-part directories), same filename (family DS)
    assert a.datasheet.endswith("lp5907-family.pdf")
    assert b.datasheet.endswith("lp5907-family.pdf")
    assert a.datasheet != b.datasheet  # per-part directories
