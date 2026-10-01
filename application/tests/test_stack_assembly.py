"""Per-reflow stack-assembly export (`smash.export.stack_assembly`)."""
from __future__ import annotations

import importlib
import pathlib
import re
import sys

import pytest


@pytest.fixture(scope="module")
def built():
    """Full maximalist design + panel + spacers + lands (one build, reused)."""
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_maximalist_system")
    finally:
        sys.path.pop(0)
    from smash.layout.boards.smash_evb_v1 import build_panel
    from smash.layout.placer import place_design

    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in (gen.build_qpd_module,
               gen.build_yagi_antenna_a_flex, gen.build_yagi_antenna_b_flex,
               gen.build_nose_cap, gen.build_camera_module,
               gen.build_activation_interface, gen.build_radar_module,
               gen.build_fins_module, gen.build_companion_compute,
               gen.build_power_board, gen.build_wakeup_board):
        fn(d)
    panel, boards = build_panel()
    gen.build_spacers(d, boards)
    place_design(d, panel, boards)
    gen.place_lga_lands(
        d, panel, boards,
        connect=lambda net, pin: gen._net(d, net).connect(pin))
    return gen, d, panel, boards


def test_one_file_per_reflow_step(tmp_path, built):
    gen, d, panel, boards = built
    from smash.export.stack_assembly import build_stack_assembly_files

    n_elems = len([c for c in panel.snake_chain if c in boards])
    res = build_stack_assembly_files(
        d, panel, boards, tmp_path,
        connect=lambda net, pin: gen._net(d, net).connect(pin))

    # One reflow file per board-to-board interface (elements - 1).
    assert len(res) == n_elems - 1
    files = sorted(tmp_path.glob("*.kicad_pcb"))
    assert len(files) == n_elems - 1
    # Numbered in build order, aft tile first.
    assert files[0].name.startswith("01_place_")


def test_battery_close_step_is_low_temp_insn(tmp_path, built):
    """Placing activation_interface onto the battery column joins the cells'
    + tabs — it must reflow in low-temp In52/Sn48 (118 °C), the last step
    before potting, since SAC305 (~245 °C) would cook the TLM cells. Every
    other board-to-board step stays SAC305."""
    gen, d, panel, boards = built
    from smash.export.stack_assembly import build_stack_assembly_files

    res = build_stack_assembly_files(
        d, panel, boards, tmp_path,
        connect=lambda net, pin: gen._net(d, net).connect(pin))

    solder_by_upper = {upper: solder for _i, upper, _l, _p, _3d, solder in res}
    assert solder_by_upper["activation_interface"] == "In52Sn48"
    assert all(s == "SAC305" for u, s in solder_by_upper.items()
               if u != "activation_interface")
    # The assembly-instructions manifest is written and calls out the step.
    manifest = tmp_path / "assembly_steps.md"
    assert manifest.exists()
    assert "In52Sn48" in manifest.read_text()


def test_placed_component_is_paste_bearing_and_netted(tmp_path, built):
    gen, d, panel, boards = built
    from smash.export.stack_assembly import build_stack_assembly_files

    build_stack_assembly_files(
        d, panel, boards, tmp_path,
        connect=lambda net, pin: gen._net(d, net).connect(pin))

    # Pick the radar-on-spacer step and check the board-as-component.
    hit = list(tmp_path.glob("*place_radar_module_on_*.kicad_pcb"))
    assert hit, "expected a radar_module reflow file"
    text = hit[0].read_text()
    assert text.count("(") == text.count(")")          # KiCad-loadable

    m = re.search(r'\(footprint "BOARD_radar_module"(.*?)\n\t\)\n', text, re.S)
    assert m is not None, "board-as-component footprint missing"
    block = m.group(1)
    n_pads = block.count("(pad ")
    assert n_pads > 0
    # Every pad must be stencil-ready (paste) and carry a net.
    assert block.count('"F.Paste"') == n_pads
    assert block.count("(net ") == n_pads
