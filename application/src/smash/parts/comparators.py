"""Comparator factories.

Every value transcribed from per-part ground-truth in
`parts/sources/<PN>/`.
"""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments LMV331IDBVR — single comparator, open-drain output,
# rail-to-rail input, 2.7 V to 5 V VCC, SOT-23-5 (DBV)
# ═════════════════════════════════════════════════════════════════════════

_LMV331_NOTE = """\
Datasheet extras (TI LMV331/LMV393/LMV339, SLCS136V, rev May 2025).

This single-channel doc covers a family:
  LMV331 : single (this factory) — SOT-23-5
  LMV393 : dual    — SOIC-8 / VSSOP-8
  LMV339 : quad    — SOIC-14 / TSSOP-14 / VQFN-14

Absolute Max Ratings (p4 §5.1):
  V_CC supply voltage       : 5.5 V
  V_ID differential input   : ±5.5 V
  V_I input voltage range   : 0 to V_CC+
  Output short-circuit (one amplifier) to GND : unlimited (T_A ≤ 25 °C,
                                                            V_CC ≤ 5.5 V)
  T_J operating virtual junction : 150 °C
  T_STG storage : -65 to +150 °C
  >>> Short-circuit to V_CC can cause excessive heating; protect.

ESD (p4 §5.2):
  HBM (ANSI/ESDA/JEDEC JS-001) : ±2000 V (all pins)
  CDM (JESD22-C101)            : ±1000 V (all pins)

Recommended Operating Conditions (p4 §5.3):
  V_CC supply voltage : 2.7 V to 5 V
  T_A range          : -40 to +125 °C (industrial)

Key features (p1 of datasheet, not transcribed here):
  - Wide supply: 2.7 V to 5 V
  - Low supply current
  - Common-mode input voltage range includes ground
  - Output sink: see datasheet for I_OL specs
  - Open-drain output (requires external pull-up)
  - Low offset voltage

Pin layout (SOT-23-5, DBV package, datasheet p3 §4 + pinmap.txt):
  Pin 1 : 1INP  (in+ for channel 1)
  Pin 2 : GND
  Pin 3 : 1INM  (in- for channel 1)
  Pin 4 : OUT   (open-drain output)
  Pin 5 : VCCP  (positive supply)

Application caveats:
  - Output is open-drain → REQUIRES an external pull-up to operate as
    a digital comparator. Typical 10-100 kΩ to V_CC.
  - Differential input voltage rating ±5.5 V — protect with input
    clamps if larger swings are possible.
  - Short-circuit protection: output to GND is safe but output to
    V_CC can overheat the part (datasheet §5.1 note 4).

Mechanical (NOT stated in datasheet): body_material, lead_material,
weight_g, density_g_cm3, cte_ppm_k, fab_country.

Distributor (from SamacSys metadata, to verify):
  TI product page: www.ti.com/product/LMV331
"""


def _lmv331_sot23_5_footprint() -> Footprint:
    """SOT-23-5 footprint per SamacSys SOT95P280X145-5N.kicad_mod.

    Same physical footprint as LMR10510XMFE/NOPB (also TI DBV
    package), but ownership is inline — this is a separate instance
    so the 3D model path can point to the LMV331 STEP.
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
        size_mm=(2.90, 1.60),
        height_mm=1.45,
        model_3d_path="application/src/smash/parts/sources/LMV331IDBVR/LMV331IDBVR.stp",
        source="samacsys",
    )


def add_lmv331idbvr(design, ref: str, **overrides) -> Chip:
    """TI LMV331IDBVR — single open-drain comparator, V_CC=2.7..5 V,
    rail-to-rail input including ground, SOT-23-5 (DBV).

    Application note: output is open-drain — schematic must add a
    pull-up to the desired output rail.
    """
    fields = dict(
        manf="Texas Instruments",
        manf_pn="LMV331IDBVR",
        canonical_id="lmv331idbvr",
        name="LMV331IDBVR",
        value="LMV331IDBVR",
        description=(
            "Single comparator, open-drain output, V_CC=2.7..5 V, "
            "rail-to-rail input incl. ground, SOT-23-5 (DBV)"
        ),
        datasheet="application/src/smash/parts/sources/LMV331IDBVR/LMV331-LMV393-LMV339-family.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "ESD HBM ±2000 V (ANSI/ESDA/JEDEC JS-001)",
            "ESD CDM ±1000 V (JESD22-C101)",
        ],
        eccn=None, itar=None,
        package="SOT-23-5",
        size_mm=(2.90, 1.60),
        height_mm=1.45,
        temp_range_c=(-40, 125),    # T_A recommended operating
        body_material=None, lead_material=None,
        voltage_rating_v=5.5,       # V_CC abs max
        vcc_nominal_v=None,         # caller decides (3.3 or 5 V typical)
        i_rms_a=None,
        power_rating_w=None,
        rth_jc_cw=None,
        rth_ja_cw=None,             # datasheet has thermal table but not summarised here
        tj_max_c=150.0,
        pins=[
            # Per pinmap.txt + datasheet p3 §4
            Pin(num="1", name="1INP", aliases=["IN+", "INP"], type="input"),
            Pin(num="2", name="GND",                          type="ground"),
            Pin(num="3", name="1INM", aliases=["IN-", "INM"], type="input"),
            Pin(num="4", name="OUT",                          type="output",
                note="open-drain — requires external pull-up"),
            Pin(num="5", name="VCCP", aliases=["VCC", "V+"],  type="power"),
        ],
        footprint=_lmv331_sot23_5_footprint(),
        note=_LMV331_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments TLV3691IDPFR — nanopower single comparator, push-pull
# output, rail-to-rail input, V_CC 0.9–6.5 V, I_Q ~150 nA, X2SON-6 (DPF)
# ═════════════════════════════════════════════════════════════════════════

def _tlv3691_x2son6_footprint() -> Footprint:
    """X2SON-6 (DPF0006A) footprint per SamacSys TLV3691IDPFR.kicad_mod.
    Six 0.35×0.17 mm pads in two columns at ±0.525 X, rows at −0.35/0/+0.35 Y
    (0.35 mm row pitch). Ultra-small (~1.0×1.0 mm body, pads to ±0.70 X). The
    SamacSys courtyard (3.4×3.0 mm) was far larger than the part needs and bloated
    the spacer clearance cavity, so it's tightened to 1.9×1.5 mm (±0.25 mm past the
    pads/body, safe in either 0°/90° placement) — still clears the chip cleanly."""
    return Footprint(
        name="DPF0006A",
        package_class="X2SON-6",
        pads=[
            Pad(num="1", position_mm=(-0.525, -0.35), size_mm=(0.35, 0.17), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-0.525,  0.0),  size_mm=(0.35, 0.17), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-0.525, +0.35), size_mm=(0.35, 0.17), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(+0.525, +0.35), size_mm=(0.35, 0.17), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(+0.525,  0.0),  size_mm=(0.35, 0.17), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=(+0.525, -0.35), size_mm=(0.35, 0.17), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)],
        courtyard=[(-0.95, -0.75), (0.95, -0.75), (0.95, 0.75), (-0.95, 0.75)],
        pitch_mm=0.35,
        size_mm=(1.0, 1.0),
        height_mm=0.40,
        model_3d_path="application/src/smash/parts/sources/TLV3691IDPFR/TLV3691IDPFR.stp",
        source="samacsys",
    )


def add_tlv3691idpfr(design, ref: str, **overrides) -> Chip:
    """TI TLV3691IDPFR — nanopower single comparator, push-pull output,
    rail-to-rail input, V_CC 0.9–6.5 V, I_Q ~0.15 µA, X2SON-6 (DPF).

    Swapped in for the LMV331 on the piezo launch-detect: the LMV331's
    ~80 µA on the always-on 3V3 was a continuous shelf load, while the
    TLV3691's ~150 nA I_Q is shelf-negligible (so the comparator can stay
    always-on without re-railing). Output is **push-pull** — NO external
    pull-up (unlike the open-drain LMV331); it drives COMP_OUT to the M33
    EXTI directly. Pin 5 is NC; V+ is on pin 6 (not pin 5 as on the LMV331).
    """
    fields = dict(
        manf="Texas Instruments",
        manf_pn="TLV3691IDPFR",
        canonical_id="tlv3691idpfr",
        name="TLV3691IDPFR",
        value="TLV3691IDPFR",
        description=(
            "Nanopower single comparator, push-pull output, V_CC=0.9..6.5 V, "
            "I_Q 75 nA typ / 150 nA max, rail-to-rail input (+100 mV beyond rails), X2SON-6 (DPF)"
        ),
        datasheet="Research/tlv3691.pdf",   # TI SBOS694A
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "ESD HBM ±2000 V (ANSI/ESDA/JEDEC JS-001)",
            "ESD CDM ±1000 V (JESD22-C101)",
        ],
        eccn=None, itar=None,
        package="X2SON-6",
        size_mm=(1.0, 1.0),
        height_mm=0.40,
        temp_range_c=(-40, 125),
        body_material=None, lead_material=None,
        voltage_rating_v=6.5,       # V_CC abs max
        vcc_nominal_v=None,
        i_rms_a=None,
        power_rating_w=None,
        rth_jc_cw=None, rth_ja_cw=None,
        tj_max_c=150.0,
        pins=[
            Pin(num="1", name="IN+", aliases=["INP"], type="input"),
            Pin(num="2", name="GND",                  type="ground"),
            Pin(num="3", name="IN-", aliases=["INM"], type="input"),
            Pin(num="4", name="OUT",                  type="output",
                note="push-pull — no external pull-up needed"),
            Pin(num="5", name="NC",                   type="passive",
                note="no internal connection"),
            Pin(num="6", name="VCC", aliases=["V+"],  type="power"),
        ],
        footprint=_tlv3691_x2son6_footprint(),
        note=(
            "TI TLV3691 nanopower comparator (SBOS694A, rev Nov 2015). Push-pull "
            "output, V_CC 0.9–6.5 V (±0.45 to ±3.25 V), I_Q 75 nA typ / 150 nA "
            "max, rail-to-rail input extending 100 mV beyond both rails, V_OS "
            "±3 mV, response time 24 µs. X2SON-6 (DPF0006A, 1.0×1.0 mm); also in "
            "SC70-5 (DBV). Pin 5 = NC; V+ on pin 6. Replaces the LMV331 on the "
            "launch-detect to take its ~80 µA off the always-on 3V3 shelf rail — "
            "the 24 µs response is ample for the ms-scale setback event."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
