"""NFC dual-port memory / tag factories."""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def add_st25dv16kc_ie8t3(design, ref: str, **overrides) -> Chip:
    """ST ST25DV16KC-IE8T3 — Dynamic NFC/RFID tag IC with 16-Kbit
    EEPROM, dual-port access (I²C from MCU + RF from a phone),
    energy-harvesting output, SO8N package."""
    pn = "ST25DV16KC-IE8T3"
    fp_mod = src(pn, "SOP65P640X120-8N.kicad_mod")
    fields = dict(
        manf="STMicroelectronics", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Dynamic NFC tag, 16-Kbit EEPROM, dual-port (I²C + ISO 15693 "
            "RF), energy-harvesting, SO8N"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="SO8N", height_mm=1.20,
        temp_range_c=(-40, 85),
        memory_capacity_bits=16384,
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="SOP65P640X120-8N", package_class="SO8N",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            height_mm=1.20, pitch_mm=0.65,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "ST25DV16KC family — 'KC' indicates 16-Kbit EEPROM with "
            "Dual-port (I²C + RF) and an Energy Harvesting output. "
            "The 'IE8T3' suffix denotes SO8N package, tape and reel. "
            "Antenna: external loop required on AC0/AC1 pins; the "
            "NFC carrier is 13.56 MHz (ISO 15693)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
