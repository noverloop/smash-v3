"""Per-config one-piece PEEK-LDS cup (sleeve + nose) that replaced the
nose_cap PCB (2026-11-18): radome numbers, nose features, active lanes, the
shared compute contract, the lane policies and the nose-cup fallback."""
from __future__ import annotations

import importlib
import math
import pathlib
import sys

import pytest

from smash.export import nose_radome as NR
from smash.export import cup_noses as CN


@pytest.fixture(scope="module")
def built():
    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        gen = importlib.import_module("generate_stackup")
    finally:
        sys.path.pop(0)
    from smash.layout.boards.smash_evb_v1 import build_panel
    from smash.layout.placer import place_design
    from smash.parts.castellations import place_castellations

    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in (gen.build_qpd_module, gen.build_radar_nose_io,
               gen.build_camera_module, gen.build_activation_interface,
               gen.build_radar_module_awr1843aop, gen.build_fins_module,
               gen.build_companion_compute, gen.build_power_board,
               gen.build_wakeup_board):
        fn(d)
    panel, boards = build_panel()
    gen.build_spacers(d, boards)
    place_design(d, panel, boards)
    contract, _counts = place_castellations(
        d, panel, boards,
        connect=lambda net, pin: gen._net(d, net).connect(pin),
        cone_exits=gen._CONE_EXITS)
    return gen, d, panel, boards, contract


# ── radome numbers (no geometry) ─────────────────────────────────────

def test_half_wave_window_thickness():
    lam = NR.wavelength_mm(77.0)
    assert lam == pytest.approx(3.8934, abs=1e-3)
    t1 = NR.window_thickness_mm(1, 3.6, 77.0)
    assert t1 == pytest.approx(lam / (2 * math.sqrt(3.6)))
    assert t1 == pytest.approx(1.026, abs=2e-3)
    assert NR.window_thickness_mm(2, 3.6, 77.0) == pytest.approx(2 * t1)
    assert NR.radome_gap_mm(77.0) == pytest.approx(lam / 2)


def test_nose_cap_pcb_is_gone(built):
    gen, d, panel, boards, _c = built
    assert "nose_cap" not in boards
    assert "nose_cap" not in panel.snake_chain
    assert panel.snake_chain[-1] == "radar_module"
    assert not any(getattr(c, "board_tag", None) == "nose_cap" for c in d.chips)
    assert "nose_cap" not in gen._BOARD_BUILDERS
    assert all("nose_cap" not in s for s in gen.CONFIGS.values())


# ── nose features ─────────────────────────────────────────────────────

def _parts_fit(n, boards, chain):
    parts = CN._top_parts(boards[n.payload], CN._fold_M(chain, n.payload))
    z1 = n.z_payload[1]
    return [p.ref for p in parts if p.ref not in ("U_AWR",)
            and n.profile.inner_z_at(CN._part_r(p)) < z1 + p.height + CN.PART_CLEARANCE_MM - 1e-6]


def test_radar_nose_is_flat_radome(built):
    _g, _d, panel, boards, _c = built
    chain = list(panel.snake_chain)
    n = CN.nose_spec("core_radar", boards, chain)
    z1 = n.z_payload[1]
    assert n.end_t == pytest.approx(NR.window_thickness_mm(), abs=1e-3)
    aop_h = next(p.item for p in boards["radar_module"].chip_placements
                 if p.item.ref == "U_AWR").height_mm
    k = (n.z_end_in - z1 - aop_h) / (NR.wavelength_mm() / 2)
    assert k == pytest.approx(round(k), abs=1e-3) and 1 <= round(k) <= CN.RADOME_MAX_ORDER
    assert n.lens["radome_order"] == round(k)
    assert n.profile.meplat_r == pytest.approx(CN.NOSE_PROFILE["radar_module"]["meplat_r"])
    assert n.hoods == [] and _parts_fit(n, boards, chain) == []   # everything under the nose
    assert len(n.radial_windows) == 1                               # USB-C mouth
    assert {q["ref"] for q in n.pipes} == {"D_IR_TX", "D_IR_WAKE"}   # IR light pipes
    assert n.dam is not None and len(n.stops) == 3


def test_profile_is_smooth_and_tangent():
    prof = CN.NoseProfile(r_out=17.9, wall=0.8, meplat_r=10.0, z_s=50.0, z_top=55.0)
    pts = prof.outer_pts(200)
    assert pts[0] == pytest.approx((17.9, 50.0)) and pts[-1] == pytest.approx((10.0, 55.0))
    (r0, z0), (r1, z1) = pts[0], pts[1]
    assert abs(r1 - r0) < 0.05 * abs(z1 - z0)        # vertical at the cylinder (tangent)
    (ra, za), (rb, zb) = pts[-2], pts[-1]
    assert abs(zb - za) < 0.05 * abs(rb - ra)        # horizontal at the flat face (tangent)
    assert prof.inner_z_at(0.0) == pytest.approx(54.2)
    assert prof.inner_z_at(prof.r_in) == pytest.approx(50.0)
    zs = [prof.inner_z_at(r) for r in (10.0, 12.0, 14.0, 16.0, 17.0)]
    assert zs == sorted(zs, reverse=True)


def test_optical_noses_carry_a_lens_per_band(built):
    _g, _d, panel, boards, _c = built
    from smash.export import nose_optics as NO
    chain = list(panel.snake_chain)
    for cfg in ("core_qpd", "core_camera"):
        payload = CN.PAYLOADS[cfg]
        o = NO.OPTICS[payload]
        heights = {}
        for band in CN.optical_bands(payload):
            n = CN.nose_spec(cfg, boards, chain, band=band)
            L = n.lens
            sensor = next(p for p in CN._top_parts(boards[payload], CN._fold_M(chain, payload))
                          if p.ref == o["sensor"])
            z_sensor = n.z_payload[1] + sensor.height
            lam = o["bands"][band]
            assert L["z_flat"] - z_sensor == pytest.approx(
                o["lens"].focal_mm(lam) + o["lens"].centre_thickness_mm + o["defocus_mm"])
            assert n.profile.z_top == pytest.approx(L["z_flat"], abs=1e-3)   # flush
            assert n.profile.meplat_r >= L["a"] + NO.LENS_COLLAR_WALL_MM
            assert n.tube is not None and n.holes == [] and n.hoods == []
            assert len(n.stops) == 3
            heights[band] = L["z_flat"]
        assert len(set(round(h, 4) for h in heights.values())) == len(heights)  # λ moves it


def test_plain_core_nose(built):
    _g, _d, panel, boards, _c = built
    core = CN.nose_spec("core", boards, list(panel.snake_chain))
    assert core.payload is None and core.holes == [] and core.stops == [] and core.hoods == []
    assert core.profile.z_top > core.z_payload[1]
    assert core.profile.L >= CN.SHOULDER_MIN_MM


def test_lens_optics():
    from smash.export import nose_optics as NO
    assert NO.refractive_index("sapphire", 587.6) == pytest.approx(1.768, abs=1e-3)
    assert NO.refractive_index("fused_silica", 587.6) == pytest.approx(1.4585, abs=1e-3)
    L = NO.Lens(material="sapphire", diameter_mm=10.0, radius_mm=6.0, edge_mm=0.8)
    n = NO.refractive_index("sapphire", 1064.0)
    assert L.focal_mm(1064.0) == pytest.approx(6.0 / (n - 1.0))
    assert L.sag_mm == pytest.approx(6.0 - math.sqrt(36.0 - 25.0))
    assert L.height_above_sensor_mm(1550.0) > L.height_above_sensor_mm(1064.0)  # dispersion
    with pytest.raises(ValueError):
        NO.refractive_index("sapphire", 10600.0)


def test_stops_clear_of_payload_parts(built):
    _g, _d, panel, boards, _c = built
    chain = list(panel.snake_chain)
    for cfg in ("core_radar", "core_qpd", "core_camera"):
        n = CN.nose_spec(cfg, boards, chain)
        parts = CN._top_parts(boards[n.payload], CN._fold_M(chain, n.payload))
        for ang in n.stops:
            x = CN.STOP_R_MM * math.cos(math.radians(ang))
            y = CN.STOP_R_MM * math.sin(math.radians(ang))
            for p in parts:
                assert not (abs(x - p.x) < p.w / 2 + CN.STOP_D_MM / 2
                            and abs(y - p.y) < p.h / 2 + CN.STOP_D_MM / 2), (cfg, ang, p.ref)


# ── shared compute contract + per-cup lasering ────────────────────────

def test_compute_carries_all_three_payloads(built):
    _g, _d, _p, _b, contract = built
    on_compute = {k: v for k, v in contract["lanes"].items()
                  if "companion_compute" in v["boards"]}
    assert any("radar_module" in v["boards"] for v in on_compute.values())
    assert any(k.startswith("CONE:qpd_module:") for k in on_compute)
    assert any(k.startswith("CONE:camera_module:") for k in on_compute)
    # payload lanes never collide on compute
    seen = {}
    for k, v in on_compute.items():
        if v.get("kind") == "gnd_plane":
            continue
        for a in v["angles"]:
            assert a not in seen, (k, seen.get(a), a)
            seen[a] = k


def test_each_cup_lasers_only_its_payload(built):
    _g, _d, panel, boards, contract = built
    chain = list(panel.snake_chain)
    act = {}
    for cfg, payload in CN.PAYLOADS.items():
        cc = CN.cup_chain(boards, chain, payload)
        present = {n for n in cc if n in boards and not boards[n].is_spacer}
        act[cfg] = CN.active_lanes(contract, present)
    assert not any("radar_module" in on for on in act["core"].values())
    assert not any(k.startswith("CONE:") for k in act["core"])
    assert any("radar_module" in on for on in act["core_radar"].values())
    assert not any(k.startswith("CONE:") for k in act["core_radar"])
    assert any(k.startswith("CONE:qpd_module:") for k in act["core_qpd"])
    assert not any(k.startswith("CONE:camera_module:") for k in act["core_qpd"])
    assert any(k.startswith("CONE:camera_module:") for k in act["core_camera"])
    # the core lanes are lasered in every cup
    core_only = set(act["core"])
    for cfg in ("core_radar", "core_qpd", "core_camera"):
        assert core_only <= set(act[cfg])


def test_dedicated_lane_policy(built):
    _g, d, panel, boards, _c = built
    from smash.parts.castellations import castellation_contract, lane_budget
    gen = built[0]
    c = castellation_contract(d, panel, boards, cone_exits=gen._CONE_EXITS,
                              lane_policy="dedicated")
    owner = {}
    for k, v in c["lanes"].items():
        if v.get("kind") not in ("signal", "power"):
            continue
        for a in v["angles"]:
            assert a not in owner, f"{k} and {owner[a]} share {a}° under 'dedicated'"
            owner[a] = k
    b = lane_budget(d, panel, boards, cone_exits=gen._CONE_EXITS)
    assert set(b) == {"reuse", "dedicated"}
    assert b["dedicated"]["overflow"] == c["overflow"]
    assert b["reuse"]["n_used"] <= b["reuse"]["n_angles"]
    with pytest.raises(ValueError):
        castellation_contract(d, panel, boards, lane_policy="bogus")


# ── solids (cadquery) ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cups(built):
    pytest.importorskip("cadquery")
    from smash.export.sleeve_step import build_cup
    _g, _d, panel, boards, contract = built
    return {cfg: build_cup(boards, list(panel.snake_chain), contract, cfg)
            for cfg in ("core_radar", "core_qpd")}  # qpd = first band


def _inside(body, x, y, z) -> bool:
    import cadquery as cq
    return body.val().isInside(cq.Vector(x, y, z))


def test_cup_is_one_watertight_solid(cups):
    for cfg, cup in cups.items():
        b = cup["body"]
        assert b.solids().size() == 1, cfg
        assert b.val().isValid(), cfg
        assert cup["n_vias"] > 0


def test_radar_cup_window_and_openings(cups):
    cup = cups["core_radar"]
    n = cup["nose"]
    zm = n.z_end_in + n.end_t / 2
    aop = n.dam
    cx, cy = (aop[0] + aop[2]) / 2, (aop[1] + aop[3]) / 2
    assert _inside(cup["body"], cx, cy, zm)                 # solid radome over the AoP
    assert not _inside(cup["body"], cx, cy, n.z_end_in - 0.5)  # air pocket below it
    for _k, x, y, _d in n.holes:
        assert not _inside(cup["body"], x, y, zm)           # IR holes open


def test_optical_cup_lens_bore_open(cups):
    cup = cups["core_qpd"]
    L = cup["nose"].lens
    assert not _inside(cup["body"], L["x"], L["y"], L["z_flat"] - 0.2)   # bore for the lens
    assert cup["lens"] is not None and cup["lens"].solids().size() == 1
    assert _inside(cup["lens"], L["x"], L["y"], L["z_flat"] - L["tc"] + 0.05)
    # shoulder material exists between the flat face and the cylinder
    prof = cup["nose"].profile
    r_mid = (prof.meplat_r + prof.r_out) / 2
    z_mid = prof.inner_z_at(r_mid) + 0.05
    assert _inside(cup["body"], r_mid, 0.0, z_mid) or _inside(cup["body"], 0.0, r_mid, z_mid)


def test_nose_cup_fallback_split(built, monkeypatch):
    pytest.importorskip("cadquery")
    from smash.export.sleeve_step import build_cup
    _g, _d, panel, boards, contract = built
    monkeypatch.setattr(CN, "SLEEVE_SPLIT", "nose_cup")
    cup = build_cup(boards, list(panel.snake_chain), contract, "core_radar")
    assert set(cup["parts"]) == {"core_sleeve", "nose_cup"}
    zj = cup["z_joint"]
    z0, _z1 = cup["nose"].z_payload
    assert zj < z0                                  # joint in the compute↔payload gap
    from smash.export.sleeve_step import SLEEVE_WALL_MM
    r = cup["r_out"] - SLEEVE_WALL_MM / 2
    a = math.radians(CN.JOINT_SCREW_ANGLES_DEG[0])
    assert not _inside(cup["parts"]["nose_cup"], r * math.cos(a), r * math.sin(a), zj + 0.8)


def test_write_cups_per_config(built, tmp_path):
    pytest.importorskip("cadquery")
    from smash.export.sleeve_step import write_sleeve_and_mould
    _g, _d, panel, boards, contract = built
    res = write_sleeve_and_mould(boards, list(panel.snake_chain), contract, tmp_path,
                                 configs=["core"])
    cd = tmp_path / "sleeve" / "core"
    assert (cd / "cup.step").exists() and (cd / "cup_cam.md").exists()
    fd = tmp_path / "potting_mould" / "core"
    assert (fd / "fixture_cradle_nose_down.step").exists()
    assert (fd / "fixture_cap_aft_fill_vent.step").exists()
    assert res["cups"]["core"]["n_vias"] > 0
    assert "INSIDE the cup" in (cd / "cup_cam.md").read_text()
