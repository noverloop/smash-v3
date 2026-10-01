"""Tests for the spacer CAM-notes sidecar.

The Markdown notes file ships alongside each spacer STEP and tells the
fab the laminate + finish and — critically — the filled-via spec.
Spacers are FR4 PCB interposers (the CNC-Al + anodise build was
abandoned with the snake-flex interconnect); the lands on both faces
are joined by filled through-vias that carry the backbone, so the fill
must be capped + plated over to seat the lands co-planar.
"""
import pathlib
import pytest

from smash.state import Board
from smash.state.board_geometry import BoardGeometry, Hole
from smash.state.routing.via import Via
from smash.export.spacer_step import (
    SPACER_FINISH_DEFAULT,
    SPACER_MATERIAL_DEFAULT,
    write_spacer_cam_notes,
)


def _bare_spacer(name: str = "spacer_a_b") -> Board:
    """A spacer-marked Ø34 disc with no cavities or holes — exercises
    the minimal output path."""
    b = Board(name, kind="spacer",
              geometry=BoardGeometry(shape="circle", diameter_mm=34.0))
    return b


def _populated_spacer(name: str = "spacer_a_b") -> Board:
    """Spacer with 2 NPTH potting holes (Ø3 mm) — matches what
    `attach_cavities_to_spacers()` would emit."""
    g = BoardGeometry(shape="circle", diameter_mm=34.0,
                       holes=[Hole(position_mm=(9.9, 9.9),
                                    diameter_mm=3.0, plated=False,
                                    tag="potting"),
                              Hole(position_mm=(-9.9, -9.9),
                                    diameter_mm=3.0, plated=False,
                                    tag="potting")])
    return Board(name, kind="spacer", geometry=g)


def _via_spacer(name: str = "spacer_a_b") -> Board:
    """Spacer with two filled LGA-joining vias — matches what
    `place_lga_lands()` appends per land."""
    b = _bare_spacer(name)
    b.vias.append(Via(net="GND", position_mm=(2.0, 0.0), drill_mm=0.3,
                      pad_diameter_mm=0.6, filled=True))
    b.vias.append(Via(net="VBAT", position_mm=(-2.0, 0.0), drill_mm=0.3,
                      pad_diameter_mm=0.6, filled=True))
    return b


class TestCamNotesContent:
    def test_writes_markdown_file(self, tmp_path):
        sp = _bare_spacer()
        out = tmp_path / "spacer_a_b_cam.md"
        r = write_spacer_cam_notes(sp, out)
        assert out.exists() and out.stat().st_size > 100
        assert r["output_path"] == str(out)

    def test_material_callout_present(self, tmp_path):
        sp = _bare_spacer()
        out = tmp_path / "cam.md"
        write_spacer_cam_notes(sp, out)
        text = out.read_text()
        assert SPACER_MATERIAL_DEFAULT in text
        assert "FR4" in text

    def test_finish_callout_present(self, tmp_path):
        sp = _bare_spacer()
        out = tmp_path / "cam.md"
        write_spacer_cam_notes(sp, out)
        text = out.read_text()
        assert "ENIG" in text

    def test_filled_via_callout(self, tmp_path):
        """The filled-via line is the critical FR4-interposer callout —
        without it a fab might leave the barrels open and the LGA lands
        above wouldn't seat flat."""
        sp = _via_spacer()
        out = tmp_path / "cam.md"
        write_spacer_cam_notes(sp, out)
        text = out.read_text()
        assert "2 filled through-via" in text
        assert "co-planar" in text

    def test_fr4_rationale_present(self, tmp_path):
        """The 'why FR4, not anodised Al' paragraph explains why the
        spacer is a routable interposer (vias + solder) rather than a
        milled metal disc."""
        sp = _bare_spacer()
        out = tmp_path / "cam.md"
        write_spacer_cam_notes(sp, out)
        text = out.read_text()
        assert "interposer" in text.lower()
        assert "backbone" in text.lower()
        assert "copper-coin" in text.lower()

    def test_explicit_material_override(self, tmp_path):
        sp = _bare_spacer()
        out = tmp_path / "cam.md"
        r = write_spacer_cam_notes(sp, out,
                                     material="Stainless 316L",
                                     finish="Passivate per ASTM A967")
        assert r["material"] == "Stainless 316L"
        text = out.read_text()
        assert "Stainless 316L" in text
        assert "Passivate" in text


class TestCamNotesFeatures:
    def test_no_holes_no_cavities(self, tmp_path):
        sp = _bare_spacer()
        out = tmp_path / "cam.md"
        write_spacer_cam_notes(sp, out)
        text = out.read_text()
        assert "no NPTH holes" in text

    def test_no_vias_reported(self, tmp_path):
        sp = _bare_spacer()
        out = tmp_path / "cam.md"
        write_spacer_cam_notes(sp, out)
        text = out.read_text()
        assert "no filled vias" in text

    def test_potting_holes_reported(self, tmp_path):
        sp = _populated_spacer()
        out = tmp_path / "cam.md"
        r = write_spacer_cam_notes(sp, out)
        assert r["n_holes"] == 2
        text = out.read_text()
        assert "2 NPTH potting hole" in text
        assert "Ø 3.0 mm" in text

    def test_summary_dict_counts(self, tmp_path):
        sp = _populated_spacer()
        out = tmp_path / "cam.md"
        r = write_spacer_cam_notes(sp, out)
        assert r["material"] == SPACER_MATERIAL_DEFAULT
        assert r["finish"] == SPACER_FINISH_DEFAULT
        assert r["n_holes"] == 2
        assert r["n_top_cavities"] == 0
        assert r["n_bot_cavities"] == 0
