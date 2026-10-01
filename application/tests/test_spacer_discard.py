"""The radar↔nose_cap spacer is a SCAFFOLD (Stage 3 of the radar forward-end
rework). `build_config_panel` + `build_spacers` create it so `place_lga_lands`
lays the backbone lands on the radar TOP and nose_cap BOTTOM faces (each index
carrying the same net, so they mate pad-to-pad). The thick nose_cap (1.455 mm)
then clears the AWR on its own, so there is NO physical spacer: after the lands
are placed, `_drop_radar_nose_spacer` removes it entirely. These tests lock in
that contract — the radar and nose_cap end up directly stacked, joined by the
surviving radar-top/nose_cap-bottom lands.
"""
from __future__ import annotations

import importlib
import pathlib
import sys


SPACER = "spacer_radar_module_nose_cap"


def _build_radar_nose_to_lands():
    """Replicate `_generate_config({radar_module, nose_cap})` up to + including
    the LGA lands, but stop BEFORE the discard so a test can inspect both sides.
    """
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_maximalist_system")
    finally:
        sys.path.pop(0)

    board_set = {"radar_module", "nose_cap"}
    d = gen.Design()
    gen._prime_power_rails(d)
    for bn in board_set:
        gen._BOARD_BUILDERS[bn](d)
    snake = [b for b in gen._MASTER_SNAKE if b in board_set]
    panel, boards = gen.build_config_panel(snake, branches=[],
                                           straight=gen._STRAIGHT_SNAKE)
    gen.build_spacers(d, boards)
    gen._set_dynamic_spacer_thickness(d, boards)
    gen._mark_preplace_keepouts(d, boards)
    gen.place_design(d, panel, boards)
    gen._mark_radar_block_cutout(boards)
    gen._mark_usb_cavity(boards)
    gen.place_lga_lands(d, panel, boards,
                        connect=lambda net, pin: gen._net(d, net).connect(pin))
    return gen, d, panel, boards


def test_scaffold_spacer_present_before_discard():
    """The scaffold must exist (with pass-through land chips) pre-discard —
    otherwise the lands would never land on the right faces."""
    _gen, d, panel, boards = _build_radar_nose_to_lands()
    assert SPACER in boards
    assert SPACER in panel.snake_chain
    assert any(getattr(c, "board_tag", None) == SPACER for c in d.chips)


def test_discard_removes_spacer_everywhere():
    """After the discard: board, chain slot, tile, and every pass-through land
    chip + its net pins are gone — and radar/nose_cap plus their own lands
    survive untouched."""
    gen, d, panel, boards = _build_radar_nose_to_lands()
    dropped = {c.ref for c in d.chips if getattr(c, "board_tag", None) == SPACER}
    assert dropped, "scaffold spacer should carry pass-through land chips"
    n_radar = sum(getattr(c, "board_tag", None) == "radar_module" for c in d.chips)
    n_nose = sum(getattr(c, "board_tag", None) == "nose_cap" for c in d.chips)

    gen._drop_radar_nose_spacer(d, panel, boards)

    assert SPACER not in boards
    assert SPACER not in panel.snake_chain
    assert SPACER not in (panel.tiles or {})
    # the spacer's pass-through land chips are gone …
    assert not any(getattr(c, "board_tag", None) == SPACER for c in d.chips)
    # … and no net still references one of them (no orphan pins)
    assert not [(n.name, r) for n in d.nets for r, _ in n.pins if r in dropped]
    # radar + nose_cap survive; only the spacer's lands were removed
    assert "radar_module" in boards and "nose_cap" in boards
    assert sum(getattr(c, "board_tag", None) == "radar_module" for c in d.chips) == n_radar
    assert sum(getattr(c, "board_tag", None) == "nose_cap" for c in d.chips) == n_nose


def test_discard_is_idempotent():
    """A second call (or a config without the spacer) must be a safe no-op."""
    gen, d, panel, boards = _build_radar_nose_to_lands()
    gen._drop_radar_nose_spacer(d, panel, boards)
    gen._drop_radar_nose_spacer(d, panel, boards)   # must not raise
    assert SPACER not in boards
