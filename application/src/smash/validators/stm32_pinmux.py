"""STM32 alternate-function (pinmux) validator.

Replaces the old `tools/stm32_pinmux/validate.py` + per-MCU intent
files. Intent now travels with each `design.connect(..., af=, intent=)`
call; this validator cross-checks each `Pin.af_assigned` against the
CubeMX-derived `Pin.alt_functions` table that the catalog factory
populated.

Two checks:

  - `af_assignment_unavailable`: pin has been assigned an AF that
    CubeMX's MCU XML says is not one of the pin's alt functions —
    catches typos and pinmux-table changes between CubeMX versions.
  - `af_assignment_conflict`: two pins on the same chip claim the
    same AF (e.g. PB6 = USART1_TX AND PA9 = USART1_TX). USART_TX is
    a one-pin function — picking it on two pins means one of them is
    wrong.

The validator skips chips that have no `alt_functions` populated
(non-STM32 parts).

Use:
    from smash.validators.stm32_pinmux import check_pinmux
    issues = check_pinmux(design)
"""

from __future__ import annotations

from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from smash.state import Design, Issue


# Per-chip AF identifiers that are conflict-free even if reused across
# multiple pins. CubeMX models "GPIO" as one of every I/O pin's signals;
# many pins may legitimately be muxed to plain GPIO on one chip.
_NON_CONFLICTING_AFS = {"GPIO"}


def check_pinmux(design: "Design") -> list:
    """Run both AF checks against every chip in `design`. Returns a list
    of `Issue` objects from `smash.design`."""
    from smash.state import Issue

    issues: list = []
    for chip in design.chips:
        # Only check chips whose factory loaded a CubeMX AF table.
        has_af_table = any(p.alt_functions for p in chip.pins)
        if not has_af_table:
            continue

        # 1. af_assigned ∈ alt_functions
        for pin in chip.pins:
            if pin.af_assigned is None:
                continue
            if not pin.alt_functions:
                # Power / ground / NRST pin — CubeMX has no AF list for
                # it. Skip; an af_assigned on such a pin would be a
                # different kind of bug (assigning an AF to a power pin)
                # but the pinmux validator doesn't own that check.
                continue
            if pin.af_assigned not in pin.alt_functions:
                refs = [chip.ref]
                issues.append(Issue(
                    severity="error",
                    rule="af_assignment_unavailable",
                    message=(
                        f"{chip.ref}.{pin.num} ({pin.name}): AF "
                        f"{pin.af_assigned!r} is not in this pin's "
                        f"CubeMX alt-function table. "
                        f"Available: {sorted(pin.alt_functions)[:6]}..."
                    ),
                    refs=refs,
                ))

        # 2. AF conflict: same AF on two pins of the same chip
        af_to_pins: dict[str, list] = {}
        for pin in chip.pins:
            af = pin.af_assigned
            if af is None or af in _NON_CONFLICTING_AFS:
                continue
            af_to_pins.setdefault(af, []).append(pin)
        for af, pins in af_to_pins.items():
            if len(pins) > 1:
                pin_descrs = ", ".join(
                    f"{p.num}({p.name})" for p in pins
                )
                issues.append(Issue(
                    severity="error",
                    rule="af_assignment_conflict",
                    message=(
                        f"{chip.ref}: AF {af!r} is assigned to "
                        f"{len(pins)} pins ({pin_descrs}). Each "
                        f"single-instance peripheral function can only "
                        f"land on one pin per MCU."
                    ),
                    refs=[chip.ref],
                ))
    return issues


def find_pins(chip, af: str) -> list[str]:
    """Helper: return the ball positions on `chip` that can be muxed to
    `af` according to its CubeMX AF table. Lets the engineer probe
    "which pins on this MCU can do SDMMC2_CK?" without leaving Python.
    """
    out: list[str] = []
    for pin in chip.pins:
        if af in pin.alt_functions:
            out.append(pin.num)
    return out


def af_assignments(chip) -> dict[str, str]:
    """Helper: return the {ball: af} dict for every assigned pin on
    `chip`. Useful for human inspection / reports."""
    return {
        pin.num: pin.af_assigned
        for pin in chip.pins
        if pin.af_assigned is not None
    }
