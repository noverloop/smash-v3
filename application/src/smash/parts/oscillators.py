"""Oscillator factories (MEMS, crystal-based).

Every value transcribed from per-part ground-truth in
`parts/sources/<PN>/`.
"""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, src, datasheet_ref,
    build_pins,
)
from smash.parts._slug import canonical_id


# ═════════════════════════════════════════════════════════════════════════
# Microchip DSC1001CI5-008.0000 — 8 MHz MEMS oscillator, 1.7-3.6 V,
# CDFN/DFN 2.5×2.0 mm 4-pad
#
# >>> Family-frequency-range caveat:
#     DSC1001/3/4 family supports 1 MHz to 150 MHz ONLY. A
#     `DSC1001CI5-032.7680` (32.768 kHz) PN does NOT exist — for
#     32.768 kHz Microchip uses the DSC6101 / DSC2311 family. See
#     parts/TODO.md for the design-intent correction.
# ═════════════════════════════════════════════════════════════════════════

_DSC1001_NOTE = """\
Datasheet extras (Microchip DSC1001/3/4, family doc shared with all
frequencies in this family). MEMS oscillator family.

This factory: **DSC1001CI5-008.0000**
  DSC1001 : standard output drive (vs DSC1003=25 pF / DSC1004=40 pF)
  C       : Industrial temperature -40 to +85 °C
            (B = Commercial -20..+70, I = Industrial -40..+85,
             E = Ext. Industrial -40..+105)
  I       : ±25 ppm frequency tolerance (10/20/25/50 ppm available)
  5       : CDFN/DFN 2.5 × 2.0 × 0.85 mm package
            (other options 3.2×2.5, 5.0×3.2, 7.0×5.0 mm)
  008.0000: 8.000 MHz output frequency

Features (datasheet p1):
  Frequency range : 1 MHz to 150 MHz   (family-wide)
  Stability       : ±10/±20/±25/±50 ppm (depends on trim)
  Operating V     : 1.7 V to 3.6 V
  Operating T     :
    Commercial    : -20 to +70 °C
    Industrial    : -40 to +85 °C
    Ext.Industrial: -40 to +105 °C
  Standby current : 15 µA max
  Operating current (1 MHz, V_DD=1.8 V) : 6 mA typ / 6.3 mA max
  MIL-STD-883 shock & vibration resistant
  AEC-Q100 reliability qualified
  Pb-Free, RoHS, REACH SVHC compliant

Absolute Max (datasheet p2):
  V_IN  : -0.3 V to V_DD + 0.3 V
  ESD   : 4 kV HBM, ±200 V MM, 1.5 kV CDM

Recommended Operating (p2):
  V_DD   : +1.7 V to +3.6 V
  Output load : R > 10 kΩ, C ≤ 15 pF

DC Characteristics (V_DD=1.8-3.3 V, T_A=+85 °C):
  Frequency (single)   : 1-150 MHz
  Aging                : ±5 ppm/year @ +25 °C
  I_DD standby         : 15 µA max @ T=+25 °C
  Output startup time  : 1.0 ms typ / 1.3 ms max @ T=+25 °C
  Output disable time  : 20 ns typ / 100 ns max
  Output duty cycle    : 45/55 % min/max
  V_IH                 : 0.75 × V_DD min
  V_IL                 : 0.25 × V_DD max
  I_DD running (8 MHz, V_DD=1.8 V): see datasheet Table 1-1
    (1 MHz → 6.0 typ / 6.3 max mA; 27 MHz → 6.5/7.1; 70 MHz → 7.2/8.5;
     150 MHz → 8.3/11.9)

Pin layout (datasheet p1 + pinmap.txt, CDFN/DFN top view):
  1 = STANDBY#   (active-low standby enable)
  2 = GND
  3 = OUT        (clock output)
  4 = V_DD       (supply)

Application notes:
  - Drop-in compatible with standard 4-pad crystal oscillator
    footprints (e.g. industry-standard 2.5×2.0 / 3.2×2.5 mm SMD osc).
  - All-silicon MEMS resonator — robust to stress / shock /
    vibration that would fracture quartz.
  - When STANDBY# is left floating, internal pull-up enables the
    output (verify in datasheet for this specific trim).

Mechanical (NOT in datasheet front page): body_material,
lead_material, weight_g, density_g_cm3, cte_ppm_k, fab_country.

Distributor (from SamacSys metadata):
  Microchip product page: www.microchip.com/DSC1001
"""


def _dsc1001ci5_footprint() -> Footprint:
    """CDFN/DFN 2.5×2.0×0.85 mm 4-pad footprint per SamacSys
    DSC1001CI50080000.kicad_mod.

    Pads at corners: ±0.95 (x) × ±1.05 (y), 0.9 × 1.0 mm each.
    Pin 1 (STANDBY#) bottom-left, going counter-clockwise:
      1 = (-0.95, -1.05)  STANDBY#
      2 = (-0.95, +1.05)  GND
      3 = (+0.95, +1.05)  OUT
      4 = (+0.95, -1.05)  V_DD
    """
    return Footprint(
        name="DSC1001CI50080000",
        package_class="CDFN-4 (2.5×2.0)",
        pads=[
            Pad(num="1", position_mm=(-0.95, 1.05), size_mm=(1.0, 0.9), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-0.95, -1.05), size_mm=(1.0, 0.9), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(0.95, -1.05), size_mm=(1.0, 0.9), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(0.95, 1.05), size_mm=(1.0, 0.9), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-1.25, -1.6), (1.25, -1.6),
                      (1.25, 1.6), (-1.25, 1.6)],
        courtyard=[(-3.0, -2.6), (2.45, -2.6),
                   (2.45, 2.6), (-3.0, 2.6)],
        pitch_mm=None,
        size_mm=(2.5, 2.0),
        height_mm=0.85,
        model_3d_path="application/src/smash/parts/sources/DSC1001CI5-008.0000/DSC1001CI5-008.0000.stp",
        source="samacsys",
        note=(
            "CDFN/DFN 2.5×2.0×0.85 mm 4-pad MEMS oscillator footprint. "
            "Pin 1 (STANDBY#) at bottom-left, going counter-clockwise."
        ),
    )


def add_dsc1001ci5_008_0000(design, ref: str, **overrides) -> Chip:
    """Microchip DSC1001CI5-008.0000 — 8 MHz MEMS oscillator,
    ±25 ppm, 1.7-3.6 V, CDFN 2.5×2.0 mm. Industrial -40..+85 °C.
    """
    fields = dict(
        manf="Microchip",
        manf_pn="DSC1001CI5-008.0000",
        canonical_id="dsc1001ci5_008_0000",
        name="DSC1001CI5-008.0000",
        value="DSC1001CI5-008.0000",
        description=(
            "8 MHz MEMS oscillator, ±25 ppm, V_DD=1.7..3.6 V, "
            "CDFN 2.5×2.0×0.85 mm 4-pad"
        ),
        datasheet="application/src/smash/parts/sources/DSC1001CI5-008.0000/DSC1001-family.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "RoHS", "Pb-Free", "REACH SVHC",
            "AEC-Q100",
            "MIL-STD-883 (shock & vibration resistant)",
            "ESD HBM 4 kV",
            "ESD MM ±200 V",
            "ESD CDM 1.5 kV",
        ],
        eccn=None, itar=None,
        package="CDFN/DFN-4 (2.5×2.0×0.85)",
        size_mm=(2.5, 2.0),
        height_mm=0.85,
        # "I" = Industrial -40..+85 °C per datasheet temp-code table
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=None,       # not explicitly listed (abs max is V_DD+0.3)
        vcc_nominal_v=None,          # caller picks 1.8 / 2.5 / 3.3 typical
        i_rms_a=0.0063,              # 8 MHz @ 1.8 V worst-case ~6.3 mA
        power_rating_w=None,
        clock_freq_hz=8.0e6,         # the headline spec
        tolerance_pct=0.0025,        # ±25 ppm = ±0.0025 %
        rth_jc_cw=None, rth_ja_cw=None,
        tj_max_c=None,
        pins=[
            # Per pinmap.txt + datasheet p1
            Pin(num="1", name="STANDBY#", aliases=["STANDBY", "STB", "OE#"],
                type="input",
                note="active-low standby; output disabled when LOW"),
            Pin(num="2", name="GND",      type="ground"),
            Pin(num="3", name="OUT",      type="output",
                note="CMOS clock output; drive R>10 kΩ, C≤15 pF"),
            Pin(num="4", name="VDD",      aliases=["V_DD"], type="power"),
        ],
        footprint=_dsc1001ci5_footprint(),
        note=_DSC1001_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_dsc1001ci5_032_0000(design, ref: str, **overrides) -> Chip:
    """Microchip DSC1001CI5-032.0000 — 32 MHz MEMS oscillator,
    ±25 ppm, 1.7-3.6 V, CDFN 2.5×2.0 mm. Industrial -40..+85 °C.

    Same package, pinout, and electrical spec as the -008.0000 variant
    — only the programmed frequency differs. Smash uses this part for
    the STM32WBA52's 32 MHz HSE (BLE PHY reference). The MEMS resonator
    survives the 1000+ g launch setback that fractures quartz crystals.
    """
    fields = dict(
        manf="Microchip",
        manf_pn="DSC1001CI5-032.0000",
        canonical_id="dsc1001ci5_032_0000",
        name="DSC1001CI5-032.0000",
        value="DSC1001CI5-032.0000",
        description=(
            "32 MHz MEMS oscillator, ±25 ppm, V_DD=1.7..3.6 V, "
            "CDFN 2.5×2.0×0.85 mm 4-pad"
        ),
        datasheet="application/src/smash/parts/sources/DSC1001CI5-008.0000/DSC1001-family.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "RoHS", "Pb-Free", "REACH SVHC",
            "AEC-Q100",
            "MIL-STD-883 (shock & vibration resistant)",
            "ESD HBM 4 kV",
            "ESD MM ±200 V",
            "ESD CDM 1.5 kV",
        ],
        eccn=None, itar=None,
        package="CDFN/DFN-4 (2.5×2.0×0.85)",
        size_mm=(2.5, 2.0),
        height_mm=0.85,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=None,
        vcc_nominal_v=None,
        # Per DSC1001 Table 1-1: 27 MHz typ 6.5 mA / max 7.1 mA; 32 MHz
        # falls between 27 and 70 MHz lines so use ~6.8 mA worst case.
        i_rms_a=0.0071,
        power_rating_w=None,
        clock_freq_hz=32.0e6,
        tolerance_pct=0.0025,
        rth_jc_cw=None, rth_ja_cw=None,
        tj_max_c=None,
        pins=[
            Pin(num="1", name="STANDBY#", aliases=["STANDBY", "STB", "OE#"],
                type="input",
                note="active-low standby; output disabled when LOW"),
            Pin(num="2", name="GND",      type="ground"),
            Pin(num="3", name="OUT",      type="output",
                note="CMOS clock output; drive R>10 kΩ, C≤15 pF"),
            Pin(num="4", name="VDD",      aliases=["V_DD"], type="power"),
        ],
        footprint=_dsc1001ci5_footprint(),
        note=_DSC1001_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_dsc1001ci5_040_0000(design, ref: str, **overrides) -> Chip:
    """Microchip DSC1001CI5-040.0000 — 40 MHz MEMS oscillator,
    ±25 ppm, 1.7-3.6 V, CDFN 2.5×2.0 mm. Industrial -40..+85 °C.

    Same package, pinout, and electrical spec as the -008/-032 variants
    — only the programmed frequency differs (40 MHz is well inside the
    DSC1001 family's 1-150 MHz range). Smash uses this part for the
    STM32MP255's 40 MHz HSE. The all-silicon MEMS resonator survives the
    1000+ g launch setback that fractures quartz crystals.
    """
    fields = dict(
        manf="Microchip",
        manf_pn="DSC1001CI5-040.0000",
        canonical_id="dsc1001ci5_040_0000",
        name="DSC1001CI5-040.0000",
        value="DSC1001CI5-040.0000",
        description=(
            "40 MHz MEMS oscillator, ±25 ppm, V_DD=1.7..3.6 V, "
            "CDFN 2.5×2.0×0.85 mm 4-pad"
        ),
        datasheet="application/src/smash/parts/sources/DSC1001CI5-008.0000/DSC1001-family.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "RoHS", "Pb-Free", "REACH SVHC",
            "AEC-Q100",
            "MIL-STD-883 (shock & vibration resistant)",
            "ESD HBM 4 kV",
            "ESD MM ±200 V",
            "ESD CDM 1.5 kV",
        ],
        eccn=None, itar=None,
        package="CDFN/DFN-4 (2.5×2.0×0.85)",
        size_mm=(2.5, 2.0),
        height_mm=0.85,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=None,
        vcc_nominal_v=None,
        # Per DSC1001 Table 1-1: 27 MHz max 7.1 mA, 70 MHz max 8.5 mA;
        # 40 MHz interpolates to ~7.5 mA worst case.
        i_rms_a=0.0075,
        power_rating_w=None,
        clock_freq_hz=40.0e6,
        tolerance_pct=0.0025,
        rth_jc_cw=None, rth_ja_cw=None,
        tj_max_c=None,
        pins=[
            Pin(num="1", name="STANDBY#", aliases=["STANDBY", "STB", "OE#"],
                type="input",
                note="active-low standby; output disabled when LOW"),
            Pin(num="2", name="GND",      type="ground"),
            Pin(num="3", name="OUT",      type="output",
                note="CMOS clock output; drive R>10 kΩ, C≤15 pF"),
            Pin(num="4", name="VDD",      aliases=["V_DD"], type="power"),
        ],
        footprint=_dsc1001ci5_footprint(),
        note=_DSC1001_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# SiTime SiT1630AE-S6-DCC-32.768E — 32.768 kHz ultra-low-power MEMS osc
# Replaces the hallucinated `DSC1001CI5-032.7680` (DSC1001 family is
# 1 MHz minimum). SOT23-5 package.
# ═════════════════════════════════════════════════════════════════════════

def add_sit1630ae_s6_dcc_32_768e(design, ref: str, **overrides) -> Chip:
    """SiTime SiT1630AE-S6-DCC-32.768E — 32.768 kHz ultra-low-power
    MEMS oscillator, 1.0 µA typ, 1.5-3.63 V supply, SOT23-5 package.

    This is the **datasheet-correct replacement for the hallucinated
    `DSC1001CI5-032.7680`** PN that earlier system.py revisions
    referenced (Microchip's DSC1001/3/4 family is 1 MHz to 150 MHz
    only — 32.768 kHz is below their minimum).

    Order-code decode (`SiT1630AE-S6-DCC-32.768E`, per SiTime convention):
      SiT1630 : family (32.768 kHz / 16.384 kHz oscillator)
      A       : silicon revision
      E       : industrial temp -40..+85 °C
      S6      : SOT23-5 package (vs SMD-4 2.0×1.2 mm option)
      DCC     : Vdd 1.8..3.63 V, ±100 ppm stability over temperature
      32.768  : output frequency in kHz
      E       : ±20 ppm initial tolerance

    Sourcing note: SiTime is US-headquartered but uses TSMC Taiwan for
    the analog ASIC interface. The MEMS resonator itself is Bosch-process
    (Singapore / Germany). Verify against Smash's TW exclusion before
    production lock-in — may need to swap to a Microchip DSC2311 or
    DSC6101 if the TSMC dependency is a sourcing-policy violation.
    """
    pn = "SiT1630AE-S6-DCC-32.768E"
    part_dir = pn   # filesystem-safe
    sym = src(part_dir, "SiT1630AE-S6-DCC-32_768.kicad_sym")
    fp_mod = src(part_dir, "SOT-23_5pins.kicad_mod")
    # Pin names parsed verbatim from SamacSys KiCad sym (authoritative).
    # SamacSys naming: 1=GND, 2=NC/GND_1, 3=NC/GND_2, 4=VDD, 5=CLK_OUT
    # — matches SiT1630 datasheet Table 2 (SOT23-5 column).
    pins = build_pins(
        sym,
        types={
            "1": "ground",
            # Per SiT1630 datasheet (rev 1.3, Feb 2018) Table 2:
            # pins 2 and 3 = "NC/GND, Connect to GND or leave floating".
            # Type as 'reserved' so the validator allows either floating
            # OR a GND tie — datasheet sanctions both. `nc` would forbid
            # the GND tie our wakeup_board build uses.
            "2": "reserved",
            "3": "reserved",
            "4": "power",
            "5": "output",
        },
        aliases={
            "2": ["NC_2", "NC1", "NC/GND"],
            "3": ["NC_3", "NC2", "NC/GND"],
            "4": ["Vdd", "VCC"],
            "5": ["OUT", "CLK", "CLK Out"],
        },
        notes={
            "2": "datasheet: connect to GND or leave floating",
            "3": "datasheet: connect to GND or leave floating",
        },
    )
    fields = dict(
        manf="SiTime", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "32.768 kHz MEMS oscillator, 1.0 µA typ, ±20 ppm initial / "
            "±100 ppm over -40..+85 °C, Vdd=1.8..3.63 V, SOT23-5"
        ),
        datasheet=datasheet_ref(part_dir, "SiT1630.pdf"),
        package="SOT-23-5",
        size_mm=(2.9, 1.6),
        height_mm=1.45,
        temp_range_c=(-40, 85),       # 'E' grade per order code
        voltage_rating_v=3.63,         # Vdd max
        vcc_nominal_v=3.3,             # typical Smash rail
        i_rms_a=1.4e-6,                # 1.4 µA max @ -40..+85 °C
        clock_freq_hz=32768.0,
        tolerance_pct=0.002,            # ±20 ppm initial = ±0.002 %
        standards=["RoHS", "REACH", "Pb-Free"],
        pins=pins,
        footprint=Footprint(
            name="SOT-23_5pins",
            package_class="SOT-23-5",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.95,
            size_mm=(2.9, 1.6),
            height_mm=1.45,
            model_3d_path=src(part_dir, "SiT1630AE-S6-DCC-32.768.stp"),
            source="SamacSys ECAD archive (SiTime SiT1630AE-S6-DCC-32.768)",
            note=(
                "SamacSys-authoritative SOT-23-5 land pattern with "
                "datasheet-faithful pad asymmetry — pads 1-4 are 0.55 x "
                "1.30 mm but pad 5 (CLK_OUT) is 0.50 x 1.30 mm per the "
                "SiT1630 datasheet recommended pattern. Courtyard sized "
                "per IPC-7351 density-N. STEP 3D model included."
            ),
        ),
        note=(
            "SiTime SiT1630 — ultra-low-power 32.768 kHz MEMS osc, "
            "datasheet rev 1.3 (2018-02-09). Replaces the hallucinated "
            "`DSC1001CI5-032.7680` referenced in earlier Smash system.py "
            "revisions.\n\n"
            "Key features (datasheet):\n"
            "  - Initial tolerance : ±20 ppm  ('E' suffix)\n"
            "  - Stability over T  : ±100 ppm (-40..+85 °C, 'DCC' code)\n"
            "  - Operating current : 1.0 µA typ / 1.4 µA max @ +85 °C\n"
            "  - 25 °C aging       : ±1 ppm in first year\n"
            "  - Vdd range         : 1.5 V to 3.63 V (DCC = 1.8-3.63 V)\n"
            "  - Start-up time     : 300 ms typ / 450 ms max @ +85 °C\n"
            "  - Internal Vdd filtering — NO external bypass cap required\n\n"
            "Smash use: LSE (Low-Speed External) clock for STM32H562 "
            "(flight_board) and possibly the STM32MP255 (companion_compute) "
            "RTC. Configured in bypass mode (single-ended clock into "
            "OSC32_IN, OSC32_OUT NC).\n\n"
            "Order code decode in the docstring above. Symbol + footprint + "
            "STEP 3D model all from the SamacSys SiT1630AE-S6-DCC-32.768 "
            "ECAD archive (pulled 2026-05-25). Earlier revisions of this "
            "factory reused the LMV331IDBVR SOT-23-5 land pattern; the "
            "SamacSys version is now used in its place because it captures "
            "the datasheet's pad-5 asymmetry (0.50 mm vs 0.55 mm for pads "
            "1-4) that the JEDEC reuse missed.\n\n"
            ">>> Sourcing flag: SiTime's analog ASIC uses TSMC Taiwan; "
            "MEMS resonator is Bosch (SG/DE). Verify against the Smash "
            "TW exclusion before fab lock-in (system.py header line 19). "
            "If unacceptable, swap to Microchip DSC2311 or DSC6101 (32 "
            "kHz capable, USA-fab) — would require separate factory."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
