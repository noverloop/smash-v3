"""Cavity geometry — fold-projection, polygon merge, potting-channel math.

Lifted verbatim from `tools/layout_gen/cavity_geom.py` (which was already
pcbnew-free — the shared source of truth between placer and audit).
Imports only `math` and `shapely`.
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union


CAVITY_MARGIN_MM = 0.15
"""XY clearance from chip body to cavity wall. RSS of body tolerance
±0.10 (IPC-7351) + placement ±0.05 + mill ±0.10 = 0.15 mm."""

CAVITY_MERGE_THRESHOLD_MM = 0.25
"""Cavities separated by < this much get fused via morphological close."""

CAVITY_SELFTOUCH_HEAL_MM = 0.01
"""Morphological-close radius used to heal a polygon that pinches to a
near-zero-width neck where the diagonal potting channel grazes a chip
cavity. Bigger than the 0.0001 mm (4-dp) Edge.Cuts emission grid, smaller
than any real wall — so it fills only the sub-grid pinch, leaving every
genuine edge untouched (area-preserving for clean rectangles)."""

CAVITY_EDGE_WALL_MM = 1.0
"""Minimum FR4 wall between any cavity and the spacer outline. Cavities
are clipped to the outline inset by this much — keeps the spacer
structurally a plate (not a frame) at the rim and gives the potting
compound a sealed perimeter (liquid integrity)."""

CAVITY_THIN_WALL_FILL_MM = 1.0
"""Minimum FR4 wall thickness between two cavities (or between a
cavity and the outline-inset boundary). After clipping cavities to
the spacer outline, any leftover FR4 sliver thinner than this gets
absorbed into the adjacent cavity. Without this pass, two close-but-
not-touching cavities leave a 0.3-0.9 mm thin wall — too thin to mill
reliably, structurally negligible, and often dangling because its
"opposite side" is already a cutout (the outline or the next cavity).
Set the same as CAVITY_EDGE_WALL_MM by default: a wall too thin to
hold the rim is also too thin to be a meaningful interior wall."""


def _spacer_keep_region(outline_radius_mm, flex_chords,
                        inset_mm=CAVITY_EDGE_WALL_MM):
    """The spacer's true outline (circle minus each flex-launch chord)
    inset by `inset_mm` (default `CAVITY_EDGE_WALL_MM`; pass 0 for the
    PHYSICAL spacer region). `flex_chords` is a list of
    `(angle_deg, width_mm)` — at each flex the board edge is a straight
    chord at distance √(r²−(w/2)²) along that angle, so the cavity must
    keep its wall from the chord too, not just the arc."""
    from shapely.geometry import Point, Polygon
    outline = Point(0.0, 0.0).buffer(outline_radius_mm, quad_segs=64)
    big = 4.0 * outline_radius_mm
    for angle_deg, width_mm in flex_chords:
        if width_mm <= 0 or width_mm >= 2 * outline_radius_mm:
            continue
        d = math.sqrt(outline_radius_mm ** 2 - (width_mm / 2.0) ** 2)
        th = math.radians(angle_deg)
        nx, ny = math.cos(th), math.sin(th)      # toward the flex
        px, py = -ny, nx                          # along the chord
        # Keep the half-plane {p·n ≤ d} (the board side of the chord).
        half = Polygon([
            (-big * nx + s * big * px, -big * ny + s * big * py)
            for s in (-1, 1)
        ] + [
            (d * nx + s * big * px, d * ny + s * big * py)
            for s in (1, -1)
        ])
        outline = outline.intersection(half)
    return outline.buffer(-inset_mm) if inset_mm else outline


SPACER_FLOOR_MIN_MM = 1.0
"""Minimum FR4 left between a spacer's top and bottom pockets. Where both
faces need pockets deep enough that less than this would remain, the
overlap is cut clean THROUGH instead — it's potted shut, so a through
window beats a paper-thin floor that the mill would blow out."""


def _flatten_polys(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in geom.geoms
            if g.geom_type == "Polygon" and not g.is_empty]


def _to_simple_polys(polys):
    """Heal every cavity polygon to a *simple* (non-self-intersecting)
    ring that stays simple after the exporter rounds it to the 4-dp
    Edge.Cuts grid, flattening any repair that splits into pieces.

    Where the thin diagonal potting channel grazes a chip cavity the
    merged boundary pinches to a near-zero-width neck. At full precision
    the neck has a hair of positive width (shapely calls it valid), but
    the 0.0001 mm emission rounding collapses it into a self-touch — and
    a single self-touching loop on Edge.Cuts makes KiCad declare the
    whole panel outline malformed and fall back to the bounding box, so
    every tile (cavities included) renders as a filled slab. A plain
    `buffer(0)` leaves the neck sub-grid-thin, so it does NOT survive
    rounding; a small mitre morphological close fills the pinch to a real
    (>grid) width. Mitre joins keep the vertex count flat and the close
    is area-preserving for already-clean rectangles, so it is safe to run
    on every cavity."""
    eps = CAVITY_SELFTOUCH_HEAL_MM
    out = []
    for p in polys:
        if p.is_empty:
            continue
        p = p.buffer(eps, join_style=2).buffer(-eps, join_style=2)
        out.extend(_flatten_polys(p))
    return out


def split_through_cavities(top_polys, depth_top, bot_polys, depth_bot,
                           thickness_mm):
    """If the top + bottom pockets would leave < SPACER_FLOOR_MIN_MM of
    FR4 where they overlap, cut that overlap clean through. Returns
    `(top_polys, bot_polys, through_polys)`.

    The face pockets are returned UNCHANGED — the through window is an
    additional, deeper cut over the same XY (the deeper cut simply wins),
    which avoids the sliver/hole geometry that subtracting it would
    create (and that the CAD kernel chokes on)."""
    if (not top_polys or not bot_polys
            or depth_top + depth_bot <= thickness_mm - SPACER_FLOOR_MIN_MM):
        return list(top_polys), list(bot_polys), []
    through = unary_union(list(top_polys)).intersection(
        unary_union(list(bot_polys)))
    return list(top_polys), list(bot_polys), _to_simple_polys(
        _flatten_polys(through))


def clip_cavities_to_outline(polys, outline_radius_mm, flex_chords=(),
                             fill_thin_walls_mm: float = CAVITY_THIN_WALL_FILL_MM):
    """Clip each cavity polygon to the spacer outline (circle minus flex
    chords) inset by `CAVITY_EDGE_WALL_MM`, so no cavity reaches the board
    edge — arc OR flex-launch chord. Returns the (possibly split) list of
    clipped Polygons. A None/zero radius passes the polygons through.

    After clipping, run a morphological-opening pass on the leftover FR4
    walls inside the keep region: any wall narrower than
    `fill_thin_walls_mm` is absorbed into the adjacent cavity, fusing
    cavities through sub-1 mm slivers. These slivers usually have one
    end dangling at the outline-inset boundary (the "opposite side is
    cutout" case the user flagged) — they're hard to mill and
    structurally negligible, so merging them gives a cleaner single
    polygon per cavity cluster. Pass 0 to skip the fill (legacy
    behaviour)."""
    if not outline_radius_mm:
        return _to_simple_polys(list(polys))
    keep = _spacer_keep_region(outline_radius_mm, flex_chords)
    out = []
    for p in polys:
        c = p.intersection(keep)
        if c.is_empty:
            continue
        if c.geom_type == "Polygon":
            out.append(c)
        elif c.geom_type in ("MultiPolygon", "GeometryCollection"):
            out.extend(g for g in c.geoms
                       if g.geom_type == "Polygon" and not g.is_empty)

    if fill_thin_walls_mm > 0 and out:
        cav_union = unary_union(out)
        # Measure leftover FR4 against the PHYSICAL spacer (no edge-wall
        # inset): the keep-region inset is bookkeeping, not milled air.
        # A tangential crescent between a pocket top and the keep
        # boundary is backed by the real 1 mm edge annulus — e.g. the
        # C_BAT_BULK1 lobe: pocket top y=15.23, keep arc r=16 → a
        # 0.3-0.8 mm "sliver" that is physically 1.3-1.8 mm of FR4 —
        # so it must NOT be absorbed into the cavity. Radial peninsulas
        # BETWEEN two cavities stay thin in their narrow (tangential)
        # dimension either way and are still fused.
        phys = _spacer_keep_region(outline_radius_mm, flex_chords,
                                   inset_mm=0.0)
        walls = phys.difference(cav_union)
        if not walls.is_empty:
            # Morphological opening: erode by half-thickness, then
            # dilate. Anything with a constriction narrower than
            # `fill_thin_walls_mm` vanishes; the surviving "thick" core
            # is the structural FR4 we want to keep. The difference is
            # thin slivers — fuse them into the cavity.
            half = fill_thin_walls_mm / 2.0
            thick = walls.buffer(-half, join_style=2).buffer(+half,
                                                              join_style=2)
            thin = walls.difference(thick)
            if not thin.is_empty:
                merged = unary_union([cav_union, thin])
                # Re-clip to keep (the dilation may have nudged outside
                # by floating-point noise) and re-flatten.
                merged = merged.intersection(keep)
                out = []
                if merged.geom_type == "Polygon":
                    out.append(merged)
                elif merged.geom_type in ("MultiPolygon",
                                          "GeometryCollection"):
                    out.extend(g for g in merged.geoms
                               if g.geom_type == "Polygon" and not g.is_empty)
    return _to_simple_polys(out)


POTTING_HOLE_RADIUS_MM = 14.0
"""Radial distance from board centre to each potting hole centre.
History: 15.0 → 13.0 (corner reach was 17.12 mm, just past 17.0; pulled
to 15.12 mm); now 14.0 with the wider Ø3 hole + 4×4 mm keepout square
(corner reach 16.83 mm, 0.17 mm shy of the Ø34 edge — the keepout
corner ends up inside the chip's own board-edge exclusion zone, so
nothing new is excluded by the tight margin)."""
POTTING_HOLE_DIA_MM = 3.0
"""NPTH diameter (was 2.0). Widened so a Ø3 hole carries enough
cross-section + countercurrent path for resin in / air out during
vacuum-back-fill — the failure mode at Ø2 was bubble entrapment in
the deeper interboard cavities, not raw flow rate."""
POTTING_HOLE_ANGLE_DEG_A = 135.0   # NW
POTTING_HOLE_ANGLE_DEG_B = 315.0   # SE
POTTING_CHANNEL_WIDTH_MM = 2.5
"""Diagonal NW→cavity→SE channel on every spacer face — the cavity-to-
cavity crossfeed within a single spacer face. 2.5 mm wide × cavity
depth (1.0–2.0 mm) gives D_h ≈ 2.2 mm, plenty of cross-section for
Stycast 2651MM CAT 23LV (30 000 cP mixed) under vacuum (–0.5 bar) to
spread between cavities in <1 s. The through-board Ø3 holes set the
hole-to-spacer-face flow; this channel sets the cavity-to-cavity flow
on each face. Kept at 2.5 mm even after the hole widening — channel
sizing is constrained by spacer wall thickness, not the holes."""


# Spacer cavity depths — top and bottom face differ because the parts
# on each adjacent tile face have different worst-case height envelopes.
#
# TOP cavity:    receives surface-mount ICs from the adjacent tile's
#                top face. Tallest part is the EIA-3528 tantalum cap
#                (~1.9 mm body); 2.0 mm depth covers everything with
#                margin.
# BOTTOM cavity: receives surface-mount passives from the next tile's
#                bottom face. The bottom BOM was originally curated
#                under a 1 mm embedded-package height limit (carried
#                over even though embedding was dropped), so every
#                passive there is ≤1.0 mm tall. 1.0 mm pocket clears
#                them with no slack — fine because cavity volume is
#                potted regardless.
SPACER_CAVITY_DEPTH_TOP_MM = 2.0
SPACER_CAVITY_DEPTH_BOT_MM = 1.0

# Total spacer FR4 thickness. Must accommodate both face cavities plus
# a minimum bulk floor between them where both cavities overlap — any
# thinner causes the cavity floors to connect into a through-hole (no
# FR4 anywhere at the overlap XY → spacer fragments around its cavities,
# lousy bending stiffness, plate becomes a frame).
# Minimum constraint:  thickness ≥ depth_top + depth_bot + bulk_floor
# With 1 mm bulk-floor safety margin: 2.0 + 1.0 + 1.0 = 4.0 mm.
SPACER_THICKNESS_MM = 4.0


SPACER_FLOOR_EFFECTIVE_MM = 2.0
"""Effective FR4 floor thickness exposed by a 4 mm spacer to the bend
sim's composite-plate model. The real geometry has both faces milled
(top cavity ≤ 2 mm, bottom ≤ 1 mm); where one face has a cavity and the
other doesn't, ~2 mm of solid FR4 remains in the load path. Where both
overlap and the floor would fall below 1 mm, the spacer is cut clean
through and the gap is potted — those spots transfer load via the
encapsulant (Stycast 2651MM CAT 23LV, ~4 GPa) rather than FR4. 2 mm is
the area-weighted typical, NOT a worst case; an FEA pass would do this
position-dependently."""


def assign_spacer_backings(chain: list, floor_mm: float | None = None,
                            material: str = "fr4") -> None:
    """Set `spacer_floor_above_mm` / `spacer_floor_below_mm` and
    `spacer_material` on every rigid tile in a snake `chain` (list of
    Boards, in fold order). End tiles get one face only; interior tiles
    get both. Branch leaves (camera, nfc, qpd, lora) are not in the chain
    and stay at 0 — they fold off a flex and aren't sandwiched between
    spacers.

    Defaults: `floor_mm = SPACER_FLOOR_EFFECTIVE_MM` (2 mm typical),
    `material = "fr4"` (the design's spacer material — a routable PCB
    soldered to the rigid tile faces). The earlier CNC-Al + Type-II-
    anodise spacer choice was reverted: the spacers carry signal pass-
    through routing AND are soldered to the boards above and below,
    which the anodised-Al construction can't support without isolation
    pads. Per-board structural support that Al spacers previously
    provided is recovered via copper-coin inserts in the rigid tile's
    stackup (`Board.cu_coin_inserts`).
    """
    t = SPACER_FLOOR_EFFECTIVE_MM if floor_mm is None else floor_mm
    for i, b in enumerate(chain):
        b.spacer_material = material
        if i > 0:
            b.spacer_floor_below_mm = t          # spacer between chain[i-1] and b
        if i < len(chain) - 1:
            b.spacer_floor_above_mm = t          # spacer between b and chain[i+1]


def potting_hole_positions_math_yup() -> list[tuple[float, float]]:
    return [
        (POTTING_HOLE_RADIUS_MM * math.cos(math.radians(a)),
         POTTING_HOLE_RADIUS_MM * math.sin(math.radians(a)))
        for a in (POTTING_HOLE_ANGLE_DEG_A, POTTING_HOLE_ANGLE_DEG_B)
    ]


def fold_project(rx: float, ry: float, same_row: bool) -> tuple[float, float]:
    """Mirror a point from one tile's local frame onto the adjacent
    tile's frame across the connecting flex fold. Math y-up.
      same-row fold (E-W flex) → x mirrors
      same-col fold (N-S flex) → y mirrors
    """
    return (-rx, ry) if same_row else (rx, -ry)


def rotated_bbox_mm(w: float, h: float, rot_deg: float) -> tuple[float, float]:
    """Axis-aligned bbox of (w, h) rotated by rot_deg."""
    r = math.radians(rot_deg or 0)
    c, s = abs(math.cos(r)), abs(math.sin(r))
    return c * w + s * h, s * w + c * h


def project_face_to_spacer(
    source_components: dict,
    source_side: str,
    same_row: bool,
) -> list[tuple[float, float, float, float, str]]:
    """For each component on `source_side` of a neighbour tile, return
    its cavity rect (cx, cy, w, h, ref) in the adjacent spacer's local
    frame (math y-up). Rects include `CAVITY_MARGIN_MM` clearance."""
    out = []
    for ref, info in source_components.items():
        if info.get("side") != source_side:
            continue
        w = info.get("w_mm", 0.0)
        h = info.get("h_mm", 0.0)
        if w <= 0 or h <= 0:
            continue
        w_eff, h_eff = rotated_bbox_mm(w, h, info.get("rotation_deg", 0))
        cx, cy = fold_project(info["rx_mm"], info["ry_mm"], same_row)
        out.append((
            cx, cy,
            w_eff + 2.0 * CAVITY_MARGIN_MM,
            h_eff + 2.0 * CAVITY_MARGIN_MM,
            ref,
        ))
    return out


def _rect_polygon(cx: float, cy: float, w: float, h: float) -> Polygon:
    return box(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def merge_cavity_polygons(rects, channel_endpoints=None,
                          add_channel=True) -> list:
    """Union chip cavity rectangles + (optionally) the diagonal potting
    channel into one or more shapely Polygons.

    `channel_endpoints` are the two points the channel spans (the spacer's
    fold-projected potting holes). When None, fall back to the canonical
    NW→SE diagonal — used by direct callers/tests that don't carry a
    projected hole set. `add_channel=False` unions the rects alone (used
    for the tall-chip through-cuts, which need no shallow potting channel)."""
    rect_polys = [_rect_polygon(r[0], r[1], r[2], r[3]) for r in rects]
    parts = list(rect_polys)
    if add_channel:
        if channel_endpoints and len(channel_endpoints) >= 2:
            p0, p1 = channel_endpoints[0], channel_endpoints[1]
        else:
            p0, p1 = potting_hole_positions_math_yup()
        parts.append(LineString([p0, p1]).buffer(
            POTTING_CHANNEL_WIDTH_MM / 2.0, cap_style=2))
    if not parts:
        return []
    union = unary_union(parts)
    half = CAVITY_MERGE_THRESHOLD_MM / 2.0
    closed = union.buffer(half, join_style=2).buffer(-half, join_style=2)

    if closed.is_empty:
        return []
    if closed.geom_type == "Polygon":
        return [closed]
    if closed.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [g for g in closed.geoms
                if g.geom_type == "Polygon" and not g.is_empty]
    return []
