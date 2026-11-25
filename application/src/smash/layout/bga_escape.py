"""Fine-pitch BGA escape (fan-out) under the NCAB fab rules.

Generates the copper that gets every used ball of a 0.5 mm-pitch BGA out of
its ball field, so the layout EE routes onward from stubs just outside the
courtyard (like the castellation escape stubs):

  * signal balls, outer rings first, escape on the OUTER layer of the BGA's
    face — 0.085 mm tracks inside the courtyard (one track between two
    balls), a 0.12 mm stub outside it;
  * balls that cannot escape on the outer layer drop through a via-in-pad
    (VIPPO) microvia to the plane layer below, step diagonally to a
    STAGGERED microvia in the channel centre between four balls (never
    stacked), and escape on the first inner signal layer;
  * GND balls: one VIPPO microvia each into the GND plane right below;
  * power balls: VIPPO + staggered microvia onto the inner signal layer,
    where the layout EE merges each rail into an island and drops it to
    the power plane (buried vias, never under a microvia).

Layer plan per face (smash.layout.netclasses): top → F.Cu / In1 GND /
In2 signal; bottom → B.Cu / In6 GND / In5 signal.

Router: 8-direction grid A* (0.025 mm grid, ball centres and channel
centres land on grid points) in the part's own frame, obstacles = other
nets' copper inflated by clearance + half widths. Output is in board-local
coordinates (rotation / bottom-face mirror applied).
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from smash.layout.placer.grid import rotate_point
from smash.state.routing.track import Track
from smash.state.routing.via import Via

GRID = 0.025
CLR = 0.075          # copper clearance (NCAB advanced)
MARGIN = 0.005       # grid-rounding guard (channel slack is 0.0075 with 0.25 mm lands at 0.5 mm pitch)
W_ESC = 0.085        # escape track inside the courtyard (one track between 0.25 mm lands)
W_OUT = 0.120        # stub outside the courtyard (preferred width)
STUB = 0.30          # stub length outside the courtyard
MV_DRILL = 0.15
MV_LAND = 0.25
TURN = 3.0           # A* turn penalty, in grid steps
NOTE = "bga-escape"

LAYERS = {"top": ("F.Cu", "In1.Cu", "In2.Cu"), "bottom": ("B.Cu", "In6.Cu", "In5.Cu")}
_DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


class _Field:
    """Obstacle bookkeeping on one grid, per layer."""

    def __init__(self, half_extent: float):
        n = int(round(2 * half_extent / GRID)) + 1
        self.L = half_extent
        self.n = n
        ax = np.linspace(-half_extent, half_extent, n)
        self.X, self.Y = np.meshgrid(ax, ax, indexing="ij")
        self.shapes: dict[str, list] = {}

    def add_disk(self, layer, net, c, r):
        self.shapes.setdefault(layer, []).append(("d", net, c, None, r))

    def add_seg(self, layer, net, a, b, half):
        self.shapes.setdefault(layer, []).append(("s", net, a, b, half))

    def ij(self, p):
        return (int(round((p[0] + self.L) / GRID)), int(round((p[1] + self.L) / GRID)))

    def xy(self, i, j):
        return (-self.L + i * GRID, -self.L + j * GRID)

    def blocked(self, layer, net, half) -> np.ndarray:
        m = np.zeros((self.n, self.n), dtype=bool)
        for kind, snet, a, b, sh in self.shapes.get(layer, []):
            if snet == net:
                continue
            r = sh + CLR + half + MARGIN
            if kind == "d":
                lo = self.ij((a[0] - r, a[1] - r)); hi = self.ij((a[0] + r, a[1] + r))
                sl = (slice(max(lo[0], 0), min(hi[0] + 1, self.n)), slice(max(lo[1], 0), min(hi[1] + 1, self.n)))
                m[sl] |= (self.X[sl] - a[0]) ** 2 + (self.Y[sl] - a[1]) ** 2 < r * r
            else:
                lo = self.ij((min(a[0], b[0]) - r, min(a[1], b[1]) - r))
                hi = self.ij((max(a[0], b[0]) + r, max(a[1], b[1]) + r))
                sl = (slice(max(lo[0], 0), min(hi[0] + 1, self.n)), slice(max(lo[1], 0), min(hi[1] + 1, self.n)))
                X, Y = self.X[sl], self.Y[sl]
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy
                t = np.clip(((X - a[0]) * dx + (Y - a[1]) * dy) / L2, 0, 1) if L2 > 0 else 0
                m[sl] |= (X - a[0] - t * dx) ** 2 + (Y - a[1] - t * dy) ** 2 < r * r
        return m


def _astar(field: _Field, blocked: np.ndarray, start, bound: float, prefer=None):
    """Grid A* from `start` to any cell with |x| or |y| ≥ bound (the stub
    end). Returns the path as local points or None."""
    si, sj = field.ij(start)
    bi = int(math.ceil((bound + field.L) / GRID)); bl = int(math.floor((-bound + field.L) / GRID))

    def h(i, j):
        d = min(bi - i, i - bl, bi - j, j - bl)
        return max(d, 0)

    def goal(i, j):
        return i >= bi or i <= bl or j >= bi or j <= bl

    blocked = blocked.copy()
    blocked[si, sj] = False
    best = {}
    heap = [(h(si, sj), 0.0, si, sj, -1)]
    parent = {}
    while heap:
        f, g, i, j, d = heapq.heappop(heap)
        key = (i, j, d)
        if best.get(key, math.inf) < g - 1e-9:
            continue
        if goal(i, j):
            path = [(i, j)]
            k = key
            while k in parent:
                k = parent[k]
                path.append((k[0], k[1]))
            return [field.xy(a, b) for a, b in reversed(path)]
        for nd, (di, dj) in enumerate(_DIRS):
            ni, nj = i + di, j + dj
            if not (0 <= ni < field.n and 0 <= nj < field.n) or blocked[ni, nj]:
                continue
            if di and dj and (blocked[i + di, j] or blocked[i, j + dj]):
                continue                          # no corner cutting
            step = 1.4142 if di and dj else 1.0
            ng = g + step + (TURN if d not in (-1, nd) else 0.0)
            if prefer is not None and (di, dj) == prefer:
                ng -= 0.05
            nkey = (ni, nj, nd)
            if ng < best.get(nkey, math.inf):
                best[nkey] = ng
                parent[nkey] = key
                heapq.heappush(heap, (ng + h(ni, nj), ng, ni, nj, nd))
    return None


def _simplify(pts):
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[k], pts[k + 1]
        if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-9:
            out.append(b)
    out.append(pts[-1])
    return out


def _clip_to_bound(path, bound):
    """Cut the path where it first crosses the boundary square; return
    (inside part ending on the boundary, unit outward direction)."""
    for k in range(1, len(path)):
        (x0, y0), (x1, y1) = path[k - 1], path[k]
        if max(abs(x1), abs(y1)) >= bound - 1e-9:
            # parametric crossing
            ts = []
            for c0, c1 in ((x0, x1), (y0, y1)):
                for s in (bound, -bound):
                    if (c1 - c0) and 0 <= (s - c0) / (c1 - c0) <= 1:
                        ts.append((s - c0) / (c1 - c0))
            t = min(ts) if ts else 1.0
            p = (x0 + t * (x1 - x0), y0 + t * (y1 - y0))
            L = math.hypot(x1 - x0, y1 - y0) or 1.0
            return path[:k] + [p], ((x1 - x0) / L, (y1 - y0) / L)
    return path, (0.0, 0.0)


def _to_world(pl, p):
    px, py = rotate_point(p, pl.rotation_deg)
    if pl.face == "bottom":
        px = -px
    return (pl.position_mm[0] + px, pl.position_mm[1] + py)


def _to_local(pl, p):
    qx, qy = p[0] - pl.position_mm[0], p[1] - pl.position_mm[1]
    if pl.face == "bottom":
        qx = -qx
    return rotate_point((qx, qy), -pl.rotation_deg)


def _board_obstacles(field, board, placement, layers, reach):
    """Every other part's pads on the BGA's face, and the board's existing
    tracks / vias on the escape layers, in the BGA's local frame."""
    outer, plane, inner = layers
    near = lambda p: max(abs(p[0]), abs(p[1])) <= reach
    for pl in getattr(board, "chip_placements", []) or []:
        if pl is placement or pl.item is placement.item:
            continue
        fp = getattr(pl.item, "footprint", None)
        if fp is None:
            continue
        nets = getattr(pl.item, "_escape_pin_net", {})
        for pad in fp.pads:
            w, h = (pad.size_mm or (0.0, 0.0))[:2]
            ox, oy = pad.position_mm
            a, b = ((ox - (w - h) / 2, oy), (ox + (w - h) / 2, oy)) if w >= h else \
                   ((ox, oy - (h - w) / 2), (ox, oy + (h - w) / 2))
            la, lb = _to_local(placement, _to_world(pl, a)), _to_local(placement, _to_world(pl, b))
            if not (near(la) or near(lb)):
                continue
            net = nets.get(str(pad.num), f"~{pl.item.ref}.{pad.num}")
            half = min(w, h) / 2 * 1.42                  # capsule covering the rect corners
            th = getattr(pad, "drill_mm", None)
            for L in ((outer, plane, inner) if th else ((outer,) if pl.face == placement.face else ())):
                field.add_seg(L, net, la, lb, half)
    for t in getattr(board, "tracks", []) or []:
        if t.layer in layers:
            pts = [_to_local(placement, q) for q in t.path]
            if any(near(q) for q in pts):
                for a, b in zip(pts, pts[1:]):
                    field.add_seg(t.layer, t.net, a, b, t.width_mm / 2)
    order = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "In5.Cu", "In6.Cu", "B.Cu"]
    for v in getattr(board, "vias", []) or []:
        c = _to_local(placement, v.position_mm)
        if not near(c):
            continue
        i0, i1 = sorted((order.index(v.from_layer), order.index(v.to_layer)))
        for L in layers:
            if i0 <= order.index(L) <= i1:
                field.add_disk(L, v.net, c, v.pad_diameter_mm / 2)


def escape_bga(chip, placement, pin_net: dict, *, board=None, ring_limit_outer: int = 99) -> dict:
    """Escape copper for one BGA. `pin_net`: {(ref, pin num): Net}.
    Returns {"tracks": [Track], "vias": [Via], "unrouted": [ball], "stats": {}}."""
    fp = chip.footprint
    face = placement.face
    outer, plane, inner = LAYERS[face]
    pads = {str(p.num): p for p in fp.pads}
    pins = {str(p.num): p for p in chip.pins}
    xs = sorted({round(p.position_mm[0], 3) for p in fp.pads})
    ys = sorted({round(p.position_mm[1], 3) for p in fp.pads})
    pitch = min(b - a for a, b in zip(xs, xs[1:]))
    pad_r = max(max(p.size_mm) for p in fp.pads) / 2
    if fp.courtyard:
        cx = [abs(q[0]) for q in fp.courtyard]; cy = [abs(q[1]) for q in fp.courtyard]
        bound = min(max(cx), max(cy))
    else:
        bound = max(xs[-1], ys[-1]) + pitch
    bound = max(bound, max(xs[-1], ys[-1]) + pad_r + 0.15)
    field = _Field(math.ceil((bound + STUB + 0.3) / GRID) * GRID)
    if board is not None:
        _board_obstacles(field, board, placement, LAYERS[face], field.L + 0.5)

    def ring(p):
        x, y = p.position_mm
        return int(round(min(x - xs[0], xs[-1] - x, y - ys[0], ys[-1] - y) / pitch))

    kind, netname = {}, {}
    for num, pad in pads.items():
        n = pin_net.get((chip.ref, num))
        if n is None:
            kind[num] = "nc"
            field.add_disk(outer, f"~nc.{num}", pad.position_mm, pad_r)   # still a copper pad
            continue
        netname[num] = n.name
        kind[num] = "gnd" if n.kind == "ground" else "pwr" if n.kind == "power" else "sig"
        field.add_disk(outer, n.name, pad.position_mm, pad_r)

    tracks, vias, unrouted = [], [], []

    def add_via(net, c, frm, to):
        vias.append((net, c, frm, to))
        for L in (frm, to):
            field.add_disk(L, net, c, MV_LAND / 2)

    def add_track(net, layer, path, width):
        for a, b in zip(path, path[1:]):
            field.add_seg(layer, net, a, b, width / 2)
        tracks.append((net, layer, width, path))

    for num, k in kind.items():                       # GND: VIPPO into the plane
        if k == "gnd":
            add_via(netname[num], pads[num].position_mm, outer, plane)

    inside_mask = (np.abs(field.X) < bound) & (np.abs(field.Y) < bound)

    def route(num, start, layer):
        """Escape at W_ESC inside the courtyard, continuing at W_OUT for
        STUB beyond it; both widths checked against every obstacle."""
        net = netname[num]
        blk = np.where(inside_mask, field.blocked(layer, net, W_ESC / 2),
                       field.blocked(layer, net, W_OUT / 2))
        x, y = start
        side = min(((bound - x, (1, 0)), (x + bound, (-1, 0)), (bound - y, (0, 1)), (y + bound, (0, -1))))[1]
        path = _astar(field, blk, start, bound + STUB, prefer=side)
        if path is None:
            return False
        path = _simplify(path)
        inside, _ = _clip_to_bound(path, bound)
        if len(inside) < 2:
            inside = [start, inside[-1]]
        add_track(net, layer, inside, W_ESC)
        rest = [inside[-1]] + [q for q in path if max(abs(q[0]), abs(q[1])) > bound + 1e-9]
        if len(rest) >= 2:
            add_track(net, layer, _simplify(rest), W_OUT)
        return True

    sig = sorted((n for n, k in kind.items() if k == "sig"), key=lambda n: ring(pads[n]))
    deferred = []
    for num in sig:                                   # outer layer, outer rings first
        if ring(pads[num]) > ring_limit_outer or not route(num, pads[num].position_mm, outer):
            deferred.append(num)

    used_diag = set()

    def stagger(num):
        """VIPPO + staggered microvia to the inner layer; returns the
        stagger point or None."""
        x, y = pads[num].position_mm
        cands = []
        for sx in (1, -1):
            for sy in (1, -1):
                q = (round(x + sx * pitch / 2, 4), round(y + sy * pitch / 2, 4))
                # prefer the diagonal toward the nearest side
                cands.append((-max(abs(q[0]), abs(q[1])), q))
        for _, q in sorted(cands):
            if q in used_diag:
                continue
            used_diag.add(q)
            net = netname[num]
            add_via(net, pads[num].position_mm, outer, plane)
            add_via(net, q, plane, inner)
            add_track(net, plane, [pads[num].position_mm, q], W_ESC)
            return q
        return None

    stag = {}
    for num in [n for n, k in kind.items() if k == "pwr"] + deferred:
        q = stagger(num)
        if q is None:
            unrouted.append(num)
        else:
            stag[num] = q
    for num in sorted(deferred, key=lambda n: ring(pads[n])):
        if num in stag and not route(num, stag[num], inner):
            unrouted.append(num)

    # local → board
    def tb(p):
        px, py = rotate_point(p, placement.rotation_deg)
        if face == "bottom":
            px = -px
        return (round(placement.position_mm[0] + px, 4), round(placement.position_mm[1] + py, 4))

    T = [Track(net=n, layer=L, width_mm=w, path=[tb(p) for p in path], note=NOTE)
         for n, L, w, path in tracks]
    V = [Via(net=n, position_mm=tb(c), drill_mm=MV_DRILL, pad_diameter_mm=MV_LAND,
             from_layer=f, to_layer=t, kind="micro", filled=True, note=NOTE)
         for n, c, f, t in vias]
    cnt = {k: sum(1 for v in kind.values() if v == k) for k in ("sig", "gnd", "pwr", "nc")}
    return {"tracks": T, "vias": V, "unrouted": sorted(set(unrouted)),
            "stats": dict(cnt, outer=len(sig) - len(deferred), inner=len(deferred) - len(
                [u for u in unrouted if u in deferred]), unrouted=len(set(unrouted)))}


def escape_board(d, boards, refs) -> dict:
    """Add escape copper for each chip ref (if placed) to its board."""
    pin_net = {}
    for n in d.nets:
        for r, p in n.pins:
            pin_net[(r, str(p))] = n
    out = {}
    for name, b in boards.items():
        for pl in getattr(b, "chip_placements", []) or []:
            ref = getattr(pl.item, "ref", None)
            if ref in refs:
                for opl in b.chip_placements:
                    oref = getattr(opl.item, "ref", None)
                    opl.item._escape_pin_net = {str(p.num): pin_net[(oref, str(p.num))].name
                                                for p in opl.item.pins if (oref, str(p.num)) in pin_net}
                r = escape_bga(pl.item, pl, pin_net, board=b)
                b.tracks.extend(r["tracks"]); b.vias.extend(r["vias"])
                out[ref] = dict(r["stats"], board=name, unrouted_balls=r["unrouted"])
    return out
