"""Sensor IC factories — temperature, magnetometer, IMU, accelerometer.

Every value transcribed from per-part ground-truth in
`parts/sources/<PN>/`.
"""

from __future__ import annotations

from smash.state import Chip, Pin, Pad, Footprint


# ═════════════════════════════════════════════════════════════════════════
# Texas Instruments TMP117MAIDRVR — ±0.1 °C precision I²C temp sensor,
# WSON-6 (DRV package) with thermal pad
# ═════════════════════════════════════════════════════════════════════════

_TMP117_NOTE = """\
Datasheet extras (TI TMP117, SBOS755D, rev Sep 2022). Single-channel
I²C precision thermometer with EEPROM, ±0.1 °C accuracy across the
-20 to +50 °C medical band, ±0.3 °C max across -55 to +150 °C.

Variants:
  TMP117M-AIDRVR : medical-grade, WSON-6 (DRV) — this factory
  TMP117 (YBG)   : DSBGA package — separate factory if needed

Absolute Max Ratings (p5 §6.1):
  V+ supply        : -0.3 to 6 V
  V on SCL/SDA/ALERT/ADD0 : -0.3 to 6 V
  T_J operating    : -55 to +155 °C
  T_STG            : -65 to +155 °C

ESD (p5 §6.2): HBM ±2000 V (ANSI/ESDA/JEDEC JS-001),
               CDM ±1000 V (JEDEC JESD22-C101).

Recommended Operating (p5 §6.3):
  V+ supply : 1.8 V to 5.5 V (T_A=-55..+150 °C)
              1.7 V to 5.5 V (T_A=-55..+70 °C only)
  V on SCL/SDA/ALERT/ADD0 : 0 V to 5.5 V
  T_A operating : -55 to +150 °C

Pin map (datasheet p4 §5, DRV package + pinmap.txt):
  1 = SCL
  2 = GND
  3 = ALERT
  4 = ADD0   (I²C address select pin)
  5 = V+     (datasheet calls this "V+")
  6 = SDA
  7 = EP     (thermal pad — connect to GND)

I²C address: 7-bit, selectable via ADD0 tied to GND/V+/SDA/SCL → 0x48
to 0x4B.

Mechanical (NOT stated in datasheet headline): body_material,
lead_material, weight_g, density_g_cm3, cte_ppm_k, fab_country.

Distributor (from SamacSys metadata): see Mouser/TI listings.
"""


def _tmp117_wson6_footprint() -> Footprint:
    """WSON-6 (DRV package) per SamacSys SON65P200X200X80-7N.kicad_mod.
    Body 2×2 mm, height 0.8 mm, 0.65 mm pitch. Pad 7 = thermal pad."""
    return Footprint(
        name="SON65P200X200X80-7N",
        package_class="WSON-6",
        pads=[
            Pad(num="1", position_mm=(-1.05, 0.65), size_mm=(0.6, 0.35), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.05, 0.0),   size_mm=(0.6, 0.35), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-1.05, -0.65), size_mm=(0.6, 0.35), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(1.05, -0.65), size_mm=(0.6, 0.35), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(1.05, 0.0),   size_mm=(0.6, 0.35), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=(1.05, 0.65), size_mm=(0.6, 0.35), shape="rect", layer="F.Cu"),
            Pad(num="7", position_mm=(0.0, 0.0),   size_mm=(1.1, 1.7),  shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-1, -1), (1, -1), (1, 1), (-1, 1)],
        courtyard=[(-1.6, -1.3), (1.6, -1.3), (1.6, 1.3), (-1.6, 1.3)],
        pitch_mm=0.65,
        size_mm=(2.0, 2.0),
        height_mm=0.8,
        model_3d_path="application/src/smash/parts/sources/TMP117MAIDRVR/TMP117MAIDRVR.stp",
        source="samacsys",
        note="Pad 7 = exposed thermal pad. Must be soldered to GND.",
    )


def add_tmp117maidrvr(design, ref: str, **overrides) -> Chip:
    """TI TMP117MAIDRVR — ±0.1 °C precision I²C temp sensor with
    EEPROM, WSON-6 (DRV) package."""
    fields = dict(
        manf="Texas Instruments",
        manf_pn="TMP117MAIDRVR",
        canonical_id="tmp117maidrvr",
        name="TMP117MAIDRVR",
        value="TMP117MAIDRVR",
        description=(
            "I2C precision temp sensor, ±0.1 °C medical-grade "
            "accuracy, 16-bit, EEPROM, WSON-6"
        ),
        datasheet="application/src/smash/parts/sources/TMP117MAIDRVR/TMP117MAIDRVR.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[
            "ESD HBM ±2000 V (ANSI/ESDA/JEDEC JS-001)",
            "ESD CDM ±1000 V (JEDEC JESD22-C101)",
        ],
        eccn=None, itar=None,
        package="WSON-6 (DRV)",
        size_mm=(2.0, 2.0),
        height_mm=0.8,
        temp_range_c=(-55, 150),    # T_A operating
        body_material=None, lead_material=None,
        voltage_rating_v=6.0,        # V+ abs max
        vcc_nominal_v=3.3,           # typical, datasheet supports 1.8-5.5
        i_rms_a=None,
        power_rating_w=None,
        # ── thermal (TI TMP117 SBOS755D Sep 2022, §6.4 + §6.5) ───────
        # NB: components.md row used RθJC = 1.0 (the YBG DSBGA value);
        # the DRV (WSON-6) package values from the same DS table are
        # ΘJC(top) = 82.3, ΘJC(bot) = 11.7. We use the BOTTOM value
        # since WSON heat-sinks through its bottom exposed pad to the
        # PCB. Iq = 16 µA typ × 3.3V = ~53 µW; peak only on 8-avg
        # conversion bursts, still sub-mW.
        p_active_w=0.000053,                # 16 µA × 3.3V — duty 1 Hz, 8 avg (DS §6.5 p10)
        p_max_w=0.000073,                   # 22 µA × 3.3V — max Iq (DS §6.5 p10)
        rth_jc_cw=11.7,                     # DRV (WSON-6) RθJC(bot), DS §6.4 p5
        tj_max_c=155.0,                     # operating Tj max, DS §6.1 Abs Max p4
        pins=[
            # Per TI SNOSD82D Table 5-1 (Sept 2022): SCL=I, SDA=I/O.
            # TMP117 doesn't support clock-stretching, so SCL is
            # strictly listen-only.
            Pin(num="1", name="SCL",   type="input"),
            Pin(num="2", name="GND",   type="ground"),
            Pin(num="3", name="ALERT", type="output",
                note="open-drain — requires external pull-up"),
            Pin(num="4", name="ADD0",  type="input",
                note="I²C address select (tie to GND/V+/SDA/SCL)"),
            Pin(num="5", name="V+",    aliases=["VDD", "VCC", "VP"], type="power"),
            Pin(num="6", name="SDA",   type="io"),
            Pin(num="7", name="EP",    aliases=["ExposedPad"], type="ground"),
        ],
        footprint=_tmp117_wson6_footprint(),
        note=_TMP117_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# STMicroelectronics IIS2MDCTR — 3-axis high-accuracy ultra-low-power
# magnetometer, ±50 gauss, I²C + SPI, LGA-12
# ═════════════════════════════════════════════════════════════════════════

_IIS2MDC_NOTE = """\
Datasheet extras (ST IIS2MDC, DocID030986 Rev 1). 3-axis digital
magnetic sensor, ±50 gauss dynamic range, 16-bit output, I²C + SPI.

Absolute Max Ratings (p14 Table 9):
  Vdd supply        : -0.3 to 4.8 V
  Vdd_IO            : -0.3 to 4.8 V
  V on control pins (CS, SCL/SPC, SDA/SDI/SDO) : -0.3 to Vdd_IO + 0.3 V
  MEF maximum exposed magnetic field : 10000 gauss
  T_OP operating : -40 to +85 °C
  T_STG storage  : -40 to +125 °C
  ESD HBM : 2 kV
  >>> "Supply voltage on any pin should never exceed 4.8 V."

Power modes (p16-17 §4.1):
  High-resolution and low-power modes
  RMS noise / current consumption per Table 10/11

Interfaces (p1):
  I²C : standard / fast / fast-plus / high-speed
        (100 / 400 / 1000 / 3400 kHz)
  SPI : standard 3-wire / 4-wire

Pin map (per pinmap.txt + datasheet p7 §1.2, LGA-12 perimeter):
  1  = SCL_SPC      (I²C clock or SPI clock)
  2  = NC_1         (no connect)
  3  = CS           (SPI chip select; tie HIGH for I²C mode)
  4  = SDA_SDI_SDO  (data — I²C SDA or SPI MOSI/MISO)
  5  = C1           (external tuning/decoupling capacitor pin)
  6  = GND_1
  7  = INT_DRDY     (interrupt / data-ready output)
  8  = GND_2
  9  = VDD          (analog supply)
  10 = VDD_IO       (I/O supply)
  11 = NC_2
  12 = NC_3

NOTE pin name divergence: the datasheet pin table uses Vdd, Vdd_IO,
INT/DRDY, etc.  SamacSys-generated symbol uses VDD, VDD_IO, INT_DRDY.
We transcribe the SamacSys names verbatim — those are what KiCad
will see and what the netlist will reference.

Distributor: ST product page www.st.com/iis2mdc
"""


def _iis2mdc_lga12_footprint() -> Footprint:
    """LGA-12 (2x2x1 mm) footprint per SamacSys IIS2MDCTR.kicad_mod.
    Perimeter LGA: 4 pads on left/right, 2 on top/bottom."""
    return Footprint(
        name="IIS2MDCTR",
        package_class="LGA-12",
        pads=[
            # Left column (pins 1-4): x=-0.75
            Pad(num="1", position_mm=(-0.75, 0.75), size_mm=(0.35, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-0.75, 0.25), size_mm=(0.35, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-0.75, -0.25), size_mm=(0.35, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(-0.75, -0.75), size_mm=(0.35, 0.3), shape="rect", layer="F.Cu"),
            # Bottom row (pins 5-6, going right): y=-0.75 (math-y-up)
            Pad(num="5", position_mm=(-0.25, -0.75), size_mm=(0.3, 0.35), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=(0.25, -0.75), size_mm=(0.3, 0.35), shape="rect", layer="F.Cu"),
            # Right column (pins 7-10): x=+0.75, going up
            Pad(num="7", position_mm=(0.75, -0.75), size_mm=(0.35, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="8", position_mm=(0.75, -0.25), size_mm=(0.35, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="9", position_mm=(0.75, 0.25), size_mm=(0.35, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="10", position_mm=(0.75, 0.75), size_mm=(0.35, 0.3), shape="rect", layer="F.Cu"),
            # Top row (pins 11-12, going left): y=+0.75 (math-y-up)
            Pad(num="11", position_mm=(0.25, 0.75), size_mm=(0.3, 0.35), shape="rect", layer="F.Cu"),
            Pad(num="12", position_mm=(-0.25, 0.75), size_mm=(0.3, 0.35), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-1, -1), (1, -1), (1, 1), (-1, 1)],
        courtyard=[(-1.6, -1.6), (1.6, -1.6), (1.6, 1.6), (-1.6, 1.6)],
        pitch_mm=0.5,
        size_mm=(2.0, 2.0),
        height_mm=1.0,
        model_3d_path="application/src/smash/parts/sources/IIS2MDCTR/IIS2MDCTR.stp",
        source="samacsys",
    )


def add_iis2mdctr(design, ref: str, **overrides) -> Chip:
    """ST IIS2MDCTR — 3-axis ultra-low-power magnetometer, ±50 gauss,
    16-bit, I²C + SPI, LGA-12. Industrial -40..+85 °C."""
    fields = dict(
        manf="STMicroelectronics",
        manf_pn="IIS2MDCTR",
        canonical_id="iis2mdctr",
        name="IIS2MDCTR",
        value="IIS2MDCTR",
        description=(
            "3-axis digital magnetometer, ±50 gauss, 16-bit, "
            "I2C/SPI, LGA-12"
        ),
        datasheet="application/src/smash/parts/sources/IIS2MDCTR/IIS2MDCTR.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=["ESD HBM 2 kV"],
        eccn=None, itar=None,
        package="LGA-12",
        size_mm=(2.0, 2.0),
        height_mm=1.0,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=4.8,
        vcc_nominal_v=None,         # caller decides (typ 1.71-3.6 V)
        i_rms_a=None,
        power_rating_w=None,
        # ── thermal (ST IIS2MDC DocID030986 Rev 1, §2.3 Tab 5) ───────
        # Idd_HR = 1.13 mA typ in high-resolution mode (ODR=100 Hz)
        # at Vdd=2.5V → ~2.83 mW. Power-down Idd_PD = 1.5 µA × 2.5V
        # = ~4 µW. ST sensor DSes don't quote ΘJC or Tj separately;
        # only T_OP = -40 to +85 °C is given.
        p_active_w=0.0028,                  # 1.13 mA × 2.5V — Idd_HR high-res mode (DS Tab 5)
        p_max_w=0.0028,                     # same — no max Idd quoted (only typ)
        rth_jc_cw=None,                     # not quoted in DS (LGA-12 no thermal pad)
        tj_max_c=85.0,                      # T_OP max; DS only spec's T_OP, not Tj separately
        pins=[
            Pin(num="1",  name="SCL_SPC",     aliases=["SCL", "SPC"], type="io"),
            Pin(num="2",  name="NC_1",                                 type="nc"),
            Pin(num="3",  name="CS",                                   type="input"),
            Pin(num="4",  name="SDA_SDI_SDO", aliases=["SDA"],         type="io"),
            Pin(num="5",  name="C1",                                   type="io",
                note="external decoupling capacitor pin (see datasheet)"),
            Pin(num="6",  name="GND_1",                                type="ground"),
            Pin(num="7",  name="INT_DRDY",                             type="output"),
            Pin(num="8",  name="GND_2",                                type="ground"),
            Pin(num="9",  name="VDD",                                  type="power"),
            Pin(num="10", name="VDD_IO",                               type="power"),
            Pin(num="11", name="NC_2",                                 type="nc"),
            Pin(num="12", name="NC_3",                                 type="nc"),
        ],
        footprint=_iis2mdc_lga12_footprint(),
        note=_IIS2MDC_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# STMicroelectronics ISM330DHCXTR — 6-axis IMU (3-axis accel + 3-axis
# gyro), ML core, LGA-14 (2.5×3×0.86 mm)
# ═════════════════════════════════════════════════════════════════════════

_ISM330DHCX_NOTE = """\
Datasheet extras (ST ISM330DHCX). High-accuracy industrial-grade
6-axis IMU "iNEMO inertial module with embedded Machine Learning
Core" (ST's own marketing term, datasheet p1 first bullet) and
"Programmable Finite State Machine to process data from accelerometer"
(p1). Up to 16 finite state machines can be programmed independently
(datasheet §2.1). See ST AN5392 (Machine Learning Core) and AN5388
(Finite State Machine) for programming details.

Absolute Max / Recommended Operating (extracted from datasheet
electrical characteristics table):
  Vdd supply : 1.71 V (min) / 1.8 V (typ) / 3.6 V (max)
  Vdd_IO     : 1.62 V (min) / 3.6 V (max)
  T_OP operating : -40 to +105 °C  (industrial-grade)
  V_IH digital high-level input  : 0.7 × Vdd_IO
  V_IL digital low-level input   : 0.3 × Vdd_IO

Current consumption (typ, normal-mode operation):
  IddHP combined accel + gyro high-performance : 1.2 mA typ / 1.5 mA max
  IddNM combined normal mode (ODR=208 Hz)       : 0.7 mA typ
  LA_IddHP accel only high-perf                 : 360 µA typ / 430 µA max
  LA_IddLM accel low-power ODR=52 Hz            : 32 µA typ
                                  ODR=12.5 Hz   : 11 µA typ
                                  ODR=1.6 Hz    : 5.5 µA typ
  IddPD power-down                              : 3 µA typ
  Ton turn-on time                              : 35 ms typ

Pin map (datasheet + pinmap.txt, LGA-14):
  1  = SDO_SA0  (SPI MISO 4-wire / I²C address LSB)
  2  = SDX      (aux SPI sensor MOSI/SDA)
  3  = SCX      (aux SPI sensor SCK/SCL)
  4  = INT1     (interrupt 1)
  5  = VDDIO    (I/O supply)
  6  = GND_1
  7  = GND_2
  8  = VDD      (analog supply)
  9  = INT2     (interrupt 2)
  10 = OCS_AUX  (aux interface chip-select)
  11 = SDO_AUX  (aux interface data out)
  12 = CS       (main interface chip-select; HIGH = I²C, LOW = SPI)
  13 = SCL      (main I²C clock / SPI SCK)
  14 = SDA      (main I²C data / SPI MOSI)

Application caveat: this part shares its KiCad footprint with the
LSM6DS3US (same LGA-14 family). The footprint file in
parts/sources/ISM330DHCXTR/ is named `LSM6DS3USTR.kicad_mod` —
that's the SamacSys-supplied filename, NOT a transcription error.

Distributor: ST product page www.st.com/ism330dhcx
"""


def _ism330dhcx_lga14_footprint() -> Footprint:
    """LGA-14 (2.5x3x0.86 mm) footprint per SamacSys
    LSM6DS3USTR.kicad_mod. Shared between ISM330DHCX and LSM6 IMUs.
    """
    return Footprint(
        name="LSM6DS3USTR (LGA-14)",
        package_class="LGA-14",
        pads=[
            # Left column (pins 1-4): x=-1.163
            Pad(num="1", position_mm=(-1.163, -0.75), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.163, -0.25), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-1.163,  0.25), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(-1.163,  0.75), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            # Bottom row (pins 5-7): y=+0.912
            Pad(num="5", position_mm=(-0.5,  0.912), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="6", position_mm=( 0.0,  0.912), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="7", position_mm=( 0.5,  0.912), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            # Right column (pins 8-11): x=+1.163
            Pad(num="8",  position_mm=( 1.163,  0.75), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="9",  position_mm=( 1.163,  0.25), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="10", position_mm=( 1.163, -0.25), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="11", position_mm=( 1.163, -0.75), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            # Top row (pins 12-14): y=-0.912
            Pad(num="12", position_mm=( 0.5, -0.912), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="13", position_mm=( 0.0, -0.912), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
            Pad(num="14", position_mm=(-0.5, -0.912), size_mm=(0.25, 0.475), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-1.5, -1.25), (1.5, -1.25), (1.5, 1.25), (-1.5, 1.25)],
        courtyard=[(-2.918, -2.25), (2.5, -2.25), (2.5, 2.25), (-2.918, 2.25)],
        pitch_mm=0.5,
        size_mm=(2.5, 3.0),
        height_mm=0.86,
        model_3d_path="application/src/smash/parts/sources/ISM330DHCXTR/ISM330DHCXTR.stp",
        source="samacsys",
        note=(
            "LGA-14 footprint shared with the LSM6 family — SamacSys "
            "supplied as `LSM6DS3USTR.kicad_mod`."
        ),
    )


def add_ism330dhcxtr(design, ref: str, **overrides) -> Chip:
    """ST ISM330DHCXTR — 6-axis IMU with ML core + FSM, LGA-14.
    Industrial -40..+105 °C."""
    fields = dict(
        manf="STMicroelectronics",
        manf_pn="ISM330DHCXTR",
        canonical_id="ism330dhcxtr",
        name="ISM330DHCXTR",
        value="ISM330DHCXTR",
        description=(
            "6-axis IMU (3-axis accel + 3-axis gyro), embedded ML core "
            "+ FSM, LGA-14, industrial -40..+105 °C"
        ),
        datasheet="application/src/smash/parts/sources/ISM330DHCXTR/ISM330DHCXTR.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=[],   # not explicitly tagged on the datasheet front page
        eccn=None, itar=None,
        package="LGA-14 (2.5×3×0.86 mm)",
        size_mm=(2.5, 3.0),
        height_mm=0.86,
        temp_range_c=(-40, 105),    # industrial T_OP
        body_material=None, lead_material=None,
        voltage_rating_v=3.6,        # Vdd max
        vcc_nominal_v=1.8,           # Vdd typ
        i_rms_a=0.0015,              # IddHP max 1.5 mA
        power_rating_w=None,
        # ── thermal (ST ISM330DHCX DS, §5.3 Electrical Characteristics) ─
        # IddHP combined accel+gyro high-performance: 1.2 mA typ /
        # 1.5 mA max at Vdd=1.8V → 2.16 mW typ / 2.7 mW max. ST sensor
        # DSes don't quote ΘJC or Tj — only T_OP -40 to +105 °C.
        p_active_w=0.00216,                 # 1.2 mA × 1.8V — IddHP combined typ (DS Tab 8)
        p_max_w=0.0027,                     # 1.5 mA × 1.8V — IddHP combined max (DS Tab 8)
        rth_jc_cw=None,                     # not quoted (LGA-14 no thermal pad)
        tj_max_c=105.0,                     # T_OP max (industrial); DS only spec's T_OP, not Tj separately
        pins=[
            # Per pinmap.txt — matches SamacSys symbol
            Pin(num="1",  name="SDO_SA0",  aliases=["SDO", "SA0"], type="io",
                note="SPI MISO 4-wire / I²C address LSB"),
            Pin(num="2",  name="SDX",                              type="io"),
            Pin(num="3",  name="SCX",                              type="io"),
            Pin(num="4",  name="INT1",                             type="output"),
            Pin(num="5",  name="VDDIO",                            type="power"),
            Pin(num="6",  name="GND_1",                            type="ground"),
            Pin(num="7",  name="GND_2",                            type="ground"),
            Pin(num="8",  name="VDD",                              type="power"),
            Pin(num="9",  name="INT2",                             type="output"),
            Pin(num="10", name="OCS_AUX",                          type="input"),
            Pin(num="11", name="SDO_AUX",                          type="io"),
            Pin(num="12", name="CS",                               type="input",
                note="HIGH = I²C mode, LOW = SPI mode"),
            Pin(num="13", name="SCL",      aliases=["SPC"],        type="io"),
            Pin(num="14", name="SDA",      aliases=["SDI", "SDO"], type="io"),
        ],
        footprint=_ism330dhcx_lga14_footprint(),
        note=_ISM330DHCX_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


# ═════════════════════════════════════════════════════════════════════════
# STMicroelectronics H3LIS331DLTR — 3-axis ±100/±200/±400 g
# high-shock-survivability accelerometer, LGA-16
# ═════════════════════════════════════════════════════════════════════════

_H3LIS331DL_NOTE = """\
Datasheet extras (ST H3LIS331DL). 3-axis ±100/±200/±400 g
accelerometer with 10000 g high-shock survivability — picked for
impact-detection / launch-event sensing.

Product summary (datasheet p1):
  Supply voltage         : 2.16 V to 3.6 V
  Low-voltage IO         : compatible with 1.8 V
  Shock survivability    : 10000 g
  ECOPACK / RoHS compliant
  Operating temp range   : -40 to +85 °C
  Package                : TFLGA-16L, 3 × 3 × 1.0 mm³
  Packing                : Tape and reel
  Order code             : H3LIS331DLTR

Pin map (datasheet p7 §1 + pinmap.txt):
  1  = Vdd_IO  (power supply for I/O pins)
  2  = NC_1    (not connected)
  3  = NC_2
  4  = SCL_SPC (I²C clock or SPI clock)
  5  = GND_1
  6  = SDA_SDI_SDO (I²C data / SPI MOSI / 3-wire data)
  7  = SDO_SA0     (SPI MISO / I²C address LSB)
  8  = CS          (enable SPI; HIGH=I²C, LOW=SPI)
  9  = INT2        (inertial interrupt 2)
  10 = RESERVED_1  (connect to GND)
  11 = INT1        (inertial interrupt 1)
  12 = GND_2
  13 = GND_3
  14 = VDD         (analog supply)
  15 = RESERVED_2  (connect to GND)
  16 = GND_4

>>> RESERVED pins (10, 15) must be tied to GND.

Applications (datasheet p1): car crash detection, shock detection,
impact recognition, concussion detection, asset tracking, augmented
sports equipment.

Footprint note: SamacSys shares the LGA-16 footprint with the LIS3DH
family — supplied as `LIS3DHTR.kicad_mod`.

Distributor: ST product page www.st.com/h3lis331dl
"""


def _h3lis331dl_lga16_footprint() -> Footprint:
    """LGA-16 (3x3x1 mm) footprint per SamacSys LIS3DHTR.kicad_mod.
    Shared with LIS3DH 3-axis accelerometer family.

    Pad rotation is baked into the sizes. In the source mod the two SIDE
    columns carry `(at x y 90)` while the top/bottom rows are at 0, so the
    mod's `(size 0.3 0.6)` renders 0.6 wide x 0.3 tall on the columns and
    0.3 x 0.6 on the rows. Transcribing 0.3 x 0.6 for all sixteen made the
    column pads 0.6 mm tall on a 0.5 mm pitch — adjacent pads overlapping
    by 0.1 mm, i.e. a guaranteed short. Found independently on the routed
    Finalized/activation_interface board, whose EE had to correct it by
    hand before DRC would pass."""
    return Footprint(
        name="LIS3DHTR (LGA-16)",
        package_class="TFLGA-16L",
        pads=[
            # Left column (pins 1-5): x=-1.2, y from -1 to +1 in steps of 0.5
            Pad(num="1", position_mm=(-1.2, -1.0), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="2", position_mm=(-1.2, -0.5), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="3", position_mm=(-1.2,  0.0), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="4", position_mm=(-1.2,  0.5), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="5", position_mm=(-1.2,  1.0), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            # Bottom row (pins 6-8): y=+1.2
            Pad(num="6", position_mm=(-0.5,  1.2), size_mm=(0.3, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="7", position_mm=( 0.0,  1.2), size_mm=(0.3, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="8", position_mm=( 0.5,  1.2), size_mm=(0.3, 0.6), shape="rect", layer="F.Cu"),
            # Right column (pins 9-13): x=+1.2
            Pad(num="9",  position_mm=( 1.2,  1.0), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="10", position_mm=( 1.2,  0.5), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="11", position_mm=( 1.2,  0.0), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="12", position_mm=( 1.2, -0.5), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            Pad(num="13", position_mm=( 1.2, -1.0), size_mm=(0.6, 0.3), shape="rect", layer="F.Cu"),
            # Top row (pins 14-16): y=-1.2
            Pad(num="14", position_mm=( 0.5, -1.2), size_mm=(0.3, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="15", position_mm=( 0.0, -1.2), size_mm=(0.3, 0.6), shape="rect", layer="F.Cu"),
            Pad(num="16", position_mm=(-0.5, -1.2), size_mm=(0.3, 0.6), shape="rect", layer="F.Cu"),
        ],
        body_outline=[(-1.5, -1.5), (1.5, -1.5), (1.5, 1.5), (-1.5, 1.5)],
        courtyard=[(-1.8, -1.8), (1.8, -1.8), (1.8, 1.8), (-1.8, 1.8)],
        pitch_mm=0.5,
        size_mm=(3.0, 3.0),
        height_mm=1.0,
        model_3d_path="application/src/smash/parts/sources/H3LIS331DLTR/H3LIS331DLTR.stp",
        source="samacsys",
        note=(
            "TFLGA-16L footprint shared with the LIS3DH family — "
            "SamacSys supplied as `LIS3DHTR.kicad_mod`."
        ),
    )


def add_h3lis331dltr(design, ref: str, **overrides) -> Chip:
    """ST H3LIS331DLTR — 3-axis ±100/±200/±400 g high-shock
    accelerometer with 10000 g survivability, LGA-16, -40..+85 °C."""
    fields = dict(
        manf="STMicroelectronics",
        manf_pn="H3LIS331DLTR",
        canonical_id="h3lis331dltr",
        name="H3LIS331DLTR",
        value="H3LIS331DLTR",
        description=(
            "3-axis ±100/200/400 g accelerometer, 10000 g shock "
            "survivability, I2C/SPI, LGA-16 (3×3×1.0 mm)"
        ),
        datasheet="application/src/smash/parts/sources/H3LIS331DLTR/H3LIS331DLTR.pdf",
        fab_country=None, currency=None, price_1pc=None, price_20kpc=None, weight_g=None,
        standards=["RoHS", "ECOPACK"],
        eccn=None, itar=None,
        package="TFLGA-16L (3×3×1.0)",
        size_mm=(3.0, 3.0),
        height_mm=1.0,
        temp_range_c=(-40, 85),
        body_material=None, lead_material=None,
        voltage_rating_v=3.6,
        vcc_nominal_v=None,         # 2.16-3.6 V — caller chooses
        i_rms_a=None,
        power_rating_w=None,
        # ── thermal (ST H3LIS331DL DS, §5.3 Electrical Characteristics) ─
        # Idd = 300 µA normal mode @ ODR=400 Hz, 370 µA @ ODR=1000 Hz
        # at Vdd=3V → ~0.9 mW typ / 1.1 mW max. ST sensor DS doesn't
        # quote ΘJC or Tj — only T_OP -40 to +85 °C.
        p_active_w=0.0009,                  # 300 µA × 3V — Idd normal ODR=400 Hz (DS Tab 8)
        p_max_w=0.0011,                     # 370 µA × 3V — Idd normal ODR=1000 Hz (DS Tab 8)
        rth_jc_cw=None,                     # not quoted (LGA-16 no thermal pad)
        tj_max_c=85.0,                      # T_OP max; DS only spec's T_OP, not Tj separately
        pins=[
            # Per pinmap.txt + datasheet p7
            Pin(num="1",  name="VDD_IO",        aliases=["VDDIO"],  type="power"),
            Pin(num="2",  name="NC_1",                              type="nc"),
            Pin(num="3",  name="NC_2",                              type="nc"),
            Pin(num="4",  name="SCL_SPC",       aliases=["SCL"],    type="io"),
            Pin(num="5",  name="GND_1",                             type="ground"),
            Pin(num="6",  name="SDA_SDI_SDO",   aliases=["SDA"],    type="io"),
            Pin(num="7",  name="SDO_SA0",       aliases=["SDO"],    type="io"),
            Pin(num="8",  name="CS",                                type="input"),
            Pin(num="9",  name="INT2",                              type="output"),
            Pin(num="10", name="RESERVED_1",                        type="reserved",
                note="datasheet p7: Connect to GND"),
            Pin(num="11", name="INT1",                              type="output"),
            Pin(num="12", name="GND_2",                             type="ground"),
            Pin(num="13", name="GND_3",                             type="ground"),
            Pin(num="14", name="VDD",                               type="power"),
            Pin(num="15", name="RESERVED_2",                        type="reserved",
                note="datasheet implies: Connect to GND"),
            Pin(num="16", name="GND_4",                             type="ground"),
        ],
        footprint=_h3lis331dl_lga16_footprint(),
        note=_H3LIS331DL_NOTE,
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
