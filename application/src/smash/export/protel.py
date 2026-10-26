"""Protel / Tango / Altium netlist writer (.NET).

Format accepted by Altium Designer (Design → Netlist → Load Netlist),
Tango, P-CAD, and several other tools in the Protel lineage. Each
component is wrapped in [ ] with refdes / footprint / value on
consecutive lines; each net is wrapped in ( ) with the netname
followed by REF-PIN tokens, one per line.
"""

from __future__ import annotations

from pathlib import Path

from smash.state import Design
from smash.export._common import (
    all_components,
    nets_with_pins,
    net_connections,
    footprint_name,
    sanitize_protel_id,
)


def write_protel_netlist(design: Design, path: str | Path) -> dict:
    """Write a Protel/Altium netlist. Returns {n_parts, n_nets}."""
    lines: list[str] = []

    # Component block — one [ ... ] per part
    for c in all_components(design):
        ref = sanitize_protel_id(c.ref)
        footprint = sanitize_protel_id(footprint_name(c))
        manf_pn = (getattr(c, "manf_pn", "") or "").strip()
        value = (getattr(c, "value", "") or "").strip()
        name = (getattr(c, "name", "") or "").strip()
        comp_value = sanitize_protel_id(manf_pn or value or name or "PART")
        lines.append("[")
        lines.append(ref)
        lines.append(footprint)
        lines.append(comp_value)
        lines.append("]")

    # Net block — one ( ... ) per net
    n_nets = 0
    for net in nets_with_pins(design):
        n_nets += 1
        lines.append("(")
        lines.append(sanitize_protel_id(net.name))
        for ref, num in net_connections(net):
            lines.append(
                f"{sanitize_protel_id(ref)}-{sanitize_protel_id(num)}"
            )
        lines.append(")")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines))
        f.write("\n")
    return {"n_parts": len(design.chips) + len(design.batteries) + len(getattr(design, "antennas", [])),
            "n_nets":  n_nets}


def write_board_protel_netlist(design: Design, board, path: str | Path) -> dict:
    """Write one board's netlist, matching its `.kicad_pcb` exactly: the
    footprints placed on it, under the refdes (`kicad_ref`), library
    footprint name (the portable project's entry) and Value the board
    carries, and every net touching them under its board name — so
    loading it into the board in Altium changes no part or connection. The
    `unconnected-(…)` nets KiCad gives no-connect pads are left out
    (Protel syntax can't carry their parentheses), as are the board-only
    mounting holes (no symbol, no nets). Returns {n_parts, n_nets}."""
    from smash.export._common import component_value, kicad_ref
    from smash.export.portable_project import _fp_filename
    from smash.state import Chip
    from smash.state.antenna import Antenna

    refs = {pl.item.ref for pl in board.chip_placements
            if isinstance(pl.item, (Chip, Antenna)) and pl.item.footprint is not None}
    comps = [c for c in all_components(design) if c.ref in refs]
    lines: list[str] = []
    for c in comps:
        lines += ["[", kicad_ref(c.ref), _fp_filename(c.footprint.name),
                  sanitize_protel_id(component_value(c)), "]"]
    n_nets = 0
    for net in nets_with_pins(design):
        nodes = [(r, num) for r, num in net_connections(net) if r in refs]
        if not nodes:
            continue
        n_nets += 1
        lines += ["(", net.name, *(f"{kicad_ref(r)}-{num}" for r, num in nodes), ")"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n")
    return {"n_parts": len(comps), "n_nets": n_nets}
