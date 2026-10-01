"""Optical sensor / emitter factories (photodiodes, IR emitters, cameras).

The IR service-link pair (VBPW34FAS receiver + VSMB1940X01 emitter) both
live here — hand-authored artifacts, same parser-based pattern — even
though the emitter is nominally an LED; the pair is one subsystem."""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def add_sfh203fa(design, ref: str, **overrides) -> Chip:
    """OSRAM SFH 203 FA — Silicon PIN photodiode, IR-filtered (daylight
    blocking), 850-1000 nm peak sensitivity, leaded T-1¾ package
    (SamacSys-supplied footprint is a custom outline)."""
    pn = "SFH203FA"
    fp_mod = src(pn, f"{pn}.kicad_mod")
    fields = dict(
        manf="OSRAM", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Silicon PIN photodiode, IR-filtered, peak λ=850-1000 nm, "
            "T-1¾ (5 mm) plastic package"
        ),
        datasheet=datasheet_ref(pn, "OSOS-S-A0016159580-1.pdf"),
        package="T-1¾ (plastic, IR-filter daylight blocking)",
        temp_range_c=(-40, 100),    # typical for SFH series; verify in DS
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name=pn, package_class="T-1¾",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            model_3d_path=None,     # SamacSys archive contained no STEP
            source="samacsys",
            note="SamacSys archive for SFH203FA does not include a STEP 3D model.",
        ),
        note=(
            "OSRAM SFH 203 FA — PIN photodiode with **integrated "
            "IR-blocking daylight filter** ('FA' suffix). The non-FA "
            "variant (SFH 203) is the full-spectrum part. Reverse-bias "
            "this device through a load resistor (photoconductive mode) "
            "or short into a transimpedance amplifier (photovoltaic "
            "mode). The Smash QPD module uses a different OSRAM part "
            "(MT03-092 QPD); this photodiode is for the ambient / "
            "downlink optical path."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_vbpw34fas(design, ref: str, **overrides) -> Chip:
    """Vishay VBPW34FAS — silicon PIN photodiode, SMD gullwing, with
    integrated daylight-blocking filter (780–1050 nm passband, peak
    950 nm). The SMD sibling of the BPW34/SFH 203 FA class: same
    7.5 mm² die, 1.2 mm profile. Artifacts HAND-AUTHORED from DS 81127
    Rev 1.3 (no SamacSys archive) — see sources/VBPW34FAS/part_info.txt."""
    pn = "VBPW34FAS"
    fp_mod = src(pn, f"{pn}.kicad_mod")
    fields = dict(
        manf="Vishay", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Silicon PIN photodiode, SMD, daylight-blocking filter, "
            "7.5 mm² die, peak λ=950 nm, 6.4 × 3.9 × 1.2 mm gullwing"
        ),
        datasheet=datasheet_ref(pn, "vbpw34fa.pdf"),
        package="SMD gullwing GW (6.4 × 3.9 × 1.2 mm, IR daylight filter)",
        temp_range_c=(-40, 100),    # DS 81127 abs-max operating range
        weight_g=0.060,             # est — not in DS 81127 (epoxy body + leadframe)
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name=pn, package_class="SMD-GW",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            model_3d_path=None,
            source="authored",
            note=("Hand-authored from DS 81127 Rev 1.3 package drawing "
                  "6.541-5086.01-4 + recommended solder pad (2× 1.75 × 1.8 mm, "
                  "outer span 8.9 mm). No STEP model published."),
        ),
        note=(
            "Datasheet extras (Vishay DS 81127 Rev 1.3, 21-Feb-2025) — "
            "transcribed verbatim:\n"
            "Abs max: V_R 60 V; P_V 215 mW; T_j 100 °C; T_amb/T_stg "
            "−40…+100 °C; T_sd 260 °C; R_thJA 350 K/W.\n"
            "Basic (25 °C): I_ra reverse light current 45 min / 55 typ µA "
            "@ E_e=1 mW/cm², λ=950 nm, V_R=5 V; I_ro dark 2 typ / 30 max nA "
            "@ V_R=10 V; C_D 25 typ / 40 max pF @ V_R=3 V (70 pF @ 0 V); "
            "V_(BR) 60 V min; t_r=t_f 100 ns @ V_R=10 V, R_L=1 kΩ; "
            "φ ±65°; λ_p 950 nm; λ_0.5 780–1050 nm; NEP 4e-14 W/√Hz.\n"
            "MSL 3 (168 h floor life). VBPW34FASR = reverse-gullwing "
            "variant, NOT footprint-compatible — do not substitute.\n"
            "Smash use: D_IR_WAKE on radar_module — IR arming wake into "
            "the WBA55 EXTI (photoconductive: cathode to the IR_WAKE "
            "pull-up, anode to GND). The daylight filter is the first "
            "line of sunlight rejection; WBA firmware pattern/persistence "
            "check is the second."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_vsmb1940x01(design, ref: str, **overrides) -> Chip:
    """Vishay VSMB1940X01 — 940 nm high-speed IR emitting diode, GaAlAs
    double-hetero, clear 0805 SMD, AEC-Q101. The TX half of the nose
    optical service link (pairs with the VBPW34FAS receiver — its
    780–1050 nm daylight-filter passband brackets this part's 940 nm
    peak). Artifacts HAND-AUTHORED from DS 81933 Rev 1.6 — see
    sources/VSMB1940X01/part_info.txt."""
    pn = "VSMB1940X01"
    fp_mod = src(pn, f"{pn}.kicad_mod")
    fields = dict(
        manf="Vishay", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "IR emitter, 940 nm, GaAlAs DH, t_r/t_f 15 ns, 100 mA cont / "
            "200 mA pulse, ±60°, 0805 (2.0 × 1.25 × 0.85 mm)"
        ),
        datasheet=datasheet_ref(pn, "vsmb1940.pdf"),
        package="0805 chipLED (2.0 × 1.25 × 0.85 mm, clear untinted)",
        temp_range_c=(-40, 85),     # DS 81933 abs-max operating range
        weight_g=0.006,             # est — not in DS 81933 (0805 chipLED class)
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name=pn, package_class="LED-0805",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            model_3d_path=None,
            source="authored",
            note=("Hand-authored from DS 81933 Rev 1.6 package drawing "
                  "6.541-5064.01-4 + recommended solder pad (2× 1.0 × 1.45 mm, "
                  "0.6 mm gap). No STEP model."),
        ),
        standards=["RoHS", "AEC-Q101", "J-STD-020 (MSL 3, 168 h floor life)"],
        note=(
            "Datasheet extras (Vishay DS 81933 Rev 1.6, 24-Mar-2025) — "
            "transcribed verbatim:\n"
            "Abs max: V_R 5 V; I_F 100 mA; I_FM 200 mA (tp/T=0.5, "
            "tp=100 µs); I_FSM 1 A (100 µs); P_V 160 mW; T_j 100 °C; "
            "T_amb −40…+85 °C; T_stg −40…+100 °C; R_thJA 270 K/W.\n"
            "Basic (25 °C): V_F 1.15/1.35/1.6 V (min/typ/max) @ 100 mA "
            "(2.2 V typ @ 1 A pulsed); I_e 3/6/12 mW/sr @ 100 mA "
            "(60 mW/sr @ 1 A); φe 40 mW @ 100 mA; φ ±60°; λ_p 940 nm "
            "@ 30 mA; Δλ 25 nm; t_r = t_f 15 ns @ 100 mA 20–80 %; "
            "C_J 70 pF; I_R 10 µA max @ V_R 5 V; virtual source Ø0.5 mm.\n"
            "Smash use: D_IR_TX on radar_module — nose IR downlink of the "
            "optical service link. Local low-side switch keeps the drive "
            "loop tile-local (BAT_PROT → LED → R → FET → GND); only the "
            "logic-level gate crosses the backbone (WBA-keyed, so the "
            "round can answer a wand from Standby with the MP25 dark)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
