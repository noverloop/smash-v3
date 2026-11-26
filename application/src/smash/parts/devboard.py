"""Development-board parts (2026-11-21, user) — SamacSys libraries vendored
in parts/sources/<PN>/ (pads + symbol + STEP verbatim; tiny parts get their
courtyard re-ringed from the pads like the tower's SamacSys parts).

USB2514B-I/M2: the SamacSys symbol is the 2-port USB2512B pinout (pins 6-9
and 18-21 marked NC), so this factory names the 36 pins from the USB2514B
datasheet by NUMBER (the land pattern is right — same 6 × 6 QFN-36).
"""
from __future__ import annotations

from smash.state import Chip, Footprint, Pin
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def _sym(part_dir: str) -> str:
    """The vendored .kicad_sym (SamacSys sometimes mangles its file name)."""
    import pathlib
    return str(next(pathlib.Path(src(part_dir, "")).glob("*.kicad_sym")))


def _step(part_dir: str) -> str | None:
    """(2026-11-23) The vendored STEP in sources/<part_dir>/: <part_dir>.stp if
    present, else the folder's only .stp/.step (SamacSys often names it after
    the package, e.g. SON50P200X300X100-9N.step). None when the download had
    no 3D model — an absolute path to a missing file leaked into the exports."""
    import pathlib
    d = pathlib.Path(src(part_dir, ""))
    own = d / f"{part_dir}.stp"
    if own.exists():
        return datasheet_ref(part_dir, own.name)
    cands = sorted(p for p in d.iterdir() if p.suffix.lower() in (".stp", ".step")) if d.exists() else []
    return datasheet_ref(part_dir, cands[0].name) if len(cands) == 1 else None


def _sam(design, ref, *, pn, part_dir, mod, package, height_mm, size_mm, description,
         manf, pins=None, ring_courtyard=False, note="", model_rotate=None, **overrides) -> Chip:
    fp_mod = src(part_dir, mod)
    fp = Footprint(
        name=mod.rsplit(".", 1)[0], package_class=package,
        pads=pads_from_kicad_mod(fp_mod),
        body_outline=outline_polygon(fp_mod, "F.Fab"),
        courtyard=[] if ring_courtyard else outline_polygon(fp_mod, "F.CrtYd"),
        size_mm=size_mm, height_mm=height_mm,
        model_3d_path=_step(part_dir),
        # (2026-11-23) Y-up vendor STEPs (BMM350, SON-8) need (−90, 0, 0)
        **({"model_rotate_deg": model_rotate} if model_rotate else {}),
        source="samacsys",
    ).ensure_courtyard_clearance()
    fields = dict(
        manf=manf, manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=description, datasheet=None, package=package,
        size_mm=size_mm, height_mm=height_mm,
        pins=pins if pins is not None else build_pins(_sym(part_dir)),
        footprint=fp, note=note or f"SamacSys LIB_{part_dir} (vendored 2026-11-21).",
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_stm32g474ceu6(design, ref: str, **overrides) -> Chip:
    """ST STM32G474CEU6 — Cortex-M4F 170 MHz, 512 KB flash, UFQFPN-48 7×7,
    crystal-less USB FS (HSI48 + CRS), 3× FDCAN, 5 ADCs. Dev-board probe /
    console / CAN / power-meter MCU; ROM DFU bootloader over USB (BOOT0 = PB8)."""
    return _sam(design, ref, pn="STM32G474CEU6", part_dir="STM32G474CEU6",
                mod="QFN50P700X700X60-49N-D.kicad_mod", package="UFQFPN-48 (7×7)",
                height_mm=0.6, size_mm=(7.0, 7.0), manf="STMicroelectronics",
                description="MCU Cortex-M4F 170 MHz, 512 KB flash, USB FS, 3× FDCAN, UFQFPN-48",
                **overrides)


_USB2514B_PINS = {
    1: "USBDM_DN1", 2: "USBDP_DN1", 3: "USBDM_DN2", 4: "USBDP_DN2", 5: "VDDA33_1",
    6: "USBDM_DN3", 7: "USBDP_DN3", 8: "USBDM_DN4", 9: "USBDP_DN4", 10: "VDDA33_2",
    11: "TEST", 12: "PRTPWR1", 13: "OCS1_N", 14: "CRFILT", 15: "VDD33_1",
    16: "PRTPWR2", 17: "OCS2_N", 18: "PRTPWR3", 19: "OCS3_N", 20: "PRTPWR4",
    21: "OCS4_N", 22: "SDA", 23: "VDD33_2", 24: "SCL", 25: "HS_IND",
    26: "RESET_N", 27: "VBUS_DET", 28: "SUSP_IND", 29: "VDDA33_3", 30: "USBDM_UP",
    31: "USBDP_UP", 32: "XTALOUT", 33: "XTALIN", 34: "PLLFILT", 35: "RBIAS",
    36: "VDDA33_4", 37: "EP",
}


def add_usb2514b_i_m2(design, ref: str, **overrides) -> Chip:
    """Microchip USB2514B-I/M2 — USB 2.0 HS 4-port hub, 3.3 V, QFN-36 6×6,
    −40…85 °C. Pins named from the USB2514B DATASHEET by number (the
    SamacSys symbol is the 2-port USB2512B's). EP = VSS."""
    pins = [Pin(num=str(n), name=nm, type="ground" if nm == "EP" else "io")
            for n, nm in _USB2514B_PINS.items()]
    return _sam(design, ref, pn="USB2514B-I/M2", part_dir="USB2514B-I_M2",
                mod="QFN50P600X600X100-37N-D.kicad_mod", package="QFN-36 (6×6)",
                height_mm=1.0, size_mm=(6.0, 6.0), manf="Microchip",
                description="USB 2.0 hi-speed 4-port hub controller, 3.3 V, QFN-36",
                pins=pins, **overrides)


def add_ina228aidgsr(design, ref: str, **overrides) -> Chip:
    """TI INA228 — 85 V, 20-bit I²C power / ENERGY / CHARGE monitor, VSSOP-10."""
    return _sam(design, ref, pn="INA228AIDGSR", part_dir="INA228AIDGSR",
                mod="SOP50P490X110-10N.kicad_mod", package="VSSOP-10",
                height_mm=1.1, size_mm=(3.0, 3.0), manf="Texas Instruments",
                description="20-bit I2C current/voltage/power/energy/charge monitor, 85 V, VSSOP-10",
                **overrides)


def add_ina241a2idgkr(design, ref: str, **overrides) -> Chip:
    """TI INA241A2 — bidirectional current-sense amplifier, 20 V/V, 1.1 MHz,
    −5…110 V common mode, VSSOP-8 (fast current path for the meter's ADC)."""
    return _sam(design, ref, pn="INA241A2IDGKR", part_dir="INA241A2IDGKR",
                mod="SOP65P490X110-8N.kicad_mod", package="VSSOP-8",
                height_mm=1.1, size_mm=(3.0, 3.0), manf="Texas Instruments",
                description="Current-sense amplifier, 20 V/V, 1.1 MHz, bidirectional, VSSOP-8",
                **overrides)


def add_tpd4e05u06dqar(design, ref: str, **overrides) -> Chip:
    """TI TPD4E05U06 — 4-channel ESD protection for USB, USON-10 (DQA)."""
    return _sam(design, ref, pn="TPD4E05U06DQAR", part_dir="TPD4E05U06DQAR",
                mod="DQA_R-PUSON-N10_.kicad_mod", package="USON-10 (DQA)",
                height_mm=0.6, size_mm=(2.5, 1.0), manf="Texas Instruments",
                description="4-channel USB ESD protection, USON-10", ring_courtyard=True,
                **overrides)


def add_u_fl_r_smt_1(design, ref: str, **overrides) -> Chip:
    """Hirose U.FL-R-SMT-1(10) — U.FL RF receptacle. Footprint pads (Hirose
    recommended mounting pattern, catalog p.3): 3 = SIG (1.0 × 1.05 centre
    pad), 1 and 2 = GND (the shell's 1.0 × 2.2 side tabs)."""
    from smash.state import Pin
    pins = [Pin(num="1", name="GND", aliases=["GND_1"], type="ground"),
            Pin(num="2", name="GND", aliases=["GND_2"], type="ground"),
            Pin(num="3", name="SIG", type="io")]
    return _sam(design, ref, pn="U.FL-R-SMT-1(10)", part_dir="U.FL-R-SMT-1_10_",
                mod="U.FL-R-SMT-1_10_.kicad_mod", package="U.FL",
                height_mm=1.25, size_mm=(2.6, 3.0), manf="Hirose", pins=pins,
                description="U.FL coaxial receptacle, SMT", **overrides)


def add_sn74cb3t3125pwr(design, ref: str, **overrides) -> Chip:
    """TI SN74CB3T3125 — quad FET bus switch, separate active-low /OE per
    channel, Ioff (isolates a powered-down side), TSSOP-14."""
    return _sam(design, ref, pn="SN74CB3T3125PWR", part_dir="SN74CB3T3125PWR",
                mod="SOP65P640X120-14N.kicad_mod", package="TSSOP-14",
                height_mm=1.2, size_mm=(5.0, 4.4), manf="Texas Instruments",
                description="Quad FET bus switch, 5 V-tolerant, Ioff, TSSOP-14", **overrides)


def add_b3u_1000p(design, ref: str, **overrides) -> Chip:
    """Omron B3U-1000P — SMD tactile switch 3.0 × 2.5 mm, SPST-NO, 50 mA 12 V
    (SamacSys names the two contacts K / A)."""
    return _sam(design, ref, pn="B3U-1000P", part_dir="B3U-1000P",
                mod="B3U-1000P.kicad_mod", package="SMD tactile 3.0×2.5",
                height_mm=1.6, size_mm=(3.0, 2.5), manf="Omron",
                description="Tactile switch SPST-NO, SMD 3.0 x 2.5 mm", **overrides)


def add_mill_max_0906(design, ref: str, **overrides) -> Chip:
    """Mill-Max 0906-0-15-20-76-14-11-0 — spring-loaded pin (through-hole
    tail): the dev board's aft-fixture contacts."""
    import math
    chip = _sam(design, ref, pn="0906-0-15-20-76-14-11-0",
                part_dir="0906-0-15-20-76-14-11-0", mod="0906015207614110.kicad_mod",
                package="spring pin", height_mm=5.3, size_mm=(1.8, 1.8), manf="Mill-Max",
                ring_courtyard=True,                     # SamacSys CrtYd 3.8 mm > the 1.67 mm contact pitch
                description="Spring-loaded contact pin", **overrides)
    # ROUND courtyard just outside the Ø1.8 barrel (Ø1.9): the fixture's
    # staggered pins sit 2.17 mm apart, and a rectangular envelope clips its
    # diagonal neighbours although the barrels keep 0.37 mm
    r = 0.95
    chip.footprint.courtyard = [(round(r * math.cos(math.radians(a)), 4),
                                 round(r * math.sin(math.radians(a)), 4)) for a in range(0, 360, 15)]
    return chip


def add_mill_max_5849(design, ref: str, **overrides) -> Chip:
    """Mill-Max 5849-0-00-15-00-00-03-0 — PCB locating pin: Ø1.50 pin, 6.5 mm
    above its Ø1.98 flange, through-hole solder tail (PTH Ø1.6, pad Ø2.4).
    The dev-board aft fixture's DOWELS: into the aft cap's through locating
    holes (6.5 − 5.3 mm spring-pin tip = 1.2 mm engagement at rest)."""
    return _sam(design, ref, pn="5849-0-00-15-00-00-03-0",
                part_dir="5849-0-00-15-00-00-03-0", mod="5849000150000030.kicad_mod",
                package="locating pin", height_mm=6.5, size_mm=(1.98, 1.98), manf="Mill-Max",
                description="PCB locating pin Ø1.5 mm, 6.5 mm above flange, solder tail",
                ring_courtyard=True, **overrides)


def add_ads7138irter(design, ref: str, **overrides) -> Chip:
    """TI ADS7138IRTER — 8-channel 12-bit SAR ADC, I²C, WQFN-16 3 × 3 mm
    (RTE0016C, 0.8 mm max). Land per TI 4219117/B example board layout:
    16 × 0.6 × 0.24 pads at 0.5 pitch, 2.8 mm centre-to-centre, EP 1.68 sq.
    Pins per DS Pin Functions (SBAS976A): 1-6 AIN2..AIN7, 7 AVDD (also the
    reference), 8 DECAP, 9 GND, 10 DVDD, 11 ADDR, 12 ALERT, 13 SCL, 14 SDA,
    15 AIN0, 16 AIN1, EP → GND. Inputs 0…AVDD (abs max AVDD + 0.3). Dev
    strip rail monitor (bring-up)."""
    from smash.state import Pad
    pads = []
    for k, y in enumerate((0.75, 0.25, -0.25, -0.75)):          # smash y-UP, CCW from pin 1 (top-left)
        pads.append(Pad(num=str(1 + k), position_mm=(-1.4, y), size_mm=(0.6, 0.24), shape="rect"))
        pads.append(Pad(num=str(5 + k), position_mm=(-y, -1.4), size_mm=(0.24, 0.6), shape="rect"))
        pads.append(Pad(num=str(9 + k), position_mm=(1.4, -y), size_mm=(0.6, 0.24), shape="rect"))
        pads.append(Pad(num=str(13 + k), position_mm=(y, 1.4), size_mm=(0.24, 0.6), shape="rect"))
    pads.append(Pad(num="17", position_mm=(0.0, 0.0), size_mm=(1.68, 1.68), shape="rect"))
    fp = Footprint(name="TI_RTE0016C_WQFN16_3x3", package_class="WQFN-16 3x3 + EP",
                   pads=sorted(pads, key=lambda p: int(p.num)),
                   body_outline=[(-1.5, -1.5), (1.5, -1.5), (1.5, 1.5), (-1.5, 1.5)],
                   courtyard=[(-2.0, -2.0), (2.0, -2.0), (2.0, 2.0), (-2.0, 2.0)],
                   pitch_mm=0.5, size_mm=(3.0, 3.0), height_mm=0.8, source="datasheet")
    names = {1: "AIN2", 2: "AIN3", 3: "AIN4", 4: "AIN5", 5: "AIN6", 6: "AIN7", 7: "AVDD",
             8: "DECAP", 9: "GND", 10: "DVDD", 11: "ADDR", 12: "ALERT", 13: "SCL", 14: "SDA",
             15: "AIN0", 16: "AIN1", 17: "EP"}
    types = {"AVDD": "power", "DVDD": "power", "GND": "ground", "EP": "ground", "DECAP": "passive",
             "ADDR": "analog", "ALERT": "output", "SCL": "input", "SDA": "io"}
    pins = [Pin(num=str(n), name=nm, type=types.get(nm, "analog")) for n, nm in names.items()]
    fields = dict(manf="Texas Instruments", manf_pn="ADS7138IRTER", canonical_id=canonical_id("ADS7138IRTER"),
                  name="ADS7138IRTER", value="ADS7138", package="WQFN-16 (3×3)",
                  description="8-ch 12-bit SAR ADC, I²C, WQFN-16 3×3", size_mm=(3.0, 3.0), height_mm=0.8,
                  datasheet="application/src/smash/parts/sources/ADS7138IRTER/ADS7138.pdf",
                  pins=pins, footprint=fp, note="Dev-strip rail monitor (BRING_UP.md).")
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
