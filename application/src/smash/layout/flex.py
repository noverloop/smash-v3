"""Flex strip + keepout builder functions.

Construction helpers that produce `smash.state` region dataclasses
(KeepoutRegion / CavityRegion / FlexStrip live in
`smash.state.geometry`). These are pure functions — algorithm code —
no dataclasses live here.

Polygons are KiCad canvas coords (y-down) in mm. Layer names match
KiCad: "F.Cu", "B.Cu", "In1.Cu", "Eco1.User", …
"""
from __future__ import annotations

from smash.layout.geometry import Line, chord_corners
from smash.state.geometry import KeepoutRegion, FlexStrip


__all__ = [
    "flex_bend_keepout", "cavity_routing_keepout", "inter_tile_flex_strip",
]


_FLEX_BEND_DEFAULTS = dict(
    disallow_tracks=False,
    disallow_vias=True,
    disallow_pads=True,
    disallow_footprints=True,
    disallow_zone_fills=False,
)


def flex_bend_keepout(corners_mm: list[tuple[float, float]],
                      name: str) -> KeepoutRegion:
    """Rule-area covering the flex-strip rectangle on all Cu layers."""
    return KeepoutRegion(
        name=name,
        layers=["*.Cu"],
        polygon=list(corners_mm),
        **_FLEX_BEND_DEFAULTS,
    )


def cavity_routing_keepout(ring_mm: list[tuple[float, float]],
                           layers: list[str],
                           name: str) -> KeepoutRegion:
    """Per-layer keepout blocking everything inside a milled cavity."""
    return KeepoutRegion(
        name=name,
        layers=list(layers),
        polygon=list(ring_mm),
        disallow_tracks=True,
        disallow_vias=True,
        disallow_pads=True,
        disallow_footprints=True,
        disallow_zone_fills=True,
    )


def inter_tile_flex_strip(
    cx_a_mm: float, cy_a_mm: float, angle_a_deg: float,
    cx_b_mm: float, cy_b_mm: float, angle_b_deg: float,
    width_mm: float,
    radius_mm: float,
    *,
    name: str = "flex_bend",
) -> FlexStrip:
    """Build a `FlexStrip` connecting tile A → tile B.

    Pairing rule: A.ccw ↔ B.cw, A.cw ↔ B.ccw → non-crossing rectangle,
    CCW winding."""
    a_ccw, a_cw = chord_corners(cx_a_mm, cy_a_mm, angle_a_deg,
                                width_mm, radius_mm)
    b_ccw, b_cw = chord_corners(cx_b_mm, cy_b_mm, angle_b_deg,
                                width_mm, radius_mm)

    edges = [
        Line(a_ccw[0], a_ccw[1], b_cw[0],  b_cw[1]),
        Line(a_cw[0],  a_cw[1],  b_ccw[0], b_ccw[1]),
    ]
    keepout = flex_bend_keepout([a_ccw, b_cw, b_ccw, a_cw], name=name)
    return FlexStrip(name=name, edge_segments=edges, keepout=keepout)
