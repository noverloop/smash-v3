"""LDS cup (sleeve + nose) + potting fixture STEP generation.

(2026-11-18) The potted tower sits inside a per-config, ONE-PIECE injection-
moulded PEEK-LDS **cup**: the sleeve and the closed nose in one shot (no
half-shells, no seam over the radome / optical window — `smash.export.
cup_noses`). The payload board is fixed into the cup nose first, the core
tower slides in from the open aft end, then the assembly is potted INSIDE the
cup. The cup is the potting container AND the outer skin; its outside carries
the LDS side-wall traces + antennas, and a plated via through its wall lands on
every board-edge castellation its config uses (`smash.parts.castellations`).
The fixture is a nose-down cradle + an aft cap with the fill / vent ports.

Frame: PHYSICAL stack frame (aft_end_board = chain[0]), math y-up, +Z toward
the nose, z = 0 at the aft face of aft_end_board — the same frame as
`stackup_step.write_stackup_step` and the castellation lanes.

Simplifications (flagged in the CAM notes): vias are modelled as straight
Ø0.5 mm holes (the real ones are double-cone per LPKF DR_017); no draft;
the board key notch is not modelled yet.

⚠ The INNER face of a deep one-piece cup cannot be lasered
(INNER_FACE_LASERABLE = False): no inner GND plane, no inner via pad rings —
the slot antennas and the QPD / camera cone traces lose their inner ground
(antenna re-sim needed).
"""
from __future__ import annotations

import math
import pathlib

from smash.export.cup_noses import active_lanes

SLEEVE_GAP_MM = 0.1            # board edge → sleeve inner wall (solder gap)
SLEEVE_WALL_MM = 0.8           # PEEK-LDS wall (vias need ≤ 0.6 mm local wall: double-cone spot-face, not modelled)
SLEEVE_VIA_D_MM = 0.5
GROOVE_W_MM, GROOVE_D_MM = 2.0, 0.4      # inner feed (0°) / vent (180°) grooves
GROOVE_ANGLES_DEG = (105.0, 285.0)   # feed / vent; lane-free stripes (castellations.SEAM_ANGLES_DEG)
INNER_FACE_LASERABLE = False   # one-piece cup: the deep bore can't be lasered
# (2026-11-17, user) PEEK-LDS: tougher / more isotropic than LCP (which was
# "skin, not structure"), and low-loss at GHz for the slot antennas.
SLEEVE_MATERIAL = ("PEEK, LDS grade (Ensinger TECACOMP PEEK LDS; εr 3.6, tanδ 0.002 "
                   "@ 1 GHz per vendor — confirm grade/colour)")

MOULD_R_OUT_MM = 25.0
MOULD_CLEARANCE_MM = 0.05
MOULD_CAP_T_MM = 5.0
MOULD_PORT_D_MM = 3.0


def stack_z_map(boards: dict, chain: list) -> dict:
    """{tile: (z0, z1)} cumulative stack heights (same walk as the stack STEP)."""
    z, out = 0.0, {}
    for n in chain:
        b = boards.get(n)
        if b is None:
            continue
        out[n] = (z, z + b.thickness_mm)
        z += b.thickness_mm
    return out


def _sleeve_profile(boards: dict, chain: list):
    """[(z0, z1, r_in)] inner-radius segments: board radius + gap everywhere,
    stepped out around the battery ring."""
    zmap = stack_z_map(boards, chain)
    r_board = 17.0
    for n in chain:
        g = getattr(boards.get(n), "geometry", None)
        if g is not None and getattr(g, "diameter_mm", None) and not boards[n].is_spacer:
            r_board = max(r_board, g.diameter_mm / 2.0)
    r_std = r_board + SLEEVE_GAP_MM
    # (2026-11-14) the battery holder now sits INSIDE the Ø34 envelope, so the
    # bore is uniform — no step round the battery section.
    segs = []
    for n in chain:
        if n not in zmap:
            continue
        z0, z1 = zmap[n]
        r = r_std
        if segs and abs(segs[-1][2] - r) < 1e-9 and abs(segs[-1][1] - z0) < 1e-9:
            segs[-1] = (segs[-1][0], z1, r)
        else:
            segs.append((z0, z1, r))
    return segs


def _tube(cq, r_in, r_out, z0, z1):
    return (cq.Workplane("XY").circle(r_out).circle(r_in)
            .extrude(z1 - z0).translate((0, 0, z0)))


def _box(cq, x, y, w, h, z0, z1):
    return (cq.Workplane("XY").center(x, y).rect(w, h)
            .extrude(z1 - z0).translate((0, 0, z0)))


def _radial_box(cq, ang, r0, r1, w, z0, z1):
    """Box from radius r0 to r1 along angle `ang` (deg), width w, z0..z1."""
    return (cq.Workplane("XY").center((r0 + r1) / 2.0, 0.0).rect(r1 - r0, w)
            .extrude(z1 - z0).translate((0, 0, z0))
            .rotate((0, 0, 0), (0, 0, 1), ang))


def _revolve(cq, pts):
    """Solid of revolution about Z from a closed (r, z) polygon (XZ plane)."""
    return (cq.Workplane("XZ").polyline([(r, z) for r, z in pts]).close()
            .revolve(360.0, (0, 0, 0), (0, 1, 0)))


def nose_solids(cq, prof):
    """(outer solid, inner cavity solid) of the nose above prof.z_s."""
    outer = _revolve(cq, [(0.0, prof.z_s)] + prof.outer_pts() + [(0.0, prof.z_top)])
    inner = _revolve(cq, [(0.0, prof.z_s - 0.01), (prof.r_in, prof.z_s - 0.01)]
                     + prof.inner_pts()[1:] + [(0.0, prof.z_top_in)])
    return outer, inner


def lens_solid(cq, L: dict):
    """Plano-convex lens: flat face at z_flat (out), edge cylinder, convex dome."""
    x, y, a, R = L["x"], L["y"], L["a"], L["R"]
    z_rim = L["z_flat"] - L["edge"]
    rim = (cq.Workplane("XY").center(x, y).circle(a).extrude(L["edge"])
           .translate((0, 0, z_rim)))
    zc = L["z_flat"] - L["tc"] + R
    dome = (cq.Workplane("XY").sphere(R).translate((x, y, zc))
            .intersect(cq.Workplane("XY").center(x, y).circle(a)
                       .extrude(L["tc"] - L["edge"] + 0.001)
                       .translate((0, 0, L["z_flat"] - L["tc"]))))
    return rim.union(dome)


def _sector(cq, a_center: float, half_w_deg: float, z_out: float, lo: float, hi: float):
    """Block tooth / groove: an angular SECTOR of the crown annulus, radial
    flanks, its bottom and top following the cone (`cone_z` + lo / + hi).
    Revolving the radial (r, z) profile keeps the faces exactly on the cone and
    inside r_out (no flat-triangle corners)."""
    from smash.export import nose_interface as NI
    pts = [(NI.CROWN_R_IN_MM, NI.cone_z(NI.CROWN_R_IN_MM, z_out) + lo),
           (NI.CROWN_R_OUT_MM, NI.cone_z(NI.CROWN_R_OUT_MM, z_out) + lo),
           (NI.CROWN_R_OUT_MM, NI.cone_z(NI.CROWN_R_OUT_MM, z_out) + hi),
           (NI.CROWN_R_IN_MM, NI.cone_z(NI.CROWN_R_IN_MM, z_out) + hi)]
    w = (cq.Workplane("XZ").polyline(pts).close()
         .revolve(2.0 * half_w_deg, (0, 0, 0), (0, 1, 0)))
    # XZ-plane revolve sweeps from +X towards -Y; centre it on a_center.
    c = w.val().Center()                    # centroid lies on the bisector
    a0 = math.degrees(math.atan2(c.y, c.x))
    return w.rotate((0, 0, 0), (0, 0, 1), a_center - a0)


_GEOM_CACHE: dict = {}


def _cached(key, build):
    """Process-wide memo for config-independent geometry (cadquery bodies are
    immutable-by-convention: every op returns a new Workplane)."""
    if key not in _GEOM_CACHE:
        _GEOM_CACHE[key] = build()
    return _GEOM_CACHE[key]


def _screw_cutters(cq, ang, zc1, zr1, r_out, z_plate_top):
    """(plate recess, crown-funnel clearance notch round the screw tip) at `ang`."""
    from smash.export import nose_interface as NI
    recess = _radial_box(cq, ang, r_out - NI.PLATE_T_MM, r_out + 0.5, NI.PLATE_W_MM + 0.2,
                         zc1 + 0.3, z_plate_top + 0.1)
    # deeper pocket for the tab's steel FOOT round the screw head
    zs = zc1 + NI.SCREW_Z_MM
    recess = recess.union(_radial_box(cq, ang, r_out - NI.TAB_FOOT_T_MM - 0.05, r_out + 0.5,
                                      NI.TAB_INSERT_W_MM + 0.2,
                                      zs - NI.TAB_FOOT_H_MM / 2 - 0.1,
                                      zs + NI.TAB_FOOT_H_MM / 2 + 0.1))
    notch = _radial_box(cq, ang, NI.SCREW_BOSS_R_MM[0] - 0.3, NI.CROWN_NOOK_R_MM + 0.05,
                        NI.SCREW_BOSS_W_MM + 0.6, zc1 - 1.0, zr1 + 0.3)
    return recess, notch


def _core_body(cq, segs, zc0, zc1, zr1, r_in, r_out, z_plate_top, z_screw):
    """Undrilled one-piece sleeve body: the skin over the core, the PEEK ANCHOR
    BAND over compute (r ANCHOR_BAND_R_IN → skin, compute's top bears on it),
    inner feed / vent grooves, the compute KEY rib, tab recesses, inward insert
    bosses and the thread-insert bores. Returns (body, thread_inserts)."""
    from smash.export import nose_interface as NI
    core = None
    for za, zb_, r in segs:
        zb_ = min(zb_, zc1)
        if zb_ <= za:
            continue
        t = _tube(cq, r, r + SLEEVE_WALL_MM, za, zb_)
        core = t if core is None else core.union(t)
    # PEEK anchor band (user 2026-11-19: no Al ring), 0.5 mm INTO the crown's
    # outer rim (a 0.01 mm overlap made the sleeve ∪ crown union drop the tube)
    core = core.union(_tube(cq, NI.ANCHOR_BAND_R_IN_MM, r_out, zc1 - 0.01, zr1 + 0.5))
    for ang in GROOVE_ANGLES_DEG:
        a = math.radians(ang)
        rc = r_in + GROOVE_D_MM / 2.0
        core = core.cut(cq.Workplane("XY").center(rc * math.cos(a), rc * math.sin(a))
                        .transformed(rotate=(0, 0, ang))
                        .rect(GROOVE_D_MM, GROOVE_W_MM).extrude(zc1))
    # KEY rib on the inner wall at compute height (compute's edge notch)
    core = core.union(_radial_box(cq, NI.KEY_ANGLE_DEG, NI.KEY_RIB_R_MM, r_in + 0.05,
                                  NI.KEY_RIB_W_MM, zc0 - 0.3, zc1 + 0.01))
    inserts = None
    r0, r1 = NI.THREAD_INSERT_R_MM
    for ang in NI.SCREW_ANGLES_DEG:
        recess, _notch = _screw_cutters(cq, ang, zc1, zr1, r_out, z_plate_top)
        boss = _radial_box(cq, ang, NI.SCREW_BOSS_R_MM[0], NI.ANCHOR_BAND_R_IN_MM + 0.05,
                           NI.SCREW_BOSS_W_MM, zc1 + 0.01, zr1 + 0.3)
        core = core.union(boss).cut(recess)
        bore = (cq.Workplane("YZ").circle(NI.THREAD_INSERT_OD_MM / 2.0)
                .extrude(r1 - r0).translate((r0, 0, z_screw))
                .rotate((0, 0, 0), (0, 0, 1), ang))
        clear = (cq.Workplane("YZ").circle(NI_SCREW_CLEAR_D / 2.0)
                 .extrude(r_out - r1 + 0.5).translate((r1 - 0.01, 0, z_screw))
                 .rotate((0, 0, 0), (0, 0, 1), ang))
        core = core.cut(bore).cut(clear)
        ins = (cq.Workplane("YZ").circle(NI.THREAD_INSERT_OD_MM / 2.0)
               .circle(NI.HELICOIL_TAP_D_MM / 2.0).extrude(r1 - r0)
               .translate((r0, 0, z_screw)).rotate((0, 0, 0), (0, 0, 1), ang))
        inserts = ins if inserts is None else inserts.union(ins)
    return core, inserts


def _crown_body(cq, zc1, zr1, r_out, z_plate_top):
    """The crown with the screw-tip notches and tab recesses cut."""
    from smash.export import nose_interface as NI
    crown = bevel_crown(cq, zr1)
    for ang in NI.SCREW_ANGLES_DEG:
        recess, notch = _screw_cutters(cq, ang, zc1, zr1, r_out, z_plate_top)
        crown = crown.cut(notch).cut(recess)
    return crown


def _screw_solid(cq, ang: float, r_head: float, z: float, r_tip: float):
    """Radial countersunk screw (ISO 10642-ish, M3): 90° head flush at r_head,
    shank to r_tip. Illustration body for the assembly STEPs."""
    from smash.export import nose_interface as NI
    d = 3.0 if NI.SCREW.startswith("M3") else 2.5
    dk = NI.SCREW_HEAD_D_MM                        # head Ø (ISO 7046-1)
    k = (dk - d) / 2.0                             # 90° countersink depth
    head = cq.Solid.makeCone(dk / 2.0, d / 2.0, k, cq.Vector(r_head, 0, z), cq.Vector(-1, 0, 0))
    shank = cq.Solid.makeCylinder(d / 2.0, max(r_head - k - r_tip, 0.1),
                                  cq.Vector(r_head - k, 0, z), cq.Vector(-1, 0, 0))
    body = (cq.Workplane("XY").add(head.fuse(shank))
            .rotate((0, 0, 0), (0, 0, 1), ang))
    return _trim_to_skin(cq, body, z - dk, z + dk)     # head face follows the Ø35.8 skin


def _arc_shell(cq, ang: float, r0: float, r1: float, w: float, z0: float, z1: float):
    """Curved plate: the r0–r1 annulus over an arc of chord ≈ w at r1, z0–z1,
    centred on `ang` (stays inside a cylinder of radius r1)."""
    half = math.degrees(0.5 * w / r1)
    body = (cq.Workplane("XZ").polyline([(r0, z0), (r1, z0), (r1, z1), (r0, z1)]).close()
            .revolve(2.0 * half, (0, 0, 0), (0, 1, 0)))
    c = body.val().Center()
    return body.rotate((0, 0, 0), (0, 0, 1), ang - math.degrees(math.atan2(c.y, c.x)))


def _trim_to_skin(cq, body, z0: float, z1: float):
    """Flat parts (plates) put their corners at hypot(r_out, w/2) > r_out:
    trim to the skin radius so nothing exceeds Ø35.8."""
    from smash.export import nose_interface as NI
    outside = (cq.Workplane("XY").workplane(offset=z0 - 1.0)
               .circle(NI.CROWN_R_OUT_MM + 5.0).circle(NI.CROWN_R_OUT_MM)
               .extrude(z1 - z0 + 2.0))
    return body.cut(outside)


def bevel_crown(cq, zr1: float):
    """CROWN = the top of the one-piece sleeve (PEEK-LDS): its outer rim rests
    on the Ø34 Al ring's top face (zr1); inside the ring's bore it FUNNELS DOWN
    (the ring sits in the nook), a cone descending inward carrying BLOCK teeth
    (square wave |_|-|_, user 2026-11-19): a band TOOTH_H tall with a GROOVE
    cut at every contact tooth angle. Groove floors (on the cone) carry the LDS
    contacts, reached from compute's edge castellations down the sleeve's outer
    face; the walls between them are bare PEEK. Screw positions have no groove
    — the uneven gaps are the orientation key."""
    from smash.export import nose_interface as NI
    zb = zr1 + NI.CROWN_BASE_MM
    T = NI.TOOTH_H_MM
    B, rn = NI.CROWN_FUNNEL_WALL_MM, NI.CROWN_NOOK_R_MM
    # underside: flat on the ring top out to the ring bore, then a vertical
    # step down the bore and a cone parallel to the floors (funnel wall B)
    prof = [(NI.CROWN_R_OUT_MM, zr1), (rn, zr1), (rn, NI.cone_z(rn, zb) - B),
            (NI.CROWN_R_IN_MM, NI.cone_z(NI.CROWN_R_IN_MM, zb) - B),
            (NI.CROWN_R_IN_MM, NI.cone_z(NI.CROWN_R_IN_MM, zb) + T),
            (NI.CROWN_R_OUT_MM, NI.cone_z(NI.CROWN_R_OUT_MM, zb) + T)]
    body = _revolve(cq, prof)
    grooves = None
    for k in range(NI.N_TEETH):
        if k in NI.SCREW_TEETH:
            continue
        g = _sector(cq, NI.tooth_angle(k), NI.GROOVE_HALF_DEG, zb, 0.0, T + 1.0)
        grooves = g if grooves is None else grooves.union(g)
    return body.cut(grooves)


def cap_ring(cq, zr1: float, z_top: float):
    """Cap-side ring: a body from just above the crown walls (TOOTH_TOP_GAP
    clearance) up to `z_top`, with a BLOCK LAND hanging into every crown
    groove. Land tops (bottoms, facing aft) sit on the groove floors — the
    plated contact pair, preloaded by the retention screws."""
    from smash.export import nose_interface as NI
    zb = zr1 + NI.CROWN_BASE_MM
    T, G = NI.TOOTH_H_MM, NI.TOOTH_TOP_GAP_MM
    # full band down to the groove floors, then CUT the gaps (robust; unioning
    # 45 lands onto coincident cylinder faces does not fuse reliably)
    prof = [(NI.CROWN_R_IN_MM, NI.cone_z(NI.CROWN_R_IN_MM, zb)),
            (NI.CROWN_R_OUT_MM, NI.cone_z(NI.CROWN_R_OUT_MM, zb)),
            (NI.CROWN_R_OUT_MM, z_top), (NI.CROWN_R_IN_MM, z_top)]
    body = _revolve(cq, prof)
    pitch = 360.0 / NI.N_TEETH
    gap_half = pitch / 2.0 - NI.LAND_HALF_DEG          # half of (wall + 2 side clearances)
    for k in range(NI.N_TEETH):
        body = body.cut(_sector(cq, NI.tooth_angle(k) + pitch / 2.0, gap_half + 1e-3,
                                zb, -1.0, T + G))
        if k in NI.SCREW_TEETH:                        # no land at a screw position
            body = body.cut(_sector(cq, NI.tooth_angle(k), NI.LAND_HALF_DEG + 1e-3,
                                    zb, -1.0, T + G))
    return body


def build_cup(boards: dict, chain: list, contract: dict | None, config: str,
              band: str | None = None):
    """(2026-11-18) Core sleeve + nose (cap) for one config (optical: per band).

    Stack (user, 2026-11-19): the tower is built with its rings; the ONE-PIECE
    PEEK-LDS sleeve (Ø35.8) slides over it — over the Ø34 Al anchor ring too —
    and its top end, the conical block CROWN, hangs on the ring's top face.
    Sides soldered, potted up to the crown's bottom edge. The NOSE CONE (block
    lands + cone + nose, payload board screwed in) drops onto the crown; its 3
    insert-moulded stainless PLATES lie in flush recesses in the sleeve wall,
    radial countersunk screws through the sleeve into the ring's helicoil
    bosses. Nothing exceeds Ø35.8. Returns dict(parts{core_sleeve (incl. the
    crown), nose_cone (slotted for the tabs), nose_cap (λ/2 lid + retaining tabs),
    retaining_ring (stainless: ring + tabs + feet), screws}, crown
    (reference body), body, …)."""
    import cadquery as cq
    from smash.export import cup_noses as CN
    from smash.export import nose_interface as NI
    payload = CN.payload_of(config)
    cchain = CN.cup_chain(boards, chain, payload)
    segs = _sleeve_profile(boards, cchain)
    r_in = segs[-1][2]
    r_out = r_in + SLEEVE_WALL_MM
    nose = CN.nose_spec(config, boards, chain, band=band, r_out=r_out)
    prof = nose.profile
    warnings = list(nose.warnings)
    zmap = stack_z_map(boards, cchain)
    z0 = nose.z_payload[0] if nose.z_payload else segs[-1][1]     # payload bottom = gap top
    z1 = nose.z_payload[1] if nose.z_payload else z0
    zc1 = zmap[CORE_TOP_NAME][1] if CORE_TOP_NAME in zmap else z0
    zr1 = z0 - NI.CROWN_STACK_MM                                  # Al ring top / crown rim
    if zr1 <= zc1 + 0.5:
        # degenerate (e.g. no compute in the chain): an inverted anchor band
        # sends OCC's UnifySameDomain into an endless loop — refuse instead
        raise ValueError(f"build_cup: crown rim z {zr1:.2f} not above compute top "
                         f"{zc1:.2f} ({CORE_TOP_NAME} missing or gap too short)")
    if zr1 - zc1 < NI.ANCHOR_RING_MIN_MM - 1e-6:
        warnings.append(f"anchor ring only {zr1 - zc1:.2f} mm tall (< {NI.ANCHOR_RING_MIN_MM}) — "
                        "gap not sized with ANCHOR_GAP_MIN_MM")
    clip = cq.Workplane("XY").circle(r_out).extrude(1000.0).translate((0, 0, -1.0))

    # ── ONE-PIECE sleeve: the skin over the whole core AND the Ø34 Al anchor
    # ring, up to the crown base (zr1); the crown is its top end (user
    # 2026-11-19: it hangs on the ring's top face, not fastened) ──
    zb_c = zr1 + NI.CROWN_BASE_MM
    T, G = NI.TOOTH_H_MM, NI.TOOTH_TOP_GAP_MM
    z_plate_top = NI.cone_z(NI.CROWN_R_OUT_MM, zb_c) + T + G + 2.0
    z_screw = zc1 + NI.SCREW_Z_MM                 # (2026-11-20) high in the band
    # (2026-11-19) the sleeve moulding (tube, ring band, grooves, plate recesses,
    # screw holes) and the crown are identical for every config / band: built
    # once per geometry and reused (only vias + nose differ) — see _GEOM_CACHE.
    base_key = (tuple((round(a, 4), round(b, 4), round(r, 4)) for a, b, r in segs),
                round(zc1, 4), round(zr1, 4), round(r_in, 4), round(r_out, 4))
    zc0 = zmap[CORE_TOP_NAME][0] if CORE_TOP_NAME in zmap else zc1 - 1.6
    core, thread_inserts = _cached(("core", round(zc0, 4)) + base_key, lambda: _core_body(
        cq, segs, zc0, zc1, zr1, r_in, r_out, z_plate_top, z_screw))
    crown = _cached(("crown",) + base_key, lambda: _crown_body(
        cq, zc1, zr1, r_out, z_plate_top))
    # the funnel must clear compute's top-face parts inside the ring bore
    tan_c = math.tan(math.radians(NI.BEVEL_CONE_DEG))
    for pt in CN._top_parts(boards[CORE_TOP_NAME], CN._fold_M(chain, CORE_TOP_NAME)) \
            if CORE_TOP_NAME in boards else []:
        r_far = CN._part_r(pt)
        if r_far < NI.CROWN_R_IN_MM - 0.2:
            continue
        r_hit = max(NI.CROWN_R_IN_MM, min(r_far, NI.CROWN_NOOK_R_MM))
        under = NI.cone_z(r_hit, zb_c) - NI.CROWN_FUNNEL_WALL_MM
        if zc1 + pt.height + 0.2 > under and r_far < 16.0:
            warnings.append(f"{pt.ref} on compute's top (h {pt.height:.2f}, r ≤ {r_far:.1f}) "
                            f"under the crown funnel: {under - zc1:.2f} mm clearance there")

    # ── cap: land ring (its flat top = the Ø34 payload board's SEAT), cone wall ──
    z_ring_top = z0 if (prof.open and nose.payload) else max(z1 + 0.3, z_plate_top + 0.4)
    nose_body = _cached(("cap", round(zr1, 4), round(z_ring_top, 4)),
                        lambda: cap_ring(cq, zr1, z_ring_top))
    if prof.z_s > z_ring_top:
        nose_body = nose_body.union(_tube(cq, r_in, r_out, z_ring_top, prof.z_s))
    zb = z1
    h_all = prof.z_top - zb + 1.0
    radome_insert = optic_insert = aop_dam = None
    if prof.open:
        # (2026-11-19, user) OPEN shell: the straight wall above is the whole
        # nose, ending in a flat ridge at z_top; nothing overhead.
        outer = cq.Workplane("XY").circle(r_out).extrude(0.01).translate((0, 0, prof.z_top))
        inside = (cq.Workplane("XY").circle(r_in).extrude(prof.z_top - zb + 1.0)
                  .translate((0, 0, zb)))
    else:
        outer, cavity = nose_solids(cq, prof)
        nose_body = nose_body.union(outer.cut(cavity))
        inside = cavity.union(cq.Workplane("XY").circle(r_in).extrude(max(prof.z_s - zb, 0.01))
                              .translate((0, 0, zb)))
    if prof.open and nose.payload:
        # (2026-11-19) Ø34 payload seated on the land ring. (2026-11-20, user)
        # pressure-fixed by the nose CAP's rim: the 3 holes take LOCATING pins
        # (rotation to the land contacts), no screws
        for ang in NI.PAYLOAD_STOP_ANGLES_DEG:
            a = math.radians(ang)
            x, y = NI.PAYLOAD_STOP_R_MM * math.cos(a), NI.PAYLOAD_STOP_R_MM * math.sin(a)
            nose_body = nose_body.cut(
                cq.Workplane("XY").center(x, y).circle(CN.STOP_PILOT_D_MM / 2.0)
                .extrude(2.0 + 0.01).translate((0, 0, z0 - 2.0)))
        # payload edge castellations → vias in the cone wall at the tooth angles
        zp = 0.5 * (z0 + z1)
        act_p = active_lanes(contract, {nose.payload}, nose.payload)
        for key, lane in (contract or {}).get("lanes", {}).items():
            if lane.get("kind") != "crown_payload" or key not in act_p:
                continue
            for ang in lane["angles"]:
                nose_body = nose_body.cut(
                    cq.Workplane("YZ").circle(SLEEVE_VIA_D_MM / 2.0)
                    .extrude(SLEEVE_WALL_MM + 1.0).translate((r_in - 0.5, 0, zp))
                    .rotate((0, 0, 0), (0, 0, 1), float(ang)))
    else:
        for ang in nose.stops:                     # payload board screwed into the cap
            a = math.radians(ang)
            x, y = CN.STOP_R_MM * math.cos(a), CN.STOP_R_MM * math.sin(a)
            boss = (cq.Workplane("XY").center(x, y).circle(CN.STOP_D_MM / 2.0)
                    .extrude(h_all).translate((0, 0, zb))).intersect(inside)
            pilot = (cq.Workplane("XY").center(x, y).circle(CN.STOP_PILOT_D_MM / 2.0)
                     .extrude(CN.STOP_PILOT_DEPTH_MM).translate((0, 0, zb - 0.01)))
            nose_body = nose_body.union(boss).cut(pilot)
    if nose.dam is not None:                       # radar: AoP pocket dam rib
        from smash.export.nose_radome import DAM_RIB_W_MM
        x0, y0, x1, y1 = nose.dam
        if prof.open:
            # (2026-11-19, user) no radome (the OD-40 container has it): an AoP
            # DAM collar insert, board → ridge, keeps the potting off the AoP
            rib = _box(cq, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0 + 2 * DAM_RIB_W_MM,
                       y1 - y0 + 2 * DAM_RIB_W_MM, zb, prof.z_top)
            rib = rib.cut(_box(cq, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0,
                               zb - 0.01, prof.z_top + 0.01))
            aop_dam = rib
        else:
            rib = _box(cq, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0 + 2 * DAM_RIB_W_MM,
                       y1 - y0 + 2 * DAM_RIB_W_MM, zb, zb + h_all)
            rib = rib.cut(_box(cq, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0,
                               zb - 0.01, zb + h_all + 0.01))
            nose_body = nose_body.union(rib.intersect(inside))
    lens = None
    if nose.tube is not None:                      # optical: light tube + lens collar + bore
        Tb, L = nose.tube, nose.lens
        tube = (cq.Workplane("XY").center(Tb["x"], Tb["y"]).circle(Tb["r_out"]).circle(Tb["r_in"])
                .extrude(Tb["z1"] - Tb["z0"]).translate((0, 0, Tb["z0"])))
        collar = (cq.Workplane("XY").center(Tb["x"], Tb["y"]).circle(Tb["collar_r_out"])
                  .circle(Tb["r_in"]).extrude(L["z_flat"] - Tb["collar_z0"])
                  .translate((0, 0, Tb["collar_z0"]))) if Tb.get("collar_r_out") else None
        if prof.open:
            # OPTIC INSERT: light-tube dam (+ the lens collar only if the lens is ours)
            optic_insert = tube if collar is None else tube.union(collar)
        else:
            nose_body = nose_body.union(tube.union(collar).intersect(inside.union(outer)))
            nose_body = nose_body.cut(cq.Workplane("XY").center(Tb["x"], Tb["y"]).circle(Tb["r_in"])
                                      .extrude(prof.z_top - Tb["collar_z0"] + 1.0)
                                      .translate((0, 0, Tb["collar_z0"])))
        if not L.get("in_capsule"):
            lens = lens_solid(cq, L)                # (open nose: the container's lens)
    for x, y, w, h, z_in in nose.hoods:            # fallback only (warned)
        hood = _box(cq, x, y, w + 2 * prof.wall, h + 2 * prof.wall, zb,
                    z_in + prof.wall).intersect(clip)
        nose_body = nose_body.union(hood).cut(_box(cq, x, y, w, h, zb - 0.01, z_in))
    for q in nose.pipes:                           # IR light pipes: tube + bore
        tube = (cq.Workplane("XY").center(q["x"], q["y"]).circle(q["r_out"]).circle(q["r_in"])
                .extrude(prof.z_top - q["z0"] + 1.0).translate((0, 0, q["z0"])))
        clipped = tube.intersect(inside)
        if clipped.solids().size():
            nose_body = nose_body.union(clipped)
        else:
            warnings.append(f"{q['ref']} light pipe has no room under the nose (seats above it?)")
        nose_body = nose_body.cut(cq.Workplane("XY").center(q["x"], q["y"]).circle(q["r_in"])
                                  .extrude(prof.z_top - q["z0"] + 2.0).translate((0, 0, q["z0"] - 0.01)))
    for hole in nose.holes:                        # through the flat face
        kind, x, y, d = hole
        if kind == "usb_slot":                     # vertical USB-C mouth (w, h)
            w, h = d
            zh = prof.inner_z_at(math.hypot(x, y) + max(w, h) / 2) - 0.2
            nose_body = nose_body.cut(_box(cq, x, y, w, h, zh, prof.z_top + 1.0))
            continue
        zh = prof.inner_z_at(math.hypot(x, y) + d / 2) - 0.2
        nose_body = nose_body.cut(cq.Workplane("XY").center(x, y).circle(d / 2.0)
                                  .extrude(prof.z_top - zh + 1.0).translate((0, 0, zh)))

    # ── (2026-11-20, user) NOSE CAP: a λ/2 radome lid on the nose cone's ridge
    # carrying the 2 retaining TABS (stainless insert) — they drop through
    # SLOTS in the nose cone into the flush recesses of the sleeve band; radial
    # countersunk screws into the band's inserts clamp cap → (press rim) →
    # payload board → land ring → crown. Nose cone + board are pressure-fixed. ──
    cap_t = CN.cap_t_mm()
    z_lid0 = prof.z_top + CN.CAP_RIDGE_GAP_MM
    z_lid1 = z_lid0 + cap_t
    cap = cq.Workplane("XY").circle(r_out).extrude(cap_t).translate((0, 0, z_lid0))
    if prof.open and nose.payload:
        rim_r0 = r_in - 0.05 - CN.CAP_RIM_W_MM
        tparts = CN._top_parts(boards[nose.payload], CN._fold_M(chain, nose.payload))
        # parts rising through the lid (vertical USB-C): a mouth in lid + rim
        for pt in tparts:
            if z1 + pt.height > z_lid0 - CN.CAP_RIDGE_GAP_MM:
                m = CN.CAP_MOUTH_MARGIN_MM
                cap = cap.cut(_box(cq, pt.x, pt.y, pt.w + 2 * m, pt.h + 2 * m,
                                   z1, z_lid1 + 1.0))
        rim = (cq.Workplane("XY").circle(r_in - 0.05).circle(rim_r0)
               .extrude(z_lid0 - z1 + 0.01).translate((0, 0, z1)))
        crowd = [pt.ref for pt in tparts
                 if CN._part_r(pt, 0.2) > rim_r0 and z1 + pt.height > z1 + 0.05]
        if crowd:
            warnings.append(f"nose cap press rim (r ≥ {rim_r0:.2f}) over payload parts "
                            f"{', '.join(sorted(crowd)[:6])} — notched round them")
            for pt in tparts:
                if pt.ref in crowd:
                    rim = rim.cut(_box(cq, pt.x, pt.y, pt.w + 0.4, pt.h + 0.4, z1 - 0.1, z_lid0))
        cap = cap.union(rim)
        if nose.tube is not None:                  # optical: aperture over the light tube
            Tb = nose.tube
            cap = cap.cut(cq.Workplane("XY").center(Tb["x"], Tb["y"]).circle(Tb["r_in"])
                          .extrude(cap_t + 2.0).translate((0, 0, z_lid0 - 1.0)))
    screws = None
    slot_w = NI.PLATE_W_MM + 2 * CN.TAB_SLOT_CLEAR_MM
    # the RING: flush in the lid's outer edge (top face), r ≥ r_out − RING_W —
    # outside the radar FoV keep-out; PEEK lid + press rim continue under it
    steel = (cq.Workplane("XY").circle(r_out).circle(r_out - NI.CAP_RING_W_MM)
             .extrude(NI.CAP_RING_T_MM).translate((0, 0, z_lid1 - NI.CAP_RING_T_MM)))
    for ang in NI.SCREW_ANGLES_DEG:
        recess, notch = _screw_cutters(cq, ang, zc1, zr1, r_out, z_plate_top)
        nose_body = nose_body.cut(notch).cut(recess)
        # the SLOT in the nose cone the cap's tab passes through: a recess in
        # the land ring, through the shell wall above it
        nose_body = nose_body.cut(_radial_box(
            cq, ang, r_out - NI.PLATE_T_MM - CN.TAB_SLOT_CLEAR_MM, r_out + 0.5, slot_w,
            zr1 - 0.5, z0 + 0.01))
        nose_body = nose_body.cut(_radial_box(cq, ang, r_in - 0.5, r_out + 0.5, slot_w,
                                              z0, prof.z_top + 1.0))
        # (2026-11-20, user) STEEL TAB, integral with the RETAINING RING along
        # the cap's edge (one stainless part: ring + 2 tabs + countersunk feet,
        # overmoulded by the PEEK lid / press rim). Axial OBLONG slot (shifts
        # aft as the head seats — PRELOAD_OFFSET); the head bears on the foot.
        slot_len = NI_SCREW_CLEAR_D + NI.TAB_SLOT_EXTRA_MM
        zs = z_screw + NI.PRELOAD_OFFSET_MM

        def _slot(r0, depth):
            return (cq.Workplane("YZ").slot2D(slot_len, NI_SCREW_CLEAR_D, 90)
                    .extrude(depth).translate((r0, 0, zs))
                    .rotate((0, 0, 0), (0, 0, 1), ang))
        zf0 = zs - NI.TAB_FOOT_H_MM / 2
        tab = _radial_box(cq, ang, r_out - NI.PLATE_T_MM, r_out + 0.3, NI.PLATE_W_MM,
                          zc1 + NI.TAB_BOTTOM_MM, z_lid1)
        foot = _radial_box(cq, ang, r_out - NI.TAB_FOOT_T_MM, r_out + 0.3, NI.PLATE_W_MM,
                           zf0, zf0 + NI.TAB_FOOT_H_MM)
        csk = (cq.Workplane("XY").add(cq.Solid.makeCone(
                   NI.SCREW_HEAD_D_MM / 2.0 + 0.05, 0.0, NI.SCREW_HEAD_D_MM / 2.0 + 0.05,
                   cq.Vector(r_out + 0.05, 0, zs), cq.Vector(-1, 0, 0)))
               .rotate((0, 0, 0), (0, 0, 1), ang))
        st = (tab.union(foot).cut(_slot(r_out - NI.TAB_FOOT_T_MM - 0.5, NI.TAB_FOOT_T_MM + 1.0))
              .cut(csk))
        steel = st if steel is None else steel.union(st)
        scr = _screw_solid(cq, ang, r_out, z_screw, NI.SCREW_TIP_R_MM)
        screws = scr if screws is None else screws.union(scr)

    steel = _trim_to_skin(cq, steel, zc1, z_lid1 + 0.5)
    # OD-40 standoff bump, integral with the stainless ring, outside the skin:
    # ROUND OD (circular arc R CAP_BUMP_ARC_R skin → crest → skin), revolved
    zb0, zb1 = z_lid1 - NI.CAP_BUMP_H_MM, z_lid1
    bump = (cq.Workplane("XZ").moveTo(r_out, zb0)
            .threePointArc((NI.CAP_BUMP_R_MM, 0.5 * (zb0 + zb1)), (r_out, zb1))
            .close().revolve(360.0, (0, 0, 0), (0, 1, 0)))
    head_top = z_screw + NI.SCREW_HEAD_D_MM / 2.0
    if zb0 < head_top + NI.BUMP_SCREW_CLEAR_MM - 1e-6:   # must end above the heads
        warnings.append(f"cap bump bottom z {zb0:.2f} only {zb0 - head_top:.2f} mm above the "
                        f"screw heads (< {NI.BUMP_SCREW_CLEAR_MM}) — reduce CAP_BUMP_ARC_R_MM")
    inserts = steel.union(bump)
    cap = cap.cut(inserts)                         # PEEK lid / rim overmould the ring

    # ── vias: core lanes on the core sleeve (the crown / cap carry LDS only) ──
    present = {n for n in cchain if n in boards and not boards[n].is_spacer}
    active = active_lanes(contract, present, payload)
    sites = []
    for key, on in active.items():
        if contract["lanes"][key].get("kind") == "crown_payload":
            continue                               # nose-cone LDS, no sleeve via
        for bn in on:
            if bn not in zmap or bn == payload:
                continue
            zc = (zmap[bn][0] + zmap[bn][1]) / 2.0
            ln_ = contract["lanes"][key]
            for ang in ln_.get("board_angles", {}).get(bn, ln_["angles"]):
                sites.append((key, bn, float(ang), zc))
    # Cut the via holes in batches (one union of ~300 cylinders is not robust
    # in OCC and corrupted the tube); a batch that breaks the body is bisected
    # down to the offending hole, which is skipped and reported.
    uniq = sorted({(round(ang, 3), round(zc, 3)) for _k, _b, ang, zc in sites})
    # vias every config drills (core lanes, GND teeth) vs this payload's crown vias
    common = sorted({(round(ang, 3), round(zc, 3)) for k, _b, ang, zc in sites
                     if contract["lanes"][k].get("kind") != "crown_top"
                     or contract["lanes"][k].get("net") == "GND"})
    specific = [u for u in uniq if u not in set(common)]

    def _hole(ang, zc):
        return (cq.Workplane("YZ").circle(SLEEVE_VIA_D_MM / 2.0)
                .extrude(SLEEVE_WALL_MM + 1.0).translate((r_in - 0.5, 0, zc))
                .rotate((0, 0, 0), (0, 0, 1), ang))

    def _ok(body, v_before):
        try:
            return (body.solids().size() == 1 and body.val().isValid()
                    and 0 < body.val().Volume() <= v_before + 1e-6)
        except Exception:
            return False
    bad_sites = []

    def _cut(body, group):
        if not group:
            return body
        tool = None
        for ang, zc in group:
            h = _hole(ang, zc)
            tool = h if tool is None else tool.union(h)
        try:
            nxt = body.cut(tool)
        except Exception:
            nxt = None
        if nxt is not None and _ok(nxt, body.val().Volume()):
            return nxt
        if len(group) == 1:
            bad_sites.append(group[0])
            return body
        m = len(group) // 2
        return _cut(_cut(body, group[:m]), group[m:])
    def _drill(body, holes):
        for i in range(0, len(holes), 24):
            body = _cut(body, holes[i:i + 24])
        return body

    def _common():
        b = _drill(core, common)
        return b, list(bad_sites)
    core, bad0 = _cached(("drilled",) + base_key + (tuple(common),), _common)
    bad_sites[:] = list(bad0)
    core = _drill(core, specific)
    if bad_sites:
        warnings.append(f"{len(bad_sites)} sleeve via(s) not cut (OCC boolean failed): "
                        + ", ".join(f"{a:g}°@z{z:.2f}" for a, z in bad_sites[:8]))
    sleeve = core.union(crown)                     # ONE moulding: sleeve + crown
    parts = {"core_sleeve": sleeve, "thread_inserts": thread_inserts,
             "nose_cone": nose_body, "nose_cap": cap, "retaining_ring": inserts,
             **({"radome_insert": radome_insert} if radome_insert is not None else {}),
             **({"aop_dam": aop_dam} if aop_dam is not None else {}),
             **({"optic_insert": optic_insert} if optic_insert is not None else {}),
             "screws": screws}
    return {"n_vias": len(sites), "segs": segs, "nose": nose, "active": active,
            "z_end_out": z_lid1, "r_out": r_out, "cchain": cchain, "z_crown": z0,
            "z_ring": (zc1, zr1), "via_sites": sites, "warnings": warnings, "lens": lens,
            "contract_lanes": (contract or {}).get("lanes", {}),
            "crown": crown, "parts": parts, "body": sleeve.union(nose_body)}


NI_SCREW_CLEAR_D = 3.4           # M3 clearance through the plate + sleeve wall


CORE_TOP_NAME = "companion_compute"


def build_cup_potting_fixture(cup: dict):
    """Pot-in-cup fixture: a nose-down CRADLE that holds the cup by its outside
    (bore = cup envelope + clearance, closed under the nose) and an AFT CAP over
    the open end with the fill-tube port (down the 105° feed groove to the
    nose — bottom-up fill, cup nose down) and the vent port (285°)."""
    import cadquery as cq
    r_out, z_end_out = cup["r_out"], cup["z_end_out"]
    segs = cup["segs"]
    cradle = (cq.Workplane("XY").circle(MOULD_R_OUT_MM)
              .extrude(z_end_out + MOULD_CAP_T_MM))
    # bore follows the cup: cylinder up to the shoulder, then the nose's own
    # outer surface (the cradle cups the aerodynamic nose), plus any hoods.
    prof = cup["nose"].profile
    outer, _cav = nose_solids(cq, prof)
    cradle = cradle.cut(cq.Workplane("XY").circle(r_out + MOULD_CLEARANCE_MM)
                        .extrude(prof.z_s + 0.01).translate((0, 0, -0.01)))
    cradle = cradle.cut(outer).cut(cup["body"])
    if cup.get("parts", {}).get("retaining_ring") is not None:
        cradle = cradle.cut(cup["parts"]["retaining_ring"])
    cap = (cq.Workplane("XY").circle(MOULD_R_OUT_MM).extrude(MOULD_CAP_T_MM)
           .translate((0, 0, -MOULD_CAP_T_MM)))
    r_port = segs[0][2] + GROOVE_D_MM / 2.0
    for ang in GROOVE_ANGLES_DEG:
        a = math.radians(ang)
        cap = cap.cut(cq.Workplane("XY").center(r_port * math.cos(a), r_port * math.sin(a))
                      .circle(MOULD_PORT_D_MM / 2.0).extrude(MOULD_CAP_T_MM)
                      .translate((0, 0, -MOULD_CAP_T_MM)))
    return {"fixture_cradle_nose_down": cradle, "fixture_cap_aft_fill_vent": cap}


def _cup_cam_md(config: str, cup: dict, contract: dict | None) -> str:
    from smash.export import cup_noses as CN
    from smash.export import nose_interface as NI
    nose = cup["nose"]
    prof = "\n".join(f"| {z0:.2f}–{z1:.2f} | Ø{2*r:.2f} | Ø{2*(r+SLEEVE_WALL_MM):.2f} |"
                     for z0, z1, r in cup["segs"])
    n_lanes = len([k for k, v in cup["active"].items()])
    n_all = len((contract or {}).get("lanes", {}))
    stops = ", ".join(f"{a:.0f}°" for a in nose.stops) or "—"
    split = ("ONE-PIECE SLEEVE + CROWN (identical for every config) + NOSE CONE on the "
             "standard crown (nose_interface) — two mouldings" if CN.SLEEVE_SPLIT == "unified" else
             f"FALLBACK split at z {cup.get('z_joint', 0):.2f}: core sleeve + nose cup, "
             f"{len(CN.JOINT_SCREW_ANGLES_DEG)} radial Ø{CN.JOINT_SCREW_D_MM} screws per side "
             f"at {', '.join(f'{a:.0f}°' for a in CN.JOINT_SCREW_ANGLES_DEG)} into TAPPED holes in "
             "the compute↔payload gap ring (not modelled on the ring yet) — the screws carry "
             "the joint shear, never the vias")
    w = "\n".join(f"- ⚠ {x}" for x in cup["warnings"]) or "- none"
    return (
        f"# PEEK-LDS cup — {config}{' / ' + nose.band if nose.band else ''} (generated)\n\n"
        f"Material: {SLEEVE_MATERIAL}. {split}. Payload: "
        f"{nose.payload or 'none (plain end)'}.\n\n"
        "Assembly: CORE — (1) tower built with its rings; (2) on the bare sleeve: laser-"
        "drill THIS config's vias (conical, wider outside), laser the LDS pattern (COMMON "
        "to every config: all lanes incl. every crown lane) and plate lanes + via barrels "
        "(Cu + Ni/Au; hard gold on the crown pads); (3) slide the sleeve over the tower until "
        "its crown HANGS on the Ø34 Al anchor ring's top face (not fastened); (4) solder "
        "every via to its castellation from outside — SnBi (138 °C), per-via solder-ball "
        "jetting / laser soldering (or SnBi preforms + vapour phase if the cells go in "
        "afterwards); no-clean, potting-compatible flux; (5) pot inside the sleeve up to the "
        "crown's bottom edge — potting carries the sleeve's setback inertia, so the via "
        "rows are only safe once potted (handle the soldered, unpotted tower gently). NOSE — the payload board is placed on the nose cone's "
        "land ring (3 locating pins; its castellations join the land LDS) and the cone drops "
        "onto the crown (block lands into the grooves, screw positions = key); the NOSE CAP "
        f"(λ/2 radome lid, {CN.cap_t_mm():.2f} mm) goes on last: its {NI.SCREW_N} tabs pass "
        "through the slots in the nose cone into the sleeve band's recesses and "
        f"{NI.SCREW_N} radial {NI.SCREW} through the tabs' stainless inserts into the band's "
        "threaded inserts clamp cap → press rim → payload board → land ring → crown. Nose "
        "cone and board are PRESSURE-FIXED by the cap (no screws of their own); the tabs' "
        f"DIMPLED countersinks sit {NI.PRELOAD_OFFSET_MM} mm forward of the threads, so seating "
        "the heads pulls the cap aft (contact preload). The crown contact is SEPARABLE — no "
        "solder; no compliance layer if the screws preload it enough. Swap noses (e.g. the "
        "USB nose for programming) by "
        f"removing the {NI.SCREW_N} screws.\n\n"
        "| z (mm) | ID | OD |\n|---|---|---|\n" + prof + "\n\n"
        f"- Wall {SLEEVE_WALL_MM} mm; nose wall {nose.end_t:.3f} mm; shoulder starts at z "
        f"{nose.profile.z_s:.3f}, flat face inner z {nose.z_end_in:.3f}, outer z "
        f"{cup['z_end_out']:.3f}"
        + (f" ({cup['z_end_out'] - nose.z_payload[1]:.2f} mm above the payload top)"
           if nose.z_payload else "") + ".\n"
        f"- Vias Ø{SLEEVE_VIA_D_MM} × {cup['n_vias']} on {n_lanes} ACTIVE lanes of the "
        f"{n_all}-lane shared contract: every lane is lasered, only the lanes this payload "
        "uses are DRILLED (the other companion_compute castellations stay unconnected).\n"
        f"- Payload stop bosses Ø{CN.STOP_D_MM} at r {CN.STOP_R_MM} ({stops}), "
        f"pilot Ø{CN.STOP_PILOT_D_MM} × {CN.STOP_PILOT_DEPTH_MM}.\n"
        + "".join(nose.notes) +
        f"- Inner feed / vent grooves {GROOVE_W_MM} × {GROOVE_D_MM} mm at "
        f"{', '.join(f'{g:.0f}°' for g in GROOVE_ANGLES_DEG)}, aft end → nose cavity.\n"
        "- Moulding: gate on the AFT RIM (ring / fan gate), never in a window; weld lines "
        "off the windows and the via rows. Flow ~"
        f"{cup['z_end_out']:.0f} mm at {SLEEVE_WALL_MM} mm wall → mould-flow study. Core needs "
        "near-zero draft (via-to-castellation gap 0.1 mm) and PEEK shrinkage grips it: "
        "polished core + stripper sleeve.\n"
        "- LDS: OUTER face only (the deep bore cannot be lasered) — no inner GND plane / "
        "inner pad rings; slot antennas and cone traces need re-simulation.\n"
        f"\n## Warnings\n{w}\n")


def write_sleeve_and_mould(boards: dict, chain: list, contract: dict | None,
                           out_dir, configs=None) -> dict:
    """Write one cup per config (optical configs: one per wavelength band, in
    <config>/<band>/): <out_dir>/sleeve/<config>[/<band>]/cup.{step,stl},
    cup_cam.md (+ lens.step), and the matching potting_mould/ fixture.
    `configs` defaults to every config in `cup_noses.PAYLOADS`."""
    import cadquery as cq
    from smash.export import cup_noses as CN
    out_dir = pathlib.Path(out_dir)
    sd, md = out_dir / "sleeve", out_dir / "potting_mould"
    res = {}
    variants = [(c, b) for c in (configs or list(CN.PAYLOADS))
                for b in (CN.optical_bands(CN.payload_of(c))
                          if CN.payload_of(c) in ("qpd_module", "camera_module") else [None])]
    from smash.export import nose_interface as NI
    core_done = False
    for config, band in variants:
        key = config if band is None else f"{config}/{band}"
        cup = build_cup(boards, chain, contract, config, band=band)
        parts = cup["parts"]
        if not core_done:                          # shared: frame + crown contact map
            cdir = sd / "core_sleeve"
            cdir.mkdir(parents=True, exist_ok=True)
            for old in ("core_sleeve.step", "core_sleeve.stl"):
                (cdir / old).unlink(missing_ok=True)
            # frame reference for the components stackup (all parts share it)
            import json
            (cdir / "frame.json").write_text(json.dumps(
                {"compute_top_z": cup["z_ring"][0], "ring_top_z": cup["z_ring"][1]}))
            if contract and contract.get("crown"):
                crown = [NI.Contact(**c) for c in contract["crown"]]
                comp = {int(k): v for k, v in contract.get("crown_compute_angles", {}).items()}
                (cdir / "crown.md").write_text(NI.crown_md(crown, comp))
            core_done = True
        cd = sd / config / (band or "")
        cd.mkdir(parents=True, exist_ok=True)
        asm = cq.Assembly()
        asm.add(parts["core_sleeve"], name="core_sleeve", color=cq.Color(0.85, 0.8, 0.6, 1.0))
        # the sleeve moulding + LDS pattern is common; its DRILLED vias are per
        # config (only the lanes this payload uses) → one sleeve STEP per config
        cq.exporters.export(parts["core_sleeve"], str(cd / "core_sleeve.step"))
        cq.exporters.export(parts["core_sleeve"], str(cd / "core_sleeve.stl"))
        cq.exporters.export(parts["thread_inserts"], str(cd / "thread_inserts.step"))
        for old in ("tab_inserts.step", "cap_bump.step"):   # (2026-11-20) → retaining_ring
            (cd / old).unlink(missing_ok=True)
        for name in ("nose_cone", "nose_cap", "retaining_ring", "screws", "radome_insert", "optic_insert",
                     "aop_dam"):
            if name not in parts:
                continue
            cq.exporters.export(parts[name], str(cd / f"{name}.step"))
            asm.add(parts[name], name=name, color=cq.Color(0.8, 0.75, 0.55, 1.0)
                    if name == "nose_cone" else cq.Color(0.7, 0.7, 0.75, 1.0))
        if cup.get("lens") is not None:
            cq.exporters.export(cup["lens"], str(cd / "lens.step"))
            asm.add(cup["lens"], name="lens", color=cq.Color(0.6, 0.8, 1.0, 0.5))
        asm.export(str(cd / "nose_assembly.step"))
        import json
        (cd / "frame.json").write_text(json.dumps({
            "payload": cup["nose"].payload, "z_payload": list(cup["nose"].z_payload or []),
            "compute_top_z": cup["z_ring"][0], "ring_top_z": cup["z_ring"][1]}))
        cq.exporters.export(parts["nose_cone"], str(cd / "nose_cone.stl"))
        (cd / "nose_cam.md").write_text(_cup_cam_md(config, cup, contract))
        fd = md / config / (band or "")
        fd.mkdir(parents=True, exist_ok=True)
        fasm = cq.Assembly()
        for name, body in build_cup_potting_fixture(cup).items():
            cq.exporters.export(body, str(fd / f"{name}.step"))
            fasm.add(body, name=name, color=cq.Color(0.6, 0.6, 0.65, 1.0))
        fasm.export(str(fd / "potting_fixture.step"))
        (fd / "potting_fixture_cam.md").write_text(
            f"# Potting fixture — {key} (generated)\n\n"
            "Core sleeve and nose cone are potted SEPARATELY (each is its own container "
            "and outer skin). Nose cone: nose DOWN in the cradle (its bore follows the "
            "aerodynamic nose), fill bottom-up, the crown face masked (no potting on the "
            "groove / land contacts). Core: aft cap with the fill / vent ports "
            f"({', '.join(f'{g:.0f}°' for g in GROOVE_ANGLES_DEG)} grooves), crown masked. "
            "Vacuum, then pressure cure ≤ 85 °C (cells).\n\n"
            f"- Cradle: OD Ø{2*MOULD_R_OUT_MM:.0f}, bore = envelope + {MOULD_CLEARANCE_MM} mm. "
            "PTFE (proto) / hard-anodised Al + PTFE-type coat; no release agent.\n"
            "- Before the pour: plug the USB-C receptacle and the IR light pipes; the radome "
            "pocket (dam rib) and the lens light tube stay air.\n")
        res[key] = {"n_vias": cup["n_vias"], "height_mm": cup["z_end_out"],
                    "dir": cd, "fixture_dir": fd, "warnings": cup["warnings"],
                    "n_active_lanes": len(cup["active"]),
                    "nose_mm": round(cup["z_end_out"] - (cup["nose"].z_payload or (0, 0))[1], 2)}
    return {"cups": res, "sleeve_dir": sd, "mould_dir": md,
            "segments": _sleeve_profile(boards, chain),
            "height_mm": max(r["height_mm"] for r in res.values()) if res else 0.0,
            "n_vias": sum(r["n_vias"] for r in res.values())}
