"""Flex — one physical flex strip's declared intent.

Carries the construction-time configuration of an inter-board link:
strip width, optional length override, optional bridging spacer. The
geometry of the actual rendered strip lives in
`smash.state.geometry.FlexStrip` (output of the placer).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from smash.state.board import Board


@dataclass
class Flex:
    """One physical flex strip between two Boards.

    width_mm:    nominal strip width. Placer may resize per net-class
                 counts (smash.layout.constants.FLEX_WIDTH_PER_CLASS_MM).
    length_mm:   optional override. Default = grid pitch.
    spacer:      bridging spacer between snake endpoints. Pass a
                 `Board` for full configurability (overrides + future
                 fixation/interconnect pads), or a name string to
                 auto-create a default `Board(name, kind="spacer")`.
                 None on branches.
    s_fold:      branch only — the strip peels off the SIDE of an
                 interconnecting (snake) flex with a short S-bend before
                 the long straight run, instead of leaving a tile edge
                 radially. Lets a deploy branch (camera/qpd) tuck along
                 the snake without claiming its own grid cell. Ignored on
                 snake links.
    branch_side: branch only — overrides the per-panel branch-side
                 default ("N" or "S") set by `wire_straight`. Pass the
                 string "N" or "S" to force this branch off the parent's
                 north or south edge, regardless of the global default.
                 Use this when one parent carries two branches (e.g. the
                 wakeup_board hosts BOTH Yagi tiles, one on N and one
                 on S) — picking the side explicitly avoids leaving the
                 second branch dependent on whichever side was claimed
                 by the first. `None` (default) inherits the global
                 default. Ignored on snake links.
    """
    width_mm: float = 4.0
    length_mm: Optional[float] = None
    spacer: "Board | str | None" = None
    s_fold: bool = False
    branch_side: Optional[str] = None

    def spacer_board(self) -> "Board | None":
        """Return the spacer as a Board (lazily creating a default
        kind='spacer' Board if only a name was passed)."""
        if self.spacer is None:
            return None
        from smash.state.board import Board
        if isinstance(self.spacer, str):
            return Board(name=self.spacer, kind="spacer")
        self.spacer.kind = "spacer"
        return self.spacer
