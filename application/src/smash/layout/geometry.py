"""Pure-math geometry helpers used by the placer and the exporter.

Lifted from `tools/layout_gen/placer.py` (the leading-underscore
helpers) and `tools/layout_gen/dxf_outline.py` (Line/Arc/Circle +
arc_to_segments). No pcbnew. Outputs are plain `Line` segments and
`(x, y)` tuples — the exporter translates them into Edge.Cuts /
PCB_SHAPE.

Coordinate convention: KiCad canvas (y-down). Functions taking
`angle_deg` use math convention (0° = +x, CCW positive) and convert
internally.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from smash.layout.constants import ARC_SEGMENTS_PER_2PI


@dataclass
class Line:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Arc:
    cx: float
    cy: float
    radius: float
    start_deg: float
    end_deg: float


@dataclass
class Circle:
    cx: float
    cy: float
    radius: float


ANGLE_E =   0.0
ANGLE_N =  90.0
ANGLE_W = 180.0
ANGLE_S = 270.0


def arc_to_segments(arc: Arc, segments_per_2pi: int = 64) -> list[Line]:
    """Approximate an arc with line segments."""
    raw = arc.end_deg - arc.start_deg
    if raw >= 360.0 - 1e-9:
        sweep_deg = 360.0
    else:
        sweep_deg = raw % 360.0
        if sweep_deg < 1e-9 and arc.end_deg != arc.start_deg:
            sweep_deg = 360.0
    n = max(2, int(segments_per_2pi * sweep_deg / 360.0))
    pts = []
    for k in range(n + 1):
        a = math.radians(arc.start_deg + sweep_deg * k / n)
        pts.append((arc.cx + arc.radius * math.cos(a),
                    arc.cy + arc.radius * math.sin(a)))
    return [Line(x1=pts[i][0], y1=pts[i][1],
                 x2=pts[i + 1][0], y2=pts[i + 1][1])
            for i in range(len(pts) - 1)]


def grid_to_canvas(col: int, row: int,
                   canvas_origin_mm: tuple,
                   tile_diameter_mm: float,
                   tile_pitch_mm: float,
                   scale: float) -> tuple:
    radius = tile_diameter_mm * scale / 2.0
    pitch  = tile_pitch_mm * scale
    cx = canvas_origin_mm[0] + radius + col * pitch
    cy = canvas_origin_mm[1] + radius + row * pitch
    return cx, cy


def chord_corners(cx_mm: float, cy_mm: float,
                  angle_deg: float, width_mm: float,
                  radius_mm: float) -> tuple:
    """(corner_ccw, corner_cw) in KiCad canvas coords (y-down). ccw is
    +half_angle from the cutout's centre direction (math CCW)."""
    ha = math.degrees(math.asin((width_mm / 2) / radius_mm))
    a_ccw = math.radians(angle_deg + ha)
    a_cw  = math.radians(angle_deg - ha)
    ccw = (cx_mm + radius_mm * math.cos(a_ccw),
           cy_mm - radius_mm * math.sin(a_ccw))
    cw  = (cx_mm + radius_mm * math.cos(a_cw),
           cy_mm - radius_mm * math.sin(a_cw))
    return ccw, cw


def rect_chord_corners(cx_mm: float, cy_mm: float,
                       rect_w_mm: float, rect_h_mm: float,
                       angle_deg: float, width_mm: float) -> tuple:
    """(ccw, cw) corners where a flex strip attaches to a rect tile's
    edge. Diagonal angles fall back to the circular approximation."""
    hw = rect_w_mm / 2
    hh = rect_h_mm / 2
    half_gap = width_mm / 2
    a = angle_deg % 360.0
    if abs(a - ANGLE_E) < 1.0:
        ccw = (cx_mm + hw, cy_mm - (+half_gap))
        cw  = (cx_mm + hw, cy_mm - (-half_gap))
    elif abs(a - ANGLE_W) < 1.0:
        ccw = (cx_mm - hw, cy_mm - (-half_gap))
        cw  = (cx_mm - hw, cy_mm - (+half_gap))
    elif abs(a - ANGLE_N) < 1.0:
        ccw = (cx_mm + (-half_gap), cy_mm - hh)
        cw  = (cx_mm + (+half_gap), cy_mm - hh)
    elif abs(a - ANGLE_S) < 1.0:
        ccw = (cx_mm + (+half_gap), cy_mm + hh)
        cw  = (cx_mm + (-half_gap), cy_mm + hh)
    else:
        return chord_corners(cx_mm, cy_mm, angle_deg, width_mm,
                             max(hw, hh))
    return ccw, cw


CutoutKind = Literal["open", "notch", "flat"]


@dataclass
class Cutout:
    angle_deg: float
    width_mm: float
    depth_mm: float = 0.0
    kind: CutoutKind = "open"
    # For kind="flat": an optional central rectangular notch in the chord (the
    # USB-C mouth slot). The flat then splits into [left flat, notch, right flat]
    # as ONE continuous outline. 0 width => plain flat (no notch).
    notch_width_mm: float = 0.0
    notch_depth_mm: float = 0.0
    notch_offset_mm: float = 0.0   # notch centre offset along the chord (0 = centred)


def make_cutout(angle_deg: float, width_mm: float,
                depth_mm: float = 0.0, kind: CutoutKind = "open",
                notch_width_mm: float = 0.0, notch_depth_mm: float = 0.0,
                notch_offset_mm: float = 0.0) -> Cutout:
    return Cutout(angle_deg=angle_deg, width_mm=width_mm,
                  depth_mm=depth_mm, kind=kind,
                  notch_width_mm=notch_width_mm, notch_depth_mm=notch_depth_mm,
                  notch_offset_mm=notch_offset_mm)


def tile_outline_segments(centre_x_mm: float, centre_y_mm: float,
                          radius_mm: float,
                          cutouts: list[Cutout] | None = None) -> list[Line]:
    """Edge.Cuts segments for one circular tile = circle of radius_mm
    minus each cutout's angular range. Notch cutouts also contribute
    three inner-wall segments. Output in KiCad canvas coords (y-down).
    """
    cutouts = cutouts or []

    def tx(local_x: float, local_y: float) -> tuple:
        return centre_x_mm + local_x, centre_y_mm - local_y

    segs: list[Line] = []

    if not cutouts:
        full = Arc(cx=0.0, cy=0.0, radius=radius_mm,
                   start_deg=0.0, end_deg=360.0)
        for seg in arc_to_segments(full, ARC_SEGMENTS_PER_2PI):
            x1, y1 = tx(seg.x1, seg.y1)
            x2, y2 = tx(seg.x2, seg.y2)
            segs.append(Line(x1, y1, x2, y2))
        return segs

    intervals = []
    for cut in cutouts:
        if cut.width_mm >= 2 * radius_mm:
            raise ValueError(
                f"Cutout width {cut.width_mm} ≥ tile diameter "
                f"{2 * radius_mm}")
        half_angle = math.degrees(math.asin((cut.width_mm / 2) / radius_mm))
        center = cut.angle_deg % 360.0
        start = (center - half_angle) % 360.0
        end   = (center + half_angle) % 360.0
        intervals.append((start, end, cut))

    intervals.sort(key=lambda iv: iv[0])

    n = len(intervals)
    for i in range(n):
        arc_start = intervals[i][1]
        arc_end   = intervals[(i + 1) % n][0]
        if arc_end <= arc_start:
            arc_end += 360.0
        arc = Arc(cx=0.0, cy=0.0, radius=radius_mm,
                  start_deg=arc_start, end_deg=arc_end)
        for seg in arc_to_segments(arc, ARC_SEGMENTS_PER_2PI):
            x1, y1 = tx(seg.x1, seg.y1)
            x2, y2 = tx(seg.x2, seg.y2)
            segs.append(Line(x1, y1, x2, y2))

    for _start, _end, cut in intervals:
        if cut.kind not in ("notch", "flat"):
            continue
        cx_angle = cut.angle_deg
        dx = math.cos(math.radians(cx_angle))
        dy = math.sin(math.radians(cx_angle))
        px, py = -dy, dx
        hw = cut.width_mm / 2
        chord_dist = math.sqrt(radius_mm ** 2 - hw ** 2)
        out_a = (dx * chord_dist + px * hw, dy * chord_dist + py * hw)
        out_b = (dx * chord_dist - px * hw, dy * chord_dist - py * hw)
        if cut.kind == "flat":
            nw = getattr(cut, "notch_width_mm", 0.0)
            nd = getattr(cut, "notch_depth_mm", 0.0)
            no = getattr(cut, "notch_offset_mm", 0.0)
            if nw > 0.0 and nd > 0.0:
                # Flat chord with a central rectangular notch (the USB-C mouth
                # pocket): out_a -> right flat -> down the notch wall -> across
                # the notch floor -> up -> left flat -> out_b, as ONE continuous
                # edge. cpt(r, t): a point at radial distance r along (dx,dy),
                # offset t along the chord (px,py); out_a == cpt(chord_dist,+hw).
                def cpt(r, t):
                    return (dx * r + px * t, dy * r + py * t)
                inr = chord_dist - nd
                pts = [out_a,
                       cpt(chord_dist, no + nw / 2.0),
                       cpt(inr,        no + nw / 2.0),
                       cpt(inr,        no - nw / 2.0),
                       cpt(chord_dist, no - nw / 2.0),
                       out_b]
                for (lx1, ly1), (lx2, ly2) in zip(pts, pts[1:]):
                    x1, y1 = tx(lx1, ly1)
                    x2, y2 = tx(lx2, ly2)
                    segs.append(Line(x1, y1, x2, y2))
                continue
            # Straight chord across the flex-width opening, closing the
            # outline with a flat edge where the flex tab departs. Used
            # for standalone tile bodies; the panel leaves the opening
            # "open" so the flex strip bridges it.
            x1, y1 = tx(*out_a)
            x2, y2 = tx(*out_b)
            segs.append(Line(x1, y1, x2, y2))
            continue
        in_dist = chord_dist - cut.depth_mm
        in_a  = (dx * in_dist    + px * hw, dy * in_dist    + py * hw)
        in_b  = (dx * in_dist    - px * hw, dy * in_dist    - py * hw)
        for (lx1, ly1), (lx2, ly2) in [
                (out_a, in_a), (in_a, in_b), (in_b, out_b)]:
            x1, y1 = tx(lx1, ly1)
            x2, y2 = tx(lx2, ly2)
            segs.append(Line(x1, y1, x2, y2))

    return segs


def tile_radius_for(name: str, panel, scale: float,
                    default_radius_mm: float) -> float:
    rect = (panel.tile_rect_dimensions or {}).get(name)
    if rect is not None:
        return max(rect) * scale / 2.0
    d = (panel.tile_diameters or {}).get(name)
    if d is not None:
        return d * scale / 2.0
    return default_radius_mm
