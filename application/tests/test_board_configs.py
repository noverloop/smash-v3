"""Tests for build_config_panel — board-configuration variants."""
from __future__ import annotations

import pytest

from smash.layout.boards.smash_evb_v1 import build_config_panel


def _extent(panel):
    cols = [c for c, _ in panel.tiles.values()]
    rows = [r for _, r in panel.tiles.values()]
    return max(cols) + 1, max(rows) + 1


def test_three_board_snake():
    panel, boards = build_config_panel(
        ["power_board", "wakeup_board", "flight_board"])
    # 3 boards + 2 inline spacers = 5 tiles, all on distinct cells.
    assert len(panel.tiles) == 5
    assert len(set(panel.tiles.values())) == 5
    spacers = [n for n, b in boards.items() if b.is_spacer]
    assert len(spacers) == 2
    assert {"power_board", "wakeup_board", "flight_board"} <= set(boards)


def test_five_board_snake():
    names = ["power_board", "wakeup_board", "radar_module",
             "fins_module", "flight_board"]
    panel, boards = build_config_panel(names)
    assert len(panel.tiles) == 9          # 5 boards + 4 spacers
    assert len(set(panel.tiles.values())) == 9
    assert set(names) <= set(boards)


def test_branch_stubs_build_collision_free():
    from smash.state import Flex
    names = ["wakeup_board", "flight_board", "companion_compute"]
    branches = [("flight_board", "qpd_module", Flex(length_mm=70.0)),
                ("companion_compute", "camera_module", Flex(length_mm=70.0))]
    panel, boards = build_config_panel(names, branches=branches)
    assert {"qpd_module", "camera_module"} <= set(boards)
    assert len(set(panel.tiles.values())) == len(panel.tiles)


def test_single_board_config():
    panel, boards = build_config_panel(["power_board"])
    assert set(panel.tiles) == {"power_board"}


def test_empty_config_raises():
    with pytest.raises(ValueError):
        build_config_panel([])
