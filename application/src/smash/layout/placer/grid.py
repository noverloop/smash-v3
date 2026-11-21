"""Geometric primitives for the placer.

All coordinates are in millimetres. Footprint-local coordinates are
relative to the footprint's own origin (where `Pad.position_mm` is
defined). Board-local coordinates are relative to the board's origin;
the chip's `Placement.position_mm` lives in board-local space.

The placer never works in panel-global coordinates — the Panel layer
handles board → panel composition separately.
"""
from __future__ import annotations

import math
from typing import Sequence

from smash.state.footprint import Footprint
from smash.state.pad import Pad
from smash.state.topology.placement import Placement


# Per-side inflation applied to the pad bbox before merging with the
# courtyard bbox. Matches `tools/layout_gen/placer.py:120` — currently
# 0 because the courtyard already encodes IPC-7351 keep-out. Bumping
# this widens spacing without redrawing footprints.
INTER_CHIP_PAD_MARGIN_MM = 0.0


# ── rotation helpers ──────────────────────────────────────────────────

def snap_rotation(deg: float) -> int:
    """Snap an arbitrary rotation to the nearest cardinal (0/90/180/270).

    The placer + KiCad export only support cardinal rotations — non-
    cardinal angles break BGA ball-grid alignment with the board grid
    and turn length-equalization into a much harder problem.
    """
    return int(round((deg % 360) / 90)) * 90 % 360


def rotate_point(point: tuple[float, float], deg: float) -> tuple[float, float]:
    """Rotate (x, y) around the origin by `deg` (cardinal only).

    Footprint-local convention: +x right, +y up (KiCad uses +y down,
    but our data model normalises to +y up — see `Pad.position_mm`).
    """
    snap = snap_rotation(deg)
    x, y = point
    if snap == 0:    return (x, y)
    if snap == 90:   return (-y, x)
    if snap == 180:  return (-x, -y)
    if snap == 270:  return (y, -x)
    raise AssertionError(f"snap_rotation produced non-cardinal: {snap}")


# ── footprint bbox ────────────────────────────────────────────────────

def _pad_bbox(pads: Sequence[Pad]) -> tuple[float, float, float, float] | None:
    """Bbox of every pad in footprint-local coords, or None if empty."""
    if not pads:
        return None
    xs_lo: list[float] = []
    xs_hi: list[float] = []
    ys_lo: list[float] = []
    ys_hi: list[float] = []
    for p in pads:
        cx, cy = p.position_mm
        w, h = p.size_mm
        xs_lo.append(cx - w / 2); xs_hi.append(cx + w / 2)
        ys_lo.append(cy - h / 2); ys_hi.append(cy + h / 2)
    return (min(xs_lo), min(ys_lo), max(xs_hi), max(ys_hi))


def _polygon_bbox(pts: Sequence[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    """Bbox of a polygon (open or closed), or None if < 1 point."""
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def footprint_bbox_mm(
    footprint: Footprint,
    *,
    inter_chip_margin_mm: float = INTER_CHIP_PAD_MARGIN_MM,
) -> tuple[float, float, float, float]:
    """Placement bbox of a footprint, in footprint-local coords.

    Returns `(min_x, min_y, max_x, max_y)`. The bbox is the union of:
      - pad bbox, inflated by `inter_chip_margin_mm` per side
      - courtyard polygon bbox (IPC-7351 keep-out)
      - body outline bbox (worst-case fallback)

    Falls back to `footprint.size_mm` centred on the origin if all of
    the above are empty.

    Mirrors `tools/layout_gen/placer.py:_footprint_bbox_mm` but reads
    from the smash data model instead of pcbnew.
    """
    pad_bb = _pad_bbox(footprint.pads)
    if pad_bb is not None and inter_chip_margin_mm:
        m = inter_chip_margin_mm
        pad_bb = (pad_bb[0] - m, pad_bb[1] - m, pad_bb[2] + m, pad_bb[3] + m)

    crt_bb = _polygon_bbox(footprint.courtyard)
    fab_bb = _polygon_bbox(footprint.body_outline)

    candidates = [bb for bb in (pad_bb, crt_bb, fab_bb) if bb is not None]
    if candidates:
        return (
            min(bb[0] for bb in candidates),
            min(bb[1] for bb in candidates),
            max(bb[2] for bb in candidates),
            max(bb[3] for bb in candidates),
        )

    # Last-resort fallback: nominal envelope centred on origin.
    if footprint.size_mm:
        w, h = footprint.size_mm
        return (-w / 2, -h / 2, w / 2, h / 2)

    raise ValueError(
        f"footprint {footprint.name!r} has no pads, courtyard, body_outline, "
        f"or size_mm — cannot compute placement bbox"
    )


# ── world-coord transforms ────────────────────────────────────────────

def world_pad_position(
    placement: Placement,
    pad: Pad,
) -> tuple[float, float]:
    """Compute the world (board-local) position of a pad.

    Order of operations:
      1. take the pad's footprint-local position
      2. rotate by `placement.rotation_deg` around the footprint origin
      3. (if face == 'bottom') mirror in X — KiCad convention for the
         B.Cu side; pads physically swap left/right when flipped to
         the back face
      4. translate by `placement.position_mm`
    """
    px, py = rotate_point(pad.position_mm, placement.rotation_deg)
    if placement.face == "bottom":
        px = -px
    cx, cy = placement.position_mm
    return (cx + px, cy + py)


def placement_extents_mm(
    placement: Placement,
    footprint: Footprint,
    *,
    inter_chip_margin_mm: float = INTER_CHIP_PAD_MARGIN_MM,
) -> tuple[float, float, float, float]:
    """The placement's AABB in board-local coords, after rotation.

    Used by the packer to test fit and detect overlap. Returns
    `(min_x, min_y, max_x, max_y)`.
    """
    lo_x, lo_y, hi_x, hi_y = footprint_bbox_mm(
        footprint, inter_chip_margin_mm=inter_chip_margin_mm
    )
    corners = _rotated_corners(placement, (lo_x, lo_y, hi_x, hi_y))
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    cx, cy = placement.position_mm
    return (cx + min(xs), cy + min(ys), cx + max(xs), cy + max(ys))


def _is_cardinal(deg: float) -> bool:
    return abs(((deg or 0.0) % 90.0 + 45.0) % 90.0 - 45.0) < 0.5


def _rotated_corners(placement: Placement, box) -> list:
    """The footprint box's 4 corners in board-local offsets. Cardinal
    rotations use the snapped helper; (2026-11-21) any other angle (a locked
    part turned e.g. 45°, the radar AoP) is rotated EXACTLY — snapping it
    would reserve the wrong area."""
    lo_x, lo_y, hi_x, hi_y = box
    pts = [(lo_x, lo_y), (lo_x, hi_y), (hi_x, hi_y), (hi_x, lo_y)]
    deg = placement.rotation_deg or 0.0
    if _is_cardinal(deg):
        corners = [rotate_point(p, deg) for p in pts]
    else:
        import math
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        corners = [(x * c - y * s, x * s + y * c) for x, y in pts]
    if placement.face == "bottom":
        corners = [(-x, y) for x, y in corners]
    return corners


def placement_rects_mm(
    placement: Placement,
    footprint: Footprint,
    *,
    inter_chip_margin_mm: float = INTER_CHIP_PAD_MARGIN_MM,
    strip_mm: float = 0.4,
) -> list:
    """The area a placement occupies as axis-aligned rects (min_x, min_y,
    max_x, max_y). One rect (= placement_extents_mm) for cardinal rotations;
    for any other angle a STAIRCASE of horizontal strips hugging the true
    rotated outline, so a 45° part does not block its whole bounding square
    (2026-11-21: the 15 mm radar AoP turned 45° — its AABB is 24 mm)."""
    deg = placement.rotation_deg or 0.0
    if _is_cardinal(deg):
        return [placement_extents_mm(placement, footprint,
                                     inter_chip_margin_mm=inter_chip_margin_mm)]
    from shapely.geometry import Polygon, box as _box
    corners = _rotated_corners(placement, footprint_bbox_mm(
        footprint, inter_chip_margin_mm=inter_chip_margin_mm))
    cx, cy = placement.position_mm
    poly = Polygon([(cx + x, cy + y) for x, y in corners])
    x0, y0, x1, y1 = poly.bounds
    import math
    strips = max(1, math.ceil((y1 - y0) / strip_mm))   # a 45° edge overshoots ≤ strip_mm
    out = []
    for k in range(strips):
        ya, yb = y0 + (y1 - y0) * k / strips, y0 + (y1 - y0) * (k + 1) / strips
        piece = poly.intersection(_box(x0 - 1, ya, x1 + 1, yb))
        if not piece.is_empty:
            bx0, _by0, bx1, _by1 = piece.bounds
            out.append((bx0, ya, bx1, yb))
    return out


def placement_pad_extents_mm(
    placement: Placement,
    footprint: Footprint,
    *,
    clearance_mm: float = 0.0,
) -> list[tuple[float, float, float, float]]:
    """Per-PAD AABBs of a placement in board-local coords (same rotation +
    bottom-face X-mirror as `placement_extents_mm`), each ringed by
    `clearance_mm`.

    The sparse-part alternative to the single whole-footprint AABB: a
    multi-pad `manf == "project"` pseudo-part (the P_CELL_CONTACTS cell-centre
    triangle, pogo clusters) occupies its pad islands, not the enveloping
    courtyard — treating it as one box blocks the empty board between the
    pads (overlap false-positives; phantom LGA-land keepouts)."""
    rects: list[tuple[float, float, float, float]] = []
    cx, cy = placement.position_mm
    for pad in footprint.pads:
        w, h = pad.size_mm
        px, py = pad.position_mm
        lo = (px - w / 2 - clearance_mm, py - h / 2 - clearance_mm)
        hi = (px + w / 2 + clearance_mm, py + h / 2 + clearance_mm)
        corners = [rotate_point(pt, placement.rotation_deg)
                   for pt in (lo, (lo[0], hi[1]), (hi[0], lo[1]), hi)]
        if placement.face == "bottom":
            corners = [(-x, y) for x, y in corners]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        rects.append((cx + min(xs), cy + min(ys),
                      cx + max(xs), cy + max(ys)))
    return rects


# ── AABB ops for the packer ───────────────────────────────────────────

def rects_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    *,
    eps_mm: float = 1e-6,
) -> bool:
    """True iff two AABBs `(min_x, min_y, max_x, max_y)` overlap.

    Edge-touching counts as non-overlap (open interval), so abutting
    chips with zero gap don't trip the packer's collision check.
    `eps_mm` guards against floating-point boundary jitter.
    """
    if a[2] <= b[0] + eps_mm:  return False
    if b[2] <= a[0] + eps_mm:  return False
    if a[3] <= b[1] + eps_mm:  return False
    if b[3] <= a[1] + eps_mm:  return False
    return True
