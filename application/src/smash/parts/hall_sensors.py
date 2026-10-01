"""Hall-effect sensor factories."""

from __future__ import annotations

from smash.state import Chip, Footprint
from smash.parts._artifacts import (
    pads_from_kicad_mod, outline_polygon, build_pins, src, datasheet_ref,
)
from smash.parts._slug import canonical_id


def add_drv5023ajqlpg(design, ref: str, **overrides) -> Chip:
    """TI DRV5023AJQLPG — digital-output unipolar Hall-effect switch,
    open-drain output, SOT-23 (DBZ package). The 'A' suffix denotes
    the lowest operating threshold (B_OP = 3.5 mT typ); 'JQ' = AEC-Q100
    grade 0 (-40 to +150 °C ambient)."""
    pn = "DRV5023AJQLPG"
    fp_mod = src(pn, f"{pn}.kicad_mod")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Digital Hall-effect switch, unipolar, open-drain output, "
            "B_OP=3.5 mT typ (A threshold), AEC-Q100 grade 0, SOT-23"
        ),
        datasheet=datasheet_ref(pn, "drv5023.pdf"),
        package="SOT-23 (DBZ)",
        temp_range_c=(-40, 150),    # AEC-Q100 grade 0 ambient
        voltage_rating_v=27.0,       # typical V_CC abs max for DRV5023
        standards=["AEC-Q100 Grade 0"],
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name=pn, package_class="SOT-23",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.95,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "DRV5023 family threshold suffixes (datasheet Table 1):\n"
            "  A : B_OP = 3.5 mT typ   (this part — lowest)\n"
            "  B : B_OP = 6.9 mT typ\n"
            "  E : B_OP = 17.0 mT typ\n"
            "  F : B_OP = 21.0 mT typ  (highest)\n"
            "All AJ* variants are AEC-Q100 grade 0 (-40 to +150 °C); "
            "AB* variants are grade 1 (-40 to +85 °C).\n\n"
            "Output is open-drain — REQUIRES external pull-up. Detects "
            "South-pole field (or North-pole depending on orientation, "
            "see DS). Unipolar = latches off only on field removal, "
            "not on reversal."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_drv5032fcqdbzr(design, ref: str, **overrides) -> Chip:
    """TI DRV5032FC — NANOPOWER Hall-effect switch, OMNIPOLAR, OPEN-DRAIN,
    SOT-23 (DBZ). B_OP = 4.8 mT max, 20 Hz sampling, I_CC 1.6 uA typ /
    3.5 uA max @ 3 V. The magnetic-wake listener (dual IR + magnetic
    wakeup, 2026-07-30): omnipolar = round orientation in the container
    doesn't matter; open-drain = wire-ORs into MAIN_SW_GATE through the
    spare D_NFC_WAKE cathode AND level-shifts BAT_RAW->3V3_AON naturally;
    20 Hz sampling supports a ~2 Hz coded wake pattern."""
    pn = "DRV5032FCQDBZR"
    fp_mod = src(pn, f"{pn}.kicad_mod")
    fields = dict(
        manf="Texas Instruments", manf_pn=pn, canonical_id=canonical_id(pn), name=pn, value=pn,
        description=(
            "Nanopower Hall-effect switch, omnipolar, open-drain, "
            "B_OP=4.8 mT max, 20 Hz sampling, 1.6 uA typ, SOT-23"
        ),
        datasheet=datasheet_ref(pn, "drv5032.pdf"),
        package="SOT-23 (DBZ)",
        temp_range_c=(-40, 85),
        voltage_rating_v=5.5,
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name=pn, package_class="SOT-23",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.95,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "DBZ pinout: 1=VCC (1.65-5.5 V), 2=OUT, 3=GND — identical to "
            "DRV5023 DBZ; footprint/symbol reused from that part's "
            "SamacSys sources.\n"
            "Output is open-drain, asserts LOW while |B| >= B_OP in EITHER "
            "polarity, samples at 20 Hz (t_S 50 ms) — an external coded "
            "field must hold each bit >= ~100 ms for guaranteed sampling.\n"
            "Runs on BAT_RAW (always-live): wakes the round from TRUE "
            "shelf through a closed (aluminium) container where NFC and "
            "IR are both blind. Through STEEL walls the flux is shunted "
            "~30-100x — transmitter coil must be sized accordingly "
            "(bench-test item)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)


def add_rr123_1h02_612(design, ref: str, **overrides) -> Chip:
    """Coto RedRock RR123-1H02-612 — TMR NANOPOWER magnetic switch,
    omnipolar, ACTIVE-LOW push-pull, LGA-4 1.45 x 1.45 x 0.44 mm.
    B_OP 0.7 mT / B_RP 0.3 mT (suffix H), f_SW 1 Hz typ (0.5-2 Hz,
    +/-50 % over temp), I_DD(avg) 20 nA, VDD 1.0-3.6 V (ABS MAX 3.6 V —
    must NOT hang on BAT_RAW; feed from a dedicated always-on nano-LDO).
    The SHELF-WAKE ear (2026-07-30): 0.7 mT operate = 7x more sensitive
    than the DRV5032FC arming listener — the through-container wake coil
    shrinks 7x and through-steel becomes plausible."""
    pn = "RR123-1H02-612"
    fp_mod = src(pn, f"{pn}.kicad_mod")
    fields = dict(
        manf="Coto Technology", manf_pn=pn, canonical_id=canonical_id(pn),
        name=pn, value=pn,
        description=(
            "TMR nanopower magnetic switch, omnipolar, active-low "
            "push-pull, B_OP 0.7 mT, 1 Hz sampling, 20 nA, LGA-4"
        ),
        datasheet=datasheet_ref(pn, "redrock-rr123-datasheet.pdf"),
        package="LGA-4 (1.45x1.45 mm)",
        temp_range_c=(-40, 85),
        voltage_rating_v=3.6,
        pins=build_pins(src(pn, f"{pn}.kicad_sym")),
        footprint=Footprint(
            name=pn, package_class="LGA-4",
            pads=pads_from_kicad_mod(fp_mod),
            body_outline=outline_polygon(fp_mod, "F.Fab"),
            courtyard=outline_polygon(fp_mod, "F.CrtYd"),
            pitch_mm=0.8,
            model_3d_path=datasheet_ref(pn, f"{pn}.stp"),
            source="samacsys",
        ),
        note=(
            "Suffix decode 1H02-612: omnipolar / Op 7 G Rel 3 G / 1.0 Hz "
            "clock / LGA-4 / 1.0-3.6 V / ACTIVE LOW / -40..85 C.\n"
            "Pins (SamacSys symbol): VDD, DIGITAL_OUT, GND, "
            "LATCH_CONTROL.\n"
            "Output is PUSH-PULL (weak sink 100 uA / 140 kohm): sized only "
            "to pull the wake-OR diode legs (~10 uA static), never a hard "
            "load. Idles HIGH at its own VDD — keep it off MCU pins that "
            "can be unpowered.\n"
            "f_SW 1 Hz typ with +/-50 % temp drift: shelf-wake code bits "
            "must be >= ~3 s (full sequence ~10-15 s — depot bulk wake, "
            "not a quick tap).\n"
            "LATCH_CONTROL tied inactive (GND assumed — VERIFY polarity "
            "in the full DS). Single-source (Coto)."
        ),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, **fields)
