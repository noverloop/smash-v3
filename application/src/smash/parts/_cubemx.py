"""Parse a vendored CubeMX MCU XML into an alternate-function table.

The CubeMX MCU XMLs are the external ground truth for which signals
each pin of an STM32 chip can be muxed to. We vendor the XML directly
into each MCU's per-part source directory (alongside the SamacSys ZIP,
KiCad sym, footprint, STEP, datasheet) so the build doesn't depend on
having CubeMX installed.

This parser is the catalog-side replacement for
`tools/stm32_pinmux/parse.py` — same XML schema, but no JSON cache, no
filename-mangling logic (the path is passed in directly), and the
output is shaped to feed straight into `Pin.alt_functions`.

Parsing is `lru_cache`'d on path so the factory is fast even when many
tests instantiate the same MCU.
"""

from __future__ import annotations

import functools
import xml.etree.ElementTree as ET
from typing import Iterable


XML_NS = "{http://mcd.rou.st.com/modules.php?name=mcu}"


@functools.lru_cache(maxsize=None)
def load_af_table(xml_path: str) -> dict[str, dict]:
    """Parse `<part-dir>/cubemx.xml` → {pin_name: {position, type, signals}}.

    `pin_name` matches the `Name` attribute on `<Pin>` elements (e.g.
    "PA0", "PB12", "VSS", "VDDA", "PH0-OSC_IN(PH0)" — CubeMX keeps the
    fused-pin names verbatim).

    `signals` is the **full alternate-function list** for that pin —
    the same data CubeMX's GUI uses to validate pinmux choices.

    For pins that share a name (multiple VSS / VDD balls), all
    positions are recorded under the same key in `positions`. The
    `signals` list is the union (typically empty for power pins, so
    union == any one of them).
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    out: dict[str, dict] = {}
    for pin_el in root.findall(f"{XML_NS}Pin"):
        name = pin_el.get("Name") or ""
        position = pin_el.get("Position") or ""
        ptype = pin_el.get("Type") or ""
        signals = [
            s.get("Name")
            for s in pin_el.findall(f"{XML_NS}Signal")
            if s.get("Name")
        ]
        if name in out:
            out[name]["positions"].append(position)
            # Union of signals (power rails normally have empty lists)
            for s in signals:
                if s not in out[name]["signals"]:
                    out[name]["signals"].append(s)
        else:
            out[name] = {
                "positions": [position],
                "type":      ptype,
                "signals":   signals,
            }
    return out


def alt_functions_by_pin_name(xml_path: str) -> dict[str, list[str]]:
    """Convenience: {pin_name: [signals...]} for factory `build_pins`
    overlays. Empty lists for power/ground pins."""
    af_table = load_af_table(xml_path)
    return {name: info["signals"] for name, info in af_table.items()}


def alt_functions_by_position(xml_path: str) -> dict[str, list[str]]:
    """Same as above but keyed by ball position ("J4") instead of name
    ("PD0"). Useful when the factory's pin map is keyed by ball coord."""
    af_table = load_af_table(xml_path)
    by_pos: dict[str, list[str]] = {}
    for name, info in af_table.items():
        for pos in info["positions"]:
            if pos:
                by_pos[pos] = info["signals"]
    return by_pos
