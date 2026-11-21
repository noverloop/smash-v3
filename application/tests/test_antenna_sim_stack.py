"""(2026-11-21) The antenna (and inductive) sim's board levels must match the
generated stack: the slots use the whole potted gap as their cavity, so a
stale gap height silently invalidates every result (S1's gap went 4.4 → 2.4 mm
when the backbone spacers were sized to their parts)."""
from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def stack():
    sys.path.insert(0, str(REPO))
    try:
        gen = importlib.import_module("generate_stackup")
    finally:
        sys.path.pop(0)
    from smash.layout.placer import place_design
    from smash.layout.placer.spacer_sizing import size_backbone_spacers
    from smash.export.sleeve_step import stack_z_map
    d = gen.Design()
    gen._set_battery_mode("maximalist")
    gen._prime_power_rails(d)
    for fn in (gen.build_qpd_module, gen.build_radar_nose_io, gen.build_usb_nose,
               gen.build_camera_module, gen.build_aft_end_board, gen.build_activation_interface,
               gen.build_radar_module_awr1843aop, gen.build_companion_compute,
               gen.build_power_board, gen.build_wakeup_board, gen.build_fins_module):
        fn(d)
    gen._empty_aft_end_top(d)
    panel, boards = gen.build_panel(straight=gen._STRAIGHT_SNAKE,
                                    battery_length_mm=gen._compartment_mm())
    gen.build_spacers(d, boards)
    gen._mark_preplace_keepouts(d, boards)
    gen._mark_ring_band_keepouts(panel, boards)
    place_design(d, panel, boards)
    size_backbone_spacers(panel, boards)
    return stack_z_map(boards, panel.snake_chain)


def test_sim_board_levels_match_the_generated_stack(stack):
    from smash.sim.antenna import geometry as g
    for board, z_mid in g.BOARD_MID_Z_MM.items():
        z0, z1 = stack[board]
        assert (z0 + z1) / 2 == pytest.approx(z_mid, abs=0.01), board
        assert z1 - z0 == pytest.approx(g.BOARD_T_MM, abs=0.01), board
