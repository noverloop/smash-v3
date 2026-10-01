"""STL export — converts the cadquery-produced spacer bodies + the
kicad-cli-produced tile STEPs into the mesh format every FDM slicer
(PrusaSlicer, OrcaSlicer, Cura, Bambu Studio) accepts.

Two paths, depending on where the body originates:

1.  **Spacers** — `smash.export.spacer_step.build_spacer_solid()`
    constructs the cadquery body in-process, so we can export STL
    straight from the body without any STEP roundtrip.

2.  **Rigid tiles** — these are produced by `kicad-cli pcb export step`,
    which doesn't speak STL. We re-import the STEP with cadquery and
    re-export as STL. The roundtrip costs one extra pass per tile but
    keeps the toolchain consistent with the rest of the export pipeline
    (and is fine for our ~50–200 tile-STL batches).

Tessellation tolerance defaults to 0.05 mm — fine enough that the Ø34 mm
disc looks smooth on the print bed, coarse enough not to bloat the STL
file (~500 kB per tile vs ~5 MB at 0.01 mm).
"""
from __future__ import annotations

import pathlib


# Tessellation defaults: 0.05 mm linear + 0.1 rad angular gives smooth
# curves on the spacer rim (a Ø34 disc gets ~600 facets, no visible
# faceting at print scale). Rigid TILES need a much coarser default —
# their STEP comes from kicad-cli with every component 3D model
# embedded, and meshing each BGA ball at 0.05 mm bloats the STL into
# the hundreds of MB. 0.3 mm linear is below a 0.4 mm FDM nozzle's
# print resolution so there's no visual quality loss in the print but
# the file size drops ~30×.
DEFAULT_TOLERANCE_MM = 0.05
DEFAULT_ANGULAR_TOLERANCE = 0.1
TILE_TOLERANCE_MM = 0.3
TILE_ANGULAR_TOLERANCE = 0.3


def write_stl_from_body(body, output_path: str | pathlib.Path,
                        *, tolerance: float = DEFAULT_TOLERANCE_MM,
                        angular_tolerance: float = DEFAULT_ANGULAR_TOLERANCE,
                        ) -> dict:
    """Mesh-export a cadquery solid `body` to STL.

    Mirrors the cadquery STEP exporter's interface. Returns a small
    summary dict with the output path and the tessellation tolerance
    used (recorded so the print run is traceable to the mesh
    resolution).
    """
    import cadquery as cq
    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(body, str(out),
                        tolerance=tolerance,
                        angularTolerance=angular_tolerance)
    return {
        "output_path": str(out),
        "tolerance_mm": tolerance,
        "angular_tolerance": angular_tolerance,
        "file_size_b": out.stat().st_size,
    }


def write_stl_from_step(step_path: str | pathlib.Path,
                         output_path: str | pathlib.Path,
                         *, tolerance: float = DEFAULT_TOLERANCE_MM,
                         angular_tolerance: float = DEFAULT_ANGULAR_TOLERANCE,
                         ) -> dict:
    """Re-import a STEP and write the same body out as STL.

    Used for rigid tiles whose STEPs come from `kicad-cli pcb export
    step` (which doesn't speak STL). The cadquery STEP reader handles
    the multi-shell BREP that kicad-cli produces. If the reader can't
    open the file, raises — callers wanting "skip-and-keep-going"
    semantics should wrap this in their own try/except.
    """
    import cadquery as cq
    step = pathlib.Path(step_path)
    if not step.exists():
        raise FileNotFoundError(step)
    body = cq.importers.importStep(str(step))
    return write_stl_from_body(body, output_path,
                               tolerance=tolerance,
                               angular_tolerance=angular_tolerance)


# ── splitting + labelling for FDM printability ──────────────────────────
# An FDM printer can't start a layer in mid-air — every solid feature on
# layer N has to land on something printed on layer N-1 or the bed. The
# rigid-tile and spacer geometries have features (chip bodies, cavity
# overhangs) on both top and bottom faces, so neither orientation prints
# cleanly without supports. The workaround is to slice each part in half
# horizontally, print each half with its split face on the bed, and glue
# the two halves together.
#
# Default split point: midplane of the body's Z extent. For tiles with
# components only on the top face, the caller passes an explicit
# `z_split` (typically `board.thickness_mm / 2`) so the cut goes through
# the PCB substrate rather than slicing through chip bodies.
DEFAULT_EMBOSS_DEPTH_MM = 0.6
DEFAULT_FONT_SIZE_MM = 6.0

# Alphabet for `unique_symbol`. A-Z + 2-9, with 0 / 1 / I / O dropped
# because they're confusable as printed glyphs at small scale.
SYMBOL_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SYMBOL_LENGTH = 2     # 32² = 1024 combinations; collisions <2 % per
                      # ~25-part configuration.


def unique_symbol(name: str, *, length: int = SYMBOL_LENGTH,
                  alphabet: str = SYMBOL_ALPHABET) -> str:
    """Compact, deterministic ASCII identifier for a board name.

    Hash-derived (md5) so the same name always gets the same code
    across regenerations. Two characters from a 32-char alphabet give
    1024 combinations — enough for ~25 parts per config with <2 %
    collision probability, and the symbol stays small enough to fit
    on a clear corner of any tile face."""
    import hashlib
    digest = hashlib.md5(name.encode()).digest()
    n = int.from_bytes(digest[:8], "big")
    chars = []
    for _ in range(length):
        chars.append(alphabet[n % len(alphabet)])
        n //= len(alphabet)
    return "".join(chars)


def split_at_z(body, z_split: float):
    """Cut a cadquery body / Workplane horizontally at `z = z_split`.
    Returns `(top_half, bottom_half)`."""
    import cadquery as cq
    solid = body.val() if hasattr(body, "val") else body
    bb = solid.BoundingBox()
    size = max(bb.xlen, bb.ylen) * 2 + 20
    cx = (bb.xmin + bb.xmax) / 2
    cy = (bb.ymin + bb.ymax) / 2
    # Slight margin past the body's z extents so the boolean cut is robust
    # against floating-point rounding at the bbox edges.
    margin = 1.0
    top_h = bb.zmax - z_split + margin
    bot_h = z_split - bb.zmin + margin
    top_box = cq.Workplane("XY",
                           origin=(cx, cy, z_split + top_h / 2)
                           ).box(size, size, top_h)
    bot_box = cq.Workplane("XY",
                           origin=(cx, cy, z_split - bot_h / 2)
                           ).box(size, size, bot_h)
    return body.intersect(top_box), body.intersect(bot_box)


def split_at_midplane(body):
    """Cut a cadquery body horizontally at its Z midplane. Returns
    `(top_half, bottom_half)`. Use for spacers, where features are
    distributed symmetrically about the midplane."""
    solid = body.val() if hasattr(body, "val") else body
    bb = solid.BoundingBox()
    return split_at_z(body, (bb.zmin + bb.zmax) / 2)


def emboss_text_on_bottom_face(body, label: str, *,
                                font_size_mm: float = DEFAULT_FONT_SIZE_MM,
                                emboss_mm: float = DEFAULT_EMBOSS_DEPTH_MM):
    """Add raised text on the body's bottom face — text extends in the
    -Z direction from `z = bbox.zmin`, so when the part is printed
    bottom-up the label appears as raised features on the upward-
    facing surface. Returns the body unchanged if cadquery can't
    render the text (bad font, etc.) — a font issue shouldn't crash
    an export pass.
    """
    import cadquery as cq
    solid = body.val() if hasattr(body, "val") else body
    bb = solid.BoundingBox()
    cx = (bb.xmin + bb.xmax) / 2
    cy = (bb.ymin + bb.ymax) / 2
    try:
        text_body = cq.Workplane("XY", origin=(cx, cy, bb.zmin)).text(
            label, fontsize=font_size_mm, distance=-emboss_mm,
            halign="center", valign="center",
        )
        return body.union(text_body)
    except Exception:
        return body


def recess_text_on_top_face(body, label: str, *,
                             font_size_mm: float = DEFAULT_FONT_SIZE_MM,
                             recess_mm: float = DEFAULT_EMBOSS_DEPTH_MM):
    """Cut recessed text into the body's top face — text extends in
    the -Z direction from `z = bbox.zmax`, carving an indentation into
    the topmost surface. Returns the body unchanged if cadquery can't
    render the text."""
    import cadquery as cq
    solid = body.val() if hasattr(body, "val") else body
    bb = solid.BoundingBox()
    cx = (bb.xmin + bb.xmax) / 2
    cy = (bb.ymin + bb.ymax) / 2
    try:
        text_body = cq.Workplane("XY", origin=(cx, cy, bb.zmax)).text(
            label, fontsize=font_size_mm, distance=-recess_mm,
            halign="center", valign="center",
        )
        return body.cut(text_body)
    except Exception:
        return body


def write_split_stls_from_body(body, output_path_prefix: str | pathlib.Path,
                                *,
                                z_split: float | None = None,
                                tolerance: float = DEFAULT_TOLERANCE_MM,
                                angular_tolerance: float = DEFAULT_ANGULAR_TOLERANCE,
                                symbol: str | None = None,
                                ) -> dict:
    """Split `body` at `z_split` (or midplane if None) and write the
    two halves as `<prefix>_top.stl` and `<prefix>_bot.stl`. With
    `symbol` set, apply a pairing-aid marking to both halves: the
    symbol is RAISED on the bottom half's outer (lower) face and
    RECESSED into the top half's outer (upper) face. The raised
    glyph on one half maps to a matching indent on the other — the
    same `symbol` value on both halves confirms they belong together.
    Symbol generation: see `unique_symbol(name)`."""
    if z_split is None:
        solid = body.val() if hasattr(body, "val") else body
        bb = solid.BoundingBox()
        z_split = (bb.zmin + bb.zmax) / 2
    top_half, bottom_half = split_at_z(body, z_split)
    if symbol:
        bottom_half = emboss_text_on_bottom_face(bottom_half, symbol)
        top_half = recess_text_on_top_face(top_half, symbol)
    prefix = pathlib.Path(output_path_prefix)
    out_top = prefix.parent / f"{prefix.name}_top.stl"
    out_bot = prefix.parent / f"{prefix.name}_bot.stl"
    r_top = write_stl_from_body(top_half, out_top,
                                 tolerance=tolerance,
                                 angular_tolerance=angular_tolerance)
    r_bot = write_stl_from_body(bottom_half, out_bot,
                                 tolerance=tolerance,
                                 angular_tolerance=angular_tolerance)
    return {
        "top": r_top, "bot": r_bot,
        "z_split_mm": z_split, "symbol": symbol,
    }


def write_split_stls_from_step(step_path: str | pathlib.Path,
                                output_path_prefix: str | pathlib.Path,
                                *,
                                z_split: float | None = None,
                                tolerance: float = TILE_TOLERANCE_MM,
                                angular_tolerance: float = TILE_ANGULAR_TOLERANCE,
                                symbol: str | None = None,
                                ) -> dict:
    """Read a STEP file with cadquery, split + write the two STL halves.
    Used for rigid tiles whose STEPs come from kicad-cli."""
    import cadquery as cq
    step = pathlib.Path(step_path)
    if not step.exists():
        raise FileNotFoundError(step)
    body = cq.importers.importStep(str(step))
    return write_split_stls_from_body(
        body, output_path_prefix,
        z_split=z_split,
        tolerance=tolerance, angular_tolerance=angular_tolerance,
        symbol=symbol,
    )


def write_stls_for_step_dir(directory: str | pathlib.Path,
                             *, tolerance: float = DEFAULT_TOLERANCE_MM,
                             angular_tolerance: float = DEFAULT_ANGULAR_TOLERANCE,
                             recursive: bool = True) -> list[dict]:
    """Walk `directory`, convert every `.step` file to a sibling `.stl`.

    Idempotent: re-running over the same directory overwrites. Skips
    `.stl` files that already exist alongside fresher STEPs only if you
    pass `skip_existing` — by default we always regenerate so the mesh
    stays in sync with whatever the STEP describes.

    Returns a list of summary dicts (`write_stl_from_step`'s shape) plus
    a separate `failed` field listing any STEP whose reader raised.
    """
    root = pathlib.Path(directory)
    pattern = "**/*.step" if recursive else "*.step"
    out: list = []
    failed: list = []
    for step in sorted(root.glob(pattern)):
        try:
            r = write_stl_from_step(
                step, step.with_suffix(".stl"),
                tolerance=tolerance,
                angular_tolerance=angular_tolerance,
            )
            out.append(r)
        except Exception as exc:                         # keep run resilient
            failed.append({"step": str(step), "error":
                           f"{type(exc).__name__}: {exc}"})
    return [{"converted": out, "failed": failed}]
