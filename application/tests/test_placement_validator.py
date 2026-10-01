"""Tests for smash.validators.placement.check_chip_overlaps."""
from __future__ import annotations

import pytest

from smash.state import Design, Footprint, Pad
from smash.state.topology.placement import Placement
from smash.validators.placement import (
    check_chip_overlaps,
    assert_no_locked_overlaps,
    LockedOverlapError,
)


def _chip(d, ref, board, pos, face="top", *, locked=False, manf="ACME"):
    fp = Footprint(name="SQ", pads=[Pad("1", (0, 0), (4, 4))],
                   courtyard=[(-2, -2), (2, -2), (2, 2), (-2, 2)])
    c = d.add_chip(ref=ref, manf_pn="X", manf=manf, footprint=fp,
                   board_tag=board)
    return Placement(position_mm=pos, rotation_deg=0, item=c, face=face,
                     locked=locked)


class _B:
    def __init__(self, name, placements):
        self.name = name
        self.chip_placements = placements


def test_detects_overlap():
    d = Design()
    a = _chip(d, "U_A", "b", (0.0, 0.0))
    b = _chip(d, "U_B", "b", (2.0, 0.0))   # 4mm courtyards, 2mm apart → overlap
    issues = check_chip_overlaps({"b": _B("b", [a, b])})
    assert len(issues) == 1
    assert {issues[0].ref_a, issues[0].ref_b} == {"U_A", "U_B"}


def test_touching_is_clean():
    d = Design()
    a = _chip(d, "U_A", "b", (0.0, 0.0))
    b = _chip(d, "U_B", "b", (4.0, 0.0))   # courtyards exactly abut → OK
    assert check_chip_overlaps({"b": _B("b", [a, b])}) == []


def test_different_faces_dont_collide():
    d = Design()
    a = _chip(d, "U_A", "b", (0.0, 0.0))
    b = _chip(d, "U_B", "b", (0.0, 0.0), face="bottom")
    assert check_chip_overlaps({"b": _B("b", [a, b])}) == []


def test_locked_overlap_raises():
    """A locked component overlapping another real part hard-fails — the
    placer can't move it. This is the companion bottom-decap-pile class."""
    d = Design()
    a = _chip(d, "C_A", "b", (0.0, 0.0), face="bottom", locked=True)
    b = _chip(d, "C_B", "b", (2.0, 0.0), face="bottom", locked=True)
    with pytest.raises(LockedOverlapError):
        assert_no_locked_overlaps({"b": _B("b", [a, b])})


def test_locked_vs_packed_overlap_raises():
    """One locked + one packed real part overlapping still hard-fails."""
    d = Design()
    a = _chip(d, "C_A", "b", (0.0, 0.0), locked=True)
    b = _chip(d, "C_B", "b", (2.0, 0.0), locked=False)
    with pytest.raises(LockedOverlapError):
        assert_no_locked_overlaps({"b": _B("b", [a, b])})


def test_packed_only_overlap_is_warning_not_error():
    """Two packed (unlocked) parts overlapping is returned, not raised —
    the packer near-miss is a soft signal."""
    d = Design()
    a = _chip(d, "C_A", "b", (0.0, 0.0))
    b = _chip(d, "C_B", "b", (2.0, 0.0))
    issues = assert_no_locked_overlaps({"b": _B("b", [a, b])})
    assert len(issues) == 1 and not issues[0].involves_locked


def test_locked_pseudo_overlap_is_ignored():
    """`manf=='project'` pseudo-parts (spacer scaffold, LGA land arrays)
    coincide by design — a locked overlap between them must NOT fail."""
    d = Design()
    a = _chip(d, "SP", "b", (0.0, 0.0), locked=True, manf="project")
    b = _chip(d, "J_LANDS", "b", (2.0, 0.0), locked=True, manf="project")
    assert assert_no_locked_overlaps({"b": _B("b", [a, b])}) == []


def test_twin_panel_has_no_overlaps():
    """The shipping twin must place every chip (locked + packed) without
    a single courtyard overlap."""
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
               gen.build_fins_module,
               gen.build_companion_compute,
               gen.build_power_board, gen.build_wakeup_board]:   # wakeup folds in IMU/mag
        fn(d)
    panel, boards = build_panel()
    gen.build_spacers(d, boards)
    place_design(d, panel, boards)

    issues = check_chip_overlaps(boards)
    assert issues == [], "\n".join(str(i) for i in issues)
