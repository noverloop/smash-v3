"""Track — one routed copper trace on a single layer."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Track:
    """One routed trace: a constant-width polyline on a single Cu layer.

    `path` is the trace centreline in board-local mm (math-y-up — the
    same convention as `Pad.position_mm` and `Placement.position_mm`),
    a list of >=2 `(x, y)` vertices. A KiCad/Freerouting `(wire (path
    LAYER WIDTH x y ...))` maps to exactly one Track.

    For the thermal model, a Track contributes lateral copper on `layer`
    along its length × `width_mm`; for IR-drop / current-density it
    carries `net`.
    """
    net: str | None                     # connected net name (None if unbound)
    layer: str                          # "F.Cu", "In3", "B.Cu", ...
    width_mm: float
    path: list                          # [(x, y), ...] board-local, math-y-up
    note: str | None = None             # free-form catch-all

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["path"] = [list(pt) for pt in self.path]
        return d
