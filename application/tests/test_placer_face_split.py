"""Tests for the declarative face-split rule."""
from __future__ import annotations

import pytest

from smash.layout.placer.face_split import (
    goes_to_bottom,
    is_embeddable_passive,
    is_mating_pad,
    is_test_point,
)
from smash.state.chip import Chip
from smash.state.footprint import Footprint
from smash.state.pad import Pad


def _chip(ref: str, fp_name: str = "Generic:X", description: str = "") -> Chip:
    return Chip(
        ref=ref,
        manf_pn="X",
        description=description,
        footprint=Footprint(
            name=fp_name,
            pads=[Pad(num="1", position_mm=(0, 0), size_mm=(1, 1))],
        ),
    )


# ── is_mating_pad ────────────────────────────────────────────────────

@pytest.mark.parametrize("ref,expected", [
    ("P_CELLS",         True),
    ("P_NOSE",          True),
    ("J_NOSE_CAN_P",    False),    # J_ refs are the primary face, not the mate
    ("U_MPU",           False),
    ("R1",              False),
])
def test_is_mating_pad(ref, expected):
    assert is_mating_pad(_chip(ref)) is expected


# ── is_test_point ────────────────────────────────────────────────────

@pytest.mark.parametrize("fp_name,expected", [
    ("TestPoint:TestPoint_Pad_D1.5mm",      True),
    ("TestPoint:TestPoint_Pad_1.5x1.5mm",   True),
    ("TestPoint:TestPoint_Antenna",         True),
    ("Capacitor_SMD:C_0402_1005Metric",     False),
    ("Resistor_SMD:R_0603_1608Metric",      False),
])
def test_is_test_point(fp_name, expected):
    assert is_test_point(_chip("X1", fp_name=fp_name)) is expected


def test_is_test_point_no_footprint():
    """Chip without footprint can't be a test point."""
    c = Chip(ref="X1", manf_pn="x")
    assert is_test_point(c) is False


# ── is_embeddable_passive — by footprint prefix ──────────────────────

@pytest.mark.parametrize("fp_name,expected", [
    ("Resistor_SMD:R_0402_1005Metric",     True),
    ("Resistor_SMD:R_0603_1608Metric",     True),
    ("Resistor_SMD:R_0805_2012Metric",     False),   # not in list
    ("Inductor_SMD:L_0402_1005Metric",     True),
    ("Inductor_SMD:L_0805_2012Metric",     True),
    ("Inductor_SMD:L_0603_1608Metric",     False),   # not in list
    ("Inductor_SMD:L_2012_2.0x1.2mm",      False),
    ("Capacitor_SMD:C_0402_1005Metric",    True),
    ("Capacitor_SMD:C_0603_1608Metric",    True),
    ("Capacitor_SMD:C_0805_2012Metric",    True),
    ("Capacitor_SMD:C_1206_3216Metric",    True),
    ("Capacitor_Tantalum_SMD:CP_EIA-3528", False),   # tantalum: too tall
    ("SOIC127P600X175-8N",                 False),   # IC: top
    ("VFBGA-424",                          False),   # BGA: top
])
def test_is_embeddable_passive(fp_name, expected):
    assert is_embeddable_passive(_chip("X1", fp_name=fp_name)) is expected


def test_is_embeddable_passive_ecm_flag():
    """[DNP/ECM] in description forces embeddable even for non-matching
    footprints."""
    c = _chip("U1", fp_name="SOIC127P600X175-8N",
              description="something [DNP/ECM] something")
    assert is_embeddable_passive(c) is True


def test_is_embeddable_passive_no_footprint():
    c = Chip(ref="X", manf_pn="x")
    assert is_embeddable_passive(c) is False


# ── composite: goes_to_bottom ────────────────────────────────────────

def test_goes_to_bottom_mating_pad_wins():
    """Even with a non-passive footprint, P_* refs go to bottom."""
    c = _chip("P_CELLS", fp_name="LGA-module")
    assert goes_to_bottom(c) is True


def test_goes_to_bottom_ic_stays_top():
    c = _chip("U_MPU", fp_name="VFBGA-424")
    assert goes_to_bottom(c) is False


def test_goes_to_bottom_0402_resistor_goes_bottom():
    c = _chip("R1", fp_name="Resistor_SMD:R_0402_1005Metric")
    assert goes_to_bottom(c) is True


def test_goes_to_bottom_tantalum_stays_top():
    """Tantalum caps are EIA-3528 (~1.9 mm tall) — too thick for ECP
    embedding. They stay on the top face."""
    c = _chip("C_TANT1", fp_name="Capacitor_Tantalum_SMD:CP_EIA-3528")
    assert goes_to_bottom(c) is False


def test_goes_to_bottom_test_point_goes_bottom():
    c = _chip("TP_VBAT", fp_name="TestPoint:TestPoint_Pad_D1.5mm")
    assert goes_to_bottom(c) is True


# ── end-to-end: the orchestrator picks up the split ─────────────────

def test_orchestrator_packs_to_both_faces():
    """When the design has both top-face ICs and bottom-face passives,
    placements should land on the correct faces."""
    from smash.layout.placer.orchestrator import place_design
    from smash.state import Board, Design

    d = Design()
    board = Board("flight_board")

    # One IC (top) + a few passives (bottom). Use a ref that does NOT
    # appear in locked_placements.json — the orchestrator pulls locks
    # by ref, so a clash would land the chip as locked, not packed.
    d.add_chip(ref="U_FACE_TEST_IC", manf_pn="X",
               footprint=Footprint(name="SOIC127P600X175-8N",
                                   pads=[Pad("1", (0,0), (3,3))]),
               board_tag="flight_board")
    for i in range(5):
        d.add_chip(ref=f"R_FACE_TEST_{i}", manf_pn="R",
                   footprint=Footprint(
                       name="Resistor_SMD:R_0402_1005Metric",
                       pads=[Pad("1", (0,0), (0.6,0.7))]),
                   board_tag="flight_board")

    class _FakePanel:
        snake_chain = ["flight_board"]
        tiles = {"flight_board": (0, 0)}

    rep = place_design(d, _FakePanel(), {"flight_board": board})
    stats = rep.per_board[0]
    assert stats.n_packed_top    == 1
    assert stats.n_packed_bottom == 5
    # Verify the placement.face matches the split
    top_refs    = {p.item.ref for p in board.chip_placements if p.face == "top"}
    bottom_refs = {p.item.ref for p in board.chip_placements if p.face == "bottom"}
    assert top_refs    == {"U_FACE_TEST_IC"}
    assert bottom_refs == {f"R_FACE_TEST_{i}" for i in range(5)}


def test_twin_no_overflow_with_face_split():
    """The full 454-chip twin should fit when the face split is on.
    power_board (88) and flight_board (106) previously overflowed
    because every chip landed on top; with the split, the 0402/0603/
    test-point parts move to bottom."""
    import importlib, pathlib, sys
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_maximalist_system")
    finally:
        sys.path.pop(0)
    from smash.layout.boards.smash_evb_v1 import build_panel
    from smash.layout.placer import place_design

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

    panel, boards = build_panel()
    rep = place_design(d, panel, boards)

    failing = [s for s in rep.per_board if s.overflow]
    assert failing == [], (
        "twin overflowed even with face split:\n" +
        "\n".join(
            f"  {s.board_name}: top={s.n_packed_top}/{s.max_reach_top_mm:.1f}mm "
            f"bot={s.n_packed_bottom}/{s.max_reach_bot_mm:.1f}mm"
            for s in failing
        )
    )
