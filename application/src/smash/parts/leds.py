"""LED factories. Values transcribed verbatim from per-part ground-truth
artifacts in `parts/sources/<PN>/`."""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint
from smash.parts._chip_mass import WEIGHT_G_LED_0603


# ═════════════════════════════════════════════════════════════════════════
# Lite-On Technology LTST-C190GKT — 0603 chip LED, green (565 nm peak,
# 569 nm dominant)
#
# Ground-truth artifacts (parts/sources/LTST-C190GKT/):
#   - LTST-C190GKT.pdf          : Lite-On datasheet BNS-OD-C131/A4
#   - LIB_LTST-C190GKT.samacsys.zip : SamacSys ECAD archive (ID 12842258)
#   - LTST-C190GKT.kicad_sym    : KiCad symbol (extracted)
#   - LEDC1608X90N.kicad_mod    : KiCad footprint (extracted)
#   - LTST-C190GKT.stp          : STEP 3D model
#   - pinmap.txt                : K=1, A=2
# ═════════════════════════════════════════════════════════════════════════

_LTST_C190GKT_NOTE = """\
Datasheet extras (Lite-On LTST-C190GKT, BNS-OD-C131/A4) — fields not
yet promoted to schema. All values transcribed verbatim.

Identity:
  Lens   : Water Clear
  Die    : GaP on GaP, Green
  Source color : Green
  Tape   : 8 mm, 7-inch reel, 3000 pcs/reel

Absolute Max Ratings (datasheet p2):
  Power dissipation       : 100 mW
  Peak forward current    : 120 mA  (1/10 duty, 0.1 ms pulse width)
  DC forward current      : 30 mA   (stored in i_rms_a)
  Linear derating from 50 °C : 0.6 mA/°C
  Reverse voltage         : 5 V
  Operating temperature   : -55 to +85 °C
  Storage temperature     : -55 to +85 °C
  Wave soldering          : 260 °C for 5 s
  IR soldering            : 260 °C for 5 s
  Vapor-phase soldering   : 215 °C for 3 min

Electrical / Optical (datasheet p4, T_A=25 °C):
  Luminous intensity Iv : 1.8 min / 6.0 typ mcd @ I_F=10 mA
  Viewing angle 2θ½     : 130 deg typ
  Peak wavelength λ_P   : 565 nm
  Dominant wavelength λ_d : 569 nm
  Spectral half-width Δλ : 30 nm
  Forward voltage V_F   : 2.1 typ / 2.6 max V @ I_F=20 mA
  Reverse current I_R   : 10 µA max @ V_R=5 V
  Capacitance C         : 35 pF @ V_F=0, f=1 MHz

Intensity bin codes (datasheet p5):
  G : 1.80 – 2.80 mcd
  H : 2.80 – 4.50 mcd
  J : 4.50 – 7.10 mcd
  K : 7.10 – 11.2 mcd
  L : 11.2 – 18.0 mcd
  (Tolerance ±15 % per bin)

Reliability (datasheet p10):
  Tested per MIL-STD-750D, MIL-STD-883D, MIL-STD-202F, JIS C 7021,
  J-STD-020 (IR-reflow profile). Operation life: 1000 h @ 20 mA.

Application caveat (datasheet p9):
  "The LEDs described here are intended to be used for ordinary
   electronic equipment. Consult Lite-On's sales in advance for
   applications in which exceptional reliability is required,
   particularly when the failure or malfunction may directly
   jeopardize life or health (aviation, transportation, traffic
   control, medical and life support, safety devices)."
  >>> Munition-zone use needs explicit qualification from Lite-On.

Mechanical (NOT in datasheet):
  body_material : LED encapsulant, typically epoxy resin (not stated)
  lead_material : NOT STATED
  weight_g      : NOT STATED
  fab_country   : NOT IN DATASHEET — needs Mouser/Lite-On traceability

Distributor links (from SamacSys metadata):
  Datasheet URL : https://media.digikey.com/pdf/Data%20Sheets/\
Lite-On%20PDFs/LTST-C190GKT.pdf
  Mouser PN     : 859-LTST-C190GKT
  Mouser URL    : https://www.mouser.co.uk/ProductDetail/LITEON/\
LTST-C190GKT?qs=drxkyCeiWgbQzclgbojDOg%3D%3D
  Arrow PN      : LTST-C190GKT
  Pricing       : NOT captured — live distributor quote required
"""


def _ltst_c190gkt_footprint() -> Footprint:
    """0603 (1608 metric) chip LED footprint per the SamacSys-generated
    `LEDC1608X90N.kicad_mod`.

    Pads (cathode=1 on the left, anode=2 on the right, matching the
    chamfered F.Fab corner at -X,-Y indicating pin 1):
      pad 1 (K) : (-0.75, 0) mm, 0.9 × 0.95 mm rect
      pad 2 (A) : (+0.75, 0) mm, 0.9 × 0.95 mm rect
    Body 1.60 × 0.80 × 0.90 mm; courtyard ±1.65 × ±0.925 mm.
    """
    return Footprint(
        name="LEDC1608X90N",
        package_class="LED-0603",
        pads=[
            Pad(num="1", position_mm=(-0.75, 0.0),
                size_mm=(0.9, 0.95), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(+0.75, 0.0),
                size_mm=(0.9, 0.95), shape="rect", layer="F.Cu"),
        ],
        body_outline=[
            (-0.8, -0.4), (+0.8, -0.4),
            (+0.8, +0.4), (-0.8, +0.4),
        ],
        courtyard=[
            (-1.65, -0.925), (+1.65, -0.925),
            (+1.65, +0.925), (-1.65, +0.925),
        ],
        pitch_mm=None,                # 2-pin LED, no array pitch
        size_mm=(1.6, 0.8),           # nominal body 1.6 × 0.8 mm (0603)
        height_mm=0.9,                # per KiCad sym Height property
        model_3d_path="application/src/smash/parts/sources/LTST-C190GKT/LTST-C190GKT.stp",
        source="samacsys",
        note=(
            "SamacSys 0603 chip-LED footprint. Pin 1 = cathode "
            "(silkscreen chamfer at -X,-Y corner of F.Fab marks it). "
            "Chip-LED naming: LEDC1608X90N = LED-Chip, 1608 metric "
            "size, 0.90 mm height."
        ),
    )


def add_ltst_c190gkt(design, ref: str, **overrides) -> Chip:
    """Lite-On LTST-C190GKT — Green chip LED in 0603 (1608 metric),
    565 nm peak / 569 nm dominant wavelength, V_F=2.1 V typ @ 20 mA,
    I_F_DC=30 mA absolute max.

    Ground-truth in `parts/sources/LTST-C190GKT/`.
    """
    fields = dict(
        manf="Lite-On Technology",
        manf_pn="LTST-C190GKT",
        canonical_id="ltst_c190gkt",
        name="LTST-C190GKT",
        value="LTST-C190GKT",
        description=(
            "Green LED, 565 nm peak / 569 nm dominant, V_F=2.1 V typ "
            "@ 20 mA, I_F_DC=30 mA max, 0603 (1608 metric)"
        ),
        datasheet="application/src/smash/parts/sources/LTST-C190GKT/LTST-C190GKT.pdf",
        fab_country=None,
        currency=None,
        price_1pc=None,
        price_20kpc=None,
        weight_g=WEIGHT_G_LED_0603,   # 0603 chip-LED, vendor-pool estimate
        standards=[
            "RoHS",
            # Lite-On's reliability matrix references these MIL/JIS/JEDEC
            # documents (datasheet p10 reliability test table)
            "MIL-STD-750D",
            "MIL-STD-883D",
            "MIL-STD-202F",
            "JIS C 7021",
            "J-STD-020 (IR-reflow profile)",
        ],
        eccn=None,
        itar=None,
        package="0603 (1608 metric)",
        size_mm=(1.6, 0.8),
        height_mm=0.9,
        # Datasheet p2: operating range -55 to +85 °C
        temp_range_c=(-55, 85),
        body_material=None,
        lead_material=None,
        # LED electrical fields
        voltage_rating_v=5.0,         # reverse voltage limit
        # vcc_nominal_v is meaningless for an LED — leave None
        i_rms_a=0.030,                # DC forward current max = 30 mA
        power_rating_w=0.100,         # 100 mW dissipation max
        p_max_w=0.100,
        rth_jc_cw=None,
        rth_ja_cw=None,               # NOT stated for this LED
        tj_max_c=None,                # storage max is 85 °C; junction
                                      # max not stated separately
        # Pins per pinmap.txt + KiCad sym
        pins=[
            Pin(num="1", name="K", aliases=["Cathode"], type="io"),
            Pin(num="2", name="A", aliases=["Anode"],   type="io"),
        ],
        footprint=_ltst_c190gkt_footprint(),
        note=_LTST_C190GKT_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Lite-On LTST-C190KRKT — RED chip LED, 0603. Paired with the LTST-C190GKT
# green as the nose status indicator: both V_F ~2 V, so a single low rail drives
# the pair (green=Ready, red=batt<1h, amber=both, off=dormant) with the M33
# sinking each cathode — no level-shift, unlike the SK6812MINI it replaces (whose
# 5 V VDD needed a 3.5 V WS2812 DIN, out of spec for a 3.3 V GPIO). Shares the
# LEDC1608X90N 0603 package + 3D with the green.
#
# >>> PROVISIONAL: exact red orderable + V_F/λ not confirmed (no red datasheet
#     fetched). Footprint + 3D are the VERIFIED shared package.
# ═════════════════════════════════════════════════════════════════════════


def add_ltst_c190krkt(design, ref: str, **overrides) -> Chip:
    """Lite-On LTST-C190KRKT — RED chip LED, 0603 (1608 metric), V_F ~2.0 V typ
    @ 20 mA. Shares the LEDC1608X90N package + 3D with the LTST-C190GKT green;
    the two form the nose status-indicator pair — both ~2 V, common-anode, the
    M33 sinks each cathode through a current-limit resistor.

    >>> PROVISIONAL: exact red C190 orderable + its V_F/λ not yet confirmed (no
        red datasheet fetched). Footprint + 3D are the VERIFIED shared 0603
        package (from LTST-C190GKT). Values below are standard red-0603 typicals.
    """
    fields = dict(
        manf="Lite-On Technology",
        manf_pn="LTST-C190KRKT",
        canonical_id="ltst_c190krkt",
        name="LTST-C190KRKT",
        value="LTST-C190KRKT",
        description=(
            "Red LED, ~625 nm, V_F ~2.0 V typ @ 20 mA, I_F_DC=30 mA max, "
            "0603 (1608 metric) — shares package with LTST-C190GKT"
        ),
        datasheet=None,                 # red datasheet not fetched; pkg shared w/ C190GKT
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=WEIGHT_G_LED_0603,
        standards=["RoHS"],
        eccn=None, itar=None,
        package="0603 (1608 metric)",
        size_mm=(1.6, 0.8),
        height_mm=0.9,
        temp_range_c=(-40, 85),         # typical red 0603; confirm w/ datasheet
        body_material=None, lead_material=None,
        voltage_rating_v=5.0,           # typical red 0603 reverse limit; confirm
        i_rms_a=0.030,                  # typical red 0603 DC I_F max; confirm
        power_rating_w=0.100, p_max_w=0.100,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=None,
        pins=[
            Pin(num="1", name="K", aliases=["Cathode"], type="io"),
            Pin(num="2", name="A", aliases=["Anode"],   type="io"),
        ],
        footprint=_ltst_c190gkt_footprint(),   # shared LEDC1608X90N 0603 package
        note=(
            "Lite-On LTST-C190KRKT RED 0603 chip LED — nose status-indicator "
            "pair with the LTST-C190GKT green; replaces the SK6812MINI (whose "
            "5 V VDD vs 3.3 V WS2812 DIN threshold was out of spec).\n\n"
            ">>> PROVISIONAL red part: exact orderable + V_F/λ not confirmed (no "
            "red datasheet fetched). Footprint + 3D are the VERIFIED shared 0603 "
            "package from LTST-C190GKT. Confirm the orderable + fetch the red "
            "datasheet to promote verbatim."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# Opsco SK6812MINI-012 — addressable RGB LED, WS2812 single-line protocol, so
# ONE serial data line (DIN) drives R+G+B to any colour. Verified against
# parts/sources / Research/SK6812MINI-012.pdf (Opsco rev B/0, 2024-04-23).
#   Pinout (datasheet p4): 1 DIN, 2 VDD, 3 DOUT, 4 GND.
#   Package 3.7 x 3.5 x 1.1 mm; VDD 3.7-5.5 V; 5 V @ 12 mA/colour; 800 kbps.
# ═════════════════════════════════════════════════════════════════════════

def _sk6812mini_footprint() -> Footprint:
    """SK6812MINI-012 — 3.7 x 3.5 mm, 4 corner pads per the datasheet's
    recommended land pattern (p5, top view): 3 DOUT (top-left), 2 VDD
    (top-right), 4 GND (bottom-left), 1 DIN (bottom-right)."""
    P = lambda n, x, y: Pad(num=n, position_mm=(x, y), size_mm=(1.4, 1.0),
                            shape="rect", layer="F.Cu")
    return Footprint(
        name="LED_SK6812MINI_3.7x3.5",
        pads=[P("1", 1.0, -0.85), P("2", 1.0, 0.85),
              P("3", -1.0, 0.85), P("4", -1.0, -0.85)],
    )


def add_sk6812mini(design, ref: str, **overrides) -> Chip:
    """Opsco SK6812MINI-012 — addressable RGB LED (WS2812 protocol), single-wire
    DIN full-colour, integrated controller, VDD 3.7-5.5 V, 5 V @ 12 mA/colour."""
    fields = dict(
        manf="Dongguan Opsco Optoelectronics", manf_pn="SK6812MINI-012",
        canonical_id="sk6812mini_012", name="SK6812MINI-012",
        value="SK6812MINI-012",
        description=("Addressable RGB LED (WS2812 protocol), single-wire DIN, "
                     "integrated controller, VDD 3.7-5.5 V, 5 V @ 12 mA/colour, "
                     "800 kbps, 3.7x3.5x1.1 mm"),
        datasheet="Research/SK6812MINI-012.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None,
        weight_g=WEIGHT_G_LED_0603, standards=["RoHS", "REACH", "ESD HBM 2 kV"],
        eccn=None, itar=None,
        package="SK6812MINI (3.7x3.5x1.1)", size_mm=(3.7, 3.5), height_mm=1.1,
        temp_range_c=(-40, 85), body_material=None, lead_material=None,
        voltage_rating_v=5.5, i_rms_a=0.060, power_rating_w=0.3, p_max_w=0.3,
        rth_jc_cw=None, rth_ja_cw=None, tj_max_c=None,
        pins=[
            Pin(num="1", name="DIN",  type="input"),
            Pin(num="2", name="VDD",  type="power"),
            Pin(num="3", name="DOUT", type="output"),
            Pin(num="4", name="GND",  type="ground"),
        ],
        footprint=_sk6812mini_footprint(),
        note="SK6812MINI-012 verified vs Research/SK6812MINI-012.pdf (Opsco rev "
             "B/0). NB: at 5 V VDD the WS2812 DIN threshold is ~0.7xVDD=3.5 V, so "
             "a 3.3 V GPIO is marginal — level-shift DIN or run VDD ~4 V if needed.",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
