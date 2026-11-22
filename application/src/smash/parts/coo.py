"""Country of origin from distributor data (2026-11-21).

`smash/data/coo_mouser.json` holds Mouser's per-part origin / assembly /
diffusion (wafer fab) countries from a Price & Availability bulk response.
`apply_coo(design)` writes them into each chip's `fab_country` after the
design is built, overriding hand-entered values (Mouser's data is the
authority; it reflects Mouser's CURRENT stock lot).
"""
from __future__ import annotations

import json
import pathlib

_FILE = pathlib.Path(__file__).resolve().parents[1] / "data" / "coo_mouser.json"


def load() -> dict:
    """{our MPN (as submitted) or Mouser's MPN: entry}."""
    try:
        parts = json.loads(_FILE.read_text())["parts"]
    except Exception:
        return {}
    out = {}
    for mpn, e in parts.items():
        out[mpn.upper()] = e
        if e.get("input"):
            out[e["input"].upper()] = e
    return out


def describe(e: dict) -> str:
    bits = [f"origin {e['origin']}" if e.get("origin") else None,
            f"assembly {e['assembly']}" if e.get("assembly") else None,
            f"wafer {e['diffusion']}" if e.get("diffusion") else None]
    return "; ".join(b for b in bits if b) + " (Mouser stock, 2026-11-21)"


def has_china(e: dict) -> bool:
    return any("china" in str(e.get(k) or "").lower() for k in ("origin", "assembly", "diffusion"))


def apply_coo(design) -> int:
    data, n = load(), 0
    for c in design.chips:
        e = data.get(str(c.manf_pn or "").upper())
        if e and (e.get("origin") or e.get("assembly") or e.get("diffusion")):
            c.fab_country = describe(e)
            n += 1
    return n
