"""Standard nose interface: the CROWN (2026-11-18, user).

Stack (user, 2026-11-19): the tower is built with its rings (compute → Ø34
Al ANCHOR RING → payload), then ONE PEEK-LDS SLEEVE (Ø35.8, plastic) slides
over it; its top end IS the CROWN, which hangs on the anchor ring's top face
("like a person hanging on the side of a swimming pool") — not fastened.
The sides are soldered (vias → castellations), then the tower is potted up to
the crown's bottom edge. Finally the NOSE CONE (payload board screwed inside)
drops onto the crown and is held by 2 TABS of its own moulding (stainless insert inside):
countersunk radial M3 screws through each tab's oblong slot and a clearance
hole in the sleeve wall, threaded through the Al ring's 1 mm wall (tip free in
the potted bore) — which also clamps the crown onto the ring. Reverse load ≈ 15 % of setback; spin torque
rides the teeth. Nothing exceeds Ø35.8.

Crown wiring: each groove's LDS runs down the sleeve's OUTER face over the
ring to its own EDGE castellation on companion_compute (soldered with the
sides). Compute slots are assigned order-preserving per sector between the
screws (`compute_side_angles`), so the single-layer fan never crosses and
never runs under a retaining plate. The nose cone carries LDS on its LANDS,
joined to the payload board's castellations at the tooth angles.

Electrical contact (2026-11-19, user): BLOCK teeth (|_|-|_). LDS on the
crown's GROOVE FLOORS and the cap's LAND TOPS — both on the 30° cone, so the
screw clamp presses them together directly. The crown walls between grooves
are bare PEEK (one net per groove, walls isolate) and keep a small gap to the
cap. Cu + Ni/Au (this zone carries no antenna).

ONE pattern for every nose: tooth k carries the same net on every nose.
"""
from __future__ import annotations

import dataclasses
import math

N_TEETH = 48                     # 7.5° pitch (≈ 2.2 mm at r 16.8)
# Four SCREW teeth carry no contact: the radial retention screws pass through
# the lane-free gaps there. Their UNEVEN spacing (97.5 / 67.5 / 67.5 / 127.5°)
# is the orientation key — a nose only meshes one way round. Chosen where
# compute's top face has room for the Al-ring screw bosses (EE-placed MPU /
# DDR4 / NAND_A / NAND_B; compute sits turned 180° in the stack).
SCREW_TEETH = (25, 43)           # 2 screws (user 2026-11-19): 135° / 225° = the key

# Teeth left unplated. Was (3, 4, 29) while the crown landed on compute
# top-face pads (MPU / DDR4 corners); the outer-lane castellations free them.
BLOCKED_TEETH = ()               # (2026-11-19) none: no top-face pads any more
# (2026-11-18, user) BEVEL connector: a 4 mm annulus around the small payload
# board, its contacts on a CONE. (2026-11-19, user) The cone is HIGHEST AT THE
# OUTER EDGE and slopes DOWN toward the centre: the crown's outer rim rests on
# the Ø34 Al ring's top face, and inside the ring's bore (r < CROWN_NOOK_R) the
# crown funnels down beside the ring — the ring sits in that nook, so the cone
# drop is absorbed next to the ring instead of stacked on top of it.
CROWN_R_IN_MM, CROWN_R_OUT_MM = 13.9, 17.9   # 4 mm bevel ring; outer edge flush Ø35.8
BEVEL_CONE_DEG = 30.0            # cone angle from horizontal (taller ring ↔ stronger wedge)
# (2026-11-19) crown body under the floors at the OUTER edge. The floors slope
# down inward, so this is sized for ≥ CROWN_FLOOR_MIN of PEEK over the ring top
# at the ring's inner edge (r 16): the ring used to poke into the grooves.
CROWN_FLOOR_MIN_MM = 0.5
CROWN_FUNNEL_WALL_MM = 0.8       # funnel wall (inside the ring bore), parallel to the floors
CROWN_BASE_MM = round((17.9 - 16.0) * math.tan(math.radians(30.0)) + CROWN_FLOOR_MIN_MM, 3)
# (2026-11-19, user) payload boards are Ø34 again, sitting ON TOP of the nose
# cone's land ring (not inside the crown): their edge castellations at the tooth
# angles reach the lands through vias in the cone wall + its outer face.
PAYLOAD_R_MM = 17.0
LAND_RING_TOP_MM = 0.8           # PEEK above the land roots at the outer edge (board seat)
PAYLOAD_STOP_R_MM = 15.4         # payload LOCATING pins into the land-ring top (cap clamps it)
PAYLOAD_STOP_ANGLES_DEG = (71.25, 191.25, 326.25)
PAYLOAD_STOP_HOLE_D_MM = 1.6
# (2026-11-19, user) The anchor "ring" is a PEEK BAND of the one-piece sleeve
# moulding (r ANCHOR_BAND_R_IN → skin), bearing on compute's top ring band —
# no Al part. The M3 threads are moulded-in stainless THREAD INSERTS in two
# small inward bosses (PEEK alone strips at ~0.5 kN < 0.7 kN/screw, and creeps).
ANCHOR_BAND_R_IN_MM = 16.0
THREAD_INSERT = "M3 stainless moulded-in threaded insert, Ø4.2 × 2.6 (radial)"
THREAD_INSERT_OD_MM = 4.2
# (2026-11-20) inward of the tab's 1.3 mm steel FOOT (+0.1): r 13.9–16.5
THREAD_INSERT_R_MM = (17.9 - 1.3 - 0.1 - 2.6, 17.9 - 1.3 - 0.1)
# (2026-11-20, user: tab too short / head too big / pull-down too weak) the
# screw sits HIGH in the band so head + steel foot lie wholly on the tab
# (tab starts compute top + 0.4); the band is as tall as the insert's top.
TAB_BOTTOM_MM = 0.4              # tab lower end above compute's top
SCREW_HEAD_D_MM = 5.5            # ISO 7046-1 M3, 90°
SCREW_HEAD_K_MM = (5.5 - 3.0) / 2.0          # 90° countersink depth (1.25)
TAB_FOOT_T_MM = 1.3              # stainless FOOT under the head: countersink ≥ k, flush
TAB_FOOT_H_MM = SCREW_HEAD_D_MM + 0.8        # foot height (axial) round the head
SCREW_Z_MM = TAB_BOTTOM_MM + TAB_FOOT_H_MM / 2.0 + 0.05   # screw axis above compute top
ANCHOR_RING_MIN_MM = round(SCREW_Z_MM + THREAD_INSERT_OD_MM / 2.0, 3)   # band height (≈5.7)
# Compute ↔ sleeve KEY (user): a notch in compute's edge + a rib on the sleeve's
# inner wall at compute height, at the first screw angle (no castellations
# there; under the ring band). Only compute reaches the rib (tower enters aft).
KEY_W_MM, KEY_DEPTH_MM = 1.2, 0.8            # compute edge notch
KEY_RIB_W_MM, KEY_RIB_R_MM = 1.0, 16.4       # sleeve rib (0.1 clearance each side / radially)
CROWN_NOOK_R_MM = 15.9           # crown funnel's outer wall: Al ring bore (r 16) − 0.1
# (2026-11-19, user) BLOCK teeth (square wave |_|-|_), not triangles. The
# crown is a band TOOTH_H tall with a GROOVE at every contact angle; the cap
# hangs a LAND into each groove. Contact = groove FLOOR ↔ land TOP, both on
# the 30° cone, so the screw preload presses them directly (normal force ≈
# F_axial / cos 30°). Crown walls never touch the cap (TOOTH_TOP_GAP) and are
# bare PEEK between nets. Flanks are radial (sector teeth).
TOOTH_PROFILE = "block"
TOOTH_H_MM = 0.8                 # wall / land height above the cone
TOOTH_TOP_GAP_MM = 0.1           # crown wall top ↔ cap body (only floors touch)
TOOTH_SIDE_CLEAR_MM = 0.05       # land ↔ wall, per side, at r_in
_PITCH_DEG = 360.0 / N_TEETH
_CLEAR_DEG = math.degrees(TOOTH_SIDE_CLEAR_MM / CROWN_R_IN_MM)
GROOVE_HALF_DEG = _PITCH_DEG / 4.0 + _CLEAR_DEG   # crown groove (half angular width)
LAND_HALF_DEG = _PITCH_DEG / 4.0 - _CLEAR_DEG     # cap land
BEVEL_RISE_MM = (CROWN_R_OUT_MM - CROWN_R_IN_MM) * math.tan(math.radians(BEVEL_CONE_DEG))
# payload-board bottom above the band top = the land ring's flat top (the board
# seat): the land roots at the OUTER edge + LAND_RING_TOP of PEEK.
CROWN_STACK_MM = CROWN_BASE_MM + TOOTH_H_MM + TOOTH_TOP_GAP_MM + LAND_RING_TOP_MM
ANCHOR_GAP_MIN_MM = ANCHOR_RING_MIN_MM + CROWN_STACK_MM


def cone_z(r: float, z_base: float) -> float:
    """Crown cone surface (groove floors) height at radius r, z_base = the floor
    at the OUTER edge — the highest point; the cone descends inward."""
    return z_base - (CROWN_R_OUT_MM - r) * math.tan(math.radians(BEVEL_CONE_DEG))
CROWN_PHASE_DEG = 3.75           # tooth centres off the 0° lane centre
# Nets that need more than one tooth (current): VBUS up to ~3 A on depot USB.
MULTIPLICITY = {"USB_VBUS": 3, "BAT_PROT": 2, "COMP_3V3": 2, "3V3": 1}
DIFF_PAIRS = (("CAM_CSI_CLK_P", "CAM_CSI_CLK_N"), ("CAM_CSI_D0_P", "CAM_CSI_D0_N"),
              ("CAM_CSI_D1_P", "CAM_CSI_D1_N"), ("USB_D_P", "USB_D_N"))
PAYLOAD_BOARDS = ("radar_module", "qpd_module", "camera_module", "usb_nose")
HOST = "companion_compute"
# Retention (user): retaining tabs of the nose cone (stainless insert) + screws
# into the Al anchor ring, reachable from OUTSIDE to swap noses, so they run
# RADIALLY — through the plate and a clearance hole in the sleeve wall into an
# inward boss of the ring. Reverse load puts them in SHEAR; spin torque rides
# the teeth. (2026-11-19, user) TWO fat, short screws (thread within the 4 mm
# ring height) instead of three M2.5: frees the 93.75° sector for crown lanes.
SCREW = "M3 × 4 90° countersunk (ISO 7046-1, Ø5.5 head), class 8.8 (radial, in shear)"
SCREW_N = 2
SCREW_L_MM = 4.0
# The screw threads into the band's moulded insert; the crown funnel keeps a
# clearance notch round the insert boss.
SCREW_TIP_R_MM = 17.9 - SCREW_L_MM          # head flush with the Ø35.8 skin
SCREW_BOSS_R_MM = (THREAD_INSERT_R_MM[0] - 0.3, 16.0)   # inward PEEK boss round the insert
SCREW_BOSS_W_MM = 5.4
SCREW_SHEAR_KN = 1.93            # per M3 8.8: 0.6 × 640 MPa × 5.03 mm²
# M3 tapped DIRECTLY in the ring wall: an M3 helicoil (Ø3.9 tap) would not fit
# the 4 mm ring; a few nose swaps are fine in 7075 threads.
HELICOIL = THREAD_INSERT
HELICOIL_TAP_D_MM = 2.5
# (2026-11-19, user) The retaining "plate" is a TAB of the nose cone (one PEEK
# moulding) with an OBLONG slot (axial, so the tab can shift aft while the
# countersunk head seats). Plain PEEK is overstressed in bearing at ~0.7 kN per
# screw, so a thin stainless INSERT (same slot, formed countersink) is
# overmoulded inside the tab and carries the screw load.
PLATE_T_MM = 0.6                 # PEEK tab thickness, in a flush SLEEVE recess
PLATE_W_MM = 7.0                 # M3 head Ø5.5 + 0.75 each side
TAB_INSERT_W_MM = PLATE_W_MM                 # steel tab / foot width (head Ø5.5 + 0.75 each side)
# (2026-11-20, user: "the steel insert doesn't convince me") the tabs are STEEL,
# integral with a RETAINING RING along the nose cap's edge — one stainless part
# (17-4PH H1025, MIM or machined): ring flush in the lid's top outer edge, two
# 0.6 mm tabs down through the nose-cone slots, 1.3 mm countersunk feet. The
# PEEK lid (λ/2 radome) + press rim overmould it; screw load → foot → tab →
# ring → the whole PEEK lid edge (≈ 170 mm² bearing) → press rim → board.
CAP_RING_W_MM = 1.6              # radial (r 16.3–17.9: outside the radar FoV keep-out)
CAP_RING_T_MM = 0.5              # axial, flush with the lid top (PEEK under it)
CAP_RING_MATERIAL = "17-4PH stainless (1.4542, H1025), MIM / machined"
# (2026-11-20, user) the real nose cap also carries a BUMP, OD 40, so the Ø35.8
# body keeps its distance from the bore (standoff / bourrelet). Stainless,
# machined INTEGRAL with the retaining ring (user: "can be stainless too") —
# no braze joint; one part = ring + bump + tabs + feet.
CAP_BUMP_R_MM = 20.0
# (2026-11-20, user) wider, ROUND on the OD (line contact → least friction):
# a circular-arc profile from the skin (r 17.9) to the OD-40 crest; the width
# follows from R and the 2.1 mm step, top flush with the lid. (user) it ENDS
# ABOVE THE SCREW HEADS (no cut-outs): R 4.4 → ≈ 7.5 mm wide, ≥ 0.3 mm clear.
CAP_BUMP_ARC_R_MM = 4.4
BUMP_SCREW_CLEAR_MM = 0.3
_s = CAP_BUMP_R_MM - 17.9
CAP_BUMP_H_MM = round(2.0 * math.sqrt(2.0 * CAP_BUMP_ARC_R_MM * _s - _s * _s), 3)   # axial width
TAB_SLOT_EXTRA_MM = 0.2          # slot length − clearance Ø (axial travel ±0.1 ≥ PRELOAD_OFFSET)
# (2026-11-19, user) Contact preload from the 90° countersunk head: the plate's
# (dimpled) countersink sits PRELOAD_OFFSET forward of the ring's thread axis,
# so seating the head pulls the nose CAP aft (≈ 0.5–1 kN per screw at ~1 N·m).
# (2026-11-20) The head now seats ENTIRELY on steel: the strip ends in a 1.3 mm
# stainless FOOT (countersunk 90°, flush with the skin) in a deeper recess of
# the sleeve band — the wedge acts steel on steel, no PEEK under the head.
PRELOAD_OFFSET_MM = 0.05
NOSE_MASS_G = 20.0               # potted nose module, est.


@dataclasses.dataclass
class Contact:
    tooth: int
    angle_deg: float             # tooth centre (physical frame)
    net: str
    role: str                    # "signal" | "power" | "gnd" | "pair_p" | "pair_n" | "spare"


def tooth_angle(k: int) -> float:
    return round((CROWN_PHASE_DEG + k * 360.0 / N_TEETH) % 360.0, 4)


SCREW_ANGLES_DEG = tuple(tooth_angle(k) for k in SCREW_TEETH)
KEY_ANGLE_DEG = SCREW_ANGLES_DEG[0]          # compute key notch / sleeve rib (physical)


def contact_teeth() -> list:
    return [k for k in range(N_TEETH) if k not in SCREW_TEETH and k not in BLOCKED_TEETH]


# Crown order (cyclic, from the key tooth): functional groups so the compute
# EE sees each payload's nets bunched together.
GROUPS = (("power", ("BAT_PROT", "USB_VBUS", "COMP_3V3", "3V3", "COMP_1V2", "COMP_1V8",
                     "COMP_2V8")),
          ("ir", ("IR_TX", "IR_WAKE")),
          ("usb", ("USB_D_P", "USB_D_N")),
          ("radar", ("RADAR_EN", "AWR_NRESET", "AWR_FAULT", "AWR_DRDY", "AWR_SPI_CS",
                     "AWR_SPI_CLK", "AWR_SPI_MOSI", "AWR_SPI_MISO")),
          ("qpd", ("QPD_TIA_A", "QPD_TIA_B", "QPD_TIA_C", "QPD_TIA_D")),
          ("camera", ("CAM_EXTCLK", "CAM_CSI_CLK_P", "CAM_CSI_CLK_N", "CAM_CSI_D0_P",
                      "CAM_CSI_D0_N", "CAM_CSI_D1_P", "CAM_CSI_D1_N")))


def group_order(nets) -> dict:
    """{net: sort key} — group index then position within the group; unknown
    nets go last (alphabetical)."""
    out = {}
    for gi, (_g, members) in enumerate(GROUPS):
        for mi, n in enumerate(members):
            out[n] = gi * 100 + mi
    for n in sorted(nets):
        out.setdefault(n, 10_000 + sorted(nets).index(n))
    return out


def build_sequence(nets: list, order_angle: dict, slots: int | None = None,
                   fill: bool = True) -> list:
    """Cyclic net sequence for the crown: nets ordered by their compute-side
    angle (so fans don't cross), power nets repeated, every differential pair
    kept adjacent and flanked by GND, remaining teeth filled with GND evenly."""
    pair_of = {}
    for p, n in DIFF_PAIRS:
        pair_of[p] = (p, n)
        pair_of[n] = (p, n)
    seen, units = set(), []
    for net in sorted(nets, key=lambda x: (order_angle.get(x, 0.0), x)):
        if net in seen:
            continue
        if net in pair_of and all(x in nets for x in pair_of[net]):
            p, n = pair_of[net]
            units.append([("GND", "gnd"), (p, "pair_p"), (n, "pair_n"), ("GND", "gnd")])
            seen |= {p, n}
        else:
            role = "power" if MULTIPLICITY.get(net, 1) > 1 or net in ("3V3",) or net.startswith(("COMP_", "BAT_", "USB_VBUS")) else "signal"
            units.append([(net, role)] * MULTIPLICITY.get(net, 1))
            seen.add(net)
    seq = [x for u in units for x in u]
    # collapse doubled GNDs between adjacent pairs
    out = []
    for x in seq:
        if out and x[0] == "GND" and out[-1][0] == "GND":
            continue
        out.append(x)
    if slots is None:
        slots = len(contact_teeth())
    if len(out) > slots:
        raise ValueError(f"crown: {len(out)} contacts needed, {slots} teeth")
    extra = slots - len(out)
    if extra and fill:                    # spread the spare teeth as GND, evenly — never inside a pair
        cuts = [k for k in range(1, len(out)) if out[k][1] != "pair_n"]
        for i in range(extra, 0, -1):
            want = i * len(out) / (extra + 1)
            k = min(cuts, key=lambda c: abs(c - want))
            out.insert(k, ("GND", "gnd"))
            cuts = [c + 1 if c >= k else c for c in cuts]
    return out


def allocate(nets: list, order_angle: dict, teeth: list | None = None) -> list:
    """Contacts on `teeth` (default: every contact tooth). Teeth left out stay
    unplated (they still mesh). Placed UNIT by unit (a net with its repeats, or
    a GND-guarded differential pair): a pair's P / N always land on two
    ADJACENT teeth of the same screw sector — if not, a spare GND tooth is
    spent first. Remaining spare teeth (at the end) become GND."""
    teeth = sorted(contact_teeth() if teeth is None else teeth)
    seq = build_sequence(nets, order_angle, slots=10 ** 6, fill=False)
    # split back into units: a pair unit = (P, N) (its guards are GNDs in seq)
    spare = len(teeth) - len(seq)
    if spare < 0:
        raise ValueError(f"crown: {len(seq)} contacts needed, {len(teeth)} teeth")

    def adjacent(i):                 # teeth[i] and teeth[i+1] neighbours, same sector
        return (i + 1 < len(teeth) and teeth[i + 1] == teeth[i] + 1
                and screw_sector(tooth_angle(teeth[i])) == screw_sector(tooth_angle(teeth[i + 1])))
    out, i, q, used_spare = [], 0, 0, 0
    while q < len(seq):
        if i >= len(teeth):
            raise ValueError(f"crown: {len(seq)} contacts don't fit {len(teeth)} teeth "
                             "with the pair rules")
        net, role = seq[q]
        if role == "pair_p" and not adjacent(i):
            if used_spare >= spare:
                raise ValueError("crown: no spare tooth to keep a differential pair adjacent")
            out.append(Contact(teeth[i], tooth_angle(teeth[i]), "GND", "gnd"))
            i += 1
            used_spare += 1
            continue
        out.append(Contact(teeth[i], tooth_angle(teeth[i]), net, role))
        i += 1
        q += 1
    for k in teeth[i:]:
        out.append(Contact(k, tooth_angle(k), "GND", "gnd"))
    return out


def screw_sector(a: float) -> int:
    """Index of the sector between consecutive screws holding angle `a`
    (sector k starts just after sorted(SCREW_ANGLES_DEG)[k-1])."""
    scr = sorted(SCREW_ANGLES_DEG)
    return sum(1 for sa in scr if a % 360.0 > sa) % len(scr)


def usable_teeth(caps: dict) -> list:
    """Contact teeth limited to `caps[sector]` per screw sector (free compute
    rim slots there): a contiguous block in the middle of a capped sector."""
    out = []
    for sk in sorted({screw_sector(tooth_angle(k)) for k in contact_teeth()}):
        ks = [k for k in contact_teeth() if screw_sector(tooth_angle(k)) == sk]
        scr = sorted(SCREW_ANGLES_DEG)
        ks.sort(key=lambda k: (tooth_angle(k) - scr[sk - 1]) % 360.0)
        n = min(len(ks), max(0, caps.get(sk, len(ks))))
        if n >= len(ks):
            out += ks
        elif n > 0:                    # a CONTIGUOUS block mid-sector (pairs need neighbours)
            a = (len(ks) - n) // 2
            out += ks[a:a + n]
    return sorted(out)


# (2026-11-20) the crown → compute FAN on the sleeve's outer face runs over the
# anchor band only (compute top + 0.4 → ring top − 0.4: nothing else there).
# Single-layer LDS, so neighbouring lanes must keep LANE_CLEAR_MM along their
# whole DIAGONAL — a long, shallow jog squeezes 0.6 mm power lanes together
# (the unroll showed them merging). fan_slots() checks the real geometry.
FAN_MARGIN_MM = 0.4
FAN_H_MM = ANCHOR_RING_MIN_MM - 2 * FAN_MARGIN_MM
LANE_CLEAR_MM = 0.15


def _seg_dist(p1, p2, q1, q2) -> float:
    """Minimum distance between segments p1p2 and q1q2 (0 if they cross)."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2 = cross(q1, q2, p1), cross(q1, q2, p2)
    d3, d4 = cross(p1, p2, q1), cross(p1, p2, q2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return 0.0

    def pt(p, a, b):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L = vx * vx + vy * vy
        u = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L))
        return math.hypot(p[0] - a[0] - u * vx, p[1] - a[1] - u * vy)
    return min(pt(p1, q1, q2), pt(p2, q1, q2), pt(q1, p1, p2), pt(q2, p1, p2))


def fan_unit_segments(x_slot: float, xs_teeth: list, h: float) -> list:
    """The fan copper of one unit in (x, z) mm, z = 0 at the fan bottom: a
    diagonal from its compute slot to the mean of its teeth, then a bar over its
    teeth at the top (a merged power run / a single tooth: no bar)."""
    xm = sum(xs_teeth) / len(xs_teeth)
    segs = [((x_slot, 0.0), (xm, h))]
    if len(xs_teeth) > 1:
        segs.append(((min(xs_teeth), h), (max(xs_teeth), h)))
    return segs


def fan_gap(a: tuple, b: tuple, h: float, r: float) -> float:
    """Copper gap (edge to edge) between two fan units a, b = (slot_deg,
    [tooth_deg…], width_mm), angles already unwrapped."""
    mm = lambda d: math.radians(d) * r
    sa = fan_unit_segments(mm(a[0]), [mm(t) for t in a[1]], h)
    sb = fan_unit_segments(mm(b[0]), [mm(t) for t in b[1]], h)
    d = min(_seg_dist(p1, p2, q1, q2) for p1, p2 in sa for q1, q2 in sb)
    return d - 0.5 * (a[2] + b[2])


def fan_slots(units: list, free: list, start: float, r: float = None,
              h: float = FAN_H_MM, clear: float = LANE_CLEAR_MM) -> tuple:
    """Order-preserving units → free compute slots for the crown fan.
    `units` = [(key, [tooth_deg…], width_mm)], `free` = slot angles, both
    cyclic from `start`. Minimises (worst clearance shortfall, total jog): every
    neighbouring pair keeps `clear` along its diagonals when possible.
    → ({key: slot_deg}, worst_gap_mm)."""
    r = CROWN_R_OUT_MM if r is None else r
    if not units or not free:
        return {}, float("inf")
    uw = lambda a: (a - start) % 360.0
    us = sorted(units, key=lambda u: uw(sum(u[1]) / len(u[1])))
    fr = sorted(free, key=uw)
    C, F = len(us), len(fr)
    if F < C:
        return {}, float("-inf")
    INF = (float("inf"), float("inf"))
    tdeg = [[uw(t) for t in u[1]] for u in us]
    jog = lambda i, j: abs(uw(fr[j]) - sum(tdeg[i]) / len(tdeg[i]))
    cost = [[INF] * F for _ in range(C)]
    back = [[-1] * F for _ in range(C)]
    for j in range(F - C + 1):
        cost[0][j] = (0.0, jog(0, j))
    for i in range(1, C):
        for j in range(i, F - (C - 1 - i)):
            for jp in range(i - 1, j):
                c0 = cost[i - 1][jp]
                if c0 == INF:
                    continue
                g = fan_gap((uw(fr[jp]), tdeg[i - 1], us[i - 1][2]),
                            (uw(fr[j]), tdeg[i], us[i][2]), h, r)
                c = (max(c0[0], max(0.0, clear - g)), c0[1] + jog(i, j))
                if c < cost[i][j]:
                    cost[i][j], back[i][j] = c, jp
    j = min(range(F), key=lambda k: cost[C - 1][k])
    short = cost[C - 1][j][0]
    out = {}
    for i in range(C - 1, -1, -1):
        out[us[i][0]] = fr[j]
        j = back[i][j]
    return out, clear - short


def compute_side_angles(contacts: list, free: list, ring_step: float,
                        start: float | None = None) -> dict:
    """{tooth: compute castellation angle}: an ORDER-PRESERVING assignment of
    contacts to free compute rim slots (cyclic, from the first contact) that
    minimises the total angular jog — so the single-layer LDS fan from compute
    up to the crown never crosses. Dynamic programme over (contact, slot)."""
    if not free or not contacts:
        return {}
    if start is None:
        start = contacts[0].angle_deg - 360.0 / N_TEETH / 2
    unwrap = lambda a: (a - start) % 360.0
    contacts = sorted(contacts, key=lambda c: unwrap(c.angle_deg))
    fr = sorted(free, key=unwrap)
    F, C = len(fr), len(contacts)
    if F < C:
        return {}
    INF = float("inf")
    cost = [[INF] * F for _ in range(C)]
    back = [[-1] * F for _ in range(C)]
    for j in range(F):
        cost[0][j] = abs(unwrap(fr[j]) - unwrap(contacts[0].angle_deg))
    for i in range(1, C):
        best, arg = INF, -1
        ti = unwrap(contacts[i].angle_deg)
        for j in range(i, F - (C - 1 - i)):
            if cost[i - 1][j - 1] < best:
                best, arg = cost[i - 1][j - 1], j - 1
            if best < INF:
                cost[i][j] = best + abs(unwrap(fr[j]) - ti)
                back[i][j] = arg
    j = min(range(F), key=lambda k: cost[C - 1][k])
    out = {}
    for i in range(C - 1, -1, -1):
        out[contacts[i].tooth] = fr[j]
        j = back[i][j]
    return out


def retention_md() -> str:
    g = 9.81
    lines = ["| platform | setback kG | setback N (nose) | reverse 15 % N | screw SF |", "|---|---|---|---|---|"]
    for name, kg in (("Bofors 40 mm", 46.7), ("M777 155 mm", 13.9), ("M252 81 mm", 13.8)):
        f = NOSE_MASS_G * 1e-3 * kg * 1e3 * g
        rev = 0.15 * f
        sf = SCREW_N * SCREW_SHEAR_KN * 1e3 / rev
        lines.append(f"| {name} | {kg:g} | {f:.0f} | {rev:.0f} | {sf:.1f} |")
    return "\n".join(lines)


def crown_md(contacts: list, comp_angles: dict) -> str:
    rows = ["| tooth | angle ° | compute ° | net | role |", "|---|---|---|---|---|"]
    for c in contacts:
        ca = comp_angles.get(c.tooth)
        cs = ("GND ring" if ca == "ring" else "—" if ca is None
              else ca if isinstance(ca, str) else f"{ca:.2f}")
        rows.append(f"| {c.tooth} | {c.angle_deg:.2f} | {cs} | {c.net} | {c.role} |")
    return (
        "# Nose interface — crown (generated)\n\n"
        f"{N_TEETH}-position BLOCK crown (square wave |_|-|_) on a {BEVEL_CONE_DEG:g}° cone, "
        f"{360 / N_TEETH:g}° pitch, r {CROWN_R_IN_MM}–{CROWN_R_OUT_MM} mm, wall / land height "
        f"{TOOTH_H_MM} mm, groove {2 * GROOVE_HALF_DEG:.2f}°, land {2 * LAND_HALF_DEG:.2f}° "
        f"({TOOTH_SIDE_CLEAR_MM} mm side clearance at r_in), {TOOTH_TOP_GAP_MM} mm gap over the "
        f"walls. Positions {', '.join(str(k) for k in SCREW_TEETH)} are SCREW positions (no "
        "groove / no land; the uneven spacing is the orientation key).\n\n"
        "- Contacts = LDS only (user): the CROWN carries LDS on its GROOVE FLOORS, the CAP on "
        "its LAND TOPS; both lie on the cone, so the screw clamp presses them together. Walls "
        "between grooves are bare PEEK (isolation). Finish Cu + Ni/Au. The crown is the top "
        "of the one-piece sleeve: each groove's LDS runs down the sleeve's OUTER face over the "
        "anchor band to an edge castellation on companion_compute (column 'compute °'), "
        "soldered with the sides; no lane passes under a retaining plate. The fan over the "
        f"band (≥ {FAN_H_MM:g} mm tall) keeps ≥ {LANE_CLEAR_MM} mm between lanes: repeated "
        "power teeth of one rail join (Y) into ONE lane / castellation, and the GND teeth are "
        "tied by an LDS GND RING at the crown's inner edge (signal grooves stop 0.3 mm short "
        "of it), linked to compute by one GND lane per screw sector.\n"
        f"- Retention: {SCREW_N} TABS of the NOSE CAP (the λ/2 radome lid on the nose cone; "
        "they drop through SLOTS in the nose cone, whose land ring + payload board the cap's "
        f"press rim clamps onto the crown) — {PLATE_T_MM} × {PLATE_W_MM} mm STEEL tabs integral "
        f"with a {CAP_RING_W_MM} × {CAP_RING_T_MM} mm retaining RING along the cap's edge "
        f"(+ integral OD {2 * CAP_BUMP_R_MM:g} standoff BUMP) "
        f"({CAP_RING_MATERIAL}; overmoulded by the PEEK lid), {TAB_FOOT_T_MM} mm countersunk "
        f"feet, axial OBLONG slot +{TAB_SLOT_EXTRA_MM} mm — "
        "lie in FLUSH recesses in the sleeve's PEEK anchor band; one "
        f"{SCREW} per tab at {', '.join(f'{a:g}°' for a in SCREW_ANGLES_DEG)} into a "
        f"{THREAD_INSERT} in a small inward boss of the band. The sleeve's crown sits on the "
        "band (one moulding); the screws clamp nose → crown/band. Compute is KEYED to the sleeve "
        f"(edge notch + rib at {KEY_ANGLE_DEG:g}°). Heads "
        "reachable from outside (nose swap); OD stays Ø35.8.\n"
        "- Same pattern on every nose (radar / QPD / camera / USB): tooth k = the same net.\n\n"
        "## Retention loads (nose ≈ " + f"{NOSE_MASS_G:g} g)\n\n" + retention_md() + "\n\n"
        "## Contact map\n\n" + "\n".join(rows) + "\n")
