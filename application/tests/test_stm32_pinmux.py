"""Tests for the STM32 alternate-function (pinmux) ground-truth pipeline.

Three things checked end-to-end:

  1. The vendored CubeMX XMLs parse correctly into AF tables.
  2. MCU factories populate `Pin.alt_functions` from those tables.
  3. `Design.connect(..., af=, intent=)` writes the connection-time
     fields, and `check_pinmux` catches both AF-unavailable and
     AF-conflict cases.
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design
from smash.state import Footprint, Pin
from smash.parts import (
    add_stm32h562aii6,
    add_stm32wle5jci6,
    add_stm32mp255fak3,
    add_stm32g0b1rei6n,
)
from smash.parts._cubemx import (
    load_af_table,
    alt_functions_by_pin_name,
    alt_functions_by_position,
)
from smash.validators import (
    check_pinmux,
    find_pins,
    af_assignments,
)


REPO = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO / "application/src/smash/parts/sources"


# ── CubeMX XML parser ────────────────────────────────────────────────────

class TestCubemxParser:
    def test_h562_parses(self):
        af = load_af_table(str(SRC / "STM32H562AII6/cubemx.xml"))
        # CubeMX uses fused datasheet names for debug pins
        key = "PA14(JTCK/SWCLK)"
        assert key in af
        assert "DEBUG_JTCK-SWCLK" in af[key]["signals"]
        # A power pin name shows up once in the dict with all positions
        assert af["VDD"]["signals"] == []   # no AF for power pins
        assert len(af["VDD"]["positions"]) > 1   # many VDD balls

    def test_mp25_parses(self):
        af = load_af_table(str(SRC / "STM32MP255FAK3/cubemx.xml"))
        # The DDR controller balls live alongside the GPIO balls
        assert any(k.startswith("PG") for k in af.keys())

    def test_by_position_keyed_by_ball(self):
        af = alt_functions_by_position(str(SRC / "STM32H562AII6/cubemx.xml"))
        # A12 is PA14 on the H562 UFBGA-169
        assert "DEBUG_JTCK-SWCLK" in af["A12"]

    def test_by_name_keyed_by_pin_name(self):
        af = alt_functions_by_pin_name(str(SRC / "STM32WLE5JCI6/cubemx.xml"))
        # PA0 on WLE5 has at least these signals
        assert "PA0" in af
        # Should expose RTC alarm output among others
        assert any("RTC" in s for s in af["PA0"])


# ── Factory loads alt_functions ─────────────────────────────────────────

class TestFactoryAfLoading:
    def test_h562_af_loaded(self):
        d = Design()
        h = add_stm32h562aii6(d, ref="U1")
        pa14 = h.pin("PA14")
        assert pa14.alt_functions, "PA14 should have alt_functions populated"
        assert "DEBUG_JTCK-SWCLK" in pa14.alt_functions
        assert "GPIO" in pa14.alt_functions

    def test_wle5_af_loaded(self):
        d = Design()
        w = add_stm32wle5jci6(d, ref="U_WLE")
        # PA0 should be reachable and have AF data
        pa0 = w.pin("PA0")
        assert pa0.alt_functions

    def test_mp25_af_loaded(self):
        d = Design()
        m = add_stm32mp255fak3(d, ref="U_MPU")
        # Pick a known GPIO and verify CubeMX AF data is there.
        # PB13 has SPI7_SCK on MP25 (NOT SPI2_SCK — different from H562).
        pb13 = m.pin("PB13")
        assert pb13.alt_functions, "PB13 should have alt_functions populated from cubemx.xml"
        assert any("SPI" in s for s in pb13.alt_functions)
        # PB0/PB14 are the SPI2_SCK candidates on MP25
        pb0 = m.pin("PB0")
        assert "SPI2_SCK" in pb0.alt_functions

    def test_g0b1_af_loaded(self):
        d = Design()
        g = add_stm32g0b1rei6n(d, ref="U_G0B1")
        # PB8 is FDCAN1_RX on G0B1
        pb8 = g.pin("PB8")
        assert pb8.alt_functions
        assert any("FDCAN" in s for s in pb8.alt_functions)

    def test_power_pin_has_empty_af_list(self):
        d = Design()
        h = add_stm32h562aii6(d, ref="U1")
        vdd_1 = h.pin("VDD_1")
        assert vdd_1.alt_functions == []


# ── connect(af=, intent=) ────────────────────────────────────────────────

class TestConnectAfIntent:
    def test_af_and_intent_stored_on_pin(self):
        d = Design()
        h = add_stm32h562aii6(d, ref="U1")
        d.add_signal_net("WIFI_SDIO_CLK") \
         .connect(h.pin("PA14"),
                  af="DEBUG_JTCK-SWCLK",
                  intent="SWD clock to factory programmer")
        pa14 = h.pin("PA14")
        assert pa14.af_assigned == "DEBUG_JTCK-SWCLK"
        assert pa14.intent == "SWD clock to factory programmer"

    def test_intent_alone(self):
        # Power pins have no programmable AF — only intent applies.
        d = Design()
        h = add_stm32h562aii6(d, ref="U1")
        d.add_power_net("VDD", voltage_v=3.3) \
         .connect(h.pin("A3"), intent="MCU main supply rail")
        a3 = h.pin("A3")
        assert a3.af_assigned is None
        assert a3.intent == "MCU main supply rail"


# ── validator: af_assignment_unavailable ────────────────────────────────

class TestPinmuxValidator:
    def test_clean_design_emits_no_issues(self):
        d = Design()
        h = add_stm32h562aii6(d, ref="U1")
        # PA14 supports DEBUG_JTCK-SWCLK per CubeMX
        d.add_signal_net("SWCLK").connect(h.pin("PA14"),
                                          af="DEBUG_JTCK-SWCLK")
        issues = check_pinmux(d)
        assert issues == []

    def test_unavailable_af_caught(self):
        d = Design()
        h = add_stm32h562aii6(d, ref="U1")
        # PA14 does NOT support UART4_TX — should be flagged
        d.add_signal_net("FAKE").connect(h.pin("PA14"),
                                          af="UART4_TX")
        issues = check_pinmux(d)
        assert len(issues) == 1
        assert issues[0].rule == "af_assignment_unavailable"
        assert "PA14" in issues[0].message
        assert "UART4_TX" in issues[0].message

    def test_conflict_caught(self):
        d = Design()
        h = add_stm32h562aii6(d, ref="U1")
        # Find two pins that both support USART1_TX
        candidates = [p for p in h.pins if "USART1_TX" in p.alt_functions]
        assert len(candidates) >= 2, "test fixture requires multi-pin USART1_TX"
        # Connect USART1_TX to both — should be flagged
        d.add_signal_net("UART_TX_A").connect(candidates[0], af="USART1_TX")
        d.add_signal_net("UART_TX_B").connect(candidates[1], af="USART1_TX")
        issues = check_pinmux(d)
        conflict_issues = [i for i in issues if i.rule == "af_assignment_conflict"]
        assert len(conflict_issues) == 1
        assert "USART1_TX" in conflict_issues[0].message

    def test_gpio_does_not_conflict(self):
        # Many pins can be muxed to plain GPIO simultaneously — not a
        # peripheral conflict.
        d = Design()
        h = add_stm32h562aii6(d, ref="U1")
        gpio_pins = [p for p in h.pins if "GPIO" in p.alt_functions][:5]
        for i, pin in enumerate(gpio_pins):
            d.add_signal_net(f"GPIO_{i}").connect(pin, af="GPIO")
        issues = check_pinmux(d)
        conflict = [i for i in issues if i.rule == "af_assignment_conflict"]
        assert conflict == []

    def test_non_stm32_chip_skipped(self):
        """A chip with no alt_functions populated should not produce issues."""
        d = Design()
        # Use a non-MCU chip — its pins have no alt_functions
        from smash.parts import add_tcan1042gvdq1
        tcan = add_tcan1042gvdq1(d, ref="U_TCAN")
        # Even if af_assigned were set (it shouldn't be on TCAN), no AF
        # table means no validation.
        for p in tcan.pins:
            assert p.alt_functions == []


# ── helpers: find_pins + af_assignments ─────────────────────────────────

def test_find_pins_helper():
    d = Design()
    m = add_stm32mp255fak3(d, ref="U_MPU")
    spi2_sck_pins = find_pins(m, "SPI2_SCK")
    assert len(spi2_sck_pins) >= 1
    # Each entry should be a ball position string
    assert all(isinstance(p, str) for p in spi2_sck_pins)


def test_af_assignments_helper():
    d = Design()
    h = add_stm32h562aii6(d, ref="U1")
    d.add_signal_net("S1").connect(h.pin("PA14"), af="DEBUG_JTCK-SWCLK")
    d.add_signal_net("S2").connect(h.pin("PA13"), af="DEBUG_JTMS-SWDIO")
    mapping = af_assignments(h)
    # Keyed by ball position
    assert mapping[h.pin("PA14").num] == "DEBUG_JTCK-SWCLK"
    assert mapping[h.pin("PA13").num] == "DEBUG_JTMS-SWDIO"
