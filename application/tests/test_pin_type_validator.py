"""Tests for the `_v_pin_type_vs_net_kind` validator."""
from __future__ import annotations

from smash.state import Design, Pin


# ── catches: power pin on signal net ───────────────────────────────────

def test_power_pin_on_signal_net_flagged():
    d = Design()
    chip = d.add_chip(ref="U1", pins=[Pin(num="1", name="VCC", type="power")])
    sig = d.add_signal_net("MAYBE_VCC")
    sig.connect(chip.pin("1"))

    issues = [i for i in d.validate() if i.rule == "power_pin_on_non_power_net"]
    assert len(issues) == 1
    assert "VCC" in issues[0].message
    assert "U1" in issues[0].refs


def test_power_pin_on_power_net_clean():
    d = Design()
    chip = d.add_chip(ref="U1", pins=[Pin(num="1", name="VCC", type="power")])
    d.add_power_net("VDD", voltage_v=3.3).connect(chip.pin("1"))

    issues = [i for i in d.validate() if i.rule == "power_pin_on_non_power_net"]
    assert issues == []


# ── catches: ground pin on signal net ──────────────────────────────────

def test_ground_pin_on_signal_net_flagged():
    d = Design()
    chip = d.add_chip(ref="U1", pins=[Pin(num="2", name="GND", type="ground")])
    d.add_signal_net("NOT_GND").connect(chip.pin("2"))

    issues = [i for i in d.validate() if i.rule == "ground_pin_on_non_ground_net"]
    assert len(issues) == 1


def test_ground_pin_on_ground_net_clean():
    d = Design()
    chip = d.add_chip(ref="U1", pins=[Pin(num="2", name="GND", type="ground")])
    d.add_ground_net("GND").connect(chip.pin("2"))

    issues = [i for i in d.validate() if i.rule == "ground_pin_on_non_ground_net"]
    assert issues == []


# ── supply-mode is encoded in the factory choice, not pin aliases ─────

def test_supply_mode_via_specialized_factory_single_supply():
    """The user's design rule: factories must specialize per supply
    mode rather than carrying ambiguous aliases on a single pin.
    Single-supply AD8603 factory has V- typed as `ground` — the
    validator accepts it on a ground net without any relaxation."""
    from smash.parts import add_ad8603aujz_r2_single_supply
    d = Design()
    chip = add_ad8603aujz_r2_single_supply(d, ref="U_OPA")
    d.add_ground_net("GND").connect(chip.pin("2"))
    d.add_power_net("VDD", voltage_v=3.3).connect(chip.pin("5"))
    pin_issues = [i for i in d.validate()
                  if i.rule in ("power_pin_on_non_power_net",
                                "ground_pin_on_non_ground_net")]
    assert pin_issues == []


def test_supply_mode_via_specialized_factory_dual_supply():
    """Dual-supply AD8603 factory has V- typed as `power` — wire it
    to a negative power rail."""
    from smash.parts import add_ad8603aujz_r2_dual_supply
    d = Design()
    chip = add_ad8603aujz_r2_dual_supply(d, ref="U_OPA")
    d.add_power_net("VEE", voltage_v=-2.5).connect(chip.pin("2"))
    d.add_power_net("VDD", voltage_v=2.5).connect(chip.pin("5"))
    pin_issues = [i for i in d.validate()
                  if i.rule in ("power_pin_on_non_power_net",
                                "ground_pin_on_non_ground_net")]
    assert pin_issues == []


# ── signal-class pins are unrestricted ─────────────────────────────────

def test_io_pin_on_power_net_not_flagged():
    """A logic-input enable tied to VDD is normal. Don't flag."""
    d = Design()
    chip = d.add_chip(ref="U1", pins=[Pin(num="3", name="EN", type="input")])
    d.add_power_net("VDD", voltage_v=3.3).connect(chip.pin("3"))

    pin_issues = [i for i in d.validate()
                  if i.rule in ("power_pin_on_non_power_net",
                                 "ground_pin_on_non_ground_net")]
    assert pin_issues == []


def test_io_pin_on_ground_net_not_flagged():
    """A strap input pulled to GND is normal. Don't flag."""
    d = Design()
    chip = d.add_chip(ref="U1", pins=[Pin(num="4", name="STRAP", type="io")])
    d.add_ground_net("GND").connect(chip.pin("4"))

    pin_issues = [i for i in d.validate()
                  if i.rule in ("power_pin_on_non_power_net",
                                 "ground_pin_on_non_ground_net")]
    assert pin_issues == []


# ── untyped pins are skipped (don't false-positive on legacy data) ─────

def test_untyped_pin_skipped():
    d = Design()
    chip = d.add_chip(ref="U1", pins=[Pin(num="1", name="X", type=None)])
    d.add_signal_net("SIG").connect(chip.pin("1"))

    pin_issues = [i for i in d.validate()
                  if i.rule in ("power_pin_on_non_power_net",
                                 "ground_pin_on_non_ground_net")]
    assert pin_issues == []
