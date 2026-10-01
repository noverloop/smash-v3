"""Tests for smash.export.stackup_step — folded-tower FEA assembly.

Skips when cadquery isn't installed.
"""
from __future__ import annotations

import math

import pytest

cq = pytest.importorskip("cadquery")

from smash.state import Design, Board
from smash.state.board_geometry import BoardGeometry
from smash.export.stackup_step import write_stackup_step, build_board_solid


def _disc_board(name: str) -> Board:
    return Board(name, geometry=BoardGeometry(shape="circle", diameter_mm=34.0))


def test_build_board_solid_volume():
    solid = build_board_solid(_disc_board("x"), 2.0)
    vol = solid.val().Volume()
    assert vol == pytest.approx(math.pi * 17.0 ** 2 * 2.0, rel=0.02)


def test_stackup_assembles_boards(tmp_path):
    d = Design()
    boards = {"a": _disc_board("a"), "b": _disc_board("b")}
    out = tmp_path / "stack.step"
    r = write_stackup_step(d, boards, ["a", "b"], out,
                           with_components=False, with_potting=False)
    assert out.is_file() and out.stat().st_size > 0
    assert r["n_boards"] == 2
    assert r["n_spacers"] == 0
    assert r["height_mm"] == pytest.approx(2 * 2.226, abs=0.01)
    assert out.read_text(errors="ignore").lstrip().startswith("ISO-10303-21")


def test_stackup_skips_unknown_names(tmp_path):
    d = Design()
    boards = {"a": _disc_board("a")}
    r = write_stackup_step(d, boards, ["a", "missing"], tmp_path / "s.step",
                           with_components=False, with_potting=False)
    assert r["n_boards"] == 1


# ── layered-rigid stack ───────────────────────────────────────────────


def _fitted_disc(name: str) -> Board:
    """Disc-outline tile with a fitted stackup so the layered iterator
    has Cu + dielectric layers to walk."""
    b = Board(name,
              geometry=BoardGeometry(shape="circle", diameter_mm=34.0))
    return b.set_fitted_stackup()


def test_stackup_layered_rigid_expands_each_tile(tmp_path):
    """With `with_layered_rigid=True`, each rigid tile is expanded
    into its per-layer bodies (Cu + dielectric + soldermask) instead
    of a single FR4 disc."""
    from smash import default_fab_profile
    d = Design()
    boards = {"a": _fitted_disc("a"), "b": _fitted_disc("b")}
    out = tmp_path / "stack_layered.step"
    r = write_stackup_step(d, boards, ["a", "b"], out,
                           with_components=False, with_potting=False,
                           with_layered_rigid=True,
                           fab=default_fab_profile())
    assert out.is_file() and out.stat().st_size > 0
    assert r["n_boards"] == 2          # still 2 logical tiles
    # 14L FR4 board → 14 Cu + 13 dielectric + 2 mask = 29 bodies per tile.
    # Two tiles → 58 layered bodies in the assembly.
    assert r["n_layered_bodies"] == 58


def test_stackup_layered_default_off(tmp_path):
    """Default behaviour stays the single-FR4-disc fast path."""
    d = Design()
    boards = {"a": _fitted_disc("a"), "b": _fitted_disc("b")}
    out = tmp_path / "stack_single.step"
    r = write_stackup_step(d, boards, ["a", "b"], out,
                           with_components=False, with_potting=False)
    # No layered expansion → counter stays at 0.
    assert r["n_layered_bodies"] == 0
    # Legacy single-FR4 path: each tile still adds ONE FR4 body.
    assert r["n_boards"] == 2
