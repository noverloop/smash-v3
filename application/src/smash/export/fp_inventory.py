"""Footprint-inventory CSV writer + reader.

Generates a SamacSys / Component-Search-Engine download checklist for
the layout EE. Persists three manual columns across regenerations
(Status, Allegro_Equivalent, Notes) so user edits survive a rerun.

Workflow:
  1. `write_footprint_inventory(design, "parts_to_fetch.csv")` →
     emits the checklist
  2. EE opens the CSV in a spreadsheet
  3. Click each SamacSys_URL → download → land in `library/`
  4. Fill in Allegro_Equivalent with the library name SamacSys produced
  5. Re-run the writer → reads back the CSV, preserves the edits;
     write_allegro_netlist() picks up the mapping
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

from smash.state import Design
from smash.export._common import all_components, footprint_full


_FIELDS = [
    "KiCad_Footprint", "Used_By_N_Parts", "Example_Parts",
    "Example_Manf_PN", "SamacSys_URL",
    "Status", "Allegro_Equivalent", "Notes",
]


def write_footprint_inventory(design: Design, path: str | Path) -> dict:
    """Write the footprint-inventory CSV. Returns {n_footprints, n_mapped}."""
    by_fp: dict[str, dict] = {}
    for c in all_components(design):
        fp = footprint_full(c) or "UNDEFINED"
        info = by_fp.setdefault(fp, {"refs": [], "manf_pns": set()})
        info["refs"].append(c.ref)
        mpn = (getattr(c, "manf_pn", "") or "").strip()
        if mpn:
            info["manf_pns"].add(mpn)

    # Preserve manual columns from any existing file at the same path.
    existing = _read_existing(path)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        for fp, info in sorted(
            by_fp.items(), key=lambda kv: (-len(kv[1]["refs"]), kv[0])
        ):
            example_refs = ", ".join(sorted(info["refs"])[:3])
            example_mpn = (
                sorted(info["manf_pns"])[0] if info["manf_pns"] else ""
            )
            if example_mpn:
                url = f"https://componentsearchengine.com/part/model/{example_mpn}"
            else:
                fp_tail = fp.split(":")[-1] if ":" in fp else fp
                url = f"https://componentsearchengine.com/search/{fp_tail}"
            prior = existing.get(fp, {})
            w.writerow({
                "KiCad_Footprint":    fp,
                "Used_By_N_Parts":    len(info["refs"]),
                "Example_Parts":      example_refs,
                "Example_Manf_PN":    example_mpn,
                "SamacSys_URL":       url,
                "Status":             prior.get("Status", ""),
                "Allegro_Equivalent": prior.get("Allegro_Equivalent", ""),
                "Notes":              prior.get("Notes", ""),
            })
    n_mapped = sum(
        1 for fp in by_fp
        if existing.get(fp, {}).get("Allegro_Equivalent", "").strip()
    )
    return {"n_footprints": len(by_fp), "n_mapped": n_mapped}


def load_allegro_fp_map(path: str | Path) -> dict[str, str]:
    """Read `Allegro_Equivalent` mappings from a previously-written
    inventory CSV. Returns {KiCad_Footprint: Allegro_Equivalent} for
    non-empty entries. Returns an empty dict if the file is missing or
    has no mappings."""
    mapping: dict[str, str] = {}
    try:
        with open(path, "r", newline="") as f:
            for row in csv.DictReader(f):
                v = (row.get("Allegro_Equivalent", "") or "").strip()
                if v:
                    mapping[row["KiCad_Footprint"]] = v
    except (FileNotFoundError, KeyError):
        pass
    return mapping


def _read_existing(path: str | Path) -> dict[str, dict]:
    """Load the three manual columns from an existing CSV. Returns
    {KiCad_Footprint: {Status, Allegro_Equivalent, Notes}}."""
    existing: dict[str, dict] = {}
    try:
        with open(path, "r", newline="") as f:
            for row in csv.DictReader(f):
                key = row.get("KiCad_Footprint", "")
                if key:
                    existing[key] = {
                        "Status":             row.get("Status", ""),
                        "Allegro_Equivalent": row.get("Allegro_Equivalent", ""),
                        "Notes":              row.get("Notes", ""),
                    }
    except (FileNotFoundError, KeyError):
        pass
    return existing
