"""Validators for the design + the files emitted by smash.export.

Two categories:

  - **Design validators** check the electrical model itself.
    Today: STM32 alternate-function (pinmux) consistency.
  - **Format validators** check output-format well-formedness.
    Today: Specctra DSN.

Design-time electrical validators registered via the `@validator`
decorator in `smash.design` (no-floating-chips, unique-refs, etc.)
continue to live there; this module hosts the larger validators that
need their own files.
"""

from smash.validators.stm32_pinmux import (
    check_pinmux,
    find_pins,
    af_assignments,
)
from smash.validators.specctra import (
    validate_specctra_dsn,
    parse_dsn,
    DsnIssue,
    DsnPcbDesign,
)
from smash.validators.placement import (
    check_chip_overlaps,
    OverlapIssue,
    assert_no_locked_overlaps,
    LockedOverlapError,
    check_spacer_chip_clearance,
    ClearanceIssue,
)
from smash.validators.fab import check_fab_rules

__all__ = [
    # design validators
    "check_pinmux",
    "find_pins",
    "af_assignments",
    # placement validators
    "check_chip_overlaps",
    "OverlapIssue",
    "assert_no_locked_overlaps",
    "LockedOverlapError",
    "check_spacer_chip_clearance",
    "ClearanceIssue",
    # fab-rule validators
    "check_fab_rules",
    # format validators
    "validate_specctra_dsn",
    "parse_dsn",
    "DsnIssue",
    "DsnPcbDesign",
]
