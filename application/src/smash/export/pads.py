"""PADS Layout ASCII netlist (.asc).

Accepted by PADS Layout, Xpedition Layout (via PADS netlist reader),
and most Mentor/Siemens layout-side importers. Bypasses schematic
capture — parts arrive with refdes + part-type; decals (footprints)
get assigned during layout via library mapping.

Sections (order matters — PART must precede NET):
  *PART*  : RefDes  PartName@Decal
  *NET*   : *SIGNAL* <netname>  followed by REF.PIN tokens
  *END*   : terminator
"""

from __future__ import annotations

from pathlib import Path

from smash.state import Design
from smash.export._common import (
    all_components,
    nets_with_pins,
    net_connections,
    footprint_name,
    sanitize_pads_id,
)


def write_pads_netlist(design: Design, path: str | Path) -> dict:
    """Write the PADS Layout ASCII netlist. Returns {n_parts, n_nets}."""
    lines: list[str] = []
    lines.append("!PADS-POWERPCB-V9.0-METRIC! NETLIST FILE 1.0")
    lines.append("*PADS-POWERPCB-V9.0-METRIC*")
    lines.append("")

    # *PART* — RefDes  PartName@Decal
    lines.append("*PART*")
    for c in all_components(design):
        ref = sanitize_pads_id(c.ref)
        manf_pn = (getattr(c, "manf_pn", "") or "").strip()
        value = (getattr(c, "value", "") or "").strip()
        name = (getattr(c, "name", "") or "").strip()
        decal = sanitize_pads_id(footprint_name(c))
        part_name = sanitize_pads_id(manf_pn or value or name or "PART")
        lines.append(f"{ref}    {part_name}@{decal}")
    lines.append("")

    # *NET* — one *SIGNAL* per net, REF.PIN tokens wrapped ~6 per line
    lines.append("*NET*")
    n_nets = 0
    for net in nets_with_pins(design):
        n_nets += 1
        net_name = sanitize_pads_id(net.name)
        connections = [
            f"{sanitize_pads_id(ref)}.{sanitize_pads_id(num)}"
            for ref, num in net_connections(net)
        ]
        lines.append("")
        lines.append(f"*SIGNAL* {net_name}")
        for i in range(0, len(connections), 6):
            lines.append(" ".join(connections[i:i + 6]))
    lines.append("")
    lines.append("*END*")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines))
        f.write("\n")
    return {"n_parts": len(design.chips) + len(design.batteries) + len(getattr(design, "antennas", [])),
            "n_nets":  n_nets}
