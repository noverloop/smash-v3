"""Tests for smash.layout.placer.grid — bbox, rotation, world coords,
AABB overlap."""
from __future__ import annotations

import math
import pytest

from smash.state.footprint import Footprint
from smash.state.pad import Pad
from smash.state.topology.placement import Placement
from smash.layout.placer.grid import (
    footprint_bbox_mm,
    placement_extents_mm,
    rects_overlap,
    rotate_point,
    snap_rotation,
    world_pad_position,
)


# ── snap_rotation ─────────────────────────────────────────────────────

@pytest.mark.parametrize("inp,exp", [
    (0,    0),  (44,   0),  (46,   90),  (89,  90),  (90,  90),
    (134, 90), (136, 180),  (180, 180),  (270, 270), (359,  0),
    (-90, 270), (450, 90), (720,  0),
])
def test_snap_rotation(inp, exp):
    """Cardinal snap. Exact midpoints (45/135/225/315) are ambiguous —
    Python's banker's rounding decides; we don't test those."""
    assert snap_rotation(inp) == exp


# ── rotate_point ──────────────────────────────────────────────────────

def test_rotate_point_identity():
    assert rotate_point((1.0, 2.0), 0) == (1.0, 2.0)


def test_rotate_point_90():
    assert rotate_point((1.0, 0.0), 90) == (0.0, 1.0)


def test_rotate_point_180():
    x, y = rotate_point((3.0, -4.0), 180)
    assert (x, y) == (-3.0, 4.0)


def test_rotate_point_270():
    x, y = rotate_point((1.0, 0.0), 270)
    assert (x, y) == (0.0, -1.0)


def test_rotate_point_snaps_non_cardinal():
    # 80° snaps to 90°
    assert rotate_point((1.0, 0.0), 80) == (0.0, 1.0)


# ── footprint_bbox_mm ─────────────────────────────────────────────────

def _two_pad_fp() -> Footprint:
    """0402-ish: two 0.6×0.7 pads at ±0.5 in x."""
    return Footprint(
        name="C_0402",
        pads=[
            Pad(num="1", position_mm=(-0.5, 0.0), size_mm=(0.6, 0.7)),
            Pad(num="2", position_mm=( 0.5, 0.0), size_mm=(0.6, 0.7)),
        ],
        size_mm=(1.6, 0.8),
        package_class="0402",
    )


def test_bbox_pads_only():
    bb = footprint_bbox_mm(_two_pad_fp())
    # x: ±0.5 ± 0.3 = ±0.8; y: ±0.35
    assert bb == pytest.approx((-0.8, -0.35, 0.8, 0.35))


def test_bbox_pad_margin_inflates():
    bb = footprint_bbox_mm(_two_pad_fp(), inter_chip_margin_mm=0.1)
    assert bb == pytest.approx((-0.9, -0.45, 0.9, 0.45))


def test_bbox_courtyard_dominates():
    fp = _two_pad_fp()
    fp.courtyard = [(-1.5, -1.0), (1.5, -1.0), (1.5, 1.0), (-1.5, 1.0)]
    bb = footprint_bbox_mm(fp)
    # Courtyard is bigger than pads → courtyard wins
    assert bb == pytest.approx((-1.5, -1.0, 1.5, 1.0))


def test_bbox_falls_back_to_size_mm():
    fp = Footprint(name="X", size_mm=(2.0, 1.0), package_class="QFN")
    bb = footprint_bbox_mm(fp)
    assert bb == pytest.approx((-1.0, -0.5, 1.0, 0.5))


def test_bbox_empty_footprint_raises():
    with pytest.raises(ValueError, match="cannot compute placement bbox"):
        footprint_bbox_mm(Footprint(name="empty"))


# ── world_pad_position ────────────────────────────────────────────────

def test_world_pad_unrotated():
    fp = _two_pad_fp()
    pl = Placement(position_mm=(10.0, 20.0), rotation_deg=0, item=None)
    # pad 2 is at footprint-local (+0.5, 0) → world (10.5, 20)
    assert world_pad_position(pl, fp.pads[1]) == pytest.approx((10.5, 20.0))


def test_world_pad_rotated_90():
    fp = _two_pad_fp()
    pl = Placement(position_mm=(10.0, 20.0), rotation_deg=90, item=None)
    # pad 2 (+0.5, 0) rotated 90° → (0, +0.5) → world (10.0, 20.5)
    assert world_pad_position(pl, fp.pads[1]) == pytest.approx((10.0, 20.5))


def test_world_pad_rotated_180():
    fp = _two_pad_fp()
    pl = Placement(position_mm=(10.0, 20.0), rotation_deg=180, item=None)
    # pad 2 (+0.5, 0) rotated 180° → (-0.5, 0) → world (9.5, 20.0)
    assert world_pad_position(pl, fp.pads[1]) == pytest.approx((9.5, 20.0))


def test_world_pad_bottom_face_mirrors_x():
    fp = _two_pad_fp()
    pl = Placement(position_mm=(10.0, 20.0), rotation_deg=0, item=None,
                   face="bottom")
    # pad 2 (+0.5, 0) flipped to bottom → x mirrored → world (9.5, 20.0)
    assert world_pad_position(pl, fp.pads[1]) == pytest.approx((9.5, 20.0))


# ── placement_extents_mm ──────────────────────────────────────────────

def test_extents_unrotated():
    fp = _two_pad_fp()
    pl = Placement(position_mm=(10.0, 20.0), rotation_deg=0, item=None)
    ext = placement_extents_mm(pl, fp)
    assert ext == pytest.approx((9.2, 19.65, 10.8, 20.35))


def test_extents_rotated_90_swaps_dims():
    fp = _two_pad_fp()
    pl = Placement(position_mm=(0.0, 0.0), rotation_deg=90, item=None)
    ext = placement_extents_mm(pl, fp)
    # Bbox was 1.6 wide × 0.7 tall → after 90° → 0.7 × 1.6
    w = ext[2] - ext[0]; h = ext[3] - ext[1]
    assert w == pytest.approx(0.7)
    assert h == pytest.approx(1.6)


# ── rects_overlap ─────────────────────────────────────────────────────

def test_rects_overlap_yes():
    assert rects_overlap((0, 0, 2, 2), (1, 1, 3, 3))


def test_rects_overlap_no_disjoint():
    assert not rects_overlap((0, 0, 1, 1), (2, 2, 3, 3))


def test_rects_overlap_edge_touch_counts_as_no():
    # Abutting chips with zero gap should NOT overlap (open interval)
    assert not rects_overlap((0, 0, 1, 1), (1, 0, 2, 1))


def test_rects_overlap_inside():
    # Fully contained → overlap
    assert rects_overlap((0, 0, 10, 10), (3, 3, 4, 4))


def test_rects_overlap_eps_tolerance():
    # Touching with tiny float jitter still counts as non-overlap
    assert not rects_overlap((0, 0, 1.0, 1.0), (1.0 + 1e-9, 0, 2, 1))
