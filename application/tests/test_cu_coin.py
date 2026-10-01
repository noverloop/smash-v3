"""Tests for the CuCoinInsert dataclass."""
import pytest

from smash.state import CuCoinInsert


# ── geometry / validation ─────────────────────────────────────────────


class TestCuCoinInsertGeometry:
    def test_basic_T_coin(self):
        c = CuCoinInsert(
            position_mm=(0, 0),
            length_mm=20.0, width_mm=7.0,
            ladder_length_mm=16.0, ladder_width_mm=5.0,
            thickness_mm=1.0, z_top_mm=1.4,
            flange_thickness_mm=0.5, kind="T",
        )
        assert c.shank_thickness_mm == pytest.approx(0.5)
        assert c.z_bottom_mm == pytest.approx(0.4)
        # Q (flange overhang per side)
        assert c.Q_long_mm == pytest.approx(2.0)
        assert c.Q_short_mm == pytest.approx(1.0)

    def test_ladder_cannot_exceed_flange(self):
        with pytest.raises(ValueError, match="can't extend past flange"):
            CuCoinInsert(
                position_mm=(0, 0),
                length_mm=10.0, width_mm=7.0,
                ladder_length_mm=12.0,    # > length
                ladder_width_mm=5.0,
                thickness_mm=1.0, z_top_mm=1.0,
            )

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError, match="kind must be one of"):
            CuCoinInsert(
                position_mm=(0, 0),
                length_mm=10.0, width_mm=7.0,
                ladder_length_mm=10.0, ladder_width_mm=7.0,
                thickness_mm=1.0, z_top_mm=1.0, kind="X",
            )

    def test_i_coin_cannot_have_flange_thickness(self):
        with pytest.raises(ValueError, match="I-coin must have"):
            CuCoinInsert(
                position_mm=(0, 0),
                length_mm=10.0, width_mm=7.0,
                ladder_length_mm=10.0, ladder_width_mm=7.0,
                thickness_mm=1.0, z_top_mm=1.0,
                flange_thickness_mm=0.3, kind="I",
            )

    def test_covers_position_inside_flange_centre(self):
        c = CuCoinInsert(
            position_mm=(0, 0),
            length_mm=20.0, width_mm=7.0,
            ladder_length_mm=16.0, ladder_width_mm=5.0,
            thickness_mm=1.0, z_top_mm=1.0,
        )
        # Centre is inside.
        assert c.covers_position(0, 0)
        # Inside along long axis.
        assert c.covers_position(9, 0)
        # Outside long axis.
        assert not c.covers_position(11, 0)
        # Outside short axis.
        assert not c.covers_position(0, 4)

    def test_covers_position_with_clearance(self):
        """A small chip with corner_reach = 2 mm at (0, 0) inside a 20 × 7
        flange should be covered (2 ≤ 3.5 in short axis)."""
        c = CuCoinInsert(
            position_mm=(0, 0),
            length_mm=20.0, width_mm=7.0,
            ladder_length_mm=16.0, ladder_width_mm=5.0,
            thickness_mm=1.0, z_top_mm=1.0,
        )
        assert c.covers_position(0, 0, clearance_mm=2.0)
        # A bigger chip (5 mm half-span) WON'T fit short-axis-wise.
        assert not c.covers_position(0, 0, clearance_mm=5.0)

    def test_rotation_aligns_long_axis(self):
        """A 20 × 7 strip at the origin rotated 90° has its long axis
        along +Y. A point at (0, 9) should be covered (inside the long
        axis), but (9, 0) should not (outside the short axis)."""
        c = CuCoinInsert(
            position_mm=(0, 0),
            length_mm=20.0, width_mm=7.0,
            ladder_length_mm=16.0, ladder_width_mm=5.0,
            thickness_mm=1.0, z_top_mm=1.0,
            rotation_deg=90.0,
        )
        assert c.covers_position(0, 9)
        assert not c.covers_position(9, 0)

    def test_flange_area_no_chamfer(self):
        c = CuCoinInsert(
            position_mm=(0, 0),
            length_mm=20.0, width_mm=10.0,
            ladder_length_mm=16.0, ladder_width_mm=8.0,
            thickness_mm=1.0, z_top_mm=1.0,
        )
        assert c.flange_area_mm2 == pytest.approx(200.0)

    def test_flange_area_with_chamfer(self):
        """Each corner loses R²·(1 − π/4) of area; four corners total
        4·R²·(1 − π/4). For 20 × 20 with R = 5 mm: 21.46 mm² removed."""
        import math
        c = CuCoinInsert(
            position_mm=(0, 0),
            length_mm=20.0, width_mm=20.0,
            ladder_length_mm=16.0, ladder_width_mm=16.0,
            thickness_mm=1.0, z_top_mm=1.0,
            corner_chamfer_radius_mm=5.0,
        )
        expected = 400.0 - 4.0 * 25.0 * (1.0 - math.pi / 4.0)
        assert c.flange_area_mm2 == pytest.approx(expected)

    def test_chamfer_validation_rejects_overlapping_arcs(self):
        with pytest.raises(ValueError, match="chamfer arcs would overlap"):
            CuCoinInsert(
                position_mm=(0, 0),
                length_mm=10.0, width_mm=8.0,
                ladder_length_mm=10.0, ladder_width_mm=8.0,
                thickness_mm=1.0, z_top_mm=1.0,
                corner_chamfer_radius_mm=5.0,    # > min(L,W)/2 = 4
            )

