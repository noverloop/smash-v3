"""LDO (low-dropout linear regulator) factories.

Every value transcribed from the per-part ground-truth artifacts in
`parts/sources/<PN>/`. See each factory's docstring for source citation.
"""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


# ═════════════════════════════════════════════════════════════════════════
# STMicroelectronics LDL112 family — 1.2 A LDO, DFN6 (3x3), fixed Vout
#
# A single datasheet (DS10321 Rev 3, Feb 2019) covers the whole LDL112
# family. We expose one factory per concrete orderable part number; the
# private `_ldl112_dfn6_3x3_base()` helper builds the shared metadata.
#
# Variants in the DFN6 (3x3) "PV" series (datasheet p20 Table 10):
#   LDL112PV18R = 1.8 V fixed
#   LDL112PV33R = 3.3 V fixed
#   LDL112PUxxR = DFN6 (2x2) variants  — different package, separate
#                                        factories when needed
#   LDL112DxxR  = SO8-batwing variants — same
#
# Ground-truth lives in `parts/sources/LDL112PV33R/` and
# `parts/sources/LDL112PV18R/` (both fully populated).
# ═════════════════════════════════════════════════════════════════════════

_LDL112_NOTE_TEMPLATE = """\
Datasheet extras (STMicroelectronics LDL112, DS10321 Rev 3, Feb 2019,
shared across all family variants) — fields not yet promoted to schema.

Identity:
  Family : LDL112 (1.2 A low quiescent current LDO with reverse
                   current protection)
  Variant: {variant_descr}

Features (p1):
  - VIN range: 1.6 V to 5.5 V
  - Very low dropout: 300 mV typ at 1 A load
  - Low Iq: 35 µA typ at no-load, 1 µA max in off mode
  - Vout accuracy ±2.0 % at 25 °C
  - 1.2 A guaranteed output current
  - Compatible with ceramic Cout = 1 µF
  - Internal current and thermal limit
  - Reverse current protection
  - Output discharge function (optional)

Absolute Max Ratings (p5 Table 2):
  VIN  : -0.3 V to 7 V
  VOUT : -0.3 V to VIN + 0.3 V
  VEN  : -0.3 V to VIN + 0.3 V
  VADJ : 2 V
  IOUT : internally limited
  PD   : internally limited
  TSTG : -65 to +150 °C
  TOP  : -40 to +125 °C (operating junction temperature)

Thermal data (p5 Table 3, DFN6 (3x3) package):
  R_thJA : 55 °C/W  (stored in rth_ja_cw)
  R_thJC : 10 °C/W  (stored in rth_jc_cw)

Electrical (p6 Table 4 — fixed version, T_J=25 °C):
  VOUT accuracy : ±2.0 % @ T_J=25 °C
                  ±3.0 % over -40 to +125 °C
  Static line regulation : 0.05 %/V typ, 0.1 %/V max
  Static load regulation : 15 mV typ, 30 mV max (0 mA → 1.2 A)
  VDROP : 300 mV typ @ I_OUT=1 A, VOUT=3.3 V
          350 mV typ / 600 mV max @ I_OUT=1.2 A
  eN output noise : 135 µVRMS typ (10 Hz-100 kHz, IOUT=10 mA, VOUT=3.3V)
  SVR supply rejection : 57 dB typ (1 kHz, 200 mV ripple, IOUT=10 mA)
  IQ quiescent : 35 µA typ / 70 µA max @ I_OUT=0
                 250 µA typ / 400 µA max @ I_OUT=1.2 A
  IQ in off mode : 0.1 µA typ / 1 µA max (VEN=GND)
  ISC short-circuit current : 1.4 A min / 2 A typ (RL=0, VIN>2.1 V)
  VEN logic low  : 0.35 V max
  VEN logic high : 1.4 V min
  IEN input current : 100 nA max (VEN=VIN)
  TSHDN thermal shutdown : 165 °C typ, 20 °C hysteresis
  COUT : 1 µF min, 10 µF max (ceramic, see p10 Section 7)

Mechanical — DFN6 (3x3) package (p14 Table 6):
  A   : 0.80 min / 1.00 max  (height)
  A1  : 0 min / 0.02 typ / 0.05 max  (standoff)
  A3  : 0.20 typ  (lead height of nailhead)
  b   : 0.23 min / 0.45 max  (lead width)
  D   : 2.90 min / 3.00 typ / 3.10 max  (length)
  D2  : 2.23 min / 2.50 max  (exposed pad length)
  E   : 2.90 min / 3.00 typ / 3.10 max  (width)
  E2  : 1.50 min / 1.75 max  (exposed pad width)
  e   : 0.95 typ  (lead pitch)
  L   : 0.30 min / 0.40 typ / 0.50 max  (lead length)

Pin layout (p3 Table 1) — fixed version uses pin 3 as NC; the
adjustable version uses pin 3 as ADJ. SamacSys-generated symbols vary
in how this is labeled across PV variants; we transcribe each
symbol's actual pin-3 name as the canonical Pin.name (see factory).

Order codes (datasheet p20 Table 10):
{order_codes}

Qualification: NOT explicitly tagged in datasheet (consumer / industrial-
grade per TOP=-40..+125 °C). RoHS / Pb-free compliance: NOT explicitly
stated on the datasheet front page (but standard for ST commercial).

Mechanical (NOT stated in datasheet):
  body_material, lead_material, weight_g, density_g_cm3, cte_ppm_k,
  fab_country — NOT IN DATASHEET; needs supplier traceability.

Distributor links (from SamacSys metadata, snapshot 2017+):
  datasheet URL : https://www.st.com/resource/en/datasheet/ldl112.pdf
  Mouser PN     : {mouser_pn}
  Mouser URL    : see SamacSys metadata
  Arrow PN      : {arrow_pn}
"""


def _ldl112pv_dfn6_3x3_footprint(stp_path: str) -> Footprint:
    """DFN6 (3x3) footprint from SamacSys-generated
    SON95P300X300X100-7N-D.kicad_mod (identical between PV33R and PV18R
    archives — the SamacSys archive bundles the same footprint with both
    parts).

    Pads verbatim from the .kicad_mod:
      pad 1-3 (left column) :  x=-1.50 mm, y ∈ {-0.95, 0, +0.95}, 0.4×0.8 mm
      pad 4-6 (right column):  x=+1.50 mm, y ∈ {+0.95, 0, -0.95}, 0.4×0.8 mm
      pad 7 (exposed pad)   :  (0, 0), 1.75 × 2.5 mm
    Pin numbering goes 1→6 counter-clockwise starting at top-left,
    matching the datasheet pin assignment (p3 Figure 3).
    """
    return Footprint(
        name="SON95P300X300X100-7N-D",
        package_class="DFN-6",
        pads=[
            Pad(num="1", position_mm=(-1.5, 0.95),
                size_mm=(0.8, 0.4), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.5, 0.0),
                size_mm=(0.8, 0.4), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-1.5, -0.95),
                size_mm=(0.8, 0.4), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(1.5, -0.95),
                size_mm=(0.8, 0.4), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(1.5, 0.0),
                size_mm=(0.8, 0.4), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=(1.5, 0.95),
                size_mm=(0.8, 0.4), shape="rect", layer="F.Cu"),
            # Exposed thermal pad — must be soldered to GND for thermal
            # spec (datasheet p3 Table 1).
            Pad(num="7", position_mm=(0.0, 0.0),
                size_mm=(1.75, 2.5), shape="rect", layer="F.Cu"),
        ],
        body_outline=[
            (-1.5, -1.5), (+1.5, -1.5),
            (+1.5, +1.5), (-1.5, +1.5),
        ],
        courtyard=[
            (-2.125, -1.8), (+2.125, -1.8),
            (+2.125, +1.8), (-2.125, +1.8),
        ],
        pitch_mm=0.95,                # `e` typ
        size_mm=(3.0, 3.0),           # D × E nominal
        height_mm=1.00,               # A max
        model_3d_path=stp_path,
        source="samacsys",
        note=(
            "SamacSys DFN6 (3x3) footprint. Exposed pad (pin 7) MUST "
            "be soldered to GND for thermal spec (datasheet p3 Table 1)."
        ),
    )


def _ldl112pv_base(
    *,
    manf_pn: str,
    vout_v: float,
    pin3_name: str,
    pin5_name: str,
    description: str,
    datasheet_path: str,
    stp_path: str,
    mouser_pn: str,
    arrow_pn: str,
    variant_descr: str,
) -> dict:
    """Build the keyword-arg dict for one LDL112PVxxR variant. Caller
    feeds it into design.add_chip(...).
    """
    note = _LDL112_NOTE_TEMPLATE.format(
        variant_descr=variant_descr,
        order_codes=(
            "  LDL112PV18R (DFN6 3x3, 1.8 V)\n"
            "  LDL112PV33R (DFN6 3x3, 3.3 V)\n"
            "  LDL112PU18R (DFN6 2x2, 1.8 V)\n"
            "  LDL112PU33R (DFN6 2x2, 3.3 V)\n"
            "  LDL112D18R  (SO8-batwing, 1.8 V)\n"
            "  LDL112D33R  (SO8-batwing, 3.3 V)"
        ),
        mouser_pn=mouser_pn,
        arrow_pn=arrow_pn,
    )
    return dict(
        manf="STMicroelectronics",
        manf_pn=manf_pn,
        canonical_id=canonical_id(manf_pn),
        name=manf_pn,
        value=manf_pn,
        description=description,
        datasheet=datasheet_path,
        fab_country=None,
        currency=None,
        price_1pc=None,
        price_20kpc=None,
        weight_g=None,
        standards=[],                       # not stated on datasheet
        eccn=None,
        itar=None,
        package="DFN-6 (3x3)",
        size_mm=(3.0, 3.0),
        height_mm=1.00,
        # Operating junction temperature range per datasheet p5 Table 2:
        # TOP = -40 to +125 °C. Storage = -65 to +150 °C; we use TOP.
        temp_range_c=(-40, 125),
        body_material=None,
        lead_material=None,
        # Electrical / regulator characteristics
        voltage_rating_v=7.0,               # VIN absolute max (p5 Table 2)
        vcc_nominal_v=vout_v,               # the regulated output
        i_rms_a=1.2,                        # guaranteed I_OUT
        power_rating_w=None,                # "internally limited" (p5)
        # Thermal (DFN6 3x3 — DS10321 Rev 3 Feb 2019 p5 Table 3)
        # Iq = 35 µA typ no-load, 250 µA typ @ 1.2A load (DS §5 p4).
        # Active power dissipation = (V_IN - V_OUT) × I_OUT + I_q × V_IN.
        # Smash use cases: PV33R powers AR0234 (~0.4 W load, Vin ≈
        # 3.7V battery, drop ≈ 0.4V → P_diss ≈ 0.05 W); PV18R powers
        # IWR1843 1.8V rail (Vin = 3.3V, drop = 1.5V, Iout up to ~0.5A
        # → P_diss up to 0.75 W). We choose p_active for the lighter
        # PV33R/AR0234 case, p_max for the heavier PV18R/IWR case —
        # both per-orderable factories share this base.
        p_active_w=0.05,                    # (Vin-Vout)*Iout typical, AR0234 use case
        p_max_w=0.75,                       # (Vin-Vout)*Iout worst, IWR 1.8V rail @ 0.5A
        rth_jc_cw=10.0,
        rth_ja_cw=55.0,
        tj_max_c=125.0,
        # Pins — per pinmap.txt for the specific variant (matches the
        # SamacSys-generated kicad_sym). Pin 3's name differs between
        # PV18R (NC_1) and PV33R (ADJ) because of SamacSys variant
        # quirks — we keep each verbatim.
        pins=[
            Pin(num="1", name="EN",       type="input"),
            Pin(num="2", name="GND",      type="ground"),
            # Per ST DS10321 (LDL112 rev 3, Feb 2019) Figure 3 pin
            # diagram (FIXED version): pin 3 is labeled "NC".
            # SamacSys's family symbol carries the adjustable-variant
            # label ("ADJ" on PV33R, "NC_1" on PV18R); we keep the
            # SamacSys-flavored name as an alias so the symbol-imported
            # KiCad schematic still resolves it, but the primary name
            # follows the datasheet.
            Pin(num="3", name="NC", aliases=[pin3_name], type="nc"),
            Pin(num="4", name="VOUT",     type="power"),
            # Pin 5 is "NC" per datasheet; SamacSys names it NC, NC_2
            # depending on variant — carry as alias.
            Pin(num="5", name="NC", aliases=[pin5_name] if pin5_name != "NC" else [],
                type="nc"),
            Pin(num="6", name="VIN",      type="power"),
            # Exposed pad — pin 7 per the SamacSys symbol. MUST be GND.
            Pin(num="7", name="EP", aliases=["ExposedPad"], type="ground"),
        ],
        footprint=_ldl112pv_dfn6_3x3_footprint(stp_path),
        note=note,
    )


def add_ldl112pv33r(design, ref: str, **overrides) -> Chip:
    """STMicroelectronics LDL112PV33R — 1.2 A LDO, V_OUT=3.3 V fixed,
    DFN6 (3x3) package.

    Ground-truth in `parts/sources/LDL112PV33R/`.

    Pin 3 is labeled "ADJ" in this variant's SamacSys symbol even
    though the PV33R is a FIXED-output device (the ADJ pin is
    non-functional on the fixed variants per datasheet p3 Table 1).
    Treat pin 3 as no-connect in this variant.
    """
    fields = _ldl112pv_base(
        manf_pn="LDL112PV33R",
        vout_v=3.3,
        pin3_name="ADJ",            # per SamacSys symbol (idiosyncratic)
        pin5_name="NC",
        description=(
            "LDO 1.2 A, V_OUT=3.3 V fixed, VIN=1.6..5.5 V, dropout "
            "300 mV typ @ 1 A, DFN6 (3x3)"
        ),
        datasheet_path="application/src/smash/parts/sources/LDL112PV33R/LDL112.pdf",
        stp_path="application/src/smash/parts/sources/LDL112PV33R/LDL112PV33R.stp",
        mouser_pn="511-LDL112PV33R",
        arrow_pn="LDL112PV33R",
        variant_descr="LDL112PV33R: DFN6 (3x3), V_OUT=3.3 V fixed",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_ldl112pv18r(design, ref: str, **overrides) -> Chip:
    """STMicroelectronics LDL112PV18R — 1.2 A LDO, V_OUT=1.8 V fixed,
    DFN6 (3x3) package.

    Ground-truth in `parts/sources/LDL112PV18R/`.

    SamacSys symbol labels pin 3 as "NC_1" and pin 5 as "NC_2"
    (no-connects on the fixed version per datasheet p3 Table 1).
    """
    fields = _ldl112pv_base(
        manf_pn="LDL112PV18R",
        vout_v=1.8,
        pin3_name="NC_1",
        pin5_name="NC_2",
        description=(
            "LDO 1.2 A, V_OUT=1.8 V fixed, VIN=1.6..5.5 V, dropout "
            "300 mV typ @ 1 A, DFN6 (3x3)"
        ),
        datasheet_path="application/src/smash/parts/sources/LDL112PV18R/LDL112.pdf",
        stp_path="application/src/smash/parts/sources/LDL112PV18R/LDL112PV18R.stp",
        mouser_pn="511-LDL112PV18R",
        arrow_pn="LDL112PV18R",
        variant_descr="LDL112PV18R: DFN6 (3x3), V_OUT=1.8 V fixed",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# STMicroelectronics STLQ020 family — 200 mA ultra-low-Iq LDO
#
# STLQ020J30R = Flip-Chip 4 (DSBGA-4) package, V_OUT=3.0 V fixed.
#
# >>> Note on order code: an earlier version of this codebase referenced
#     "STLQ020M33R", which is NOT a valid ST order code. Per the
#     datasheet (DS12072 Rev 4) Table 9, the valid order codes are
#     STLQ020{C18R,C22R,C28R,C33R} (SOT323-5L),
#     STLQ020{J18R,J25R,J30R,J33R} (Flip-Chip 4), and
#     STLQ020{PU19R,PU28R,PU33R,PUR} (DFN6-2x2). When the design needs
#     3.3 V instead of 3.0 V, switch to STLQ020J33R (same package, same
#     spec, different trim) or STLQ020C33R (SOT323-5L).
#
# Ground-truth lives in `parts/sources/STLQ020J30R/`.
# ═════════════════════════════════════════════════════════════════════════

_STLQ020J30R_NOTE = """\
Datasheet extras (STMicroelectronics STLQ020, DS12072 Rev 4) — fields
not yet promoted to schema.

Identity:
  Family   : STLQ020 (200 mA ultra-low-Iq LDO)
  Variant  : STLQ020J30R = Flip-Chip 4 (DSBGA-4), V_OUT=3.0 V fixed
  Marking  : "M7" (datasheet p20 Table 9)
  Packing  : Tape and reel

>>> Order-code sanity check: earlier project notes referenced
    "STLQ020M33R", which is NOT a valid ST order code. Per datasheet
    p20 Table 9, the valid 3.3 V variants are:
      STLQ020C33R  (SOT323-5L)
      STLQ020J33R  (Flip-Chip 4)
      STLQ020PU33R (DFN6-2x2)
    The "M" prefix does not exist in the STLQ020 order code system.
    If the design rail truly needs 3.3 V instead of 3.0 V, switch to
    STLQ020J33R (same package, same spec, different trim).

Features (p1):
  - VIN range: 1.5 V to 5.5 V (operating 2 to 5.5 V per p6 Table 4)
  - Vout range available: 0.8 V to 4.5 V, 50 mV step, plus adjustable
  - Vout accuracy 2 % at room temperature, 3 % across temperature
  - Iq typ 300 nA at IOUT=0; 100 µA at IOUT=0.2 A
  - Packages: DFN6-2x2, SOT323-5L, Flip-Chip 4

Absolute Max Ratings (p5 Table 2):
  VIN   : -0.3 V to 7 V
  VOUT  : -0.3 V to VIN + 0.3 V
  VADJ  : -0.3 V to 2 V
  EN    : -0.3 V to VIN + 0.3 V
  ESD   : CDM ±500 V; HBM ±2000 V
  TJ-OP : -40 to +125 °C
  TJ-MAX: 150 °C
  TSTG  : -55 to +150 °C

Thermal data (p5 Table 3, Flip-Chip 4):
  R_thJC : NOT STATED for Flip-Chip 4 (only DFN6/SOT323 listed)
  R_thJA : 180 °C/W   (stored in rth_ja_cw)

Electrical (p6 Table 4, fixed version, T_J=25 °C):
  VIN operating  : 2 V min / 5.5 V max
  VOUT accuracy  : ±2 % @ T_J=25 °C; ±3 % across temp
  Static line    : 0.005 %/V typ, 0.05 %/V max
  Static load    : 0.0015 %/mA typ, 0.005 %/mA max
  VDROP          : 160 mV typ @ VOUT=2.5V, IOUT=200 mA
                   15 mV typ @ VOUT=2.5V, IOUT=20 mA
  Output noise   : 135 µVRMS/VOUT, 10 Hz-100 kHz
  SVR @ 100 Hz   : 52 dB typ
  SVR @ 1 kHz    : 35 dB typ
  SVR @ 10 kHz   : 45 dB typ
  Iq @ IOUT=0    : 300 nA typ / 1000 nA max
  Iq @ IOUT=0.2A : 100 µA typ / 150 µA max
  Shutdown Iq    : 5 nA typ / 50 nA max (VEN=0)
  ISC            : 380 mA typ (VOUT=0)
  RLOW discharge : 100 Ω typ (VEN=0, on specific version only)
  VEN logic low  : 0.4 V max
  VEN logic high : 1.2 V min
  IEN            : 1 nA typ (VEN=VIN)
  TSHDN          : 160 °C typ, 20 °C hysteresis

Mechanical — Flip-Chip 4 (DSBGA-4) package (p17 Table 7):
  Body  : 0.77 × 0.77 × 0.61 mm (W × L × H, max)
  Pitch : 0.40 mm (BGA pitch)
  Balls : 0.208 mm Ø (per SamacSys .kicad_mod)

Pin layout (p3 Table 1, Flip-Chip 4):
  A1 = VIN, A2 = VOUT, B1 = EN, B2 = GND
  (No ADJ pin on Flip-Chip 4 variants — only DFN6/SOT323 expose ADJ)

Qualification: ESD CDM ±500 V, HBM ±2000 V (p5). Operating junction
-40 to +125 °C — industrial-grade range. RoHS/Pb-free compliance NOT
explicitly stated on datasheet (assume standard ST commercial).

Mechanical (NOT stated in datasheet):
  body_material (DSBGA is usually epoxy underfill), lead_material
  (SAC305 SnAgCu solder balls typical), weight_g, density_g_cm3,
  cte_ppm_k, fab_country — needs supplier traceability.

Distributor links (from SamacSys metadata):
  datasheet URL : https://www.st.com/resource/en/datasheet/stlq020.pdf
  Mouser PN     : 511-STLQ020J30R
  Mouser URL    : https://www.mouser.co.uk/ProductDetail/STMicroelectronics/\
STLQ020J30R?qs=u4fy%2FsgLU9MJfI0qLS4mGA%3D%3D
  Arrow PN      : STLQ020J30R
"""


def _stlq020j30r_footprint() -> Footprint:
    """Flip-Chip 4 (DSBGA-4) footprint per SamacSys-generated
    `BGA4C40P2X2_77X77X61.kicad_mod`.

    Pads (BGA naming A1/A2/B1/B2):
      A1 (VIN)  : (-0.20, -0.20) mm, 0.208 mm Ø circle
      A2 (VOUT) : (+0.20, -0.20) mm, 0.208 mm Ø circle
      B1 (EN)   : (-0.20, +0.20) mm, 0.208 mm Ø circle
      B2 (GND)  : (+0.20, +0.20) mm, 0.208 mm Ø circle
    Pitch 0.40 mm both axes. Body 0.77 × 0.77 × 0.61 mm.
    """
    return Footprint(
        name="BGA4C40P2X2_77X77X61",
        package_class="DSBGA",
        pads=[
            Pad(num="A1", position_mm=(-0.2, 0.2),
                size_mm=(0.208, 0.208), shape="round", layer="F.Cu"),
            Pad(num="A2", position_mm=(0.2, 0.2),
                size_mm=(0.208, 0.208), shape="round", layer="F.Cu"),
            Pad(num="B1", position_mm=(-0.2, -0.2),
                size_mm=(0.208, 0.208), shape="round", layer="F.Cu"),
            Pad(num="B2", position_mm=(0.2, -0.2),
                size_mm=(0.208, 0.208), shape="round", layer="F.Cu"),
        ],
        body_outline=[
            (-0.386, -0.386), (+0.387, -0.386),
            (+0.387, +0.387), (-0.386, +0.387),
        ],
        courtyard=[
            (-1.402, -1.402), (+1.401, -1.402),
            (+1.401, +1.401), (-1.402, +1.401),
        ],
        pitch_mm=0.40,
        size_mm=(0.77, 0.77),
        height_mm=0.61,
        model_3d_path="application/src/smash/parts/sources/STLQ020J30R/STLQ020J30R.stp",
        source="samacsys",
        note=(
            "SamacSys Flip-Chip 4 footprint, IPC name "
            "BGA4C40P2X2_77X77X61 (4 balls, 0.40 mm pitch, 2×2 array, "
            "0.77 × 0.77 × 0.61 mm body)."
        ),
    )


def add_stlq020j30r(design, ref: str, **overrides) -> Chip:
    """STMicroelectronics STLQ020J30R — 200 mA ultra-low-Iq LDO,
    V_OUT=3.0 V fixed, Flip-Chip 4 (DSBGA-4) package.

    Quiescent current 300 nA typ at no-load — picked for always-on
    monitoring rails where keeping the device alive between long
    sleeps dominates battery budget.

    Ground-truth in `parts/sources/STLQ020J30R/`.
    """
    fields = dict(
        manf="STMicroelectronics",
        manf_pn="STLQ020J30R",
        canonical_id="stlq020j30r",
        name="STLQ020J30R",
        value="STLQ020J30R",
        description=(
            "LDO 200 mA, V_OUT=3.0 V fixed, VIN=2..5.5 V, "
            "Iq=300 nA typ no-load, Flip-Chip 4 (DSBGA-4)"
        ),
        datasheet="application/src/smash/parts/sources/STLQ020J30R/STLQ020.pdf",
        fab_country=None,
        currency=None,
        price_1pc=None,
        price_20kpc=None,
        weight_g=None,
        standards=[
            "ESD HBM ±2000 V",
            "ESD CDM ±500 V",
        ],
        eccn=None,
        itar=None,
        package="Flip-Chip 4 (DSBGA-4)",
        size_mm=(0.77, 0.77),
        height_mm=0.61,
        temp_range_c=(-40, 125),            # TJ-OP (p5)
        body_material=None,
        lead_material=None,
        voltage_rating_v=7.0,               # VIN absolute max (p5)
        vcc_nominal_v=3.0,                  # the 3.0 V trim (J30R)
        i_rms_a=0.200,                      # 200 mA max IOUT
        power_rating_w=None,                # internally limited
        rth_jc_cw=None,                     # NOT stated for Flip-Chip 4
        rth_ja_cw=180.0,                    # p5 Table 3
        tj_max_c=150.0,                     # TJ-MAX (p5)
        pins=[
            # Per pinmap.txt + datasheet p3 Table 1 + SamacSys symbol
            Pin(num="A1", name="VIN",  type="power"),
            Pin(num="A2", name="VOUT", type="power"),
            Pin(num="B1", name="EN",   type="input"),
            Pin(num="B2", name="GND",  type="ground"),
        ],
        footprint=_stlq020j30r_footprint(),
        note=_STLQ020J30R_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments LP5907 family — 250 mA ultra-low-noise CMOS LDO
#
# One datasheet (TI SNVS774) covers the whole family — only the output-
# voltage trim differs across variants. Single SOT-23-5 (DBV) package.
# All variants share the same pin layout, footprint, and abs-max.
#
# Variants in the datasheet (output voltage):
#   LP5907MFX-1.2/NOPB  -1.5  -1.8  -2.5  -2.7  -2.8  -2.85
#   LP5907MFX-2.9/NOPB  -3.0  -3.1  -3.2  -3.3  -3.6  -4.0  -4.5  -5.0
# Smash uses the -1.2 and -2.8 variants as the DNP camera-rail
# alternatives (instead of STPMIC25's BUCK6 + LDO5).
# ═════════════════════════════════════════════════════════════════════════

def _lp5907_base(
    *, part_dir: str, manf_pn: str, sym_filename: str,
    vout_v: float,
    stp_filename: str,
) -> dict:
    """Shared kw dict for one LP5907MFX-<vout> variant. Caller adds
    the variant-specific `ref` + overrides and passes through to
    `Design.add_chip`."""
    fp_mod = src(part_dir, "SOT95P280X145-5N.kicad_mod")
    return dict(
        manf="Texas Instruments",
        manf_pn=manf_pn,
        canonical_id=canonical_id(manf_pn),
        name=manf_pn,
        value=manf_pn,
        description=(
            f"Ultra-low-noise LDO, V_OUT={vout_v} V fixed, "
            "I_OUT=250 mA, V_IN=2.2..5.5 V, SOT-23-5 (DBV)"
        ),
        datasheet=datasheet_ref(part_dir, "lp5907-family.pdf"),
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None,
        standards=[],   # not declared on the front page of the family DS
        eccn=None, itar=None,
        package="SOT-23-5 (DBV)",
        size_mm=(2.9, 1.6),
        height_mm=1.45,
        temp_range_c=(-40, 125),    # industrial T_J operating per family DS
        body_material=None, lead_material=None,
        voltage_rating_v=6.0,        # V_IN abs max per family DS
        vcc_nominal_v=vout_v,
        i_rms_a=0.250,               # 250 mA continuous
        power_rating_w=None,         # internally limited
        rth_jc_cw=None, rth_ja_cw=None,
        tj_max_c=125.0,
        pins=build_pins(
            src(part_dir, sym_filename),
            types={
                "IN":  "power",
                "GND": "ground",
                "EN":  "input",
                "N/C": "nc",
                "OUT": "power",
            },
            notes={
                "EN":  "active-high enable; do NOT leave floating",
                "N/C": "datasheet: leave unconnected or tie to GND",
            },
        ),
        footprint=Footprint(
            name="SOT95P280X145-5N",
            package_class="SOT-23-5 (DBV)",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.95,
            size_mm=(2.9, 1.6),
            height_mm=1.45,
            model_3d_path=datasheet_ref(part_dir, stp_filename),
            source="samacsys",
        ),
        note=(
            "LP5907 family — single-channel 250 mA ultra-low-noise LDO. "
            "Same datasheet (TI SNVS774) covers every voltage trim "
            "from 1.2 V up to 5.0 V; only the manf_pn suffix differs.\n\n"
            "Key family specs (from datasheet):\n"
            "  - V_IN range : 2.2 V to 5.5 V\n"
            "  - V_OUT      : fixed per order code; this part is "
            f"{vout_v} V\n"
            "  - I_OUT max  : 250 mA\n"
            "  - Output noise: 6.5 µVrms (10 Hz – 100 kHz, V_OUT=2.8 V)\n"
            "  - PSRR       : 82 dB @ 1 kHz, 75 dB @ 10 kHz\n"
            "  - I_Q        : 11 µA typ\n"
            "  - Shutdown   : 0.01 µA typ (EN=GND)\n"
            "  - Dropout    : 120 mV typ @ I_OUT=150 mA\n"
            "  - Package    : SOT-23-5 (DBV-5)\n\n"
            "Smash use (`add_optional_camera_ldos()` on power_board): "
            "DNP-by-default low-noise alternatives to the STPMIC25's "
            "BUCK6 (1.2 V camera VDD) and LDO5 (2.8 V camera VAA) "
            "rails. Populate these LP5907s when the camera demands "
            "lower-noise rails than the switching PMIC can provide; "
            "DNP them when the PMIC suffices.\n\n"
            "EN pin must NOT float (no internal pull-up/pull-down). "
            "For always-on use, tie EN to V_IN. The N/C pin (pin 4) "
            "is not internally connected — leave open or tie to GND."
        ),
    )


def add_lp5907mfx_1_2_nopb(design, ref: str, **overrides) -> Chip:
    """TI LP5907MFX-1.2/NOPB — 250 mA low-noise LDO, V_OUT=1.2 V fixed,
    SOT-23-5. Used on `power_board` as DNP alternative to STPMIC25 BUCK6
    for the camera's 1.2 V VDD/VDD_PHY/VDD_DATA rails."""
    fields = _lp5907_base(
        part_dir="LP5907MFX-1.2_NOPB",
        manf_pn="LP5907MFX-1.2/NOPB",
        sym_filename="LP5907MFX-1_2_NOPB.kicad_sym",
        vout_v=1.2,
        stp_filename="LP5907MFX-1.2_NOPB.stp",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_tps7a0233pdbvr(design, ref: str, **overrides) -> Chip:
    """TI TPS7A0233PDBVR — 25 nA-IQ nanopower LDO, 200 mA, V_OUT=3.3 V
    fixed, SOT-23-5 (DBV). THE always-on (AON) regulator: hangs directly
    on BAT_RAW (upstream of the wake-gated eFuse) and powers the 3V3_AON
    standby domain (WBA55 + H3LIS + ST25DV VCC + TLV3691), so Standby
    runs with the eFuse AND the main path OFF.

    Why this part (DS `tps7a02.pdf`, in sources/ + Research/):
      - IQ 25 nA typ, even in dropout — vanishes vs the ~17 µA AON loads
      - 200 mA, dropout 270 mV max — 5× margin over WBA BLE TX peaks
      - load transient SPEC'd 1 mA→50 mA/1 µs @1 µF: the WBA sleep→TX
        profile (the classic nanopower-LDO weakness, explicitly solved)
      - "smart enable" internal pull-down: EN floating/0 = OFF, no
        external pull-down needed for the AON latch
      - SOT-23-5: leaded + shock-robust (supersedes the abandoned
        STLQ020J33R DSBGA-4 concept, see add_stlq020j33r notes)

    The "P" suffix is TI's current production die for the 3.3 V DBV
    orderable — same datasheet family as plain TPS7A0233DBVR."""
    pn = "TPS7A0233PDBVR"
    fp_mod = src(pn, "SOT95P280X145-5N.kicad_mod")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=(
            "Nanopower LDO 200 mA, IQ 25 nA, V_OUT=3.3 V fixed, "
            "VIN=1.5..6.0 V, dropout 270 mV max @ 200 mA, SOT-23-5 — "
            "the 3V3_AON standby-domain regulator"
        ),
        datasheet=datasheet_ref(pn, "tps7a02.pdf"),
        package="SOT-23-5 (DBV)",
        size_mm=(2.9, 1.6), height_mm=1.45,
        temp_range_c=(-40, 125),
        voltage_rating_v=6.0,              # VIN max
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="SOT95P280X145-5N", package_class="SOT-23-5",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.95, size_mm=(2.9, 1.6), height_mm=1.45,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "TPS7A02 nanopower LDO as the 3V3_AON always-on regulator on "
            "activation_interface: IN=BAT_RAW (3.2-4.1 V cells; never sees "
            "depot USB, which ORs into BAT_PROT), OUT=3V3_AON, EN raised by "
            "the NFC-GPO wake (via Q_AON_EN) or held by a WBA GPIO. 1 uF "
            "X7R in + out per DS. The LDO's own ~current limit is the "
            "protection for this ~17 uA domain (it bypasses the eFuse by "
            "design)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_lp5907mfx_2_8_nopb(design, ref: str, **overrides) -> Chip:
    """TI LP5907MFX-2.8/NOPB — 250 mA low-noise LDO, V_OUT=2.8 V fixed,
    SOT-23-5. Used on `power_board` as DNP alternative to STPMIC25 LDO5
    for the camera's 2.8 V VAA/VAA_PIX/VAA_PHY rails — the
    image-quality-critical analog supply for the AR0234CS sensor."""
    fields = _lp5907_base(
        part_dir="LP5907MFX-2.8_NOPB",
        manf_pn="LP5907MFX-2.8/NOPB",
        sym_filename="LP5907MFX-2_8_NOPB.kicad_sym",
        vout_v=2.8,
        stp_filename="LP5907MFX-2.8_NOPB.stp",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# STMicroelectronics STLQ020J33R — 3.3 V trim of the STLQ020 family.
# Same Flip-Chip 4 (DSBGA-4) package as STLQ020J30R; only V_OUT differs.
#
# This is the **datasheet-correct replacement for the hallucinated
# `STLQ020M33R`** PN that earlier system.py revisions used.
# ═════════════════════════════════════════════════════════════════════════

def add_stlq020j33r(design, ref: str, **overrides) -> Chip:
    """STMicroelectronics STLQ020J33R — 200 mA ultra-low-Iq LDO,
    V_OUT=3.3 V fixed, Flip-Chip 4 (DSBGA-4) package.

    Replaces the hallucinated `STLQ020M33R` in system.py
    `add_st25dv_and_wakeup_ldo()` (line 1067-1129) — the always-on
    LDO that powers WLE5 + ST25DV from BAT_PROT.

    >>> **Package mismatch with the original SOT-23-5 design intent.**
        system.py line 1118-1119 explicitly says: "AP2112K-3.3 used as
        KiCad symbol placeholder (standard SOT-23-5 LDO pinout); real
        part is STLQ020M33R from ST — same pinout, footprint." That
        assumption is WRONG — the STLQ020 family doesn't ship in
        SOT-23-5 at all. Real STLQ020 packages are:
          STLQ020C33R  → SOT323-5L (5-lead small outline, ≈ SOT-23-5)
          STLQ020J33R  → DSBGA-4 (0.77 × 0.77 × 0.61 mm, this factory)
          STLQ020PU33R → DFN6-2x2 with exposed thermal pad
        Adopting J33R means the PCB footprint at the WLE5-LDO position
        switches from SOT-23-5 to DSBGA-4 (different pads, BGA reflow,
        underfill recommended for shock).

    >>> **High-G launch survivability** (1000+ G axial): DSBGA-4 with
        0.40 mm pitch balls is more demanding than a leaded SOT-23-5.
        Smash already uses Loctite Eccobond UF-1173/3811/3812
        underfill in other DSBGA positions (e.g. the QPD module's
        existing STLQ020J30R) — same mitigation applies here.
    """
    pn = "STLQ020J33R"
    fp_mod = src(pn, "BGA4C40P2X2_77X77X61.kicad_mod")
    fields = dict(
        manf="STMicroelectronics", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "LDO 200 mA, V_OUT=3.3 V fixed, V_IN=2..5.5 V, "
            "Iq=300 nA typ no-load, Flip-Chip 4 (DSBGA-4)"
        ),
        datasheet=datasheet_ref(pn, "STLQ020.pdf"),
        package="Flip-Chip 4 (DSBGA-4)",
        size_mm=(0.77, 0.77),
        height_mm=0.61,
        temp_range_c=(-40, 125),
        voltage_rating_v=7.0,          # V_IN abs max
        vcc_nominal_v=3.3,             # the 3.3 V trim (J33R)
        i_rms_a=0.200,                 # 200 mA max IOUT
        power_rating_w=None,           # internally limited
        rth_jc_cw=None,                # not stated for Flip-Chip 4
        rth_ja_cw=180.0,               # same as J30R per family DS Table 3
        tj_max_c=150.0,
        standards=[
            "ESD HBM ±2000 V",
            "ESD CDM ±500 V",
        ],
        pins=build_pins(
            src(pn, f"{pn}.kicad_sym"),
            types={
                "VIN":  "power",
                "VOUT": "power",
                "EN":   "input",
                "GND":  "ground",
            },
        ),
        footprint=Footprint(
            name="BGA4C40P2X2_77X77X61",
            package_class="DSBGA-4",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.40,
            size_mm=(0.77, 0.77),
            height_mm=0.61,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
            note=(
                "DSBGA-4 (Flip-Chip), 4 balls A1/A2/B1/B2. Bare-die "
                "package — underfill recommended for high-G launch "
                "survivability."
            ),
        ),
        note=(
            "STMicroelectronics STLQ020J33R — 3.3 V variant of the "
            "STLQ020 family, otherwise identical to STLQ020J30R "
            "(catalog factory `add_stlq020j30r`). Same DSBGA-4 "
            "package, same pinout, same datasheet — only the output "
            "trim differs (3.3 V vs 3.0 V).\n\n"
            "Smash use (system.py `add_st25dv_and_wakeup_ldo()`): "
            "the always-on LDO powering WLE5 + ST25DV from BAT_PROT. "
            "Powered directly from the eFuse output; never switched "
            "off. The 300 nA quiescent current is critical — at WLE5's "
            "Stop2 sleep current (~3 µA) plus this LDO's Iq, the "
            "binding shelf load is ~3.3 µA total against the 375 mAh "
            "TLM-1520HPM/S 3P pack → multi-year shelf life.\n\n"
            "Order code decode (STLQ020J33R, per datasheet p20 Table 9):\n"
            "  STLQ020 : family (200 mA nano-Iq LDO)\n"
            "  J       : Flip-Chip 4 (DSBGA) package\n"
            "  33      : 3.3 V output trim\n"
            "  R       : tape and reel\n"
            "Marking: 'MB' (datasheet p20)\n\n"
            "Pin layout (per the SamacSys-generated KiCad sym, "
            "verified against datasheet p3 Table 1 Flip-Chip 4 column):\n"
            "  A1 = VIN\n"
            "  A2 = VOUT\n"
            "  B1 = EN\n"
            "  B2 = GND"
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# STMicroelectronics STLQ020C33R — SOT323-5L (5-lead, ≈ SOT-23-5)
# variant of the STLQ020 family. 3.3 V trim, same 200 mA / 300 nA Iq.
#
# **Recommended replacement for the hallucinated `STLQ020M33R`** —
# matches the original SOT-23-5 design intent better than the
# DSBGA-4 J33R variant (5-lead leaded → far more shock-tolerant than
# Flip-Chip 4 under Smash's 1000+ G launch loads).
# ═════════════════════════════════════════════════════════════════════════

def add_stlq020c33r(design, ref: str, **overrides) -> Chip:
    """STMicroelectronics STLQ020C33R — 200 mA ultra-low-Iq LDO,
    V_OUT=3.3 V fixed, SOT323-5L (5-lead SC-70, 2.0 × 1.25 × 1.0 mm).

    **This is the Smash-recommended replacement for the hallucinated
    `STLQ020M33R`** in system.py's `add_st25dv_and_wakeup_ldo()` (line
    1067-1129). The original design intent assumed SOT-23-5; SOT323-5L
    is the closest STLQ020 variant — same 5-lead leaded topology, just
    a smaller body and 0.65 mm pitch (vs SOT-23-5's 0.95 mm pitch).
    Leaded package → mechanically robust under Smash's 1000+ G launch
    shock (vs the DSBGA-4 J33R variant which needs underfill).

    Sibling factory: `add_stlq020j33r` for the Flip-Chip 4 variant
    (smaller but bare-die / underfill required).
    """
    pn = "STLQ020C33R"
    fp_mod = src(pn, "SOT65P210X110-5N.kicad_mod")
    fields = dict(
        manf="STMicroelectronics", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "LDO 200 mA, V_OUT=3.3 V fixed, V_IN=2..5.5 V, "
            "Iq=300 nA typ no-load, SOT323-5L (5-lead SC-70)"
        ),
        datasheet=datasheet_ref(pn, "STLQ020.pdf"),
        package="SOT323-5L (SC-70-5)",
        size_mm=(2.0, 1.25),
        height_mm=1.0,
        temp_range_c=(-40, 125),
        voltage_rating_v=7.0,
        vcc_nominal_v=3.3,
        i_rms_a=0.200,
        rth_ja_cw=250.0,               # SOT323-5L per family DS Table 3
        tj_max_c=150.0,
        standards=[
            "ESD HBM ±2000 V",
            "ESD CDM ±500 V",
        ],
        pins=build_pins(
            src(pn, f"{pn}.kicad_sym"),
            types={
                "VIN":  "power",
                "VOUT": "power",
                "EN":   "input",
                "GND":  "ground",
                "NC":   "nc",
            },
            notes={
                "NC": "datasheet: not connected — leave floating or tie to GND",
                "EN": "active-high enable; do NOT leave floating",
            },
        ),
        footprint=Footprint(
            name="SOT65P210X110-5N",
            package_class="SOT323-5L (SC-70-5)",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.65,
            size_mm=(2.0, 1.25),
            height_mm=1.0,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "STMicroelectronics STLQ020C33R — 3.3 V variant of the "
            "STLQ020 family in SOT323-5L (SC-70-5) package. Same "
            "silicon as STLQ020J33R (DSBGA-4) and STLQ020J30R "
            "(DSBGA-4, 3.0 V trim); the 'C' prefix indicates the "
            "SOT323-5L leaded package.\n\n"
            "Smash use (system.py `add_st25dv_and_wakeup_ldo()`): the "
            "always-on LDO powering WLE5 + ST25DV from BAT_PROT. The "
            "original system.py used `Regulator_Linear:AP2112K-3.3` "
            "as a SOT-23-5 placeholder with `manf_pn=\"STLQ020M33R\"` "
            "(hallucinated PN). C33R is the closest fit:\n"
            "  - 5-lead leaded package (same topology as SOT-23-5)\n"
            "  - 0.65 mm pitch (vs SOT-23-5's 0.95 mm; smaller body)\n"
            "  - Shock-tolerant for high-G launch (vs J33R DSBGA-4\n"
            "    which needs underfill)\n\n"
            "Order code decode (STLQ020C33R, per datasheet p20 Table 9):\n"
            "  STLQ020 : family (200 mA nano-Iq LDO)\n"
            "  C       : SOT323-5L package\n"
            "  33      : 3.3 V output trim\n"
            "  R       : tape and reel\n"
            "Marking: 'QMB' (datasheet p20)\n\n"
            "Pin layout (per the SamacSys-generated KiCad sym + "
            "datasheet p3 Table 1 SOT323-5L column):\n"
            "  1 = VIN\n"
            "  2 = GND\n"
            "  3 = EN\n"
            "  4 = NC  (leave floating or tie to GND)\n"
            "  5 = VOUT\n\n"
            "PCB footprint impact vs the original SOT-23-5 placeholder:\n"
            "  - 5 pads, smaller pitch (0.65 mm vs 0.95 mm)\n"
            "  - Smaller body (2.0×1.25 vs 2.9×1.6 mm)\n"
            "  - Same pin TOPOLOGY (5-lead small outline) — schematic "
            "    wiring stays the same; PCB footprint pad geometry "
            "    needs updating."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
