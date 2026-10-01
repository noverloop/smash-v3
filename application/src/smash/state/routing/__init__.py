"""smash.state.routing — board-local conductor geometry.

Tracks (routed traces), vias (layer-spanning holes), and zones (copper
pours). These live on a `Board` alongside `chip_placements`; the panel
graph (`topology/`) and design-intent regions (`geometry/`) are
separate concerns. All coordinates are board-local mm, math-y-up.
"""
from smash.state.routing.track import Track
from smash.state.routing.via import Via, VIA_KINDS
from smash.state.routing.zone import Zone

__all__ = ["Track", "Via", "VIA_KINDS", "Zone"]
