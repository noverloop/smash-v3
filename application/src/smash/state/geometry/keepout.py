"""KeepoutRegion — one rule-area zone, position-free template.

The Board / Panel that contains the region carries the
`(position_mm, rotation_deg)` via a `Placement`. Polygon corners are
in the region's own local frame.

The exporter emits one `pcbnew.ZONE` per (region × layer) — KiCad's
multi-layer zones don't compose cleanly for rule areas.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KeepoutRegion:
    name: str
    layers: list[str]
    polygon: list[tuple[float, float]]
    disallow_tracks: bool = False
    disallow_vias: bool = True
    disallow_pads: bool = True
    disallow_footprints: bool = True
    disallow_zone_fills: bool = False
