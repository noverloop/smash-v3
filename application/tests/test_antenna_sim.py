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


@pytest.mark.parametrize("opt,n", [("A", 3), ("B", 3), ("C", 3), ("C2", 2)])
def test_options_fit_the_tower_and_sector(opt, n):
    m = cases.option_model(opt)
    z0, z1 = m.z_extent
    a0, a1 = g.ANTENNA_SECTOR_DEG
    assert len(m.slots) == n and len(m.ports) == n
    if opt in ("C", "C2"):          # A/B are historic; GND castellations moved 2026-11-17
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


def test_c2_is_c_without_the_middle_slot():
    c = {s.name: s for s in cases.option_slots("C")}
    c2 = cases.option_slots("C2")
    assert [s.name for s in c2] == ["S1", "S3"]
    assert all(s == c[s.name] for s in c2)


@pytest.mark.parametrize("opt,mat", [("A", "composite"), ("C", "pec")])
def test_battery_compartment_is_holder_material_not_potting(opt, mat):
    """The compartment is not potted: holder material round the cells up to
    their tops, air in the headroom; the cells still win over the block."""
    by = {s.name: s for s in cases.option_model(opt).sectors}
    blk, head = by["holder_block"], by["holder_headroom"]
    assert blk.material == mat and head.material == "air"
    assert min(blk.priority, head.priority) > by["potting"].priority
    assert by["cell1"].priority > blk.priority
    assert blk.z1 == pytest.approx(g.CELL_Z_MM[1]) == head.z0
    assert head.z1 == pytest.approx(g.BOARD_MID_Z_MM["activation_interface"] - g.BOARD_T_MM / 2)


def test_stepped_ring_closes_a_peek_cavity():
    lo = "activation_interface"
    by = {s.name: s for s in cases.option_model("C2", ring_setback_mm=4.0).sectors}
    ins, wall = by[f"ring_insert_{lo}"], by[f"ring_step_{lo}"]
    assert ins.material == "peek" and wall.material == "pec"
    assert ins.r_in == pytest.approx(g.RING_R_OUT_MM - 4.0) == wall.r_out
    assert ins.r_out == pytest.approx(g.SLEEVE_R_IN_MM)
    assert (ins.a0, ins.a1) == (wall.a0, wall.a1) == cases.ANTENNA_SECTOR_FREE
    assert min(ins.priority, wall.priority) > by[f"ring_{lo}"].priority
    # radial end walls tie the stepped wall back to the full ring at both edges
    ea, eb = by[f"ring_end_a_{lo}"], by[f"ring_end_b_{lo}"]
    for e in (ea, eb):
        assert e.material == "pec"
        assert (e.r_in, e.r_out) == (pytest.approx(wall.r_in), pytest.approx(g.RING_R_IN_MM))
    assert ea.a1 == pytest.approx(ins.a0) and eb.a0 == pytest.approx(ins.a1)
    assert f"ring_cut_{lo}" not in by            # no potting in front of the wall
    # default stays the plain cut
    assert f"ring_cut_{lo}" in {s.name for s in cases.option_model("C2").sectors}


def test_model_json_round_trip():
    d = g.model_to_dict(cases.option_model("C"), excite="P_S2")
    assert d["excite"] == "P_S2"
    assert {"lds_lcp", "potting_black", "fr4"} <= set(d["materials"])
    assert all("priority" in s for s in d["sectors"])


def test_feed_castellations_cover_the_drawn_slots():
    """C2 (S1 + S3) won the slot study; S4 = the 4.6-5.0 GHz transverter slot
    retuned 2026-11-18 (sim C2_P_S4_p17_sc90_f20_w2); feed angles = the CPW
    strip centres the sim used."""
    from smash.parts.antenna_slots import SLOTS
    assert set(ANTENNA_FEED_ANGLES_DEG) == {"ANT_HF_S1", "ANT_HF_S4"}
    m = cases.option_model("C2", feed="castellation", skin="local", S1_scale=0.95,
                           S1_angle=110, S3_dir=-1, S3_gap="wakeup_board", S3_feed=5,
                           S3_scale=0.905, S4_f=4.4, S4_gap="fin_ble_board", S4_angle=143,
                           S4_scale=0.9, S4_width=2.0, S4_feed=2.0,
                           skin_clip_deg=(109.0, 255.0))
    sim = {s.name: s for s in m.slots}
    strips = {s.name: s for s in m.sectors if s.name.endswith("_cpw_strip")}
    for sl in SLOTS:
        ss = sim[sl.name]
        assert ss.length == pytest.approx(sl.direction * sl.length_mm, abs=0.01)
        assert ss.angle_deg == pytest.approx(sl.start_deg) and ss.width == sl.width_mm
        st = strips[f"{sl.name}_cpw_strip"]
        assert 0.5 * (st.a0 + st.a1) == pytest.approx(ANTENNA_FEED_ANGLES_DEG[sl.net], abs=0.1)


# ── 2026-11-17: per-slot overrides, castellation (CPW) feed, real pottings ──

def test_slot_overrides_change_length_feed_and_direction():
    base = {s.name: s for s in cases.option_model("C2").slots}
    m = cases.option_model("C2", S3_scale=0.89, S3_feed=3.0, S3_dir=-1)
    s1, s3 = {s.name: s for s in m.slots}["S1"], {s.name: s for s in m.slots}["S3"]
    assert s1 == base["S1"]                                   # untouched
    assert abs(s3.length) == pytest.approx(0.89 * abs(base["S3"].length))
    assert s3.length < 0 and s3.angle_deg == pytest.approx(253.0)
    assert s3.feed_offset == 3.0
    a0, a1 = g.ANTENNA_SECTOR_DEG
    for sec in s3.sectors(0, g.SLEEVE_R_OUT_MM, "x", 0):
        assert a0 <= sec.a0 and sec.a1 <= a1


def test_slot_overrides_rejected_outside_c():
    with pytest.raises(ValueError):
        cases.option_model("A", S1_scale=0.9)


def test_castellation_feed_runs_a_cpw_from_the_radio_board():
    m = cases.option_model("C2", feed="castellation", S3_dir=-1, skin="local")
    zb = g.BOARD_MID_Z_MM["wakeup_board"]
    ports = {p.name: p for p in m.ports}
    slots = {s.name: s for s in m.slots}
    for name in ("S1", "S3"):
        p = ports[f"P_{name}"]
        assert p.z == pytest.approx(zb) and p.axis == "tangential"
        strip = next(s for s in m.sectors if s.name == f"{name}_cpw_strip")
        sl = slots[name]
        # strip spans board level → across the slot onto its far side
        assert strip.z0 <= zb <= strip.z1
        assert strip.z0 < sl.z_start - sl.width / 2 or strip.z1 > sl.z_start + sl.width / 2
        assert strip.z0 < sl.z_start < strip.z1
        assert strip.priority > 12                            # wins over the slot cut
    assert abs(ports["P_S1"].angle_deg - ports["P_S3"].angle_deg) > 20   # distinct castellations


def test_ideal_feed_is_still_the_default():
    m = cases.option_model("C2")
    assert all(p.axis == "z" for p in m.ports)
    assert not any("cpw" in s.name for s in m.sectors)


@pytest.mark.parametrize("pot", ["potting_23lv", "potting_cat11"])
def test_real_pottings_reach_the_model_json(pot):
    d = g.model_to_dict(cases.option_model("C2", potting=pot))
    assert pot in d["materials"] and d["materials"][pot]["eps_r"] > 3.5


def test_castellation_feed_ties_cpw_ground_to_the_board():
    """GND castellations either side of the feed bond the CPW ground to the
    radio board's ground disc; the centre strip stays off the board."""
    m = cases.option_model("C2", feed="castellation", S3_dir=-1, skin="local")
    zb = g.BOARD_MID_Z_MM["wakeup_board"]
    by = {s.name: s for s in m.sectors}
    for name in ("S1", "S3"):
        strip = by[f"{name}_cpw_strip"]
        for side in "ab":
            tie = by[f"{name}_cpw_gnd_tie_{side}"]
            assert tie.material == "pec" and tie.r_in < g.BOARD_R_MM < tie.r_out
            assert tie.z0 <= zb <= tie.z1
            assert tie.a1 <= strip.a0 or tie.a0 >= strip.a1        # never shorts the strip
        assert strip.r_in > g.BOARD_R_MM


def test_slot_gap_override_moves_s3_next_to_the_radio_board():
    m = cases.option_model("C2", S3_gap="wakeup_board", S3_dir=-1, feed="castellation",
                           skin="local")
    s3 = {s.name: s for s in m.slots}["S3"]
    lo, hi = g.BOARD_MID_Z_MM["wakeup_board"], g.BOARD_MID_Z_MM["power_board"]
    assert s3.z_start == pytest.approx((lo + hi) / 2)
    # S1's feed ground stays clear of the S3 slot cut
    by = {s.name: s for s in m.sectors}
    assert by["S1_cpw_gnd"].z1 < s3.z_start - s3.width / 2


def test_extra_high_band_slot_s4():
    """S4 (transverter high band) appears only when S4_f is given; it sits in
    its own gap, can be widened, and gets its own castellation feed."""
    base = cases.option_model("C2")
    assert "S4" not in {s.name for s in base.slots}
    m = cases.option_model("C2", feed="castellation", skin="local", S3_dir=-1,
                           S4_f=4.75, S4_gap="fin_ble_board", S4_angle=140,
                           S4_width=3.0, S4_feed=3)
    s4 = {s.name: s for s in m.slots}["S4"]
    assert s4.width == 3.0 and s4.angle_deg == 140
    assert s4.total_length == pytest.approx(g.half_wave_slot_mm(4.75, cases.EPS_EFF))
    lo, hi = g.BOARD_MID_Z_MM["fin_ble_board"], g.BOARD_MID_Z_MM["wakeup_board"]
    assert s4.z_start == pytest.approx((lo + hi) / 2)
    assert "P_S4" in {p.name for p in m.ports}
    with pytest.raises(ValueError):
        cases.option_model("C2", S4_f=5.8)                    # no gap given


def test_sweep_range_and_extra_far_field_points_reach_the_model():
    d = g.model_to_dict(cases.option_model("C2"), f_start_ghz=3.0, f_stop_ghz=7.0,
                        ff_extra_ghz=(3.5, 5.8))
    assert (d["f_start_ghz"], d["f_stop_ghz"]) == (3.0, 7.0)
    assert d["ff_extra_ghz"] == [3.5, 5.8]


def test_ring_setback_can_be_limited_to_one_gap():
    """The stepped ring helps S4 (4-7 GHz) but kills S1 — so it is per gap."""
    m = cases.option_model("C2", ring_setback_mm=4.0, ring_setback_gaps=("fin_ble_board",))
    names = {s.name for s in m.sectors}
    assert "ring_step_fin_ble_board" in names and "ring_cut_fin_ble_board" not in names
    assert "ring_cut_activation_interface" in names            # S1's gap untouched
    assert "ring_step_activation_interface" not in names


def test_keepout_can_skip_a_slot():
    kw = dict(S4_f=4.4, S4_gap="fin_ble_board", S4_angle=140, S4_width=3.0)
    default = {s.name for s in cases.option_model("C2", **kw).sectors}
    assert any(n.startswith("keepout_S4") for n in default)   # 3 mm S4 fills its gap
    names = {s.name for s in cases.option_model("C2", keepout_slots=("S1", "S3"), **kw).sectors}
    assert not any(n.startswith("keepout_S4") for n in names)



def test_drawn_copper_stays_clear_of_the_seam_and_signal_sector():
    from smash.parts import antenna_slots as AS
    from smash.parts.castellations import SEAM_ANGLES_DEG, SEAM_HALF_WIDTH_DEG
    mids = {b: z for b, z in g.BOARD_MID_Z_MM.items()}
    geo = AS.unrolled_geometry(mids, SEAM_ANGLES_DEG[0], (0.0, 60.0))
    x_lo = AS.SLEEVE_R_OUT_MM * math.radians(SEAM_HALF_WIDTH_DEG)
    x_hi = AS.SLEEVE_R_OUT_MM * math.radians(255.0 - SEAM_ANGLES_DEG[0])
    for x0, _z0, x1, _z1 in geo["copper"] + [r for _n, r in geo["strips"]]:
        assert x_lo - 1e-6 <= x0 and x1 <= x_hi + 1e-6
    for sl in AS.SLOTS:                       # the slot itself also clears the seam
        assert sl.span_deg[0] >= SEAM_ANGLES_DEG[0] + SEAM_HALF_WIDTH_DEG
        assert sl.span_deg[1] <= 255.0


def test_slot_can_be_switched_off():
    m = cases.option_model("C2", S3_off=1)
    assert [s.name for s in m.slots] == ["S1"] and [p.name for p in m.ports] == ["P_S1"]
