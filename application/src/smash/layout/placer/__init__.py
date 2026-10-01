"""`smash.layout.placer` — board-local placement of chips.

Ported from `tools/layout_gen/placer.py`. Scope (per the P1 plan):

- `grid`     — footprint bbox, rotation snap, world-coord transforms,
               AABB overlap. The geometric primitives used by everything
               downstream.
- `pack`     — placement of unanchored chips into available board area
               (TODO).
- `cavities` — placement of chips destined for a cavity well (TODO).

`place_design(design, board)` (TODO) orchestrates locks → cavities → pack.

This package operates entirely on the smash data model; it does not
import pcbnew, and it does not load BOMs or footprints from disk —
those already live on `Board` and `Chip` respectively.
"""
from smash.layout.placer.grid import (
    INTER_CHIP_PAD_MARGIN_MM,
    footprint_bbox_mm,
    placement_extents_mm,
    rects_overlap,
    rotate_point,
    snap_rotation,
    world_pad_position,
)
from smash.layout.placer.pack import (
    COMP_GAP_MM,
    pack_radial,
)
from smash.layout.placer.cavities import (
    attach_cavities_to_spacers,
)
from smash.layout.placer.face_split import (
    goes_to_bottom,
    is_embeddable_passive,
    is_mating_pad,
    is_test_point,
)
from smash.layout.placer.orchestrator import (
    DesignPlacementReport,
    PlacementStats,
    place_design,
)
from smash.layout.placer.spacer_sizing import (
    gap_required_thickness,
    size_backbone_spacers,
)

__all__ = [
    "INTER_CHIP_PAD_MARGIN_MM",
    "COMP_GAP_MM",
    "DesignPlacementReport",
    "PlacementStats",
    "attach_cavities_to_spacers",
    "gap_required_thickness",
    "size_backbone_spacers",
    "footprint_bbox_mm",
    "goes_to_bottom",
    "is_embeddable_passive",
    "is_mating_pad",
    "is_test_point",
    "pack_radial",
    "place_design",
    "placement_extents_mm",
    "rects_overlap",
    "rotate_point",
    "snap_rotation",
    "world_pad_position",
]
