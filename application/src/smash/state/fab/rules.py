"""DesignRules — the factory's DRC limits."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class DesignRules:
    """Minimum manufacturable geometry — the DRC envelope. Defaults are
    harvested from the project's `.kicad_dru` (archived
    `tools/layout_gen/placer.py` template): a mainstream multilayer
    process with an HDI/microvia option.

    `max_aspect_ratio` is finished board thickness ÷ drill diameter (a
    PTH plating limit). The `micro_*` fields apply to laser microvias.
    """
    # ── plated through-hole / standard ──────────────────────────────
    min_trace_mm: float = 0.20
    min_space_mm: float = 0.20
    min_drill_mm: float = 0.25
    min_via_diameter_mm: float = 0.45
    min_annular_ring_mm: float = 0.10
    max_aspect_ratio: float = 10.0          # thickness ÷ drill
    # ── clearances ──────────────────────────────────────────────────
    edge_clearance_mm: float = 0.25
    hole_to_hole_mm: float = 0.25
    silk_to_pad_mm: float = 0.15
    # ── HDI microvia ────────────────────────────────────────────────
    micro_min_drill_mm: float = 0.15
    micro_min_via_diameter_mm: float = 0.25
    micro_min_annular_mm: float = 0.05
    # ── board envelope ──────────────────────────────────────────────
    min_board_thickness_mm: float = 0.40
    max_board_thickness_mm: float = 3.20
    note: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DesignRules":
        return cls(**d)
