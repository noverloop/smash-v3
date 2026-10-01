"""Tests for smash.layout.placer.spacer_sizing — dynamic backbone-spacer height.

A spacer must clear the SUM of the lower-tile top-face chip height and the
upper-tile bottom-face chip height where they overlap in XY (opposing parts
share the gap), else just the tallest single chip — plus clearance, rounded up
to 0.1 mm and floored at a practical minimum.
"""
from __future__ import annotations

from types import SimpleNamespace

from smash.state import Footprint, Pad
from smash.state.topology.placement import Placement
from smash.layout.placer.spacer_sizing import (
    SPACER_CLEARANCE_MM,
    SPACER_MIN_THICKNESS_MM,
    gap_required_thickness,
)


def _fp(height_mm, side=1.0):
    return Footprint(
        name="TESTPART",
        pads=[Pad(num="1", position_mm=(0.0, 0.0), size_mm=(side, side),
                  shape="rect", layer="F.Cu")],
        height_mm=height_mm,
    )


def _placement(ref, height_mm, xy, face):
    chip = SimpleNamespace(ref=ref, footprint=_fp(height_mm))
    return Placement(position_mm=xy, rotation_deg=0, face=face, item=chip)


def _board(*placements):
    return SimpleNamespace(chip_placements=list(placements))


def test_overlapping_opposing_chips_add():
    # top chip 1.4 over bottom chip 1.8 at the same XY → 3.2 + 0.3 = 3.5
    lower = _board(_placement("U_A", 1.4, (0.0, 0.0), "top"))
    upper = _board(_placement("U_B", 1.8, (0.0, 0.0), "bottom"))
    assert gap_required_thickness(lower, upper) == 3.5


def test_non_overlapping_uses_max_not_sum():
    # far apart → no coincidence → just the tallest single + clearance
    lower = _board(_placement("U_A", 1.4, (0.0, 0.0), "top"))
    upper = _board(_placement("U_B", 1.8, (10.0, 10.0), "bottom"))
    assert gap_required_thickness(lower, upper) == 2.1   # 1.8 + 0.3


def test_floored_at_minimum():
    lower = _board(_placement("U_A", 0.4, (0.0, 0.0), "top"))
    upper = _board()
    # 0.4 + 0.3 = 0.7 → floored
    assert gap_required_thickness(lower, upper) == SPACER_MIN_THICKNESS_MM


def test_flat_lands_excluded():
    # J_/P_/TP_/SP* are flat — they don't drive the gap
    lower = _board(_placement("J_lands_top", 0.5, (0.0, 0.0), "top"),
                   _placement("SP1", 0.5, (0.0, 0.0), "top"))
    upper = _board(_placement("TP_x", 0.5, (0.0, 0.0), "bottom"))
    assert gap_required_thickness(lower, upper) == SPACER_MIN_THICKNESS_MM


def test_rounds_up_to_tenth():
    # 1.05 + 0.95 = 2.0 + 0.3 clearance = 2.3 (already a tenth)
    lower = _board(_placement("U_A", 1.05, (0.0, 0.0), "top"))
    upper = _board(_placement("U_B", 0.96, (0.0, 0.0), "bottom"))
    # 1.05 + 0.96 = 2.01 + 0.3 = 2.31 → ceil to 2.4
    assert gap_required_thickness(lower, upper) == 2.4
    assert SPACER_CLEARANCE_MM == 0.3
