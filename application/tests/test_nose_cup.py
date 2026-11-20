"""Nose modules on the standard crown (2026-11-19): ONE-PIECE PEEK-LDS sleeve
(Ø35.8) over the tower and its Ø34 Al anchor ring, its top end = the conical
BLOCK crown hanging on the ring (outer lanes down to compute castellations) →
nose cone with block lands + small Ø27 payload board, held by 3 flush plates
+ radial screws through the sleeve into the ring.
Radome / lens / profile numbers, the crown contract, active lanes, solids."""
from __future__ import annotations

import importlib
import math
import pathlib
import sys

import pytest

from smash.export import nose_radome as NR
from smash.export import cup_noses as CN
from smash.export import nose_interface as NI


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
    for fn in (gen.build_qpd_module, gen.build_radar_nose_io, gen.build_usb_nose,
               gen.build_camera_module, gen.build_activation_interface,
               gen.build_radar_module_awr1843aop, gen.build_fins_module,
               gen.build_companion_compute, gen.build_power_board,
               gen.build_wakeup_board):
        fn(d)
    panel, boards = build_panel()
    gen.build_spacers(d, boards)
    gen._mark_preplace_keepouts(d, boards)
    gen._mark_ring_band_keepouts(panel, boards)
    place_design(d, panel, boards)
    from smash.layout.placer.spacer_sizing import size_backbone_spacers
    size_backbone_spacers(panel, boards)          # enforces the nose anchor gap
    contract, _counts = place_castellations(
        d, panel, boards,
        connect=lambda net, pin: gen._net(d, net).connect(pin),
        cone_exits=gen._CONE_EXITS)
    return gen, d, panel, boards, contract


# ── radome / lens / profile numbers (no geometry) ─────────────────────

def test_half_wave_window_thickness():
    lam = NR.wavelength_mm(77.0)
    assert lam == pytest.approx(3.8934, abs=1e-3)
    t1 = NR.window_thickness_mm(1, 3.6, 77.0)
    assert t1 == pytest.approx(lam / (2 * math.sqrt(3.6)))
    assert t1 == pytest.approx(1.026, abs=2e-3)
    assert NR.window_thickness_mm(2, 3.6, 77.0) == pytest.approx(2 * t1)
    assert NR.radome_gap_mm(77.0) == pytest.approx(lam / 2)


def test_profile_is_smooth_and_tangent():
    prof = CN.NoseProfile(r_out=17.9, wall=0.8, meplat_r=10.0, z_s=50.0, z_top=55.0)
    pts = prof.outer_pts(200)
    assert pts[0] == pytest.approx((17.9, 50.0)) and pts[-1] == pytest.approx((10.0, 55.0))
    (r0, z0), (r1, z1) = pts[0], pts[1]
    assert abs(r1 - r0) < 0.05 * abs(z1 - z0)
    (ra, za), (rb, zb) = pts[-2], pts[-1]
    assert abs(zb - za) < 0.05 * abs(rb - ra)
    assert prof.inner_z_at(0.0) == pytest.approx(54.2)
    assert prof.inner_z_at(prof.r_in) == pytest.approx(50.0)


def test_lens_optics():
    from smash.export import nose_optics as NO
    assert NO.refractive_index("sapphire", 587.6) == pytest.approx(1.768, abs=1e-3)
    assert NO.refractive_index("fused_silica", 587.6) == pytest.approx(1.4585, abs=1e-3)
    L = NO.Lens(material="sapphire", diameter_mm=10.0, radius_mm=6.0, edge_mm=0.8)
    n = NO.refractive_index("sapphire", 1064.0)
    assert L.focal_mm(1064.0) == pytest.approx(6.0 / (n - 1.0))
    assert L.height_above_sensor_mm(1550.0) > L.height_above_sensor_mm(1064.0)
    with pytest.raises(ValueError):
        NO.refractive_index("sapphire", 10600.0)


# ── crown spec ────────────────────────────────────────────────────────

def test_crown_spec_keys_and_retention():
    assert len(NI.contact_teeth()) == NI.N_TEETH - len(NI.SCREW_TEETH) - len(NI.BLOCKED_TEETH)
    assert NI.SCREW_N == 2 == len(NI.SCREW_TEETH)
    gaps = sorted(NI.SCREW_ANGLES_DEG)
    spacing = [round((b - a) % 360, 3) for a, b in zip(gaps, gaps[1:] + gaps[:1])]
    assert len(set(spacing)) == 2                       # uneven → fits one way round
    rev = 0.15 * NI.NOSE_MASS_G * 1e-3 * 46.7e3 * 9.81
    assert NI.SCREW_N * NI.SCREW_SHEAR_KN * 1e3 / rev >= 2.0
    # bevel: 4 mm annulus, cone rises inward, gap sized for ring + crown
    assert NI.CROWN_R_OUT_MM - NI.CROWN_R_IN_MM == pytest.approx(4.0)
    # (2026-11-19) cone highest at the OUTER edge, descending inward: the drop
    # sits beside the Al ring (nook), so the gap only adds base − rise + teeth
    assert NI.cone_z(NI.CROWN_R_IN_MM, 0.0) < NI.cone_z(NI.CROWN_R_OUT_MM, 0.0) == 0.0
    assert NI.CROWN_STACK_MM == pytest.approx(
        NI.CROWN_BASE_MM + NI.TOOTH_H_MM + NI.TOOTH_TOP_GAP_MM + NI.LAND_RING_TOP_MM)
    assert NI.ANCHOR_GAP_MIN_MM == pytest.approx(NI.ANCHOR_RING_MIN_MM + NI.CROWN_STACK_MM)
    # the nook absorbs the cone drop beside the band: the stack carries only
    # the drop across the band (17.9 → 16.0), not the full 4 mm bevel rise
    assert NI.CROWN_BASE_MM < NI.BEVEL_RISE_MM
    assert NI.cone_z(16.0, NI.CROWN_BASE_MM) == pytest.approx(NI.CROWN_FLOOR_MIN_MM, abs=1e-3)
    # (2026-11-19, user) payload is Ø34, seated ABOVE the land ring, inside the skin
    assert NI.PAYLOAD_R_MM == pytest.approx(17.0) and NI.PAYLOAD_R_MM < NI.CROWN_R_OUT_MM


def test_crown_sequence_keeps_pairs_together():
    nets = ["BAT_PROT", "USB_VBUS", "USB_D_P", "USB_D_N", "CAM_CSI_CLK_P", "CAM_CSI_CLK_N",
            "IR_TX", "IR_WAKE", "RADAR_EN"]
    seq = NI.build_sequence(nets, NI.group_order(nets))
    assert len(seq) == len(NI.contact_teeth())
    names = [n for n, _r in seq]
    for p, n in (("USB_D_P", "USB_D_N"), ("CAM_CSI_CLK_P", "CAM_CSI_CLK_N")):
        i = names.index(p)
        assert names[i + 1] == n                       # adjacent
        assert names[i - 1] == "GND" and names[i + 2] == "GND"   # guarded
    assert names.count("USB_VBUS") == NI.MULTIPLICITY["USB_VBUS"]
    # unit placement on a capped tooth set: a pair never straddles a screw /
    # a missing tooth (spares go in first)
    cs = NI.allocate(nets, NI.group_order(nets))
    by = {c.tooth: c for c in cs}
    for c in cs:
        if c.role == "pair_p":
            n_ = by.get(c.tooth + 1)
            assert n_ is not None and n_.role == "pair_n"
            assert NI.screw_sector(c.angle_deg) == NI.screw_sector(n_.angle_deg)


# ── crown contract in the built design ────────────────────────────────

def test_nose_payloads_reach_compute_only_through_the_crown(built):
    gen, d, panel, boards, contract = built
    assert "usb_nose" in boards
    assert "J_USB_C" in {c.ref for c in d.chips if c.board_tag == "usb_nose"}
    crown = contract["crown"]
    assert not contract.get("crown_overflow")
    assert 0 < len(crown) <= len(NI.contact_teeth())       # capped by free compute slots
    nets = {c["net"] for c in crown}
    for n in ("AWR_SPI_CLK", "QPD_TIA_A", "CAM_CSI_D0_P", "USB_D_P", "USB_VBUS", "IR_WAKE"):
        assert n in nets
    for k, v in contract["lanes"].items():          # no ordinary lane reaches a payload
        if v.get("kind") not in ("crown_payload",):
            assert not set(v["boards"]) & set(NI.PAYLOAD_BOARDS), k
    # (2026-11-19) compute: one EDGE castellation per crown contact (no top pads)
    assert not any(c.ref.startswith("J_CROWN_") for c in d.chips)
    cast = next(c for c in d.chips if c.ref == "J_CAST_companion_compute")
    names = {pin.name.rsplit("@", 1)[0] for pin in cast.pins}
    assert {k for k, v in contract["lanes"].items() if v["kind"] == "crown_top"} <= names
    # payload boards: Ø27, castellations at the tooth angles on their own rim
    for pb in NI.PAYLOAD_BOARDS:
        if pb in boards:
            assert boards[pb].geometry.diameter_mm == pytest.approx(2 * NI.PAYLOAD_R_MM)


def test_each_nose_lasers_its_crown_lanes(built):
    _g, _d, panel, boards, contract = built
    chain = list(panel.snake_chain)
    n_crown = len(contract["crown"])
    for cfg, payload in CN.PAYLOADS.items():
        cc = CN.cup_chain(boards, chain, payload)
        present = {n for n in cc if n in boards and not boards[n].is_spacer}
        act = CN.active_lanes(contract, present, payload)
        need = sum(1 for k, v in contract["lanes"].items() if k.startswith("CROWN:")
                   and payload in v.get("payloads", [payload]))
        assert 0 < need < n_crown                     # only this payload's nets get vias
        assert sum(1 for k in act if k.startswith("CROWN:")) == need
        # nose side: one contact per TOOTH (sleeve side: merged power runs and
        # the GND ring need fewer lanes than teeth)
        need_p = sum(1 for k, v in contract["lanes"].items() if k.startswith("CROWNP:")
                     and payload in v.get("payloads", [payload]))
        assert need_p >= need
        assert sum(1 for k in act if k.startswith("CROWNP:")) == need_p
        assert all(act[k] == [payload] for k in act if k.startswith("CROWNP:"))


# ── nose features ─────────────────────────────────────────────────────

def _parts_fit(n, boards, chain):
    parts = CN._top_parts(boards[n.payload], CN._fold_M(chain, n.payload))
    z1 = n.z_payload[1]
    return [p.ref for p in parts if p.ref not in ("U_AWR",)
            and n.profile.inner_z_at(CN._part_r(p)) < z1 + p.height + CN.PART_CLEARANCE_MM - 1e-6]


def test_radar_nose_is_open_without_radome(built):
    """(2026-11-19, user) OPEN nose, no radome in the 3D — the finishing
    capsule (OD 40) carries it; the AoP dam and the board stops remain."""
    _g, _d, panel, boards, _c = built
    chain = list(panel.snake_chain)
    n = CN.nose_spec("core_radar", boards, chain)
    assert n.profile.open
    assert n.lens == {"radome": None}
    assert n.radial_windows == [] and n.hoods == [] and n.pipes == []
    assert n.dam is not None
    # (2026-11-20) the payload is PRESSURE-FIXED by the nose cap and located
    # by 3 pins in its nose_stop holes (no stop-boss screws any more)
    stops = [h for h in boards["radar_module"].geometry.holes if h.tag == "nose_stop"]
    assert len(stops) == 3

def test_usb_nose_vertical_usb_c(built):
    _g, _d, panel, boards, _c = built
    chain = list(panel.snake_chain)
    n = CN.nose_spec("core", boards, chain)
    assert n.payload == "usb_nose" and n.profile.open
    assert n.radial_windows == [] and n.holes == [] and n.pipes == []   # open front
    # uniform ridge (set by the radar): the vertical USB-C rises through the
    # open end into the finishing container
    assert n.profile.z_top == pytest.approx(
        n.z_payload[1] + CN._ridge_height(boards, chain), abs=1e-3)
    assert n.hoods == []


def test_open_nose_ridge_is_uniform_and_clears_the_radar(built):
    """(2026-11-19, user) every nose cone ends at the SAME height above its
    payload board, set by the radar's tallest part + clearance."""
    _g, _d, panel, boards, _c = built
    chain = list(panel.snake_chain)
    ridges = set()
    for cfg in ("core", "core_radar", "core_qpd", "core_camera"):
        n = CN.nose_spec(cfg, boards, chain)
        assert n.profile.open and n.profile.z_s == n.profile.z_top, cfg   # no shoulder
        ridges.add(round(n.profile.z_top - n.z_payload[1], 3))
    assert len(ridges) == 1
    n = CN.nose_spec("core_radar", boards, chain)
    parts = CN._top_parts(boards["radar_module"], CN._fold_M(chain, "radar_module"))
    tall = max(n.z_payload[1] + p.height for p in parts)
    assert n.profile.z_top >= tall + CN.OPEN_RIDGE_CLEAR_MM - 1e-6

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
            sensor = next(p for p in CN._top_parts(boards[payload], CN._fold_M(chain, payload))
                          if p.ref == o["sensor"])
            lam = o["bands"][band]
            assert n.lens["z_flat"] - (n.z_payload[1] + sensor.height) == pytest.approx(
                o["lens"].focal_mm(lam) + o["lens"].centre_thickness_mm + o["defocus_mm"])
            assert n.tube is not None and n.hoods == [] and n.pipes == []
            assert n.lens["in_capsule"] and n.tube["z1"] == n.profile.z_top
            heights[band] = n.lens["z_flat"]
        assert len(set(round(h, 4) for h in heights.values())) == len(heights)


# ── solids (cadquery) ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cups(built):
    pytest.importorskip("cadquery")
    from smash.export.sleeve_step import build_cup
    _g, _d, panel, boards, contract = built
    return {cfg: build_cup(boards, list(panel.snake_chain), contract, cfg)
            for cfg in ("core_radar", "core", "core_qpd")}


def _inside(body, x, y, z) -> bool:
    import cadquery as cq
    return body.val().isInside(cq.Vector(x, y, z))


def test_parts_are_valid_solids_within_the_envelope(cups):
    for cfg, cup in cups.items():
        P = cup["parts"]
        for name in ("core_sleeve", "nose_cone", "nose_cap"):   # sleeve + crown = ONE piece
            assert P[name].solids().size() == 1, (cfg, name)
            assert P[name].val().isValid(), (cfg, name)
        # (2026-11-20) ONE stainless part: ring + both tabs + feet
        assert P["retaining_ring"].solids().size() == 1
        assert P["retaining_ring"].val().isValid()
        for name, b in P.items():                      # nothing exceeds Ø35.8 …
            bb = b.val().BoundingBox()
            lim = NI.CAP_BUMP_R_MM if name == "retaining_ring" else 17.9   # … but its OD-40 bump
            assert max(abs(bb.xmin), abs(bb.xmax), abs(bb.ymin), abs(bb.ymax)) <= lim + 1e-3, (cfg, name)


def test_sleeve_vias_are_drilled_per_config(cups):
    """(2026-11-19) One moulding + one LDS pattern; only the vias this config's
    payload uses are drilled — a radar sleeve has no camera-lane vias."""
    radar, usb = cups["core_radar"], cups["core"]
    assert radar["n_vias"] != usb["n_vias"]
    for cup in (radar, usb):
        pl = cup["nose"].payload
        for key in cup["active"]:
            uses = cup.get("contract_lanes", {}).get(key, {}).get("payloads")
            assert uses is None or pl in uses


def test_bevel_crown_and_cap_mesh_on_the_cone(cups):
    cup = cups["core_radar"]
    crown, nose = cup["crown"], cup["parts"]["nose_cone"]
    sleeve = cup["parts"]["core_sleeve"]
    zc1, zr1 = cup["z_ring"]
    zb = zr1 + NI.CROWN_BASE_MM
    rm = 0.5 * (16.0 + NI.CROWN_R_OUT_MM)              # over the ring
    zcone = NI.cone_z(rm, zb)
    k = NI.contact_teeth()[3]
    a = math.radians(NI.tooth_angle(k))
    a2 = a + math.radians(360 / NI.N_TEETH / 2)
    # block teeth: groove (contact) at the tooth angle, wall half a pitch over
    assert not _inside(crown, rm * math.cos(a), rm * math.sin(a), zcone + 0.3)    # groove
    assert _inside(nose, rm * math.cos(a), rm * math.sin(a), zcone + 0.3)         # cap land in it
    assert _inside(crown, rm * math.cos(a2), rm * math.sin(a2), zcone + 0.3)      # crown wall
    assert not _inside(nose, rm * math.cos(a2), rm * math.sin(a2), zcone + 0.3)
    assert crown.intersect(nose).solids().size() == 0                            # no interference
    ks = NI.SCREW_TEETH[0]                                                       # key: no groove/land
    s_ = math.radians(NI.tooth_angle(ks))
    assert _inside(crown, rm * math.cos(s_), rm * math.sin(s_), zcone + 0.3)
    # one piece: the crown wall is part of the sleeve, which runs on over the
    # Ø34 Al ring (r 16–17) down to compute — the ring stays inside it
    assert _inside(sleeve, rm * math.cos(a2), rm * math.sin(a2), zcone + 0.3)
    rs = 0.5 * (17.1 + 17.9)
    assert _inside(sleeve, rs * math.cos(a), rs * math.sin(a), 0.5 * (zc1 + zr1))
    # (2026-11-19) the anchor "ring" is a PEEK band of the same moulding
    assert _inside(sleeve, 16.5 * math.cos(a), 16.5 * math.sin(a), 0.5 * (zc1 + zr1))
    assert not _inside(sleeve, 15.5 * math.cos(a), 15.5 * math.sin(a), 0.5 * (zc1 + zr1))
    assert cup["parts"]["thread_inserts"].solids().size() == NI.SCREW_N
    # compute KEY rib on the inner wall at compute height
    ka = math.radians(NI.KEY_ANGLE_DEG)
    assert _inside(sleeve, 16.75 * math.cos(ka), 16.75 * math.sin(ka), zc1 - 0.4)
    assert not _inside(sleeve, 16.75 * math.cos(ka + 0.2), 16.75 * math.sin(ka + 0.2), zc1 - 0.4)
    # the crown funnels DOWN into the ring's bore (the ring sits in the nook)
    zf = NI.cone_z(14.5, zb) - 0.4                       # inside the funnel wall …
    assert zf < zr1                                      # … below the band top
    assert _inside(sleeve, 14.5 * math.cos(a2), 14.5 * math.sin(a2), zf)
    assert _inside(cup["parts"]["screws"], 17.0 * math.cos(math.radians(NI.SCREW_ANGLES_DEG[0])),
                   17.0 * math.sin(math.radians(NI.SCREW_ANGLES_DEG[0])), 0.5 * (zc1 + zr1))
    # the thread insert's bore through the band at each screw
    sa = math.radians(NI.SCREW_ANGLES_DEG[0])
    zs = 0.5 * (zc1 + zr1)
    assert not _inside(sleeve, rs * math.cos(sa), rs * math.sin(sa), zs)
    ri = 0.5 * (NI.THREAD_INSERT_R_MM[0] + 16.0)
    assert _inside(cup["parts"]["thread_inserts"], ri * math.cos(sa) + 1.8 * -math.sin(sa),
                   ri * math.sin(sa) + 1.8 * math.cos(sa), zs)


def test_radar_window(cups):
    """Open nose, no radome part: nothing of the nose cone sits over the AoP."""
    cup = cups["core_radar"]
    n, nose = cup["nose"], cup["parts"]["nose_cone"]
    assert "radome_insert" not in cup["parts"]
    x0, y0, x1, y1 = n.dam
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    assert not _inside(nose, cx, cy, n.profile.z_top - 0.2)   # open shell

def test_optic_insert(cups):
    cup = cups["core_qpd"]
    T = cup["nose"].tube
    ins = cup["parts"]["optic_insert"]
    r = 0.5 * (T["r_in"] + T["r_out"])
    assert _inside(ins, T["x"] + r, T["y"], 0.5 * (T["z0"] + T["z1"]))     # light tube wall
    assert not _inside(ins, T["x"], T["y"], 0.5 * (T["z0"] + T["z1"]))     # open bore


def test_write_noses(built, tmp_path):
    pytest.importorskip("cadquery")
    from smash.export.sleeve_step import write_sleeve_and_mould
    _g, _d, panel, boards, contract = built
    res = write_sleeve_and_mould(boards, list(panel.snake_chain), contract, tmp_path,
                                 configs=["core"])
    assert (tmp_path / "sleeve" / "core_sleeve" / "frame.json").exists()
    assert "Contact map" in (tmp_path / "sleeve" / "core_sleeve" / "crown.md").read_text()
    cd = tmp_path / "sleeve" / "core"
    for f in ("core_sleeve.step", "nose_cone.step", "retaining_ring.step", "screws.step",
              "nose_cam.md", "frame.json"):
        assert (cd / f).exists(), f
    assert res["cups"]["core"]["n_vias"] > 0


def test_unrolled_sleeve_copper_keeps_clearance(built, tmp_path):
    """(2026-11-20) the unroll is one LDS layer: no two different-net lanes may
    touch — the crown fan over the anchor band used to merge its 0.6 mm power
    lanes (long shallow jogs). Repeated power teeth now Y-join into one lane,
    GND teeth ride the crown's GND ring (one link lane per sector)."""
    import itertools
    import re
    from smash.export.sleeve_layout import write_unrolled_sleeve
    _g, _d, panel, boards, contract = built
    assert contract["crown_gnd_ring"]
    assert all(v == "ring" or isinstance(v, float)
               for v in contract["crown_compute_angles"].values())
    out = tmp_path / "unroll.kicad_pcb"
    write_unrolled_sleeve(boards, list(panel.snake_chain), contract, out)
    segs = [tuple(map(float, m[:5])) + (int(m[5]),) for m in re.findall(
        r'\(segment \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\) '
        r'\(width ([\d.]+)\) \(layer "F.Cu"\) \(net (\d+)\)', out.read_text())]
    assert segs
    bad = []
    for a, b in itertools.combinations(segs, 2):
        if a[5] == b[5]:
            continue
        g = NI._seg_dist(a[:2], a[2:4], b[:2], b[2:4]) - (a[4] + b[4]) / 2
        if g < 0.1:
            bad.append((round(g, 3), a, b))
    assert not bad, bad[:5]



def test_nose_cap_carries_the_tabs_through_slots_in_the_nose_cone(cups):
    """(2026-11-20, user) the TABS belong to the nose CAP (λ/2 radome lid); the
    nose cone only has SLOTS they pass through. The cap's press rim bears on
    the payload board, so cone + board are pressure-fixed by the cap."""
    for cfg, cup in cups.items():
        P, n = cup["parts"], cup["nose"]
        cap, cone, sleeve = P["nose_cap"], P["nose_cone"], P["core_sleeve"]
        zc1, zr1 = cup["z_ring"]
        # probe beside the stainless insert (insert is 1 mm narrower than the tab)
        r_tab, side = cup["r_out"] - 0.4, NI.PLATE_W_MM / 2 - 0.3
        for ang in NI.SCREW_ANGLES_DEG:
            a = math.radians(ang)
            x = r_tab * math.cos(a) - side * math.sin(a)
            y = r_tab * math.sin(a) + side * math.cos(a)
            for z in (zr1 + 0.5, n.z_payload[0] + 0.3, n.profile.z_top - 0.3):
                assert (_inside(cap, x, y, z) or _inside(P["retaining_ring"], x, y, z)), \
                    (cfg, ang, z)                                     # the cap's tab …
                assert not _inside(cone, x, y, z), (cfg, ang, z)     # … in the cone's slot
        for other in (cone, sleeve, P["retaining_ring"], P["thread_inserts"]):
            v = cap.intersect(other).val().Volume() if cap.intersect(other).solids().size() else 0.0
            assert v < 1e-3, cfg
        # press rim reaches the payload board top at its edge annulus
        r_rim = cup["r_out"] - 0.8 - 0.05 - 0.4
        z_b = n.z_payload[1]
        hits = [_inside(cap, r_rim * math.cos(math.radians(t)), r_rim * math.sin(math.radians(t)),
                        z_b + 0.05) for t in (10.0, 100.0, 250.0)]
        assert any(hits), cfg
        # the lid sits over the ridge
        assert _inside(cap, 0.0, 0.0, n.profile.z_top + 0.3) or cfg != "core_radar", cfg


def test_radar_cap_is_a_half_wave_radome_at_k_half_lambda():
    from smash.export import nose_radome as NR
    assert CN.cap_t_mm() == pytest.approx(NR.window_thickness_mm(), abs=1e-3)


def test_radar_cap_gap_is_k_half_lambda(built):
    from smash.export import nose_radome as NR
    _g, _d, panel, boards, _c = built
    chain = list(panel.snake_chain)
    n = CN.nose_spec("core_radar", boards, chain)
    aop = next(p.item for p in boards["radar_module"].chip_placements
               if p.item.ref == "U_AWR").height_mm
    gap = n.profile.z_top + CN.CAP_RIDGE_GAP_MM - (n.z_payload[1] + aop)
    k = gap / (NR.wavelength_mm() / 2)
    assert k >= 1 - 1e-3 and k == pytest.approx(round(k), abs=1e-3)



def test_screw_head_bears_on_the_steel_foot_within_the_tab(cups):
    """(2026-11-20, user: tab too short, head too big, pull-down too weak) the
    Ø5.5 ISO 7046 head lies wholly on the tab (above its lower end) and seats
    in a countersink in the 1.3 mm stainless FOOT — steel under the whole
    head; the thread insert sits inward of the foot, inside the band."""
    cup = cups["core_radar"]
    zc1, zr1 = cup["z_ring"]
    P, r_out = cup["parts"], cup["r_out"]
    assert zr1 - zc1 >= NI.ANCHOR_RING_MIN_MM - 1e-6
    zs = zc1 + NI.SCREW_Z_MM
    assert zs - NI.SCREW_HEAD_D_MM / 2 >= zc1 + NI.TAB_BOTTOM_MM          # head on the tab
    assert NI.TAB_FOOT_T_MM >= NI.SCREW_HEAD_K_MM                         # flush countersink
    assert NI.THREAD_INSERT_R_MM[1] <= r_out - NI.TAB_FOOT_T_MM
    assert zs + NI.THREAD_INSERT_OD_MM / 2 <= zr1 + 1e-6                  # insert in the band
    for ang in NI.SCREW_ANGLES_DEG:
        a = math.radians(ang)
        # just outside the 90° countersink cone, at two depths: steel (the foot)
        for depth in (0.6, 0.95):
            rr, dz = r_out - depth, NI.SCREW_HEAD_D_MM / 2 - depth + 0.35
            for sgn in (-1, 1):
                assert _inside(P["retaining_ring"], rr * math.cos(a), rr * math.sin(a),
                               zs + sgn * dz), (ang, depth, sgn)



def test_tabs_hang_from_a_steel_ring_with_the_copper_bump(cups):
    """(2026-11-20, user) the tabs are steel, integral with a retaining RING
    along the cap's edge (overmoulded by the PEEK lid) and its stainless OD-40
    bump (keeps the Ø35.8 body off the bore) — ONE part. Ring + bump stay outside the
    radar FoV keep-out (r ≥ 12.7) — the λ/2 window in the middle is PEEK only."""
    cup = cups["core_radar"]
    P, n, r_out = cup["parts"], cup["nose"], cup["r_out"]
    ring, cap = P["retaining_ring"], P["nose_cap"]
    bump = ring                                         # stainless, integral
    z_top = cup["z_end_out"]
    for t in (0.0, 90.0, 200.0, 300.0):                 # ring all round, at the top edge
        a = math.radians(t)
        r = r_out - NI.CAP_RING_W_MM / 2
        assert _inside(ring, r * math.cos(a), r * math.sin(a), z_top - NI.CAP_RING_T_MM / 2), t
        rb = 0.5 * (r_out + NI.CAP_BUMP_R_MM)
        assert _inside(bump, rb * math.cos(a), rb * math.sin(a), z_top - NI.CAP_BUMP_H_MM / 2), t
        # ROUND OD: the crest (OD 40) only at mid-width, back to the skin at the edges
        rc = NI.CAP_BUMP_R_MM - 0.05
        assert _inside(bump, rc * math.cos(a), rc * math.sin(a), z_top - NI.CAP_BUMP_H_MM / 2), t
        assert not _inside(bump, rc * math.cos(a), rc * math.sin(a), z_top - 0.3), t
    assert r_out - NI.CAP_RING_W_MM >= 12.7
    assert _inside(cap, 0.0, 0.0, z_top - 0.3) or n.payload != "radar_module"    # PEEK window
    bb = ring.val().BoundingBox()
    assert bb.zmin <= cup["z_ring"][0] + NI.TAB_BOTTOM_MM + 1e-3          # tabs reach down



def test_bump_ends_above_the_screw_heads(cups):
    """(user) the round bump ENDS above the screw heads — no cut-outs; the
    heads go in and out radially past nothing."""
    for cfg, cup in cups.items():
        zc1 = cup["z_ring"][0]
        head_top = zc1 + NI.SCREW_Z_MM + NI.SCREW_HEAD_D_MM / 2
        bb = cup["parts"]["retaining_ring"].val().BoundingBox()
        ring = cup["parts"]["retaining_ring"]
        for ang in NI.SCREW_ANGLES_DEG:
            a = math.radians(ang)
            for r in (18.0, 18.5, 19.5):
                for z in (head_top, head_top + NI.BUMP_SCREW_CLEAR_MM - 0.05):
                    assert not _inside(ring, r * math.cos(a), r * math.sin(a), z), (cfg, ang, r)
        assert not any("cap bump bottom" in w for w in cup.get("warnings", [])), cfg
