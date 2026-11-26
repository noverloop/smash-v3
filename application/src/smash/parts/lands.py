"""Datasheet land patterns over the library-generator ones.

SamacSys / SnapMagic footprints are IPC "nominal" lands: pads longer and wider
than most manufacturers recommend. Extra copper costs routing room around the
part (and fan-out space on 0.10 / 0.10 rules) without a soldering benefit, and a
few generator lands are SMALLER than the datasheet (thermal pads, diode lands).
Each entry below sets a part's pads to its manufacturer's recommended land; the
part's pin positions stay where the datasheet puts them. Keyed by manf_pn and
applied by Design.add_chip, so every factory and every board gets the same land.
Courtyards are left as they are (grow-only clearance still applies).
"""
from __future__ import annotations

import dataclasses


def _set(fp, nums=None, *, size=None, x=None, y=None, shape=None, mask=None):
    """Resize / move pads. nums None = every pad. x / y: a callable
    (old coordinate) -> new coordinate, or None to keep."""
    out = []
    for p in fp.pads:
        if nums is None or p.num in nums:
            px, py = p.position_mm
            kw = {}
            if size is not None:
                kw["size_mm"] = tuple(size)
            if x is not None or y is not None:
                kw["position_mm"] = (x(px) if x else px, y(py) if y else py)
            if shape is not None:
                kw["shape"] = shape
            if mask is not None:                       # NSMD: mask opening = land + 2 × mask
                kw["solder_mask_expansion_mm"] = mask
            p = dataclasses.replace(p, **kw)
        out.append(p)
    fp.pads = out


def _sgn(v):
    return 1.0 if v > 0 else -1.0 if v < 0 else 0.0


def _rows_x(cx):
    """Pads in two rows on ±x: put each row's centre at ±cx."""
    return lambda x: _sgn(x) * cx


def _qfn_pins(fp, n_side, pitch, centre, pad_len, pad_w, ep=None, ep_num=None):
    """Square QFN: snap each perimeter pad to its exact pitch slot, centre it
    `centre` mm from the package centre, size pad_len x pad_w (long axis
    pointing out); optional square/rect exposed pad."""
    half = (n_side - 1) / 2 * pitch
    slots = [-half + i * pitch for i in range(n_side)]
    snap = lambda v: min(slots, key=lambda s: abs(s - v))
    out = []
    for p in fp.pads:
        x, y = p.position_mm
        if p.num == ep_num:
            if ep:
                p = dataclasses.replace(p, size_mm=tuple(ep))
        elif abs(x) > abs(y):                      # left / right rows
            p = dataclasses.replace(p, position_mm=(_sgn(x) * centre, snap(y)),
                                    size_mm=(pad_len, pad_w))
        else:                                      # top / bottom rows
            p = dataclasses.replace(p, position_mm=(snap(x), _sgn(y) * centre),
                                    size_mm=(pad_w, pad_len))
        out.append(p)
    fp.pads = out


# manf_pn -> (function(fp), datasheet reference)
LANDS = {
    "AWR1843ARBGALPQ1": (
        lambda fp: _set(fp, size=(0.40, 0.40), mask=0.05),
        "TI AWR1843AOP DS, ALP0180A land pattern example: 180× Ø0.4 NSMD (preferred), "
        "mask opening Ø0.5"),
    "STM32WBA55UGI7": (
        lambda fp: _set(fp, size=(0.30, 0.30), mask=0.05),
        "ST STM32WBA55 DS Table 102 UFBGA59 recommended PCB design rules: Dpad 0.300, "
        "Dsm 0.400 (NSMD)"),
    "STM32U545REI6Q": (
        lambda fp: _set(fp, size=(0.28, 0.28), mask=0.045),
        "ST STM32U545 DS p.286 Table 147 UFBGA64 example PCB design rules: Dpad 0.280, "
        "Dsm 0.370 (NSMD)"),
    "NX7002AK,215": (
        lambda fp: _set(fp, size=(0.70, 0.60), x=_rows_x(1.00)),
        "Nexperia NX7002AK DS Fig. 19 (sot023_fr): lands 0.6 × 0.7, rows 2.0 apart, pitch 1.9"),
    "TPS62822DLCR": (
        lambda fp: _set(fp, size=(0.60, 0.25), x=_rows_x(0.65)),
        "TI TPS62822 DS DLC0008B example board layout: 8× 0.6 × 0.25, rows 1.3 apart"),
    "MCP9808T-E/MC": (
        lambda fp: (_set(fp, [str(i) for i in range(1, 9)], size=(0.75, 0.26), x=_rows_x(1.45)),
                    _set(fp, ["9"], size=(1.75, 1.45))),
        "Microchip MCP9808 DS C04-2123B (MC 2×3 DFN): X1 ≤ 0.30, Y1 ≤ 0.75, C1 2.90, "
        "EP ≤ 1.45 × 1.75, pin–EP G ≥ 0.20"),
    "DSC1001CI1-027.0000": (
        lambda fp: _set(fp, size=(0.90, 0.90)),
        "Microchip DSC1001 DS, CDFN 3.2 × 2.5 recommended land: 0.9 × 0.9, 1.9 × 2.1 pitch"),
    "DSC1001CI5-032.0000T": (
        lambda fp: _set(fp, size=(0.90, 0.90)),
        "Microchip DSC1001 DS, CDFN 3.2 × 2.5 recommended land: 0.9 × 0.9, 1.9 × 2.1 pitch"),
    "SIT1533AI-H4-DCC-32.768E": (
        lambda fp: (_set(fp, ["1", "3"], size=(0.40, 1.40), x=_rows_x(0.80)),
                    _set(fp, ["2", "4"], size=(0.20, 0.40))),
        "SiTime SiT1533 DS p.10 'SiTime only' solder land (ends 0.4 × 1.4, outer 2.0; "
        "centre 0.2 × 0.4) — no crystal fits this footprint"),
    "LP5907MFX-2.8/NOPB": (
        lambda fp: _set(fp, size=(1.10, 0.60), x=_rows_x(1.30)),
        "TI LP5907 DS DBV0005A example board layout: 5× 1.1 × 0.6, rows 2.6 apart"),
    "LR2021IMLTRT": (
        lambda fp: _set(fp, ["33"], size=(3.70, 3.70)),
        "Semtech LR2021 DS Fig. 24-3 land pattern: EP 3.7 (pins already 0.30 × 0.80)"),
    "ADF4351BCPZ-RL7": (
        lambda fp: _qfn_pins(fp, 8, 0.50, 2.30, 0.50, 0.30, ep_num="33"),
        "ADI ADF4351 DS PCB design guidelines + CP-32-7: pad = lead + 0.1 L / + 0.05 W "
        "(0.30 × 0.50, centred on the lead at 2.30), exact 0.50 pitch; EP 3.25 kept"),
    "LTC3124EDHC#TRPBF": (
        lambda fp: (_set(fp, [str(i) for i in range(1, 17)], size=(0.65, 0.25), x=_rows_x(1.425)),
                    _set(fp, ["17"], size=(1.65, 4.40))),
        "ADI LTC3124 DS DHC16 recommended solder pad: 0.25 × 0.65, outer span 3.50, EP 1.65 × 4.40"),
    "TPS61175PWPR": (
        lambda fp: _set(fp, ["15"], size=(2.60, 2.59)),
        "TI TPS61175 DS PWP0014K land pattern example: thermal pad 2.60 × 2.59"),
    "PNS40010AERX": (
        lambda fp: _set(fp, size=(1.20, 1.20), x=_rows_x(1.40)),
        "Nexperia PNS40010AER DS §13 CFP3 reflow footprint: 1.2 × 1.2, pitch 2.8"),
    "UJ20-C-H-G-MSMT-1A-P16-TR-67": (
        lambda fp: _set(fp, ["SH1", "SH2", "SH3", "SH4"], size=(0.90, 1.60), shape="oval"),
        "Same Sky UJ20-C-H DS recommended PCB layout: shell slots 0.65 × 1.2 kept; pads "
        "0.8 → 0.9 mm wide so the plated slot keeps a 0.125 mm ring on every layer (fab "
        "minimum 0.10)"),
    "CX90B-16P": (
        lambda fp: _set(fp, ["SH1", "SH2"], size=(1.10, 2.60), shape="oval"),
        "Hirose CX90B-16P drawing EDC3-632698 recommended PCB layout: front shell posts "
        "R0.30 thru (0.6 × 2.0 slot) in R0.55 land (1.10 × 2.60); the rest of the land "
        "matches the CX90B-16P1 library footprint"),
    "PESD36VS1ULSYL": (
        lambda fp: _set(fp, size=(0.50, 0.70), x=_rows_x(0.40)),
        "Nexperia PESD36VS1UL DS Fig. 12 (SOD882BD): 0.5 × 0.7, gap 0.30, span 1.30"),
}


def apply_land(manf_pn: str | None, fp) -> bool:
    """Set `fp`'s pads to the datasheet land for `manf_pn` (idempotent)."""
    entry = LANDS.get(manf_pn or "")
    if entry is None or fp is None or getattr(fp, "_datasheet_land", False):
        return False
    fn, ref = entry
    fn(fp)
    fp.source = f"{fp.source or ''} — land per {ref}".lstrip(" —")
    fp._datasheet_land = True
    return True
