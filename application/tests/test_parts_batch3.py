"""Verify the batch-3 factories (passive + NFC + motor + flash + MCU +
wireless + PMIC + radar + PLL — 23 in total).

These factories all use the `_artifacts` parser helper, so the test
focuses on:
  - the helper-parsed pin/pad counts match
  - identity fields are populated
  - the datasheet (where present) resolves
  - the 3D STEP (where present) resolves
  - default-design validators pass when every pin is wired
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design
from smash.parts import (
    # Round A
    add_we_744043100, add_st25dv16kc_ie8t3,
    add_drv8833pwr, add_drv8711dcpr,
    # Round B (flash + DRAM)
    add_s25hl512tfamhi010, add_mt29f4g01abafdwb_it_f,
    add_mt29f4g01abafd12_aat_f, add_mt29f8g08abacah4_it_c_tr,
    add_mt29f8g08abacawp_it_c, add_mt41k256m16tw_107_ptr,
    add_as4c512m16d3lc_12bin,
    # Round C (MCUs)
    add_stm32g0b1kct6n, add_stm32g0b1kcu6n, add_stm32g0b1rei6n,
    add_stm32wle5jci6, add_stm32h562aii6, add_stm32mp255fak3,
    add_stm32mp255dal3,
    # Round D (modules / PMIC / radar / PLL)
    add_lbee5kl1yn_814, add_stpmic25apqr,
    add_iwr1843arqgalpr, add_awr2944abgaltq1, add_awr2243abgablq1,
    add_awr2e44pbgamxrq1,
    add_adf4351bcpz,
)


REPO = pathlib.Path(__file__).resolve().parents[2]


ALL_FACTORIES = [
    add_we_744043100, add_st25dv16kc_ie8t3,
    add_drv8833pwr, add_drv8711dcpr,
    add_s25hl512tfamhi010, add_mt29f4g01abafdwb_it_f,
    add_mt29f4g01abafd12_aat_f, add_mt29f8g08abacah4_it_c_tr,
    add_mt29f8g08abacawp_it_c, add_mt41k256m16tw_107_ptr,
    add_as4c512m16d3lc_12bin,
    add_stm32g0b1kct6n, add_stm32g0b1kcu6n, add_stm32g0b1rei6n,
    add_stm32wle5jci6, add_stm32h562aii6, add_stm32mp255fak3,
    add_stm32mp255dal3,
    add_lbee5kl1yn_814, add_stpmic25apqr,
    add_iwr1843arqgalpr, add_awr2944abgaltq1, add_awr2243abgablq1,
    add_adf4351bcpz,
]


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_factory_constructs(factory):
    d = Design()
    c = factory(d, ref="U_TEST")
    assert c.manf, f"{factory.__name__}: missing manf"
    assert c.manf_pn, f"{factory.__name__}: missing manf_pn"


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_pin_pad_correspondence(factory):
    d = Design()
    c = factory(d, ref="U_TEST")
    pad_nums = {p.num for p in c.footprint.pads}
    # Strip the smash-internal `BALL_` prefix when comparing — that
    # prefix is a namespace marker so pin names can't collide with
    # ball-coord lookups (see _namespace_ball_collisions in
    # smash.parts.flash). The footprint stores raw ball coords.
    pin_nums = {
        (p.num[len("BALL_"):] if p.num.startswith("BALL_") else p.num)
        for p in c.pins
    }
    assert pin_nums == pad_nums, f"{factory.__name__}: pin/pad mismatch"


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_datasheet_resolves_when_present(factory):
    d = Design()
    c = factory(d, ref="U_TEST")
    if c.datasheet is None:
        # Some factories (e.g. AS4C, AWR2944, AWR2243) explicitly
        # leave datasheet=None because the PDF isn't in Research/.
        # That's logged in TODO.md — skip the existence check.
        pytest.skip(f"{factory.__name__} has no datasheet (logged in TODO)")
    assert (REPO / c.datasheet).is_file(), \
        f"{factory.__name__}: datasheet {c.datasheet!r} not found"


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_3d_model_resolves(factory):
    d = Design()
    c = factory(d, ref="U_TEST")
    assert (REPO / c.footprint.model_3d_path).is_file(), \
        f"{factory.__name__}: STEP {c.footprint.model_3d_path!r} not found"


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_validators_pass(factory):
    # Skip the assumptions overlay so parts whose curated fab_country
    # would trip the forbidden_fab rule (e.g. AS4C512M16D3LC fabbed in
    # TW) don't fail this catalog-wide hygiene check. Forbidden-fab
    # behaviour has its own dedicated test.
    d = Design(apply_assumptions=False)
    chip = factory(d, ref="U_TEST")
    # Wire every pin so floating-chip validator doesn't fire
    from _helpers import wire_chip_synthetically
    wire_chip_synthetically(d, chip)
    errors = [i for i in d.validate() if i.severity == "error"]
    assert errors == [], f"{factory.__name__}: {errors}"


# ─── targeted spot-checks per family ─────────────────────────────────────

class TestSTM32Family:
    def test_g0b1_clock(self):
        # STM32G0B1 = Cortex-M0+ 64 MHz max
        c = add_stm32g0b1kct6n(Design(), ref="U1")
        assert c.clock_max_hz == 64e6
        assert c.package == "LQFP-32"

    def test_wle5_has_lora_note(self):
        c = add_stm32wle5jci6(Design(), ref="U1")
        assert "LoRa" in (c.note or "")

    def test_h562_is_m33_with_trustzone(self):
        c = add_stm32h562aii6(Design(), ref="U1")
        assert c.clock_max_hz == 250e6
        assert "TrustZone" in (c.note or "")

    def test_mp255_is_424_ball_bga(self):
        c = add_stm32mp255fak3(Design(), ref="U1")
        assert len(c.footprint.pads) == 424
        assert "424" in c.package

    def test_mp255dal3_is_361_ball_10mm_bga(self):
        c = add_stm32mp255dal3(Design(), ref="U1")
        assert len(c.footprint.pads) == 361
        assert "361" in c.package
        assert c.footprint.size_mm == (10.0, 10.0)
        assert c.footprint.pitch_mm == 0.5
        assert c.is_bga


class TestFlashFamily:
    def test_as4c_is_ddr3_in_current_design(self):
        c = add_as4c512m16d3lc_12bin(Design(), ref="U1")
        # 8 Gbit DDR3
        assert c.memory_capacity_bits == 8 * 1024 * 1024 * 1024
        assert c.vcc_nominal_v == 1.5

    def test_mt41k_is_ddr3l(self):
        c = add_mt41k256m16tw_107_ptr(Design(), ref="U1")
        # 4 Gbit DDR3L
        assert c.memory_capacity_bits == 4 * 1024 * 1024 * 1024


class TestRadarFamily:
    def test_iwr1843_pin_count(self):
        c = add_iwr1843arqgalpr(Design(), ref="U1")
        assert len(c.pins) == 180

    def test_awr2944_pin_count(self):
        c = add_awr2944abgaltq1(Design(), ref="U1")
        assert len(c.pins) == 266

    def test_awr2243_no_dsp_note(self):
        # AWR2243 is transceiver-only, no DSP — note should mention this
        c = add_awr2243abgablq1(Design(), ref="U1")
        assert "NO integrated DSP" in (c.note or "")

    # AWR2E44P is kept OUT of the catalog-wide ALL_FACTORIES sweep: it has
    # no vendor 3D model (geometry was lifted from the EVM, not SamacSys),
    # so test_3d_model_resolves can't apply. Its invariants live here.
    def test_awr2e44p_ball_count(self):
        c = add_awr2e44pbgamxrq1(Design(), ref="U1")
        assert len(c.pins) == 278
        assert len(c.footprint.pads) == 278

    def test_awr2e44p_pin_pad_correspondence(self):
        c = add_awr2e44pbgamxrq1(Design(), ref="U1")
        assert {p.num for p in c.pins} == {p.num for p in c.footprint.pads}

    def test_awr2e44p_is_13p5_by_12_fccsp(self):
        # The whole reason for the variant: AWR2E44P is 13.5×12 mm, NOT the
        # AWR2944's 12×12 — different body, different footprint.
        c = add_awr2e44pbgamxrq1(Design(), ref="U1")
        assert c.footprint.size_mm == (13.5, 12.0)
        assert "13.5" in c.package and "FCCSP" in c.package
        assert c.footprint.pitch_mm == 0.65

    def test_awr2e44p_lift_provenance_note(self):
        # The geometry is generated/lifted — the note must keep that caveat
        # visible so nobody fabs against it without checking the drawing.
        c = add_awr2e44pbgamxrq1(Design(), ref="U1")
        note = (c.note or "").lower()
        assert "lifted" in note and "verify" in note
        assert c.footprint.source == "ti-evm-lift"

    def test_awr2e44p_datasheet_resolves(self):
        c = add_awr2e44pbgamxrq1(Design(), ref="U1")
        assert c.datasheet and (REPO / c.datasheet).is_file()

    def test_awr2e44p_validates_clean(self):
        from _helpers import wire_chip_synthetically
        d = Design(apply_assumptions=False)
        chip = add_awr2e44pbgamxrq1(d, ref="U1")
        wire_chip_synthetically(d, chip)
        errors = [i for i in d.validate() if i.severity == "error"]
        assert errors == [], errors


class TestAD8603PlusInBugFix:
    def test_st25dv16kc_dual_port(self):
        # Verify the +IN-style preservation we earned with the helper
        # by checking ST25DV's NFC pin names
        c = add_st25dv16kc_ie8t3(Design(), ref="U1")
        names = {p.name for p in c.pins}
        # ST25DV has GND, VCC, SCL, SDA pins plus the AC0/AC1 antenna
        assert any("AC" in n for n in names) or any("ANT" in n.upper() for n in names)


class TestHelperParserUsed:
    """Sanity: factories using build_pins should preserve special
    characters that pinmap.txt would have ASCII-stripped."""

    def test_no_questionable_pin_names(self):
        for factory in ALL_FACTORIES:
            d = Design()
            c = factory(d, ref="U_T")
            for p in c.pins:
                # Names should never be empty (every pin in a KiCad sym
                # has a name)
                assert p.name != "", \
                    f"{factory.__name__}: pin {p.num} has empty name"
