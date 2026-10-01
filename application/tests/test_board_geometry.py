"""Tests for smash.state.board_geometry — value objects + JSON loader."""
from __future__ import annotations

import pytest

from smash.state import Board
from smash.state.board_geometry import (
    BoardGeometry,
    Hole,
    Keepout,
    POTTING_HOLE_KEEPOUT_HALF_MM,
    all_known_names,
    load_board_geometry,
)
from smash.layout.cavities import (
    POTTING_HOLE_DIA_MM,
    POTTING_HOLE_RADIUS_MM,
)


# ── registry has every board name we expect ───────────────────────────

EXPECTED_NAMES = {
    "power_board", "wakeup_board", "flight_board", "radar_module",
    "fins_module", "fin_ble_board",
    "companion_compute", "companion_io", "nose_cap",
    "activation_interface", "aft_end_board", "cell_floor_board",
    "camera_module", "qpd_module",
    "nfc_antenna_flex",
    "yagi_ant_a_flex", "yagi_ant_b_flex",
}


def test_registry_contains_all_evb_boards():
    assert set(all_known_names()) == EXPECTED_NAMES


# ── per-board geometry sanity ─────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "power_board", "wakeup_board", "flight_board", "radar_module",
    "fins_module",
    "companion_compute", "companion_io", "nose_cap",
])
def test_main_rigid_boards_are_d34_with_potting(name):
    g = load_board_geometry(name)
    assert g.shape == "circle"
    assert g.diameter_mm == 34.0
    assert len(g.holes) == 2
    assert all(h.tag == "potting" for h in g.holes)
    assert all(h.diameter_mm == POTTING_HOLE_DIA_MM for h in g.holes)
    assert all(not h.plated for h in g.holes)  # NPTH
    # Holes sit on a 15-mm radial circle around the centre
    for h in g.holes:
        r = (h.position_mm[0] ** 2 + h.position_mm[1] ** 2) ** 0.5
        assert r == pytest.approx(POTTING_HOLE_RADIUS_MM, abs=1e-6)


def test_activation_interface_is_d34_circle_with_potting():
    """User-confirmed (battery reorg): activation_interface is the
    battery-connector tile, and potting is injected into the battery
    compartment FROM the activation side — so it now carries the
    standard NW/SE potting holes (the pogo array having moved to
    aft_end_board freed the bottom face). The aft_end_board, now the
    sealed aft floor, has none."""
    g = load_board_geometry("activation_interface")
    assert g.shape == "circle"
    assert g.diameter_mm == 34.0
    assert len(g.holes) == 2
    assert all(h.tag == "potting" for h in g.holes)
    assert g.dxf_path is None


def test_aft_end_board_is_d34_circle_with_no_potting():
    """The aft_end_board is the sealed aft floor of the stack: potting
    enters from the activation side, so the aft board takes NO potting
    holes (would breach the seal)."""
    g = load_board_geometry("aft_end_board")
    assert g.shape == "circle"
    assert g.diameter_mm == 34.0
    assert g.holes == []
    assert g.keepouts == []


def test_camera_module_is_d15_circle():
    g = load_board_geometry("camera_module")
    assert g.shape == "circle"
    assert g.diameter_mm == 15.0
    assert g.holes == []


def test_qpd_module_is_d20_circle():
    g = load_board_geometry("qpd_module")
    assert g.shape == "circle"
    assert g.diameter_mm == 20.0
    assert g.holes == []


def test_nfc_antenna_flex_is_round():
    # Reshaped from the 21×36 rect to a Ø22 round coil so it S-folds like
    # the camera/qpd tiles (17-turn round spiral, ~4.82 µH).
    g = load_board_geometry("nfc_antenna_flex")
    assert g.shape == "circle"
    assert g.diameter_mm == 22.0
    assert g.rect_dimensions is None


# ── spacer fallback ───────────────────────────────────────────────────

def test_spacer_default_template():
    """Any name starting with `spacer_` not in the registry falls back
    to `_spacer_default` — Ø34 circle with NO fixed potting holes. The
    spacer's 2 potting through-holes are drilled at placement time by
    attach_cavities_to_spacers(), fold-projected from the neighbouring
    tiles' holes so they align with the PCB through the accordion fold."""
    g = load_board_geometry("spacer_power_board_wakeup_board")
    assert g.shape == "circle"
    assert g.diameter_mm == 34.0
    assert len(g.holes) == 0


def test_spacer_unknown_name_still_falls_back():
    g = load_board_geometry("spacer_anything_at_all")
    assert g.shape == "circle"
    assert len(g.holes) == 0


def test_unknown_non_spacer_raises():
    with pytest.raises(KeyError, match="no board_geometries.json entry"):
        load_board_geometry("totally_made_up_board")


# ── potting hole keepouts have correct size ──────────────────────────

def test_potting_hole_keepouts_are_square_around_each_hole():
    g = load_board_geometry("flight_board")
    assert len(g.keepouts) == 2
    h = POTTING_HOLE_KEEPOUT_HALF_MM
    for ko, hole in zip(g.keepouts, g.holes):
        assert ko.tag == "potting_hole"
        assert ko.scope == "component"
        hx, hy = hole.position_mm
        # 4 corners around hole at ±1.5 mm
        expected = {(hx - h, hy - h), (hx + h, hy - h),
                    (hx + h, hy + h), (hx - h, hy + h)}
        assert set(tuple(p) for p in ko.polygon) == expected


# ── Board auto-wires geometry from registry ───────────────────────────

def test_board_autoload_by_name():
    b = Board("flight_board")
    assert b.geometry is not None
    assert b.geometry.shape == "circle"
    assert b.geometry.diameter_mm == 34.0
    # Shortcuts
    assert b.diameter_mm == 34.0
    assert b.rect_dimensions is None
    assert b.outline_dxf is None


def test_board_unknown_name_geometry_none():
    """Test fixtures construct ad-hoc Boards. Unknown name → geometry
    stays None (no auto-fail), and the property shortcuts return None."""
    b = Board("some_test_fixture_board")
    assert b.geometry is None
    assert b.diameter_mm is None
    assert b.rect_dimensions is None
    assert b.outline_dxf is None


def test_board_inline_geometry_overrides_autoload():
    """Caller can pass `geometry=...` to override the JSON default."""
    custom = BoardGeometry(shape="circle", diameter_mm=42.0)
    b = Board("flight_board", geometry=custom)
    assert b.geometry is custom
    assert b.diameter_mm == 42.0


# ── value object round-trips through to_dict ──────────────────────────

def test_hole_to_dict_roundtrip():
    h = Hole(position_mm=(1.0, 2.0), diameter_mm=2.0,
             plated=False, tag="potting")
    d = h.to_dict()
    assert d == {"position_mm": [1.0, 2.0], "diameter_mm": 2.0,
                 "plated": False, "tag": "potting", "note": None}


def test_keepout_to_dict_roundtrip():
    k = Keepout(polygon=[(0, 0), (1, 0), (1, 1)],
                layers=("F.Cu",), scope="component", tag="x")
    d = k.to_dict()
    assert d["polygon"] == [[0, 0], [1, 0], [1, 1]]
    assert d["layers"] == ["F.Cu"]
    assert d["scope"] == "component"


def test_geometry_to_dict_keeps_holes_keepouts():
    g = load_board_geometry("flight_board")
    d = g.to_dict()
    assert d["shape"] == "circle"
    assert d["diameter_mm"] == 34.0
    assert len(d["holes"]) == 2
    assert len(d["keepouts"]) == 2
    assert "flex_cutouts" not in d   # panel-build artifact, not a definition
