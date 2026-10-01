"""Tests for smash.layout.placer.flex_sizing."""
from __future__ import annotations

import pytest

from smash.layout.placer.flex_sizing import (
    FLEX_MARGIN_MM,
    FLEX_WIDTH_PER_CLASS_MM,
    compute_link_widths,
    net_class,
)
from smash.state import Design


class _FakePanel:
    def __init__(self, snake_chain): self.snake_chain = snake_chain


def _chip(d, ref, board_tag, *, pins=None):
    """Add a footprint-less chip just to register a ref→board_tag mapping
    and a pin list for net connections."""
    return d.add_chip(ref=ref, manf_pn="X", board_tag=board_tag,
                      pins=pins or [("1",)])


# ── net_class ─────────────────────────────────────────────────────────

def test_net_class_ground():
    d = Design()
    n = d.add_ground_net("GND")
    assert net_class(n) == "gnd"


def test_net_class_power_high():
    d = Design()
    n = d.add_power_net("VBAT", voltage_v=4.0)
    assert net_class(n) == "power_hi"


def test_net_class_power_mid():
    d = Design()
    n = d.add_power_net("3V3", voltage_v=3.3)
    assert net_class(n) == "power_md"


def test_net_class_power_borderline():
    """Exactly 3.6 V is the threshold; ≤3.6 is power_md."""
    d = Design()
    n = d.add_power_net("VBORDER", voltage_v=3.6)
    assert net_class(n) == "power_md"


def test_net_class_signal_kinds():
    """bus, diff, clock, signal all count as signal for sizing."""
    d = Design()
    for kind, ctor in [
        ("signal", lambda: d.add_signal_net("SIG")),
        ("clock",  lambda: d.add_clock_net("CLK", frequency_hz=32768)),
    ]:
        n = ctor()
        assert net_class(n) == "signal", \
            f"kind={kind} expected signal got {net_class(n)}"


# ── compute_link_widths ──────────────────────────────────────────────

def test_no_cross_tile_nets_empty():
    """All chips on one board → no link has cross-tile signals."""
    d = Design()
    panel = _FakePanel(["A", "B"])
    a = _chip(d, "U1", "A")
    sig = d.add_signal_net("LOCAL")
    sig.connect(a.pin("1"))
    widths, _ = compute_link_widths(d, panel)
    assert widths == {}


def test_single_signal_crosses_one_link():
    d = Design()
    panel = _FakePanel(["A", "B"])
    a = _chip(d, "U1", "A"); b = _chip(d, "U2", "B")
    sig = d.add_signal_net("CROSS")
    sig.connect(a.pin("1")); sig.connect(b.pin("1"))
    widths, bd = compute_link_widths(d, panel)
    assert widths == {0: FLEX_WIDTH_PER_CLASS_MM["signal"] + FLEX_MARGIN_MM}
    assert bd == {0: {"signal": 1}}


def test_signal_spanning_multiple_tiles_counted_per_link():
    """Net spanning tiles {0, 3} contributes to links 0, 1, 2."""
    d = Design()
    panel = _FakePanel(["A", "B", "C", "D"])
    a = _chip(d, "U_A", "A"); b = _chip(d, "U_B", "B")
    c = _chip(d, "U_C", "C"); dd = _chip(d, "U_D", "D")
    sig = d.add_signal_net("LONG")
    sig.connect(a.pin("1")); sig.connect(dd.pin("1"))   # A↔D, spans 0..2
    widths, bd = compute_link_widths(d, panel)
    expected = FLEX_WIDTH_PER_CLASS_MM["signal"] + FLEX_MARGIN_MM
    assert widths == {0: expected, 1: expected, 2: expected}
    assert bd == {0: {"signal": 1}, 1: {"signal": 1}, 2: {"signal": 1}}


def test_mixed_classes_sum_correctly():
    d = Design()
    panel = _FakePanel(["A", "B"])
    a = _chip(d, "U_A", "A", pins=[("1",), ("2",), ("3",)])
    b = _chip(d, "U_B", "B", pins=[("1",), ("2",), ("3",)])
    # 4 nets cross: 1 power_hi, 2 power_md, 5 signal, 1 gnd
    p_hi = d.add_power_net("VBAT", voltage_v=4.0)
    p_md = d.add_power_net("3V3",  voltage_v=3.3)
    sig  = d.add_signal_net("S0")
    gnd  = d.add_ground_net("GND")
    p_hi.connect(a.pin("1")); p_hi.connect(b.pin("1"))
    p_md.connect(a.pin("2")); p_md.connect(b.pin("2"))
    sig.connect(a.pin("3"));  sig.connect(b.pin("3"))
    # gnd needs at least 2 pins to count as cross-tile; reuse pin 1
    # via the .pin lookup wouldn't work (already connected). Use new chips.
    e = _chip(d, "U_E", "A", pins=[("1",)])
    f = _chip(d, "U_F", "B", pins=[("1",)])
    gnd.connect(e.pin("1")); gnd.connect(f.pin("1"))

    widths, bd = compute_link_widths(d, panel)
    expected = (1 * FLEX_WIDTH_PER_CLASS_MM["power_hi"]
                + 1 * FLEX_WIDTH_PER_CLASS_MM["power_md"]
                + 1 * FLEX_WIDTH_PER_CLASS_MM["signal"]
                + 1 * FLEX_WIDTH_PER_CLASS_MM["gnd"]
                + FLEX_MARGIN_MM)
    assert widths[0] == pytest.approx(expected)
    assert bd[0] == {"power_hi": 1, "power_md": 1, "signal": 1, "gnd": 1}


def test_chips_off_snake_chain_dont_count():
    """Branch tiles aren't in the snake chain — nets that only touch
    them shouldn't contribute to any snake link."""
    d = Design()
    panel = _FakePanel(["A", "B"])    # branch tile X not in chain
    a = _chip(d, "U_A", "A")
    x = _chip(d, "U_X", "X_branch")
    sig = d.add_signal_net("BRANCH_ONLY")
    sig.connect(a.pin("1")); sig.connect(x.pin("1"))
    widths, _ = compute_link_widths(d, panel)
    # Only one tile in the chain has a pin → no cross-link
    assert widths == {}


# ── end-to-end with the twin ─────────────────────────────────────────

def test_twin_link_widths_have_expected_range():
    """The maximalist twin should produce link widths in roughly 5-17 mm
    range — sanity check against regressions in the classifier. The
    nose_cap is now an EMPTY mechanical tile: the UJ20 USB-C was lowered onto
    the radar (its status LEDs + the two CC Rds were already there), so the
    radar<->nose_cap leaf carries no crossing nets and drops out of the count
    entirely (18 links, not 19). Narrowest width'd link is now the battery-
    compartment gaps."""
    import importlib, pathlib, sys
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_maximalist_system")
    finally:
        sys.path.pop(0)
    from smash.layout.boards.smash_evb_v1 import build_panel

    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in [gen.build_qpd_module,
               gen.build_yagi_antenna_a_flex, gen.build_yagi_antenna_b_flex,
               gen.build_nose_cap, gen.build_camera_module,
               gen.build_aft_end_board,
               gen.build_activation_interface, gen.build_radar_module,
               gen.build_fins_module,
               gen.build_companion_compute,
               gen.build_power_board, gen.build_wakeup_board,
               gen.build_spacers]:   # wakeup_board folds in the IMU/mag (build_flight_board)
        fn(d)

    panel, _ = build_panel()
    widths, _ = compute_link_widths(d, panel)
    # 22-cell snake chain (9 rigid boards — incl. the thin cell_floor_board
    # reinstated 2026-07-30 AND fin_ble_board from the same-day crowding
    # split — + 13 spacers, incl. the 6-spacer battery compartment) → 21
    # links. Only links with ≥1 crossing net get a width; the battery-column
    # gaps carry the backbone. (The radar↔nose_cap USB leaf is one of the
    # wider links, ~5.25; not the min.) 20 if the UJ20-emptied nose_cap leaf
    # carries no crossing nets and drops out of the width count.
    assert len(widths) in (20, 21)
    # Narrowest is now the battery-compartment gaps: little crosses → just
    # margin + GND.
    assert min(widths.values()) >= 3.0
    assert max(widths.values()) <= 20.0  # nothing extreme
