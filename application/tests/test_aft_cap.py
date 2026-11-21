"""(2026-11-19) aft_end_cap — the aft public interface: the bench pads became
contacts of an aft-facing crown on a PEEK-LDS cap; the parachute wires are
clamp tabs on aft_end_board's bottom (cutter pads at the centre)."""
from __future__ import annotations

import importlib
import math
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built():
    sys.path.insert(0, str(REPO))
    try:
        gen = importlib.import_module("generate_stackup")
    finally:
        sys.path.pop(0)
    from smash.layout.placer import place_design
    from smash.parts.castellations import place_castellations
    from smash.layout.placer.spacer_sizing import size_backbone_spacers
    d = gen.Design()
    gen._set_battery_mode("maximalist")
    gen._prime_power_rails(d)
    for fn in (gen.build_qpd_module, gen.build_radar_nose_io, gen.build_usb_nose,
               gen.build_camera_module, gen.build_aft_end_board, gen.build_activation_interface,
               gen.build_radar_module_awr1843aop, gen.build_companion_compute,
               gen.build_power_board, gen.build_wakeup_board, gen.build_fins_module):
        fn(d)
    gen._empty_aft_end_top(d)
    panel, boards = gen.build_panel(straight=gen._STRAIGHT_SNAKE,
                                    battery_length_mm=gen._compartment_mm())
    gen.build_spacers(d, boards)
    gen._mark_preplace_keepouts(d, boards)
    gen._mark_ring_band_keepouts(panel, boards)
    place_design(d, panel, boards)
    size_backbone_spacers(panel, boards)
    contract, counts = place_castellations(
        d, panel, boards, connect=lambda n, p: gen._net(d, n).connect(p),
        cone_exits=gen._CONE_EXITS)
    return gen, d, boards, contract, counts


def test_every_cap_net_has_a_tooth_and_the_fan_never_crosses(built):
    gen, d, _b, contract, _c = built
    cap = contract["aft_cap"]
    assert cap and not cap["missing"]
    sig = [t for t in cap["contacts"] if t["role"] == "signal"]
    cap_refs = {c.ref for c in d.chips if c.board_tag == gen.AFT_CAP}
    nets = {n.name for n in d.nets if {rf for rf, _p in n.pins} & cap_refs
            and n.name not in ("GND", "FLEX_GND")}
    assert {t["net"] for t in sig} == nets
    assert len(sig) >= 39
    screws = [t for t in cap["contacts"] if t["role"] == "screw"]
    assert len(screws) == 3 and all(t["label"] == "" for t in screws)
    sa = sorted(t["angle_deg"] for t in screws)
    assert len({round((b - a) % 360, 3) for a, b in zip(sa, sa[1:] + sa[:1])}) == 3   # keyed
    start = screws[0]["angle_deg"]
    u = lambda a: (a - start) % 360.0
    teeth = [u(t["angle_deg"]) for t in sorted(sig, key=lambda t: u(t["lane_angle"]))]
    assert teeth == sorted(teeth)                       # order-preserving: no crossings
    assert cap["gnd_link"] is not None


def test_battery_zone_fan_never_crosses(built):
    """(2026-11-19) cap lanes AND the aft board's own lanes fan together in the
    battery zone, in one cyclic order: tops and bottoms sorted the same way."""
    _g, _d, _b, contract, _c = built
    from smash.parts.castellations import AFT_CAP_SCREW_TEETH, aft_tooth_angle
    start = aft_tooth_angle(AFT_CAP_SCREW_TEETH[0])
    u = lambda a: (a - start) % 360.0
    fans = sorted((u(ln["fan"]["top_deg"]), u(ln["fan"]["bottom_deg"]), k)
                  for k, ln in contract["lanes"].items() if ln.get("fan"))
    assert len(fans) >= 39
    bottoms = [b for _t, b, _k in fans]
    assert bottoms == sorted(bottoms) and len(set(bottoms)) == len(bottoms)
    gaps = [b - a for a, b in zip(bottoms, bottoms[1:])]
    assert min(gaps) >= math.degrees(0.8 / 17.0) - 1e-6     # one lane pitch apart
    # cap lanes end on a tooth: straight down onto the cap, no skin jog
    for t in contract["aft_cap"]["contacts"]:
        if t["role"] == "signal":
            assert contract["lanes"][t["net"]]["fan"]["bottom_deg"] == t["angle_deg"]


def test_cap_lanes_skip_the_aft_board(built):
    gen, d, _b, contract, _c = built
    aft_refs = {c.ref for c in d.chips if c.board_tag == "aft_end_board"}
    for key, ln in contract["lanes"].items():
        if not ln.get("aft_cap"):
            continue
        net = d.net_by_name(ln.get("net", key))
        if net is not None and not ({rf for rf, _p in net.pins} & aft_refs):
            assert "aft_end_board" not in ln["boards"], key


def test_aft_board_keeps_tabs_and_cutter_pads(built):
    gen, _d, boards, _c, _n = built
    refs = {pl.item.ref: pl for pl in boards["aft_end_board"].chip_placements}
    for i in range(16):
        pl = refs[f"P_ACT_WIRE_{i}"]
        assert pl.face == "bottom"
        assert math.hypot(*pl.position_mm) == pytest.approx(6.4, abs=1e-2)
    for c in range(4):                      # (2026-11-20) matrix column tabs, inner ring
        assert math.hypot(*refs[f"P_ACT_COL_{c}"].position_mm) == pytest.approx(3.8, abs=1e-2)
    for r in gen._AFT_CUTTER_PADS:
        assert math.hypot(*refs[r].position_mm) < 2.0          # centre of the tab ring
    assert not any(r.startswith("TP_") and r not in gen._AFT_CUTTER_PADS for r in refs)


def test_cap_solid_and_drawings(built, tmp_path):
    pytest.importorskip("cadquery")
    from smash.export.aft_cap import write_aft_cap
    _g, _d, _b, contract, _c = built
    r = write_aft_cap(contract, tmp_path)
    assert r["valid"] and r["solids"] == 1
    import cadquery as cq
    body = cq.importers.importStep(str(tmp_path / "aft_end_cap.step"))
    bb = body.val().BoundingBox()
    assert max(abs(bb.xmin), abs(bb.xmax), abs(bb.ymin), abs(bb.ymax)) <= 17.9 + 1e-3
    assert bb.zmax <= 1e-6                                      # hangs off the aft face
    svg = (tmp_path / "aft_end_cap_face.svg").read_text()
    assert "SWDIO" in svg and "rotate(" in svg                 # radial gate labels
    from smash.export.aft_cap import CAP_SCREW_ANGLES_DEG, CAP_SCREW_R_MM
    holes = boards_holes = None
    assert "Contact map" in (tmp_path / "aft_end_cap.md").read_text()


def test_cap_crown_is_slanted_tallest_inside(built):
    """(2026-11-20, user) the aft crown is a cone — compliant, self-centring
    contacts under acceleration. (2026-11-21, user) TALLEST (aft-most) at the
    inner diameter, shortest at the outer one (less height at the OD). Probed
    on a screw position (solid land) and in a contact groove (floor on the
    cone, T deep)."""
    cq = pytest.importorskip("cadquery")
    from smash.export import aft_cap as AC
    from smash.export import nose_interface as NI
    _g, _d, _b, contract, _c = built
    cap = contract["aft_cap"]
    body = AC.build_aft_cap(cq, cap, 17.9)
    z_plate = -AC.CAP_PLATE_T_MM
    inside = lambda r, a, z: body.val().isInside(
        cq.Vector(r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), z))
    if AC.cone_deg() > 0:                                               # (flat since 2026-11-21)
        assert AC.tip_z(14.3, z_plate, 17.9) < AC.tip_z(17.5, z_plate, 17.9)  # aft-most inside
    else:
        assert AC.tip_z(14.3, z_plate, 17.9) == pytest.approx(AC.tip_z(17.5, z_plate, 17.9))
    a_scr = AC.CAP_SCREW_ANGLES_DEG[0]
    groove = next(c["angle_deg"] for c in cap["contacts"] if c["role"] == "signal")
    for r in (14.3, 16.0, 17.5):
        zt = AC.tip_z(r, z_plate, 17.9)
        assert inside(r, a_scr, zt + 0.05) and not inside(r, a_scr, zt - 0.05)
        assert not inside(r, groove, zt + 0.05)                         # groove …
        assert inside(r, groove, zt + NI.TOOTH_H_MM + 0.05)             # … floor on the cone
    assert body.solids().size() == 1 and body.val().isValid()


def test_cells_are_wired_to_aft_end_board(built):
    """(2026-11-20, user) Tadiran /P cells: − pins straight through the holder
    floor into PTHs at the cell axes, + pins via wires down the potting channel
    into PTHs round its exit — all on aft_end_board; nothing on the battery
    ceiling (activation_interface's bottom face is empty)."""
    from smash.export import spacer_step as SS
    _g, d, boards, contract, _c = built
    chips = {c.ref: c for c in d.chips}
    assert not any(r.startswith("P_CELL_TAB") for r in chips)
    refs = {pl.item.ref: pl for b in boards.values() for pl in b.chip_placements}
    for k, (x, y) in enumerate(SS.cell_centres_xy(), 1):
        pl = refs[f"P_CELL_PIN_NEG{k}"]
        assert chips[f"P_CELL_PIN_NEG{k}"].board_tag == "aft_end_board"
        assert pl.position_mm == pytest.approx((x, y), abs=1e-3)
    for k, (x, y) in enumerate(SS.cell_wire_pads_xy(), 1):
        pl = refs[f"P_CELL_WIRE_POS{k}"]
        assert chips[f"P_CELL_WIRE_POS{k}"].board_tag == "aft_end_board"
        assert pl.position_mm == pytest.approx((x, y), abs=1e-3)
        # every wire PTH lies inside the floor-underside fan-out pocket
        from shapely.geometry import Point
        assert SS.wire_fan_pocket().contains(Point(x, y).buffer(0.65))
    # the lead PTHs clear the clamp-tab ring and the cap screw holes
    for k in range(1, 4):
        for ref in (f"P_CELL_PIN_NEG{k}", f"P_CELL_WIRE_POS{k}"):
            x, y = refs[ref].position_mm
            for t in [r for r in refs if r.startswith(("P_ACT_WIRE_", "P_ACT_COL_"))]:
                assert math.dist((x, y), refs[t].position_mm) > 0.8 + 0.8 + 0.2, (ref, t)
            for h in boards["aft_end_board"].geometry.holes:
                assert math.dist((x, y), h.position_mm) > h.diameter_mm / 2 + 0.8 + 0.2, ref
    # (2026-11-21, user) the ceiling's bottom carries NO components (only
    # pads / test points), so the part headroom above the cells can go
    ceiling = boards["activation_interface"]
    for pl in ceiling.chip_placements:
        if pl.face != "bottom" or pl.item.ref.startswith(("J_", "TP_", "P_")):
            continue
        raise AssertionError(f"{pl.item.ref} on the battery ceiling's bottom")



def test_parachute_matrix(built):
    """(2026-11-20, user) 4 × 4 diode matrix driven straight by the fin MCU:
    16 wires, each with its own steering diode on aft_end's TOP (inside the
    holder-floor pocket); only rows + columns cross to aft_end; no decoder."""
    from shapely.geometry import box
    from smash.export import spacer_step as SS
    _g, d, boards, contract, _c = built
    chips = {c.ref: c for c in d.chips}
    assert "U_ACTIVATE_DEC" not in chips and not any(r.startswith("Q_ACTIVATE_N") for r in chips)
    nets = {}
    for c in d.chips:
        for p in c.pins:
            n = getattr(p.net, "name", p.net)
            if n:
                nets.setdefault(n, set()).add((c.ref, p.name))
    for k in range(16):
        r, col = k // 4, k % 4
        assert (f"D_ACT_WIRE_{k}", "A") in nets[f"ACT_ROW_{r}"]
        assert {(f"D_ACT_WIRE_{k}", "K"), (f"P_ACT_WIRE_{k}", "1")} <= nets[f"ACT_WIRE_{k}"]
    for i in range(4):
        assert ("U_G0B1_FIN", f"PA{i}") in nets[f"ACT_ROW_SEL_{i}"]
        assert ("U_G0B1_FIN", f"PA{5 + i}") in nets[f"ACT_COL_SEL_{i}"]
    refs = {pl.item.ref: pl for b in boards.values() for pl in b.chip_placements}
    pocket = SS.piezo_pocket()
    for k in range(16):
        pl = refs[f"D_ACT_WIRE_{k}"]
        assert chips[f"D_ACT_WIRE_{k}"].board_tag == "aft_end_board" and pl.face == "top"
        x, y = pl.position_mm
        from shapely.geometry import Point
        assert pocket.contains(Point(x, y).buffer(0.6)), k     # 1.0 × 0.6 body + margin
    # wires no longer need their own lane to aft_end: only rows / columns cross
    lanes = contract["lanes"]
    assert not any(n.startswith("ACT_WIRE_") for n in lanes)
