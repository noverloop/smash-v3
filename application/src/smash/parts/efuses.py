"""eFuse (current-limited power switch) factories."""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments TPS25940AQRVCTQ1 — 2.7-18 V eFuse with short-to-battery
# protection, AEC-Q100 grade 1, WQFN-20 (3×4 mm)
# ═════════════════════════════════════════════════════════════════════════

_TPS25940A_NOTE = """\
Datasheet extras (TI TPS25940-Q1 family, SLVSDJ0E, rev Jan 2021).

Family covered by this datasheet (p1 title):
  TPS25940-Q1   : standard eFuse — auto-retry on fault
  TPS25940A-Q1  : auto-retry  (this factory — TPS25940AQRVCTQ1)
  TPS25940L-Q1  : latch-off on fault (one-shot — requires power cycle)
  TPS259401A-Q1 : auto-retry variant with different retry timing
All in WQFN-20 (3×4 mm) RVC package.

Headline features (p1):
  Qualified for automotive — AEC-Q100 grade 1 (-40 to +125 °C ambient)
  AEC-Q100 HBM Classification Level 2
  AEC-Q100 CDM Classification Level C5
  2.7-V to 18-V operating voltage, 20 V abs max
  Total R_ON 42 mΩ typ
  0.6-A to 5.3-A adjustable current limit (±8 %)
  IMON current indicator output, ±8 % accuracy
  Adjustable UV/OV thresholds (±2 %)
  Reverse current blocking with 1 µs reverse voltage shutoff
  Programmable dVo/dt control
  Power-good (PGOOD) and fault (FLT) outputs
  Short-to-battery and short-to-ground protection

Absolute Max Ratings (p5 §7.1):
  IN, OUT, PGTH, PGOOD, EN/UVLO, OVP, DEVSLP, FLT : -0.3 to +20 V
  IN, OUT (10 ms transient)                       : 22 V
  dVdT, ILIM                                      : -0.3 to +3.6 V
  IMON                                            : -0.3 to +7 V
  Sink current (PGOOD, FLT, dVdT)                 : 10 mA
  I_MAX continuous switch current @ T_A=85 °C     : 4.78 A
  Source current (dVdT, ILIM, IMON)               : internally limited
  T_J max                                         : 150 °C
  T_STG                                           : -65 to +150 °C

Pin layout (datasheet + pinmap.txt, WQFN-20, all 5 OUT pads paralleled,
all 5 IN pads paralleled — must all be soldered to maximise current
handling and minimise R_ON):
   1 = DEVSLP   (deep-sleep mode pin)
   2 = PGOOD    (power-good output, open-drain)
   3 = PGTH     (power-good threshold input)
   4-8  = OUT_1..OUT_5  (output, 5× paralleled)
   9-13 = IN_1..IN_5    (input,  5× paralleled)
  14 = EN        (enable / undervoltage lockout)
  15 = OVP       (overvoltage protection threshold)
  16 = GND
  17 = ILIM      (current-limit set resistor)
  18 = DVDT      (output ramp control cap)
  19 = IMON      (current monitor analog output)
  20 = FLT       (fault output, open-drain) — pinmap.txt uses
                  KiCad bar-notation `F\\L\\T\\` for the active-low signal
  21 = EP        (exposed thermal pad — must be soldered to GND)

Mechanical (NOT in datasheet headline): body_material, lead_material,
weight_g, fab_country.

Distributor: see Mouser/TI listings.
"""


def _tps25940_wqfn20_footprint() -> Footprint:
    """WQFN-20 (3×4 mm, 0.5 mm pitch) footprint with central EP per
    SamacSys QFN50P300X400X80-21N.kicad_mod. Pads paralleled per
    datasheet."""
    pads = []
    # Pad table per the SamacSys mod, y negated into the model's y-up
    # frame; the side-column pads carry a 90° rotation in the mod, so
    # their (size 0.25 0.85) renders 0.85 wide × 0.25 tall (baked here).
    # Left column pins 1-6 at x=-1.45, y=+1.25..-1.25 step -0.5
    for i, y in enumerate([1.25, 0.75, 0.25, -0.25, -0.75, -1.25], start=1):
        pads.append(Pad(num=str(i), position_mm=(-1.45, y),
                        size_mm=(0.85, 0.25), shape="rect", layer="F.Cu"))
    # Bottom row pins 7-10 at y=-1.95, x=-0.75..0.75 step 0.5
    for i, x in enumerate([-0.75, -0.25, 0.25, 0.75], start=7):
        pads.append(Pad(num=str(i), position_mm=(x, -1.95),
                        size_mm=(0.25, 0.85), shape="rect", layer="F.Cu"))
    # Right column pins 11-16 at x=+1.45, y=-1.25..+1.25 step 0.5
    for i, y in enumerate([-1.25, -0.75, -0.25, 0.25, 0.75, 1.25], start=11):
        pads.append(Pad(num=str(i), position_mm=(1.45, y),
                        size_mm=(0.85, 0.25), shape="rect", layer="F.Cu"))
    # Top row pins 17-20 at y=+1.95, x=0.75..-0.75 step -0.5
    for i, x in enumerate([0.75, 0.25, -0.25, -0.75], start=17):
        pads.append(Pad(num=str(i), position_mm=(x, 1.95),
                        size_mm=(0.25, 0.85), shape="rect", layer="F.Cu"))
    # EP (pin 21)
    pads.append(Pad(num="21", position_mm=(0.0, 0.0),
                    size_mm=(1.7, 2.7), shape="rect", layer="F.Cu"))
    return Footprint(
        name="QFN50P300X400X80-21N",
        package_class="WQFN-20",
        pads=pads,
        body_outline=[(-1.5, -2), (1.5, -2), (1.5, 2), (-1.5, 2)],
        courtyard=[(-2.125, -2.625), (2.125, -2.625),
                   (2.125, 2.625), (-2.125, 2.625)],
        pitch_mm=0.5,
        size_mm=(3.0, 4.0),
        height_mm=0.8,
        model_3d_path="application/src/smash/parts/sources/TPS25940AQRVCTQ1/TPS25940AQRVCTQ1.stp",
        source="samacsys",
        note="Exposed pad (pin 21) MUST be soldered to GND.",
    )


def add_tps25940aqrvctq1(design, ref: str, **overrides) -> Chip:
    """TI TPS25940AQRVCTQ1 — automotive eFuse, 2.7..18 V, adjustable
    0.6..5.3 A current limit, auto-retry on fault (A variant),
    AEC-Q100 grade 1, WQFN-20 (3×4 mm)."""
    fields = dict(
        manf="Texas Instruments",
        manf_pn="TPS25940AQRVCTQ1",
        canonical_id="tps25940aqrvctq1",
        name="TPS25940AQRVCTQ1",
        value="TPS25940AQRVCTQ1",
        description=(
            "Automotive eFuse, V_IN=2.7..18 V (20 V abs max), R_ON=42 mΩ typ, "
            "adjustable 0.6..5.3 A current limit, auto-retry, AEC-Q100 G1, "
            "WQFN-20"
        ),
        datasheet="application/src/smash/parts/sources/TPS25940AQRVCTQ1/TPS25940.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "AEC-Q100 Grade 1",
            "AEC-Q100 HBM Classification Level 2",
            "AEC-Q100 CDM Classification Level C5",
        ],
        eccn=None, itar=None,
        package="WQFN-20 (RVC, 3×4 mm)",
        size_mm=(3.0, 4.0),
        height_mm=0.8,
        temp_range_c=(-40, 125),     # AEC-Q100 G1 ambient operating
        body_material=None, lead_material=None,
        voltage_rating_v=20.0,       # abs max IN/OUT
        i_rms_a=4.78,                # I_MAX continuous @ T_A=85 °C
        power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None,
        tj_max_c=150.0,
        pins=[
            Pin(num="1",  name="DEVSLP",            type="input"),
            Pin(num="2",  name="PGOOD",             type="output",
                note="open-drain — requires external pull-up"),
            Pin(num="3",  name="PGTH",              type="input"),
            Pin(num="4",  name="OUT_1",             type="power",
                note="paralleled with OUT_2..OUT_5; solder ALL for spec R_ON"),
            Pin(num="5",  name="OUT_2",             type="power"),
            Pin(num="6",  name="OUT_3",             type="power"),
            Pin(num="7",  name="OUT_4",             type="power"),
            Pin(num="8",  name="OUT_5",             type="power"),
            Pin(num="9",  name="IN_1",              type="power",
                note="paralleled with IN_2..IN_5; solder ALL for spec R_ON"),
            Pin(num="10", name="IN_2",              type="power"),
            Pin(num="11", name="IN_3",              type="power"),
            Pin(num="12", name="IN_4",              type="power"),
            Pin(num="13", name="IN_5",              type="power"),
            Pin(num="14", name="EN",                type="input"),
            Pin(num="15", name="OVP",               type="input"),
            Pin(num="16", name="GND",               type="ground"),
            Pin(num="17", name="ILIM",              type="io",
                note="connect resistor to GND to program current limit"),
            Pin(num="18", name="DVDT",              type="io",
                note="connect capacitor to GND to program output ramp"),
            Pin(num="19", name="IMON",              type="output",
                note="current monitor analog output, ±8 % accuracy"),
            # SamacSys pinmap uses bar-notation "F\\L\\T\\" — datasheet name
            # is /FLT (active-low). Stored verbatim as it appears in pinmap.
            Pin(num="20", name="F\\L\\T\\", aliases=["FLT", "/FLT"],
                type="output", note="open-drain fault output"),
            Pin(num="21", name="EP", aliases=["ExposedPad"], type="ground",
                note="exposed thermal pad — must be soldered to GND"),
        ],
        footprint=_tps25940_wqfn20_footprint(),
        note=_TPS25940A_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments TPS259621DDAR — 2.7-19 V eFuse with pin-selectable
# OV clamp + auto-retry, 89-mΩ R_ON, SOIC-8 with exposed thermal pad
# ═════════════════════════════════════════════════════════════════════════

_TPS259621_NOTE = """\
Datasheet extras (TI TPS2596xx family, SLVSET8A, May 2019 rev A).

Family covered by this datasheet (p1 Table):
  TPS259620 : OVC pin-selectable (3.8/5.7/13.8 V), latch-off fault
  TPS259621 : OVC pin-selectable (3.8/5.7/13.8 V), AUTO-RETRY  <-- this
  TPS259630 : Adjustable OVLO, latch-off
  TPS259631 : Adjustable OVLO, auto-retry
All in SOIC-8 (DDA) package, 4.91 × 3.9 mm body + exposed thermal pad.

Headline features (p1):
  V_IN range            : 2.7 V to 19 V
  Absolute max V_IN     : 21 V (22 V at T_A=25 °C)
  R_ON                  : 89 mΩ typ
  Current limit range   : 0.125 A to 2 A (adjustable via R_ILM)
  Current limit accuracy: ±10.4 % max across range / ±5.5 % max @ 1 A
  Active-high EN with adjustable UVLO
  Fast OV clamp response: 5 µs typ
  Adjustable OVLO response: 1.3 µs typ
  Adjustable dVdt output slew rate (external cap on DVDT)
  Overtemperature protection (OTP)
  Fault indication pin (FLT, open-drain)
  Load current monitor on ILM pin
  Immune to Electrical Fast Transients per IEC 61000-4-4
  UL 2367 recognition (pending at datasheet rev A)
  IEC 62368 CB certification (pending at datasheet rev A)

Applications (p1):
  Energy meters
  UL 60335-1 15-W LPC in appliances
  IP network cameras

Absolute Max Ratings (p5 §7.1):
  V_IN              : -0.3 V to 21 V (22 V @ T_A=25 °C)
  V_OUT             : -0.3 V to min(21 V, V_IN + 0.3 V)
  V_EN/UVLO         : -0.3 V to 7 V
  V_OVCSEL/OVLO     : -0.3 V to 7 V
  V_dVdT            : up to 2.5 V
  V_FLTb            : -0.3 V to 7 V
  I_FLTb sink       : 10 mA max
  I_MAX continuous  : internally limited
  T_LEAD soldering  : 300 °C max
  T_J operating     : -40 to +125 °C (datasheet p1 "characterized
                                      over junction temp range")
  T_STG             : -65 to +150 °C

Pin layout (datasheet pin function table + pinmap.txt, SOIC-8 + EP):
  1 = GND_1
  2 = DVDT     (analog input — slew-rate program cap to GND)
  3 = EN/UVLO  (active-high enable; resistor divider for UVLO threshold)
  4 = IN       (supply input)
  5 = OUT      (switched supply output)
  6 = FLTb     (open-drain fault output, active low — pinmap encodes
                with bar-notation `F\\L\\T\\`)
  7 = ILM      (current limit set / load current monitor analog output)
  8 = OVCSEL   (on TPS25962x: overvoltage clamp level select)
       For this part (TPS259621): pin 8 SELECTS clamp threshold.
       For TPS259631 the same pin is OVLO (user-adjustable threshold).
  9 = ExposedPad (thermal pad — connect to GND for thermal sink)

Application-level cautions:
  - OVCSEL pin must NOT float (datasheet pin function table on
    OVLO/OVCSEL). Tie per chosen clamp level.
  - The exposed pad is "used primarily for heat dissipation and must
    be connected to system ground" (datasheet pin function table).
  - This is the AUTO-RETRY variant. On fault, the device retries
    after a built-in delay. If the application requires single-shot
    latch-off, switch order code to TPS259620 or TPS259630.

Mechanical (NOT in datasheet headline): body_material, lead_material,
weight_g, fab_country.
"""


def _tps259621_soic8_ep_footprint() -> Footprint:
    """SOIC-8 (DDA package) + exposed thermal pad per SamacSys
    SOIC127P600X170-9N.kicad_mod. Body 4.91 × 3.9 mm, EP centered
    at origin (2.4 × 3.1 mm)."""
    return Footprint(
        name="SOIC127P600X170-9N",
        package_class="SOIC-8 (DDA, with EP)",
        pads=[
            Pad(num="1", position_mm=(-2.712, 1.905), size_mm=(1.525, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-2.712, 0.635), size_mm=(1.525, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-2.712, -0.635), size_mm=(1.525, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(-2.712, -1.905), size_mm=(1.525, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(2.712, -1.905), size_mm=(1.525, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=(2.712, -0.635), size_mm=(1.525, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="7", position_mm=(2.712, 0.635), size_mm=(1.525, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="8", position_mm=(2.712, 1.905), size_mm=(1.525, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="9", position_mm=(0.0, 0.0),   size_mm=(2.4, 3.1),   shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-1.95, -2.45), (1.95, -2.45),
                      (1.95, 2.45), (-1.95, 2.45)],
        courtyard=[(-3.725, -2.75), (3.725, -2.75),
                   (3.725, 2.75), (-3.725, 2.75)],
        pitch_mm=1.27,
        size_mm=(4.91, 3.9),
        height_mm=1.70,
        model_3d_path="application/src/smash/parts/sources/TPS259621DDAR/TPS259621DDAR.stp",
        source="samacsys",
        note="Exposed pad (pin 9) MUST be soldered to GND for thermal.",
    )


def add_tps259621ddar(design, ref: str, **overrides) -> Chip:
    """TI TPS259621DDAR — 2.7-19 V eFuse, 89-mΩ R_ON, adjustable
    0.125-2 A current limit, pin-selectable overvoltage clamp
    (3.8/5.7/13.8 V), AUTO-RETRY on fault, SOIC-8 with exposed pad.
    """
    fields = dict(
        manf="Texas Instruments",
        manf_pn="TPS259621DDAR",
        canonical_id="tps259621ddar",
        name="TPS259621DDAR",
        value="TPS259621DDAR",
        description=(
            "eFuse, V_IN=2.7..19 V (21 V abs max), R_ON=89 mΩ typ, "
            "adjustable 0.125..2 A current limit, pin-selectable OV "
            "clamp (3.8/5.7/13.8 V), auto-retry, SOIC-8 + EP"
        ),
        datasheet="application/src/smash/parts/sources/TPS259621DDAR/TPS2596-family.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "IEC 61000-4-4 (EFT immune)",
            "UL 2367 recognition (pending at DS rev A)",
            "IEC 62368 CB (pending at DS rev A)",
        ],
        eccn=None, itar=None,
        package="SOIC-8 (DDA, with EP)",
        size_mm=(4.91, 3.9),
        height_mm=1.70,
        temp_range_c=(-40, 125),    # T_J operating per p1
        body_material=None, lead_material=None,
        voltage_rating_v=21.0,       # V_IN abs max
        i_rms_a=2.0,                 # max current-limit setting
        power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None,
        tj_max_c=125.0,
        pins=[
            # Per pinmap.txt + datasheet pin function table
            Pin(num="1", name="GND_1", aliases=["GND"], type="ground"),
            Pin(num="2", name="DVDT",  type="io",
                note="cap to GND programs output slew rate"),
            Pin(num="3", name="EN_UVLO", aliases=["EN", "UVLO"],
                type="input",
                note="active-high enable; resistor divider sets UVLO threshold"),
            Pin(num="4", name="IN",    type="power"),
            Pin(num="5", name="OUT",   type="power"),
            # Datasheet name is FLTb / /FLT — SamacSys uses bar-notation
            Pin(num="6", name="F\\L\\T\\", aliases=["FLT", "/FLT", "FLTb"],
                type="output", note="open-drain fault output (active low)"),
            Pin(num="7", name="ILM",   type="io",
                note="resistor to GND sets current limit; also analog "
                     "current-monitor output"),
            # On TPS25962x (this part): OVCSEL; on TPS25963x: OVLO
            Pin(num="8", name="OVLO_OVCSEL", aliases=["OVCSEL", "OVLO"],
                type="input",
                note="TPS25962x: pin-selectable OV clamp level "
                     "(3.8/5.7/13.8 V). Must NOT float."),
            Pin(num="9", name="GND_2", aliases=["EP", "ExposedPad"],
                type="ground",
                note="exposed thermal pad — must be soldered to GND"),
        ],
        footprint=_tps259621_soic8_ep_footprint(),
        note=_TPS259621_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
