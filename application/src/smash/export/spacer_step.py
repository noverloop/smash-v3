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

import dataclasses
import math

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

# (2026-11-15) After the aft reorder the battery holder sits on aft_end, so
# the aft-most PLAIN gap — activation_interface ↔ fin_ble — carries the Al
# ring (the old names pointed at gaps that no longer exist, which silently
# dropped the rings). The ring IS the gap's spacer: no standoffs in it.
# (2026-11-21, user) fin_ble merged into activation: the ring moves to
# activation ↔ wakeup (slot S4's gap), and wakeup ↔ power (slot S1's gap since
# the p21 antenna move) gets one too — 2 mm GF30 PEEK behind both slots.
GAP_RING_GAPS = ("spacer_activation_interface_wakeup_board",
                 "spacer_wakeup_board_power_board")
# Gaps with NO hardware. (The radar ↔ nose_cap entry went with the nose_cap
# PCB, retired 2026-11-18.)
NO_HARDWARE_GAPS: tuple = ()
# (2026-11-17, user) Gap rings are GF30 PEEK (30 % glass-filled), 2.0 mm wall,
# CLOSED all round: RF-transparent (εr ≈ 3.8, low loss) behind the slot
# antennas, so no openings; twice the 1 mm Al ring's area to make up for
# PEEK's lower strength (setback load is shared with the potted monolith —
# check in the launch FEA). Not carbon-filled (conductive / lossy at GHz).
RING_MATERIAL = "PEEK GF30 (30 % glass-filled), annealed after machining"
RING_IS_METAL = False
RING_LABEL = "PEEK RING"
RING_R_IN_MM, RING_R_OUT_MM = 15.0, 17.0      # 2.0 mm wall, OD 34 = board edge; bears on the
                                              # mask-tented castellation annuli (mask + anodise = 2× insulation)


@dataclasses.dataclass(frozen=True)
class RingSpec:
    material: str
    is_metal: bool
    label: str
    r_in: float
    r_out: float = 17.0


RING_PEEK = RingSpec(RING_MATERIAL, False, RING_LABEL, 15.0)
RING_AL = RingSpec("7075-T6 aluminium, hard anodised (anodise = insulation)", True,
                   "AL RING", 16.0)
# (2026-11-17, user) 2 mm GF30 PEEK ONLY in the slot gaps; every other gap
# keeps a 1 mm Al ring to preserve board space. (2026-11-21) fin_ble merged
# into activation and S1 moved up: the slot gaps are now activation↔wakeup
# (S4) and wakeup↔power (S1), so wakeup↔power is PEEK.
AL_RING_GAPS = ("spacer_power_board_companion_compute",
                # (2026-11-21) fixed noses: compute ↔ payload is an ordinary
                # sized gap with a 1 mm Al ring in every config
                "spacer_companion_compute_radar_module",
                "spacer_companion_compute_qpd_module",
                "spacer_companion_compute_camera_module",
                "spacer_companion_compute_usb_nose")


def ring_spec(spacer_name: str) -> RingSpec:
    return RING_AL if spacer_name in AL_RING_GAPS else RING_PEEK

RING_CLEARANCE_MM = 0.2                       # silk "standoff distance" each side
# (2026-11-17, user) A ring is OPEN only where a slot antenna sits in its
# gap, over that slot's span + a margin (antenna_slots.ring_openings) — no
# metal behind the slot. The rings are structural, so the opening is kept as
# narrow as the slot allows; gaps without a slot keep a full ring. A C-ring
# that still spans > 180° locates and spaces its two boards; potting fills
# the opening.


def ring_open_sector(spacer_name: str):
    """(a0, a1) physical degrees where this gap's ring is open, or None.
    Only a METAL ring opens behind a slot; the PEEK ring stays closed."""
    if not ring_spec(spacer_name).is_metal:
        return None
    from smash.parts.antenna_slots import ring_openings
    for (lo, hi), sec in ring_openings().items():
        if spacer_name == f"spacer_{lo}_{hi}":
            return sec
    return None
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
BATT_FEED_ANGLES_DEG = (105.0, 285.0) # behind the sleeve's feed / vent grooves (= its seams)
BATT_NOTCH_R_IN_MM = 9.0             # notch reaches into the cell cavity at the seam angles
BATT_CHANNEL_D_MM, BATT_CHANNEL_R_MM, BATT_CHANNEL_ANGLE_DEG = 3.0, 13.0, 135.0   # = the boards' potting hole (continuous channel)
# (2026-11-21, user) The compartment IS potted now: a full-height LINK SLOT
# cuts the 0.26 mm web between the axial potting channel and the 90° cell
# bore, so potting rising in the channel floods the cell cavity (the three
# bores join through the centre triangle) and vents up through the headroom
# into activation_interface's potting hole. Inboard of the 0.8 mm skin
# (r ≈ 9-13), so the skin stays hoop-continuous.
BATT_CHANNEL_LINK_CELL_DEG = 90.0
BATT_CHANNEL_LINK_W_MM = 1.5
# Headroom (2026-11-14, user): the compartment is the cell length + a
# headroom above the cells; there the holder is just its EDGE RING
# (r 16–17), so fin_ble_board's whole bottom face (inside r 15.8) is free
# for parts ≤ headroom − 0.2 mm. The cells' existing + tab extensions are
# bent across the headroom to the P_CELL_CONTACTS pads on fin_ble.
BATT_CELL_LENGTH_MM = 21.0
# (2026-11-15) CLOSED FLOOR under the cells: they stand on it, and its
# underside carries a shallow POCKET for the launch piezo (Ø10 × 0.4 disc on
# aft_end's top, on the spin axis) + its comparator column (0402s + X2SON).
# (2026-11-23, user) The floor is a SEPARATE 7075 PLATE: the holder is open at
# the aft end, the pre-wired cells slide in from below into the built tower,
# the plate closes it, then aft_end + the aft cap go on and the cap's M2 screws
# clamp cap / aft_end / plate into the holder's taps. Same 1.2 mm, same pockets.
BATT_FLOOR_MM = 1.2
BATT_PZ_POCKET_DEPTH_MM = 0.6
BATT_PZ_DISC_POCKET_R_MM = 5.4                  # Ø10 disc + 0.4 radial clearance
BATT_PZ_SLOT_MM = (4.6, -2.4, 10.4, 2.4)        # comparator column slot (x0, y0, x1, y1)
# (2026-11-23) MAX9064 UCSP-4 is 0.69 mm (> the 0.6 mm pocket): a local 1.8 mm □
# sub-pocket over U_COMP_PZ (7.8, 0) to 0.69 + 0.2 → 0.9 mm, leaving a 0.3 mm
# 7075 web over that 1.8 mm span only.
BATT_PZ_COMP_POCKET_MM = (6.9, -0.9, 8.7, 0.9)
BATT_PZ_COMP_POCKET_DEPTH_MM = 0.9
BATT_HEADROOM_MM = 0.4           # (2026-11-23) flat AWG 30 + joint over the trimmed + pin (was 1.0 for pin→wire joints, 2.0 for tabs)
# (2026-11-20, user) Tadiran /P cells (axial pins), no tabs: each − pin goes
# straight down through a floor hole into a PTH on aft_end_board.
# (2026-11-23, user) Each cell is PRE-WIRED before it slides in: the + pin is
# trimmed, an AWG 30 wire is soldered flat across the cell's + end and laid
# down a GROOVE in that cell's own bore wall, so it rides in with the cell and
# exits through a floor-plate hole straight into its PTH on aft_end_board (no
# more trip across the cell tops to the potting channel → headroom 1.0 → 0.4).
# Groove at the cell angle −90° (bore wall): clears the 0.8 mm skin, the
# potting channel, the cap screws / counterbores, the fixture dowel holes and
# the diode ring (aft_cap / test_battery_compartment check it).
WIRE_GROOVE_OFFSET_DEG = -90.0
WIRE_GROOVE_D_MM = 0.9           # AWG 30 PTFE (Ø ~0.5) + clearance
WIRE_HOLE_D_MM = 1.2             # floor-plate hole at the groove exit
CELL_PIN_HOLE_D_MM = 1.2         # floor hole round the Ø0.8 − pin (placeholder)
WIRE_FAN_POCKET_DEPTH_MM = 0.6   # (2026-11-23) now just the channel-exit pocket (potting path)
BATT_TOP_RING_R_IN_MM = 16.0
BATT_PART_CLEARANCE_MM = 0.2

SLOT_W_MM = 2.0                               # notch width (tangential)
NOTCH_DEPTH_MM = 0.5                          # notch depth (axial), top + bottom edge
STANDOFF_D_MM = 1.2
# (2026-11-15) Standoffs sit fully INSIDE the aluminium rings' bore (incl. the
# ring's clearance), so they never overlap a ring / the holder's top ring:
# standoff keepout (edge + clearance) ends where the ring keepout starts → r 14.2 mm.
STANDOFF_R_MM = RING_R_IN_MM - 2 * RING_CLEARANCE_MM - STANDOFF_D_MM / 2.0   # keepouts touch, never overlap
# (2026-11-15) 75/165/255/345°: still symmetric under the fold + 180° turn,
# 30° clear of the boards' Ø3 potting hole at 135° (r 13) and of the sleeve
# seams at 105/285°.
STANDOFF_ANGLES_DEG = (75.0, 165.0, 255.0, 345.0)


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


def cell_centres_xy() -> list:
    """Cell axes (physical frame) — the − pins / floor holes."""
    import math
    return [(BATT_CLUSTER_R_MM * math.cos(math.radians(a)),
             BATT_CLUSTER_R_MM * math.sin(math.radians(a))) for a in BATT_CELL_ANGLES_DEG]


def cell_wire_pads_xy() -> list:
    """+ wire exits = the bore-wall grooves (2026-11-23): the floor-plate hole
    and the PTH on aft_end_board sit straight below each groove."""
    import math
    out = []
    for (cx, cy), th in zip(cell_centres_xy(), BATT_CELL_ANGLES_DEG):
        a = math.radians(th + WIRE_GROOVE_OFFSET_DEG)
        out.append((round(cx + (BATT_BORE_R_MM + 0.05) * math.cos(a), 3),
                    round(cy + (BATT_BORE_R_MM + 0.05) * math.sin(a), 3)))
    return out


def wire_fan_pocket():
    """Shapely outline of the plate-underside pocket at the potting-channel
    exit (the + wires no longer use it since 2026-11-23; the potting groove
    still joins it to the piezo pocket)."""
    from shapely.geometry import Point
    cx, cy = _batt_channel_xy()
    return Point(cx, cy).buffer(BATT_CHANNEL_D_MM / 2.0 + 0.6, 48)


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


# (2026-11-20) + an ANNULUS for the parachute matrix's 16 steering diodes
# (BAS40-02L, 0.39 mm tall) on aft_end's top at r 6.4: same 0.6 mm depth; the
# floor keeps 0.6 mm over the 2 mm span (~130 MPa under the cells' setback).
BATT_DIODE_RING_MM = (7.2, 9.0)


# (2026-11-21, user: "all potted") a POTTING GROOVE joins the floor-underside
# pocket (piezo disc + comparator slot + diode ring = one cavity) to the Ø3
# channel's + wire fan-out pocket, so the potting rising in the channel floods
# it — no trapped air round the piezo, comparator or diodes. Along the
# channel's own angle (135°: between the 90° cell pin and the 153° cap screw).
BATT_POT_GROOVE_W_MM = 1.0


def piezo_pocket():
    """Shapely outline of the floor-underside pocket (physical frame):
    piezo disc + comparator slot + the steering-diode annulus + the potting
    groove out to the channel / wire fan-out pocket."""
    from shapely.geometry import LineString, Point, box
    ring = Point(0, 0).buffer(BATT_DIODE_RING_MM[1], 96).difference(
        Point(0, 0).buffer(BATT_DIODE_RING_MM[0], 96))
    cx, cy = _batt_channel_xy()
    a = math.atan2(cy, cx)
    r0 = BATT_DIODE_RING_MM[1] - 0.3
    groove = LineString([(r0 * math.cos(a), r0 * math.sin(a)), (cx, cy)]).buffer(
        BATT_POT_GROOVE_W_MM / 2.0, cap_style=2)
    return (Point(0, 0).buffer(BATT_PZ_DISC_POCKET_R_MM, 96).union(box(*BATT_PZ_SLOT_MM))
            .union(ring).union(groove))


def _battery_floor_plate(cq):
    """(2026-11-23) The separate 7075 floor plate (z 0 … BATT_FLOOR_MM): piezo /
    comparator / diode pocket + channel-exit pocket in its underside, − pin
    holes, + wire holes under the bore grooves, the potting channel, and
    clearance holes for the aft cap's M2 screws (they clamp it to the holder)."""
    import math
    from smash.export.aft_cap import CAP_SCREW_ANGLES_DEG, CAP_SCREW_R_MM, CAP_SCREW_CLEAR_D_MM
    f = BATT_FLOOR_MM
    plate = cq.Workplane("XY").circle(BATT_HOLDER_R_OUT_MM).extrude(f)
    plate = plate.cut(_poly_extrude(cq, piezo_pocket(), BATT_PZ_POCKET_DEPTH_MM))
    from shapely.geometry import box as _box
    plate = plate.cut(_poly_extrude(cq, _box(*BATT_PZ_COMP_POCKET_MM), BATT_PZ_COMP_POCKET_DEPTH_MM))
    plate = plate.cut(_poly_extrude(cq, wire_fan_pocket(), WIRE_FAN_POCKET_DEPTH_MM))
    for x, y in cell_centres_xy():                 # − pins
        plate = plate.cut(cq.Workplane("XY").center(x, y).circle(CELL_PIN_HOLE_D_MM / 2.0).extrude(f))
    for x, y in cell_wire_pads_xy():               # + wires out of the grooves
        plate = plate.cut(cq.Workplane("XY").center(x, y).circle(WIRE_HOLE_D_MM / 2.0).extrude(f))
    cx, cy = _batt_channel_xy()
    plate = plate.cut(cq.Workplane("XY").center(cx, cy).circle(BATT_CHANNEL_D_MM / 2.0).extrude(f))
    from smash.layout import cavities as _CAV            # (2026-11-23) fixture rim-pin notch
    plate = plate.cut(_align_slot(cq, 17.0 - _CAV.ALIGN_NOTCH_DEPTH_MM, f))
    for ang in CAP_SCREW_ANGLES_DEG:
        a = math.radians(ang)
        plate = plate.cut(cq.Workplane("XY").center(CAP_SCREW_R_MM * math.cos(a), CAP_SCREW_R_MM * math.sin(a))
                          .circle(CAP_SCREW_CLEAR_D_MM / 2.0).extrude(f))
    return plate


def _battery_holder_body(cq, h, with_plate: bool = True):
    """Cell-locating block (OPEN at the aft end since 2026-11-23) on top of the
    separate floor plate, + a 1 mm EDGE RING up to h. Potting: the axial
    channel + its link slot into the cell cavity. Per-cell + wire grooves in
    the bore walls. with_plate=True returns holder ∪ plate (stack views);
    False = the holder alone (machining STEP)."""
    import math
    f = BATT_FLOOR_MM
    hc = min(BATT_CELL_LENGTH_MM, h - f)
    block = cq.Workplane("XY").circle(BATT_HOLDER_R_OUT_MM).extrude(hc).translate((0, 0, f))
    block = block.cut(_poly_extrude(cq, battery_holder_cavity(), hc, z0=f))
    body = block
    cx, cy = _batt_channel_xy()
    body = body.cut(cq.Workplane("XY").center(cx, cy)
                    .circle(BATT_CHANNEL_D_MM / 2.0).extrude(hc).translate((0, 0, f)))
    # channel → cell-cavity link slot (full block height)
    la = math.radians(BATT_CHANNEL_LINK_CELL_DEG)
    bx, by = BATT_CLUSTER_R_MM * math.cos(la), BATT_CLUSTER_R_MM * math.sin(la)
    ln = math.hypot(bx - cx, by - cy)
    body = body.cut(cq.Workplane("XY").center((cx + bx) / 2, (cy + by) / 2)
                    .transformed(rotate=(0, 0, math.degrees(math.atan2(by - cy, bx - cx))))
                    .rect(ln, BATT_CHANNEL_LINK_W_MM).extrude(hc).translate((0, 0, f)))
    # (2026-11-23) + wire grooves, full bore height, one per cell
    for x, y in cell_wire_pads_xy():
        body = body.cut(cq.Workplane("XY").center(x, y).circle(WIRE_GROOVE_D_MM / 2.0)
                        .extrude(hc).translate((0, 0, f)))
    if h > f + hc + 1e-6:
        ring = (cq.Workplane("XY").circle(BATT_HOLDER_R_OUT_MM)
                .circle(BATT_TOP_RING_R_IN_MM).extrude(h - f - hc)
                .translate((0, 0, f + hc)))
        body = body.union(ring)
    # (2026-11-23) axial groove for the sleeve's alignment rib, full height
    from smash.layout import cavities as _CAV
    body = body.cut(_align_slot(cq, 17.0 - _CAV.ALIGN_NOTCH_DEPTH_MM - 0.1, h - f, z0=f))
    # TAPPED M2 holes for the aft_end_cap screws, from the holder's bottom face
    # (z = f, on top of the plate), in the solid webs BETWEEN the cells.
    from smash.export.aft_cap import (CAP_SCREW_ANGLES_DEG, CAP_SCREW_R_MM,
                                      HOLDER_TAP_DRILL_MM, HOLDER_TAP_DEPTH_MM)
    for ang in CAP_SCREW_ANGLES_DEG:
        a = math.radians(ang)
        body = body.cut(cq.Workplane("XY").center(CAP_SCREW_R_MM * math.cos(a),
                                                  CAP_SCREW_R_MM * math.sin(a))
                        .circle(HOLDER_TAP_DRILL_MM / 2.0).extrude(HOLDER_TAP_DEPTH_MM)
                        .translate((0, 0, f)))
    if with_plate:
        body = body.union(_battery_floor_plate(cq))
    return body

def _write_floor_plate(cq, out_dir, res) -> None:
    """(2026-11-23) <out_dir>/battery_floor_plate/{.step,.stl,_cam.md}."""
    d = pathlib.Path(out_dir) / "battery_floor_plate"
    d.mkdir(parents=True, exist_ok=True)
    plate = _battery_floor_plate(cq)
    step = d / "battery_floor_plate.step"
    cq.exporters.export(plate, str(step))
    cq.exporters.export(plate, str(d / "battery_floor_plate.stl"))
    (d / "battery_floor_plate_cam.md").write_text(
        "# battery_floor_plate — gap hardware (generated)\n\n"
        "Kind: battery_holder floor. Material: 7075-T6 aluminium, hard anodised.\n"
        f"Geometry: Ø{2*BATT_HOLDER_R_OUT_MM:.0f} × {BATT_FLOOR_MM:g} mm plate under the open holder; "
        f"underside pocket {BATT_PZ_POCKET_DEPTH_MM:g} mm (comparator sub-pocket {BATT_PZ_COMP_POCKET_DEPTH_MM:g} mm; piezo disc + comparator column + "
        f"steering-diode annulus + potting groove to the channel exit); Ø{CELL_PIN_HOLE_D_MM:g} − pin "
        f"holes on the cell axes; Ø{WIRE_HOLE_D_MM:g} + wire holes under the bore grooves; Ø"
        f"{BATT_CHANNEL_D_MM:g} potting channel; Ø2.2 clearance holes for the aft cap's M2 screws; "
        "1.2 × 1.0 mm rim notch at 285° (the sleeve's alignment rib, as on the boards).\n"
        "Assembly: cells (pre-wired) slide into the holder from the aft end → this plate → "
        "aft_end_board (solder − pins + + wires from below) → aft cap; the cap screws clamp "
        "cap / aft_end / plate into the holder's M2 taps.\n")
    res.append({"name": "battery_floor_plate", "kind": "battery_holder", "step": step,
                "height_mm": BATT_FLOOR_MM})


def gap_kind(name: str) -> str:
    if name.startswith("spacer_battery_"):
        return "battery_holder"
    # (2026-11-15) Every non-battery gap carries a ring (Al or GF30 PEEK, see
    # ring_spec). No PEEK standoffs.
    if name in NO_HARDWARE_GAPS:
        return "none"
    return "ring"


def _align_slot(cq, r_floor, h, z0=0.0):
    """(2026-11-23) Radial slot for the sleeve's alignment rib at
    cavities.ALIGN_NOTCH_ANGLE_DEG: ALIGN_RING_GAP_MM wide, from r_floor out
    through the OD, height h from z0."""
    import math
    from smash.layout import cavities as CAV
    a = CAV.ALIGN_NOTCH_ANGLE_DEG
    L = BATT_HOLDER_R_OUT_MM + 1.0 - r_floor
    rc = r_floor + L / 2.0
    return (cq.Workplane("XY").center(rc * math.cos(math.radians(a)), rc * math.sin(math.radians(a)))
            .transformed(rotate=(0, 0, a)).rect(L, CAV.ALIGN_RING_GAP_MM).extrude(h)
            .translate((0, 0, z0)))


def _ring_body(cq, r_in, r_out, h, open_sector=None):
    """C-ring: OPEN over `open_sector` (the antenna sector, 2026-11-17).
    (2026-11-20, user) NO potting notches any more — the potting runs up the
    main potting-hole axis through the boards, not along the board faces."""
    import math
    body = (cq.Workplane("XY").circle(r_out).circle(r_in).extrude(h))
    if open_sector:
        a0, a1 = open_sector
        R = r_out + 1.0
        pts = [(0.0, 0.0)] + [(R * math.cos(math.radians(a0 + (a1 - a0) * k / 16)),
                               R * math.sin(math.radians(a0 + (a1 - a0) * k / 16)))
                              for k in range(17)]
        body = body.cut(cq.Workplane("XY").polyline(pts).close().extrude(h))
    # (2026-11-23) gap for the sleeve's alignment rib (fixes the
    # ring's orientation too)
    body = body.cut(_align_slot(cq, r_in - 0.5, h))
    return body


ANCHOR_GAP = "spacer_companion_compute_radar_module"   # snap ring: built in sleeve_step (nose set)


def is_anchor_gap(name: str) -> bool:
    """compute ↔ any nose payload (radar / QPD / camera / USB nose): the Al
    anchor ring under the crown, in every config."""
    from smash.export import nose_interface as NI
    return NI.MODULAR and any(name == f"spacer_{NI.HOST}_{p}" for p in NI.PAYLOAD_BOARDS)


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
    if kind == "none":
        return None
    if kind == "ring":
        if is_anchor_gap(name):
            return None          # (2026-11-20) the SNAP RING is built with the nose set (sleeve_step)
        rs = ring_spec(name)
        return _ring_body(cq, rs.r_in, rs.r_out, h, ring_open_sector(name)), h, name, kind
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
        if kind == "none":
            continue
        if kind == "battery_holder":
            if name != (batt[0] if batt else None):
                continue
            h = sum(boards[n].thickness_mm for n in batt)
            body = _battery_holder_body(cq, h, with_plate=False)
            label, mat = "battery_holder", "7075-T6 aluminium, hard anodised (insulates the live cell cans)"
            _write_floor_plate(cq, out_dir, res)
            dims = (f"Ø{2*BATT_HOLDER_R_OUT_MM:.0f} × {h:.2f} mm block, 3 cell bores "
                    f"Ø{2*BATT_BORE_R_MM:.2f} (location fit on the cell flanks), tip "
                    f"reliefs ±{BATT_TIP_RELIEF_HALF_DEG:g}° to r {BATT_TIP_RELIEF_R_MM} → "
                    f"{BATT_HOLDER_R_OUT_MM - BATT_CLUSTER_R_MM - BATT_TIP_RELIEF_R_MM:.1f} mm "
                    "skin in hoop TENSION only; potting: axial Ø"
                    f"{BATT_CHANNEL_D_MM} channel at {BATT_CHANNEL_ANGLE_DEG:g}°, linked to the cell cavity by a "
                    f"{BATT_CHANNEL_LINK_W_MM:g} mm full-height slot (the compartment is potted round "
                    "the cells); above the "
                    f"{BATT_CELL_LENGTH_MM:g} mm cell block a 1 mm edge ring (r "
                    f"{BATT_TOP_RING_R_IN_MM:g}–{BATT_HOLDER_R_OUT_MM:g}) over the "
                    f"{BATT_HEADROOM_MM:g} mm headroom under activation_interface (its bottom "
                    "face carries no parts); open at the aft end (closed by the battery_floor_plate): the "
                    "pre-wired Tadiran /P cells slide in from below — − pins through the plate "
                    f"into aft_end PTHs, + pins trimmed with an AWG 30 wire soldered flat and laid in a "
                    f"Ø{WIRE_GROOVE_D_MM:g} groove in each bore wall (cell angle "
                    f"{WIRE_GROOVE_OFFSET_DEG:+g}°) → plate hole → aft_end PTH; M2 taps "
                    "from the holder's bottom face; 1.2 mm axial groove at 285° to r 15.9 "
                    "for the sleeve's alignment rib")
        elif kind == "ring" and is_anchor_gap(name):
            continue             # (2026-11-20) the SNAP RING is built with the nose set (sleeve_step)
        elif kind == "ring":
            h = b.thickness_mm
            osec = ring_open_sector(name)
            rs = ring_spec(name)
            body = _ring_body(cq, rs.r_in, rs.r_out, h, osec)
            label, mat = name, rs.material
            opening = (f", OPEN {osec[0]:g}–{osec[1]:g}° (slot antenna in this gap: no "
                       "metal behind it; potting fills the opening)" if osec else "")
            from smash.layout import cavities as _CAV
            dims = (f"{'C-' if osec else ''}ring ID Ø{2*rs.r_in:.1f} / OD Ø{2*rs.r_out:.1f}"
                    f" × {h:.2f} mm{opening}; {_CAV.ALIGN_RING_GAP_MM:g} mm radial GAP at "
                    f"{_CAV.ALIGN_NOTCH_ANGLE_DEG:g}° for the "
                    "sleeve's alignment rib (it also sets the ring's orientation); the ring spaces its two boards")
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
        if kind == "ring":
            slots = ("- Break all edges (GF30 is notch-sensitive).\n" if "GF30" in mat
                     else "- Break all edges; hard anodise after machining.\n")
        else:
            slots = ""
        (d / f"{label}_cam.md").write_text(
            f"# {label} — gap hardware (generated)\n\n"
            f"Kind: {kind}. Material: {mat}.\n"
            f"Geometry: {dims}.\n{slots}"
            "Frame: tower frame (aft_end_board top view, 0° = +X, CCW), +Z toward the nose.\n"
            "Potted in place inside the LDS sleeve.\n")
        res.append({"name": label, "kind": kind, "step": step, "height_mm": h})
    return res
