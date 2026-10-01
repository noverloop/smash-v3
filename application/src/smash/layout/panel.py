"""PanelLayout — legacy dict-of-tiles bridge to the tools/-side placer.

The new `Panel` container (with `board_placements` + `flex_strips`)
lives in `smash.state.panel`; this module keeps the dict form because
the existing `tools/layout_gen/placer.py` consumes it directly.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PanelLayout:
    """2D grid layout of tiles on the EVB panel + ordered snake chain.

    See `tools/layout_gen/placer.py:PanelLayout` for the full per-field
    rationale (kept short here to avoid duplicating prose; the original
    source is canonical for design notes).
    """
    tiles: dict
    snake_chain: list
    tile_outlines: dict = None
    tile_diameters: dict = None
    branches: list = None
    tile_rect_dimensions: dict = None
    branch_flex_lengths: dict = None
    branch_s_fold: set = None      # {(parent, child)} drawn with an S-turn
    spacer_edge_keepout_mm: float = 0.0
    spacer_centre_support_radius_mm: float = 0.0
    tile_top_substrate: dict = None
    tile_al_backing_mm: dict = None
    snake_flex: bool = True        # False ⇒ snake tiles joined ONLY by the
                                   # board-to-board LGA lands through the
                                   # spacers — no snake flex strips drawn, and
                                   # no flex-launch chords cut at the snake
                                   # interfaces (frees that edge area for
                                   # lands). Branch/module flexes unaffected.
                                   # Set False by the panel builders.

    # ── folded-stack height ──────────────────────────────────────────

    def stack_height_mm(self, boards: dict) -> float:
        """Axial height of the folded accordion = sum of the z-thickness
        of every tile in the snake chain (rigid boards + their spacers).
        Branch tiles (nfc/qpd/camera) fold radially off the stack, so
        they aren't in `snake_chain` and don't count."""
        return sum(boards[n].thickness_mm
                   for n in self.snake_chain if n in boards)
