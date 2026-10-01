"""Issue — one validation finding against a Design (NamedTuple)."""
from __future__ import annotations

from typing import NamedTuple


class Issue(NamedTuple):
    severity: str                        # "error" | "warning" | "info"
    rule: str                            # short tag, e.g. "ddr3_net_complete"
    message: str
    refs: tuple = ()                     # tuple of part refs / net names
