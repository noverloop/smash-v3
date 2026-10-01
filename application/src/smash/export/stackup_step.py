"""Assemble the folded rigid-flex tower in 3D for structural FEA.

The snake chain folds into a vertical stack of concentric Ø34 tiles —
rigid boards (≈2.226 mm 14L FR4) alternating with 4 mm FR4 spacers — at
cumulative Z. This exporter emits a MULTI-BODY STEP assembly so an FEA
mesher can assign per-body materials and inter-layer contacts:

  - each rigid board   → solid FR4 disc (+ any through holes)
  - each spacer        → build_spacer_solid (disc − cavities − potting holes)
  - component masses    → a block per placed chip on the facing side, so the
                          components' inertial load under setback is captured
  - potting encapsulant → the Ø stack envelope minus the FR4 bodies, i.e.
                          the vacuum-potting compound filling the interstices
                          (mostly the spacer cavities + flat notches)

Branch tiles (camera/qpd/nfc) hang off deploy flexes outside the tower,
so they're excluded — only the `snake_chain` is stacked.

The whole tower is built along +Z from z=0 (bottom tile) upward.
"""
from __future__ import annotations

import pathlib

from smash.state import Chip
from smash.state.antenna import Antenna
from smash.export.spacer_step import build_spacer_solid
from smash.layout.placer.grid import footprint_bbox_mm


def build_board_solid(board, thickness_mm: float):
    """A rigid board's FR4 body: its outline extruded by `thickness_mm`,
    with any through-holes drilled. Origin at the tile centre, base at
    z=0. Raises ImportError without cadquery."""
    import cadquery as cq

    g = board.geometry
    if g is not None and g.shape == "circle" and g.diameter_mm:
        body = cq.Workplane("XY").circle(g.diameter_mm / 2.0).extrude(thickness_mm)
    elif g is not None and g.shape == "rect" and g.rect_dimensions:
        w, h = g.rect_dimensions
        body = cq.Workplane("XY").rect(w, h).extrude(thickness_mm)
    else:
        raise ValueError(f"board {board.name!r}: unsupported geometry {g}")

    # Flat chord on the N rim — matches the KiCad outline's
    # make_cutout(_ANGLE_N, 17.0, kind="flat") for these tiles (kicad_pcb._tile_cuts).
    # Without it the STEP solid is a FULL circle, so the radar-mounted USB-C mouth
    # has no edge to exit and the USB notch becomes a closed pocket that the boolean
    # leaves filled. Cut the circular segment north of the chord line. (USB-C N
    # chord, 17 mm — keep in sync with _tile_cuts.)
    if g.shape == "circle" and g.diameter_mm and board.name in ("nose_cap", "radar_module"):
        import math as _math
        _r = g.diameter_mm / 2.0
        _y_flat = _math.sqrt(max(_r * _r - (17.0 / 2.0) ** 2, 0.0))
        _seg = (cq.Workplane("XY").center(0.0, _y_flat + _r)
                .rect(2.2 * _r, 2.0 * _r).extrude(thickness_mm))
        body = body.cut(_seg)
        # USB-C mouth notch in the flat: per-tile width (radar 10.2 mm to clear the
        # mouth while the flats still carry the solder lands; nose_cap 12.5 mm to
        # clear the body poking up), reaching 6.3 mm in from the chord (floor y ~= _y_flat -
        # 6.3), connecting to the chord cut above so the outline is rim -> flat ->
        # notch -> flat -> rim. Replaces the old separate usb_mid_mount_cavity.
        # Keep in sync with _tile_cuts (kicad_pcb).
        _nw, _nd = (10.2 if board.name == "radar_module" else 12.5), 6.3
        _nfloor, _ntop = _y_flat - _nd, _y_flat + 1.0
        _notch = (cq.Workplane("XY").center(0.0, (_nfloor + _ntop) / 2.0)
                  .rect(_nw, _ntop - _nfloor).extrude(thickness_mm))
        body = body.cut(_notch)

    for hole in (g.holes or []):
        x, y = hole.position_mm
        body = (body.faces(">Z").workplane(centerOption="ProjectedOrigin")
                .moveTo(x, y).hole(hole.diameter_mm))

    # Cut any board cutouts marked as CavityRegions — the nose USB mid-mount
    # window, the radar metal-block window, the piezo pocket, … A "through"
    # cut goes full depth; "top"/"bottom" is a blind pocket from that face.
    # Without this, board cutouts are invisible in the stackup (only spacers
    # were getting their cavities cut). Mirrors build_spacer_solid's loop.
    from smash.state.geometry.cavity import CavityRegion
    for placement in (getattr(board, "cavity_placements", None) or []):
        region = placement.item
        if not isinstance(region, CavityRegion):
            continue
        pts = list(region.exterior_polygon)
        if len(pts) < 3:
            continue
        # "through" spans the whole body by definition — its stored depth_mm
        # is the thickness at cavity-attach time and goes stale when
        # size_backbone_spacers later grows a spacer (0.3 mm un-milled skin
        # on wakeup↔power at 4.0→4.3 before this guard).
        depth = (thickness_mm if region.face == "through"
                 else (region.depth_mm or thickness_mm))
        clean: list = []
        for p in pts:
            if not clean or (abs(clean[-1][0] - p[0]) > 1e-9
                             or abs(clean[-1][1] - p[1]) > 1e-9):
                clean.append(p)
        if (len(clean) >= 2 and abs(clean[0][0] - clean[-1][0]) < 1e-9
                and abs(clean[0][1] - clean[-1][1]) < 1e-9):
            clean.pop()
        if len(clean) < 3:
            continue
        z_offset = thickness_mm - depth if region.face == "top" else 0.0
        verts = [cq.Vector(x, y, z_offset) for x, y in clean]
        cut = cq.Solid.extrudeLinear(
            cq.Face.makeFromWires(cq.Wire.makePolygon(verts, close=True)),
            cq.Vector(0, 0, depth))
        body = body.cut(cq.Workplane().newObject([cut]))
    return body


def _component_blocks(board, thickness_mm: float):
    """`(ref, solid)` mass-blocks for each placed chip, in the board's OWN
    local frame (base at z=0). A top-face chip extrudes UP from the top
    (z=thickness); a bottom-face chip extrudes DOWN from the base (z=0).
    Box = footprint size × component height, rotated by the placement
    angle. The caller applies the board's fold pose so the blocks travel
    with the board."""
    import cadquery as cq

    blocks = []
    for pl in board.chip_placements:
        c = pl.item
        if not isinstance(c, (Chip, Antenna)):
            continue
        # Backbone LGA-land arrays (manf_pn 'LGA_lands') are thin copper pads
        # spanning the board — negligible mass, but their pad bbox is huge, so
        # they'd render as a big ~20 mm mass-box on every tile (the square at the
        # top of each board). They're an interconnect, not a component weight →
        # skip them from the mass model.
        if getattr(c, "manf_pn", None) == "LGA_lands":
            continue
        fp = c.footprint
        if fp is None:
            continue
        # Project pseudo-parts with NO body height — the cell contact pads
        # (BatteryContacts_3), pogo arrays, etc. — are flat copper on the board
        # surface, not a component mass, yet their footprint bbox would render as
        # a solid cube (the "square copper coin" over the cells). Skip them; the
        # real per-pad copper lives in the layered/copper view. Gated on
        # manf=="project" so a REAL part with height data merely unset still gets
        # its 0.5 mm-default block (the mass model stays complete).
        if (getattr(c, "manf", None) == "project"
                and not (getattr(fp, "height_mm", None)
                         or getattr(c, "height_mm", None))):
            continue
        # Weight block = the package BODY (fp.size_mm), capped per-axis at the
        # footprint bbox. Two over-sizing sources to avoid: footprint_bbox_mm
        # unions in the courtyard keepout (the LDL112 DFN6's 4.25×3.6 courtyard
        # vs its 3.0×3.0 body — block poked its radar-block cutout, milled from
        # fp.size_mm), and a part's nominal size_mm can exceed the drawn
        # footprint in one axis (the U_COMP_BOOST TSSOP: size_mm 3.0×4.4 vs bbox
        # 6.3×3.6 — its 4.4 body width poked the spacer cavity, milled from
        # footprint_bbox_mm). min(size_mm, bbox) fits inside BOTH cutouts. Fall
        # back to the bbox for parts with no nominal size (kicad_mod footprints).
        lo_x, lo_y, hi_x, hi_y = footprint_bbox_mm(fp)
        fbw, fbh = hi_x - lo_x, hi_y - lo_y
        sz = getattr(fp, "size_mm", None)
        if sz and sz[0] > 0 and sz[1] > 0:
            w, h = min(sz[0], fbw), min(sz[1], fbh)
        else:
            w, h = fbw, fbh
        ht = (getattr(fp, "height_mm", None) or getattr(c, "height_mm", None)
              or 0.5)
        if w <= 0 or h <= 0 or ht <= 0:
            continue
        x, y = pl.position_mm
        face = getattr(pl, "face", "top") or "top"
        base_z = thickness_mm if face == "top" else -ht
        blk = (cq.Workplane("XY")
               .box(w, h, ht, centered=(True, True, False))
               .rotate((0, 0, 0), (0, 0, 1), getattr(pl, "rotation_deg", 0.0) or 0.0)
               .translate((x, y, base_z)))
        blocks.append((c.ref, blk))
    return blocks


def _fold_signs(tiles, prev_name, name) -> tuple:
    """In-plane mirror signs (sx, sy) for the accordion hinge between two
    consecutive chain tiles. A same-row (E-W) fold rotates 180° about a
    vertical hinge → x mirrors; a same-col (N-S) fold rotates about a
    horizontal hinge → y mirrors. Matches cavities.fold_project. Without
    grid positions, assume E-W (the historical default)."""
    if tiles and prev_name in tiles and name in tiles:
        if tiles[prev_name][1] == tiles[name][1]:
            return (-1.0, 1.0)        # same row → E-W fold
        return (1.0, -1.0)            # same col → N-S fold
    return (-1.0, 1.0)


def _apply_pose(body, mx: float, my: float, mz: float, z: float, t: float):
    """Place a tile body at its cumulative fold pose. (mx,my,mz) is always
    a proper 180° rotation (det +1) — identity, or 180° about X/Y/Z — so
    cadquery can realise the reflection as a rotation. Bodies built from
    z∈[0,t]; an X/Y flip sends them to [-t,0], so add t to the Z shift to
    re-seat the slot at [z, z+t]."""
    if (mx, my, mz) == (-1.0, 1.0, -1.0):
        body = body.rotate((0, 0, 0), (0, 1, 0), 180)      # E-W parity
    elif (mx, my, mz) == (1.0, -1.0, -1.0):
        body = body.rotate((0, 0, 0), (1, 0, 0), 180)      # N-S parity
    elif (mx, my, mz) == (-1.0, -1.0, 1.0):
        body = body.rotate((0, 0, 0), (0, 0, 1), 180)      # double fold
    # else identity
    return body.translate((0, 0, z + (t if mz < 0 else 0.0)))


def write_stackup_step(
    design,
    boards: dict,
    snake_chain,
    output_path: str | pathlib.Path,
    *,
    with_components: bool = True,
    with_potting: bool = True,
    with_layered_rigid: bool = False,
    fab=None,
    tiles: dict | None = None,
) -> dict:
    """Emit the folded tower as one multi-body STEP assembly.

    Stacks every `snake_chain` tile (boards + spacers) at cumulative Z,
    concentric. Optionally adds per-chip component-mass blocks and a
    single potting-encapsulant body (stack envelope − FR4 bodies).

    With `with_layered_rigid=True`, each rigid tile is expanded into
    its per-layer assembly via `iter_layered_board_bodies` — every Cu
    foil, dielectric, soldermask, via barrel and Al backing becomes
    its own posed body in the folded stack. Chip blocks come from the
    layered iterator (with_components is forwarded). The fab profile
    is passed through for material lookups. Result: a STEP file
    suitable for whole-system EM (radar near-field through the
    housing, inter-tile coupling, etc.). File is BIG — expect tens of
    MB for the maximalist panel.

    `with_layered_rigid=False` (default) keeps the legacy single-FR4
    disc per tile — fast and small, fine for structural / inertial
    studies that don't need per-layer detail.

    Returns a summary dict. Raises ImportError without cadquery.
    """
    import cadquery as cq

    asm = cq.Assembly()
    z = 0.0
    n_boards = n_spacers = n_comps = n_layered = 0
    fr4_bodies = []          # boards + spacers, for the potting subtraction
    max_radius = 0.0

    # Cumulative fold pose. Each accordion hinge composes an in-plane
    # mirror (x for E-W, y for N-S) with a z-flip. Applying this same pose
    # to BOTH boards and spacers reproduces the physical fold, so a
    # spacer's milled cavity (placed at cavities.fold_project) lands under
    # the very chip it clears — regardless of run direction or corners.
    # On a straight E-W run this reduces to the historical "boards upright,
    # spacers flipped 180° about Y".
    prev = None
    for name in snake_chain:
        b = boards.get(name)
        if b is None:
            continue
        t = b.thickness_mm
        g = b.geometry
        if g is not None and getattr(g, "diameter_mm", None):
            max_radius = max(max_radius, g.diameter_mm / 2.0)

        # Per-tile pose. The backbone is an INTERPOSER STACK, not an accordion
        # fold (the snake-flex scheme is gone): every rigid board stacks upright
        # with F.Cu facing the nose (+Z). Only the FR4 spacers flip 180° about
        # their fold-direction axis — vestigial from the snake-flex era, but
        # their cavities are pre-mirrored by cavities.fold_project to suit, so
        # the flip keeps each cavity under the chip it clears. (The old
        # cumulative-parity pose mis-flipped every board downstream of the
        # battery compartment's run of spacers — caught by check_stack_collisions.)
        if getattr(b, "is_spacer", False):
            sx, sy = (_fold_signs(tiles, prev, name)
                      if prev is not None else (-1.0, 1.0))
            mx, my, mz = sx, sy, -1.0
        else:
            mx, my, mz = 1.0, 1.0, 1.0

        if getattr(b, "is_spacer", False):
            body, _, _ = build_spacer_solid(b, t)
            body = _apply_pose(body, mx, my, mz, z, t)
            asm.add(body, name=name, color=cq.Color(0.4, 0.5, 0.6, 1.0))
            fr4_bodies.append(body)
            n_spacers += 1
        elif with_layered_rigid:
            # Layered rigid: walk each per-layer body, apply the same
            # fold pose, add to top-level assembly. Component blocks
            # come from the iterator (so we don't double-count).
            from smash.export.layered_step import iter_layered_board_bodies
            for body, record, color in iter_layered_board_bodies(
                    b, fab=fab, base_z=0.0,
                    with_components=with_components,
                    with_al_backing=True):
                body = _apply_pose(body, mx, my, mz, z, t)
                asm.add(body, name=f"{name}.{record.name.split('.', 1)[1]}",
                        color=color)
                # Treat FR4 / Cu / mask as solid bodies for potting
                # subtraction; chip bodies live INSIDE the potting and
                # don't carve into it.
                if record.role != "chip":
                    fr4_bodies.append(body)
                n_layered += 1
            n_boards += 1
        else:
            body = _apply_pose(build_board_solid(b, t), mx, my, mz, z, t)
            asm.add(body, name=name, color=cq.Color(0.1, 0.5, 0.2, 1.0))
            fr4_bodies.append(body)
            n_boards += 1
            if with_components:
                for ref, blk in _component_blocks(b, t):
                    blk = _apply_pose(blk, mx, my, mz, z, t)
                    asm.add(blk, name=f"{name}.{ref}",
                            color=cq.Color(0.7, 0.7, 0.2, 1.0))
                    n_comps += 1
        z += t
        prev = name

    total_h = z
    if with_potting and total_h > 0 and max_radius > 0 and fr4_bodies:
        # Vacuum potting = stack envelope minus the FR4 (boards + spacers).
        # What remains is the spacer cavities, flat notches and edge gaps
        # the compound fills. (Component blocks are left as separate bodies;
        # they sit inside this fill — a small modelled overlap.)
        pot = cq.Workplane("XY").circle(max_radius).extrude(total_h)
        for fb in fr4_bodies:
            pot = pot.cut(fb)
        asm.add(pot, name="potting",
                color=cq.Color(0.8, 0.4, 0.4, 0.4))

    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # `Assembly.export` is the non-deprecated STEP writer (was `.save`).
    if hasattr(asm, "export"):
        asm.export(str(out))
    else:                                   # older cadquery
        asm.save(str(out))

    return {
        "output_path":   str(out),
        "n_boards":      n_boards,
        "n_spacers":     n_spacers,
        "n_components":  n_comps,
        "n_layered_bodies": n_layered,
        "has_potting":   with_potting,
        "height_mm":     round(total_h, 2),
    }


def write_stackup_components_step(
    boards: dict,
    snake_chain,
    tile_step_dir,
    output_path,
    *,
    tiles: dict | None = None,
) -> dict:
    """Fold the DETAILED per-tile STEPs into the tower — the component-render
    counterpart of `write_stackup_step`'s mass-block FEA tower.

    Each tile's real 3D model (board + actual component bodies + through-cuts)
    is read from ``tile_step_dir/<name>/<name>.step`` (boards from
    `_export_tile_steps`, spacers from `write_all_spacer_steps`) and posed with
    the SAME per-tile fold: rigid boards upright (F.Cu → nose), FR4 spacers
    flipped 180° about their fold-direction axis. So the nose USB-C, the radar
    block and every chip show as their true geometry instead of mass boxes.

    Tiles whose STEP is missing on disk are skipped, but their Z slot is still
    reserved so the stack height stays right (a dropped scaffold spacer is
    absent from `boards`, so it takes no slot). Run the tile + spacer STEP
    exports first. Raises ImportError without cadquery.
    """
    import cadquery as cq

    tile_step_dir = pathlib.Path(tile_step_dir)
    asm = cq.Assembly()
    z = 0.0
    prev = None
    n_tiles = 0
    for name in snake_chain:
        b = boards.get(name)
        if b is None:            # dropped scaffold spacer — tiles mate directly
            continue
        t = b.thickness_mm
        is_spacer = getattr(b, "is_spacer", False)
        step_path = tile_step_dir / name / f"{name}.step"
        if step_path.exists():
            if is_spacer:
                sx, sy = (_fold_signs(tiles, prev, name)
                          if prev is not None else (-1.0, 1.0))
                mx, my, mz = sx, sy, -1.0
            else:
                mx, my, mz = 1.0, 1.0, 1.0
            body = _apply_pose(cq.importers.importStep(str(step_path)),
                               mx, my, mz, z, t)
            asm.add(body, name=name)
            # Embedded Cu coins: the per-tile STEP is FR4-only, so add the coin
            # prisms here (Cu-coloured) — otherwise the coin only appears in the
            # per-board LAYERED STEP, and edits to it look like they "didn't take"
            # in this components stackup (KiCad reads cu_coin_inserts directly and
            # does show them, hence the mismatch).
            from smash.export.layered_step import _coin_extruded_body
            for ci, coin in enumerate(getattr(b, "cu_coin_inserts", None) or []):
                cbody = _apply_pose(
                    _coin_extruded_body(coin, thickness_mm=coin.thickness_mm,
                                        base_z_mm=coin.z_bottom_mm),
                    mx, my, mz, z, t)
                asm.add(cbody, name=f"{name}.coin{ci}",
                        color=cq.Color(0.72, 0.45, 0.20, 1.0))   # copper
            n_tiles += 1
        z += t
        prev = name

    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(asm, "export"):
        asm.export(str(out))
    else:                                   # older cadquery
        asm.save(str(out))
    return {"output_path": str(out), "n_tiles": n_tiles,
            "height_mm": round(z, 2)}


def _max_face_height_mm(board, face: str) -> float:
    """Tallest component on `face` of `board` (its protrusion above the board
    surface). Used to size how far parts poke out the two END boards."""
    h = 0.0
    for pl in getattr(board, "chip_placements", []):
        if (getattr(pl, "face", "top") or "top") != face:
            continue
        c = pl.item
        fp = getattr(c, "footprint", None)
        ch = (getattr(c, "height_mm", None)
              or (getattr(fp, "height_mm", None) if fp else None) or 0.0)
        h = max(h, ch)
    return h


def _system_z_extent(boards: dict, snake_chain) -> tuple:
    """`(z_min, z_max)` of the folded system along the stack axis. The FR4 stack
    runs z=0..stack_height; components on the two END boards' OUTER faces poke
    beyond it (the nose tile's top-face parts up, the aft tile's bottom-face
    parts down). Interior-board parts sit inside the spacer cavities, within the
    stack, so they don't extend the envelope."""
    z = 0.0
    pos = {}
    for name in snake_chain:
        b = boards.get(name)
        if b is None:
            continue
        pos[name] = (z, b.thickness_mm)
        z += b.thickness_mm
    z_min, z_max = 0.0, z
    chain_boards = [n for n in snake_chain
                    if boards.get(n) is not None
                    and not getattr(boards[n], "is_spacer", False)]
    if chain_boards:
        first, last = chain_boards[0], chain_boards[-1]
        z_min = min(z_min, pos[first][0] - _max_face_height_mm(boards[first], "bottom"))
        z_max = max(z_max, pos[last][0] + pos[last][1]
                    + _max_face_height_mm(boards[last], "top"))
    return z_min, z_max


def write_consolidated_stackup_stl(
    boards: dict, snake_chain, output_path, *, diameter_mm: float = 34.0,
    tile_step_dir=None,
) -> dict:
    """A SOLID cylinder enclosing the folded system — for 3D-printing a fit
    mock-up. Ø=`diameter_mm` (the board Ø), rising to the FR4 stack top. If
    `tile_step_dir` is given, the parts poking ABOVE the stack top on the nose
    tile (the USB-C receptacle) are kept as their REAL 3D geometry — lifted from
    the nose per-tile STEP (already correctly placed by kicad-cli) and unioned on
    top — so the connector's true shape + reach show for fit-checking, instead of
    being absorbed into the solid. Exports STL. Raises ImportError without
    cadquery."""
    import cadquery as cq
    z0, _z1 = _system_z_extent(boards, snake_chain)
    zbase, z = {}, 0.0
    for n in snake_chain:
        b = boards.get(n)
        if b is None:
            continue
        zbase[n] = z
        z += b.thickness_mm
    stack_top = z
    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    solid = (cq.Workplane("XY").circle(diameter_mm / 2.0)
             .extrude(stack_top - z0).translate((0.0, 0.0, z0)))
    retained = False
    if tile_step_dir:
        tops = [n for n in snake_chain if boards.get(n) is not None
                and not getattr(boards[n], "is_spacer", False)]
        nose = tops[-1] if tops else None
        sp = (pathlib.Path(tile_step_dir) / nose / f"{nose}.step") if nose else None
        if sp is not None and sp.exists():
            try:
                tile = cq.importers.importStep(str(sp)).translate(
                    (0.0, 0.0, zbase[nose]))
                above = (cq.Workplane("XY").circle(diameter_mm)
                         .extrude(100.0).translate((0.0, 0.0, stack_top)))
                poke = tile.intersect(above)
                if poke.val().Volume() > 0.01:
                    solid = solid.union(poke)
                    retained = True
            except Exception:                    # keep the bare cylinder on failure
                retained = False
    cq.exporters.export(solid, str(out), exportType="STL")
    zmax = solid.val().BoundingBox().zmax
    return {"output_path": str(out), "diameter_mm": diameter_mm,
            "height_mm": round(zmax - z0, 2), "usb_retained": retained}


def write_housing_stl(
    boards: dict, snake_chain, output_path, *,
    inner_dia_mm: float = 34.0, outer_dia_mm: float = 39.0,
    floor_dia_mm: float = 30.0, floor_thickness_mm: float = 2.0,
    floor_relief_mm: float = 1.0,
) -> dict:
    """The HOUSING the system drops into — an open-top tube (inner Ø=
    `inner_dia_mm`, outer Ø=`outer_dia_mm`) with a CLOSED bottom. The bottom is a
    sealed floor; the system's aft tile lands on a central Ø=`floor_dia_mm` pad,
    with the ring out to the bore recessed by `floor_relief_mm` for edge
    clearance. Same z-span as the consolidated cylinder. Exports STL. Raises
    ImportError without cadquery."""
    import cadquery as cq
    z0, z1 = _system_z_extent(boards, snake_chain)
    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tube = (cq.Workplane("XY").circle(outer_dia_mm / 2.0)
            .circle(inner_dia_mm / 2.0)
            .extrude(z1 - z0).translate((0.0, 0.0, z0)))
    # Sealed bottom: a full-width disc that seals + connects to the wall, below
    # the system. The aft tile lands on a central Ø(floor_dia) pad; the ring out
    # to the bore is recessed so the board edge / aft parts clear it.
    base = (cq.Workplane("XY").circle(outer_dia_mm / 2.0)
            .extrude(floor_thickness_mm)
            .translate((0.0, 0.0, z0 - floor_thickness_mm)))
    housing = tube.union(base)
    if 0.0 < floor_dia_mm < inner_dia_mm and floor_relief_mm > 0.0:
        relief = (cq.Workplane("XY").circle(inner_dia_mm / 2.0)
                  .circle(floor_dia_mm / 2.0)
                  .extrude(floor_relief_mm)
                  .translate((0.0, 0.0, z0 - floor_relief_mm)))
        housing = housing.cut(relief)
    cq.exporters.export(housing, str(out), exportType="STL")
    return {"output_path": str(out), "inner_dia_mm": inner_dia_mm,
            "outer_dia_mm": outer_dia_mm, "floor_dia_mm": floor_dia_mm,
            "height_mm": round(z1 - z0, 2)}
