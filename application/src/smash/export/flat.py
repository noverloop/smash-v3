"""Three-column tab-delimited netlist (NET<tab>REF<tab>PIN per row).

Format accepted by Mentor/Siemens Xpedition, PADS, and most
Allegro/Calay-style importers. Sorted by net name then by ref/pin for
stable diffs.
"""

from __future__ import annotations

from pathlib import Path

from smash.state import Design
from smash.export._common import nets_with_pins, net_connections


def write_flat_netlist(design: Design, path: str | Path) -> dict:
    """Write the tab-delimited netlist. Returns {n_connections}."""
    rows: list[tuple[str, str, str]] = []
    for net in nets_with_pins(design):
        for ref, num in net_connections(net):
            rows.append((net.name, ref, num))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("NET\tREF\tPIN\n")
        for net_name, ref, pin in rows:
            f.write(f"{net_name}\t{ref}\t{pin}\n")
    return {"n_connections": len(rows)}
