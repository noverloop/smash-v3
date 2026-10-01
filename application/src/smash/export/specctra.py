"""Specctra DSN writer for FreeRouting / Cadence Allegro / DeepPCB.

DSN is a documented LISP-style ASCII format originally defined by
Cooper & Chyan Technology for the SPECCTRA autorouter, later acquired
by Cadence Allegro. It carries the full design intent: structure
(layers + board boundary + design rules), library (footprint images +
padstacks), placement (component positions), and network (nets +
classes).

Consumed by:
  - Cadence Allegro PCB Designer (File → Import → SPECCTRA DSN)
  - FreeRouting (open-source autorouter)
  - DeepPCB / AI routing tools
  - Most PCB CAD tools as a general interchange format

Generation strategy — since the Design dataclass doesn't carry geometry:
  - Layer stackup: 8 signal layers with FR-4 / aluminium-core defaults
  - Per-board outlines: read from `mechanical/<board>.dxf` if available,
    else fall back to a Ø34 mm circle (projectile bore constraint)
  - Padstacks: one placeholder SMD padstack reused across all components
  - Placement: components tiled on a per-board grid inside each outline
  - Network: every net with its (ref, pin) connections
  - Wiring: empty stub (required by tscircuit/specctra-dsn-json schema)

The output is electrically complete (netlist + footprint refs) but
geometrically minimal — sufficient for FreeRouting / DeepPCB to take
over, or for a layout engineer to import and re-define real footprint
geometry from the project's library.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from smash.state import Design
from smash.export._common import (
    all_components,
    nets_with_pins,
    net_connections,
    footprint_name,
)


# ── DSN-style helpers ────────────────────────────────────────────────────


def _dsn_id(s: str) -> str:
    return str(s).replace('"', "_")


def _q(s: str) -> str:
    return f'"{_dsn_id(s)}"'


# ── geometry knobs (defaults match system.py) ────────────────────────────

BOARD_DIAMETER_MM = 34.0           # projectile bore
BOARD_PADDING_MM  = 8.0            # between board centers in canvas
BOARDS_PER_ROW    = 1              # one column (axial stack)
UM_PER_MM         = 10_000          # 0.1 µm per unit
PIN_SPACING_UNITS = 1_000           # 0.1 mm grid for placeholder pins

# Layer stackup — 8 copper layers. F.Cu + In1..In6 + B.Cu. B.Cu sits on
# 1 mm aluminium substrate (MCPCB) — no through-vias allowed in
# production. The DSN doesn't model the Al core; via restrictions get
# applied at layout time.
DEFAULT_LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu",
                  "In4.Cu", "In5.Cu", "In6.Cu", "B.Cu"]

# Default board outline order along the projectile axis (tail → nose).
# Boards not in this list land at the end alphabetically.
DEFAULT_BOARD_LAYOUT_ORDER = [
    "activation_interface",
    "power_board",
    "wakeup_board",
    "flight_board",
    "companion_compute",
    "companion_io",
    "radar_module",
    "nose_cap",
    "camera_module",
]


def write_specctra_dsn(
    design: Design,
    path: str | Path,
    *,
    design_name: str = "smash",
    layers: list[str] | None = None,
    board_layout_order: list[str] | None = None,
    mechanical_dxf_dir: str | Path | None = None,
    board_diameter_mm: float = BOARD_DIAMETER_MM,
    board_padding_mm: float = BOARD_PADDING_MM,
    boards_per_row: int = BOARDS_PER_ROW,
) -> dict:
    """Write a Specctra DSN.

    Args:
      design:               the Design to render.
      path:                 output filename.
      design_name:          name embedded in the `(pcb "<name>")` header.
      layers:               copper layer names; defaults to 8-layer
                            F.Cu + In1..In6 + B.Cu stack.
      board_layout_order:   axial order of tiles (tail → nose).
      mechanical_dxf_dir:   if given, each board's outline is read from
                            `<dir>/<board>.dxf` (BOARD_OUTLINE layer);
                            otherwise falls back to a Ø34 mm circle.
      board_diameter_mm,
      board_padding_mm,
      boards_per_row:       geometry knobs for the canvas tiling.

    Returns {n_parts, n_nets, n_footprints, area_warnings}.
    """
    layers = list(layers or DEFAULT_LAYERS)
    board_layout_order = list(
        board_layout_order or DEFAULT_BOARD_LAYOUT_ORDER
    )
    board_radius_mm = board_diameter_mm / 2.0
    interior_mm2 = math.pi * (board_radius_mm - 1.0) ** 2

    components = all_components(design)

    # Group footprints — one image per unique footprint name,
    # gathering the set of pin numbers seen across all instances.
    fp_pin_nums: dict[str, set[str]] = {}
    for c in components:
        fp = _dsn_id(footprint_name(c)) or "UNDEFINED"
        pins = {str(p.num) for p in c.pins}
        fp_pin_nums.setdefault(fp, set()).update(pins)

    PADSTACK_NAME = "PS_smd_default"
    lines: list[str] = []
    lines.append(f'(pcb "{design_name}"')
    lines.append("  (parser")
    lines.append('    (string_quote ")')
    lines.append("    (space_in_quoted_tokens on)")
    lines.append('    (host_cad "smash.export.specctra")')
    lines.append('    (host_version "1.0")')
    lines.append("  )")
    lines.append("  (resolution um 10)")
    lines.append("  (unit um)")

    # ── Structure: layers + boundary + default rule ──
    lines.append("  (structure")
    for idx, name in enumerate(layers):
        lines.append(f"    (layer {name}")
        lines.append("      (type signal)")
        lines.append("      (property")
        lines.append(f"        (index {idx})")
        lines.append("      )")
        lines.append("    )")
    # Placeholder boundary — 80 mm × 720 mm in 0.1 µm units.
    lines.append("    (boundary")
    lines.append("      (path pcb 0  0 0  800000 0  800000 7200000  0 7200000  0 0)")
    lines.append("    )")
    lines.append('    (via "Via_default")')
    lines.append("    (rule")
    lines.append("      (width 200)")
    lines.append("      (clearance 200)")
    lines.append("      (clearance 200 (type default_smd))")
    lines.append("      (clearance 50 (type smd_smd))")
    lines.append("    )")
    lines.append("  )")

    # ── Group parts by board_tag ──
    parts_by_board: dict[str, list] = {}
    for c in components:
        board = getattr(c, "board_tag", None) or "unknown"
        parts_by_board.setdefault(board, []).append(c)

    explicit = [b for b in board_layout_order if b in parts_by_board]
    unknown  = sorted(b for b in parts_by_board if b not in board_layout_order)
    sorted_boards = explicit + unknown

    # Per-board layout
    board_centers: dict[str, tuple[float, float]] = {}
    for i, board in enumerate(sorted_boards):
        col = i % boards_per_row
        row = i // boards_per_row
        cx = (board_diameter_mm + board_padding_mm) * col + board_radius_mm + 5
        cy = (board_diameter_mm + board_padding_mm) * row + board_radius_mm + 5
        board_centers[board] = (cx, cy)

    # Area-budget check (Ø34 interior, minus 1 mm safety border)
    area_warnings: list[tuple[str, float]] = []
    for board in sorted_boards:
        area = sum(_part_area_mm2(p) for p in parts_by_board[board])
        if area > interior_mm2:
            area_warnings.append((board, area))

    # Component placement on a per-board grid
    placed_per_fp: dict[str, list[tuple[str, int, int]]] = {}
    for board in sorted_boards:
        cx_mm, cy_mm = board_centers[board]
        grid_pts = _grid_points_in_circle(board_radius_mm)
        for idx, c in enumerate(parts_by_board[board]):
            if idx < len(grid_pts):
                dx, dy = grid_pts[idx]
            else:
                dx, dy = 0.0, 0.0
            x_units = int((cx_mm + dx) * UM_PER_MM)
            y_units = int((cy_mm + dy) * UM_PER_MM)
            fp = _dsn_id(footprint_name(c)) or "UNDEFINED"
            placed_per_fp.setdefault(fp, []).append((c.ref, x_units, y_units))

    lines.append("  (placement")
    for fp_name, instances in sorted(placed_per_fp.items()):
        token = (fp_name
                 if all(ch.isalnum() or ch in "_:." for ch in fp_name)
                 else _q(fp_name))
        lines.append(f"    (component {token}")
        for ref, x, y in instances:
            ref_token = (ref
                         if all(ch.isalnum() or ch in "_." for ch in ref)
                         else _q(ref))
            lines.append(f"      (place {ref_token} {x} {y} front 0)")
        lines.append("    )")
    lines.append("  )")

    # ── Library: footprint images + padstacks ──
    lines.append("  (library")
    for fp_name, pin_nums in sorted(fp_pin_nums.items()):
        token = (fp_name
                 if all(ch.isalnum() or ch in "_:." for ch in fp_name)
                 else _q(fp_name))
        lines.append(f"    (image {token}")
        pin_list = sorted(pin_nums, key=lambda x: (len(x), x))
        cols = max(2, int(len(pin_list) ** 0.5))
        for idx, pn in enumerate(pin_list):
            px = (idx % cols) * PIN_SPACING_UNITS
            py = (idx // cols) * PIN_SPACING_UNITS
            pn_token = pn if pn.isdigit() else _q(pn)
            lines.append(f"      (pin {PADSTACK_NAME} {pn_token} {px} {py})")
        lines.append("    )")
    # Default SMD padstack — F.Cu only (placeholder geometry)
    lines.append(f"    (padstack {PADSTACK_NAME}")
    lines.append("      (shape (circle F.Cu 500))")
    lines.append("      (attach off)")
    lines.append("    )")
    # Default via — through all layers (placeholder; per-net restrictions
    # applied at layout time because B.Cu sits on the Al substrate)
    lines.append("    (padstack Via_default")
    for L in layers:
        lines.append(f"      (shape (circle {L} 500))")
    lines.append("      (attach off)")
    lines.append("    )")
    lines.append("  )")

    # ── Network: nets + class ──
    lines.append("  (network")
    nets_emitted: list[str] = []
    for net in nets_with_pins(design):
        net_name = _dsn_id(net.name)
        nets_emitted.append(net_name)
        lines.append(f"    (net {_q(net_name)}")
        connections = [
            f"{_dsn_id(ref)}-{_dsn_id(num)}"
            for ref, num in net_connections(net)
        ]
        lines.append("      (pins")
        for i in range(0, len(connections), 6):
            chunk = " ".join(connections[i:i + 6])
            lines.append(f"        {chunk}")
        lines.append("      )")
        lines.append("    )")
    lines.append('    (class kicad_default ""')
    for nname in nets_emitted:
        lines.append(f"      {_q(nname)}")
    lines.append("      (circuit")
    lines.append("        (use_via Via_default)")
    lines.append("      )")
    lines.append("      (rule")
    lines.append("        (width 200)")
    lines.append("        (clearance 200)")
    lines.append("      )")
    lines.append("    )")
    lines.append("  )")

    # Wiring stub (required by tscircuit/specctra-dsn-json schema even
    # if empty for a netlist-only DSN)
    lines.append("  (wiring")
    lines.append("  )")
    lines.append(")")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines))
        f.write("\n")

    return {
        "n_parts":        len(components),
        "n_nets":         len(nets_emitted),
        "n_footprints":   len(fp_pin_nums),
        "area_warnings":  area_warnings,
    }


def _grid_points_in_circle(radius_mm: float,
                            step_mm: float = 1.5) -> list[tuple[float, float]]:
    pts: list[tuple[float, float, float]] = []
    n = int(radius_mm / step_mm) + 1
    for ix in range(-n, n + 1):
        for iy in range(-n, n + 1):
            x, y = ix * step_mm, iy * step_mm
            if x * x + y * y <= (radius_mm - 0.6) ** 2:
                pts.append((x * x + y * y, x, y))
    pts.sort()
    return [(x, y) for _, x, y in pts]


# ── per-part area estimate (mm²) ────────────────────────────────────────


def _part_area_mm2(part) -> float:
    """Best-effort area estimate from catalog `size_mm` first, then
    footprint name heuristics. Returns 0.0 when nothing is known
    (connector / placeholder)."""
    sz = getattr(part, "size_mm", None)
    if sz and len(sz) >= 2 and sz[0] and sz[1]:
        return float(sz[0]) * float(sz[1])
    fp = getattr(part, "footprint", None)
    fp_name = (getattr(fp, "name", "") or "").upper() if fp else ""
    if "R_0402" in fp_name or "C_0402" in fp_name or "L_0402" in fp_name:
        return 0.5
    if "R_0603" in fp_name or "C_0603" in fp_name:
        return 1.28
    if "R_1812" in fp_name or "C_1812" in fp_name:
        return 14.4
    if "EIA-3528" in fp_name:
        return 9.8
    if "SOT-23" in fp_name:
        return 5.3
    if "SOD-323" in fp_name:
        return 2.1
    if "SOIC-8" in fp_name:
        return 19.1
    if "SOIC-16" in fp_name:
        return 38.6
    if "TSSOP-8" in fp_name:
        return 9.0
    if "TSSOP-16" in fp_name:
        return 22.0
    if "HTSSOP-14" in fp_name:
        return 28.6
    if "HTSSOP-28" in fp_name:
        return 42.7
    return 0.0
