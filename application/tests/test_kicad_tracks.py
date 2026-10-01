"""Tests for smash.export.kicad_pcb — routed tracks + blind vias.

`board.tracks` (Track polylines) emit one `(segment …)` per consecutive
path point pair; `board.vias` spanning less than F.Cu↔B.Cu emit the
KiCad `blind` token. Coordinates flip math-y-up → KiCad y-down at the
boundary, same as every other emitter.
"""
from __future__ import annotations

import pathlib

import pytest

from smash.export import write_kicad_pcb
from smash.state import Board, Design
from smash.state.routing import Track, Via


@pytest.fixture
def tmp_pcb(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "out.kicad_pcb"


def _routed_board() -> Board:
    board = Board("companion_compute", copper_layers=20)
    board.tracks.append(Track(
        net="DDR4_DQ0", layer="In3.Cu", width_mm=0.1,
        path=[(0.0, 0.0), (1.5, 0.0), (1.5, 2.0)],
    ))
    # Blind F.Cu→In3.Cu landing on the track's far end…
    board.vias.append(Via(
        net="DDR4_DQ0", position_mm=(1.5, 2.0),
        drill_mm=0.15, pad_diameter_mm=0.25,
        from_layer="F.Cu", to_layer="In3.Cu", filled=True,
    ))
    # …plus a plain through-via for contrast.
    board.vias.append(Via(
        net="GND", position_mm=(0.0, 0.0),
        drill_mm=0.15, pad_diameter_mm=0.25,
        from_layer="F.Cu", to_layer="B.Cu",
    ))
    return board


# ── segments ──────────────────────────────────────────────────────────

def test_track_emits_one_segment_per_path_pair(tmp_pcb):
    d = Design()
    write_kicad_pcb(d, _routed_board(), tmp_pcb)
    text = tmp_pcb.read_text()
    assert text.count("(segment") == 2
    # Y flips at the boundary: (1.5, 2.0) math-y-up → 1.5 -2 in KiCad.
    assert (
        '\t(segment\n'
        '\t\t(start 0 0)\n'
        '\t\t(end 1.5 0)\n'
        '\t\t(width 0.1)\n'
        '\t\t(layer "In3.Cu")\n'
        '\t\t(net "DDR4_DQ0")\n'
    ) in text
    assert (
        '\t(segment\n'
        '\t\t(start 1.5 0)\n'
        '\t\t(end 1.5 -2)\n'
        '\t\t(width 0.1)\n'
        '\t\t(layer "In3.Cu")\n'
        '\t\t(net "DDR4_DQ0")\n'
    ) in text


def test_degenerate_tracks_skipped(tmp_pcb):
    d = Design()
    board = Board("companion_compute", copper_layers=20)
    board.tracks.append(Track(            # <2 points — nothing to draw
        net="X", layer="In3.Cu", width_mm=0.1, path=[(0.0, 0.0)]))
    board.tracks.append(Track(            # zero-length segment in path
        net="X", layer="In3.Cu", width_mm=0.1,
        path=[(0.0, 0.0), (0.0, 0.0), (1.0, 0.0)]))
    write_kicad_pcb(d, board, tmp_pcb)
    assert tmp_pcb.read_text().count("(segment") == 1


# ── blind vs through vias ─────────────────────────────────────────────

def test_blind_via_carries_blind_token(tmp_pcb):
    d = Design()
    write_kicad_pcb(d, _routed_board(), tmp_pcb)
    text = tmp_pcb.read_text()
    assert (
        '\t(via blind\n'
        '\t\t(at 1.5 -2)\n'
        '\t\t(size 0.25)\n'
        '\t\t(drill 0.15)\n'
        '\t\t(layers "F.Cu" "In3.Cu")\n'
        # inner-span vias drop unused annular rings (the EE blind-via
        # DDR field runs tracks 0.025 mm off passed-through barrels)
        '\t\t(remove_unused_layers yes)\n'
        '\t\t(keep_end_layers yes)\n'
        '\t\t(net "DDR4_DQ0")\n'
    ) in text
    # The F.Cu→B.Cu via stays a plain `(via` — exactly one of each.
    assert text.count("(via blind") == 1
    assert text.count("(via") == 2
    assert '\t(via\n\t\t(at 0 0)\n' in text


def test_reversed_full_span_is_still_through(tmp_pcb):
    """(B.Cu, F.Cu) is the same full span as (F.Cu, B.Cu) — no blind."""
    d = Design()
    board = Board("companion_compute", copper_layers=20)
    board.vias.append(Via(
        net="GND", position_mm=(0.0, 0.0),
        drill_mm=0.15, pad_diameter_mm=0.25,
        from_layer="B.Cu", to_layer="F.Cu",
    ))
    write_kicad_pcb(d, board, tmp_pcb)
    assert "(via blind" not in tmp_pcb.read_text()
