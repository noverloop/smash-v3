"""RF (radio-frequency) parts — switches, baluns, filters, mixers, PLLs."""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


# ═════════════════════════════════════════════════════════════════════════
# Infineon BGS12WN6E6327XTSA1 — 0.05–9 GHz SPDT RF switch with on-chip
# CMOS logic, PG-TSNP-6-10 (0.7 × 1.1 × 0.375 mm)
# ═════════════════════════════════════════════════════════════════════════

_BGS12_NOTE = """\
Datasheet extras (Infineon BGS12WN6, datasheet rev 2.9, 2026-04-24).

Headline (datasheet p1):
  Frequency range : 0.05 GHz to 9 GHz
  Size            : 0.7 × 1.1 × 0.375 mm (max height)
  Configuration   : SPDT (single-pole double-throw)
  Fast switching speed
  Low insertion loss
  High port-to-port isolation up to 9 GHz
  RF input power  : up to 30 dBm
  Low current consumption
  No DC blocking caps required (if no DC on RF lines)
  Integrated on-chip CMOS logic (single-pin digital control)

Order code (p1):
  BGS12WN6 E6327 : package PG-TSNP-6-10 (this factory)
  BGS12WN6 E6329 : package PG-TSNP-6-2  (different reel size only)

Applications (p1):
  Antenna selection / Tx-Rx switching in IEEE 802.11a/b/g/n/ac/ax WLAN
  Bluetooth (up to 6.0)
  UWB (IEEE 802.15.4)
  Cellular (up to 6G)

Qualification (p1): industrial per JEDEC 47/20/22.
Pb-free / RoHS / WEEE compliant package.

Absolute Max Ratings (datasheet, abs-max section):
  T_STG storage              : -55 to +150 °C
  T_J junction max           : 125 °C
  P_RF,max RF input power    : 30 dBm (CW, VSWR 1:1, Z0=50 Ω)
  V_RFDC max DC on RF ports  : 0 V (NO DC ALLOWED on RF ports)
  R_thJS junction-to-solder  : 70 K/W
  ESD CDM, V_ESD,CDM         : ±1 kV (ANSI/ESDA/JEDEC JS-002)
  ESD HBM, V_ESD,HBM         : ±1 kV (ANSI/ESDA/JEDEC JS-001)
  ESD RF ports (with 27 nH shunt inductor) : ±8 kV (IEC 61000-4-2 contact)
  ESD RF ports (with 56 nH shunt inductor) : ±6 kV

>>> "No DC voltages allowed on RF ports" — datasheet abs max. The
    "no DC blocking caps required" claim in features applies only
    when the external circuit guarantees no DC on the RF lines.

Pin layout (datasheet + pinmap.txt, PG-TSNP-6-10):
  1 = RF2   (RF throw output 2)
  2 = GND
  3 = RF1   (RF throw output 1)
  4 = VDD   (control logic supply)
  5 = RFIN  (RF common input)
  6 = CTRL  (digital control input; selects RF1 or RF2)

Application notes (datasheet body):
  - The RF I/O ports are bidirectional; "RFIN" / "RF1" / "RF2"
    naming reflects the typical Tx-Rx switching topology but the
    switch works in either direction.
  - The isolated port is a "reflective short" (datasheet description).
  - Direct connection to digital control pin — no extra interface
    circuitry, simplifying system design.

Mechanical (NOT in datasheet headline): body_material, lead_material,
weight_g, fab_country.

Distributor (SamacSys metadata): see Infineon listings.
"""


def _bgs12_tsnp6_footprint() -> Footprint:
    """PG-TSNP-6-10 footprint per SamacSys BGS12WN6E6327XTSA1.kicad_mod.

    Tiny package: pads on a 0.4 mm pitch grid, 0.25 × 0.25 mm each.
    Layout: 3 pads on top row (y=+0.2), 3 pads on bottom row (y=-0.2),
    with pin 1 at (-0.4, +0.2). Pin numbering goes counter-clockwise
    from pin 1 → top-right → bottom-right → bottom-left.
    """
    return Footprint(
        name="BGS12WN6E6327XTSA1",
        package_class="PG-TSNP-6-10",
        pads=[
            # Top row (y=+0.2): pins 1, 2, 3 going right
            Pad(num="1", position_mm=(-0.4, -0.2), size_mm=(0.25, 0.25), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(0.0, -0.2), size_mm=(0.25, 0.25), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(0.4, -0.2), size_mm=(0.25, 0.25), shape="rect", layer="F.Cu"),
            # Bottom row (y=-0.2): pins 4, 5, 6 going left
            Pad(num="4", position_mm=(0.4, 0.2), size_mm=(0.25, 0.25), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(0.0, 0.2), size_mm=(0.25, 0.25), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=(-0.4, 0.2), size_mm=(0.25, 0.25), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-0.55, -0.35), (0.55, -0.35), (0.55, 0.35), (-0.55, 0.35)],
        courtyard=[(-1.55, -1.35), (1.55, -1.35), (1.55, 1.35), (-1.55, 1.35)],
        pitch_mm=0.4,
        size_mm=(1.1, 0.7),         # body 0.7 × 1.1 per datasheet (W × L)
        height_mm=0.375,            # max height per datasheet
        model_3d_path="application/src/smash/parts/sources/BGS12WN6E6327XTSA1/BGS12WN6E6327XTSA1.stp",
        source="samacsys",
    )


def add_bgs12wn6e6327xtsa1(design, ref: str, **overrides) -> Chip:
    """Infineon BGS12WN6E6327XTSA1 — 0.05–9 GHz broadband SPDT RF
    switch with on-chip CMOS logic, PG-TSNP-6-10 (0.7×1.1×0.375 mm)."""
    fields = dict(
        manf="Infineon",
        manf_pn="BGS12WN6E6327XTSA1",
        canonical_id="bgs12wn6e6327xtsa1",
        name="BGS12WN6E6327XTSA1",
        value="BGS12WN6E6327XTSA1",
        description=(
            "SPDT RF switch, 0.05-9 GHz, low insertion loss, up to "
            "30 dBm RF input power, single-pin CMOS logic control, "
            "PG-TSNP-6-10 (0.7×1.1×0.375 mm)"
        ),
        datasheet="application/src/smash/parts/sources/BGS12WN6E6327XTSA1/BGS12WN6.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "RoHS", "WEEE", "Pb-Free",
            "JEDEC47", "JEDEC20", "JEDEC22 (Industrial qualification)",
            "ESD CDM ±1 kV (ANSI/ESDA/JEDEC JS-002)",
            "ESD HBM ±1 kV (ANSI/ESDA/JEDEC JS-001)",
            "ESD RF ports ±8 kV (with 27 nH shunt, IEC 61000-4-2)",
            "ESD RF ports ±6 kV (with 56 nH shunt, IEC 61000-4-2)",
        ],
        eccn=None, itar=None,
        package="PG-TSNP-6-10",
        size_mm=(1.1, 0.7),
        height_mm=0.375,
        temp_range_c=(-55, 150),    # T_STG range (operating range likely
                                    # tighter — datasheet T_J max 125°C)
        body_material=None, lead_material=None,
        voltage_rating_v=None,       # not extracted from datasheet table
        vcc_nominal_v=None,          # caller decides (typ 1.8 / 2.5 / 3.3 V)
        i_rms_a=None,
        power_rating_w=None,
        rth_jc_cw=70.0,              # R_thJS — junction-to-solder, datasheet
        rth_ja_cw=None,
        tj_max_c=125.0,
        pins=[
            # Per pinmap.txt
            Pin(num="1", name="RF2",  type="io",
                note="RF throw output 2"),
            Pin(num="2", name="GND",  type="ground"),
            Pin(num="3", name="RF1",  type="io",
                note="RF throw output 1"),
            Pin(num="4", name="VDD",  type="power",
                note="control-logic supply only — NOT on RF lines"),
            Pin(num="5", name="RFIN", type="io",
                note="RF common input — NO DC voltage allowed"),
            Pin(num="6", name="CTRL", type="input",
                note="digital control: HIGH/LOW selects RF1 vs RF2 (see DS)"),
        ],
        footprint=_bgs12_tsnp6_footprint(),
        note=_BGS12_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Analog Devices ADF4351BCPZ — Wideband PLL with integrated VCO,
# 35 MHz to 4.4 GHz output, 32-lead LFCSP + EP
# ═════════════════════════════════════════════════════════════════════════

def add_adf4351bcpz(design, ref: str, **overrides) -> Chip:
    """ADI ADF4351BCPZ — wideband fractional-N PLL with integrated
    VCO, 35 MHz to 4.4 GHz output (output dividers /1, /2, /4,
    /8, /16, /32, /64), 32-LFCSP with thermal pad."""
    pn = "ADF4351BCPZ"
    fp_mod = src(pn, "QFN50P500X500X100-33N.kicad_mod")
    fields = dict(
        manf="Analog Devices", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Wideband fractional-N PLL with integrated VCO, "
            "35 MHz to 4.4 GHz output, LFCSP-32"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="LFCSP-32 (5×5 mm)",
        size_mm=(5.0, 5.0), height_mm=1.0,
        temp_range_c=(-40, 85),
        clock_max_hz=4.4e9,
        # ── thermal (ADI ADF4351 Rev D, Table 4 + abs max section) ───
        # Power supplies typ/max (DS Specs Table 1 p3):
        #   DIDD + AIDD : 21 mA typ / 27 mA max
        #   IVCO        : 70 mA typ / 80 mA max
        #   IRFOUT      : 21 mA typ / 26 mA max
        #   Dividers    : 6 mA per /2 stage (up to ~36 mA)
        # Total typ @ Vdd=3.3V, VCO + RFOUT enabled: ~125 mA × 3.3V
        # = 0.41 W. Worst-case (max + all dividers + 3.6V): ~170 mA
        # × 3.6V = 0.61 W.
        # ΘJA = 27.3 °C/W for 32-Lead LFCSP CP-32-7 with exposed pad
        # soldered to GND (DS Table 4 p4). NO ΘJC quoted.
        p_active_w=0.41,                    # 125 mA × 3.3V — typ VCO+RFOUT (DS Table 1 p3)
        p_max_w=0.61,                       # 170 mA × 3.6V — max VCO+RFOUT+dividers (DS Table 1)
        rth_jc_cw=None,                     # not quoted (only ΘJA given), DS Table 4 p4
        tj_max_c=150.0,                     # Tj max, DS Abs Max p4
        standards=["RoHS"],
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="QFN50P500X500X100-33N", package_class="LFCSP-32",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.5, size_mm=(5.0, 5.0), height_mm=1.0,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "ADF4351 = wideband fractional-N PLL with integrated VCO. "
            "Output range 35 MHz to 4.4 GHz via VCO + selectable /N "
            "output divider. SPI 3-wire control (CE, CLK, DATA, LE). "
            "Requires external loop filter on CP_OUT pin."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
