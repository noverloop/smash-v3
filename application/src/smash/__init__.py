"""Smash design data-model library.

Public API — re-exports the core dataclasses + builders so callers
can write `from smash import Design, Chip, ...` without knowing the
internal module layout. State lives in `smash.state` (one class per
file under that package); this module is the thin convenience surface
on top of it.
"""

from smash.state import (
    # identity
    Chip, Battery, Pin, Pad, Footprint, Net, NET_KINDS,
    # validators
    Issue, validator, VALIDATORS,
    # stackup
    Dielectric, Layer, fit_stackup, StackupSpec,
    # fab capabilities
    FabProfile, default_fab_profile,
    # geometry regions
    KeepoutRegion, CavityRegion, FlexStrip,
    # topology + placement
    Flex, BoardEdge, Placement,
    # routing (conductor geometry)
    Track, Via, Zone,
    # 3D resolution (board-local)
    track_polyline_3d, via_segment_3d, zone_polygon_3d,
    pad_xyz, chip_body_3d, board_solder, chip_underfill,
    copper_on_layer, layer_elevations, stack_height_mm,
    # containers
    Board, Panel,
    # netlist
    Netlist,
    # top-level + helpers
    Design, BoardView, NetHandle, SmashState,
)
from smash import components_md
from smash import parts
from smash import sim


__version__ = "0.1.0"

__all__ = [
    "Chip", "Battery", "Pin", "Pad", "Footprint",
    "Net", "NET_KINDS",
    "Design", "BoardView", "NetHandle",
    "Issue", "validator", "VALIDATORS",
    "Dielectric", "Layer", "fit_stackup", "StackupSpec",
    "FabProfile", "default_fab_profile",
    "KeepoutRegion", "CavityRegion", "FlexStrip",
    "Flex", "BoardEdge", "Placement",
    "Track", "Via", "Zone",
    "track_polyline_3d", "via_segment_3d", "zone_polygon_3d",
    "pad_xyz", "chip_body_3d", "board_solder", "chip_underfill",
    "copper_on_layer", "layer_elevations", "stack_height_mm",
    "Board", "Panel", "Netlist", "SmashState",
    "components_md", "parts", "sim",
    "__version__",
]
