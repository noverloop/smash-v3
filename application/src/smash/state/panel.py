"""Panel — placed multi-board container.

`board_placements` records where each Board sits on the panel canvas
(mm, y-down) with its rotation. `flex_strips` carries the inter-board
flex strips (already in panel-canvas coords because a strip spans two
boards).

The Boards inside each Placement remain template-like: their own
`chip_placements / cavity_placements / keepout_placements` describe
what's on them in board-local coords. The legacy `PanelLayout` (in
`smash.layout.panel`) is still around for the dict-of-tiles bridge to
the existing tools/-side placer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from smash.state.geometry import FlexStrip
from smash.state.topology.placement import Placement


@dataclass
class Panel:
    board_placements: list[Placement] = field(default_factory=list)
    flex_strips: list[FlexStrip] = field(default_factory=list)
