"""Tests for smash.export.gerbers — the kicad-cli fab-output driver.

The end-to-end tests need a working kicad-cli (same dependency as the
STEP exports) and skip cleanly without one, so CI stays green on
machines without KiCad.
"""
from __future__ import annotations

import zipfile

import pytest

from smash.export import write_kicad_pcb
from smash.export.gerbers import fab_layer_list, write_gerbers
from smash.state import Board, Design


def _kicad_cli():
    from smash.export.kicad_step import find_kicad_cli, KiCadCliNotFound
    try:
        return find_kicad_cli()
    except KiCadCliNotFound:
        return None


requires_kicad = pytest.mark.skipif(
    _kicad_cli() is None, reason="kicad-cli not installed")


# ── layer list derivation ─────────────────────────────────────────────

def test_fab_layer_list_matches_fitted_stackup():
    """Copper set comes from the same fitted stackup as the .kicad_pcb
    layer table (default fit = 14L), followed by the fixed fab tail."""
    layers = fab_layer_list(Board("flight_board"))
    copper = [l for l in layers if l.endswith(".Cu")]
    assert copper[0] == "F.Cu" and copper[-1] == "B.Cu"
    assert len(copper) == 14
    assert copper[1:-1] == [f"In{i}.Cu" for i in range(1, 13)]
    assert layers[-1] == "Edge.Cuts"
    for side in ("F", "B"):
        assert f"{side}.Mask" in layers
        assert f"{side}.SilkS" in layers
        assert f"{side}.Paste" in layers


def test_fab_layer_list_respects_layer_override():
    """A 20L coined-tile stackup plots 20 copper layers."""
    copper = [l for l in fab_layer_list(Board("companion_compute",
                                              copper_layers=20))
              if l.endswith(".Cu")]
    assert len(copper) == 20
    assert copper[1:-1] == [f"In{i}.Cu" for i in range(1, 19)]


# ── end-to-end plot (needs kicad-cli) ─────────────────────────────────

@requires_kicad
def test_write_gerbers_full_set(tmp_path):
    """A bare Ø34 tile plots every copper layer, the fab tail, the
    Excellon PTH/NPTH pair + maps, and a job file — all zipped."""
    d = Design()
    board = Board("flight_board")           # Ø34, 2 NPTH potting holes
    pcb = tmp_path / "flight_board.kicad_pcb"
    write_kicad_pcb(d, board, pcb)
    r = write_gerbers(pcb, board)

    files = {p.name for p in r["dir"].iterdir()}
    # 14 copper: F/B + 12 inner
    assert "flight_board-F_Cu.gtl" in files
    assert "flight_board-B_Cu.gbl" in files
    for i in range(1, 13):
        assert f"flight_board-In{i}_Cu.g{i}" in files
    assert r["n_copper"] == 14
    # outline + job + drill set (potting holes are NPTH)
    assert "flight_board-Edge_Cuts.gm1" in files
    assert "flight_board-job.gbrjob" in files
    for drl in ("flight_board-PTH.drl", "flight_board-NPTH.drl",
                "flight_board-PTH-drl_map.gbr",
                "flight_board-NPTH-drl_map.gbr"):
        assert drl in files
    npth = (r["dir"] / "flight_board-NPTH.drl").read_text()
    assert "T1C3.000" in npth               # Ø3.0 mm potting holes

    # zip mirrors the directory, sits beside the pcb
    assert r["zip"] == pcb.parent / "flight_board_gerbers.zip"
    assert set(zipfile.ZipFile(r["zip"]).namelist()) == files
    assert r["n_files"] == len(files)


@requires_kicad
def test_write_gerbers_clears_stale_plots(tmp_path):
    """A re-run must not leave plots from a previous (wider) layer set
    behind — stale fab files are the classic wrong-board-ordered bug."""
    d = Design()
    board = Board("flight_board")
    pcb = tmp_path / "flight_board.kicad_pcb"
    write_kicad_pcb(d, board, pcb)
    r1 = write_gerbers(pcb, board)
    stale = r1["dir"] / "flight_board-In18_Cu.g18"   # not in a 14L set
    stale.write_text("stale layer from an old 20L run")
    r2 = write_gerbers(pcb, board)
    assert not stale.exists()
    assert set(zipfile.ZipFile(r2["zip"]).namelist()) == {
        p.name for p in r2["dir"].iterdir()}
