"""STM32 function map — what each MCU pin is FOR, checked against CubeMX.

The pin mux is per pin (GPIOx_AFR), but several rules are chip-level. This is
the design's ".ioc": every net that needs a peripheral names the CubeMX signal
it relies on, and `check()` verifies:

  F1 available      the pin offers that signal (CubeMX MCU XML)
  F2 unique         no signal is used on two pins of one chip
  F3 one instance   the signals of one bus come from ONE peripheral instance
                    (SCK/MOSI/MISO all SPI2, not SPI2 + SPI4)
  F4 EXTI lines     interrupt inputs: at most N per line number (pin n of every
                    port shares EXTI line n; the MP25 has two EXTI controllers)
  F5 boot ROM       pins the MP25 boot ROM drives as UART TX during serial boot
                    carry only nets where that is harmless

Not covered here (checked elsewhere / by review): I/O bank supply per pin, MP25
resource isolation (RIF: which core owns a peripheral — firmware).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from functools import cache
from pathlib import Path

CUBEMX_DB = Path("/Applications/STMicroelectronics/STM32CubeMX.app/Contents/Resources/db/mcu")

# chip ref → {net: regex the CubeMX signal must match}
FUNCTIONS: dict[str, dict[str, str]] = {
    "U_MPU": {
        "NAND_OSPI_CLK": r"OCTOSPIM_P1_CLK", "NAND_OSPI_IO0": r"OCTOSPIM_P1_IO0",
        "NAND_OSPI_IO1": r"OCTOSPIM_P1_IO1", "NAND_OSPI_IO2": r"OCTOSPIM_P1_IO2",
        "NAND_OSPI_IO3": r"OCTOSPIM_P1_IO3", "NAND_OSPI_CS0": r"OCTOSPIM_P1_NCS1",
        "NAND_OSPI_CS1": r"OCTOSPIM_P1_NCS2",
        "QPD_TIA_A": r"ADC\d_INP\d+", "QPD_TIA_B": r"ADC\d_INP\d+",
        "QPD_TIA_C": r"ADC\d_INP\d+", "QPD_TIA_D": r"ADC\d_INP\d+",
        "SYS_SPI_SCLK": r"SPI\d_SCK", "SYS_SPI_MOSI": r"SPI\d_MOSI", "SYS_SPI_MISO": r"SPI\d_MISO",
        "WBA_HCI_SCK": r"SPI\d_SCK", "WBA_HCI_MOSI": r"SPI\d_MOSI", "WBA_HCI_MISO": r"SPI\d_MISO",
        "AWR_SPI_CLK": r"SPI\d_SCK", "AWR_SPI_MOSI": r"SPI\d_MOSI", "AWR_SPI_MISO": r"SPI\d_MISO",
        "WBA_UART_TX": r"(LP)?US?ART\d_RX", "WBA_UART_RX": r"(LP)?US?ART\d_TX",     # net named from the WBA side
        "AWR_RS232_RX": r"(LP)?US?ART\d_TX", "AWR_RS232_TX": r"(LP)?US?ART\d_RX",   # net named from the AWR side
        "MP25_CONSOLE_TX": r"(LP)?US?ART\d_TX", "MP25_CONSOLE_RX": r"(LP)?US?ART\d_RX",
        "EXT_CAN_TX": r"FDCAN\d_TX", "EXT_CAN_RX": r"FDCAN\d_RX",
        "I2C2_SCL": r"I2C\d_SCL", "I2C2_SDA": r"I2C\d_SDA",
        "I2C3_SCL": r"I2C\d_SCL", "I2C3_SDA": r"I2C\d_SDA",
        "SYS_I2C_SCL": r"I2C\d_SCL", "SYS_I2C_SDA": r"I2C\d_SDA",
    },
    "U_WBA": {
        "LR_SPI_SCK": r"SPI\d_SCK", "LR_SPI_MOSI": r"SPI\d_MOSI", "LR_SPI_MISO": r"SPI\d_MISO",
        "WBA_HCI_SCK": r"SPI\d_SCK", "WBA_HCI_MOSI": r"SPI\d_MOSI", "WBA_HCI_MISO": r"SPI\d_MISO",
        "WBA_HCI_NSS": r"SPI\d_NSS",
        "WBA_UART_TX": r"(LP)?US?ART\d_TX", "WBA_UART_RX": r"(LP)?US?ART\d_RX",
        "I2C2_SCL": r"I2C\d_SCL", "I2C2_SDA": r"I2C\d_SDA",
        "BAT_SENSE": r"ADC\d_IN\d+",
    },
    "U_FIN_MCU": {
        "SYS_SPI_SCLK": r"SPI\d_SCK", "SYS_SPI_MOSI": r"SPI\d_MOSI", "SYS_SPI_MISO": r"SPI\d_MISO",
        "SYS_SPI_CS_FIN": r"SPI\d_NSS",
        # TC78H653 xEN inputs are PWM'd: one timer channel each
        **{f"FIN{k}_{ab}EN": r"TIM\d+_CH\d" for k in (1, 2, 3, 4) for ab in "AB"},
    },
    "U_DEV_MCU": {
        "DEV_TWR_CONS_TX_G": r"(LP)?US?ART\d_RX",     # listens to the MP25 console TX
        "DEV_TWR_CONS_RX_G": r"(LP)?US?ART\d_TX",
        "DEV_TWR_SWO_G": r"(LP)?US?ART\d_RX",
        "DEV_USB_UP_P": r"USB_DP", "DEV_USB_UP_N": r"USB_DM",
        "DEV_CAN_TX": r"FDCAN\d_TX", "DEV_CAN_RX": r"FDCAN\d_RX",
        "DEV_I2C_SCL": r"I2C\d_SCL", "DEV_I2C_SDA": r"I2C\d_SDA",
        "DEV_ISENSE": r"ADC\d_IN\d+", "DEV_TWR_VDD_SENSE": r"ADC\d_IN\d+",
    },
}

# chip ref → buses whose signals must come from ONE peripheral instance
BUSES: dict[str, list[list[str]]] = {
    "U_MPU": [["NAND_OSPI_CLK", "NAND_OSPI_IO0", "NAND_OSPI_IO1", "NAND_OSPI_IO2",
               "NAND_OSPI_IO3", "NAND_OSPI_CS0", "NAND_OSPI_CS1"],
              ["SYS_SPI_SCLK", "SYS_SPI_MOSI", "SYS_SPI_MISO"],
              ["WBA_HCI_SCK", "WBA_HCI_MOSI", "WBA_HCI_MISO"],
              ["AWR_SPI_CLK", "AWR_SPI_MOSI", "AWR_SPI_MISO"],
              ["WBA_UART_TX", "WBA_UART_RX"], ["AWR_RS232_RX", "AWR_RS232_TX"],
              ["MP25_CONSOLE_TX", "MP25_CONSOLE_RX"], ["EXT_CAN_TX", "EXT_CAN_RX"],
              ["I2C2_SCL", "I2C2_SDA"], ["I2C3_SCL", "I2C3_SDA"], ["SYS_I2C_SCL", "SYS_I2C_SDA"]],
    "U_WBA": [["LR_SPI_SCK", "LR_SPI_MOSI", "LR_SPI_MISO"],
              ["WBA_HCI_SCK", "WBA_HCI_MOSI", "WBA_HCI_MISO", "WBA_HCI_NSS"],
              ["WBA_UART_TX", "WBA_UART_RX"], ["I2C2_SCL", "I2C2_SDA"]],
    "U_FIN_MCU": [["SYS_SPI_SCLK", "SYS_SPI_MOSI", "SYS_SPI_MISO", "SYS_SPI_CS_FIN"]],
    "U_DEV_MCU": [["DEV_TWR_CONS_TX_G", "DEV_TWR_CONS_RX_G"], ["DEV_CAN_TX", "DEV_CAN_RX"],
                  ["DEV_I2C_SCL", "DEV_I2C_SDA"]],
}

# chip ref → nets used as interrupt inputs (EXTI)
INTERRUPTS: dict[str, list[str]] = {
    "U_MPU": ["MAG_DRDY", "IMU1_INT", "IMU2_INT", "IMU3_INT", "H3LIS_INT1", "AWR_DRDY",
              "AWR_FAULT", "COMP_OUT", "WBA_HCI_IRQ", "TMP1_ALERT", "PMIC_PWR_OK"],
    "U_WBA": ["LR_IRQ", "LR_BUSY", "MAG_WAKE_N", "IR_WAKE"],
}
EXTI_PER_LINE = {"U_MPU": 2}          # MP25: EXTI1 + EXTI2 (DS14285 §3.21); others: 1

# MP25 boot ROM: UART TX pins it drives in serial boot (DS14285 Table 6) →
# nets allowed there, with the reason it is harmless
BOOT_ROM_TX = {"U_MPU": {"PA4": "USART2_TX", "PA0": "UART5_TX", "PF5": "USART6_TX",
                         "PG3": "UART8_TX", "PD13": "UART9_TX"}}
BOOT_ROM_OK = {
    "WBA_UART_RX": "the WBA's UART RX — listening is harmless",
    "MP25_CONSOLE_TX": "the console itself",
    "SYS_SPI_CS_FIN": "fin chip-select: idle-high = deselected",
}


def _xml_for(pn: str) -> Path | None:
    m = re.match(r"(STM32\w+?)(\d)(Q?)$", pn or "")
    if not m:
        return None
    f = CUBEMX_DB / f"{m.group(1)}x{m.group(3)}.xml"
    return f if f.exists() else None


@cache
def cubemx_signals(xml: Path) -> dict:
    """ball/pin position → (pin name, [signal names])."""
    out = {}
    for el in ET.parse(xml).getroot().iter():
        if el.tag.endswith("Pin") and "Position" in el.attrib:
            out[el.attrib["Position"]] = (
                el.attrib["Name"], [s.attrib.get("Name", "") for s in el if s.tag.endswith("Signal")])
    return out


def _net(p):
    n = p.net
    return getattr(n, "name", n)


def _gpio(name: str) -> tuple | None:
    m = re.match(r"P([A-Z])(\d+)", name)
    return (m.group(1), int(m.group(2))) if m else None


def check(design) -> list[str]:
    errs: list[str] = []
    chips = {c.ref: c for c in design.chips}
    for ref, fmap in FUNCTIONS.items():
        c = chips.get(ref)
        if c is None:
            continue
        xml = _xml_for(c.manf_pn)
        if xml is None:
            errs.append(f"{ref}: no CubeMX XML for {c.manf_pn}")
            continue
        db = cubemx_signals(xml)
        by_net: dict = {}
        for p in c.pins:
            if _net(p):
                by_net.setdefault(_net(p), []).append(p)
        chosen: dict = {}                         # net → matched signal
        for net, rx in fmap.items():
            pins = by_net.get(net)
            if not pins:
                errs.append(f"F1 {ref}: no pin on {net}")
                continue
            for p in pins:
                sigs = db.get(p.num, ("", []))[1]
                hit = [s for s in sigs if re.fullmatch(rx, s)]
                if not hit:
                    errs.append(f"F1 {ref}.{p.num} ({p.name}) on {net}: no signal ~{rx} ({sigs})")
                else:
                    chosen[net] = hit[0]
        # F2: a signal on two pins
        seen: dict = {}
        for net, sig in chosen.items():
            if sig in seen:
                errs.append(f"F2 {ref}: {sig} used by {seen[sig]} and {net}")
            seen[sig] = net
        # F3: one instance per bus (an ambiguous match picks the instance the bus agrees on)
        for bus in BUSES.get(ref, []):
            options = []
            for net in bus:
                ps = by_net.get(net, [])
                sigs = {s for p in ps for s in db.get(p.num, ("", []))[1]
                        if re.fullmatch(fmap.get(net, r"$^"), s)}
                options.append({s.split("_")[0] for s in sigs})
            if options and all(options):
                common = set.intersection(*options)
                if not common:
                    errs.append(f"F3 {ref}: bus {bus} spans instances {options}")
        # F4: EXTI lines
        cap = EXTI_PER_LINE.get(ref, 1)
        lines: dict = {}
        for net in INTERRUPTS.get(ref, []):
            for p in by_net.get(net, []):
                g = _gpio(db.get(p.num, (p.name, []))[0])
                if g:
                    lines.setdefault(g[1], []).append(f"{net}@P{g[0]}{g[1]}")
        for n, srcs in sorted(lines.items()):
            if len(srcs) > cap:
                errs.append(f"F4 {ref}: EXTI line {n} has {len(srcs)} sources (max {cap}): {srcs}")
        # F5: boot-ROM TX pins
        for pin_name, sig in BOOT_ROM_TX.get(ref, {}).items():
            for p in c.pins:
                if db.get(p.num, ("", []))[0].split("(")[0].split("-")[0] == pin_name:
                    net = _net(p)
                    if net and net not in BOOT_ROM_OK:
                        errs.append(f"F5 {ref}.{pin_name}: boot ROM drives {sig} into {net}")
    return errs
