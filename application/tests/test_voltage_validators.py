"""Tests for the three voltage-consistency validators."""
from __future__ import annotations

import json
import tempfile
import pathlib

from smash.state import Design, Net, Pin


# ── _v_power_net_has_voltage ──────────────────────────────────────────

def test_power_net_without_voltage_flagged():
    """A net with kind='power' but voltage_v=None should fail."""
    d = Design()
    # Bypass add_power_net's required voltage_v by constructing the
    # Net directly.
    n = Net(name="HALF_DEFINED_RAIL", kind="power", voltage_v=None)
    d.nets.append(n)
    issues = [i for i in d.validate() if i.rule == "power_net_missing_voltage"]
    assert len(issues) == 1
    assert "HALF_DEFINED_RAIL" in issues[0].message


def test_power_net_with_voltage_clean():
    d = Design()
    d.add_power_net("VDD", voltage_v=3.3)
    assert [i for i in d.validate()
            if i.rule == "power_net_missing_voltage"] == []


def test_signal_net_without_voltage_not_flagged():
    """Signal/ground nets have no voltage_v and shouldn't be flagged."""
    d = Design()
    d.add_signal_net("DATA")
    d.add_ground_net("GND")
    assert [i for i in d.validate()
            if i.rule == "power_net_missing_voltage"] == []


# ── _v_net_voltage_matches_pinspec (range check) ───────────────────────

def test_voltage_outside_range_flagged():
    """LDL112PV33R VIN accepts 1.6 - 5.5 V per datasheet. Feeding it
    6 V should fail."""
    from smash.parts.ldos import add_ldl112pv33r
    d = Design()
    c = add_ldl112pv33r(d, ref="U_LDO")
    # Wire VIN to a 6 V rail (above 5.5 V abs max)
    d.add_power_net("OVER_RAIL", voltage_v=6.0).connect(c.pin("VIN"))
    # Wire other power pins so floating-pin validator doesn't fire
    d.add_power_net("VOUT_RAIL", voltage_v=3.3).connect(c.pin("VOUT"))
    d.add_signal_net("EN_SIG").connect(c.pin("EN"))
    d.add_ground_net("GND").connect_all([c.pin("GND"), c.pin("EP")])
    issues = [i for i in d.validate() if i.rule == "voltage_outside_pin_rating"]
    assert any("OVER_RAIL" in i.message for i in issues)


def test_voltage_inside_range_clean():
    """Same chip, but VIN gets 3.3 V (well within the 1.6-5.5 V range)."""
    from smash.parts.ldos import add_ldl112pv33r
    d = Design()
    c = add_ldl112pv33r(d, ref="U_LDO")
    d.add_power_net("INPUT_RAIL", voltage_v=3.3).connect(c.pin("VIN"))
    d.add_power_net("VOUT_RAIL", voltage_v=3.3).connect(c.pin("VOUT"))
    d.add_signal_net("EN_SIG").connect(c.pin("EN"))
    d.add_ground_net("GND").connect_all([c.pin("GND"), c.pin("EP")])
    assert [i for i in d.validate()
            if i.rule == "voltage_outside_pin_rating"] == []


# ── _v_net_voltage_matches_pinspec (nominal check) ─────────────────────

def test_voltage_mismatch_pin_nominal_flagged():
    """LDL112PV33R VOUT is nominally 3.3 V per pinspec. Connecting it
    to a 5 V net (well outside ±10 %) should fail."""
    from smash.parts.ldos import add_ldl112pv33r
    d = Design()
    c = add_ldl112pv33r(d, ref="U_LDO")
    d.add_power_net("WRONG_VOUT", voltage_v=5.0).connect(c.pin("VOUT"))
    d.add_power_net("VIN_RAIL", voltage_v=4.0).connect(c.pin("VIN"))
    d.add_signal_net("EN_SIG").connect(c.pin("EN"))
    d.add_ground_net("GND").connect_all([c.pin("GND"), c.pin("EP")])
    issues = [i for i in d.validate()
              if i.rule == "voltage_mismatch_pin_nominal"]
    assert any("WRONG_VOUT" in i.message for i in issues)


def test_voltage_within_tolerance_clean():
    """LDL112PV33R VOUT at 3.5 V is within ±10 % of 3.3 V nominal."""
    from smash.parts.ldos import add_ldl112pv33r
    d = Design()
    c = add_ldl112pv33r(d, ref="U_LDO")
    # 3.5 V is within ±10 % of 3.3 V (3.3 × 1.1 = 3.63)
    d.add_power_net("VOUT_RAIL", voltage_v=3.5).connect(c.pin("VOUT"))
    d.add_power_net("VIN_RAIL", voltage_v=4.0).connect(c.pin("VIN"))
    d.add_signal_net("EN_SIG").connect(c.pin("EN"))
    d.add_ground_net("GND").connect_all([c.pin("GND"), c.pin("EP")])
    assert [i for i in d.validate()
            if i.rule == "voltage_mismatch_pin_nominal"] == []


# ── interaction with chips without pinspec sidecars ────────────────────

def test_chip_without_pinspec_not_voltage_validated():
    """A chip with manf_pn that has no pinspec.json sidecar should
    skip voltage validation silently (opt-in framework)."""
    d = Design()
    c = d.add_chip(
        ref="U_UNKNOWN", manf_pn="NONEXISTENT_PN_12345",
        pins=[Pin(num="1", name="VDD", type="power")],
    )
    d.add_power_net("ARBITRARY", voltage_v=99.9).connect(c.pin("1"))
    # No pinspec, no voltage cross-check
    voltage_issues = [i for i in d.validate()
                      if i.rule in ("voltage_outside_pin_rating",
                                    "voltage_mismatch_pin_nominal")]
    assert voltage_issues == []


# ── end-to-end against the twin ────────────────────────────────────────

def test_twin_voltage_checks_pass():
    """The maximalist twin should pass all three voltage validators."""
    import importlib, pathlib, sys
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_maximalist_system")
    finally:
        sys.path.pop(0)

    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in [gen.build_qpd_module,
               gen.build_yagi_antenna_a_flex, gen.build_yagi_antenna_b_flex,
               gen.build_nose_cap, gen.build_camera_module,
               gen.build_activation_interface, gen.build_radar_module,
               gen.build_companion_compute,
               gen.build_power_board, gen.build_wakeup_board,
               gen.build_spacers]:   # wakeup_board folds in the IMU/mag (build_flight_board)
        fn(d)

    voltage_issues = [i for i in d.validate()
                      if i.rule in ("power_net_missing_voltage",
                                    "voltage_outside_pin_rating",
                                    "voltage_mismatch_pin_nominal")]
    assert voltage_issues == [], (
        f"twin voltage validators failed:\n" +
        "\n".join(f"  [{i.rule}] {i.message}" for i in voltage_issues)
    )
