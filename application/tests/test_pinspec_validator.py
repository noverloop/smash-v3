"""Tests for the datasheet-as-validator framework (smash.parts._pinspec)."""
from __future__ import annotations

from smash.parts._pinspec import load_pinspec, compare, _norm
from smash.parts.ldos import add_ldl112pv33r, add_ldl112pv18r
from smash.parts.sensors import add_tmp117maidrvr
from smash.parts.oscillators import add_sit1630ae_s6_dcc_32_768e
from smash.state import Design, Pin


# ── pinspec loader ────────────────────────────────────────────────────

def test_load_pinspec_returns_none_when_missing():
    assert load_pinspec("DOES_NOT_EXIST_PN") is None


def test_load_ldl112pv33r_pinspec():
    spec = load_pinspec("LDL112PV33R")
    assert spec is not None
    assert spec.manf_pn == "LDL112PV33R"
    assert "DS10321" in spec.datasheet
    nums = {p.num for p in spec.pins}
    assert nums == {"1", "2", "3", "4", "5", "6", "7"}


def test_load_tmp117_pinspec():
    spec = load_pinspec("TMP117MAIDRVR")
    assert spec is not None
    assert spec.pins[2].name == "ALERT"
    assert spec.pins[2].type == "output"


# ── name normalization ────────────────────────────────────────────────

def test_norm_equates_underscore_and_space():
    assert _norm("CLK Out") == _norm("CLK_OUT") == "clk_out"
    assert _norm("  NC ") == _norm("nc") == "nc"


# ── factory matches its pinspec ───────────────────────────────────────

def test_ldl112pv33r_factory_matches_pinspec():
    d = Design()
    c = add_ldl112pv33r(d, ref="U_T")
    spec = load_pinspec(c.manf_pn)
    assert compare(c, spec) == []


def test_ldl112pv18r_factory_matches_pinspec():
    d = Design()
    c = add_ldl112pv18r(d, ref="U_T")
    spec = load_pinspec(c.manf_pn)
    assert compare(c, spec) == []


def test_tmp117_factory_matches_pinspec():
    d = Design()
    c = add_tmp117maidrvr(d, ref="U_T")
    spec = load_pinspec(c.manf_pn)
    assert compare(c, spec) == []


def test_sit1630_factory_matches_pinspec():
    d = Design()
    c = add_sit1630ae_s6_dcc_32_768e(d, ref="U_T")
    spec = load_pinspec(c.manf_pn)
    assert compare(c, spec) == []


# ── compare() catches drift ───────────────────────────────────────────

def test_compare_flags_type_mismatch():
    """Synthesise a chip with a deliberately-wrong pin type."""
    d = Design()
    c = d.add_chip(
        ref="U_FAKE", manf_pn="LDL112PV33R",
        pins=[
            Pin(num="1", name="EN",   type="power"),    # WRONG: pinspec says input
            Pin(num="2", name="GND",  type="ground"),
            Pin(num="3", name="NC",   type="nc"),
            Pin(num="4", name="VOUT", type="power"),
            Pin(num="5", name="NC",   type="nc"),
            Pin(num="6", name="VIN",  type="power"),
            Pin(num="7", name="EP",   type="ground"),
        ],
    )
    spec = load_pinspec("LDL112PV33R")
    issues = compare(c, spec)
    type_issues = [r for r, _ in issues if r == "pinspec_type_mismatch"]
    assert len(type_issues) == 1


def test_compare_passes_when_name_in_aliases():
    """Lenient name check: pinspec's canonical name needs to appear in
    factory's name+alias set, not necessarily as primary."""
    d = Design()
    c = d.add_chip(
        ref="U_FAKE", manf_pn="LDL112PV33R",
        pins=[
            Pin(num="1", name="EN",   type="input"),
            Pin(num="2", name="GND",  type="ground"),
            Pin(num="3", name="ADJ",  aliases=["NC"], type="nc"),  # primary != pinspec but alias matches
            Pin(num="4", name="VOUT", type="power"),
            Pin(num="5", name="NC",   type="nc"),
            Pin(num="6", name="VIN",  type="power"),
            Pin(num="7", name="EP",   type="ground"),
        ],
    )
    spec = load_pinspec("LDL112PV33R")
    name_issues = [r for r, _ in compare(c, spec) if r == "pinspec_name_mismatch"]
    assert name_issues == []


def test_compare_flags_extra_pin():
    """Factory has a pin number not in the pinspec."""
    d = Design()
    c = d.add_chip(
        ref="U_FAKE", manf_pn="LDL112PV33R",
        pins=[
            Pin(num="1", name="EN",   type="input"),
            Pin(num="2", name="GND",  type="ground"),
            Pin(num="3", name="NC",   type="nc"),
            Pin(num="4", name="VOUT", type="power"),
            Pin(num="5", name="NC",   type="nc"),
            Pin(num="6", name="VIN",  type="power"),
            Pin(num="7", name="EP",   type="ground"),
            Pin(num="99", name="GHOST", type="input"),
        ],
    )
    spec = load_pinspec("LDL112PV33R")
    extra = [r for r, _ in compare(c, spec) if r == "pinspec_extra_pin"]
    assert len(extra) == 1


# ── design-level validator integration ────────────────────────────────

def test_design_validate_runs_pinspec_check():
    """Design.validate() should invoke _v_factory_matches_pinspec
    automatically. Build a chip with a wrong-type pin and confirm the
    issue surfaces."""
    d = Design()
    d.add_chip(
        ref="U_FAKE", manf_pn="LDL112PV33R",
        pins=[
            Pin(num="1", name="EN",   type="power"),    # wrong
            Pin(num="2", name="GND",  type="ground"),
            Pin(num="3", name="NC",   type="nc"),
            Pin(num="4", name="VOUT", type="power"),
            Pin(num="5", name="NC",   type="nc"),
            Pin(num="6", name="VIN",  type="power"),
            Pin(num="7", name="EP",   type="ground"),
        ],
    )
    issues = list(d.validate())
    pinspec_issues = [i for i in issues if i.rule.startswith("pinspec_")]
    assert any("type_mismatch" in i.rule for i in pinspec_issues)
