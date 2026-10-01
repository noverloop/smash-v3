"""Via — one layer-spanning plated hole."""
from __future__ import annotations

import dataclasses


VIA_KINDS = ("signal", "thermal", "stitching")


@dataclasses.dataclass
class Via:
    """One plated through/blind/buried via.

    `position_mm` is the via centre in board-local mm (math-y-up).
    `from_layer` / `to_layer` name the Cu layers the barrel spans
    ("F.Cu".."B.Cu" for a through via; inner names for blind/buried).
    `drill_mm` is the finished hole diameter, `pad_diameter_mm` the
    annular pad on the copper layers.

    `kind` discriminates intent — "signal" (routing), "thermal" (heat
    path under a hot die), or "stitching" (plane/shield tie). `filled`
    marks a copper/resin-filled barrel: relevant to the z-axis thermal
    path (a filled via shorts the FR4 dielectric resistance, an open
    one carries only the plated barrel).
    """
    net: str | None                     # connected net name (None if unbound)
    position_mm: tuple                  # (x, y) board-local, math-y-up
    drill_mm: float
    pad_diameter_mm: float
    from_layer: str = "F.Cu"
    to_layer: str = "B.Cu"
    kind: str = "signal"                # one of VIA_KINDS
    filled: bool = False                # copper/resin-filled barrel
    note: str | None = None             # free-form catch-all

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["position_mm"] = list(self.position_mm)
        return d
