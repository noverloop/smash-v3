"""Layout pipeline tuning knobs and design-wide constants.

All literal magic numbers used by the placer / flex generator / outline
generator live here so the algorithm code stays readable. Values come
from `tools/layout_gen/placer.py`; the comments preserve the why.
"""
from __future__ import annotations


# ── packing geometry ────────────────────────────────────────────────────

COMP_GAP_MM = 0.4
"""Inter-component gap (added on top of the courtyard) during packing."""

INTER_CHIP_PAD_MARGIN_MM = 0.0
"""Per-pad expansion margin when computing placement bbox.

Placer bbox = max(pad_bbox + margin, courtyard_bbox). For SamacSys
footprints whose courtyard sits flush with the pads, this margin
guarantees minimum pad-to-pad gap between adjacent chips even when
courtyards touch — needed by bga_fanout (surface-escape traces
terminate at the chip's pad bbox).
"""

BOARD_MARGIN_MM = 0.4
"""Minimum component bbox → Edge.Cuts distance (IPC class 2 minimum)."""

EDGE_CUTS_WIDTH_MM = 0.15
"""Edge.Cuts line width — fab CAM operators prefer ~0.10-0.15 mm."""

ARC_SEGMENTS_PER_2PI = 96
"""Arc → segment count for full circle approximation. 96 is smooth
enough that fab CAM treats it as a circle; finer is wasted bytes."""


# ── flex sizing (per net class) ─────────────────────────────────────────

FLEX_WIDTH_PER_CLASS_MM = {
    "gnd":      0.0,    # plane on L2, no linear contribution
    "power_hi": 1.5,    # wider region for current capacity
    "power_md": 0.5,    # own region on L3 with clearance
    "signal":   0.15,   # split across L1+L4, half-pitch
}
"""4L flex assumption: signals on L1+L4, GND on L2, power on L3."""

FLEX_MARGIN_MM = 3.0
"""Bend relief + edge clearance added to every populated link."""


# Per-ref locked placements (board-local position + rotation + reason)
# moved to `smash/data/locked_placements.json` (loaded by
# `smash.layout.locked.load_locked_placements`). Placer reads it before
# the radial packer runs.
