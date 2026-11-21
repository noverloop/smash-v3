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
  B.Cu = sleeve INNER face: GND plane in the antenna sector (+ via pads),
         CUT AWAY behind the slot antennas (metal behind a slot shorts it).
  Inner-face x uses the outer radius too (vias must line up on both faces);
  the real inner face is 4.5 % shorter — irrelevant for a plane.

Antennas (2026-11-17): the simulated ARC SLOTS of smash.parts.antenna_slots
— each a slot in a local GND copper patch on the outer face, fed by a CPW
from the radio board's feed castellation (castellations.ANTENNA_FEED_ANGLES_DEG).
"""
from __future__ import annotations

import math
import pathlib

from smash.parts.castellations import (
    SEAM_ANGLES_DEG, SEAM_HALF_WIDTH_DEG, CAST_DRILL_MM,
    SIGNAL_SECTOR_CENTRE_DEG, SIGNAL_SECTOR_HALF_DEG,
)
from smash.export.sleeve_step import (SLEEVE_GAP_MM, SLEEVE_WALL_MM,
                                      INNER_FACE_LASERABLE, stack_z_map)

VIA_PAD_MM = 0.75
GND_PLANE_MARGIN_MM = 1.0          # plane stops this far from the sector edges
ANT_WINDOW_MARGIN_MM = 1.5         # plane cut-back round each antenna element
# Plug ring (2026-11-14): a band of the sleeve BELOW the aft board (z < 0).
# It carries the aft board's former bottom-face interface, unchanged (same
# groups, labels and pads: SPI, FIN 1-4, CAN, BAT, PARACHUTE WIRES — the 33 V
# mux sector outputs + common —, GROUND, PROGRAM_MP25, …) as solderable gold
# pads on its OUTER face: ONE row, all pads the same size, copper running
# to the ring's aft edge (wires soldered on; the nichrome restraint wires are
# attached mechanically to their pads — same pad, no solder). Each pad is fed from its own
# exit castellation on the aft board (contract["plug"]) by a non-crossing
# fan-out; no trace crosses a seam (each half-shell fans out on its own).
PLUG_PAD_GAP_MM = 0.45            # copper gap between neighbouring pads
PLUG_PAD_H_MM = 4.0                # pad length, ending at the aft edge
PLUG_LABEL_BAND_MM = 3.2           # pad names + group captions above the pads
PLUG_LEVEL_STEP_MM = 0.4
PLUG_TRACE_MM = 0.25


def _x_of(theta_deg: float, r: float) -> float:
    d = (theta_deg - SEAM_ANGLES_DEG[0]) % 360.0
    return r * math.radians(d)


def _board_mid(boards, zmap) -> dict:
    return {n: 0.5 * (z0 + z1) for n, (z0, z1) in zmap.items()
            if n in boards and not boards[n].is_spacer}


def _rect_cells(polys) -> list:
    """Decompose a shapely (Multi)Polygon into axis-aligned rectangles
    (x0, z0, x1, z1): grid split at every vertex, cells merged along x."""
    from shapely.geometry import box as _box
    geoms = getattr(polys, "geoms", [polys])
    xs = sorted({round(x, 4) for g in geoms for x, _z in g.exterior.coords}
                | {round(x, 4) for g in geoms for i in g.interiors for x, _z in i.coords})
    zs = sorted({round(z, 4) for g in geoms for _x, z in g.exterior.coords}
                | {round(z, 4) for g in geoms for i in g.interiors for _x, z in i.coords})
    out = []
    for za, zb in zip(zs, zs[1:]):
        run = None
        for xa, xb in zip(xs, xs[1:]):
            c = _box(xa, za, xb, zb)
            inside = polys.intersection(c).area > 0.99 * c.area
            if inside:
                run = (run[0], xb) if run else (xa, xb)
            elif run:
                out.append((run[0], za, run[1], zb)); run = None
        if run:
            out.append((run[0], za, run[1], zb))
    return out


def _antenna_copper(boards, zmap, H):
    """(gnd_cells, strips, feeds, labels, slot_rects, window_rects) of the
    slot antennas in the unrolled frame (x from the 105° seam, z up)."""
    from shapely.geometry import box as _box
    from shapely.ops import unary_union
    from smash.parts import antenna_slots as AS
    geo = AS.unrolled_geometry(_board_mid(boards, zmap), SEAM_ANGLES_DEG[0], (0.5, H - 0.5))
    if not geo["copper"]:
        return [], [], [], [], [], []
    cu = unary_union([_box(*r) for r in geo["copper"]])
    cuts = unary_union([_box(*r) for r in geo["cutouts"]])
    gnd = cu.difference(cuts)
    slot_rects = [r for r in geo["cutouts"]]
    windows = [(x0 - ANT_WINDOW_MARGIN_MM, z0 - ANT_WINDOW_MARGIN_MM,
                x1 + ANT_WINDOW_MARGIN_MM, z1 + ANT_WINDOW_MARGIN_MM)
               for x0, z0, x1, z1 in geo["copper"]]
    return (_rect_cells(gnd), geo["strips"], geo["feeds"], geo["labels"],
            slot_rects, windows)


def _crown_z(boards, chain, zmap) -> float:
    """z of the crown plane: the top of the compute↔payload gap (payload bottom)."""
    from smash.export import nose_interface as NI
    for i, nm in enumerate(chain):
        if nm == NI.HOST:
            for nx in chain[i + 1:]:
                if nx in boards and not boards[nx].is_spacer:
                    return zmap[nx][0] if nx in zmap else max(z for _a, z in zmap.values())
            return zmap[nm][1]
    return max(z for _a, z in zmap.values())


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

    def path(pts, w, n):
        """Polyline on the unroll (pts = [(x on the unroll, z)]). A step that
        crosses the 105° seam is drawn the SHORT way: out of one sheet edge
        and back in at the other (it is a small jog on the cylinder)."""
        out = []
        for (xa, za), (xb, zb) in zip(pts, pts[1:]):
            if abs(xa - xb) < 1e-9 and abs(za - zb) < 1e-9:
                continue
            if abs(xb - xa) > W / 2:                       # wrap over the seam
                xb2 = xb - W if xb > xa else xb + W
                xe = W if xb2 > xa else 0.0
                t = (xe - xa) / (xb2 - xa)
                zm = za + t * (zb - za)
                segs_ = [((xa, za), (xe, zm)), ((W - xe, zm), (xb, zb))]
            else:
                segs_ = [((xa, za), (xb, zb))]
            for (x1, z1), (x2, z2) in segs_:
                out.append(f'\t(segment (start {X(x1)} {Y(z1)}) (end {X(x2)} {Y(z2)}) '
                           f'(width {w}) (layer "F.Cu") (net {n}))')
        return out

    items, n_vias, n_lanes = [], 0, 0
    lanes = contract.get("lanes", {})
    # battery-zone fan band: aft board top → next rigid board bottom (+ margins)
    fz = ((contract.get("aft_cap") or {}).get("fan_zone"))
    fan_z = ((zmap[fz[0]][1] + 1.0, zmap[fz[1]][0] - 1.0)
             if fz and fz[0] in zmap and fz[1] in zmap else None)
    # (2026-11-20) STAGGERED fan diagonals: two wide neighbours jogging the
    # same way run parallel and close up to (spacing × cos φ). Each lane's
    # diagonal may start lower (0.5 mm steps) until it keeps the LDS clearance
    # to every neighbour already drawn — checked on the real geometry.
    fan_drop = {}
    if fan_z is not None:
        from smash.export.nose_interface import _seg_dist, LANE_CLEAR_MM
        fl = [(k, ln) for k, ln in lanes.items() if ln.get("fan")]
        fl.sort(key=lambda kl: _x_of(kl[1]["fan"]["top_deg"], r_out))
        drawn = []                         # (xt, xb, drop, w)
        zt, zb = fan_z[1], fan_z[0]

        def segs(xt, xb, drop):
            return [((xt, zt + 5.0), (xt, zt - drop)), ((xt, zt - drop), (xb, zb))]
        for k, ln in fl:
            w = ln.get("width_mm", 0.2)
            xt = _x_of(ln["fan"]["top_deg"], r_out)
            xb = _x_of(ln["fan"]["bottom_deg"], r_out)
            xb = xt + ((xb - xt + W / 2) % W - W / 2)          # short way round
            drop = 0.0
            while drop < 0.6 * (zt - zb):
                mine = segs(xt, xb, drop)
                if all(_seg_dist(a1, a2, b1, b2) - 0.5 * (w + ow) >= LANE_CLEAR_MM
                       for (oxt, oxb, od, ow) in drawn[-6:]
                       for a1, a2 in mine for b1, b2 in segs(oxt, oxb, od)):
                    break
                drop += 0.5
            fan_drop[k] = drop
            drawn.append((xt, xb, drop, w))
    for net, lane in lanes.items():
        kind = lane.get("kind", "signal")
        if kind == "crown_payload":
            continue                       # nose-cone copper, not the core sleeve
        n = nid("GND" if kind == "gnd_plane" else lane.get("net", net))
        zs = sorted(sum(zmap[b]) / 2.0 for b in lane["boards"] if b in zmap)
        fan = lane.get("fan")
        if fan and fan_z is not None:
            # (2026-11-19) battery-zone FAN: down at the lane angle to the top of
            # the zone, diagonal to the bottom angle, then down at that angle to
            # the aft board's castellation (or on to the rim → aft_end_cap)
            w = lane.get("width_mm", 0.2)
            xt, xb = _x_of(fan["top_deg"], r_out), _x_of(fan["bottom_deg"], r_out)
            z_hi = max(zs) if zs else fan_z[1]
            z_lo = 0.0 if lane.get("aft_cap") else min(zs) if zs else 0.0
            for zc in zs:
                bn_ = next(b for b in lane["boards"] if b in zmap and abs(sum(zmap[b]) / 2.0 - zc) < 1e-9)
                xa = X(_x_of(lane.get("board_angles", {}).get(bn_, [fan["top_deg"]])[0], r_out))
                items.append(f'\t(via (at {xa} {Y(zc)}) (size {VIA_PAD_MM}) '
                             f'(drill {CAST_DRILL_MM}) (layers "F.Cu" "B.Cu") (net {n}))')
                n_vias += 1
            zd = fan_z[1] - fan_drop.get(net, 0.0)
            items += path([(xt, z_hi), (xt, zd), (xb, fan_z[0]), (xb, z_lo)], w, n)
            n_lanes += 1
            continue
        ba = lane.get("board_angles", {})
        for ang in lane["angles"]:
            x = X(_x_of(ang, r_out))
            # (2026-11-21) a per-board override (board_angles) drops this
            # angle's via at boards whose castellation it removed
            zs_a = sorted(sum(zmap[b]) / 2.0 for b in lane["boards"]
                          if b in zmap and ang in ba.get(b, lane["angles"]))
            for zc in zs_a:
                items.append(f'\t(via (at {x} {Y(zc)}) (size {VIA_PAD_MM}) '
                             f'(drill {CAST_DRILL_MM}) (layers "F.Cu" "B.Cu") (net {n}))')
                n_vias += 1
            if kind == "cone_exit" and zs:
                # runs up to the sleeve's nose rim → continues on the LDS cone
                items.append(f'\t(segment (start {x} {Y(zs[0])}) (end {x} {Y(H)}) '
                             f'(width {lane.get("width_mm", 0.2)}) (layer "F.Cu") (net {n}))')
                n_lanes += 1
            elif kind in ("crown", "crown_top") and zs:
                # (2026-11-19) compute edge castellation → up the sleeve's outer
                # face over the Al ring, jogging to its tooth angle (order-
                # preserving fan, never under a plate), then straight onto the
                # crown base, where the groove floor continues on the cone.
                # Straight UP out of compute's via row first; the fan runs over
                # the anchor band (nothing else there), the jog takes the short
                # way over the seam.
                from smash.export import nose_interface as NI
                # (2026-11-20) a merged power run: the diagonal ends at the mean of
                # its teeth, a bar spans them, one riser per tooth (NI.fan_slots
                # checked this geometry for clearance)
                w = lane.get("width_mm", 0.2)
                xr = _x_of(ang, r_out)
                xts = [_x_of(a, r_out) for a in lane.get("tooth_angles", [lane["tooth_angle"]])]
                xts = [xts[0] + ((xt - xts[0] + W / 2) % W - W / 2) for xt in xts]   # unwrap
                xm = (sum(xts) / len(xts)) % W
                xts = sorted(xt % W for xt in xts) if max(xts) - min(xts) < W / 2 else xts
                z_top = _crown_z(boards, chain, zmap)
                z_ring = z_top - NI.CROWN_STACK_MM
                z_base = z_ring + NI.CROWN_BASE_MM
                zc_top = max(z1 for b_, (z0_, z1) in zmap.items() if b_ in lane["boards"])
                # (2026-11-20) diagonal from just over the compute via to just
                # under the crown floor (snap ring: the ring alone is too short)
                zf0 = zs[0] + NI.FAN_MARGIN_BOTTOM_MM
                zf1 = z_base - NI.FAN_MARGIN_MM
                zf0 += lane.get("fan_lift_mm", 0.0)       # stagger (fan_slots)
                items += path([(xr, zs[0]), (xr, zf0), (xm, zf1)], w, n)
                if len(xts) > 1:                  # tooth to tooth (path wraps the seam)
                    items += path([(xt % W, zf1) for xt in xts], w, n)
                for xt in (x % W for x in xts):
                    items += path([(xt, zf1), (xt, z_base)], w, n)
                n_lanes += 1
            elif kind in ("signal", "power", "gnd_guard") and lane.get("aft_cap") and zs:
                # (2026-11-19) continues past the aft board to the aft rim (z 0)
                # and on over the aft_end_cap's skin into its crown groove
                w = lane.get("width_mm", 0.2)
                items.append(f'\t(segment (start {x} {Y(0.0)}) (end {x} {Y(zs[-1])}) '
                             f'(width {w}) (layer "F.Cu") (net {n}))')
                n_lanes += 1
            elif kind in ("signal", "power", "gnd_guard") and len(zs) >= 2:
                w = lane.get("width_mm", 0.2)
                items.append(f'\t(segment (start {x} {Y(zs[0])}) (end {x} {Y(zs[-1])}) '
                             f'(width {w}) (layer "F.Cu") (net {n}))')
                n_lanes += 1

    # Slot antennas: GND patch copper (pre-filled zones), CPW strips, the
    # feed vias the contract lacks (S4: reserved, no board castellation yet).
    cells, strips, feeds, labels, slot_rects, windows = _antenna_copper(boards, zmap, H)
    g_ant = nid("GND")
    for x0, z0, x1, z1 in cells:
        poly = (f'(xy {X(x0)} {Y(z1)}) (xy {X(x1)} {Y(z1)}) '
                f'(xy {X(x1)} {Y(z0)}) (xy {X(x0)} {Y(z0)})')
        items.append(f'\t(zone (net {g_ant}) (net_name "GND") (layer "F.Cu") (hatch none 0.5) '
                     f'(connect_pads yes (clearance 0.2)) (min_thickness 0.1) (fill yes) '
                     f'(polygon (pts {poly})) (filled_polygon (layer "F.Cu") (pts {poly})))')
    for net, (x0, z0, x1, z1) in strips:
        n = nid(net)
        xc = 0.5 * (x0 + x1)
        items.append(f'\t(segment (start {X(xc)} {Y(z0)}) (end {X(xc)} {Y(z1)}) '
                     f'(width {round(x1 - x0, 3)}) (layer "F.Cu") (net {n}))')
    for net, xf, zb in feeds:
        if net not in lanes:
            items.append(f'\t(via (at {X(xf)} {Y(zb)}) (size {VIA_PAD_MM}) (drill {CAST_DRILL_MM}) '
                         f'(layers "F.Cu" "B.Cu") (net {nid(net)}))')
            items.append(f'\t(gr_text "{net} feed - RESERVED (no board castellation yet)" '
                         f'(at {X(xf)} {Y(zb) - 1.2:.2f}) (layer "F.SilkS") '
                         f'(effects (font (size 0.5 0.5) (thickness 0.08))))')
    for x0, z0, x1, z1 in slot_rects:
        for (xa, za, xb, zb) in ((x0, z0, x1, z0), (x1, z0, x1, z1), (x1, z1, x0, z1), (x0, z1, x0, z0)):
            items.append(f'\t(gr_line (start {X(xa)} {Y(za)}) (end {X(xb)} {Y(zb)}) '
                         f'(stroke (width 0.05) (type solid)) (layer "F.SilkS"))')
    for text, xm, zl in labels:
        items.append(f'\t(gr_text "{text}" (at {X(xm)} {Y(zl):.2f}) (layer "F.SilkS") '
                     f'(effects (font (size 0.7 0.7) (thickness 0.1))))')
    ants = labels

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
    # (2026-11-18) One-piece cup: the deep bore can't be lasered, so the inner
    # GND plane is NOT emitted (the antenna sector loses its inner ground —
    # re-simulate). Kept behind INNER_FACE_LASERABLE for a half-shell sleeve.
    if INNER_FACE_LASERABLE:
        items.append(
            f'\t(zone (net {g}) (net_name "GND") (layer "B.Cu") (hatch edge 0.5) '
            f'(connect_pads yes (clearance 0.2)) (min_thickness 0.2) '
            f'(fill yes (thermal_gap 0.3) (thermal_bridge_width 0.3)) '
            f'(polygon (pts (xy {X(gx0)} {Y(H - 0.5)}) (xy {X(gx1)} {Y(H - 0.5)}) '
            f'(xy {X(gx1)} {Y(0.5)}) (xy {X(gx0)} {Y(0.5)}))) ' + " ".join(fills) + ')')

    # ── Plug ring ──
    plug = contract.get("plug", [])
    ab = contract.get("aft_board")
    zf = sum(zmap[ab]) / 2.0 if ab in zmap else 0.0
    hw = r_out * math.radians(SEAM_HALF_WIDTH_DEG) + 0.6
    halves = [(hw, W / 2 - hw), (W / 2 + hw, W - hw)]
    placed = []                                     # (entry, cx, px, row)
    per_half = [sum(1 for e in plug if (_x_of(e["angle"], r_out) < W / 2) == (lo < W / 2))
                for lo, _hi in halves]
    pitch = min((hi - lo) / max(n_, 1) for (lo, hi), n_ in zip(halves, per_half))
    PLUG_PAD_W_MM = pitch - PLUG_PAD_GAP_MM
    for lo, hi in halves:
        es = sorted((e for e in plug
                     if (_x_of(e["angle"], r_out) < W / 2) == (lo < W / 2)),
                    key=lambda e: _x_of(e["angle"], r_out))
        if not es:
            continue
        x0 = (lo + hi) / 2 - pitch * len(es) / 2
        for i, e in enumerate(es):
            placed.append((e, _x_of(e["angle"], r_out), x0 + pitch * (i + 0.5), 0))
    # levels: right-movers — the left one jogs LOWER; left-movers mirrored.
    depth = {}
    for sgn in (1, -1):
        movers = [t for t in placed if sgn * (t[2] - t[1]) > 1e-6]
        movers.sort(key=lambda t: -sgn * t[1])        # process the far end first
        done = []
        for t in movers:
            ia = sorted((t[1], t[2]))
            d_ = 1 + max([depth[id(u)] for u in done
                          if not (sorted((u[1], u[2]))[1] < ia[0] - 0.3
                                  or sorted((u[1], u[2]))[0] > ia[1] + 0.3)] or [0])
            depth[id(t)] = d_
            done.append(t)
    n_lv = max(depth.values() or [0])
    z_top = -0.6
    za1 = z_top - (n_lv + 1) * PLUG_LEVEL_STEP_MM - PLUG_LABEL_BAND_MM
    rows = [(za1, za1 - PLUG_PAD_H_MM)]
    ring_bottom = rows[0][1]                         # pads run to the aft edge
    if not plug:
        ring_bottom = 0.0                            # no plug ring
    n_plug = 0
    gbox = {}
    for t in placed:
        e, cx, px, row = t
        n = nid(e["net"])
        xc, xp = X(cx), X(px)
        items.append(f'\t(via (at {xc} {Y(zf)}) (size {VIA_PAD_MM}) (drill {CAST_DRILL_MM}) '
                     f'(layers "F.Cu" "B.Cu") (net {n}))')
        zl = z_top - depth.get(id(t), 0) * PLUG_LEVEL_STEP_MM
        pts = [(xc, Y(zf)), (xc, Y(zl)), (xp, Y(zl)), (xp, Y(rows[row][0]))]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if (x1, y1) != (x2, y2):
                items.append(f'\t(segment (start {x1} {y1}) (end {x2} {y2}) '
                             f'(width {PLUG_TRACE_MM}) (layer "F.Cu") (net {n}))')
        zt, zb = rows[row]
        pw = PLUG_PAD_W_MM / 2
        poly = (f'(xy {xp - pw:.3f} {Y(zt)}) (xy {xp + pw:.3f} {Y(zt)}) '
                f'(xy {xp + pw:.3f} {Y(zb)}) (xy {xp - pw:.3f} {Y(zb)})')
        items.append(f'\t(zone (net {n}) (net_name "{e["net"]}") (layer "F.Cu") (hatch none 0.5) '
                     f'(connect_pads yes (clearance 0.15)) (min_thickness 0.1) (fill yes) '
                     f'(polygon (pts {poly})) (filled_polygon (layer "F.Cu") (pts {poly})))')
        square = e["ref"].endswith("_0") or e["ref"] in ("P_ACT_WIRE_0",)
        short = {"P_ACTIVATE_COMMON": "COM", "TP_PARACHUTE_CUTTER_SET": "SET",
                 "TP_ACT_CONFIRM": "CONF", "TP_SPI_CS_FIN": "CS"}.get(
            e["ref"], e["ref"].replace("TP_", "").replace("P_ACT_WIRE_", "W").replace("P_ACT_COL_", "C")
            .replace("SPI_", "").replace("I2C_", "").replace("JUMP_", "J")
            .replace("MP25_", "").replace("GPIO_", "IO").replace("FIN", "F")
            .replace("BAT_", "").replace("CAN_", "CAN").replace("HALL_", "H"))
        items.append(f'\t(gr_text "{short}" '
                     f'(at {xp:.3f} {Y(zt + 1.2):.2f} 90) (layer "F.SilkS") '
                     f'(effects (font (size 0.45 0.45) (thickness 0.07))))')
        x0g, x1g = gbox.get(e["group"], (xp, xp))
        gbox[e["group"]] = (min(x0g, xp), max(x1g, xp))
        n_plug += 1
    for gi, (label, (x0g, x1g)) in enumerate(gbox.items()):
        bx0, bx1 = x0g - PLUG_PAD_W_MM / 2 - 0.3, x1g + PLUG_PAD_W_MM / 2 + 0.3
        by0, by1 = Y(rows[0][0] + 2.3), Y(rows[0][0] + 0.15)
        for (xa, ya, xb, yb) in ((bx0, by0, bx1, by0), (bx1, by0, bx1, by1),
                                 (bx1, by1, bx0, by1), (bx0, by1, bx0, by0)):
            items.append(f'\t(gr_line (start {xa:.3f} {ya}) (end {xb:.3f} {yb}) '
                         f'(stroke (width 0.12) (type solid)) (layer "F.SilkS"))')
        items.append(f'\t(gr_text "{label}" (at {(bx0 + bx1) / 2:.3f} {by0 - 0.5 - 0.8 * (gi % 2):.2f}) '
                     f'(layer "F.SilkS") (effects (font (size 0.6 0.6) (thickness 0.09))))')
    if plug:
        items.append(f'\t(gr_line (start {X(0)} {Y(0)}) (end {X(W)} {Y(0)}) (stroke (width 0.3) (type solid)) (layer "F.SilkS"))')
    PLUG_H = -ring_bottom

    # Aluminium BEHIND the sleeve (battery holder, aft rings): outline bands
    # across the full width at their height, so antennas / lanes over metal
    # are visible. (Al = ground right behind the antenna copper: fine for a
    # patch / PIFA, kills a Yagi.)
    from smash.export.spacer_step import gap_kind, ring_open_sector, ring_spec
    metal = {}
    for n, (z0, z1) in zmap.items():
        if n in boards and boards[n].is_spacer and gap_kind(n) in ("battery_holder", "ring"):
            key = "battery_holder" if gap_kind(n) == "battery_holder" else n
            a, b_ = metal.get(key, (z0, z1))
            metal[key] = (min(a, z0), max(b_, z1))
    for key, (z0, z1) in metal.items():
        label = ("AL BATTERY HOLDER BEHIND (r 17.0, GND)" if key == "battery_holder"
                 else f"{ring_spec(key).label} BEHIND (r {ring_spec(key).r_in:g}-{ring_spec(key).r_out:g})"
                      + (f", OPEN {ring_open_sector(key)[0]:g}-{ring_open_sector(key)[1]:g} deg"
                         if ring_open_sector(key) else ""))
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
    items.append(f'\t(gr_text "ANTENNA SECTOR (slots on outer face; ' + ("inner GND cut behind them" if INNER_FACE_LASERABLE else "NO inner GND - one-piece cup") + ')" '
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
\t(gr_rect (start {X(0)} {Y(H)}) (end {X(W)} {Y(-PLUG_H)}) (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts"))
{body}
)
''')
    return {"path": out_path, "width_mm": W, "height_mm": H, "n_vias": n_vias,
            "n_lanes": n_lanes, "n_plug": n_plug, "n_antennas": len(ants), "r_out": r_out}


def write_sleeve_copper_step(boards: dict, chain: list, contract: dict,
                             out_path, thickness_mm: float = 0.03) -> dict:
    """Wrap the outer-face copper (lanes + slot-antenna patches / feeds) back onto the
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
        if lane.get("kind", "signal") not in ("signal", "power", "gnd_guard"):
            continue
        zs = sorted(sum(zmap[b]) / 2.0 for b in lane["boards"] if b in zmap)
        if len(zs) < 2:
            continue
        for ang in lane["angles"]:
            strip(ang, zs[0], zs[-1], lane.get("width_mm", 0.2))
    H = max(z1 for _z0, z1 in zmap.values())
    cells, strips, _feeds, _labels, _slots, _win = _antenna_copper(boards, zmap, H)
    theta0 = SEAM_ANGLES_DEG[0]
    for x0, z0, x1, z1 in cells + [r for _n, r in strips]:
        arc(theta0 + math.degrees(x0 / r_out), theta0 + math.degrees(x1 / r_out),
            0.5 * (z0 + z1), z1 - z0)
    asm = cq.Assembly()
    for k, b in enumerate(bodies):
        asm.add(b, name=f"cu{k}", color=cq.Color(0.85, 0.55, 0.2, 1.0))
    out_path = pathlib.Path(out_path)
    asm.export(str(out_path))
    return {"path": out_path, "n_bodies": len(bodies)}


def add_sleeve_schematic_parts(design, contract, connect) -> list:
    """Add the LDS sleeve to `design` as schematic parts (board_tag "sleeve"):
    J_SLEEVE — one pin per lane conductor, in UNROLLED order (x = R·θ from
    the 105° seam, as in sleeve_unrolled.kicad_pcb), each tied to its net;
    AE_<slot> — one per slot antenna in antenna_slots.SLOTS whose feed net exists (feed + GND).
    Meant for a schematic-only copy of the design. Returns the new refs."""
    from smash.state import Pin, Pad, Footprint
    r = contract["radius_mm"]
    items = []
    for key, lane in contract.get("lanes", {}).items():
        if lane.get("kind") == "antenna_feed":
            continue
        net = "GND" if lane.get("kind") == "gnd_plane" else lane.get("net", key)
        for a in lane["angles"]:
            items.append((_x_of(a, r), a, key, net, lane.get("kind", "signal")))
    items.sort()
    pins, pads = [], []
    for i, (x, a, key, _net, kind) in enumerate(items, 1):
        pins.append(Pin(num=str(i), name=f"{key}@{a:g}deg", type="passive",
                        note=f"sleeve {kind} lane, x={x:.2f} mm on the unroll"))
        pads.append(Pad(num=str(i), position_mm=(round(x, 3), 0.0), size_mm=(0.3, 0.3),
                        shape="rect", layer="F.Cu"))
    W = 2 * math.pi * r
    fp = Footprint(name="LDS_sleeve_unrolled", package_class="LDS sleeve (unrolled)",
                   pads=pads, size_mm=(W, 1.0), height_mm=0.0, source="project")
    sl = design.add_chip(ref="J_SLEEVE", board_tag="sleeve", manf="project",
                         manf_pn="LDS_SLEEVE", name="LDS_SLEEVE", value="LDS sleeve",
                         footprint=fp, pins=pins, weight_g=0.0, height_mm=0.0,
                         note="2D unroll of the LDS sleeve: one pin per lane conductor "
                              "(see sleeve/sleeve_unrolled.kicad_pcb)")
    for i, (_x, _a, _k, net, _kind) in enumerate(items, 1):
        connect(net, sl.pin(str(i)))
    refs = ["J_SLEEVE"]
    from smash.parts.antenna_slots import SLOTS
    for ref, feed, label in ((f"AE_{a.name}", a.net, a.label) for a in SLOTS):
        if feed not in contract.get("lanes", {}):
            continue
        afp = Footprint(name="sleeve_antenna", package_class="LDS antenna",
                        pads=[Pad(num="1", position_mm=(0, 0), size_mm=(0.5, 0.5), shape="rect", layer="F.Cu"),
                              Pad(num="2", position_mm=(1, 0), size_mm=(0.5, 0.5), shape="rect", layer="F.Cu")],
                        size_mm=(1, 1), height_mm=0.0, source="project")
        ae = design.add_chip(ref=ref, board_tag="sleeve", manf="project",
                             manf_pn="LDS_ANTENNA", name="LDS_ANTENNA", value=label,
                             footprint=afp, weight_g=0.0, height_mm=0.0,
                             pins=[Pin(num="1", name="FEED", type="passive"),
                                   Pin(num="2", name="GND", type="passive", note="slot patch GND (GND castellations)")],
                             note=f"{label}: printed arc slot in a GND copper patch on the sleeve outer face "
                                  "(smash.parts.antenna_slots), CPW-fed from its feed castellation")
        connect(feed, ae.pin("1")); connect("GND", ae.pin("2"))
        refs.append(ref)
    return refs


def merge_unrolled_sleeve_into_panel(sleeve_pcb, panel_pcb, gap_mm: float = 15.0) -> dict:
    """Append the 2D unroll (`sleeve_pcb`, written by write_unrolled_sleeve)
    to the stackup panel `panel_pcb`, placed below every existing item.
    Numeric net ids → the panel's named-net form; all coordinates shifted.
    Idempotent per panel write (the panel is regenerated each build)."""
    import re
    import pathlib
    sleeve_pcb, panel_pcb = pathlib.Path(sleeve_pcb), pathlib.Path(panel_pcb)
    s = sleeve_pcb.read_text()
    p = panel_pcb.read_text()
    nets = dict(re.findall(r'^\t\(net (\d+) "([^"]*)"\)', s, re.M))
    keep = ("gr_line", "gr_rect", "gr_text", "gr_poly", "gr_circle",
            "segment", "via", "zone")
    items = [ln for ln in s.splitlines()
             if ln.startswith("\t(") and ln[2:].split(" ", 1)[0] in keep]
    coord = re.compile(r'\((at|start|end|xy|center|mid) (-?[\d.]+) (-?[\d.]+)')
    ys = [float(m.group(3)) for m in coord.finditer(p)]
    xs = [float(m.group(2)) for m in coord.finditer(p)]
    sy = [float(m.group(3)) for ln in items for m in coord.finditer(ln)]
    sx = [float(m.group(2)) for ln in items for m in coord.finditer(ln)]
    dx = (min(xs) if xs else 0.0) - (min(sx) if sx else 0.0)
    dy = (max(ys) if ys else 0.0) + gap_mm - (min(sy) if sy else 0.0)

    def shift(m):
        return f"({m.group(1)} {float(m.group(2)) + dx:.4f} {float(m.group(3)) + dy:.4f}"

    out = []
    for ln in items:
        ln = coord.sub(shift, ln)
        ln = re.sub(r'\(net (\d+)\) \(net_name "[^"]*"\)',
                    lambda m: f'(net "{nets.get(m.group(1), "")}")', ln)
        ln = re.sub(r'\(net (\d+)\)', lambda m: f'(net "{nets.get(m.group(1), "")}")', ln)
        out.append(ln)
    title = (f'\t(gr_text "LDS CUP SLEEVE - 2D UNROLL, UNION OF ALL CONFIGS (outer face F.Cu)" '
             f'(at {min(sx) + dx:.4f} {min(sy) + dy - 4:.4f} 0) (layer "F.SilkS") '
             f'(effects (font (size 2 2) (thickness 0.3)) (justify left)))')
    body = p.rstrip()
    assert body.endswith(")")
    body = body[:-1].rstrip() + "\n" + "\n".join([title] + out) + "\n)\n"
    panel_pcb.write_text(body)
    return {"n_items": len(out), "offset_mm": (dx, dy)}
