"""Dynamic backbone-spacer thickness — size each spacer to the gap it bridges.

A spacer between two rigid tiles must clear, at every (x,y), the SUM of the
lower tile's top-face chip height and the upper tile's bottom-face chip height:
opposing parts share the gap, so a tall part sitting over another tall part
collides unless the spacer is at least their combined height. The minimum
spacer thickness is therefore

    max over (x,y) of [ lower_top_h(x,y) + upper_bottom_h(x,y) ] + clearance,

rounded up to 0.1 mm and floored at a practical minimum (via aspect ratio /
potting flow / handling a thin FR4 disc).

Heights come from `smash.export.model_height.footprint_height_mm`
(datasheet height_mm → IPC-name-encoded height → 2 mm worst-case). Flat
placements — LGA lands (J_/P_), mating pads, test points (TP_), and SP*
spacer support pads — are excluded.

Battery-compartment spacers are NOT sized here: their thickness is fixed by the
cell length (`thickness_override_mm` set at panel build), not by clearance.
"""
from __future__ import annotations

import math

from smash.export.model_height import footprint_height_mm
from smash.layout.placer.grid import placement_extents_mm

SPACER_CLEARANCE_MM = 0.3        # gap margin over the stacked-component height
SPACER_MIN_THICKNESS_MM = 2.0    # practical floor (via aspect / potting / handling)
_FLAT_PREFIXES = ("J_", "P_", "TP_", "SP")


def _face_chips(board, face):
    """[(height_mm, (lo_x,lo_y,hi_x,hi_y))] of real components on `face`."""
    out = []
    for p in board.chip_placements:
        if p.face != face:
            continue
        if str(getattr(p.item, "ref", "")).startswith(_FLAT_PREFIXES):
            continue
        fp = getattr(p.item, "footprint", None)
        if fp is None:
            continue
        h, _src = footprint_height_mm(fp)
        # The CHIP's datasheet height outranks anything the footprint chain
        # can infer, and some footprints carry no parseable height at all
        # (`SAMESKY_UJ20-…` is a 4.30 mm receptacle that resolves to the
        # 2.0 mm assumption). Take the larger — never under-size a gap.
        chip_h = getattr(p.item, "height_mm", None)
        if chip_h:
            h = max(h, float(chip_h))
        try:
            bb = placement_extents_mm(p, fp)
        except Exception:
            continue
        out.append((h, bb))
    return out


def _xy_overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def gap_required_thickness(
    lower,
    upper,
    *,
    clearance: float = SPACER_CLEARANCE_MM,
    floor: float = SPACER_MIN_THICKNESS_MM,
) -> float:
    """Minimum spacer thickness (mm) for the `lower`↔`upper` gap — the
    overlap-aware (lower-top + upper-bottom) coincidence + clearance, rounded
    up to 0.1 mm and floored at `floor`. `lower` mounts the spacer on its TOP
    face; `upper` on its BOTTOM."""
    lt = _face_chips(lower, "top")
    ub = _face_chips(upper, "bottom")
    worst = 0.0
    for h, _bb in lt + ub:                 # single chip vs the bare board above
        worst = max(worst, h)
    for hl, bl in lt:                      # opposing chips that overlap → add
        for hu, bu in ub:
            if _xy_overlap(bl, bu):
                worst = max(worst, hl + hu)
    needed = math.ceil((worst + clearance) * 10.0) / 10.0   # → 0.1 mm
    return max(needed, floor)


def size_backbone_spacers(
    panel,
    boards: dict,
    *,
    clearance: float = SPACER_CLEARANCE_MM,
    floor: float = SPACER_MIN_THICKNESS_MM,
) -> dict:
    """Set `thickness_override_mm` on every backbone spacer in the snake to the
    thickness the gap it bridges actually needs. Skips battery-compartment
    spacers (fixed by cell length). Call AFTER `place_design` (needs the placed
    chips). Returns ``{spacer_name: thickness_mm}``."""
    chain = panel.snake_chain or []
    sized: dict = {}
    for i, name in enumerate(chain):
        b = boards.get(name)
        if b is None or not getattr(b, "is_spacer", False):
            continue
        if "battery" in name:              # cell-length column — fixed
            continue
        lower = boards.get(chain[i - 1]) if i > 0 else None
        upper = boards.get(chain[i + 1]) if i + 1 < len(chain) else None
        if lower is None or upper is None:
            continue
        t = gap_required_thickness(lower, upper, clearance=clearance, floor=floor)
        b.thickness_override_mm = t
        sized[name] = t
    return sized
