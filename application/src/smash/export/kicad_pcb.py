"""Write a `.kicad_pcb` file for one placed Board.

S-expression text output — no `pcbnew` dependency. KiCad v8+ parses
this without `(net N "...")` declarations: pad `(net "NAME")` refs
implicitly define the net list. Older KiCad versions may refuse — bump
this generator only when a real consumer needs it.

Scope (P2 / task #161):
  - Layers block + minimal setup
  - Footprints with pads (Reference + Value props, pad geom, net
    binding by string name)
  - Edge.Cuts board outline (circle / polygon)
  - NPTH potting holes as np_thru_hole pads (own footprint each)
  - Board-level plated vias (`board.vias`) — e.g. the interposer spacers'
    filled per-land through-vias (net bound by name); blind vias carry
    the KiCad `blind` token
  - Routed tracks (`board.tracks`) — one `(segment …)` per consecutive
    path point pair (net bound by name)

Out of scope (separate tasks):
  - Per-board stackup (constant default for now)
  - DRC rule sidecar (.kicad_dru)
  - Project sidecar (.kicad_pro)
  - 3D model path rewriting
  - Zones — smash doesn't model these (tracks + vias now are)
  - Panel-level concatenation of multiple boards

Coordinate convention: smash uses math-y-up; KiCad uses screen-y-down.
This emitter flips Y once at the boundary (positions, pad offsets,
edge geometry).
"""
from __future__ import annotations

import json
import math
import pathlib
import uuid as _uuid
from typing import Iterable

from smash.state.board import Board
from smash.state import Chip
from smash.state.antenna import Antenna
from smash.state.design import Design
from smash.state.geometry.cavity import CavityRegion
from smash.state.topology.placement import Placement
from smash.export._common import _strip_ball_prefix
from smash.roots import git_repo_root, resolve_repo_path


# UUID namespace for stable element IDs. Anything generated under this
# namespace from the same (board, ref, kind) tuple is reproducible
# across runs — important for git diffs of the generated .kicad_pcb.
_NS = _uuid.UUID("8c5b9c1e-1a82-4a4a-9c4b-1c1a40000001")


# A drawing sheet (page frame + title block) with no graphic items —
# KiCad draws nothing for it. `(setup …)` only sets margin/text defaults.
_BLANK_WKS = (
    '(kicad_wks (version 20220228) (generator "smash") '
    '(generator_version "10.0")\n'
    '\t(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)'
    '(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))\n'
    ')\n'
)


def write_blank_drawing_sheet(pcb_path) -> None:
    """Suppress the drawing sheet (frame + title block) for a generated
    `.kicad_pcb`. Writes a shared blank `empty.kicad_wks` in the board's
    directory and a sibling `<stem>.kicad_pro` whose pcbnew
    `page_layout_descr_file` points at it, so the board opens with no
    page frame. KiCad fills the rest of the project with defaults.

    The panel folds out well past any standard paper size; rather than
    grow the page, we drop the sheet entirely (per design request).
    """
    pcb = pathlib.Path(pcb_path)
    wks = pcb.parent / "empty.kicad_wks"
    if not wks.exists():
        wks.write_text(_BLANK_WKS)
    pro = pcb.with_suffix(".kicad_pro")
    # Default net class + DRC rules for the advanced-HDI buildup. KiCad keeps
    # net-class clearance in the PROJECT, not the .kicad_pcb — with this
    # absent KiCad falls back to its 0.2 mm default, so every pad shows a
    # 0.2 mm "keepout" clearance ring (way past a tight courtyard). 0.075 mm
    # is the board's actual clearance rule (the 75 um / NCAB-Advanced-HDI
    # class the DDR route is built to); track/via match the buildup so DRC
    # doesn't flag the 0.1 mm traces and 0.15 mm microvia drills.
    pro.write_text(json.dumps({
        "board": {"design_settings": {"rules": {
            "min_clearance": 0.075,
            "min_track_width": 0.1,
            "min_through_hole_diameter": 0.15,
            "min_via_diameter": 0.3,
            "min_microvia_diameter": 0.25,
            "min_microvia_drill": 0.15,
        }}},
        "meta": {"filename": pro.name, "version": 3},
        "net_settings": {
            "classes": [{
                "name": "Default",
                "clearance": 0.075,
                "track_width": 0.1,
                "via_diameter": 0.3,
                "via_drill": 0.15,
                "microvia_diameter": 0.25,
                "microvia_drill": 0.15,
                "diff_pair_gap": 0.15,
                "diff_pair_width": 0.1,
            }],
            "meta": {"version": 3},
        },
        "pcbnew": {"page_layout_descr_file": "empty.kicad_wks"},
    }, indent=2) + "\n")


def _uid(*parts: str) -> str:
    return str(_uuid.uuid5(_NS, "/".join(parts)))


def _fmt(v: float) -> str:
    """Format a float for kicad_pcb output: strip trailing zeros, keep
    bounded precision so floating-point noise doesn't poison the diff."""
    if v == int(v):
        return f"{int(v)}"
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _flip_y(p: tuple[float, float]) -> tuple[float, float]:
    """Math-y-up → KiCad y-down."""
    return (p[0], -p[1])


def _world(
    p: tuple[float, float],
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float]:
    """Translate a math-y-up board-local point into canvas-y-down world
    coords. `offset_xy` is already canvas-y-down (the tile centre on
    the panel, or (0, 0) for a single-board file)."""
    fx, fy = _flip_y(p)
    return (offset_xy[0] + fx, offset_xy[1] + fy)


# ── layers + setup ────────────────────────────────────────────────────

# Layer ID assignment matches what pcbnew emits for a 14L board:
# In1..In12 occupy the even-spaced slots between F.Cu (0) and B.Cu (2).
# Numbering lifted verbatim from a real KiCad 10 .kicad_pcb for byte-
# compat (so a regenerated panel diffs cleanly against pcbnew's output).
# Non-copper layers — fixed tail appended after the copper layers (which
# are derived per-board from the stackup). Ordinals lifted verbatim from a
# real KiCad 10 .kicad_pcb for byte-compat.
_NONCU_LAYERS_BLOCK = """\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)"""

# Copper layer roles that KiCad's (layers ...) block tags as "power"
# (planes); everything else is "signal".
_PLANE_ROLES = {"power", "ground", "embedded_cap_gnd", "embedded_cap_power"}


def _kicad_cu_ordinal(name: str) -> int:
    """KiCad layer ordinal for a copper layer: F.Cu=0, B.Cu=2,
    In_k.Cu=2k+2 (In1=4 … In12=26)."""
    if name == "F.Cu":
        return 0
    if name == "B.Cu":
        return 2
    return 2 * int(name[2:].split(".")[0]) + 2     # "In7.Cu" → 7 → 16


def _board_stackup(board) -> list:
    """The board's fitted stackup, or a default fit when it has none (so a
    bare Board still exports the full buildup). Spacers get a hand-built
    2-layer buildup instead of the 14L default fit."""
    if getattr(board, "is_spacer", False):
        return _spacer_stackup(board)
    if getattr(board, "stackup", None):
        return board.stackup
    from smash.state.stackup.fit import fit_stackup, StackupSpec
    return fit_stackup(StackupSpec.for_board(board))


def _spacer_stackup(board) -> list:
    """2-layer buildup for a spacer interposer: 1 oz LGA-land foil on each
    face around a single FR4 core milled to the spacer's own thickness.
    Stated directly rather than via the catalog fitter — the fitter's
    stocked laminates cap near 150 µm per gap, nowhere near a 2-5 mm
    spacer core."""
    from smash.state.stackup.layer import Layer
    from smash.state.stackup.dielectric import Dielectric
    foil_um = 35.0
    core = Dielectric(
        material="FR4", kind="core",
        thickness_um=board.thickness_mm * 1000.0 - 2 * foil_um,
        epsilon_r=4.5, loss_tangent=0.02)
    return [
        Layer(name="F.Cu", index=0, role="signal", thickness_um=foil_um,
              dielectric_below=core),
        Layer(name="B.Cu", index=1, role="signal", thickness_um=foil_um),
    ]


def _render_layers_block(board) -> str:
    """The `(layers ...)` block: copper layers derived from the stackup
    (ordinal + power/signal type) + the fixed non-copper tail."""
    lines = ["\t(layers"]
    for layer in _board_stackup(board):
        typ = "power" if layer.role in _PLANE_ROLES else "signal"
        lines.append(f'\t\t({_kicad_cu_ordinal(layer.name)} "{layer.name}" {typ})')
    lines.append(_NONCU_LAYERS_BLOCK)
    lines.append("\t)")
    return "\n".join(lines)

def _render_stackup_block(board) -> str:
    """The `(stackup ...)` block from the board's fitted buildup: the
    fixed silk/paste/mask wrapper + one copper layer (and its
    `dielectric_below`) per stackup entry + the ENIG finish."""
    lines = [
        "\t\t(stackup",
        '\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))',
        '\t\t\t(layer "F.Paste" (type "Top Solder Paste"))',
        '\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "Green") (thickness 0.01))',
    ]
    d = 0
    for layer in _board_stackup(board):
        lines.append(f'\t\t\t(layer "{layer.name}" (type "copper") '
                     f'(thickness {_fmt(layer.thickness_um / 1000.0)}))')
        di = getattr(layer, "dielectric_below", None)
        if di is None:
            continue
        d += 1
        parts = [f'\t\t\t(layer "dielectric {d}"',
                 f'(type "{di.kind or "core"}")',
                 f'(thickness {_fmt(di.thickness_um / 1000.0)})']
        if di.material:
            parts.append(f'(material "{di.material}")')
        if di.epsilon_r is not None:
            parts.append(f'(epsilon_r {_fmt(di.epsilon_r)})')
        if di.loss_tangent is not None:
            parts.append(f'(loss_tangent {_fmt(di.loss_tangent)})')
        lines.append(" ".join(parts) + ")")
    lines += [
        '\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "Green") (thickness 0.01))',
        '\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))',
        '\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))',
        '\t\t\t(copper_finish "ENIG")',
        "\t\t\t(dielectric_constraints no)",
        "\t\t)",
    ]
    return "\n".join(lines)


def _setup_block(board) -> str:
    """The `(setup ...)` block wrapping the board-derived stackup."""
    return ("\t(setup\n"
            f"{_render_stackup_block(board)}\n"
            "\t\t(pad_to_mask_clearance 0)\n"
            "\t\t(allow_soldermask_bridges_in_footprints no)\n"
            "\t)")


# ── lookup: chip pad → net name ───────────────────────────────────────

def _pin_to_net_name(chip: Chip, pad_num: str) -> str | None:
    """Find the net connected to the chip pin for footprint pad
    `pad_num`, if any. `Pin.net` is the net's string name (the data
    model carries the back-edge by name, not by object reference).
    Returns None for unconnected pads.

    Footprint pad numbers are raw ball coords ("A1"); some BGA factories
    namespace a ball coord that collides with a logical pin name by
    prefixing the chip pin with `BALL_` (e.g. DDR3 ball A1 collides with
    address-bit name A1 → pin num "BALL_A1"). Strip that prefix before
    matching so the raw pad still resolves its net — without this, every
    collided ball (6 on the DDR3: A1/A2/A3/A7/A8/A9) exports with no
    net, like the canonical-netlist path already strips it."""
    for pin in chip.pins:
        if _strip_ball_prefix(pin.num) != pad_num:
            continue
        return pin.net
    return None


# ── footprint emit ────────────────────────────────────────────────────

def _emit_fp_poly(
    points: list,
    *,
    layer: str,
    width_mm: float,
    uuid_seed: str,
) -> str:
    """One footprint-local polygon as an `(fp_poly ...)` block. Points
    are math-y-up board-local; flipped to KiCad y-down here."""
    pts = [_flip_y(p) for p in points]
    pts_str = " ".join(f"(xy {_fmt(x)} {_fmt(y)})" for x, y in pts)
    return (
        f'\t\t(fp_poly\n'
        f'\t\t\t(pts {pts_str})\n'
        f'\t\t\t(stroke (width {_fmt(width_mm)}) (type solid))\n'
        f'\t\t\t(fill no)\n'
        f'\t\t\t(layer "{layer}")\n'
        f'\t\t\t(uuid "{uuid_seed}")\n'
        f'\t\t)'
    )


def _emit_footprint(
    placement: Placement,
    *,
    board_name: str,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> str:
    """One `(footprint ...)` block from a chip Placement. `offset_xy`
    is the tile centre in canvas coords for panel exports; pass (0, 0)
    for single-board files."""
    chip: Chip = placement.item
    fp = chip.footprint
    if fp is None:
        # Chip without a footprint can't be emitted as a footprint
        # block. Skip silently — the orchestrator already records it
        # in PlacementStats.n_unplaced.
        return ""

    face = placement.face
    fp_layer = "F.Cu" if face == "top" else "B.Cu"
    silk_layer = "F.SilkS" if face == "top" else "B.SilkS"

    x, y = _world(placement.position_mm, offset_xy)
    rot = placement.rotation_deg

    # Bottom-face bake: the data model stores footprint geometry in F.*
    # orientation and `world_pad_position` mirrors X after rotation (a
    # part flipped onto the back face lands mirrored in top view). KiCad
    # renders a footprint's stored coordinates literally, so the same
    # transform must be baked into the emitted block — mirror every
    # footprint-local X and negate the orientation (mirror_x∘R(θ) =
    # R(−θ)∘mirror_x). Without this the exported B.Cu copper is the
    # mirror image of the model: unassemblable pinout for asymmetric
    # packages, and packer keepouts that don't match the plot.
    mirror = face == "bottom"
    if mirror:
        rot = (-rot) % 360.0

    def _mx(p: tuple[float, float]) -> tuple[float, float]:
        return (-p[0], p[1]) if mirror else p

    # Face-aware layer selection. Footprint geometry is stored in the
    # data model in F.* orientation; if the chip lands on the bottom
    # face, every F.* mention gets remapped to its B.* equivalent so
    # KiCad renders the part on the correct side.
    def _flip_layer(layer: str) -> str:
        if face != "bottom":
            return layer
        flip = {"F.Cu": "B.Cu", "B.Cu": "F.Cu",
                "F.Mask": "B.Mask", "B.Mask": "F.Mask",
                "F.Paste": "B.Paste", "B.Paste": "F.Paste",
                "F.SilkS": "B.SilkS", "B.SilkS": "F.SilkS",
                "F.Fab":  "B.Fab",  "B.Fab":  "F.Fab",
                "F.CrtYd": "B.CrtYd", "B.CrtYd": "F.CrtYd"}
        return flip.get(layer, layer)

    fab_layer   = _flip_layer("F.Fab")
    crtyd_layer = _flip_layer("F.CrtYd")

    parts: list[str] = []
    parts.append(f'\t(footprint "{fp.name}"')
    parts.append(f'\t\t(layer "{fp_layer}")')
    parts.append(f'\t\t(uuid "{_uid(board_name, chip.ref)}")')
    parts.append(f'\t\t(at {_fmt(x)} {_fmt(y)} {_fmt(rot)})')
    if chip.description:
        # Escape any quote characters; descr is a freeform string
        descr = chip.description.replace('"', r'\"')
        parts.append(f'\t\t(descr "{descr}")')

    # Reference property — kept (KiCad needs a refdes for netlist/DRC
    # association) but HIDDEN: this is a potted assembly, so there is no
    # printed silkscreen anywhere. `(hide yes)` keeps it off the silk
    # gerber. Value is likewise hidden.
    parts.append(
        f'\t\t(property "Reference" "{chip.ref}"\n'
        f'\t\t\t(at 0 0 0)\n'
        f'\t\t\t(layer "{silk_layer}")\n'
        f'\t\t\t(hide yes)\n'
        f'\t\t\t(uuid "{_uid(board_name, chip.ref, "prop_ref")}")\n'
        f'\t\t\t(effects (font (size 1 1) (thickness 0.15)))\n'
        f'\t\t)'
    )
    value = chip.manf_pn or chip.ref
    parts.append(
        f'\t\t(property "Value" "{value}"\n'
        f'\t\t\t(at 0 0 0)\n'
        f'\t\t\t(layer "{silk_layer}")\n'
        f'\t\t\t(hide yes)\n'
        f'\t\t\t(uuid "{_uid(board_name, chip.ref, "prop_value")}")\n'
        f'\t\t\t(effects (font (size 1 1) (thickness 0.15)))\n'
        f'\t\t)'
    )

    # Body outline + courtyard polygons. Body lives on F.Fab (yellow
    # in fab view); courtyard on F.CrtYd (red dashed in pcbnew default
    # view). The data model stores both as math-y-up; flip and emit
    # as a single fp_poly each.
    if fp.body_outline:
        parts.append(_emit_fp_poly(
            [_mx(p) for p in fp.body_outline], layer=fab_layer, width_mm=0.1,
            uuid_seed=_uid(board_name, chip.ref, "body_outline"),
        ))
    if fp.courtyard:
        parts.append(_emit_fp_poly(
            [_mx(p) for p in fp.courtyard], layer=crtyd_layer, width_mm=0.05,
            uuid_seed=_uid(board_name, chip.ref, "courtyard"),
        ))

    # Pads
    for pad in fp.pads:
        parts.append(_emit_pad(pad, chip, face=face, board_name=board_name,
                               mirror_x=mirror, orientation_deg=rot))

    # Non-pad copper polylines (e.g. NFC spiral coil). Emit one fp_line
    # per segment in the polyline — these are footprint-local, so KiCad
    # rotates/translates them with the rest of the footprint.
    for cl_idx, cl in enumerate(fp.copper_lines):
        pts = cl["points"]
        layer = cl["layer"]
        w = cl["width_mm"]
        # On the bottom face, F.Cu → B.Cu (the placer face is what
        # decides; copper_lines are written in F.Cu-orientation by the
        # factory and follow the footprint's face).
        if face == "bottom":
            if layer == "F.Cu":   layer = "B.Cu"
            elif layer == "B.Cu": layer = "F.Cu"
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            ax, ay = _flip_y(_mx(a)); bx, by = _flip_y(_mx(b))
            parts.append(
                f'\t\t(fp_line\n'
                f'\t\t\t(start {_fmt(ax)} {_fmt(ay)})\n'
                f'\t\t\t(end {_fmt(bx)} {_fmt(by)})\n'
                f'\t\t\t(stroke (width {_fmt(w)}) (type default))\n'
                f'\t\t\t(layer "{layer}")\n'
                f'\t\t\t(uuid "{_uid(board_name, chip.ref, "cu_line", str(cl_idx), str(i))}")\n'
                f'\t\t)'
            )

    # Embedded fonts trailer required by KiCad v8+
    parts.append("\t\t(embedded_fonts no)")

    # 3D model reference — KiCad wants an absolute filesystem path so
    # it can load the .stp file at render time. Explicit model paths
    # on the data model (e.g. SamacSys-sourced ICs) win; otherwise
    # try to auto-derive a KiCad-stock model path for footprints
    # whose library prefix is one of the well-known stock libs
    # (passives, test points). The result is `${KICAD10_3DMODEL_DIR}/
    # <lib>.3dshapes/<fp_name>.step`.
    model = fp.model_3d_path or _kicad_stock_model_path(fp.name)
    if model:
        parts.append(_emit_model(model))

    parts.append("\t)")
    return "\n".join(parts)


# Git root for library_kicad/. Smash part artifacts live under Export/
# and are resolved via resolve_repo_path (Export first, then git root).
_REPO_ROOT = git_repo_root()

# KiCad's stock 3D-model libraries map 1:1 with footprint libraries —
# Resistor_SMD footprint library → Resistor_SMD.3dshapes 3D library,
# etc. Anything in this set gets an automatic
# `${KICAD10_3DMODEL_DIR}/<lib>.3dshapes/<fp>.step` model path when
# the factory hasn't set one explicitly.
_KICAD_STOCK_3D_LIBS = frozenset({
    "Capacitor_SMD",
    "Capacitor_Tantalum_SMD",
    "Resistor_SMD",
    "Inductor_SMD",
    "LED_SMD",
    "TestPoint",
})


def _kicad_stock_model_path(fp_name: str) -> str | None:
    """If `fp_name` is a KiCad-stock footprint (e.g.
    "Capacitor_SMD:C_0402_1005Metric"), return the repo-local path to
    its matching .step file. Otherwise None.

    The .step files are copied from KiCad's stock 3dmodels directory
    into library_kicad/3dmodels/<lib>.3dshapes/ at the repo root so
    the PCB is self-contained — no dependency on KICAD10_3DMODEL_DIR
    pointing at the right place. Returns None if the .step file
    isn't in the repo yet (chip will render without a 3D body)."""
    if ":" not in fp_name:
        return None
    lib, base = fp_name.split(":", 1)
    if lib not in _KICAD_STOCK_3D_LIBS:
        return None
    candidate = _REPO_ROOT / "library_kicad" / "3dmodels" / f"{lib}.3dshapes" / f"{base}.step"
    if not candidate.exists():
        return None
    return str(candidate)


def _emit_model(model_path: str) -> str:
    """`(model ...)` block referencing a 3D .stp/.wrl file.

    Three input forms:
      - Absolute path: emitted as-is.
      - `${KICAD10_3DMODEL_DIR}/…` env-var path: emitted as-is (KiCad
        resolves the variable at render time).
      - Anything else: resolved against the repo root.

    For SamacSys-sourced models, the matching .kicad_mod typically
    declares a model rotation (often -90° on the X axis, since SamacSys
    STEPs are exported with Y as the "up" direction rather than Z).
    Look for a sibling .kicad_mod, parse its (model …) block, and
    use that offset+rotation; otherwise emit zeros.
    """
    if model_path.startswith("${") or pathlib.Path(model_path).is_absolute():
        out_path = model_path
        kicad_mod_search_dir = (pathlib.Path(model_path).parent
                                if not model_path.startswith("${") else None)
    else:
        resolved = resolve_repo_path(model_path)
        out_path = str(resolved)
        kicad_mod_search_dir = resolved.parent

    offset, rotate = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    if kicad_mod_search_dir and kicad_mod_search_dir.is_dir():
        for mod_file in kicad_mod_search_dir.glob("*.kicad_mod"):
            parsed = _parse_kicad_mod_model_xform(mod_file)
            if parsed is not None:
                offset, rotate = parsed
                break
    return (
        f'\t\t(model "{out_path}"\n'
        f'\t\t\t(offset (xyz {_fmt(offset[0])} {_fmt(offset[1])} {_fmt(offset[2])}))\n'
        f'\t\t\t(scale (xyz 1 1 1))\n'
        f'\t\t\t(rotate (xyz {_fmt(rotate[0])} {_fmt(rotate[1])} {_fmt(rotate[2])}))\n'
        f'\t\t)'
    )


import re as _re

# SamacSys/KiCad mod files declare:
#   (model NAME.stp
#     (at (xyz X Y Z))           ← model offset in mm
#     (scale (xyz 1 1 1))
#     (rotate (xyz RX RY RZ))    ← rotation in degrees
#   )
_MODEL_BLOCK_RX = _re.compile(
    r"\(model\s+\S+\s*"
    r"\(\s*at\s*\(\s*xyz\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\)\s*\)\s*"
    r"\(\s*scale\s*\(\s*xyz\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s*\)\s*\)\s*"
    r"\(\s*rotate\s*\(\s*xyz\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\)\s*\)\s*\)",
    _re.IGNORECASE,
)


def _parse_kicad_mod_model_xform(
    path: pathlib.Path,
) -> tuple | None:
    """Return ((ox, oy, oz), (rx, ry, rz)) parsed from the (model …)
    block in a .kicad_mod file. None if no block / parse failure."""
    try:
        text = path.read_text()
    except OSError:
        return None
    m = _MODEL_BLOCK_RX.search(text)
    if not m:
        return None
    nums = [float(g) for g in m.groups()]
    return (tuple(nums[:3]), tuple(nums[3:]))


def _emit_pad(pad, chip: Chip, *, face: str, board_name: str,
              mirror_x: bool = False, orientation_deg: float = 0.0) -> str:
    """One `(pad ...)` block. `mirror_x` bakes the bottom-face flip into
    the pad's footprint-local position (see `_emit_footprint`).

    `orientation_deg` is the footprint's emitted orientation. KiCad stores a
    pad's angle **absolutely** (footprint orientation + any pad-local
    rotation), not relative to its footprint: omitting it on a footprint
    placed at 90° leaves the pad *positions* rotated but the pad *shapes*
    axis-aligned, so a non-square pad plots across its terminal. The data
    model has no pad-local rotation — `Pad.size_mm` carries any 90° pad
    rotation as a W/H swap — so the absolute angle is just the footprint's.
    """
    # Pad layer set: top → F.Cu/F.Mask(+F.Paste if SMD), bottom → B.*
    pth = pad.drill_mm is not None
    if pth:
        # PTH spans all copper + mask layers
        layers = '"*.Cu" "*.Mask"'
    elif face == "top":
        # SMD on top face
        layers = '"F.Cu" "F.Mask"' + (' "F.Paste"' if pad.paste else "")
    else:
        layers = '"B.Cu" "B.Mask"' + (' "B.Paste"' if pad.paste else "")

    # Position is footprint-local (KiCad orientation applied later)
    lx, ly = pad.position_mm
    if mirror_x:
        lx = -lx
    px, py = _flip_y((lx, ly))
    w, h = pad.size_mm
    shape = pad.shape    # "round" / "rect" / "oval" / "roundrect"
    # KiCad shape names: round→circle, oval→oval, rect→rect, roundrect→roundrect
    shape_map = {"round": "circle"}
    kshape = shape_map.get(shape, shape)
    pad_type = "thru_hole" if pth else "smd"

    lines: list[str] = []
    lines.append(f'\t\t(pad "{pad.num}" {pad_type} {kshape}')
    ang = orientation_deg % 360.0
    lines.append(f'\t\t\t(at {_fmt(px)} {_fmt(py)}'
                 + (f' {_fmt(ang)})' if abs(ang) > 1e-9 else ')'))
    lines.append(f'\t\t\t(size {_fmt(w)} {_fmt(h)})')
    if pth:
        lines.append(f'\t\t\t(drill {_fmt(pad.drill_mm)})')
    lines.append(f'\t\t\t(layers {layers})')

    net_name = _pin_to_net_name(chip, pad.num)
    if net_name:
        lines.append(f'\t\t\t(net "{net_name}")')
    # Per-pad solder-mask expansion. The board-level `pad_to_mask_clearance`
    # is 0 (mask aperture == copper); a pad that needs an oversized aperture
    # carries its own margin, which overrides the board default in KiCad.
    if pad.solder_mask_expansion_mm is not None:
        lines.append('\t\t\t(solder_mask_margin '
                     f'{_fmt(pad.solder_mask_expansion_mm)})')
    lines.append(f'\t\t\t(uuid "{_uid(board_name, chip.ref, "pad", pad.num)}")')
    lines.append("\t\t)")
    return "\n".join(lines)


# ── outline ───────────────────────────────────────────────────────────

def _rect_outline_segments(
    rect_dimensions: tuple,
    cutouts: list,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[tuple]:
    """Rect-tile outline as a list of ((x1, y1), (x2, y2)) segments.

    Walks the 4 axis-aligned edges (E → S → W → N in canvas y-down).
    For each edge whose compass direction matches a cutout's
    angle_deg, the edge is broken into two partial segments flanking
    the cutout (leaving a clear gap of `cut.width_mm` for the flex
    strip endpoints to land on).
    """
    w, h = rect_dimensions
    hw, hh = w / 2, h / 2
    ox, oy = offset_xy

    # Corners in canvas y-down (TL, TR, BR, BL).
    TL = (ox - hw, oy - hh)
    TR = (ox + hw, oy - hh)
    BR = (ox + hw, oy + hh)
    BL = (ox - hw, oy + hh)

    # Match cutouts to edges by compass angle.
    # ANGLE_E=0, ANGLE_N=90, ANGLE_W=180, ANGLE_S=270 (math-y-up
    # convention used by _grid_dir_to_angle). The canvas-y-down rect
    # has its top edge at y=-hh+oy, so a cutout at "N" (math up)
    # carves into the TOP edge.
    cuts_by_dir = {"E": None, "N": None, "W": None, "S": None}
    for cut in cutouts:
        a = cut.angle_deg % 360
        if   abs(a -   0.0) < 1.0: cuts_by_dir["E"] = cut
        elif abs(a -  90.0) < 1.0: cuts_by_dir["N"] = cut
        elif abs(a - 180.0) < 1.0: cuts_by_dir["W"] = cut
        elif abs(a - 270.0) < 1.0: cuts_by_dir["S"] = cut

    def _edge_with_cut(a, b, cut, axis: str) -> list:
        """Split edge a→b around the cutout's midpoint. Preserves
        traversal direction: the first segment goes from `a` to the
        edge of the cutout on a's side, the second from the edge on
        b's side to `b`."""
        if cut is None:
            return [(a, b)]
        half = cut.width_mm / 2
        if axis == "x":
            mid_x = (a[0] + b[0]) / 2
            y = a[1]
            # Pick offset signs so the first chord sits on a's side.
            sign_a = -1 if a[0] < b[0] else +1
            return [(a, (mid_x + sign_a * half, y)),
                    ((mid_x - sign_a * half, y), b)]
        else:
            x = a[0]
            mid_y = (a[1] + b[1]) / 2
            sign_a = -1 if a[1] < b[1] else +1
            return [(a, (x, mid_y + sign_a * half)),
                    ((x, mid_y - sign_a * half), b)]

    segs: list = []
    # Top edge (y = -hh + oy) — runs TL → TR (west to east). N cutout
    # lives here.
    segs.extend(_edge_with_cut(TL, TR, cuts_by_dir["N"], axis="x"))
    # East edge: TR → BR (top to bottom). E cutout.
    segs.extend(_edge_with_cut(TR, BR, cuts_by_dir["E"], axis="y"))
    # Bottom edge: BR → BL (east to west). S cutout.
    segs.extend(_edge_with_cut(BR, BL, cuts_by_dir["S"], axis="x"))
    # West edge: BL → TL (bottom to top). W cutout.
    segs.extend(_edge_with_cut(BL, TL, cuts_by_dir["W"], axis="y"))
    return segs


def _emit_outline(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
    cutouts: list | None = None,
) -> list[str]:
    """Edge.Cuts geometry for the board outline.

    Circle without cutouts → `gr_circle`. Circle with cutouts →
    discretized `gr_line` segments via `tile_outline_segments`. Rect
    → 4 `gr_line` segments. DXF → NotImplementedError. `offset_xy`
    translates the result into panel canvas coords (panel exporter)
    or stays (0, 0) (single-board exporter).
    """
    g = board.geometry
    if g is None:
        return []
    out: list[str] = []
    ox, oy = offset_xy
    if g.shape == "circle":
        r = (g.diameter_mm or 0) / 2.0
        if cutouts:
            # Discretized outline with chord notches at flex attach
            # points. `tile_outline_segments` already returns canvas-
            # y-down segments centred at (ox, oy).
            from smash.layout.geometry import tile_outline_segments
            for i, seg in enumerate(tile_outline_segments(ox, oy, r, cutouts)):
                out.append(
                    f'\t(gr_line\n'
                    f'\t\t(start {_fmt(seg.x1)} {_fmt(seg.y1)})\n'
                    f'\t\t(end {_fmt(seg.x2)} {_fmt(seg.y2)})\n'
                    f'\t\t(stroke (width 0.15) (type default))\n'
                    f'\t\t(layer "Edge.Cuts")\n'
                    f'\t\t(uuid "{_uid(board.name, "outline_arc_seg", str(i))}")\n'
                    f'\t)'
                )
        else:
            out.append(
                f'\t(gr_circle\n'
                f'\t\t(center {_fmt(ox)} {_fmt(oy)})\n'
                f'\t\t(end {_fmt(ox + r)} {_fmt(oy)})\n'
                f'\t\t(stroke (width 0.15) (type default))\n'
                f'\t\t(fill no)\n'
                f'\t\t(layer "Edge.Cuts")\n'
                f'\t\t(uuid "{_uid(board.name, "outline_circle")}")\n'
                f'\t)'
            )
    elif g.shape == "rect":
        # Rect outline with optional flex cutouts. For each axis-
        # aligned edge that carries a cutout, emit the two partial
        # edge segments flanking the cutout; otherwise emit the
        # full edge. tile centre = offset_xy (canvas y-down).
        for seg in _rect_outline_segments(
            g.rect_dimensions, cutouts or [],
            offset_xy=offset_xy,
        ):
            out.append(
                f'\t(gr_line\n'
                f'\t\t(start {_fmt(seg[0][0])} {_fmt(seg[0][1])})\n'
                f'\t\t(end {_fmt(seg[1][0])} {_fmt(seg[1][1])})\n'
                f'\t\t(stroke (width 0.15) (type default))\n'
                f'\t\t(layer "Edge.Cuts")\n'
                f'\t\t(uuid "{_uid(board.name, "outline_seg", _fmt(seg[0][0]), _fmt(seg[0][1]))}")\n'
                f'\t)'
            )
    elif g.shape == "dxf":
        raise NotImplementedError(
            f"DXF outline export not implemented for board {board.name!r}"
        )
    return out


def _emit_holes(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """One NPTH footprint per drilled hole — an `np_thru_hole` pad, NOT
    an Edge.Cuts circle.

    A hole drawn as a closed Edge.Cuts circle is just one more loop in
    the board-outline soup. With the outer outline + chip through-cuts
    already on Edge.Cuts, the extra hole loops can stop KiCad from
    stitching a single contiguous outline; it then falls back to the
    bounding box (a filled square board) and the cavities render as solid
    instead of cut (see the standalone-tile note in `write_kicad_pcb`).
    An `np_thru_hole` pad is layer-independent: it always renders as a
    real drilled hole and lands in the drill file, no matter how the
    outline is interpreted. A plated hole (rare here) becomes a plain
    `thru_hole` pad; size == drill, so neither carries a copper annulus."""
    g = board.geometry
    if g is None:
        return []
    out: list[str] = []
    for i, hole in enumerate(g.holes):
        cx, cy = _world(hole.position_mm, offset_xy)
        d = hole.diameter_mm
        seed = (board.name, "hole", str(i), hole.tag or "")
        pad_type = "thru_hole" if hole.plated else "np_thru_hole"
        out.append(
            f'\t(footprint "smash_mech:{hole.tag or "hole"}"\n'
            f'\t\t(layer "F.Cu")\n'
            f'\t\t(uuid "{_uid(*seed, "fp")}")\n'
            f'\t\t(at {_fmt(cx)} {_fmt(cy)})\n'
            f'\t\t(attr exclude_from_pos_files exclude_from_bom '
            f'allow_missing_courtyard)\n'
            f'\t\t(property "Reference" ""\n'
            f'\t\t\t(at 0 0 0)\n'
            f'\t\t\t(layer "F.SilkS")\n'
            f'\t\t\t(hide yes)\n'
            f'\t\t\t(uuid "{_uid(*seed, "ref")}")\n'
            f'\t\t\t(effects (font (size 1 1) (thickness 0.15)))\n'
            f'\t\t)\n'
            f'\t\t(pad "" {pad_type} circle\n'
            f'\t\t\t(at 0 0)\n'
            f'\t\t\t(size {_fmt(d)} {_fmt(d)})\n'
            f'\t\t\t(drill {_fmt(d)})\n'
            f'\t\t\t(layers "*.Cu" "*.Mask")\n'
            f'\t\t\t(uuid "{_uid(*seed, "pad")}")\n'
            f'\t\t)\n'
            f'\t)'
        )
    return out


def _emit_vias(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """Board-level plated through-vias (`board.vias`). The interposer spacers
    carry a filled through-via per LGA land joining the top pad to the bottom
    pad on the same net — the conducting board-to-board path up the stack.
    Net is bound by name (same KiCad-v8+ implicit-netlist convention as pads).
    KiCad has no per-via 'filled' token; fill is a stackup/fab attribute, so a
    filled via emits like any through-via and the intent rides on `Via.filled`
    in the model + the fab notes.

    A via whose span is not the full F.Cu↔B.Cu emits the `blind` token
    (KiCad 10 grammar: `(via [blind|micro] (at …) …)`)."""
    out: list[str] = []
    for i, v in enumerate(getattr(board, "vias", []) or []):
        cx, cy = _world(v.position_mm, offset_xy)
        through = {v.from_layer, v.to_layer} == {"F.Cu", "B.Cu"}
        outer = {"F.Cu", "B.Cu"} & {v.from_layer, v.to_layer}
        kind = getattr(v, "kind", None)
        head = ('\t(via micro' if kind == "micro"
                else '\t(via' if through or kind == "through"
                else '\t(via buried' if kind == "buried" or not outer
                else '\t(via blind')
        block = [
            head,
            f'\t\t(at {_fmt(cx)} {_fmt(cy)})',
            f'\t\t(size {_fmt(v.pad_diameter_mm)})',
            f'\t\t(drill {_fmt(v.drill_mm)})',
            f'\t\t(layers "{v.from_layer}" "{v.to_layer}")',
        ]
        if head in ('\t(via blind', '\t(via buried'):
            # passed-through layers keep only the barrel — the EE
            # blind-via DDR field runs tracks 0.025 mm off the drill;
            # full annular rings there would short (matches the
            # connectivity tool's barrel model + the fab note)
            block.append('\t\t(remove_unused_layers yes)')
            block.append('\t\t(keep_end_layers yes)')
        if v.net:
            block.append(f'\t\t(net "{v.net}")')
        block.append(f'\t\t(uuid "{_uid(board.name, "via", str(i))}")')
        block.append('\t)')
        out.append("\n".join(block))
    return out


def _emit_zones(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """Copper pours (`board.zones`, smash.state.routing.Zone) as KiCad
    zone blocks — net-tied filled polygons, one layer each. Outline is
    board-local math-y-up; the exporter applies the same y-flip as
    every other emitter."""
    out: list[str] = []
    for i, z in enumerate(getattr(board, "zones", []) or []):
        pts = []
        for (x, y) in z.outline_mm:
            cx, cy = _world((x, y), offset_xy)
            pts.append(f'\t\t\t\t(xy {_fmt(cx)} {_fmt(cy)})')
        if len(pts) < 3:
            continue
        layer = z.layer if z.layer.endswith(".Cu") or "." in z.layer \
            else z.layer + ".Cu"
        out.append("\n".join([
            '\t(zone',
            f'\t\t(net "{z.net or ""}")',
            f'\t\t(layer "{layer}")',
            f'\t\t(uuid "{_uid(board.name, "zone", str(i))}")',
            '\t\t(hatch edge 0.5)',
            '\t\t(connect_pads thru_hole_only (clearance 0.2))'
            if not z.filled else
            '\t\t(connect_pads (clearance 0.2))',
            '\t\t(min_thickness 0.1)',
            '\t\t(filled_areas_thickness no)',
            '\t\t(fill yes\n\t\t\t(thermal_gap 0.3)\n'
            '\t\t\t(thermal_bridge_width 0.3)\n\t\t)',
            '\t\t(polygon\n\t\t\t(pts',
            "\n".join(pts),
            '\t\t\t)\n\t\t)',
        ] + _emit_zone_fills(z, offset_xy) + [
            '\t)',
        ]))
    return out


def _emit_zone_fills(z, offset_xy) -> list[str]:
    """The zone's COMPUTED pour, as KiCad `(filled_polygon …)` blocks.

    A `(polygon …)` outline is only the boundary: KiCad plots copper from
    the filled polygons it computes, and `kicad-cli` does NOT refill on
    export. So a zone emitted without this produces a completely EMPTY
    gerber layer — the plane is drawn in the board and absent from the fab
    data. Only populated for zones imported from a solved layout; zones we
    author ourselves have no fill until KiCad computes one."""
    out: list[str] = []
    for f in (getattr(z, "fill_polygons_mm", None) or []):
        pts = []
        for (x, y) in f["pts"]:
            cx, cy = _world((x, y), offset_xy)
            pts.append(f'\t\t\t\t(xy {_fmt(cx)} {_fmt(cy)})')
        if len(pts) < 3:
            continue
        out.append("\n".join([
            '\t\t(filled_polygon',
            f'\t\t\t(layer "{f.get("layer") or z.layer}")',
            '\t\t\t(pts',
            "\n".join(pts),
            '\t\t\t)',
            '\t\t)',
        ]))
    return out


def _emit_segments(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """Routed copper traces (`board.tracks`). A Track is a constant-width
    polyline on one Cu layer; KiCad has no polyline track item, so each
    consecutive path point pair emits one `(segment …)`. The router stores
    full KiCad layer names ("In3.Cu", …) so `t.layer` passes through
    verbatim. Net is bound by name (same KiCad-v8+ implicit-netlist
    convention as pads/vias)."""
    out: list[str] = []
    for i, t in enumerate(getattr(board, "tracks", []) or []):
        pts = [_world(p, offset_xy) for p in (t.path or [])]
        if len(pts) < 2:
            continue
        for j, (a, b) in enumerate(zip(pts, pts[1:])):
            if a == b:
                continue            # zero-length — invisible, skip
            block = [
                '\t(segment',
                f'\t\t(start {_fmt(a[0])} {_fmt(a[1])})',
                f'\t\t(end {_fmt(b[0])} {_fmt(b[1])})',
                f'\t\t(width {_fmt(t.width_mm)})',
                f'\t\t(layer "{t.layer}")',
            ]
            if t.net:
                block.append(f'\t\t(net "{t.net}")')
            block.append(
                f'\t\t(uuid "{_uid(board.name, "track", str(i), str(j))}")')
            block.append('\t)')
            out.append("\n".join(block))
    return out


def _emit_substrate_callout(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """Per-tile fab note on F.Fab when the board overrides the default
    substrate or carries an Al backing. The single global stackup in
    the .kicad_pcb can't encode per-region materials, so the fab reads
    these silkscreen labels at the affected tile."""
    out: list[str] = []
    lines: list[str] = []
    sub = (getattr(board, "top_substrate", "fr4") or "fr4").lower()
    if sub == "rogers_ro4350b_5mil":
        lines.append("L1: ROGERS RO4350B 5 mil")
    elif sub != "fr4":
        lines.append(f"L1: {sub.upper()}")

    al = getattr(board, "al_backing_mm", 0.0) or 0.0
    if al > 0:
        lines.append(f"BOTTOM: {al:.1f} mm AL BACKING")

    if not lines:
        return out

    cx, cy = offset_xy
    # Stack the labels vertically with 1.5 mm pitch, centred on tile.
    # gr_text requires `(at x y rot)` (three args) — KiCad 10 rejects
    # the two-arg form silently with "Failed to load board".
    for i, txt in enumerate(lines):
        y = cy + (i - (len(lines) - 1) / 2.0) * 1.5
        out.append(
            f'\t(gr_text "{txt}"\n'
            f'\t\t(at {_fmt(cx)} {_fmt(y)} 0)\n'
            f'\t\t(layer "F.Fab")\n'
            f'\t\t(effects (font (size 1 1) (thickness 0.15)))\n'
            f'\t\t(uuid "{_uid(board.name, "fab_note", str(i))}")\n'
            f'\t)'
        )
    return out


def _emit_cavities(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """Cavity polygons: Eco1.User (top pocket) / Eco2.User (bottom
    pocket) / Edge.Cuts (through-cut window where both faces meet and no
    FR4 floor remains — potted shut in the assembly)."""
    out: list[str] = []
    _layer_for = {"top": "Eco1.User", "bottom": "Eco2.User",
                  "through": "Edge.Cuts"}
    for j, pl in enumerate(board.cavity_placements):
        region = pl.item
        if not isinstance(region, CavityRegion):
            continue
        layer = _layer_for.get(region.face, "Eco2.User")
        pts = [_world(p, offset_xy) for p in region.exterior_polygon]
        for i, (a, b) in enumerate(zip(pts, pts[1:] + pts[:1])):
            out.append(
                f'\t(gr_line\n'
                f'\t\t(start {_fmt(a[0])} {_fmt(a[1])})\n'
                f'\t\t(end {_fmt(b[0])} {_fmt(b[1])})\n'
                f'\t\t(stroke (width 0.15) (type default))\n'
                f'\t\t(layer "{layer}")\n'
                f'\t\t(uuid "{_uid(board.name, "cavity", str(j), str(i))}")\n'
                f'\t)'
            )
    return out


# Silk-overlay caption font. The aft bench array packs 15 group captions
# into the gaps between 2.1 mm-pitch pad rows, so the caption size is set by
# how much vertical room the rows leave, not by taste.
#
# ⚠ 0.45 mm glyph / 0.075 mm stroke is BELOW the usual fab floor for
# silkscreen legibility (commonly ~0.6 mm height and ~0.10 mm line width;
# nothing is recorded in-repo for NCAB). Thin ink can blur or drop out at
# this size. Chosen deliberately for density — CONFIRM against the fab's
# silkscreen spec before release, and raise both numbers together if they
# push back (the stroke/height ratio here is 0.167, near KiCad's 0.15).
_SILK_LABEL_MM = 0.45
_SILK_LABEL_STROKE_MM = 0.075


def _emit_silk_overlays(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """Annotation outlines from `board.silk_overlays` — e.g. the facing
    spacer's through-cut window fold-mirrored into this board's frame
    (see `_mark_spacer_cavity_silk`). Drawn as a thin closed gr_line
    loop + a small label so face chips can be re-placed against the
    REAL cutout boundary without opening the spacer board."""
    out: list[str] = []
    for j, (layer, poly, label) in enumerate(
            getattr(board, "silk_overlays", []) or []):
        if not poly:
            continue
        pts = [_world(p, offset_xy) for p in poly]
        # Fewer than 3 points is a LABEL-ONLY overlay: caption, no outline.
        # Used for single-pad bench groups (FIRE, GROUND) where boxing one
        # pad adds nothing but the group still needs naming.
        for i, (a, b) in enumerate([] if len(pts) < 3 else
                                   list(zip(pts, pts[1:] + pts[:1]))):
            out.append(
                f'\t(gr_line\n'
                f'\t\t(start {_fmt(a[0])} {_fmt(a[1])})\n'
                f'\t\t(end {_fmt(b[0])} {_fmt(b[1])})\n'
                f'\t\t(stroke (width 0.12) (type dash))\n'
                f'\t\t(layer "{layer}")\n'
                f'\t\t(uuid "{_uid(board.name, "silkov", str(j), str(i))}")\n'
                f'\t)'
            )
        if label:
            lx = sum(p[0] for p in pts) / len(pts)
            ly = min(p[1] for p in pts) - (0.10 + _SILK_LABEL_MM / 2.0)
            mirror = '\n\t\t\t(justify mirror)' if layer.startswith("B.") \
                else ''
            out.append(
                f'\t(gr_text "{label}"\n'
                f'\t\t(at {_fmt(lx)} {_fmt(ly)} 0)\n'
                f'\t\t(layer "{layer}")\n'
                f'\t\t(uuid "{_uid(board.name, "silkov", str(j), "lbl")}")\n'
                f'\t\t(effects\n'
                f'\t\t\t(font (size {_SILK_LABEL_MM} {_SILK_LABEL_MM}) '
                f'(thickness {_SILK_LABEL_STROKE_MM}))'
                f'{mirror}\n'
                f'\t\t)\n'
                f'\t)'
            )
    return out


# ── Cu coin annotation (both silkscreens) ─────────────────────────────

_COIN_ARC_SEGMENTS = 8     # chords per 90° corner chamfer (~1 mm at R=5)


def _coin_outline_points(coin, *, ladder: bool = False) -> list:
    """Plan-view outline of the coin's flange (or ladder) in the board's
    math-y-up local frame. Geometry matches `layered_step._coin_2d_footprint`:
    rectangle centred at the origin with `length_mm` along +X, the flange's
    quarter-circle corner chamfers polygonized, then rotated by
    `rotation_deg` and translated to `position_mm`. The ladder is
    rectangular — never chamfered."""
    L = float(coin.ladder_length_mm if ladder else coin.length_mm)
    W = float(coin.ladder_width_mm if ladder else coin.width_mm)
    R = 0.0 if ladder else float(coin.corner_chamfer_radius_mm or 0.0)
    hx, hy = L / 2.0, W / 2.0
    if R > 0:
        # One quarter-circle per corner, CCW from the NE corner; the
        # straight flange edges fall out of joining consecutive arcs.
        pts = []
        corners = (((hx - R), (hy - R), 0.0),
                   (-(hx - R), (hy - R), 90.0),
                   (-(hx - R), -(hy - R), 180.0),
                   ((hx - R), -(hy - R), 270.0))
        for cx, cy, a0 in corners:
            for k in range(_COIN_ARC_SEGMENTS + 1):
                a = math.radians(a0 + 90.0 * k / _COIN_ARC_SEGMENTS)
                pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))
    else:
        pts = [(hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy)]
    rot = math.radians(coin.rotation_deg or 0.0)
    cr, sr = math.cos(rot), math.sin(rot)
    px, py = coin.position_mm
    return [(px + x * cr - y * sr, py + x * sr + y * cr) for (x, y) in pts]


def _coin_absorbed_copper(board, coin) -> list:
    """Names of the copper layers whose z-range overlaps the coin's —
    the layers the coin replaces inside its footprint (no copper exists
    there; routing must stay on the layers above/below the coin)."""
    names = []
    z = getattr(board, "thickness_mm", 0.0) or 0.0
    for layer in getattr(board, "stackup", None) or []:
        z_top = z
        z -= (getattr(layer, "thickness_um", 0) or 0) / 1000.0
        z_bottom = z
        di = getattr(layer, "dielectric_below", None)
        z -= (getattr(di, "thickness_um", 0) if di else 0) / 1000.0
        if z_bottom < coin.z_top_mm - 1e-6 and z_top > coin.z_bottom_mm + 1e-6:
            names.append(layer.name)
    return names


def _emit_coin_outlines(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """Cu-coin inserts (`board.cu_coin_inserts`) drawn on BOTH
    silkscreens: a dashed flange loop + a dashed ladder loop + a label
    naming the absorbed copper span. Pure annotation for the layout EE —
    inside the flange outline the absorbed inner layers don't exist, so
    tracks/zones there must keep to the layers above/below the coin."""
    out: list[str] = []
    for j, coin in enumerate(getattr(board, "cu_coin_inserts", None) or []):
        flange = [_world(p, offset_xy) for p in _coin_outline_points(coin)]
        loops = [("flange", flange)]
        # An I-coin (ladder == flange) would just re-draw the same loop.
        if coin.Q_long_mm > 1e-6 or coin.Q_short_mm > 1e-6:
            loops.append(("ladder", [
                _world(p, offset_xy)
                for p in _coin_outline_points(coin, ladder=True)]))
        absorbed = _coin_absorbed_copper(board, coin)
        label = (f"Cu coin {_fmt(coin.length_mm)}x{_fmt(coin.width_mm)}"
                 f"x{_fmt(coin.thickness_mm)}mm")
        if absorbed:
            first = absorbed[0].removesuffix(".Cu")
            last = absorbed[-1].removesuffix(".Cu")
            span = first if first == last else f"{first}..{last}"
            label += f" - absorbs {span} (keepout)"
        for layer in ("F.SilkS", "B.SilkS"):
            for tag, pts in loops:
                for i, (a, b) in enumerate(zip(pts, pts[1:] + pts[:1])):
                    out.append(
                        f'\t(gr_line\n'
                        f'\t\t(start {_fmt(a[0])} {_fmt(a[1])})\n'
                        f'\t\t(end {_fmt(b[0])} {_fmt(b[1])})\n'
                        f'\t\t(stroke (width 0.12) (type dash))\n'
                        f'\t\t(layer "{layer}")\n'
                        f'\t\t(uuid "{_uid(board.name, "coin", str(j), layer, tag, str(i))}")\n'
                        f'\t)'
                    )
            lx = _world(coin.position_mm, offset_xy)[0]
            ly = min(p[1] for p in flange) - 1.0
            mirror = '\n\t\t\t(justify mirror)' if layer.startswith("B.") \
                else ''
            out.append(
                f'\t(gr_text "{label}"\n'
                f'\t\t(at {_fmt(lx)} {_fmt(ly)} 0)\n'
                f'\t\t(layer "{layer}")\n'
                f'\t\t(uuid "{_uid(board.name, "coin", str(j), layer, "lbl")}")\n'
                f'\t\t(effects\n'
                f'\t\t\t(font (size 0.8 0.8) (thickness 0.12))'
                f'{mirror}\n'
                f'\t\t)\n'
                f'\t)'
            )
    return out


def _emit_eccobond(
    board: Board,
    *,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """Eccobond corner-stake marks on F.Adhes / B.Adhes — a short 45°
    stroke dispensed into each component corner for shock/vibration
    survival (Smash sees 1000+ G setback). Applied to every placed chip;
    BGAs get a longer stroke (corner staking is mandatory for them). The
    stroke scales down on tiny parts so it never overruns the body."""
    from smash.layout.placer.grid import placement_extents_mm
    out: list[str] = []
    for k, pl in enumerate(board.chip_placements):
        chip = pl.item
        fp = getattr(chip, "footprint", None)
        if fp is None:
            continue
        x1, y1, x2, y2 = placement_extents_mm(pl, fp)
        w, h = x2 - x1, y2 - y1
        if min(w, h) <= 0:
            continue
        ln = (1.5 if getattr(chip, "is_bga", False) else 1.0)
        ln = min(ln, 0.4 * min(w, h))           # stay inside small parts
        layer = "F.Adhes" if pl.face == "top" else "B.Adhes"
        # 45° stroke from each corner toward the body centre.
        corners = (((x1, y1), (1, 1)), ((x2, y1), (-1, 1)),
                   ((x2, y2), (-1, -1)), ((x1, y2), (1, -1)))
        for ci, ((cx, cy), (sx, sy)) in enumerate(corners):
            a = _world((cx, cy), offset_xy)
            b = _world((cx + sx * ln, cy + sy * ln), offset_xy)
            out.append(
                f'\t(gr_line\n'
                f'\t\t(start {_fmt(a[0])} {_fmt(a[1])})\n'
                f'\t\t(end {_fmt(b[0])} {_fmt(b[1])})\n'
                f'\t\t(stroke (width 0.2) (type default))\n'
                f'\t\t(layer "{layer}")\n'
                f'\t\t(uuid "{_uid(board.name, "eccobond", str(k), str(ci))}")\n'
                f'\t)'
            )
    return out


# ── top-level entry point ─────────────────────────────────────────────

def write_kicad_pcb(
    design: Design,
    board: Board,
    output_path: str | pathlib.Path,
    *,
    panel=None,
    flex_width_mm: float | None = None,
    link_widths_mm: dict | None = None,
    cutouts_override: list | None = None,
) -> dict:
    """Write a `.kicad_pcb` file for `board` with its placed chips.

    `design` is required so pad net references can be resolved (the
    Chip's pins carry net links; the Board's chip_placements just
    reference Chip objects). Returns a small summary dict.

    Pass `panel` to model this board's flex-launch cutouts (the chord
    where each adjacent flex leaves the tile edge). The cutout angles +
    widths depend on the board's neighbours in that panel/config — so a
    config build passes `cutouts_override` (the raw cutout list captured
    from the maximalist panel) instead, keeping the fabbed outline
    identical in every configuration (economies of scale). The override
    still gets the open→flat chord closure below.
    """
    out_path = pathlib.Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cutouts = None
    raw_cutouts = cutouts_override
    if raw_cutouts is None and panel is not None:
        if flex_width_mm is None:
            flex_width_mm = _DEFAULT_FLEX_WIDTH_MM
        if link_widths_mm is None:
            from smash.layout.placer.flex_sizing import compute_link_widths
            link_widths_mm, _ = compute_link_widths(design, panel)
        raw_cutouts = _cutouts_for_tile(board.name, panel, flex_width_mm,
                                        link_widths_mm)
    if raw_cutouts is not None:
        from smash.layout.geometry import make_cutout
        # A standalone tile has no flex strip to bridge the "open" flex
        # openings, so close each with a flat chord — otherwise the
        # outline isn't a closed loop and kicad-cli falls back to the
        # bounding box (a square board). The panel keeps them open.
        cutouts = [
            make_cutout(c.angle_deg, c.width_mm, c.depth_mm, kind="flat")
            if c.kind == "open" else c
            for c in raw_cutouts
        ]

    parts: list[str] = []
    parts.append('(kicad_pcb')
    # Match the version stamp emitted by KiCad 10.x on this machine
    # (see output/kicad_pcbs/smash_evb_v1/smash_evb_v1.kicad_pcb).
    # Older version strings trigger a "created with an older version
    # of KiCad" dialog on open.
    parts.append('\t(version 20260206)')
    parts.append('\t(generator "smash")')
    parts.append('\t(generator_version "10.0")')
    # Spacers stamp their true milled thickness (the .gbrjob + 3D read
    # it); rigid tiles keep the KiCad-default 1.6 — their real Z rides
    # in the per-layer stackup block.
    thick = (board.thickness_mm if getattr(board, "is_spacer", False)
             else 1.6)
    parts.append(f'\t(general (thickness {_fmt(thick)}) '
                 '(legacy_teardrops no))')
    parts.append('\t(paper "A4")')
    parts.append(_render_layers_block(board))
    parts.append(_setup_block(board))

    # Outline + holes + cavity polygons + substrate callout
    parts.extend(_emit_outline(board, cutouts=cutouts))
    parts.extend(_emit_holes(board))
    parts.extend(_emit_cavities(board))
    parts.extend(_emit_silk_overlays(board))
    parts.extend(_emit_coin_outlines(board))
    parts.extend(_emit_vias(board))
    parts.extend(_emit_zones(board))
    parts.extend(_emit_segments(board))
    parts.extend(_emit_eccobond(board))
    parts.extend(_emit_substrate_callout(board))

    # Footprints
    n_footprints = 0
    for pl in board.chip_placements:
        if not isinstance(pl.item, (Chip, Antenna)):
            continue
        block = _emit_footprint(pl, board_name=board.name)
        if block:
            parts.append(block)
            n_footprints += 1

    parts.append('\t(embedded_fonts no)')
    parts.append(')')

    out_path.write_text("\n".join(parts) + "\n")

    return {
        "output_path":  str(out_path),
        "n_footprints": n_footprints,
        "n_outline":    1 if board.geometry else 0,
        "n_holes":      len(board.geometry.holes) if board.geometry else 0,
        "n_cavities":   len(board.cavity_placements),
    }


# ── panel-level export ───────────────────────────────────────────────

# Compass angles used by the flex chord cutouts + flex strip geometry.
# Match the constants in tools/layout_gen/placer.py:1334-1337.
_ANGLE_E = 0.0
_ANGLE_N = 90.0
_ANGLE_W = 180.0
_ANGLE_S = 270.0

# Default panel grid (matches the old placer's defaults).
_DEFAULT_TILE_PITCH_MM     = 44.0
_DEFAULT_CANVAS_ORIGIN_MM  = (40.0, 40.0)
_DEFAULT_FLEX_WIDTH_MM     = 4.0


def _grid_dir_to_angle(dcol: int, drow: int) -> float | None:
    """(dcol, drow) → compass angle in canvas y-down. Returns None for
    non-axis-aligned steps (no flex possible)."""
    if (dcol, drow) == ( 1,  0): return _ANGLE_E
    if (dcol, drow) == (-1,  0): return _ANGLE_W
    if (dcol, drow) == ( 0,  1): return _ANGLE_S
    if (dcol, drow) == ( 0, -1): return _ANGLE_N
    return None


def _co_cell_offsets(panel, tile_pitch_mm):
    """Canvas offsets for tiles that share a grid cell (the fold solver
    may stack two same-axis deploy branches, e.g. camera + qpd). Each
    co-celled tile is nudged side-by-side, perpendicular to its flex
    axis, so the boards + their parallel flexes separate without
    crossing. Returns `{tile_name: (dx, dy)}` (canvas y-down)."""
    from collections import defaultdict
    cell_names: dict = defaultdict(list)
    for nm, cell in panel.tiles.items():
        cell_names[cell].append(nm)
    parent_of = {c: p for (p, c) in (panel.branches or [])}
    spread = tile_pitch_mm / 4.0
    offsets: dict = {}
    for cell, names in cell_names.items():
        if len(names) <= 1:
            continue
        names = sorted(names)
        for k, nm in enumerate(names):
            s = (k - (len(names) - 1) / 2.0) * 2.0 * spread
            p = parent_of.get(nm)
            vertical_flex = (p in panel.tiles
                             and panel.tiles[p][0] == cell[0])
            offsets[nm] = (s, 0.0) if vertical_flex else (0.0, s)
    return offsets


def _branch_leaf_offsets(panel, boards, canvas_origin_mm, tile_pitch_mm):
    """Push each branch leaf out from its parent so the rendered straight
    flex equals `branch_flex_lengths`. Deploy flexes (camera/qpd/nfc) are
    physical lengths that occupy their full extent in the flat panel, so
    the leaf must sit `parent_r + flex_len + leaf_r` from the parent
    centre along the (axis-aligned) branch direction — not on the
    packed adjacent cell. Returns `{leaf_name: (dx, dy)}` to ADD to the
    leaf's grid centre (and to its flex-strip endpoint)."""
    lengths = panel.branch_flex_lengths or {}
    s_fold = panel.branch_s_fold or set()
    offs: dict = {}
    for (parent, child) in (panel.branches or []):
        if parent not in panel.tiles or child not in panel.tiles:
            continue
        if parent not in boards or child not in boards:
            continue
        L = lengths.get((parent, child))
        if not L:
            continue
        pcol, prow = panel.tiles[parent]
        ccol, crow = panel.tiles[child]
        pc = _panel_centre(pcol, prow, canvas_origin_mm, tile_pitch_mm)
        gc = _panel_centre(ccol, crow, canvas_origin_mm, tile_pitch_mm)
        if (parent, child) in s_fold:
            # S-turn: leaf at the run end, mapped onto the parent's snake
            # axis (canonical frame → world via the run/offset basis).
            run_hat, offset_hat = _s_fold_axes(panel, parent, child)
            _x0, _y0, _x1, y2, leaf_cx = _s_fold_geometry(
                0.0, 0.0, _tile_radius(boards[parent]),
                boards[child], L, _DEFAULT_FLEX_WIDTH_MM, tile_pitch_mm, "N")
            a, b = leaf_cx, -y2
            lwx = pc[0] + a * run_hat[0] + b * offset_hat[0]
            lwy = pc[1] + a * run_hat[1] + b * offset_hat[1]
            offs[child] = (lwx - gc[0], lwy - gc[1])
            continue
        dcol, drow = ccol - pcol, crow - prow
        norm = math.hypot(dcol, drow)
        if norm == 0:
            continue
        ux, uy = dcol / norm, drow / norm
        dist = _tile_radius(boards[parent]) + L + _tile_radius(boards[child])
        cnew = (pc[0] + ux * dist, pc[1] + uy * dist)
        offs[child] = (cnew[0] - gc[0], cnew[1] - gc[1])
    return offs


def _panel_centre(
    col: int, row: int,
    canvas_origin_mm: tuple[float, float],
    tile_pitch_mm: float,
) -> tuple[float, float]:
    """Compute a tile's canvas-y-down centre. Origin sits one half-
    pitch in from canvas_origin_mm so the tile fits within the cell."""
    ox, oy = canvas_origin_mm
    half = tile_pitch_mm / 2.0
    return (ox + half + col * tile_pitch_mm,
            oy + half + row * tile_pitch_mm)


def _cutouts_for_tile(
    name: str,
    panel,
    flex_width_mm: float,
    link_widths_mm: dict | None = None,
) -> list:
    """Build chord cutouts at the flex-attach angles for this tile.

    If `link_widths_mm` is provided (per-snake-link widths from
    `compute_link_widths`), each chord uses its own flex's width;
    otherwise everything falls back to `flex_width_mm`."""
    from smash.layout.geometry import make_cutout

    tiles = panel.tiles
    if name not in tiles:
        return []
    col, row = tiles[name]
    cuts: list = []

    # If this tile is an S-fold parent, its run-side snake link and the
    # branch share ONE merged opening (a "split in the road"). Resolve the
    # neighbour to skip and the merged cutout up front.
    s_fold = panel.branch_s_fold or set()
    sfold_skip_nbr = None
    sfold_combined = None     # (world centre angle, width)
    for (parent, child) in (panel.branches or []):
        if (parent, child) in s_fold and name == parent and child in tiles:
            run_hat, offset_hat = _s_fold_axes(panel, parent, child)
            snk = _s_fold_run_neighbor(panel, parent, run_hat)
            sfold_skip_nbr = snk
            snake_w = flex_width_mm
            if link_widths_mm and snk in (panel.snake_chain or []):
                link_k = min(chain_idx for chain_idx in
                             (panel.snake_chain.index(parent),
                              panel.snake_chain.index(snk)))
                snake_w = link_widths_mm.get(link_k, flex_width_mm)
            th_c, w_comb = _combined_cutout(
                _S_FOLD_TILE_R_MM, snake_w, flex_width_mm)
            sfold_combined = (
                _map_s_fold_angle(th_c, run_hat, offset_hat), w_comb)
            break

    # Snake-chain neighbours (consecutive entries). Skipped when the panel
    # has no snake flex — there's no strip leaving the edge, so the tile stays
    # a full Ø34 circle at every snake interface (cutting a chord with nothing
    # attached leaves a malformed, non-circular outline). Branch cutouts below
    # are still emitted.
    chain = (panel.snake_chain or []) if getattr(panel, "snake_flex", True) else []
    if name in chain:
        idx = chain.index(name)
        for nbr_idx, link_k in [(idx - 1, idx - 1), (idx + 1, idx)]:
            if 0 <= nbr_idx < len(chain):
                nbr = chain[nbr_idx]
                if nbr not in tiles:
                    continue
                if nbr == sfold_skip_nbr:
                    continue   # merged into the S-fold fork opening below
                nc, nr = tiles[nbr]
                angle = _grid_dir_to_angle(nc - col, nr - row)
                if angle is None:
                    continue
                # Per-link width if we have it, else the fallback
                w = (link_widths_mm.get(link_k, flex_width_mm)
                     if link_widths_mm else flex_width_mm)
                cuts.append(make_cutout(angle, w))

    # Branch neighbours (extra flex tails outside the snake) — these
    # don't carry the snake bus, so use the fallback width
    for (parent, child) in (panel.branches or []):
        if (parent, child) in s_fold:
            # S-turn cutouts: parent exits through ONE merged opening
            # (snake link + branch) that forks in the gap; leaf opening
            # faces back along the run.
            run_hat, offset_hat = _s_fold_axes(panel, parent, child)
            if name == parent:
                angle_w = sfold_combined[1] if sfold_combined else flex_width_mm
                angle_c = (sfold_combined[0] if sfold_combined else
                           _map_s_fold_angle(
                               _s_fold_parent_angle(
                                   _S_FOLD_TILE_R_MM, flex_width_mm),
                               run_hat, offset_hat))
                cuts.append(make_cutout(angle_c, angle_w))
            elif name == child:
                cuts.append(make_cutout(
                    _map_s_fold_angle(_ANGLE_W, run_hat, offset_hat),
                    flex_width_mm))
            continue
        if name == parent and child in tiles:
            nc, nr = tiles[child]
        elif name == child and parent in tiles:
            nc, nr = tiles[parent]
        else:
            continue
        angle = _grid_dir_to_angle(nc - col, nr - row)
        if angle is not None:
            cuts.append(make_cutout(angle, flex_width_mm))

    # Static flat for the edge-mount USB-C: a 17 mm NORTH chord so the connector
    # seats against a straight edge (mouth out) instead of fighting the curved
    # Ø34 rim — the pads sit on-board just inboard of the flat (y≈14.72). The
    # chord also carries the connector mouth notch (see below).
    # The USB-C lowered to the radar; BOTH tiles keep the 17 mm N chord, and the
    # chord now CARRIES the connector mouth notch (flat -> notch -> flat, ONE
    # continuous outline) rather than a separate overlapping through-cut cavity —
    # the overlap was confusing the outline boolean and leaving stray FR4
    # rectangles. The notch is CENTRED, depth 6.3 mm (floor y~8.42, clearing the
    # radar Cu coin at y~8.0); the WIDTH is per-tile (see below).
    if name in ("nose_cap", "radar_module"):
        # WIDTH is per-tile: the connector MOUNTS on the radar. Its notch is
        # 10.2 mm (+/-5.1) -> wide enough to clear the ~8.3 mm mouth while the flat
        # segments beside it (~3.4 mm each) still carry the solder lands (pads at
        # x +/-5.745, just outside the wall). The NOSE_CAP keeps the WIDE 12.5 mm
        # notch to clear the connector body poking up from the radar.
        _nw = 10.2 if name == "radar_module" else 12.5
        cuts.append(make_cutout(_ANGLE_N, 17.0, kind="flat",
                                notch_width_mm=_nw, notch_depth_mm=6.3,
                                notch_offset_mm=0.0))

    return cuts


def _chord_corners_for_board(
    cx: float, cy: float, angle: float, width_mm: float, board: Board,
) -> tuple:
    """Dispatch to rect_chord_corners for rect tiles, chord_corners
    for circles. Rect tiles need their chord corners on the actual
    edge (not on a virtual circle of radius min(w,h)/2) — otherwise
    the flex strip endpoints land INSIDE the rect and the outline
    polygon doesn't close.
    """
    from smash.layout.geometry import chord_corners, rect_chord_corners
    g = board.geometry if board else None
    if g and g.shape == "rect" and g.rect_dimensions:
        w, h = g.rect_dimensions
        return rect_chord_corners(cx, cy, w, h, angle, width_mm)
    r = _tile_radius(board) if board else 17.0
    return chord_corners(cx, cy, angle, width_mm, r)


def _emit_flex_strip(
    a_cx: float, a_cy: float, a_angle: float, a_board: Board,
    b_cx: float, b_cy: float, b_angle: float, b_board: Board,
    *,
    width_mm: float,
    name: str,
) -> list[str]:
    """Two gr_line segments forming a non-crossing rectangle between
    two tile chord midpoints. Uses A.ccw ↔ B.cw / A.cw ↔ B.ccw pairing
    so the resulting rectangle is non-crossing and CCW-wound for
    polygon traversal. Also emits a filled Dwgs.User polygon covering
    the flex area so the strip is unmistakably visible during layout
    review (it's otherwise just two lonely Edge.Cuts segments)."""
    from smash.layout.geometry import Line
    a_ccw, a_cw = _chord_corners_for_board(a_cx, a_cy, a_angle, width_mm, a_board)
    b_ccw, b_cw = _chord_corners_for_board(b_cx, b_cy, b_angle, width_mm, b_board)
    segments = [
        Line(a_ccw[0], a_ccw[1], b_cw[0],  b_cw[1]),
        Line(a_cw[0],  a_cw[1],  b_ccw[0], b_ccw[1]),
    ]

    out: list[str] = []
    for i, seg in enumerate(segments):
        out.append(
            f'\t(gr_line\n'
            f'\t\t(start {_fmt(seg.x1)} {_fmt(seg.y1)})\n'
            f'\t\t(end {_fmt(seg.x2)} {_fmt(seg.y2)})\n'
            f'\t\t(stroke (width 0.15) (type default))\n'
            f'\t\t(layer "Edge.Cuts")\n'
            f'\t\t(uuid "{_uid(name, "flex_edge", str(i))}")\n'
            f'\t)'
        )

    # Filled Dwgs.User polygon covering the flex area. Traversal:
    # a_ccw → b_cw (long side 1) → b_ccw (chord at B) → a_cw (long
    # side 2) → a_ccw (chord at A). Closes as one quadrilateral.
    out.extend(_emit_flex_area_marker(
        [a_ccw, b_cw, b_ccw, a_cw],
        name=name, tag="area",
        label=_short_flex_label(name),
        label_xy=((a_cx + b_cx) / 2.0, (a_cy + b_cy) / 2.0),
    ))
    return out


# ── flex-area marker (user layer) ─────────────────────────────────────

_FLEX_AREA_LAYER = "Dwgs.User"
_FLEX_AREA_TEXT_SIZE_MM = 1.2
_FLEX_AREA_TEXT_THICKNESS_MM = 0.2


def _short_flex_label(name: str) -> str:
    """Compact human label for a flex marker.

    Strips the `flex_` / `flex_branch_` prefix and the `__` separator —
    "flex_branch_wakeup_board__yagi_ant_a_flex" becomes
    "wakeup_board → yagi_ant_a_flex". Long board names stay readable;
    this is the only place a flex is named in the layout view."""
    s = name
    for pre in ("flex_branch_", "flex_"):
        if s.startswith(pre):
            s = s[len(pre):]
            break
    return s.replace("__", " → ")


def _emit_flex_area_marker(
    points: list,
    *,
    name: str,
    tag: str = "area",
    layer: str = _FLEX_AREA_LAYER,
    label: str | None = None,
    label_xy: tuple[float, float] | None = None,
) -> list[str]:
    """Emit a filled gr_poly (and optional gr_text label) on `layer`
    covering a flex strip's area. `points` is the closed polygon, in
    panel canvas coordinates, traversed in order. Pure annotation —
    Dwgs.User is not fabricated, but renders prominently in the layout
    viewer so flex strips read at a glance instead of hiding inside the
    Edge.Cuts polyline soup."""
    pts_str = " ".join(f"(xy {_fmt(x)} {_fmt(y)})" for (x, y) in points)
    out = [
        f'\t(gr_poly\n'
        f'\t\t(pts {pts_str})\n'
        f'\t\t(stroke (width 0.1) (type solid))\n'
        f'\t\t(fill solid)\n'
        f'\t\t(layer "{layer}")\n'
        f'\t\t(uuid "{_uid(name, tag, "poly")}")\n'
        f'\t)'
    ]
    if label and label_xy is not None:
        lx, ly = label_xy
        out.append(
            f'\t(gr_text "{label}"\n'
            f'\t\t(at {_fmt(lx)} {_fmt(ly)} 0)\n'
            f'\t\t(layer "{layer}")\n'
            f'\t\t(uuid "{_uid(name, tag, "label")}")\n'
            f'\t\t(effects\n'
            f'\t\t\t(font (size {_FLEX_AREA_TEXT_SIZE_MM} '
            f'{_FLEX_AREA_TEXT_SIZE_MM}) '
            f'(thickness {_FLEX_AREA_TEXT_THICKNESS_MM}))\n'
            f'\t\t)\n'
            f'\t)'
        )
    return out


_SNAKE_FLEX_W_MM = 4.0      # nominal snake-flex width for the edge offset
_S_FOLD_TILE_R_MM = 17.0    # Ø34 snake tiles the East run passes over
_S_FOLD_SNAKE_CLEAR_MM = 0.6  # board sliver between snake flex + branch exit
_S_FOLD_FORK_DEPTH_MM = 4.0   # shared bridge length before the snake/branch fork


def _s_fold_run_neighbor(panel, parent, run_hat):
    """The snake-chain neighbour of `parent` lying in the `run_hat`
    direction — the snake link the branch forks off of. Returns its tile
    name (a spacer) or None."""
    chain = panel.snake_chain or []
    t = panel.tiles or {}
    if parent not in chain or parent not in t:
        return None
    i = chain.index(parent)
    pc = t[parent]
    best, best_dot = None, -9.0
    for j in (i - 1, i + 1):
        if 0 <= j < len(chain) and chain[j] in t:
            nc = t[chain[j]]
            dx, dy = float(nc[0] - pc[0]), float(nc[1] - pc[1])
            n = math.hypot(dx, dy) or 1.0
            dot = (dx / n) * run_hat[0] + (dy / n) * run_hat[1]
            if dot > best_dot:
                best_dot, best = dot, chain[j]
    return best


def _combined_cutout(parent_r, snake_w, branch_w):
    """Canonical centre angle (deg, in the run/offset frame) and width of
    the single merged opening that carries the snake link AND the branch
    out of the parent as one bridge. The snake link sits at canonical
    East (angle 0); the branch abuts it on the toward-leaf side with no
    sliver, so the union spans [-ha_s, +ha_s + 2*ha_b]."""
    ha_s = math.degrees(math.asin((snake_w / 2.0) / parent_r))
    ha_b = math.degrees(math.asin((branch_w / 2.0) / parent_r))
    th_c = ha_b
    w_comb = 2.0 * parent_r * math.sin(math.radians(ha_s + ha_b))
    return th_c, w_comb


def _branch_side(panel, parent, child):
    """"N" or "S" — which side of the snake row the branch leaf sits on,
    read from the grid (leaf row vs parent row). Defaults "N"."""
    t = panel.tiles or {}
    if parent in t and child in t:
        return "S" if t[child][1] > t[parent][1] else "N"
    return "N"


def _s_fold_parent_angle(parent_r, branch_w):
    """Centre angle (deg, north-of-East) of the parent's branch cutout,
    placed so the branch opening sits just North of the snake flex's
    North edge (a thin board sliver between them)."""
    ha = math.degrees(math.asin((branch_w / 2.0) / parent_r))
    south_off = _SNAKE_FLEX_W_MM / 2.0 + _S_FOLD_SNAKE_CLEAR_MM
    south_ang = math.degrees(math.asin(min(0.99, south_off / parent_r)))
    return south_ang + ha


def _leaf_half_extents(board):
    """(half-width, half-height) of a leaf tile. Circle → (r, r);
    rect → (w/2, h/2)."""
    g = getattr(board, "geometry", None)
    if g is not None and g.shape == "rect" and g.rect_dimensions:
        w, h = g.rect_dimensions
        return w / 2.0, h / 2.0
    r = _tile_radius(board)
    return r, r


def _s_fold_geometry(px, py, parent_r, leaf_board, flex_len, width, pitch,
                     side="N"):
    """S-turn deploy-flex geometry (canvas y-down). `side` is "N" (run
    above the snake row, N=-y) or "S" (below).

    The branch peels off the snake flex's near edge right at the board
    edge, rises/drops, then runs East to a leaf whose centre is aligned
    to a flex-region centre line (a gap between snake cells).

    Lift sizing: a small ROUND leaf nestles into the gap (only its disc
    must clear the two flanking tile centres → short lift); a tall RECT
    leaf (NFC) is moved fully clear of the snake row.

    Returns `(x0, y0, x1, y2, leaf_cx)`; y0/y2 carry the sign of `side`."""
    sgn = -1.0 if side == "N" else 1.0
    h = width / 2.0
    leaf_hw, leaf_vh = _leaf_half_extents(leaf_board)
    is_rect = (getattr(leaf_board, "geometry", None) is not None
               and leaf_board.geometry.shape == "rect")
    y0 = py + sgn * (_SNAKE_FLEX_W_MM / 2.0 + h)   # split at snake flex edge
    x0 = px + parent_r
    x1 = x0 + h + 1.0                              # riser hugs the board edge
    min_cx = px + parent_r + flex_len + leaf_hw
    k = max(0, math.ceil((min_cx - (px + pitch / 2.0)) / pitch))
    leaf_cx = px + pitch / 2.0 + k * pitch
    run_clear = _S_FOLD_TILE_R_MM + h + 1.0
    if is_rect:
        leaf_clear = _S_FOLD_TILE_R_MM + leaf_vh + 2.0
    else:
        d = (leaf_vh + _S_FOLD_TILE_R_MM) ** 2 - (pitch / 2.0) ** 2
        leaf_clear = (math.sqrt(d) + 2.0) if d > 0 else 0.0
    y2 = py + sgn * max(run_clear, leaf_clear)
    return x0, y0, x1, y2, leaf_cx


def _emit_open_polyline(points, name, tag):
    """Open Edge.Cuts polyline through `points` (list of (x, y)). Drops
    zero-length segments (coincident consecutive points) — KiCad flags
    those as a malformed outline."""
    pruned = [points[0]]
    for p in points[1:]:
        if abs(p[0] - pruned[-1][0]) > 1e-6 or abs(p[1] - pruned[-1][1]) > 1e-6:
            pruned.append(p)
    points = pruned
    out = []
    for i in range(len(points) - 1):
        sx, sy = points[i]
        ex, ey = points[i + 1]
        out.append(
            f'\t(gr_line\n'
            f'\t\t(start {_fmt(sx)} {_fmt(sy)})\n'
            f'\t\t(end {_fmt(ex)} {_fmt(ey)})\n'
            f'\t\t(stroke (width 0.15) (type default))\n'
            f'\t\t(layer "Edge.Cuts")\n'
            f'\t\t(uuid "{_uid(name, tag, str(i))}")\n'
            f'\t)')
    return out


def _s_fold_axes(panel, parent: str, child: str):
    """`(run_hat, offset_hat)` world unit vectors (canvas y-down): run =
    the parent's snake axis, oriented to point AWAY from the fold centroid
    (the leaf deploys outward, so neighbouring branches on the same lane
    diverge instead of overlapping); offset = toward the leaf's grid cell
    (the perpendicular side it was wired onto)."""
    t = panel.tiles or {}
    pc, cc = t[parent], t[child]
    ox, oy = float(cc[0] - pc[0]), float(cc[1] - pc[1])
    on = math.hypot(ox, oy) or 1.0
    offset_hat = (ox / on, oy / on)
    run_hat = (1.0, 0.0)
    chain = panel.snake_chain or []
    if parent in chain:
        i = chain.index(parent)
        nbr = (chain[i + 1] if i + 1 < len(chain)
               else (chain[i - 1] if i > 0 else None))
        if nbr in t:
            rx, ry = float(t[nbr][0] - pc[0]), float(t[nbr][1] - pc[1])
            rn = math.hypot(rx, ry) or 1.0
            run_hat = (rx / rn, ry / rn)
    # Orient the run outward (away from the snake centroid) so two branches
    # sharing a lane run in opposite directions and don't collide.
    cells = list(t.values())
    gx = sum(c[0] for c in cells) / len(cells)
    gy = sum(c[1] for c in cells) / len(cells)
    if run_hat[0] * (gx - pc[0]) + run_hat[1] * (gy - pc[1]) > 0:
        run_hat = (-run_hat[0], -run_hat[1])
    return run_hat, offset_hat


def _map_s_fold_angle(theta_deg, run_hat, offset_hat):
    """Map a canonical cutout angle (run=+x/East, offset=North; the
    chord_corners y-down convention) onto the world snake axis."""
    th = math.radians(theta_deg)
    a, b = math.cos(th), math.sin(th)
    dx = a * run_hat[0] + b * offset_hat[0]
    dy = a * run_hat[1] + b * offset_hat[1]
    return math.degrees(math.atan2(-dy, dx))


def _emit_s_fold_flex(center, run_hat, offset_hat, parent_r, leaf_board, *,
                      flex_len, width, pitch, name):
    """Render an S-turn deploy flex as TWO open rails closing against the
    parent's branch cutout and the leaf's West cutout (one continuous
    contour, like the snake strips). Built in a canonical frame (run =
    +x/East, offset toward leaf = North) and mapped onto the parent's
    actual snake axis via the `(run_hat, offset_hat)` basis, so it works
    for any fold orientation. Rail endpoints anchor to the tiles' world
    cutout corners (correct even for a rotated leaf)."""
    from smash.layout.geometry import chord_corners
    cx, cy = center

    def M(pt):                          # canonical (origin) → world
        a, b = pt[0], -pt[1]
        return (cx + a * run_hat[0] + b * offset_hat[0],
                cy + a * run_hat[1] + b * offset_hat[1])

    _x0, _y0, _x1, y2, leaf_cx = _s_fold_geometry(
        0.0, 0.0, parent_r, leaf_board, flex_len, width, pitch, "N")
    h = width / 2.0
    pa = _s_fold_parent_angle(parent_r, width)        # canonical N-of-E
    p_a, p_b = chord_corners(0.0, 0.0, pa, width, parent_r)
    l_a, l_b = _chord_corners_for_board(leaf_cx, y2, _ANGLE_W,
                                        width, leaf_board)
    p_far, p_near = sorted((p_a, p_b), key=lambda p: -abs(p[1]))
    l_far, l_near = sorted((l_a, l_b), key=lambda p: -abs(p[1]))
    leaf_c = M((leaf_cx, y2))
    Pw = chord_corners(cx, cy, _map_s_fold_angle(pa, run_hat, offset_hat),
                       width, parent_r)
    Lw = _chord_corners_for_board(
        leaf_c[0], leaf_c[1], _map_s_fold_angle(_ANGLE_W, run_hat, offset_hat),
        width, leaf_board)

    def _far_near(corners, ctr):
        s = sorted(corners, key=lambda p: -((p[0] - ctr[0]) * offset_hat[0]
                                            + (p[1] - ctr[1]) * offset_hat[1]))
        return s[0], s[1]

    P_far, P_near = _far_near(Pw, (cx, cy))
    L_far, L_near = _far_near(Lw, leaf_c)
    xc = parent_r + 3.0
    y_far, y_near = y2 - h, y2 + h            # canonical side "N" (sgn = -1)
    out = []
    out += _emit_open_polyline(
        [P_far, M((xc - h, p_far[1])), M((xc - h, y_far)),
         M((l_far[0], y_far)), L_far], name, "rO")
    out += _emit_open_polyline(
        [P_near, M((xc + h, p_near[1])), M((xc + h, y_near)),
         M((l_near[0], y_near)), L_near], name, "rI")
    # Filled marker on Dwgs.User. Traversal: outer rail forward (P_far
    # → L_far), close across the leaf chord (L_far → L_near), inner
    # rail backward (L_near → P_near), close across the parent chord
    # (P_near → P_far).
    out += _emit_flex_area_marker(
        [P_far, M((xc - h, p_far[1])), M((xc - h, y_far)),
         M((l_far[0], y_far)), L_far,
         L_near, M((l_near[0], y_near)), M((xc + h, y_near)),
         M((xc + h, p_near[1])), P_near],
        name=name, tag="area",
        label=_short_flex_label(name),
        label_xy=(0.5 * (cx + leaf_c[0]), 0.5 * (cy + leaf_c[1])),
    )
    return out


def _emit_s_fold_fork(center, run_hat, offset_hat, parent_r, leaf_board, *,
                      flex_len, width, pitch, name,
                      snk_center, snk_board, snk_angle, snake_w,
                      fork_depth=_S_FOLD_FORK_DEPTH_MM):
    """Render the S-fold branch-off as a "split in the road": the snake
    link and the branch leave the parent through ONE merged opening of
    width `snake_w + width`, run together as a short shared bridge, then
    FORK at a single crotch vertex — snake rails continue to the spacer
    (`snk`), branch rails peel off to the leaf. No flex overlaps flex.

    Outline (one closed contour): parent arc -> A (snake-outer corner of
    the merged opening) -> snk -> snk arc -> crotch F -> leaf -> leaf arc
    -> B (branch-outer corner) -> parent arc. F is shared by the snake
    inner rail and the branch inner rail."""
    from smash.layout.geometry import chord_corners
    cx, cy = center

    def M(pt):                          # canonical (origin) -> world
        a, b = pt[0], -pt[1]
        return (cx + a * run_hat[0] + b * offset_hat[0],
                cy + a * run_hat[1] + b * offset_hat[1])

    def _far_near(corners, ctr):        # far = toward leaf (+offset_hat)
        s = sorted(corners, key=lambda p: -((p[0] - ctr[0]) * offset_hat[0]
                                            + (p[1] - ctr[1]) * offset_hat[1]))
        return s[0], s[1]

    _x0, _y0, _x1, y2, leaf_cx = _s_fold_geometry(
        0.0, 0.0, parent_r, leaf_board, flex_len, width, pitch, "N")
    h = width / 2.0

    # Merged parent opening (snake link + branch) — corners in canonical
    # space (for bend heights) and world (for anchors).
    th_c, w_comb = _combined_cutout(parent_r, snake_w, width)
    ang_c_w = _map_s_fold_angle(th_c, run_hat, offset_hat)
    ca, cb = chord_corners(0.0, 0.0, th_c, w_comb, parent_r)
    B_canon, A_canon = sorted((ca, cb), key=lambda p: p[1])  # -y = toward leaf
    Cw = chord_corners(cx, cy, ang_c_w, w_comb, parent_r)
    B_world, A_world = _far_near(Cw, (cx, cy))   # B = branch-outer (leaf-side)

    # Crotch F: `fork_depth` out along the run, offset to the snake's
    # INNER edge (snake_w/2 toward the branch) — NOT the merged-opening
    # centre. This keeps the continuing snake flex a clean snake_w-wide
    # rectangle that meets the receiver (spacer) opening square, so the
    # snake inner rail runs parallel to the run axis instead of skewing
    # diagonally into the narrower receiver. (run_hat ⟂ offset_hat, so
    # offset_hat is the perpendicular toward the branch.)
    F_canon = (parent_r + fork_depth, -snake_w / 2.0)
    F_world = M(F_canon)

    # Leaf-side corners (unchanged from the plain S-fold).
    l_a, l_b = _chord_corners_for_board(leaf_cx, y2, _ANGLE_W,
                                        width, leaf_board)
    l_far, l_near = sorted((l_a, l_b), key=lambda p: -abs(p[1]))
    leaf_c = M((leaf_cx, y2))
    Lw = _chord_corners_for_board(
        leaf_c[0], leaf_c[1], _map_s_fold_angle(_ANGLE_W, run_hat, offset_hat),
        width, leaf_board)
    L_far, L_near = _far_near(Lw, leaf_c)

    xc = parent_r + 3.0
    y_far, y_near = y2 - h, y2 + h            # canonical side "N" (sgn = -1)

    out = []
    # Branch outer rail (toward leaf), anchored at the merged opening's
    # branch-outer corner B.
    out += _emit_open_polyline(
        [B_world, M((xc - h, B_canon[1])), M((xc - h, y_far)),
         M((l_far[0], y_far)), L_far], name, "brO")
    # Branch inner rail (snake side), anchored at the crotch F.
    out += _emit_open_polyline(
        [F_world, M((xc + h, F_canon[1])), M((xc + h, y_near)),
         M((l_near[0], y_near)), L_near], name, "brI")

    # Snake rails sharing the bridge: outer A -> snk (away-leaf), inner
    # F -> snk (toward-leaf). Together with the branch rails these meet
    # at the single crotch F.
    snk_corners = _chord_corners_for_board(
        snk_center[0], snk_center[1], snk_angle, snake_w, snk_board)
    snk_far, snk_near = _far_near(snk_corners, snk_center)
    out += _emit_open_polyline([A_world, snk_near], name, "snO")
    out += _emit_open_polyline([F_world, snk_far], name, "snI")

    # Filled markers on Dwgs.User — one for the branch limb, one for
    # the snake limb that shares the merged opening on the parent.
    #
    # Branch limb: B_world (branch-outer at parent) → outer rail → L_far
    # → close across leaf chord → L_near → inner rail backward → F_world
    # → close back through the crotch / merged opening (F → B is a
    # single segment across the fork bridge, which is part of the same
    # rigid-flex transition).
    out += _emit_flex_area_marker(
        [B_world, M((xc - h, B_canon[1])), M((xc - h, y_far)),
         M((l_far[0], y_far)), L_far,
         L_near, M((l_near[0], y_near)), M((xc + h, y_near)),
         M((xc + h, F_canon[1])), F_world],
        name=name, tag="branch_area",
        label=_short_flex_label(name),
        label_xy=(0.5 * (cx + leaf_c[0]), 0.5 * (cy + leaf_c[1])),
    )
    # Snake limb: simple quadrilateral A → snk_near → snk_far → F.
    out += _emit_flex_area_marker(
        [A_world, snk_near, snk_far, F_world],
        name=name, tag="snake_area",
        # No label on the snake limb — the branch label already names
        # the parent ↔ child pair, and the snake link is already named
        # implicitly by the spacer between its two endpoints.
    )
    return out


def _tile_radius(board: Board) -> float:
    """Effective radius for chord-corner geometry — circle uses its
    own radius; rect uses half its smaller side so the flex meets the
    short edge."""
    g = board.geometry
    if g is None:
        return 17.0   # fallback Ø34 / 2
    if g.shape == "circle" and g.diameter_mm:
        return g.diameter_mm / 2.0
    if g.shape == "rect" and g.rect_dimensions:
        w, h = g.rect_dimensions
        return min(w, h) / 2.0
    return 17.0


def write_kicad_panel(
    design: Design,
    panel,
    boards: dict,
    output_path: str | pathlib.Path,
    *,
    tile_pitch_mm: float = _DEFAULT_TILE_PITCH_MM,
    canvas_origin_mm: tuple[float, float] = _DEFAULT_CANVAS_ORIGIN_MM,
    flex_width_mm: float = _DEFAULT_FLEX_WIDTH_MM,
    link_widths_mm: dict | None = None,
) -> dict:
    """Emit ONE `.kicad_pcb` containing every board positioned on the
    panel grid plus flex strips between adjacent snake/branch tiles.

    `flex_width_mm` is the fallback width for any flex without an
    explicit entry in `link_widths_mm` (branches don't carry the snake
    bus, so they always fall through to this value).

    `link_widths_mm` is `{snake_link_index: width_mm}` from
    `smash.layout.placer.flex_sizing.compute_link_widths`. If None,
    the function computes it from `design` + `panel` automatically.
    Pass an empty dict to force every link to the fallback width.

    The single-board exporter (`write_kicad_pcb`) is still available
    for board-at-a-time iteration.
    """
    # Auto-size flex strips from the netlist unless the caller
    # explicitly opts out.
    if link_widths_mm is None:
        from smash.layout.placer.flex_sizing import compute_link_widths
        link_widths_mm, _ = compute_link_widths(design, panel)
    out_path = pathlib.Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    parts: list[str] = []
    parts.append('(kicad_pcb')
    parts.append('\t(version 20260206)')
    parts.append('\t(generator "smash")')
    parts.append('\t(generator_version "10.0")')
    parts.append('\t(general (thickness 1.6) (legacy_teardrops no))')
    parts.append('\t(paper "A4")')
    # Panel shares one fab stackup; emit the default fitted buildup.
    parts.append(_render_layers_block(None))
    parts.append(_setup_block(None))

    # 1. Per-board geometry (outline + holes + cavities + footprints)
    n_footprints = 0
    n_holes = 0
    n_cavities = 0
    co_offsets = _co_cell_offsets(panel, tile_pitch_mm)
    branch_offsets = _branch_leaf_offsets(
        panel, boards, canvas_origin_mm, tile_pitch_mm)
    for name, (col, row) in panel.tiles.items():
        board = boards.get(name)
        if board is None:
            continue
        centre = _panel_centre(col, row, canvas_origin_mm, tile_pitch_mm)
        ox, oy = co_offsets.get(name, (0.0, 0.0))
        bx, by = branch_offsets.get(name, (0.0, 0.0))
        centre = (centre[0] + ox + bx, centre[1] + oy + by)
        cuts = _cutouts_for_tile(name, panel, flex_width_mm,
                                 link_widths_mm=link_widths_mm)

        parts.extend(_emit_outline(board, offset_xy=centre, cutouts=cuts))
        parts.extend(_emit_holes(board, offset_xy=centre))
        parts.extend(_emit_cavities(board, offset_xy=centre))
        parts.extend(_emit_silk_overlays(board, offset_xy=centre))
        parts.extend(_emit_coin_outlines(board, offset_xy=centre))
        parts.extend(_emit_vias(board, offset_xy=centre))
        parts.extend(_emit_zones(board, offset_xy=centre))
        parts.extend(_emit_segments(board, offset_xy=centre))
        parts.extend(_emit_eccobond(board, offset_xy=centre))
        parts.extend(_emit_substrate_callout(board, offset_xy=centre))

        for pl in board.chip_placements:
            if not isinstance(pl.item, (Chip, Antenna)):
                continue
            block = _emit_footprint(pl, board_name=name, offset_xy=centre)
            if block:
                parts.append(block)
                n_footprints += 1

        if board.geometry:
            n_holes    += len(board.geometry.holes)
        n_cavities += len(board.cavity_placements)

    # 2. Flex strips: every snake-consecutive pair + every branch
    n_flex = 0
    n_flex += _emit_flex_strips_for_panel(
        panel, boards, parts,
        canvas_origin_mm=canvas_origin_mm,
        tile_pitch_mm=tile_pitch_mm,
        flex_width_mm=flex_width_mm,
        link_widths_mm=link_widths_mm,
        branch_offsets=branch_offsets,
    )

    parts.append('\t(embedded_fonts no)')
    parts.append(')')
    out_path.write_text("\n".join(parts) + "\n")

    return {
        "output_path":  str(out_path),
        "n_tiles":      len(panel.tiles),
        "n_footprints": n_footprints,
        "n_holes":      n_holes,
        "n_cavities":   n_cavities,
        "n_flex_strips": n_flex,
    }


def _emit_flex_strips_for_panel(
    panel, boards: dict, out_parts: list,
    *,
    canvas_origin_mm: tuple[float, float],
    tile_pitch_mm: float,
    flex_width_mm: float,
    link_widths_mm: dict | None = None,
    branch_offsets: dict | None = None,
) -> int:
    """Append flex-strip gr_lines to `out_parts`. Returns the count.

    Snake links use `link_widths_mm[k]` when available (per-link sizing
    from compute_link_widths). Branches always use `flex_width_mm`."""
    n = 0

    def _centre_board(name: str):
        if name not in panel.tiles or name not in boards:
            return None
        col, row = panel.tiles[name]
        cx, cy = _panel_centre(col, row, canvas_origin_mm, tile_pitch_mm)
        return cx, cy, boards[name]

    # S-fold parents merge their run-side snake link with the branch into
    # one forking bridge — that snake link is drawn by the fork emitter,
    # so suppress its plain strip here.
    s_fold = panel.branch_s_fold or set()
    fork_links = {}      # frozenset({parent, snk}) -> (parent, child)
    for (parent, child) in (panel.branches or []):
        if (parent, child) in s_fold and parent in panel.tiles:
            run_hat, _oh = _s_fold_axes(panel, parent, child)
            snk = _s_fold_run_neighbor(panel, parent, run_hat)
            if snk is not None:
                fork_links[frozenset((parent, snk))] = (parent, child)

    # Snake chain pairs — skipped entirely when the panel has no snake flex
    # (the snake tiles are joined by the board-to-board LGA lands through the
    # spacers instead, so no flex strip bridges them). Branch flexes below
    # are always drawn.
    chain = (panel.snake_chain or []) if getattr(panel, "snake_flex", True) else []
    for k in range(len(chain) - 1):
        a, b = chain[k], chain[k + 1]
        if frozenset((a, b)) in fork_links:
            continue   # drawn as part of the S-fold fork
        a_info = _centre_board(a)
        b_info = _centre_board(b)
        if a_info is None or b_info is None:
            continue
        a_cx, a_cy, a_brd = a_info
        b_cx, b_cy, b_brd = b_info
        a_col, a_row = panel.tiles[a]
        b_col, b_row = panel.tiles[b]
        a_angle = _grid_dir_to_angle(b_col - a_col, b_row - a_row)
        b_angle = _grid_dir_to_angle(a_col - b_col, a_row - b_row)
        if a_angle is None or b_angle is None:
            continue
        width = (link_widths_mm.get(k, flex_width_mm)
                 if link_widths_mm else flex_width_mm)
        out_parts.extend(_emit_flex_strip(
            a_cx, a_cy, a_angle, a_brd,
            b_cx, b_cy, b_angle, b_brd,
            width_mm=width,
            name=f"flex_{a}__{b}",
        ))
        n += 1

    # Branches
    for (parent, child) in (panel.branches or []):
        p_info = _centre_board(parent)
        c_info = _centre_board(child)
        if p_info is None or c_info is None:
            continue
        p_cx, p_cy, p_brd = p_info
        c_cx, c_cy, c_brd = c_info
        if (parent, child) in (panel.branch_s_fold or set()):
            # S-turn deploy flex forking off the parent's run-side snake
            # link, oriented to the parent's snake axis (folded or
            # straight). The snake link is drawn here too (suppressed in
            # the chain loop above).
            L = (panel.branch_flex_lengths or {}).get((parent, child), 70.0)
            run_hat, offset_hat = _s_fold_axes(panel, parent, child)
            snk = _s_fold_run_neighbor(panel, parent, run_hat)
            snk_info = _centre_board(snk) if snk else None
            if snk_info is not None:
                snk_cx, snk_cy, snk_brd = snk_info
                p_col, p_row = panel.tiles[parent]
                s_col, s_row = panel.tiles[snk]
                snk_angle = _grid_dir_to_angle(p_col - s_col, p_row - s_row)
                snake_w = flex_width_mm
                if link_widths_mm and snk in chain:
                    link_k = min(chain.index(parent), chain.index(snk))
                    snake_w = link_widths_mm.get(link_k, flex_width_mm)
                out_parts.extend(_emit_s_fold_fork(
                    (p_cx, p_cy), run_hat, offset_hat,
                    _tile_radius(p_brd), c_brd,
                    flex_len=L, width=flex_width_mm, pitch=tile_pitch_mm,
                    name=f"flex_branch_{parent}__{child}",
                    snk_center=(snk_cx, snk_cy), snk_board=snk_brd,
                    snk_angle=snk_angle, snake_w=snake_w))
            else:
                out_parts.extend(_emit_s_fold_flex(
                    (p_cx, p_cy), run_hat, offset_hat,
                    _tile_radius(p_brd), c_brd,
                    flex_len=L, width=flex_width_mm, pitch=tile_pitch_mm,
                    name=f"flex_branch_{parent}__{child}"))
            n += 1
            continue
        # Push the leaf endpoint out to its flex-length distance so the
        # rendered strip equals branch_flex_lengths (matches the leaf
        # geometry, which is offset by the same amount in the tile loop).
        bx, by = (branch_offsets or {}).get(child, (0.0, 0.0))
        c_cx += bx
        c_cy += by
        p_col, p_row = panel.tiles[parent]
        c_col, c_row = panel.tiles[child]
        p_angle = _grid_dir_to_angle(c_col - p_col, c_row - p_row)
        c_angle = _grid_dir_to_angle(p_col - c_col, p_row - c_row)
        if p_angle is None or c_angle is None:
            continue
        out_parts.extend(_emit_flex_strip(
            p_cx, p_cy, p_angle, p_brd,
            c_cx, c_cy, c_angle, c_brd,
            width_mm=flex_width_mm,
            name=f"flex_branch_{parent}__{child}",
        ))
        n += 1

    return n
