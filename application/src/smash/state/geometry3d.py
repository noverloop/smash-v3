"""Board-local 3D resolution — routing elements → `(x, y, z)`.

The XY of every routing primitive is already board-local (math-y-up,
board-centre origin), shared with `Pad`/`Placement`. This module adds the
Z half by reading each element's layer elevation from `Board.layer_z_mm`
(z = 0 at the board's bottom face, +Z up — see `Board._layer_elevations`).

These free functions are the surface a physics-sim mesher consumes: each
returns geometry in the board frame. Resolution is strict — a routing
layer not present in the board's stackup raises `KeyError` (a routing↔
stackup validator is the intended guard that reports such a mismatch
cleanly rather than crashing the mesher).
"""
from __future__ import annotations

import math


def track_polyline_3d(board, track) -> list:
    """A `Track` as a 3D centreline `[(x, y, z), …]`; z is the track
    layer's copper mid-plane."""
    z, _ = board.layer_z_mm(track.layer)
    return [(x, y, z) for x, y in track.path]


def via_segment_3d(board, via) -> tuple:
    """A `Via` barrel as `((x, y, z_top), (x, y, z_bottom))`, spanning the
    full Z extent between its `from_layer` and `to_layer`."""
    fb, ft = board.layer_span_mm(via.from_layer)
    tb, tt = board.layer_span_mm(via.to_layer)
    z_top, z_bottom = max(ft, tt), min(fb, tb)
    x, y = via.position_mm
    return ((x, y, z_top), (x, y, z_bottom))


def zone_polygon_3d(board, zone) -> list:
    """A `Zone` pour outline as a 3D polygon `[(x, y, z), …]` at its
    layer's copper mid-plane."""
    z, _ = board.layer_z_mm(zone.layer)
    return [(x, y, z) for x, y in zone.outline_mm]


def copper_on_layer(board, layer_name: str) -> dict:
    """The etched-copper element set on one layer, each paired with its
    3D geometry: tracks/zones whose `layer` matches, and vias whose barrel
    passes through `layer_name`. Returns
    `{"tracks": [(track, polyline)], "zones": [(zone, polygon)],
      "vias": [(via, segment)]}` — the per-layer view a mesher iterates."""
    z_layer, _ = board.layer_z_mm(layer_name)        # also validates the name
    tracks = [(t, track_polyline_3d(board, t))
              for t in board.tracks if t.layer == layer_name]
    zones = [(zn, zone_polygon_3d(board, zn))
             for zn in board.zones if zn.layer == layer_name]
    vias = []
    eps = 1e-9
    for v in board.vias:
        (x, y, z_top), (_, _, z_bot) = via_segment_3d(board, v)
        if z_bot - eps <= z_layer <= z_top + eps:
            vias.append((v, ((x, y, z_top), (x, y, z_bot))))
    return {"tracks": tracks, "zones": zones, "vias": vias}


def _face_layer(face: str) -> str:
    """Outer copper a component on `face` mounts to."""
    return "F.Cu" if (face or "top") == "top" else "B.Cu"


def pad_xyz(board, placement, pad) -> tuple:
    """Board-local `(x, y, z)` of a footprint pad. `pad.position_mm` is
    footprint-local; this composes the placement transform — mirror in X
    for a bottom-face part (KiCad's flip), rotate by `rotation_deg`,
    translate to `position_mm` — and takes z from the mounting face's
    outer copper plane."""
    px, py = pad.position_mm
    face = getattr(placement, "face", "top") or "top"
    if face == "bottom":
        px = -px                                   # flip to back mirrors X
    rot = math.radians(getattr(placement, "rotation_deg", 0.0) or 0.0)
    cos, sin = math.cos(rot), math.sin(rot)
    rx = px * cos - py * sin
    ry = px * sin + py * cos
    cx, cy = placement.position_mm
    z, _ = board.layer_z_mm(_face_layer(face))
    return (cx + rx, cy + ry, z)


def chip_body_3d(board, placement) -> dict:
    """Board-local bounding box of a placed component body. The box is
    `size_mm` (footprint envelope) extruded by the component height AWAY
    from the board — up from the top surface for a top-face part, down
    below z=0 for a bottom-face part (mirrors `stackup_step._component_
    blocks`). Returns a descriptor a mesher extrudes/rotates."""
    chip = placement.item
    fp = getattr(chip, "footprint", None)
    w, h = (getattr(fp, "size_mm", None)
            or getattr(chip, "size_mm", None) or (1.0, 1.0))
    ht = (getattr(fp, "height_mm", None)
          or getattr(chip, "height_mm", None) or 0.5)
    face = getattr(placement, "face", "top") or "top"
    base_z = board.thickness_mm if face == "top" else -ht
    cx, cy = placement.position_mm
    return {
        "ref": getattr(chip, "ref", None),
        "center_mm": (cx, cy),
        "size_mm": (w, h),
        "base_z_mm": base_z,
        "height_mm": ht,
        "rotation_deg": getattr(placement, "rotation_deg", 0.0) or 0.0,
        "face": face,
    }


def board_solder(board, *, fab=None):
    """The `Solder` for a board's joints: `board.solder` resolved against
    the fab catalog, falling back to the profile's default reflow paste."""
    from smash.state.fab import default_fab_profile
    prof = fab or default_fab_profile()
    if getattr(board, "solder", None):
        return prof.solder(board.solder) or prof.default_solder
    return prof.default_solder


def chip_underfill(chip, *, fab=None):
    """The `Adhesive` under a chip, or None if it isn't underfilled."""
    name = getattr(chip, "underfill", None)
    if not name:
        return None
    from smash.state.fab import default_fab_profile
    return (fab or default_fab_profile()).adhesive(name)


def layer_elevations(board) -> dict:
    """`{name: (z_bottom_mm, z_top_mm, z_tol_mm)}` for every copper layer
    (passthrough to `Board._layer_elevations`)."""
    return board._layer_elevations()


def stack_height_mm(board) -> float:
    """Z extent of the conductor stack — top of the topmost copper layer
    (F.Cu), board-local. 0.0 for a board with no stackup."""
    elev = board._layer_elevations()
    return max((top for _, top, _ in elev.values()), default=0.0)
