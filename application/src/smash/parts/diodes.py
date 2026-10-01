"""Discrete diode factories (Schottky, signal, TVS).

Every value transcribed from per-part ground-truth in
`parts/sources/<PN>/`.
"""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint
from smash.parts._chip_mass import WEIGHT_G_SOT
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


# ═════════════════════════════════════════════════════════════════════════
# onsemi MBRS340T3G — 3 A, 40 V Schottky power rectifier, SMC package
# ═════════════════════════════════════════════════════════════════════════

_MBRS340T3G_NOTE = """\
Datasheet extras (onsemi MBRS320T3G/MBRS330T3G/MBRS340T3G family,
MBRS340T3/D, Aug 2021 rev 15).

Family voltage variants (datasheet p1 ordering table):
  MBRS320T3G   :  20 V (V_RRM)
  MBRS330T3G   :  30 V
  MBRS340T3G   :  40 V   <-- this factory
  SBRS8320T3G  :  20 V, AEC-Q101 + PPAP (automotive)
  SBRS8340T3G  :  40 V, AEC-Q101 + PPAP (automotive)
  NRVBS330T3G  :  30 V, AEC-Q101 + PPAP (automotive)
>>> For AEC-Q101 paths, use SBRS8340T3G — same die, automotive qual.

Maximum Ratings (p2):
  V_RRM peak repetitive reverse voltage : 40 V  (this is the 40R variant)
  I_F(AV) average rectified forward current : 3.0 A @ T_L=110 °C
                                              4.0 A @ T_L=105 °C
  I_FSM non-repetitive peak surge (half-wave, 60 Hz, 1 cycle) : 80 A
  T_J operating junction : -65 to +150 °C
  ISO 7637 Pulse #1 (100 V, 10 W) : 5000 pulses
  ESD MM : > 400 V (Class C)
  ESD HBM: > 8000 V (Class 3B)

Thermal:
  R_θJL junction-to-lead : 11 °C/W

Electrical (T_J=25 °C, p2):
  V_F forward voltage max : 0.50 V @ I_F=3.0 A
  I_R reverse current max : 2.0 mA @ rated V_R (25 °C)
                            20 mA @ rated V_R (100 °C)
  Typical capacitance @ V_R=0 : 658 pF (datasheet p3 Fig 5)

Mechanical (p1):
  Package : SMC 2-LEAD (Case 403AC, JEDEC DO-214AB)
  Body : epoxy, molded; UL 94 V-0
  Weight : 217 mg (approximate)
  Polarity : polarity band on plastic body indicates CATHODE lead
  Cathode lead temp for soldering : 260 °C max for 10 s
  MSL : MSL 1
  ESD : MM Class C, HBM Class 3B (datasheet p1 Mechanical Char)
  Lead finish : Pb-Free, Halogen Free/BFR Free, RoHS Compliant
  >>> WEIGHT IS STATED in datasheet — 217 mg / 0.217 g
"""


def _mbrs340_smc_footprint() -> Footprint:
    """SMC 2-LEAD package per SamacSys DIOM8059X261N.kicad_mod.

    Pads at (±3.45, 0), 2.25 × 3.15 mm each. Body 7.95 × 5.9 ×
    2.61 mm. The SamacSys IPC naming DIOM8059X261N translates to
    DIO (diode), Molded (M), body 8059 (8.0×5.9 mm), X261N (2.61 mm
    height).
    """
    return Footprint(
        name="DIOM8059X261N",
        package_class="SMC (DO-214AB)",
        pads=[
            # Pinmap: pin 1=K, pin 2=A.
            Pad(num="1", position_mm=(-3.45, 0.0),
                size_mm=(2.25, 3.15), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(+3.45, 0.0),
                size_mm=(2.25, 3.15), shape="rect", layer="F.Cu"),
        ],
        body_outline=[
            (-3.975, -2.95), (3.975, -2.95),
            (3.975, 2.95), (-3.975, 2.95),
        ],
        courtyard=[
            (-4.825, -3.375), (4.825, -3.375),
            (4.825, 3.375), (-4.825, 3.375),
        ],
        pitch_mm=None,                # 2-lead, no array pitch
        size_mm=(7.95, 5.90),
        height_mm=2.61,
        model_3d_path="application/src/smash/parts/sources/MBRS340T3G/MBRS340T3G.stp",
        source="samacsys",
        note=(
            "SMC package, JEDEC DO-214AB. Polarity band on body marks "
            "cathode = pin 1."
        ),
    )


def add_mbrs340t3g(design, ref: str, **overrides) -> Chip:
    """onsemi MBRS340T3G — Schottky power rectifier, V_RRM=40 V,
    I_F(AV)=3 A @ T_L=110 °C, V_F=0.50 V max @ 3 A, SMC (DO-214AB)
    package.

    For automotive use, switch to SBRS8340T3G (same die, AEC-Q101 + PPAP).
    """
    fields = dict(
        manf="onsemi",
        manf_pn="MBRS340T3G",
        canonical_id="mbrs340t3g",
        name="MBRS340T3G",
        value="MBRS340T3G",
        description=(
            "Schottky power rectifier, V_RRM=40 V, I_F(AV)=3 A "
            "@ T_L=110 °C, V_F=0.50 V max @ 3 A, SMC"
        ),
        datasheet="application/src/smash/parts/sources/MBRS340T3G/MBRS340T3G.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        # Weight is stated in this datasheet — populate.
        weight_g=0.217,
        standards=[
            "RoHS",
            "Pb-Free",
            "Halogen-Free",
            "BFR-Free",
            "UL 94 V-0",
            "MSL 1",
            "ISO 7637 Pulse #1 (5000 pulses)",
            "ESD MM Class C (>400 V)",
            "ESD HBM Class 3B (>8000 V)",
        ],
        eccn=None, itar=None,
        package="SMC (DO-214AB)",
        size_mm=(7.95, 5.90),
        height_mm=2.61,
        temp_range_c=(-65, 150),    # T_J operating
        body_material="epoxy mold compound (UL 94 V-0)",
        lead_material=None,         # not stated, "corrosion-resistant external surfaces"
        voltage_rating_v=40.0,      # V_RRM
        i_rms_a=3.0,                # I_F(AV) @ T_L=110 °C
        power_rating_w=None,        # see datasheet Fig 6 (depends on duty)
        rth_jc_cw=None,
        rth_ja_cw=None,             # only R_θJL stated (11 °C/W)
        tj_max_c=150.0,
        pins=[
            # Pinmap.txt + datasheet polarity band: pin 1=K (cathode), pin 2=A
            Pin(num="1", name="K", aliases=["Cathode"], type="io"),
            Pin(num="2", name="A", aliases=["Anode"],   type="io"),
        ],
        footprint=_mbrs340_smc_footprint(),
        note=_MBRS340T3G_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_mbrs540t3g(design, ref: str, **overrides) -> Chip:
    """onsemi MBRS540T3G — Schottky power rectifier, V_RRM=40 V, I_F(AV)=5 A,
    V_F=0.50 V max @ 5 A (T_C=25 °C), SMC (DO-214AB). The 5 A sibling of the
    MBRS340 (same SMC package), sized to the battery/eFuse path so a depot USB-C
    can run the FULL unit by ORing VBUS into BAT_PROT.

    For automotive use, switch to NRVBS540T3G (same die, AEC-Q101)."""
    base = "MBRS540T3G"
    fp_mod = src(base, "DIOM7958X256N.kicad_mod")
    fields = dict(
        manf="onsemi", manf_pn="MBRS540T3G",
        canonical_id=canonical_id("MBRS540T3G"),
        name="MBRS540T3G", value="MBRS540T3G",
        description=(
            "Schottky power rectifier, V_RRM=40 V, I_F(AV)=5 A, "
            "V_F=0.50 V max @ 5 A, SMC"
        ),
        datasheet=datasheet_ref(base, f"{base}.pdf"),
        weight_g=0.217,            # datasheet: 217 mg
        standards=["RoHS", "Pb-Free", "Halogen-Free", "BFR-Free",
                   "UL 94 V-0", "MSL 1"],
        package="SMC (DO-214AB)",
        size_mm=(7.95, 5.90), height_mm=2.56,
        temp_range_c=(-65, 150),   # T_J operating
        body_material="epoxy mold compound (UL 94 V-0)",
        voltage_rating_v=40.0,     # V_RRM
        i_rms_a=5.0,               # I_F(AV)
        tj_max_c=150.0,
        pins=[
            Pin(num="1", name="K", aliases=["Cathode"], type="io"),
            Pin(num="2", name="A", aliases=["Anode"],   type="io"),
        ],
        footprint=Footprint(
            name="DIOM7958X256N", package_class="SMC (DO-214AB)",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            # Height is load-bearing: spacer-gap sizing reads it from the
            # FOOTPRINT, and a two-terminal IPC name (…X256N, no pin-count
            # field) does not parse, so without this the chain silently
            # falls back to its 2.0 mm assumption for a 2.56 mm part.
            size_mm=(7.95, 5.90), height_mm=2.56,
            model_3d_path=datasheet_ref(base, f"{base}.stp"),
            source="samacsys",
        ),
        note=(
            "5 A sibling of the MBRS340 (same SMC package). The depot USB-C ORs "
            "VBUS into BAT_PROT through this diode (Q_ISO's ideal-diode reverse-"
            "blocks the primary cells), so it's rated to the pack limit to run the full unit. "
            "Automotive: NRVBS540T3G (AEC-Q101)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


_PMEG040V050EPE_QZ_NOTE = """\
Datasheet extras (Nexperia PMEG040V050EPE, product data sheet 15 July 2024).

Ordering: the "-QZ" suffix is Nexperia PACKING only — per their FAQ, "the
suffix at the end of the part number refers to the packing method. There is
no difference in function or material composition between the variants."
Same die, same CFP15B, same AEC-Q101 qualification as the bare type number.

Limiting values (Table 5):
  V_R   reverse voltage (Tj = 25 °C)                    : 40 V
  I_F   forward current (δ = 1; Tsp ≤ 171 °C)           : 7 A
  I_F(AV) average forward current
        (δ = 0.5; f = 20 kHz; square; Tsp ≤ 172 °C)     : 5 A
  I_FSM non-repetitive peak (half sine, tp = 8.3 ms)    : 120 A
  P_tot total power dissipation (Tamb ≤ 25 °C)          : 1.66 W standard
                                                          2.15 W (1 cm² cathode pad)
  T_j   junction temperature                            : 175 °C
  T_amb / T_stg                                         : -55…175 / -65…175 °C

Thermal (Table 6):
  Rth(j-a)  free air, standard footprint                : 90 K/W
            with a 1 cm² cathode mounting pad           : 70 K/W
  Rth(j-sp) junction to solder point                    : 3 K/W

Characteristics (Tj = 25 °C, pulsed):
  V_F @ I_F = 1 A                                       : 360 typ / 420 max mV
  V_F @ I_F = 3 A                                       : 425 typ / 490 max mV
  V_F @ I_F = 5 A                                       : 475 typ / 520 max mV
  I_R @ V_R = 40 V                                      : 30 typ / 120 max µA

Mechanical:
  Package : CFP15B (SOT1289B), a.k.a. TO-277 / 3-PowerDFN — clip-bond,
            thermally enhanced ULTRA-THIN SMD; 3 leads, 2.13 mm pitch
  Body    : 5.8 × 4.3 × 0.95 mm; overall height 1.1 mm max
  Pinning : 1 = A (anode), 2 = A (anode), 3 = K (cathode, the clip pad)

Why this part (2026-09-02): it replaced the MBRS540T3G as D_BOOST_COMP.
Same 40 V / 5 A envelope and essentially the same forward drop (520 vs
500 mV max at 5 A), but 1.1 mm tall instead of 2.56 mm — the SMC body was
the one part on power_board's top face that pushed the power↔companion
spacer past what the rest of the gap needs. Also lower reverse leakage
(120 µA vs 0.3 mA max at rated V_R), 175 °C T_j instead of 150 °C, and
AEC-Q101 out of the box (MBRS540T3G needs the NRVBS540T3G sibling for that).
Surge is lower (120 A vs 190 A I_FSM), which is irrelevant for a DC-DC
rectifier that never sees a mains half-cycle.
"""


def add_pmeg040v050epe_qz(design, ref: str, **overrides) -> Chip:
    """Nexperia PMEG040V050EPE-QZ — low-V_F Schottky barrier rectifier,
    V_RRM=40 V, I_F(AV)=5 A, V_F=520 mV max @ 5 A, CFP15B (SOT1289B),
    1.1 mm max height. AEC-Q101.

    The flat, clip-bond alternative to the MBRS540T3G in the same 40 V/5 A
    envelope — see the note for why the height matters to spacer sizing."""
    pn = "PMEG040V050EPE-QZ"
    fp_mod = src(pn, "PMEG040V050EPEQZ.kicad_mod")
    fields = dict(
        manf="Nexperia", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=(
            "Schottky barrier rectifier, low V_F, V_RRM=40 V, "
            "I_F(AV)=5 A, V_F=520 mV max @ 5 A, CFP15B (1.1 mm)"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        standards=["AEC-Q101", "RoHS", "Pb-Free", "Halogen-Free"],
        package="CFP15B (SOT1289B)",
        size_mm=(5.80, 4.30), height_mm=1.10,
        temp_range_c=(-55, 175),      # T_j operating
        body_material="epoxy mold compound",
        voltage_rating_v=40.0,        # V_R
        i_rms_a=5.0,                  # I_F(AV)
        power_rating_w=1.66,          # P_tot, standard footprint, Tamb ≤ 25 °C
        tj_max_c=175.0,
        pins=build_pins(
            src(pn, f"{pn}.kicad_sym"),
            types={"A_1": "io", "A_2": "io", "K": "io"},
            aliases={"A_1": ["A", "Anode"], "A_2": ["A", "Anode"],
                     "K": ["Cathode"]},
        ),
        footprint=Footprint(
            name="PMEG040V050EPEQZ", package_class="CFP15B (SOT1289B)",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=2.13,
            # SamacSys names this footprint after the part, not IPC-7351,
            # so the name carries no height field — set it explicitly or
            # spacer sizing falls back to its 2.0 mm assumption.
            size_mm=(5.80, 4.30), height_mm=1.10,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=_PMEG040V050EPE_QZ_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Infineon BAT64-06-TP — dual Schottky diode, common-anode, SOT-23
# ═════════════════════════════════════════════════════════════════════════

def add_bat64_06_tp(design, ref: str, **overrides) -> Chip:
    """Infineon BAT64-06-TP — dual Si Schottky diode, common-anode
    configuration, V_R=40 V, I_F=250 mA, AEC-Q101 qualified, SOT-23.

    The '-TP' suffix indicates Tape & Pack (loose ammunition-pack
    packing, vs '-TR' tape-and-reel). Same die / footprint as -TR."""
    pn = "BAT64-06-TP"
    fp_mod = src(pn, "SOT95P237X125-3N.kicad_mod")
    fields = dict(
        manf="Infineon", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Dual Si Schottky diode, common anode, V_R=40 V, "
            "I_F=250 mA, AEC-Q101, SOT-23 (Tape & Pack)"
        ),
        datasheet=datasheet_ref(pn, "BAT64-04_06(SOT-23).pdf"),
        package="SOT-23",
        weight_g=WEIGHT_G_SOT["SOT-23"],  # SOT-23 typical (3.0×1.4×1.0 epoxy)
        temp_range_c=(-55, 150),
        voltage_rating_v=40.0,        # V_R per datasheet
        i_rms_a=0.250,                # I_F continuous
        standards=[
            "AEC-Q101",
            "RoHS", "Pb-Free",
        ],
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="SOT95P237X125-3N", package_class="SOT-23",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.95,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "Infineon BAT64-06 = dual Schottky, common-anode "
            "configuration. Pin 3 is the common anode; pins 1, 2 are "
            "separate cathodes (K1, K2). Used for bias isolation, "
            "polarity protection, and clamping. The -TP variant uses "
            "Tape & Pack (loose pack) packaging; switch to -TR for "
            "tape-and-reel.\n\n"
            "Same datasheet covers BAT64, BAT64-02, BAT64-04, BAT64-05, "
            "and BAT64-06 (different diode configurations in identical "
            "SOT-23 packages — see datasheet p1 marking table)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
