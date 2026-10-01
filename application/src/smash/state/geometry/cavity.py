"""CavityRegion — one milled pocket on a Board face."""
from __future__ import annotations

from dataclasses import dataclass, field

from smash.state.geometry.keepout import KeepoutRegion


@dataclass
class CavityRegion:
    """A milled cavity on one face of a Board (typically a spacer).

    `exterior_polygon` corners and `interior_holes` are in the region's
    own local frame. The parent Board's `cavity_placements` list owns
    the `(position_mm, rotation_deg)` record.

    `face` is "top" or "bottom"; the exporter writes the polygon on
    Eco1.User (top) or Eco2.User (bottom) and adds the `depth_mm`
    callout next to it. `routing_keepouts` are per-Cu-layer rule areas
    that block routing inside the pocket — placed via the parent
    Board's `keepout_placements`, not stacked inside the cavity.
    """
    name: str
    face: str
    exterior_polygon: list[tuple[float, float]]
    interior_holes: list[list[tuple[float, float]]] = field(default_factory=list)
    depth_mm: float = 0.0
    routing_keepouts: list[KeepoutRegion] = field(default_factory=list)
