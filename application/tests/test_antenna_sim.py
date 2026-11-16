"""Sleeve-antenna simulation model (smash.sim.antenna) — geometry only; the
FDTD run itself needs the `smash-openems` Docker image and is not part of
the unit suite."""
from __future__ import annotations

import math

import pytest

from smash.sim.antenna import cases, geometry as g
from smash.parts.castellations import ANTENNA_FEED_ANGLES_DEG


def test_half_wave_slot_length():
    assert g.half_wave_slot_mm(2.4, 1.0) == pytest.approx(62.46, abs=0.05)
    assert g.half_wave_slot_mm(2.4, 2.25) == pytest.approx(41.64, abs=0.05)


def test_cell_gaps_follow_rotation():
    assert g.cell_gap_angles(90.0) == [30.0, 150.0, 270.0]
    assert g.cell_gap_angles(70.0) == [10.0, 130.0, 250.0]


@pytest.mark.parametrize("opt", ["A", "B", "C"])
def test_options_fit_the_tower_and_sector(opt):
    m = cases.option_model(opt)
    z0, z1 = m.z_extent
    a0, a1 = g.ANTENNA_SECTOR_DEG
    assert len(m.slots) == 3 and len(m.ports) == 3
    assert g.slot_angles_clear_of_gnd(m.slots)
    for s in m.slots:
        for sec in s.sectors(g.SLEEVE_R_OUT_MM - 0.4, g.SLEEVE_R_OUT_MM, "lds_lcp", 12):
            assert z0 - 1e-6 <= sec.z0 and sec.z1 <= z1 + 1e-6, f"{s.name} leaves the tower"
            assert a0 - 2.0 <= sec.a0 and sec.a1 <= a1 + 2.0, f"{s.name} leaves the sector"
        # every slot is (close to) half a wavelength at its design frequency
        assert s.total_length == pytest.approx(
            g.half_wave_slot_mm(s.f_design_ghz, cases.EPS_EFF), rel=0.02)


def test_axial_feeds_sit_at_the_wakeup_castellation_level():
    for opt in ("A", "B"):
        for p in cases.option_model(opt).ports:
            assert p.z == pytest.approx(g.BOARD_MID_Z_MM["wakeup_board"], abs=0.01)
            assert p.axis == "tangential"


def test_option_b_slots_do_not_cross():
    m = cases.option_model("B")
    secs = [s for s in m.sectors if s.name.startswith(("S1_", "S2_", "S3_"))]
    for i, a in enumerate(secs):
        for b in secs[i + 1:]:
            if a.name[:2] == b.name[:2]:
                continue
            overlap_z = a.z0 < b.z1 and b.z0 < a.z1
            overlap_a = a.a0 < b.a1 and b.a0 < a.a1
            assert not (overlap_z and overlap_a), f"{a.name} crosses {b.name}"


def test_model_json_round_trip():
    d = g.model_to_dict(cases.option_model("C"), excite="P_S2")
    assert d["excite"] == "P_S2"
    assert {"lds_lcp", "potting_black", "fr4"} <= set(d["materials"])
    assert all("priority" in s for s in d["sectors"])


def test_feed_castellations_cover_the_three_slots():
    assert {"ANT_HF_S1", "ANT_HF_S2", "ANT_HF_S3"} <= set(ANTENNA_FEED_ANGLES_DEG)
