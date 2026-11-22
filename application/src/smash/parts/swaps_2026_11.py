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
                                           "nc" if nm.startswith("NC") else "io"))
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
                pins=pins, ring_courtyard=True, note=f"Replaces TMP117 (China lots) — {_WHY}.", **overrides)


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
