"""Tests for the BAT64-06-TP, DRV5023AJQLPG, SFH203FA factories."""

from __future__ import annotations

import pathlib

import pytest

from smash import Design
from smash.parts import (
    add_bat64_06_tp, add_drv5023ajqlpg, add_sfh203fa,
    add_ar0234cssm00suka0_cp, add_mx60lf8g28ad_xki_t,
)


REPO = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO / "application/src/smash/parts/sources"

ALL_FACTORIES = [
    add_bat64_06_tp, add_drv5023ajqlpg, add_sfh203fa,
    add_ar0234cssm00suka0_cp, add_mx60lf8g28ad_xki_t,
]


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_constructs(factory):
    d = Design()
    c = factory(d, ref="U_T")
    assert c.manf and c.manf_pn


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_pin_pad(factory):
    d = Design()
    c = factory(d, ref="U_T")
    assert {p.num for p in c.pins} == {p.num for p in c.footprint.pads}


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_datasheet_resolves(factory):
    d = Design()
    c = factory(d, ref="U_T")
    assert (REPO / c.datasheet).is_file()


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_validates(factory):
    # Skip the assumptions overlay so parts whose curated fab_country
    # trips forbidden_fab (e.g. AR0234 fabbed in IT/CN) don't fail this
    # catalog-wide hygiene check. Sourcing-rule behaviour is asserted
    # by its own dedicated test.
    d = Design(apply_assumptions=False)
    c = factory(d, ref="U_T")
    from _helpers import wire_chip_synthetically
    wire_chip_synthetically(d, c)
    errors = [i for i in d.validate() if i.severity == "error"]
    assert errors == []


def test_bat64_common_anode():
    # Datasheet schematic + KiCad sym: pin 3 is the common anode,
    # pins 1 and 2 are separate cathodes.
    c = add_bat64_06_tp(Design(), ref="D1")
    by_name = {p.name: p for p in c.pins}
    assert "COM_A" in by_name or any("A" in n and "COM" in n for n in by_name)
    # Two cathode pins
    cathodes = [p for p in c.pins if "K" in p.name]
    assert len(cathodes) == 2

def test_drv5023_threshold_aliases():
    c = add_drv5023ajqlpg(Design(), ref="U1")
    # AJQ = AEC-Q100 grade 0
    assert "AEC-Q100 Grade 0" in c.standards
    # AJQLPG = SOT-23
    assert "SOT-23" in c.package

def test_sfh203_ir_filter():
    c = add_sfh203fa(Design(), ref="D1")
    # FA suffix = IR-blocking daylight filter
    assert "IR-filter" in c.package or "IR" in c.description


def test_sfh203_no_3d_model():
    # The SamacSys archive for SFH203FA doesn't include a STEP file
    c = add_sfh203fa(Design(), ref="D1")
    assert c.footprint.model_3d_path is None


# ── AR0234 (datasheet-derived pin map, project-built footprint) ─────────

class TestAR0234:
    def test_83_pins(self):
        c = add_ar0234cssm00suka0_cp(Design(), ref="U1")
        assert len(c.pins) == 83

    def test_power_rails_have_multiple_balls(self):
        c = add_ar0234cssm00suka0_cp(Design(), ref="U1")
        # Per datasheet Table 3
        assert len([p for p in c.pins if p.name == "VDD"]) == 7
        assert len([p for p in c.pins if p.name == "VAA"]) == 4
        assert len([p for p in c.pins if p.name == "DGND"]) == 13
        assert len([p for p in c.pins if p.name == "VDD_IO"]) == 8

    def test_specific_ball_assignments(self):
        c = add_ar0234cssm00suka0_cp(Design(), ref="U1")
        # MIPI clock differential at D11/D12
        assert c.pin("D11").name == "CLK_P"
        assert c.pin("D12").name == "CLK_N"
        # Reset on F7
        assert c.pin("F7").name == "RESET_BAR"
        # Two-wire serial at F6/E6
        assert c.pin("F6").name == "SCLK"
        assert c.pin("E6").name == "SDATA"

    def test_reserved_pins_have_note(self):
        c = add_ar0234cssm00suka0_cp(Design(), ref="U1")
        for ball in ("A11", "B9"):
            p = c.pin(ball)
            assert p.name == "Reserved"
            assert "do not connect" in (p.note or "").lower()

    def test_voltage_domain_grouping(self):
        c = add_ar0234cssm00suka0_cp(Design(), ref="U1")
        # VAA and VAA_PIX share the 2.8 V domain
        vaa_domain = {p.voltage_domain for p in c.pins
                       if p.name in ("VAA", "VAA_PIX", "VAA_PHY")}
        assert vaa_domain == {"VAA"}


# ── MX60LF (datasheet-derived pin map, REUSED ONFI footprint) ──────────

class TestMX60LF:
    def test_63_balls(self):
        c = add_mx60lf8g28ad_xki_t(Design(), ref="U1")
        assert len(c.pins) == 63

    def test_io_pins_per_onfi(self):
        c = add_mx60lf8g28ad_xki_t(Design(), ref="U1")
        # Per MX60LF datasheet ball diagram
        # I/O0=H4, I/O1=J4, I/O2=K4, I/O3=K5, I/O4=K6,
        # I/O5=J7, I/O6=K7, I/O7=J8
        for ball, expected in [
            ("H4", "I/O0"), ("J4", "I/O1"), ("K4", "I/O2"), ("K5", "I/O3"),
            ("K6", "I/O4"), ("J7", "I/O5"), ("K7", "I/O6"), ("J8", "I/O7"),
        ]:
            assert c.pin(ball).name == expected

    def test_control_signals_are_active_low(self):
        c = add_mx60lf8g28ad_xki_t(Design(), ref="U1")
        # WE#, CE#, RE#, WP#, R/B# all have KiCad bar-notation '\#'
        for ball, base in [("C3", "WP"), ("C6", "CE"),
                           ("C7", "WE"), ("D4", "RE"), ("C8", "R/B")]:
            p = c.pin(ball)
            assert "\\#" in p.name, f"{ball}: {p.name!r} missing bar"
            # Alias should also work
            assert c.pin(f"{base}#").num == ball

    def test_footprint_reused_from_micron(self):
        # The footprint name + source string should reflect the
        # JEDEC/ONFI reuse from Micron
        c = add_mx60lf8g28ad_xki_t(Design(), ref="U1")
        assert "BGA63" in c.footprint.name
        assert "Micron" in (c.footprint.source or "")

    def test_outer_balls_are_nc(self):
        c = add_mx60lf8g28ad_xki_t(Design(), ref="U1")
        # All A/B/L/M corner balls except the rest are NC
        for ball in ["A1", "A10", "B1", "B10", "L1", "M10"]:
            p = c.pin(ball)
            assert p.name == "NC"
            assert p.type == "nc"
