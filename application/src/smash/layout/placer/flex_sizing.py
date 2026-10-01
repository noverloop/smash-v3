"""Per-flex-link width computation.

Each flex strip in the snake chain gets a width based on how many nets
cross it and what class they are. Mirrors
`tools/layout_gen/placer.py:count_cross_tile_signals`:

  net class      width contribution (mm)
  ─────────      ──────────────────────
  ground         0.00     (assumed to use plane copper everywhere)
  power_hi       1.50     (battery rail, >3.6 V)
  power_md       0.50     (post-regulator rail)
  signal         0.15

For each net spanning tiles {i₀, …, iₙ} on the snake chain, every link
in [min, max) gets += contribution. After tallying, every non-zero
link gets += FLEX_MARGIN_MM = 3.0 (bend relief + edge clearance).
"""
from __future__ import annotations

from collections import defaultdict

from smash.state.chip import Chip
from smash.state.design import Design


# Per-net contribution to flex width, assuming a 4-layer flex stackup
# (GND / SIG / SIG / GND — two signal layers + two reference planes).
# The smash design fixes the flex at 4L by spec, so these constants
# are the right granularity. If a future variant uses 2L flex (single
# signal layer), every value here doubles.
#
#   signal 0.15 mm  ←  ~0.075 mm trace + 0.075 mm space, split across
#                      two signal layers (so 1 net = 0.075 mm on each)
#   power_md 0.50 mm ← 5× signal — typical decoupling-rail width
#   power_hi 1.50 mm ← battery rail, sized for fault current
#   gnd 0.00 mm     ← uses GND-plane copper on layers 1 + 4, no extra width
FLEX_WIDTH_PER_CLASS_MM: dict[str, float] = {
    "gnd":      0.00,
    "power_hi": 1.50,
    "power_md": 0.50,
    "signal":   0.15,
}
FLEX_MARGIN_MM = 3.0
"""Per-link constant overhead: flex bend relief + edge clearance for
fab tolerance. Added once to every link that carries anything."""

POWER_HI_THRESHOLD_V = 3.6
"""Above this, a power net is classified `power_hi` (wider trace).
Below, `power_md`. Threshold sits just above 3.3 V to cleanly split
battery rails (3.7-4.2 V) from post-regulator rails (≤3.3 V)."""


def net_class(net) -> str:
    """Classify a Net (or NetHandle) by kind + voltage. Returns one of
    the four keys of FLEX_WIDTH_PER_CLASS_MM. Bus / diff / clock nets
    all count as signal — they carry data, not power."""
    # NetHandle is the chainable wrapper Design.add_*_net returns;
    # unwrap to the underlying Net so callers can pass either.
    if hasattr(net, "net") and hasattr(net.net, "kind"):
        net = net.net
    if net.kind == "ground":
        return "gnd"
    if net.kind == "power":
        v = net.voltage_v or 0.0
        return "power_hi" if v > POWER_HI_THRESHOLD_V else "power_md"
    return "signal"


def compute_link_widths(
    design: Design,
    panel,
) -> tuple[dict, dict]:
    """For the panel's snake chain, return (per_link_width_mm, breakdown).

    `per_link_width_mm` is `{k: total_width_mm}` for k in
    [0, len(snake_chain)-1). Links with no crossing nets are omitted.
    `breakdown` is `{k: {class: count}}` — useful for diagnostics.
    """
    chain = panel.snake_chain or []
    tile_idx = {name: i for i, name in enumerate(chain)}

    # ref → snake-chain tile index
    ref_to_idx: dict[str, int] = {}
    for chip in design.chips:
        if chip.board_tag in tile_idx:
            ref_to_idx[chip.ref] = tile_idx[chip.board_tag]

    breakdown: dict = defaultdict(lambda: defaultdict(int))
    widths:    dict = defaultdict(float)

    for net in design.nets:
        tiles_seen = {ref_to_idx[ref] for ref, _ in net.pins
                      if ref in ref_to_idx}
        if len(tiles_seen) <= 1:
            continue
        cls = net_class(net)
        w = FLEX_WIDTH_PER_CLASS_MM[cls]
        lo, hi = min(tiles_seen), max(tiles_seen)
        for k in range(lo, hi):
            breakdown[k][cls] += 1
            widths[k] += w

    # Margin on every link that carries anything
    for k in widths:
        widths[k] += FLEX_MARGIN_MM

    return dict(widths), {k: dict(v) for k, v in breakdown.items()}
