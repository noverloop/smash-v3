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
               gen.build_radar_nose_io, gen.build_camera_module,
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
    return [c for c in d.chips if getattr(c, "manf_pn", None) == "CASTELLATIONS"
            and not c.ref.startswith("J_CROWN_")]


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
            for a in lane.get("board_angles", {}).get(b, lane["angles"]):
                key = (b, a)
                assert key not in seen, f"{net} and {seen[key]} share {a}° on {b}"
                seen[key] = net


def test_lanes_avoid_reserved_sectors(built):
    _d, _p, _b, contract, _n, _M = built
    for net, lane in contract["lanes"].items():
        if lane.get("kind") in ("crown_payload", "crown_top"):
            continue      # crown tooth angles — the seams / grooves are core-sleeve only
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
            ln = contract["lanes"][net]
            assert ang in ln.get("board_angles", {}).get(c.board_tag, ln["angles"])


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
            if kind in ("cone_exit", "crown_top", "crown_payload"):
                continue                     # nose crown: all round the rim (nose_interface)
            if kind in ("signal", "power", "plug_exit", "gnd_guard"):
                # (2026-11-18) lanes from the wakeup board upward may also use
                # the antenna sector — both slot antennas sit below wakeup
                upper = all(b not in ("aft_end_board", "activation_interface", "fin_ble_board")
                            for b in lane["boards"])
                assert in_signal(a) or upper, (net, a)
            else:
                assert not in_signal(a), (net, a)
    assert {"gnd_plane", "antenna_feed"} <= kinds


def test_radio_is_wakeup_local(built):
    """The LR2021 sits next to its WBA host on wakeup (2026-11-16): none of
    its host / RF-switch nets crosses a joint, so none gets a lane; BLE_RF
    stays on wakeup too."""
    d, _p, _b, contract, _n, _M = built
    lr = next(c for c in d.chips if c.ref == "U_LR")
    assert lr.board_tag == "wakeup_board"
    for ref in ("U_LR_SW_HF", "Y_LR_TCXO"):
        assert next(c for c in d.chips if c.ref == ref).board_tag == "wakeup_board", ref
    local = ("LR_SPI_SCK", "LR_SPI_MOSI", "LR_SPI_MISO", "LR_NSS", "LR_BUSY",
             "LR_IRQ", "LR_NRESET", "LR_RFSW_TX", "BLE_RF")
    for name in local:
        assert name not in contract["lanes"], name
        net = d.net_by_name(name)
        boards = {next(c for c in d.chips if c.ref == rf).board_tag
                  for rf, _pin in net.pins}
        assert boards == {"wakeup_board"}, (name, boards)


def test_feed_lane_on_radio_board(built):
    """Antenna feed castellations sit on the board that carries the feed
    net's chips (the radio board), not on a hard-coded tile."""
    d, _p, _b, contract, _n, _M = built
    from smash.parts.castellations import ANTENNA_FEED_ANGLES_DEG
    assert set(ANTENNA_FEED_ANGLES_DEG) == {"ANT_HF_S1", "ANT_HF_S4"}
    for fname in ANTENNA_FEED_ANGLES_DEG:
        # S4 has its circuit since 2026-11-18 (_build_transverter).
        assert d.net_by_name(fname) is not None, fname
        lane = contract["lanes"][fname]
        assert lane["kind"] == "antenna_feed"
        net = d.net_by_name(fname)
        chip_boards = {next(c for c in d.chips if c.ref == rf).board_tag
                       for rf, _pin in net.pins
                       if not rf.startswith("J_CAST_")}
        assert lane["boards"] == ["wakeup_board"] and chip_boards == {"wakeup_board"}



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
    assert refs[0] == "J_SLEEVE" and "AE_S1" in refs and "AE_S3" not in refs
    assert "AE_S4" in refs                        # S4 transverter since 2026-11-18
    assert not {"AE_S2", "J_LF_EXT"} & set(refs)
    assert not any(c.ref == "J_SLEEVE" for c in d.chips)
    sl = next(c for c in s.chips if c.ref == "J_SLEEVE")
    xs = [p.position_mm[0] for p in sl.footprint.pads]
    assert xs == sorted(xs)                       # unrolled order
    write_kicad_schematic(s, tmp_path)
    assert "J_SLEEVE" in (tmp_path / "smash.kicad_sch").read_text()


def test_nose_payloads_use_the_crown(built):
    """(2026-11-18) Every nose payload (radar / QPD / camera / USB) reaches
    compute through the standard crown: compute edge castellations (outer
    sleeve lanes up to the grooves), payload pads AT the teeth — no cone
    exits, no lanes through the payload boards."""
    d, _p, boards, contract, counts, _M = built
    assert not any(v["kind"] == "cone_exit" for v in contract["lanes"].values())
    crown = {k: v for k, v in contract["lanes"].items() if v["kind"] == "crown_top"}
    assert crown and all(v["boards"] == ["companion_compute"] for v in crown.values())
    # (2026-11-19) each crown contact = its own compute EDGE castellation
    assert not contract.get("crown_overflow")
    assert all(len(v["angles"]) == 1 for v in crown.values())
    comp = [a for ln in contract["lanes"].values()
            if "companion_compute" in ln["boards"] for a in ln["angles"]]
    assert len(comp) == len(set(comp))                     # no shared compute slot
    step = math.degrees(0.8 / contract["radius_mm"])       # CAST_PITCH_MM
    cs_ = sorted(comp)
    gaps = [(b - a) % 360 for a, b in zip(cs_, cs_[1:] + cs_[:1])]
    assert min(gaps) >= step - 1e-3                         # no two vias merge
    # never across a release-pin hole; fan order-preserving per hook sector
    from smash.export import nose_interface as NI
    scr = sorted(NI.SCREW_ANGLES_DEG)
    half = math.degrees((0.5 * NI.RELEASE_EXCL_W_MM) / contract["radius_mm"])   # release-pin holes
    sec = NI.screw_sector
    for v in crown.values():
        a = v["angles"][0]
        assert all(min(abs(a - sa), 360 - abs(a - sa)) > half for sa in scr)
        assert sec(a) == sec(v["tooth_angle"])
    for sk in range(len(scr)):
        vs = sorted((v for v in crown.values() if sec(v["tooth_angle"]) == sk),
                    key=lambda v: (v["tooth_angle"] - scr[sk - 1]) % 360)
        cs = [(v["angles"][0] - scr[sk - 1]) % 360 for v in vs]
        assert cs == sorted(cs)                                # never crosses
    for leaf in ("qpd_module", "camera_module", "radar_module"):
        if leaf in boards:
            assert counts.get(leaf, 0) >= len(crown)
    assert not any(c.ref.startswith("J_FLEX") or "LAUNCH" in c.ref.upper()
                   for c in d.chips)


def test_feed_angles_clear_of_gnd_castellations():
    from smash.parts.castellations import (ANTENNA_FEED_ANGLES_DEG,
                                           GND_CAST_ANGLES_DEG)
    from smash.parts.antenna_slots import SLOTS
    assert set(ANTENNA_FEED_ANGLES_DEG) == {"ANT_HF_S1", "ANT_HF_S4"}
    for a in ANTENNA_FEED_ANGLES_DEG.values():
        assert 105.0 < a < 255.0
        assert all(abs(a - g) >= 5.0 for g in GND_CAST_ANGLES_DEG)
    # every feed is flanked by a GND castellation on each side (grounded CPW)
    for sl in SLOTS:
        f = ANTENNA_FEED_ANGLES_DEG[sl.net]
        assert any(g < f for g in GND_CAST_ANGLES_DEG if f - g < 8)
        assert any(g > f for g in GND_CAST_ANGLES_DEG if g - f < 8)
