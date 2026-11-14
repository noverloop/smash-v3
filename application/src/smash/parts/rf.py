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
