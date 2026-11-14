"""Board-edge castellation contract (`smash.parts.castellations`) — the
side-wall interconnect that replaced the LGA lands (2026-11-14)."""
from __future__ import annotations

import importlib
import math
import pathlib
import sys

import pytest


@pytest.fixture(scope="module")
def built():
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_stackup")
    finally:
        sys.path.pop(0)
    from smash.layout.boards.smash_evb_v1 import build_panel
    from smash.layout.placer import place_design
    from smash.parts.castellations import (place_castellations,
                                           board_fold_transforms)

    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in (gen.build_qpd_module,
               gen.build_nose_cap, gen.build_camera_module,
               gen.build_activation_interface, gen.build_radar_module,
               gen.build_fins_module, gen.build_companion_compute,
               gen.build_power_board, gen.build_wakeup_board):
        fn(d)
    panel, boards = build_panel()
    gen.build_spacers(d, boards)
    place_design(d, panel, boards)
    M = board_fold_transforms(panel, list(panel.snake_chain))
    contract, counts = place_castellations(
        d, panel, boards,
        connect=lambda net, pin: gen._net(d, net).connect(pin))
    return d, panel, boards, contract, counts, M


def _cast_chips(d):
    return [c for c in d.chips if getattr(c, "manf_pn", None) == "CASTELLATIONS"]


def test_every_rigid_snake_board_gets_castellations(built):
    _d, panel, boards, _c, counts, _M = built
    rigid = [n for n in panel.snake_chain if n in boards
             and not getattr(boards[n], "is_spacer", False)
             and getattr(boards[n], "kind", "rigid") != "flex"]
    assert set(counts) == set(rigid)


def test_no_lane_shared_on_a_board(built):
    """Two nets may share an angle only when their board spans don't
    overlap — never on the same board."""
    _d, _p, _b, contract, _n, _M = built
    seen = {}
    for net, lane in contract["lanes"].items():
        for b in lane["boards"]:
            for a in lane["angles"]:
                key = (b, a)
                assert key not in seen, f"{net} and {seen[key]} share {a}° on {b}"
                seen[key] = net


def test_lanes_avoid_reserved_sectors(built):
    _d, _p, _b, contract, _n, _M = built
    for net, lane in contract["lanes"].items():
        for a in lane["angles"]:
            for c, hw in contract["reserved_deg"]:
                assert min(abs(a - c), 360 - abs(a - c)) >= hw, (net, a)


def test_pads_sit_on_the_outline(built):
    d, _p, _b, contract, _n, _M = built
    r = contract["radius_mm"]
    for c in _cast_chips(d):
        for pad in c.footprint.pads:
            assert math.hypot(*pad.position_mm) == pytest.approx(r, abs=1e-3)
            assert pad.drill_mm and pad.note == "castellated"


def test_each_lane_is_one_physical_angle_through_the_fold(built):
    """Map every pad back from its board's folded frame to the physical
    frame: all pads of a net land on that net's lane angles."""
    d, _p, _b, contract, _n, M = built
    for c in _cast_chips(d):
        Mb = M[c.board_tag]
        for pin, pad in zip(c.pins, c.footprint.pads):
            net, ang = pin.name.rsplit("@", 1)
            ang = float(ang.removesuffix("deg"))
            x, y = pad.position_mm
            # M is a signed diagonal/permutation reflection → its own inverse.
            (m11, m12), (m21, m22) = Mb
            px, py = m11 * x + m21 * y, m12 * x + m22 * y
            phys = math.degrees(math.atan2(py, px)) % 360
            assert min(abs(phys - ang), 360 - abs(phys - ang)) < 1e-3, (c.ref, net)
            assert ang in contract["lanes"][net]["angles"]


def test_lane_capacity_headroom(built):
    _d, _p, _b, contract, _n, _M = built
    assert contract["n_used"] <= contract["n_angles"]
    assert contract["n_used"] < contract["n_angles"], "no spare lanes left"


def test_lane_frame_matches_stack_assembly_pose(built):
    """The castellation frame mapping must equal the pose the stack STEP uses
    for every rigid board (upright; nose-ward group turned 180°)."""
    _d, panel, boards, _c, _n, M = built
    from smash.export.stackup_step import _tile_pose
    chain = list(panel.snake_chain)
    prev = None
    for n in chain:
        b = boards[n]
        if not b.is_spacer and b.kind == "rigid":
            mx, my, _mz = _tile_pose(panel.tiles, chain, prev, n, False)
            assert M[n] == ((mx, 0), (0, my)), n
        prev = n
