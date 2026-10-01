"""Pad — one conductor on a Footprint."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Pad:
    """One conductor of a Footprint — physical pad geometry.

    `num` matches the Pin.num used in electrical wiring. `position_mm`
    is relative to the footprint's local origin (the placer translates
    + rotates the whole footprint by the Chip's position_mm /
    rotation_deg when it lands on a board).
    """
    num: str                          # "K10", "1", "+", "TAB"
    position_mm: tuple                # (x, y) relative to footprint origin
    size_mm: tuple                    # pad dimensions (W, H)
    shape: str = "rect"               # "round" | "rect" | "oval" | "roundrect" | "custom"
    layer: str = "F.Cu"               # "F.Cu" | "B.Cu" | "*.Cu" (PTH spans all)
    drill_mm: float | None = None     # PTH drill; None = SMD
    paste: bool = True                # in solder-paste mask?
    solder_mask_expansion_mm: float | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["position_mm"] = list(self.position_mm)
        d["size_mm"]     = list(self.size_mm)
        return d

