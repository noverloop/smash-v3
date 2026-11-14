"""Unrolled LDS-sleeve layout (2026-11-14).

The sleeve is a cylinder, so its surface unrolls into a flat rectangle with no
distortion: an axial lane at physical angle θ is a straight vertical line at
x = R·θ. This module writes that flat layout as a 2-layer KiCad board (opens in
Altium) for the layout EE, and wraps the same copper back onto the cylinder as
a STEP for the MID shop's laser software.

Unrolled frame
  x = R_OUT · (θ − SEAM_ANGLES_DEG[0]) in rad, wrapped to [0, 2π·R_OUT) —
      the board's left/right edges are the 105° seam; the 285° seam is the
      silkscreen stripe at x = π·R_OUT.
  y (KiCad, down) = H − z, z = stack height from the aft face (+Z → nose).
  F.Cu = sleeve OUTER face: signal / power lanes, via pads, antenna copper.
  B.Cu = sleeve INNER face: GND plane in the antenna sector (+ via pads).
  Inner-face x uses the outer radius too (vias must line up on both faces);
  the real inner face is 4.5 % shorter — irrelevant for a plane.

Antennas are PLACEHOLDERS (outline + feed + a meander of roughly the right
electrical length): final geometry needs EM simulation with the sleeve, the
GND plane and the potted tower. They sit at fin_ble_board's level, fed from
its feed castellations (castellations.ANTENNA_FEED_ANGLES_DEG).
"""
from __future__ import annotations

import math
import pathlib

from smash.parts.castellations import (
    SEAM_ANGLES_DEG, SEAM_HALF_WIDTH_DEG, CAST_DRILL_MM,
    SIGNAL_SECTOR_CENTRE_DEG, SIGNAL_SECTOR_HALF_DEG,
)
from smash.export.sleeve_step import (SLEEVE_GAP_MM, SLEEVE_WALL_MM,
                                      stack_z_map)

VIA_PAD_MM = 0.75
GND_PLANE_MARGIN_MM = 1.0          # plane stops this far from the sector edges
ANT_WINDOW_MARGIN_MM = 1.5         # plane cut-back round each antenna element
# Plug ring (2026-11-14): a band of the sleeve BELOW the aft board (z < 0) that
# plugs into the follow-up object. Its OUTER face carries the bus as flat gold
# pads (spring contacts in the mating bore press radially — spin presses them
# harder); the 33 V restraint pair ends in two moulded Faston-size tabs
# (2.8 × 0.8 mm, Ø1.4 latch hole) in the antenna sector, reached on the INNER
# face so they cross no bus pad.
PLUG_H_MM = 7.0
PLUG_PAD_LEN_MM = 3.0
PLUG_PAD_Z_MM = (-4.5, -1.5)
TAB_W_MM, TAB_LEN_MM, TAB_HOLE_MM = 2.8, 6.5, 1.4
TAB_ANGLES_DEG = (170.0, 190.0)     # 33 V tabs, ~6 mm apart, far from the bus
GND_PLUG_ANGLES_DEG = (113.0, 120.0, 240.0, 247.0)


def _x_of(theta_deg: float, r: float) -> float:
    d = (theta_deg - SEAM_ANGLES_DEG[0]) % 360.0
    return r * math.radians(d)


def _antenna_placeholders(contract, zmap, r, width):
    """[(net, [(x, z), …] polyline, width_mm, label)] — a meander folded into a
    bounded box beside each feed (fin_ble level, inside the antenna sector).
    Horizontal (circumferential) runs of the box width, stepping axially, until
    the target electrical length is used up or the box is full."""
    out = []
    lanes = contract.get("lanes", {})
    #            label,                 length, box_w, box_h, step, dir(+1 nose / -1 aft)
    # Both hang AFT-ward from fin_ble over the aluminium battery holder, which
    # is their ground (PIFA-style over a backplane ~0.9 mm behind).
    specs = {"ANT_2G4_FEED": ("2.4 GHz PIFA (mLRS + BLE)", 24.0, 10.0, 12.0, 2.0, -1),
             "ANT_SUBG_FEED": ("868-923 MHz PIFA (LoRa)", 80.0, 26.0, 16.0, 2.0, -1)}
    for net, (label, length_mm, bw, bh, step, sgn) in specs.items():
        lane = lanes.get(net)
        if not lane or "fin_ble_board" not in zmap:
            continue
        x0 = _x_of(lane["angles"][0], r)
        z0 = sum(zmap["fin_ble_board"]) / 2.0
        pts = [(x0, z0)]
        z = z0 + sgn * 1.5                       # short riser off the feed
        pts.append((x0, z))
        used, x, go_right = 1.5, x0, True
        while used < length_mm and abs(z - z0) + step <= bh:
            nx = x0 + (bw / 2 if go_right else -bw / 2)
            run = min(abs(nx - x), length_mm - used)
            x = x + (run if nx > x else -run)
            pts.append((x, z)); used += run
            if used >= length_mm:
                break
            z += sgn * step
            pts.append((x, z)); used += step
            go_right = not go_right
        out.append((net, pts, 0.5, label))
    return out


def write_unrolled_sleeve(boards: dict, chain: list, contract: dict,
                          out_path) -> dict:
    """Write the unrolled sleeve as a 2-layer KiCad board. Returns a summary."""
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    zmap = stack_z_map(boards, chain)
    H = max(z1 for _z0, z1 in zmap.values())
    r_out = 17.0 + SLEEVE_GAP_MM + SLEEVE_WALL_MM
    W = 2 * math.pi * r_out
    rigid = [n for n in chain if n in boards and not boards[n].is_spacer
             and boards[n].kind == "rigid"]

    nets = ["", "GND"]
    def nid(n):
        if n not in nets:
            nets.append(n)
        return nets.index(n)

    OX, OY = 20.0, 30.0                    # place the board on the drawing sheet

    def Y(z):
        return round(OY + H - z, 4)

    def X(x):
        return round(OX + x, 4)

    items, n_vias, n_lanes = [], 0, 0
    lanes = contract.get("lanes", {})
    for net, lane in lanes.items():
        kind = lane.get("kind", "signal")
        n = nid("GND" if kind == "gnd_plane" else net)
        zs = sorted(sum(zmap[b]) / 2.0 for b in lane["boards"] if b in zmap)
        for ang in lane["angles"]:
            x = X(_x_of(ang, r_out))
            for zc in zs:
                items.append(f'\t(via (at {x} {Y(zc)}) (size {VIA_PAD_MM}) '
                             f'(drill {CAST_DRILL_MM}) (layers "F.Cu" "B.Cu") (net {n}))')
                n_vias += 1
            if kind in ("signal", "power") and len(zs) >= 2:
                w = lane.get("width_mm", 0.2)
                items.append(f'\t(segment (start {x} {Y(zs[0])}) (end {x} {Y(zs[-1])}) '
                             f'(width {w}) (layer "F.Cu") (net {n}))')
                n_lanes += 1

    ants = _antenna_placeholders(contract, zmap, r_out, W)
    windows = []
    for net, pts, w, label in ants:
        n = nid(net)
        for (xa, za), (xb, zb) in zip(pts, pts[1:]):
            items.append(f'\t(segment (start {X(xa)} {Y(za)}) (end {X(xb)} {Y(zb)}) '
                         f'(width {w}) (layer "F.Cu") (net {n}))')
        xs = [p[0] for p in pts]; zs = [p[1] for p in pts]
        wx0, wz1 = min(xs), min(zs) - 0.4
        # no plane window: over the Al holder the antenna is a PIFA on that ground
        items.append(f'\t(gr_text "{label} - PLACEHOLDER" (at {X(wx0)} {Y(wz1) + 1.0:.2f}) '
                     f'(layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15)) (justify left)))')

    # Inner GND plane over the antenna sector, minus the antenna windows —
    # written PRE-FILLED (rectangles from a grid split at the window edges)
    # so it shows without a refill; KiCad / Altium may repour it.
    a0 = SIGNAL_SECTOR_CENTRE_DEG + SIGNAL_SECTOR_HALF_DEG     # 105°
    a1 = SIGNAL_SECTOR_CENTRE_DEG - SIGNAL_SECTOR_HALF_DEG + 360.0  # 255°
    gx0 = _x_of(a0, r_out) + GND_PLANE_MARGIN_MM
    gx1 = _x_of(a1, r_out) - GND_PLANE_MARGIN_MM
    g = nid("GND")
    from shapely.geometry import box as _box
    plane = _box(gx0, 0.5, gx1, H - 0.5)
    for (wx0, wz0, wx1, wz1) in windows:
        plane = plane.difference(_box(wx0, wz0, wx1, wz1))
    xs_cut = sorted({round(v, 4) for v in (gx0, gx1, *[w[0] for w in windows],
                                          *[w[2] for w in windows])})
    zs_cut = sorted({round(v, 4) for v in (0.5, H - 0.5, *[w[1] for w in windows],
                                          *[w[3] for w in windows])})
    fills = []
    for xa, xb in zip(xs_cut, xs_cut[1:]):
        for za, zb in zip(zs_cut, zs_cut[1:]):
            cell = _box(xa, za, xb, zb)
            if plane.contains(cell.centroid) and plane.intersection(cell).area > 0.99 * cell.area:
                fills.append(f'(filled_polygon (layer "B.Cu") (pts (xy {X(xa)} {Y(zb)}) '
                             f'(xy {X(xb)} {Y(zb)}) (xy {X(xb)} {Y(za)}) (xy {X(xa)} {Y(za)})))')
    items.append(
        f'\t(zone (net {g}) (net_name "GND") (layer "B.Cu") (hatch edge 0.5) '
        f'(connect_pads yes (clearance 0.2)) (min_thickness 0.2) '
        f'(fill yes (thermal_gap 0.3) (thermal_bridge_width 0.3)) '
        f'(polygon (pts (xy {X(gx0)} {Y(H - 0.5)}) (xy {X(gx1)} {Y(H - 0.5)}) '
        f'(xy {X(gx1)} {Y(0.5)}) (xy {X(gx0)} {Y(0.5)}))) ' + " ".join(fills) + ')')

    # ── Plug ring ──
    from smash.parts.castellations import RESTRAINT_NETS
    first = rigid[0] if rigid else None
    zf = sum(zmap[first]) / 2.0 if first else 0.0
    n_plug = 0
    pz0, pz1 = PLUG_PAD_Z_MM
    for net, lane in lanes.items():
        kind = lane.get("kind", "signal")
        if first not in lane["boards"] or kind in ("gnd_plane", "antenna_feed"):
            continue
        n = nid(net)
        for ang in lane["angles"]:
            x = X(_x_of(ang, r_out))
            w = lane.get("width_mm", 0.2)
            if kind == "plug_exit":                     # via at the aft board
                items.append(f'\t(via (at {x} {Y(zf)}) (size {VIA_PAD_MM}) '
                             f'(drill {CAST_DRILL_MM}) (layers "F.Cu" "B.Cu") (net {n}))')
            if net in RESTRAINT_NETS:
                # down to the ring, via to the inner face, across to its tab
                tab = TAB_ANGLES_DEG[RESTRAINT_NETS.index(net)]
                zr = pz1 + 0.5 if net == RESTRAINT_NETS[0] else pz0 + 0.5
                tx = X(_x_of(tab, r_out))
                items.append(f'\t(segment (start {x} {Y(zf)}) (end {x} {Y(zr)}) (width {w}) (layer "F.Cu") (net {n}))')
                for vx in (x, tx):
                    items.append(f'\t(via (at {vx} {Y(zr)}) (size 1.0) (drill 0.5) (layers "F.Cu" "B.Cu") (net {n}))')
                items.append(f'\t(segment (start {x} {Y(zr)}) (end {tx} {Y(zr)}) (width {w}) (layer "B.Cu") (net {n}))')
                ty0 = -PLUG_H_MM + 0.5
                items.append(f'\t(segment (start {tx} {Y(zr)}) (end {tx} {Y(ty0)}) (width {TAB_W_MM}) (layer "F.Cu") (net {n}))')
                items.append(f'\t(gr_circle (center {tx} {Y(ty0 + 1.6)}) (end {tx + TAB_HOLE_MM / 2} {Y(ty0 + 1.6)}) '
                             f'(stroke (width 0.1) (type solid)) (fill none) (layer "Edge.Cuts"))')
                ox0, ox1 = tx - TAB_W_MM / 2, tx + TAB_W_MM / 2
                for (xa, ya, xb, yb) in ((ox0, Y(-PLUG_H_MM), ox0, Y(-PLUG_H_MM - TAB_LEN_MM)),
                                         (ox0, Y(-PLUG_H_MM - TAB_LEN_MM), ox1, Y(-PLUG_H_MM - TAB_LEN_MM)),
                                         (ox1, Y(-PLUG_H_MM - TAB_LEN_MM), ox1, Y(-PLUG_H_MM))):
                    items.append(f'\t(gr_line (start {xa:.3f} {ya}) (end {xb:.3f} {yb}) (stroke (width 0.15) (type solid)) (layer "F.SilkS"))')
                items.append(f'\t(gr_text "33V {'HV' if net == RESTRAINT_NETS[0] else 'RET'}" (at {tx} {Y(-PLUG_H_MM - TAB_LEN_MM - 1.2)}) (layer "F.SilkS") '
                             f'(effects (font (size 0.7 0.7) (thickness 0.1))))')
                n_plug += 1
                continue
            # bus pad: lane runs on down to a flat contact pad on the ring
            pw = max(0.5, w)
            items.append(f'\t(segment (start {x} {Y(zf)}) (end {x} {Y(pz1)}) (width {w}) (layer "F.Cu") (net {n}))')
            items.append(f'\t(zone (net {n}) (net_name "{net}") (layer "F.Cu") (hatch none 0.5) '
                         f'(connect_pads yes (clearance 0.15)) (min_thickness 0.1) (fill yes) '
                         f'(polygon (pts (xy {x - pw / 2:.3f} {Y(pz1)}) (xy {x + pw / 2:.3f} {Y(pz1)}) '
                         f'(xy {x + pw / 2:.3f} {Y(pz0)}) (xy {x - pw / 2:.3f} {Y(pz0)}))) '
                         f'(filled_polygon (layer "F.Cu") (pts (xy {x - pw / 2:.3f} {Y(pz1)}) (xy {x + pw / 2:.3f} {Y(pz1)}) '
                         f'(xy {x + pw / 2:.3f} {Y(pz0)}) (xy {x - pw / 2:.3f} {Y(pz0)}))))')
            n_plug += 1
    g_ = nid("GND")
    for ga in GND_PLUG_ANGLES_DEG:                     # GND pads from the inner plane
        gx = X(_x_of(ga, r_out))
        items.append(f'\t(via (at {gx} {Y(0.9)}) (size {VIA_PAD_MM}) (drill {CAST_DRILL_MM}) (layers "F.Cu" "B.Cu") (net {g_}))')
        items.append(f'\t(segment (start {gx} {Y(0.9)}) (end {gx} {Y(pz1)}) (width 0.6) (layer "F.Cu") (net {g_}))')
        items.append(f'\t(zone (net {g_}) (net_name "GND") (layer "F.Cu") (hatch none 0.5) (connect_pads yes (clearance 0.15)) '
                     f'(min_thickness 0.1) (fill yes) (polygon (pts (xy {gx - 0.75:.3f} {Y(pz1)}) (xy {gx + 0.75:.3f} {Y(pz1)}) '
                     f'(xy {gx + 0.75:.3f} {Y(pz0)}) (xy {gx - 0.75:.3f} {Y(pz0)}))) (filled_polygon (layer "F.Cu") '
                     f'(pts (xy {gx - 0.75:.3f} {Y(pz1)}) (xy {gx + 0.75:.3f} {Y(pz1)}) (xy {gx + 0.75:.3f} {Y(pz0)}) (xy {gx - 0.75:.3f} {Y(pz0)}))))')
        n_plug += 1
    items.append(f'\t(gr_line (start {X(0)} {Y(0)}) (end {X(W)} {Y(0)}) (stroke (width 0.3) (type solid)) (layer "F.SilkS"))')
    items.append(f'\t(gr_text "PLUG RING (outer-face contact pads; 33V restraint tabs)" '
                 f'(at {X(W * 0.72)} {Y(-PLUG_H_MM) + 1.6:.2f}) (layer "F.SilkS") (effects (font (size 0.9 0.9) (thickness 0.14))))')

    # Aluminium BEHIND the sleeve (battery holder, aft rings): outline bands
    # across the full width at their height, so antennas / lanes over metal
    # are visible. (Al = ground right behind the antenna copper: fine for a
    # patch / PIFA, kills a Yagi.)
    from smash.export.spacer_step import gap_kind
    metal = {}
    for n, (z0, z1) in zmap.items():
        if n in boards and boards[n].is_spacer and gap_kind(n) in ("battery_holder", "ring"):
            key = "battery_holder" if gap_kind(n) == "battery_holder" else n
            a, b_ = metal.get(key, (z0, z1))
            metal[key] = (min(a, z0), max(b_, z1))
    for key, (z0, z1) in metal.items():
        label = ("AL BATTERY HOLDER BEHIND (r 17.0, GND)" if key == "battery_holder"
                 else "AL RING BEHIND (r 15.2-16.2)")
        pts = [(X(0), Y(z1)), (X(W), Y(z1)), (X(W), Y(z0)), (X(0), Y(z0))]
        for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
            items.append(f'\t(gr_line (start {xa} {ya}) (end {xb} {yb}) '
                         f'(stroke (width 0.3) (type dash_dot)) (layer "F.SilkS"))')
        items.append(f'\t(gr_text "{label}" (at {X(W / 2)} {Y((z0 + z1) / 2):.2f}) '
                     f'(layer "F.SilkS") (effects (font (size 1.2 1.2) (thickness 0.18))))')

    # Silkscreen: board levels, seams, sectors.
    for b in rigid:
        z0, z1 = zmap[b]
        for z in (z0, z1):
            items.append(f'\t(gr_line (start {X(0)} {Y(z)}) (end {X(W)} {Y(z)}) '
                         f'(stroke (width 0.05) (type dash)) (layer "F.SilkS"))')
        items.append(f'\t(gr_text "{b}" (at {X(-1)} {Y((z0 + z1) / 2):.2f}) (layer "F.SilkS") '
                     f'(effects (font (size 0.8 0.8) (thickness 0.12)) (justify right)))')
    hw = r_out * math.radians(SEAM_HALF_WIDTH_DEG)
    for xc in (0.0, W / 2.0, W):            # 105° seam = both edges; 285° = middle
        for xs_ in (xc - hw, xc + hw):
            if 0.0 <= xs_ <= W:
                items.append(f'\t(gr_line (start {X(xs_)} {Y(H)}) (end {X(xs_)} {Y(0)}) '
                             f'(stroke (width 0.15) (type solid)) (layer "F.SilkS"))')
    items.append(f'\t(gr_text "ANTENNA SECTOR (inner face = GND plane)" '
                 f'(at {X((gx0 + gx1) / 2)} {Y(H) - 2:.2f}) (layer "F.SilkS") '
                 f'(effects (font (size 1.2 1.2) (thickness 0.18))))')
    items.append(f'\t(gr_text "SIGNAL SECTOR (outer-face lanes)" '
                 f'(at {X((gx1 + W) / 2)} {Y(H) - 2:.2f}) (layer "F.SilkS") '
                 f'(effects (font (size 1.2 1.2) (thickness 0.18))))')

    net_lines = "\n".join(f'\t(net {i} "{n}")' for i, n in enumerate(nets))
    body = "\n".join(items)
    out_path.write_text(f'''(kicad_pcb (version 20240108) (generator "smash_sleeve_layout") (generator_version "1")
\t(general (thickness {SLEEVE_WALL_MM}))
\t(paper "A4")
\t(layers
\t\t(0 "F.Cu" signal "Sleeve.Outer")
\t\t(31 "B.Cu" signal "Sleeve.Inner")
\t\t(36 "B.SilkS" user "B.Silkscreen")
\t\t(37 "F.SilkS" user "F.Silkscreen")
\t\t(38 "B.Mask" user)
\t\t(39 "F.Mask" user)
\t\t(44 "Edge.Cuts" user)
\t)
\t(setup (pad_to_mask_clearance 0))
{net_lines}
\t(gr_rect (start {X(0)} {Y(H)}) (end {X(W)} {Y(-PLUG_H_MM)}) (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts"))
{body}
)
''')
    return {"path": out_path, "width_mm": W, "height_mm": H, "n_vias": n_vias,
            "n_lanes": n_lanes, "n_plug": n_plug, "n_antennas": len(ants), "r_out": r_out}


def write_sleeve_copper_step(boards: dict, chain: list, contract: dict,
                             out_path, thickness_mm: float = 0.03) -> dict:
    """Wrap the outer-face copper (lanes + antenna placeholders) back onto the
    cylinder as thin solids (exaggerated to `thickness_mm` so it shows)."""
    import cadquery as cq
    zmap = stack_z_map(boards, chain)
    r_out = 17.0 + SLEEVE_GAP_MM + SLEEVE_WALL_MM
    bodies = []

    def strip(theta_deg, z0, z1, w):
        h = max(z1 - z0, 0.05)
        b = (cq.Workplane("XY").box(thickness_mm, w, h, centered=(False, True, False))
             .translate((r_out, 0, z0)).rotate((0, 0, 0), (0, 0, 1), theta_deg))
        bodies.append(b)

    def arc(theta0, theta1, z, w):
        # circumferential run: a thin annular sector at height z
        t0, t1 = sorted((theta0, theta1))
        if t1 - t0 < 1e-6:
            return
        sec = (cq.Workplane("XY").circle(r_out + thickness_mm).circle(r_out)
               .extrude(w).translate((0, 0, z - w / 2)))
        wedge = (cq.Workplane("XY").polyline(
            [(0, 0)] + [((r_out + 1) * math.cos(math.radians(t)),
                         (r_out + 1) * math.sin(math.radians(t)))
                        for t in (t0 + (t1 - t0) * k / 8 for k in range(9))])
            .close().extrude(w).translate((0, 0, z - w / 2)))
        bodies.append(sec.intersect(wedge))

    for net, lane in contract.get("lanes", {}).items():
        if lane.get("kind", "signal") not in ("signal", "power"):
            continue
        zs = sorted(sum(zmap[b]) / 2.0 for b in lane["boards"] if b in zmap)
        if len(zs) < 2:
            continue
        for ang in lane["angles"]:
            strip(ang, zs[0], zs[-1], lane.get("width_mm", 0.2))
    for net, pts, w, _label in _antenna_placeholders(contract, zmap, r_out, 0):
        theta0 = SEAM_ANGLES_DEG[0]
        for (xa, za), (xb, zb) in zip(pts, pts[1:]):
            ta = theta0 + math.degrees(xa / r_out)
            tb = theta0 + math.degrees(xb / r_out)
            if abs(xa - xb) < 1e-6:
                strip(ta, min(za, zb), max(za, zb), w)
            else:
                arc(ta, tb, za, w)
    asm = cq.Assembly()
    for k, b in enumerate(bodies):
        asm.add(b, name=f"cu{k}", color=cq.Color(0.85, 0.55, 0.2, 1.0))
    out_path = pathlib.Path(out_path)
    asm.export(str(out_path))
    return {"path": out_path, "n_bodies": len(bodies)}
