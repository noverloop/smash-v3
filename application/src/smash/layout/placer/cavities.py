"""Cavity placement — compute spacer pockets from neighbour-tile chips.

For every spacer in the snake chain, mill a pocket on each face that
swallows the tall components on the adjacent rigid tile's facing side.
After folding the panel into the projectile sleeve, the rigid tile's
components sit inside the spacer's pocket — milling is the easier
manufacturing path (no spaghetti routing around tall parts on the back
side of the next tile).

Source-of-truth math lives in `smash.layout.cavities`:
  - `project_face_to_spacer(...)` — fold-mirror chip bboxes from a
    source tile's frame into the adjacent spacer's frame
  - `merge_cavity_polygons(...)` — union the per-chip rects + the
    diagonal NW→SE potting channel into one or more polygons

This module is the panel-walker that hooks those primitives into the
data model: it iterates each spacer in `panel.snake_chain`, gathers
chip placements from the prev (top-face source) and next (bottom-face
source) rigid tiles, and appends `Placement(item=CavityRegion(...))`
records to `spacer.cavity_placements`.
"""
from __future__ import annotations

from typing import Iterable

from shapely.ops import unary_union

from smash.layout.cavities import (
    POTTING_HOLE_DIA_MM,
    SPACER_CAVITY_DEPTH_TOP_MM,
    SPACER_THICKNESS_MM,
    clip_cavities_to_outline,
    fold_project,
    merge_cavity_polygons,
    project_face_to_spacer,
)
from smash.layout.placer.grid import footprint_bbox_mm
from smash.state.board import Board
from smash.state.board_geometry import Hole
from smash.state import Chip
from smash.state.antenna import Antenna
from smash.state.geometry.cavity import CavityRegion
from smash.state.topology.placement import Placement


def _source_components_dict(board: Board, source_side: str) -> dict:
    """Translate `board.chip_placements` into the dict shape that
    `project_face_to_spacer` expects.

    Skips placements whose chip has no footprint (project-internal
    pads without a real footprint bbox can't be cavity-cleared)."""
    out: dict = {}
    for p in board.chip_placements:
        if not isinstance(p.item, (Chip, Antenna)):
            continue
        if p.item.footprint is None:
            continue
        if p.face != source_side:
            continue
        lo_x, lo_y, hi_x, hi_y = footprint_bbox_mm(p.item.footprint)
        z = (p.item.height_mm
             or (p.item.footprint.height_mm if p.item.footprint else None))
        out[p.item.ref] = {
            "side":         p.face,
            "w_mm":         hi_x - lo_x,
            "h_mm":         hi_y - lo_y,
            "z_mm":         z,
            "rotation_deg": p.rotation_deg,
            "rx_mm":        p.position_mm[0],
            "ry_mm":        p.position_mm[1],
        }
    return out


# Fallback height for a footprint that carries no z (assume it needs the
# deeper pocket so we never under-mill).
_DEFAULT_CHIP_HEIGHT_MM = 2.0


def _split_by_height(source_dict: dict, thresh_mm: float) -> tuple[dict, dict]:
    """Partition a face's chips into (short, tall) at `thresh_mm`. Chips
    with unknown height assume the safe default and stay SHORT (pocketed,
    not cut through)."""
    short: dict = {}
    tall: dict = {}
    for k, v in source_dict.items():
        z = v.get("z_mm") or _DEFAULT_CHIP_HEIGHT_MM
        (tall if z > thresh_mm else short)[k] = v
    return short, tall


def _face_cavity_depth(source_dict: dict) -> float:
    """Uniform pocket depth for one tile face: the tallest chip on that
    face, rounded up to 1 mm or 2 mm (per the spacer's two pocket
    classes). Heights above 2 mm round to 2 mm and are reported by the
    caller — the 4 mm spacer budget only allows a 2 mm top pocket."""
    zs = [info.get("z_mm") or _DEFAULT_CHIP_HEIGHT_MM
          for info in source_dict.values()]
    tallest = max(zs) if zs else 0.0
    return 1.0 if tallest <= 1.0 else 2.0


def _project_potting_holes(board: Board, same_row: bool) -> list:
    """Fold-project a neighbour tile's potting holes into the adjacent
    spacer's local frame (math y-up). The spacer is mirrored relative to
    its neighbours by the accordion fold, so the projected positions —
    not the neighbour's raw NW/SE — are where the spacer must align."""
    if board is None or board.geometry is None:
        return []
    return [fold_project(h.position_mm[0], h.position_mm[1], same_row)
            for h in board.geometry.holes
            if getattr(h, "tag", None) == "potting"]


def _dedupe_points(pts, tol: float = 1e-3) -> list:
    """Drop near-coincident points (prev + next neighbours project to the
    same spot on a straight spacer; keep one)."""
    out: list = []
    for p in pts:
        if not any(abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol
                   for q in out):
            out.append(p)
    return out


def _polygon_to_region(
    poly, *, face: str, depth_mm: float, name: str,
) -> CavityRegion:
    """Translate a shapely Polygon → CavityRegion. Strips the closing
    duplicate point that shapely emits at the end of each ring."""
    exterior = [(x, y) for x, y in poly.exterior.coords][:-1]
    interiors = [
        [(x, y) for x, y in ring.coords][:-1]
        for ring in poly.interiors
    ]
    return CavityRegion(
        name=name,
        face=face,
        exterior_polygon=exterior,
        interior_holes=interiors,
        depth_mm=depth_mm,
    )


def _as_polys(geom) -> list:
    """Flatten a shapely (Multi)Polygon / GeometryCollection / empty into a
    list of non-empty Polygons."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in geom.geoms
            if g.geom_type == "Polygon" and not g.is_empty]


def _flex_chords(panel, spacer_name, i, chain, link_widths):
    """The (angle_deg, width_mm) of each flex launching off this spacer —
    one toward the prev tile, one toward the next. Angle is in the
    spacer's math-y-up local frame (grid row grows downward, so y flips).
    Used to clip cavities back from the flat flex-launch chord edges.

    When the panel carries no snake flex (`panel.snake_flex` False), the snake
    interfaces are joined by LGA lands instead — there is no launch cut, so no
    chord is returned and the full disc is available for cavities/lands."""
    import math
    if not getattr(panel, "snake_flex", True):
        return []
    sc, sr = panel.tiles[spacer_name]
    chords = []
    for nbr_i, link_k in ((i - 1, i - 1), (i + 1, i)):
        if not (0 <= nbr_i < len(chain)):
            continue
        nc, nr = panel.tiles[chain[nbr_i]]
        angle = math.degrees(math.atan2(-(nr - sr), nc - sc))
        # Links with no crossing nets are omitted from link_widths; the
        # flex still physically exists at a minimum width.
        w = link_widths.get(link_k, 3.0) if link_widths else 3.0
        chords.append((angle, w))
    return chords


def attach_cavities_to_spacers(
    panel,
    boards: dict,
    link_widths: dict | None = None,
) -> int:
    """For every spacer in the panel's snake chain, build CavityRegion
    records for both faces and append them to `spacer.cavity_placements`.

    Returns the number of CavityRegion entries added across all spacers
    — useful for sanity tests + diagnostics.

    `link_widths` maps snake-link index → flex width (mm) from
    `compute_link_widths`; used to clip cavities back from the flex-launch
    chord edges. Each spacer's `cavity_placements` is cleared first so
    this call is idempotent.
    """
    chain = panel.snake_chain or []
    n_added = 0
    for i, name in enumerate(chain):
        if name not in boards:
            continue
        spacer = boards[name]
        if not spacer.is_spacer:
            continue
        # Prev + next rigid tiles in the chain (guaranteed to exist
        # because spacers are always interposed between two rigids).
        prev_name = chain[i - 1] if i > 0 else None
        next_name = chain[i + 1] if i + 1 < len(chain) else None
        prev_board = boards.get(prev_name) if prev_name else None
        next_board = boards.get(next_name) if next_name else None

        # Wipe any previous cavity placements so this is re-runnable.
        spacer.cavity_placements.clear()

        radius = (spacer.geometry.outline_radius_mm
                  if spacer.geometry else None)
        chords = _flex_chords(panel, name, i, chain, link_widths)

        # Fold direction: row-equal → E-W fold (mirror in x);
        # col-equal → N-S fold (mirror in y). cavity_geom.fold_project
        # consumes the boolean directly.
        sp_col, sp_row = panel.tiles[name]
        prev_same_row = (panel.tiles[prev_name][1] == sp_row
                         if prev_name in panel.tiles else None)
        next_same_row = (panel.tiles[next_name][1] == sp_row
                         if next_name in panel.tiles else None)

        # Potting holes: project each RIGID neighbour's holes through the
        # fold. A spacer sits on one snake edge, so both its folds share an
        # axis and the two neighbours project to the same pair → dedupe to
        # two. Spacer neighbours (the battery run interleaves no boards) are
        # SKIPPED: projecting a sibling spacer's freshly-stamped holes
        # cascades a second, mirrored hole pair down the column, which
        # _apply_battery_bore then threads as an extra potting channel that
        # aligns with nothing on the rigid end tiles.
        potting_pts = []
        if prev_same_row is not None and not getattr(prev_board, "is_spacer",
                                                     False):
            potting_pts += _project_potting_holes(prev_board, prev_same_row)
        if next_same_row is not None and not getattr(next_board, "is_spacer",
                                                     False):
            potting_pts += _project_potting_holes(next_board, next_same_row)
        potting_pts = _dedupe_points(potting_pts)
        # Drill them as Ø2 NPTH through-holes (idempotent: replace prior).
        if spacer.geometry is not None:
            spacer.geometry.holes = [
                h for h in spacer.geometry.holes
                if getattr(h, "tag", None) != "potting"]
            for (x, y) in potting_pts:
                spacer.geometry.holes.append(Hole(
                    position_mm=(x, y), diameter_mm=POTTING_HOLE_DIA_MM,
                    plated=False, tag="potting"))

        # The radar↔nose spacer carries the milled metal-block through-window
        # (the waveguide/horn block passes through it). Every cavity on a spacer
        # is now unioned into one full-thickness through-cut (see the merge
        # policy below), so a diagonal potting channel here would be cut clean
        # through — slicing the spacer in half between the two potting holes,
        # across the block window. Drop the channel on this spacer; its two Ø2
        # potting through-holes alone vent/fill it (the holes are kept).
        no_potting_channel = (name == "spacer_radar_module_nose_cap")

        top_polys: list = []
        bot_polys: list = []
        tall_through: list = []          # chips taller than a face pocket

        # Chips taller than the deepest face pocket can't be cleared by a
        # blind pocket (they'd punch past the floor into the opposite
        # cavity), so cut them clean through the spacer instead.
        tall_thresh = SPACER_CAVITY_DEPTH_TOP_MM

        import os
        _dbg = (os.environ.get("SMASH_CAVITY_DEBUG") == name)
        if prev_board is not None and prev_same_row is not None:
            top_dict = _source_components_dict(prev_board, "top")
            short, tall = _split_by_height(top_dict, tall_thresh)
            if _dbg:
                for ref, info in sorted(top_dict.items()):
                    if abs(info["rx_mm"]) < 6 and info["ry_mm"] > 10:
                        print(f"CAVDBG prev-top {ref}: pos=({info['rx_mm']:.2f},"
                              f"{info['ry_mm']:.2f}) w={info['w_mm']:.2f} "
                              f"h={info['h_mm']:.2f} rot={info['rotation_deg']}"
                              f" z={info['z_mm']}")
            if short:
                rects = project_face_to_spacer(short, "top", prev_same_row)
                top_polys = clip_cavities_to_outline(
                    merge_cavity_polygons(rects, channel_endpoints=potting_pts,
                                          add_channel=not no_potting_channel),
                    radius, chords)
            if tall:
                rects = project_face_to_spacer(tall, "top", prev_same_row)
                tall_through += clip_cavities_to_outline(
                    merge_cavity_polygons(rects, add_channel=False),
                    radius, chords)

        if next_board is not None and next_same_row is not None:
            bot_dict = _source_components_dict(next_board, "bottom")
            short, tall = _split_by_height(bot_dict, tall_thresh)
            if short:
                rects = project_face_to_spacer(short, "bottom", next_same_row)
                bot_polys = clip_cavities_to_outline(
                    merge_cavity_polygons(rects, channel_endpoints=potting_pts,
                                          add_channel=not no_potting_channel),
                    radius, chords)
            if tall:
                rects = project_face_to_spacer(tall, "bottom", next_same_row)
                tall_through += clip_cavities_to_outline(
                    merge_cavity_polygons(rects, add_channel=False),
                    radius, chords)

        # Merge policy (EE direction): rather than mill opposing
        # partial-depth pockets — two shallow pockets on opposite faces
        # leave a thin, fragile FR4 web between the two neighbours' chips
        # and never read as an Edge.Cuts window — union every cavity region
        # for this spacer and cut it clean THROUGH the full thickness. The
        # chips on both neighbour faces share the spacer volume, so one
        # through window clears them all and yields a single clean,
        # manufacturable outline, cut at full spacer thickness.
        through_polys = _as_polys(
            unary_union(list(top_polys) + list(bot_polys) + tall_through))

        def _emit(polys, face, depth, tag):
            nonlocal n_added
            for j, poly in enumerate(polys):
                spacer.cavity_placements.append(Placement(
                    position_mm=(0.0, 0.0), rotation_deg=0, face=face,
                    item=_polygon_to_region(
                        poly, face=face, depth_mm=depth,
                        name=f"{name}__{tag}_{j}"),
                ))
                n_added += 1

        # Through-cut depth = this spacer's actual milled thickness (per-spacer
        # override when set, e.g. the thin radar↔nose_cap spacer; else uniform).
        _emit(through_polys, "through", spacer.thickness_mm, "through_cut")

    return n_added
