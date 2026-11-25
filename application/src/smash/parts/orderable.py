"""Orderable part numbers for generic passive placeholders (2026-11-22).

The passive factories name parts generically ("C0402 X7R 100nF",
"CRCW0402 10k 1% e3", "SQCSVA 8.2pF", "TBD 0402 C0G/NP0 0.5pF ..."). This
module resolves those to the orderable MPNs chosen in the BOM-sourcing
rounds (availability/decisions.csv), so the generated BOM is orderable as-is.
`apply_orderable(design)` rewrites `manf_pn` / `manf` in place and keeps the
placeholder in `note`. Run it BEFORE `apply_coo` (COO is keyed by MPN).
"""
from __future__ import annotations

import re

# accepted swaps for specific values (availability/decisions.csv)
_C0G_0402_MURATA = {0.5: "GJM1555C1HR50BB01D", 0.8: "GJM1555C1HR80BB01D", 1.0: "GJM1555C1H1R0BB01D",
                    1.1: "GJM1555C1H1R1BB01D", 1.2: "GJM1555C1H1R2BB01D", 5.1: "GJM1555C1H5R1BB01D"}
_X7R_0402_MURATA = {100e-9: "GRM155R71C104KA88D", 47e-9: "GRM155R71E473KA88D"}


def _ohms(v: str) -> float:
    m = re.match(r"([\d.]+)\s*([kKmM]?)", v)
    return float(m[1]) * {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3, "": 1}[m[2]]


def _rcode(o: float) -> str:
    if o < 100:
        return f"{o:.1f}".replace(".", "R").ljust(4, "0")[:4]
    for div, sfx in ((1e6, "M"), (1e3, "K"), (1, "R")):
        if o >= div:
            txt = f"{o / div:.3g}"
            if "." in txt:
                a, b = txt.split("."); code = a + sfx + b
            else:
                code = txt + sfx
            return code.ljust(4, "0")[:4] if sfx != "R" else (txt + "R")[:4]
    return ""


def _farads(v: str) -> float:
    m = re.match(r"([\d.]+)\s*([pnu])", v)
    return float(m[1]) * {"p": 1e-12, "n": 1e-9, "u": 1e-6}[m[2]]


def _capcode(f: float) -> str:
    pf, e = f * 1e12, 0
    while pf >= 100:
        pf /= 10; e += 1
    return f"{int(round(pf)):02d}{e}"


def _c0g_code(pf: float) -> tuple[str, str]:
    if pf < 10:
        return f"{pf:.1f}".replace(".", "R"), "B"
    return _capcode(pf * 1e-12), "J"


def resolve(mpn: str) -> tuple[str, str] | None:
    """(orderable MPN, manufacturer) for a generic placeholder, else None."""
    m = re.match(r"CRCW0402 ([\d.]+[kKM]?|[\d.]+m) 1% e3", mpn)
    if m:
        v = m[1]
        special = {"0": "CRCW04020000Z0ED", "10m": "WFCP0402R0100FE66", "200m": "RCWE0402R200FKEA"}
        return (special.get(v) or f"CRCW0402{_rcode(_ohms(v))}FKED"), "Vishay"
    m = re.match(r"CRCW0603 ([\d.]+[kKM]?) 1% e3", mpn)
    if m:
        return f"CRCW0603{_rcode(_ohms(m[1]))}FKEA", "Vishay"
    m = re.match(r"C0402 X7R ([\d.]+[pnu]F)", mpn)
    if m:
        f = _farads(m[1])
        for k, pn in _X7R_0402_MURATA.items():
            if abs(f - k) < k * 1e-3:
                return pn, "Murata"
        return f"C0402C{_capcode(f)}K3RACTU", "KEMET"
    m = re.match(r"C-Series MIL-PRF-32535 X7R 0603 ([\d.]+[pnu]F)", mpn)
    if m:
        code = _capcode(_farads(m[1]))
        volt = {"225": "8", "474": "3"}.get(code, "5")     # as verified in full-BOM round 13
        return f"C0603C{code}K{volt}RACTU", "KEMET"
    m = re.match(r"TBD 0402 C0G/NP0 ([\d.]+)pF", mpn)
    if m:
        pf = float(m[1])
        if pf in _C0G_0402_MURATA:
            return _C0G_0402_MURATA[pf], "Murata"
        code, tol = _c0g_code(pf)
        return f"04025A{code}{tol}AT2A", "Kyocera AVX"
    if mpn.startswith("TBD 0402 C0G/NP0 1nF"):
        return "C0402C102J3GACTU", "KEMET"
    if mpn.startswith("TBD 0402 X5R 2.2uF"):
        return "C0402C225M9PACTU", "KEMET"
    m = re.match(r"SQCSVA ([\d.]+)pF", mpn)          # AVX SQCS is obsolete → KEMET C0G 0603
    if m:
        return f"C0603C{_kemet_c0g(float(m[1]))}5GACTU", "KEMET"
    m = re.match(r"WE-KI 0402 ([\d.]+)nH", mpn)
    if m:
        nh = float(m[1])
        return (f"7447650{int(round(nh * 10)):02d}A" if nh < 10 else f"7447651{int(round(nh)):02d}A"), "Würth Elektronik"
    if mpn.startswith("T491T 22uF"):
        return "T491T226K010AT", "KEMET"
    return None


def _kemet_c0g(pf: float) -> str:
    """KEMET C0603C…GAC capacitance+tolerance code: 8.2 pF → 829C, 10 pF → 100J."""
    if pf < 10:
        mant = int(round(pf * 10))            # 8.2 → 82
        return f"{mant}9C"                     # KEMET: two digits + '9' (×0.1 pF), C = ±0.25 pF
    return f"{_capcode(pf * 1e-12)}J"


def apply_orderable(design) -> int:
    """Rewrite generic passive placeholders to orderable MPNs. Returns the count."""
    n = 0
    for c in design.chips:
        r = resolve(str(c.manf_pn or ""))
        if r:
            placeholder = c.manf_pn
            c.manf_pn, c.manf = r
            c.note = (c.note or "") + f"\n\n[orderable] placeholder '{placeholder}' → {r[0]} ({r[1]})."
            n += 1
    return n
