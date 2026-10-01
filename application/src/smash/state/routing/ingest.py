"""Ingest a routed Specctra session (`.ses`) into native routing.

Converts the parsed `Session` (from `smash.validators.specctra._session`)
into `Track` / `Via` objects:

  - **units → mm**: a `(resolution um 10)` declares 10 sub-units per µm,
    i.e. 10 000 integer units per mm. Coordinates are divided out.
  - **Y-flip**: a `.ses` is screen-y-down (the autorouter inherits
    KiCad's convention); native routing is math-y-up, so Y is negated
    (the inverse of `smash.export.kicad_pcb._flip_y`).
  - **via resolution**: drill, pad diameter and layer span come from the
    padstack, not the via node. Pad diameter + span layers are read from
    the padstack's `circle` shapes; the finished drill (which a `.ses`
    padstack does not carry) is parsed from the KiCad padstack *name*
    (`Via[a-b]_<pad>:<drill>_um`).

The `.ses` coordinates are **panel-global** (the whole folded panel is
routed as one PCB). `import_session()` returns panel-global `Track`/`Via`;
`localize()` splits them per board given an explicit
`board_offsets = {board: (cx_mm, cy_mm)}` table in the same math-y-up
panel frame (the tile centres the panel exporter placed each board at).
`ingest_session()` ties the two together and appends onto each `Board`.

KiCad sessions carry copper only as wires/vias — never filled zones — so
nothing here populates `Board.zones`.
"""
from __future__ import annotations

import dataclasses
import re

from smash.state.routing.track import Track
from smash.state.routing.via import Via
from smash.validators.specctra._session import Session, parse_session


# KiCad via-padstack name, e.g. "Via[0-1]_600:300_um" → pad 600 µm, drill 300 µm.
_VIA_NAME_RE = re.compile(r"\[(\d+)-(\d+)\]_(\d+):(\d+)")


@dataclasses.dataclass
class ParsedRouting:
    """Panel-global routing extracted from a `.ses` (pre-localization)."""
    tracks: list                        # list[Track], panel-global mm
    vias: list                          # list[Via], panel-global mm


def _units_per_mm(resolution) -> float:
    """Integer DSN units per mm. `(resolution um V)` → V sub-units per
    µm → V*1000 per mm; `(resolution mm V)` → V per mm."""
    unit = (resolution.unit or "um").lower()
    v = resolution.value
    if unit == "um":
        return v * 1000.0
    if unit == "mm":
        return v
    if unit in ("inch", "in"):
        return v / 25.4
    raise ValueError(f"unsupported resolution unit {unit!r}")


def _resolve_padstack(session: Session, name: str):
    """Return (drill_mm, pad_diameter_mm, from_layer, to_layer) for a via
    padstack. Pad + span layers come from the padstack's circle shapes;
    the drill comes from the `<pad>:<drill>` token in the padstack name."""
    upm = _units_per_mm(session.resolution)
    ps = session.padstacks.get(name)

    layers: list[str] = []
    pad_mm = 0.0
    if ps is not None:
        for shape in ps.shapes:
            layer = getattr(shape, "layer", None)
            radius = getattr(shape, "radius", None)   # Specctra circle: diameter
            if layer and layer not in layers:
                layers.append(layer)
            if radius is not None:
                pad_mm = max(pad_mm, radius / upm)

    drill_mm = 0.0
    m = _VIA_NAME_RE.search(name or "")
    if m:
        name_pad_um, name_drill_um = float(m.group(3)), float(m.group(4))
        drill_mm = name_drill_um / 1000.0
        if pad_mm <= 0.0:
            pad_mm = name_pad_um / 1000.0

    from_layer = layers[0] if layers else "F.Cu"
    to_layer = layers[-1] if layers else "B.Cu"
    return drill_mm, pad_mm, from_layer, to_layer


def import_session(source) -> ParsedRouting:
    """Parse a `.ses` and convert its wiring to panel-global `Track`/`Via`
    (mm, math-y-up). `source` is a path or raw text."""
    session = source if isinstance(source, Session) else parse_session(source)
    upm = _units_per_mm(session.resolution)

    def _xy(x, y):
        # units → mm, then screen-y-down → math-y-up.
        return (x / upm, -(y / upm))

    tracks: list = []
    for w in session.wiring.wires:
        shape = w.shape
        coords = getattr(shape, "coordinates", None) or []
        if len(coords) < 2:
            continue
        tracks.append(Track(
            net=w.net,
            layer=shape.layer,
            width_mm=shape.width / upm,
            path=[_xy(px, py) for px, py in coords],
        ))

    vias: list = []
    for v in session.wiring.vias:
        if v.x is None or v.y is None:
            continue
        drill_mm, pad_mm, from_layer, to_layer = _resolve_padstack(
            session, v.primary_padstack)
        vias.append(Via(
            net=v.net,
            position_mm=_xy(v.x, v.y),
            drill_mm=drill_mm,
            pad_diameter_mm=pad_mm,
            from_layer=from_layer,
            to_layer=to_layer,
        ))

    return ParsedRouting(tracks=tracks, vias=vias)


def _nearest_board(point, board_offsets):
    px, py = point
    return min(board_offsets,
               key=lambda b: (board_offsets[b][0] - px) ** 2
                             + (board_offsets[b][1] - py) ** 2)


def localize(parsed: ParsedRouting, board_offsets: dict) -> dict:
    """Split panel-global routing into per-board, board-local routing.

    `board_offsets = {board: (cx_mm, cy_mm)}` gives each tile's centre in
    the panel's math-y-up frame. Each track is assigned to the board
    nearest its first vertex (a routed trace stays within one tile), each
    via to the board nearest its centre, and coordinates are shifted into
    that board's local frame. Returns `{board: (tracks, vias)}`.
    """
    if not board_offsets:
        raise ValueError("localize() needs a non-empty board_offsets table")

    out: dict = {b: ([], []) for b in board_offsets}
    for t in parsed.tracks:
        b = _nearest_board(t.path[0], board_offsets)
        ox, oy = board_offsets[b]
        out[b][0].append(dataclasses.replace(
            t, path=[(x - ox, y - oy) for x, y in t.path]))
    for v in parsed.vias:
        b = _nearest_board(v.position_mm, board_offsets)
        ox, oy = board_offsets[b]
        x, y = v.position_mm
        out[b][1].append(dataclasses.replace(v, position_mm=(x - ox, y - oy)))
    return out


def ingest_session(smash_state, source, *, board_offsets: dict) -> dict:
    """Parse a routed `.ses` and append its tracks/vias onto the matching
    `Board`s in `smash_state`, in board-local coordinates. `board_offsets`
    maps board name → tile centre (math-y-up mm) on the routed panel.
    Returns `{board: (n_tracks, n_vias)}` for the boards that gained
    routing. Boards in `board_offsets` but absent from `smash_state` are
    skipped."""
    parsed = import_session(source)
    per_board = localize(parsed, board_offsets)
    counts: dict = {}
    for name, (tracks, vias) in per_board.items():
        board = smash_state.boards.get(name)
        if board is None or (not tracks and not vias):
            continue
        board.tracks.extend(tracks)
        board.vias.extend(vias)
        counts[name] = (len(tracks), len(vias))
    return counts
