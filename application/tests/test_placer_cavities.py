"""Tests for smash.layout.placer.cavities — spacer pocket synthesis."""
from __future__ import annotations

from smash.layout.cavities import (
    SPACER_CAVITY_DEPTH_BOT_MM,
    SPACER_CAVITY_DEPTH_TOP_MM,
    SPACER_THICKNESS_MM,
)
from smash.layout.placer.cavities import attach_cavities_to_spacers
from smash.state import Board
from smash.state.chip import Chip
from smash.state.footprint import Footprint
from smash.state.geometry.cavity import CavityRegion
from smash.state.pad import Pad
from smash.state.topology.placement import Placement


# ── tiny panel scaffold (no full smash_evb_v1 build needed) ──────────

class _FakePanel:
    """Mimics the minimal PanelLayout surface the walker needs."""
    def __init__(self, snake_chain, tiles):
        self.snake_chain = snake_chain
        self.tiles = tiles


def _make_chip(ref: str, w_mm: float, h_mm: float,
               height_mm: float | None = None) -> Chip:
    fp = Footprint(
        name=f"FP_{ref}",
        pads=[Pad(num="1", position_mm=(0.0, 0.0),
                  size_mm=(w_mm, h_mm))],
    )
    return Chip(ref=ref, manf_pn=f"PN_{ref}", footprint=fp,
                height_mm=height_mm)


# ── walker basics ─────────────────────────────────────────────────────

def test_no_spacers_no_cavities():
    panel = _FakePanel(snake_chain=["a", "b"],
                       tiles={"a": (0, 0), "b": (1, 0)})
    a = Board("a"); b = Board("b")    # both rigid (default kind)
    n = attach_cavities_to_spacers(panel, {"a": a, "b": b})
    assert n == 0


def test_spacer_with_no_neighbour_chips_yields_potting_channel_only():
    """Even with no chips on neighbours, the potting NW→SE channel is
    drawn — so each spacer face gets exactly 1 polygon."""
    rigid_a = Board("a")
    sp      = Board("sp_a_b", kind="spacer")
    rigid_b = Board("b")
    panel = _FakePanel(
        snake_chain=["a", "sp_a_b", "b"],
        tiles={"a": (0, 0), "sp_a_b": (1, 0), "b": (2, 0)},
    )
    n = attach_cavities_to_spacers(panel,
                                   {"a": rigid_a, "sp_a_b": sp, "b": rigid_b})
    # No chips on either side → no source_components → walker skips
    # the project+merge step entirely; no cavities at all.
    assert n == 0
    assert sp.cavity_placements == []


def test_spacer_top_face_from_prev_top_chips_ew_fold():
    """A→spacer→B fold along E-W (row equal). Chips on A's TOP face
    project onto the spacer with X mirrored. Per the merge-to-through
    policy every cavity is cut clean through the full spacer thickness."""
    rigid_a = Board("a")
    sp      = Board("sp_a_b", kind="spacer")
    rigid_b = Board("b")
    # Place one chip on rigid A's TOP face at (+5, +2) — after E-W
    # fold, mirrored to (-5, +2) in the spacer's frame.
    chip = _make_chip("U1", w_mm=4.0, h_mm=2.0)
    rigid_a.chip_placements.append(Placement(
        position_mm=(5.0, 2.0), rotation_deg=0, item=chip, face="top",
    ))
    panel = _FakePanel(
        snake_chain=["a", "sp_a_b", "b"],
        tiles={"a": (0, 0), "sp_a_b": (1, 0), "b": (2, 0)},
    )
    n = attach_cavities_to_spacers(panel,
                                   {"a": rigid_a, "sp_a_b": sp, "b": rigid_b})
    # 1 polygon (chip rect ∪ potting channel), cut through. Bottom face: no chips on B.
    assert n == 1
    pl = sp.cavity_placements[0]
    assert isinstance(pl.item, CavityRegion)
    assert pl.item.face == "through"
    assert pl.item.depth_mm == SPACER_THICKNESS_MM
    # The polygon must touch the mirrored chip center (-5, +2) — confirm
    # via bounding box.
    xs = [x for x, _ in pl.item.exterior_polygon]
    ys = [y for _, y in pl.item.exterior_polygon]
    assert min(xs) <= -5.0 <= max(xs)
    assert min(ys) <= 2.0  <= max(ys)


def test_spacer_bottom_face_from_next_bottom_chips_ns_fold():
    """A→spacer→B fold along N-S (col equal). Chips on B's BOTTOM
    face mirror in Y onto the spacer; cut through (merge-to-through)."""
    rigid_a = Board("a")
    sp      = Board("sp_a_b", kind="spacer")
    rigid_b = Board("b")
    # Short part on the bottom face → 1 mm pocket (depth = tallest chip
    # on the face, rounded up to 1 or 2 mm).
    chip = _make_chip("R1", w_mm=2.0, h_mm=2.0, height_mm=0.6)
    rigid_b.chip_placements.append(Placement(
        position_mm=(3.0, 4.0), rotation_deg=0, item=chip, face="bottom",
    ))
    panel = _FakePanel(
        snake_chain=["a", "sp_a_b", "b"],
        tiles={"a": (0, 0), "sp_a_b": (0, 1), "b": (0, 2)},   # N-S
    )
    n = attach_cavities_to_spacers(panel,
                                   {"a": rigid_a, "sp_a_b": sp, "b": rigid_b})
    assert n == 1
    pl = sp.cavity_placements[0]
    assert pl.item.face == "through"
    assert pl.item.depth_mm == SPACER_THICKNESS_MM
    # Y mirrored: (3, 4) → (3, -4)
    ys = [y for _, y in pl.item.exterior_polygon]
    assert min(ys) <= -4.0 <= max(ys)


def test_chips_on_wrong_face_ignored():
    """Bottom-face chip on prev tile should NOT contribute to spacer
    top-face cavity (only prev's TOP-face chips project to TOP)."""
    rigid_a = Board("a")
    sp      = Board("sp_a_b", kind="spacer")
    rigid_b = Board("b")
    rigid_a.chip_placements.append(Placement(
        position_mm=(5.0, 0.0), rotation_deg=0,
        item=_make_chip("U_BOT", 4.0, 2.0), face="bottom",
    ))
    panel = _FakePanel(
        snake_chain=["a", "sp_a_b", "b"],
        tiles={"a": (0, 0), "sp_a_b": (1, 0), "b": (2, 0)},
    )
    n = attach_cavities_to_spacers(panel,
                                   {"a": rigid_a, "sp_a_b": sp, "b": rigid_b})
    # Neither face — top has nothing, bottom looks at B which is empty
    assert n == 0


def test_chips_without_footprint_skipped():
    """Project pads (face=top/bottom, no footprint) shouldn't crash."""
    rigid_a = Board("a")
    sp      = Board("sp_a_b", kind="spacer")
    rigid_b = Board("b")
    pad_chip = Chip(ref="P_PAD", manf_pn="project")   # no footprint
    rigid_a.chip_placements.append(Placement(
        position_mm=(0.0, 0.0), rotation_deg=0, item=pad_chip, face="top",
    ))
    panel = _FakePanel(
        snake_chain=["a", "sp_a_b", "b"],
        tiles={"a": (0, 0), "sp_a_b": (1, 0), "b": (2, 0)},
    )
    # Should not crash, and the no-footprint chip contributes nothing
    n = attach_cavities_to_spacers(panel,
                                   {"a": rigid_a, "sp_a_b": sp, "b": rigid_b})
    assert n == 0


def test_idempotent_clears_existing():
    """Re-running the walker should not double-up cavities."""
    rigid_a = Board("a")
    sp      = Board("sp_a_b", kind="spacer")
    rigid_b = Board("b")
    rigid_a.chip_placements.append(Placement(
        position_mm=(5.0, 0.0), rotation_deg=0,
        item=_make_chip("U", 2.0, 2.0), face="top",
    ))
    panel = _FakePanel(
        snake_chain=["a", "sp_a_b", "b"],
        tiles={"a": (0, 0), "sp_a_b": (1, 0), "b": (2, 0)},
    )
    n1 = attach_cavities_to_spacers(panel,
                                    {"a": rigid_a, "sp_a_b": sp, "b": rigid_b})
    n2 = attach_cavities_to_spacers(panel,
                                    {"a": rigid_a, "sp_a_b": sp, "b": rigid_b})
    assert n1 == n2
    # Spacer's list should now hold just n2 cavities (not 2*n)
    assert len(sp.cavity_placements) == n2


# ── full-panel sanity (no chips placed → only walks topology) ────────

def test_full_evb_panel_walks_six_spacers_clean():
    """Building the EVB panel and running the walker with no chips on
    any board → no cavities (potting channel only is skipped because
    we gate on source_components being non-empty)."""
    from smash.layout.boards.smash_evb_v1 import build_panel
    panel, boards = build_panel()
    spacers = [b for n, b in boards.items() if b.is_spacer]
    # smash_evb_v1 doesn't currently expose spacers in `boards` (only
    # rigids), but the walker iterates the snake chain — so we don't
    # need them in the boards map.
    n = attach_cavities_to_spacers(panel, boards)
    # No chip_placements on any board → no cavities to mill
    assert n == 0


# ── edge clearance: cavities clipped to a min wall from the outline ──

def test_cavity_clipped_to_min_wall_from_edge():
    """A chip placed near the Ø34 spacer edge must have its cavity
    clipped so a minimum FR4 wall remains to the outline."""
    import math
    from smash.layout.cavities import CAVITY_EDGE_WALL_MM

    rigid_a = Board("a")
    sp      = Board("spacer_a_b", kind="spacer")   # spacer_ → Ø34 default
    rigid_b = Board("b")
    # Big part shoved out near the rim on A's TOP face.
    chip = _make_chip("U1", w_mm=10.0, h_mm=10.0, height_mm=1.8)
    rigid_a.chip_placements.append(Placement(
        position_mm=(12.0, 0.0), rotation_deg=0, item=chip, face="top",
    ))
    panel = _FakePanel(
        snake_chain=["a", "spacer_a_b", "b"],
        tiles={"a": (0, 0), "spacer_a_b": (1, 0), "b": (2, 0)},
    )
    attach_cavities_to_spacers(
        panel, {"a": rigid_a, "spacer_a_b": sp, "b": rigid_b})
    assert sp.geometry is not None and sp.geometry.diameter_mm == 34.0
    limit = sp.geometry.outline_radius_mm - CAVITY_EDGE_WALL_MM
    for pl in sp.cavity_placements:
        reach = max(math.hypot(x, y) for x, y in pl.item.exterior_polygon)
        assert reach <= limit + 1e-6, f"cavity reaches {reach} > {limit}"
