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
                   note="looser stability grade, stocked at 2 suppliers",
                   description="27 MHz MEMS oscillator, ±50 ppm, V_DD=1.7..3.6 V, CDFN 3.2×2.5 mm 4-pad")
    ov.update(overrides)
    return add_dsc1001ci5_027_0000(design, ref, **ov)


def add_sit1602bi_12_xxe_40(design, ref: str, *, vdd: str = "18", **overrides) -> Chip:
    """SiTime SiT1602BI-12-{vdd}E-40.000000 — 40 MHz MEMS XO, ±25 ppm (code 2),
    PQFN 2.5 × 2.0 × 0.75 mm (package code 1), programmed to order (vdd "18" =
    1.8 V, "33" = 3.3 V). Pins = DSC1001's (1 OE, active high; 2 GND; 3 OUT;
    4 VDD) so its pin names are reused; the LAND is SiTime's 2520 one (pads
    1.0 × 1.1 at 1.9 × 1.5 centres, SiT1602B DS p.10) — the DSC1001 "C" land
    is the 3.2 × 2.5 package."""
    from smash.parts.oscillators import add_dsc1001ci5_040_0000
    from smash.parts.devboard import src, _step
    from smash.parts._artifacts import pads_from_kicad_mod, outline_polygon
    pn = f"SIT1602BI-12-{vdd}E-40.000000"
    mod = src("SiT8008BI-12-33E-27.000000", "QFN_2520_4pins.kicad_mod")   # SiTime 2520 land
    fp = Footprint(name="QFN_2520_4pins", package_class="PQFN-4 (2.5×2.0)",
                   pads=pads_from_kicad_mod(mod), body_outline=outline_polygon(mod, "F.Fab"),
                   courtyard=outline_polygon(mod, "F.CrtYd"), size_mm=(2.5, 2.0), height_mm=0.75,
                   model_3d_path=_step("SiT8008BI-12-33E-27.000000"),
                   source="samacsys").ensure_courtyard_clearance()
    ov = _renumber("DSC1001CI5-040.0000", pn, manf="SiTime",
                   note="DSC1001CI5-040 had 0 stock at Mouser + Digi-Key",
                   description=f"40 MHz MEMS oscillator, LVCMOS, {vdd[0]}.{vdd[1]} V, ±25 ppm, PQFN 2.5×2.0",
                   package="PQFN-4 (2.5×2.0×0.75)", size_mm=(2.5, 2.0), height_mm=0.75, footprint=fp)
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
    """NXP TJA1462ATK/0Z — CAN FD SIC transceiver, HVSON-8 3×3. The A variant
    has the VIO pin (5) that sets the TXD/RXD logic level (3.3 V here); on the
    B variant pin 5 is n.c. and the logic follows VCC = 5 V (TJA1462 DS Rev 3
    Fig. 1 note 1, Table 8 note 3). Function name kept for call sites. EP (9) → GND."""
    pins = [Pin(num="1", name="TXD", type="input"), Pin(num="2", name="GND", type="ground"),
            Pin(num="3", name="VCC", type="power"), Pin(num="4", name="RXD", type="output"),
            Pin(num="5", name="VIO", type="power"), Pin(num="6", name="CANL", type="io"),
            Pin(num="7", name="CANH", type="io"), Pin(num="8", name="STB", type="input"),
            Pin(num="9", name="EP", type="ground")]
    return _sam(design, ref, pn="TJA1462ATK/0Z", part_dir="TJA1462BTK_0Z",   # same HVSON-8 land/symbol
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


def add_stm32u545rei6q(design, ref: str, **overrides) -> Chip:
    """ST STM32U545REI6Q — Cortex-M33 160 MHz, 512 KB, TrustZone + AES/SAES/PKA,
    UFBGA-64 5×5, SMPS ("Q") package: VLXSMPS → 2.2 µH → VDD11 (both balls)
    with VDD11 + VDDSMPS decoupling. Pins/balls = SamacSys symbol, checked
    against CubeMX STM32U545REIxQ.xml (64/64 match). Replaces the
    STM32G0B1REI6N fin-node MCU (Mouser 39 pcs, 52 wk)."""
    from smash.parts.devboard import _sym
    from smash.parts._artifacts import build_pins
    return _sam(design, ref, pn="STM32U545REI6Q", part_dir="STM32U545REI6Q",
                mod="BGA64C50P8X8_500X500X60.kicad_mod", package="UFBGA-64 (5×5, 0.5)",
                height_mm=0.6, size_mm=(5.0, 5.0), manf="STMicroelectronics",
                description="MCU Cortex-M33 160 MHz, 512 KB flash, TrustZone, AES/PKA, SMPS, UFBGA-64",
                pins=build_pins(_sym("STM32U545REI6Q")),
                note=f"Fin node MCU — {_WHY}.", **overrides)


_TC78H653_PINS = {1: "IN4/PHA_B", 2: "IN3/ENB_B", 3: "NC_1", 4: "IN1/ENB_A", 5: "IN2/PHA_A",
                  6: "STBY", 7: "NC_2", 8: "GND_1", 9: "OUT2", 10: "OUT1", 11: "OUT3",
                  12: "OUT4", 13: "GND_2", 14: "VM", 15: "LARGE", 16: "MODE", 17: "EP"}


def add_tc78h653ftg(design, ref: str, **overrides) -> Chip:
    """Toshiba TC78H653FTG,EL — 1.8 V dual H-bridge, VM 1.8-7.5 V, 2 A/bridge
    (small mode), P-VQFN16 3×3. Pins per the Toshiba datasheet (2018-11-13,
    vendored as TC78H653FTG_datasheet.pdf): MODE = H → PHASE input mode
    (IN1/ENB_A = enable/PWM, IN2/PHA_A = phase; IN3/ENB_B, IN4/PHA_B), LARGE = L
    → two independent bridges (stepper). No internal current regulation —
    the coil current is set by VM / winding R, firmware PWMs ENB to limit it.
    Generic IPC QFN-16 land (no vendor land); EP → GND."""
    pins = [Pin(num=str(n), name=nm, type=("ground" if nm.startswith(("GND", "EP")) else
                                           "nc" if nm.startswith("NC") else
                                           "power" if nm == "VM" else
                                           "output" if nm.startswith("OUT") else "input"))
            for n, nm in _TC78H653_PINS.items()]
    return _sam(design, ref, pn="TC78H653FTG,EL", part_dir="TC78H653FTG_EL",
                mod="QFN50P300X300X90-17N.kicad_mod", package="P-VQFN16-0303 (3×3)",
                height_mm=0.9, size_mm=(3.0, 3.0), manf="Toshiba",
                description="Dual H-bridge driver 1.8-7.5 V, 2 A, phase/enable, VQFN-16",
                pins=pins, ring_courtyard=True,
                note=f"Replaces DRV8428 (China lots) — {_WHY}. No current regulation (VREF gone).",
                **overrides)


def add_stm32u535cbu6(design, ref: str, **overrides) -> Chip:
    """ST STM32U535CBU6 — Cortex-M33 160 MHz, 128 KB flash, TrustZone, USB FS
    (crystal-less, HSI48 + CRS), FDCAN1, UFQFPN-48 7×7 + EP (LDO version:
    VCAP 4.7 µF). Dev-board probe MCU replacing the STM32G474CEU6 (0 stock,
    52 wk). Ball map = SamacSys symbol; peripheral pins from CubeMX
    STM32U535CBUx.xml."""
    from smash.parts.devboard import _sym
    from smash.parts._artifacts import build_pins
    pins = build_pins(_sym("STM32U535CBU6"))
    for p in pins:
        if p.name == "PE":
            p.aliases = list(p.aliases or []) + ["EP"]
    return _sam(design, ref, pn="STM32U535CBU6", part_dir="STM32U535CBU6",
                mod="QFN50P700X700X60-49N.kicad_mod", package="UFQFPN-48 (7×7)",
                height_mm=0.6, size_mm=(7.0, 7.0), manf="STMicroelectronics",
                description="MCU Cortex-M33 160 MHz, 128 KB flash, USB FS, FDCAN, UFQFPN-48",
                pins=pins, note=f"Dev-board MCU — {_WHY}. Buy the Mouser Taiwan lot.", **overrides)


def add_mcp9808t_e_mc(design, ref: str, **overrides) -> Chip:
    """Microchip MCP9808T-E/MC — ±0.25 °C (typ) I²C temperature sensor, DFN-8
    2×3 + EP. Pins (DS20005095): 1 SDA, 2 SCL, 3 Alert (open-drain), 4 GND,
    5 A2, 6 A1, 7 A0, 8 VDD, 9 EP (→ GND). Address 0b0011 A2 A1 A0.
    Generic IPC DFN land (SnapMagic SON50P200X300X100-9N)."""
    pins = [Pin(num="1", name="SDA", type="io"), Pin(num="2", name="SCL", type="input"),
            Pin(num="3", name="ALERT", type="output"), Pin(num="4", name="GND", type="ground"),
            Pin(num="5", name="A2", type="input"), Pin(num="6", name="A1", type="input"),
            Pin(num="7", name="A0", type="input"), Pin(num="8", name="VDD", aliases=["V+"], type="power"),
            Pin(num="9", name="EP", type="ground")]
    return _sam(design, ref, pn="MCP9808T-E/MC", part_dir="MCP9808T-E_MC",
                mod="SON50P200X300X100-9N.kicad_mod", package="DFN-8 (2×3)", height_mm=1.0,
                size_mm=(2.0, 3.0), manf="Microchip", description="I²C digital temperature sensor ±0.25 °C, DFN-8",
                pins=pins, ring_courtyard=True, note=f"Replaces TMP117 (China lots) — {_WHY}.",
                model_rotate=(-90.0, 0.0, 0.0), **overrides)   # vendor STEP is Y-up


def add_bmm350(design, ref: str, **overrides) -> Chip:
    """Bosch Sensortec BMM350 — 3-axis TMR magnetometer, I²C/I3C, WLCSP-9
    1.28×1.28×0.54, 0.4 mm pitch. Balls (Bosch DS): A1 INT, A2 SDA, A3 SCK,
    B1 GND, B2 ADSEL (GND → 0x14, VDDIO → 0x15), B3 VDDIO, C1 VDD, C2 CRST
    (external 2.2 µF low-ESL), C3 BYPASS (→ GND). SnapMagic land + symbol.
    Replaces the IIS2MDC (0 stock). ⚠ check its noise against the magnetic-
    link sim (written for the IIS2MDC)."""
    from smash.parts.devboard import _sym
    from smash.parts._artifacts import build_pins
    c = _sam(design, ref, pn="BMM350", part_dir="BMM350", mod="BGA9C40P3X3_128X128X54.kicad_mod",
             package="WLCSP-9 (1.28×1.28)", height_mm=0.54, size_mm=(1.28, 1.28),
             manf="Bosch Sensortec", description="3-axis TMR magnetometer, I²C/I3C, WLCSP-9",
             pins=build_pins(_sym("BMM350")), ring_courtyard=True,
             model_rotate=(-90.0, 0.0, 0.0),                    # vendor STEP is Y-up
             note=f"Replaces IIS2MDCTR (0 stock) — {_WHY}; new driver; check noise vs the mag-link sim.",
             **overrides)
    return c


def add_sit5356aecfq_33n0_32(design, ref: str, **overrides) -> Chip:
    """SiTime SiT5356AECFQ-33N0-32.000000T — 32 MHz MEMS Super-TCXO, clipped
    sine, 3.3 V, −40…105 °C, 5.0 × 3.2 mm ceramic QFN-10, programmed to order
    (SiTime direct). This configuration: pin 1 = NC (no OE/VC), no I²C.
    Balls: 1 OE/VC/NC, 2 SCL/NC, 3 NC, 4 GND, 5 A0/NC, 6 CLK, 7-8 NC, 9 VDD,
    10 SDA/NC. Library = SamacSys model of the 20 MHz sibling (same package)."""
    from smash.parts.devboard import _sym
    from smash.parts._artifacts import build_pins
    pins = build_pins(_sym("SiT5356AECFQ-33N0-20.000000"))
    for p in pins:
        if p.name == "CLK":
            p.aliases = list(p.aliases or []) + ["OUT"]
    c = _sam(design, ref, pn="SiT5356AECFQ-33N0-32.000000T", part_dir="SiT5356AECFQ-33N0-20.000000",
             mod="Ceramic_QFN_5032_10pins.kicad_mod", package="QFN-10 ceramic (5.0×3.2)", height_mm=0.9,
             size_mm=(5.0, 3.2), manf="SiTime", description="32 MHz MEMS Super-TCXO, clipped sine, 3.3 V",
             pins=pins, note=f"Fitted LoRa reference (MEMS, shock) — {_WHY}; TG2016 footprint stays as the unfitted alternate.",
             **overrides)
    c.footprint.model_3d_path = "application/src/smash/parts/sources/SiT5356AECFQ-33N0-20.000000/SiT5356AECFQ-33N0-20.000000.stp"
    return c


def add_mcp6541t_e_ot(design, ref: str, **overrides) -> Chip:
    """Microchip MCP6541T-E/OT — push-pull nanopower comparator (600 nA),
    1.6-5.5 V, SOT-23-5: 1 OUT, 2 VSS, 3 VIN+, 4 VIN−, 5 VDD."""
    from smash.parts.devboard import _sym
    from smash.parts._artifacts import build_pins
    return _sam(design, ref, pn="MCP6541T-E/OT", part_dir="MCP6541T-E_OT", mod="SOT95P270X145-5N.kicad_mod",
                package="SOT-23-5", height_mm=1.45, size_mm=(2.9, 2.8), manf="Microchip",
                description="Push-pull nanopower comparator 600 nA, SOT-23-5",
                pins=build_pins(_sym("MCP6541T-E_OT")),
                note=f"Replaces TLV3691IDPFR (China lots) — {_WHY}.", **overrides)


# ── 2026-11-22 libraries drop (rounds 17-19) ────────────────────────────────
from smash.state import Pad, Footprint                       # noqa: E402
from smash.parts._artifacts import datasheet_ref             # noqa: E402


def add_lmr10510ysde_nopb(design, ref: str, **overrides) -> Chip:
    """TI LMR10510YSDE/NOPB — the same 1 A / 1.6 MHz non-synchronous buck as
    the XMFE, in WSON-6 3 × 3 × 0.8 mm (vs SOT-23-5 1.45 mm): smaller-parts
    round 17. Pins 1 FB, 2 GND, 3 SW, 4 VIND (power in), 5 VINA (analog in,
    tie to VIN), 6 EN, 7 DAP (exposed pad → GND)."""
    pins = [Pin(num="1", name="FB", type="input"), Pin(num="2", name="GND", type="power"),
            Pin(num="3", name="SW", type="output"),
            Pin(num="4", name="VIN", aliases=["VIND"], type="power"),
            Pin(num="5", name="VINA", type="power"), Pin(num="6", name="EN", type="input"),
            Pin(num="7", name="DAP", aliases=["EP"], type="power")]
    return _sam(design, ref, pn="LMR10510YSDE/NOPB", part_dir="LMR10510YSDE_NOPB",
                mod="SON95P300X300X80-7N.kicad_mod", package="WSON-6 (3×3)", height_mm=0.8,
                size_mm=(3.0, 3.0), manf="Texas Instruments",
                description="Step-down buck 3-5.5 V in, 1 A, 1.6 MHz, WSON-6 3×3",
                pins=pins, note=f"Replaces LMR10510XMFE (SOT-23-5 1.45 mm) — {_WHY}.", **overrides)


def add_ssm3k35ctc_l3f(design, ref: str, **overrides) -> Chip:
    """Toshiba SSM3K35CTC,L3F — N-FET 20 V 0.25 A, CST3C 0.8 × 0.6 × 0.38 mm
    (vs RU1J002YN 1.05 mm). VGS ±10 V; for drains ≤ ~12 V only. Pins 1 G,
    2 S, 3 D. Land = SamacSys CST3C (SSM3J64CTC family)."""
    pins = [Pin(num="1", name="G", aliases=["Gate"], type="input"),
            Pin(num="2", name="S", aliases=["Source"], type="io"),
            Pin(num="3", name="D", aliases=["Drain"], type="io")]
    return _sam(design, ref, pn="SSM3K35CTC,L3F", part_dir="SSM3K35CTC_L3F", mod="SSM3J64CTCL3F.kicad_mod",
                package="CST3C", height_mm=0.38, size_mm=(0.8, 0.6), manf="Toshiba",
                description="N-MOSFET 20 V 0.25 A, CST3C 0.38 mm", pins=pins, ring_courtyard=True,
                note=f"Low-voltage replacement for RU1J002YNTCL (height) — {_WHY}.", **overrides)


def add_ssm3k7002kfu_lf(design, ref: str, **overrides) -> Chip:
    """Toshiba SSM3K7002KF,LF — N-FET 60 V 0.4 A, S-Mini (SOT-346 / SC-59)
    2.9 × 2.5 × 1.1 mm, on the SC-59 land it was always drawn on (1SS294LFT).
    For the 33 V activation / cutter / coil positions. Pins 1 G, 2 S, 3 D.
    VGS ±20 V. (Function name kept for call sites; the KFU is the USM/SOT-323
    package, which does not fit this land.)"""
    pins = [Pin(num="1", name="G", aliases=["Gate"], type="input"),
            Pin(num="2", name="S", aliases=["Source"], type="io"),
            Pin(num="3", name="D", aliases=["Drain"], type="io")]
    return _sam(design, ref, pn="SSM3K7002KF,LF", part_dir="SSM3K7002KFU_LF", mod="1SS294LFT.kicad_mod",
                package="S-Mini (SOT-346 / SC-59)", height_mm=1.1, size_mm=(2.9, 2.5), manf="Toshiba",
                description="N-MOSFET 60 V 0.4 A, S-Mini/SC-59", pins=pins, ring_courtyard=True,
                note=f"33 V-position replacement for RU1J002YNTCL — {_WHY}.", **overrides)


def add_nx7002ak_215(design, ref: str, **overrides) -> Chip:
    """Nexperia NX7002AK,215 — N-FET 60 V, 190 mA (Tamb 25 °C) / 760 mA
    peak, V_GSth 1.1-2.1 V, R_DS(on) 5.2 Ω max at V_GS 5 V, V_GS ±20 V,
    SOT23 (TO-236AB) 2.9 × 2.5 × 1.1 mm max. Pins 1 G, 2 S, 3 D (DS Table 2).
    For the 33 V activation / cutter positions (≤ 120 mA wire pulses) and the
    health-coil driver (~0.13 A pulses at the 3.3 V gate drive). IPC
    SOT95P237 land (= the DS reflow footprint, 0.95 mm pitch)."""
    pins = [Pin(num="1", name="G", aliases=["Gate"], type="input"),
            Pin(num="2", name="S", aliases=["Source"], type="io"),
            Pin(num="3", name="D", aliases=["Drain"], type="io")]
    return _sam(design, ref, pn="NX7002AK,215", part_dir="NX7002AK_215", mod="SOT95P237X112-3N.kicad_mod",
                package="SOT23 (TO-236AB)", height_mm=1.1, size_mm=(2.9, 2.5), manf="Nexperia",
                description="N-MOSFET 60 V 190 mA, logic-level, SOT23", pins=pins, ring_courtyard=True,
                datasheet="application/src/smash/parts/sources/NX7002AK_215/NX7002AK_215.pdf",
                note="Sourcing round 25: Mouser + Farnell + Digi-Key, Malaysia.", **overrides)


def add_ihlp2020bzer100m01(design, ref: str, **overrides) -> Chip:
    """Vishay IHLP2020BZER100M01 — 10 µH ±20 %, IHLP-2020BZ-01, 5.49 × 5.18 ×
    2.0 mm. Replaces the XGL5020-822 on L_ACTIVATE (round 19: Mouser + Digi-Key
    Mexico lots). Isat 4.0 A typ (20 % drop), heat rating 2.3 A: covers the
    TPS61175's 1.29 A operating peak (electrical audit)."""
    pins = [Pin(num="1", name="1", type="passive"), Pin(num="2", name="2", type="passive")]
    return _sam(design, ref, pn="IHLP2020BZER100M01", part_dir="IHLP2020BZER100M01",
                mod="INDPM5552X200N.kicad_mod", package="IHLP-2020BZ", height_mm=2.0,
                size_mm=(5.49, 5.18), manf="Vishay", value="10uH",
                description="Power inductor 10 µH, IHLP-2020BZ-01, 2.0 mm", pins=pins,
                note=f"Replaces XGL5020-822MEC — {_WHY}.", **overrides)


def add_ncs1_292p(design, ref: str, **overrides) -> Chip:
    """Mini-Circuits NCS1-292+ — 1:1 50 Ω LTCC balun 1650-2850 MHz, 2.0 × 1.25
    × 0.84 mm (GE0805C-1). 1 unbalanced (dot), 2 GND / DC feed, 3 balanced,
    4 balanced (dot), 5 not used (ground externally), 6 NC. LTC5552 IF balun."""
    pins = [Pin(num="1", name="UNBAL", type="io"), Pin(num="2", name="GND_DC", type="power"),
            Pin(num="3", name="BAL_N", type="io"), Pin(num="4", name="BAL_P", type="io"),
            Pin(num="5", name="NU_GND", type="power"), Pin(num="6", name="NC", type="no_connect")]
    return _sam(design, ref, pn="NCS1-292+", part_dir="NCS1-292P", mod="NCS1292.kicad_mod",
                package="GE0805C-1", height_mm=0.84, size_mm=(2.0, 1.25), manf="Mini-Circuits",
                description="Ceramic balun 1:1 50 Ω, 1.65-2.85 GHz, 0805", pins=pins,
                note=f"LTC5552 differential IF → single-ended 2.1-2.4 GHz — {_WHY}.", **overrides)


def add_pe64904d_z(design, ref: str, **overrides) -> Chip:
    """pSemi PE64904D-Z — DTC ~1.1-5.1 pF, 32 states, 3-wire serial; 10-lead
    QFN 2 × 2 × 0.45 mm. Land = SamacSys PE64904C-Z (the C → D change is the
    2023 ordering-code PCN, same package). Pins 1/2 RF−, 3 DGND, 4 VDD, 5 SCL,
    6 SEN, 7 SDA, 8/9 RF+, 10 GND. Same pin roles as the PE64906 (no EP)."""
    pins = [Pin(num="1", name="RF-_1", type="io"), Pin(num="2", name="RF-_2", type="io"),
            Pin(num="3", name="GND_1", aliases=["DGND"], type="power"),
            Pin(num="4", name="VDD", type="power"), Pin(num="5", name="SCL", type="input"),
            Pin(num="6", name="SEN", type="input"), Pin(num="7", name="SDA", type="input"),
            Pin(num="8", name="RF+_1", type="io"), Pin(num="9", name="RF+_2", type="io"),
            Pin(num="10", name="GND_2", aliases=["GND"], type="power")]
    return _sam(design, ref, pn="PE64904D-Z", part_dir="PE64904C-Z", mod="QFN50P200X200X50-10N-D.kicad_mod",
                package="QFN-10 2x2", height_mm=0.45, size_mm=(2.0, 2.0), manf="pSemi",
                description="Digitally tunable capacitor ~1.1-5.1 pF, 32 states, QFN-10 2x2",
                pins=pins, note=f"Replaces PE64906B-Z (0 stock) — {_WHY}. RECHECK the S1 tuner match (range shifted up ~0.2-0.5 pF).",
                **overrides)


def _land_fp(name, pads, size, height, part_dir=None, note=""):
    w, h = size
    fp = Footprint(name=name, package_class=name, pads=pads,
                   body_outline=[(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)],
                   courtyard=[], size_mm=size, height_mm=height,
                   model_3d_path=datasheet_ref(part_dir, f"{part_dir}.stp") if part_dir else None,
                   source="datasheet", note=note)
    return fp.ensure_courtyard_clearance()


def add_tlv7031dpwr(design, ref: str, **overrides) -> Chip:
    """TI TLV7031DPWR — nanopower (335 nA) push-pull comparator, X2SON-5 (DPW)
    0.8 × 0.8 × 0.4 mm max. Pins (X2SON, DS Table 4-1): 1 OUT, 2 V+, 3 V−
    (centre pad), 4 IN−, 5 IN+. Land = TI DPW0005A "Example board layout"
    (4 × 0.42 × 0.22 at ±0.39 / ±0.24; TI centre 0.25 ◇ drawn as a 0.20 □ for 0.08 mm clearance)."""
    pads = [Pad(num="1", position_mm=(-0.39, -0.24), size_mm=(0.42, 0.22)),
            Pad(num="2", position_mm=(-0.39, 0.24), size_mm=(0.42, 0.22)),
            Pad(num="4", position_mm=(0.39, 0.24), size_mm=(0.42, 0.22)),
            Pad(num="5", position_mm=(0.39, -0.24), size_mm=(0.42, 0.22)),
            Pad(num="3", position_mm=(0.0, 0.0), size_mm=(0.20, 0.20))]
    fp = _land_fp("TI_DPW0005A_X2SON-5", pads, (0.8, 0.8), 0.4, part_dir="TLV7031DPWR",
                  note="TI DPW0005A land (datasheet SNOSD20, p.54)")
    pins = [Pin(num="1", name="OUT", type="output"), Pin(num="2", name="V+", aliases=["VCC"], type="power"),
            Pin(num="3", name="V-", aliases=["GND", "VEE"], type="power"),
            Pin(num="4", name="IN-", type="input"), Pin(num="5", name="IN+", type="input")]
    fields = dict(manf="Texas Instruments", manf_pn="TLV7031DPWR", canonical_id=canonical_id("TLV7031DPWR"),
                  name="TLV7031DPWR", value="TLV7031", package="X2SON-5 (DPW)",
                  description="Nanopower comparator 335 nA, push-pull, X2SON-5 0.8×0.8×0.4",
                  size_mm=(0.8, 0.8), height_mm=0.4, pins=pins, footprint=fp,
                  datasheet="application/src/smash/parts/sources/TLV7031DPWR/tlv7031.pdf",
                  note=f"Replaces TLV3691 (China lots; Digi-Key US lot) — {_WHY}.")
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_s1318d33_a4t2u4(design, ref: str, **overrides) -> Chip:
    """ABLIC S-1318D33-A4T2U4 — 3.3 V 100 mA LDO, 95 nA Iq, HSNT-4(1010)
    1.0 × 1.0 × 0.4 mm. D type: ON/OFF active-high, NO discharge shunt, NO
    ON/OFF pull-down (add one where 'floating = off' is relied on). Pins (DS
    Table 8): 1 VOUT, 2 VSS, 3 ON/OFF, 4 VIN; heat sink → GND (DS note *1).
    Land = ABLIC PL004-A-L-SD-2.0 (pads 0.30 × 0.37 at ±0.325 / ±0.54;
    heat sink drawn as a 0.30 □ + 1.02 × 0.12 bar)."""
    # smash y-UP, in the orientation of the package drawing PL004-A-P-SD (top
    # view: 1 bottom-left, 2 bottom-right, 3 top-right, 4 top-left; 1–2 and
    # 4–3 are the 0.65 mm pairs along the heat-sink bar) — the land
    # PL004-A-L-SD has its 0.65 mm pairs along x. (Fig. 6's sketch is the same
    # part turned 90°; its corners must not be copied onto this land.)
    pads = [Pad(num="1", position_mm=(-0.325, -0.54), size_mm=(0.30, 0.37)),
            Pad(num="2", position_mm=(0.325, -0.54), size_mm=(0.30, 0.37)),
            Pad(num="3", position_mm=(0.325, 0.54), size_mm=(0.30, 0.37)),
            Pad(num="4", position_mm=(-0.325, 0.54), size_mm=(0.30, 0.37)),
            Pad(num="5", position_mm=(0.0, 0.0), size_mm=(0.30, 0.30)),
            Pad(num="5", position_mm=(0.0, 0.0), size_mm=(1.02, 0.12))]
    fp = _land_fp("ABLIC_HSNT-4-1010", pads, (1.0, 1.0), 0.4,
                  note="ABLIC HSNT-4(1010) land PL004-A-L-SD-2.0 (S-1318 DS p.41)")
    # (2026-11-23) package STEP from SnapMagic's S-1318A33-A4T2U4 (same
    # HSNT-4(1010) body; the A/D suffix is only the ON/OFF logic). It is Y-up:
    # −90° about X seats it (z 0-0.4). The land stays the ABLIC datasheet one
    # (SnapMagic's is rotated 90° with placeholder custom pads). ⚠ Pin-1 corner
    # of the model not verified against the land — check in the 3D viewer.
    fp.model_3d_path = datasheet_ref("S-1318D33-A4T2U4", "HSNT-4-1010_S-1318A33.step")
    fp.model_rotate_deg = (-90.0, 0.0, 0.0)
    pins = [Pin(num="1", name="VOUT", aliases=["OUT"], type="power"),
            Pin(num="2", name="VSS", aliases=["GND"], type="power"),
            Pin(num="3", name="ON/OFF", aliases=["EN"], type="input"),
            Pin(num="4", name="VIN", aliases=["IN"], type="power"),
            Pin(num="5", name="EP", type="power")]
    fields = dict(manf="ABLIC", manf_pn="S-1318D33-A4T2U4", canonical_id=canonical_id("S-1318D33-A4T2U4"),
                  name="S-1318D33-A4T2U4", value="3.3V", package="HSNT-4(1010)",
                  description="LDO 3.3 V 100 mA, 95 nA Iq, HSNT-4 1.0×1.0×0.4",
                  size_mm=(1.0, 1.0), height_mm=0.4, pins=pins, footprint=fp,
                  datasheet="application/src/smash/parts/sources/S-1318D33-A4T2U4/S-1318_datasheet.pdf",
                  note=f"Replaces XC6504A331MR-G (SOT-25 1.3 mm) — {_WHY}.")
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_s1318d18_a4t2u4(design, ref: str, **overrides) -> Chip:
    """ABLIC S-1318D18-A4T2U4 — the 1.8 V output code of the S-1318D33 (same
    die family, HSNT-4(1010) land and pinout; S-1318 DS Table 6)."""
    f = dict(manf_pn="S-1318D18-A4T2U4", canonical_id=canonical_id("S-1318D18-A4T2U4"),
             name="S-1318D18-A4T2U4", value="1.8V",
             description="LDO 1.8 V 100 mA, 95 nA Iq, HSNT-4 1.0×1.0×0.4",
             note="1.8 V code of the S-1318 family (BMM350 VDD).")
    f.update(overrides)
    return add_s1318d33_a4t2u4(design, ref, **f)


def add_s1318a18_a4t2u4(design, ref: str, **overrides) -> Chip:
    """ABLIC S-1318A18-A4T2U4 — 1.8 V, A type (S-1318 DS Table 1: discharge
    shunt + ON/OFF constant-current pull-down), same HSNT-4(1010) land and
    pinout as the D type. With ON/OFF tied to VIN it draws 0.1 µA more (DS
    Table 12 note 2) — on the Ready-only 3V3 rail, so not a shelf cost."""
    f = dict(manf_pn="S-1318A18-A4T2U4", canonical_id=canonical_id("S-1318A18-A4T2U4"),
             name="S-1318A18-A4T2U4", value="1.8V",
             description="LDO 1.8 V 100 mA, 95 nA Iq, HSNT-4 1.0×1.0×0.4",
             note="1.8 V A-type code of the S-1318 family (BMM350 VDD); sourcing round 25: Mouser + Digi-Key, Japan.")
    f.update(overrides)
    return add_s1318d33_a4t2u4(design, ref, **f)


# ── dev board: round 20 (2026-11-22) ─────────────────────────────────────────
def add_wurth_61304021121(design, ref: str, **overrides) -> Chip:
    """Würth WR-PHD 61304021121 — 2 × 20 pin header, 2.54 mm, THT, 8.69 mm
    (round 20: all 3 suppliers, Taiwan). Engineer breakout on the dev board."""
    return _sam(design, ref, pn="61304021121", part_dir="61304021121",
                mod="HDRV40W64P254X254_2X20_5080X508X869P.kicad_mod", package="2x20 2.54 mm THT",
                height_mm=8.69, size_mm=(50.8, 5.08), manf="Würth Elektronik",
                description="Pin header 2×20, 2.54 mm, THT", note=f"Dev breakout — {_WHY}.", **overrides)


def add_wurth_691137710002(design, ref: str, **overrides) -> Chip:
    """Würth WR-TBL 691137710002 — 2-pole PCB terminal block, 5.0 mm, THT
    (round 20: all 3 suppliers, Italy). Bench supply input."""
    pins = [Pin(num="1", name="1", type="passive"), Pin(num="2", name="2", type="passive")]
    return _sam(design, ref, pn="691137710002", part_dir="691137710002",
                mod="SHDR2W70P0X500_1X2_1000X750X1150P.kicad_mod", package="Terminal block 2P 5.0 mm",
                height_mm=11.5, size_mm=(10.0, 7.5), manf="Würth Elektronik", pins=pins,
                description="PCB terminal block 2-pole 5.0 mm", note=f"Bench input — {_WHY}.", **overrides)


def add_pac1941t_1e_4mx(design, ref: str, **overrides) -> Chip:
    """Microchip PAC1941T-1E/4MX — 1-channel power monitor with accumulator,
    0-9 V bus, ±100 mV sense FSR, I²C; 16-VQFN 3 × 3 (round 20: Mouser 2,346 +
    Digi-Key 763, Thailand). Pins (DS Table 3-1): 1 SLOW/ALERT1, 2 VDD, 3 GND,
    4 SCL, 5 SDA, 6 ADDRSEL, 11 SENSE1+, 12 SENSE1−, 15 GPIO/ALERT2, 16 PWRDN,
    17 EP (not connected). PAC1941-1: pins 7-10, 13, 14 must be grounded."""
    pins = [Pin(num="1", name="SLOW/ALERT1", type="io"), Pin(num="2", name="VDD", type="power"),
            Pin(num="3", name="GND", type="power"), Pin(num="4", name="SCL", type="input"),
            Pin(num="5", name="SDA", type="io"), Pin(num="6", name="ADDRSEL", type="input"),
            Pin(num="7", name="SENSE3-", type="input"), Pin(num="8", name="SENSE3+", type="input"),
            Pin(num="9", name="SENSE4-", type="input"), Pin(num="10", name="SENSE4+", type="input"),
            Pin(num="11", name="SENSE1+", type="input"), Pin(num="12", name="SENSE1-", type="input"),
            Pin(num="13", name="SENSE2+", type="input"), Pin(num="14", name="SENSE2-", type="input"),
            Pin(num="15", name="GPIO/ALERT2", type="io"), Pin(num="16", name="PWRDN", type="input"),
            Pin(num="17", name="EP", type="passive")]
    return _sam(design, ref, pn="PAC1941T-1E/4MX", part_dir="PAC1941T-1E_4MX",
                mod="QFN50P300X300X90-17N-D.kicad_mod", package="VQFN-16 3x3", height_mm=0.9,
                size_mm=(3.0, 3.0), manf="Microchip", pins=pins,
                description="Power monitor 1-ch, 9 V FSR, accumulator, I²C, VQFN-16",
                note=f"Replaces INA228 on the bench shunt — {_WHY}.", **overrides)


# ── 2026-11-23 battery-sim regulator swaps (sourcing round 21) ──────────────
_WHY_R21 = ("battery sim on the fixed 3P pack, sourcing round 21 "
            "(availability/decisions.csv)")


def add_ltc3124edhc_trpbf(design, ref: str, **overrides) -> Chip:
    """Analog Devices LTC3124EDHC#TRPBF — 2-phase synchronous boost, VIN 1.8 V
    start / 0.5 V after start-up, VOUT 2.5-15 V, 2.5 A min (3.5 typ) peak
    switch current PER PHASE, true output disconnect when SD is low (DS 3124f).
    DFN-16 5 × 3 × 0.75 mm + EP. Pins (DS Pin Functions): 1 SWB, 2 PGNDB,
    3 SWA, 4 PGNDA, 5 VIN, 6 PWM/SYNC, 7 VCC, 8 RT, 9 VC, 10 FB, 11 SD,
    12 SGND, 13 VOUTA, 14 NC (DS: tie to VOUT for copper), 15 VOUTB, 16 CAP,
    17 EP = PGND. SnapMagic land (no paste on the EP — add windows at layout);
    the SnapMagic symbol omits pin 14, so pins are listed here from the DS."""
    names = {1: "SWB", 2: "PGNDB", 3: "SWA", 4: "PGNDA", 5: "VIN", 6: "PWM/SYNC",
             7: "VCC", 8: "RT", 9: "VC", 10: "FB", 11: "SD", 12: "SGND", 13: "VOUTA",
             14: "NC", 15: "VOUTB", 16: "CAP", 17: "PGND"}
    kinds = {"VIN": "power", "VOUTA": "power", "VOUTB": "power", "VCC": "power",
             # grounds typed "power" like the other regulator factories (the
             # power_board GND rides the FLEX_GND net)
             "PGNDA": "power", "PGNDB": "power", "PGND": "power", "SGND": "power",
             "SWA": "output", "SWB": "output", "NC": "passive"}
    pins = [Pin(num=str(n), name=nm, aliases=(["EP"] if n == 17 else []),
                type=kinds.get(nm, "input")) for n, nm in names.items()]
    c = _sam(design, ref, pn="LTC3124EDHC#TRPBF", part_dir="LTC3124EDHC_TRPBF",
             mod="SON50P300X500X80-17N.kicad_mod", package="DFN-16 (5×3) DHC", height_mm=0.8,
             size_mm=(3.0, 5.0), manf="Analog Devices", pins=pins, ring_courtyard=True,
             description="2-phase sync boost 1.8-5.5 V in, 2.5-15 V out, 2 × 2.5 A, output disconnect, DFN-16",
             datasheet=datasheet_ref("LTC3124EDHC_TRPBF", "3124f.pdf"),
             note=f"Replaces TPS61175 on COMP_5V — {_WHY_R21}. SnapMagic land.", **overrides)
    c.footprint.source = "snapmagic"
    # SnapMagic STEP is Y-up and long along X: −90° about X seats it (z 0-0.75),
    # +90° about Z lays the 5 mm side along the pad columns. ⚠ Pin-1 marker
    # orientation (±90° about Z) not verified — check in the 3D viewer.
    c.footprint.model_rotate_deg = (-90.0, 0.0, 90.0)
    return c


def add_tps62822dlcr(design, ref: str, **overrides) -> Chip:
    """TI TPS62822DLCR — 2 A synchronous buck, VIN 2.4-5.5 V (UVLO ~2.2 V
    falling), VFB 0.6 V, 4 µA IQ, ILIM 2.7 A min; VQFN-8 2.0 × 1.5 × 1.0 mm
    (DS SLVSDV6C). Pins: 1 EN, 2 FB, 3 AGND, 4 NC, 5 PGND, 6 SW, 7 VIN, 8 PG.
    App values: L 0.47 µH, COUT 2 × 10 µF, R2 ≤ 120 k, CFF = 12 µs / R2."""
    return _sam(design, ref, pn="TPS62822DLCR", part_dir="TPS62822DLCR",
                mod="SON50P150X200X100-8N.kicad_mod", package="VQFN-8 (2.0×1.5) DLC",
                height_mm=1.0, size_mm=(1.5, 2.0), manf="Texas Instruments",
                description="Sync buck 2.4-5.5 V in, 2 A, 0.6 V FB, VQFN-8 2×1.5",
                datasheet=datasheet_ref("TPS62822DLCR", "tps62822.pdf"),
                note=f"Replaces LMR10510 / XC6220 on the radar rails — {_WHY_R21}.", **overrides)


def add_tps62088yfpr(design, ref: str, **overrides) -> Chip:
    """TI TPS62088YFPR — 3 A synchronous buck, VIN 2.4-5.5 V (UVLO 2.2 V
    falling), VFB 0.6 V (adjustable version), ILIM 3.6 A min, 4 MHz; WCSP-6
    0.8 × 1.2 × 0.5 mm, 0.4 mm pitch. Balls: A1 EN, A2 VIN, B1 PG, B2 SW,
    C1 FB, C2 GND. App values: L 0.24 µH, COUT 2 × 10 µF, R2 100 k + 120 pF
    feed-forward (required on the adjustable version)."""
    return _sam(design, ref, pn="TPS62088YFPR", part_dir="TPS62088YFPR",
                mod="BGA6C40P2X3_80X120X50.kicad_mod", package="DSBGA-6 (0.8×1.2) YFP",
                height_mm=0.5, size_mm=(0.8, 1.2), manf="Texas Instruments", ring_courtyard=True,
                description="Sync buck 2.4-5.5 V in, 3 A, 0.6 V FB, WCSP-6",
                datasheet=datasheet_ref("TPS62088YFPR", "tps62088.pdf"),
                note=f"Replaces LMR10510 on the AWR 1.3 V RF rail (up to 2.0 A) — {_WHY_R21}.",
                **overrides)


# ── camera: AR0234 (EOL) → ST VB1943 (2026-11-23, user: height + rail OK) ───
def add_vb1943cajx_1(design, ref: str, **overrides) -> Chip:
    """ST VB1943CAJX/1 — 5.1 MP (2560 × 1984) RGB-NIR global + rolling shutter
    sensor, 2.25 µm 3D-stacked BSI, 1/2.5", MIPI CSI-2 dual/quad lane (lane
    order + polarity remappable), I²C ≤ 1 MHz at 0x20 (8-bit, = 0x10 7-bit).
    OBGA 10 × 9 at 0.8 mm (74 balls, centre depopulated), 8.9 × 10.3 × 2.2 mm
    (DS14880 Rev 3). Supplies: VANA 2.8 V (2.70-2.90), VCORE 1.15 V
    (1.05-1.26), VDDIO 1.8 V (1.70-1.90), any order; RESETN ≥ 100 µs after.
    EXTCLK 12-50 MHz, sub-range on CLK_RANGE0/1 (DS Table 10).
    SamacSys BGA74C80P9X10_890X1030X220 land + symbol (pins by ball ID)."""
    from smash.parts.devboard import _sym
    from smash.parts._artifacts import build_pins, type_pins_by_base
    # Ball types: DS14880 Rev 3 Table 5. GPIO0-3 have internal pull-downs
    # (Table 11) and NCG may float or go to AGND, so both are "reserved"
    # (connect or float); NC must float. pinspec.json is the cross-check.
    t = {"VANA": "power", "VCORE": "power", "VDDIO": "power",
         "AGND": "ground", "DGND": "ground",
         "LDO2V4": "analog", "VRT": "analog", "CPNEG_IN": "analog",
         "CPNEG_OUT": "analog", "CPPOS_IN": "analog", "CPPOS_OUT": "analog",
         "CLKP": "output", "CLKN": "output",
         "RESETN": "input", "SCL": "input", "SDA": "io", "EXTCLK": "input",
         "CLK_RANGE0": "input", "CLK_RANGE1": "input", "PORTEST": "input",
         "NC": "nc", "NCG": "reserved"}
    t.update({f"GPIO{i}": "reserved" for i in range(4)})
    t.update({f"DATA{i}{s}": "output" for i in range(1, 5) for s in "PN"})
    pins = type_pins_by_base(build_pins(_sym("VB1943CAJX_1")), t)
    c = _sam(design, ref, pn="VB1943CAJX/1", part_dir="VB1943CAJX_1", pins=pins,
             mod="BGA74C80P9X10_890X1030X220.kicad_mod", package="OBGA-74 (8.9×10.3, 0.8 mm)",
             height_mm=2.2, size_mm=(8.9, 10.3), manf="STMicroelectronics",
             description="Image sensor 5.1 MP RGB-NIR GS/RS, MIPI CSI-2 2/4-lane, OBGA-74",
             datasheet=datasheet_ref("VB1943CAJX_1", "DS_vd1943.pdf"),
             note="Replaces AR0234CSSM00SUKA0-CP (EOL) — user 2026-11-23 accepted +0.75 mm "
                  "and the 1.15 V core rail. SamacSys land/symbol/STEP.", **overrides)
    # SamacSys STEP is Y-up (x ±4.45, y 0-1.44, z ±5.15): seat it like the
    # LTC3124's. ⚠ The STEP body is 1.44 mm vs the DS 2.2 mm max — the stack
    # uses height_mm (2.2). Pin-1 corner not verified in the 3D viewer.
    c.footprint.model_rotate_deg = (-90.0, 0.0, 0.0)
    return c


# ── piezo comparator: TLV7031 (one 480 pcs non-China lot) → MAX9064 (R23) ─────
def add_max9064ebs_tg45(design, ref: str, **overrides) -> Chip:
    """ADI (Maxim) MAX9064EBS+TG45 — ultra-low-power single comparator with an
    INTERNAL 0.2 V threshold (one input), push-pull output, ~0.4 µA, 1.0-5.5 V.
    UCSP-4 2 × 2 bumps at 0.5 mm, 1.0 × 1.0 × 0.69 mm max (SamacSys
    BGA4C50P2X2_100X100X69). Bumps (SamacSys symbol): A1 OUT, A2 IN, B1 VCC,
    B2 GND, matching the datasheet's "TOP VIEW (BUMPS ON BOTTOM)" (19-4105 Rev 11 p.1)
    and pin table (p.7): noninverting input, push-pull output. Sourcing round 23
    (2026-11-23): Farnell 5,300 + Digi-Key 9,626 Taiwan, Mouser 211 US."""
    pins = [Pin(num="A1", name="OUT", type="output"),
            Pin(num="A2", name="IN", aliases=["IN+"], type="input"),
            Pin(num="B1", name="VCC", aliases=["V+"], type="power"),
            Pin(num="B2", name="GND", aliases=["V-"], type="power")]
    return _sam(design, ref, pn="MAX9064EBS+TG45", part_dir="MAX9064EBS_TG45",
                mod="BGA4C50P2X2_100X100X69.kicad_mod", package="UCSP-4 (1.0×1.0, 0.5 mm)",
                height_mm=0.69, size_mm=(1.0, 1.0), manf="Analog Devices", pins=pins,
                ring_courtyard=True,
                description="Comparator, internal 0.2 V threshold, push-pull, ~0.4 µA, UCSP-4",
                note="Replaces TLV7031DPWR (only non-China stock was one 480 pcs lot) — "
                     "sourcing round 23 (2026-11-23). SamacSys land/symbol/STEP.", **overrides)


def add_pns40010aerx(design, ref: str, **overrides) -> Chip:
    """Nexperia PNS40010AERX (AEC-Q101) — 400 V / 1 A low-leakage planar silicon
    rectifier, SOD123W (SamacSys SODFL3517X110N: 3.5 × 1.7 × 1.1 mm). Pin 1 =
    K (cathode, band), pin 2 = A. Used as the aft-end external-power diode
    (EXT_VIN → BAT_PROT): silicon, not Schottky — in storage the cells hold
    BAT_PROT up and the interlock / wake dividers give EXT_VIN a path to
    ground, so a Schottky's µA reverse leakage would drain the cells; a
    planar silicon junction leaks nA at 3-4 V. Its ~0.7 V drop is irrelevant
    (the fixture sets its own supply voltage)."""
    pins = [Pin(num="1", name="K", aliases=["CATHODE"], type="passive"),
            Pin(num="2", name="A", aliases=["ANODE"], type="passive")]
    return _sam(design, ref, pn="PNS40010AERX", part_dir="PNS40010AERX",
                mod="SODFL3517X110N.kicad_mod", package="SOD123W",
                height_mm=1.1, size_mm=(3.5, 1.7), manf="Nexperia", pins=pins,
                description="Rectifier 400 V 1 A, low leakage, planar silicon, SOD123W",
                note="Aft-end external power diode (2026-11-23, user; PNS40010ER,115 is obsolete). "
                     "SamacSys land/symbol/STEP.",
                **overrides)


def add_mcp4725a0t_e_ch(design, ref: str, **overrides) -> Chip:
    """Microchip MCP4725A0T-E/CH — 12-bit I²C DAC with EEPROM, SOT-23-6,
    VDD (2.7–5.5 V) is the reference, rail-to-rail output. I²C address
    1100·A2·A1·A0 with A2A1 = 00 (the "A0" part) → 0x60 with A0 = GND.
    Power-up loads the EEPROM; factory default = mid-scale (0.5 × VDD)
    (DS22039D Table 5-3). Pins: 1 VOUT, 2 VSS, 3 VDD, 4 SDA, 5 SCL, 6 A0.
    Footprint: KiCad library SOT-23-6; symbol: KiCad Analog_DAC MCP4725."""
    from smash.parts.devboard import _sam
    return _sam(design, ref, pn="MCP4725A0T-E/CH", part_dir="MCP4725A0T-E_CH",
                mod="SOT-23-6.kicad_mod", package="SOT-23-6", height_mm=1.45,
                size_mm=(2.9, 2.8), manf="Microchip",
                description="12-bit DAC with EEPROM, I2C, SOT-23-6",
                note="KiCad library SOT-23-6 land + Microchip DS22039D.", **overrides)
