"""connectors — board-to-board ring-LGA interconnect.

Replaces the snake flexes with a ring of LGA pads on each Ø34 tile's
perimeter, soldered board-to-board (Eurocircuits: "the board acts as a
chip with a footprint that's aligned and soldered"). The FR4 spacer
between tiles becomes a vertical interposer carrying the backbone bus
through-via from face to face.

Geometry (see the plan file `the-flexes-…`):
  * Pads sit on a ring at `radius_mm` (~15 mm), inside the 17 mm edge.
  * The four CARDINAL sectors (N/S/E/W) are flex-launch zones — the board
    is notched there — so they are kept clear; pads live in the four
    DIAGONAL arcs between cardinals.
  * Self-keying (poka-yoke): the pad pattern is made rotationally UNIQUE
    so it can only mate one way —
      - dense pad clusters in the two potting-hole sectors (135°/315°),
      - a radial inner+outer KEY pad pair at one unique angle,
    which together break all rotational symmetry. Verified by
    `is_rotationally_unique()`.

Pinout (`backbone_pinout`) is GND-dominant: the shared control-bus pair
(GND-flanked), the 4 V rails + 3V3 multiplied for current, everything else GND
(current + clean return + isolation). The same map on every tile means
net X lands on the same pad everywhere, so the stack self-aligns.
"""
from __future__ import annotations

import math
import re

from smash.state import Chip, Pin, Footprint
from smash.state.pad import Pad
from smash.state.routing.via import Via

# ── ring geometry defaults ──────────────────────────────────────────────
RING_RADIUS_MM = 15.0           # pad-centre ring (inside the 17 mm edge)
PAD_D_MM = 1.0                  # round LGA pad Ø (board-to-board solder)
PAD_PITCH_MM = 2.5              # centre-to-centre along the arc
CARDINAL_KEEPOUT_DEG = 18.0     # half-width kept clear around each N/S/E/W
CARDINALS_DEG = (0.0, 90.0, 180.0, 270.0)      # E, N, W, S — flex-launch
POTTING_ANGLES_DEG = (135.0, 315.0)            # NW, SE potting holes
CLUSTER_INSET_MM = 3.0          # inner-row radius offset for clusters / key
DIAGONALS_DEG = (45.0, 135.0, 225.0, 315.0)    # arc centres

# Backbone nets carried by the ring (GND is the fill).
GND_NET = "GND"
_BACKBONE_MULTIPLICITY = [       # (net, pads) for the non-GND backbone
    ("SYS_I2C_SCL", 1), ("SYS_I2C_SDA", 1),     # shared control bus (ex-CAN)
    ("3V3", 3), ("BAT_PROT", 3), ("BAT_RAW", 3),
]


def _arc_angles(radius_mm: float, pitch_mm: float, keepout_deg: float) -> list[float]:
    """Equidistant pad angles (deg) in the four diagonal arcs, with the
    cardinal sectors (± `keepout_deg`) kept clear."""
    ang_pitch = math.degrees(pitch_mm / radius_mm)   # angular pitch per pad
    half = 45.0 - keepout_deg                        # arc half-width each side of a diagonal
    angles: list[float] = []
    for centre in DIAGONALS_DEG:
        n = int((2 * half) // ang_pitch)             # pads that fit in this arc
        span = n * ang_pitch
        start = centre - span / 2.0
        angles.extend(start + k * ang_pitch for k in range(n + 1))
    return angles


def _polar(radius_mm: float, angle_deg: float) -> tuple:
    a = math.radians(angle_deg)
    return (round(radius_mm * math.cos(a), 4), round(radius_mm * math.sin(a), 4))


def ring_lga_footprint(*, name: str = "RingLGA_Backbone",
                       radius_mm: float = RING_RADIUS_MM,
                       pad_d_mm: float = PAD_D_MM,
                       pitch_mm: float = PAD_PITCH_MM,
                       cardinal_keepout_deg: float = CARDINAL_KEEPOUT_DEG,
                       potting_angles: tuple = POTTING_ANGLES_DEG,
                       cluster_pads: int = 2,
                       radial_key_angle: float = 45.0) -> Footprint:
    """Build the self-keying ring-LGA `Footprint`.

    Pads (in stable index order): (1) the equidistant diagonal-arc base
    ring, (2) `cluster_pads` inner-row pads per potting-hole sector, (3) a
    single radial KEY pad (inner row) at `radial_key_angle` that breaks the
    residual 180° symmetry. Pad nums are "1".."N" in that order.
    """
    pads: list = []
    n = 1

    def add(angle, r):
        nonlocal n
        pads.append(Pad(num=str(n), position_mm=_polar(r, angle),
                        size_mm=(pad_d_mm, pad_d_mm), shape="round", layer="F.Cu"))
        n += 1

    # (1) base ring — equidistant in the diagonal arcs
    for a in _arc_angles(radius_mm, pitch_mm, cardinal_keepout_deg):
        add(a, radius_mm)
    # (2) potting-hole clusters — inner row, centred on each potting angle
    inner = radius_mm - CLUSTER_INSET_MM
    ang_pitch = math.degrees(pitch_mm / inner)
    for pa in potting_angles:
        start = pa - (cluster_pads - 1) * ang_pitch / 2.0
        for k in range(cluster_pads):
            add(start + k * ang_pitch, inner)
    # (3) radial key pad — single inner pad at a unique angle → breaks 180°
    add(radial_key_angle, inner)

    return Footprint(
        name=name, pads=pads, package_class="LGA (board-to-board ring)",
        pitch_mm=pitch_mm, size_mm=(2 * radius_mm, 2 * radius_mm),
        source="project (generated ring-LGA)",
        note="self-keying backbone interconnect ring; cardinals (N/S/E/W) "
             "kept clear for flex launches; potting-hole clusters + radial "
             "key pad make it one-way-mating",
    )


def backbone_pinout(pad_nums: list[str]) -> dict:
    """Map pad num → net for the backbone ring. GND-dominant; the shared
    control-bus pair is adjacent and GND-flanked; the 4 V rails + 3V3 are
    multiplied and spread for current. Deterministic for a given pad count."""
    pinout = {num: GND_NET for num in pad_nums}
    N = len(pad_nums)
    # Control-bus pair adjacent at indices 1,2 (index 0 and 3 stay GND flanks).
    if N >= 4:
        pinout[pad_nums[1]] = "SYS_I2C_SCL"
        pinout[pad_nums[2]] = "SYS_I2C_SDA"
    # Spread the 9 power pads across the remaining ring, GND between groups.
    power_pads = [net for net, cnt in _BACKBONE_MULTIPLICITY[2:] for _ in range(cnt)]
    free = [i for i in range(5, N) if i not in (1, 2)]
    if free and power_pads:
        step = max(1, len(free) // len(power_pads))
        for j, net in enumerate(power_pads):
            idx = free[min(j * step, len(free) - 1)]
            pinout[pad_nums[idx]] = net
    return pinout


def add_ring_lga(design, ref: str, *, board_tag: str, face: str = "top",
                 footprint: Footprint | None = None, **overrides) -> Chip:
    """Add a ring-LGA connector `Chip` to a board. `face` is advisory; the
    `P_`/`J_` ref prefix drives the placer's face split (P_*→bottom). The
    caller wires each pin to its backbone net via `backbone_pinout`."""
    fp = footprint or ring_lga_footprint()
    pins = [Pin(num=p.num, name=p.num) for p in fp.pads]
    fields = dict(
        manf="project", manf_pn="RingLGA_Backbone", name="RingLGA_Backbone",
        description=f"board-to-board backbone ring-LGA ({face} face)",
        footprint=fp, pins=pins,
        note="self-keying perimeter ring carrying the power/gnd/CAN backbone",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, board_tag=board_tag, **fields)


# ── self-keying verification (used by tests + DRC) ──────────────────────

# ════════════════════════════════════════════════════════════════════════
# Adaptive LGA-land placer — inject square solder lands into the FREE area of
# each board-to-board joint (around components / cavities / holes), instead of
# a fixed ring. Per joint, the land grid is the INTERSECTION of the two mating
# faces' free regions, so every land has flat contact on both sides.
# ════════════════════════════════════════════════════════════════════════

LAND_SIZE_MM = 0.9              # square LGA land side

# Solder-mask expansion for the TOP-face land fields (EE request, Sjoert's
# routed power_board 2026-09-28). The board default is 0 (aperture == copper),
# which the fab can't hold on the land array; the top field's apertures open
# 25 µm per side. Emitted per pad by the .kicad_pcb writer because KiCad's
# board-level `pad_to_mask_clearance` is global and a library footprint can't
# carry it either. Bottom (`P_`) fields keep the default — mask expansion
# there is a fab question that hasn't been asked yet.
LGA_TOP_MASK_EXPANSION_MM = 0.025
LGA_VIA_DRILL_MM = 0.3         # filled through-via drill joining top↔bottom land
LAND_PITCH_MM = 1.6             # land grid pitch (centre-to-centre)
LAND_EDGE_CLEARANCE_MM = 0.4    # land outer extent → board edge
LAND_KEEPOUT_MM = 0.3           # land → component / cavity / hole
_POTTING_KEEPOUT_HALF_MM = 2.8  # half-side of the square no-land zone around
                                # each potting hole (Ø3 hole + 4×4 mm board
                                # keepout; 2.8 keeps a clear ~1 mm gap from the
                                # hole so no land crowds the rim on either face)

# ── Backbone land-assignment policy ──────────────────────────────────────
# Each board-to-board joint carries exactly the nets that CROSS it (computed
# from the real netlist by smash.layout.interconnect.crossing_nets_by_gap),
# packed into that joint's free lands by `_assign_gap_lands`. Power rails get
# several lands for current sharing; every other crossing net gets one; GND
# fills the rest (return current + shielding). This guarantees by construction
# that every inter-board connection has a land on both mating faces — the
# property tools/connectivity_audit.py verifies.

# Nets that cross via dedicated RF / coax routing along the spine, NOT the
# single-ended digital LGA backbone (antenna feeds, Yagi splitter legs, NFC
# coil, WBA radio port). Excluded from land assignment.
_OFF_BACKBONE_RE = re.compile(r"ANT|YAGI|WILK|NFC_AC|(?:^|_)RF(?:$|_)")

# Lands per power rail (current sharing). Named overrides for the heavy
# always-on rails; every other power net gets _POWER_MULT, every signal 1.
_POWER_MULT = 2
_RAIL_MULT = {"3V3": 3, "BAT_PROT": 2, "BAT_RAW": 2}

# Adaptive land density: a CROWDED joint (a tile-edge chip — e.g. the DDR4 in
# companion's NE corner — shrinks the joint's free region) re-packs at a finer
# pitch until every crossing net still gets a land, rather than silently
# dropping nets. Only joints that overflow at the default pitch densify; the
# land side stays LAND_SIZE_MM, so the floor pitch (1.27 mm) keeps a ~0.37 mm
# inter-land gap. The fold(Q) on each tile densifies with Q, so the mate stays
# pad-to-pad.
_LAND_PITCH_LADDER = (1.45, 1.35, 1.27)


def is_off_backbone(net_name: str) -> bool:
    """True for RF/coax nets that route along the spine, not over LGA lands."""
    return bool(_OFF_BACKBONE_RE.search(net_name))


def _rail_land_count(name: str) -> int:
    return _RAIL_MULT.get(name, _POWER_MULT)


def _spacer_keepout(spacer):
    """Merged land-keepout for a spacer joint = union of ALL its milled
    cavities (top + bottom faces — a cavity clears the facing tile's
    components, so the union covers both tiles) + a square zone around each
    REAL potting hole.

    Both the cavity polygons and the potting holes are read from the spacer's
    OWN placed geometry, which already bakes in the spacer's fold-projection
    and face-flip. A hard-coded math-y-up hole position would land on the
    wrong diagonal once the spacer is flipped — avoiding a phantom hole while
    leaving the real holes exposed (the observed overflow + rotation bug).

    Merging both faces is also what makes the interposer work: a land must
    have flat copper on BOTH spacer faces to carry the bus through-via, so it
    must avoid any cavity on either face. Returns a shapely geometry (or None)."""
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    regions = []
    for pl in spacer.cavity_placements:
        ext = getattr(pl.item, "exterior_polygon", None)   # NOT .polygon
        if not ext:
            continue
        cx, cy = pl.position_mm
        regions.append(Polygon([(px + cx, py + cy) for px, py in ext])
                       .buffer(LAND_KEEPOUT_MM))
    geom = spacer.geometry
    if geom is not None:
        h = _POTTING_KEEPOUT_HALF_MM
        for hole in geom.holes:
            if getattr(hole, "tag", None) != "potting":
                continue
            hx, hy = hole.position_mm
            regions.append(box(hx - h, hy - h, hx + h, hy + h))
    return unary_union(regions) if regions else None


_BRANCH_KEEPOUT_W_MM = 8.0      # launch-mouth width kept clear for a branch flex
_BRANCH_KEEPOUT_DEPTH_MM = 4.0  # how far in from the rim the mouth is cleared


def _branch_launch_keepout(tile, panel):
    """Keepout box at each BRANCH-flex launch mouth on `tile`. Branch flexes
    (nfc / yagi / qpd / camera) leave the parent tile's N or S edge radially,
    so a land at that mouth would foul the strip. The spacer-derived joint
    keepout only knows the snake flexes, not these tile-local branches, so we
    add them here. Launch angle uses the same grid convention as `_flex_chords`
    (`atan2(-Δrow, Δcol)`; grid row grows downward). Returns a geometry or None."""
    from shapely.geometry import box
    from shapely import affinity
    from shapely.ops import unary_union
    if tile.geometry is None or panel.tiles is None:
        return None
    tcr = panel.tiles.get(tile.name)
    if tcr is None:
        return None
    tcol, trow = tcr
    r = tile.geometry.outline_radius_mm
    w = _BRANCH_KEEPOUT_W_MM
    regs = []
    for parent, leaf in (panel.branches or []):
        if parent != tile.name:
            continue
        lcr = panel.tiles.get(leaf)
        if lcr is None:
            continue
        lcol, lrow = lcr
        ang = math.degrees(math.atan2(-(lrow - trow), lcol - tcol))
        # Box on the +x rim (r-depth … past the edge), rotated to the launch.
        mouth = box(r - _BRANCH_KEEPOUT_DEPTH_MM, -w / 2.0, r + 1.0, w / 2.0)
        regs.append(affinity.rotate(mouth, ang, origin=(0.0, 0.0)))
    return unary_union(regs) if regs else None


def _straddle_keepout(tile):
    """Tile-frame union of the courtyards of MID-MOUNT components on `tile` — a
    part whose body straddles the board, embedded ~50% (the nose_cap USB-C). It
    mounts on the OUTER face and its body protrudes AWAY from the spacer, so it
    spawns NO milled cavity and the cavity-derived free region misses it — yet an
    LGA land on the mating (opposite) face would sit directly under the embedded
    body, which can't mate. The mid-mount THROUGH notch is already a cavity; this
    holds lands out of the full connector body courtyard around it. Same
    tile-centred frame as `_branch_launch_keepout` (so it composes with
    `_fold_reflect`). Mid-mount parts are flagged by `MSMT` (Mid-mount SMT) in
    the part number / package. Returns a geometry or None."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    from smash.layout.placer.grid import placement_extents_mm
    regs = []
    for pl in tile.chip_placements:
        chip = pl.item
        sig = ((getattr(chip, "manf_pn", None) or "") + " "
               + (getattr(chip, "package", None) or "")).lower()
        if "msmt" not in sig and "mid-mount" not in sig:
            continue
        fp = getattr(chip, "footprint", None)
        if fp is None:
            continue
        try:
            lo_x, lo_y, hi_x, hi_y = placement_extents_mm(pl, fp)
        except Exception:
            continue
        regs.append(box(lo_x - LAND_KEEPOUT_MM, lo_y - LAND_KEEPOUT_MM,
                        hi_x + LAND_KEEPOUT_MM, hi_y + LAND_KEEPOUT_MM))
    return unary_union(regs) if regs else None


def _tile_keepout_components(tile, face, *, mirror):
    """Constituent land-keepouts on `tile`'s `face`, in the LGA local frame: one
    (label, box) per component courtyard + one per potting hole. `_tile_component_
    keepout` unions these. Frame handling: mirror X for a bottom-mating tile.
    EXCLUDES the cell via-tabs (P_CELL_TAB*) — they sit within the cell bore
    (battery compartment), so the bore already covers them and they need no extra
    keepout. LGA land chips ('LGA_lands') are skipped. Sparse multi-pad project
    pseudo-parts (P_CELL_CONTACTS' cell-centre triangle) contribute one box per
    PAD, not their enveloping courtyard — the envelope spans the empty board
    between the pads (for the contact triangle: the whole inter-lobe valley
    ring) and starved joints of lands there for no physical reason."""
    from shapely.geometry import box
    from smash.layout.placer.grid import (placement_extents_mm,
                                          placement_pad_extents_mm)
    out = []
    for pl in tile.chip_placements:
        if getattr(pl, "face", None) != face:
            continue
        chip = pl.item
        ref = getattr(chip, "ref", "") or "chip"
        if getattr(chip, "manf_pn", None) == "LGA_lands":
            continue
        if ref.startswith("P_CELL_TAB"):     # within the cell bore — no extra keepout
            continue
        fp = getattr(chip, "footprint", None)
        if fp is None:
            continue
        try:
            if getattr(chip, "manf", None) == "project" and len(fp.pads) >= 2:
                rects = [(f"{ref}[pad{i + 1}]", r) for i, r in
                         enumerate(placement_pad_extents_mm(pl, fp))]
            else:
                rects = [(ref, placement_extents_mm(pl, fp))]
        except Exception:
            continue
        for lbl, (lo_x, lo_y, hi_x, hi_y) in rects:
            if mirror:
                lo_x, hi_x = -hi_x, -lo_x
            out.append((lbl, box(lo_x - LAND_KEEPOUT_MM, lo_y - LAND_KEEPOUT_MM,
                                 hi_x + LAND_KEEPOUT_MM, hi_y + LAND_KEEPOUT_MM)))
    # The tile's OWN potting holes sit at its un-projected angles (135°/315°),
    # NOT the spacer's fold-projected ones — so they too must be cleared in the
    # tile frame (mirror in X for a bottom-mating face, as for components).
    geom = tile.geometry
    if geom is not None:
        h = _POTTING_KEEPOUT_HALF_MM
        for hole in geom.holes:
            if getattr(hole, "tag", None) != "potting":
                continue
            hx, hy = hole.position_mm
            if mirror:
                hx = -hx
            out.append(("potting hole", box(hx - h, hy - h, hx + h, hy + h)))
    return out


def _tile_component_keepout(tile, face, *, mirror):
    """Union of component-courtyard AABBs + potting-hole boxes on `tile`'s `face`
    (LGA local frame) — see `_tile_keepout_components` for the per-piece detail
    and frame handling. A land can't sit on a short chip or potting hole even
    where no milled cavity exists, so these clear the joint."""
    from shapely.ops import unary_union
    regs = [g for _, g in _tile_keepout_components(tile, face, mirror=mirror)]
    return unary_union(regs) if regs else None


def _tile_cavity_keepout(tile, face):
    """Union of the tile's milled cavity polygons on its mating `face`
    (tile-local frame). A land over a blind pocket or through-cut has no flat
    contact, so these must be cleared from the joint — but UNLIKE components
    they spawn no projected spacer cavity (they're appended post-place, e.g.
    the Ø24 piezo-disk pocket on aft_end_board's top), so the spacer-derived
    free region misses them. A `through` cavity blocks both faces."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    regs = []
    for pl in (getattr(tile, "cavity_placements", None) or []):
        region = getattr(pl, "item", None)
        poly = getattr(region, "exterior_polygon", None)
        if not poly:
            continue
        cav_face = getattr(region, "face", None) or getattr(pl, "face", "top")
        if cav_face not in (face, "through"):
            continue
        px, py = pl.position_mm
        regs.append(Polygon([(x + px, y + py) for x, y in poly]))
    return unary_union(regs) if regs else None


def _joint_free_region(spacer, panel, chain, link_widths):
    """Landable region of a spacer joint = the spacer's true keep-region
    (outline circle minus each flex-launch chord, inset by the cavity edge
    wall) minus the merged cavity + potting-hole keepout. Basing it on the
    flex-chord-aware keep-region is what holds lands out of the flex-launch
    zones — the board is physically notched there, so a land would hang off
    the cut edge. Same region for both spacer faces, so its two land arrays
    align → the through-via connects pad-to-pad."""
    from smash.layout.cavities import _spacer_keep_region
    from smash.layout.placer.cavities import _flex_chords
    r = spacer.geometry.outline_radius_mm
    idx = chain.index(spacer.name)
    chords = _flex_chords(panel, spacer.name, idx, chain, link_widths)
    free = _spacer_keep_region(r, chords)
    ko = _spacer_keepout(spacer)
    if ko is not None:
        free = free.difference(ko)
    return free


def _grid_pack(region, *, size=LAND_SIZE_MM, pitch=LAND_PITCH_MM):
    """Square-land centres on a pitch grid whose full footprint fits inside
    `region`. Returns [(x, y), …] sorted for determinism."""
    from shapely.geometry import box
    if region.is_empty:
        return []
    minx, miny, maxx, maxy = region.bounds
    pts, y = [], miny + size / 2.0
    while y <= maxy:
        x = minx + size / 2.0
        while x <= maxx:
            # Round first, then test, so the STORED centre is the one proven
            # to fit (avoids sub-micron boundary lands slipping the check).
            cx, cy = round(x, 3), round(y, 3)
            if region.contains(box(cx - size / 2, cy - size / 2,
                                   cx + size / 2, cy + size / 2)):
                pts.append((cx, cy))
            x += pitch
        y += pitch
    return sorted(pts)


def _lands_footprint(name: str, positions: list) -> Footprint:
    pads = [Pad(num=str(i + 1), position_mm=p, size_mm=(LAND_SIZE_MM, LAND_SIZE_MM),
                shape="rect", layer="F.Cu") for i, p in enumerate(positions)]
    return Footprint(name=name, pads=pads,
                     package_class="LGA (board-to-board land array)",
                     source="project (adaptive land placer)",
                     note="square solder lands packed into the joint free area")


# Differential land pairs: nets that MUST occupy physically adjacent lands so
# their go/return currents cancel. The fin coil phases are the case that
# matters — each DRV8428E bridge drives one coil between AOUT1/AOUT2 (and
# BOUT1/BOUT2), and those phases cross ~22 LGA lands to reach the drivers on
# fin_ble_board. Split the pair and you get a PWM-switched loop the length of
# the joint instead of a tight one: the raster pack put FIN3_BOUT1/BOUT2
# 28.8 mm apart (vs a 1.60 mm pitch) before this pass existed.
_LAND_PAIR_RE = re.compile(r'^(FIN\d+)_([AB])OUT1$')


def _pair_partner(net: str) -> str | None:
    m = _LAND_PAIR_RE.match(net or "")
    return f"{m.group(1)}_{m.group(2)}OUT2" if m else None


def _pair_adjacent_lands(Q, net_list) -> int:
    """Re-seat differential pairs onto physically adjacent lands, in place.

    `Q[i]` is land i's position, `net_list[i]` its net. `_assign_gap_lands`
    packs by index with no knowledge of geometry, so a pair that is adjacent
    in the list can land at opposite ends of the raster — FIN3_BOUT1/BOUT2
    came out 28.8 mm apart on a 1.60 mm pitch.

    Any land is as good as any other for a net that is not a differential
    leg (GND filler, the multiplied power rails, ordinary single-ended
    signals), so pairs are made adjacent by PERMUTING assignments: nothing
    gains or loses a land. Two strategies, in order:
      1. move the partner next to leg 1, displacing that land's net into the
         partner's old slot;
      2. if leg 1 has no relocatable neighbour (it is boxed in by other
         pairs), move BOTH legs onto a free adjacent slot pair and push the
         two displaced nets into the legs' old slots.
    Returns the number of pairs re-seated."""
    if not Q or len(Q) < 2:
        return 0

    def dist(a, b):
        return math.hypot(Q[a][0] - Q[b][0], Q[a][1] - Q[b][1])

    n = len(Q)
    pitch = min((dist(a, b) for a in range(n) for b in range(a + 1, n)),
                default=0.0)
    if pitch <= 0:
        return 0
    near = pitch * 1.5
    nbrs = {i: [j for j in range(n) if j != i and dist(i, j) <= near]
            for i in range(n)}

    # Both legs of every pair present on this joint are protected from being
    # displaced; everything else may be moved freely.
    legs = set()
    for net in net_list:
        p = _pair_partner(net)
        if p and p in net_list:
            legs.add(net)
            legs.add(p)

    fixed = 0
    for net in sorted(legs):
        partner = _pair_partner(net)
        if partner is None or partner not in net_list or net not in net_list:
            continue
        i1, i2 = net_list.index(net), net_list.index(partner)
        if dist(i1, i2) <= near:
            continue
        # (1) slide the partner in beside leg 1
        cand = [j for j in nbrs[i1] if j != i2 and net_list[j] not in legs]
        if cand:
            j = min(cand, key=lambda k: dist(i1, k))
            net_list[j], net_list[i2] = net_list[i2], net_list[j]
            fixed += 1
            continue
        # (2) leg 1 is boxed in — move the whole pair to a free adjacent slot
        slot = None
        for a in range(n):
            if net_list[a] in legs:
                continue
            for b in nbrs[a]:
                if b != a and net_list[b] not in legs:
                    slot = (a, b)
                    break
            if slot:
                break
        if slot is None:
            continue
        a, b = slot
        net_list[a], net_list[i1] = net_list[i1], net_list[a]
        i2 = net_list.index(partner)          # may have shifted in the swap
        net_list[b], net_list[i2] = net_list[i2], net_list[b]
        fixed += 1
    return fixed


def _assign_gap_lands(crossing, budget: int, kind_of: dict) -> tuple:
    """Ordered net-per-land list for one joint's `budget` lands.

    Every crossing net (minus RF/off-backbone) gets ≥1 land FIRST — that is
    what makes the connectivity audit pass. Leftover lands add current-sharing
    copies of the power rails, then GND fills the remainder. Returns
    ``(plan, overflow)`` where `overflow` is any crossing net that did not fit
    (should be empty; the caller emits a warning if not — never silent)."""
    nets = sorted(n for n in crossing
                  if n != GND_NET and not is_off_backbone(n))
    overflow = nets[budget:]                  # pathological: more nets than lands
    plan = nets[:budget]
    # Spend remaining lands on extra power-rail copies (current sharing),
    # round-robin by copy index: every rail gets its 2nd land before any
    # rail gets a 3rd. On a shrinking joint the heavy rails then degrade
    # LAST and together — the old plan-order loop starved BAT_RAW's (5 A
    # pack feed) redundancy while 3V3 kept a 3rd copy.
    if len(plan) < budget:
        rails = sorted((n for n in plan if kind_of.get(n) == "power"),
                       key=lambda n: (-_rail_land_count(n), n))
        rnd = 1
        while len(plan) < budget:
            added = False
            for n in rails:
                if len(plan) >= budget:
                    break
                if _rail_land_count(n) - 1 >= rnd:
                    plan.append(n)
                    added = True
            if not added:
                break
            rnd += 1
    # GND fills the rest (return current + shield + isolation).
    if len(plan) < budget:
        plan += [GND_NET] * (budget - len(plan))
    return plan, overflow


def is_rotationally_unique(footprint: Footprint, *, tol_mm: float = 0.05) -> bool:
    """True iff no NON-identity rotation maps the pad set onto itself — i.e.
    the ring can only mate in one orientation. Sweeps candidate angles
    (the 4-fold base lattice + a fine sweep) and checks for a match."""
    pts = [p.position_mm for p in footprint.pads]
    def matches(angle_deg: float) -> bool:
        a = math.radians(angle_deg)
        ca, sa = math.cos(a), math.sin(a)
        rot = [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]
        for rx, ry in rot:
            if not any(abs(rx - x) <= tol_mm and abs(ry - y) <= tol_mm
                       for x, y in pts):
                return False
        return True
    # any non-zero angle (sampled every 1°) that reproduces the set → ambiguous
    return not any(matches(a) for a in range(1, 360))


def _fold(pts, same_row):
    """Reflect across the snake fold, reusing the SAME transform that places
    the potting holes and projects the cavities (`fold_project`): x mirrors on
    a same-row (E-W) fold, y on a same-col (N-S) fold. `fold_project` is its
    own inverse, so applying it round-trips a spacer-frame point to the
    neighbour-tile frame and back."""
    return [(-x, y) if same_row else (x, -y) for x, y in pts]


def _fold_reflect(geom, same_row):
    """Shapely-geometry version of `_fold` — reflect a keepout polygon across
    the fold so a tile-frame keepout can be expressed in the spacer frame."""
    from shapely import affinity
    return (affinity.scale(geom, xfact=-1.0, yfact=1.0, origin=(0.0, 0.0))
            if same_row else
            affinity.scale(geom, xfact=1.0, yfact=-1.0, origin=(0.0, 0.0)))


# ── battery-compartment shared column lands ─────────────────────────────
def _battery_column_lands(boards, panel, chain) -> tuple | None:
    """Shared LGA land centres for the battery compartment (BOTH modes —
    the single-cell rectangle and the 3-cell trefoil), in the common spacer
    frame — or None when this build has no battery run.

    Every `spacer_battery_*` tile is the same Ø34 disc in the same snake row, so
    ONE pattern serves the whole column; the identical lands on each spacer are
    what make the interposer through-vias stack pad-to-pad up the cell stack
    (the per-spacer grid-pack gave each a slightly different pattern → no clean
    via column, and the tightest spacer dropped crossing nets; in triple mode
    the mid-column joints matched ZERO pads and every backbone/GND via
    dead-ended in bare FR4). The landable region subtracts the cell-bore union
    (which includes spacer_battery_1's potting-channel fingers, keeping lands
    off the threaded holes) AND both rigid END tiles' component + cavity
    courtyards (battery-floor top face, activation bottom face — folded into
    the spacer frame), because `_mark_battery_pockets` clears each spacer's
    milled cavities down to the bare bore, leaving the spacers otherwise blind
    to the cell contacts / solder tabs / comparator they fold onto."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    batt = [boards[n] for n in chain
            if n.startswith("spacer_battery") and boards.get(n) is not None]
    if not batt:
        return None
    # cell bore on each spacer (union covers spacer_battery_1's potting finger).
    # Only the bore itself — NOT any preserved neighbour-chip clearance cut on
    # the aft-most spacer — so the single-cell shape test below stays a clean
    # rectangle (the comparator parts are cleared from the land region anyway,
    # via the aft_end component keepout below).
    bores = []
    for b in batt:
        for pl in b.cavity_placements:
            if getattr(pl.item, "name", None) != "cell_bores_merged":
                continue
            poly = getattr(pl.item, "exterior_polygon", None)
            if poly:
                bores.append(Polygon([(x, y) for x, y in poly]))
    if not bores:
        return None
    cell = unary_union(bores)
    ref = batt[0]
    r = ref.geometry.outline_radius_mm
    sp_row = panel.tiles[ref.name][1] if panel.tiles else None
    ko = [cell]
    # The two rigid tiles bracketing the column — their parts must be cleared in
    # the spacer frame so the folded lands don't foul them on either end tile.
    i0 = chain.index(batt[0].name)
    iN = chain.index(batt[-1].name) + 1
    before = boards[chain[i0 - 1]] if i0 > 0 else None
    after = boards[chain[iN]] if iN < len(chain) else None
    for nb, nb_face in ((before, "top"), (after, "bottom")):
        if nb is None or nb.is_spacer:
            continue
        sr = (panel.tiles[nb.name][1] == sp_row) if panel.tiles else True
        for g in (_tile_component_keepout(nb, nb_face, mirror=False),
                  _tile_cavity_keepout(nb, nb_face)):
            if g is not None and not g.is_empty:
                ko.append(_fold_reflect(g, sr))
    free = Point(0.0, 0.0).buffer(r - LAND_EDGE_CLEARANCE_MM)
    free = free.difference(unary_union(ko).buffer(LAND_KEEPOUT_MM))
    # No cardinal-wedge restriction: whatever ring the bore union leaves free
    # (diagonal corners for the axis-aligned single cell, the inter-lobe
    # valleys + rim ring for the trefoil) is packed with lands. (The old
    # cardinal-only pattern was for the DIAGONAL cell, whose rotated rectangle +
    # on-axis contacts blocked the diagonals.) The free region is returned
    # alongside the pattern so a crowded column can densify — every battery
    # spacer densifies from this SAME region + the SAME gap crossing set, so
    # the refined pattern stays identical up the column.
    return _grid_pack(free), free


def _emit_land_field(design, board_obj, ref, foot_pts, net_list, face, *,
                     connect):
    """Create one LGA_lands chip on `board_obj` with pads at `foot_pts`
    carrying `net_list`, and place it on `face` (locked, board origin).
    Shared by the fresh computation and the reference replay, so a config
    that inherits the maximalist pattern emits byte-identical fields.

    `foot_pts` is the INTENDED board-local (world) pattern. Bottom-face
    placements are X-mirrored by the model (`world_pad_position`) and the
    exporter bakes the same flip, so pre-mirror the pattern here: pad i
    then lands at foot_pts[i] in world coords on either face — over the
    spacer through-via / mating pad it must join."""
    from smash.state.topology.placement import Placement
    if face == "bottom":
        foot_pts = [(-x, y) for (x, y) in foot_pts]
    fp = _lands_footprint(ref, foot_pts)
    if face == "top":
        for pad in fp.pads:
            pad.solder_mask_expansion_mm = LGA_TOP_MASK_EXPANSION_MM
    chip = design.add_chip(
        ref=ref, board_tag=board_obj.name, manf="project",
        manf_pn="LGA_lands", name="LGA_lands", footprint=fp,
        pins=[Pin(num=p.num, name=p.num) for p in fp.pads],
        note="adaptive board-to-board backbone lands")
    for j, pin in enumerate(chip.pins):
        net = net_list[j] if j < len(net_list) else GND_NET
        connect(net, chip.pin(pin.num))
    board_obj.chip_placements.append(Placement(
        position_mm=(0.0, 0.0), rotation_deg=0.0, item=chip,
        face=face, locked=True))
    return chip


def _pack_joint_nets(Q, free, crossing, kind_of, name) -> tuple:
    """Assign `crossing` nets to the raster-packed lands `Q` of joint `name`,
    densifying from `free` if they overflow and re-seating differential
    pairs. Returns ``(Q, net_list)`` — Q may be the denser re-pack."""
    import sys
    net_list, overflow = _assign_gap_lands(crossing, len(Q), kind_of)
    if overflow and free is not None:
        # Crowded joint: densify (finer pitch) until every crossing net
        # lands. Keep the densest pack tried even if a step still
        # overflows. (Battery-column joints densify from the column's
        # SHARED free region + shared gap crossing set, so all of them
        # refine to the same denser pattern and stay pad-matched.)
        for fine in _LAND_PITCH_LADDER:
            Qf = _grid_pack(free, pitch=fine)
            if len(Qf) <= len(Q):
                continue
            nl, ov = _assign_gap_lands(crossing, len(Qf), kind_of)
            Q, net_list, overflow = Qf, nl, ov
            if not ov:
                break
    if overflow:
        print(f"  WARNING: LGA joint {name}: {len(overflow)} crossing "
              f"net(s) exceed {len(Q)} lands, NOT carried: "
              f"{', '.join(sorted(overflow))}", file=sys.stderr)

    # Differential coil pairs onto adjacent lands before anything is
    # emitted — the four mating faces all index the same net_list, so
    # fixing it here fixes the spacer, both tiles and the through-vias.
    _pair_adjacent_lands(Q, net_list)
    return Q, net_list


def _check_pinned_joint(name, Q, net_list, free, crossing) -> None:
    """Warn (never fix) where an EE-pinned land field disagrees with the
    stackup: a land not wholly inside the joint's free region (it would sit
    over a cavity, potting hole or flex mouth), or a crossing net the field
    doesn't carry."""
    import sys
    from shapely.geometry import box
    h = LAND_SIZE_MM / 2.0
    if free is not None:
        bad = [(i + 1, x, y, net_list[i]) for i, (x, y) in enumerate(Q)
               if not free.contains(box(x - h, y - h, x + h, y + h))]
        for n, x, y, net in bad:
            print(f"  WARNING: LGA joint {name}: pinned land {n} ({net}) at "
                  f"spacer ({x:.3f}, {y:.3f}) is outside the joint free "
                  f"region", file=sys.stderr)
    carried = set(net_list)
    missing = sorted(n for n in crossing
                     if n != GND_NET and not is_off_backbone(n)
                     and n not in carried)
    if missing:
        print(f"  WARNING: LGA joint {name}: pinned field does not carry "
              f"crossing net(s): {', '.join(missing)}", file=sys.stderr)


def place_lga_lands(design, panel, boards, *, connect,
                    reference: dict | None = None,
                    capture: dict | None = None,
                    pinned: dict | None = None) -> dict:
    """Adaptive board-to-board LGA lands — POST-PROCESSING after place_design.

    The land pattern is computed ONCE per spacer, in the SPACER's local frame,
    against the spacer's authoritative keepout (its milled cavities — which are
    the neighbour tiles' components already `fold_project`-ed by the cavity
    placer — plus the fold-projected potting holes and the flex-launch chords).
    Lands are then placed on the four mating faces by reusing `fold_project`:

      • spacer top  ← pattern Q                (mates the BEFORE tile)
      • spacer bottom ← mirror_x(Q)            → board-local Q (through-via)
      • before tile (top face)  ← fold(Q)      → board-local fold(Q)
      • after tile (bottom face) ← mirror_x(fold(Q)) → board-local fold(Q)

    Because the cavities are `fold_project(components)` and `fold_project` is an
    involution, a land at fold(Q) on a tile automatically clears that tile's
    OWN components and holes — no separate (and previously mis-mirrored)
    tile-frame keepout is needed. The same index → same net on every face, and
    the geometry now mates pad-to-pad through the fold and through-via on the
    spacer. Returns {spacer_name: n_lands}.

    Net assignment is SEGMENT-AWARE: each joint carries exactly the nets that
    CROSS it (from smash.layout.interconnect.crossing_nets_by_gap), packed into
    its lands by `_assign_gap_lands` — power rails multiplied for current, GND
    filling the rest. The same net_list drives all four mating faces, so index
    i carries net X everywhere and the through-via + fold join pad-to-pad.

    `connect` is a callable `(net_name, pin) -> None` (the generator passes its
    `_net`-based connector).

    Economies-of-scale inheritance: `reference` maps spacer name → the joint
    record a previous (maximalist) run stored via `capture`. A spacer whose
    config neighbours match the record replays it VERBATIM — same pattern,
    same nets, same folded tile projections — instead of recomputing from
    this config's crossing census, so every config fabs the same joint.
    Config crossing nets absent from the replayed field are warned about,
    not silently dropped. `capture`, when a dict, is filled with those
    records for freshly computed joints.

    EE-pinned joints: `pinned` maps spacer name → {"tile", "pts", "nets"} —
    a land field an EE routed by hand on one neighbour tile (`pts` in that
    tile's board-local frame, land i carrying nets[i]). The joint adopts it
    INSTEAD of the raster pack: Q is the fold of `pts` into the spacer frame,
    and the spacer faces, through-vias and the OTHER neighbour all follow, so
    the routed board mates unchanged. Nets are kept verbatim (no densify, no
    pair re-seating — the copper was drawn on them); lands outside the joint's
    free region and crossing nets the field doesn't carry are warned about,
    never silently fixed."""
    import sys
    from smash.state.topology.placement import Placement
    from smash.layout.placer.flex_sizing import compute_link_widths
    from smash.layout.interconnect import crossing_nets_by_gap
    chain = panel.snake_chain
    link_widths, _ = compute_link_widths(design, panel)
    added: dict = {}

    # Which nets cross each gap (real pins only — lands don't exist yet) and
    # each net's kind (for power-rail multiplicity). Computed once up front.
    crossing_by_gap, spacer_at_gap, _order = crossing_nets_by_gap(
        design, panel, boards)
    gap_of_spacer = {sp: g for g, sps in spacer_at_gap.items() for sp in sps}
    kind_of = {n.name: n.kind for n in design.nets}
    # One shared pattern (+ its free region, for densify) for the battery
    # column — both cell modes; None for non-battery builds → per-spacer pack.
    _batt = _battery_column_lands(boards, panel, chain)
    batt_lands, batt_free = _batt if _batt is not None else (None, None)

    def _emit(board_obj, ref, foot_pts, net_list, face):
        return _emit_land_field(design, board_obj, ref, foot_pts, net_list,
                                face, connect=connect)

    def _spacer_vias(spacer, Q, net_list):
        # Filled through-via per land: top pad i ↔ bottom pad i, same net.
        # This is the conducting board-to-board path through the interposer
        # (and, for the battery-column spacers, what carries the cell rails +
        # backbone up the stack). The pads on both faces sit at Q[i], so the
        # via is centred there.
        for (vx, vy), vnet in zip(Q, net_list):
            spacer.vias.append(Via(
                net=vnet, position_mm=(vx, vy),
                drill_mm=LGA_VIA_DRILL_MM, pad_diameter_mm=LAND_SIZE_MM,
                from_layer="F.Cu", to_layer="B.Cu", filled=True,
                kind="signal", note="LGA land interposer through-via"))

    for sidx, name in enumerate(chain):
        spacer = boards.get(name)
        if spacer is None or not spacer.is_spacer:
            continue
        before = boards[chain[sidx - 1]] if sidx > 0 else None
        after = boards[chain[sidx + 1]] if sidx + 1 < len(chain) else None
        sp_row = panel.tiles[name][1] if panel.tiles else None
        sr_before = (panel.tiles[before.name][1] == sp_row
                     if before is not None and panel.tiles else True)
        sr_after = (panel.tiles[after.name][1] == sp_row
                    if after is not None and panel.tiles else True)

        # ── reference replay (economies of scale) ────────────────────
        # A joint the maximalist build already carries, mating the SAME
        # two neighbours, is replayed verbatim — pattern, nets, and the
        # folded tile projections — so this config fabs the identical
        # spacer + tile faces. A neighbour mismatch (e.g. core_1cell's
        # re-ordered battery column) falls through to fresh computation.
        ref_j = (reference or {}).get(name)
        if ref_j is not None and \
                ref_j["before"] == (before.name if before is not None else None) and \
                ref_j["after"] == (after.name if after is not None else None):
            Q, net_list = ref_j["Q"], ref_j["nets"]
            gap = gap_of_spacer.get(name)
            crossing = (crossing_by_gap.get(gap, set())
                        if gap is not None else set())
            missing = sorted(crossing - set(net_list))
            if missing:
                print(f"  WARNING: LGA joint {name}: config crossing "
                      f"net(s) not in the inherited maximalist field: "
                      f"{', '.join(missing)} — the shared boards cannot "
                      f"carry them across this joint", file=sys.stderr)
            _emit(spacer, f"J_{name}_top", Q, net_list, "top")
            _emit(spacer, f"P_{name}_bot", Q, net_list, "bottom")
            _spacer_vias(spacer, Q, net_list)
            if before is not None and not before.is_spacer:
                _emit(before, f"J_{before.name}_{name}", ref_j["Qb"],
                      net_list, "top")
            if after is not None and not after.is_spacer:
                _emit(after, f"P_{after.name}_{name}", ref_j["Qa"],
                      net_list, "bottom")
            added[name] = len(Q)
            continue

        if batt_lands is not None and name.startswith("spacer_battery"):
            # Battery column: ONE shared pattern for every spacer in the run
            # (so the through-vias stack pad-to-pad up the cell stack), already
            # clear of the cell bore + potting fingers + both end tiles' parts.
            # `free` is the column's shared region: every battery spacer shares
            # one gap (hence one crossing set), so the densify ladder below
            # refines each to the IDENTICAL denser pattern — the column stays
            # pad-matched even when it has to densify.
            Q = batt_lands
            free = batt_free
        else:
            # Spacer-frame free region: authoritative cavities + projected holes
            # + flex chords, plus each neighbour's branch-launch mouth reflected
            # into the spacer frame (so the round-trip clears it on the tile).
            free = _joint_free_region(spacer, panel, chain, link_widths)
            # before mates on its TOP face (gets J_*_top), after on its BOTTOM
            # (gets P_*_bot) — clear each neighbour's branch-launch mouth AND its
            # milled cavities on that mating face (reflected into the spacer
            # frame, so the round-trip clears them on the tile too).
            for nb, sr, nb_face in ((before, sr_before, "top"),
                                    (after, sr_after, "bottom")):
                if nb is None:
                    continue
                bko = _branch_launch_keepout(nb, panel)
                if bko is not None:
                    free = free.difference(_fold_reflect(bko, sr))
                # Mid-mount parts (nose_cap USB-C) straddle the board but spawn
                # no milled cavity — keep lands out of their full body courtyard
                # on the mating face.
                sko = _straddle_keepout(nb)
                if sko is not None:
                    free = free.difference(_fold_reflect(sko, sr))
                # The neighbour's milled cavities on this mating face (e.g. the
                # piezo pocket; a `through` cavity like the USB notch blocks both
                # faces) — reflected into the spacer frame like the keepouts.
                cko = _tile_cavity_keepout(nb, nb_face)
                if cko is not None:
                    free = free.difference(_fold_reflect(cko, sr))
            Q = _grid_pack(free)
        if not Q:
            continue

        # The exporter writes a footprint's pads at their literal (flip-y)
        # coords on whichever Cu layer the face selects — it does NOT apply a
        # B.Cu X-mirror. So a pad's rendered board-local XY equals its
        # footprint-local XY on BOTH faces; we therefore author the intended
        # world position directly (no mirror_x). Spacer faces both carry Q (so
        # a straight through-via joins top pad i ↔ bottom pad i); each tile
        # carries fold(Q) so it folds onto the spacer's Q and, being the fold
        # of the spacer's cavities/holes, clears its own components + holes.
        # Assign this joint's crossing nets to its lands (same list on all four
        # mating faces → index i carries the same net everywhere).
        gap = gap_of_spacer.get(name)
        crossing = crossing_by_gap.get(gap, set()) if gap is not None else set()
        pin = (pinned or {}).get(name)
        if pin is not None:
            # EE-pinned joint: the routed tile's field, folded into the spacer
            # frame (fold is its own inverse). Verbatim — see docstring.
            nb_sr = {before.name if before is not None else None: sr_before,
                     after.name if after is not None else None: sr_after}
            Q = _fold([tuple(p) for p in pin["pts"]], nb_sr[pin["tile"]])
            net_list = list(pin["nets"])
            _check_pinned_joint(name, Q, net_list, free, crossing)
        else:
            Q, net_list = _pack_joint_nets(Q, free, crossing, kind_of, name)

        _emit(spacer, f"J_{name}_top", Q, net_list, "top")
        _emit(spacer, f"P_{name}_bot", Q, net_list, "bottom")
        _spacer_vias(spacer, Q, net_list)
        # Project mating lands onto a RIGID neighbour only. When the
        # neighbour is itself a spacer (a battery-compartment run of
        # replicated spacers), skip it: that spacer places its own J_top /
        # P_bot at the same Q, so consecutive copies mate pad-to-pad (and the
        # filled vias carry the nets straight up the column).
        Qb = _fold(Q, sr_before)
        Qa = _fold(Q, sr_after)
        if before is not None and not before.is_spacer:
            _emit(before, f"J_{before.name}_{name}", Qb, net_list, "top")
        if after is not None and not after.is_spacer:
            _emit(after, f"P_{after.name}_{name}", Qa, net_list, "bottom")
        added[name] = len(Q)
        if capture is not None:
            capture[name] = {
                "Q": [tuple(p) for p in Q],
                "nets": list(net_list),
                "Qb": [tuple(p) for p in Qb],
                "Qa": [tuple(p) for p in Qa],
                "before": before.name if before is not None else None,
                "after": after.name if after is not None else None,
            }
    return added


# ── branch-flex launch strips ─────────────────────────────────────────
# Per-net routing anchors at each end of a BRANCH flex (qpd / camera).
# The strip sits inside the `_branch_launch_keepout` mouth, so the land
# packer already keeps clear of it; pad k carries the SAME net on both
# ends, so the flex web copper between the strips is a 1:1 straight
# parallel run (auto-generatable; no hand routing on the flex).
LAUNCH_PAD_MM = 0.6
LAUNCH_PITCH_MAX_MM = 1.0
LAUNCH_ROW_INSET_MM = 1.4      # row centreline inset from the rim


def place_branch_flex_launches(design, boards, *, catalog,
                               connect) -> dict:
    """One pad-row strip per end of every branch flex — the FIXED
    interface where the rigid-board routing meets the flex web.

    `catalog` entries are `(parent, leaf, side, nets)` — the version-
    controlled launch CONTRACT (see _FLEX_LAUNCH_CATALOG in the
    generator): the PARENT strip is emitted whenever the parent board
    is in the build, leaf present or NOT, so the parent routes ONCE
    and every config carries identical strips (an unpopulated
    "connector" at the flex mouth when the leaf is absent). The leaf
    strip is emitted only when the leaf is in the build, and the live
    crossing-net census is then validated against the contract — a
    leaf-builder net change breaks generation loudly instead of
    silently moving pads. Pad k carries nets[k] on both ends; the row
    tangent is shared, so the flat-panel ribbon joins pad k to pad k
    as a straight parallel run. Strips sit inside the
    `_branch_launch_keepout` mouth, so the land packer stays clear.
    Returns {(parent, leaf): n_nets}."""
    from smash.state.topology.placement import Placement
    _DIR = {"N": (0.0, 1.0), "S": (0.0, -1.0),
            "E": (1.0, 0.0), "W": (-1.0, 0.0)}
    tag = {c.ref: getattr(c, "board_tag", None) for c in design.chips}
    added: dict = {}
    for parent, leaf, side, nets in catalog:
        pb, lb = boards.get(parent), boards.get(leaf)
        if pb is None or not nets:
            continue
        if lb is not None:
            census = sorted({n.name for n in design.nets
                             if not is_off_backbone(n.name)
                             and {parent, leaf} <= {tag.get(r)
                                                    for r, _p in n.pins}})
            if census != sorted(nets):
                raise SystemExit(
                    f"flex-launch contract broken for {parent}->{leaf}: "
                    f"catalog {sorted(nets)} vs census {census} — "
                    f"update _FLEX_LAUNCH_CATALOG deliberately")
        n = len(nets)
        pitch = min(LAUNCH_PITCH_MAX_MM,
                    (_BRANCH_KEEPOUT_W_MM - 1.5) / max(n - 1, 1))
        span = (n - 1) * pitch
        ux, uy = _DIR[side]
        # ONE tangent for both strips (from the parent->leaf axis): in
        # the FLAT panel the flex ribbon runs straight, so pad k must
        # sit at the same panel-frame chord offset on both ends — a
        # per-side tangent would mirror the row and cross the ribbon.
        tx, ty = -uy, ux
        ends = [(pb, ux, uy, "J")]
        if lb is not None:
            ends.append((lb, -ux, -uy, "P"))
        for board_obj, sx, sy, kind in ends:
            r = (board_obj.geometry.outline_radius_mm
                 if board_obj.geometry is not None else 17.0)
            d = r - LAUNCH_ROW_INSET_MM
            cx, cy = sx * d, sy * d
            pts = [(round(cx + tx * (k * pitch - span / 2.0), 3),
                    round(cy + ty * (k * pitch - span / 2.0), 3))
                   for k in range(n)]
            ref = f"{kind}_FLEXL_{parent}__{leaf}"
            fp = Footprint(
                name=ref,
                pads=[Pad(num=str(k + 1), position_mm=p,
                          size_mm=(LAUNCH_PAD_MM, LAUNCH_PAD_MM),
                          shape="rect", layer="F.Cu")
                      for k, p in enumerate(pts)],
                package_class="flex launch strip",
                source="project (branch-flex launch)",
                note="per-net anchors where the rigid routing meets the"
                     " branch flex web; same pad index = same net on"
                     " both ends of the flex")
            chip = design.add_chip(
                ref=ref, board_tag=board_obj.name, manf="project",
                manf_pn="FLEX_LAUNCH", name="FLEX_LAUNCH",
                footprint=fp,
                pins=[Pin(num=p.num, name=p.num) for p in fp.pads],
                note="branch-flex launch strip")
            for k, pin in enumerate(chip.pins):
                connect(nets[k], chip.pin(pin.num))
            board_obj.chip_placements.append(Placement(
                position_mm=(0.0, 0.0), rotation_deg=0.0, face="top",
                item=chip, locked=True))
        added[(parent, leaf)] = n
    return added
