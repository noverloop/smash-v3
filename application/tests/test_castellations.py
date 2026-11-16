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
        connect=lambda net, pin: gen._net(d, net).connect(pin),
        cone_exits=gen._CONE_EXITS)
    return d, panel, boards, contract, counts, M


def _cast_chips(d):
    return [c for c in d.chips if getattr(c, "manf_pn", None) == "CASTELLATIONS"]


def test_every_rigid_snake_board_gets_castellations(built):
    _d, panel, boards, _c, counts, _M = built
    rigid = [n for n in panel.snake_chain if n in boards
             and not getattr(boards[n], "is_spacer", False)
             and getattr(boards[n], "kind", "rigid") != "flex"]
    leaves = {dst for _src, dst in (panel.branches or []) if dst in boards}
    assert set(counts) == set(rigid) | leaves


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
    d, _p, boards, contract, _n, _M = built
    for c in _cast_chips(d):
        r = boards[c.board_tag].geometry.outline_radius_mm or contract["radius_mm"]
        for pad in c.footprint.pads:
            assert math.hypot(*pad.position_mm) == pytest.approx(r, abs=1e-3)
            assert pad.drill_mm and pad.note == "castellated"


def test_each_lane_is_one_physical_angle_through_the_fold(built):
    """Map every pad back from its board's folded frame to the physical
    frame: all pads of a net land on that net's lane angles."""
    d, _p, _b, contract, _n, M = built
    parent = dict((dst, src) for src, dst in (_p.branches or []))
    for c in _cast_chips(d):
        Mb = M.get(c.board_tag) or M[parent[c.board_tag]]
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


def test_signal_lanes_stay_in_the_signal_sector(built):
    """Signal / power lanes only in the 210° signal sector; GND castellations
    and antenna feeds only in the opposite antenna sector (no lanes there)."""
    from smash.parts.castellations import (SIGNAL_SECTOR_CENTRE_DEG,
                                           SIGNAL_SECTOR_HALF_DEG)
    _d, _p, _b, contract, _n, _M = built

    def in_signal(a):
        d = (a - SIGNAL_SECTOR_CENTRE_DEG + 180) % 360 - 180
        return abs(d) <= SIGNAL_SECTOR_HALF_DEG
    kinds = set()
    for net, lane in contract["lanes"].items():
        kind = lane.get("kind", "signal")
        kinds.add(kind)
        for a in lane["angles"]:
            if kind == "cone_exit":
                continue                     # nose-cone exits: antenna sector (cone over GND)
            if kind in ("signal", "power", "plug_exit", "gnd_guard"):
                assert in_signal(a), (net, a)
            else:
                assert not in_signal(a), (net, a)
    assert {"gnd_plane", "antenna_feed"} <= kinds


def test_lr_bus_crosses_as_one_gnd_guarded_block(built):
    """The 7 LR2021 lines (WBA55 on wakeup → fin_ble) take one physically
    contiguous run of lanes, interleaved G S G S … G with GND guards that
    connect to GND on both boards."""
    from smash.parts.castellations import GUARDED_BUSES
    d, _p, _b, contract, _n, _M = built
    bus_nets, guard = GUARDED_BUSES["LR"]
    lanes = contract["lanes"]
    g = lanes[guard]
    assert g["kind"] == "gnd_guard" and g["net"] in ("GND", "FLEX_GND")
    assert {"wakeup_board", "fin_ble_board"} <= set(g["boards"])
    sig = [lanes[n]["angles"][0] for n in bus_nets]
    block = sorted(g["angles"] + sig, key=lambda a: (a + 180) % 360)
    assert len(block) == 2 * len(bus_nets) + 1
    assert set(block[0::2]) == set(g["angles"])          # guards on the outside + between
    assert set(block[1::2]) == set(sig)
    step = math.degrees(contract["pitch_mm"] / contract["radius_mm"])
    for a, b in zip(block, block[1:]):
        assert abs(((b - a) + 180) % 360 - 180) < 1.5 * step   # no gaps
    # every guard pad is a real GND connection
    for c in _cast_chips(d):
        for pin in c.pins:
            if pin.name.startswith(guard + "@"):
                net = d.net_by_name(pin.net) if isinstance(pin.net, str) else pin.net
                assert net is not None and {net.name, *(net.aliases or [])} & {"GND", "FLEX_GND"}, (c.ref, pin.name)


def test_sleeve_joins_the_schematic_on_a_copy(built, tmp_path):
    """The 2D unroll's lanes + antennas become a 'sleeve' frame in the
    system schematic, added to a copy only (PCB design untouched)."""
    import copy
    from smash.export.kicad_sch import write_kicad_schematic
    from smash.export.sleeve_layout import add_sleeve_schematic_parts
    d, _p, _b, contract, _n, _M = built
    s = copy.deepcopy(d)
    gen = sys.modules["generate_stackup"]
    refs = add_sleeve_schematic_parts(
        s, contract, connect=lambda net, pin: gen._net(s, net).connect(pin))
    assert refs[0] == "J_SLEEVE" and {"AE_2G4", "AE_SUBG"} <= set(refs)
    assert not any(c.ref == "J_SLEEVE" for c in d.chips)
    sl = next(c for c in s.chips if c.ref == "J_SLEEVE")
    xs = [p.position_mm[0] for p in sl.footprint.pads]
    assert xs == sorted(xs)                       # unrolled order
    write_kicad_schematic(s, tmp_path)
    assert "J_SLEEVE" in (tmp_path / "smash.kicad_sch").read_text()


def test_nose_cone_exits_replace_the_branch_flex(built):
    """QPD / camera links leave companion_compute through castellations (one
    angle per net, free above compute) and land on the leaf PCB at the
    same angle; GND rides the GND castellations on the leaves too."""
    d, _p, boards, contract, counts, _M = built
    cone = {k: v for k, v in contract["lanes"].items() if v["kind"] == "cone_exit"}
    assert cone
    for k, v in cone.items():
        assert v["boards"][0] == "companion_compute"
        assert v["boards"][1] in ("qpd_module", "camera_module")
    for leaf in ("qpd_module", "camera_module"):
        assert counts.get(leaf, 0) >= 1
    assert not any(c.ref.startswith("J_FLEX") or "LAUNCH" in c.ref.upper()
                   for c in d.chips)
