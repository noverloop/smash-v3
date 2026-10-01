"""Placement record — `(position_mm, rotation_deg, item, face, locked)`.

Used wherever a container holds positioned items:
  - `Panel.board_placements`  — boards on the panel canvas
  - `Board.chip_placements`   — chips on a board (board-local)
  - `Board.cavity_placements`
  - `Board.keepout_placements`

The contained `item` is position-free; the container owns this record.

`rotation_deg` rotates the item in-plane about its own centre BEFORE
the position offset is applied.

`face` is the mount side for the item:
  - "top"    — F.Cu side of the parent board
  - "bottom" — B.Cu side
For a Board placed on a Panel the same notion applies to which side of
the panel the board's primary face points to.

`locked = True` means the placer / router cannot modify this entry.
Use for hand-anchored chips, forced rotations, manually-tuned traces.
Unlocked entries are free for the algorithm to (re)compute.
"""
from __future__ import annotations

from typing import Any, NamedTuple


class Placement(NamedTuple):
    position_mm: tuple[float, float]
    rotation_deg: float
    item: Any
    face: str = "top"
    locked: bool = False
