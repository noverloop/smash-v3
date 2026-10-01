"""Motor driver factories."""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def add_drv8833pwr(design, ref: str, **overrides) -> Chip:
    """TI DRV8833PWR — dual H-bridge motor driver, 2.7-10.8 V, 1.5 A
    RMS per H-bridge (peak 2 A), TSSOP-16."""
    pn = "DRV8833PWR"
    fp_mod = src(pn, "SOP65P640X120-16N.kicad_mod")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Dual H-bridge motor driver, V_M=2.7..10.8 V, "
            "I_RMS=1.5 A per H-bridge (2 A peak), TSSOP-16"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="TSSOP-16",
        temp_range_c=(-40, 125),
        voltage_rating_v=11.8,       # V_M abs max per datasheet (verify §6.1)
        i_rms_a=1.5,
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="SOP65P640X120-16N", package_class="TSSOP-16",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.65,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ).ensure_courtyard_clearance(),  # some SamacSys F.CrtYd hug the pads
        note=(
            "DRV8833 dual H-bridge — typical use is two DC brushed "
            "motors OR one stepper. PWM input control with parallel "
            "input select. Has built-in current regulation per "
            "H-bridge (sense resistor on AISEN/BISEN)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_drv8428epwpr(design, ref: str, **overrides) -> Chip:
    """TI DRV8428EPWPR — integrated dual H-bridge stepper / 2× brushed-DC
    driver, 4.5-33 V, ~2.1 A RMS (3 A peak) per bridge, HTSSOP-16 with EP.

    PH/EN control variant ('E'): each bridge driven by a phase pin
    (APH/BPH = direction) + enable pin (AEN/BEN = PWM); per-bridge current
    limit set by VREFA/VREFB. Integrated MOSFETs — no external FETs (unlike
    the DRV8711 pre-driver it replaces)."""
    pn = "DRV8428EPWPR"
    fp_mod = src(pn, "SOP65P640X120-17N.kicad_mod")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Integrated dual H-bridge stepper/brushed driver, "
            "V_M=4.5..33 V, ~2.1 A RMS per bridge, PH/EN control, "
            "HTSSOP-16 with EP"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="HTSSOP-16",
        temp_range_c=(-40, 125),
        voltage_rating_v=33.0,
        i_rms_a=2.1,
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="SOP65P640X120-17N", package_class="HTSSOP-16",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.65,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ).ensure_courtyard_clearance(),  # some SamacSys F.CrtYd hug the pads
        note=(
            "DRV8428E — INTEGRATED bipolar stepper driver (replaces the "
            "DRV8711 pre-driver + its 8 external FETs). PH/EN interface: "
            "APH/AEN + BPH/BEN drive the two bridges (PWM the EN pin, "
            "toggle PH for direction); VREFA/VREFB set per-bridge current; "
            "DECAY/TOFF sets decay; NSLEEP enables. EP = GND thermal pad."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_drv8711dcpr(design, ref: str, **overrides) -> Chip:
    """TI DRV8711DCPR — bipolar stepper pre-driver (gate drive for
    external MOSFETs), microstepping up to 1/256, SPI control,
    HTSSOP-38 with thermal pad."""
    pn = "DRV8711DCPR"
    fp_mod = src(pn, "SOP50P640X120-39N.kicad_mod")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Bipolar stepper pre-driver with SPI control, "
            "1/256 microstepping, external N-FET gate drive, "
            "HTSSOP-38 with EP"
        ),
        datasheet=datasheet_ref(pn, f"{pn}.pdf"),
        package="HTSSOP-38",
        temp_range_c=(-40, 125),
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name="SOP50P640X120-39N", package_class="HTSSOP-38",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.5,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ).ensure_courtyard_clearance(),  # some SamacSys F.CrtYd hug the pads
        note=(
            "DRV8711 — pre-driver, NOT an integrated stepper driver. "
            "Requires 4× external N-channel MOSFETs (two H-bridges). "
            "SPI for configuration; STEP/DIR for step generation. "
            "Includes adaptive blanking time, decay-mode control, "
            "and stall detect."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
