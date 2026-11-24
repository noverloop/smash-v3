"""RF (radio-frequency) parts — switches, baluns, filters, mixers, PLLs."""

from __future__ import annotations

from dataclasses import replace as _dc_replace
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
        # 2026-11-18: Infineon lists assembly in CN and MY (wafer DE) → fails
        # the no-Chinese-chips rule; replaced by BGS12P2L6 in the design.
        fab_country="DE (wafer), CN/MY (assembly)", currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
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
        fab_country="TW (wafer), KR/PH (assembly)",   # Mouser AU / Arrow / Farnell UK, 2026-11-18
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


# ═════════════════════════════════════════════════════════════════════════
# Shared helper for the SamacSys-sourced 2.4 GHz radio parts below
# ═════════════════════════════════════════════════════════════════════════

def _samacsys_qfn_footprint(part_dir: str, mod_file: str, *, name: str,
                            package_class: str, pitch_mm: float,
                            size_mm: tuple, height_mm: float) -> Footprint:
    mod = src(part_dir, mod_file)
    return Footprint(
        name=name,
        package_class=package_class,
        pads=pads_from_kicad_mod(mod),
        body_outline=outline_polygon(mod, "F.Fab") or [
            (-size_mm[0] / 2, -size_mm[1] / 2), (size_mm[0] / 2, -size_mm[1] / 2),
            (size_mm[0] / 2, size_mm[1] / 2), (-size_mm[0] / 2, size_mm[1] / 2)],
        courtyard=outline_polygon(mod, "F.CrtYd"),
        pitch_mm=pitch_mm,
        size_mm=size_mm,
        height_mm=height_mm,
        model_3d_path=datasheet_ref(part_dir, f"{part_dir}.stp"),
        source="samacsys",
    )


def _check_pins_vs_pads(pn: str, pins: list, fp: Footprint) -> None:
    pads = {p.num for p in fp.pads}
    mapped = {p.num for p in pins}
    if pads != mapped:
        raise ValueError(f"{pn}: pin/pad mismatch — pads not mapped: "
                         f"{pads - mapped}, pins without pad: {mapped - pads}")


# ═════════════════════════════════════════════════════════════════════════
# Semtech SX1280 — 2.4 GHz LoRa® / FLRC / GFSK / BLE-PHY transceiver,
# VQFN-24 4×4 mm + exposed pad
# ═════════════════════════════════════════════════════════════════════════

_SX1280_NOTE = """\
Datasheet extras (Semtech SX1280/SX1281 DS, Rev 3.2, March 2020).

Pin table (§2 Table 2-1). The datasheet numbers the exposed pad "0";
the SamacSys footprint numbers it "25" — same pad, GND.

Supplies (Table 2-1): VBAT 1.8–3.7 V; VBAT_IO 1.8–3.7 V and must be
≤ VBAT. VDD_IN "Connect to Pin 12" (DCC_FB, the internal regulator
output).

Regulation (§5.1): LDO enabled by default in all modes; the DC-DC buck
(15 µH between DCC_SW pin 14 and DCC_FB pin 12) is optional —
"LDO-only operation is possible which negates the need for the 15 μH
inductor", at higher energy consumption. All DS specs are given with
the DC-DC enabled.

Reference: 52 MHz crystal (§3.7 Table 3-9: CLOAD 10 pF, internal foot
capacitances — no external load caps), or a 0.8 V clipped-sine TCXO
AC-coupled into XTA (§15.2).

Host interface (§9): SPI (CPOL=0, CPHA=0, up to 18 MHz) or UART on the
same pins; at power-up both are enabled until the first valid
transaction (§9.2). BUSY low = ready for a new command (§9.1) — must be
checked before every transaction. Wake from Sleep = falling edge on NSS
(§9.3.3).

Reference design BOM (§15.1.2): RF match C0 0.8 pF, L1 3.0 nH, PI
filter C1 1.2 pF / L2 2.5 nH / C2 1.2 pF, DC block C3 100 pF; C5/C6
10 nF on VR_PA; C8 100 nF VBAT_IO; C10 100 nF VBAT; C9 470 nF DCC_FB.
"""


def add_sx1280(design, ref: str, **overrides) -> Chip:
    """Semtech SX1280 — 2.4 GHz LoRa/FLRC/GFSK transceiver, SPI/UART
    host interface, VQFN-24 4×4 mm (QFN50P400X400X100-25N-D)."""
    pn = "SX1280"
    fp = _samacsys_qfn_footprint(
        pn, "QFN50P400X400X100-25N-D.kicad_mod",
        name="QFN50P400X400X100-25N-D", package_class="VQFN-24 4x4 + EP",
        pitch_mm=0.5, size_mm=(4.0, 4.0), height_mm=1.0)
    P = Pin
    pins = [
        P(num="1",  name="VR_PA",    type="power",  note="Regulated supply for the PA (internal; decouple only)"),
        P(num="2",  name="VDD_IN",   type="power",  note="Regulated supply input. Connect to Pin 12."),
        P(num="3",  name="NRESET",   type="input",  note="Reset, active low, internal 50 kΩ pull-up"),
        P(num="4",  name="XTA",      type="passive", note="Reference oscillator connection or TCXO input"),
        P(num="5",  name="GND",      type="ground"),
        P(num="6",  name="XTB",      type="passive", note="Reference oscillator connection"),
        P(num="7",  name="BUSY",     type="output", note="Transceiver busy indicator"),
        P(num="8",  name="DIO1",     type="io"),
        P(num="9",  name="DIO2",     type="io"),
        P(num="10", name="DIO3",     type="io"),
        P(num="11", name="VBAT_IO",  type="power",  note="Digital IO supply 1.8–3.7 V, must be ≤ VBAT"),
        P(num="12", name="DCC_FB",   type="power",  note="Regulated output voltage from the internal regulator"),
        P(num="13", name="GND",      type="ground"),
        P(num="14", name="DCC_SW",   type="output", note="DC-DC switcher output (NC in LDO-only use)"),
        P(num="15", name="VBAT",     type="power",  note="RFIC supply 1.8–3.7 V, must be ≥ VBAT_IO"),
        P(num="16", name="MISO_TX",  type="output", aliases=["MISO", "TX"]),
        P(num="17", name="MOSI_RX",  type="input",  aliases=["MOSI", "RX"]),
        P(num="18", name="SCK_RTSN", type="input",  aliases=["SCK", "RTSN"]),
        P(num="19", name="NSS_CTS",  type="input",  aliases=["NSS", "CTS"]),
        P(num="20", name="GND",      type="ground"),
        P(num="21", name="GND",      type="ground"),
        P(num="22", name="RFIO",     type="io",     note="RF transmit output and receive input"),
        P(num="23", name="GND",      type="ground"),
        P(num="24", name="GND",      type="ground"),
        P(num="25", name="GND",      type="ground", aliases=["EP", "0"],
          note="Exposed ground pad (DS pin 0)"),
    ]
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="Semtech", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=("2.4 GHz LoRa/FLRC/GFSK transceiver, SPI/UART host "
                     "interface, VQFN-24 4×4 mm"),
        datasheet=datasheet_ref(pn, "SX1280.pdf"),
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None, standards=[], eccn=None, itar=None,
        package="VQFN-24 4x4", size_mm=(4.0, 4.0), height_mm=1.0,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=3.7, vcc_nominal_v=3.3,
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=None,
        pins=pins, footprint=fp, note=_SX1280_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Nordic nRF21540-QDAA-R7 — 2.4 GHz RF front-end module (PA + LNA + 2:1
# antenna switch), QFN-16 4×4 mm + exposed pad
# ═════════════════════════════════════════════════════════════════════════

_NRF21540_NOTE = """\
Product Specification extras (Nordic nRF21540 PS, docs.nordicsemi.com).

Pin assignments (Table 1). NOTE: the SamacSys symbol names pin 10 "TRE";
the PS names it TRX ("Transceiver interface") — PS name used here.

Ratings: VDD abs max 3.6 V; recommended 1.7 / 3.0 / 3.6 V. RF input
abs max: TRX +5 dBm (CW, TX mode), ANT +15 dBm (CW, RX/Program).
T_OP −40…+105 °C. ZL 50 Ω (single-ended 50 Ω matched in/out).

Electrical (VDD 3 V, 25 °C, 2440 MHz): PSAT 21.5 dBm, G_TX 20 dB
(adjustable 5…21 dB), I_TX 110 mA @ +20 dBm / 38 mA @ +10 dBm,
I_RX 2.9 mA, G_RX 13 dB, NF 2.7 dB, I_PD 45 nA, I_PG 1.1 mA.

Control (Operational states): PDN=0 → power-down; PDN=1 → Program;
then RX_EN / TX_EN (or SPI CONFREG0/1) → RX / TX. Only one state at a
time. ANT_SEL=0 → ANT1, =1 → ANT2 (switches isolate in PD/PG).
Settling (max): PD→PG 17.5 µs, PG→TX/RX 10.5 µs, TX/RX→PD 10 µs.

SPI optional ("I/O, SPI, or a combination"). Unused: SCK, MOSI → VSS;
CSN → VDD; MISO unconnected. SPI FSCK max 8.9 MHz.

Reference BOM (dual antenna, QFN16): 1.0 pF / 2.0 pF NP0, 1.9 nH /
3.0 nH, 100 nF, 10 µF, 33 kΩ — pin mapping is in the PS schematic
image (not transcribed); confirm before routing.
"""


def add_nrf21540_qdaa_r7(design, ref: str, **overrides) -> Chip:
    """Nordic nRF21540-QDAA-R7 — 2.4 GHz RF FEM (+21 dBm PA, 13 dB LNA,
    2:1 antenna switch), GPIO or SPI control, QFN-16 4×4 mm."""
    pn = "nRF21540-QDAA-R7"
    fp = _samacsys_qfn_footprint(
        pn, "QFN65P400X400X95-17N-D.kicad_mod",
        name="QFN65P400X400X95-17N-D", package_class="QFN-16 4x4 + EP",
        pitch_mm=0.65, size_mm=(4.0, 4.0), height_mm=0.95)
    P = Pin
    pins = [
        P(num="1",  name="VSS",     type="ground"),
        P(num="2",  name="ANT1",    type="io",    note="First antenna interface (50 Ω)"),
        P(num="3",  name="ANT2",    type="io",    note="Second antenna interface (50 Ω)"),
        P(num="4",  name="MODE",    type="input", note="TX power mode control"),
        P(num="5",  name="VDD",     type="power", note="Supply voltage 1.7–3.6 V"),
        P(num="6",  name="VDD",     type="power", note="Supply voltage 1.7–3.6 V"),
        P(num="7",  name="RX_EN",   type="input", note="RX mode enable"),
        P(num="8",  name="ANT_SEL", type="input", note="Antenna select (0 = ANT1)"),
        P(num="9",  name="TX_EN",   type="input", note="TX mode enable"),
        P(num="10", name="TRX",     type="io",    aliases=["TRE"],
          note="Transceiver interface (50 Ω); abs max +5 dBm in TX"),
        P(num="11", name="PDN",     type="input", note="Power-down, active low"),
        P(num="12", name="SCK",     type="input", note="SPI clock; VSS if SPI unused"),
        P(num="13", name="MOSI",    type="input", note="SPI data in; VSS if SPI unused"),
        P(num="14", name="MISO",    type="output", note="SPI data out; NC if SPI unused"),
        P(num="15", name="CSN",     type="input", note="SPI chip select, active low; VDD if SPI unused"),
        P(num="16", name="VSS",     type="ground"),
        P(num="17", name="VSS",     type="ground", aliases=["DAP", "EP"],
          note="Exposed pad (DAP) — ground"),
    ]
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="Nordic Semiconductor", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=("2.4 GHz RF front-end: +21 dBm PA, 13 dB LNA, 2:1 "
                     "antenna switch, GPIO/SPI control, QFN-16 4×4 mm"),
        datasheet=None,
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None, standards=["J-STD-020 260 °C reflow", "MSL 2",
                                  "ESD HBM 1 kV", "ESD CDM 2 kV"],
        eccn=None, itar=None,
        package="QFN-16 4x4", size_mm=(4.0, 4.0), height_mm=0.95,
        temp_range_c=(-40, 105),
        body_material=None, lead_material=None,
        voltage_rating_v=3.6, vcc_nominal_v=3.0,
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=None,
        pins=pins, footprint=fp, note=_NRF21540_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Semtech LR2021IMLTRT — LoRa Plus multi-band transceiver (sub-GHz +
# 2.4 GHz), QFN-32 5×5 mm + exposed pad
# ═════════════════════════════════════════════════════════════════════════

_LR2021_NOTE = """\
Datasheet: Semtech LR20xx FINAL Datasheet Rev 2.2 (DS.LR20xx, 29/07/26).
Pin names / numbers (SamacSys symbol v1.1) match Table 2-1.

Headline: 150-960 MHz LF path (RFO_LF1/2, RFI_LF; PA_LF up to +22 dBm) +
1500-2500 MHz HF path (RFO_HF, RFI_HF; PA_HF up to +12 dBm); LoRa, FLRC,
(G)FSK, OOK, 4-FSK, O-QPSK, LR-FHSS (TX only); SPI up to 16 MHz + BUSY;
ambient -40…+85 °C (Table "Top"); 1.8-3.7 V.

Supply (§1.8.4, Fig 1-13/1-14): SIMO DC-DC (2.2 µH coil LXB-LXA, §3.6) or
LDO mode (no coil, LXA/LXB NC). Either way VDCC1 (output) -> VDCC2 (input)
and VPAX1 (output) -> VPAX2 (PA-regulator input) on the PCB, each
decoupled; VPAX1 is NEVER tied to VBAT. VR_PA (regulated PA supply,
ramped by REG_PA) feeds a CHOKE to each PA output (§1.5, Fig 1-4).
RFO_LF1 and RFO_LF2 MUST be connected together (one single-ended LF PA).

DIO5-DIO11: IRQ / RF-switch / GPIO / clock / TX-RX trigger, set with
SetDioFunction in Standby RC only. After POR/reset DIO5 and DIO6 are
PULLED UP (others Hi-Z) - don't put a switch control on them unless that
default is safe (§5.1.1, §6.8.1). SetDioRfSwitchConfig masks: standby,
rx_lf, tx_lf, rx_hf, tx_hf.

Reference design (§23.4, Fig 23-1): switchless direct-tie, 32 MHz crystal
+ NTC, series R on host lines (220-470 ohm); RF L/C values only in the
Semtech ref BOM. A TCXO is "essential" below -20 °C / above +70 °C (§23.3).
Calibration: image cal needed for >10 MHz or >10 °C change; PLL/AAF for
>50 MHz or ±20 °C; CalibFE (0x0123) up to 3 frequencies, 4 MHz steps.
"""


def add_lr2021imltrt(design, ref: str, **overrides) -> Chip:
    """Semtech LR2021IMLTRT — LoRa Plus sub-GHz + 2.4 GHz transceiver,
    SPI host interface, QFN-32 5×5 mm (QFN50P500X500X100-33N-D)."""
    pn = "LR2021IMLTRT"
    fp = _samacsys_qfn_footprint(
        pn, "QFN50P500X500X100-33N-D.kicad_mod",
        name="QFN50P500X500X100-33N-D", package_class="QFN-32 5x5 + EP",
        pitch_mm=0.5, size_mm=(5.0, 5.0), height_mm=1.0)
    P = Pin
    pins = [
        P(num="1",  name="VR_PA",   type="power",  note="Regulated supply for all PAs: feeds a choke to each PA output; decouple"),
        P(num="2",  name="VPAX2",   type="power",  note="Supply input of the PA regulator - connect to VPAX1"),
        P(num="3",  name="NTC",     type="passive", note="Reference-temperature NTC sense (optional)"),
        P(num="4",  name="XTA",     type="passive", note="32 MHz crystal or external reference (TCXO) input"),
        P(num="5",  name="XTB",     type="passive", note="32 MHz crystal (NC with a TCXO)"),
        P(num="6",  name="VTCXO/VNTC", type="power", aliases=["VTCXO"], note="TCXO supply output (REG_TCXO) / NTC supply"),
        P(num="7",  name="DIO11",   type="io"),
        P(num="8",  name="DIO10",   type="io"),
        P(num="9",  name="DIO9",    type="io"),
        P(num="10", name="DIO8",    type="io"),
        P(num="11", name="DIO7",    type="io"),
        P(num="12", name="VDCC1",   type="power",  note="SIMO/LDO output - connect to VDCC2"),
        P(num="13", name="VPAX1",   type="power",  note="SIMO/LDO output for the PA supply - connect to VPAX2 (never to VBAT)"),
        P(num="14", name="LXB",     type="passive", note="SIMO coil (2.2 µH to LXA); NC in LDO mode"),
        P(num="15", name="GND_DCC", type="ground"),
        P(num="16", name="LXA",     type="passive", note="SIMO coil (2.2 µH to LXB); NC in LDO mode"),
        P(num="17", name="VBAT",    type="power",  note="Main supply 1.8-3.7 V"),
        P(num="18", name="DIO6",    type="io", note="pulled UP after POR/reset (DS §5.1.1)"),
        P(num="19", name="DIO5",    type="io", note="pulled UP after POR/reset (DS §5.1.1)"),
        P(num="20", name="NRESET",  type="input",  note="Reset, active low"),
        P(num="21", name="MISO",    type="output"),
        P(num="22", name="MOSI",    type="input"),
        P(num="23", name="SCK",     type="input"),
        P(num="24", name="NSS",     type="input"),
        P(num="25", name="BUSY",    type="output", note="Busy indicator — poll low before each SPI command"),
        P(num="26", name="VDCC2",   type="power",  note="Regulated supply input - from VDCC1"),
        P(num="27", name="RFO_LF2", type="output", note="LF PA output - MUST be tied to RFO_LF1 (single-ended)"),
        P(num="28", name="RFO_LF1", type="output", note="LF PA output (up to +22 dBm) - tied to RFO_LF2"),
        P(num="29", name="RFI_LF",  type="input",  note="Sub-GHz RX input"),
        P(num="30", name="GND",     type="ground"),
        P(num="31", name="RFI_HF",  type="input",  note="HF RX input (1.5-2.5 GHz)"),
        P(num="32", name="RFO_HF",  type="output", note="HF PA output (1.5-2.5 GHz, up to +12 dBm); needs a VR_PA choke"),
        P(num="33", name="EP",      type="ground", aliases=["GND_EP"], note="Exposed ground pad"),
    ]
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="Semtech", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=("LoRa Plus multi-band transceiver: 150-960 MHz (+22 dBm) "
                     "+ 1.6-2.5 GHz (+12 dBm), LoRa/FLRC/FSK/O-QPSK, SPI, "
                     "QFN-32 5×5 mm"),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        fab_country="TW (assembly)",  # Mouser IN COO, 2026-11-18
        currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None, standards=["RoHS"], eccn=None, itar=None,
        package="QFN-32 5x5", size_mm=(5.0, 5.0), height_mm=1.0,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=3.7, vcc_nominal_v=3.3,
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=None,
        pins=pins, footprint=fp, note=_LR2021_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# pSemi (Murata) PE42442A-Z — UltraCMOS SP4T absorptive RF switch,
# 30 MHz–6 GHz, QFN-24 4×4 mm + exposed pad
# ═════════════════════════════════════════════════════════════════════════

_PE42442_NOTE = """\
Datasheet: pSemi PE42442 Product Specification DOC-33414-9.01 (10/2025),
vendored. SamacSys LIB v1.1 (2020-08-20) checked against it: all 24 pins +
EP identical; footprint 0.5 mm pitch, 0.30 mm pads, EP 2.75 mm match the
recommended land pattern (SamacSys pads 0.8 mm long vs 0.6 mm in the DS -
0.2 mm longer toe outward, inner edge identical). SamacSys lists the maker
as "Peregrine Semiconductor" (pSemi's former name).

Absorptive: unselected RF ports are terminated in 50 ohm. Operating range
30-6000 MHz, -40…+125 °C, VDD 2.3-5.5 V (110 µA), VIH 1.17-3.6 V (3.3 V
GPIO OK). RF input 33 dBm CW at 105 °C (terminated ports 24 dBm). IL 0.85 /
0.90 / 1.10 / 1.15 dB at 450 / 900 / 2100 / 2700 MHz (+25 °C; 1.18 / 1.50 dB
at 900 / 2700 MHz at 125 °C). Isolation RFC-RFx 61 / 55 / 52 dB at 900 /
2100 / 2700 MHz. Switching 255 ns.

Control (DS Tables 5/6): 2-pin control recommended for new designs -
V3 (pin 19) to GND; V2 V1 = 01 RF1, 10 RF2, 11 RF3, 00 RF4 (so pull-downs
park it on RF4). 3-pin control adds ALL-OFF (V3=1 with V2V1 != 00).
VSS_EXT (pin 20) to GND = internal negative-voltage generator (max 25 kHz
switching rate, ~-120 dBm spur). RF pins must sit at 0 VDC (DC blocks
only if DC is present). EVK: each control line 0 ohm + 100 pF + 1 Mohm
pull-down; VDD 100 pF + 1 µF. MSL1.
"""


def add_pe42442a_z(design, ref: str, **overrides) -> Chip:
    """pSemi (Murata) PE42442A-Z — absorptive SP4T RF switch, 30 MHz–6 GHz,
    2/3-pin CMOS control, QFN-24 4×4 mm (QFN50P400X400X80-25N-D)."""
    pn = "PE42442A-Z"
    fp = _samacsys_qfn_footprint(
        pn, "QFN50P400X400X80-25N-D.kicad_mod",
        name="QFN50P400X400X80-25N-D", package_class="QFN-24 4x4 + EP",
        pitch_mm=0.5, size_mm=(4.0, 4.0), height_mm=0.8)
    P = Pin
    gnd = {"1", "2", "3", "4", "6", "7", "9", "10", "12", "13", "15", "21", "23", "24"}
    named = {
        "5":  P(num="5",  name="RF4", type="io", note="RF port 4 (V2V1=00, the pull-down default); 0 VDC"),
        "8":  P(num="8",  name="RF3", type="io", note="RF port 3 (V2V1=11); 0 VDC"),
        "11": P(num="11", name="RF2", type="io", note="RF port 2 (V2V1=10); 0 VDC"),
        "14": P(num="14", name="RF1", type="io", note="RF port 1 (V2V1=01); 0 VDC"),
        "16": P(num="16", name="VDD", type="power", note="Supply 2.3-5.5 V"),
        "17": P(num="17", name="V1", type="input", note="Control logic input 1"),
        "18": P(num="18", name="V2", type="input", note="Control logic input 2"),
        "19": P(num="19", name="V3", type="input", note="Control logic input 3 - GND for 2-pin control"),
        "20": P(num="20", name="VSS_EXT", type="power", aliases=["VSSEXT"],
                note="GND = internal negative supply; or external -3.2…-3.6 V (bypass mode)"),
        "22": P(num="22", name="RFC", type="io", note="RF common; 0 VDC"),
        "25": P(num="25", name="EP", type="ground", aliases=["GND_EP"], note="Exposed ground pad"),
    }
    pins = []
    for n in sorted({p.num for p in fp.pads}, key=int):
        if n in named:
            pins.append(named[n])
        elif n in gnd:
            pins.append(P(num=n, name=f"GND_{n}", type="ground"))
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="pSemi (Murata)", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=("SP4T absorptive RF switch, 30 MHz-6 GHz, high isolation, "
                     "33 dBm, 2/3-pin CMOS control, QFN-24 4×4 mm"),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None, standards=["RoHS", "MSL1"], eccn=None, itar=None,
        package="QFN-24 4x4", size_mm=(4.0, 4.0), height_mm=0.8,
        temp_range_c=(-40, 125),
        body_material=None, lead_material=None,
        voltage_rating_v=5.5, vcc_nominal_v=3.3,
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=None,
        pins=pins, footprint=fp, note=_PE42442_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# pSemi (Murata) PE64906B-Z — 5-bit digitally tunable capacitor (DTC),
# 100-3000 MHz, 10-lead 2×2×0.55 mm QFN + EP
# ═════════════════════════════════════════════════════════════════════════

_PE64906_NOTE = """\
Datasheet: pSemi PE64906 Product Specification DOC-82123-4.03 (09/2026),
vendored. SamacSys LIB v3.1 (2019-01-09) supplies the symbol and 3D model;
its pin numbering matches DS Table 9 / Fig 19 (1-2 RF-, 3/10 GND, 4 VDD,
5 SCL, 6 SEN, 7 SDA, 8-9 RF+, 11 = EP GND).

⚠ FOOTPRINT: the SamacSys land puts the side pads at ±1.25 mm, 0.7 mm long
(0.9-1.6 mm from centre) — only ~0.1 mm over the 0.20 mm leads (0.8-1.0 mm).
The pads here follow the DS "recommended land pattern" (Fig 20): side pads
0.45 × 0.25 mm centred at ±0.975 mm, pins 5/10 0.25 × 0.45 mm at ±0.975 mm,
EP 0.95 × 0.95 mm, 0.5 mm pitch, 2.40 mm overall.

Shunt C (RF- grounded) 0.90-4.60 pF in 32 states, 119 fF steps (at 100 MHz;
tolerance Cmin 0.81-0.99, Cmax 3.68-5.52 pF). Q at 1710-2170 MHz: 40 at
Cmin, 13 at Cmax (Ls removed). SRF 7.9 GHz at state 0. VDD 2.30-4.80 V,
140 µA typ (25 µA standby). 3-wire serial (SCL/SDA/SEN, 8-bit telegram MSB
first, latched on SEN falling edge; SCL ≥ 38.4 ns period); SCL/SDA/VDD may be
shared between DTCs with a dedicated SEN each (DS Fig 10). Switching ≤ 12 µs,
startup/wake ≤ 70 µs. RF- needs a DC path to GND. MSL1, -40…+85 °C.
"""


def _pe64906_footprint() -> Footprint:
    """DS recommended land pattern (Fig 20), orientation as SamacSys / Fig 19:
    pins 1-4 down the left, 5 bottom, 6-9 up the right, 10 top, EP 11."""
    side = (0.45, 0.25)
    pads = [Pad(num=str(n), position_mm=(-0.975, y), size_mm=side, shape="rect", layer="F.Cu")
            for n, y in zip((1, 2, 3, 4), (-0.75, -0.25, 0.25, 0.75))]
    pads.append(Pad(num="5", position_mm=(0.0, 0.975), size_mm=(0.25, 0.45),
                    shape="rect", layer="F.Cu"))
    pads += [Pad(num=str(n), position_mm=(0.975, y), size_mm=side, shape="rect", layer="F.Cu")
             for n, y in zip((6, 7, 8, 9), (0.75, 0.25, -0.25, -0.75))]
    pads.append(Pad(num="10", position_mm=(0.0, -0.975), size_mm=(0.25, 0.45),
                    shape="rect", layer="F.Cu"))
    pads.append(Pad(num="11", position_mm=(0.0, 0.0), size_mm=(0.95, 0.95),
                    shape="rect", layer="F.Cu"))
    return Footprint(
        name="QFN50P200X200X60-11N-D_DS", package_class="QFN-10 2x2 + EP",
        pads=pads,
        body_outline=[(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
        courtyard=[(-1.45, -1.45), (1.45, -1.45), (1.45, 1.45), (-1.45, 1.45)],
        pitch_mm=0.5, size_mm=(2.0, 2.0), height_mm=0.6,
        model_3d_path=datasheet_ref("PE64906B-Z", "PE64906B-Z.stp"),
        source="custom")


def add_pe64906b_z(design, ref: str, **overrides) -> Chip:
    """pSemi (Murata) PE64906B-Z — 5-bit DTC, 0.9-4.6 pF shunt, 100-3000 MHz,
    3-wire serial control, 10-lead 2×2 mm QFN."""
    pn = "PE64906B-Z"
    fp = _pe64906_footprint()
    P = Pin
    pins = [
        P(num="1", name="RF-_1", type="io", aliases=["RF-"], note="RF− (tie 1+2; GND in shunt use)"),
        P(num="2", name="RF-_2", type="io", note="RF− (tie 1+2)"),
        P(num="3", name="GND_1", type="ground"),
        P(num="4", name="VDD", type="power", note="Supply 2.30-4.80 V"),
        P(num="5", name="SCL", type="input", note="Serial clock"),
        P(num="6", name="SEN", type="input", note="Serial latch enable (state applied on falling edge)"),
        P(num="7", name="SDA", type="input", note="Serial data"),
        P(num="8", name="RF+_1", type="io", aliases=["RF+"], note="RF+ (tie 8+9)"),
        P(num="9", name="RF+_2", type="io", note="RF+ (tie 8+9)"),
        P(num="10", name="GND_2", type="ground"),
        P(num="11", name="EP", type="ground", note="Exposed pad, GND"),
    ]
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="pSemi (Murata)", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=("Digitally tunable capacitor, 5-bit, 0.9-4.6 pF shunt, "
                     "100-3000 MHz, 3-wire serial, QFN-10 2×2 mm"),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None, standards=["RoHS", "MSL1", "ESD HBM 2 kV"], eccn=None, itar=None,
        package="QFN-10 2x2", size_mm=(2.0, 2.0), height_mm=0.6,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=4.8, vcc_nominal_v=3.3,
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=None,
        pins=pins, footprint=fp, note=_PE64906_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# S4 transverter parts (2026-11-18, user-approved): 4.4–5.0 GHz on slot S4.
# Sourcing rule (user): no Chinese chips — incl. die fab / assembly / test in
# China; EU/US preferred. `fab_country` records the verified (or best-known)
# manufacturing sites; tests reject "CN" on the radio/transverter parts.
# ═════════════════════════════════════════════════════════════════════════

_BGS12P2L6_NOTE = """\
Datasheet: Infineon BGS12P2L6 (vendored BGS12P2L6.pdf) + PG-TSLP-6-4 land
pattern (PG-TSLP-6-4.pdf). SamacSys LIB v2.1 footprint matches the Infineon
land: 6 × 0.25 × 0.25 mm pads, 0.4 mm pitch, rows ±0.2 mm.

0.05-6 GHz SPDT, RF input up to 37 dBm (abs max 38 dBm), VDD 1.65-3.4 V
(65 µA typ), CTRL low ≤ 0.45 V / high ≥ 1.0 V, -40…+85 °C.
IL 0.31 / 0.39 / 0.47 dB typ at 2.17-2.7 / 3.3-3.8 / 4.4-5.0 GHz; isolation
RFin-RFx 26-29 dB, RF1-RF2 31-35 dB at 4.4-5.0 GHz. No supply decoupling
required (DS). Power-up settling 5 µs typ.

Pins: 1 RF2, 2 GND, 3 RF1, 4 VDD, 5 RFin, 6 CTRL. Truth table: CTRL 0 →
RFIN-RF1, CTRL 1 → RFIN-RF2 — same pin names / logic as the BGS12WN6 it
replaces (2026-11-18: BGS12WN6 rejected — Infineon lists CN + MY assembly).
Origin (Infineon product page / Mouser, 2026-11-18): wafer DE, assembly MY.
"""


def add_bgs12p2l6e6327xtsa1(design, ref: str, **overrides) -> Chip:
    """Infineon BGS12P2L6E6327XTSA1 — 0.05–6 GHz SPDT, 37 dBm, on-chip CMOS
    logic, PG-TSLP-6-4 (0.7 × 1.1 × 0.31 mm). Pin-name-compatible with the
    BGS12WN6 (RF1/RF2/RFIN/CTRL/VDD/GND, CTRL 0 → RF1)."""
    pn = "BGS12P2L6E6327XTSA1"
    fp = _samacsys_qfn_footprint(
        pn, f"{pn}.kicad_mod", name="PG-TSLP-6-4", package_class="PG-TSLP-6-4",
        pitch_mm=0.4, size_mm=(1.1, 0.7), height_mm=0.31)
    pins = [
        Pin(num="1", name="RF2", type="io", note="RF throw 2 (CTRL=1); no DC"),
        Pin(num="2", name="GND", type="ground"),
        Pin(num="3", name="RF1", type="io", note="RF throw 1 (CTRL=0); no DC"),
        Pin(num="4", name="VDD", type="power", note="1.65-3.4 V logic supply"),
        Pin(num="5", name="RFIN", type="io", aliases=["RFin"], note="RF common; no DC"),
        Pin(num="6", name="CTRL", type="input", note="0 → RF1, 1 → RF2"),
    ]
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="Infineon", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description="SPDT RF switch, 0.05-6 GHz, 37 dBm, CMOS control, PG-TSLP-6-4",
        datasheet=datasheet_ref(pn, "BGS12P2L6.pdf"),
        fab_country="DE (wafer), MY (assembly)", currency=None, price_1pc=None,
        price_20kpc=None, weight_g=None,
        standards=["RoHS", "Halogen-free", "ESD HBM ±1 kV", "ESD CDM ±1 kV"],
        eccn=None, itar=None,
        package="PG-TSLP-6-4", size_mm=(1.1, 0.7), height_mm=0.31,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=3.6, vcc_nominal_v=3.3,
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=125.0,
        pins=pins, footprint=fp, note=_BGS12P2L6_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


_LTC5549_NOTE = """\
Datasheet: ADI (Linear) LTC5549 rev A "5549fa" (vendored LTC5549IUDB.pdf).
SamacSys LIB (UDB_VARIATIONA) footprint checked against DS p18 "Recommended
solder pad": 12 × 0.25 mm pads at 0.5 mm, exposed pad 0.77 × 0.25 mm (it
really is that small — DS Detail B).

Passive double-balanced mixer, up- OR down-conversion. RF 2-14 GHz, LO
1-12 GHz (0 dBm ±6 dBm drive, internal buffer; X2 pin enables an LO doubler),
IF 0.5-6 GHz. Conversion loss 8.0 dB at 5.8 GHz (7.8 dB at 2 GHz); up-
conversion input P1dB +15.5 dBm, down-conversion IIP3 +28.2 dBm at 5.8 GHz.
LO-RF leakage < -30 dBm, LO-IF < -27 dBm. VCC 3.3 V, 115 mA typ / 136 mA
max; EN > 1.2 V on, < 0.3 V off (376 kΩ pull-down), turn-on 0.2 µs /
off 0.1 µs (TDD). All RF/IF/LO ports single-ended 50 Ω, internal
transformers with low DC resistance to GND → series DC blocks required.
Tc -40…+105 °C.

Pins: 1/3/4/6/10/12 + EP 13 GND, 2 IF, 5 RF, 7 EN, 8 X2, 9 VCC, 11 LO.
Origin (Farnell BE / Mouser DK, 2026-11-18): PH / TH assembly.
"""


def add_ltc5549iudb(design, ref: str, **overrides) -> Chip:
    """ADI LTC5549IUDB#TRMPBF — 2–14 GHz passive double-balanced mixer with
    LO buffer + optional LO doubler, up/down-conversion, 3.3 V / 115 mA,
    12-lead 3 × 2 mm QFN (UDB)."""
    pn = "LTC5549IUDB"
    fp = _samacsys_qfn_footprint(
        pn, "UDB_VARIATIONA.kicad_mod", name="UDB_VARIATIONA",
        package_class="QFN-12 3x2 (UDB) + EP", pitch_mm=0.5, size_mm=(3.0, 2.0),
        height_mm=0.75)
    gnd = {"1": "GND_1", "3": "GND_2", "4": "GND_3", "6": "GND_4",
           "10": "GND_5", "12": "GND_6", "13": "EP"}
    named = {
        "2": Pin(num="2", name="IF", type="io", note="IF port 0.5-6 GHz, 50 Ω; DC block"),
        "5": Pin(num="5", name="RF", type="io", note="RF port 2-14 GHz, 50 Ω; DC block"),
        "7": Pin(num="7", name="EN", type="input", note="> 1.2 V on, < 0.3 V off; 376 kΩ pull-down"),
        "8": Pin(num="8", name="X2", type="input", note="LO doubler: > 1.2 V on; 376 kΩ pull-down"),
        "9": Pin(num="9", name="VCC", type="power", note="3.3 V, 115 mA"),
        "11": Pin(num="11", name="LO", type="input", note="LO 1-12 GHz, 0 dBm; DC block (pin ~1.6 V)"),
    }
    pins = [named[n] if n in named else Pin(num=n, name=gnd[n], type="ground")
            for n in sorted({p.num for p in fp.pads}, key=int)]
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="Analog Devices", manf_pn="LTC5549IUDB#TRMPBF", canonical_id=canonical_id(pn),
        name=pn, value="LTC5549",
        description=("Mixer 2-14 GHz RF / 0.5-6 GHz IF, up/down-conversion, LO buffer "
                     "+ doubler, 3.3 V 115 mA, QFN-12 3x2"),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        fab_country="PH/TH (assembly)", currency=None, price_1pc=None,
        price_20kpc=None, weight_g=None, standards=["RoHS"], eccn=None, itar=None,
        package="QFN-12 3x2 (UDB)", size_mm=(3.0, 2.0), height_mm=0.75,
        temp_range_c=(-40, 105),
        body_material=None, lead_material=None,
        voltage_rating_v=4.0, vcc_nominal_v=3.3,
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=150.0,
        p_active_w=0.38,                 # 115 mA × 3.3 V (DS)
        pins=pins, footprint=fp, note=_LTC5549_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)



_LTC5552_NOTE = """\
Datasheet: ADI (Linear) LTC5552 rev F, Japanese edition "j5552f" (vendored
LTC5552IUDB.pdf; the English PDF was not retrievable 2026-11-22).
Package: UDB 12-lead 3 x 2 mm QFN, LTC DWG 05-08-1985 Rev 0 -- the SAME
drawing as the LTC5549, so the LTC5549's SamacSys land/3D model is reused.

Passive double-balanced mixer, up- OR down-conversion. RF 3-20 GHz, LO
1-20 GHz (0 dBm drive, internal LO amplifier), IF DC-6 GHz. Conversion loss
~6.9-7 dB at 4 GHz. VCC 3.0-3.6 V, 132 mA typ / 150 mA max; EN > 1.2 V on
(internal pull-down). No LO doubler.

IF is DIFFERENTIAL: IF+ (2) / IF- (3), ~25 ohm each single-ended -> 50 ohm
single-ended needs an external 1:1 balun (ADI eval: Mini-Circuits
TC1-1-13M+, 4.5 MHz-3 GHz; TCM1-83X+ to 6 GHz). IF pins are DC-coupled to
the diodes (no DC block on the balanced side). RF and LO 50 ohm; LO takes an
18 pF series cap (pin ~DC-biased).

Pinout vs LTC5549: identical except pin 3 (GND -> IF-) and pin 8
(X2 -> GND). Chosen 2026-11-22 (mixer round 18) as the buildable
replacement for the restricted LTC5549: #TRMPBF stocked at Mouser 95 /
Farnell 591 / Digi-Key 1,648 (Thailand).

Pins: 1/4/6/8/10/12 + EP 13 GND, 2 IF+, 3 IF-, 5 RF, 7 EN, 9 VCC, 11 LO.
"""


def add_ltc5552iudb(design, ref: str, **overrides) -> Chip:
    """ADI LTC5552IUDB#TRMPBF -- 3-20 GHz passive double-balanced mixer,
    0 dBm LO (internal LO amp), differential DC-6 GHz IF, up/down-conversion,
    3.3 V / 132 mA, 12-lead 3 x 2 mm QFN (UDB, same land as the LTC5549)."""
    pn = "LTC5552IUDB"
    fp = _samacsys_qfn_footprint(
        "LTC5549IUDB", "UDB_VARIATIONA.kicad_mod", name="UDB_VARIATIONA",
        package_class="QFN-12 3x2 (UDB) + EP", pitch_mm=0.5, size_mm=(3.0, 2.0),
        height_mm=0.75)
    gnd = {"1": "GND_1", "4": "GND_3", "6": "GND_4", "8": "GND_7",
           "10": "GND_5", "12": "GND_6", "13": "EP"}
    named = {
        "2": Pin(num="2", name="IF+", type="io", note="differential IF DC-6 GHz, ~25 ohm; to 1:1 balun"),
        "3": Pin(num="3", name="IF-", type="io", note="differential IF DC-6 GHz, ~25 ohm; to 1:1 balun"),
        "5": Pin(num="5", name="RF", type="io", note="RF port 3-20 GHz, 50 ohm; DC block"),
        "7": Pin(num="7", name="EN", type="input", note="> 1.2 V on; internal pull-down"),
        "9": Pin(num="9", name="VCC", type="power", note="3.3 V, 132 mA"),
        "11": Pin(num="11", name="LO", type="input", note="LO 1-20 GHz, 0 dBm; 18 pF series cap"),
    }
    pins = [named[n] if n in named else Pin(num=n, name=gnd[n], type="ground")
            for n in sorted({p.num for p in fp.pads}, key=int)]
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="Analog Devices", manf_pn="LTC5552IUDB#TRMPBF", canonical_id=canonical_id(pn),
        name=pn, value="LTC5552",
        description=("Mixer 3-20 GHz RF / DC-6 GHz differential IF, up/down-conversion, "
                     "0 dBm LO, 3.3 V 132 mA, QFN-12 3x2"),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        fab_country="TH (assembly)", currency=None, price_1pc=None,
        price_20kpc=None, weight_g=None, standards=["RoHS"], eccn=None, itar=None,
        package="QFN-12 3x2 (UDB)", size_mm=(3.0, 2.0), height_mm=0.75,
        temp_range_c=(-40, 105),
        body_material=None, lead_material=None,
        voltage_rating_v=4.0, vcc_nominal_v=3.3,
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=25.0, rth_ja_cw=None, tj_max_c=150.0,
        p_active_w=0.44,                 # 132 mA x 3.3 V (DS)
        pins=pins, footprint=fp, note=_LTC5552_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


_GRF5126_NOTE = """\
Datasheet: Guerrilla RF GRF5126 Rel. 0 (2026-01-20, vendored GRF5126.pdf) +
Custom Tune 4400-5000 MHz (2025-10-08, GRF5126_tune_4400-5000MHz.pdf).
NO SamacSys model exists (user, 2026-11-18): footprint = DS p19 "Recommended
PCB Footprint" (0.25 × 0.45 mm pads, 0.5 mm pitch, toe 0.15 mm past the
3.00 mm outline; EP 1.70 mm square with pin-1 chamfer); 3D = SamacSys model
of the package-identical GRF5109.

Two-stage GaAs pHEMT linear driver, 1.8-5 GHz by tune; VDD 3-5.5 V.
4400-5000 MHz tune @ 5 V / 110 mA (VBIAS1/2 via 2740 Ω / 2320 Ω from 5 V,
VGAIN 1.8 V = high gain): gain 31.1 / 32.6 / 31.1 dB, OP1dB 22.0 / 22.3 /
22.2 dBm, OP3dB 25.7 / 25.7 / 25.1 dBm, OIP3 32-35 dBm at 4.4 / 4.7 / 5.0
GHz (IP1dB -8…-9 dBm). Low-gain mode (VGAIN 0): ~24 dB, OP1dB ~21 dBm.
Abs max: VDD 6 V, RF in 23 dBm, Tpkg -40…+115 °C, stage dissipation
185 mW / 475 mW. VBIAS1/VBIAS2 < 0.2 V disables the stage. ESD HBM 250 V.

Pins: 1 GND, 2 RF_IN (DC block), 4 VDD1 (inductor + bypass), 10 RF_OUT/VDD
(choke), 13 VBIAS2, 14 VBIAS1, 15 VGAIN (≥ 1.0 V high gain, ≤ 0.5 V low),
3/5/6/7/8/9/11/12/16 NC (ground recommended), EP GND.
Origin: Guerrilla RF (US, fabless); assembly MY per Mouser on sibling parts
— NOT confirmed for this part (ask Guerrilla for a COO statement).
"""


def _grf5126_footprint() -> Footprint:
    """GRF5126 DS p19 recommended land: QFN-16 3 × 3, pins CCW from pin 1 at
    the top of the left side (KiCad y down)."""
    side, toe = (0.45, 0.25), 1.425          # pad spans 1.20 … 1.65 mm from centre
    ys = (-0.75, -0.25, 0.25, 0.75)
    pads = [Pad(num=str(n), position_mm=(-toe, y), size_mm=side, shape="rect", layer="F.Cu")
            for n, y in zip((1, 2, 3, 4), ys)]
    pads += [Pad(num=str(n), position_mm=(x, toe), size_mm=side[::-1], shape="rect", layer="F.Cu")
             for n, x in zip((5, 6, 7, 8), ys)]
    pads += [Pad(num=str(n), position_mm=(toe, y), size_mm=side, shape="rect", layer="F.Cu")
             for n, y in zip((9, 10, 11, 12), ys[::-1])]
    pads += [Pad(num=str(n), position_mm=(x, -toe), size_mm=side[::-1], shape="rect", layer="F.Cu")
             for n, x in zip((13, 14, 15, 16), ys[::-1])]
    pads.append(Pad(num="17", position_mm=(0.0, 0.0), size_mm=(1.70, 1.70),
                    shape="rect", layer="F.Cu"))
    # smash pads are y-UP (the exporter flips once); the list above was written
    # y-down, so mirror it — pin numbers must wind counter-clockwise in top view
    # (test_footprint_winding).
    pads = [_dc_replace(p, position_mm=(p.position_mm[0], -p.position_mm[1])) for p in pads]
    return Footprint(
        name="QFN16_3x3_GRF5126_DS", package_class="QFN-16 3x3 + EP",
        pads=pads,
        body_outline=[(-1.5, -1.5), (1.5, -1.5), (1.5, 1.5), (-1.5, 1.5)],
        courtyard=[(-1.9, -1.9), (1.9, -1.9), (1.9, 1.9), (-1.9, 1.9)],
        pitch_mm=0.5, size_mm=(3.0, 3.0), height_mm=0.85,
        model_3d_path=datasheet_ref("GRF5126", "GRF5126.stp"),
        # (2026-11-20) the vendor STEP is Y-up (height along +Y): stand it up
        model_rotate_deg=(-90.0, 0.0, 0.0),
        source="custom")


def add_grf5126(design, ref: str, **overrides) -> Chip:
    """Guerrilla RF GRF5126 — 1.8–5 GHz two-stage linear driver/PA, 37 dB,
    OP1dB ~22 dBm with the 4400–5000 MHz tune at 5 V, QFN-16 3 × 3 mm."""
    pn = "GRF5126"
    fp = _grf5126_footprint()
    named = {
        "1": Pin(num="1", name="GND", type="ground", note="internally grounded; via at the pin"),
        "2": Pin(num="2", name="RF_IN", type="input", note="DC block required"),
        "4": Pin(num="4", name="VDD1", type="power", note="via inductor + bypass (RF present)"),
        "10": Pin(num="10", name="RF_OUT", type="output", aliases=["RF_OUT/VDD"],
                  note="RF out + stage-2 VDD through an RF choke"),
        "13": Pin(num="13", name="VBIAS2", type="input", note="series R to VDD sets IDDQ2; < 0.2 V = off"),
        "14": Pin(num="14", name="VBIAS1", type="input", note="series R to VDD sets IDDQ1; < 0.2 V = off"),
        "15": Pin(num="15", name="VGAIN", type="input", note="≥ 1.0 V high gain, ≤ 0.5 V low gain"),
        "17": Pin(num="17", name="EP", type="ground", note="exposed pad: RF/DC GND + heat sink"),
    }
    pins = [named.get(str(n)) or Pin(num=str(n), name=f"NC_{n}", type="passive",
                                       note="no internal connection — ground (DS)")
            for n in range(1, 18)]
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="Guerrilla RF", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=("Linear driver/PA 1.8-5 GHz (4.4-5.0 GHz tune), 31-33 dB, "
                     "OP1dB 22 dBm @ 5 V, QFN-16 3x3"),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        fab_country="US design (fabless); MY assembly — unconfirmed for this part",
        currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=["RoHS", "MSL1", "ESD HBM 250 V"], eccn=None, itar=None,
        package="QFN-16 3x3", size_mm=(3.0, 3.0), height_mm=0.85,
        temp_range_c=(-40, 115),
        body_material=None, lead_material=None,
        voltage_rating_v=6.0, vcc_nominal_v=5.0,
        i_rms_a=None, power_rating_w=0.66,       # 185 + 475 mW stage abs max
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=170.0,
        p_active_w=0.55,                          # 5 V × 110 mA quiescent
        pins=pins, footprint=fp, note=_GRF5126_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


_GRF2073W_NOTE = """\
Datasheet: Guerrilla RF GRF2073W Rel. D (2025-09-11, vendored GRF2073W.pdf);
de-embedded S-parameters in GRF2073W_Spars.zip (for the 4.4-5.0 GHz match).
Footprint = DS p23 "Suggested PCB Footprint" (pads 0.55 × 0.25 mm at
±0.925 mm, 0.5 mm pitch, EP 0.60 × 1.20 mm) — tighter than the SamacSys
SON50P200X200X80-9N (0.3 × 0.8 pads, EP 0.65 × 1.25), which is kept only
for its 3D model.

AEC-Q100 Grade 2 ultra-low-noise LNA, 1.0-6.8 GHz by tune. Ref 5 V/70 mA:
gain 20.5 dB / OP1dB 20 dBm at 2.33 GHz; 18.5 dB / 18 dBm at 3.6 GHz; NF
~0.9-1.0 dB at 5 GHz (Guerrilla app data). VDD 0-6 V (run on 3V3 here).
Abs max: RF in 23 dBm, Tpkg -40…+105 °C, MSL1.

Pins: 1 VENABLE (series R sets IDDQ; ≤ 0.2 V = off), 2 RF_IN (match must
DC-block), 7 RF_OUT/VDD (VDD via bias inductor), 3/4/5/6/8 NC (ground
recommended), EP GND.
Origin: Guerrilla RF (US, fabless); MY assembly per Mouser on sibling parts
— NOT confirmed for this part.
"""


def _grf2073w_footprint() -> Footprint:
    side, x = (0.55, 0.25), 0.925
    ys = (-0.75, -0.25, 0.25, 0.75)
    pads = [Pad(num=str(n), position_mm=(-x, y), size_mm=side, shape="rect", layer="F.Cu")
            for n, y in zip((1, 2, 3, 4), ys)]
    pads += [Pad(num=str(n), position_mm=(x, y), size_mm=side, shape="rect", layer="F.Cu")
             for n, y in zip((5, 6, 7, 8), ys[::-1])]
    pads.append(Pad(num="9", position_mm=(0.0, 0.0), size_mm=(0.60, 1.20),
                    shape="rect", layer="F.Cu"))
    # smash pads are y-UP (the exporter flips once); the list above was written
    # y-down, so mirror it — pin numbers must wind counter-clockwise in top view
    # (test_footprint_winding).
    pads = [_dc_replace(p, position_mm=(p.position_mm[0], -p.position_mm[1])) for p in pads]
    return Footprint(
        name="DFN8_2x2_GRF2073W_DS", package_class="DFN-8 2x2 + EP",
        pads=pads,
        body_outline=[(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
        courtyard=[(-1.45, -1.25), (1.45, -1.25), (1.45, 1.25), (-1.45, 1.25)],
        pitch_mm=0.5, size_mm=(2.0, 2.0), height_mm=0.75,
        model_3d_path=datasheet_ref("GRF2073W", "GRF2073W.stp"),
        source="custom")


def add_grf2073w(design, ref: str, **overrides) -> Chip:
    """Guerrilla RF GRF2073W — AEC-Q100 ultra-low-noise LNA, 1.0–6.8 GHz,
    enable pin, DFN-8 2 × 2 mm."""
    pn = "GRF2073W"
    fp = _grf2073w_footprint()
    named = {
        "1": Pin(num="1", name="VENABLE", type="input", note="series R sets IDDQ; ≤ 0.2 V = off"),
        "2": Pin(num="2", name="RF_IN", type="input", note="match must DC-block"),
        "7": Pin(num="7", name="RF_OUT", type="output", aliases=["RF_OUT/VDD"],
                 note="RF out; VDD via bias inductor"),
        "9": Pin(num="9", name="EP", type="ground", note="exposed pad GND"),
    }
    pins = [named.get(str(n)) or Pin(num=str(n), name=f"NC_{n}", type="passive",
                                       note="no internal connection — ground (DS)")
            for n in range(1, 10)]
    _check_pins_vs_pads(pn, pins, fp)
    fields = dict(
        manf="Guerrilla RF", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description="Ultra-low-noise LNA 1.0-6.8 GHz, AEC-Q100 Gr 2, enable pin, DFN-8 2x2",
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        fab_country="US design (fabless); MY assembly — unconfirmed for this part",
        currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=["RoHS", "MSL1", "AEC-Q100 Grade 2"], eccn=None, itar=None,
        package="DFN-8 2x2", size_mm=(2.0, 2.0), height_mm=0.75,
        temp_range_c=(-40, 105),
        body_material=None, lead_material=None,
        voltage_rating_v=6.0, vcc_nominal_v=3.3,
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=170.0,
        pins=pins, footprint=fp, note=_GRF2073W_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def _tcxo_2016_footprint() -> Footprint:
    """Generic 2.0 × 1.6 mm 4-pad TCXO land (JEDEC-style, pads 1-4 CCW)."""
    pads = [Pad(num=n, position_mm=(x, y), size_mm=(0.65, 0.55), shape="rect", layer="F.Cu")
            for n, x, y in (("1", -0.725, 0.525), ("2", 0.725, 0.525),
                            ("3", 0.725, -0.525), ("4", -0.725, -0.525))]
    return Footprint(
        name="TCXO_2016_4PAD", package_class="SMD 2016 4-pad",
        pads=pads,
        body_outline=[(-1.0, -0.8), (1.0, -0.8), (1.0, 0.8), (-1.0, 0.8)],
        courtyard=[(-1.3, -1.1), (1.3, -1.1), (1.3, 1.1), (-1.3, 1.1)],
        pitch_mm=1.45, size_mm=(2.0, 1.6), height_mm=0.8, source="project")


def add_tcxo_32m_2016(design, ref: str, **overrides) -> Chip:
    """Epson TG2016SMN 32.0000M-MCGNNM0 — 32 MHz clipped-sine TCXO, 2.0 × 1.6
    mm (2026-11-21, user: orderable at Mouser; replaces the generic
    placeholder). SnapMagic footprint + symbol vendored in
    parts/sources/TG2016SMN_32.0000M-MCGNNM0/ (no 3D model supplied).
    Pin 1 NC, 2 GND, 3 OUT (clipped sine, AC-coupled into XTA), 4 VCC —
    fed from the LR2021 VTCXO output (firmware SetTcxoMode sets the level:
    match it to this part's supply-voltage code)."""
    pn = "TG2016SMN 32.0000M-MCGNNM0"
    d_ = "TG2016SMN_32.0000M-MCGNNM0"
    fp_mod = src(d_, "OSC_TG2016SMN_32.0000M-MCGNNM0.kicad_mod")
    fp = Footprint(
        name="OSC_TG2016SMN_32.0000M-MCGNNM0", package_class="SMD 2016 TCXO",
        pads=pads_from_kicad_mod(fp_mod), body_outline=outline_polygon(fp_mod, "F.Fab"),
        courtyard=outline_polygon(fp_mod, "F.CrtYd"), size_mm=(2.0, 1.6), height_mm=0.8,
        source="snapmagic").ensure_courtyard_clearance()
    fields = dict(
        manf="Epson", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value="32MHz TCXO",
        description="Epson TG2016SMN 32 MHz clipped-sine TCXO, 2.0×1.6 mm",
        datasheet=None,
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None, standards=["RoHS"], eccn=None, itar=None,
        package="SMD 2016", size_mm=(2.0, 1.6), height_mm=0.8,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=3.6, vcc_nominal_v=3.0,   # "M" supply code = 2.8-3.3 V part: set LR2021 VTCXO to 3.0 V if this DNP fallback is fitted
        i_rms_a=None, power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=None,
        pins=[Pin(num="1", name="NC", type="nc", note="no connect"),
              Pin(num="2", name="GND", type="ground"),
              Pin(num="3", name="OUT", type="output", note="clipped sine, AC-couple"),
              Pin(num="4", name="VDD", aliases=["VCC"], type="power")],
        footprint=fp,
        note=("Epson TG2016SMN 32 MHz (Mouser-orderable). Check the supply-voltage code "
              "of MCGNNM0 against the LR2021 VTCXO setting (datasheet not vendored yet)."),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def _mirror_y(fp):
    """These lands were transcribed y-down; smash pads are y-UP (the exporter
    flips once) — mirror so the pins wind counter-clockwise in top view."""
    from dataclasses import replace as _r
    fp.pads = [_r(p, position_mm=(p.position_mm[0], -p.position_mm[1])) for p in fp.pads]
    return fp

__pe64906_footprint_raw = _pe64906_footprint


def _pe64906_footprint():
    return _mirror_y(__pe64906_footprint_raw())

__tcxo_2016_footprint_raw = _tcxo_2016_footprint


def _tcxo_2016_footprint():
    return _mirror_y(__tcxo_2016_footprint_raw())
