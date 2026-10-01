"""Tests for the Group D family-parameterized passives + netlist helpers.

Covers:

  - value-string parsing (R/C/L; SI prefixes; R-notation)
  - factory output (SI fields, footprint, height, datasheet path)
  - dispatch policy in `cap_to_gnd` (2.2–10 µF → N×0603 array)
  - ECM-absorbed flag → Chip.dnp + note marker (gated by ECM_ABSORB)
  - wiring helpers connect the right nets
  - I²C pullup pair creation
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design
from smash import netlist as smash_netlist
from smash.parts._passives_util import (
    parse_resistance_ohm, parse_capacitance_f, parse_inductance_h,
)
from smash.parts.passives import (
    add_resistor_0402_vishay,
    add_capacitor_x7r_0402_kemet,
    add_capacitor_x7r_0603_kemet_mil,
    add_capacitor_x7r_0805_kemet_mil,
    add_capacitor_c0g_0603_avx_sqcs,
    add_capacitor_tantalum_3528_kemet_t491,
    add_capacitor_polymer_7343_kemet_t528,
    add_inductor_we_ki_0402_wurth,
    add_inductor_tms201210alm_tdk,
)
from smash.netlist import (
    _cap_factory_for_value,
    cap_to_gnd, res_between, ind_between, add_i2c_pullups,
)


REPO = pathlib.Path(__file__).resolve().parents[2]


# ── value parsing ───────────────────────────────────────────────────────


class TestParseResistance:
    @pytest.mark.parametrize("s,expected", [
        ("100",     100.0),
        ("4.7k",    4700.0),
        ("49k9",    49900.0),       # k-notation in middle
        ("4R7",     4.7),           # R = decimal point
        ("0R1",     0.1),
        ("100m",    0.1),
        ("1.5M",    1.5e6),
    ])
    def test_parses(self, s, expected):
        assert parse_resistance_ohm(s) == pytest.approx(expected)


class TestParseCapacitance:
    @pytest.mark.parametrize("s,expected", [
        ("100nF",   100e-9),
        ("1uF",     1e-6),
        ("4.7uF",   4.7e-6),
        ("22uF",    22e-6),
        ("100uF",   100e-6),
        ("10pF",    10e-12),
        ("22uF/16V", 22e-6),       # voltage suffix dropped
        ("0.1uF",   0.1e-6),
    ])
    def test_parses(self, s, expected):
        assert parse_capacitance_f(s) == pytest.approx(expected)


class TestParseInductance:
    @pytest.mark.parametrize("s,expected", [
        ("10nH",    10e-9),
        ("1uH",     1e-6),
        ("4.7uH",   4.7e-6),
        ("4u7",     4.7e-6),       # u as decimal
        ("10uH",    10e-6),
        ("100nH",   100e-9),
        ("1.0uH",   1e-6),
    ])
    def test_parses(self, s, expected):
        assert parse_inductance_h(s) == pytest.approx(expected)


# ── resistor factory ────────────────────────────────────────────────────


class TestResistor0402:
    def test_creates_resistor(self):
        d = Design()
        r = add_resistor_0402_vishay(d, ref="R1", value="4.7k")
        assert r.resistance_ohm == 4700.0
        assert r.tolerance_pct == 1.0
        assert r.size_mm == (1.0, 0.5)
        assert r.height_mm == 0.45
        assert r.power_rating_w == 0.063
        assert r.manf == "Vishay"
        assert "CRCW0402" in r.manf_pn
        # Two-pin footprint
        assert len(r.footprint.pads) == 2

    def test_datasheet_resolves(self):
        d = Design()
        r = add_resistor_0402_vishay(d, ref="R1", value="100")
        assert (REPO / r.datasheet).is_file()


# ── capacitor factories ─────────────────────────────────────────────────


class TestCapacitors:
    def test_0402_x7r_ecm_placeholder(self):
        d = Design()
        c = add_capacitor_x7r_0402_kemet(d, ref="C1", value="100nF")
        assert c.capacitance_f == pytest.approx(100e-9)
        assert c.height_mm == 0.50
        assert "X7R" in c.dielectric

    def test_0603_mil_x7r(self):
        d = Design()
        c = add_capacitor_x7r_0603_kemet_mil(d, ref="C1", value="1uF")
        assert c.capacitance_f == 1e-6
        assert c.size_mm == (1.6, 0.8)
        assert c.height_mm == 0.95
        assert "MIL-PRF-32535" in c.standards

    def test_0805_mil_x7r(self):
        d = Design()
        c = add_capacitor_x7r_0805_kemet_mil(d, ref="C1", value="2.2uF")
        assert c.capacitance_f == 2.2e-6
        assert c.size_mm == (2.0, 1.25)
        assert c.height_mm == 1.45

    def test_avx_sqcs_c0g(self):
        """AVX SQCS is C0G ceramic — NOT silver mica (system.py was wrong).
        The note explains the historical confusion."""
        d = Design()
        c = add_capacitor_c0g_0603_avx_sqcs(d, ref="C1", value="10pF")
        assert c.dielectric == "C0G/NP0"
        # The note mentions "silver mica" to flag the historical mislabel,
        # not to claim the part IS silver mica.
        assert "C0G" in (c.note or "")
        assert "not silver mica" in (c.note or "").lower() \
            or "misnamed" in (c.note or "").lower() \
            or "mis-labelled" in (c.note or "").lower()
        assert c.voltage_rating_v == 250.0
        assert c.size_mm == (1.6, 0.8)
        assert c.height_mm == 0.76

    def test_t491_case_b_uses_thinnest_variant(self):
        """T491 case-B 3528-12 is 1.10 mm Z (vs system.py's -21 = 1.90 mm)."""
        d = Design()
        c = add_capacitor_tantalum_3528_kemet_t491(d, ref="C1", value="22uF")
        assert c.height_mm == 1.10
        assert "MnO" in c.dielectric

    def test_t528_case_x_uses_thinnest_variant(self):
        """T528 case-X 7343-15 is 1.40 mm Z (vs system.py's -43 = 4.30 mm)."""
        d = Design()
        c = add_capacitor_polymer_7343_kemet_t528(d, ref="C1", value="100uF")
        assert c.height_mm == 1.40
        assert "KO-CAP" in c.dielectric


# ── inductor factories ──────────────────────────────────────────────────


class TestInductors:
    def test_we_ki_0402(self):
        d = Design()
        l = add_inductor_we_ki_0402_wurth(d, ref="L1", value="10nH")
        assert l.inductance_h == 10e-9
        assert l.size_mm == (1.0, 0.5)
        assert l.height_mm == 0.55

    def test_tms_1u0_isat(self):
        d = Design()
        l = add_inductor_tms201210alm_tdk(d, ref="L1", value="1.0uH")
        assert l.inductance_h == 1e-6
        assert l.i_sat_a == 2.7
        assert l.height_mm == 1.0
        assert l.manf_pn == "TMS201210ALM-1R0MTAA"

    def test_tms_r47_isat_higher(self):
        """0.47 µH variant has higher Isat — for BUCK1 high-current swap."""
        d = Design()
        l = add_inductor_tms201210alm_tdk(d, ref="L1", value="0.47uH")
        assert l.i_sat_a == 3.4
        assert l.manf_pn == "TMS201210ALM-R47MTAA"


# ── cap_to_gnd dispatch policy ──────────────────────────────────────────


class TestCapToGndDispatch:
    @pytest.mark.parametrize("value,expected_factory,expected_n", [
        ("10pF",   "add_capacitor_c0g_0603_avx_sqcs", 1),
        ("100nF",  "add_capacitor_x7r_0402_kemet",    1),
        ("470nF",  "add_capacitor_x7r_0603_kemet_mil", 1),   # <0.9 µF → 0603
        ("1uF",    "add_capacitor_x7r_0805_kemet_mil", 1),   # ≥0.9 µF → 0805
                                                             # (matches system.py:_cap_fp)
        ("2.2uF",  "add_capacitor_x7r_0603_kemet_mil", 1),  # parallel of 1
        ("4.7uF",  "add_capacitor_x7r_0603_kemet_mil", 2),  # 2×2.2 µF
        ("10uF",   "add_capacitor_x7r_0603_kemet_mil", 5),  # 5×2.2 µF parallel
        ("22uF",   "add_capacitor_tantalum_3528_kemet_t491", 1),
        ("100uF",  "add_capacitor_polymer_7343_kemet_t528",  1),
    ])
    def test_dispatch(self, value, expected_factory, expected_n):
        factory, n = _cap_factory_for_value(value)
        assert factory.__name__ == expected_factory
        assert n == expected_n


class TestCapToGnd:
    def test_single_cap_wired_to_two_nets(self):
        d = Design()
        d.add_signal_net("VDD"); d.add_ground_net("GND")
        chips = cap_to_gnd(d, "VDD", "100nF", ref="C1")
        assert len(chips) == 1
        # Net should have the connection
        net = d.net_by_name("VDD")
        assert ("C1", "1") in net.pins
        gnd = d.net_by_name("GND")
        assert ("C1", "2") in gnd.pins

    def test_10uF_emits_5_parallel_0603(self):
        """The 10 µF win — parallel array, lower Z, lower ESR.
        Each array element is a 2.2 µF 0603; 5 in parallel = ~11 µF."""
        d = Design()
        d.add_signal_net("VDD"); d.add_ground_net("GND")
        chips = cap_to_gnd(d, "VDD", "10uF", ref="C_BULK")
        assert len(chips) == 5
        refs = {c.ref for c in chips}
        assert refs == {"C_BULK_1", "C_BULK_2", "C_BULK_3", "C_BULK_4", "C_BULK_5"}
        # Each is a 0603 X7R MIL part at 2.2 µF
        for c in chips:
            assert c.size_mm == (1.6, 0.8)
            assert c.capacitance_f == pytest.approx(2.2e-6)
            assert c.value == "2.2uF"
        # All 5 are connected to VDD and to GND
        vdd_pins = {(r, n) for r, n in d.net_by_name("VDD").pins}
        assert len(vdd_pins) == 5

    def test_embedded_cap_absorbs_populated_when_switch_off(self):
        """Default build (ECM_ABSORB off): the flag is recorded in the
        note but the cap is a real, populated part."""
        d = Design()
        d.add_signal_net("VDD"); d.add_ground_net("GND")
        chips = cap_to_gnd(d, "VDD", "100nF",
                            ref="C_HF", embedded_cap_absorbs=True)
        assert len(chips) == 1
        assert chips[0].dnp is False
        assert "ECM candidate — POPULATED" in (chips[0].note or "")

    def test_embedded_cap_absorbs_marks_dnp_when_switch_on(self, monkeypatch):
        """SMASH_ECM_ABSORB=1 build: the laminate takes the position and
        the part is DNP'd out of the BOM."""
        monkeypatch.setattr(smash_netlist, "ECM_ABSORB", True)
        d = Design()
        d.add_signal_net("VDD"); d.add_ground_net("GND")
        chips = cap_to_gnd(d, "VDD", "100nF",
                            ref="C_HF", embedded_cap_absorbs=True)
        assert len(chips) == 1
        assert chips[0].dnp is True
        assert "ECM-absorbed" in (chips[0].note or "")

    def test_force_c0g_overrides_x7r(self):
        """For RF / TIA feedback positions where C0G matters."""
        d = Design()
        d.add_signal_net("RF"); d.add_ground_net("GND")
        chips = cap_to_gnd(d, "RF", "1nF", ref="C_RF", force_c0g=True)
        assert chips[0].dielectric == "C0G/NP0"


# ── res_between + ind_between ──────────────────────────────────────────


def test_res_between():
    d = Design()
    d.add_power_net("VDD", voltage_v=3.3); d.add_signal_net("SDA")
    r = res_between(d, "VDD", "SDA", "4.7k", ref="RPU_SDA")
    assert r.resistance_ohm == 4700.0
    # Wiring: net VDD has pin 1, net SDA has pin 2
    assert ("RPU_SDA", "1") in d.net_by_name("VDD").pins
    assert ("RPU_SDA", "2") in d.net_by_name("SDA").pins


def test_ind_between_auto_dispatch():
    d = Design()
    d.add_signal_net("VIN"); d.add_signal_net("SW")
    # 100 nH → WE-KI 0402
    l1 = ind_between(d, "VIN", "SW", "100nH", ref="L1")
    assert l1.manf == "Würth Elektronik"
    # 1 µH → TMS201210ALM
    l2 = ind_between(d, "VIN", "SW", "1.0uH", ref="L2")
    assert l2.manf == "TDK"


def test_ind_between_rejects_unknown_range():
    d = Design()
    d.add_signal_net("A"); d.add_signal_net("B")
    with pytest.raises(ValueError, match="no auto-dispatch"):
        ind_between(d, "A", "B", "10uH", ref="L_BIG")


# ── i2c pullups ────────────────────────────────────────────────────────


def test_i2c_pullups_creates_pair():
    d = Design()
    d.add_power_net("VDD", voltage_v=3.3)
    d.add_signal_net("I2C_SCL"); d.add_signal_net("I2C_SDA")
    r_scl, r_sda = add_i2c_pullups(d, "I2C_SCL", "I2C_SDA",
                                    vdd_net="VDD", value="4.7k",
                                    prefix="RPU")
    assert r_scl.resistance_ohm == 4700.0
    assert r_sda.resistance_ohm == 4700.0
    # Names follow prefix_<net> pattern
    assert "I2C_SCL" in r_scl.ref
    assert "I2C_SDA" in r_sda.ref
    # Intent string captured
    assert "SCL" in (r_scl.pin("1").intent or r_scl.pin("2").intent or "")
