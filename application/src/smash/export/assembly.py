"""Assembly outputs: placement list (CPL) + assembly BOM from one .kicad_pcb.

Both files are read from the board's own footprints, so their designators
match each other and the silkscreen by construction (the board's references,
e.g. U_MPU1 — not the design refs). Only fitted parts with an MPN are listed:
fiducials, test points, castellations, fixture pins and other board-only
footprints carry no MPN, and not-fitted (dnp) parts are left out.

  <stem>_cpl.csv           Designator, Mid X, Mid Y, Rotation, Layer  (mm, deg)
  <stem>_bom_assembly.csv  Designator (all refs), Quantity, MPN, Manufacturer,
                           Value, Footprint, Description

Coordinates are KiCad's board coordinates (Y up, as kicad-cli writes pos files);
the assembler aligns on the fiducials.
"""
from __future__ import annotations

import csv
import pathlib
import re
import subprocess
import tempfile

_FP_SPLIT = re.compile(r"\n\t\(footprint ")


def _prop(block: str, key: str) -> str:
    m = re.search(rf'\(property "{key}" "([^"]*)"', block)
    return m.group(1) if m else ""


def fitted_parts(pcb_text: str) -> dict:
    """{reference: dict(mpn, manufacturer, value, footprint, description)} for
    fitted footprints that carry an MPN."""
    out = {}
    for blk in _FP_SPLIT.split(pcb_text)[1:]:
        ref = _prop(blk, "Reference")
        attr = re.search(r"\(attr ([^)]*)\)", blk)
        flags = set(attr.group(1).split()) if attr else set()
        if not ref or flags & {"dnp", "exclude_from_bom", "board_only"}:
            continue
        mpn = _prop(blk, "MPN")
        if not mpn:
            continue
        out[ref] = dict(mpn=mpn, manufacturer=_prop(blk, "Manufacturer"), value=_prop(blk, "Value"),
                        footprint=blk.split('"')[1], description=_prop(blk, "Description"))
    return out


def write_assembly(pcb_path, out_dir, kicad_cli) -> dict:
    """Write <stem>_cpl.csv and <stem>_bom_assembly.csv into out_dir."""
    pcb_path, out_dir = pathlib.Path(pcb_path), pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = fitted_parts(pcb_path.read_text())
    with tempfile.TemporaryDirectory() as td:
        pos = pathlib.Path(td) / "pos.csv"
        subprocess.run([str(kicad_cli), "pcb", "export", "pos", "--format", "csv", "--units", "mm",
                        "--side", "both", "--exclude-dnp", "-o", str(pos), str(pcb_path)],
                       check=True, capture_output=True)
        rows = list(csv.DictReader(pos.open()))
    stem = pcb_path.stem
    cpl = out_dir / f"{stem}_cpl.csv"
    placed = set()
    with cpl.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Rotation", "Layer"])
        for r in rows:
            if r["Ref"] in parts:
                w.writerow([r["Ref"], r["PosX"], r["PosY"], r["Rot"], r["Side"]])
                placed.add(r["Ref"])
    groups: dict = {}
    for ref in sorted(placed):
        p = parts[ref]
        groups.setdefault((p["mpn"], p["manufacturer"]), {**p, "refs": []})["refs"].append(ref)
    bom = out_dir / f"{stem}_bom_assembly.csv"
    with bom.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Quantity", "MPN", "Manufacturer", "Value", "Footprint", "Description"])
        for (mpn, man), g in groups.items():
            w.writerow([" ".join(g["refs"]), len(g["refs"]), mpn, man, g["value"], g["footprint"],
                        g["description"]])
    missing = sorted(set(parts) - placed)          # fitted with MPN but not in the pos file
    return {"cpl": cpl, "bom": bom, "lines": len(groups), "parts": len(placed), "missing": missing}
