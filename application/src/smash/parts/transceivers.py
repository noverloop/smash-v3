"""Bus transceivers (CAN, RS-485, LVDS, etc.).

Every value transcribed from per-part ground-truth in
`parts/sources/<PN>/`.
"""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments TCAN1042GVDQ1 — automotive fault-protected CAN-FD
# transceiver, ISO 11898-2:2016, 5 Mbps (G suffix), I/O level shifting
# (V suffix), AEC-Q100 grade 1, SOIC-8 (D package)
# ═════════════════════════════════════════════════════════════════════════

_TCAN1042GVDQ1_NOTE = """\
Datasheet extras (TI TCAN1042-Q1 family, SLLSES9D, rev Oct 2021).
This factory covers the **TCAN1042GVDQ1** orderable:
  G  : "Turbo" CAN — supports 5 Mbps CAN-FD (vs 2 Mbps on non-G)
  V  : I/O level shifting via dedicated VIO pin (pin 5)
  D  : SOIC-8 package (DQ1 = automotive tape & reel)
  Q1 : AEC-Q100 grade 1 qualified

Family covered by the same datasheet (variants in p1 title):
  TCAN1042-Q1    : 2 Mbps,  non-V (no VIO),     non-H (±58 V bus)
  TCAN1042V-Q1   : 2 Mbps,  V (VIO level shift), non-H (±58 V)
  TCAN1042H-Q1   : 2 Mbps,  non-V,              H (±70 V bus)
  TCAN1042HV-Q1  : 2 Mbps,  V,                  H (±70 V)
  TCAN1042G-Q1   : 5 Mbps,  non-V,              non-H (±58 V)
  TCAN1042GV-Q1  : 5 Mbps,  V,                  non-H (±58 V)  <-- this
  TCAN1042HG-Q1  : 5 Mbps,  non-V,              H (±70 V)
  TCAN1042HGV-Q1 : 5 Mbps,  V,                  H (±70 V)

Standards (datasheet p1):
  ISO 11898-2:2016 high-speed CAN physical layer
  ISO 11898-5:2007 (low-power mode)
  IEC 62228-3 (EMC up to 500 kbps without common-mode choke)
  AEC-Q100 grade 1 (automotive)
  Functional Safety-Capable (documentation available)

Absolute Max Ratings (p6 §7.1):
  V_CC              : -0.3 to +7 V
  V_IO (V suffix)   : -0.3 to +7 V
  V_BUS (CANH/CANL) : -58 to +58 V (non-H variants)  <-- this part
  V_Diff (CANH-CANL): -58 to +58 V (non-H)
  V_Logic_Input  (TXD, STB) : -0.3 V to 7 V, ≤ V_IO + 0.3 V
  V_Logic_Output (RXD)      : -0.3 V to 7 V, ≤ V_IO + 0.3 V
  I_O(RXD)          : -8 to +8 mA
  T_J operating     : -55 to +150 °C
  T_STG             : -65 to +150 °C

ESD (p6 §7.2):
  HBM Class 3A (all pins)            : ±6 kV
  HBM Class 3B (CANH, CANL to GND)   : ±16 kV   (IEC ESD survival)
  CDM Class C6 (all pins, AEC Q100-011): ±1.5 kV
  Machine Model (JEDEC JESD22 A115)  : ±200 V

Pin map (datasheet pin diagram + pinmap.txt, SOIC-8):
  1 = TXD     (transmit data input from MCU)
  2 = GND
  3 = VCC     (5 V supply, can be 3.3 V on non-V variants — see DS)
  4 = RXD     (receive data output to MCU)
  5 = VIO     (I/O level-shifting supply; "V" suffix specific —
               NC on non-V variants)
  6 = CANL    (CAN bus low)
  7 = CANH    (CAN bus high)
  8 = STB     (standby mode select; HIGH=standby, LOW=normal)

Protection features (datasheet p1):
  - Bus fault protection: ±58 V (non-H), ±70 V (H variants)
  - IEC ESD protection up to ±15 kV
  - Undervoltage protection on V_CC and V_IO
  - Driver dominant time-out (TXD DTO) — data rates down to 10 kbps
  - Thermal shutdown (TSD)
  - Ideal passive behavior when unpowered (high-Z bus + RXD)
  - Receiver common-mode input voltage: ±30 V

Loop delay: 110 ns typ.

Application caveats:
  - CAN bus is differential — CANH/CANL must be routed as a 120 Ω
    differential pair, terminated 120 Ω at both ends of the bus.
  - VIO=NC on non-V variants; this part REQUIRES VIO connected to
    the I/O rail (typ 3.3 V or 5 V).
  - STB pin must NOT be floated — tie to MCU GPIO or GND.

Mechanical (NOT in datasheet): body_material, lead_material,
weight_g, density_g_cm3, cte_ppm_k, fab_country.

Distributor (from SamacSys metadata): see Mouser/TI listings.
"""


def _tcan1042_soic8_footprint() -> Footprint:
    """SOIC-8 (TI D package) footprint per SamacSys
    SOIC127P600X175-8N.kicad_mod. Body 4.9 × 3.91 mm nominal,
    height 1.75 mm max, 1.27 mm pitch.
    """
    return Footprint(
        name="SOIC127P600X175-8N",
        package_class="SOIC-8",
        pads=[
            Pad(num="1", position_mm=(-2.711, 1.905), size_mm=(1.528, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-2.711, 0.635), size_mm=(1.528, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-2.711, -0.635), size_mm=(1.528, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(-2.711, -1.905), size_mm=(1.528, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(2.711, -1.905), size_mm=(1.528, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=(2.711, -0.635), size_mm=(1.528, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="7", position_mm=(2.711, 0.635), size_mm=(1.528, 0.65), shape="rect", layer="F.Cu"),
            Pad(num="8", position_mm=(2.711, 1.905), size_mm=(1.528, 0.65), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-1.948, -2.452), (1.948, -2.452),
                      (1.948, 2.452), (-1.948, 2.452)],
        courtyard=[(-3.725, -2.75), (3.725, -2.75),
                   (3.725, 2.75), (-3.725, 2.75)],
        pitch_mm=1.27,
        size_mm=(4.90, 3.91),     # TI D package nominal
        height_mm=1.75,
        model_3d_path="application/src/smash/parts/sources/TCAN1042GVDQ1/TCAN1042GVDQ1.stp",
        source="samacsys",
    )


def add_tcan1042gvdq1(design, ref: str, **overrides) -> Chip:
    """TI TCAN1042GVDQ1 — automotive fault-protected CAN-FD
    transceiver, 5 Mbps, I/O level shifting via VIO pin, ±58 V bus
    fault protection, AEC-Q100 grade 1, SOIC-8.
    """
    fields = dict(
        manf="Texas Instruments",
        manf_pn="TCAN1042GVDQ1",
        canonical_id="tcan1042gvdq1",
        name="TCAN1042GVDQ1",
        value="TCAN1042GVDQ1",
        description=(
            "Automotive CAN-FD transceiver, ISO 11898-2:2016, "
            "5 Mbps (G), VIO level shifting (V), ±58 V bus fault "
            "protection, AEC-Q100 grade 1, SOIC-8"
        ),
        datasheet="application/src/smash/parts/sources/TCAN1042GVDQ1/TCAN1042-family.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "ISO 11898-2:2016",
            "ISO 11898-5:2007",
            "IEC 62228-3 (EMC up to 500 kbps)",
            "AEC-Q100 Grade 1",
            "Functional Safety-Capable",
            "ESD HBM Class 3A ±6 kV (all pins)",
            "ESD HBM Class 3B ±16 kV (CANH/CANL to GND)",
            "ESD CDM Class C6 ±1.5 kV",
            "ESD Machine Model ±200 V",
        ],
        eccn=None, itar=None,
        package="SOIC-8 (TI D)",
        size_mm=(4.90, 3.91),
        height_mm=1.75,
        temp_range_c=(-55, 150),    # T_J operating range
        body_material=None, lead_material=None,
        voltage_rating_v=7.0,        # V_CC / V_IO abs max
        vcc_nominal_v=5.0,           # typ; also supports 3.3 V
        i_rms_a=None,                # see datasheet electrical chars
        power_rating_w=None,
        # ── thermal (TI TCAN1042-Q1 SLLSES9D Oct 2021, §7.5+7.6) ─────
        # NB: components.md TCAN1042GVD row used RθJC = 37.6 (the DRB
        # VSON value); the D (SOIC-8) package value from the same DS
        # is 48.3 °C/W. Active dissipation: ICC normal mode dominant
        # typ 40 mA × Vcc=5V × ~50% duty cycle (half dominant, half
        # recessive) → ~0.10 W typ; peak with bus fault 110 mA × 5V
        # = 0.55 W. We bound p_max at 0.40 W (dominant 80 mA × 5V,
        # high bus load) since the 110 mA fault case is transient.
        p_active_w=0.10,                    # 50% duty (40 mA dom + 1.5 mA rec)/2 × 5V (DS §7.6 p9)
        p_max_w=0.40,                       # 80 mA dom × 5V high bus load typ (DS §7.6 p9)
        rth_jc_cw=48.3,                     # D (SOIC-8) RθJC(top), DS §7.5 p8
        tj_max_c=150.0,                     # max op'l Tj, DS §6.x p7
        pins=[
            # Per pinmap.txt + datasheet pin diagram
            Pin(num="1", name="TXD",  type="input",
                note="from MCU controller; driver dominant time-out protected"),
            Pin(num="2", name="GND",  type="ground"),
            Pin(num="3", name="VCC",  type="power",
                note="5 V (or 3.3 V on non-V variants; see datasheet)"),
            Pin(num="4", name="RXD",  type="output",
                note="to MCU controller; level matches VIO on this V-suffix part"),
            Pin(num="5", name="VIO",  type="power",
                note="I/O level-shifting supply (V-suffix specific). "
                     "Connect to MCU I/O rail (typ 3.3 V or 5 V). "
                     "NC on non-V variants."),
            Pin(num="6", name="CANL", type="io",
                note="differential pair with CANH"),
            Pin(num="7", name="CANH", type="io",
                note="differential pair with CANL"),
            Pin(num="8", name="STB",  type="input",
                note="standby select: HIGH=standby, LOW=normal. Must not float."),
        ],
        footprint=_tcan1042_soic8_footprint(),
        note=_TCAN1042GVDQ1_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
