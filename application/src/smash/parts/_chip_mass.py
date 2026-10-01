"""Datasheet-derived (or vendor-pool-estimated) per-package chip-mass
constants for the bend / spin / lateral solver.

The bend sim's spin and lateral-impact paths compute `F = m · ω² · r`
(or `F = m · g₀ · g`) per chip and divide by the joint shear area to
get τ. Without a populated `Chip.weight_g`, the sim falls back to a
flat 0.5 g default — fine for a BGA but 25–500× too heavy for a 0402
ceramic, which means the RPM envelope gets clipped by chips that
physically can't generate that force.

Centralising the mass numbers in ONE place lets parts factories
spread them across all chips with zero per-factory duplication. The
values come from manufacturer datasheets where listed (Vishay /
KEMET / Würth publish typical mass for most stock packages); for
the families that don't list, the value is a density-based estimate
(ceramic MLC ~5.5 g/cm³, tantalum slug ~5.5 g/cm³, polymer-tantalum
~3 g/cm³, epoxy-encapsulated IC ~1.7 g/cm³) cross-checked against
the published mass of an adjacent size in the same family.

Per-part overrides (datasheet-published exact mass for a specific
PN) go on the factory call itself (`weight_g=`), not in this table.
"""
from __future__ import annotations


# ── packaged ceramic passives (MLC R / C / L) ──────────────────────────
# Vishay CRCW (R) and KEMET C-Series (C X7R) both publish typical
# masses. Inductors track the same body weight at the smallest sizes
# (multilayer ceramic), then jump where the part is wound.

WEIGHT_G_PASSIVE = {
    # imperial codes — body L × W × H (mm) noted for sanity
    "0402":   0.0006,    # 1.0 × 0.5 × 0.5  — Vishay datasheet 0.5-0.7 mg
    "0603":   0.0020,    # 1.6 × 0.8 × 0.8  — Vishay datasheet 1.6-2.5 mg
    "0805":   0.0050,    # 2.0 × 1.25 × 1.45 — KEMET datasheet 4-6 mg
    "1206":   0.0100,    # 3.2 × 1.6 × 0.8   — Vishay datasheet 8-12 mg
    "1210":   0.0170,    # 3.2 × 2.5 × 0.8   — KEMET datasheet 15-20 mg
}

# Tantalum + polymer bulk caps (KEMET T491 / T528 publish mass per
# case code; mass = published typical for the thinnest variant of
# each case).
WEIGHT_G_TANTALUM_3528B = 0.030   # 3.5 × 2.8 × 1.10  case-B-12 thinnest variant
WEIGHT_G_TANTALUM_7343X = 0.060   # 7.3 × 4.3 × 1.40  case-X-15 polymer thinnest

# Würth WE-PD shielded power inductors (744043 series datasheet).
# 4848 body = 0.28 g (datasheet typical). Larger / smaller bodies
# scale roughly as L³ for shielded ferrite cores.
WEIGHT_G_INDUCTOR_WEPD_4848 = 0.280
WEIGHT_G_INDUCTOR_TDK_TMS20 = 0.007   # TMS201210ALM, 2.0×1.25×1.0 wirewound

# Discrete diodes / LEDs in 0603 / SOD-style bodies.
WEIGHT_G_LED_0603       = 0.0025      # Lite-On LTST-C190GKT class
WEIGHT_G_DIODE_SOD323   = 0.0080      # SOD-323: 1.7×1.25×0.95
WEIGHT_G_DIODE_SOD523   = 0.0030      # SOD-523: 1.2×0.8×0.7
WEIGHT_G_DIODE_DO214AC  = 0.130       # DO-214AC / SMA: 4.4×2.7×2.3, MBRS340 class
WEIGHT_G_DIODE_DO214AB  = 0.220       # DO-214AB / SMC: 6.6×3.5×2.4


# ── packaged semiconductors (epoxy IC body + leadframe) ─────────────────
# Body density ~1.7 g/cm³ for epoxy moulding; mass cross-checked
# against published TI / NXP / Microchip datasheet ZA tables for the
# common package codes.

WEIGHT_G_SOT = {
    "SOT-23":      0.012,    # 3-pad, 3.0 × 1.4 × 1.0
    "SOT-23-5":    0.013,    # 5-pad SOT-23, same body
    "SOT-23-6":    0.014,    # 6-pad SOT-23, same body
    "SOT-353":     0.005,    # SC-70-5, 2.0 × 1.25 × 0.95
    "SOT-363":     0.005,    # SC-70-6
    "SOT-563":     0.003,    # SC-89, 1.6 × 1.6 × 0.6
    "SOT-553":     0.003,
    "SOT-89":      0.045,    # 4.5 × 2.5 × 1.5
    "SOT-223":     0.080,    # 6.5 × 3.5 × 1.6
}

WEIGHT_G_QFN_BY_SIDE_MM = {
    # square QFN, side length in mm → mass in g. Cross-checked vs.
    # NXP LFCSP and TI VQFN datasheet ZA tables.
    2.0:  0.005,
    3.0:  0.018,
    4.0:  0.035,
    5.0:  0.055,
    6.0:  0.080,
    7.0:  0.110,
    8.0:  0.145,
    9.0:  0.185,
    10.0: 0.230,
}

WEIGHT_G_SO_BY_LEADS = {
    # SOIC / TSSOP / MSOP — rough mass by lead count, narrow body.
    # For wider SOIC (300-mil) the mass roughly doubles per pin count.
    8:  0.075,    # SOIC-8 narrow
    14: 0.130,
    16: 0.150,
    20: 0.200,
    28: 0.285,
}

# BGA / WLCSP / FBGA: substrate + silicon die + solder balls.
# Approximate density 2.0–2.5 g/cm³ for the body+substrate stack.
WEIGHT_G_BGA_BODY_DENSITY = 2.2   # g/cm³ — applied to size_mm × height


def weight_g_for_bga(size_mm: tuple, height_mm: float) -> float:
    """Estimate BGA / FBGA / WLCSP body mass from envelope (mm) using
    a typical 2.2 g/cm³ body+substrate density. Used by big-package
    factories (AWR2944 12 × 12 BGA ≈ 230 mg, MPU 10 × 10 ≈ 160 mg,
    DDR3 9 × 13 ≈ 150 mg)."""
    w, h = size_mm
    return WEIGHT_G_BGA_BODY_DENSITY * w * h * height_mm * 1e-3


def weight_g_for_qfn(size_mm: tuple) -> float:
    """Approximate QFN/LFCSP mass from square-side length, linearly
    interpolating the published-mass table above. Body height for
    standard QFN is 0.85–1.0 mm; this lookup assumes the standard
    height. Caller can override per-PN with the actual datasheet
    number when needed."""
    side = max(size_mm)
    keys = sorted(WEIGHT_G_QFN_BY_SIDE_MM)
    if side <= keys[0]:
        return WEIGHT_G_QFN_BY_SIDE_MM[keys[0]]
    if side >= keys[-1]:
        return WEIGHT_G_QFN_BY_SIDE_MM[keys[-1]]
    for lo, hi in zip(keys, keys[1:]):
        if lo <= side <= hi:
            t = (side - lo) / (hi - lo)
            return (WEIGHT_G_QFN_BY_SIDE_MM[lo] * (1 - t)
                    + WEIGHT_G_QFN_BY_SIDE_MM[hi] * t)
    return WEIGHT_G_QFN_BY_SIDE_MM[keys[-1]]   # unreachable, satisfies type


def weight_g_for_passive(package_class: str) -> float | None:
    """Stock-passive mass by IPC imperial size code (`0402`, `0603`,
    `0805`, `1206`, `1210`). Returns None for codes not in the table —
    caller falls back to its own estimate."""
    return WEIGHT_G_PASSIVE.get(package_class)
