"""Tests for smash.layout.locked — locked_placements.json loader."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from smash.layout.locked import (
    LockedPlacement,
    load_locked_placements,
    _parse_entry,
)


# ── happy-path: the real shipping data file ────────────────────────────

def test_load_returns_dict_keyed_by_ref():
    locked = load_locked_placements()
    assert isinstance(locked, dict)
    assert all(isinstance(k, str) for k in locked)
    assert all(isinstance(v, LockedPlacement) for v in locked.values())


def test_load_skips_meta_block():
    locked = load_locked_placements()
    assert "_meta" not in locked


def test_real_data_has_mpu_and_ddr4_anchors():
    """The two anchors the user called out explicitly."""
    locked = load_locked_placements()
    assert "U_MPU" in locked
    assert "U_DDR4" in locked


def test_u_ddr4_rotation_is_zero():
    """DDR (now DDR4 KTDM4G4B626BGIEAT) un-rotated at 0°: the STM32MP2
    DDR4 reference places the DRAM un-rotated east of the MPU. Was 270°
    for the DDR3L AN5724 reference before the DDR4 swap."""
    locked = load_locked_placements()
    assert locked["U_DDR4"].rotation_deg == 0.0


def test_u_mpu_west_of_ddr4_no_overlap():
    """MPU west of DDR4, side-by-side, courtyards clear. MPU is the
    VFBGA-361 (10 mm body, courtyard half-width 6.0); DDR4 is the
    FBGA-96 (7.5×13, courtyard half-width 4.8) → centres must be ≥
    10.8 mm apart so the courtyards don't overlap. They sit 13.5 mm
    apart in X (both moved 2 mm south for top-face SPI-NAND room)."""
    locked = load_locked_placements()
    mpu_x = locked["U_MPU"].position_mm[0]
    ddr_x = locked["U_DDR4"].position_mm[0]
    assert mpu_x < 0 < ddr_x
    assert ddr_x - mpu_x >= 10.8


def test_real_data_has_all_anchors():
    """Migration from CENTRE_ANCHOR_REFS. P_AFT_LGA was dropped when
    activation_interface became flex-connected (no more rigid-mate LGA
    harness). U1 (H562) was un-locked once the packer learned the flex-
    chord keep-region. U_WLE and U_WIFI were un-locked after audit (the
    cluster anchors had stale justifications; the packer's edge/meridian
    cost model places them sensibly without the lock). U_FLASH (the H562's
    QSPI NOR) was dropped entirely when flight control consolidated onto
    the MP25 Cortex-M33."""
    locked = load_locked_placements()
    expected = {"U_PMIC", "U_MPU", "U_DDR4", "P_CELL_CONTACTS"}
    assert expected <= set(locked)
    for ref in ("P_AFT_LGA", "U1", "U_WLE", "U_WIFI", "U_FLASH"):
        assert ref not in locked, f"{ref} should not be locked anymore"


def test_all_entries_have_reason():
    """Every locked placement must explain itself — no silent anchors."""
    locked = load_locked_placements()
    for ref, lp in locked.items():
        assert lp.reason, f"{ref}: missing reason"
        assert len(lp.reason) > 10, f"{ref}: reason too short"


# ── entry parsing ─────────────────────────────────────────────────────

def test_parse_entry_minimal():
    lp = _parse_entry("U_X", {"position_mm": [1.0, 2.0]})
    assert lp.position_mm == (1.0, 2.0)
    assert lp.rotation_deg == 0.0
    assert lp.face == "top"
    assert lp.reason is None


def test_parse_entry_full():
    lp = _parse_entry("U_X", {
        "position_mm": [3.5, -1.2],
        "rotation_deg": 90,
        "face": "bottom",
        "reason": "because reasons",
    })
    assert lp.position_mm == (3.5, -1.2)
    assert lp.rotation_deg == 90.0
    assert lp.face == "bottom"
    assert lp.reason == "because reasons"


def test_parse_entry_rejects_missing_position():
    with pytest.raises(ValueError, match="position_mm"):
        _parse_entry("U_X", {})


def test_parse_entry_rejects_bad_position_shape():
    with pytest.raises(ValueError, match="position_mm"):
        _parse_entry("U_X", {"position_mm": [1.0]})
    with pytest.raises(ValueError, match="position_mm"):
        _parse_entry("U_X", {"position_mm": "foo"})


def test_parse_entry_rejects_bad_rotation():
    with pytest.raises(ValueError, match="rotation_deg"):
        _parse_entry("U_X", {"position_mm": [0, 0], "rotation_deg": "nope"})


def test_parse_entry_rejects_bad_face():
    with pytest.raises(ValueError, match="face"):
        _parse_entry("U_X", {"position_mm": [0, 0], "face": "side"})


def test_parse_entry_accepts_int_coords():
    lp = _parse_entry("U_X", {"position_mm": [0, 0]})
    assert lp.position_mm == (0.0, 0.0)
    assert isinstance(lp.position_mm[0], float)
