"""EDIF 200 netlist writer (LISP S-expression).

Carries part attributes (value, manf_pn, footprint, board, manf,
fab_country, cost_usd) as EDIF properties so they survive a round-trip
through tools that preserve EDIF properties (Xpedition, OrCAD
Capture). Designed for netlist-only handoff — no schematic geometry,
no hierarchy, single flat view.

Parts are grouped into reusable EDIF "cells" by (name, footprint,
sorted pin signature). Catalog factories produce consistent Part data,
so multiple instances of the same chip (e.g. 4× TCAN1042 across the
design) consolidate to one shared cell.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from smash.state import Design
from smash.export._common import (
    all_components,
    nets_with_pins,
    net_connections,
    sanitize_ascii,
    sanitize_edif_id,
)


# Pin-type to EDIF direction. EDIF only has INPUT / OUTPUT / INOUT —
# everything fuzzy collapses to INOUT to be safe.
_DIR_MAP = {
    "power":   "INPUT",
    "ground":  "INPUT",
    "input":   "INPUT",
    "output":  "OUTPUT",
    "io":      "INOUT",
    "analog":  "INOUT",
    "clock":   "INPUT",
    "nc":      "INPUT",
    "reserved": "INPUT",
}


def _dir(pin) -> str:
    return _DIR_MAP.get(getattr(pin, "type", None) or "", "INOUT")


def _quote(s: str) -> str:
    """Quoted EDIF stringToken — ASCII-only, with % and " escaped per
    EDIF 2.0."""
    s = sanitize_ascii(s)
    s = s.replace("%", "%37%").replace('"', "%34%")
    return '"' + s + '"'


def _named(s: str) -> str:
    """Emit either a bare identifier or a (rename safe "original") form."""
    safe = sanitize_edif_id(s)
    if safe == str(s):
        return safe
    return f"(rename {safe} {_quote(s)})"


def write_edif(design: Design, path: str | Path,
               *, design_name: str = "smash_design") -> dict:
    """Write an EDIF 200 netlist to `path`. Returns {n_cells, n_instances,
    n_nets}."""
    components = all_components(design)

    # Group components into reusable EDIF cells by (name, footprint, sorted
    # pin signature). Two instances of the same chip share one cell.
    cells: dict[str, dict] = {}
    comp_to_cell: dict[str, str] = {}
    for c in components:
        pins = sorted(c.pins, key=lambda p: str(p.num))
        fp_name = ""
        fp = getattr(c, "footprint", None)
        if fp is not None:
            fp_name = getattr(fp, "name", "") or ""
        sig = (
            getattr(c, "name", "PART") or getattr(c, "manf_pn", "PART") or "PART",
            fp_name,
            tuple(
                (str(p.num), getattr(p, "name", "") or "", _dir(p))
                for p in pins
            ),
        )
        prefix = sanitize_edif_id(
            getattr(c, "name", None)
            or getattr(c, "manf_pn", None)
            or "PART"
        )
        cell_id = f"{prefix}_{abs(hash(sig)) % 10_000_000:07d}"
        if cell_id not in cells:
            cells[cell_id] = {"pins": pins, "parts": []}
        cells[cell_id]["parts"].append(c)
        comp_to_cell[c.ref] = cell_id

    out: list[str] = []
    w = out.append
    ts = datetime.now()
    w(f"(edif {sanitize_edif_id(design_name)}")
    w("  (edifVersion 2 0 0)")
    w("  (edifLevel 0)")
    w("  (keywordMap (keywordLevel 0))")
    w("  (status")
    w("    (written")
    w(f"      (timeStamp {ts.year} {ts.month} {ts.day} "
      f"{ts.hour} {ts.minute} {ts.second})")
    w('      (author "Smash Electronics")')
    w('      (program "smash.export.edif" (version "1"))))')

    # Cell library
    w("  (library cell_lib")
    w("    (edifLevel 0)")
    w("    (technology (numberDefinition))")
    for cid, info in sorted(cells.items()):
        w(f"    (cell {cid}")
        w("      (cellType GENERIC)")
        w("      (view netlist_view")
        w("        (viewType SCHEMATIC)")
        w("        (interface")
        for pin in info["pins"]:
            pname = _named(f"P{pin.num}")
            w(f"          (port {pname} (direction {_dir(pin)}))")
        w("        )))")
    w("  )")

    # Design library
    w("  (library design_lib")
    w("    (edifLevel 0)")
    w("    (technology (numberDefinition))")
    w(f"    (cell {sanitize_edif_id(design_name)}")
    w("      (cellType GENERIC)")
    w("      (view netlist_view")
    w("        (viewType NETLIST)")
    w("        (interface)")
    w("        (contents")

    # Instances
    for c in sorted(components, key=lambda x: x.ref):
        cid = comp_to_cell[c.ref]
        w(f"          (instance {_named(c.ref)}")
        w(f"            (viewRef netlist_view "
          f"(cellRef {cid} (libraryRef cell_lib)))")
        prop_attrs = [
            ("VALUE",       getattr(c, "value",       None)),
            ("FOOTPRINT",   getattr(getattr(c, "footprint", None), "name", None)),
            ("MANF",        getattr(c, "manf",        None)),
            ("MANF_PN",     getattr(c, "manf_pn",     None)),
            ("DESCRIPTION", getattr(c, "description", None)),
            ("BOARD",       getattr(c, "board_tag",   None)),
            ("FAB_COUNTRY", getattr(c, "fab_country", None)),
        ]
        for prop, val in prop_attrs:
            if val:
                w(f"            (property {prop} (string {_quote(val)}))")
        cost = getattr(c, "price_1pc", None)
        if cost is not None:
            ccy = getattr(c, "currency", None) or "USD"
            w(f"            (property COST_{ccy} "
              f"(string {_quote(f'{cost:.2f}')}))")
        w("          )")

    # Nets
    n_nets = 0
    for net in nets_with_pins(design):
        n_nets += 1
        w(f"          (net {_named(net.name)}")
        w("            (joined")
        for ref, num in net_connections(net):
            pref = sanitize_edif_id(ref)
            pport = _named(f"P{num}")
            w(f"              (portRef {pport} (instanceRef {pref}))")
        w("            )")
        w("          )")
    w("        )")
    w("      )")
    w("    )")
    w("  )")

    # Top-level design statement — names the root cell.
    w(f"  (design {sanitize_edif_id(design_name)}")
    w(f"    (cellRef {sanitize_edif_id(design_name)} "
      f"(libraryRef design_lib)))")
    w(")")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(out))
        f.write("\n")

    return {"n_cells":     len(cells),
            "n_instances": len(components),
            "n_nets":      n_nets}
