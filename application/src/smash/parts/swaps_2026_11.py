"""BOM-sourcing swaps accepted 2026-11-22 (see availability/decisions.csv).

Each factory replaces an unorderable / China-lot / obsolete part. Where the
new part is the same die or the same package + pinout, the factory wraps the
old one and only changes the part number (and notes why). Otherwise it is
built from the vendored library in parts/sources/<dir>/ (pads + STEP
verbatim; pin NAMES kept compatible with the old part's callers, the vendor
names as aliases).
"""
from __future__ import annotations

from smash.state import Chip, Pin
from smash.parts.devboard import _sam
from smash.parts._slug import canonical_id

_WHY = "BOM sourcing 2026-11-22 (availability/decisions.csv)"


def _renumber(base, pn: str, manf: str | None = None, note: str = "", **extra):
    """Override dict that re-labels a part built by an existing factory."""
    d = dict(manf_pn=pn, name=pn, value=pn, canonical_id=canonical_id(pn), **extra)
    if manf:
        d["manf"] = manf
    d["note"] = f"{note} ({_WHY}; footprint/pins from {base})."
    return d


# ── same die / package, new part number ─────────────────────────────────

def add_stm32mp257fal3(design, ref: str, **overrides) -> Chip:
    """ST STM32MP257FAL3 — the MP255FAL3 superset (adds the NPU), secure F
    variant, same VFBGA-361 10×10 AL package. CubeMX STM32MP255FALx.xml vs
    STM32MP257FALx.xml: all 361 balls identical (name + position)."""
    from smash.parts.mcus import add_stm32mp255fal3
    ov = _renumber("STM32MP255FAL3", "STM32MP257FAL3",
                   note="MP255FAL3 had 0 stock at all 3 suppliers; MP257 adds the NPU",
                   description="STM32MP257F: 2× Cortex-A35 1.5 GHz + M33, NPU, GPU, secure boot + crypto, VFBGA-361 10×10")
    ov.update(overrides)
    return add_stm32mp255fal3(design, ref, **ov)


def add_adf4351bcpz_rl7(design, ref: str, **overrides) -> Chip:
    """ADF4351BCPZ in the -RL7 reel code (the stocked ordering code)."""
    from smash.parts.rf import add_adf4351bcpz
    ov = _renumber("ADF4351BCPZ", "ADF4351BCPZ-RL7", note="same part, reel code")
    ov.update(overrides)
    return add_adf4351bcpz(design, ref, **ov)


def add_dsc1001ci1_027_0000(design, ref: str, **overrides) -> Chip:
    """Microchip DSC1001CI1-027.0000 — same DSC1001 die, ±50 ppm grade."""
    from smash.parts.oscillators import add_dsc1001ci5_027_0000
    ov = _renumber("DSC1001CI5-027.0000", "DSC1001CI1-027.0000",
                   note="looser stability grade, stocked at 2 suppliers")
    ov.update(overrides)
    return add_dsc1001ci5_027_0000(design, ref, **ov)


def add_sit1602bi_12_xxe_40(design, ref: str, *, vdd: str = "18", **overrides) -> Chip:
    """SiTime SiT1602BI-12-{vdd}E-40.000000 — 40 MHz MEMS XO, ±20 ppm, 2.5 × 2.0 mm,
    programmed to order (vdd "18" = 1.8 V, "33" = 3.3 V). 2520 pinout = DSC1001's
    (1 OE/ST, 2 GND, 3 OUT, 4 VDD), so the DSC1001 land and pin names are reused."""
    from smash.parts.oscillators import add_dsc1001ci5_040_0000
    pn = f"SIT1602BI-12-{vdd}E-40.000000"
    ov = _renumber("DSC1001CI5-040.0000", pn, manf="SiTime",
                   note="DSC1001CI5-040 had 0 stock at Mouser + Digi-Key",
                   description=f"40 MHz MEMS oscillator, LVCMOS, {vdd[0]}.{vdd[1]} V, ±20 ppm, 2.5×2.0 mm")
    ov.update(overrides)
    return add_dsc1001ci5_040_0000(design, ref, **ov)


def add_mx25v8035fzni(design, ref: str, **overrides) -> Chip:
    """Macronix MX25V8035FZNI — 8 Mb QSPI NOR, WSON-8 6×5. Standard SPI-NOR
    pinout = SST26VF080A's (1 CS#, 2 SO/SIO1, 3 WP#/SIO2, 4 GND, 5 SI/SIO0,
    6 SCLK, 7 HOLD#/SIO3, 8 VCC), same WSON land. ⚠ confirm the AWR1843
    boot ROM's QSPI support for this part before release."""
    from smash.parts.flash import add_sst26vf080a
    ov = _renumber("SST26VF080A-104I/MF", "MX25V8035FZNI", manf="Macronix",
                   note="SST26VF080A stock was thin; TI radar EVMs use the MX25V family",
                   description="8 Mb serial NOR flash, quad SPI, 2.3-3.6 V, WSON-8 6×5")
    ov.update(overrides)
    return add_sst26vf080a(design, ref, **ov)


# ── new libraries, pin names kept compatible with the old callers ───────

def add_ssm3j372r_lf(design, ref: str, **overrides) -> Chip:
    """Toshiba SSM3J372R,LF — P-FET −30 V / −6 A, Vth −0.5…−1.2 V, RDS(on)
    50 mΩ max @ −4.5 V, SOT-23F. Pins 1 G, 2 S, 3 D (= IRLML6402). VGS max
    +6 V / −12 V."""
    pins = [Pin(num="1", name="G", aliases=["Gate"], type="input"),
            Pin(num="2", name="S", aliases=["Source"], type="io"),
            Pin(num="3", name="D", aliases=["Drain"], type="io")]
    return _sam(design, ref, pn="SSM3J372R,LF", part_dir="SSM3J372R_LF", mod="SSM3J372RLF.kicad_mod",
                package="SOT-23F", height_mm=0.9, size_mm=(2.9, 2.4), manf="Toshiba",
                description="P-MOSFET −30 V −6 A, 50 mΩ @ −4.5 V, SOT-23F", pins=pins,
                ring_courtyard=True, note=f"Replaces IRLML6402TRPBF (obsolete) — {_WHY}.", **overrides)


def add_ru1j002yntcl(design, ref: str, **overrides) -> Chip:
    """ROHM RU1J002YNTCL — N-FET 50 V 0.2 A, 0.9 V drive, SOT-323FL. Pins
    1 G, 2 S, 3 D (= BSS138AKM numbering). VGS max ±8 V."""
    pins = [Pin(num="1", name="G", aliases=["Gate"], type="input"),
            Pin(num="2", name="S", aliases=["Source"], type="io"),
            Pin(num="3", name="D", aliases=["Drain"], type="io")]
    return _sam(design, ref, pn="RU1J002YNTCL", part_dir="RU1J002YNTCL", mod="SOTFL65P210X105-3N.kicad_mod",
                package="SOT-323FL (UMT3F)", height_mm=1.05, size_mm=(2.0, 2.1), manf="ROHM",
                description="N-MOSFET 50 V 0.2 A, 0.9 V drive, SOT-323FL", pins=pins,
                ring_courtyard=True, note=f"Replaces BSS138AKM-QYL (China lots) — {_WHY}.", **overrides)


def add_rb160vam_60(design, ref: str, **overrides) -> Chip:
    """ROHM RB160VAM-60TR — Schottky 60 V 1 A, TUMD2SM. Pins 1 K, 2 A."""
    pins = [Pin(num="1", name="K", aliases=["Cathode"], type="io"),
            Pin(num="2", name="A", aliases=["Anode"], type="io")]
    return _sam(design, ref, pn="RB160VAM-60TR", part_dir="RB160VAM-60", mod="RB160VAM60.kicad_mod",
                package="TUMD2SM", height_mm=0.7, size_mm=(2.5, 1.3), manf="ROHM",
                description="Schottky diode 60 V 1 A, TUMD2SM", pins=pins, ring_courtyard=True,
                note=f"Replaces PMEG6010CEJ (China lots) — {_WHY}.", **overrides)


def add_vemd5110x01(design, ref: str, **overrides) -> Chip:
    """Vishay VEMD5110X01 — PIN photodiode with daylight-blocking filter
    (790–1050 nm), top-view SMD. Pads 1 + 2 = cathode (both must be
    connected: `K` and `K2`), 3 = anode, 4 = NC."""
    pins = [Pin(num="1", name="K", aliases=["CATHODE_1"], type="io"),
            Pin(num="2", name="K2", aliases=["CATHODE_2"], type="io"),
            Pin(num="3", name="A", aliases=["ANODE"], type="io"),
            Pin(num="4", name="NC", type="nc")]
    return _sam(design, ref, pn="VEMD5110X01", part_dir="VEMD5110X01", mod="VEMD5110X01.kicad_mod",
                package="SMD top view (5.0×4.0)", height_mm=0.9, size_mm=(5.0, 4.0), manf="Vishay",
                description="Si PIN photodiode, daylight filter 790-1050 nm, ±65°", pins=pins,
                note=(f"Replaces VBPW34FAS (China lots) — {_WHY}. Sensitive area smaller "
                      "than the VBPW34FAS: re-check the IR wake margin."), **overrides)


def _sot25_ldo(design, ref, *, pn, part_dir, mod, description, note, **overrides) -> Chip:
    """Torex SOT-25 LDO: 1 VIN, 2 VSS, 3 CE, 4 NC, 5 VOUT. Names follow the
    old LDO callers (IN/VIN, GND, EN, OUT/VOUT); no exposed pad."""
    pins = [Pin(num="1", name="VIN", aliases=["IN"], type="power"),
            Pin(num="2", name="GND", aliases=["VSS"], type="ground"),
            Pin(num="3", name="EN", aliases=["CE"], type="input"),
            Pin(num="4", name="NC", type="nc"),
            Pin(num="5", name="VOUT", aliases=["OUT"], type="power")]
    return _sam(design, ref, pn=pn, part_dir=part_dir, mod=mod, package="SOT-25", height_mm=1.3,
                size_mm=(2.9, 2.8), manf="Torex", description=description, pins=pins,
                note=f"{note} — {_WHY}.", **overrides)


def add_xc6504a331mr_g(design, ref: str, **overrides) -> Chip:
    """Torex XC6504A331MR-G — 3.3 V nano-Iq LDO (0.6 µA), SOT-25."""
    return _sot25_ldo(design, ref, pn="XC6504A331MR-G", part_dir="XC6504A331MR-G",
                      mod="SOT95P280X130-5N.kicad_mod",
                      description="3.3 V 150 mA LDO, 0.6 µA Iq, CL-less, SOT-25",
                      note="Replaces TPS7A0233PDQNR (China lots); +0.3/+0.18 mm face rise accepted",
                      **overrides)


def add_xc6220b181mr_g(design, ref: str, **overrides) -> Chip:
    """Torex XC6220B181MR-G — 1.8 V 1 A LDO, SOT-25 (600 mW). SnapMagic land
    shared with the XC8107 (same Torex MR SOT-25). ⚠ thermal check at the
    radar's 1.8 V load."""
    c = _sot25_ldo(design, ref, pn="XC6220B181MR-G", part_dir="XC6220B181MR-G",
                   mod="IC_XC8107AC20MR-G.kicad_mod",
                   description="1.8 V 1 A LDO, low noise, SOT-25",
                   note="Replaces LDL112PV18R (China lots)", **overrides)
    c.footprint.model_rotate_deg = _XC6220_MODEL_ROT    # SnapMagic STEP is Y-up
    return c


_XC6220_MODEL_ROT = (-90.0, 0.0, 0.0)


def add_tja1462btk_0z(design, ref: str, **overrides) -> Chip:
    """NXP TJA1462BTK/0Z — CAN FD SIC transceiver, HVSON-8 3×3. B variant:
    pin 5 = VIO (SamacSys symbol labels it N.C. — the B datasheet pinout
    wins). EP (9) → GND."""
    pins = [Pin(num="1", name="TXD", type="input"), Pin(num="2", name="GND", type="ground"),
            Pin(num="3", name="VCC", type="power"), Pin(num="4", name="RXD", type="output"),
            Pin(num="5", name="VIO", type="power"), Pin(num="6", name="CANL", type="io"),
            Pin(num="7", name="CANH", type="io"), Pin(num="8", name="STB", type="input"),
            Pin(num="9", name="EP", type="ground")]
    return _sam(design, ref, pn="TJA1462BTK/0Z", part_dir="TJA1462BTK_0Z",
                mod="SON65P300X300X100-9N-D.kicad_mod", package="HVSON-8 (3×3)", height_mm=1.0,
                size_mm=(3.0, 3.0), manf="NXP", description="CAN FD SIC transceiver 8 Mbit/s, VIO, HVSON-8",
                pins=pins, note=f"Replaces TCAN1042 (China lot / EOL) — {_WHY}.", **overrides)


def add_ism330dlctr(design, ref: str, **overrides) -> Chip:
    """ST ISM330DLCTR — industrial 6-axis IMU, LGA-14 2.5×3×0.86 (same
    package/pinout family as the ISM330DHCX; register map differs → driver)."""
    from smash.parts.devboard import _sym
    from smash.parts._artifacts import build_pins
    pins = build_pins(_sym("ISM330DLCTR"))
    for p in pins:
        if p.name == "SDO/SA0":
            p.aliases = list(p.aliases or []) + ["SA0", "SDO"]
    return _sam(design, ref, pn="ISM330DLCTR", part_dir="ISM330DLCTR", mod="LGA-14_1.kicad_mod",
                package="LGA-14 (2.5×3)", height_mm=0.86, size_mm=(2.5, 3.0),
                manf="STMicroelectronics", description="Industrial 6-axis IMU (accel + gyro), LGA-14",
                pins=pins, note=f"Replaces ISM330DHCXTR (0 stock) — {_WHY}; firmware driver changes.",
                **overrides)


def add_usblc6_4sc6(design, ref: str, **overrides) -> Chip:
    """ST USBLC6-4SC6 — 4-line USB ESD array, SOT-23-6. 1 I/O1, 2 GND,
    3 I/O2, 4 I/O3, 5 VBUS, 6 I/O4 (I/O1↔I/O4 and I/O2↔I/O3 are the
    flow-through pairs)."""
    from smash.parts.devboard import _sym
    from smash.parts._artifacts import build_pins
    return _sam(design, ref, pn="USBLC6-4SC6", part_dir="USBLC6-4SC6", mod="SOT95P280X145-6N.kicad_mod",
                package="SOT-23-6", height_mm=1.45, size_mm=(2.9, 2.8), manf="STMicroelectronics",
                description="4-line USB ESD protection, SOT-23-6", pins=build_pins(_sym("USBLC6-4SC6")),
                note=f"Replaces TPD4E05U06DQAR (China lots) — {_WHY}.", **overrides)
