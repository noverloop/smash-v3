"""Memory IC factories — EEPROMs, NOR flash, NAND flash, DRAM, NFC.

Every value transcribed from per-part ground-truth in
`parts/sources/<PN>/`.
"""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint


# ═════════════════════════════════════════════════════════════════════════
# STMicroelectronics M24C01-RMN6TP — 1-Kbit I²C EEPROM, SO8N (MN)
# ═════════════════════════════════════════════════════════════════════════

_M24C01_NOTE = """\
Datasheet extras (ST M24C01/02-W M24C01/02-R M24C02-F, DS9398 Rev 8,
Jul 2023). Family doc covering both 1-Kbit and 2-Kbit variants with
different voltage ranges.

Order code decode (M24C01-RMN6TP):
  M24C01 : 1-Kbit (128 byte) I²C EEPROM, page size 16 byte
  R      : 1.8 to 5.5 V supply range  (vs W: 2.5..5.5 V, F: 1.7..5.5 V)
  MN     : SO8N package (8-Lead SOIC narrow, 150 mil body width)
  6      : ST product designator
  TP     : Tape and reel, Pb-free (ECOPACK2)

Features (datasheet p1):
  I²C interface : 100 kHz (standard) and 400 kHz (fast mode)
  Memory : 1024 bits = 128 bytes, page size 16 bytes
  Supply (R variant): 1.8 V to 5.5 V
  Operating T : -40 to +85 °C (industrial)
  Write cycle (byte + page): 5 ms max
  Endurance : > 4 million write cycles
  Retention : > 200 years
  Hardware write protection (WC# pin) on the whole memory array
  Enhanced ESD/latch-up protection

Pin layout (datasheet p1 + pinmap.txt, SO8N):
  1 = E0   (I²C address bit 0)
  2 = E1   (I²C address bit 1)
  3 = E2   (I²C address bit 2 — tie per device address)
  4 = VSS  (ground)
  5 = SDA  (I²C data)
  6 = SCL  (I²C clock)
  7 = WC#  (write control, active low — tie LOW to enable writes)
           SamacSys pinmap encodes with bar-notation `W\\C\\`
  8 = VCC  (supply)

I²C address: 1010 A2 A1 A0 (7-bit) = 0xA0 base, with A2/A1/A0 set by
E2/E1/E0 strapping. Default 0x50 if all E pins are at VSS.

Compliance (datasheet p1 Packages section):
  SO8N (ECOPACK2)        — this factory's package
  RoHS-compliant, Halogen-free

Mechanical (NOT in datasheet headline): body_material, lead_material,
weight_g, fab_country.

Distributor: see Mouser/ST listings.
"""


def _m24c01_so8n_footprint() -> Footprint:
    """SO8N (8-Lead SOIC narrow, 150 mil) footprint per SamacSys
    SOIC127P600X175-8N.kicad_mod. SAME footprint as TCAN1042 — both
    are TI/ST SO8N. Each chip carries its own Footprint instance with
    its own 3D model path.
    """
    return Footprint(
        name="SOIC127P600X175-8N",
        package_class="SO8N (SOIC-8)",
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
        size_mm=(4.90, 3.91),
        height_mm=1.75,
        model_3d_path="application/src/smash/parts/sources/M24C01-RMN6TP/M24C01-RMN6TP.stp",
        source="samacsys",
    )


def add_m24c01_rmn6tp(design, ref: str, **overrides) -> Chip:
    """ST M24C01-RMN6TP — 1-Kbit (128-byte) I²C EEPROM, 1.8-5.5 V
    supply, SO8N package. Default I²C base address 0xA0; E0/E1/E2
    pins select address LSBs."""
    fields = dict(
        manf="STMicroelectronics",
        manf_pn="M24C01-RMN6TP",
        canonical_id="m24c01_rmn6tp",
        name="M24C01-RMN6TP",
        value="M24C01-RMN6TP",
        description=(
            "I²C EEPROM, 1 Kbit (128 byte), 16-byte page, 100/400 kHz, "
            "V_CC=1.8..5.5 V, SO8N"
        ),
        datasheet="application/src/smash/parts/sources/M24C01-RMN6TP/M24C01-family.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=["RoHS", "Halogen-Free", "ECOPACK2"],
        eccn=None, itar=None,
        package="SO8N (SOIC-8 narrow)",
        size_mm=(4.90, 3.91),
        height_mm=1.75,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=None,       # not stated as a fixed abs max here
        vcc_nominal_v=3.3,           # within R variant 1.8-5.5 V range
        i_rms_a=None,
        power_rating_w=None,
        memory_capacity_bits=1024,   # 1 Kbit
        rth_jc_cw=None, rth_ja_cw=None,
        tj_max_c=None,
        pins=[
            Pin(num="1", name="E0",  type="input",
                note="I²C device-address bit 0 strap (tie GND or VCC)"),
            Pin(num="2", name="E1",  type="input",
                note="I²C device-address bit 1 strap (tie GND or VCC)"),
            Pin(num="3", name="E2",  type="input",
                note="I²C device-address bit 2 strap (tie GND or VCC)"),
            Pin(num="4", name="VSS", aliases=["GND"], type="ground"),
            Pin(num="5", name="SDA", type="io"),
            Pin(num="6", name="SCL", type="io"),
            # Datasheet pin name is /WC; SamacSys encodes with KiCad
            # bar-notation 'W\\C\\'
            Pin(num="7", name="W\\C\\", aliases=["WC", "/WC", "WC#"],
                type="input",
                note="write control, active-low — tie LOW to enable writes"),
            Pin(num="8", name="VCC", type="power"),
        ],
        footprint=_m24c01_so8n_footprint(),
        note=_M24C01_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
