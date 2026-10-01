"""Radial packer — centre-out placement of unanchored chips.

Ported from `tools/layout_gen/placer.py:_pack_radial_exhaustive`. The
non-exhaustive variant (`_pack_radial`) was dropped — only the
exhaustive one was actually used on real designs (per user).

What the exhaustive packer adds over the simple one:
  1. Per-chip rotation: 0° vs 90° (helps non-square footprints fit)
  2. Edge alignment: 16 anchor positions per placed chip instead of 8
     (each side has 3 — flush-low, centre, flush-high — letting small
     parts stack along one edge of a larger part), plus 4 corners.
  3. Multi-ordering search: 3 deterministic heuristics + N random
     shuffles; keep the one with the smallest max_reach.

Cost: O(N_orderings × n³ × anchors). For n=80, 15 orderings, 32 anchors
× 2 rotations: ~25 M ops. A few seconds in Python — fine because we
only run the packer on the handful of dense tiles that aren't already
fully covered by locked placements.
"""
from __future__ import annotations

import math
import random
from typing import Iterable, Sequence

from shapely.geometry import box as _box
from shapely.prepared import prep as _prep

from smash.layout.placer.grid import (
    placement_extents_mm,
    rects_overlap,
)
from smash.state.board import Board
from smash.state import Chip
from smash.state.antenna import Antenna
from smash.state.topology.placement import Placement
from smash.layout.cavities import _spacer_keep_region, CAVITY_EDGE_WALL_MM


# Component-to-component gap the packer leaves between PACKED parts'
# courtyards. 0.001 mm (1 um) = a hairline anti-abut gap: at 0.0 the packer
# placed neighbours exactly touching and floating-point left their courtyards
# overlapping by <0.1 um, which reads as a courtyard overlap. 1 um clears
# that with zero practical cost — far too small to shrink the per-joint
# backbone LGA land area (that only bit at ~0.1 mm, which dropped ~16
# inter-board nets). The >=100 um copper floor still comes from the courtyard
# ring (COURTYARD_CLEARANCE_MM); locked placements bypass the packer, so the
# EE's hand-tightened clusters are untouched.
COMP_GAP_MM = 0.001


# ── helpers ───────────────────────────────────────────────────────────

def _chip_extents(chip: Chip, rotation_deg: float) -> tuple[float, float]:
    """Origin-symmetric width, height of a chip's placement bbox after
    rotation.

    The packer's collision/anchor math is *centred*: it treats a chip as
    a (w, h) box centred on its stored position, which is the footprint
    ORIGIN. Many footprints (e.g. the SamacSys SOT-23 with origin at
    pad 1) have a courtyard that isn't centred on the origin, so a plain
    (hi−lo) size would let the off-centre courtyard poke past where the
    packer reserves space → overlaps. Returning `2·max(|lo|, |hi|)` per
    axis makes the centred box big enough to contain the real courtyard
    wherever it sits, so abutting chips never collide.
    """
    if chip.footprint is None:
        raise ValueError(
            f"chip {chip.ref!r} has no footprint — cannot pack"
        )
    pl = Placement(position_mm=(0.0, 0.0), rotation_deg=rotation_deg,
                   item=chip)
    lo_x, lo_y, hi_x, hi_y = placement_extents_mm(pl, chip.footprint)
    return (2.0 * max(abs(lo_x), abs(hi_x)),
            2.0 * max(abs(lo_y), abs(hi_y)))


def _anchors_with_alignment(
    px: float, py: float, pw: float, ph: float, nw: float, nh: float,
    gap: float = COMP_GAP_MM,
) -> list[tuple[float, float]]:
    """16 candidate positions for a new comp (nw, nh) around a placed
    one (px, py, pw, ph). 4 sides × 3 alignments + 4 corners.

    Matches tools/layout_gen/placer.py:_anchors_with_alignment.
    """
    dx_card  = (pw + nw) / 2 + gap
    dy_card  = (ph + nh) / 2 + gap
    dx_align = (pw - nw) / 2
    dy_align = (ph - nh) / 2

    anchors: list[tuple[float, float]] = []
    # North & south sides — 3 horizontal alignments each
    for sy in (-1, +1):
        y = py + sy * dy_card
        for off_x in (-dx_align, 0.0, +dx_align):
            anchors.append((px + off_x, y))
    # West & east sides — 3 vertical alignments each
    for sx in (-1, +1):
        x = px + sx * dx_card
        for off_y in (-dy_align, 0.0, +dy_align):
            anchors.append((x, py + off_y))
    # 4 corners
    for sx in (-1, +1):
        for sy in (-1, +1):
            anchors.append((px + sx * dx_card, py + sy * dy_card))
    return anchors


def _polygon_contains_rect(
    polygon_xs: tuple[float, float],
    polygon_ys: tuple[float, float],
    cx: float, cy: float, w: float, h: float,
) -> bool:
    """For rectangular outlines: is the AABB (cx ± w/2, cy ± h/2)
    fully inside the polygon's bounding extents?"""
    return (cx - w / 2 >= polygon_xs[0]
            and cx + w / 2 <= polygon_xs[1]
            and cy - h / 2 >= polygon_ys[0]
            and cy + h / 2 <= polygon_ys[1])


def _inside_outline_circle(
    radius: float, cx: float, cy: float, w: float, h: float,
) -> bool:
    """Tight check: the chip's far corner from origin must be within
    the circle. Same reach formula as the old placer."""
    far_x = abs(cx) + w / 2
    far_y = abs(cy) + h / 2
    return (far_x * far_x + far_y * far_y) <= radius * radius


def _keepout_blocks(
    keepout_rects: list[tuple[float, float, float, float]],
    cx: float, cy: float, w: float, h: float,
) -> bool:
    """True iff the chip's AABB overlaps any keepout rect."""
    chip_rect = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    return any(rects_overlap(chip_rect, ko) for ko in keepout_rects)


def _keepout_rects_from_geometry(
    board: Board,
    face: str = "top",
) -> list[tuple[float, float, float, float]]:
    """Extract AABB form (min_x, min_y, max_x, max_y) of every
    component-scope keepout on the board that applies to `face`.
    Non-component scopes (routing-only) are skipped — the packer only
    cares about placement exclusions.

    A keepout's `layers` selects which face(s) it applies to: `*.Cu`
    (the default) blocks both faces; `F.Cu` blocks only the top; `B.Cu`
    only the bottom. This lets a one-sided milled pocket (e.g. the piezo
    disk pocket on aft_end_board's top) reserve area on its own face
    without evicting parts on the solid opposite face."""
    g = board.geometry
    if g is None:
        return []
    want = "F.Cu" if face == "top" else "B.Cu"
    rects: list[tuple[float, float, float, float]] = []
    for ko in g.keepouts:
        if ko.scope not in ("component", "both"):
            continue
        layers = tuple(getattr(ko, "layers", ("*.Cu",)) or ("*.Cu",))
        if not ("*.Cu" in layers or want in layers):
            continue
        xs = [p[0] for p in ko.polygon]
        ys = [p[1] for p in ko.polygon]
        rects.append((min(xs), min(ys), max(xs), max(ys)))
    return rects


# ── core: one packing attempt with a given ordering ──────────────────

def _try_single_packing(
    ordering: list[Chip],
    already_placed: list[tuple[float, float, float, float]],
    keepout_rects: list[tuple[float, float, float, float]],
    *,
    outline_radius_mm: float | None,
    outline_xs: tuple[float, float] | None,
    outline_ys: tuple[float, float] | None,
    keep_region=None,
    flex_halfplanes: Sequence[tuple[float, float, float]] = (),
) -> tuple[dict, dict, float, list[tuple[float, float, float, float]]]:
    """One run of the packer. Returns
    (placements_rel, rotations_deg, max_reach, all_extents).

    `already_placed` is the list of locked-chip / cavity extents
    expressed as (cx, cy, w, h) tuples — these are obstacles, not
    things to move. The packer's own placements get appended to this
    list as it goes.
    """
    placements: dict = {}        # chip.ref → (rx, ry)
    rotations:  dict = {}        # chip.ref → 0 | 90
    # `extents` mixes three things, used by the candidate-search loop:
    # already-placed chips (collision + anchors), keepout AABBs (anchors
    # only — chip-vs-keepout collision is done via keepout_rects with
    # the rect-overlap test), and chips placed by *this* packing run.
    # `packed_only_extents` mirrors just the last category so the final
    # max_reach calculation isn't biased by edge-touching potting-hole
    # keepouts (whose AABBs extend marginally past the outline radius).
    extents = list(already_placed)
    for (kx1, ky1, kx2, ky2) in keepout_rects:
        kw = kx2 - kx1
        kh = ky2 - ky1
        extents.append(((kx1 + kx2) / 2.0, (ky1 + ky2) / 2.0, kw, kh))
    packed_only_extents: list[tuple[float, float, float, float]] = []

    def collides(x: float, y: float, w: float, h: float) -> bool:
        for px, py, pw, ph in extents:
            if (abs(x - px) < (w + pw) / 2 + COMP_GAP_MM
                    and abs(y - py) < (h + ph) / 2 + COMP_GAP_MM):
                return True
        if _keepout_blocks(keepout_rects, x, y, w, h):
            return True
        return False

    # Margin (mm) within which a chip is "near" a flex chord and needs the
    # exact polygon test; clear of every chord by this much, the analytic
    # half-plane bound already guarantees coverage (the only discrepancy is
    # the chord/arc fillet from the cavity's inward buffer, ≤ the wall).
    _NEAR_BAND = CAVITY_EDGE_WALL_MM + 0.5

    arc_keep = ((outline_radius_mm - CAVITY_EDGE_WALL_MM)
                if outline_radius_mm is not None else None)

    def inside_outline(x: float, y: float, w: float, h: float) -> bool:
        if outline_radius_mm is not None:
            if not _inside_outline_circle(outline_radius_mm, x, y, w, h):
                return False
            if keep_region is None:
                return True
            # The chip's cavity is clipped to (outline − flex chords) inset
            # by the edge wall; the chip must sit fully inside that region.
            # Fast path: analytic bounds (arc + each chord). Clear of every
            # boundary by _NEAR_BAND → accept; past any → reject; only in
            # the thin near-boundary band run the exact (prepared) polygon
            # test, where the cavity's inward-buffer fillet matters.
            far_x = abs(x) + w / 2.0
            far_y = abs(y) + h / 2.0
            reach = math.hypot(far_x, far_y)
            near = reach > arc_keep - _NEAR_BAND
            for nx, ny, lim in flex_halfplanes:
                proj = x * nx + y * ny + abs(w / 2 * nx) + abs(h / 2 * ny)
                if proj > lim:
                    return False
                if proj > lim - _NEAR_BAND:
                    near = True
            if near:
                return keep_region.contains(
                    _box(x - w / 2, y - h / 2, x + w / 2, y + h / 2))
            return True
        if outline_xs is not None and outline_ys is not None:
            return _polygon_contains_rect(outline_xs, outline_ys, x, y, w, h)
        return True  # no outline constraint

    for chip in ordering:
        # Try both cardinal orientations; keep the candidate closest
        # to the centre that's both inside the outline and collision-free.
        # The origin (0, 0) is always tried — it's the natural seat for
        # the first chip and remains a preferred candidate while a
        # central pocket is still empty. Anchor positions around every
        # already-placed extent (including keepouts, seeded above) are
        # also tested.
        best: tuple[float, float, int, float, float, float] | None = None
        for rot in (0, 90):
            w, h = _chip_extents(chip, rot)
            if (not collides(0.0, 0.0, w, h)
                    and inside_outline(0.0, 0.0, w, h)):
                if best is None or 0.0 < best[3]:
                    best = (0.0, 0.0, rot, 0.0, w, h)
            for (px, py, pw, ph) in extents:
                for ax, ay in _anchors_with_alignment(px, py, pw, ph, w, h):
                    if collides(ax, ay, w, h):
                        continue
                    if not inside_outline(ax, ay, w, h):
                        continue
                    d2 = ax * ax + ay * ay
                    if best is None or d2 < best[3]:
                        best = (ax, ay, rot, d2, w, h)

        if best is None:
            # Pathological fallback — no anchor fits. Drop the chip far
            # away so the run completes; max_reach will signal overflow.
            w0, h0 = _chip_extents(chip, 0)
            fallback_x = (outline_radius_mm or 0.0) * 4.0 + 100.0
            placements[chip.ref] = (fallback_x, 0.0)
            rotations[chip.ref]  = 0
            extents.append((fallback_x, 0.0, w0, h0))
            packed_only_extents.append((fallback_x, 0.0, w0, h0))
            continue

        x, y, rot, _, w, h = best
        placements[chip.ref] = (x, y)
        rotations[chip.ref]  = rot
        extents.append((x, y, w, h))
        packed_only_extents.append((x, y, w, h))

    # max_reach uses the tight corner-distance formula. Compute it
    # only over chips placed by this run — seeded keepout AABBs and
    # pre-existing locks aren't a packer overflow.
    max_reach = 0.0
    for cx, cy, w, h in packed_only_extents:
        far_x = abs(cx) + w / 2
        far_y = abs(cy) + h / 2
        max_reach = max(max_reach, math.hypot(far_x, far_y))

    return placements, rotations, max_reach, packed_only_extents


# ── public entry: multi-ordering search ──────────────────────────────

# ── cutout (spacer-cavity) cost model ──────────────────────────────────
# Each packed chip is milled out of the adjacent spacer. The packer ranks
# candidate packings by a weighted cutout cost rather than raw compactness:
#
#   cost = Σ_chips  area · (1 + EDGE_K · (reach/R)^EDGE_P · meridian_mult)
#
# - area keeps the total cutout small (tight pack).
# - (reach/R)^EDGE_P makes a rim cutout far more expensive than a central
#   one, so the cluster is pulled inward off the load-bearing rim.
# - meridian_mult multiplies that edge penalty where the cutout sits in
#   the angular sector of a flex launch — that rim is already thinned by
#   the flex chord, so notching it there is much worse.
EDGE_K = 4.0
EDGE_P = 2.0
MERIDIAN_MULT = 8.0
MERIDIAN_HALFWIDTH_DEG = 20.0


def _cutout_cost(
    placements: dict,
    rotations: dict,
    chip_by_ref: dict,
    outline_radius_mm: float | None,
    flex_dirs: Sequence[tuple[float, float]],
) -> float:
    """Weighted spacer-cavity cost for a packing (lower is better)."""
    R = outline_radius_mm
    cos_thresh = math.cos(math.radians(MERIDIAN_HALFWIDTH_DEG))
    total = 0.0
    for ref, (x, y) in placements.items():
        chip = chip_by_ref[ref]
        w, h = _chip_extents(chip, rotations.get(ref, 0.0))
        area = w * h
        if R and R > 0:
            reach = math.hypot(abs(x) + w / 2.0, abs(y) + h / 2.0)
            edge = min(1.0, reach / R) ** EDGE_P
        else:
            edge = 0.0
        mult = 1.0
        n = math.hypot(x, y)
        if edge and n > 1e-6 and flex_dirs:
            ux, uy = x / n, y / n
            if any(ux * fx + uy * fy >= cos_thresh for fx, fy in flex_dirs):
                mult = MERIDIAN_MULT
        total += area * (1.0 + EDGE_K * edge * mult)
    return total


def pack_radial(
    *,
    chips_to_place: Iterable[Chip],
    board: Board,
    already_placed: Iterable[Placement] = (),
    face: str = "top",
    n_random_orderings: int = 40,
    seed: int = 42,
    flex_dirs: Sequence[tuple[float, float]] = (),
    flex_chords: Sequence[tuple[float, float]] = (),
) -> tuple[list[Placement], float, bool]:
    """Pack `chips_to_place` into the available area on `board`.

    `already_placed` is the list of placements that already exist on
    the board (locked anchors, cavity-resident chips, etc.) — these are
    obstacles, but only the ones on the same `face` as the packer are
    used (top and bottom share the outline but don't collide with each
    other through the board).

    `face` is the mount side for everything packed in this call —
    "top" (default) or "bottom". The orchestrator typically calls
    pack_radial twice per board: once with face="top" for ICs/BGAs,
    once with face="bottom" for embeddable passives, test points, and
    mating pads. Each Placement returned carries this `face`.

    Returns `(new_placements, max_reach_mm, overflow)`. `overflow=True`
    means at least one chip ended up outside the outline-radius / rect.

    `flex_dirs` are unit vectors (placement frame, y-up) pointing from the
    board centre toward each flex launch — cutouts in those angular
    sectors are penalised hardest (see `_cutout_cost`).

    `flex_chords` are `(angle_deg, width_mm)` for each flex launch (same
    list the spacer's cavity clip uses). A chip's spacer cavity is clipped
    at each flex chord AND the outline arc, inset by CAVITY_EDGE_WALL_MM —
    so the packer holds every chip inside that same keep-region, else the
    cavity wouldn't fully cover the chip (it'd push against the flex wall).

    Search strategy: 3 deterministic orderings (area desc, longest-edge
    desc, perimeter desc) + N random shuffles. Keep the run with the
    lowest weighted cutout cost (`_cutout_cost`).
    """
    chips = list(chips_to_place)
    if not chips:
        return [], 0.0, False
    chip_by_ref = {c.ref: c for c in chips}

    g = board.geometry
    outline_radius_mm = g.outline_radius_mm if g else None
    outline_xs: tuple[float, float] | None = None
    outline_ys: tuple[float, float] | None = None
    if g and g.shape == "rect" and g.rect_dimensions is not None:
        w, h = g.rect_dimensions
        outline_radius_mm = None              # rect: use bbox check
        outline_xs = (-w / 2.0, w / 2.0)
        outline_ys = (-h / 2.0, h / 2.0)

    keepout_rects = _keepout_rects_from_geometry(board, face)

    # Keep-region matching the spacer cavity clip (outline minus the flex
    # chords, inset by the edge wall). The analytic half-planes are the
    # fast bound; the prepared polygon is the exact test for the thin
    # near-chord band where the cavity's inward-buffer fillet matters.
    #
    # Built whenever there's a circular outline — NOT only when flex chords
    # exist. With the snake flex removed `flex_chords` is empty, but the tile
    # still must keep chips off the board edge: `_spacer_keep_region(r, [])`
    # is the full Ø-circle inset by CAVITY_EDGE_WALL_MM, so the edge-wall
    # margin (and therefore overflow on an over-packed tile) is enforced on
    # every tile, not just flex tiles.
    keep_region = None
    flex_halfplanes: list[tuple[float, float, float]] = []
    if outline_radius_mm is not None:
        for ang, width in flex_chords:
            if 0.0 < width < 2.0 * outline_radius_mm:
                d = math.sqrt(outline_radius_mm ** 2 - (width / 2.0) ** 2)
                th = math.radians(ang)
                flex_halfplanes.append(
                    (math.cos(th), math.sin(th), d - CAVITY_EDGE_WALL_MM))
        region = _spacer_keep_region(outline_radius_mm, flex_chords)
        if not region.is_empty:
            keep_region = _prep(region)

    # Translate already-placed Placements on the SAME face to extents.
    # Top and bottom faces share the outline but parts on opposite
    # faces don't collide through the board — filter aggressively.
    obstacles: list[tuple[float, float, float, float]] = []
    for p in already_placed:
        if p.face != face:
            continue
        if not isinstance(p.item, (Chip, Antenna)) or p.item.footprint is None:
            continue
        lo_x, lo_y, hi_x, hi_y = placement_extents_mm(p, p.item.footprint)
        obstacles.append((
            (lo_x + hi_x) / 2.0,
            (lo_y + hi_y) / 2.0,
            hi_x - lo_x,
            hi_y - lo_y,
        ))

    # Sortable chip metadata (cached so we don't recompute extents in
    # every ordering)
    def _chip_w(c: Chip) -> float: return _chip_extents(c, 0)[0]
    def _chip_h(c: Chip) -> float: return _chip_extents(c, 0)[1]
    def _chip_area(c: Chip) -> float: return _chip_w(c) * _chip_h(c)

    orderings: list[list[Chip]] = [
        sorted(chips, key=lambda c: -_chip_area(c)),
        sorted(chips, key=lambda c: -max(_chip_w(c), _chip_h(c))),
        sorted(chips, key=lambda c: -(_chip_w(c) + _chip_h(c))),
    ]
    rng = random.Random(seed)
    for _ in range(n_random_orderings):
        order = list(chips)
        rng.shuffle(order)
        orderings.append(order)

    # Rank legal packs (nothing past the rim) by cutout cost; only if
    # EVERY ordering overflows do we fall back to the least-overflowing
    # one (min max_reach).
    best_legal: tuple[dict, dict, float, float] | None = None
    best_any: tuple[dict, dict, float, float] | None = None
    for ordering in orderings:
        placements, rotations, max_reach, _ = _try_single_packing(
            ordering, obstacles, keepout_rects,
            outline_radius_mm=outline_radius_mm,
            outline_xs=outline_xs,
            outline_ys=outline_ys,
            keep_region=keep_region,
            flex_halfplanes=flex_halfplanes,
        )
        cost = _cutout_cost(placements, rotations, chip_by_ref,
                            outline_radius_mm, flex_dirs)
        overflows = (outline_radius_mm is not None
                     and max_reach > outline_radius_mm)
        if not overflows and (best_legal is None or cost < best_legal[3]):
            best_legal = (placements, rotations, max_reach, cost)
        if best_any is None or max_reach < best_any[2]:
            best_any = (placements, rotations, max_reach, cost)

    best = best_legal if best_legal is not None else best_any
    assert best is not None
    pos_map, rot_map, max_reach, _cost = best

    # Build Placement records, indexed back to the original chip objects
    new_placements: list[Placement] = []
    for ref, (x, y) in pos_map.items():
        new_placements.append(Placement(
            position_mm=(x, y),
            rotation_deg=rot_map[ref],
            item=chip_by_ref[ref],
            face=face,
            locked=False,
        ))

    overflow = (outline_radius_mm is not None
                and max_reach > outline_radius_mm)
    return new_placements, max_reach, overflow
