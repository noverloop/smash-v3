"""Discrete MOSFET factories.

Every value here is transcribed from the per-part ground-truth artifacts
in `parts/sources/<PN>/`. See each factory's docstring for the exact
source citation per field.
"""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


# ─────────────────────────────────────────────────────────────────────────
# Infineon (formerly International Rectifier) IRLML6402TRPBF
#
# Ground-truth artifacts (all in parts/sources/IRLML6402TRPBF/):
#   - IRLML6402TRPBF.pdf         : datasheet, rev 4/28/2014 (9 pages)
#   - LIB_IRLML6402TRPBF.samacsys.zip : SamacSys ECAD archive, part ID
#                                       551340, released 2017-04-11
#   - IRLML6402TRPBF.kicad_sym   : KiCad 6 symbol (extracted from ZIP)
#   - SOT95P237X112-3N.kicad_mod : KiCad footprint (extracted from ZIP)
#   - IRLML6402TRPBF.stp         : STEP 3D model (extracted from ZIP)
#   - pinmap.txt                 : 3-line pin map (project, hand-built)
#   - part_info.txt              : SamacSys metadata
# ─────────────────────────────────────────────────────────────────────────

_IRLML6402TRPBF_NOTE = """\
Datasheet extras (Infineon IRLML6402PbF, April 28 2014) — fields not
yet promoted to the schema. All values transcribed verbatim from the
PDF (signs preserved; P-channel device, so most ratings are negative).

Absolute Max Ratings (table p1):
  V_GS gate-source voltage : ±12 V
  I_DM pulsed drain current: -22 A   (note ①: repetitive rating; pulse
                                      width limited by max T_J)
  I_D @ T_A=70 °C, V_GS=-4.5V: -2.2 A
  P_D @ T_A=25 °C            : 1.3 W
  P_D @ T_A=70 °C            : 0.8 W
  Linear derating factor    : 0.01 W/°C
  E_AS single-pulse avalanche: 11 mJ
                              (note ④: T_J=25 °C, L=1.65 mH,
                               R_G=25 Ω, I_AS=-3.7 A)

R_θJA (table p1):
  typ 75 °C/W, max 100 °C/W   (note ③: 1" square single-layer 1 oz Cu
                               FR4, steady state)
                              schema field rth_ja_cw holds the MAX
                              (100); typ kept here for thermal sim.

Electrical Characteristics @ T_J=25 °C (table p2):
  V_(BR)DSS : -20 V min     (V_GS=0V, I_D=-250 µA)
  ΔV_(BR)DSS/ΔT_J : -0.009 V/°C typ   (ref 25 °C, I_D=-1 mA)
  R_DS(on) @ V_GS=-4.5V, I_D=-3.7A : 0.050 Ω typ / 0.065 Ω max
  R_DS(on) @ V_GS=-2.5V, I_D=-3.1A : 0.080 Ω typ / 0.135 Ω max
  V_GS(th) gate threshold : -0.40 min / -0.55 typ / -1.2 max V
                            (V_DS=V_GS, I_D=-250 µA)
  gfs forward transconductance : 6.0 S min (V_DS=-10V, I_D=-3.7A)
  I_DSS drain leakage : -1.0 µA max @ V_GS=0V, V_DS=-20V (25 °C);
                        -25 µA max at T_J=70 °C
  I_GSS gate leakage   : -100 nA fwd / +100 nA rev (V_GS=±12V)
  Q_g total gate charge : 8.0 typ / 12 max nC  (I_D=-3.7A,
                                                V_DS=-10V, V_GS=-5V)
  Q_gs : 1.2 typ / 1.8 max nC
  Q_gd Miller charge   : 2.8 typ / 4.2 max nC
  Switching times (R_G=89 Ω, R_D=2.7 Ω, V_DD=-10V):
    t_d(on) = 350 ns typ
    t_r     =  48 ns typ
    t_d(off)= 588 ns typ
    t_f     = 381 ns typ
  Capacitances @ V_DS=-10V, V_GS=0V, f=1 MHz:
    C_iss = 633 pF typ
    C_oss = 145 pF typ
    C_rss = 110 pF typ

Body-Diode (source-drain) ratings (table p2):
  I_S continuous source current (body diode) : -1.3 A
  I_SM pulsed source current                 : -22 A
  V_SD diode forward voltage : -1.2 V max (T_J=25 °C, I_S=-1.0A,
                                           V_GS=0V)
  t_rr reverse recovery time : 29 ns typ / 43 ns max  (I_F=-1.0A)
  Q_rr reverse recovery charge: 11 nC typ / 17 nC max (di/dt=-100 A/µs)

Qualification (table p9):
  Qualification level    : Consumer (per JEDEC JESD47F)
  Moisture sensitivity   : MSL1 (per JEDEC J-STD-020D)
  RoHS                   : Yes
  >>> Consumer-grade only — NOT automotive (AEC-Q101) nor industrial.
      Surface this to sourcing when used in high-reliability paths.

Package marking (p7):
  X = "E" for IRLML6402   (followed by year/work-week date code)

Mechanical (NOT stated in datasheet — needed from supplier traceability):
  body_material  : NOT STATED — typical SOT-23 is epoxy mold compound
  lead_material  : NOT STATED — datasheet only says "Cu WIRE Halogen Free"
                                (that's the bond wire, not the leadframe)
  weight_g       : NOT STATED — typical SOT-23 ≈ 0.008 g
  density_g_cm3  : NOT STATED
  cte_ppm_k      : NOT STATED
  fab_country    : NOT IN DATASHEET — needs Mouser/Infineon traceability

Distributor links (from SamacSys metadata, snapshot 2017-04-11):
  datasheet URL : http://www.infineon.com/dgdl/irlml6402pbf.pdf\
?fileId=5546d462533600a401535668d5c2263c
  Mouser PN     : 942-IRLML6402TRPBF
  Mouser URL    : https://www.mouser.co.uk/ProductDetail/Infineon-\
Technologies/IRLML6402TRPBF?qs=9%252BKlkBgLFf0HuZuONx2Ewg%3D%3D
  Arrow PN      : IRLML6402TRPBF
  Arrow URL     : https://www.arrow.com/en/products/irlml6402trpbf/\
infineon-technologies-ag?utm_currency=USD&region=nac
  Pricing       : NOT in datasheet/SamacSys — needs live distributor quote
"""


def _irlml6402trpbf_footprint() -> Footprint:
    """SOT-23 footprint per Infineon IRLML6402TRPBF datasheet p7
    (Micro3 / SOT-23 / JEDEC TO-236AB) and the SamacSys-generated KiCad
    footprint `SOT95P237X112-3N.kicad_mod`.

    Pad geometry — verbatim from `SOT95P237X112-3N.kicad_mod`:
      pad 1 (G): (-1.05, -0.95) mm, 0.6 × 1.3 mm SMD rect
      pad 2 (S): (-1.05, +0.95) mm, 0.6 × 1.3 mm SMD rect
      pad 3 (D): (+1.05,  0.00) mm, 0.6 × 1.3 mm SMD rect

    Body outline (F.Fab): 1.30 mm × 2.92 mm rectangle centered at origin,
    matching datasheet E1=1.20-1.40 mm and D=2.80-3.04 mm.

    Courtyard (F.CrtYd): 3.90 × 3.54 mm — derived from the SamacSys
    `.kicad_mod` (±1.95 mm × ±1.77 mm from origin).

    Height: 1.12 mm (datasheet A max).
    """
    return Footprint(
        name="SOT95P237X112-3N",
        package_class="SOT-23",
        pads=[
            Pad(num="1", position_mm=(-1.05, 0.95),
                size_mm=(1.3, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.05, -0.95),
                size_mm=(1.3, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(1.05, 0.0),
                size_mm=(1.3, 0.6), shape="rect", layer="F.Cu"),
        ],
        body_outline=[
            (-0.65, -1.46),
            (+0.65, -1.46),
            (+0.65, +1.46),
            (-0.65, +1.46),
        ],
        courtyard=[
            (-1.95, -1.77),
            (+1.95, -1.77),
            (+1.95, +1.77),
            (-1.95, +1.77),
        ],
        pitch_mm=0.95,                         # datasheet `e` BSC
        size_mm=(2.92, 1.30),                  # nominal D × E1
        height_mm=1.12,                        # datasheet A max
        model_3d_path="application/src/smash/parts/sources/IRLML6402TRPBF/IRLML6402TRPBF.stp",
        source="samacsys",
        note=(
            "SamacSys-generated KiCad footprint, IPC name "
            "SOT95P237X112-3N (0.95 mm pitch, 2.37 mm overall lead "
            "span, 1.12 mm max height, 3 pins). Conforms to JEDEC "
            "TO-236AB outline (datasheet p7)."
        ),
    )


def add_irlml6402trpbf(design, ref: str, **overrides) -> Chip:
    """Infineon (formerly International Rectifier) IRLML6402TRPBF —
    HEXFET® Power MOSFET, P-channel, V_DSS=-20 V, R_DS(on)=65 mΩ max
    @ V_GS=-4.5 V, I_D=-3.7 A continuous, SOT-23 (Micro3) package.

    Ground-truth artifacts live in `parts/sources/IRLML6402TRPBF/`:
      - datasheet:  IRLML6402TRPBF.pdf (Infineon, rev 2014-04-28)
      - SamacSys:   LIB_IRLML6402TRPBF.samacsys.zip
      - footprint:  SOT95P237X112-3N.kicad_mod
      - 3D:         IRLML6402TRPBF.stp
      - pinmap:     pinmap.txt  (G=1, S=2, D=3)

    Fields not in the schema are recorded verbatim in `note`
    (see module-level `_IRLML6402TRPBF_NOTE`).

    `overrides` keyword arguments are passed through to
    `Design.add_chip()` last, so any caller can override a transcribed
    value (e.g. set `board_tag`, `dnp`, `role`, `position_mm` at
    instantiation time without editing this factory).
    """
    fields = dict(
        manf="Infineon",
        manf_pn="IRLML6402TRPBF",
        canonical_id="irlml6402trpbf",
        name="IRLML6402TRPBF",
        value="IRLML6402TRPBF",
        description=(
            "HEXFET Power MOSFET, P-Channel, V_DSS=-20 V, "
            "R_DS(on)=65 mOhm max @ V_GS=-4.5 V, I_D=-3.7 A, "
            "SOT-23 (Micro3)"
        ),
        datasheet="application/src/smash/parts/sources/IRLML6402TRPBF/IRLML6402TRPBF.pdf",

        # Sourcing — not in datasheet; left unset, see note.
        fab_country=None,
        currency=None,
        price_1pc=None,
        price_20kpc=None,
        weight_g=None,

        # Compliance — datasheet p1 + p9.
        # Strings are the qualification standards the part is rated
        # against; transcribed from the datasheet's compliance section.
        standards=[
            "RoHS",
            "Halogen-Free",
            "JEDEC TO-236AB",
            "JEDEC JESD47F (Consumer)",
            "JEDEC J-STD-020D MSL1",
        ],
        eccn=None,                # NOT in datasheet
        itar=None,                # NOT in datasheet (commercial part)

        # Mechanical (package).
        package="SOT-23",         # also "Micro3" / JEDEC TO-236AB
        size_mm=(2.92, 1.30),     # nominal D × E1
        height_mm=1.12,           # datasheet A max
        temp_range_c=(-55, 150),  # T_J / T_STG (p1)
        body_material=None,       # NOT STATED in datasheet
        lead_material=None,       # NOT STATED; "Cu WIRE Halogen Free"
                                  # is the bond wire, not the leadframe

        # Electrical (Absolute Max + Electrical Characteristics, p1-2).
        # `voltage_rating_v` is V_DS max (datasheet uses negative sign
        # for P-channel; we store the magnitude).
        voltage_rating_v=20.0,    # V_DS max
        i_rms_a=3.7,              # I_D continuous @ T_A=25 °C, V_GS=-4.5V
        power_rating_w=1.3,       # P_D @ T_A=25 °C
        p_max_w=1.3,              # same — duplicate field, both populated

        # Thermal (p1).
        rth_jc_cw=None,           # NOT IN DATASHEET — only R_θJA given
        rth_ja_cw=100.0,          # R_θJA MAX. Typ=75 is in `note`.
        tj_max_c=150.0,           # T_J max

        # Pin list — datasheet p1 pin diagram + pinmap.txt + KiCad sym.
        # Three sources agree: G=1, S=2, D=3.
        pins=[
            Pin(num="1", name="G", aliases=["Gate"],   type="input"),
            Pin(num="2", name="S", aliases=["Source"], type="io"),
            Pin(num="3", name="D", aliases=["Drain"],  type="io"),
        ],

        # Footprint — built from SamacSys-generated `.kicad_mod`.
        footprint=_irlml6402trpbf_footprint(),

        # Free-form: every datasheet fact not yet structured.
        note=_IRLML6402TRPBF_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─────────────────────────────────────────────────────────────────────────
# Infineon (formerly International Rectifier) IRLML6244TRPBF
#
# N-channel HEXFET Power MOSFET, V_DS=20 V, R_DS(on) max 21 mΩ @ V_GS=4.5V,
# I_D=6.3 A. The N-channel counterpart to IRLML6402 in the same Micro3
# (SOT-23) package, used as a load/system switch.
#
# Ground-truth artifacts (parts/sources/IRLML6244TRPBF/):
#   - IRLML6244TRPBF.pdf         : datasheet, doc PD-97535A, rev 03/09/12
#   - LIB_IRLML6244TRPBF.samacsys.zip : SamacSys ECAD archive
#   - IRLML6244TRPBF.kicad_sym   : KiCad symbol (extracted from ZIP)
#   - SOT95P237X112-3N.kicad_mod : KiCad footprint (extracted from ZIP)
#   - IRLML6244TRPBF.stp         : STEP 3D model
#   - pinmap.txt, part_info.txt
# ─────────────────────────────────────────────────────────────────────────

_IRLML6244TRPBF_NOTE = """\
Datasheet extras (Infineon IRLML6244PbF, doc PD-97535A, 03/09/12) —
fields not yet promoted to the schema. Values transcribed verbatim;
N-channel device, all signs positive.

Absolute Max Ratings (table p1):
  V_GS gate-source voltage : ±12 V
  I_DM pulsed drain current: 32 A
  I_D @ T_A=70 °C, V_GS=10V: 5.1 A
  P_D @ T_A=25 °C          : 1.3 W
  P_D @ T_A=70 °C          : 0.80 W
  Linear derating factor   : 0.01 W/°C

R_θJA (table p1):
  steady state max : 100 °C/W  (this is what rth_ja_cw holds)
  t<10 s max       :  99 °C/W

Electrical Characteristics @ T_J=25 °C (table p2):
  V_(BR)DSS : 20 V min (V_GS=0V, I_D=250 µA)
  ΔV_(BR)DSS/ΔT_J : 7.8 mV/°C typ (ref 25 °C, I_D=1 mA)
  R_DS(on) @ V_GS=4.5V, I_D=6.3A : 16.0 mΩ typ / 21.0 mΩ max
  R_DS(on) @ V_GS=2.5V, I_D=5.1A : 22.0 mΩ typ / 27.0 mΩ max
  V_GS(th) gate threshold : 0.5 min / 0.9 typ / 1.1 max V
                            (V_DS=V_GS, I_D=10 µA)
  gfs forward transconductance : 17 S min (V_DS=10V, I_D=6.3A)
  I_DSS : 1.0 µA max @ V_DS=16V, V_GS=0V (25 °C);
          150 µA max at T_J=125 °C
  I_GSS : 100 nA fwd / -100 nA rev (V_GS=±12V)
  R_G internal gate resistance : 1.7 Ω typ
  Q_g  : 8.9  nC typ   (I_D=6.3A, V_DS=10V, V_GS=4.5V)
  Q_gs : 0.68 nC typ
  Q_gd : 4.4  nC typ
  Switching times (V_DD=10V, I_D=1.0A, R_G=6.8Ω, V_GS=4.5V):
    t_d(on) =  4.9 ns typ
    t_r     =  7.5 ns typ
    t_d(off)= 19   ns typ
    t_f     = 12   ns typ
  Capacitances @ V_DS=16V, V_GS=0V, f=1 MHz:
    C_iss = 700 pF typ
    C_oss = 140 pF typ
    C_rss =  98 pF typ

Body-diode ratings (table p2):
  I_S continuous source current : 1.3 A
  I_SM pulsed                   : 32 A
  V_SD diode forward voltage : 1.2 V max (T_J=25 °C, I_S=6.3A, V_GS=0V)
  t_rr reverse recovery time : 12 ns typ / 18 ns max
                               (T_J=25 °C, V_R=15V, I_F=1.3A)
  Q_rr reverse recovery charge : 5.1 nC typ / 7.7 nC max
                                 (di/dt=100 A/µs)

Qualification (datasheet p9):
  Qualification level    : Consumer (per JEDEC JESD47F)
  Moisture sensitivity   : MSL1 (per IPC/JEDEC J-STD-020D)
  RoHS                   : Yes
  >>> Consumer-grade only — NOT AEC-Q101 nor industrial. Higher
      qualification ratings may be available on request per p9 footnote.

Standard pack:
  Form     : Tape and reel
  Quantity : 3000

Mechanical (NOT stated in datasheet — needed from supplier traceability):
  body_material, lead_material, weight_g, density_g_cm3, cte_ppm_k
  fab_country — NOT IN DATASHEET

Distributor links (from SamacSys metadata):
  datasheet URL : http://www.infineon.com/dgdl/irlml6244pbf.pdf\
?fileId=5546d462533600a4015356686fed261f
  Mouser PN     : 942-IRLML6244TRPBF
  Mouser URL    : https://www.mouser.co.uk/ProductDetail/Infineon-\
Technologies/IRLML6244TRPBF?qs=9%252BKlkBgLFf1HkY%2F2U%252BIhLQ%3D%3D
  Arrow PN      : IRLML6244TRPBF
  Pricing       : NOT captured — needs live distributor quote
"""


def _irlml6244trpbf_footprint() -> Footprint:
    """SOT-23 footprint per Infineon IRLML6244TRPBF datasheet p8
    (Micro3 / SOT-23 / JEDEC TO-236AB) and the SamacSys-generated KiCad
    footprint `SOT95P237X112-3N.kicad_mod` from the IRLML6244 SamacSys
    archive. The footprint is identical to IRLML6402's (same package,
    same SamacSys generator).
    """
    return Footprint(
        name="SOT95P237X112-3N",
        package_class="SOT-23",
        pads=[
            Pad(num="1", position_mm=(-1.05, 0.95),
                size_mm=(1.3, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.05, -0.95),
                size_mm=(1.3, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(1.05, 0.0),
                size_mm=(1.3, 0.6), shape="rect", layer="F.Cu"),
        ],
        body_outline=[
            (-0.65, -1.46), (+0.65, -1.46),
            (+0.65, +1.46), (-0.65, +1.46),
        ],
        courtyard=[
            (-1.95, -1.77), (+1.95, -1.77),
            (+1.95, +1.77), (-1.95, +1.77),
        ],
        pitch_mm=0.95,
        size_mm=(2.92, 1.30),
        height_mm=1.12,
        model_3d_path="application/src/smash/parts/sources/IRLML6244TRPBF/IRLML6244TRPBF.stp",
        source="samacsys",
        note=(
            "SamacSys footprint, IPC name SOT95P237X112-3N. "
            "Conforms to JEDEC TO-236AB (datasheet p8)."
        ),
    )


def add_irlml6244trpbf(design, ref: str, **overrides) -> Chip:
    """Infineon IRLML6244TRPBF — N-channel HEXFET Power MOSFET,
    V_DSS=20 V, R_DS(on)=21 mΩ max @ V_GS=4.5 V, I_D=6.3 A continuous,
    SOT-23 (Micro3) package. Application: load/system switch.

    Ground-truth in `parts/sources/IRLML6244TRPBF/`.
    """
    fields = dict(
        manf="Infineon",
        manf_pn="IRLML6244TRPBF",
        canonical_id="irlml6244trpbf",
        name="IRLML6244TRPBF",
        value="IRLML6244TRPBF",
        description=(
            "HEXFET Power MOSFET, N-Channel, V_DSS=20 V, "
            "R_DS(on)=21 mOhm max @ V_GS=4.5 V, I_D=6.3 A, "
            "SOT-23 (Micro3)"
        ),
        datasheet="application/src/smash/parts/sources/IRLML6244TRPBF/IRLML6244TRPBF.pdf",
        fab_country=None,
        currency=None,
        price_1pc=None,
        price_20kpc=None,
        weight_g=None,
        standards=[
            "RoHS",
            "Halogen-Free",
            "JEDEC TO-236AB",
            "JEDEC JESD47F (Consumer)",
            "JEDEC J-STD-020D MSL1",
        ],
        eccn=None,
        itar=None,
        package="SOT-23",
        size_mm=(2.92, 1.30),
        height_mm=1.12,
        temp_range_c=(-55, 150),
        body_material=None,
        lead_material=None,
        voltage_rating_v=20.0,    # V_DS max (p1)
        i_rms_a=6.3,              # I_D @ T_A=25 °C, V_GS=10V (p1)
        power_rating_w=1.3,       # P_D @ T_A=25 °C (p1)
        p_max_w=1.3,
        rth_jc_cw=None,           # NOT in datasheet
        rth_ja_cw=100.0,          # R_θJA steady-state max (p1)
        tj_max_c=150.0,
        pins=[
            Pin(num="1", name="G", aliases=["Gate"],   type="input"),
            Pin(num="2", name="S", aliases=["Source"], type="io"),
            Pin(num="3", name="D", aliases=["Drain"],  type="io"),
        ],
        footprint=_irlml6244trpbf_footprint(),
        note=_IRLML6244TRPBF_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─────────────────────────────────────────────────────────────────────────
# onsemi BSS138LT1G
#
# N-channel logic-level MOSFET, V_DSS=50 V, I_D=200 mA, SOT-23. Used
# where higher V_DS is needed than the IRLML6244 can give (e.g. level
# shifters, low-current high-voltage switching).
#
# Ground-truth artifacts (parts/sources/BSS138LT1G/):
#   - BSS138LT1G.pdf      : datasheet, BSS138LT1/D rev 14, April 2024
#                           (original publication 2016)
#   - BSS138LT1G.kicad_sym: KiCad symbol (project library_kicad)
#   - BSS138LT1G.stp      : STEP 3D model
#   - pinmap.txt          : G=1, S=2, D=3
#   - part_info.txt       : project metadata (package SOT96P237X111-3N)
#
# NOTE: no SamacSys ZIP / .kicad_mod is currently in the repo for this
# part. The footprint is built directly from onsemi's recommended
# mounting footprint (datasheet p6) — 0.56 × 0.95 mm pads on 1.90 mm
# vertical pitch — rather than the IPC-density-B SamacSys derivative.
# When the SamacSys archive is fetched later, this can be updated.
# ─────────────────────────────────────────────────────────────────────────

_BSS138LT1G_NOTE = """\
Datasheet extras (onsemi BSS138LT1G, doc BSS138LT1/D, rev 14
April 2024) — fields not yet promoted to the schema. N-channel,
all signs positive.

Absolute Max Ratings (table p1):
  V_DSS  drain-source voltage : 50 V
  V_GS   gate-source voltage  : ±20 V (continuous)
  I_D    continuous @ T_A=25 °C : 200 mA
  I_DM   pulsed (tp ≤ 10 µs) : 800 mA
  P_D    @ T_A=25 °C : 225 mW
  R_θJA  : 556 °C/W   (stored in rth_ja_cw)
  T_L    max lead temp for 10 s soldering : 260 °C
  ESD ratings (datasheet feature bullets):
    HBM Class 0A
    MM  Class M1A
    CDM Class IV

OFF Characteristics (table p2):
  V_(BR)DSS : 50 V min (V_GS=0, I_D=250 µA)
  I_DSS @ V_DS=25V, 25 °C  : 0.1 µA max
  I_DSS @ V_DS=50V, 25 °C  : 0.5 µA max
  I_DSS @ V_DS=50V, 150 °C : 5.0 µA max
  I_GSS @ V_GS=±20V        : ±0.1 µA max

ON Characteristics (table p2):
  V_GS(th) gate threshold : 0.85 V min / 1.5 V max
                            (V_DS=V_GS, I_D=1.0 mA)
  r_DS(on) @ V_GS=2.75V, I_D<200 mA, T_A=-40..+85 °C :
                            5.6 Ω typ / 10 Ω max
  r_DS(on) @ V_GS=5.0V, I_D=200 mA : 3.5 Ω typ
  gfs forward transconductance : 100 mmhos min
                                 (V_DS=25V, I_D=200 mA, f=1 kHz)

Dynamic Characteristics (table p2, f=1 MHz, V_DS=25V, V_GS=0):
  C_iss : 40 typ / 50 max pF
  C_oss : 12 typ / 25 max pF
  C_rss : 3.5 typ / 5.0 max pF

Switching (table p2, V_DD=30V, I_D=0.2A):
  t_d(on)  : 20 ns max
  t_d(off) : 20 ns max
(Note 2: switching chars independent of T_J)

Qualification:
  Pb-Free, Halogen Free / BFR Free, RoHS Compliant.
  ESD: HBM Class 0A, MM Class M1A, CDM Class IV.
  >>> The BSS138LT1G variant is COMMERCIAL. The closely-related
      BVSS138LT1G (BVSS prefix) is AEC-Q101 Qualified and PPAP
      Capable — switch to BVSS for automotive/high-reliability
      paths.

Part-marking code: J1 (Device Code) + M (Date Code)
(datasheet p1 marking diagram)

Package (Case 318, Issue AU, dated 14 Aug 2024):
  outline conforms to JEDEC TO-236
  Dimensions D × E × A = 2.90 × 1.30 × 1.00 mm nominal,
                         max 3.04 × 1.40 × 1.11 mm
  Pitch e = 1.78-1.90-2.04 mm

FOOTPRINT NOTE: The current `footprint` field is built from onsemi's
recommended mounting footprint (datasheet p6): 0.56 × 0.95 mm pads
on 1.90 mm vertical pitch. The KiCad-sym lists footprint name
SOT96P237X111-3N (SamacSys IPC convention). No SamacSys ZIP /
.kicad_mod is currently in parts/sources/ — fetch and replace when
available.

Mechanical (NOT stated in datasheet):
  body_material, lead_material, weight_g, density_g_cm3, cte_ppm_k,
  fab_country.

Distributor links (from KiCad sym):
  datasheet URL : https://www.onsemi.com/pub/Collateral/BSS138LT1-D.PDF
  Mouser PN     : 863-BSS138LT1G
  Mouser URL    : https://www.mouser.co.uk/ProductDetail/onsemi/\
BSS138LT1G?qs=vNc2DXHODiKPZ2y3rQhTYQ%3D%3D
  Arrow PN      : BSS138LT1G
  Pricing       : NOT captured — needs live distributor quote
"""


def _bss138lt1g_footprint() -> Footprint:
    """SOT-23 footprint per onsemi BSS138LT1G datasheet p6 recommended
    mounting footprint. NOT from a SamacSys .kicad_mod — that file is
    not currently in the repo. Pads from the datasheet diagram, rotated
    into the project's horizontal SOT-23 orientation (leads along ±x),
    in the model's math-y-up frame:

      pad size       : 0.95 mm (W, along the lead) × 0.56 mm (H) — the
                        datasheet's 0.56 × 0.95 pad rotated with the
                        layout so the long axis follows the lead
      pad 1 (G) at   : (-1.05, +0.95) mm  [pin 1: upper-left, y-up]
      pad 2 (S) at   : (-1.05, -0.95) mm  [pin 2: lower-left]
      pad 3 (D) at   : (+1.05,  0.00) mm  [pin 3: right-center]
      pin 1↔2 pitch  : 1.90 mm  (datasheet `e` nominal)
      lateral pitch  : ≈2.10 mm pad-c-to-pad-c (from layout symmetry;
                        datasheet shows 0.95 vertical pad offset and
                        leaves the lateral spacing implicit through HE)

    The pad-centre coordinates are picked to match the project's
    standard SOT-23 layout (same convention as IRLML6402/IRLML6244 and
    the library_kicad SOT96P237X111-3N vendor footprint, which puts
    pin 1 upper-left) so physical interchange is unambiguous.
    (2026-09-01: the original transcription wrote the y-signs in the
    datasheet's screen-y-down sense and kept the pad W/H unrotated —
    pin 1/2 copper was vertically mirrored and the pads lay across the
    leads instead of along them.)
    """
    return Footprint(
        name="SOT96P237X111-3N",      # from BSS138 KiCad sym Footprint property
        package_class="SOT-23",
        pads=[
            Pad(num="1", position_mm=(-1.05, 0.95),
                size_mm=(0.95, 0.56), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.05, -0.95),
                size_mm=(0.95, 0.56), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(1.05, 0.0),
                size_mm=(0.95, 0.56), shape="rect", layer="F.Cu"),
        ],
        body_outline=[
            # Datasheet Case 318: D=2.90 × E1=1.30 nominal body
            (-0.65, -1.45), (+0.65, -1.45),
            (+0.65, +1.45), (-0.65, +1.45),
        ],
        courtyard=[],                 # not derived — ringed below from pads
        pitch_mm=1.90,                # `e` nominal (pin 1 to pin 2 c-to-c)
        size_mm=(2.90, 1.30),         # D × E1 nominal
        height_mm=1.11,               # A max
        model_3d_path="application/src/smash/parts/sources/BSS138LT1G/BSS138LT1G.stp",
        source="onsemi-datasheet",
        note=(
            "Built from onsemi datasheet p6 'Recommended Mounting "
            "Footprint' (0.56 × 0.95 mm pads on 1.90 mm vertical "
            "pitch). NOT derived from a SamacSys .kicad_mod — that "
            "archive is not currently in parts/sources/BSS138LT1G/. "
            "Footprint name (SOT96P237X111-3N) is from the KiCad "
            "symbol's Footprint property."
        ),
    ).ensure_courtyard_clearance()    # SamacSys F.CrtYd absent — ring the pads


def add_bss138lt1g(design, ref: str, **overrides) -> Chip:
    """onsemi BSS138LT1G — N-channel logic-level MOSFET, V_DSS=50 V,
    R_DS(on)=3.5 Ω typ @ V_GS=5.0 V, I_D=200 mA continuous, SOT-23.

    The BSS138L family is the workhorse low-side switch / level-shifter
    NMOS. Lower current than IRLML6244 (200 mA vs 6.3 A) but 2.5× the
    V_DS (50 V vs 20 V) — pick this when the rail is >20 V or when
    standard pull-up level-shifting is the topology.

    Variant note: `BVSS138LT1G` (BVSS prefix) is the AEC-Q101-qualified
    automotive variant — same die, different qual + PPAP. Switch to
    that part number for automotive/high-reliability paths.

    Ground-truth in `parts/sources/BSS138LT1G/`.
    """
    fields = dict(
        manf="onsemi",
        manf_pn="BSS138LT1G",
        canonical_id="bss138lt1g",
        name="BSS138LT1G",
        value="BSS138LT1G",
        description=(
            "MOSFET Power N-Channel, V_DSS=50 V, "
            "R_DS(on)=3.5 Ohm typ @ V_GS=5.0 V, I_D=200 mA, SOT-23"
        ),
        datasheet="application/src/smash/parts/sources/BSS138LT1G/BSS138LT1G.pdf",
        fab_country=None,
        currency=None,
        price_1pc=None,
        price_20kpc=None,
        weight_g=None,
        standards=[
            "RoHS",
            "Halogen-Free",
            "BFR-Free",
            "Pb-Free",
            "JEDEC TO-236",
            "ESD HBM Class 0A",
            "ESD MM Class M1A",
            "ESD CDM Class IV",
        ],
        eccn=None,
        itar=None,
        package="SOT-23",
        size_mm=(2.90, 1.30),         # D × E1 nominal
        height_mm=1.11,               # A max
        temp_range_c=(-55, 150),      # T_J, T_stg (p1)
        body_material=None,
        lead_material=None,
        voltage_rating_v=50.0,        # V_DSS (p1)
        i_rms_a=0.200,                # I_D = 200 mA continuous @ T_A=25 °C
        power_rating_w=0.225,         # P_D = 225 mW @ T_A=25 °C
        p_max_w=0.225,
        rth_jc_cw=None,               # NOT in datasheet
        rth_ja_cw=556.0,              # R_θJA (p1) — high because SOT-23
        tj_max_c=150.0,
        pins=[
            Pin(num="1", name="G", aliases=["Gate"],   type="input"),
            Pin(num="2", name="S", aliases=["Source"], type="io"),
            Pin(num="3", name="D", aliases=["Drain"],  type="io"),
        ],
        footprint=_bss138lt1g_footprint(),
        note=_BSS138LT1G_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─────────────────────────────────────────────────────────────────────────
# Diodes Inc. DMN6075SQ-7 — 60 V N-channel MOSFET, SOT-23
#
# Ground-truth in parts/sources/DMN6075SQ-7/ (SamacSys zip + DS
# DIOD-S-A0009189360-1 → DMN6075SQ.pdf). The 12× low-side sector-select
# switch in the aft activation array: blocks the 30 V FIRE_HV rail,
# passes the ~1 A burn-wire current with 2× margin, driven ~4 V from the
# BAT_PROT-powered CD74HC4514 decoder (so a worst-case 3 V-threshold part
# is still well enhanced).
# ─────────────────────────────────────────────────────────────────────────

_DMN6075SQ_NOTE = """\
Datasheet extras (Diodes Inc. DMN6075SQ, DIOD-S-A0009189360-1).

Absolute Max (25 °C):
  V_DSS  drain-source           : 60 V
  V_GSS  gate-source            : ±20 V
  I_DM   pulsed drain (10 µs)   : 12 A
  T_J / T_stg                   : 150 °C

Static (typ/max):
  R_DS(on) @ V_GS=10 V          : 69 / 85 mΩ   (I_D=3.2 A)
  R_DS(on) @ V_GS=4.5 V         : 75 / 120 mΩ  (I_D=2.8 A)
  V_GS(th)                      : 1 / 3 V       (V_DS=V_GS, I_D=250 µA)
  I_D continuous @ V_GS=10 V    : 2.5 A
  I_D continuous @ V_GS=4.5 V   : 2.0 A
  Q_g @ V_GS=4.5 V              : 5.6 nC

AEC-Q101 qualified. SOT-23 (pins: 1=G, 2=S, 3=D).

Smash use: aft activation array, low-side sector select (one of 12). The
gate is driven by a CD74HC4514 output rail powered from BAT_PROT
(~3.6-4.2 V) — chosen over 3V3 precisely because V_GS(th) runs to 3 V max,
so 3.3 V drive could leave a worst-case part barely on. Source→GND,
drain→one nichrome burn-wire; FIRE_HV (30 V cap) reaches the wire only
when the DMP6110 ARM is on.
"""


def _dmn6075sq_footprint() -> Footprint:
    pn = "DMN6075SQ-7"
    fp_mod = src(pn, "SOT96P240X110-3N.kicad_mod")
    return Footprint(
        name="SOT96P240X110-3N",
        package_class="SOT-23",
        pads=pads_from_kicad_mod(fp_mod),
        body_outline=outline_polygon(fp_mod, "F.Fab"),
        courtyard=outline_polygon(fp_mod, "F.CrtYd"),
        pitch_mm=0.95,
        size_mm=(2.90, 1.30),
        height_mm=1.10,
        model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
        source="samacsys",
    )


def add_dmn6075sq_7(design, ref: str, **overrides) -> Chip:
    """Diodes Inc. DMN6075SQ-7 — 60 V N-channel MOSFET, R_DS(on)=120 mΩ
    @ V_GS=4.5 V, I_D=2.0 A continuous / 12 A pulsed, V_GS(th)=1..3 V,
    SOT-23. AEC-Q101. The aft activation array's low-side sector select."""
    pn = "DMN6075SQ-7"
    fields = dict(
        manf="Diodes Incorporated", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=(
            "MOSFET N-Channel, V_DSS=60 V, R_DS(on)=120 mΩ @ V_GS=4.5 V, "
            "I_D=2.0 A, V_GS(th)=1..3 V, SOT-23"
        ),
        datasheet=datasheet_ref(pn, "DMN6075SQ.pdf"),
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None,
        standards=["AEC-Q101", "RoHS", "Halogen-Free", "Pb-Free"],
        eccn=None, itar=None,
        package="SOT-23",
        size_mm=(2.90, 1.30),
        height_mm=1.10,
        temp_range_c=(-55, 150),       # T_J / T_stg
        body_material=None, lead_material=None,
        voltage_rating_v=60.0,         # V_DSS
        i_rms_a=2.0,                   # I_D continuous @ V_GS=4.5 V
        power_rating_w=None,
        rth_jc_cw=None,
        tj_max_c=150.0,
        pins=build_pins(
            src(pn, f"{pn}.kicad_sym"),
            types={"G": "input", "S": "io", "D": "io"},
            aliases={"G": ["Gate"], "S": ["Source"], "D": ["Drain"]},
        ),
        footprint=_dmn6075sq_footprint(),
        note=_DMN6075SQ_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ─────────────────────────────────────────────────────────────────────────
# Diodes Inc. DMP6110SVT-7 — -60 V P-channel MOSFET, TSOT-26
#
# Ground-truth in parts/sources/DMP6110SVT-7/ (SamacSys zip + DS
# DIOD-S-A0001248745-1 → DMP6110SVT.pdf). The aft activation array's
# high-side master ARM: isolates the charged 30 V firing cap from all 12
# burn-wires until ACTIVATE_SET arms. Drain split across pins 1,2,5,6
# (paralleled in the package). Source sits at FIRE_HV (30 V), so the gate
# needs a zener clamp (V_GSS ±20 V) on the level-shift drive.
# ─────────────────────────────────────────────────────────────────────────

_DMP6110SVT_NOTE = """\
Datasheet extras (Diodes Inc. DMP6110SVT, DIOD-S-A0001248745-1).

Absolute Max (25 °C):
  V_DSS  drain-source           : -60 V
  V_GSS  gate-source            : ±20 V   ← gate must be clamped (source=30 V)
  I_DM   pulsed drain (380 µs)  : -24 A
  T_J / T_stg                   : 150 °C

Static (typ/max):
  R_DS(on) @ V_GS=-10 V         : 105 mΩ  (I_D=-4.5 A)
  R_DS(on) @ V_GS=-4.5 V        : 130 mΩ  (I_D=-3.5 A)
  V_GS(th)                      : -1 / -3 V
  I_D continuous @ V_GS=-10 V   : -7.3 A
  I_D continuous @ V_GS=-4.5 V  : -6.5 A
  V_SD diode forward            : -0.7 / -1.2 V (I_S=-1 A)

AEC-Q101 qualified. TSOT-26 (pins: 1,2,5,6=D, 3=G, 4=S).

Smash use: aft activation array, high-side ARM. Source→FIRE_HV (30 V cap),
drain→the 12 sector-select NFET array. Disarmed, the cap can't reach any
burn-wire even if a select NFET shorts. Because the source rides at 30 V,
the gate is driven through a level-shift NFET (ACTIVATE_SET) with a
~12-15 V zener gate-source clamp so V_GS stays inside the ±20 V limit while
still fully enhancing the device (R_DS(on) 105 mΩ at -10 V).
"""


def _dmp6110svt_footprint() -> Footprint:
    pn = "DMP6110SVT-7"
    fp_mod = src(pn, "SOT95P280X100-6N.kicad_mod")
    return Footprint(
        name="SOT95P280X100-6N",
        package_class="TSOT-26",
        pads=pads_from_kicad_mod(fp_mod),
        body_outline=outline_polygon(fp_mod, "F.Fab"),
        courtyard=outline_polygon(fp_mod, "F.CrtYd"),
        pitch_mm=0.95,
        size_mm=(2.90, 1.60),
        height_mm=1.00,
        model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
        source="samacsys",
    )


def add_dmp6110svt_7(design, ref: str, **overrides) -> Chip:
    """Diodes Inc. DMP6110SVT-7 — -60 V P-channel MOSFET, R_DS(on)=130 mΩ
    @ V_GS=-4.5 V, I_D=-6.5 A continuous / -24 A pulsed, V_GS(th)=-1..-3 V,
    V_GSS ±20 V, TSOT-26. AEC-Q101. The aft activation array's high-side
    ARM (drain on pins 1,2,5,6)."""
    pn = "DMP6110SVT-7"
    fields = dict(
        manf="Diodes Incorporated", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=(
            "MOSFET P-Channel, V_DSS=-60 V, R_DS(on)=130 mΩ @ V_GS=-4.5 V, "
            "I_D=-6.5 A, V_GS(th)=-1..-3 V, TSOT-26"
        ),
        datasheet=datasheet_ref(pn, "DMP6110SVT.pdf"),
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=None,
        standards=["AEC-Q101", "RoHS", "Halogen-Free", "Pb-Free"],
        eccn=None, itar=None,
        package="TSOT-26",
        size_mm=(2.90, 1.60),
        height_mm=1.00,
        temp_range_c=(-55, 150),
        body_material=None, lead_material=None,
        voltage_rating_v=60.0,         # |V_DSS|
        i_rms_a=6.5,                   # |I_D| continuous @ V_GS=-4.5 V
        power_rating_w=None,
        rth_jc_cw=None,
        tj_max_c=150.0,
        pins=build_pins(
            src(pn, f"{pn}.kicad_sym"),
            types={"G": "input", "S": "io",
                   "D_1": "io", "D_2": "io", "D_3": "io", "D_4": "io"},
            aliases={"G": ["Gate"], "S": ["Source"],
                     "D_1": ["D", "Drain"]},
        ),
        footprint=_dmp6110svt_footprint(),
        note=_DMP6110SVT_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
