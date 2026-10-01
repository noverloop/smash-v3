"""Tests for the board-to-board ring-LGA interconnect (Phase 1):
footprint geometry, self-keying uniqueness, and the backbone pinout."""

import math

from smash import Design
from smash.parts.connectors import (
    ring_lga_footprint, backbone_pinout, add_ring_lga, is_rotationally_unique,
    CARDINALS_DEG, CARDINAL_KEEPOUT_DEG, RING_RADIUS_MM, GND_NET,
)


def _angle(pos):
    return math.degrees(math.atan2(pos[1], pos[0])) % 360.0


class TestRingFootprint:
    def test_pad_count_reasonable(self):
        fp = ring_lga_footprint()
        assert 18 <= len(fp.pads) <= 32, f"got {len(fp.pads)} pads"

    def test_cardinals_kept_clear(self):
        # No pad within the keepout half-width of any N/S/E/W flex-launch sector.
        fp = ring_lga_footprint()
        for p in fp.pads:
            a = _angle(p.position_mm)
            for c in CARDINALS_DEG:
                d = abs((a - c + 180) % 360 - 180)
                assert d >= CARDINAL_KEEPOUT_DEG - 1e-6, \
                    f"pad at {a:.1f}° intrudes on cardinal {c}°"

    def test_base_pads_on_ring(self):
        # The base-ring pads sit at the ring radius (clusters/key are inset).
        fp = ring_lga_footprint()
        radii = [math.hypot(*p.position_mm) for p in fp.pads]
        assert any(abs(r - RING_RADIUS_MM) < 1e-3 for r in radii)
        assert max(radii) <= RING_RADIUS_MM + 1e-3   # 4-decimal pad rounding


class TestSelfKeying:
    def test_pattern_is_rotationally_unique(self):
        # The clusters + radial key pad must break ALL rotational symmetry,
        # so the ring can only solder one way.
        assert is_rotationally_unique(ring_lga_footprint())

    def test_plain_ring_would_be_ambiguous(self):
        # Sanity: a ring with no clusters/key (4 identical arcs) IS symmetric,
        # proving the test actually detects ambiguity.
        fp = ring_lga_footprint(cluster_pads=0)
        # remove the lone radial key pad too → pure 4-fold arcs
        fp.pads = [p for p in fp.pads
                   if abs(math.hypot(*p.position_mm) - RING_RADIUS_MM) < 1e-3]
        assert not is_rotationally_unique(fp)


class TestBackbonePinout:
    def test_net_multiplicities(self):
        fp = ring_lga_footprint()
        pinout = backbone_pinout([p.num for p in fp.pads])
        from collections import Counter
        c = Counter(pinout.values())
        assert c["SYS_I2C_SCL"] == 1 and c["SYS_I2C_SDA"] == 1
        assert c["3V3"] == 3 and c["BAT_PROT"] == 3 and c["BAT_RAW"] == 3
        # GND is the dominant fill
        assert c[GND_NET] >= len(fp.pads) // 2
        assert sum(c.values()) == len(fp.pads)

    def test_control_bus_pair_adjacent_and_gnd_flanked(self):
        fp = ring_lga_footprint()
        nums = [p.num for p in fp.pads]
        pinout = backbone_pinout(nums)
        i_p = nums.index(next(n for n in nums if pinout[n] == "SYS_I2C_SCL"))
        i_n = nums.index(next(n for n in nums if pinout[n] == "SYS_I2C_SDA"))
        assert abs(i_p - i_n) == 1                      # adjacent
        assert pinout[nums[min(i_p, i_n) - 1]] == GND_NET   # GND flank


class TestAddRingLga:
    def test_part_has_pin_per_pad(self):
        d = Design()
        fp = ring_lga_footprint()
        chip = add_ring_lga(d, ref="J_TEST_TOP", board_tag="flight_board")
        assert len(chip.pins) == len(fp.pads)
        assert {p.num for p in chip.pins} == {p.num for p in fp.pads}
