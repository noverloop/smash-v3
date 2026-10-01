"""Tests for the per-board PCB fab notes writer."""
import pathlib

import pytest

from smash.state import Board, CuCoinInsert
from smash.export.pcb_fab_notes import write_pcb_fab_notes


@pytest.fixture
def radar_with_coin():
    b = Board("radar_module", top_substrate="rogers_ro4350b_5mil",
              copper_layers=20)
    b.set_fitted_stackup()
    b.cu_coin_inserts = [CuCoinInsert(
        position_mm=(0.0, 0.0),
        length_mm=20.0, width_mm=20.0,
        ladder_length_mm=16.0, ladder_width_mm=16.0,
        thickness_mm=3.0, z_top_mm=3.15,
        flange_thickness_mm=0.5,
        corner_chamfer_radius_mm=5.0,
        kind="T",
        note="under U_AWR",
    )]
    return b


@pytest.fixture
def bare_flight():
    b = Board("flight_board")
    b.set_fitted_stackup()
    return b


class TestPCBFabNotes:
    def test_writes_file_with_solder_section(self, radar_with_coin, tmp_path):
        out = tmp_path / "radar_fab.md"
        r = write_pcb_fab_notes(radar_with_coin, out)
        assert pathlib.Path(r["output_path"]).exists()
        text = out.read_text()
        assert "## Solder paste" in text
        assert "SAC305" in text
        # The fab-profile-sourced solder mechanical constants are in the file
        assert "41 GPa" in text                  # E from profile
        assert "0.4" in text                     # ν from profile
        assert "34 MPa" in text                  # shear strength

    def test_includes_layer_count_override(self, radar_with_coin, tmp_path):
        out = tmp_path / "radar_fab.md"
        write_pcb_fab_notes(radar_with_coin, out)
        text = out.read_text()
        assert "20-layer" in text                # the per-board override
        assert "ROGERS_RO4350B_5MIL" in text     # top substrate callout

    def test_includes_coin_section_in_ncab_symbols(self, radar_with_coin, tmp_path):
        out = tmp_path / "radar_fab.md"
        write_pcb_fab_notes(radar_with_coin, out)
        text = out.read_text()
        assert "NCAB Copper Coin" in text
        # Each NCAB symbol the fab cross-references
        for sym in ("NCAB X", "NCAB Y", "NCAB X1", "NCAB Y1",
                    "NCAB H", "NCAB H1", "NCAB H2", "NCAB R", "Q ("):
            assert sym in text, f"missing NCAB symbol {sym!r} in fab notes"
        assert "under U_AWR" in text             # the coin note flows through

    def test_no_coin_section_when_board_has_no_coins(self, bare_flight, tmp_path):
        out = tmp_path / "flight_fab.md"
        write_pcb_fab_notes(bare_flight, out)
        text = out.read_text()
        assert "## Solder paste" in text
        assert "Cu coin" not in text             # no coin section emitted

    def test_summary_string(self, radar_with_coin, bare_flight, tmp_path):
        r1 = write_pcb_fab_notes(radar_with_coin, tmp_path / "r.md")
        r2 = write_pcb_fab_notes(bare_flight, tmp_path / "f.md")
        assert r1["summary"] == "20L + 1 Cu coin"
        assert r2["summary"] == "14L"

    def test_refuses_non_rigid(self, tmp_path):
        spacer = Board("spacer_x", kind="spacer")
        with pytest.raises(ValueError, match="for rigid tiles"):
            write_pcb_fab_notes(spacer, tmp_path / "x.md")
