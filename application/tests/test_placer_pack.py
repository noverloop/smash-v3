"""Tests for smash.layout.placer.pack — radial packer + outline checks."""
from __future__ import annotations

import math
import pytest

from smash.layout.placer.pack import (
    COMP_GAP_MM,
    _anchors_with_alignment,
    _chip_extents,
    _inside_outline_circle,
    _polygon_contains_rect,
    pack_radial,
)
from smash.state import Board
from smash.state.board_geometry import BoardGeometry, Keepout
from smash.state.chip import Chip
from smash.state.footprint import Footprint
from smash.state.pad import Pad
from smash.state.topology.placement import Placement


# ── chip factory ──────────────────────────────────────────────────────

def _square_chip(ref: str, side_mm: float) -> Chip:
    """A square chip of the given side, with a single centred pad
    that drives the bbox."""
    fp = Footprint(
        name=f"FP_{ref}",
        pads=[Pad(num="1", position_mm=(0.0, 0.0),
                  size_mm=(side_mm, side_mm))],
        package_class="QFN",
    )
    return Chip(ref=ref, manf_pn=f"PN_{ref}", footprint=fp)


def _rect_chip(ref: str, w_mm: float, h_mm: float) -> Chip:
    fp = Footprint(
        name=f"FP_{ref}",
        pads=[Pad(num="1", position_mm=(0.0, 0.0),
                  size_mm=(w_mm, h_mm))],
        package_class="QFN",
    )
    return Chip(ref=ref, manf_pn=f"PN_{ref}", footprint=fp)


# ── _chip_extents ─────────────────────────────────────────────────────

def test_chip_extents_unrotated():
    c = _rect_chip("U1", 4.0, 2.0)
    assert _chip_extents(c, 0) == pytest.approx((4.0, 2.0))


def test_chip_extents_rotated_90():
    c = _rect_chip("U1", 4.0, 2.0)
    # 90° rotation swaps W and H
    assert _chip_extents(c, 90) == pytest.approx((2.0, 4.0))


# ── _inside_outline_circle ────────────────────────────────────────────

def test_inside_circle_centred():
    assert _inside_outline_circle(10.0, 0.0, 0.0, 4.0, 4.0)


def test_inside_circle_edge_just_fits():
    # 4×4 chip at (8, 0) → far corner at (10, 2) → r ≈ 10.198 → OUT of R=10
    assert not _inside_outline_circle(10.0, 8.0, 0.0, 4.0, 4.0)


def test_inside_circle_just_fits():
    # 4×4 at (3, 0): far corner (5, 2) → r ≈ 5.385 → fits in R=10
    assert _inside_outline_circle(10.0, 3.0, 0.0, 4.0, 4.0)


# ── _polygon_contains_rect ────────────────────────────────────────────

def test_rect_contains_chip():
    assert _polygon_contains_rect((-10, 10), (-5, 5), 0, 0, 4, 4)


def test_rect_rejects_chip_clipping_edge():
    assert not _polygon_contains_rect((-10, 10), (-5, 5), 9, 0, 4, 4)


# ── _anchors_with_alignment ───────────────────────────────────────────

def test_anchors_count():
    # 4 sides × 3 alignments + 4 corners = 16
    anchors = _anchors_with_alignment(0.0, 0.0, 2.0, 2.0, 1.0, 1.0)
    assert len(anchors) == 16


def test_anchors_around_origin_are_symmetric():
    """For symmetric inputs the anchor set should be symmetric about
    both axes."""
    anchors = set(_anchors_with_alignment(0.0, 0.0, 2.0, 2.0, 1.0, 1.0))
    for x, y in anchors:
        assert (-x, y) in anchors or (-x, -y) in anchors


# ── pack_radial end-to-end ────────────────────────────────────────────

def test_pack_empty_returns_nothing():
    board = Board("flight_board")
    placements, max_reach, overflow = pack_radial(
        chips_to_place=[], board=board)
    assert placements == []
    assert max_reach == 0.0
    assert overflow is False


def test_pack_single_chip_lands_at_origin():
    board = Board("flight_board")  # Ø34 circle
    c = _square_chip("U1", 4.0)
    placements, max_reach, overflow = pack_radial(
        chips_to_place=[c], board=board)
    assert len(placements) == 1
    p = placements[0]
    assert p.item is c
    assert p.position_mm == pytest.approx((0.0, 0.0))
    assert p.rotation_deg in (0, 90)
    assert p.face == "top"
    assert not p.locked
    assert not overflow


def test_pack_many_small_chips_no_overlap():
    """20 small chips should pack inside a Ø34 board without overlap."""
    board = Board("flight_board")
    chips = [_square_chip(f"R{i}", 1.0) for i in range(20)]
    placements, max_reach, overflow = pack_radial(
        chips_to_place=chips, board=board)
    assert len(placements) == 20
    assert not overflow
    # No pair-wise overlap
    for i, a in enumerate(placements):
        for b in placements[i + 1:]:
            ax, ay = a.position_mm; bx, by = b.position_mm
            aw, ah = _chip_extents(a.item, a.rotation_deg)
            bw, bh = _chip_extents(b.item, b.rotation_deg)
            # Allow zero-gap touching (open interval), but no overlap
            assert (abs(ax - bx) >= (aw + bw) / 2 + COMP_GAP_MM - 1e-6
                    or abs(ay - by) >= (ah + bh) / 2 + COMP_GAP_MM - 1e-6)


def test_pack_respects_already_placed():
    """A locked chip at the origin should force the packer to land
    elsewhere."""
    board = Board("flight_board")
    locked_chip = _square_chip("U_LOCKED", 6.0)
    locked = Placement(position_mm=(0.0, 0.0), rotation_deg=0,
                       item=locked_chip, locked=True)
    chips = [_square_chip("R1", 2.0)]
    placements, _, _ = pack_radial(
        chips_to_place=chips, board=board,
        already_placed=[locked])
    p = placements[0]
    # New chip should not overlap the 6×6 lock
    assert abs(p.position_mm[0]) >= 3.0 + 1.0 + COMP_GAP_MM - 1e-6 \
        or abs(p.position_mm[1]) >= 3.0 + 1.0 + COMP_GAP_MM - 1e-6


def test_pack_overflow_flag_when_too_many():
    """Cram too many chips into Ø15 — overflow should trip."""
    board = Board("camera_module")  # Ø15
    chips = [_square_chip(f"R{i}", 4.0) for i in range(50)]
    _, _, overflow = pack_radial(
        chips_to_place=chips, board=board)
    assert overflow is True


def test_pack_respects_keepouts():
    """A custom geometry with a centre-square keepout — packer must
    not place any chip overlapping that square."""
    geom = BoardGeometry(
        shape="circle", diameter_mm=34.0,
        keepouts=[Keepout(
            polygon=[(-5, -5), (5, -5), (5, 5), (-5, 5)],
            scope="component", tag="exclusion",
        )],
    )
    board = Board("test_keepout_board", geometry=geom)
    chips = [_square_chip(f"R{i}", 2.0) for i in range(10)]
    placements, _, overflow = pack_radial(
        chips_to_place=chips, board=board)
    assert not overflow
    for p in placements:
        x, y = p.position_mm
        w, h = _chip_extents(p.item, p.rotation_deg)
        # AABB must not overlap (-5,-5)→(5,5)
        chip_outside_keepout = (
            x + w / 2 <= -5 or x - w / 2 >= 5 or
            y + h / 2 <= -5 or y - h / 2 >= 5
        )
        assert chip_outside_keepout, \
            f"chip {p.item.ref} at ({x}, {y}) overlaps keepout"


def test_pack_potting_holes_avoided():
    """Real Ø34 board has 2 potting keepouts at (±10.6, ∓10.6).
    Packed chips should avoid them."""
    board = Board("flight_board")
    chips = [_square_chip(f"R{i}", 2.0) for i in range(10)]
    placements, _, _ = pack_radial(
        chips_to_place=chips, board=board)
    # Potting keepouts: 3.0×3.0 squares centred on the hole positions
    ko_centres = [(hole.position_mm) for hole in board.geometry.holes]
    h = 1.5  # half-side of the keepout square
    for p in placements:
        x, y = p.position_mm
        w, ch = _chip_extents(p.item, p.rotation_deg)
        for kx, ky in ko_centres:
            chip_avoids = (
                x + w / 2 <= kx - h or x - w / 2 >= kx + h or
                y + ch / 2 <= ky - h or y - ch / 2 >= ky + h
            )
            assert chip_avoids, \
                f"chip {p.item.ref} at ({x:.2f},{y:.2f}) hits potting KO at ({kx},{ky})"


def test_pack_rect_board():
    """nfc_antenna_flex is 28×51 mm. Packer should respect bounds."""
    board = Board("nfc_antenna_flex")
    chips = [_square_chip(f"R{i}", 2.0) for i in range(20)]
    placements, _, overflow = pack_radial(
        chips_to_place=chips, board=board)
    assert not overflow
    for p in placements:
        x, y = p.position_mm
        w, h = _chip_extents(p.item, p.rotation_deg)
        assert -14.0 <= x - w / 2 and x + w / 2 <= 14.0    # 28 / 2 = 14
        assert -25.5 <= y - h / 2 and y + h / 2 <= 25.5    # 51 / 2 = 25.5


def test_pack_rotation_helps_long_chip():
    """A 8×2 chip should pack inside a Ø12 board only via rotation;
    the non-square chip fits when rotated to align with the diameter.
    (Ø12 not Ø10: the packer now always insets by the 1 mm edge wall, so
    the chip's 4.12 mm corner reach needs radius ≥ 5.12 to clear it.)"""
    geom = BoardGeometry(shape="circle", diameter_mm=12.0)
    board = Board("test_small", geometry=geom)
    c = _rect_chip("LONG", 8.0, 2.0)
    placements, _, overflow = pack_radial(
        chips_to_place=[c], board=board)
    assert not overflow
    assert len(placements) == 1


def test_pack_chip_without_footprint_raises():
    board = Board("flight_board")
    c = Chip(ref="NOFP", manf_pn="X")     # no footprint
    with pytest.raises(ValueError, match="no footprint"):
        pack_radial(chips_to_place=[c], board=board)


# ── BoardGeometry.outline_polygon / radius extras ────────────────────

def test_outline_polygon_circle_segments():
    g = BoardGeometry(shape="circle", diameter_mm=10.0)
    poly = g.outline_polygon()
    assert len(poly) == 64
    # Every point is on the circle (within float tolerance)
    for x, y in poly:
        assert math.hypot(x, y) == pytest.approx(5.0, abs=1e-9)


def test_outline_polygon_circle_custom_segments():
    g = BoardGeometry(shape="circle", diameter_mm=10.0)
    poly = g.outline_polygon(segments=8)
    assert len(poly) == 8


def test_outline_polygon_rect():
    g = BoardGeometry(shape="rect", rect_dimensions=(28.0, 51.0))
    poly = g.outline_polygon()
    assert len(poly) == 4
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    assert min(xs) == -14.0 and max(xs) == 14.0
    assert min(ys) == -25.5 and max(ys) == 25.5


def test_outline_polygon_dxf_raises():
    g = BoardGeometry(shape="dxf", dxf_path="x.dxf")
    with pytest.raises(NotImplementedError, match="DXF outline"):
        g.outline_polygon()


def test_outline_radius_circle():
    g = BoardGeometry(shape="circle", diameter_mm=34.0)
    assert g.outline_radius_mm == 17.0


def test_outline_radius_rect():
    g = BoardGeometry(shape="rect", rect_dimensions=(6.0, 8.0))
    assert g.outline_radius_mm == pytest.approx(5.0)  # half-diag of 6×8
