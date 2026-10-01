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
    # Rotate the four corners; cardinal rotations keep the result
    # axis-aligned but may swap which corner is min vs max.
    corners = [
        rotate_point((lo_x, lo_y), placement.rotation_deg),
        rotate_point((lo_x, hi_y), placement.rotation_deg),
        rotate_point((hi_x, lo_y), placement.rotation_deg),
        rotate_point((hi_x, hi_y), placement.rotation_deg),
    ]
    if placement.face == "bottom":
        corners = [(-x, y) for x, y in corners]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    cx, cy = placement.position_mm
    return (cx + min(xs), cy + min(ys), cx + max(xs), cy + max(ys))


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
