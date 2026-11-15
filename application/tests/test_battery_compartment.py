"""Integration tests for the aft battery compartment.

The ~21 mm Li-MnO₂ pack is modeled into the physical stackup as a run of
N manufacturable FR4 spacers between `aft_end_board` (cell −, sealed aft
floor) and `activation_interface` (cell +, battery connector). These
tests lock the compartment's load-bearing invariants — spacer count +
thickness split, the merged single through-cut, the filled-via backbone
pass-through, the split cell contacts, and the potting-hole placement —
against the full maximalist build.
"""
from __future__ import annotations

import importlib
import math
import pathlib
import sys

import pytest

from smash.layout.boards.smash_evb_v1 import (
    BATTERY_LENGTH_MM,
    MAX_SPACER_THICKNESS_MM,
    battery_spacer_count,
    build_panel,
)
from smash.layout.placer import place_design


@pytest.fixture(scope="module")
def built():
    """Full maximalist design + panel + cavities + lands (one build)."""
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_stackup")
    finally:
        sys.path.pop(0)
    gen._set_battery_mode("maximalist")  # maximalist superset = the 3-cell pack
    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in (gen.build_qpd_module,
               gen.build_nose_cap, gen.build_camera_module,
               gen.build_aft_end_board,
               gen.build_activation_interface,
               gen.build_radar_module, gen.build_fins_module,
               gen.build_companion_compute, gen.build_power_board,
               gen.build_wakeup_board):
        fn(d)
    gen._empty_aft_end_top(d)            # 2026-11-15 aft reorder
    panel, boards = build_panel()
    gen.build_spacers(d, boards)
    place_design(d, panel, boards)
    gen._mark_radar_block_cutout(boards)
    gen._mark_battery_pockets(boards)
    gen.place_lga_lands(
        d, panel, boards,
        connect=lambda net, pin: gen._net(d, net).connect(pin))
    return gen, d, panel, boards


def _battery_spacers(boards):
    return {n: b for n, b in boards.items() if "battery" in n}


# ── spacer count + thickness split ────────────────────────────────────

def test_spacer_count_matches_fab_cap():
    """No single 21 mm spacer — the holder is ceil(L/MAX) thinner discs."""
    n = battery_spacer_count()
    assert n == math.ceil(BATTERY_LENGTH_MM / MAX_SPACER_THICKNESS_MM)
    assert BATTERY_LENGTH_MM / n <= MAX_SPACER_THICKNESS_MM


def test_six_battery_spacers_sum_to_cell_length(built):
    _gen, _d, _panel, boards = built
    sp = _battery_spacers(boards)
    assert len(sp) == battery_spacer_count()
    thicks = [b.thickness_mm for b in sp.values()]
    # Each ≤ the fab cap, identical (one design replicated), summing to L.
    assert all(t <= MAX_SPACER_THICKNESS_MM + 1e-9 for t in thicks)
    assert max(thicks) - min(thicks) < 1e-9
    assert sum(thicks) == pytest.approx(BATTERY_LENGTH_MM, abs=1e-6)


# ── snake topology ────────────────────────────────────────────────────

def test_compartment_sits_between_aft_end_and_activation(built):
    """(2026-11-15 aft reorder) cell_floor_board is gone: the Al compartment
    is glued + screwed straight onto aft_end_board's bare top face, and
    activation_interface (carrying aft_end's former top-face parts) is the
    ceiling, under fin_ble_board."""
    _gen, _d, panel, boards = built
    chain = [c for c in panel.snake_chain]
    assert chain[0] == "aft_end_board"
    assert "cell_floor_board" not in chain
    bat = [c for c in chain if "battery" in c]
    assert len(bat) == battery_spacer_count()
    i0 = chain.index(bat[0])
    assert chain[i0 - 1] == "aft_end_board"
    assert chain[i0 + len(bat)] == "activation_interface"


def test_aft_end_top_face_is_empty(built):
    """Only the bottom-face interface pads (+ castellations) stay on aft_end."""
    _gen, _d, _panel, boards = built
    for pl in boards["aft_end_board"].chip_placements:
        ref = pl.item.ref
        if ref.startswith("J_") and "spacer" in ref:
            continue                     # legacy LGA land chip (this fixture only)
        assert ref.startswith(("TP_", "P_ACT", "J_CAST_")), ref


# ── merged through-cut (no unsustainable centre web) ──────────────────

def test_cells_are_one_merged_through_cut(built):
    _gen, _d, _panel, boards = built
    for name, b in _battery_spacers(boards).items():
        cavs = b.cavity_placements or []
        names = [c.item.name for c in cavs]
        assert names == ["cell_bores_merged"], f"{name}: {names}"
        assert cavs[0].item.face == "through"


# ── filled-via backbone pass-through ──────────────────────────────────

def test_every_battery_spacer_has_filled_vias_on_backbone(built):
    _gen, _d, _panel, boards = built
    for name, b in _battery_spacers(boards).items():
        vias = b.vias or []
        assert vias, f"{name} has no vias"
        assert all(v.filled for v in vias), f"{name} has unfilled vias"
        nets = {v.net for v in vias}
        # The backbone GND must thread the whole column.
        assert {"GND", "FLEX_GND"} & nets, f"{name} vias missing GND: {sorted(nets)}"


# ── split cell contacts ───────────────────────────────────────────────

def _placement(board, ref):
    for p in board.chip_placements or []:
        if getattr(p.item, "ref", None) == ref:
            return p
    return None


def test_cell_contacts_3cell_split(built):
    """(2026-11-15) Both tab sets (+ and −, one per cell) land on
    activation_interface's BOTTOM face — the compartment ceiling."""
    _gen, _d, _panel, boards = built
    act = boards["activation_interface"]
    assert _placement(act, "P_CELL_CONTACTS") is None
    for k in (1, 2, 3):
        for pol in ("POS", "NEG"):
            pl = _placement(act, f"P_CELL_TAB_{pol}{k}")
            assert pl is not None and pl.face == "bottom", f"P_CELL_TAB_{pol}{k}"


# ── no structural Cu coins remain anywhere ────────────────────────────

def test_no_cu_coins_anywhere(built):
    """radar/companion coins were removed 2026-07-04 (coin audit); the last
    coin — cell_floor_board's compression plate — went in the 2026-07-30
    battery rework (the tile survives as a THIN 6L floor, but the potted
    monolith carries the pack load — no coin came back)."""
    _gen, _d, _panel, boards = built
    coined = [n for n, b in boards.items() if getattr(b, "cu_coin_inserts", None)]
    assert coined == []
    # standard board stackup (2026-11-14): cell_floor is the same 8L board as
    # every other rigid tile (was a thin 6L floor, and before that a 3.3 mm
    # 20L coin host)
    assert "cell_floor_board" not in boards     # dropped 2026-11-15


def test_piezo_disc_smd_no_pocket(built):
    """The Steminc SMD10T04R111 disc reflows flat on fin_ble_board's TOP
    face (the disc + comparator column swapped off the saturated aft_end
    top in the 2026-07-31 stack reorder). TOP (nose-facing) is the hard
    mechanical rule: rapid deceleration loads the ceramic in COMPRESSION against
    rigid FR4; an aft-facing mount would put the disc's inertial load on the
    In52 joints in tension and bend the ceramic over potting voids. NO
    milled pocket cavity remains anywhere (the pocket existed to recess
    the old CEB-21018 brass diaphragm and give it flex room)."""
    _gen, _d, _panel, boards = built
    for bname in ("aft_end_board", "fin_ble_board"):
        cavs = boards[bname].cavity_placements or []
        assert "piezo_disk_pocket" not in [c.item.name for c in cavs]
    pl = _placement(boards["fin_ble_board"], "P_PIEZO")
    assert pl is not None and pl.face == "top"
    assert pl.position_mm == (0.0, 0.0)          # locked on the spin axis
    assert pl.item.footprint.name == "PiezoDisc_SMD10T04R111"
    assert pl.item.height_mm == pytest.approx(0.4)


def test_piezo_disc_never_aft_facing(built):
    """The piezo disc must sit on a nose-facing (top) face: rapid deceleration
    then loads the ceramic in compression; aft-facing would put its inertial
    load on the In52 joints in tension. (Replaces the old blanket "no chips on
    activation_interface bottom" rule — that face is open to small parts that
    opt in with feature="bottom".)"""
    _gen, _d, _panel, boards = built
    for name, b in boards.items():
        for p in getattr(b, "chip_placements", []) or []:
            if getattr(p.item, "ref", "") == "P_PIEZO":
                assert p.face == "top", f"P_PIEZO on {name} {p.face} face"


def test_no_lga_lands_on_piezo_disc(built):
    """The Ø10 SMD disc sits proud on fin_ble_board's top face, so the
    backbone LGA lands at the fin_ble↔wakeup joint must clear its footprint
    — no land pad inside r < 5.3 mm (disc radius + clearance) of the locked
    centre."""
    _gen, _d, _panel, boards = built
    sp = boards["spacer_fin_ble_board_wakeup_board"]
    bad = []
    for p in sp.chip_placements:
        ref = getattr(p.item, "ref", "")
        if not (ref.startswith(("J_", "P_")) and ref.endswith(("_top", "_bot"))):
            continue
        fp = getattr(p.item, "footprint", None)
        if fp is None:
            continue
        for pad in fp.pads:
            if math.hypot(pad.position_mm[0], pad.position_mm[1]) < 5.3:
                bad.append((ref, pad.num))
    assert not bad, f"{len(bad)} LGA land pad(s) over the Ø10 piezo disc: {bad[:5]}"


# ── potting injected from the activation side ─────────────────────────

def test_potting_holes_on_activation_not_aft(built):
    _gen, _d, _panel, boards = built
    aft = boards["aft_end_board"].geometry
    act = boards["activation_interface"].geometry
    assert (aft.holes or []) == []          # sealed aft floor
    assert len(act.holes or []) == 1        # potting enters here
    assert all(h.tag == "potting" for h in act.holes)


# ── core: single horizontal TLM-1530M/S ─────────────────────────

def test_core_single_cell_compartment():
    """The core_1cell opt-in swaps the 3× vertical TLM-1520 pack for ONE
    horizontal TLM-1530M/S: a 15.1 mm compartment (4 spacers vs 6), single-cell
    tab lands with no isolation resistors, and the TLM-1530M cell record."""
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_stackup")
    finally:
        sys.path.pop(0)
    prev = gen._BATTERY_MODE
    gen._set_battery_mode("core_1cell")
    try:
        # 15.1 mm compartment depth → 4 spacers (vs 21 mm → 6, unchanged)
        assert gen._compartment_mm() == 15.1
        assert battery_spacer_count(15.1) == 4
        assert battery_spacer_count(21.0) == 6      # 3-cell (default) depth
        # power_board battery wiring: 2 tab lands; the per-cell 200 mΩ
        # isolation resistors fab UNCONDITIONALLY (power_board is one
        # shared part across every config — economies of scale; single
        # mode leaves them as BAT_CELLx_POS stubs, DNP at assembly)
        d = gen.Design(); gen._prime_power_rails(d); gen.build_power_board(d)
        refs = [c.ref for c in d.chips]
        assert "P_CELL_TAB_POS" in refs and "P_CELL_TAB_NEG" in refs
        assert "P_CELL_CONTACTS" not in refs and "P_CELL_CONTACTS_AFT" not in refs
        assert [r for r in refs if r.startswith("R_BAT") and r.endswith("_ISO")] \
            == ["R_BAT1_ISO", "R_BAT2_ISO", "R_BAT3_ISO"]
        # the TLM-1530M/S cell record carries 200 mAh for the BOM
        cells = [b for b in d.batteries if b.ref == "BT_CELL"]
        assert len(cells) == 1
        assert cells[0].manf_pn == "TLM-1530M/S"
        assert cells[0].capacity_mah == 200.0
        # cell side-tab lands on the ceiling (activation_interface, 2026-11-15)
        tabs = [c for c in d.chips if c.ref in ("P_CELL_TAB_POS", "P_CELL_TAB_NEG")]
        assert len(tabs) == 2 and all(t.board_tag == "activation_interface" for t in tabs)
        # the single-cell opt-in DROPS cell_floor_board (cell lies on aft_end)
        bs = gen._config_boards("core_1cell", gen.CONFIGS["core_1cell"])
        assert "cell_floor_board" not in bs
        d2 = gen.Design(); gen._prime_power_rails(d2)
        for bn in bs:
            gen._BOARD_BUILDERS[bn](d2)
        snake = [b for b in gen._MASTER_SNAKE if b in bs]
        _panel, boards = gen.build_config_panel(
            snake, straight=gen._STRAIGHT_SNAKE,
            battery_length_mm=gen._compartment_mm())
        assert "cell_floor_board" not in boards
        bat = _battery_spacers(boards)
        assert len(bat) == 4
        thicks = [b.thickness_mm for b in bat.values()]
        assert sum(thicks) == pytest.approx(15.1, abs=1e-6)
        # compartment sits between aft_end_board and activation_interface
        chain = list(_panel.snake_chain)
        i0 = chain.index([c for c in chain if "battery" in c][0])
        assert chain[i0 - 1] == "aft_end_board"
        assert chain[i0 + len(bat)] == "activation_interface"
        assert all(t <= MAX_SPACER_THICKNESS_MM + 1e-9 for t in thicks)
        assert max(thicks) - min(thicks) < 1e-9
    finally:
        gen._BATTERY_MODE = prev


def test_peek_standoffs_stay_inside_the_aluminium_rings():
    from smash.export import spacer_step as S
    edge = S.STANDOFF_R_MM + S.STANDOFF_D_MM / 2.0
    assert edge <= S.RING_R_IN_MM - S.RING_CLEARANCE_MM + 1e-9
    assert edge < S.BATT_TOP_RING_R_IN_MM


def test_aluminium_ring_gap_exists_in_the_chain():
    """The ring gap names must match a real gap (they silently went stale
    after the aft reorder)."""
    from smash.layout.boards.smash_evb_v1 import build_panel
    from smash.export.spacer_step import GAP_RING_GAPS
    panel, boards = build_panel()
    assert set(GAP_RING_GAPS) <= set(panel.snake_chain)
