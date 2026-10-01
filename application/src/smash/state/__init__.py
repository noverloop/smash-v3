"""smash.state — single source of truth for design state.

Every dataclass / NamedTuple describing a piece of the design lives
under this package, one class per file. `smash.layout`, `smash.parts`,
`smash.export`, and `smash.validators` are algorithms that operate
on this state.
"""
from smash.state.pad import Pad
from smash.state.footprint import Footprint
from smash.state.pin import Pin
from smash.state.chip import Chip
from smash.state.battery import Battery
from smash.state.antenna import Antenna
from smash.state.net import Net, NET_KINDS
from smash.state.issue import Issue
from smash.state.validators import validator, VALIDATORS
from smash.state.stackup import Dielectric, Layer, fit_stackup, StackupSpec
from smash.state.fab import FabProfile, default_fab_profile
from smash.state.geometry import KeepoutRegion, CavityRegion, FlexStrip
from smash.state.topology import Flex, BoardEdge, Placement
from smash.state.routing import Track, Via, Zone
from smash.state.cu_coin import CuCoinInsert
from smash.state.geometry3d import (
    track_polyline_3d, via_segment_3d, zone_polygon_3d,
    pad_xyz, chip_body_3d, board_solder, chip_underfill,
    copper_on_layer, layer_elevations, stack_height_mm,
)
from smash.state.board import Board
from smash.state.panel import Panel
from smash.state.netlist import Netlist
from smash.state.design import Design, BoardView, NetHandle
from smash.state.smash_state import SmashState


__all__ = [
    # identity
    "Pad", "Footprint", "Pin", "Chip", "Battery", "Antenna",
    "Net", "NET_KINDS",
    # validators
    "Issue", "validator", "VALIDATORS",
    # stackup
    "Dielectric", "Layer", "fit_stackup", "StackupSpec",
    # fab capabilities
    "FabProfile", "default_fab_profile",
    # geometry regions
    "KeepoutRegion", "CavityRegion", "FlexStrip",
    # topology + placement
    "Flex", "BoardEdge", "Placement",
    # routing (conductor geometry)
    "Track", "Via", "Zone",
    # 3D resolution (board-local)
    "track_polyline_3d", "via_segment_3d", "zone_polygon_3d",
    "pad_xyz", "chip_body_3d", "board_solder", "chip_underfill",
    "copper_on_layer", "layer_elevations", "stack_height_mm",
    # containers
    "Board", "Panel",
    # netlist
    "Netlist",
    # top-level + helpers
    "Design", "BoardView", "NetHandle",
    "SmashState",
]
