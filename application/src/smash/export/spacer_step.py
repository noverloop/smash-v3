"""Generate STEP files for the FR4 spacer interposer tiles.

KiCad treats a spacer tile as a blank PCB region using the global
1.6 mm board thickness — wrong for the actual stack, where spacers are
**FR4 PCB interposers** carrying copper LGA lands on both faces joined
by filled through-vias (the power/GND/CAN backbone passes straight
through on the same net), reflow-soldered to the rigid tiles above and
below. The earlier CNC-Al + Type-II-anodise spacer was abandoned once
the snake-flex interconnect proved infeasible: an anodised-Al disc can
neither carry plated vias nor take solder. Per-board structural support
(which the Al disc once provided) now comes from copper-coin inserts in
the rigid tiles' stackup, not the spacer. This module generates a true
CAD body per spacer using cadquery / OpenCASCADE, with:

  - circular Ø34 mm disc, extruded to the board's own `thickness_mm`
    (4 mm backbone spacers; the battery compartment is a run of thinner
    discs, e.g. 3.5 mm, so each stays under the fab layer cap)
  - NPTH potting holes drilled through (Ø3 mm at the 14 mm radial)
  - top-face cavities routed to 2 mm depth (from
    `spacer.cavity_placements` where face='top')
  - bottom-face cavities routed to 1 mm depth (face='bottom')

Material + finish callouts for the fab are written to a sibling
`<name>_cam.md` Markdown file via `write_spacer_cam_notes()` —
geometry alone in the STEP isn't enough; the shop needs the laminate +
finish spec and the filled-via callout (the fill must be capped + plated
over so the LGA lands above seat co-planar).

The output STEP can be loaded into FreeCAD / Fusion / mesh tools for
3D layout validation and physics-sim mesh generation.
"""
from __future__ import annotations

import pathlib
from typing import Iterable

from smash.state.board import Board
from smash.state.geometry.cavity import CavityRegion


# Mirror constants from smash.layout.cavities so this module stays
# importable without circular deps if those constants ever need to
# differ. Default values match what the cavities module declares.
DEFAULT_SPACER_THICKNESS_MM = 4.0
DEFAULT_TOP_CAVITY_DEPTH_MM = 2.0
DEFAULT_BOT_CAVITY_DEPTH_MM = 1.0

# Fab spec for the FR4 spacer interposer. ENIG is the project-wide
# surface finish (cf. kicad_pcb.py copper_finish + eurocircuits_pool /
# ncab fab profiles) — solderable + flat, which the filled LGA lands on
# both faces need (the spacer reflows to the tiles above and below).
SPACER_MATERIAL_DEFAULT = "FR4"
SPACER_FINISH_DEFAULT = "ENIG (electroless nickel / immersion gold)"
SPACER_TOLERANCE_MM = 0.05                     # ± laminate thickness
SPACER_ROUTE_TOLERANCE_MM = 0.1                # ± routed outline / cavity edge


def build_spacer_solid(spacer: Board, thickness_mm: float):
    """Build the spacer's cadquery body — a Ø disc, potting holes drilled
    through, and the milled cavity pockets cut on each face. Returns
    `(body, n_top_cavities, n_bot_cavities)`. The disc edge is kept solid
    (the spacers are the tower's load-bearing interposers; the flex routes
    past, not through). Raises ImportError if cadquery isn't installed."""
    import cadquery as cq

    g = spacer.geometry
    if g is None or g.shape != "circle" or g.diameter_mm is None:
        raise ValueError(
            f"spacer {spacer.name!r}: expected circle geometry with "
            f"diameter_mm; got {g}"
        )
    radius = g.diameter_mm / 2.0

    # Base disc, centred on XY plane, extruded +Z by thickness.
    body = cq.Workplane("XY").circle(radius).extrude(thickness_mm)

    # Potting holes — through the whole disc.
    for hole in g.holes:
        x, y = hole.position_mm
        body = (
            body.faces(">Z").workplane(centerOption="ProjectedOrigin")
            .moveTo(x, y)
            .hole(hole.diameter_mm)
        )

    # Cavity pockets. Each CavityRegion's exterior_polygon is math-y-up
    # board-local mm; cadquery's default workplane is XY math-y-up so
    # no axis flip needed.
    n_top = 0
    n_bot = 0
    for placement in spacer.cavity_placements:
        region = placement.item
        if not isinstance(region, CavityRegion):
            continue
        pts = list(region.exterior_polygon)
        if len(pts) < 3:
            continue
        if region.face == "through":
            # A through-cut spans the WHOLE spacer by definition. Its stored
            # depth_mm is the thickness at cavity-attach time, which goes
            # stale when size_backbone_spacers later grows the spacer (e.g.
            # wakeup↔power 4.0 → 4.3): cutting the stale depth left a 0.3 mm
            # un-milled skin every neighbour-face chip collided with.
            depth = thickness_mm
        else:
            depth = region.depth_mm or (
                DEFAULT_TOP_CAVITY_DEPTH_MM if region.face == "top"
                else DEFAULT_BOT_CAVITY_DEPTH_MM
            )
        # Dedupe consecutive vertices AND drop the closing point if
        # it duplicates the start — shapely / merge_cavity_polygons
        # sometimes emits both forms. Either left in place produces a
        # zero-length edge that BRepLib rejects with "No geometry".
        clean: list = []
        for p in pts:
            if not clean or (abs(clean[-1][0] - p[0]) > 1e-9 or
                             abs(clean[-1][1] - p[1]) > 1e-9):
                clean.append(p)
        if len(clean) >= 2 and (abs(clean[0][0] - clean[-1][0]) < 1e-9
                                and abs(clean[0][1] - clean[-1][1]) < 1e-9):
            clean.pop()
        if len(clean) < 3:
            continue

        # Build the closed wire directly via Wire.makePolygon (auto-
        # closes the last → first edge) and extrude. This avoids the
        # placeSketch/polyline pitfalls in cadquery 2.7.
        z_offset = thickness_mm - depth if region.face == "top" else 0.0
        verts = [cq.Vector(x, y, z_offset) for x, y in clean]
        wire = cq.Wire.makePolygon(verts, close=True)
        face = cq.Face.makeFromWires(wire)
        cavity_solid = cq.Solid.extrudeLinear(
            face, cq.Vector(0, 0, depth),
        )
        if region.face == "top":
            n_top += 1
        else:
            n_bot += 1
        body = body.cut(cq.Workplane().newObject([cavity_solid]))

    return body, n_top, n_bot


def write_spacer_step(
    spacer: Board,
    output_path: str | pathlib.Path,
    *,
    thickness_mm: float = DEFAULT_SPACER_THICKNESS_MM,
) -> dict:
    """Write `<spacer.name>.step` for the spacer's CAD body (see
    build_spacer_solid). Returns a small summary dict."""
    import cadquery as cq

    body, n_top, n_bot = build_spacer_solid(spacer, thickness_mm)
    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(body, str(out))

    return {
        "output_path":     str(out),
        "thickness_mm":    thickness_mm,
        "n_holes":         len(spacer.geometry.holes),
        "n_top_cavities":  n_top,
        "n_bot_cavities":  n_bot,
    }


def write_spacer_stl(
    spacer: Board,
    output_path: str | pathlib.Path,
    *,
    thickness_mm: float = DEFAULT_SPACER_THICKNESS_MM,
    split: bool = True,
) -> dict:
    """Mesh-export the spacer body to STL for FDM 3D printing — no
    STEP roundtrip (we have the cadquery body in hand). With
    `split=True` (default), the body is cut horizontally at midplane
    and written as two halves (`<name>_top.stl` + `<name>_bot.stl`);
    each half prints flat-down on the bed with no supports. With
    `split=False`, a single `<name>.stl` is emitted (legacy form).
    Tessellation uses `smash.export.stl`'s defaults (0.05 mm linear,
    0.1 rad angular)."""
    from smash.export.stl import (
        unique_symbol,
        write_split_stls_from_body,
        write_stl_from_body,
    )
    body, n_top, n_bot = build_spacer_solid(spacer, thickness_mm)
    out = pathlib.Path(output_path)
    info = {
        "thickness_mm":   thickness_mm,
        "n_holes":        len(spacer.geometry.holes),
        "n_top_cavities": n_top,
        "n_bot_cavities": n_bot,
    }
    if split:
        prefix = out.parent / out.stem            # drop the .stl suffix
        r = write_split_stls_from_body(body, prefix,
                                        symbol=unique_symbol(spacer.name))
        info.update({
            "output_top_path":  r["top"]["output_path"],
            "output_bot_path":  r["bot"]["output_path"],
            "split_z_mm":       r["z_split_mm"],
            "symbol":           r["symbol"],
            "top_file_size_b":  r["top"]["file_size_b"],
            "bot_file_size_b":  r["bot"]["file_size_b"],
        })
    else:
        r = write_stl_from_body(body, out)
        info.update(r)
    return info


def write_spacer_cam_notes(spacer: Board, output_path: str | pathlib.Path,
                            *, thickness_mm: float = DEFAULT_SPACER_THICKNESS_MM,
                            material: str = SPACER_MATERIAL_DEFAULT,
                            finish: str = SPACER_FINISH_DEFAULT,
                            ) -> dict:
    """Write a `<output_path>` Markdown file with the fab callout the
    shop needs alongside the STEP — laminate + finish, thickness,
    tolerances, the filled-via spec, NPTH + routed-cavity callouts.

    The STEP carries geometry but not the build spec; the critical part
    of this file is the **filled-via** callout — the spacer is a routable
    FR4 interposer whose top↔bottom LGA lands are joined by filled
    through-vias, and the fill must be capped + plated over so the lands
    seat co-planar against the tiles reflowed above and below.
    """
    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    g = spacer.geometry
    diameter_mm = (g.diameter_mm if g and g.shape == "circle"
                   and g.diameter_mm else None)
    n_holes = len(g.holes) if g and g.holes else 0
    if g and g.holes:
        hole_dia = g.holes[0].diameter_mm
    else:
        hole_dia = None

    n_top_cavs = sum(1 for r in (spacer.cavity_placements or [])
                     if getattr(r, "face", "top") == "top")
    n_bot_cavs = sum(1 for r in (spacer.cavity_placements or [])
                     if getattr(r, "face", "top") == "bottom")
    vias = getattr(spacer, "vias", None) or []
    n_vias = len(vias)
    n_filled = sum(1 for v in vias if getattr(v, "filled", False))

    lines = [
        f"# `{spacer.name}` — fab callout",
        "",
        f"Companion to `{out.with_suffix('.step').name}` (3D geometry).",
        "",
        "## Material",
        "",
        f"- **{material}** PCB interposer (same laminate family as the "
        "rigid tiles)",
        f"- thickness: {thickness_mm:.2f} mm",
        f"- outline: Ø {diameter_mm:.1f} mm disc" if diameter_mm
        else "- outline: see STEP",
        "",
        "## Surface finish",
        "",
        f"- **{finish}** — solderable + flat (the spacer reflows to the "
        "tiles above and below)",
        "- green LPSM solder mask both faces; lands left exposed",
        "",
        "**Why FR4, not anodised Al:** the spacer is a routable PCB "
        "interposer — copper LGA lands on both faces joined by filled "
        "through-vias carry the power/GND/CAN backbone straight through "
        "on the same net, and it is reflow-soldered to the rigid tiles "
        "above and below. An anodised-aluminium disc can do neither (no "
        "plated vias, oxide won't take solder); the CNC-Al spacer was "
        "abandoned when the snake-flex interconnect proved infeasible. "
        "Per-board structural support is now carried by copper-coin "
        "inserts in the rigid tiles, not the spacer.",
        "",
        "## Tolerances",
        "",
        f"- overall thickness: ± {SPACER_TOLERANCE_MM} mm",
        f"- routed outline / cavity edge: ± {SPACER_ROUTE_TOLERANCE_MM} mm",
        "",
        "## Features",
        "",
        (f"- {n_vias} filled through-via(s)"
         + (f" ({n_filled} capped + plated over for co-planar lands)"
            if n_filled else "")
         if n_vias else "- no filled vias (mechanical-only spacer)"),
        (f"- {n_holes} NPTH potting hole(s), Ø {hole_dia:.1f} mm each"
         if n_holes and hole_dia else "- no NPTH holes"),
        f"- {n_top_cavs} top-face routed cavity(ies), "
        f"depth {DEFAULT_TOP_CAVITY_DEPTH_MM} mm",
        f"- {n_bot_cavs} bottom-face routed cavity(ies), "
        f"depth {DEFAULT_BOT_CAVITY_DEPTH_MM} mm",
        "- cavity / cutout geometry per the STEP + Gerber/drill set",
        "",
        "## Notes",
        "",
        "- All routing + drill from the STEP / fab data. No flat 2D "
        "drawing needed.",
        "- Via fill must be capped and plated over (not just plugged) so "
        "the LGA lands seat co-planar — the backbone + cell rails rely "
        "on the fill being flush with the land.",
        "- A through-cut cavity (battery compartment) is a routed window, "
        "not a blind pocket — cells nest into the aligned column of cuts.",
        "",
    ]
    out.write_text("\n".join(lines))
    return {
        "output_path": str(out),
        "material": material,
        "finish": finish,
        "n_top_cavities": n_top_cavs,
        "n_bot_cavities": n_bot_cavs,
        "n_holes": n_holes,
    }


def write_all_spacer_steps(
    boards: dict,
    output_dir: str | pathlib.Path,
    *,
    thickness_mm: float = DEFAULT_SPACER_THICKNESS_MM,
    also_stl: bool = True,
    also_cam_notes: bool = True,
    subdir: bool = False,
) -> list[dict]:
    """Write one STEP per spacer in `boards` to `output_dir`.

    Convenience wrapper for the twin's emit pipeline. Returns the list
    of summary dicts from `write_spacer_step`. With `also_stl=True`
    (default), a sibling `.stl` is dropped next to each `.step` for
    the 3D-print toolchain. With `also_cam_notes=True` (default), a
    sibling `_cam.md` Markdown file is dropped next to each `.step`
    carrying the material + anodise + tolerance callouts the CAM
    shop needs (the STEP alone doesn't tell the fab to ship Al with
    Type II finish — geometry without material is incomplete).
    """
    out_dir = pathlib.Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear stale spacer STEPs / STLs / CAM notes from earlier runs —
    # the snake order (hence spacer names) changes, so leftover files
    # would misrepresent the panel. Scope the glob to `spacer_*` so
    # this is safe to share a directory with the board/panel STEPs
    # (which keep stable names).
    if not subdir:
        for pattern in ("spacer_*.step", "spacer_*.stl",
                        "spacer_*_top.stl", "spacer_*_bot.stl",
                        "spacer_*_cam.md"):
            for old in out_dir.glob(pattern):
                old.unlink()
    results = []
    for name, board in boards.items():
        if not getattr(board, "is_spacer", False):
            continue
        # subdir=True drops each spacer in its own out_dir/<name>/ folder
        # (board-per-folder layout); else flat in out_dir.
        sp_dir = out_dir / name if subdir else out_dir
        if subdir:
            sp_dir.mkdir(parents=True, exist_ok=True)
        # Each spacer renders at its OWN milled thickness: the backbone
        # interposers are SPACER_THICKNESS_MM (4 mm), but the battery compartment
        # is a run of thinner discs (thickness_override_mm) so a single fab panel
        # stays under the layer cap. thickness_mm is the fallback for boards that
        # don't expose the property.
        t = getattr(board, "thickness_mm", None) or thickness_mm
        r = write_spacer_step(
            board, sp_dir / f"{name}.step",
            thickness_mm=t,
        )
        if also_stl:
            r_stl = write_spacer_stl(
                board, sp_dir / f"{name}.stl",
                thickness_mm=t,
            )
            r["stl_output_top_path"] = r_stl["output_top_path"]
            r["stl_output_bot_path"] = r_stl["output_bot_path"]
            r["stl_top_file_size_b"] = r_stl["top_file_size_b"]
            r["stl_bot_file_size_b"] = r_stl["bot_file_size_b"]
        if also_cam_notes:
            r_cam = write_spacer_cam_notes(
                board, sp_dir / f"{name}_cam.md",
                thickness_mm=t,
            )
            r["cam_notes_path"] = r_cam["output_path"]
            r["material"] = r_cam["material"]
            r["finish"] = r_cam["finish"]
        results.append(r)
    return results


# ═════════════════════════════════════════════════════════════════════════
# PEEK battery holder (2026-11-14) — replaces the 6 FR4 battery spacers
# ═════════════════════════════════════════════════════════════════════════
#
# Machined PEEK sleeve between cell_floor_board (E, below) and fin_ble_board
# (L, above). Exposed to air on the outside, so it is also the RF window for
# the conformal antennas. Cells are solder-free and replaceable (spring /
# pressure contacts on E and L), so the compartment itself is NOT potted:
# the potting holes are plain through-channels that carry potting past the
# compartment to the thin aft gaps (D/C/B). The L↔E backbone runs on an
# integral rigid-flex link down the SOUTH crescent (flex channel below).
#
# Frame: the battery spacers' own frame (math y-up, +Z = nose), so the
# fold-projected potting holes the generator already computes for them line
# up with E's and L's holes by construction. The cell triangle (90/210/330°)
# and the south channel are mirror-symmetric, so the fold mirror between E
# and L does not move them; the two antenna pockets (30°/150°) swap under the
# mirror — both are cut, so either assignment holds.

PEEK_HOLDER_NAME = "peek_battery_holder"
PEEK_CELL_BORE_R_MM = 7.6          # Ø14.8 TLM-1520HPM + 0.2 mm radial clearance
PEEK_CELL_CLUSTER_R_MM = 8.6       # cell-centre triangle (matches P_CELL_CONTACTS)
PEEK_CELL_ANGLES_DEG = (90.0, 210.0, 330.0)
PEEK_WALL_MM = 1.0                 # outer skin over the crescents
PEEK_FLEX_CHANNEL_W_MM = 10.0      # L↔E rigid-flex link (~46 nets, 2 layers)
PEEK_FLEX_CHANNEL_D_MM = 1.5       # radial gap for the flex (+ bend relief)
PEEK_FLEX_ANGLE_DEG = 270.0        # south crescent
PEEK_ANT_POCKET_W_MM = 8.0         # conformal antenna flex pockets
PEEK_ANT_POCKET_D_MM = 1.0
PEEK_ANT_ANGLES_DEG = (24.0, 156.0)   # off the 30/150° crescent centres: 0.68 mm web to the 45° potting hole
PEEK_MATERIAL = "PEEK (unfilled, natural) — RF window; εr ≈ 3.2, tanδ ≈ 0.003"


def _wall_slot(cq, r_outer_wall: float, angle_deg: float, width: float,
               depth: float, height: float):
    """A rectangular through-slot whose outer face sits on the inner face of
    the PEEK skin (r = r_outer_wall), centred on `angle_deg`."""
    import math
    r_mid = r_outer_wall - depth / 2.0
    a = math.radians(angle_deg)
    return (cq.Workplane("XY")
            .center(r_mid * math.cos(a), r_mid * math.sin(a))
            .transformed(rotate=(0, 0, angle_deg))
            .rect(depth, width)
            .extrude(height))


def build_peek_holder_solid(battery_spacers: list, height_mm: float,
                            diameter_mm: float = 34.0):
    """Build the PEEK holder body. `battery_spacers` are the generator's
    spacer_battery_* Boards (after _mark_battery_pockets): their potting
    holes (deduplicated) become Ø-matched through-holes. Returns
    `(body, holes)` where `holes` is the list of (x, y, Ø) drilled."""
    import math
    import cadquery as cq

    R = diameter_mm / 2.0
    body = cq.Workplane("XY").circle(R).extrude(height_mm)

    # Cell bores — through, so cells drop in from either end.
    for ang in PEEK_CELL_ANGLES_DEG:
        a = math.radians(ang)
        cx, cy = (PEEK_CELL_CLUSTER_R_MM * math.cos(a),
                  PEEK_CELL_CLUSTER_R_MM * math.sin(a))
        body = body.cut(cq.Workplane("XY").center(cx, cy)
                        .circle(PEEK_CELL_BORE_R_MM).extrude(height_mm))

    # The three bores overlap (cells nearly touch), which would leave a loose
    # trefoil island at the centre — cut the cell-centre triangle so the
    # holder is ONE solid with a single merged cell cavity.
    tri = [(PEEK_CELL_CLUSTER_R_MM * math.cos(math.radians(a)),
            PEEK_CELL_CLUSTER_R_MM * math.sin(math.radians(a)))
           for a in PEEK_CELL_ANGLES_DEG]
    body = body.cut(cq.Workplane("XY").polyline(tri).close().extrude(height_mm))

    r_skin = R - PEEK_WALL_MM
    body = body.cut(_wall_slot(cq, r_skin, PEEK_FLEX_ANGLE_DEG,
                               PEEK_FLEX_CHANNEL_W_MM, PEEK_FLEX_CHANNEL_D_MM,
                               height_mm))
    for ang in PEEK_ANT_ANGLES_DEG:
        body = body.cut(_wall_slot(cq, r_skin, ang, PEEK_ANT_POCKET_W_MM,
                                   PEEK_ANT_POCKET_D_MM, height_mm))

    # Potting through-holes — union of every battery spacer's holes.
    seen, holes = set(), []
    for sp in battery_spacers:
        g = getattr(sp, "geometry", None)
        for h in (getattr(g, "holes", None) or []):
            x, y = h.position_mm
            key = (round(x, 2), round(y, 2))
            if key in seen:
                continue
            seen.add(key)
            holes.append((x, y, h.diameter_mm))
            body = body.cut(cq.Workplane("XY").center(x, y)
                            .circle(h.diameter_mm / 2.0).extrude(height_mm))
    return body, holes


def write_peek_holder(battery_spacers: list, out_dir: str | pathlib.Path,
                      height_mm: float, diameter_mm: float = 34.0) -> dict:
    """Write <out_dir>/peek_battery_holder/{.step,.stl,_cam.md}."""
    import cadquery as cq

    d = pathlib.Path(out_dir) / PEEK_HOLDER_NAME
    d.mkdir(parents=True, exist_ok=True)
    body, holes = build_peek_holder_solid(battery_spacers, height_mm,
                                          diameter_mm)
    step = d / f"{PEEK_HOLDER_NAME}.step"
    stl = d / f"{PEEK_HOLDER_NAME}.stl"
    cq.exporters.export(body, str(step))
    cq.exporters.export(body, str(stl))
    bb = body.val().BoundingBox()
    vol = body.val().Volume()
    hole_lines = "\n".join(f"| ({x:+.3f}, {y:+.3f}) | Ø{dia:.2f} |"
                           for x, y, dia in holes) or "| — | — |"
    (d / f"{PEEK_HOLDER_NAME}_cam.md").write_text(f"""# {PEEK_HOLDER_NAME} — machining notes (generated)

Material: {PEEK_MATERIAL}. Machined, not moulded (tolerances below).
Envelope: Ø{diameter_mm:.1f} × {height_mm:.2f} mm (bbox {bb.xlen:.2f} × {bb.ylen:.2f} × {bb.zlen:.2f}); volume {vol:.0f} mm³ (≈ {vol * 1.30e-3:.2f} g at 1.30 g/cm³).
Frame: math y-up, +Z toward the nose; same frame as the battery spacers it replaces.

## Features (all through, full height)
- 3 cell bores Ø{2 * PEEK_CELL_BORE_R_MM:.1f} at r = {PEEK_CELL_CLUSTER_R_MM} mm, {', '.join(f'{a:.0f}°' for a in PEEK_CELL_ANGLES_DEG)}, merged into one trefoil cavity (centre triangle cut — the bores overlap).
  Thinnest skin at the bores: {diameter_mm / 2 - PEEK_CELL_CLUSTER_R_MM - PEEK_CELL_BORE_R_MM:.2f} mm (⚠ below the {PEEK_WALL_MM} mm target — the Ø14.8 cells in a Ø34 envelope leave no more).
- Flex channel (L↔E integral rigid-flex): {PEEK_FLEX_CHANNEL_W_MM} × {PEEK_FLEX_CHANNEL_D_MM} mm at {PEEK_FLEX_ANGLE_DEG:.0f}° (south), against a {PEEK_WALL_MM} mm skin.
- Antenna pockets (conformal flex antennas): {PEEK_ANT_POCKET_W_MM} × {PEEK_ANT_POCKET_D_MM} mm at {', '.join(f'{a:.0f}°' for a in PEEK_ANT_ANGLES_DEG)}, against a {PEEK_WALL_MM} mm skin.
- Potting through-holes ({len(holes)}), fold-projected from cell_floor_board + fin_ble_board:

| Position (mm) | Diameter |
|---|---|
{hole_lines}

## Tolerances
- Height ±0.05 mm (sets the cell-contact preload between E and L).
- Bores / slots / holes ±0.05 mm; outer Ø ±0.05 mm.

## Open items
- ⚠ The boards' OTHER potting hole (at 225° in this frame, on both
  cell_floor_board and fin_ble_board) lies entirely inside a cell bore. With
  the compartment no longer potted it would pour potting onto the cells:
  plug it on E and L (or drop it from those two boards) — only the 45° hole
  carries potting through the holder to the aft gaps.
- Cell contact preload / retention for replaceable cells (spring contacts on E and L).
- Confirm the flex bend radius against the {PEEK_FLEX_CHANNEL_D_MM} mm channel depth once the flex stackup is chosen.
""")
    return {"step": step, "stl": stl, "holes": holes, "volume_mm3": vol,
            "bbox": (bb.xlen, bb.ylen, bb.zlen)}


# ═════════════════════════════════════════════════════════════════════════
# Gap hardware (2026-11-14) — spacers are no longer PCBs
# ═════════════════════════════════════════════════════════════════════════
#
# The tower is potted inside an LDS sleeve; inter-board signals run on the
# sleeve and land on board-edge castellations, so a gap needs no FR4
# interposer. What remains per gap is mechanical:
#   • the two aft-most gaps carry the most setback load → a plain 1 mm
#     7075-T6 hard-anodised RING (recessed inside the castellation zone),
#     with feed + vent slots for the potting;
#   • the battery compartment → one Al battery RING round the cells (takes
#     the cells' 50k-rpm centrifugal load), feed + vent slots;
#   • every other gap → 4 small PEEK STANDOFFS that set the gap; potting
#     fills the rest.
# Frame: PHYSICAL (the aft_end_board / chain[0] frame), +Z toward the nose.

GAP_RING_GAPS = ("spacer_aft_end_board_activation_interface",
                 "spacer_activation_interface_cell_floor_board")
RING_R_IN_MM, RING_R_OUT_MM = 15.2, 16.2      # 1.0 mm wall, OD 32.4
RING_CLEARANCE_MM = 0.2                       # silk "standoff distance" each side
# Battery HOLDER (2026-11-14, replaces the Ø38 battery ring): a 7075-T6
# hard-anodised block inside the Ø34 envelope with three cell bores. Cells
# bear on the bore FLANKS (location fit); a shallow relief at each cell's
# outer tip keeps the cell off the thin (0.8 mm) skin there, so the
# centrifugal load (~2.1 kN/cell at 50k rpm) enters via the flanks and the
# skin carries HOOP TENSION only (≈ F/√3 ≈ 1.2 kN → ~74 MPa on 0.8 × 21 mm).
# The skin must stay hoop-continuous: potting enters through small radial
# holes + an axial channel, never a full-height slot.
BATT_HOLDER_R_OUT_MM = 17.0
BATT_CLUSTER_R_MM = 8.6
BATT_CELL_ANGLES_DEG = (90.0, 210.0, 330.0)
BATT_BORE_R_MM = 7.45                 # Ø14.8 cell + 0.05 radial location fit
BATT_TIP_RELIEF_R_MM = 7.6            # tip relief → skin = 17 − 8.6 − 7.6 = 0.8 mm
BATT_TIP_RELIEF_HALF_DEG = 30.0
BATT_FEED_ANGLES_DEG = (0.0, 180.0)   # behind the sleeve's feed / vent grooves
BATT_NOTCH_R_IN_MM = 12.0            # notch reaches into the cell cavity (bore edge ≈ r 13.5 at 0°/180°)
BATT_CHANNEL_D_MM, BATT_CHANNEL_R_MM, BATT_CHANNEL_ANGLE_DEG = 3.0, 13.0, 135.0   # = the boards' potting hole (continuous channel)
# Headroom (2026-11-14, user): the compartment is the cell length + a
# headroom above the cells; there the holder is just its EDGE RING
# (r 16–17), so fin_ble_board's whole bottom face (inside r 15.8) is free
# for parts ≤ headroom − 0.2 mm. The cells' existing + tab extensions are
# bent across the headroom to the P_CELL_CONTACTS pads on fin_ble.
BATT_CELL_LENGTH_MM = 21.0
BATT_HEADROOM_MM = 2.0
BATT_TOP_RING_R_IN_MM = 16.0
BATT_PART_CLEARANCE_MM = 0.2

SLOT_W_MM = 2.0                               # notch width (tangential)
NOTCH_DEPTH_MM = 0.5                          # notch depth (axial), top + bottom edge
SLOT_ANGLES_DEG = (0.0, 180.0)                # = castellation reserved sectors
STANDOFF_D_MM, STANDOFF_R_MM = 1.2, 15.8
STANDOFF_ANGLES_DEG = (45.0, 135.0, 225.0, 315.0)   # symmetric under fold + 180° turn


def battery_holder_cavity():
    """Shapely polygon of the holder's CELL cavity (bores + centre triangle +
    tip reliefs), physical frame."""
    import math
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    parts = []
    tri = []
    for ang in BATT_CELL_ANGLES_DEG:
        a = math.radians(ang)
        cx, cy = BATT_CLUSTER_R_MM * math.cos(a), BATT_CLUSTER_R_MM * math.sin(a)
        tri.append((cx, cy))
        parts.append(Point(cx, cy).buffer(BATT_BORE_R_MM, 96))
        # tip relief: annular sector round the cell's outermost point
        pts = []
        n = 24
        for k in range(n + 1):
            t = math.radians(ang - BATT_TIP_RELIEF_HALF_DEG
                             + 2 * BATT_TIP_RELIEF_HALF_DEG * k / n)
            pts.append((cx + BATT_TIP_RELIEF_R_MM * math.cos(t),
                        cy + BATT_TIP_RELIEF_R_MM * math.sin(t)))
        for k in range(n, -1, -1):
            t = math.radians(ang - BATT_TIP_RELIEF_HALF_DEG
                             + 2 * BATT_TIP_RELIEF_HALF_DEG * k / n)
            pts.append((cx + (BATT_BORE_R_MM - 0.2) * math.cos(t),
                        cy + (BATT_BORE_R_MM - 0.2) * math.sin(t)))
        parts.append(Polygon(pts))
    parts.append(Polygon(tri))
    return unary_union(parts)


def _batt_channel_xy():
    import math
    a = math.radians(BATT_CHANNEL_ANGLE_DEG)
    return BATT_CHANNEL_R_MM * math.cos(a), BATT_CHANNEL_R_MM * math.sin(a)


def _poly_extrude(cq, poly, h, z0=0.0):
    # drop sub-µm segments from the buffered unions (OCC rejects them)
    poly = poly.simplify(0.003, preserve_topology=True)
    ext = list(poly.exterior.coords)[:-1]
    wp = cq.Workplane("XY").polyline(ext).close().extrude(h).translate((0, 0, z0))
    for hole in poly.interiors:
        hp = (cq.Workplane("XY").polyline(list(hole.coords)[:-1]).close()
              .extrude(h).translate((0, 0, z0)))
        wp = wp.cut(hp)
    return wp


def _battery_holder_body(cq, h):
    """Cell-locating block (z 0 … cell length) + a 1 mm EDGE RING above it
    (up to h = cell length + headroom). Potting: edge notches at the bottom
    (feed) and the ring's top edge (vent) at 0° / 180°, + the axial channel."""
    import math
    hc = min(BATT_CELL_LENGTH_MM, h)
    body = cq.Workplane("XY").circle(BATT_HOLDER_R_OUT_MM).extrude(hc)
    body = body.cut(_poly_extrude(cq, battery_holder_cavity(), hc))
    cx, cy = _batt_channel_xy()
    body = body.cut(cq.Workplane("XY").center(cx, cy)
                    .circle(BATT_CHANNEL_D_MM / 2.0).extrude(hc))
    if h > hc + 1e-6:
        ring = (cq.Workplane("XY").circle(BATT_HOLDER_R_OUT_MM)
                .circle(BATT_TOP_RING_R_IN_MM).extrude(h - hc)
                .translate((0, 0, hc)))
        body = body.union(ring)
    for ang in BATT_FEED_ANGLES_DEG:
        a = math.radians(ang)
        for z0, r0 in ((0.0, BATT_NOTCH_R_IN_MM),
                       (h - NOTCH_DEPTH_MM, BATT_TOP_RING_R_IN_MM - 0.5)):
            r1 = BATT_HOLDER_R_OUT_MM + 0.5
            cut = (cq.Workplane("XY")
                   .center((r0 + r1) / 2 * math.cos(a), (r0 + r1) / 2 * math.sin(a))
                   .transformed(rotate=(0, 0, ang))
                   .rect(r1 - r0, SLOT_W_MM).extrude(NOTCH_DEPTH_MM)
                   .translate((0, 0, z0)))
            body = body.cut(cut)
    return body

def gap_kind(name: str) -> str:
    if name.startswith("spacer_battery_"):
        return "battery_holder"
    if name in GAP_RING_GAPS:
        return "ring"
    return "standoffs"


def _ring_body(cq, r_in, r_out, h):
    """Plain ring with potting NOTCHES at its top and bottom edges (at the
    feed / vent angles) — not full-height slots, so the ring stays
    hoop-continuous. Potting runs in along the board face through the
    notch on each end."""
    import math
    body = (cq.Workplane("XY").circle(r_out).circle(r_in).extrude(h))
    d = min(NOTCH_DEPTH_MM, h / 3.0)
    for ang in SLOT_ANGLES_DEG:
        a = math.radians(ang)
        rm = (r_in + r_out) / 2.0
        for z0 in (0.0, h - d):
            cut = (cq.Workplane("XY").center(rm * math.cos(a), rm * math.sin(a))
                   .transformed(rotate=(0, 0, ang))
                   .rect((r_out - r_in) * 3.0, SLOT_W_MM).extrude(d)
                   .translate((0, 0, z0)))
            body = body.cut(cut)
    return body


def _standoffs_body(cq, h):
    import math
    body = None
    for ang in STANDOFF_ANGLES_DEG:
        a = math.radians(ang)
        s = (cq.Workplane("XY")
             .center(STANDOFF_R_MM * math.cos(a), STANDOFF_R_MM * math.sin(a))
             .circle(STANDOFF_D_MM / 2.0).extrude(h))
        body = s if body is None else body.union(s)
    return body


def gap_hardware_body(name: str, boards: dict, chain: list):
    """(body, height_mm, label, kind) for the hardware of gap `name`, in the
    PHYSICAL frame with z ∈ [0, height]; None for a battery spacer that is
    not the first of its run (the run has ONE ring spanning it all)."""
    import cadquery as cq
    b = boards[name]
    kind = gap_kind(name)
    if kind == "battery_holder":
        batt = [n for n in chain if n in boards and gap_kind(n) == "battery_holder"]
        if not batt or name != batt[0]:
            return None
        h = sum(boards[n].thickness_mm for n in batt)
        return _battery_holder_body(cq, h), h, "battery_holder", kind
    h = b.thickness_mm
    if kind == "ring":
        return _ring_body(cq, RING_R_IN_MM, RING_R_OUT_MM, h), h, name, kind
    return _standoffs_body(cq, h), h, name, kind


def write_gap_hardware(boards: dict, chain: list, out_dir) -> list:
    """Write one STEP (+ STL + _cam.md) per gap's hardware into
    <out_dir>/<spacer>/; the battery run gets ONE ring in
    <out_dir>/battery_holder/. Returns summary dicts."""
    import cadquery as cq
    out_dir = pathlib.Path(out_dir)
    res = []
    batt = [n for n in chain if n in boards and gap_kind(n) == "battery_holder"]
    for name in chain:
        b = boards.get(name)
        if b is None or not getattr(b, "is_spacer", False):
            continue
        kind = gap_kind(name)
        if kind == "battery_holder":
            if name != (batt[0] if batt else None):
                continue
            h = sum(boards[n].thickness_mm for n in batt)
            body = _battery_holder_body(cq, h)
            label, mat = "battery_holder", "7075-T6 aluminium, hard anodised (insulates the live cell cans)"
            dims = (f"Ø{2*BATT_HOLDER_R_OUT_MM:.0f} × {h:.2f} mm block, 3 cell bores "
                    f"Ø{2*BATT_BORE_R_MM:.2f} (location fit on the cell flanks), tip "
                    f"reliefs ±{BATT_TIP_RELIEF_HALF_DEG:g}° to r {BATT_TIP_RELIEF_R_MM} → "
                    f"{BATT_HOLDER_R_OUT_MM - BATT_CLUSTER_R_MM - BATT_TIP_RELIEF_R_MM:.1f} mm "
                    "skin in hoop TENSION only; potting: top + bottom edge notches "
                    f"{SLOT_W_MM} × {NOTCH_DEPTH_MM} mm at {BATT_FEED_ANGLES_DEG} + axial Ø"
                    f"{BATT_CHANNEL_D_MM} channel at {BATT_CHANNEL_ANGLE_DEG:g}°; above the "
                    f"{BATT_CELL_LENGTH_MM:g} mm cell block only a 1 mm EDGE RING (r "
                    f"{BATT_TOP_RING_R_IN_MM:g}–{BATT_HOLDER_R_OUT_MM:g}) over the "
                    f"{BATT_HEADROOM_MM:g} mm headroom under fin_ble; the cells' + tab "
                    "extensions bend across it to P_CELL_CONTACTS")
        elif kind == "ring":
            h = b.thickness_mm
            body = _ring_body(cq, RING_R_IN_MM, RING_R_OUT_MM, h)
            label, mat = name, "7075-T6 aluminium, hard anodised (anodise = insulation)"
            dims = (f"ring ID Ø{2*RING_R_IN_MM:.1f} / OD Ø{2*RING_R_OUT_MM:.1f}"
                    f" × {h:.2f} mm")
        else:
            h = b.thickness_mm
            body = _standoffs_body(cq, h)
            label, mat = name, "PEEK (plasma-treat before bonding)"
            dims = (f"{len(STANDOFF_ANGLES_DEG)} × Ø{STANDOFF_D_MM} × {h:.2f} mm "
                    f"standoffs at r = {STANDOFF_R_MM} mm")
        d = out_dir / label
        d.mkdir(parents=True, exist_ok=True)
        step, stl = d / f"{label}.step", d / f"{label}.stl"
        cq.exporters.export(body, str(step))
        cq.exporters.export(body, str(stl))
        slots = (f"- Potting notches {SLOT_W_MM} mm wide × {NOTCH_DEPTH_MM} mm deep "
                 "at the TOP and BOTTOM edge (ring stays hoop-continuous) at "
                 f"{', '.join(f'{a:.0f}°' for a in SLOT_ANGLES_DEG)} "
                 "(= the sleeve's feed / vent grooves).\n"
                 if kind == "ring" else "")
        (d / f"{label}_cam.md").write_text(
            f"# {label} — gap hardware (generated)\n\n"
            f"Kind: {kind}. Material: {mat}.\n"
            f"Geometry: {dims}.\n{slots}"
            "Frame: physical stack frame (aft_end_board), +Z toward the nose.\n"
            "Not a PCB: the gap is potted inside the LDS sleeve; signals cross "
            "on the sleeve via board-edge castellations.\n")
        res.append({"name": label, "kind": kind, "step": step, "height_mm": h})
    return res
