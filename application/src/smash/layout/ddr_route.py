"""DDR4 ↔ STM32MP25 inner-layer router for companion_compute (AN5724).

Routes the full MPU↔DRAM DDR4 interface as VIPPO fan-outs + length-matched
inner-layer traces:

  - **VIPPO** (via-in-pad, plated over): one filled+capped stacked-microvia
    column in every DDR ball pad of both BGAs — drill 0.15 / pad 0.25 mm
    (DesignRules micro_min_*). Data stacks span F.Cu→In3.Cu (3 laser
    levels), A/C stacks F.Cu→In4.Cu (4 levels). No dog-bones, no F.Cu
    escapes.
  - **AN5724 §6.5 stack** (the six-layer allocation for the VFBGA361),
    mapped onto the top of the 20L buildup: **In1.Cu = data** (DQ/DM/
    DQS, referenced to the unified In2 GND plane), **In3.Cu = A/C**
    (+ CK and the slow nets — GND above and below, a true stripline),
    In4/In5 = the embedded-cap GND/VDD_DDR pair playing the template's
    L4/L5 planes. Depth overflow (In1↔In3) is the escape hatch when a
    net's template layer is unroutable.
  - Everything sits ABOVE the (shortened) central Cu coin — it caps at
    z=2.35 mm, below In5's underside at 2.472 mm, so the coin polygon
    is not an x-y routing obstacle (see smash_evb_v1.py).

Clearance regimes (AN5724 §6.1):
  - inside a BGA ball field the S-3S rule is waived → 0.075 mm clearance
    (NCAB-Advanced HDI), which is exactly one 0.10 mm trace through the
    0.25 mm gap between adjacent 0.25 mm via lands on the MPU's 0.5 mm
    grid;
  - everywhere else S-3S with S = 0.15 mm (the In2→In3 prepreg) → 0.45 mm
    edge-to-edge between different nets, and the same spacing between
    sections of the same trace inside a tuning pattern (§6.2).

Length matching (AN5724 §7.2/§7.3, STM32MP25 tolerances):
  - DQ/DM ↔ byte DQS mean: ±1.42 mm;  A/C ↔ CK mean: ±3.55 mm;
    DQS ↔ CK: ±12.07 mm. Totals include the MPU package-internal length
    per ball (vendored ST table, smash/data/mp25_al_ddr4_pkg_lengths.json
    — STM32MP25xxAL / VFBGA-361 = our DAL3). The DRAM package and the
    (group-uniform) via-stack depth are excluded: both cancel inside a
    match group.
  - Tuning is **switchback-only** (§6.2: switchback over serpentine —
    no meanders): the stair-step Z-detour from the archived mini-router,
    re-parameterised to h = p = 0.55 mm (0.45 mm section gap + trace).
    The reference pair (DQS per byte, CK for A/C) is tuned UP to the
    longest natural member first, then every member is tuned to the
    reference's *achieved* length, so residuals stay inside tolerance
    even with the 4h ≈ 2.2 mm minimum-insertable-excess granularity.
  - Diff pairs: constant 0.15 mm edge gap (≈100 Ω with 0.10 mm traces in
    this buildup), no intra-pair equalization (§6.2) — the T leg is the
    grid-routed reference polyline, the C leg a constant-offset copy
    (corner deltas cancel on balanced turns; the residual skew is
    reported). BGA breakout stubs are exempt, as on every DDR layout.

Routing engine: sequential A* on a 0.05 mm lattice (ball centres and the
half-pitch channels are both lattice points), 4-direction states with a
turn penalty so paths come out as long straight Manhattan runs the
switchback inserter can use. Obstacles are kept as a stamp registry and
rasterised into per-layer/per-rule boolean grids; a net's own via lands
are carved out (and exactly recomputed) around its endpoints. After
routing, an exact (grid-free) audit checks pairwise clearances and the
AN5724 length groups; `route_companion_ddr` raises on hard violations
unless `strict=False`.

STATUS — work in progress (run `tools/route_ddr.py --lax` for the live
report). What converges today: VIPPO via fields for all 52 nets; all
three diff pairs (CK, DQS0, DQS1) route end-to-end as constant-gap
offset pairs with switchback tuning and ~1.3-1.8 mm reported skew; the
A/C remap + planar DQ swizzle in the generator; the exact-capacity MPU
escape assignment; the audits. What does not yet: roughly thirty member
nets still deadlock on escape/corridor capacity interactions (the
escape resources are at exact capacity, and the residual conflicts
between escape order, boulevard lane order and switchback head-room
need either a final assignment pass on the DRAM side or rip-up/retry).
Because of that, this router is NOT wired into the default generator
pipeline — `tools/route_ddr.py` is the entry point while it matures.

Frames: everything here is board-local, math-y-up — the same convention
as `Pad.position_mm` / `Placement.position_mm` / `Track` / `Via`.
"""
from __future__ import annotations

import dataclasses
import heapq
import json
import math
import os
import time
import pathlib
import re

import numpy as np

from smash.export._common import _strip_ball_prefix
from smash.state.routing.track import Track
from smash.state.routing.via import Via

# ── geometry constants ────────────────────────────────────────────────
# AN5724 §6.5 — the six-layer allocation for the VFBGA361, mapped onto
# the top of companion_compute's stack (see smash_evb_v1.py): In1 =
# DATA (over the In2 GND plane), In3 = A/C (GND above and below — a
# true stripline), In4/In5 = the embedded-cap GND/VDD_DDR pair playing
# the template's L4/L5 planes. In2 is a plane, NOT a routing level —
# the routing ladder is (F.Cu, In1, In3, In4) in PHYSICAL top-down
# order. F.Cu is the LAST-RESORT overflow (placements are final, so
# the placed components' pads are modelled as keep-outs; a net routed
# on the surface needs NO via at all — the balls connect directly,
# exactly like the reference's TOP-layer data). In4 is the overflow
# level the 2.0 mm coin frees (referenced to the In5 cap-pair GND
# below). A VIPPO stack descends only as deep as its net's level
# (surface = none, data = ONE laser level, A/C = three, overflow =
# four), so shallow nets gate nothing below them.
L_LEVELS = ("F.Cu", "In1.Cu", "In3.Cu", "In4.Cu", "In5.Cu")

TRACE_W = 0.10                  # mm — AN5724 §6.3 55 Ω class in this buildup
CLR_FIELD = 0.075               # mm — below-BGA waiver (§6.1)
CLR_OPEN = 0.30                 # mm — S-2S, S = 0.15 prepreg. §6.1 wants
                                #      S-3S "if more space is available";
                                #      22+30 nets across a 6.3 mm corridor
                                #      is exactly the case where it isn't,
                                #      and §6.1 names S-2S as the fallback
                                #      to prefer over S-1S. The audit
                                #      reports S-2S→S-3S shortfalls as
                                #      advisories, not violations.
VIA_DRILL = 0.15                # mm — stacked laser microvia, filled+capped
VIA_PAD = 0.25                  # mm — land; 0.05 annular (micro_min_annular)
DIFF_GAP = 0.15                 # mm edge-to-edge → 0.25 centre-to-centre
SELF_TOUCH = 0.11               # mm — same-net centreline floor: below
                                #      TRACE_W the copper edges MERGE and the
                                #      meander/staircase is shorted out (the
                                #      length report becomes fiction). The
                                #      reference stubs run 0.127 same-net
                                #      internally — legal, real length.
NPTH_CLEAR = 0.30               # mm — copper keep-back from NPTH drill
                                #      walls (potting holes); drill wander
                                #      alone eats ~0.1, so the trace-class
                                #      0.075 is NOT a hole clearance
FIELD_MARGIN = 0.40             # mm — ball-extent inflation that still uses
                                #      the BGA waiver clearances
EDGE_KEEPIN = 0.50              # mm — stay this far inside the board edge

GRID = 0.05                     # mm — lattice pitch (ball + channel aligned)
TURN_COST = 40                  # cells — 2 mm equivalent per 90° corner
H_WEIGHT = 1.06                 # weighted-A* inflation (audited anyway)

SB_H = 0.55                     # mm — switchback floor/pitch (§6.2 S-3S
                                #      inside the pattern: 0.45 gap + trace)
SB_MARGIN = 1.0                 # mm — keep-back from segment ends
SB_MIN_EXCESS = 4 * SB_H        # mm — smallest insertable extra length

TOL_BYTE = 1.42                 # mm — DQ/DM vs byte DQS (AN5724 §7.2, MP25)
TOL_AC = 3.55                   # mm — A/C vs CK (§7.3)
TOL_DQS_CK = 12.07              # mm — DQS vs CK (§7.2)

_PKG_JSON = (pathlib.Path(__file__).resolve().parents[1]
             / "data" / "mp25_al_ddr4_pkg_lengths.json")
_REF_JSON = (pathlib.Path(__file__).resolve().parents[1]
             / "data" / "mp25_al_ddr4_ref_escapes.json")

_NOTE = "ddr4-route"            # tag on emitted Track/Via for idempotency

# ── net classification ────────────────────────────────────────────────
_RE_DATA0 = re.compile(r"^DDR4_(DQ[0-7]|DM0_N|DQS0_[TC])$")
_RE_DATA1 = re.compile(r"^DDR4_(DQ(?:[89]|1[0-5])|DM1_N|DQS1_[TC])$")
_RE_AC = re.compile(
    r"^DDR4_(A\d+|BA[01]|BG0|ACT_N|RAS_N_A16|CAS_N_A15|WE_N_A14"
    r"|CKE|CS_N|ODT|CK_[TC])$")
_RE_MISC = re.compile(r"^DDR4_(RESET_N|VREFCA|ALERT_N)$")

PAIRS = {                       # pair name → (T net, C net)
    "DQS0": ("DDR4_DQS0_T", "DDR4_DQS0_C"),
    "DQS1": ("DDR4_DQS1_T", "DDR4_DQS1_C"),
    "CK":   ("DDR4_CK_T",   "DDR4_CK_C"),
}
_PAIR_NETS = {n for tc in PAIRS.values() for n in tc}


def _group_of(net: str) -> str | None:
    if _RE_DATA0.match(net):
        return "BYTE0"
    if _RE_DATA1.match(net):
        return "BYTE1"
    if _RE_AC.match(net):
        return "AC"
    if _RE_MISC.match(net):
        return "MISC"
    return None


def _levels_for(group: str):
    """Depth-overflow candidate order per match group — the §6.5
    template assignment first (data → In1, A/C → In3; their breakout
    bands are disjoint rows, but their CORRIDOR bundles fight when
    forced onto one level), the other level as the escape hatch."""
    if group in ("BYTE0", "BYTE1"):
        return ("In1.Cu", "In4.Cu", "In5.Cu", "In3.Cu", "F.Cu")
    return ("In3.Cu", "In4.Cu", "In5.Cu", "In1.Cu", "F.Cu")


# ── small geometry helpers ────────────────────────────────────────────
def _path_len(wp) -> float:
    return sum(abs(b[0] - a[0]) + abs(b[1] - a[1])
               for a, b in zip(wp, wp[1:]))


def _compress(wp):
    """Drop collinear interior points from a rectilinear waypoint list."""
    if len(wp) < 3:
        return list(wp)
    out = [wp[0]]
    for p in wp[1:-1]:
        a, b = out[-1], p
        # keep p unless previous→p→next is collinear with next point
        out.append(p)
        if len(out) >= 3:
            x0, y0 = out[-3]
            x1, y1 = out[-2]
            x2, y2 = out[-1]
            if (x0 == x1 == x2) or (y0 == y1 == y2):
                out.pop(-2)
    # final point
    out.append(wp[-1])
    if len(out) >= 3:
        x0, y0 = out[-3]
        x1, y1 = out[-2]
        x2, y2 = out[-1]
        if (x0 == x1 == x2) or (y0 == y1 == y2):
            out.pop(-2)
    return out


def _seg_seg_dist(p1, p2, q1, q2) -> float:
    """Min distance between two 2D segments (exact, for the audit)."""
    def d_point_seg(p, a, b):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 <= 1e-18:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def ccw(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

    d1, d2 = ccw(p1, p2, q1), ccw(p1, p2, q2)
    d3, d4 = ccw(q1, q2, p1), ccw(q1, q2, p2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0          # proper crossing
    return min(d_point_seg(q1, p1, p2), d_point_seg(q2, p1, p2),
               d_point_seg(p1, q1, q2), d_point_seg(p2, q1, q2))


def _self_ok(wp, min_gap, lo=None, hi=None, *, fiction_mm=None,
             max_touches=4):
    """Same-net self-spacing. Strict mode (fiction_mm None): no two
    non-adjacent segments closer than `min_gap` — used for freshly
    inserted switchback patterns (§6.2 spacing quality; lo/hi restrict
    to pairs involving the insertion). Lenient mode (fiction_mm set):
    a sub-gap touch SHORTS the polyline at that point, but the length
    fiction equals the BYPASSED length — the reference's pad-exit
    doglegs touch within ~0.2 mm of copper (harmless, the pad is one
    node anyway), while a meander crossed mid-pattern bypasses
    millimetres. So a touch is fatal only if it bypasses more than
    `fiction_mm`, or if touches pile up (dense staircase fusion =
    many micro-bypasses ≈ √2 length lie). Segments sharing an endpoint
    are adjacent."""
    segs = list(zip(wp, wp[1:]))
    m = len(segs)
    cum = [0.0]
    for (a, b) in segs:
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))

    def touch(i, j):
        (a1, b1), (a2, b2) = segs[i], segs[j]
        for u in (a1, b1):
            for v in (a2, b2):
                if abs(u[0] - v[0]) + abs(u[1] - v[1]) < 1e-6:
                    return True
        return False

    touches = 0
    for i in range(m):
        if lo is not None and not (lo <= i < hi):
            rng = range(max(i + 2, lo), min(m, hi))
        else:
            rng = range(i + 2, m)
        for j in rng:
            if touch(i, j):
                continue
            if _seg_seg_dist(*segs[i], *segs[j]) >= min_gap:
                continue
            if fiction_mm is None:
                return False
            bypass = cum[j] - cum[i + 1]
            if bypass > fiction_mm:
                return False
            touches += 1
            if touches > max_touches:
                return False
    return True


# ── switchback (ported from archive/tools/layout_gen/minirouter.py) ───
def _u_detour_candidates(wp, need_mm: float, *, d_min: float = 0.45,
                         d_max: float = 1.2, w: float = 0.80):
    """Yield U-detour insertions, longest host first: replace `w` of a
    straight run with a rectangular dip of depth d — adds EXACTLY 2d,
    d CONTINUOUS in [d_min, d_max]. This is the length-driven member
    primitive: switchback patterns quantize at ~3.1 mm and need tall
    in-pattern-spaced hosts; a U closes any residual ≥ 2·d_min and
    hosts on any straight ≥ w + 2·SB_MARGIN. Depth caps at 1.2: a
    deep dip barges into space LATER nets need (measured: d_max 3.0
    cost AC four in-tol members and squeezed DQ3 out entirely) — many
    shallow dips are neighbourly, one deep dip is not. Yields
    (new_wp, added, side, (ins_lo, ins_hi))."""
    if need_mm < 2 * d_min - 0.05:
        return
    d = min(max(need_mm / 2.0, d_min), d_max)
    segs = list(zip(wp, wp[1:]))
    hosts = []
    for i, (a, b) in enumerate(segs):
        if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) > 0.3:
            hosts.append((i, abs(a[1] - b[1]), "y"))
        elif abs(a[1] - b[1]) < 1e-9 and abs(a[0] - b[0]) > 0.3:
            hosts.append((i, abs(a[0] - b[0]), "x"))
    hosts.sort(key=lambda h2: -h2[1])
    for idx, seg_len, axis in hosts:
        if seg_len < w + 2 * SB_MARGIN:
            continue
        a, b = segs[idx]
        al, pe = (0, 1) if axis == "x" else (1, 0)
        lo, hi = min(a[al], b[al]), max(a[al], b[al])
        A = (lo + hi) / 2.0 - w / 2.0
        B = A + w
        base = a[pe]

        def pt(alv, pev):
            return (alv, pev) if axis == "x" else (pev, alv)

        for sgn in (+1, -1):
            yd = base + sgn * d
            inner = [pt(A, base), pt(A, yd), pt(B, yd), pt(B, base)]
            if b[al] < a[al]:
                inner = list(reversed(inner))
            new_wp = list(wp[:idx + 1]) + inner + list(wp[idx + 1:])
            yield new_wp, 2.0 * d, sgn, (idx, idx + 5)


def _accordion_candidates(wp, need_mm: float, *, d_min: float = 0.45,
                          d_max: float = 1.2):
    """ONE consolidated length structure per route: a multi-period
    serpentine at a single host — n periods of depth d add 2·n·d, the
    LAST period trimmed so the total closes `need_mm` exactly.
    Scattered structures fragment the corridor (every dip carries its
    own clearance perimeter — the measured mutual-hemming failure);
    one accordion concentrates the cost at one place and leaves the
    rest of the run clean. Yields (new_wp, added, side, ins)."""
    if need_mm < 2 * d_min - 0.05:
        return
    WT, GAP = 0.50, 0.50            # top width / inter-period gap
    segs = list(zip(wp, wp[1:]))
    hosts = []
    for i, (a, b) in enumerate(segs):
        if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) > 1.0:
            hosts.append((i, abs(a[1] - b[1]), "y"))
        elif abs(a[1] - b[1]) < 1e-9 and abs(a[0] - b[0]) > 1.0:
            hosts.append((i, abs(a[0] - b[0]), "x"))
    hosts.sort(key=lambda h2: -h2[1])
    for idx, seg_len, axis in hosts:
        room = seg_len - 2 * SB_MARGIN
        n_fit = int((room + GAP) // (WT + GAP))
        if n_fit < 1:
            continue
        n_need = max(1, int(math.ceil(need_mm / (2 * d_max))))
        n_use = min(n_need, n_fit)
        d_full = d_max if n_use > 1 or need_mm > 2 * d_max \
            else max(need_mm / 2.0, d_min)
        rem = need_mm - (n_use - 1) * 2 * d_full
        d_last = max(d_min, min(d_full, rem / 2.0))
        a, b = segs[idx]
        al, pe = (0, 1) if axis == "x" else (1, 0)
        lo, hi = min(a[al], b[al]), max(a[al], b[al])
        span = n_use * WT + (n_use - 1) * GAP
        A = (lo + hi) / 2.0 - span / 2.0
        base = a[pe]

        def pt(alv, pev):
            return (alv, pev) if axis == "x" else (pev, alv)

        for sgn in (+1, -1):
            inner = []
            x0 = A
            added = 0.0
            for k in range(n_use):
                d = d_last if k == n_use - 1 else d_full
                yd = base + sgn * d
                inner += [pt(x0, base), pt(x0, yd),
                          pt(x0 + WT, yd), pt(x0 + WT, base)]
                added += 2 * d
                x0 += WT + GAP
            if b[al] < a[al]:
                inner = list(reversed(inner))
            new_wp = list(wp[:idx + 1]) + inner + list(wp[idx + 1:])
            yield (new_wp, added, sgn,
                   (idx, idx + len(inner) + 1))


def _switchback_candidates(wp, extra_mm: float, *, h: float = SB_H):
    """Yield (new_wp, achieved_excess, side) candidates that insert one
    AN5724 §6.2 switchback (stair-step Z-detour) into a straight segment
    of `wp`, longest segment / +side first.

    Excess added = 4h + 2·run − 2p with p = h; both floors hold the
    §6.2 in-pattern S-3S spacing (0.45 mm gap at h = 0.55)."""
    if extra_mm <= 0.01:
        return
    p = h
    run = max(p, (extra_mm + 2 * p - 4 * h) / 2.0)

    segs = list(zip(wp, wp[1:]))
    candidates = []
    for i, (a, b) in enumerate(segs):
        if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) > 0.5:
            candidates.append((i, abs(a[1] - b[1]), "y"))
        elif abs(a[1] - b[1]) < 1e-9 and abs(a[0] - b[0]) > 0.5:
            candidates.append((i, abs(a[0] - b[0]), "x"))
    candidates.sort(key=lambda c: -c[1])

    for idx, seg_len, axis in candidates:
        a, b = segs[idx]
        room = seg_len - 2 * SB_MARGIN
        if room < p + 0.50:
            continue
        # floor at p + 0.45: the pattern's two return-runs sit
        # use_run − p apart, and below S-3S (0.45) the SHAPE ITSELF
        # violates the in-pattern spacing rule (at p + 0.1 they fused
        # at one trace width). Minimum honest insertion is therefore
        # 4h + 2(p+0.45) − 2p ≈ 3.1 mm — callers must check the
        # residual actually improves before accepting.
        use_run = max(min(run, room), p + 0.45)
        al, pe = (0, 1) if axis == "x" else (1, 0)
        lo, hi = min(a[al], b[al]), max(a[al], b[al])
        centre = (lo + hi) / 2.0
        A = centre - use_run / 2.0
        B = A + use_run
        Ap = A + p
        if not (A < Ap < B):
            continue
        base = a[pe]
        for s in (+1, -1):
            ph = base + s * h
            p2h = base + s * 2.0 * h

            def pt(alv, pev):
                return (alv, pev) if axis == "x" else (pev, alv)

            inner = [pt(A, base), pt(A, p2h), pt(B, p2h),
                     pt(B, ph), pt(Ap, ph), pt(Ap, base)]
            if b[al] < a[al]:
                inner = list(reversed(inner))
            new_wp = list(wp[:idx + 1]) + inner + list(wp[idx + 1:])
            achieved = 4 * h + 2 * use_run - 2 * p
            yield new_wp, achieved, s, (idx, idx + 7)


def _offset_leg(centerline, offset: float):
    """Constant-offset copy of a rectilinear polyline (the C leg of a
    pair, at `offset` to the LEFT of travel for offset > 0). A 90°
    corner's offset point is the intersection of the two offset lines
    (= corner + Li·o + Lo·o), so the gap is constant through every
    bend; corner length deltas cancel when left/right turns balance."""
    if len(centerline) < 2:
        return list(centerline)

    def dirof(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if abs(dx) >= abs(dy):
            return (1, 0) if dx > 0 else (-1, 0)
        return (0, 1) if dy > 0 else (0, -1)

    def left(d):
        return (-d[1], d[0])

    out = []
    n = len(centerline)
    for i, ptv in enumerate(centerline):
        if i == 0:
            Li = Lo = left(dirof(centerline[0], centerline[1]))
        elif i == n - 1:
            Li = Lo = left(dirof(centerline[-2], centerline[-1]))
        else:
            Li = left(dirof(centerline[i - 1], ptv))
            Lo = left(dirof(ptv, centerline[i + 1]))
        if Li == Lo:                        # straight (or endpoint)
            out.append((ptv[0] + Li[0] * offset, ptv[1] + Li[1] * offset))
        else:                               # 90° corner
            out.append((ptv[0] + (Li[0] + Lo[0]) * offset,
                        ptv[1] + (Li[1] + Lo[1]) * offset))
    return out


# ── stamp registry + boolean grids ────────────────────────────────────
@dataclasses.dataclass
class _Stamp:
    kind: str                   # "disk" | "capsule"
    geom: tuple                 # disk: (x, y); capsule: (x1, y1, x2, y2)
    half_w: float               # physical half-width of the obstacle
    owner: int                  # net index (-1 = static obstacle)
    pad: bool = False           # via land / hole: S-3S doesn't apply —
                                # field (DRC) clearance in every region
    infield: bool = False       # BGA-field copper (escape stubs): same —
                                # it must not cast S-2S shadows across
                                # the field boundary into the corridor


class _Grids:
    """Per-layer rasterised obstacle grids.

    Four boolean grids: {field, open} × {single, pair}. A cell is blocked
    for a candidate trace CENTRELINE when an obstacle's inflated radius
    covers the cell centre; inflation = half_w + clearance + TRACE_W/2
    (+ the pair's extra half-width on the pair grids). Field/open rule
    choice is by the candidate cell's `in_field` flag.
    """
    PAIR_EXTRA = (TRACE_W + DIFF_GAP)        # C leg at 0.25 centre offset

    def __init__(self, xmin, ymin, xmax, ymax, field_boxes):
        self.x0, self.y0 = xmin, ymin
        self.nx = int(round((xmax - xmin) / GRID)) + 1
        self.ny = int(round((ymax - ymin) / GRID)) + 1
        shape = (self.nx, self.ny)
        self.bf = np.zeros(shape, bool)      # field rules, single trace
        self.bo = np.zeros(shape, bool)      # open rules, single trace
        self.pf = np.zeros(shape, bool)      # field rules, pair body
        self.po = np.zeros(shape, bool)      # open rules, pair body
        self.in_field = np.zeros(shape, bool)
        self.collar = np.zeros(shape, bool)
        xs = xmin + GRID * np.arange(self.nx)
        ys = ymin + GRID * np.arange(self.ny)
        self._xs, self._ys = xs, ys
        for (fx1, fy1, fx2, fy2) in field_boxes:
            ix1, ix2 = self._ix(fx1), self._ix(fx2)
            iy1, iy2 = self._iy(fy1), self._iy(fy2)
            self.in_field[ix1:ix2 + 1, iy1:iy2 + 1] = True
            jx1, jx2 = self._ix(fx1 - 0.6), self._ix(fx2 + 0.6)
            jy1, jy2 = self._iy(fy1 - 0.6), self._iy(fy2 + 0.6)
            self.collar[jx1:jx2 + 1, jy1:jy2 + 1] = True
        self.collar &= ~self.in_field       # breakout ring round each box
        self.stamps: list[_Stamp] = []

    # index helpers (clamped)
    def _ix(self, x):
        return min(max(int(round((x - self.x0) / GRID)), 0), self.nx - 1)

    def _iy(self, y):
        return min(max(int(round((y - self.y0) / GRID)), 0), self.ny - 1)

    def cell_xy(self, ix, iy):
        return (self.x0 + ix * GRID, self.y0 + iy * GRID)

    def block_edge(self, cx, cy, r_keepin):
        """Block everything outside the keep-in circle on all grids."""
        self._keepin_r = r_keepin
        X = self._xs[:, None] - cx
        Y = self._ys[None, :] - cy
        far = (X * X + Y * Y) > (r_keepin * r_keepin)
        for g in (self.bf, self.bo, self.pf, self.po):
            g |= far

    # ---- rasterisation ------------------------------------------------
    def _radii(self, st):
        """(field, open, pair-field, pair-open) inflation radii for a
        stamp. Pads (via lands, holes) take the DRC clearance in every
        region — S-3S (§6.1) is a trace-to-trace coupling rule, not a
        pad rule — otherwise the BGA via columns at the field boundary
        would wall off the corridor entry."""
        if isinstance(st, _Stamp) and (st.pad or st.infield):
            r = st.half_w + CLR_FIELD + TRACE_W / 2
            return (r, r, r + self.PAIR_EXTRA, r + self.PAIR_EXTRA)
        half_w = st.half_w if isinstance(st, _Stamp) else st
        return (half_w + CLR_FIELD + TRACE_W / 2,
                half_w + CLR_OPEN + TRACE_W / 2,
                half_w + CLR_FIELD + TRACE_W / 2 + self.PAIR_EXTRA,
                half_w + CLR_OPEN + TRACE_W / 2 + self.PAIR_EXTRA)

    def _paint(self, stamp: _Stamp, grids=None):
        rf, ro, prf, pro = self._radii(stamp)
        targets = grids or [(self.bf, rf), (self.bo, ro),
                            (self.pf, prf), (self.po, pro)]
        for g, r in targets:
            self._mask_into(g, stamp, r)

    def _mask_into(self, g, stamp: _Stamp, r):
        if stamp.kind == "disk":
            x, y = stamp.geom
            x1, x2 = self._ix(x - r), self._ix(x + r)
            y1, y2 = self._iy(y - r), self._iy(y + r)
            X = self._xs[x1:x2 + 1, None] - x
            Y = self._ys[None, y1:y2 + 1] - y
            g[x1:x2 + 1, y1:y2 + 1] |= (X * X + Y * Y) < r * r - 1e-12
        else:
            ax, ay, bx, by = stamp.geom
            x1 = self._ix(min(ax, bx) - r); x2 = self._ix(max(ax, bx) + r)
            y1 = self._iy(min(ay, by) - r); y2 = self._iy(max(ay, by) + r)
            X = self._xs[x1:x2 + 1, None]
            Y = self._ys[None, y1:y2 + 1]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            if L2 < 1e-18:
                t = np.zeros_like(X * Y)
            else:
                t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0.0, 1.0)
            ddx = X - (ax + t * dx)
            ddy = Y - (ay + t * dy)
            g[x1:x2 + 1, y1:y2 + 1] |= (ddx * ddx + ddy * ddy) < r * r - 1e-12

    def add_disk(self, x, y, half_w, owner=-1):
        st = _Stamp("disk", (x, y), half_w, owner, pad=True)
        self.stamps.append(st)
        self._paint(st)

    def add_path(self, wp, half_w, owner):
        for a, b in zip(wp, wp[1:]):
            if a == b:
                continue
            mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            inf = bool(self.in_field[self._ix(mid[0]), self._iy(mid[1])])
            st = _Stamp("capsule", (a[0], a[1], b[0], b[1]), half_w,
                        owner, infield=inf)
            self.stamps.append(st)
            self._paint(st)

    def carve_owner(self, owner, around: list[tuple]):
        """Exactly recompute the grids in windows around `around` points
        with the stamps of `owner` (an int or a set of ints) excluded —
        frees a net's (or a diff pair's) own via lands before routing."""
        owners = {owner} if isinstance(owner, int) else set(owner)
        R = 1.0
        rmax = max(self._radii(VIA_PAD / 2))
        for (cx, cy) in around:
            x1, x2 = self._ix(cx - R), self._ix(cx + R)
            y1, y2 = self._iy(cy - R), self._iy(cy + R)
            for g in (self.bf, self.bo, self.pf, self.po):
                g[x1:x2 + 1, y1:y2 + 1] = False
            win = (cx - R - rmax, cy - R - rmax, cx + R + rmax, cy + R + rmax)
            for st in self.stamps:
                if st.owner in owners:
                    continue
                gx1, gy1, gx2, gy2 = self._bbox(st)
                if (gx2 < win[0] or gx1 > win[2]
                        or gy2 < win[1] or gy1 > win[3]):
                    continue
                # repaint only inside the carved window
                sub = self._window_painter(st, x1, x2, y1, y2)
                sub()

    def _window_painter(self, st: _Stamp, x1, x2, y1, y2):
        rf, ro, prf, pro = self._radii(st)

        def run():
            for g, r in ((self.bf, rf), (self.bo, ro),
                         (self.pf, prf), (self.po, pro)):
                self._mask_window(g, st, r, x1, x2, y1, y2)
        return run

    def _mask_window(self, g, st, r, x1, x2, y1, y2):
        X = self._xs[x1:x2 + 1, None]
        Y = self._ys[None, y1:y2 + 1]
        if st.kind == "disk":
            x, y = st.geom
            g[x1:x2 + 1, y1:y2 + 1] |= ((X - x) ** 2 + (Y - y) ** 2) < r * r - 1e-12
        else:
            ax, ay, bx, by = st.geom
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = (np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
                 if L2 > 1e-18 else np.zeros_like(X * Y))
            g[x1:x2 + 1, y1:y2 + 1] |= (((X - (ax + t * dx)) ** 2
                                         + (Y - (ay + t * dy)) ** 2)
                                        < r * r - 1e-12)

    def _bbox(self, st: _Stamp):
        rmax = max(self._radii(st))
        if st.kind == "disk":
            x, y = st.geom
            return (x - rmax, y - rmax, x + rmax, y + rmax)
        ax, ay, bx, by = st.geom
        return (min(ax, bx) - rmax, min(ay, by) - rmax,
                max(ax, bx) + rmax, max(ay, by) + rmax)

    # ---- queries -------------------------------------------------------
    def blocked(self, ix, iy, pair=False):
        """pair=False → single-trace rules; True/"open" → pair-width
        rules in the open corridor only. Inside the BGA fields AND in
        the 0.6 mm breakout collar around them the single rules apply —
        the C leg splits off in breakout territory, and the collar is
        where clustered escape-stub mouths live (pair inflation there
        seals them; the offset C body is path_clear-checked anyway)."""
        if self.in_field[ix, iy]:
            return self.pf[ix, iy] if pair is True else self.bf[ix, iy]
        if pair and not self.collar[ix, iy]:
            return self.po[ix, iy]
        return self.bo[ix, iy]

    def infield(self, ix, iy):
        return self.in_field[ix, iy]

    def incollar(self, ix, iy):
        return self.collar[ix, iy]

    def repaint_all(self):
        """Rebuild the rule grids from the stamp registry — used by the
        difficulty-restart teardown after bulk stamp removal."""
        for g in (self.bf, self.bo, self.pf, self.po):
            g[:] = False
        if getattr(self, "_keepin_r", None):
            self.block_edge(0.0, 0.0, self._keepin_r)
        for st in self.stamps:
            self._paint(st)

    def relaxed_view(self, field_owners, skip_owners, x1, y1, x2, y2):
        """A grid view for routing a diff-pair leg NEXT TO its partner:
        inside the window the partner's (`field_owners`) stamps are
        repainted at FIELD-rule radius — §6.2 exempts the pair gap from
        S-3S — and the leg's own (`skip_owners`) stamps are left out
        entirely (its via lands). Everything else keeps its normal
        rules. Exact recompute, window-limited."""
        return _GridView(self, field_owners, skip_owners, x1, y1, x2, y2)

    def path_clear(self, wp, pair=False):
        """Sample a candidate polyline at half-cell pitch against the
        grids (same test as A*, for switchback insertion)."""
        return _path_clear_on(self, wp, pair=pair)


class _GridView:
    """Window-limited overlay over _Grids where a chosen owner set is
    painted with FIELD radii everywhere (pair-gap exemption). Exposes the
    same interface _astar needs (_ix/_iy/cell_xy/blocked)."""

    def __init__(self, base: _Grids, field_owners, skip_owners,
                 x1, y1, x2, y2):
        self.base = base
        self._ix = base._ix
        self._iy = base._iy
        self.cell_xy = base.cell_xy
        ix1, ix2 = base._ix(x1), base._ix(x2)
        iy1, iy2 = base._iy(y1), base._iy(y2)
        self.win = (ix1, iy1, ix2, iy2)
        shape = (ix2 - ix1 + 1, iy2 - iy1 + 1)
        bf = np.zeros(shape, bool)
        bo = np.zeros(shape, bool)
        # recompute the window from scratch: non-owner stamps at normal
        # radii, owner stamps at field radii on BOTH rule grids
        sub = _Grids.__new__(_Grids)
        sub.x0 = base.x0 + ix1 * GRID
        sub.y0 = base.y0 + iy1 * GRID
        sub.nx, sub.ny = shape
        sub._xs = sub.x0 + GRID * np.arange(shape[0])
        sub._ys = sub.y0 + GRID * np.arange(shape[1])
        sub.bf, sub.bo = bf, bo
        sub.pf = np.zeros(shape, bool)      # unused by single-leg A*
        sub.po = np.zeros(shape, bool)
        wbb = (sub.x0 - 2, sub.y0 - 2,
               sub.x0 + shape[0] * GRID + 2, sub.y0 + shape[1] * GRID + 2)
        for st in base.stamps:
            if st.owner in skip_owners:
                continue                    # the leg's own via lands
            sx1, sy1, sx2, sy2 = base._bbox(st)
            if sx2 < wbb[0] or sx1 > wbb[2] or sy2 < wbb[1] or sy1 > wbb[3]:
                continue
            rf, ro, _, _ = base._radii(st)
            if st.owner in field_owners:
                ro = rf                     # pair-gap exemption
            sub._mask_into(bf, st, rf)
            sub._mask_into(bo, st, ro)
        # board-edge keep-in (block_edge isn't a stamp)
        X = sub._xs[:, None]
        Y = sub._ys[None, :]
        bf |= (X * X + Y * Y) > (base._keepin_r ** 2)
        bo |= (X * X + Y * Y) > (base._keepin_r ** 2)
        self._bf, self._bo = bf, bo

    def blocked(self, ix, iy, pair=False):
        ix1, iy1, ix2, iy2 = self.win
        if not (ix1 <= ix <= ix2 and iy1 <= iy <= iy2):
            return True
        if self.base.in_field[ix, iy]:
            return self._bf[ix - ix1, iy - iy1]
        return self._bo[ix - ix1, iy - iy1]

    def infield(self, ix, iy):
        return self.base.in_field[ix, iy]

    def incollar(self, ix, iy):
        return self.base.collar[ix, iy]


_TMP_OWNER = -7                 # sentinel for transient own-stub paint


def _clip_at_tip(poly, back=0.18):
    """Polyline ENDING at a search tip, shortened by `back` so the
    painted stub blocks everything except the cell the search leaves
    from."""
    out = list(poly)
    need = back
    while len(out) >= 2 and need > 0:
        ax, ay = out[-2]
        bx, by = out[-1]
        L = math.hypot(bx - ax, by - ay)
        if L <= need + 1e-9:
            out.pop()
            need -= L
        else:
            t = (L - need) / L
            out[-1] = (ax + (bx - ax) * t, ay + (by - ay) * t)
            need = 0.0
    return out if len(out) >= 2 else None


def _paint_own_stubs(gr, prefix, start, goal, tail, owner=_TMP_OWNER):
    """Temporarily paint a net's own prefix/tail as hard obstacles so
    its OWN A* cannot cross its future stub copper — the tip carve
    windows (and non-home levels, where stubs are never reserved) are
    otherwise blind spots that produce same-net crossings."""
    polys = []
    if prefix:
        c = _clip_at_tip(list(prefix) + [start])
        if c:
            polys.append(c)
    if tail:
        c = _clip_at_tip(([goal] + list(tail))[::-1])
        if c:
            polys.append(c)
    for poly in polys:
        gr.add_path(poly, TRACE_W / 2, owner)
    return polys


def _unpaint_tmp(gr, polys):
    if not polys:
        return
    gr.stamps = [st for st in gr.stamps if st.owner != _TMP_OWNER]
    pts = []
    for poly in polys:
        for (x, y) in poly:
            pts.append((x, y))
    gr.carve_owner(-999, pts)


def _path_clear_on(gridlike, wp, pair=False):
    """path_clear over anything exposing blocked()/_ix/_iy — the base
    grids and the pair-exempt views alike."""
    for a, b in zip(wp, wp[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(int(L / (GRID / 2)), 1)
        for k in range(n + 1):
            x = a[0] + (b[0] - a[0]) * k / n
            y = a[1] + (b[1] - a[1]) * k / n
            if gridlike.blocked(gridlike._ix(x), gridlike._iy(y),
                                pair=pair):
                return False
    return True


def _dejog(gridlike, wp, pair=False):
    """Remove sub-0.2 mm lateral jogs between collinear runs — the
    string-pull leaves them where an L was blocked, putting same-net
    copper edges at touching distance (length fiction texture) and
    poisoning every strict spacing window nearby. The shorter run
    shifts onto the other's line when the grid allows; the adjacent
    perpendicular corner absorbs the offset. Path endpoints are
    pinned (stub tips / ball attaches)."""
    wp = [tuple(q) for q in wp]
    changed = True
    while changed:
        changed = False
        for k in range(1, len(wp) - 2):
            A, B, C, D = wp[k - 1], wp[k], wp[k + 1], wp[k + 2]
            jx, jy = C[0] - B[0], C[1] - B[1]
            if not 1e-9 < math.hypot(jx, jy) <= 0.2:
                continue
            abx, aby = B[0] - A[0], B[1] - A[1]
            cdx, cdy = D[0] - C[0], D[1] - C[1]
            if abs(abx * cdy - aby * cdx) > 1e-9:
                continue                    # runs not collinear-parallel
            if abs(abx * jx + aby * jy) > 1e-9:
                continue                    # jog not perpendicular
            # option 1: shift the A-run onto CD's line (needs an
            # interior, perpendicular predecessor to absorb)
            if k >= 2:
                P = wp[k - 2]
                A2 = (A[0] + jx, A[1] + jy)
                cand = wp[:k - 1] + [A2, C] + wp[k + 2:]
                if _path_clear_on(gridlike, [P, A2, C], pair=pair):
                    wp = cand
                    changed = True
                    break
            # option 2: shift the D-run onto AB's line
            if k + 3 <= len(wp) - 1:
                Q = wp[k + 3]
                D2 = (D[0] - jx, D[1] - jy)
                cand = wp[:k + 1] + [D2] + wp[k + 3:]
                if _path_clear_on(gridlike, [B, D2, Q], pair=pair):
                    wp = cand
                    changed = True
                    break
    return _compress(wp)


def _rect_simplify(gridlike, wp, pair=False):
    """Greedy rectilinear string-pull: replace each staircase chunk
    with the longest clearance-checked L (either corner). Lattice A*
    micro-staircases are a CORRECTNESS problem, not cosmetics: rungs
    0.1 mm apart fuse into a diagonal copper blob, so the conducted
    length is ~√2 shorter than the reported Manhattan length. The
    simplification preserves Manhattan length exactly while making the
    copper honest — and gives switchbacks long straight hosts and pair
    offsets loop-free corners."""
    if len(wp) < 3:
        return list(wp)
    out = [wp[0]]
    i = 0
    N = len(wp)
    while i < N - 1:
        adv = i + 1
        piece = [wp[i + 1]]
        j = N - 1
        while j > i + 1:
            a, b = wp[i], wp[j]
            c1 = (b[0], a[1])
            c2 = (a[0], b[1])
            cand = None
            for c in (c1, c2):
                seg = [a] + ([c] if c != a and c != b else []) + [b]
                if _path_clear_on(gridlike, seg, pair=pair):
                    cand = seg[1:]
                    break
            if cand is not None:
                piece = cand
                adv = j
                break
            j -= 1
        out.extend(piece)
        i = adv
    return _dejog(gridlike, _compress(out), pair=pair)


# ── A* ────────────────────────────────────────────────────────────────
_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_LAST_FAIL = ""
_LAST_COST = 0.0
_DEBUG = bool(os.environ.get("SMASH_DDR_DEBUG"))


def _dir_index(a, b):
    """_DIRS index of the axis-aligned segment a→b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dy):
        return 0 if dx > 0 else 1
    return 2 if dy > 0 else 3


def _astar(grids: _Grids, start, goal, *, pair=False, margin=5.0,
           start_dir=None, goal_dir=None, guide=None, cong=None,
           max_pops=4_000_000, h_weight=None):
    """4-direction lattice A* with a per-turn penalty and a cross-track
    penalty pulling the path toward `guide` (a reference polyline from
    the structured route plan; defaults to the start→goal chord). The
    penalty is free within 0.45 mm — one lane — and grows beyond, so
    paths follow their planned boulevard/climb instead of L-shapes
    whose verticals wall off a corridor entrance for every later net.
    `start_dir` / `goal_dir` (an index into _DIRS) pin the leaving /
    arriving heading — used to splice pair legs onto their breakout
    connectors seamlessly.

    `cong=(present, history, w_present)` enables PathFinder-style
    negotiated congestion: `present` counts OTHER nets currently
    claiming each cell and `history` accumulates over iterations —
    both are soft costs, so contested cells stay usable but get
    progressively expensive until the nets negotiate themselves apart.
    Returns a compressed waypoint list, or None; the achieved g-cost is
    left in the module global `_LAST_COST` for level arbitration."""
    sx, sy = grids._ix(start[0]), grids._iy(start[1])
    gx, gy = grids._ix(goal[0]), grids._iy(goal[1])
    pts = [start] + list(guide or []) + [goal]
    x1 = grids._ix(min(p[0] for p in pts) - margin)
    x2 = grids._ix(max(p[0] for p in pts) + margin)
    y1 = grids._iy(min(p[1] for p in pts) - margin)
    y2 = grids._iy(max(p[1] for p in pts) + margin)

    segs = [(a, b) for a, b in zip(pts, pts[1:])
            if a != b]

    def xtrack(ix, iy):
        px, py = grids.cell_xy(ix, iy)
        d2 = math.inf
        for (ax, ay), (bx, by) in segs:
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = (((px - ax) * dx + (py - ay) * dy) / L2) if L2 else 0.0
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            ex, ey = px - (ax + t * dx), py - (ay + t * dy)
            d2 = min(d2, ex * ex + ey * ey)
        return 0.35 * max(0.0, math.sqrt(d2) - 0.45)

    hw = h_weight if h_weight is not None else H_WEIGHT

    def h(ix, iy):
        return (abs(ix - gx) + abs(iy - gy)) * hw

    openq = []
    best = {}
    if start_dir is None:
        heapq.heappush(openq, (h(sx, sy), 0.0, sx, sy, -1))
        best[(sx, sy, -1)] = 0.0
    else:
        heapq.heappush(openq, (h(sx, sy), 0.0, sx, sy, start_dir))
        best[(sx, sy, start_dir)] = 0.0
    came = {}
    pops = 0
    global _LAST_FAIL
    while openq:
        f, g, ix, iy, d = heapq.heappop(openq)
        if best.get((ix, iy, d), math.inf) < g - 1e-9:
            continue
        pops += 1
        if pops > max_pops:
            _LAST_FAIL = f"pop-cap {max_pops}"
            return None
        if ix == gx and iy == gy and (goal_dir is None or d == goal_dir):
            # reconstruct
            global _LAST_COST
            _LAST_COST = g
            path = [(ix, iy)]
            key = (ix, iy, d)
            while key in came:
                key = came[key]
                path.append((key[0], key[1]))
            path.reverse()
            wp = [grids.cell_xy(i, j) for (i, j) in path]
            return _compress(wp)
        for nd, (dx, dy) in enumerate(_DIRS):
            if d >= 0 and (dx == -_DIRS[d][0] and dy == -_DIRS[d][1]):
                continue                      # no immediate reversal
            jx, jy = ix + dx, iy + dy
            if not (x1 <= jx <= x2 and y1 <= jy <= y2):
                continue
            if grids.blocked(jx, jy, pair=pair):
                # the goal/start cells themselves are pre-carved; all
                # other blocked cells are hard obstacles
                if not (jx == gx and jy == gy):
                    continue
            # in-field surcharge: BGA-field cells are expensive, so paths
            # only dip in near their own endpoints — threading a field
            # interior would consume the escape channels later vias need.
            # The breakout collar has its own surcharge: a corridor run
            # PARKED along a field boundary walls off every unrouted
            # escape mouth on that edge (crossing the ring costs a fixed
            # ~1.8 cells; loitering in it does not pay).
            if grids.infield(jx, jy):
                step = 4.0
            elif grids.incollar(jx, jy):
                step = 2.5
            else:
                step = 1.0
            ng = (g + step + xtrack(jx, jy)
                  + (TURN_COST if (d >= 0 and nd != d) else 0))
            if cong is not None:
                ng += cong[2] * cong[0][jx, jy] + cong[1][jx, jy]
            key = (jx, jy, nd)
            if ng < best.get(key, math.inf) - 1e-9:
                best[key] = ng
                came[key] = (ix, iy, d)
                heapq.heappush(openq, (ng + h(jx, jy), ng, jx, jy, nd))
    _LAST_FAIL = f"exhausted after {pops} pops"
    return None


def _astar_ml(grids, start, goal, *, start_lvls, goal_lvls, hop_ok,
              start_dir=None, goal_dir=None, guide=None,
              via_cost=50.0, attach_cost=8.0, margin=4.0,
              max_pops=6_000_000, guide_w=0.35):
    """Multi-layer lattice A*: state is (cell, LEVEL, heading). Planar
    moves obey that level's grid; vertical moves hop between physically
    adjacent routing levels through a buried µvia pair — legal only
    where `hop_ok[(la, lb)]` says a pad-sized disc is clear on BOTH
    levels and outside the BGA fields (hop lands must not eat escape
    lanes). `via_cost` prices a hop at ~2.5 mm of detour, so hops
    happen exactly where a same-layer route-around is longer than
    that. `attach_cost` × physical depth biases the BALL attach toward
    shallow VIPPO stacks. Returns a list of (x, y, level_name) or
    None."""
    levels = L_LEVELS
    g0 = grids[levels[0]]
    sx, sy = g0._ix(start[0]), g0._iy(start[1])
    gx, gy = g0._ix(goal[0]), g0._iy(goal[1])
    pts = [start] + list(guide or []) + [goal]
    x1 = g0._ix(min(p[0] for p in pts) - margin)
    x2 = g0._ix(max(p[0] for p in pts) + margin)
    y1 = g0._iy(min(p[1] for p in pts) - margin)
    y2 = g0._iy(max(p[1] for p in pts) + margin)
    segs = [(a, b) for a, b in zip(pts, pts[1:]) if a != b]

    def xtrack(ix, iy):
        px, py = g0.cell_xy(ix, iy)
        d2 = math.inf
        for (ax, ay), (bx, by) in segs:
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = (((px - ax) * dx + (py - ay) * dy) / L2) if L2 else 0.0
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            ex, ey = px - (ax + t * dx), py - (ay + t * dy)
            d2 = min(d2, ex * ex + ey * ey)
        return guide_w * max(0.0, math.sqrt(d2) - 0.45)

    def h(ix, iy):
        return (abs(ix - gx) + abs(iy - gy)) * H_WEIGHT

    def depth_of(L):
        return int(L[2:-3]) if L.startswith("In") else 0

    openq = []
    best = {}
    came = {}
    for L in start_lvls:
        li = levels.index(L)
        g = attach_cost * depth_of(L)
        d0 = -1 if start_dir is None else start_dir
        key = (sx, sy, li, d0)
        if g < best.get(key, math.inf):
            best[key] = g
            heapq.heappush(openq, (g + h(sx, sy), g, sx, sy, li, d0))
    goal_li = {levels.index(L) for L in goal_lvls}
    pops = 0
    global _LAST_FAIL, _LAST_COST
    while openq:
        f, g, ix, iy, li, d = heapq.heappop(openq)
        if best.get((ix, iy, li, d), math.inf) < g - 1e-9:
            continue
        pops += 1
        if pops > max_pops:
            _LAST_FAIL = f"ml pop-cap {max_pops}"
            return None
        if (ix == gx and iy == gy and li in goal_li
                and (goal_dir is None or d == goal_dir)):
            _LAST_COST = g + attach_cost * depth_of(levels[li])
            path = [(ix, iy, li)]
            key = (ix, iy, li, d)
            while key in came:
                key = came[key]
                path.append((key[0], key[1], key[2]))
            path.reverse()
            return [(g0.cell_xy(i, j) + (levels[k],))
                    for (i, j, k) in path]
        gr = grids[levels[li]]
        for nd, (dx, dy) in enumerate(_DIRS):
            if d >= 0 and (dx == -_DIRS[d][0] and dy == -_DIRS[d][1]):
                continue
            jx, jy = ix + dx, iy + dy
            if not (x1 <= jx <= x2 and y1 <= jy <= y2):
                continue
            if gr.blocked(jx, jy, pair=False):
                if not (jx == gx and jy == gy):
                    continue
            if gr.infield(jx, jy):
                step = 4.0
            elif gr.incollar(jx, jy):
                step = 2.5
            else:
                step = 1.0
            ng = (g + step + xtrack(jx, jy)
                  + (TURN_COST if (d >= 0 and nd != d) else 0))
            key = (jx, jy, li, nd)
            if ng < best.get(key, math.inf) - 1e-9:
                best[key] = ng
                came[key] = (ix, iy, li, d)
                heapq.heappush(openq, (ng + h(jx, jy), ng, jx, jy,
                                       li, nd))
        for lj in (li - 1, li + 1):
            if not (0 <= lj < len(levels)):
                continue
            # hops snap to a 0.4 mm lattice: any two hop stacks are
            # >= 8 cells apart by construction (drill-to-drill rule;
            # a down-up jump over one trace otherwise lands its two
            # stacks with overlapping drills)
            if ix % 8 or iy % 8:
                continue
            pk = (levels[min(li, lj)], levels[max(li, lj)])
            if not hop_ok[pk][ix, iy]:
                continue
            ng = g + via_cost
            key = (ix, iy, lj, -1)      # free heading after the via
            if ng < best.get(key, math.inf) - 1e-9:
                best[key] = ng
                came[key] = (ix, iy, li, d)
                heapq.heappush(openq, (ng + h(ix, iy), ng, ix, iy,
                                       lj, -1))
    _LAST_FAIL = f"ml exhausted after {pops} pops"
    return None


def _excise_loops(mlp):
    """Cut state-space loops out of a reconstructed multi-layer path.
    A* over (cell, level, heading) may revisit a cell with a different
    heading — a same-level self-crossing in copper. Every lattice
    crossing passes through a shared (x, y, level) point, so it is
    always an excisable loop: keep the first visit, drop the detour."""
    changed = True
    while changed:
        changed = False
        seen = {}
        for i, key in enumerate(mlp):
            if key in seen:
                del mlp[seen[key] + 1:i + 1]
                changed = True
                break
            seen[key] = i
    return mlp


# ── structured route plan ─────────────────────────────────────────────
def _plan_routes(ends, est, target_est):
    """Per-net guide polylines + routing order, from the board's actual
    topology (both chips locked, rotation 0):

      - BYTE1 (+DQS1 T): over the top — escape the MPU field north, run
        an allocated north-boulevard lane, drop into the DRAM data field
        from above through the vacant half-pitch column channels
        (target.x ± 0.4; the DRAM has no balls between its column
        groups, so the gaps run the full field height).
      - BYTE0, west-column targets (+DQS0 T): straight across the
        corridor into the DRAM west edge at the target row.
      - BYTE0, east-column targets: south boulevard below the MPU/DRAM,
        then climb the same vacant column channels from below (crossing
        the DRAM A/C rows inside the gaps, in-field rules).
      - A/C (+CK T) on In4: west columns straight across; east columns
        via a shallower south boulevard. MISC nets: free chords, last.

    Boulevard lanes are allocated in drop/climb-x order — a lane only
    ever crosses drops of nets on lanes FARTHER from the field, so the
    bundle is planar — at 0.55 mm pitch (S-3S) plus a 1.2 mm switchback
    allowance on the open side for any net whose tuning estimate needs
    one (bump height 2h = 1.1).
    """
    by_net = {e.net: e for e in ends}

    def drop_x(e):
        """Vertical entry channel for boulevard nets. West-column
        targets drop right beside their ball; the DRAM's east columns
        (7/8) are entered through the wide vacant mid-canyon between
        column groups 3 and 7 (x 5.65…8.1) and finished along the
        in-field row channels — keeping the north-lane drops at x ≤ 8.05
        so the outermost lanes still fit inside the Ø34 edge."""
        tx = e.dram_xy[0]
        if tx <= 5.8:
            return tx + 0.4
        return 8.05

    def alloc(nets, y0, sgn, pitch=0.55):
        """Lane y per net, stacked away from the fields in drop-x order.
        Flat pitch — switchbacks land on each lane's tail east of the
        previous lane's climb, where the sky toward the field is clear,
        so no per-lane bump allowance is reserved."""
        lanes = {}
        y = y0
        for e in sorted(nets, key=lambda e: (drop_x(e), e.dram_xy[1])):
            lanes[e.net] = round(y / GRID) * GRID
            y += sgn * pitch
        return lanes

    plan = {}
    skip_c = {c for (_t, c) in PAIRS.values()}

    b1 = [e for e in ends if e.group == "BYTE1" and e.net not in skip_c]
    north = alloc(b1, 9.05, +1, pitch=0.45)
    for e in b1:
        dx_ = drop_x(e)
        plan[e.net] = [(e.mpu_xy[0], north[e.net]), (dx_, north[e.net]),
                       (dx_, e.dram_xy[1])]

    b0 = [e for e in ends if e.group == "BYTE0" and e.net not in skip_c]
    b0_west = [e for e in b0 if e.dram_xy[0] <= 5.8]
    b0_south = [e for e in b0 if e.dram_xy[0] > 5.8]
    south0 = alloc(b0_south, -7.7, -1)
    for e in b0_west:
        plan[e.net] = []                    # straight chord
    for e in b0_south:
        dx_ = drop_x(e)
        plan[e.net] = [(e.mpu_xy[0], south0[e.net]), (dx_, south0[e.net]),
                       (dx_, e.dram_xy[1])]

    # A/C splits three ways: the DRAM's bottom rows (P/R/T, ty ≤ −2) are
    # a short hop from the open south — they enter from below directly,
    # no boulevard lane; deeper east-column targets take south lanes;
    # the remaining west-column targets cross as chords (9 × S-2S fits
    # the 5.5 mm west-entry band, which 20 chords at S-3S did not).
    ac = [e for e in ends if e.group == "AC" and e.net not in skip_c]
    ac_direct = [e for e in ac if e.dram_xy[1] <= -2.0]
    ac_lane = [e for e in ac if e.dram_xy[1] > -2.0
               and e.dram_xy[0] > 5.8]
    ac_west = [e for e in ac if e.dram_xy[1] > -2.0
               and e.dram_xy[0] <= 5.8]
    southA = alloc(ac_lane, -4.95, -1)
    for e in ac_west:
        plan[e.net] = []
    for e in ac_direct:
        cx_ = e.dram_xy[0] + 0.4
        plan[e.net] = [(cx_, -4.65), (cx_, e.dram_xy[1])]
    for e in ac_lane:
        dx_ = drop_x(e)
        plan[e.net] = [(e.mpu_xy[0], southA[e.net]), (dx_, southA[e.net]),
                       (dx_, e.dram_xy[1])]

    for e in ends:
        if e.group == "MISC":
            if e.net == "DDR4_RESET_N":     # P1, bottom row — same
                plan[e.net] = [(4.1, -4.65), (4.1, e.dram_xy[1])]
            else:
                plan[e.net] = []

    # Routing order: refs first within each region; boulevard groups in
    # lane order (nearest-the-field lane first) so each next path nests
    # outward; chord groups by target row, north first; MISC last.
    def _lane_order(group, lanes):
        return [e.net for e in sorted(group, key=lambda e: abs(
            lanes[e.net]))]

    # More-constrained groups first: boulevard/climb nets have specific
    # lanes; chord nets can flex around whatever is already there.
    order = []
    order.append(("pair", "DQS1"))
    order += [("net", n) for n in _lane_order(b1, north)
              if n != "DDR4_DQS1_T"]
    order.append(("pair", "DQS0"))
    order += [("net", n) for n in _lane_order(b0_south, south0)]
    order += [("net", e.net) for e in
              sorted(b0_west, key=lambda e: -e.dram_xy[1])
              if e.net != "DDR4_DQS0_T"]
    order.append(("pair", "CK"))
    order += [("net", n) for n in _lane_order(ac_lane, southA)
              if n != "DDR4_CK_T"]
    order += [("net", e.net) for e in
              sorted(ac_direct, key=lambda e: e.dram_xy[0])]
    order += [("net", e.net) for e in
              sorted(ac_west, key=lambda e: -e.dram_xy[1])]
    order += [("net", e.net) for e in ends if e.group == "MISC"]

    # exit side per net for the MPU escape assignment (pair C legs leave
    # the same side as their T), plus each boulevard net's lane depth
    # rank — escape verticals are handed out in lane order so that every
    # later (deeper-lane) net descends WEST of the already-committed
    # lane runs (planar fan).
    E_, N_, S_ = 0, 2, 3
    exit_dir = {}
    lane_rank = {}
    for e in b1:
        exit_dir[e.net] = N_
        lane_rank[e.net] = abs(north[e.net])
    exit_dir["DDR4_DQS1_C"] = N_
    lane_rank["DDR4_DQS1_C"] = lane_rank.get("DDR4_DQS1_T", 0.0)
    for e in b0_south:
        exit_dir[e.net] = S_
        lane_rank[e.net] = abs(south0[e.net])
    for e in ac_lane:
        exit_dir[e.net] = S_
        lane_rank[e.net] = abs(southA[e.net])
    exit_dir["DDR4_CK_C"] = S_
    lane_rank["DDR4_CK_C"] = lane_rank.get("DDR4_CK_T", 0.0)
    return plan, order, exit_dir, lane_rank


# ── reference-design escape transplant ────────────────────────────────
def _cardinal_or_none(a, b):
    """_DIRS index of segment a→b when within 30° of a cardinal, else
    None (transplanted reference stubs contain 45° segments — A* then
    starts/ends unconstrained)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if math.hypot(dx, dy) < 1e-9:
        return None
    ang = math.degrees(math.atan2(dy, dx)) % 360.0
    for d_idx, target in ((0, 0.0), (2, 90.0), (1, 180.0), (3, 270.0)):
        delta = abs(ang - target)
        if min(delta, 360.0 - delta) <= 30.0:
            return d_idx
    return None


def _stub_exit(wp):
    """(end_point, outward_dir_index) using the last ≥0.1 mm segment."""
    for k in range(len(wp) - 2, -1, -1):
        if (abs(wp[k][0] - wp[-1][0]) + abs(wp[k][1] - wp[-1][1])) > 0.1:
            return wp[-1], _cardinal_or_none(wp[k], wp[-1])
    return wp[-1], None


def _load_ref_stubs(ends, mpu_centre, dram_centre):
    """Escape stubs lifted from ST's routed AL/DDR4 reference
    (tools/extract_ref_escapes.py → smash/data/…_ref_escapes.json).

    Same packages, rotation 0 and the same net→ball map as the
    reference, so its per-net escape polylines are valid here verbatim
    in package-relative coordinates; only the corridor is re-routed.

    One transplant caveat is validated here: wherever the reference
    DOG-BONED a via instead of going in-pad, its escape traces may
    legally cross that ball's centre — but WE put a VIPPO land on every
    ball, so such a stub would overlap a foreign land. Those stubs are
    dropped (the net falls back to the assigner).

    Returns {("mpu"|"dram", net): board-frame waypoints, path[0] = the
    ball/via centre}. Missing file → {} (router falls back wholesale)."""
    try:
        doc = json.loads(_REF_JSON.read_text())
    except FileNotFoundError:
        return {}
    by_net = {e.net: e for e in ends}

    # foreign-land lattice: under depth-overflow routing every DDR ball
    # carries a VIPPO land on every routing level (conservative model —
    # a net's final depth isn't known when its neighbours route), so a
    # stub must clear ALL foreign ball centres
    def foreign(side, net):
        return [(e.mpu_xy if side == "mpu" else e.dram_xy)
                for e in ends if e.net != net]

    out = {}
    dropped = []
    for side, (cx, cy) in (("mpu", mpu_centre), ("dram", dram_centre)):
        for net, rec in doc.get(side, {}).items():
            if net not in by_net:
                continue
            wp = []
            for (px, py) in rec["path"]:
                q = (cx + px, cy + py)
                if wp and abs(q[0] - wp[-1][0]) + abs(q[1] - wp[-1][1]) < 1e-6:
                    continue
                wp.append(q)
            if len(wp) < 2:
                continue
            # A* splices at the outer end — make sure it's on the lattice
            ex = round(wp[-1][0] / GRID) * GRID
            ey = round(wp[-1][1] / GRID) * GRID
            if abs(ex - wp[-1][0]) > 1e-6 or abs(ey - wp[-1][1]) > 1e-6:
                wp.append((ex, ey))
            ok = True
            for (fx, fy) in foreign(side, net):
                for a, b in zip(wp, wp[1:]):
                    if _seg_seg_dist(a, b, (fx, fy), (fx, fy)) < 0.245:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                dropped.append((side, net))
                continue
            out[(side, net)] = wp
    if dropped and _DEBUG:
        print(f"  ref-stub drops (cross a foreign VIPPO land): {dropped}")
    return out


# ── MPU-field escape assignment ───────────────────────────────────────
def _mpu_escape_assign(ends, exit_dir, lane_rank, skip=frozenset(),
                       seed_geo=(), bfs=True):
    """Deterministic, exit-direction-aware escape stubs out of the MPU's
    DDR ball cluster (col17/18/19 at x −4.2/−3.7/−3.2 + ZQ col16).

    The exits are EXACTLY at capacity (one trace per half-row channel,
    one row-line per col19 row), and a net that exits on the wrong side
    then walls off every exit it crosses on its way around — greedy A*
    keeps deadlocking on this. So each net leaves on the side its
    boulevard plan needs (`exit_dir[net]` ∈ E/N/S):

      E (chord nets):  col19 row line; col17/18 a half-row channel.
      N/S (boulevard): straight up/down its own column when it is the
        end via of that column; else an inter-column vertical (the
        −3.95/−3.45/−2.95 half-pitch gaps run the full cluster height);
        else west along its row (only when the columns west of it are
        vacant) or west along a free half-row channel, to a staggered
        west-fan vertical (the BGA interior has no other DDR vias).
        Fan order: nets farther from their exit edge take more-western
        verticals, so the fan is planar by construction.

    Returns {net: (stub_waypoints, exit_dir_index)}. ALERT_N (a GPIO
    ball far west of the cluster) is excluded — it routes free."""
    E, N, S = 0, 2, 3
    COLS = (-4.2, -3.7, -3.2)
    stubs = {}
    X_EXIT = -2.9                       # just inside the field-box edge
    # one assignment space over the whole cluster (stub geometry is
    # level-agnostic under depth-overflow routing — every stub blocks
    # every routing level), split into the three geometric row bands:
    # byte1 rows (top), A/C rows (middle), byte0 rows (bottom)
    cluster = [e for e in ends if e.mpu_xy[0] > -4.5]
    if cluster:
        bands = [[e for e in cluster if e.mpu_xy[1] > 0],
                 [e for e in cluster if -5.45 < e.mpu_xy[1] <= 0],
                 [e for e in cluster if e.mpu_xy[1] <= -5.45]]
        for band_all in bands:
            # occupancy/extents from the WHOLE band; assignment only for
            # nets without a transplanted reference stub
            members = [e for e in band_all if e.net not in skip]
            if not members:
                continue
            ys = sorted({round(e.mpu_xy[1], 2) for e in band_all},
                        reverse=True)
            y_top, y_bot = ys[0], ys[-1]
            occupied = {(round(e.mpu_xy[0], 2), round(e.mpu_xy[1], 2))
                        for e in band_all}
            ch_taken = set()
            vert_taken = set()              # inter-column x's used
            fan_j = 0
            seed_stubs = [[tuple(p) for p in path] for path in seed_geo]

            def col_end_free(e, d):
                """True if e is the last via of its column toward d."""
                cx = round(e.mpu_xy[0], 2)
                yy = e.mpu_xy[1]
                rows = [y for (c, y) in occupied if c == cx]
                return (max(rows) == round(yy, 2) if d == N
                        else min(rows) == round(yy, 2))

            def vert_for(e):
                cx = round(e.mpu_xy[0], 2)
                for xv in (cx + 0.25, cx - 0.25):
                    xv = round(xv, 2)
                    if xv in (-4.45,):      # first fan slot — leave it
                        continue
                    if -4.0 <= xv <= -2.9 and xv not in vert_taken:
                        return xv
                return None

            def west_clear(e):
                cx = round(e.mpu_xy[0], 2)
                yy = round(e.mpu_xy[1], 2)
                return all((c, yy) not in occupied
                           for c in COLS if c < cx - 0.01)

            band_stubs = list(seed_stubs)   # geometry self-check pool —
                                            # seeded with the transplanted
                                            # reference stubs so fallback
                                            # nets can't collide with them

            def crosses(wp):
                for a, b in zip(wp, wp[1:]):
                    for owp in band_stubs:
                        for c, d_ in zip(owp, owp[1:]):
                            if _seg_seg_dist(a, b, c, d_) < 0.165:
                                return True
                return False

            def channel(e, prefs, cx, y_r):
                for y_ch in prefs:
                    if round(y_ch, 2) in ch_taken:
                        continue
                    wp = [e.mpu_xy, (cx, y_ch), (X_EXIT, y_ch)]
                    if crosses(wp):
                        continue
                    ch_taken.add(round(y_ch, 2))
                    return wp
                return None

            # E-exiters first (channels are their only resource)
            for e in sorted(members, key=lambda e: -e.mpu_xy[1]):
                if exit_dir.get(e.net, E) != E:
                    continue
                cx = round(e.mpu_xy[0], 2)
                y_r = e.mpu_xy[1]
                if cx == -3.2:
                    wp = [e.mpu_xy, (X_EXIT, y_r)]
                    if not crosses(wp):
                        stubs[e.net] = (wp, E)
                        band_stubs.append(wp)
                    continue
                prefs = ((y_r + 0.25, y_r - 0.25) if cx == -3.7
                         else (y_r - 0.25, y_r + 0.25))
                wp = channel(e, prefs, cx, y_r)
                if wp is not None:
                    stubs[e.net] = (wp, E)
                    band_stubs.append(wp)
                # else: fall through to the N/S fan below as a last
                # resort (treated as a vertical exiter toward mid)

            # N/S exiters in LANE order: the shallowest-lane net takes
            # the easternmost exit vertical, so each later (deeper)
            # net's descent runs west of every already-committed lane —
            # the boulevard access fan stays planar
            ns = [e for e in members if exit_dir.get(e.net, E) != E
                  or e.net not in stubs]

            for e in sorted(ns, key=lambda e: lane_rank.get(e.net, 99.0)):
                if e.net in stubs:
                    continue
                d = exit_dir.get(e.net, E)
                if d == E:                  # overflowed E net → nearest edge
                    d = N if (e.mpu_xy[1] - y_bot
                              > y_top - e.mpu_xy[1]) else S
                y_end = round(((y_top + 0.7) if d == N else (y_bot - 0.7))
                              / GRID) * GRID
                cx = round(e.mpu_xy[0], 2)
                y_r = e.mpu_xy[1]
                cands = []
                if col_end_free(e, d):
                    cands.append([e.mpu_xy, (cx, y_end)])
                xv = vert_for(e)
                if xv is not None:
                    cands.append([e.mpu_xy, (xv, y_r), (xv, y_end)])
                # west-fan options (slide west until crossing-free)
                for j in range(fan_j, fan_j + 8):
                    x_w = round((-4.45 - 0.25 * j) / GRID) * GRID
                    if west_clear(e):
                        cands.append([e.mpu_xy, (x_w, y_r), (x_w, y_end)])
                    else:
                        for y_ch in ((y_r - 0.25, y_r + 0.25)
                                     if d == S else (y_r + 0.25,
                                                     y_r - 0.25)):
                            if round(y_ch, 2) not in ch_taken:
                                cands.append([e.mpu_xy, (cx, y_ch),
                                              (x_w, y_ch), (x_w, y_end)])
                for wp in cands:
                    if crosses(wp):
                        continue
                    stubs[e.net] = (wp, d)
                    band_stubs.append(wp)
                    if len(wp) == 2:        # straight own-column exit
                        occupied.add((cx, round(y_end, 2)))
                    elif len(wp) == 3:      # inter-column or row-west fan
                        xv_used = round(wp[1][0], 2)
                        if xv_used > -4.4:
                            vert_taken.add(xv_used)
                        else:
                            fan_j = max(fan_j, int(round(
                                (-4.45 - xv_used) / 0.25)) + 1)
                    else:                   # channel-west + fan vertical
                        ch_taken.add(round(wp[1][1], 2))
                        fan_j = max(fan_j, int(round(
                            (-4.45 - wp[2][0]) / 0.25)) + 1)
                    break
                # else: no template stub — flood-fill picks it up below

            # ── flood-fill fallback ────────────────────────────────────
            # The template resources (row lines, channels, verticals,
            # fans) are an idealised description of the field's gaps; a
            # net they cannot serve is NOT necessarily sealed — it only
            # becomes sealed once the global stub reservations stamp.
            # So compute a shortest-path escape NOW, against just the
            # via lattice and the stubs assigned so far, and reserve it
            # like any other stub. (Measured: routing order cannot save
            # these nets — with first priority they still fail, because
            # their seal is the reservations themselves.)
            for e in members:
                if not bfs or e.net in stubs:
                    continue
                wp = _bfs_escape(e, band_all, band_stubs)
                if wp is None:
                    continue                # truly sealed — A* from via
                d = _stub_exit(wp)[1]
                stubs[e.net] = (wp, d)
                band_stubs.append(wp)
    return stubs


def _bfs_escape(e, band_all, band_stubs):
    """Shortest-path escape for a net the stub templates couldn't
    serve: BFS on a local 0.05 mm lattice over the cluster window,
    obstacles = the other vias (0.25 centre keep-out) and the already-
    assigned stub polylines (0.175), goal = anywhere past the cluster
    hull + 0.4 mm. Returns compressed waypoints or None."""
    X1, Y1, X2, Y2 = -6.2, -8.4, -2.3, 2.8      # cluster window (board)
    nx = int(round((X2 - X1) / GRID)) + 1
    ny = int(round((Y2 - Y1) / GRID)) + 1
    blocked = np.zeros((nx, ny), bool)
    xs = X1 + GRID * np.arange(nx)
    ys = Y1 + GRID * np.arange(ny)

    def paint_disk(px, py, r):
        m = (xs[:, None] - px) ** 2 + (ys[None, :] - py) ** 2 < r * r
        blocked[m] = True

    for o in band_all:
        if o.net == e.net:
            continue
        paint_disk(*o.mpu_xy, 0.25)
    for wp in band_stubs:
        for a, b in zip(wp, wp[1:]):
            seg = np.hypot(b[0] - a[0], b[1] - a[1])
            for k in range(int(seg / 0.03) + 1):
                t = k / max(int(seg / 0.03), 1)
                paint_disk(a[0] + (b[0] - a[0]) * t,
                           a[1] + (b[1] - a[1]) * t, 0.175)

    hx1, hy1 = -4.95, -7.45                     # cluster hull + 0.4
    hx2, hy2 = -2.95, 2.05

    def outside(px, py):
        return not (hx1 <= px <= hx2 and hy1 <= py <= hy2)

    si = int(round((e.mpu_xy[0] - X1) / GRID))
    sj = int(round((e.mpu_xy[1] - Y1) / GRID))
    import collections as _c
    q = _c.deque([(si, sj)])
    came = {(si, sj): None}
    hit = None
    while q:
        ci, cj = q.popleft()
        px, py = X1 + ci * GRID, Y1 + cj * GRID
        if outside(px, py):
            hit = (ci, cj)
            break
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = ci + di, cj + dj
            if not (0 <= ni < nx and 0 <= nj < ny):
                continue
            if (ni, nj) in came or blocked[ni, nj]:
                continue
            came[(ni, nj)] = (ci, cj)
            q.append((ni, nj))
    if hit is None:
        return None
    path = []
    cur = hit
    while cur is not None:
        path.append((X1 + cur[0] * GRID, Y1 + cur[1] * GRID))
        cur = came[cur]
    path.reverse()
    return _compress(path) if len(path) >= 2 else None


# ── endpoint extraction ───────────────────────────────────────────────
@dataclasses.dataclass
class _NetEnd:
    net: str
    group: str                  # BYTE0/BYTE1/AC/MISC — matching only;
                                # the routing LEVEL is assigned by the
                                # depth-overflow loop, not by group
    mpu_xy: tuple
    dram_xy: tuple
    pkg_mm: float
    # REAL F.Cu pad radii (footprint), NOT the VIPPO land radius —
    # surface obstacles modelled at land size let F.Cu tracks graze
    # the physical Ø0.298/Ø0.41 pads (raster-audit-found shorts)
    mpu_pad_r: float = VIA_PAD / 2
    dram_pad_r: float = VIA_PAD / 2


def _chip_pad_xy(chip, placement):
    """{pin_name: absolute (x, y)} and {pin_name: net} for a placed chip."""
    px, py = placement.position_mm
    rot = math.radians(placement.rotation_deg or 0.0)
    c, s = math.cos(rot), math.sin(rot)
    pos = {}
    net = {}
    pad_xy = {p.num: p.position_mm for p in chip.footprint.pads}
    for pin in chip.pins:
        num = _strip_ball_prefix(pin.num)
        if num not in pad_xy:
            continue
        x, y = pad_xy[num]
        pos[pin.name] = (px + x * c - y * s, py + x * s + y * c)
        net[pin.name] = pin.net
    return pos, net


def collect_endpoints(design, board, mpu_ref="U_MPU", dram_ref="U_DDR4"):
    """Inter-chip DDR4_* endpoints in board coords + MPU package lengths."""
    pl = {p.item.ref: p for p in board.chip_placements
          if getattr(p.item, "ref", None) in (mpu_ref, dram_ref)}
    if set(pl) != {mpu_ref, dram_ref}:
        raise ValueError(f"{board.name}: need {mpu_ref}+{dram_ref} placed, "
                         f"got {sorted(pl)}")
    for r in (mpu_ref, dram_ref):
        if pl[r].face != "top":
            raise ValueError(f"{r} not on the top face")
    chips = {c.ref: c for c in design.chips}
    mpu_xy, mpu_net = _chip_pad_xy(chips[mpu_ref], pl[mpu_ref])
    ddr_xy, ddr_net = _chip_pad_xy(chips[dram_ref], pl[dram_ref])

    def _pad_radius(chip):
        fp = getattr(chip, "footprint", None)
        sizes = [max(pd.size_mm) for pd in (fp.pads if fp else ())
                 if getattr(pd, "size_mm", None)]
        return (max(sizes) / 2.0) if sizes else VIA_PAD / 2

    pad_r_m = _pad_radius(chips[mpu_ref])
    pad_r_d = _pad_radius(chips[dram_ref])

    pkg = json.loads(_PKG_JSON.read_text())["lengths_mm"]

    by_net_m = {}
    for name, n in mpu_net.items():
        if n and n.startswith("DDR4_"):
            by_net_m[n] = (mpu_xy[name], pkg.get(name, 0.0))
    # ALERT_N rides a GPIO ball (PG12), not a DDR PHY ball → pkg 0.0
    ends = []
    for name, n in ddr_net.items():
        if not n or not n.startswith("DDR4_"):
            continue
        g = _group_of(n)
        if g is None or n not in by_net_m:
            continue
        (mxy, pkg_mm) = by_net_m[n]
        ends.append(_NetEnd(net=n, group=g,
                            mpu_xy=mxy, dram_xy=ddr_xy[name],
                            pkg_mm=pkg_mm,
                            mpu_pad_r=pad_r_m, dram_pad_r=pad_r_d))
    ends.sort(key=lambda e: e.net)
    return ends


# ── report ────────────────────────────────────────────────────────────
@dataclasses.dataclass
class RouteRow:
    net: str
    group: str
    pkg_mm: float
    board_mm: float
    total_mm: float
    delta_mm: float | None      # vs group reference mean (None for MISC/ref)
    tol_mm: float | None
    ok: bool
    tuned_mm: float             # switchback length added


@dataclasses.dataclass
class DdrRouteReport:
    rows: list
    n_vias: int
    n_tracks: int
    clearance_violations: list
    s3s_warnings: list
    pair_skew_mm: dict
    unrouted: list

    @property
    def ok(self) -> bool:
        return (not self.unrouted and not self.clearance_violations
                and all(r.ok for r in self.rows))

    def summary(self) -> str:
        out = []
        for gname, tol in (("BYTE0", TOL_BYTE), ("BYTE1", TOL_BYTE),
                           ("AC", TOL_AC)):
            rows = [r for r in self.rows if r.group == gname]
            if not rows:
                continue
            worst = max((abs(r.delta_mm) for r in rows
                         if r.delta_mm is not None), default=0.0)
            n_ok = sum(r.ok for r in rows)
            out.append(f"{gname}: {n_ok}/{len(rows)} in ±{tol} mm, "
                       f"worst |Δ| {worst:.2f} mm")
        out.append(f"vias {self.n_vias}, tracks {self.n_tracks}, "
                   f"clearance violations {len(self.clearance_violations)}, "
                   f"S-3S warnings {len(self.s3s_warnings)}, "
                   f"unrouted {len(self.unrouted)}")
        for p, sk in self.pair_skew_mm.items():
            out.append(f"pair {p}: intra-pair skew {sk:.2f} mm")
        return "\n".join(out)


# ── main entry ────────────────────────────────────────────────────────
def route_companion_ddr(design, board, *, mpu_ref="U_MPU",
                        dram_ref="U_DDR4", strict=True) -> DdrRouteReport:
    """Route the DDR4 interface on `board`; appends Tracks + Vias and
    returns the report. Idempotent (clears its own previous output)."""
    board.tracks = [t for t in board.tracks if t.note != _NOTE]
    board.vias = [v for v in board.vias if v.note is None
                  or not v.note.startswith(_NOTE)]

    ends = collect_endpoints(design, board, mpu_ref, dram_ref)
    if not ends:
        raise ValueError("no DDR4 inter-chip nets found")

    # field boxes (ball extents + margin) — clearance-regime regions
    boxes = []
    for pts in ((tuple(e.mpu_xy for e in ends)),
                (tuple(e.dram_xy for e in ends))):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        boxes.append((min(xs) - FIELD_MARGIN, min(ys) - FIELD_MARGIN,
                      max(xs) + FIELD_MARGIN, max(ys) + FIELD_MARGIN))
    # ALERT_N's GPIO ball sits outside the DDR cluster; widen the MPU box
    # to the full BGA so its escape also runs under the waiver
    g = board.geometry
    R = (g.diameter_mm / 2.0 if g and getattr(g, "diameter_mm", None)
         else 17.0)
    grids = {ly: _Grids(-R, -R, R, R, boxes) for ly in L_LEVELS}
    for gr in grids.values():
        gr.block_edge(0.0, 0.0, R - EDGE_KEEPIN)
        if g is not None:
            for hole in getattr(g, "holes", []) or []:
                hx, hy = hole.position_mm
                # pad-class stamps inflate by CLR_FIELD — widen the
                # half-width so the effective keep-back is NPTH_CLEAR
                gr.add_disk(hx, hy, hole.diameter_mm / 2.0
                            + (NPTH_CLEAR - CLR_FIELD))

    # ── VIPPO lands: a net's final depth isn't known until it routes,
    # so every ball conservatively carries a land on EVERY routing
    # level (this is also what makes the lifted escape geometry
    # level-portable). The Via objects are built after routing, as deep
    # as each net's assigned level only.
    idx_of = {e.net: i for i, e in enumerate(ends)}
    level_of = {}               # net → primary (MPU-attach) layer
    attach = {}                 # net → (mpu_attach, dram_attach)
    net_hops = {}               # net → [(x, y, La, Lb) buried hops]
    # PHYSICAL land model: a stack only lands on the levels it passes
    # (F.Cu, rank 0, carries every ball's PAD and is included in every
    # net's span). Each net's prior = its affinity-first level; a net
    # that overflows deeper stamps the extra lands when it commits.
    def _ball_r(e, xy, ly):
        """Ball obstacle radius: the VIPPO land on inner levels, the
        REAL footprint pad on F.Cu (Ø0.298 MPU / Ø0.41 DRAM) — the
        land radius there lets surface tracks graze physical pads."""
        if ly != "F.Cu":
            return VIA_PAD / 2
        return e.mpu_pad_r if xy == e.mpu_xy else e.dram_pad_r

    # (prior ball lands are stamped by _reset_routing_state below)

    # ── F.Cu surface keep-outs: the REAL component copper ─────────────
    # Placements are final. Every pad of every top-face placement —
    # including the two BGAs' non-DDR balls — blocks the surface level
    # (traces may still pass UNDER small bodies; that is normal SMD
    # practice). DDR balls are already stamped per-net above.
    ddr_balls = {(round(x, 2), round(y, 2))
                 for e in ends for (x, y) in (e.mpu_xy, e.dram_xy)}
    fcu_pads = []
    for pl in board.chip_placements:
        if pl.face != "top":
            continue
        fp = getattr(pl.item, "footprint", None)
        if fp is None:
            continue
        px, py = pl.position_mm
        rot = math.radians(pl.rotation_deg or 0.0)
        c, sn = math.cos(rot), math.sin(rot)
        for pad in fp.pads:
            x0, y0 = pad.position_mm
            x = px + x0 * c - y0 * sn
            y = py + x0 * sn + y0 * c
            if (round(x, 2), round(y, 2)) in ddr_balls:
                continue
            r = max(pad.size_mm) / 2.0 if getattr(pad, "size_mm", None) \
                else 0.3
            grids["F.Cu"].add_disk(x, y, r)
            fcu_pads.append((x, y, r, None))
    for e in ends:
        fcu_pads.append((*e.mpu_xy, e.mpu_pad_r, e.net))
        fcu_pads.append((*e.dram_xy, e.dram_pad_r, e.net))

    # ── plan targets from Manhattan estimates ─────────────────────────
    est = {e.net: (abs(e.mpu_xy[0] - e.dram_xy[0])
                   + abs(e.mpu_xy[1] - e.dram_xy[1]) + e.pkg_mm)
           for e in ends}
    pair_mean_est = {}
    for pname, (t, c) in PAIRS.items():
        pair_mean_est[pname] = (est[t] + est[c]) / 2.0

    def members(gname):
        return [e for e in ends if e.group == gname
                and e.net not in _PAIR_NETS]

    target_est = {
        "BYTE0": max([est[m.net] for m in members("BYTE0")]
                     + [pair_mean_est["DQS0"]]) + 0.4,
        "BYTE1": max([est[m.net] for m in members("BYTE1")]
                     + [pair_mean_est["DQS1"]]) + 0.4,
        "AC":    max([est[m.net] for m in members("AC")]
                     + [pair_mean_est["CK"]]) + 0.4,
    }

    tracks = []
    unrouted = []
    stripped = set()            # nets whose stub reservations were
                                # released — their stub geometry must be
                                # re-validated before any re-commit
    routed_len = {}             # net → board length (mm)
    tuned = {n: 0.0 for n in idx_of}
    pair_skew = {}

    by_net = {e.net: e for e in ends}

    # ── structured route plan ──────────────────────────────────────────
    # Escape stubs transplanted from ST's routed reference where
    # available (same packages/rotation/ball map — they apply verbatim);
    # the boulevard plan + exact-capacity assigner cover the rest.
    plan, order_list, exit_dir, lane_rank = _plan_routes(ends, est,
                                                         target_est)
    pl_of = {p.item.ref: p for p in board.chip_placements
             if getattr(p.item, "ref", None) in (mpu_ref, dram_ref)}
    ref_stubs = _load_ref_stubs(ends, pl_of[mpu_ref].position_mm,
                                pl_of[dram_ref].position_mm)
    _skip = frozenset(n for (side, n) in ref_stubs if side == "mpu")
    _seed = [wp for (side, _n), wp in ref_stubs.items() if side == "mpu"]
    # two escape-stub variants with complementary victim sets (both
    # MEASURED): templates-only routes the flexible majority; +BFS
    # flood-fill frees the template-less nets but displaces others.
    # The singles phase runs under each and keeps the better outcome.
    stub_variants = [
        _mpu_escape_assign(ends, exit_dir, lane_rank, skip=_skip,
                           seed_geo=_seed, bfs=False),
        _mpu_escape_assign(ends, exit_dir, lane_rank, skip=_skip,
                           seed_geo=_seed, bfs=True),
    ]
    stubs = stub_variants[0]
    if ref_stubs:
        # Transplanted exits are spread along the MPU field boundary —
        # route in a clockwise BOUNDARY SWEEP (north edge W→E, east edge
        # N→S, south edge E→W) so that each same-edge neighbour nests
        # under the previous run instead of walling its mouth; the
        # exit/entry orders are mutually planar (they coexisted on the
        # reference's routed plane). Pairs still go first — their routed
        # lengths set the per-group tuning targets.
        bx1, by1, bx2, by2 = boxes[0]

        def _sweep(net):
            wp = ref_stubs.get(("mpu", net))
            if wp is not None:
                tx, ty = wp[-1]
            else:
                st = stubs.get(net)
                tx, ty = (st[0][-1] if st else by_net[net].mpu_xy)
            if ty >= by2 - 0.3:                         # north edge W→E
                return tx - bx1
            if tx >= bx2 - 0.3:                         # east edge N→S
                return (bx2 - bx1) + (by2 - ty)
            if ty <= by1 + 0.3:                         # south edge E→W
                return (bx2 - bx1) + (by2 - by1) + (bx2 - tx)
            return 2 * (bx2 - bx1) + (by2 - by1) + (ty - by1)

        singles = [e.net for e in ends if e.net not in _PAIR_NETS]
        order_list = ([("pair", "DQS1"), ("pair", "DQS0"), ("pair", "CK")]
                      + [("net", n) for n in
                         sorted(singles, key=_sweep)])
        for (side, n) in ref_stubs:
            plan[n] = []                    # chord guidance

    # ── helpers ────────────────────────────────────────────────────────
    def commit(net, layer, wp, *, pair_leg=False):
        owner = idx_of[net]
        grids[layer].add_path(wp, TRACE_W / 2, owner)
        tracks.append(Track(net=net, layer=layer, width_mm=TRACE_W,
                            path=[tuple(p) for p in wp], note=_NOTE))
        routed_len[net] = routed_len.get(net, 0.0) + _path_len(wp)

    def tune(layer, wp, want_extra, *, pair_offs=None,
             consolidate=True):
        """Insert switchbacks until ≥ want_extra−0.3 added (or no fit).
        For a pair body pass the C-leg offset: both the tuned T path and
        its offset C copy must clear. Returns (waypoints, added)."""
        added = 0.0
        cur = list(wp)
        # ONE structure per route (consolidation keeps the corridor
        # legible — measured: byte0's first gain of the campaign);
        # scattered shallow dips ONLY as fallback where no single
        # structure can host (measured: A/C's tight quarters)
        gens = ((_accordion_candidates, _u_detour_candidates,
                 _u_detour_candidates, _u_detour_candidates)
                if consolidate else
                (_u_detour_candidates,) * 4)
        for _gen in gens:
            need = want_extra - added
            if need < SB_MIN_EXCESS / 2:
                break
            placed = False
            for cand, ach, _side, ins in _gen(cur, need):
                if abs(need - ach) >= abs(need) - 0.05:
                    continue        # would not shrink the residual
                # the pattern must keep §6.2 spacing from the net's OWN
                # path too — a meander that touches its own trace is
                # shorted out and the added length is fiction
                if not _self_ok(cand, SB_H - 0.10,
                                ins[0] + 1, ins[1] - 1):
                    continue
                okc = grids[layer].path_clear(cand,
                                              pair=pair_offs is not None)
                if okc and pair_offs is not None:
                    okc = grids[layer].path_clear(
                        _offset_leg(cand, pair_offs), pair=False)
                if okc:
                    cur = cand
                    added += ach
                    placed = True
                    break
            if not placed:
                break
        return cur, added

    # ── pre-stamp EVERY stub (both ends, all nets, ALL levels) ─────────
    # Corridor routes of earlier nets must see later nets' escape stubs
    # as obstacles — otherwise a route hugging the field boundary parks
    # on a sibling's stub mouth and seals it. Stubs block every routing
    # level (like the lands: depth not yet known); each net's own stub
    # tips are carved back out just before its A* attempt on a level.
    stub_home = {nn: _levels_for(by_net[nn].group)[0] for nn in idx_of}

    def _reset_routing_state():
        """Back to the pre-routing state: only static copper (pads,
        holes, F.Cu keep-outs, owner −1) survives; prior-depth ball
        lands and stub reservations are re-stamped; all bookkeeping
        cleared. Used at setup and between global phases."""
        nonlocal tracks
        for gr in grids.values():
            gr.stamps = [st for st in gr.stamps if st.owner == -1]
            gr.repaint_all()
        tracks = []
        routed_len.clear()
        level_of.clear()
        attach.clear()
        net_hops.clear()
        stripped.clear()
        pair_skew.clear()
        for k in list(tuned):
            tuned[k] = 0.0
        unrouted[:] = []
        for e in ends:
            depth = L_LEVELS.index(_levels_for(e.group)[0]) + 1
            for xy in (e.mpu_xy, e.dram_xy):
                for ly in L_LEVELS[:depth]:
                    grids[ly].add_disk(xy[0], xy[1],
                                       _ball_r(e, xy, ly),
                                       idx_of[e.net])
        for (side, nn), swp in ref_stubs.items():
            grids[stub_home[nn]].add_path(swp, TRACE_W / 2, idx_of[nn])
        for nn, (swp, _sd) in stubs.items():
            grids[stub_home[nn]].add_path(swp, TRACE_W / 2, idx_of[nn])

    _reset_routing_state()

    def _hop_maps():
        """Per adjacent-level pair: True where a buried hop via pair
        may land — a pad-sized disc clear on BOTH levels, outside the
        BGA fields (hop lands must not consume escape lanes)."""
        eff = {}
        for L in L_LEVELS:
            gr = grids[L]
            eff[L] = (np.where(gr.in_field, gr.bf, gr.bo)
                      | gr.in_field)
        maps = {}
        for a, b in zip(L_LEVELS, L_LEVELS[1:]):
            M = eff[a] | eff[b]
            D = M.copy()
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if dx * dx + dy * dy > 4:
                        continue
                    D |= np.roll(np.roll(M, dx, 0), dy, 1)
            maps[(a, b)] = ~D
        return maps

    def _escape_start(net, mpu_xy):
        """(astar_start, start_dir, stub_prefix) — transplanted reference
        stub first, then the assigner's (all pre-stamped above)."""
        wp = ref_stubs.get(("mpu", net))
        if wp is not None:
            end, sdir = _stub_exit(wp)
            return end, sdir, list(wp[:-1])
        st = stubs.get(net)
        if st is None:
            return mpu_xy, None, []
        swp, sdir = st
        return swp[-1], sdir, list(swp[:-1])

    def _entry_goal(net, dram_xy):
        """(astar_goal, goal_dir, tail) — the DRAM-side transplanted stub
        reversed onto the path end; goal_dir keeps the splice smooth."""
        wp = ref_stubs.get(("dram", net))
        if wp is None:
            return dram_xy, None, []
        # arrival heading ≈ direction stub_end → next stub point inward
        gdir = None
        for k in range(len(wp) - 2, -1, -1):
            if (abs(wp[k][0] - wp[-1][0])
                    + abs(wp[k][1] - wp[-1][1])) > 0.1:
                gdir = _cardinal_or_none(wp[-1], wp[k])
                break
        tail = list(reversed(wp))[1:]       # stub_end already on the path
        return wp[-1], gdir, tail

    def _attach_ok(xy, lv):
        """May a VIPPO stack legally descend to `lv` at this ball NOW?
        Commit-time land deepening must never stamp a land under
        copper committed earlier — every level the stack passes needs
        a pad-sized disc clear at the ball column. (Own paint is
        already carved around the ball when this runs.)"""
        g0 = grids[L_LEVELS[0]]
        cx, cy = g0._ix(xy[0]), g0._iy(xy[1])
        # r=1 cell: tests the land-overlap class exactly. Wider discs
        # reach into the paint of LEGAL neighbour stubs (transplants
        # may pass 0.245 from a foreign ball centre) and over-reject;
        # sub-25 µm land shaves are the audit's backstop.
        for ly in L_LEVELS[:L_LEVELS.index(lv) + 1]:
            gq = grids[ly]
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                if gq.blocked(cx + dx, cy + dy, pair=False):
                    return False
        return True

    def _stub_levels(e, prefix, start, tail, goal):
        """Per-side sets of levels where this net's (immovable) stub
        geometry is clear — the reserved home level is implicitly
        valid unless the reservation was released."""
        ladder = _levels_for(e.group)
        s_ok, g_ok = [], []
        for lv in ladder:
            gr = grids[lv]
            home = lv == stub_home[e.net] and e.net not in stripped
            if (home or not prefix
                    or gr.path_clear(list(prefix) + [start])):
                s_ok.append(lv)
            if (home or not tail
                    or gr.path_clear([goal] + list(tail))):
                g_ok.append(lv)
        return s_ok, g_ok

    # ── structured byte buses ──────────────────────────────────────────
    # Per review: organic tuning starves because hosts are hemmed by
    # neighbours. Each byte gets a BUS — parallel lanes spanning the
    # inter-field corridor, interleaved across two layers, each lane
    # OWNING a slot wide enough for trombone tuning (continuous depth →
    # exact length, no pattern quantum). Breakouts reach the lane ends
    # with the multi-layer hop search, which also absorbs the DQ
    # swizzle reordering. A/C stays organic (looser ±3.55 tolerance,
    # and it inherits the corridor space the bytes vacate).
    BUS_X = (-1.9, 1.9)             # lane span INBOARD of both stub
                                    # bands INCLUDING their S-2S paint
                                    # (deepest stub x≈2.4 + 0.405 open
                                    # inflation ⇒ ends must clear ±2.0)
    BUS_PITCH = 0.8                 # interleaved combs: same-layer
                                    # neighbours sit at 2×pitch (1.6),
                                    # trombone amp ±0.50
    _BUS_BANDS = {"BYTE0": (("In1.Cu", "In4.Cu"), -3.6, -1),
                  "BYTE1": (("In3.Cu", "In5.Cu"), +3.4, +1)}

    def _bus_plan():
        """net → (layer, y_lane); lanes ordered by MPU-side ball y so
        the west breakouts nest; layers interleave so adjacent lanes
        can cross at the east end (swizzle)."""
        plan_ = {}
        for g, (lys, y0, sgn) in _BUS_BANDS.items():
            members = sorted(
                (e2 for e2 in ends if e2.group == g),
                key=lambda e2: sgn * e2.mpu_xy[1])
            # the DQS pair shares ONE slot (T lane + C offset)
            seen_pair = False
            k = 0
            for e2 in members:
                if e2.net in _PAIR_NETS:
                    if seen_pair:
                        continue
                    seen_pair = True
                lane_y = y0 + sgn * k * BUS_PITCH
                plan_[e2.net] = (lys[k % 2], round(lane_y, 2))
                k += 1
        # pair complements ride the T lane (offset applied at route)
        for pname, (tn, cn) in PAIRS.items():
            if tn in plan_:
                plan_[cn] = plan_[tn]
        return plan_

    # Bus v1 is EXPERIMENTAL (SMASH_DDR_BUS=1): six instrumented
    # iterations each removed a real seal (own-tail paint entombing
    # the east seed; lane paint over its own mouth; lane ends inside
    # the S-2S-inflated reservation bands; arrival-direction pins;
    # window too narrow for east-flank wraps) yet breakouts still
    # miss and four byte0 nets regress — v2 needs per-net lane ends
    # derived from breakout feasibility, not a fixed span. Default
    # stays the proven organic router.
    bus_lane = _bus_plan() if os.environ.get("SMASH_DDR_BUS") else {}

    def _route_bus_member(e) -> bool:
        """Breakout → lane → breakout. The lane is a straight run on
        its layer; both breakouts are multi-layer hop searches with
        the lane end as a pinned target."""
        L, ly = bus_lane[e.net]
        x_e, x_x = BUS_X
        start, sdir, prefix = _escape_start(e.net, e.mpu_xy)
        goal, gdir, tail = _entry_goal(e.net, e.dram_xy)
        pts = [e.mpu_xy, e.dram_xy, start, goal,
               (x_e, ly), (x_x, ly)]
        for gr in grids.values():
            gr.carve_owner(idx_of[e.net], pts)
        s_ok, g_ok = _stub_levels(e, prefix, start, tail, goal)
        s_ok = [lv for lv in s_ok if _attach_ok(e.mpu_xy, lv)]
        g_ok = [lv for lv in g_ok if _attach_ok(e.dram_xy, lv)]
        if not s_ok or not g_ok:
            for gr in grids.values():
                gr.carve_owner(-999, pts)
            return False
        # west search: full own-stub paint (tail is far away)
        paints = [(grids[lv],
                   _paint_own_stubs(grids[lv], prefix, start, goal,
                                    tail)) for lv in L_LEVELS]
        hop = _hop_maps()
        mlp_w = _astar_ml(grids, start, (x_e, ly), start_lvls=s_ok,
                          goal_lvls=[L], hop_ok=hop, start_dir=sdir,
                          goal_dir=0, margin=3.0)
        for gr, polys in paints:
            _unpaint_tmp(gr, polys)
        mlp_e = None
        if mlp_w is not None:
            # east search: PREFIX-ONLY paint. The lane exit sits in
            # the DRAM stub-tip band — painting the own tail entombs
            # the seed inside its own goal's paint (that was every
            # east miss). The fiction gate still catches rare
            # tail-crossings at commit.
            paints = [(grids[lv],
                       _paint_own_stubs(grids[lv], prefix, start,
                                        goal, None))
                      for lv in L_LEVELS]
            # lane is not committed yet — paint it so the east breakout
            # cannot cross it, but STOP SHORT of the east mouth (the
            # east search starts there; painting over it seals it at
            # birth — that was 71 of 85 bus misses)
            lane_paint = ((x_e, ly), (x_x - 0.3, ly))
            grids[L].add_path(list(lane_paint), TRACE_W / 2,
                              idx_of[e.net])
            # search OUTWARD from the net's own tail tip (like the
            # organic router does from its mouth): the lane exit sits
            # outside the S-2S-inflated reservation band, and a seed
            # out there cannot cross OTHER nets' fat stub paint to
            # get in — but leaving through one's own carved mouth gap
            # works, exactly as every organic route proves.
            _REV = {0: 1, 1: 0, 2: 3, 3: 2, None: None}
            mlp_e = _astar_ml(grids, goal, (x_x, ly),
                              start_lvls=g_ok, goal_lvls=[L],
                              hop_ok=_hop_maps(),
                              start_dir=_REV[gdir], goal_dir=None,
                              margin=6.0)
            if mlp_e is not None:
                mlp_e = list(reversed(mlp_e))
            elif _DEBUG:
                print(f"    east-out@search from tail tip {goal}: "
                      f"{_LAST_FAIL}")
            # remove ONLY the temp lane capsule — an owner-wide strip
            # also nuked the net's own stub reservation when its home
            # level is the bus layer (4 byte0 nets died downstream)
            gr0 = grids[L]
            tg = (lane_paint[0][0], lane_paint[0][1],
                  lane_paint[1][0], lane_paint[1][1])
            gr0.stamps = [st for st in gr0.stamps
                          if not (st.owner == idx_of[e.net]
                                  and st.kind == "capsule"
                                  and max(abs(st.geom[k] - tg[k])
                                          for k in range(4)) < 1e-6)]
            xs_rp = []
            xq = x_e
            while xq < x_x + 0.8:
                xs_rp.append((xq, ly))
                xq += 1.6
            gr0.carve_owner(-999, xs_rp)
        for gr, polys in paints:
            _unpaint_tmp(gr, polys)
        if mlp_w is None or mlp_e is None:
            if _DEBUG:
                print(f"  bus-miss {e.net} "
                      f"({'west' if mlp_w is None else 'east'}): "
                      f"{_LAST_FAIL}")
                if mlp_w is not None and mlp_e is None:
                    g0 = grids[L]
                    six, siy = g0._ix(x_x), g0._iy(ly)
                    nb = {d2: g0.blocked(six + d2[0], siy + d2[1],
                                         pair=False)
                          for d2 in ((1, 0), (0, 1), (0, -1))}
                    near = [(st.owner, st.kind)
                            for st in g0.stamps
                            if st.kind == "capsule"
                            and _seg_seg_dist(
                                (st.geom[0], st.geom[1]),
                                (st.geom[2], st.geom[3]),
                                (x_x, ly), (x_x, ly)) < 0.4]
                    print(f"    seed=({x_x},{ly}) on {L} nb={nb} "
                          f"near={near[:6]}")
            for gr in grids.values():
                gr.carve_owner(-999, pts)
            return False
        # stitch: west breakout ends at (x_e, ly, L); the lane is the
        # straight to (x_x, ly, L) on the same level; east continues
        mlp = (_excise_loops(list(mlp_w)) + [(x_x, ly, L)]
               + _excise_loops(list(mlp_e))[1:])
        runs, hops = [], []
        cur_lv = mlp[0][2]
        cur = [(mlp[0][0], mlp[0][1])]
        for (x, y, Lv) in mlp[1:]:
            if Lv != cur_lv:
                hops.append((x, y, cur_lv, Lv))
                runs.append((cur_lv, cur))
                cur = [(x, y)]
                cur_lv = Lv
            else:
                cur.append((x, y))
        runs.append((cur_lv, cur))
        runs = [(Lv, _rect_simplify(grids[Lv], _compress(wq)))
                for (Lv, wq) in runs if len(wq) >= 2]
        if not runs:
            for gr in grids.values():
                gr.carve_owner(-999, pts)
            return False
        return _commit_single(e, runs, hops, prefix, tail)

    def route_member(e: _NetEnd, seed=None) -> bool:
        """Route one single net: the negotiated `(level, mid)` seed
        first (hard-validated), then ONE multi-layer search over the
        whole ladder — planar where that is cheapest, buried µvia hops
        (priced ~2.5 mm each) where a same-layer route-around would be
        longer. Ball attach levels are chosen per SIDE by the search.
        Tune matched groups against their routed reference pair. True
        on success — the caller owns the unrouted bookkeeping."""
        if (e.net in bus_lane and e.net not in _PAIR_NETS
                and _route_bus_member(e)):
            return True
        start, sdir, prefix = _escape_start(e.net, e.mpu_xy)
        goal, gdir, tail = _entry_goal(e.net, e.dram_xy)
        pts = [e.mpu_xy, e.dram_xy, start, goal]
        if seed is not None:
            lv = seed[0]
            gr = grids[lv]
            gr.carve_owner(idx_of[e.net], pts)
            s_ok, g_ok = _stub_levels(e, prefix, start, tail, goal)
            if (lv in s_ok and lv in g_ok
                    and _attach_ok(e.mpu_xy, lv)
                    and _attach_ok(e.dram_xy, lv)
                    and gr.path_clear(seed[1])):
                wp = _rect_simplify(gr, list(seed[1]))
                if _commit_single(e, [(lv, wp)], [], prefix, tail):
                    return True
            gr.carve_owner(-999, pts)
        for gr in grids.values():
            gr.carve_owner(idx_of[e.net], pts)
        s_ok, g_ok = _stub_levels(e, prefix, start, tail, goal)
        s_at = [lv for lv in s_ok if _attach_ok(e.mpu_xy, lv)]
        g_at = [lv for lv in g_ok if _attach_ok(e.dram_xy, lv)]
        if _DEBUG and e.net == os.environ.get("SMASH_DDR_PROBE"):
            print(f"  PROBE {e.net}: stub s={s_ok} g={g_ok} "
                  f"attach s={s_at} g={g_at} sdir={sdir} gdir={gdir} "
                  f"start={start} goal={goal}")
        s_ok, g_ok = s_at, g_at
        if not s_ok or not g_ok:
            for gr in grids.values():
                gr.carve_owner(-999, pts)
            return False
        paints = [(grids[lv],
                   _paint_own_stubs(grids[lv], prefix, start, goal,
                                    tail)) for lv in L_LEVELS]
        mlp = _astar_ml(grids, start, goal, start_lvls=s_ok,
                        goal_lvls=g_ok, hop_ok=_hop_maps(),
                        start_dir=sdir, goal_dir=gdir,
                        guide=plan.get(e.net) or None)
        if mlp is None:
            for gr, polys in paints:
                _unpaint_tmp(gr, polys)
            if _DEBUG:
                print(f"  miss {e.net} (ml): {_LAST_FAIL}")
            for gr in grids.values():
                gr.carve_owner(-999, pts)
            return False
        mlp = _excise_loops(list(mlp))
        # split into per-level runs + hop points
        runs, hops = [], []
        cur_lv = mlp[0][2]
        cur = [(mlp[0][0], mlp[0][1])]
        for (x, y, L) in mlp[1:]:
            if L != cur_lv:
                hops.append((x, y, cur_lv, L))
                runs.append((cur_lv, cur))
                cur = [(x, y)]
                cur_lv = L
            else:
                cur.append((x, y))
        runs.append((cur_lv, cur))
        # simplify UNDER the own-stub paint: the string-pull validates
        # its L-shortcuts against the grids, and without the paint a
        # shortcut legally slices across this net's own tail line
        runs = [(L, _rect_simplify(grids[L], _compress(wp)))
                for (L, wp) in runs if len(wp) >= 2]
        for gr, polys in paints:
            _unpaint_tmp(gr, polys)
        if not runs:
            for gr in grids.values():
                gr.carve_owner(-999, pts)
            return False
        runs_raw = [(L, list(wp)) for (L, wp) in runs]
        if e.group in ("BYTE0", "BYTE1", "AC"):
            tol = TOL_BYTE if e.group.startswith("BYTE") else TOL_AC
            board_len = (_path_len(prefix) + _path_len(tail)
                         + sum(_path_len(w) for (_l, w) in runs))
            delta = ref_total_of(e.group) - (e.pkg_mm + board_len)
            if delta > tol - 0.3:
                # tune the longest run — switchbacks want a long
                # straight host away from the BGA fields
                k = max(range(len(runs)),
                        key=lambda i: _path_len(runs[i][1]))
                wk, added = tune(runs[k][0], runs[k][1], delta)
                runs[k] = (runs[k][0], wk)
                tuned[e.net] += added
        if _commit_single(e, runs, hops, prefix, tail):
            return True
        # the tuner only sees the bare run — a pattern can land too
        # close to the composed prefix/tail. Routed-but-undertuned
        # beats unrouted: commit the raw geometry, report the miss.
        if runs != runs_raw:
            tuned[e.net] = 0.0
            return _commit_single(e, runs_raw, hops, prefix, tail)
        return False

    def _commit_single(e, runs, hops, prefix, tail) -> bool:
        """Self-validate and commit a routed single (one or more
        per-level runs + buried hop vias). False = nothing committed."""
        pts = [e.mpu_xy, e.dram_xy]
        polys = []
        for i, (L, wp) in enumerate(runs):
            poly = list(wp)
            if i == 0 and prefix:
                poly = list(prefix) + poly
            if i == len(runs) - 1 and tail:
                poly = poly + list(tail)
            polys.append((L, poly))
        for (L, poly) in polys:
            if not _self_ok(poly, SELF_TOUCH, fiction_mm=0.5):
                if _DEBUG:
                    print(f"  self-clash {e.net} on {L} (ml)")
                tuned[e.net] = 0.0
                for gr in grids.values():
                    gr.carve_owner(-999, pts)
                return False
        for (L, poly) in polys:
            commit(e.net, L, poly)
        lv_m, lv_d = runs[0][0], runs[-1][0]
        level_of[e.net] = lv_m
        attach[e.net] = (lv_m, lv_d)
        net_hops[e.net] = list(hops)
        stripped.discard(e.net)
        for (x, y, La, Lb) in hops:
            for L in (La, Lb):
                grids[L].add_disk(x, y, VIA_PAD / 2, idx_of[e.net])
        # ball lands deepen to each side's attach level
        for xy, lv in ((e.mpu_xy, lv_m), (e.dram_xy, lv_d)):
            for ly in L_LEVELS[:L_LEVELS.index(lv) + 1]:
                grids[ly].add_disk(xy[0], xy[1], _ball_r(e, xy, ly),
                                   idx_of[e.net])
        return True

    def solve_member(e, guide_override=None, force_level=None,
                     pops_cap=None, guide_w=None):
        """route_member's search half WITHOUT committing: returns a
        solution dict (runs/hops/prefix/tail/polys/vias/board_len) or
        None, leaving the grids exactly as found. Candidates for the
        decision-tree search are generated this way against the
        static+pairs grid state, so every candidate already avoids
        every net's stub reservations and the pairs."""
        start, sdir, prefix = _escape_start(e.net, e.mpu_xy)
        goal, gdir, tail = _entry_goal(e.net, e.dram_xy)
        pts = [e.mpu_xy, e.dram_xy, start, goal]
        for gr in grids.values():
            gr.carve_owner(idx_of[e.net], pts)
        s_ok, g_ok = _stub_levels(e, prefix, start, tail, goal)
        s_ok = [lv for lv in s_ok if _attach_ok(e.mpu_xy, lv)]
        g_ok = [lv for lv in g_ok if _attach_ok(e.dram_xy, lv)]
        if force_level is not None:
            s_ok = [lv for lv in s_ok if lv == force_level]
            g_ok = [lv for lv in g_ok if lv == force_level]
        sol = None
        if s_ok and g_ok:
            paints = [(grids[lv],
                       _paint_own_stubs(grids[lv], prefix, start,
                                        goal, tail))
                      for lv in L_LEVELS]
            mlp = _astar_ml(grids, start, goal, start_lvls=s_ok,
                            goal_lvls=g_ok, hop_ok=_hop_maps(),
                            start_dir=sdir, goal_dir=gdir,
                            guide=(guide_override
                                   or plan.get(e.net) or None),
                            max_pops=pops_cap or 6_000_000,
                            guide_w=(guide_w if guide_w is not None
                                     else 0.35))
            if mlp is not None:
                mlp = _excise_loops(list(mlp))
                runs, hops = [], []
                cur_lv = mlp[0][2]
                cur = [(mlp[0][0], mlp[0][1])]
                for (x, y, L) in mlp[1:]:
                    if L != cur_lv:
                        hops.append((x, y, cur_lv, L))
                        runs.append((cur_lv, cur))
                        cur = [(x, y)]
                        cur_lv = L
                    else:
                        cur.append((x, y))
                runs.append((cur_lv, cur))
                runs = [(L, _rect_simplify(grids[L], _compress(wq)))
                        for (L, wq) in runs if len(wq) >= 2]
            else:
                runs = []
            for gr, polys in paints:
                _unpaint_tmp(gr, polys)
            if runs:
                if e.group in ("BYTE0", "BYTE1", "AC"):
                    tol2 = (TOL_BYTE if e.group.startswith("BYTE")
                            else TOL_AC)
                    blen = (_path_len(prefix) + _path_len(tail)
                            + sum(_path_len(w) for (_l, w) in runs))
                    dlt = ref_total_of(e.group) - (e.pkg_mm + blen)
                    if dlt > tol2 - 0.3:
                        k = max(range(len(runs)),
                                key=lambda i: _path_len(runs[i][1]))
                        wk, _add = tune(runs[k][0], runs[k][1], dlt)
                        runs[k] = (runs[k][0], wk)
                polys2 = []
                okq = True
                for i, (L, wq) in enumerate(runs):
                    poly = list(wq)
                    if i == 0 and prefix:
                        poly = list(prefix) + poly
                    if i == len(runs) - 1 and tail:
                        poly = poly + list(tail)
                    if not _self_ok(poly, SELF_TOUCH, fiction_mm=0.5):
                        okq = False
                        break
                    polys2.append((L, poly))
                if okq:
                    blen = sum(_path_len(pq) for (_l, pq) in polys2)
                    rank_m = L_LEVELS.index(runs[0][0])
                    rank_d = L_LEVELS.index(runs[-1][0])
                    vias2 = [(e.mpu_xy[0], e.mpu_xy[1], 0, rank_m),
                             (e.dram_xy[0], e.dram_xy[1], 0, rank_d)]
                    for (x, y, La, Lb) in hops:
                        r1, r2 = sorted((L_LEVELS.index(La),
                                         L_LEVELS.index(Lb)))
                        vias2.append((x, y, r1, r2))
                    sol = {"net": e.net, "runs": runs, "hops": hops,
                           "prefix": prefix, "tail": tail,
                           "polys": polys2, "vias": vias2,
                           "board_len": blen}
        for gr in grids.values():
            gr.carve_owner(-999, pts)
        return sol

    def _sols_conflict(sa, sb):
        """Exact geometric incompatibility between two candidate
        solutions of DIFFERENT nets (audit clearance classes)."""
        for (La, pa) in sa["polys"]:
            for (Lb, pb) in sb["polys"]:
                if La != Lb:
                    continue
                for q1, q2 in zip(pa, pa[1:]):
                    for q3, q4 in zip(pb, pb[1:]):
                        if _seg_seg_dist(q1, q2, q3, q4) < 0.40:
                            return True
        for (vx, vy, r1, r2) in sa["vias"]:
            for (Lb, pb) in sb["polys"]:
                rb = L_LEVELS.index(Lb)
                if not (r1 <= rb <= r2):
                    continue
                for q3, q4 in zip(pb, pb[1:]):
                    if _seg_seg_dist((vx, vy), (vx, vy),
                                     q3, q4) < 0.25:
                        return True
        for (vx, vy, r1, r2) in sb["vias"]:
            for (La, pa) in sa["polys"]:
                ra = L_LEVELS.index(La)
                if not (r1 <= ra <= r2):
                    continue
                for q1, q2 in zip(pa, pa[1:]):
                    if _seg_seg_dist((vx, vy), (vx, vy),
                                     q1, q2) < 0.25:
                        return True
        for (ax, ay, a1, a2) in sa["vias"]:
            for (bx, by, b1, b2) in sb["vias"]:
                if a1 > b2 or b1 > a2:
                    continue
                if math.hypot(ax - bx, ay - by) < 0.40:
                    return True
        return False

    def _csp_members(member_list):
        """The decision tree per review: each net's claimed route is a
        decision, alternative routes are sibling branches. Candidates
        are generated against the static+pairs state and the pairwise
        conflict matrix is PRECOMPUTED, so the tree search itself is
        pure boolean: DFS + forward checking over bitmask domains,
        most-constrained variable first. Returns ({net: sol}, leftover
        nets for greedy fallback)."""
        cands = {}
        for e2 in member_list:
            tol2 = (TOL_BYTE if e2.group.startswith("BYTE")
                    else TOL_AC) if e2.group != "MISC" else None
            ref2 = (ref_total_of(e2.group)
                    if e2.group in ("BYTE0", "BYTE1", "AC") else None)
            est_short = (abs(e2.dram_xy[0] - e2.mpu_xy[0])
                         + abs(e2.dram_xy[1] - e2.mpu_xy[1]) + 3.0)
            dv0 = (ref2 - (e2.pkg_mm + est_short)) if ref2 else 0.0
            # DIVERSE branches: per-LEVEL forced candidates (layer
            # assignment joins the joint search — v1 generated against
            # empty grids and every net piled into the same channels,
            # max compatible subset 15/45), lateral chord shifts, and
            # deficit waypoints
            variants = [(None, None)]
            for lv2 in _levels_for(e2.group):
                variants.append((None, lv2))
            mx0 = (e2.mpu_xy[0] + e2.dram_xy[0]) / 2.0
            my0 = (e2.mpu_xy[1] + e2.dram_xy[1]) / 2.0
            for off2 in (+1.2, -1.2):
                variants.append(([e2.mpu_xy, (mx0, my0 + off2),
                                  e2.dram_xy], None))
            if dv0 > 0.6:
                off = min(dv0 / 2.0, 5.5)
                for tpos in (0.5, 0.35, 0.65):
                    mx = (e2.mpu_xy[0]
                          + (e2.dram_xy[0] - e2.mpu_xy[0]) * tpos)
                    my = (e2.mpu_xy[1]
                          + (e2.dram_xy[1] - e2.mpu_xy[1]) * tpos)
                    for sg2 in (+1, -1):
                        py = my + sg2 * off
                        if 3.0 < abs(py) < 9.8:
                            py = 10.8 if py > 0 else -10.8
                        py = max(-11.5, min(11.5, py))
                        variants.append(([e2.mpu_xy, (mx, py),
                                          e2.dram_xy], None))
            lst = []
            for (gd, flv) in variants:
                # a branch that needs >350k pops to even exist is not
                # a good decision — cap generation searches
                sol = solve_member(e2, guide_override=gd,
                                   force_level=flv,
                                   pops_cap=350_000)
                if sol is None:
                    continue
                if ref2 is not None:
                    dlt = ref2 - (e2.pkg_mm + sol["board_len"])
                    sol["delta"] = dlt
                    sol["inwin"] = abs(dlt) <= tol2 - 0.3
                else:
                    sol["delta"] = None
                    sol["inwin"] = True
                key = (sol["runs"][0][0], sol["runs"][-1][0],
                       round(sol["board_len"], 1))
                if any((s2["runs"][0][0], s2["runs"][-1][0],
                        round(s2["board_len"], 1)) == key
                       for s2 in lst):
                    continue
                lst.append(sol)
                if len(lst) >= 9:
                    break
            # in-window candidates first, then least |delta|
            lst.sort(key=lambda s2: (not s2["inwin"],
                                     abs(s2["delta"] or 0.0)))
            if lst:
                cands[e2.net] = lst
        nets = sorted(cands, key=lambda nn: len(cands[nn]))
        if _DEBUG:
            print(f"  csp: {len(nets)} vars, domain sizes "
                  f"{[len(cands[nn]) for nn in nets][:12]}…")
        # conflict matrix as compatibility bitmasks
        compat = {}
        for i, ni in enumerate(nets):
            for j in range(i + 1, len(nets)):
                nj = nets[j]
                for ki, si in enumerate(cands[ni]):
                    m = 0
                    for kj, sj in enumerate(cands[nj]):
                        if not _sols_conflict(si, sj):
                            m |= 1 << kj
                    compat[(ni, ki, nj)] = m
                    for kj in range(len(cands[nj])):
                        mm = compat.get((nj, kj, ni), 0)
                        if m >> kj & 1:
                            mm |= 1 << ki
                        compat[(nj, kj, ni)] = mm
        full = {nn: (1 << len(cands[nn])) - 1 for nn in nets}
        budget = [400000]

        def dfs(idx, dom):
            if budget[0] <= 0:
                return None
            budget[0] -= 1
            if idx == len(nets):
                return {}
            ni = nets[idx]
            d = dom[ni]
            k = 0
            while d:
                if d & 1:
                    ndom = dict(dom)
                    ok2 = True
                    for j in range(idx + 1, len(nets)):
                        nj = nets[j]
                        ndom[nj] = dom[nj] & compat.get(
                            (ni, k, nj), full[nj])
                        if ndom[nj] == 0:
                            ok2 = False
                            break
                    if ok2:
                        sub = dfs(idx + 1, ndom)
                        if sub is not None:
                            sub[ni] = k
                            return sub
                d >>= 1
                k += 1
            return None

        pick = dfs(0, dict(full))
        if pick is None:
            # no full assignment in budget — greedy-consistent fill:
            # walk variables, keep first candidate compatible with
            # all already-picked (partial > nothing)
            pick = {}
            for ni in nets:
                for k, si in enumerate(cands[ni]):
                    if all(compat.get((nj, pick[nj], ni),
                                      full[ni]) >> k & 1
                           for nj in pick):
                        pick[ni] = k
                        break
        sols = {nn: cands[nn][k] for nn, k in pick.items()}
        left = [e2 for e2 in member_list if e2.net not in sols]
        if _DEBUG:
            inw = sum(1 for s2 in sols.values() if s2["inwin"])
            print(f"  csp: assigned {len(sols)}/{len(member_list)}, "
                  f"in-window {inw}, budget left {budget[0]}")
        return sols, left

    def commit_solution(e, sol) -> bool:
        for gr in grids.values():
            gr.carve_owner(idx_of[e.net],
                           [e.mpu_xy, e.dram_xy])
        return _commit_single(e, sol["runs"], sol["hops"],
                              sol["prefix"], sol["tail"])

    def _split_at_boxes(wp):
        """Insert vertices where the (axis-aligned) path crosses the
        field-box outlines inflated by 0.2 mm, so the open-corridor run
        is bounded by explicit vertices. Crossing coords stay on the
        lattice (box edges = ball extents + 0.4 ± 0.2, all multiples of
        0.05)."""
        infl = [(b[0] - 0.2, b[1] - 0.2, b[2] + 0.2, b[3] + 0.2)
                for b in boxes]
        out = [wp[0]]
        for a, b in zip(wp, wp[1:]):
            cuts = []
            if abs(a[1] - b[1]) < 1e-9:                 # x-run
                lo, hi = sorted((a[0], b[0]))
                for (x1, y1, x2, y2) in infl:
                    if y1 <= a[1] <= y2:
                        for xc in (x1, x2):
                            if lo < xc < hi:
                                cuts.append((xc, a[1]))
                cuts.sort(key=lambda p: (p[0] - a[0]) ** 2)
            else:                                       # y-run
                lo, hi = sorted((a[1], b[1]))
                for (x1, y1, x2, y2) in infl:
                    if x1 <= a[0] <= x2:
                        for yc in (y1, y2):
                            if lo < yc < hi:
                                cuts.append((a[0], yc))
                cuts.sort(key=lambda p: (p[1] - a[1]) ** 2)
            out.extend(cuts)
            out.append(b)
        return out

    def _cut_open_run(wp_raw):
        """(split_wp, i, j) bounding the open-corridor run: the longest
        vertex span whose every segment lies clear of both (inflated)
        field boxes. The [i..j] slice is where the C leg rides at the
        constant pair offset; the in-field remainders are breakout
        territory (§6.2-exempt)."""
        wp = _split_at_boxes(wp_raw)

        def outside(p):
            return not _in_any_box(p, [(b[0] - 0.1, b[1] - 0.1,
                                        b[2] + 0.1, b[3] + 0.1)
                                       for b in boxes])

        def seg_ok(k):
            mid = ((wp[k][0] + wp[k + 1][0]) / 2,
                   (wp[k][1] + wp[k + 1][1]) / 2)
            return outside(mid)

        best = None
        k = 0
        while k < len(wp) - 1:
            if seg_ok(k):
                k2 = k
                while k2 < len(wp) - 1 and seg_ok(k2):
                    k2 += 1
                length = _path_len(wp[k:k2 + 1])
                if best is None or length > best[2]:
                    best = (k, k2, length)
                k = k2
            else:
                k += 1
        if best is None or best[2] < 1.5:
            return None
        return wp, best[0], best[1]

    def route_pair(pname, want_total_mean, guide=None):
        """T leg routed via→via in one A* (pair-width inflation outside
        the fields only). Its open-region run is offset by the constant
        0.25 mm pair pitch to make the C body (§6.2 constant gap);
        short in-field connectors tie the C body to the C vias —
        BGA-breakout territory, where every DDR layout splits its
        pairs. σ (which side C rides) is auto-retried."""
        tnet, cnet = PAIRS[pname]
        eT, eC = by_net[tnet], by_net[cnet]
        own = [eT.mpu_xy, eT.dram_xy, eC.mpu_xy, eC.dram_xy]
        startT, sdT, prefixT = _escape_start(tnet, eT.mpu_xy)
        goalT, gdT, tailT = _entry_goal(tnet, eT.dram_xy)
        startC, sdC, prefixC = _escape_start(cnet, eC.mpu_xy)
        goalCd, gdCd, tailCd = _entry_goal(cnet, eC.dram_xy)
        for layer in _levels_for(by_net[tnet].group):   # overflow, both legs
            if _route_pair_on(pname, layer, tnet, cnet, eT, eC, own,
                              startT, sdT, prefixT, goalT, gdT, tailT,
                              startC, sdC, prefixC, goalCd, gdCd, tailCd,
                              want_total_mean, guide):
                level_of[tnet] = layer
                level_of[cnet] = layer
                return
        unrouted.append(f"{pname} (pair)")

    def _route_pair_on(pname, layer, tnet, cnet, eT, eC, own,
                       startT, sdT, prefixT, goalT, gdT, tailT,
                       startC, sdC, prefixC, goalCd, gdCd, tailCd,
                       want_total_mean, guide):
        gr = grids[layer]
        # Only T's OWN lands/stub tips are carved for the T-leg A* —
        # C's via pads and stubs stay hard obstacles so T can't route
        # through its partner (the C connectors use the skip-owner view).
        gr.carve_owner(idx_of[tnet],
                       [eT.mpu_xy, eT.dram_xy, startT, goalT])
        if ((tnet in stripped or layer != stub_home[tnet]) and not (
                (not prefixT or gr.path_clear(list(prefixT) + [startT]))
                and (not tailT or gr.path_clear([goalT] + list(tailT))))):
            gr.carve_owner(-999, own)
            return False
        if ((cnet in stripped or layer != stub_home[cnet])
                and prefixC and not gr.path_clear(
                    list(prefixC) + [startC])):
            gr.carve_owner(-999, own)
            return False
        own_paint = _paint_own_stubs(gr, prefixT, startT, goalT, tailT)
        wp_raw = _astar(gr, startT, goalT, pair="open", margin=4.0,
                        start_dir=sdT, goal_dir=gdT, guide=guide)
        _unpaint_tmp(gr, own_paint)
        if wp_raw is not None:
            wp_raw = _rect_simplify(gr, wp_raw, pair="open")
        # T's own lands go straight back in: the C-leg clearance checks
        # below must see them (they were carved only for T's A*)
        for xy in (eT.mpu_xy, eT.dram_xy):
            gr.add_disk(xy[0], xy[1], VIA_PAD / 2, idx_of[tnet])
        if wp_raw is not None:
            wp_raw = prefixT + wp_raw + tailT
        cut = _cut_open_run(wp_raw) if wp_raw is not None else None
        if cut is None:
            if _DEBUG:
                print(f"  PAIR {pname} miss on {layer}: T leg "
                      f"{'A* fail: ' + _LAST_FAIL if wp_raw is None else 'no open-run cut'}")
            gr.carve_owner(-999, own)       # repaint everything
            return False
        wp, i, j = cut

        # pairs commit UNTUNED: per-segment normal offset of a pattern
        # flips side on alternating legs and the C copy self-touches.
        # Length targets are met POST-commit by _stretch_pair (rigid
        # translated C patterns), while the corridor is still empty.
        mid = wp[i:j + 1]
        for offs_try in (+(TRACE_W + DIFF_GAP), -(TRACE_W + DIFF_GAP)):
            mid_t, added = list(mid), 0.0
            cbody = _offset_leg(mid_t, offs_try)
            if not gr.path_clear(cbody, pair=False):
                continue
            wp_t = list(wp[:i]) + mid_t + list(wp[j + 1:])
            if (not _self_ok(wp_t, SELF_TOUCH, fiction_mm=0.5)
                    or not _self_ok(cbody, SELF_TOUCH,
                                    fiction_mm=0.5)):
                continue
            # C connectors: from the C vias to the C-body ends, in the
            # §6.2-exempt view (T at field radius, C's own lands skipped)
            d0 = _dir_index(mid_t[0], mid_t[1])
            d1 = _dir_index(mid_t[-2], mid_t[-1])
            commit(tnet, layer, wp_t)
            # the C net's own stubs go in as transient hard paint: the
            # views SKIP C's reserved stamps, so its connectors could
            # otherwise cross C's own future stub copper
            c_paint = _paint_own_stubs(gr, prefixC, startC, goalCd,
                                       tailCd)
            vm = gr.relaxed_view(
                {idx_of[tnet]}, {idx_of[cnet]},
                min(startC[0], cbody[0][0]) - 2.5,
                min(startC[1], cbody[0][1]) - 2.5,
                max(startC[0], cbody[0][0]) + 2.5,
                max(startC[1], cbody[0][1]) + 2.5)
            con_m = _astar(vm, startC, cbody[0], start_dir=sdC,
                           goal_dir=d0, margin=2.5)
            if con_m is not None:
                # string-pull in the view: the skip-owner view can't
                # see the C net's own stub, so the raw connector may
                # hug it at one-cell spacing — the L replacement
                # passes the self-rule
                con_m = prefixC + _rect_simplify(vm, con_m)
            vd = gr.relaxed_view(
                {idx_of[tnet]}, {idx_of[cnet]},
                min(goalCd[0], cbody[-1][0]) - 2.5,
                min(goalCd[1], cbody[-1][1]) - 2.5,
                max(goalCd[0], cbody[-1][0]) + 2.5,
                max(goalCd[1], cbody[-1][1]) + 2.5)
            con_d = _astar(vd, cbody[-1], goalCd, start_dir=d1,
                           goal_dir=gdCd, margin=2.5)
            if con_d is not None:
                con_d = list(_rect_simplify(vd, con_d)) + tailCd
            _unpaint_tmp(gr, c_paint)
            if con_m is None or con_d is None:
                if _DEBUG:
                    print(f"  PAIR {pname} σ={offs_try:+.2f}: con_m="
                          f"{'ok' if con_m else _LAST_FAIL} "
                          f"con_d={'ok' if con_d else 'FAIL'} "
                          f"cb0={cbody[0]} cb-1={cbody[-1]} "
                          f"d0={d0} d1={d1}")
                # wrong σ — unwind the committed T leg and flip sides
                _uncommit(tnet, layer, wp_t)
                continue
            full_c = list(con_m) + list(cbody[1:-1]) + list(con_d)
            if not _self_ok(full_c, SELF_TOUCH, fiction_mm=0.5):
                if _DEBUG:
                    print(f"  PAIR {pname} σ={offs_try:+.2f}: C self-clash")
                _uncommit(tnet, layer, wp_t)
                continue
            tuned[tnet] += added
            tuned[cnet] += added
            commit(cnet, layer, full_c)
            for e in (eT, eC):
                # pairs are single-level: both balls attach at `layer`
                # (via emission reads `attach` — leaving it unset cost
                # all six pair nets their ball stacks, found by user
                # inspection: an In1 track starting ON the M17 pad)
                attach[e.net] = (layer, layer)
                net_hops[e.net] = []
                for xy in (e.mpu_xy, e.dram_xy):
                    for ly in L_LEVELS[:L_LEVELS.index(layer) + 1]:
                        grids[ly].add_disk(xy[0], xy[1],
                                           _ball_r(e, xy, ly),
                                           idx_of[e.net])
            pair_skew[pname] = abs(routed_len.get(tnet, 0.0)
                                   - routed_len.get(cnet, 0.0))
            stripped.discard(tnet)
            stripped.discard(cnet)
            return True
        if _DEBUG:
            print(f"  PAIR {pname} miss on {layer}: C leg (both σ)")
        gr.carve_owner(-999, own)
        return False

    def _uncommit(net, layer, wp):
        """Remove the just-committed path again (σ retry)."""
        owner = idx_of[net]
        gr = grids[layer]
        gr.stamps = [st for st in gr.stamps
                     if not (st.owner == owner and st.kind == "capsule")]
        nonlocal tracks
        tracks = [t for t in tracks if t.net != net]
        routed_len.pop(net, None)
        # repaint the affected corridor exactly
        xs = [p[0] for p in wp]; ys = [p[1] for p in wp]
        step = 1.6
        pts = []
        x1, x2 = min(xs) - 0.8, max(xs) + 0.8
        y1, y2 = min(ys) - 0.8, max(ys) + 0.8
        xx = x1
        while xx <= x2:
            yy = y1
            while yy <= y2:
                pts.append((xx, yy))
                yy += step
            xx += step
        gr.carve_owner(-999, pts)

    # ── routing sequence: plan order (refs first within each region) ──
    _G_OF_PAIR = {"DQS0": "BYTE0", "DQS1": "BYTE1", "CK": "AC"}

    def ref_total_of(gname):
        t, c = PAIRS[{"BYTE0": "DQS0", "BYTE1": "DQS1", "AC": "CK"}[gname]]
        return ((routed_len.get(t, 0.0) + by_net[t].pkg_mm)
                + (routed_len.get(c, 0.0) + by_net[c].pkg_mm)) / 2.0

    # pairs first — their routed lengths fix the per-group tuning targets
    def _phase_targets():
        """Sweep the per-group reference TOTAL that maximises in-tol
        members, given phase-1's measured lengths. Members can still
        ADD ~3 mm at route time (never subtract); the pair can only be
        LENGTHENED beyond its natural minimum (current minus its own
        patterns), up to ~18 mm in the empty corridor. Only groups
        whose projected miss count improves return a target — phase 2
        re-routes everything with the pair pre-stretched while the
        corridor still has room."""
        out = {}
        for (g, pname, tol) in (("AC", "CK", TOL_AC),
                                ("BYTE0", "DQS0", TOL_BYTE),
                                ("BYTE1", "DQS1", TOL_BYTE)):
            Ls = [by_net[nn].pkg_mm + routed_len[nn]
                  for nn in routed_len
                  if nn in by_net and by_net[nn].group == g
                  and nn not in _PAIR_NETS]
            if not Ls:
                continue
            cur_ref = ref_total_of(g)
            cur_miss = sum(1 for L in Ls if abs(cur_ref - L) > tol)
            tnet, _cn = PAIRS[pname]
            nat_min = cur_ref - tuned.get(tnet, 0.0)
            best = None
            r = nat_min
            while r <= nat_min + 18.0:
                miss = sum(1 for L in Ls
                           if not (-(tol - 0.3) <= r - L
                                   <= (tol - 0.3) + 3.0))
                if best is None or miss < best[0]:
                    best = (miss, r)
                r += 0.2
            if best is not None and best[0] < cur_miss:
                out[g] = best[1]
        return out

    def _snapshot_net(net):
        return ([(t.layer, [tuple(q) for q in t.path])
                 for t in tracks if t.net == net],
                routed_len.get(net), level_of.get(net),
                attach.get(net), list(net_hops.get(net, ())),
                tuned.get(net, 0.0))

    def _remove_net(net):
        nonlocal tracks
        owner = idx_of[net]
        for gr in grids.values():
            gr.stamps = [st for st in gr.stamps if st.owner != owner]
            gr.repaint_all()
        tracks = [t for t in tracks if t.net != net]
        routed_len.pop(net, None)
        level_of.pop(net, None)
        attach.pop(net, None)
        net_hops.pop(net, None)
        tuned[net] = 0.0
        e = by_net[net]
        depth = L_LEVELS.index(_levels_for(e.group)[0]) + 1
        for xy in (e.mpu_xy, e.dram_xy):
            for ly in L_LEVELS[:depth]:
                grids[ly].add_disk(xy[0], xy[1], _ball_r(e, xy, ly),
                                   idx_of[net])
        for side in ("mpu", "dram"):
            if (side, net) in ref_stubs:
                grids[stub_home[net]].add_path(ref_stubs[(side, net)],
                                               TRACE_W / 2, idx_of[net])
        if net in stubs:
            grids[stub_home[net]].add_path(stubs[net][0], TRACE_W / 2,
                                           idx_of[net])

    def _restore_net(net, snap):
        polys, _rl, lv, at, hops, tn = snap
        for (ly, path) in polys:
            commit(net, ly, path)
        level_of[net] = lv
        attach[net] = at
        net_hops[net] = hops
        tuned[net] = tn
        e = by_net[net]
        for (x, y, La, Lb) in hops:
            for L in (La, Lb):
                grids[L].add_disk(x, y, VIA_PAD / 2, idx_of[net])
        for xy, lvv in ((e.mpu_xy, at[0]), (e.dram_xy, at[1])):
            for ly in L_LEVELS[:L_LEVELS.index(lvv) + 1]:
                grids[ly].add_disk(xy[0], xy[1], _ball_r(e, xy, ly),
                                   idx_of[net])


    pair_target = dict(target_est)
    _ph_hist = []
    for _phase in range(3):
        def _lengthen_pair(pname, need):
            """Matched away-side patterns on BOTH legs of a routed pair —
            the group reference rises by the added length; gap and skew
            are preserved by construction."""
            tnet, cnet = PAIRS[pname]
            if tuned.get(tnet, 0.0) > 0.05:
                return 0.0          # one structure per route
            tt = [t for t in tracks if t.net == tnet]
            ct = [t for t in tracks if t.net == cnet]
            if len(tt) != 1 or len(ct) != 1:
                return 0.0
            tt, ct = tt[0], ct[0]
            # merge collinear chains first: a pattern's base segments
            # are COLLINEAR with the host line's continuation — on an
            # uncompressed path the strict spacing check sees them as
            # non-adjacent segments at distance zero and rejects every
            # candidate (members never hit this: tune() works on
            # compressed runs)
            tt.path = _compress([tuple(q) for q in tt.path])
            ct.path = _compress([tuple(q) for q in ct.path])
            for o in (idx_of[tnet], idx_of[cnet]):
                for gr in grids.values():
                    gr.stamps = [st for st in gr.stamps
                                 if not (st.owner == o
                                         and st.kind == "capsule")]
                    gr.repaint_all()
            added = 0.0
            stuck = False
            rej = {"cand": 0, "apex": 0, "self45": 0, "gridT": 0,
                   "host": 0, "selfC": 0, "gridC": 0}
            while added < need - 0.3 and not stuck:
                stuck = True
                for c, ach, _sd, ins in _accordion_candidates(
                        tt.path, need - added):
                    rej["cand"] += 1
                    res = need - added
                    if abs(res - ach) >= abs(res) - 0.05:
                        continue    # would not shrink the residual
                    # away-side only: the bump APEX must move away from C
                    # (the pattern's first/last points sit ON the T line,
                    # 0.25 from C by construction — testing them rejects
                    # every candidate)
                    apex = c[ins[0] + 2]
                    if min(_seg_seg_dist(apex, apex, a, b)
                           for a, b in zip(ct.path, ct.path[1:])) < 0.5:
                        rej["apex"] += 1
                        continue
                    if not _self_ok(c, SB_H - 0.10,
                                    ins[0] + 1, ins[1] - 1):
                        rej["self45"] += 1
                        continue
                    if not grids[tt.layer].path_clear(c):
                        rej["gridT"] += 1
                        continue
                    # mirrored pattern on the C leg, same host position
                    host_a, host_b = c[ins[0]], c[ins[1]]
                    cc = None
                    hlen = math.hypot(host_b[0] - host_a[0],
                                      host_b[1] - host_a[1])
                    for k, (a, b) in enumerate(zip(ct.path,
                                                   ct.path[1:])):
                        # congruent host only: a mismatched C segment adds
                        # a different length than T's and the skew drifts
                        if abs(math.hypot(b[0] - a[0], b[1] - a[1])
                               - hlen) > 0.1:
                            continue
                        if _seg_seg_dist(a, b, host_a, host_a) < 0.35 \
                                and _seg_seg_dist(a, b, host_b,
                                                  host_b) < 0.35:
                            off = (a[0] - host_a[0] + b[0] - host_b[0],
                                   a[1] - host_a[1] + b[1] - host_b[1])
                            off = (off[0] / 2.0, off[1] / 2.0)
                            patt = [(q[0] + off[0], q[1] + off[1])
                                    for q in c[ins[0] + 1:ins[1]]]
                            cc = (list(ct.path[:k + 1]) + patt
                                  + list(ct.path[k + 1:]))
                            break
                    if cc is None:
                        rej["host"] += 1
                        continue
                    if not _self_ok(cc, SELF_TOUCH, fiction_mm=0.5):
                        rej["selfC"] += 1
                        continue
                    if not grids[ct.layer].path_clear(cc):
                        rej["gridC"] += 1
                        continue
                    tt.path = [tuple(q) for q in c]
                    ct.path = [tuple(q) for q in cc]
                    added += ach
                    stuck = False
                    break
            for o, t in ((idx_of[tnet], tt), (idx_of[cnet], ct)):
                grids[t.layer].add_path(t.path, TRACE_W / 2, o)
            if _DEBUG:
                print(f"  retune: pair {pname} want={need:.2f} "
                      f"added={added:.2f} rej={rej}")
            if added:
                routed_len[tnet] = _path_len(tt.path)
                routed_len[cnet] = _path_len(ct.path)
                tuned[tnet] = tuned.get(tnet, 0.0) + added
                tuned[cnet] = tuned.get(cnet, 0.0) + added
                if _DEBUG:
                    print(f"  retune: pair {pname} +{added:.2f} mm")
            return added


        if (_phase == 0 and os.environ.get("SMASH_DDR_TREE")
                and not os.environ.get("SMASH_DDR_CSP")):
            # FEASIBLE REFERENCES (the campaign's deepest finding):
            # some members' geometric MINIMUM exceeds the pair's
            # natural length by >10 mm (east-flank DRAM wraps) — no
            # variant can subtract length, so a window centred on the
            # natural pair is UNSATISFIABLE and the tree underflows
            # at node 0. Measure every member's direct minimum in the
            # empty corridor and raise each pair target to the
            # longest member's floor; everyone else ADDS length via
            # tuned variants.
            _gmin = {}
            for e3 in (by_net[nm] for kd, nm in order_list
                       if kd == "net"):
                if e3.group not in ("BYTE0", "BYTE1", "AC"):
                    continue
                d3 = solve_member(e3, pops_cap=2_000_000)
                if d3 is None:
                    continue
                L3 = e3.pkg_mm + d3["board_len"]
                if L3 > _gmin.get(e3.group, 0.0):
                    _gmin[e3.group] = L3
            for g3, pn3 in (("BYTE0", "DQS0"), ("BYTE1", "DQS1"),
                            ("AC", "CK")):
                tol3 = TOL_BYTE if g3.startswith("BYTE") else TOL_AC
                if g3 in _gmin:
                    floor3 = _gmin[g3] - (tol3 - 0.6)
                    if floor3 > pair_target[g3]:
                        if _DEBUG:
                            print(f"  feasible ref {g3}: "
                                  f"{pair_target[g3]:.2f} → "
                                  f"{floor3:.2f}")
                        pair_target[g3] = floor3

        for kind, name in order_list:
            if kind == "pair":
                # LENGTH-DRIVEN pair routing: chord-guided pairs hug
                # the field walls (in-field surcharge), leaving no
                # hostable side for ANY stretch primitive — six
                # generations of post-hoc stretching starved on that
                # geometry. Instead, when the target demands extra
                # length, route the body through an off-chord waypoint
                # sized to the deficit: the detour IS the length,
                # crossing open corridor; U-dips close the residual.
                tnet0, _cn0 = PAIRS[name]
                eT0 = by_net[tnet0]
                gpr = _G_OF_PAIR[name]
                chord = (abs(eT0.dram_xy[0] - eT0.mpu_xy[0])
                         + abs(eT0.dram_xy[1] - eT0.mpu_xy[1]))
                est = chord + 3.0           # + breakout overhead
                want_pre = (pair_target[gpr]
                            - ((eT0.pkg_mm + by_net[_cn0].pkg_mm) / 2.0
                               + est))
                guide0 = plan.get(PAIRS[name][0]) or None
                if want_pre > 1.5:
                    mx = (eT0.mpu_xy[0] + eT0.dram_xy[0]) / 2.0
                    my = (eT0.mpu_xy[1] + eT0.dram_xy[1]) / 2.0
                    sgn0 = 1.0 if my > 0 else -1.0
                    py = my + sgn0 * (want_pre / 2.0)
                    # parking INSIDE the byte escape bands (|y| 3…9.8)
                    # displaces members and the keep-best reverts the
                    # whole phase — jump BEYOND to the rim (transit
                    # crossings are cheap; parking is what kills).
                    # Overshot references are fine: members close any
                    # residual continuously.
                    if 3.0 < abs(py) < 9.8:
                        py = sgn0 * 10.8
                    py = max(-11.5, min(11.5, py))
                    P = (mx, py)
                    guide0 = [eT0.mpu_xy, P, eT0.dram_xy]
                    if _DEBUG:
                        print(f"  pair {name}: detour waypoint "
                              f"{P} for +{want_pre:.1f}")
                route_pair(name, pair_target[gpr], guide=guide0)
                if not any(u.startswith(name) for u in unrouted):
                    want_p = pair_target[gpr] - ref_total_of(gpr)
                    if want_p > 0.3:
                        _lengthen_pair(name, want_p)
        singles = [by_net[name] for kind, name in order_list if kind == "net"]

        # ── PathFinder negotiated congestion (singles) ─────────────────────
        # Sequential routing with hard blocking deadlocks on shared
        # resources (whoever routes first wins arbitrarily). Here the
        # singles negotiate instead: other nets' claims are SOFT costs —
        # `present` (current sharing, escalating weight) and `history`
        # (accumulated contention) — so contested cells stay usable but get
        # progressively expensive until the nets spread across the corridor
        # and the four levels by themselves. Static copper stays HARD
        # (pads, lands, holes, the routed pairs, stub reservations on their
        # home levels). The negotiated solution is then committed through
        # the ordinary hard-validated path, so the output is exactly as
        # strict as before — negotiation only chooses better seeds.
        # MEASURED (placed board): negotiation v1 = 40/52 + 4 violations vs
        # the sequential pass's 44/52 + 0 — half-converged negotiation seeds
        # nets into contested space and their fallbacks then lose to space
        # other seeds consumed. OPT-IN via SMASH_DDR_NEGOTIATE=1 until the
        # commit-order + convergence defects are fixed; the sequential pass
        # below stays the default.
        NEGOTIATE = bool(os.environ.get("SMASH_DDR_NEGOTIATE"))
        NEGO_IT = 12
        W_P0, W_P_RAMP, H_INC = 3.0, 2.0, 1.0
        shape = (grids[L_LEVELS[0]].nx, grids[L_LEVELS[0]].ny)
        pres = {lv: np.zeros(shape, np.int16) for lv in L_LEVELS}
        hist = {lv: np.zeros(shape, np.float32) for lv in L_LEVELS}
        claims = {}                 # net → (lv, mid, flat footprint indices)

        def _footprint(gr, wp):
            """Flat cell indices a polyline claims: half the required
            centre-to-centre spacing per region, so two nets sharing a cell
            ⇔ their centrelines are too close."""
            tmp = np.zeros(shape, bool)
            for a, b in zip(wp, wp[1:]):
                if a == b:
                    continue
                mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                inf = gr.in_field[gr._ix(mid[0]), gr._iy(mid[1])]
                st = _Stamp("capsule", (a[0], a[1], b[0], b[1]), 0.0, -1)
                gr._mask_into(tmp, st, 0.09 if inf else 0.20)
            return np.flatnonzero(tmp)

        def _claim(net, lv, mid, prefix, tail):
            idx = _footprint(grids[lv], list(prefix) + list(mid) + list(tail))
            pres[lv].reshape(-1)[idx] += 1
            claims[net] = (lv, mid, idx)

        def _unclaim(net):
            lv, _mid, idx = claims.pop(net)
            pres[lv].reshape(-1)[idx] -= 1

        def _nego_route(e, w_p):
            """Soft-cost A* across the net's ladder; min-cost level wins.
            Levels where the (immovable) stub geometry is hard-blocked are
            not candidates — the final commit would bounce them anyway."""
            start, sdir, prefix = _escape_start(e.net, e.mpu_xy)
            goal, gdir, tail = _entry_goal(e.net, e.dram_xy)
            pts = [e.mpu_xy, e.dram_xy, start, goal]
            best = None
            for lv in _levels_for(e.group):
                gr = grids[lv]
                gr.carve_owner(idx_of[e.net], pts)
                stub_ok = (lv == stub_home[e.net] or (
                    (not prefix or gr.path_clear(list(prefix) + [start]))
                    and (not tail or gr.path_clear([goal] + list(tail)))))
                wp = None
                if stub_ok:
                    # negotiation A* is bounded: soft costs leave no hard
                    # walls to prune the search, so a blown-up query just
                    # forfeits this level for this iteration (greedier
                    # heuristic too — the final commit pass re-validates)
                    wp = _astar(gr, start, goal, margin=4.0, start_dir=sdir,
                                goal_dir=gdir, guide=plan.get(e.net) or None,
                                cong=(pres[lv], hist[lv], w_p),
                                max_pops=150_000, h_weight=1.3)
                gr.carve_owner(-999, pts)       # nothing committed here
                if wp is not None and (best is None or _LAST_COST < best[3]):
                    best = (lv, wp, (prefix, tail), _LAST_COST)
            return best

        nego_order = [e for e in singles] if NEGOTIATE else []
        for e in nego_order:                    # seed in sweep order
            r = _nego_route(e, W_P0)
            if r is not None:
                _claim(e.net, r[0], r[1], *r[2])
        for it in range(1, NEGO_IT + 1):
            contested = [e for e in nego_order if e.net in claims
                         and (pres[claims[e.net][0]].reshape(-1)
                              [claims[e.net][2]] > 1).any()]
            if not contested:
                break
            for lv in L_LEVELS:
                hist[lv][pres[lv] > 1] += H_INC
            w_p = W_P0 + W_P_RAMP * it
            if _DEBUG:
                print(f"  nego it{it}: {len(contested)} contested, "
                      f"w_p={w_p}")
            for e in contested:
                _unclaim(e.net)
                r = _nego_route(e, w_p)
                if r is not None:
                    _claim(e.net, r[0], r[1], *r[2])

        def _release_reservations(names):
            """Free the listed nets' capsule stamps (stub reservations and
            any committed copper) on every level, with exact repaint."""
            for name in names:
                owner = idx_of[name]
                for gr in grids.values():
                    doomed = [st for st in gr.stamps
                              if st.owner == owner and st.kind == "capsule"]
                    if not doomed:
                        continue
                    gr.stamps = [st for st in gr.stamps
                                 if not (st.owner == owner
                                         and st.kind == "capsule")]
                    xs = [c for st in doomed
                          for c in (st.geom[0], st.geom[2])]
                    ys = [c for st in doomed
                          for c in (st.geom[1], st.geom[3])]
                    pts2 = []
                    xx = min(xs) - 0.8
                    while xx <= max(xs) + 0.8:
                        yy = min(ys) - 0.8
                        while yy <= max(ys) + 0.8:
                            pts2.append((xx, yy))
                            yy += 1.6
                        xx += 1.6
                    gr.carve_owner(-999, pts2)
                stripped.add(name)

        def _run_singles(order_names):
            """One sequential pass over `order_names` (+ the dead-reservation
            release-and-retry round). Returns the unrouted name list."""
            missed = []
            for name in order_names:
                e = by_net[name]
                cl = claims.get(e.net)
                if not route_member(e, seed=(cl[0], cl[1]) if cl else None):
                    missed.append(e.net)
            if missed:
                retry, missed = list(missed), []
                _release_reservations(retry)
                for name in retry:
                    if not route_member(by_net[name]):
                        missed.append(name)
            return missed

        def _teardown_singles():
            """Strip every single's copper, reservations, hop-via lands and
            attach bookkeeping, then restore stub reservations + prior-depth
            ball lands — back to the pre-pass state (pairs untouched)."""
            nonlocal tracks
            single_names = {e.net for e in singles}
            owners = {idx_of[n] for n in single_names}
            for gr in grids.values():
                gr.stamps = [st for st in gr.stamps
                             if st.owner not in owners]
                gr.repaint_all()
            tracks = [t for t in tracks if t.net not in single_names]
            for n in single_names:
                routed_len.pop(n, None)
                level_of.pop(n, None)
                attach.pop(n, None)
                net_hops.pop(n, None)
                tuned[n] = 0.0
            stripped.clear()
            for e in singles:                   # prior-depth ball lands
                depth = L_LEVELS.index(_levels_for(e.group)[0]) + 1
                for xy in (e.mpu_xy, e.dram_xy):
                    for ly in L_LEVELS[:depth]:
                        grids[ly].add_disk(xy[0], xy[1],
                                           _ball_r(e, xy, ly),
                                           idx_of[e.net])
            for (side, n), swp in ref_stubs.items():
                if n in single_names:
                    grids[stub_home[n]].add_path(swp, TRACE_W / 2, idx_of[n])
            for n, (swp, _sd) in stubs.items():
                if n in single_names:
                    grids[stub_home[n]].add_path(swp, TRACE_W / 2, idx_of[n])

        # ── difficulty-first restarts ──────────────────────────────────────
        # Most-constrained-first, with the constraint learned rather than
        # guessed: run the proven sweep order, hoist the ACTUAL failures to
        # the front (keeping their internal sweep order, so same-edge
        # neighbours still nest), tear down and re-run. Ordering changes
        # are zero-sum in general, so every attempt is scored and the best
        # order is reproduced for the final state — the result can only
        # match or beat the single-pass router.
        if os.environ.get("SMASH_DDR_CSP"):
            # OPT-IN: the decision-tree search is built and instant,
            # but candidate GENERATION is the measured bottleneck —
            # in the static state most nets have ONE natural route
            # per stub-valid level (29/45 single-candidate, 16/45
            # none under the pop cap), so the tree has no branches.
            # v3 spec: enumerate BUS LANES as the domain values —
            # lanes are exactly the discrete, diverse, conflict-sparse
            # alternatives this formulation needs.
            # decision-tree member phase (per review): candidates =
            # branches, conflict matrix precomputed, boolean DFS picks
            # a jointly compatible in-window assignment; greedy fills
            # whatever the tree could not place. The order-restart
            # machinery is bypassed — it would tear down the JOINT
            # solution it cannot reconstruct net-by-net.
            sols_csp, left_csp = _csp_members(singles)
            csp_done = set()
            for nn in [e2.net for e2 in singles if e2.net in sols_csp]:
                if commit_solution(by_net[nn], sols_csp[nn]):
                    csp_done.add(nn)
                else:
                    left_csp.append(by_net[nn])
            missed = _run_singles(
                [e2.net for e2 in singles if e2.net not in csp_done])
            unrouted.extend(missed)
        else:
            # ── sequential decision tree, chronological backtracking ──
            # Per review (exact spec): each net's claimed route is a
            # decision, alternatives are branches. NO rips — an
            # unroutable net (or one with NO in-window variant) is a
            # branch TERMINATION: backtrack, uncommit the previous
            # decision, advance ITS cursor; a node is left only when
            # all its viable variants are exhausted. Variants are
            # generated IN CONTEXT (against the committed prefix —
            # this supplies the branch diversity static generation
            # provably lacked), admissible = in-window for matched
            # groups (routed, for MISC), ordered shortest first.
            # ── lane catalog: the corridor as owned slots ─────────
            # A lane = an exclusive strip (level, y) spanning the
            # inter-field corridor (inboard of the S-2S-inflated
            # reservation bands). Two different lanes are disjoint
            # copper BY DEFINITION, and lane distance from a net's
            # natural band modulates total length (~2·Δy of breakout)
            # — so ranking free lanes by predicted window fit gives
            # each net a LADDER OF LENGTHS, and the in-slot trombone
            # closes the residual exactly. Lanes are the tree's
            # domain values; the certificate's shared-slot contention
            # cannot exist between them.
            LANE_X0, LANE_X1 = -1.9, 1.9
            _LANE_LVLS = ("In1.Cu", "In3.Cu", "In4.Cu", "In5.Cu")
            lanes_all = []
            y4 = -10.8
            while y4 <= 10.8:
                lanes_all.append(round(y4, 2))     # y-slot; the ROUTE
                y4 += 0.8                          # picks the level

            lane_used = {}
            lane_of = {}

            def _lane_free(y4):
                # exclusivity at claim: same level within 1.2 of an
                # owned slot is taken (trombone amplitude ±0.5)
                return not any(abs(y4 - y2) < 0.05
                               for (_L2, y2) in lane_used)

            def _solve_lane(e3, y4):
                """Lane candidate via the PROVEN generator: a single-level
                full route guided through both lane ends (the hand-stitched
                two-search version pop-capped — exact-point single-level
                goals flood the window when strong guides starve the
                heuristic; stub→stub with free arrival does not)."""
                start4 = _escape_start(e3.net, e3.mpu_xy)[0]
                goal4 = _entry_goal(e3.net, e3.dram_xy)[0]
                gd4 = [start4, (LANE_X0, y4), (LANE_X1, y4), goal4]
                # FREE level (east-flank breakouts need hops; forcing
                # one level made them explode) — then VERIFY the route
                # genuinely traverses the slot on the lane's level and
                # claim it: soft guidance converted into ownership.
                sol4 = solve_member(e3, guide_override=gd4,
                                    pops_cap=800_000, guide_w=2.5)
                global _LAST_FAIL
                if sol4 is not None:
                    # LANE SNAPPING: guided routes traverse the slot
                    # but wiggle (verification rejected everything) —
                    # so REPLACE the corridor crossing with the exact
                    # lane segment: splice (X0,y_in)→(X0,y4)→(X1,y4)→
                    # (X1,y_out) into the crossing run, validate,
                    # recompute, claim as-routed.
                    snapped = None
                    why4 = "nospan"
                    for ri4, (Lv4, wq4) in enumerate(sol4["runs"]):
                        xs4 = [q[0] for q in wq4]
                        # PARTIAL-SPAN: routes may hop mid-corridor —
                        # snap whatever portion of this run overlaps
                        # the slot (≥1.6 for trombone room)
                        cx04 = max(LANE_X0, min(xs4) + 0.05)
                        cx14 = min(LANE_X1, max(xs4) - 0.05)
                        if cx14 - cx04 < 1.6:
                            continue
                        rev4 = wq4[0][0] > wq4[-1][0]
                        wd4 = list(reversed(wq4)) if rev4 else \
                            list(wq4)
                        try:
                            i04 = max(i for i, q in enumerate(wd4)
                                      if q[0] <= cx04)
                            i14 = min(i for i, q in enumerate(wd4)
                                      if q[0] >= cx14)
                        except ValueError:
                            continue
                        if i04 >= i14:
                            continue

                        def _xat(pa, pb, X):
                            if abs(pb[0] - pa[0]) < 1e-9:
                                return (X, pa[1])
                            t5 = (X - pa[0]) / (pb[0] - pa[0])
                            return (X, pa[1]
                                    + (pb[1] - pa[1]) * t5)
                        pin4 = _xat(wd4[i04], wd4[i04 + 1], cx04)
                        pout4 = _xat(wd4[i14 - 1], wd4[i14], cx14)
                        if (abs(pin4[1] - y4) > 6.0
                                or abs(pout4[1] - y4) > 6.0):
                            why4 = "far"
                            continue
                        # long stitches are NOT a defect: the stitch
                        # verticals ARE the lane detour applied
                        # post-hoc (~2·Δy, exactly what the lane was
                        # ranked for); the window filter judges.
                        mid4 = [pin4, (cx04, y4), (cx14, y4),
                                pout4]
                        new4 = (wd4[:i04 + 1] + mid4 + wd4[i14:])
                        if rev4:
                            new4 = list(reversed(new4))
                        new4 = _compress([tuple(q) for q in new4])
                        if not grids[Lv4].path_clear(new4):
                            why4 = "clearfail"
                            continue
                        snapped = (ri4, Lv4, new4)
                        break
                    if snapped is None:
                        _LAST_FAIL = "snap-" + why4
                        return None
                    ri4, Lgot, new4 = snapped
                    if any(Lgot == L2 and abs(y4 - y2) < 1.2
                           for (L2, y2) in lane_used):
                        _LAST_FAIL = "slot-taken"
                        return None
                    sol4["runs"][ri4] = (Lgot, new4)
                    # recompose polys + length from the snapped runs
                    polys5 = []
                    for i5, (Lv5, wq5) in enumerate(sol4["runs"]):
                        poly5 = list(wq5)
                        if i5 == 0 and sol4["prefix"]:
                            poly5 = list(sol4["prefix"]) + poly5
                        if (i5 == len(sol4["runs"]) - 1
                                and sol4["tail"]):
                            poly5 = poly5 + list(sol4["tail"])
                        if not _self_ok(poly5, SELF_TOUCH,
                                        fiction_mm=0.5):
                            _LAST_FAIL = "snap-self"
                            return None
                        polys5.append((Lv5, poly5))
                    sol4["polys"] = polys5
                    sol4["board_len"] = sum(
                        _path_len(pq5) for (_l5, pq5) in polys5)
                    sol4["lane"] = (Lgot, y4)
                return sol4

            def _trombone_sol(e3, sol4, need4):
                """Close the residual EXACTLY inside the owned slot:
                U-dips on the lane segment, amp ±0.5, continuous."""
                L4, y4 = sol4["lane"]
                amp4 = 0.5
                if need4 < 0.1:
                    return True
                if need4 > 3.4:
                    return False
                for ri4, (Lv4, wq4) in enumerate(sol4["runs"]):
                    if Lv4 != L4:
                        continue
                    for si4, (a4, b4) in enumerate(
                            zip(wq4, wq4[1:])):
                        if (abs(a4[1] - y4) < 0.05
                                and abs(b4[1] - y4) < 0.05
                                and abs(b4[0] - a4[0]) > 2.0):
                            x04, x14 = sorted((a4[0], b4[0]))
                            x04 += 0.3
                            inner4 = []
                            xc4 = x04
                            added4 = 0.0
                            sgn4 = 1 if y4 < 0 else -1
                            while (added4 < need4 - 0.05
                                   and xc4 + 0.5 < x14 - 0.3):
                                d4 = min(amp4,
                                         (need4 - added4) / 2.0)
                                if d4 < 0.05:
                                    break
                                yd4 = y4 + sgn4 * d4
                                inner4 += [(xc4, y4), (xc4, yd4),
                                           (xc4 + 0.5, yd4),
                                           (xc4 + 0.5, y4)]
                                added4 += 2 * d4
                                xc4 += 1.0
                            if not inner4 or added4 < need4 - 0.6:
                                return False
                            fwd4 = a4[0] < b4[0]
                            ins4 = (inner4 if fwd4
                                    else list(reversed(inner4)))
                            new4 = (list(wq4[:si4 + 1]) + ins4
                                    + list(wq4[si4 + 1:]))
                            if not grids[L4].path_clear(new4):
                                return False
                            if not _self_ok(new4, SELF_TOUCH,
                                            fiction_mm=0.5):
                                return False
                            sol4["runs"][ri4] = (Lv4, new4)
                            sol4["board_len"] += added4
                            # recompose the affected poly
                            poly4 = list(new4)
                            if ri4 == 0 and sol4["prefix"]:
                                poly4 = (list(sol4["prefix"])
                                         + poly4)
                            if (ri4 == len(sol4["runs"]) - 1
                                    and sol4["tail"]):
                                poly4 = poly4 + list(sol4["tail"])
                            for pi4, (Lp4, _pp4) in enumerate(
                                    sol4["polys"]):
                                if Lp4 == L4:
                                    sol4["polys"][pi4] = (Lp4, poly4)
                                    break
                            return True
                return False

            def _lane_variants(e3, ref3, tol3):
                """One candidate per promising free lane, ranked by
                predicted window fit (|est_total − ref|): lane choice
                IS length choice."""
                stub_m = _escape_start(e3.net, e3.mpu_xy)[0]
                stub_d = _entry_goal(e3.net, e3.dram_xy)[0]
                scored = []
                for y4 in lanes_all:
                    if not _lane_free(y4):
                        continue
                    est4 = (e3.pkg_mm
                            + abs(stub_m[0] - LANE_X0)
                            + abs(stub_m[1] - y4)
                            + (LANE_X1 - LANE_X0)
                            + abs(stub_d[0] - LANE_X1)
                            + abs(stub_d[1] - y4) + 4.5)
                    # +4.5 = +2.0 stub overhead +2.5 measured guided-
                    # route wiggle (ten lanes landed uniformly ~2.7
                    # long under the old +2.0)
                    scored.append((abs(ref3 - est4), y4))
                scored.sort()
                out4 = []
                ldbg4 = []
                pop4 = 0
                for (_sc4, y4) in scored[:10]:
                    sol4 = _solve_lane(e3, y4)
                    if sol4 is None:
                        ldbg4.append(f"(y{y4}):solve-"
                                     f"{_LAST_FAIL[:18]}")
                        if "pop-cap" in _LAST_FAIL:
                            pop4 += 1
                            if pop4 >= 3:
                                # chronic class (east-flank): every
                                # guided solve floods — stop burning
                                # the tree's wall budget, fall back
                                ldbg4.append("class-bail")
                                break
                        continue
                    dlt4 = ref3 - (e3.pkg_mm + sol4["board_len"])
                    if dlt4 < -(tol3 - 0.3):
                        ldbg4.append(f"(y{y4}):long{-dlt4:.1f}")
                        continue            # too long for the window
                    if dlt4 > tol3 - 0.3:
                        if not _trombone_sol(e3, sol4,
                                             dlt4):
                            ldbg4.append(f"(y{y4}):tromb{dlt4:.1f}")
                            continue
                    out4.append(sol4)
                    if len(out4) >= 3:
                        break
                if _DEBUG and not out4 and ldbg4:
                    print(f"    lane-empty {e3.net}: "
                          + " | ".join(ldbg4))
                out4.sort(key=lambda s4: s4["board_len"])
                return out4

            def _tree_variants(e3):
                tol3 = (TOL_BYTE if e3.group.startswith("BYTE")
                        else TOL_AC) if e3.group != "MISC" else None
                ref3 = (ref_total_of(e3.group)
                        if e3.group in ("BYTE0", "BYTE1", "AC")
                        else None)
                # measure the direct route first (near-unbounded:
                # byte1's east-flank tips need 600-800k pops — a node
                # must never be variant-less from search budget alone)
                direct3 = solve_member(e3, pops_cap=2_000_000)
                if direct3 is not None and ref3 is not None:
                    dv3 = ref3 - (e3.pkg_mm + direct3["board_len"])
                elif ref3 is not None:
                    est3 = (abs(e3.dram_xy[0] - e3.mpu_xy[0])
                            + abs(e3.dram_xy[1] - e3.mpu_xy[1]) + 3.0)
                    dv3 = ref3 - (e3.pkg_mm + est3)
                else:
                    dv3 = 0.0
                variants = []
                # level-forced first: the FREE direct is cost-optimal,
                # not length-optimal (it wraps open corridor at 39.7
                # while forced-In1 finds 26.6 — fields cost 4×), so
                # the deficit must come from the SHORTEST candidate
                pre3 = []
                for lv3 in _levels_for(e3.group):
                    s5 = solve_member(e3, force_level=lv3,
                                      pops_cap=800_000)
                    if s5 is not None:
                        pre3.append(s5)
                if direct3 is not None:
                    pre3.append(direct3)
                best_lv3 = None
                if pre3 and ref3 is not None:
                    smin3 = min(pre3, key=lambda s5: s5["board_len"])
                    Lmin3 = e3.pkg_mm + smin3["board_len"]
                    best_lv3 = smin3["runs"][0][0]
                    dv3 = ref3 - Lmin3
                if dv3 > 0.6:
                    # fractional offset LADDER, both sides: the
                    # band-jump distorts a single offset into a fixed
                    # overshoot (measured: pool bracketing the window
                    # with nothing inside) — intermediate depths fill
                    # the bracket
                    # productive order: full fraction + centre
                    # station first (historically the in-window hits),
                    # so the early-exit fires after a handful of solves
                    for frac3 in (1.0, 0.75, 0.5):
                        off3 = min(dv3 / 2.0, 5.5) * frac3
                        for tpos in (0.5, 0.35, 0.65):
                            mx3 = (e3.mpu_xy[0]
                                   + (e3.dram_xy[0]
                                      - e3.mpu_xy[0]) * tpos)
                            my3 = (e3.mpu_xy[1]
                                   + (e3.dram_xy[1]
                                      - e3.mpu_xy[1]) * tpos)
                            for sg3 in (+1, -1):
                                py3 = my3 + sg3 * off3
                                py3 = max(-11.5, min(11.5, py3))
                                gd0 = [e3.mpu_xy, (mx3, py3),
                                       e3.dram_xy]
                                # waypoint × {shortest level, free}:
                                # the in-window route is often "the
                                # SHORT level's path plus a detour" —
                                # a combination no single axis makes.
                                # Best-level combos lead (productive).
                                variants.append((gd0, best_lv3))
                    for frac3 in (1.0, 0.75, 0.5):
                        off3 = min(dv3 / 2.0, 5.5) * frac3
                        for tpos in (0.5,):
                            mx3 = (e3.mpu_xy[0]
                                   + (e3.dram_xy[0]
                                      - e3.mpu_xy[0]) * tpos)
                            my3 = (e3.mpu_xy[1]
                                   + (e3.dram_xy[1]
                                      - e3.mpu_xy[1]) * tpos)
                            for sg3 in (+1, -1):
                                py3 = my3 + sg3 * off3
                                py3 = max(-11.5, min(11.5, py3))
                                variants.append(
                                    ([e3.mpu_xy, (mx3, py3),
                                      e3.dram_xy], None))
                out3 = []
                pool3 = list(pre3)
                dbg3 = [f"pre:{e3.pkg_mm + s5['board_len']:.1f}"
                        for s5 in pre3]
                for (gd3, flv3) in variants:
                    # STRONG guide: the wrap is a deep cost basin
                    # (fields 4×) and 0.35/mm cannot pull out of it —
                    # 18 distinct waypoints returned the identical
                    # 39.73 route. Adherence enforced here; the window
                    # filter judges the result.
                    sol3 = solve_member(e3, guide_override=gd3,
                                        force_level=flv3,
                                        pops_cap=800_000,
                                        guide_w=2.5)
                    tag3 = (f"L={flv3}" if flv3 else
                            f"wp(y={gd3[1][1]:+.1f})" if gd3 else
                            "direct")
                    dbg3.append(
                        f"{tag3}:"
                        + (f"{e3.pkg_mm + sol3['board_len']:.1f}"
                           if sol3 else f"FAIL[{_LAST_FAIL[:24]}]"))
                    if sol3 is not None:
                        pool3.append(sol3)
                    if len([s4 for s4 in pool3
                            if ref3 is None
                            or abs(ref3 - (e3.pkg_mm
                                           + s4["board_len"]))
                            <= tol3 - 0.3]) >= 2:
                        break       # enough admissible branches
                for sol3 in pool3:
                    if ref3 is not None:
                        dlt3 = ref3 - (e3.pkg_mm + sol3["board_len"])
                        if abs(dlt3) > tol3 - 0.3:
                            continue    # only same-length variants
                    key3 = (sol3["runs"][0][0], sol3["runs"][-1][0],
                            round(sol3["board_len"], 1))
                    if any((s4["runs"][0][0], s4["runs"][-1][0],
                            round(s4["board_len"], 1)) == key3
                           for s4 in out3):
                        continue
                    out3.append(sol3)
                    if len(out3) >= 7:
                        break
                out3.sort(key=lambda s4: s4["board_len"])
                if _DEBUG and not out3:
                    w0 = (f"ref={ref3:.2f} win=[{ref3 - tol3 + 0.3:.2f},"
                          f"{ref3 + tol3 - 0.3:.2f}] pkg={e3.pkg_mm:.2f}"
                          if ref3 is not None else "no-window")
                    pool_d = [round(e3.pkg_mm + s4['board_len'], 2)
                              for s4 in pool3]
                    print(f"    tree-empty {e3.net}: {w0} "
                          f"pool_totals={pool_d} "
                          f"(direct {'ok' if direct3 else 'FAIL'})")
                    print("      variants: " + " | ".join(dbg3))
                return out3

            # most-constrained decisions FIRST (per review): the
            # tightest windows route while the corridor is maximally
            # empty, unconstrained nets fit around them, and failures
            # surface at shallow depth where backtracking is cheap.
            # Sweep order is preserved WITHIN each class so same-edge
            # mouths still nest.
            _cls = {"BYTE0": 0, "BYTE1": 0, "AC": 1, "MISC": 2}
            order2 = sorted(singles,
                            key=lambda e3: _cls.get(e3.group, 3))
            if not os.environ.get("SMASH_DDR_TREE"):
                # OPT-IN until the tree BEATS the default it taxes:
                # descent works (7 deep, in-window by construction),
                # lane domains open (2-4 nodes/run), but the failed
                # descent's fallback currently costs a net (A12) and
                # two generation defects remain precisely named —
                # slot verification vs guided wiggle (fix: LANE
                # SNAPPING, replace the slot span with the exact lane
                # segment post-solve) and the DQ11-class east-flank
                # generation cost.
                order2 = []
            cache2, curs2 = {}, {}
            nodes2, deepest2, bks2 = 0, 0, 0
            NODE_BUDGET = 1500
            t0_tree = time.monotonic()
            i2 = 0
            while 0 <= i2 < len(order2):
                if (nodes2 >= NODE_BUDGET
                        or time.monotonic() - t0_tree
                        > float(os.environ.get("SMASH_DDR_TREE_S",
                                                1800))):
                    if _DEBUG:
                        print(f"  tree: BOUND at depth {i2} "
                              f"(nodes {nodes2})")
                    break
                e3 = order2[i2]
                if i2 not in cache2:
                    if e3.group in ("BYTE0", "BYTE1", "AC"):
                        ref4 = ref_total_of(e3.group)
                        tol4 = (TOL_BYTE
                                if e3.group.startswith("BYTE")
                                else TOL_AC)
                        cache2[i2] = _lane_variants(e3, ref4, tol4)
                        if not cache2[i2]:
                            cache2[i2] = _tree_variants(e3)
                    else:
                        cache2[i2] = _tree_variants(e3)
                    curs2[i2] = 0
                    if _DEBUG:
                        lt = [s4.get("lane") for s4 in cache2[i2]]
                        print(f"  tree[{i2}] {e3.net}: "
                              f"{len(cache2[i2])} variants "
                              f"lanes={lt}")
                k2 = curs2[i2]
                if k2 < len(cache2[i2]):
                    curs2[i2] += 1
                    nodes2 += 1
                    sol2 = cache2[i2][k2]
                    if commit_solution(e3, sol2):
                        if sol2.get("lane") is not None:
                            lane_used[sol2["lane"]] = e3.net
                            lane_of[e3.net] = sol2["lane"]
                        i2 += 1
                        deepest2 = max(deepest2, i2)
                        for j2 in [j for j in cache2 if j >= i2]:
                            cache2.pop(j2)
                            curs2.pop(j2, None)
                else:
                    cache2.pop(i2, None)
                    curs2.pop(i2, None)
                    bks2 += 1
                    i2 -= 1
                    if i2 >= 0:
                        pn2 = order2[i2].net
                        _remove_net(pn2)
                        ln2 = lane_of.pop(pn2, None)
                        if ln2 is not None:
                            lane_used.pop(ln2, None)
            if _DEBUG:
                print(f"  tree: depth {max(i2, 0)}/{len(order2)} "
                      f"deepest {deepest2} nodes {nodes2} "
                      f"backtracks {bks2}")
            missed = _run_singles(
                [e3.net for e3 in singles
                 if e3.net not in level_of])
            unrouted.extend(missed)
            if _DEBUG and not os.environ.get("SMASH_DDR_TREE"):
                print("  tree: gated off (SMASH_DDR_TREE=1 to run)")

        # ── tolerance re-tune pass ─────────────────────────────────────────
        # Routing optimises for completion; this pass closes the LENGTH
        # gaps on the final geometry. Three tools, applied per group in
        # order: (1) too-long members (delta < −tol) try a fresh route in
        # the now-final corridor and keep it only if genuinely shorter;
        # (2) the group's reference PAIR is lengthened — matched away-side
        # patterns on both legs preserve the 0.25 gap and the skew — which
        # lifts every member's delta at once (A/C members are mostly
        # LONGER than the first-routed CK); (3) too-short members get
        # context-aware switchbacks in place: candidates validate against
        # the live grids, the full composed polyline (fiction rule) and
        # the net's other runs.
        def _reroute_shorter(net):
            snap = _snapshot_net(net)
            old_len = snap[1]
            _remove_net(net)
            if route_member(by_net[net]) and \
                    routed_len.get(net, 9e9) < old_len - 0.05:
                if _DEBUG:
                    print(f"  retune: {net} rerouted "
                          f"{old_len:.2f}→{routed_len[net]:.2f}")
                return True
            if net in routed_len:
                _remove_net(net)
            _restore_net(net, snap)
            return False

        def _trombone(net, need):
            """Exact-length tuning for bus nets: square U dips inside
            the lane's OWN slot. Depth is continuous, so the residual
            closes exactly (no pattern quantum); the slot guarantees
            hosting. Adds 2·depth per U, multiple U's spaced along
            the lane as needed."""
            L, ly = bus_lane[net]
            amp = BUS_PITCH / 2.0 - 0.30        # slot half minus S-2S
            if amp < 0.2 or need < 0.1:
                return 0.0
            mine = [t for t in tracks if t.net == net
                    and t.layer == L]
            lane_t = None
            for t in mine:
                for (a, b) in zip(t.path, t.path[1:]):
                    if (abs(a[1] - ly) < 0.05 and abs(b[1] - ly) < 0.05
                            and abs(b[0] - a[0]) > 2.0):
                        lane_t = t
                        break
                if lane_t:
                    break
            if lane_t is None:
                return 0.0
            owner = idx_of[net]
            for gr in grids.values():
                gr.stamps = [st for st in gr.stamps
                             if not (st.owner == owner
                                     and st.kind == "capsule")]
                gr.repaint_all()
            # host segment bounds
            for si, (a, b) in enumerate(zip(lane_t.path,
                                            lane_t.path[1:])):
                if (abs(a[1] - ly) < 0.05 and abs(b[1] - ly) < 0.05
                        and abs(b[0] - a[0]) > 2.0):
                    break
            x0, x1 = sorted((a[0], b[0]))
            x0 += 0.3
            x1 -= 0.3
            U_W = 0.50                          # x-extent per U
            GAP = 0.50                          # spacing between U's
            n_max = int((x1 - x0) // (U_W + GAP))
            added = 0.0
            inner = []
            xc = x0
            side = 1 if ly < 0 else -1          # dip away from centre
            k = 0
            while added < need - 0.05 and k < n_max:
                d = min(amp, (need - added) / 2.0)
                if d < 0.05:
                    break
                yd = ly + side * d
                inner += [(xc, ly), (xc, yd), (xc + U_W, yd),
                          (xc + U_W, ly)]
                added += 2.0 * d
                xc += U_W + GAP
                k += 1
            if not inner:
                for t in mine:
                    grids[t.layer].add_path(t.path, TRACE_W / 2, owner)
                return 0.0
            fwd = a[0] < b[0]
            ins_pts = inner if fwd else [q for q in reversed(inner)]
            newp = (list(lane_t.path[:si + 1]) + ins_pts
                    + list(lane_t.path[si + 1:]))
            ok = (_self_ok(newp, SELF_TOUCH, fiction_mm=0.5)
                  and grids[L].path_clear(newp))
            if ok:
                lane_t.path = [tuple(q) for q in newp]
            for t in [t2 for t2 in tracks if t2.net == net]:
                grids[t.layer].add_path(t.path, TRACE_W / 2, owner)
            if not ok:
                return 0.0
            routed_len[net] = sum(
                _path_len(t2.path) for t2 in tracks if t2.net == net)
            tuned[net] = tuned.get(net, 0.0) + added
            if _DEBUG:
                print(f"  trombone {net}: +{added:.2f} (need "
                      f"{need:.2f})")
            return added

        def _member_lengthen(net, need):
            if tuned.get(net, 0.0) > 0.05:
                return 0.0          # one structure per route
            owner = idx_of[net]
            for gr in grids.values():
                gr.stamps = [st for st in gr.stamps
                             if not (st.owner == owner
                                     and st.kind == "capsule")]
                gr.repaint_all()
            added_total = 0.0
            mine = [t for t in tracks if t.net == net]
            for t in sorted(mine, key=lambda q: -_path_len(q.path)):
                if added_total > 0.05:
                    break           # one structure per route
                stuck = False
                while added_total < need - 0.3 and not stuck:
                    stuck = True
                    for c, ach, _sd, ins in (
                            list(_accordion_candidates(
                                t.path, need - added_total))
                            or _u_detour_candidates(
                                t.path, need - added_total)):
                        res = need - added_total
                        if abs(res - ach) >= abs(res) - 0.05:
                            continue    # would not shrink the residual
                        if not _self_ok(c, SB_H - 0.10,
                                        ins[0] + 1, ins[1] - 1):
                            continue
                        if not _self_ok(c, SELF_TOUCH, fiction_mm=0.5):
                            continue
                        if not grids[t.layer].path_clear(c):
                            continue
                        clash = False
                        for o in mine:
                            if o is t or o.layer != t.layer:
                                continue
                            for k in range(ins[0],
                                           min(ins[1], len(c) - 1)):
                                for so in zip(o.path, o.path[1:]):
                                    if _seg_seg_dist(c[k], c[k + 1],
                                                     *so) < SELF_TOUCH:
                                        clash = True
                                        break
                                if clash:
                                    break
                            if clash:
                                break
                        if clash:
                            continue
                        t.path = [tuple(q) for q in c]
                        added_total += ach
                        stuck = False
                        break
            for t in mine:
                grids[t.layer].add_path(t.path, TRACE_W / 2, owner)
            routed_len[net] = sum(_path_len(t.path) for t in mine)
            tuned[net] = tuned.get(net, 0.0) + added_total
            return added_total

        def _deltas():
            out = {}
            for e2 in ends:
                if (e2.group in ("BYTE0", "BYTE1", "AC")
                        and e2.net not in _PAIR_NETS
                        and e2.net in routed_len):
                    out[e2.net] = (ref_total_of(e2.group)
                                   - (e2.pkg_mm + routed_len[e2.net]))
            return out

        _G_PAIR = (("AC", "CK", TOL_AC), ("BYTE0", "DQS0", TOL_BYTE),
                   ("BYTE1", "DQS1", TOL_BYTE))
        if not unrouted:
            for _rt in range(2):
                moved = False
                d = _deltas()
                for net, dv in sorted(d.items(), key=lambda kv: kv[1]):
                    tol = (TOL_BYTE if by_net[net].group.startswith("BYTE")
                           else TOL_AC)
                    if dv < -(tol - 0.3):
                        moved |= _reroute_shorter(net)
                d = _deltas()
                for (g, pname, tol) in _G_PAIR:
                    worst = min((dv for net2, dv in d.items()
                                 if by_net[net2].group == g), default=0.0)
                    needg = max(0.0, -worst - (tol - 0.6))
                    if needg > 0.3:
                        moved |= _lengthen_pair(pname, needg) > 0.0
                d = _deltas()
                for net, dv in sorted(d.items(), key=lambda kv: -kv[1]):
                    tol = (TOL_BYTE if by_net[net].group.startswith("BYTE")
                           else TOL_AC)
                    if dv > tol - 0.3:
                        if net in bus_lane and net not in _PAIR_NETS:
                            moved |= _trombone(net, dv) > 0.0
                        else:
                            moved |= _member_lengthen(net, dv) > 0.0
                if not moved:
                    break


        member_miss = 0
        for e2 in ends:
            if (e2.group in ("BYTE0", "BYTE1", "AC")
                    and e2.net not in _PAIR_NETS
                    and e2.net in routed_len):
                tol2 = (TOL_BYTE if e2.group.startswith("BYTE")
                        else TOL_AC)
                if abs(ref_total_of(e2.group)
                       - (e2.pkg_mm + routed_len[e2.net])) > tol2:
                    member_miss += 1
        _ph_hist.append(((len(unrouted), member_miss),
                         dict(pair_target)))
        if _phase == 0:
            if unrouted:
                break
            nxt = _phase_targets()
            if not nxt:
                break
            pair_target.update(nxt)
            if _DEBUG:
                print("  phase-2 pair targets: " + ", ".join(
                    f"{g}={v:.2f}" for g, v in sorted(nxt.items())))
            _reset_routing_state()
        elif _phase == 1:
            if _ph_hist[1][0] <= _ph_hist[0][0]:
                break                   # phase 2 held or improved
            pair_target = dict(_ph_hist[0][1])
            if _DEBUG:
                print("  phase-2 regressed "
                      f"{_ph_hist[0][0]}→{_ph_hist[1][0]} — reverting")
            _reset_routing_state()
        else:
            break

    ref_total = {g: ref_total_of(g) for g in ("BYTE0", "BYTE1", "AC")}

    # ── report rows ────────────────────────────────────────────────────
    rows = []
    for e in ends:
        if e.net not in routed_len:
            continue
        total = routed_len[e.net] + e.pkg_mm
        if e.group in ("BYTE0", "BYTE1", "AC") and e.net not in _PAIR_NETS:
            tol = TOL_BYTE if e.group.startswith("BYTE") else TOL_AC
            delta = total - ref_total[e.group]
            ok = abs(delta) <= tol
        elif e.net in _PAIR_NETS:
            tol = delta = None
            ok = True
            if e.group in ("BYTE0", "BYTE1"):       # DQS vs CK (±12.07)
                delta = ((routed_len[e.net] + e.pkg_mm)
                         - ref_total.get("AC", 0.0))
                tol = TOL_DQS_CK
                ok = abs(delta) <= tol
        else:
            tol = delta = None
            ok = True
        rows.append(RouteRow(net=e.net, group=e.group, pkg_mm=e.pkg_mm,
                             board_mm=routed_len[e.net], total_mm=total,
                             delta_mm=delta, tol_mm=tol, ok=ok,
                             tuned_mm=tuned.get(e.net, 0.0)))

    # ── via objects: each stack only as deep as its net's level ───────
    # (unrouted nets get the shallowest stack — the land is reserved on
    # every level anyway, and the report names them)
    vias = []
    for e in ends:
        at = attach.get(e.net)
        if at is None:
            continue                        # unrouted — no stack
        for xy, side, lv in ((e.mpu_xy, "mpu", at[0]),
                             (e.dram_xy, "dram", at[1])):
            if lv == "F.Cu":
                continue                    # surface attach — no stack
            depth = int(lv[2:-3])           # In4.Cu → 4 laser levels
            vias.append(Via(net=e.net, position_mm=xy, drill_mm=VIA_DRILL,
                            pad_diameter_mm=VIA_PAD, from_layer="F.Cu",
                            to_layer=lv, kind="signal", filled=True,
                            note=f"{_NOTE}: VIPPO stacked filled µvia "
                                 f"x{depth} ({side})"))
        for (x, y, La, Lb) in net_hops.get(e.net, ()):
            lo, hi = sorted((La, Lb), key=L_LEVELS.index)
            vias.append(Via(net=e.net, position_mm=(x, y),
                            drill_mm=VIA_DRILL, pad_diameter_mm=VIA_PAD,
                            from_layer=lo, to_layer=hi, kind="signal",
                            filled=True,
                            note=f"{_NOTE}: buried hop µvia "
                                 f"({lo}→{hi})"))

    # ── exact clearance audit (grid-free) ─────────────────────────────
    holes = [(h.position_mm[0], h.position_mm[1], h.diameter_mm / 2.0)
             for h in (getattr(g, "holes", []) or [])] if g else []
    viols, s3s = _audit(tracks, vias, boxes, by_net, holes, fcu_pads)
    # connectivity backstop: every routed net needs its ball stacks —
    # a missing via is an ABSENCE the clearance audit cannot see
    via_at = {(v.net, round(v.position_mm[0], 2),
               round(v.position_mm[1], 2)) for v in vias}
    for nn in level_of:
        at = attach.get(nn)
        if at is None:
            viols.append((nn, "no-stack", "attach-missing", None))
            continue
        e = by_net[nn]
        for xy, lv in ((e.mpu_xy, at[0]), (e.dram_xy, at[1])):
            if lv != "F.Cu" and (nn, round(xy[0], 2),
                                 round(xy[1], 2)) not in via_at:
                viols.append((nn, "no-stack", lv, None))

    report = DdrRouteReport(rows=rows, n_vias=len(vias),
                            n_tracks=len(tracks),
                            clearance_violations=viols,
                            s3s_warnings=s3s, pair_skew_mm=pair_skew,
                            unrouted=unrouted)
    if strict and (unrouted or viols):
        raise RuntimeError("DDR route failed:\n" + report.summary())
    board.vias.extend(vias)
    board.tracks.extend(tracks)
    return report


# ── audit ─────────────────────────────────────────────────────────────
def _in_any_box(p, boxes):
    return any(b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]
               for b in boxes)


def _audit(tracks, vias, boxes, by_net, holes=(), fcu_pads=()):
    """Exact pairwise clearance: hard limit 0.075 edge-to-edge anywhere
    (different nets); S-3S 0.45 advisory outside the BGA fields. Same-net
    non-adjacent sections must hold the §6.2 in-pattern spacing — also
    advisory (switchback floors are built at 0.45)."""
    segs = []
    for t in tracks:
        for a, b in zip(t.path, t.path[1:]):
            segs.append((t.net, t.layer, a, b))
    viols, warns = [], []
    for i in range(len(segs)):
        n1, l1, a1, b1 = segs[i]
        for j in range(i + 1, len(segs)):
            n2, l2, a2, b2 = segs[j]
            if l1 != l2:
                continue
            pairmates = (
                n1 != n2 and any({n1, n2} == set(tc)
                                 for tc in PAIRS.values()))
            if n1 == n2:
                continue        # same-net handled per-track below
            if pairmates:
                continue
            d = _seg_seg_dist(a1, b1, a2, b2) - TRACE_W
            if d < CLR_FIELD - 1e-6:
                viols.append((n1, n2, l1, round(d, 4)))
            elif d < CLR_OPEN - 1e-6:
                mid = ((a1[0] + b1[0] + a2[0] + b2[0]) / 4.0,
                       (a1[1] + b1[1] + a2[1] + b2[1]) / 4.0)
                if not _in_any_box(mid, boxes):
                    warns.append((n1, n2, l1, round(d, 4)))
    # F.Cu trace vs surface pad at REAL size (other components AND
    # both BGAs' balls — the undersized land model let tracks graze
    # physical pads; raster-audit-found)
    for (px, py, pr, pnet) in fcu_pads:
        for (nn, ll, a, b) in segs:
            if ll != "F.Cu" or nn == pnet:
                continue
            d = (_seg_seg_dist(a, b, (px, py), (px, py))
                 - TRACE_W / 2 - pr)
            if d < CLR_FIELD - 1e-3:
                viols.append((nn, f"pad@({px:+.1f},{py:+.1f})", ll,
                              round(d, 4)))
    # same-net self-touch per committed polyline — the same
    # fiction-weighted rule the commit gates use (pad-exit doglegs
    # bypass ~0.2 mm of pad-node copper: harmless; a crossed meander
    # bypasses millimetres: violation)
    for t in tracks:
        if not _self_ok(t.path, SELF_TOUCH, fiction_mm=0.5):
            viols.append((t.net, "self", t.layer, None))
    # …and ACROSS a net's tracks on one level (a multi-run net can
    # revisit a level; its two runs must not touch either)
    bynl = {}
    for t in tracks:
        bynl.setdefault((t.net, t.layer), []).append(t.path)
    for (nn, ll), paths in bynl.items():
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                for a in zip(paths[i], paths[i][1:]):
                    for b in zip(paths[j], paths[j][1:]):
                        if any(abs(u[0] - v[0]) + abs(u[1] - v[1])
                               < 1e-6 for u in a for v in b):
                            continue
                        if _seg_seg_dist(*a, *b) < SELF_TOUCH:
                            viols.append((nn, "self-x", ll, round(
                                _seg_seg_dist(*a, *b), 4)))
    # trace vs NPTH drill wall (potting holes span every layer)
    for (hx, hy, hr) in holes:
        for (nn, ll, a, b) in segs:
            d = (_seg_seg_dist(a, b, (hx, hy), (hx, hy))
                 - TRACE_W / 2 - hr)
            if d < NPTH_CLEAR - 1e-3:
                viols.append((nn, f"npth@({hx:+.1f},{hy:+.1f})", ll,
                              round(d, 4)))
    # trace vs foreign via land
    lvl_rank = {ly: k for k, ly in enumerate(L_LEVELS)}
    vinfo = [(v.net, v.from_layer, v.to_layer, *v.position_mm)
             for v in vias]
    for (vn, vf, vt, vx, vy) in vinfo:
        rf = lvl_rank.get(vf, 0)
        rt = lvl_rank.get(vt, len(L_LEVELS) - 1)
        for (n, l, a, b) in segs:
            if n == vn:
                continue
            # the via has lands on every level its span passes
            if not (l in lvl_rank and rf <= lvl_rank[l] <= rt):
                continue
            d = (_seg_seg_dist(a, b, (vx, vy), (vx, vy))
                 - TRACE_W / 2 - VIA_PAD / 2)
            if d < CLR_FIELD - 1e-6:
                viols.append((n, f"via:{vn}", l, round(d, 4)))
    # via vs via: overlapping spans need pad-pad clearance
    for i in range(len(vinfo)):
        n1, f1, t1, x1, y1 = vinfo[i]
        for j in range(i + 1, len(vinfo)):
            n2, f2, t2, x2, y2 = vinfo[j]
            dd = math.hypot(x2 - x1, y2 - y1)
            if dd < 1e-6:
                continue                    # same stack (shared ball)
            r1 = (lvl_rank.get(f1, 0), lvl_rank.get(t1, 9))
            r2 = (lvl_rank.get(f2, 0), lvl_rank.get(t2, 9))
            if r1[0] > r2[1] or r2[0] > r1[1]:
                continue                    # disjoint spans
            d = dd - VIA_PAD - CLR_FIELD
            if d < -1e-6:
                viols.append((n1, f"via-via:{n2}", f"{f1}->{t1}",
                              round(dd - VIA_PAD, 4)))
    return viols, warns
