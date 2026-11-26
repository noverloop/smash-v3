"""Fine-pitch BGA escape (fan-out) under the NCAB fab rules.

Generates the copper that gets every used ball of a 0.5 mm-pitch BGA out of
its ball field, so the layout EE routes onward from stubs just outside the
courtyard (like the castellation escape stubs):

  * signal balls, outer rings first, escape on the OUTER layer of the BGA's
    face — 0.10 mm tracks at 0.10 mm clearance (one track between two balls
    where the land leaves a 0.30 mm gap), a 0.12 mm stub outside the courtyard;
  * balls that cannot escape on the outer layer DOG-BONE: a short stub on
    the outer layer to a microvia at the diagonal site between four balls
    (outer → plane layer), a jog back on the plane layer to the spot under
    the ball and a second, STAGGERED microvia there onto the first inner
    signal layer (never stacked), where they escape;
  * GND balls: one dog-bone microvia each into the GND plane;
  * power balls: dog-bone + staggered microvia onto the inner signal layer,
    where the layout EE merges each rail into an island and drops it to
    the power plane (buried vias, never under a microvia).
  No via in a ball pad (no VIPPO): nothing needs copper filling. One laser
  microvia size, 0.10 mm drill / 0.20 mm land. `vippo=True` keeps the older
  via-in-pad scheme (microvia in the ball pad, staggered one to the diagonal).

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
CLR = 0.10           # copper clearance inside the ball field (100/100 everywhere)
CLR_OUT = 0.10       # clearance outside the courtyard
BAND = 0.15          # inside the courtyard edge, also held at CLR_OUT (the DRC rule
                     # checks an outside stub against everything near it)
MARGIN = -1e-6       # float tolerance only: a 0.10 track in the 0.30 mm gap between 0.20 mm
                     # lands has zero slack, which the exact KiCad DRC confirms
W_ESC = 0.10         # escape track inside the courtyard (one track between 0.20 mm lands)
W_OUT = 0.125        # stub outside the courtyard (the board's 125 µm track class)
STUB = 0.30          # stub length outside the courtyard
MV_DRILL = 0.10          # one laser microvia everywhere: 0.10 mm drill / 0.20 mm land
MV_LAND = 0.20
MV_SMALL = (0.10, 0.20)
VIPPO = False             # dog-bone microvias (no via in pad) — cheap HDI, nothing filled
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

    def blocked(self, layer, net, half, clr=CLR) -> np.ndarray:
        m = np.zeros((self.n, self.n), dtype=bool)
        for kind, snet, a, b, sh in self.shapes.get(layer, []):
            if snet == net:
                continue
            r = sh + clr + half + MARGIN
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


def escape_bga(chip, placement, pin_net: dict, *, board=None, ring_limit_outer: int = 99,
               vippo: bool | None = None) -> dict:
    """Escape copper for one BGA (see the module docstring). Dog-bone mode
    tries two outer-layer rings where a track fits between balls, then one;
    the result with fewer unrouted balls wins."""
    vippo = VIPPO if vippo is None else vippo
    if vippo:
        return _escape_bga(chip, placement, pin_net, board=board,
                           ring_limit_outer=ring_limit_outer, vippo=True)
    best = None
    for tr in (2, 1):
        for spare_all in (False, True):
            r = _escape_bga(chip, placement, pin_net, board=board, ring_limit_outer=ring_limit_outer,
                            vippo=False, top_rings=tr, spare_all=spare_all)
            if best is None or len(r["unrouted"]) < len(best["unrouted"]):
                best = r
            if not best["unrouted"]:
                return best
    return best


def _escape_bga(chip, placement, pin_net: dict, *, board=None, ring_limit_outer: int = 99,
                vippo: bool = False, top_rings: int | None = None, spare_all: bool = False) -> dict:
    """`pin_net`: {(ref, pin num): Net}. Returns {"tracks": [Track],
    "vias": [Via], "unrouted": [ball], "why": {ball: reason}, "stats": {}}."""
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
    # microvia land that clears the four balls round a diagonal site
    diag = pitch / math.sqrt(2)
    mv_drill, mv_land = MV_DRILL, MV_LAND
    if not vippo and diag - pad_r - CLR - MARGIN < MV_LAND / 2:
        mv_drill, mv_land = MV_SMALL
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

    tracks, vias, unrouted, why = [], [], [], {}

    def add_via(net, c, frm, to):
        vias.append((net, c, frm, to))
        for L in (frm, to):
            field.add_disk(L, net, c, mv_land / 2)

    def add_track(net, layer, path, width):
        for a, b in zip(path, path[1:]):
            field.add_seg(layer, net, a, b, width / 2)
        tracks.append((net, layer, width, path))

    used_diag = set()

    def site_free(net, q, stub_from=None):
        """A microvia land at q (outer + plane layer), and the outer-layer stub
        to it, clear every other net's copper by CLR."""
        def dist(kind_, a, b, pt):
            if kind_ == "d":
                return math.hypot(pt[0] - a[0], pt[1] - a[1])
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L2)) if L2 else 0.0
            return math.hypot(pt[0] - a[0] - t * dx, pt[1] - a[1] - t * dy)
        checks = [(outer, q, mv_land / 2), (plane, q, mv_land / 2)]
        if stub_from is not None:                    # stub midpoint at W_ESC
            m = ((stub_from[0] + q[0]) / 2, (stub_from[1] + q[1]) / 2)
            checks.append((outer, m, W_ESC / 2))
        for L, pt, half in checks:
            for k_, snet, a, b, sh in field.shapes.get(L, []):
                if snet != net and dist(k_, a, b, pt) < sh + half + CLR + MARGIN:
                    return False
        return True

    def sites_of(num):
        x, y = pads[num].position_mm
        return [(round(x + sx * pitch / 2, 4), round(y + sy * pitch / 2, 4))
                for sx in (1, -1) for sy in (1, -1)]

    def place_dogbone(num, q):
        net = netname[num]
        used_diag.add(q)
        add_track(net, outer, [pads[num].position_mm, q], W_ESC)
        add_via(net, q, outer, plane)

    def dogbone(num):
        """Late dog-bone (a ball whose outer-layer escape failed): the first
        free diagonal site, centre-ward first."""
        x, y = pads[num].position_mm
        for q in sorted(sites_of(num), key=lambda q: max(abs(q[0]), abs(q[1]))):
            if q not in used_diag and site_free(netname[num], q, stub_from=(x, y)):
                place_dogbone(num, q)
                return q
        return None

    # rings that escape on the outer layer: two where one track fits between
    # two balls, else the outermost only
    gap = pitch - 2 * pad_r
    fits = gap >= W_ESC + 2 * CLR + 2 * MARGIN
    top_rings = min(top_rings or 2, 2 if fits else 1)
    site_of, reserve, surface = {}, {}, []
    if not vippo:
        # every ball that must drop (ground, power, inner signals) gets its own
        # diagonal site BEFORE the outer layer is routed: bipartite matching
        need = [n for n, k in kind.items()
                if k in ("gnd", "pwr") or (k == "sig" and ring(pads[n]) >= top_rings)]
        need.sort(key=lambda n: -ring(pads[n]))            # inner balls choose first
        cand = {n: [q for q in sorted(sites_of(n), key=lambda q: max(abs(q[0]), abs(q[1])))
                    if site_free(netname[n], q, stub_from=pads[n].position_mm)] for n in need}
        owner = {}

        def augment(n, seen):
            for q in cand[n]:
                if q in seen:
                    continue
                seen.add(q)
                if q not in owner or augment(owner[q], seen):
                    owner[q] = n
                    return True
            return False

        for n in need:
            augment(n, set())
        # balls on the outer layer's last ring keep a site in reserve (an
        # obstacle for other nets) in case their outer-layer escape fails
        # spare sites: the last outer-layer ring only, or (spare_all) every
        # outer-layer ring — the escape wrapper tries both
        lo = 0 if spare_all else top_rings - 1
        spare = sorted((n for n, k in kind.items() if k == "sig" and lo <= ring(pads[n]) < top_rings
                        and (spare_all or top_rings > 1)), key=lambda n: -ring(pads[n]))
        for n in spare:
            cand[n] = [q for q in sorted(sites_of(n), key=lambda q: max(abs(q[0]), abs(q[1])))
                       if site_free(netname[n], q, stub_from=pads[n].position_mm)]
            augment(n, set())
        site_of = {n: q for q, n in owner.items() if n in need}
        for q, n in owner.items():
            if n in spare:
                reserve[n] = q
                for L in (outer, plane):
                    field.add_disk(L, netname[n], q, mv_land / 2)
        for n in need:
            if n in site_of:
                place_dogbone(n, site_of[n])
            elif kind[n] in ("gnd", "pwr") and ring(pads[n]) == 0:
                surface.append(n)                     # outer-ring supply ball: leave on the outer layer
            else:
                unrouted.append(n); why[n] = "no site"

    if vippo:
        for num, k in kind.items():                   # GND: VIPPO into the plane
            if k == "gnd":
                add_via(netname[num], pads[num].position_mm, outer, plane)

    inside_mask = (np.abs(field.X) < bound) & (np.abs(field.Y) < bound)
    core_mask = (np.abs(field.X) < bound - BAND) & (np.abs(field.Y) < bound - BAND)

    def route(num, start, layer):
        """Escape at W_ESC inside the courtyard, continuing at W_OUT for
        STUB beyond it; both widths checked against every obstacle."""
        net = netname[num]
        blk = np.where(core_mask, field.blocked(layer, net, W_ESC / 2),
                       np.where(inside_mask, field.blocked(layer, net, W_ESC / 2, CLR_OUT),
                                field.blocked(layer, net, W_OUT / 2, CLR_OUT)))
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

    for num in surface:                               # supply balls escaping on the outer layer
        if not route(num, pads[num].position_mm, outer):
            unrouted.append(num); why[num] = "no site, no outer path"
    sig = sorted((n for n, k in kind.items() if k == "sig"), key=lambda n: ring(pads[n]))
    deferred = []
    for num in sig:                                   # outer layer, outer rings first
        if num in site_of or num in why:
            deferred.append(num)                      # dog-boned already
        elif ring(pads[num]) > ring_limit_outer or not route(num, pads[num].position_mm, outer):
            deferred.append(num)

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
    if vippo:
        for num in [n for n, k in kind.items() if k == "pwr"] + deferred:
            q = stagger(num)
            if q is None:
                unrouted.append(num)
            else:
                stag[num] = q
    else:
        # dog-bone (power already has its site) → jog back under the ball on the
        # plane layer → staggered microvia onto the inner layer
        for num in [n for n, k in kind.items() if k == "pwr"] + sorted(deferred, key=lambda n: -ring(pads[n])):
            if num in unrouted or num in surface:
                continue
            net = netname[num]
            q = site_of.get(num)
            if q is None and num in reserve:
                q = reserve[num]
                place_dogbone(num, q)
            elif q is None and num not in why:
                q = dogbone(num)
            p = pads[num].position_mm
            if q is None:
                unrouted.append(num); why[num] = "no site"
                continue
            add_track(net, plane, [q, p], W_ESC)
            add_via(net, p, plane, inner)
            stag[num] = p
    for num in sorted(deferred, key=lambda n: ring(pads[n])):
        if num in stag and not route(num, stag[num], inner):
            unrouted.append(num); why[num] = "no inner path"

    # local → board
    def tb(p):
        px, py = rotate_point(p, placement.rotation_deg)
        if face == "bottom":
            px = -px
        return (round(placement.position_mm[0] + px, 4), round(placement.position_mm[1] + py, 4))

    T = [Track(net=n, layer=L, width_mm=w, path=[tb(p) for p in path], note=NOTE)
         for n, L, w, path in tracks]
    V = [Via(net=n, position_mm=tb(c), drill_mm=mv_drill, pad_diameter_mm=mv_land,
             from_layer=f, to_layer=t, kind="micro", filled=vippo, note=NOTE)
         for n, c, f, t in vias]
    cnt = {k: sum(1 for v in kind.values() if v == k) for k in ("sig", "gnd", "pwr", "nc")}
    return {"tracks": T, "vias": V, "unrouted": sorted(set(unrouted)), "why": why,
            "stats": dict(cnt, outer=len(sig) - len(deferred), inner=len(deferred) - len(
                [u for u in unrouted if u in deferred]), unrouted=len(set(unrouted)),
                          via="VIPPO" if vippo else f"dog-bone {mv_drill:g}/{mv_land:g}")}


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
                out[ref] = dict(r["stats"], board=name, unrouted_balls=r["unrouted"],
                                **({"why": r["why"]} if r["why"] else {}))
    return out



def escape_stub_end(board, net: str):
    """(end, unit direction, layer) of a net's BGA escape stub on `board`: the
    free end farthest from its own ball field, pointing away from the ball."""
    esc = [t for t in board.tracks if t.net == net and t.note == NOTE]
    if not esc:
        return None
    ends = [p for t in esc for p in (t.path[0], t.path[-1])]
    free = [p for p in ends if ends.count(p) == 1]
    f0 = free[0]
    pts = [p for t in board.tracks if t.note == NOTE for p in t.path
           if math.hypot(p[0] - f0[0], p[1] - f0[1]) < 8.0]           # this BGA's field only
    fc = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    e = max(free, key=lambda p: math.hypot(p[0] - fc[0], p[1] - fc[1]))
    seg = next(t for t in esc if e in (t.path[0], t.path[-1]))
    o = seg.path[0] if e == seg.path[-1] else seg.path[-1]
    L = math.hypot(e[0] - o[0], e[1] - o[1]) or 1.0
    return e, ((e[0] - o[0]) / L, (e[1] - o[1]) / L), seg.layer
