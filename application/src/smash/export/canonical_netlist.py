"""Canonical netlist — a tiny JSON projection of a Design's netlist.

The goal: an output format both `smash.export.canonical_netlist.write()`
and the SKiDL-side equivalent block in `system.py` can emit such that
a byte-diff confirms "same parts, same connectivity." No SKiDL-flavour
noise (tstamps, libsource, fields, pintype, description prose).

Shape:

    {
      "components": [
        {"ref": "...", "manf_pn": "...", "footprint": "...", "board": "..."},
        ...
      ],
      "nets": [
        {"name": "<primary>",
         "aliases": ["<other names>", ...],
         "nodes": [["ref", "pin"], ...]},
        ...
      ]
    }

Canonical rules:
  - components sorted by (board, ref)
  - each net's primary name = lexicographically first of {name, *aliases}
    so the choice of primary doesn't depend on merge order
  - aliases sorted lexicographically (excluding the primary)
  - nets list sorted by primary name
  - each net's node list sorted by (ref, pin)
  - JSON written with indent=2 + key/value order controlled explicitly
"""
from __future__ import annotations

import json
from pathlib import Path

from smash.state import Design
from smash.export._common import (
    all_components,
    nets_with_pins,
    net_connections,
    footprint_full,
)


def _canonical_footprint(component) -> str | None:
    """Footprint string for diff against SKiDL's `Net.footprint` output —
    always `library:name`. Stock KiCad footprints already store the
    library prefix; project-managed footprints just store the bare
    name, so prepend the project `footprints` library."""
    name = footprint_full(component)
    if not name:
        return None
    return name if ":" in name else f"footprints:{name}"


def write_canonical_netlist(design: Design, path: str | Path) -> dict:
    """Write a canonical-netlist JSON for `design`. Returns a summary
    dict with `{n_parts, n_nets}`."""
    components = [
        {
            "ref":       c.ref,
            "manf_pn":   (getattr(c, "manf_pn", "") or "") or None,
            "footprint": _canonical_footprint(c),
            "board":     (getattr(c, "board_tag", "") or "") or None,
        }
        for c in all_components(design)
    ]

    nets_out: list[dict] = []
    for n in nets_with_pins(design):
        all_names = sorted({n.name, *n.aliases})
        primary, *aliases = all_names
        nets_out.append({
            "name":    primary,
            "aliases": aliases,
            "nodes":   [[ref, pin] for ref, pin in net_connections(n)],
        })
    # Sort by primary name for stable diffs.
    nets_out.sort(key=lambda r: r["name"])

    payload = {
        "components": components,
        "nets": nets_out,
    }

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write("\n")

    return {"n_parts": len(components), "n_nets": len(nets_out)}
