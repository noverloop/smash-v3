"""FlexStrip — rendered geometry of one inter-board flex strip."""
from __future__ import annotations

from dataclasses import dataclass

from smash.state.geometry.keepout import KeepoutRegion


@dataclass
class FlexStrip:
    """One inter-board flex strip: two parallel Edge.Cuts walls + a
    keepout rule area covering all Cu. Spans two Boards, so its
    geometry lives in panel-canvas coords directly (no parent
    Placement). The Panel records `flex_strips` alongside
    `board_placements`.

    `edge_segments` is a list of `smash.layout.geometry.Line` (imported
    lazily by callers — we don't pull it here to keep state pcbnew-
    free and layout-agnostic)."""
    name: str
    edge_segments: list                  # list[smash.layout.geometry.Line]
    keepout: KeepoutRegion
