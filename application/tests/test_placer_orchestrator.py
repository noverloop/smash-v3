"""Tests for smash.layout.placer.orchestrator — the top-level
place_design() entry point."""
from __future__ import annotations

import pytest

from smash.layout.placer.orchestrator import (
    DesignPlacementReport,
    PlacementStats,
    place_design,
)
from smash.state import Board, Design
from smash.state.chip import Chip
from smash.state.footprint import Footprint
from smash.state.pad import Pad


class _FakePanel:
    def __init__(self, snake_chain, tiles):
        self.snake_chain = snake_chain
        self.tiles = tiles


def _square_chip(d: Design, ref: str, side_mm: float, board_tag: str) -> Chip:
    fp = Footprint(
        name=f"FP_{ref}",
        pads=[Pad(num="1", position_mm=(0.0, 0.0),
                  size_mm=(side_mm, side_mm))],
    )
    return d.add_chip(ref=ref, manf_pn=f"PN_{ref}",
                      footprint=fp, board_tag=board_tag)


# ── basics ────────────────────────────────────────────────────────────

def test_empty_design_returns_clean_report():
    d = Design()
    panel = _FakePanel(snake_chain=[], tiles={})
    rep = place_design(d, panel, {})
    assert isinstance(rep, DesignPlacementReport)
    assert rep.per_board == []
    assert rep.n_cavities_added == 0
    assert not rep.any_overflow


def test_single_board_packs_chips():
    d = Design()
    board = Board("flight_board")
    boards = {"flight_board": board}
    for i in range(5):
        _square_chip(d, f"R{i}", 1.0, "flight_board")
    panel = _FakePanel(snake_chain=["flight_board"],
                       tiles={"flight_board": (0, 0)})
    rep = place_design(d, panel, boards)
    assert len(board.chip_placements) == 5
    stats = next(s for s in rep.per_board if s.board_name == "flight_board")
    assert stats.n_locked == 0
    assert stats.n_packed == 5
    assert stats.n_unplaced == 0
    assert not stats.overflow


def test_chips_routed_by_board_tag():
    d = Design()
    a = Board("flight_board"); b = Board("power_board")
    _square_chip(d, "U_FB1", 1.0, "flight_board")
    _square_chip(d, "U_FB2", 1.0, "flight_board")
    _square_chip(d, "U_PB1", 1.0, "power_board")
    panel = _FakePanel(
        snake_chain=["flight_board", "power_board"],
        tiles={"flight_board": (0, 0), "power_board": (1, 0)},
    )
    place_design(d, panel, {"flight_board": a, "power_board": b})
    assert len(a.chip_placements) == 2
    assert len(b.chip_placements) == 1
    assert {p.item.ref for p in a.chip_placements} == {"U_FB1", "U_FB2"}
    assert {p.item.ref for p in b.chip_placements} == {"U_PB1"}


def test_locks_applied_and_packer_runs_around_them():
    """U_MPU is locked in locked_placements.json at (-5.2, 0); other
    chips on flight_board must be packed around it."""
    d = Design()
    board = Board("flight_board")
    # Need to add a chip with ref="U_MPU" and put it on flight_board.
    # The locked entry will route it there at (-5.2, 0). Note that
    # locked_placements.json puts U_MPU on power_board's MPU (no actual
    # board hint), so for the test we tag it on flight_board.
    fp = Footprint(name="MPU_fp",
                   pads=[Pad("1", (0, 0), (8, 8))],
                   package_class="BGA")
    d.add_chip(ref="U_MPU", manf_pn="MPU", footprint=fp,
               board_tag="flight_board")
    for i in range(3):
        _square_chip(d, f"X{i}", 1.0, "flight_board")
    panel = _FakePanel(snake_chain=["flight_board"],
                       tiles={"flight_board": (0, 0)})
    rep = place_design(d, panel, {"flight_board": board})
    # U_MPU's locked position should win
    mpu = next(p for p in board.chip_placements if p.item.ref == "U_MPU")
    assert mpu.locked is True
    assert mpu.position_mm == (-7.7, -2.7)
    stats = rep.per_board[0]
    assert stats.n_locked == 1
    assert stats.n_packed == 3


def test_untagged_chips_recorded():
    d = Design()
    board = Board("flight_board")
    fp = Footprint(name="X", pads=[Pad("1", (0, 0), (1, 1))])
    d.add_chip(ref="U_NO_TAG", manf_pn="X", footprint=fp)    # no board_tag
    panel = _FakePanel(snake_chain=["flight_board"],
                       tiles={"flight_board": (0, 0)})
    rep = place_design(d, panel, {"flight_board": board})
    assert rep.untagged_refs == ["U_NO_TAG"]
    assert len(board.chip_placements) == 0


def test_unknown_board_tag_recorded():
    d = Design()
    board = Board("flight_board")
    fp = Footprint(name="X", pads=[Pad("1", (0, 0), (1, 1))])
    d.add_chip(ref="U_FAR", manf_pn="X", footprint=fp,
               board_tag="nonexistent_board")
    panel = _FakePanel(snake_chain=["flight_board"],
                       tiles={"flight_board": (0, 0)})
    rep = place_design(d, panel, {"flight_board": board})
    assert rep.unknown_board_refs == [("U_FAR", "nonexistent_board")]


def test_no_footprint_chip_counted_unplaced():
    """Project pads (manf='project') have no footprint."""
    d = Design()
    board = Board("flight_board")
    d.add_chip(ref="P_PAD", manf_pn="project",
               board_tag="flight_board")
    panel = _FakePanel(snake_chain=["flight_board"],
                       tiles={"flight_board": (0, 0)})
    rep = place_design(d, panel, {"flight_board": board})
    stats = rep.per_board[0]
    assert stats.n_unplaced == 1
    assert stats.n_packed == 0
    assert len(board.chip_placements) == 0


def test_orchestrator_idempotent():
    """Running place_design twice should yield identical placements
    (no doubling, no leftover state)."""
    d = Design()
    board = Board("flight_board")
    for i in range(4):
        _square_chip(d, f"R{i}", 1.0, "flight_board")
    panel = _FakePanel(snake_chain=["flight_board"],
                       tiles={"flight_board": (0, 0)})
    place_design(d, panel, {"flight_board": board})
    first = list(board.chip_placements)
    place_design(d, panel, {"flight_board": board})
    second = list(board.chip_placements)
    assert len(first) == len(second) == 4
    # Same refs, same positions
    a = {p.item.ref: p.position_mm for p in first}
    b = {p.item.ref: p.position_mm for p in second}
    assert a == b


def test_cavities_attached_for_evb_panel():
    """End-to-end on the canonical EVB: build the panel, tag a few
    chips, run place_design, confirm spacers receive CavityRegions
    from their neighbours' top-face chips."""
    from smash.layout.boards.smash_evb_v1 import build_panel
    from smash.state.geometry.cavity import CavityRegion
    panel, boards = build_panel()

    d = Design()
    # Place a 6×6 chip dead-centre on wakeup_board (top face).
    # wakeup_board's east neighbour is fins_module (flight folded into wakeup),
    # so the chip projects onto spacer_wakeup_board_fins_module after the snake
    # fold. Per the merge-to-through policy the cavity is cut clean through.
    fp = Footprint(name="BIG",
                   pads=[Pad("1", (0, 0), (6, 6))],
                   package_class="QFN")
    d.add_chip(ref="U_BIG", manf_pn="BIG", footprint=fp,
               board_tag="wakeup_board")

    rep = place_design(d, panel, boards)
    assert rep.n_cavities_added >= 1
    # Find the spacer east of wakeup_board (wakeup↔power; fins_module folded in)
    sp = boards["spacer_wakeup_board_power_board"]
    assert any(isinstance(p.item, CavityRegion) and p.item.face == "through"
               for p in sp.cavity_placements)


def test_clears_prior_placements_on_rerun():
    """If a board already has chip_placements from a previous build,
    place_design should clear them first."""
    d = Design()
    board = Board("flight_board")
    # Pre-seed with a stale Placement
    from smash.state.topology.placement import Placement
    stale_chip = Chip(ref="STALE", manf_pn="X",
                      footprint=Footprint(name="x", pads=[Pad("1", (0,0), (1,1))]),
                      board_tag="flight_board_OLD")
    board.chip_placements.append(Placement((99, 99), 0, stale_chip))
    panel = _FakePanel(snake_chain=["flight_board"],
                       tiles={"flight_board": (0, 0)})
    place_design(d, panel, {"flight_board": board})
    # Stale entry must be gone
    assert all(p.item.ref != "STALE" for p in board.chip_placements)
