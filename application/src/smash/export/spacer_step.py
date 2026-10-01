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
