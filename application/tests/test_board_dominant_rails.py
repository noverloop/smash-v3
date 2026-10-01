"""Tests for Board.dominant_rails(design)."""
from __future__ import annotations

from smash.state import Board, Design


def _make_design_with_power_nets():
    """Tiny synthetic design: one chip on a board, two power rails
    + one signal — verify only the power rails are counted."""
    d = Design()
    board = Board("test_tile")
    chip = d.add_chip(
        ref="U1", board_tag="test_tile",
        pins=[("1",), ("2",), ("3",), ("4",), ("5",)],
    )
    d.add_power_net("VDD",      voltage_v=3.3).connect_all(
        [chip.pin("1"), chip.pin("2"), chip.pin("3")])
    d.add_power_net("COMP_1V8", voltage_v=1.8).connect(chip.pin("4"))
    d.add_signal_net("DATA").connect(chip.pin("5"))
    return d, board


def test_dominant_rails_returns_power_only():
    d, board = _make_design_with_power_nets()
    rails = board.dominant_rails(d)
    names = [name for name, _ in rails]
    assert "VDD" in names
    assert "COMP_1V8" in names
    assert "DATA" not in names  # signal net excluded


def test_dominant_rails_sorted_by_pin_count_desc():
    d, board = _make_design_with_power_nets()
    rails = board.dominant_rails(d)
    # VDD has 3 pins, COMP_1V8 has 1 → VDD first
    assert rails == [("VDD", 3), ("COMP_1V8", 1)]


def test_dominant_rails_returns_empty_for_unused_board():
    d, _ = _make_design_with_power_nets()
    empty = Board("nobody_lives_here")
    assert empty.dominant_rails(d) == []


def test_dominant_rails_excludes_dnp_by_default():
    d = Design()
    board = Board("t")
    chip_live = d.add_chip(ref="U_LIVE", board_tag="t",
                            pins=[("1",), ("2",)])
    chip_dnp = d.add_chip(ref="U_DNP", board_tag="t", dnp=True,
                           pins=[("1",), ("2",)])
    vdd = d.add_power_net("VDD", voltage_v=3.3)
    vdd.connect(chip_live.pin("1"))
    vdd.connect(chip_dnp.pin("1"))
    vdd.connect(chip_dnp.pin("2"))
    # Only the live chip's 1 pin should count.
    rails = board.dominant_rails(d)
    assert rails == [("VDD", 1)]


def test_dominant_rails_includes_dnp_when_requested():
    d = Design()
    board = Board("t")
    chip = d.add_chip(ref="U_DNP", board_tag="t", dnp=True,
                       pins=[("1",), ("2",)])
    d.add_power_net("VDD", voltage_v=3.3).connect_all(chip.pins)
    assert board.dominant_rails(d, populated_only=False) == [("VDD", 2)]
    assert board.dominant_rails(d, populated_only=True) == []


def test_dominant_rails_tiebreak_by_name():
    d = Design()
    board = Board("t")
    chip = d.add_chip(ref="U1", board_tag="t",
                       pins=[("1",), ("2",), ("3",), ("4",)])
    d.add_power_net("BBB", voltage_v=3.3).connect_all(
        [chip.pin("1"), chip.pin("2")])
    d.add_power_net("AAA", voltage_v=3.3).connect_all(
        [chip.pin("3"), chip.pin("4")])
    # Same count → alphabetical tie-break
    assert board.dominant_rails(d) == [("AAA", 2), ("BBB", 2)]


def test_dominant_rails_multi_board_isolation():
    """Two boards sharing a power net — each tile reports only its own
    chips' pin count on that net (not the total across boards)."""
    d = Design()
    b1 = Board("tile_a")
    b2 = Board("tile_b")
    c1 = d.add_chip(ref="U_A", board_tag="tile_a",
                     pins=[("1",), ("2",)])
    c2 = d.add_chip(ref="U_B", board_tag="tile_b",
                     pins=[("1",), ("2",), ("3",)])
    vdd = d.add_power_net("VDD", voltage_v=3.3)
    vdd.connect_all(c1.pins)
    vdd.connect_all(c2.pins)
    assert b1.dominant_rails(d) == [("VDD", 2)]
    assert b2.dominant_rails(d) == [("VDD", 3)]


def test_dominant_rails_ignores_ground():
    """kind='ground' nets are NOT power and must not appear."""
    d = Design()
    board = Board("t")
    chip = d.add_chip(ref="U1", board_tag="t",
                       pins=[("1",), ("2",), ("3",), ("4",)])
    d.add_ground_net("GND").connect_all(
        [chip.pin("1"), chip.pin("2"), chip.pin("3")])
    d.add_power_net("VDD", voltage_v=3.3).connect(chip.pin("4"))
    rails = board.dominant_rails(d)
    assert rails == [("VDD", 1)]
    assert "GND" not in {n for n, _ in rails}
