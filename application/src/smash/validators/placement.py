"""Placement validators — geometric sanity on a placed panel.

The packer guarantees its *own* packed chips don't collide, but LOCKED
placements (locked_placements.json) bypass that check entirely, so a
locked-vs-locked or locked-vs-packed overlap can slip through (this is
how the MPU/DDR3 courtyard overlap shipped). `check_chip_overlaps`
re-checks every placed chip on every board, locked and packed alike.

Courtyards are allowed to touch (COMP_GAP_MM = 0); only a genuine
interior overlap beyond `tol_mm` is reported.
"""
from __future__ import annotations

import dataclasses
import itertools

from smash.layout.placer.grid import (
    placement_extents_mm,
    placement_pad_extents_mm,
)
from smash.state.footprint import COURTYARD_CLEARANCE_MM


@dataclasses.dataclass(frozen=True)
class OverlapIssue:
    board: str
    face: str
    ref_a: str
    ref_b: str
    overlap_mm: tuple          # (dx, dy) interior overlap
    locked_a: bool = False     # ref_a's placement is locked
    locked_b: bool = False     # ref_b's placement is locked

    @property
    def involves_locked(self) -> bool:
        """At least one side is a locked placement — a hard defect (a
        locked part can't be moved to resolve the collision, so the
        generator must refuse it) rather than a packer near-miss."""
        return self.locked_a or self.locked_b

    def __str__(self) -> str:
        dx, dy = self.overlap_mm
        def _m(ref, lk):
            return f"{ref}{' [locked]' if lk else ''}"
        return (f"{self.board}/{self.face}: {_m(self.ref_a, self.locked_a)} "
                f"∩ {_m(self.ref_b, self.locked_b)} "
                f"overlap {dx:.2f}×{dy:.2f} mm")


def _overlap(r1, r2, tol):
    """Interior (dx, dy) overlap of two AABBs, or None if they only touch
    (within `tol`) or are disjoint."""
    dx = min(r1[2], r2[2]) - max(r1[0], r2[0])
    dy = min(r1[3], r2[3]) - max(r1[1], r2[1])
    if dx > tol and dy > tol:
        return (dx, dy)
    return None


def _placement_rects(p) -> list:
    """AABBs a placement occupies for overlap checking — usually the single
    courtyard AABB from `placement_extents_mm`.

    Multi-pad `manf == "project"` pseudo-parts (cell-contact triangle, pogo
    clusters) get one AABB **per pad** instead: their pads are sparse islands
    and the enveloping courtyard mostly covers empty board (P_CELL_CONTACTS'
    3 Ø6 pads at cluster r=8.6 span a ~20 mm box), which false-flags chips
    deliberately parked between the pads (the battery-facing faces keep
    everything inside the cell bores — see locked_placements.json). A chip
    ON one of the pads still collides with that pad's own AABB (ringed by
    COURTYARD_CLEARANCE_MM, same as an authored courtyard)."""
    fp = p.item.footprint
    if getattr(p.item, "manf", None) != "project" or len(fp.pads) < 2:
        return [placement_extents_mm(p, fp)]
    return placement_pad_extents_mm(p, fp, clearance_mm=COURTYARD_CLEARANCE_MM)


def check_chip_overlaps(boards: dict, *, tol_mm: float = 0.05,
                        include_pseudo: bool = True) -> list:
    """Return an `OverlapIssue` for every pair of chips whose courtyard
    AABBs overlap (beyond `tol_mm`) on the same board + face. Sparse
    multi-pad pseudo-parts are checked per pad (see `_placement_rects`).

    `boards` is the dict returned by build_panel after place_design has
    populated `chip_placements`. Empty list = clean.

    `include_pseudo=False` drops `manf == "project"` pseudo-parts (the
    34 mm spacer scaffold, the backbone LGA land arrays, cell-contact /
    pogo pads). Those carry no solderable component and are co-located
    by design — a spacer's land array necessarily sits on its scaffold —
    so they overlap legitimately and must not be mistaken for a real
    component collision.
    """
    issues: list = []
    for name, board in boards.items():
        placed = [p for p in board.chip_placements
                  if getattr(p.item, "footprint", None) is not None
                  and (include_pseudo
                       or getattr(p.item, "manf", None) != "project")]
        for face in ("top", "bottom"):
            on_face = [p for p in placed if p.face == face]
            rects = []
            for p in on_face:
                if p.item.footprint is None:
                    continue
                rects.append((p, _placement_rects(p)))
            for (pa, ras), (pb, rbs) in itertools.combinations(rects, 2):
                ov = max((o for ra in ras for rb in rbs
                          if (o := _overlap(ra, rb, tol_mm)) is not None),
                         key=lambda o: o[0] * o[1], default=None)
                if ov is not None:
                    issues.append(OverlapIssue(
                        board=name, face=face,
                        ref_a=pa.item.ref, ref_b=pb.item.ref,
                        overlap_mm=ov,
                        locked_a=bool(getattr(pa, "locked", False)),
                        locked_b=bool(getattr(pb, "locked", False))))
    return issues


class LockedOverlapError(RuntimeError):
    """A locked placement overlaps another placed component."""


def assert_no_locked_overlaps(boards: dict, *, tol_mm: float = 0.05) -> list:
    """Raise `LockedOverlapError` if any *locked* placement overlaps another
    component (locked or packed) on the same board + face; otherwise return
    the remaining packed-vs-packed overlaps (a soft signal the caller may
    warn on).

    A locked overlap is unrecoverable by the placer — the position is fixed
    by hand or by an imported reference layout — so it must hard-fail the
    build rather than warn. This is the guard that catches a reference layout
    locking an unplaced pile (e.g. the companion bottom decaps stacked at the
    origin) before its merged pads ship as power-to-GND shorts.

    Pseudo-parts (`manf == "project"`: spacer scaffolds, backbone land
    arrays) are excluded — their by-design coincidence is not a defect.
    """
    issues = check_chip_overlaps(boards, tol_mm=tol_mm, include_pseudo=False)
    locked = [i for i in issues if i.involves_locked]
    if locked:
        body = "\n".join(f"  {i}" for i in locked)
        raise LockedOverlapError(
            f"{len(locked)} locked-placement overlap(s):\n{body}")
    return issues


@dataclasses.dataclass(frozen=True)
class ClearanceIssue:
    """One chip that collides with a spacer's FR4 in the folded tower: its
    body bbox is not fully swallowed by any milled cavity on the mating
    face. `protrusion_mm2` is the body area overhanging into solid FR4."""
    spacer: str
    source_board: str
    face: str                  # spacer face the chip projects onto
    ref: str                   # the offending chip
    protrusion_mm2: float      # body area outside the cavity (mm²)
    protrusion_mm: tuple       # (dx, dy) extent of the protruding region

    def __str__(self) -> str:
        dx, dy = self.protrusion_mm
        return (f"{self.spacer} ← {self.source_board}/{self.ref}: "
                f"{self.protrusion_mm2:.2f} mm² ({dx:.2f}×{dy:.2f} mm) "
                f"into spacer FR4")


def check_spacer_chip_clearance(panel, boards: dict, *,
                                tol_mm2: float = 0.10) -> list:
    """Return a `ClearanceIssue` for every neighbour-tile chip whose body
    is not fully cleared by a spacer cavity — i.e. it collides with the
    spacer FR4 once the snake folds into the tower.

    For each spacer in `panel.snake_chain`, the cavity placer mills a
    through-window per facing chip (the prev tile's top face + the next
    tile's bottom face), then CLIPS those windows back from the disc edge
    (`CAVITY_EDGE_WALL_MM`) and the flex-launch chords. A chip sitting near
    either edge gets its window clipped while the chip body still extends
    past it — that overhang is the collision the user sees as red in the
    3D stack.

    This re-projects each chip's body bbox with the SAME fold-mirror math
    the placer uses (`fold_project` + `rotated_bbox_mm`), centred on the
    placement point exactly as the placer does — but WITHOUT the
    `CAVITY_MARGIN_MM` the placer pads the cavity with. So a clean chip
    (body ⊆ unclipped window) reads zero, and any protrusion is purely the
    edge/chord clip (or a dropped projection) eating into the chip's
    clearance. Skips backbone `LGA_lands` (flat copper pads placed AFTER
    the cavities — ~0 height, never a body collision).

    `panel` supplies `snake_chain` + `tiles`; `boards` is post-`place_design`
    (cavities attached). Empty list = every chip clears. Needs shapely.
    """
    from shapely.geometry import box, Polygon
    from shapely.ops import unary_union
    from smash.layout.cavities import fold_project, rotated_bbox_mm
    from smash.layout.placer.grid import footprint_bbox_mm

    issues: list = []
    chain = getattr(panel, "snake_chain", None) or []
    tiles = getattr(panel, "tiles", None) or {}

    for i, name in enumerate(chain):
        spacer = boards.get(name)
        if (spacer is None or not getattr(spacer, "is_spacer", False)
                or name not in tiles):
            continue

        # Union this spacer's milled cavities. The placer emits every region
        # at placement (0,0)/0° with the polygon already in the spacer's
        # local frame, so `exterior_polygon` is usable as-is.
        cav_polys = []
        for pl in spacer.cavity_placements:
            reg = getattr(pl, "item", None)
            ext = getattr(reg, "exterior_polygon", None)
            if not ext or len(ext) < 3:
                continue
            holes = [h for h in (getattr(reg, "interior_holes", None) or [])
                     if len(h) >= 3]
            poly = Polygon(ext, holes)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                cav_polys.append(poly)
        cavity_union = unary_union(cav_polys) if cav_polys else None

        sp_row = tiles[name][1]
        prev_name = chain[i - 1] if i > 0 else None
        next_name = chain[i + 1] if i + 1 < len(chain) else None

        # The faces that point INTO this spacer: prev tile's top + next tile's
        # bottom. Every board stacks F.Cu→nose (upright) and only the spacers
        # flip, so this fixed convention is correct (mirrors the placer's
        # attach_cavities_to_spacers).
        for nbr_name, side in ((prev_name, "top"), (next_name, "bottom")):
            nbr = boards.get(nbr_name) if nbr_name else None
            if nbr is None or nbr_name not in tiles:
                continue
            same_row = (tiles[nbr_name][1] == sp_row)
            for p in nbr.chip_placements:
                c = getattr(p, "item", None)
                fp = getattr(c, "footprint", None)
                if fp is None or p.face != side:
                    continue
                if getattr(c, "manf_pn", None) == "LGA_lands":
                    continue
                # Project pseudo-parts with no body height (cell contact pads,
                # pogo arrays) are flat copper on the surface, not a solid that
                # can collide with the spacer. Gated on manf=="project" so a real
                # part with height merely unset is still checked.
                if (getattr(c, "manf", None) == "project"
                        and not (getattr(c, "height_mm", None)
                                 or getattr(fp, "height_mm", None))):
                    continue
                lo_x, lo_y, hi_x, hi_y = footprint_bbox_mm(fp)
                w, h = hi_x - lo_x, hi_y - lo_y
                if w <= 0 or h <= 0:
                    continue
                w_eff, h_eff = rotated_bbox_mm(
                    w, h, getattr(p, "rotation_deg", 0) or 0)
                cx, cy = fold_project(
                    p.position_mm[0], p.position_mm[1], same_row)
                body = box(cx - w_eff / 2.0, cy - h_eff / 2.0,
                           cx + w_eff / 2.0, cy + h_eff / 2.0)
                prot = (body.difference(cavity_union)
                        if cavity_union is not None else body)
                if prot.is_empty or prot.area <= tol_mm2:
                    continue
                x0, y0, x1, y1 = prot.bounds
                issues.append(ClearanceIssue(
                    spacer=name, source_board=nbr_name, face=side,
                    ref=getattr(c, "ref", "?"),
                    protrusion_mm2=round(prot.area, 3),
                    protrusion_mm=(round(x1 - x0, 3), round(y1 - y0, 3))))
    return issues
