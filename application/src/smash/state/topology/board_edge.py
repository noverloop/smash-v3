"""BoardEdge — one outgoing edge on a Board's connectivity graph.

Stored in `Board.edges[direction]`. Reciprocal edge on the neighbour
is registered automatically by `Board.add_<direction>()`.
"""
from __future__ import annotations

from typing import NamedTuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from smash.state.board import Board
    from smash.state.topology.flex import Flex


class BoardEdge(NamedTuple):
    direction: str             # "N" | "E" | "S" | "W"
    other: "Board"
    flex: "Optional[Flex]"     # None for kind="mate"
    kind: str                  # "snake" | "branch" | "mate"
