"""Declarative top/bottom face assignment for unlocked chips.

Mirrors the rule baked into `tools/layout_gen/placer.py:BomEntry.goes_to_bottom`:

  goes_to_bottom  =  is_mating_pad
                  OR is_test_point
                  OR is_embeddable_passive

This isn't a search heuristic — it's design intent. Mating pads + test
points + small passives belong on the bottom by convention; the AT&S
ECP build embeds the bottom-side passives in the laminate cavity. The
placer doesn't choose; it respects what the design declares.

For Smash's Ø34 tiles, this split is essential — power_board and
flight_board have ~90+ chips each and won't fit on a single face.
"""
from __future__ import annotations

from smash.state.chip import Chip


# Footprint-name prefixes for parts small enough that AT&S ECP can
# embed them in the laminate cavity (~0.5 mm depth typical). Lifted
# verbatim from tools/layout_gen/placer.py:BomEntry.is_embeddable_passive.
# EXCLUDES tantalum caps (EIA-3528 ≈ 1.9 mm tall — too thick) — those
# stay on the surface.
_EMBEDDABLE_FP_PREFIXES = (
    "Resistor_SMD:R_0402",
    "Resistor_SMD:R_0603",
    "Inductor_SMD:L_0402",
    "Inductor_SMD:L_0805",
    "Capacitor_SMD:C_0402",
    "Capacitor_SMD:C_0603",
    "Capacitor_SMD:C_0805",
    "Capacitor_SMD:C_1206",
)
_TEST_POINT_FP_PREFIX = "TestPoint:"
_POGO_PAD_FP_PREFIX = "Pogo_Pad"
_MATING_PAD_REF_PREFIX = "P_"
_ECM_DESCRIPTION_FLAG = "[DNP/ECM]"


def is_mating_pad(chip: Chip) -> bool:
    """Board-to-board LGA pad: refs `P_*` mate with `J_*` on the
    adjacent tile. The `P_` side lives on the bottom face."""
    return chip.ref.startswith(_MATING_PAD_REF_PREFIX)


def is_test_point(chip: Chip) -> bool:
    """KiCad TestPoint-library footprint (probe pad or RF launch) or a
    pogo landing pad. These sit on the bottom alongside the ECM-embedded
    passives so the top stays clean for the silicon. The activation
    pogo array specifically MUST be bottom-face: once the snake folds,
    the bottom face is internal, so the bench-fixture connectors end up
    buried (inaccessible) rather than exposed on the outside."""
    if chip.footprint is None:
        return False
    return (chip.footprint.name.startswith(_TEST_POINT_FP_PREFIX)
            or chip.footprint.name.startswith(_POGO_PAD_FP_PREFIX))


def is_embeddable_passive(chip: Chip) -> bool:
    """0402/0603 R/L/C plus 0805/1206 C — sized for AT&S ECP embedding.
    Also includes anything tagged `[DNP/ECM]` in its description (the
    explicit ECM-route flag from the flight build)."""
    fp = chip.footprint
    if fp is None:
        return False
    if any(fp.name.startswith(p) for p in _EMBEDDABLE_FP_PREFIXES):
        return True
    if _ECM_DESCRIPTION_FLAG in (chip.description or ""):
        return True
    return False


def goes_to_bottom(chip: Chip) -> bool:
    """True iff the chip belongs on the bottom face per the design's
    declarative rule (mating pad ∨ test point ∨ embeddable passive).

    `chip.feature == "rf"` is a per-component opt-out: RF chain
    passives (impedance-matching networks, baluns, etc.) must sit on
    the SAME face as the radiator and use controlled-impedance traces,
    so they're held on the top face even when their footprint family
    would normally be embeddable. The RF antenna chip itself isn't a
    Chip — it's an Antenna — and is handled separately.

    `chip.feature == "clock"` is the converse per-component opt-in: a
    MEMS clock oscillator on a dense BGA tile rides the bottom face,
    directly beneath the host's OSC balls — shortest clock route and it
    keeps the crowded top face for the processor + memory."""
    if getattr(chip, "feature", None) == "rf":
        return False
    if getattr(chip, "feature", None) in ("clock", "bottom"):
        # "clock": MEMS oscillator beneath the host's OSC balls. "bottom": an
        # explicit per-component opt-in for small / legged support chips that
        # survive on the internal bottom face under setback — e.g. the radar's
        # SOT-23 bucks (compliant leads + low mass), kept off the nose_cap-facing
        # top so they don't need their own coupling cutout. Tall/heavy parts
        # (bulk caps) are NOT opted in — they stay on top.
        return True
    # aft_end_board is the outboune wire activation board (2026-07-31): its carries a selector for with outbound sector to activate
    # fin_ble_board (the battery-compartment ceiling since the same reorder)
    # needs no special rule: the default below sends its mating pads
    # (P_CELL_CONTACTS) + embeddable passives to the BOTTOM face — into the
    # compartment's free trefoil space — while the fins cluster stays on
    # top; the piezo disc + comparator column are face-locked "top" in
    # locked_placements (the lock's face wins), keeping the ceramic
    # compression-loaded and the high-Z PIEZO_P column together.
    if getattr(chip, "board_tag", None) == "aft_end_board":
        return is_test_point(chip)
    # The activation_interface tile is near the bottom
    # Any component relocated here keeps its passives top-side.
    if getattr(chip, "board_tag", None) == "activation_interface":
        return is_mating_pad(chip) or is_test_point(chip)
    return (is_mating_pad(chip)
            or is_test_point(chip)
            or is_embeddable_passive(chip))
