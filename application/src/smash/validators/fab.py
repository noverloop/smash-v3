"""Fab-rule validators — check routed geometry against a FabProfile.

Turns "our limit is the factory, not ourselves" into an executable
check: every routed track / via on every board is measured against the
fab's DRC envelope (`FabProfile.check_*`). Standalone `check_*(boards)`
like `validators/placement.py` — routing lives on `Board`, so this
takes the boards dict rather than a `Design`.
"""
from __future__ import annotations

from smash.state.fab import default_fab_profile


def check_fab_rules(boards: dict, *, profile=None) -> list:
    """Return an `Issue` for every routed feature that violates the
    fab's design rules. `boards` is `{name: Board}`; `profile` defaults
    to `default_fab_profile()`.

    Checks per board:
      - track width      ≥ rules.min_trace_mm
      - via drill / pad / annular ring within limits
      - via aspect ratio (board thickness ÷ drill) ≤ rules.max_aspect_ratio
    Each Issue's `refs` carries the board name + the feature's net.
    """
    profile = profile or default_fab_profile()
    issues: list = []
    for name, board in boards.items():
        thickness = getattr(board, "thickness_mm", None)
        for t in getattr(board, "tracks", []):
            issues.extend(profile.check_trace(
                t.width_mm, refs=(name, t.net or "?")))
        for v in getattr(board, "vias", []):
            refs = (name, v.net or "?")
            issues.extend(profile.check_via(
                v.pad_diameter_mm, v.drill_mm, refs=refs))
            if thickness:
                issues.extend(profile.check_aspect(
                    thickness, v.drill_mm, refs=refs))
    return issues


def _tile_radius_mm(board) -> float | None:
    """Effective radius for a rigid tile (used as the half-pitch
    contribution to snake-link gap). Mirrors the convention in
    `smash.export.kicad_pcb._tile_radius`."""
    g = getattr(board, "geometry", None)
    if g is None:
        return None
    if g.shape == "circle" and g.diameter_mm:
        return g.diameter_mm / 2.0
    if g.shape == "rect" and g.rect_dimensions:
        # rect-tile flex meets the short edge — half of min dimension
        w, h = g.rect_dimensions
        return min(w, h) / 2.0
    return None


def check_panel_flex(panel, boards: dict, *,
                     profile=None, tile_pitch_mm: float | None = None) -> list:
    """Validate every flex link in the panel against the fab's flex
    envelope.

    For each snake link (consecutive tiles in `panel.snake_chain`):
      - Compute the unrolled flex length: `tile_pitch − r_A − r_B`.
      - Check against `profile.flex.min_zone_length_180()`.

    For each branch in `panel.branches`:
      - Use `panel.branch_flex_lengths[(parent, child)]` directly.
      - Check against same minimum.

    Also runs the rigid-layer-count check on every rigid tile (each
    tile's `Board.layer_count`-or-equivalent must fit
    `flex.rigid_min/max_layers`)."""
    profile = profile or default_fab_profile()
    if profile.flex.R_min_mm is None:
        return []          # no flex process configured — nothing to do
    if tile_pitch_mm is None:
        # Use the same default the kicad_pcb exporter uses.
        tile_pitch_mm = 44.0

    issues: list = []

    # ── snake links ────────────────────────────────────────────────
    chain = getattr(panel, "snake_chain", None) or []
    for a, b in zip(chain, chain[1:]):
        b_a = boards.get(a)
        b_b = boards.get(b)
        if b_a is None or b_b is None:
            continue
        r_a = _tile_radius_mm(b_a)
        r_b = _tile_radius_mm(b_b)
        if r_a is None or r_b is None:
            continue
        available = tile_pitch_mm - r_a - r_b
        issues.extend(profile.check_flex_link(
            available, link_name=f"{a} ↔ {b}",
            refs=(a, b)))

    # ── branches ───────────────────────────────────────────────────
    lengths = getattr(panel, "branch_flex_lengths", None) or {}
    for (parent, child) in (getattr(panel, "branches", None) or []):
        L = lengths.get((parent, child))
        if L is None:
            continue
        issues.extend(profile.check_flex_link(
            L, link_name=f"{parent} → {child}",
            refs=(parent, child)))

    # ── rigid layer count ─────────────────────────────────────────
    seen_layer_counts: set[int] = set()
    for name, board in boards.items():
        if getattr(board, "kind", None) in ("spacer", "flex"):
            continue
        n = getattr(board, "layer_count", None)
        if n is None:
            # Fall back to the design's default rigid layer count from
            # the stackup; if not available, just skip.
            stackup = getattr(board, "fitted_stackup", None)
            if stackup is not None:
                cu = [l for l in getattr(stackup, "layers", [])
                      if getattr(l, "kind", "") == "copper"]
                n = len(cu) if cu else None
        if n is None or n in seen_layer_counts:
            continue
        seen_layer_counts.add(n)
        issues.extend(profile.check_flex_layer_count(n, refs=(name,)))

    return issues


def check_panel_cavities(boards: dict, *, profile=None) -> list:
    """Validate every milled spacer cavity in `boards` against the
    fab's milling envelope.

    Walks each board's `cavity_placements` (the per-face cavities the
    placer attaches to spacers) and runs `profile.check_pocket()` on
    each. Returns Issues — empty list when the fab can build everything."""
    profile = profile or default_fab_profile()
    if not profile.milling.available:
        # No milling at all — every cavity is an error.
        return [
            type(profile.check_pocket(depth_mm=0)[0])(
                "error", "milling_unavailable",
                f"{profile.name} has no controlled-depth milling but "
                f"{name} carries {len(getattr(b, 'cavity_placements', []))} "
                f"spacer cavities", (name,))
            for name, b in boards.items()
            if getattr(b, "cavity_placements", [])
        ]

    issues: list = []
    for name, board in boards.items():
        # cavity_placements are per-spacer; their depths come from the
        # spacer's face geometry.
        for cp in getattr(board, "cavity_placements", []):
            depth = getattr(cp, "depth_mm", None)
            if depth is None:
                continue
            issues.extend(profile.check_pocket(
                depth_mm=depth, refs=(name, getattr(cp, "name", "?"))))
    return issues
