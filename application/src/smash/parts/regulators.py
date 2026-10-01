"""Switching regulator factories (boost / buck).

Each factory is a faithful transcription of its per-part ground-truth
artifacts in `parts/sources/<PN>/`.
"""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint


# ═════════════════════════════════════════════════════════════════════════
# Microchip MCP1640CT-I/CHY — 0.65 V start-up synchronous boost regulator,
# 6-pin SOT-23, automatic PFM/PWM (C variant), true load disconnect
# ═════════════════════════════════════════════════════════════════════════

_MCP1640CT_NOTE = """\
Datasheet extras (Microchip MCP1640/B/C/D, DS20002234D, 2010-2015).
This factory covers the **C-variant**, automatic PFM/PWM with TRUE
load-disconnect mode, industrial temperature (-40 to +85 °C), 6-pin
SOT-23 — orderable as MCP1640CT-I/CHY (marking code BXNN).

Variants in the same datasheet:
  MCP1640  T-I/CHY : 6L SOT-23, PWM/PFM, true disconnect      (marking BANN)
  MCP1640B T-I/CHY : 6L SOT-23, PWM only,  true disconnect    (marking BWNN)
  MCP1640C T-I/CHY : 6L SOT-23, PWM/PFM, input-to-output bypass (marking BXNN)
  MCP1640D T-I/CHY : 6L SOT-23, PWM only,  input-to-output bypass (marking BYNN)
  MCP1640*-I/MC    : 8L 2×3 DFN equivalents
>>> The "C" suffix selects auto PFM/PWM + INPUT-TO-OUTPUT BYPASS while
    in shutdown (vs A/B which use TRUE LOAD DISCONNECT). When the
    schematic relies on the disabled output going to high-Z, use the
    A or B variant, NOT C/D.

>>> Source-of-truth caveat: Research/ holds the file
    `MCP1640CT-5002H_CHY.pdf` whose name includes the trim code
    "5002H". The datasheet text itself is the generic MCP1640/B/C/D
    family doc; the "5002H" suffix doesn't appear anywhere in the
    body or the ordering tables. May be a customer-coded preset
    trim — to verify with Microchip when ordering.

Absolute Max Ratings (p1):
  EN, VFB, VIN, VSW, VOUT - GND : +6.5 V
  Output short-circuit : continuous
  Output current (bypass mode)  : 400 mA
  Power dissipation : internally limited
  Storage temp     : -65 to +150 °C
  Ambient (powered): -40 to +85 °C
  Operating T_J    : -40 to +125 °C
  ESD HBM          : 3 kV
  ESD MM           : 300 V

Electrical (p2 table, VIN=1.2V, COUT=CIN=10µF, L=4.7µH, VOUT=3.3V,
IOUT=15mA, TA=+25°C; bold over -40 to +85 °C):
  V_IN min start-up : 0.65 V typ / 0.8 V max (Note 1)
  V_IN min after start-up : 0.35 V typ
  V_OUT adjust range: 2.0 V to 5.5 V (VOUT ≥ VIN)
  I_OUT max @ 1.2V/2.0V : 150 mA typ
  I_OUT max @ 1.5V/3.3V : 150 mA typ
  I_OUT max @ 3.3V/5.0V : 350 mA typ
  V_FB feedback voltage : 1.175 / 1.21 / 1.245 V
  I_QPFM quiescent (PFM, no-load) : 19 µA typ / 30 µA max
  Switching frequency : 500 kHz (PWM mode)
  Peak input current limit : 800 mA typ

Mechanical (NOT stated in datasheet): body_material, lead_material,
weight_g, density_g_cm3, cte_ppm_k, fab_country.

Distributor (from SamacSys metadata):
  Mouser PN : 579-MCP1640CT-I/CHY (verify on Mouser)
  Microchip product page: www.microchip.com/MCP1640
"""


def _mcp1640_sot23_6_footprint() -> Footprint:
    """6-pin SOT-23 footprint per SamacSys `SOT95P270X145-6N.kicad_mod`.

    Pads at (-1.25, ±0.95 / 0) and (+1.25, ±0.95 / 0), 0.6 × 1.4 mm.
    Body 1.55 × 2.90, height 1.45 mm max."""
    return Footprint(
        name="SOT95P270X145-6N",
        package_class="SOT-23-6",
        pads=[
            Pad(num="1", position_mm=(-1.25, 0.95), size_mm=(1.4, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.25, 0.0),   size_mm=(1.4, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-1.25, -0.95), size_mm=(1.4, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(1.25, -0.95), size_mm=(1.4, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(1.25, 0.0),   size_mm=(1.4, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=(1.25, 0.95), size_mm=(1.4, 0.6), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-0.775, -1.45), (0.775, -1.45), (0.775, 1.45), (-0.775, 1.45)],
        courtyard=[(-2.2, -1.8), (2.2, -1.8), (2.2, 1.8), (-2.2, 1.8)],
        pitch_mm=0.95,
        size_mm=(2.90, 1.55),
        height_mm=1.45,
        model_3d_path="application/src/smash/parts/sources/MCP1640CT-I_CHY/MCP1640CT-I_CHY.stp",
        source="samacsys",
    )


def add_mcp1640ct_i_chy(design, ref: str, **overrides) -> Chip:
    """Microchip MCP1640CT-I/CHY — 0.65 V start-up synchronous boost
    regulator, 6L SOT-23, auto PFM/PWM (C variant), input-to-output
    bypass in shutdown. Industrial -40..+85 °C."""
    fields = dict(
        manf="Microchip",
        manf_pn="MCP1640CT-I/CHY",
        canonical_id="mcp1640ct_i_chy",
        name="MCP1640CT-I/CHY",
        value="MCP1640CT-I/CHY",
        description=(
            "Synchronous boost regulator, 0.65 V start-up, V_OUT "
            "adjustable 2.0..5.5 V, 500 kHz PWM with auto PFM, "
            "input-to-output bypass in shutdown, 6L SOT-23"
        ),
        datasheet="application/src/smash/parts/sources/MCP1640CT-I_CHY/MCP1640-family.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=["ESD HBM 3 kV", "ESD MM 300 V"],
        eccn=None, itar=None,
        package="SOT-23-6",
        size_mm=(2.90, 1.55),
        height_mm=1.45,
        temp_range_c=(-40, 85),       # ambient operating (TA)
        body_material=None, lead_material=None,
        voltage_rating_v=6.5,         # EN/VFB/VIN/VSW/VOUT - GND abs max
        i_rms_a=None,                 # variable — see note (max IOUT 350 mA)
        power_rating_w=None,          # internally limited
        # ── thermal (Microchip MCP1640 DS20002234D Jul 2014) ─────────
        # Iq = 19 µA typ PFM mode (DS p1). Active dissipation is the
        # boost conversion loss — for our wakeup_board use (5 V boost
        # from 3.0-4.2 V battery at modest load) the package sees a
        # small fraction of the output power. p_active conservative
        # at "Iq dominated, low load" and p_max at "350 mA out, 95 %
        # eff" (~0.20 W out × 5 % loss = ~0.01 W); actual peak can be
        # higher with start-up bursts. Use components.md envelope.
        p_active_w=0.01,                    # Iq + light-load PFM mode (DS p1)
        p_max_w=0.05,                       # est'd peak with 350 mA out (worst-case heating)
        rth_jc_cw=None,                     # not in DS — SOT-23-6 typically not spec'd
        tj_max_c=125.0,                     # operating Tj max steady-state, DS p4 (150°C abs only transient)
        pins=[
            Pin(num="1", name="SW",   type="io"),
            Pin(num="2", name="GND",  type="ground"),
            Pin(num="3", name="EN",   type="input"),
            Pin(num="4", name="VFB",  type="input"),
            Pin(num="5", name="VOUT", type="power"),
            Pin(num="6", name="VIN",  type="power"),
        ],
        footprint=_mcp1640_sot23_6_footprint(),
        note=_MCP1640CT_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments LMR10510XMFE/NOPB — 5.5 V_IN, 1 A step-down buck,
# 5-pin SOT-23, 1.6 MHz switching frequency (X variant)
# ═════════════════════════════════════════════════════════════════════════

_LMR10510_NOTE = """\
Datasheet extras (TI LMR10510, SNVS727C, Jun 2019 rev — originally
National Semiconductor). 5-pin SOT-23 buck.

Variants in the datasheet:
  LMR10510X : 1.6 MHz switching frequency  (this factory)
  LMR10510Y : 3.0 MHz switching frequency  (different orderable, same pkg)
  Also available in 6-pin WSON (3×3) — separate factory needed.

Absolute Max Ratings (p4 §7.1):
  VIN              : -0.5 to 7 V
  FB voltage       : -0.5 to 3 V
  EN voltage       : -0.5 to 7 V
  SW voltage       : -0.5 to 7 V
  ESD              : 2 kV (HBM, single value in this older datasheet)
  Junction temp    : 150 °C (T_J max)
  Storage temp     : -65 to +150 °C

Recommended Operating (p4):
  V_IN range       : 3 V to 5.5 V
  V_OUT range      : 0.6 V to 4.5 V
  I_OUT up to      : 1 A
  Switching freq   : 1.6 MHz (X variant)

Key device features (p1):
  Internal 130 mΩ P-MOS switch
  Internally compensated
  Current-mode PWM operation
  Internal soft start
  Thermal shutdown
  Low shutdown I_Q : 30 nA typ

Mechanical (NOT in datasheet headline): body_material, lead_material,
weight_g, fab_country.

Distributor: Mouser PN to be confirmed at quote time.
"""


def _sot95p280x145_5n_footprint(model_3d_path: str) -> Footprint:
    """5-pin SOT-23 (TI DBV package) footprint per SamacSys
    `SOT95P280X145-5N.kicad_mod`. Used by BOTH LMR10510XMFE/NOPB and
    LMV331IDBVR — same physical footprint, but ownership is inline
    (each Chip gets its own Footprint instance with its own
    `model_3d_path` for the right STEP file).
    """
    return Footprint(
        name="SOT95P280X145-5N",
        package_class="SOT-23-5",
        pads=[
            Pad(num="1", position_mm=(-1.25, 0.95), size_mm=(1.2, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.25, 0.0),   size_mm=(1.2, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-1.25, -0.95), size_mm=(1.2, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(1.25, -0.95), size_mm=(1.2, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(1.25, 0.95), size_mm=(1.2, 0.6), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-0.8, -1.45), (0.8, -1.45), (0.8, 1.45), (-0.8, 1.45)],
        courtyard=[(-2.1, -1.775), (2.1, -1.775), (2.1, 1.775), (-2.1, 1.775)],
        pitch_mm=0.95,
        size_mm=(2.90, 1.60),       # nominal body, per LMR10510 datasheet p1
        height_mm=1.45,
        model_3d_path=model_3d_path,
        source="samacsys",
    )


def add_lmr10510xmfe_nopb(design, ref: str, **overrides) -> Chip:
    """TI LMR10510XMFE/NOPB — 5.5 V_IN, 1 A step-down buck, 1.6 MHz,
    SOT-23-5 (DBV package)."""
    fields = dict(
        manf="Texas Instruments",
        manf_pn="LMR10510XMFE/NOPB",
        canonical_id="lmr10510xmfe_nopb",
        name="LMR10510XMFE/NOPB",
        value="LMR10510XMFE/NOPB",
        description=(
            "Step-down buck regulator, V_IN=3..5.5 V, V_OUT=0.6..4.5 V, "
            "I_OUT=1 A, 1.6 MHz, SOT-23-5"
        ),
        datasheet="application/src/smash/parts/sources/LMR10510XMFE_NOPB/LMR10510.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=["ESD HBM 2 kV"],
        eccn=None, itar=None,
        package="SOT-23-5",
        size_mm=(2.90, 1.60),
        height_mm=1.45,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=7.0,
        i_rms_a=1.0,
        power_rating_w=None,
        # ── thermal (TI LMR10510 SNVS727C Jun 2019, §10.3) ───────────
        # DS quotes ΘJC ≈ 80 °C/W for the SOT-23-5 (vs 18 °C/W for the
        # 6-pin WSON variant). ΘJA ≈ 118 °C/W on a JEDEC board. Op'l
        # Tj max = 125 °C, abs max Tj = 150 °C (thermal shutdown at
        # 165 °C). Active power for our IWR1843 core rail use case:
        # 1.0V out × ~0.5 A typ + Iq → ~0.05 W package dissipation
        # at 87 % eff = ~0.07 W. Peak at full 1 A out: ~0.15 W.
        p_active_w=0.05,                    # IWR1843 core rail (1.0V × ~0.5A), 87% eff (DS §10.3 example)
        p_max_w=0.20,                       # peak at 1 A out, 80% eff (worst-case heating)
        rth_jc_cw=80.0,                     # SOT-23-5 ΘJC, DS §10.3 p22 (text quote)
        tj_max_c=150.0,                     # abs max Tj, DS §7.1 p4 (op'l limit 125°C)
        pins=[
            Pin(num="1", name="SW",  type="io"),
            Pin(num="2", name="GND", type="ground"),
            Pin(num="3", name="FB",  type="input"),
            Pin(num="4", name="EN",  type="input"),
            Pin(num="5", name="VIN", type="power"),
        ],
        footprint=_sot95p280x145_5n_footprint(
            "application/src/smash/parts/sources/LMR10510XMFE_NOPB/LMR10510XMFE_NOPB.stp"
        ),
        note=_LMR10510_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments TPS61085PW — 18.5 V boost converter, 2 A switch,
# 650 kHz / 1.2 MHz selectable, 8-pin TSSOP
# ═════════════════════════════════════════════════════════════════════════

_TPS61085_NOTE = """\
Datasheet extras (TI TPS61085, SLVS859B, Dec 2014).

Variants:
  TPS61085  (PW = TSSOP-8, this factory) and
  TPS61085  (DGK = VSSOP-8 — separate factory if needed).

Absolute Max Ratings (p3 §7.1):
  V_IN          : -0.3 to 7 V
  V on EN/FB/SS/FREQ/COMP : -0.3 to 7 V
  V on SW       : -0.3 to 20 V
  T_J operating : -40 to +150 °C
  T_STG         : -65 to +150 °C

ESD (p3 §7.2): HBM ±2 kV, CDM ±500 V.

Recommended Operating (p4 §7.3):
  V_IN          : 2.3 V to 6 V
  V_OUT         : up to 18.5 V (boost)
  Switching freq: 650 kHz / 1.2 MHz selectable (FREQ pin)
  Switch current: 2.0 A typ
  Switch R_DS(on): 0.13 Ω typ

Feature highlights (p1):
  - Adjustable soft-start (SS pin)
  - Thermal shutdown
  - Undervoltage lockout

Mechanical (NOT in datasheet): body_material, lead_material,
weight_g, fab_country.
"""


def _tps61085_tssop8_footprint() -> Footprint:
    """8-pin TSSOP per SamacSys SOP65P490X110-8N.kicad_mod (0.65 mm
    pitch, 4.9 mm wide, 1.1 mm height, 8 pins)."""
    return Footprint(
        name="SOP65P490X110-8N",
        package_class="TSSOP-8",
        pads=[
            Pad(num="1", position_mm=(-2.2, 0.975), size_mm=(1.4, 0.45), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-2.2, 0.325), size_mm=(1.4, 0.45), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-2.2, -0.325), size_mm=(1.4, 0.45), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(-2.2, -0.975), size_mm=(1.4, 0.45), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(2.2, -0.975), size_mm=(1.4, 0.45), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=(2.2, -0.325), size_mm=(1.4, 0.45), shape="rect", layer="F.Cu"),
            Pad(num="7", position_mm=(2.2, 0.325), size_mm=(1.4, 0.45), shape="rect", layer="F.Cu"),
            Pad(num="8", position_mm=(2.2, 0.975), size_mm=(1.4, 0.45), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-1.5, -1.5), (1.5, -1.5), (1.5, 1.5), (-1.5, 1.5)],
        courtyard=[(-3.15, -1.8), (3.15, -1.8), (3.15, 1.8), (-3.15, 1.8)],
        pitch_mm=0.65,
        size_mm=(3.0, 4.4),         # TI TSSOP-8 nominal body (datasheet p1)
        height_mm=1.10,
        model_3d_path="application/src/smash/parts/sources/TPS61085PW/TPS61085PW.stp",
        source="samacsys",
    )


def add_tps61085pw(design, ref: str, **overrides) -> Chip:
    """TI TPS61085PW — 2.3..6 V_IN boost converter to 18.5 V_OUT,
    2 A internal switch, 650 kHz / 1.2 MHz selectable, TSSOP-8."""
    fields = dict(
        manf="Texas Instruments",
        manf_pn="TPS61085PW",
        canonical_id="tps61085pw",
        name="TPS61085PW",
        value="TPS61085PW",
        description=(
            "Boost converter, V_IN=2.3..6 V, V_OUT up to 18.5 V, "
            "2 A switch, 650 kHz/1.2 MHz, TSSOP-8"
        ),
        datasheet="application/src/smash/parts/sources/TPS61085PW/TPS61085.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=["ESD HBM ±2 kV", "ESD CDM ±500 V"],
        eccn=None, itar=None,
        package="TSSOP-8",
        size_mm=(3.0, 4.4),
        height_mm=1.10,
        temp_range_c=(-40, 150),    # operating T_J range (no separate TA in p3)
        body_material=None, lead_material=None,
        voltage_rating_v=20.0,      # SW pin abs max
        i_rms_a=2.0,                # switch current
        power_rating_w=None,
        # ── thermal (TI TPS61085 SLVS859B Dec 2014, §7.4 p3) ─────────
        # NB: components.md row used Rθ_JC = 57.1 (DGK package);
        # the PW (TSSOP-8) value from the same DS table is 66.7 °C/W.
        # Iq = 70 µA typ / 100 µA max (DS §7.5). Active dissipation
        # is the boost conversion loss — for 5V → 12V or similar
        # rails at modest load (~100 mA out) eff ≈ 88 % → ~0.1 W
        # package dissipation. Peak burst: ~0.30 W at full 2 A switch.
        p_active_w=0.10,                    # est'd conversion loss at typical companion-board load
        p_max_w=0.30,                       # est'd peak with 2 A switch current at boost burst
        rth_jc_cw=66.7,                     # PW (TSSOP-8) RθJC(top), DS §7.4 p3
        tj_max_c=150.0,                     # abs max Tj, DS §7.1 p3
        pins=[
            Pin(num="1", name="COMP", type="io"),
            Pin(num="2", name="FB",   type="input"),
            Pin(num="3", name="EN",   type="input"),
            Pin(num="4", name="PGND", type="ground"),
            Pin(num="5", name="SW",   type="io"),
            Pin(num="6", name="IN",   aliases=["VIN"], type="power"),
            Pin(num="7", name="FREQ", type="input"),
            Pin(num="8", name="SS",   type="io"),
        ],
        footprint=_tps61085_tssop8_footprint(),
        note=_TPS61085_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments TPS61175PWPR — 38 V boost converter, 4 A switch,
# programmable 200 kHz-2.2 MHz, 14-pin HTSSOP + exposed pad
# ═════════════════════════════════════════════════════════════════════════

_TPS61175_NOTE = """\
Datasheet extras (TI TPS61175, SLVS892F, Apr 2019).

Absolute Max Ratings (p4 §6.1):
  V_IN           : -0.3 to 20 V
  V on EN        : -0.3 to 20 V
  V on FB/FREQ/COMP : -0.3 to 3 V
  V on SYNC/SS   : -0.3 to 7 V
  V on SW        : -0.3 to 40 V
  T_J            : -40 to +150 °C
  T_STG          : -65 to +150 °C

ESD (p4 §6.2): HBM ±2 kV, CDM ±500 V.

Recommended Operating (p4 §6.3):
  V_IN          : 2.9 V to 18 V
  V_OUT         : V_IN to 38 V
  L             : 4.7 to 47 µH
  f_SW          : 200 kHz to 2.2 MHz (set by R_FREQ resistor)
  C_IN, C_OUT   : ≥ 4.7 µF
  V_SYN logic   : up to 5 V
  T_A           : -40 to +85 °C
  T_J           : -40 to +125 °C

Thermal (p5 §6.4, PWP HTSSOP-14):
  R_θJA          : 45.2 °C/W   (this is the field rth_ja_cw)
  R_θJC(top)     : 34.9 °C/W
  R_θJC(bottom)  : 5.8 °C/W
  R_θJB          : 30.1 °C/W

Electrical (p5 §6.5, FSW=1.2 MHz, V_IN=3.6 V, TA=-40..+85 °C):
  I_Q operating  : 3.5 mA (switching, no load)
  I_SD shutdown  : 1.5 µA (EN=GND)
  V_UVLO         : 2.5 V min / 2.7 V typ
  EN logic high  : 1.2 V min
  EN logic low   : 0.4 V max
  V_REF          : 1.204 / 1.229 / 1.254 V (feedback regulation)
  R_DS(on) N-FET : 0.13 Ω typ @ V_GS=3.6 V
  I_LIM (switch) : 3 A min / 3.8 A typ / 5 A max
  T_shutdown     : 160 °C typ, 15 °C hysteresis

Pin functions (p3-4 §5):
  SW (1,2)      : switch node — connect to inductor
  VIN (3)       : input supply
  EN (4)        : enable; 800 kΩ internal pull-down
  SS (5)        : soft-start capacitor pin
  SYNC (6)      : sync input, tie to AGND when unused
  AGND (7)      : analog ground
  COMP (8)      : loop compensation
  FB (9)        : feedback (1.229 V regulation point)
  FREQ (10)     : program switching frequency via R_FREQ
  NC (11)       : "Reserved pin. Must connect this pin to ground."
  PGND (12,13,14): power ground
  EP (15)       : exposed pad — solder to analog ground

Mechanical (NOT in datasheet): body_material, lead_material,
weight_g, fab_country.
"""


def _tps61175_htssop14_footprint() -> Footprint:
    """14-lead HTSSOP + exposed pad per SamacSys
    SOP65P640X120-15N.kicad_mod (0.65 mm pitch, 6.4 mm wide leadspan,
    1.2 mm height, 14 pins + EP)."""
    pads = []
    # Pad table per the SamacSys mod (y negated into the model's y-up
    # frame; the mod's pads carry a 90° rotation, so its (size 0.45
    # 1.475) renders 1.475 wide × 0.45 tall — baked here).
    # Left column: pins 1-7 at x=-2.938, y from +1.95 down to -1.95
    for i, y in enumerate([1.95, 1.3, 0.65, 0.0, -0.65, -1.3, -1.95], start=1):
        pads.append(Pad(num=str(i), position_mm=(-2.938, y),
                        size_mm=(1.475, 0.45), shape="rect", layer="F.Cu"))
    # Right column: pins 8-14 at x=+2.938, y from -1.95 up to +1.95
    for i, y in enumerate([-1.95, -1.3, -0.65, 0.0, 0.65, 1.3, 1.95], start=8):
        pads.append(Pad(num=str(i), position_mm=(2.938, y),
                        size_mm=(1.475, 0.45), shape="rect", layer="F.Cu"))
    # Exposed pad (15) — 90°-rotated in the mod: 2.46 wide × 2.31 tall
    pads.append(Pad(num="15", position_mm=(0.0, 0.0),
                    size_mm=(2.46, 2.31), shape="rect", layer="F.Cu"))
    return Footprint(
        name="SOP65P640X120-15N",
        package_class="HTSSOP-14",
        pads=pads,
        body_outline=[(-2.2, -2.5), (2.2, -2.5), (2.2, 2.5), (-2.2, 2.5)],
        courtyard=[(-3.925, -2.8), (3.925, -2.8), (3.925, 2.8), (-3.925, 2.8)],
        pitch_mm=0.65,
        size_mm=(4.4, 5.0),         # nominal body (TI PWP package)
        height_mm=1.20,
        model_3d_path="application/src/smash/parts/sources/TPS61175PWPR/TPS61175PWPR.stp",
        source="samacsys",
        note="Exposed pad (pin 15) MUST be soldered to AGND for thermal.",
    )


def add_tps61175pwpr(design, ref: str, **overrides) -> Chip:
    """TI TPS61175PWPR — 2.9..18 V_IN boost to 38 V, 4 A switch current
    limit, programmable 200 kHz-2.2 MHz, HTSSOP-14+EP."""
    fields = dict(
        manf="Texas Instruments",
        manf_pn="TPS61175PWPR",
        canonical_id="tps61175pwpr",
        name="TPS61175PWPR",
        value="TPS61175PWPR",
        description=(
            "Boost converter, V_IN=2.9..18 V, V_OUT up to 38 V, "
            "3.8 A typ switch current limit, 200 kHz-2.2 MHz, HTSSOP-14+EP"
        ),
        datasheet="application/src/smash/parts/sources/TPS61175PWPR/TPS61175.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=["ESD HBM ±2 kV", "ESD CDM ±500 V"],
        eccn=None, itar=None,
        package="HTSSOP-14 (PWP)",
        size_mm=(4.4, 5.0),
        height_mm=1.20,
        temp_range_c=(-40, 85),    # TA recommended operating
        body_material=None, lead_material=None,
        voltage_rating_v=40.0,     # SW pin abs max
        i_rms_a=3.8,               # switch current limit typ
        power_rating_w=None,
        rth_jc_cw=5.8,             # R_θJC(bottom) — relevant for thermal pad
        rth_ja_cw=45.2,
        tj_max_c=150.0,
        pins=[
            Pin(num="1",  name="SW_1",  type="io"),
            Pin(num="2",  name="SW_2",  type="io"),
            Pin(num="3",  name="VIN",   type="power"),
            Pin(num="4",  name="EN",    type="input"),
            Pin(num="5",  name="SS",    type="io"),
            Pin(num="6",  name="SYNC",  type="input"),
            Pin(num="7",  name="AGND",  type="ground"),
            Pin(num="8",  name="COMP",  type="io"),
            Pin(num="9",  name="FB",    type="input"),
            Pin(num="10", name="FREQ",  type="input"),
            Pin(num="11", name="NC",    type="nc",
                note="datasheet: 'Reserved pin. Must connect this pin to ground.'"),
            Pin(num="12", name="PGND_1", type="ground"),
            Pin(num="13", name="PGND_2", type="ground"),
            Pin(num="14", name="PGND_3", type="ground"),
            Pin(num="15", name="EP", aliases=["ExposedPad"], type="ground"),
        ],
        footprint=_tps61175_htssop14_footprint(),
        note=_TPS61175_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
