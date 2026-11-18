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


def build_cup(boards: dict, chain: list, contract: dict | None, config: str,
              band: str | None = None):
    """One config's cup (optical configs: one per wavelength `band`). Returns
    dict(body | parts, lens, n_vias, segs, nose, active, z_end_out, r_out,
    cchain, via_sites, warnings)."""
    import cadquery as cq
    from smash.export import cup_noses as CN
    payload = CN.payload_of(config)
    cchain = CN.cup_chain(boards, chain, payload)
    segs = _sleeve_profile(boards, cchain)
    r_in = segs[-1][2]
    r_out = r_in + SLEEVE_WALL_MM
    nose = CN.nose_spec(config, boards, chain, band=band, r_out=r_out)
    prof = nose.profile
    z_top = segs[-1][1]
    warnings = list(nose.warnings)
    body = None
    for z0, z1, r in segs:
        t = _tube(cq, r, r + SLEEVE_WALL_MM, z0, z1)
        body = t if body is None else body.union(t)
    if prof.z_s > z_top:
        body = body.union(_tube(cq, r_in, r_out, z_top, prof.z_s))
    outer, cavity = nose_solids(cq, prof)
    body = body.union(outer.cut(cavity))
    zb = nose.z_payload[1] if nose.z_payload else z_top
    # internal features grow from the payload top and stop at the nose's
    # inner surface (clipped to the cavity, so they follow the shoulder)
    inside = cavity.union(cq.Workplane("XY").circle(r_in).extrude(max(prof.z_s - zb, 0.01))
                          .translate((0, 0, zb)))
    h_all = prof.z_top - zb + 1.0
    for ang in nose.stops:
        a = math.radians(ang)
        x, y = CN.STOP_R_MM * math.cos(a), CN.STOP_R_MM * math.sin(a)
        boss = (cq.Workplane("XY").center(x, y).circle(CN.STOP_D_MM / 2.0)
                .extrude(h_all).translate((0, 0, zb))).intersect(inside)
        pilot = (cq.Workplane("XY").center(x, y).circle(CN.STOP_PILOT_D_MM / 2.0)
                 .extrude(CN.STOP_PILOT_DEPTH_MM).translate((0, 0, zb - 0.01)))
        body = body.union(boss).cut(pilot)
        if prof.inner_z_at(CN.STOP_R_MM + CN.STOP_D_MM / 2) - zb < CN.STOP_PILOT_DEPTH_MM + 0.3:
            warnings.append(f"stop boss at {ang:.0f}° is only "
                            f"{prof.inner_z_at(CN.STOP_R_MM + CN.STOP_D_MM / 2) - zb:.2f} mm "
                            "tall under the shoulder — shorten the pilot or move it inboard")
    if nose.dam is not None:                       # radar: AoP pocket dam rib
        from smash.export.nose_radome import DAM_RIB_W_MM
        x0, y0, x1, y1 = nose.dam
        rib = _box(cq, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0 + 2 * DAM_RIB_W_MM,
                   y1 - y0 + 2 * DAM_RIB_W_MM, zb, zb + h_all)
        rib = rib.cut(_box(cq, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0,
                           zb - 0.01, zb + h_all + 0.01))
        body = body.union(rib.intersect(inside))
    lens = None
    if nose.tube is not None:                      # optical: light tube + lens collar + bore
        T, L = nose.tube, nose.lens
        tube = (cq.Workplane("XY").center(T["x"], T["y"]).circle(T["r_out"]).circle(T["r_in"])
                .extrude(T["z1"] - T["z0"]).translate((0, 0, T["z0"])))
        collar = (cq.Workplane("XY").center(T["x"], T["y"]).circle(T["collar_r_out"])
                  .circle(T["r_in"]).extrude(prof.z_top - T["collar_z0"])
                  .translate((0, 0, T["collar_z0"])))
        body = body.union(tube.union(collar).intersect(inside.union(outer)))
        body = body.cut(cq.Workplane("XY").center(T["x"], T["y"]).circle(T["r_in"])
                        .extrude(prof.z_top - T["collar_z0"] + 1.0)
                        .translate((0, 0, T["collar_z0"])))
        lens = lens_solid(cq, L)
    for x, y, w, h, z_in in nose.hoods:            # fallback only (warned)
        hood = _box(cq, x, y, w + 2 * prof.wall, h + 2 * prof.wall, zb,
                    z_in + prof.wall).intersect(
            cq.Workplane("XY").circle(r_out).extrude(1000.0).translate((0, 0, -1)))
        body = body.union(hood).cut(_box(cq, x, y, w, h, zb - 0.01, z_in))
    for q in nose.pipes:                           # IR light pipes: tube + bore
        tube = (cq.Workplane("XY").center(q["x"], q["y"]).circle(q["r_out"]).circle(q["r_in"])
                .extrude(prof.z_top - q["z0"] + 1.0).translate((0, 0, q["z0"])))
        body = body.union(tube.intersect(inside))
        body = body.cut(cq.Workplane("XY").center(q["x"], q["y"]).circle(q["r_in"])
                        .extrude(prof.z_top - q["z0"] + 2.0).translate((0, 0, q["z0"] - 0.01)))
    for _kind, x, y, d in nose.holes:              # vertical through the nose wall
        zh = prof.inner_z_at(math.hypot(x, y) + d / 2) - 0.2
        body = body.cut(cq.Workplane("XY").center(x, y).circle(d / 2.0)
                        .extrude(prof.z_top - zh + 1.0).translate((0, 0, zh)))
    for w_ in nose.radial_windows:
        body = body.cut(_radial_box(cq, w_["angle_deg"], w_["r_from"], r_out + 1.0,
                                    w_["w"], w_["z0"], w_["z1"]))
    # feed / vent grooves on the inner wall, aft end → nose cavity
    for ang in GROOVE_ANGLES_DEG:
        a = math.radians(ang)
        rc = r_in + GROOVE_D_MM / 2.0
        body = body.cut(cq.Workplane("XY").center(rc * math.cos(a), rc * math.sin(a))
                        .transformed(rotate=(0, 0, ang))
                        .rect(GROOVE_D_MM, GROOVE_W_MM).extrude(prof.z_s))
    # vias: one radial hole per ACTIVE castellation (this config's lanes only)
    from smash.export.cup_noses import active_lanes
    zmap = stack_z_map(boards, cchain)
    present = {n for n in cchain if n in boards and not boards[n].is_spacer}
    active = active_lanes(contract, present)
    sites = []
    for key, on in active.items():
        for bn in on:
            if bn not in zmap:
                continue
            zc = (zmap[bn][0] + zmap[bn][1]) / 2.0
            for ang in contract["lanes"][key]["angles"]:
                sites.append((key, bn, float(ang), zc))
    vias = None
    for _k, _bn, ang, zc in sites:
        v = (cq.Workplane("YZ").circle(SLEEVE_VIA_D_MM / 2.0)
             .extrude(SLEEVE_WALL_MM + 1.0).translate((r_in - 0.5, 0, zc))
             .rotate((0, 0, 0), (0, 0, 1), ang))
        vias = v if vias is None else vias.union(v)
    if vias is not None:
        body = body.cut(vias)
    for w_ in nose.radial_windows:                 # a window must not swallow a via
        half = math.degrees((w_["w"] / 2.0) / r_out)
        for key, bn, ang, zc in sites:
            d = abs((ang - w_["angle_deg"] + 180.0) % 360.0 - 180.0)
            if d < half + 1.0 and w_["z0"] - 0.3 < zc < w_["z1"] + 0.3:
                warnings.append(f"{w_['what']} window cuts the {key} via on {bn} "
                                f"({ang:.1f}°, z {zc:.2f})")
    out = {"n_vias": len(sites), "segs": segs, "nose": nose, "active": active,
           "z_end_out": prof.z_top, "r_out": r_out, "cchain": cchain,
           "via_sites": sites, "warnings": warnings, "lens": lens}
    if CN.SLEEVE_SPLIT == "nose_cup" and nose.payload is not None:
        z_joint = ((zmap[CORE_TOP_NAME][1] + nose.z_payload[0]) / 2.0
                   if CORE_TOP_NAME in zmap else nose.z_payload[0])
        lower = body.intersect(cq.Workplane("XY").circle(r_out + 6)
                               .extrude(z_joint + 1.0).translate((0, 0, -1.0)))
        upper = body.cut(lower)
        for ang in CN.JOINT_SCREW_ANGLES_DEG:
            for z_s, part in ((z_joint - 0.8, "lower"), (z_joint + 0.8, "upper")):
                h = (cq.Workplane("YZ").circle(CN.JOINT_SCREW_D_MM / 2.0)
                     .extrude(SLEEVE_WALL_MM + 1.0).translate((r_in - 0.5, 0, z_s))
                     .rotate((0, 0, 0), (0, 0, 1), ang))
                if part == "lower":
                    lower = lower.cut(h)
                else:
                    upper = upper.cut(h)
        out["parts"] = {"core_sleeve": lower, "nose_cup": upper}
        out["z_joint"] = z_joint
    out["body"] = body
    return out


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
    nose = cup["nose"]
    prof = "\n".join(f"| {z0:.2f}–{z1:.2f} | Ø{2*r:.2f} | Ø{2*(r+SLEEVE_WALL_MM):.2f} |"
                     for z0, z1, r in cup["segs"])
    n_lanes = len([k for k, v in cup["active"].items()])
    n_all = len((contract or {}).get("lanes", {}))
    stops = ", ".join(f"{a:.0f}°" for a in nose.stops) or "—"
    split = ("ONE moulding (sleeve + nose)" if CN.SLEEVE_SPLIT == "unified" else
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
        "Assembly: payload board screwed (M1.4 thread-forming into the stop-boss pilots; "
        "board needs Ø1.6 holes there — not yet on the boards) or glued onto the stop "
        "bosses → gap ring → core tower slides in from the aft end → vias soldered "
        "to the castellations from outside → potted INSIDE the cup, nose down.\n\n"
        "| z (mm) | ID | OD |\n|---|---|---|\n" + prof + "\n\n"
        f"- Wall {SLEEVE_WALL_MM} mm; nose wall {nose.end_t:.3f} mm; shoulder starts at z "
        f"{nose.profile.z_s:.3f}, flat face inner z {nose.z_end_in:.3f}, outer z "
        f"{cup['z_end_out']:.3f}"
        + (f" ({cup['z_end_out'] - nose.z_payload[1]:.2f} mm above the payload top)"
           if nose.z_payload else "") + ".\n"
        f"- Vias Ø{SLEEVE_VIA_D_MM} × {cup['n_vias']} on {n_lanes} ACTIVE lanes of the "
        f"{n_all}-lane shared contract (only this payload's lanes are lasered; the other "
        "companion_compute castellations stay bare).\n"
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
    for config, band in variants:
        key = config if band is None else f"{config}/{band}"
        cup = build_cup(boards, chain, contract, config, band=band)
        cd = sd / config / (band or "")
        cd.mkdir(parents=True, exist_ok=True)
        asm = cq.Assembly()
        for name, b in (cup.get("parts") or {"cup": cup["body"]}).items():
            cq.exporters.export(b, str(cd / f"{name}.step"))
            asm.add(b, name=name, color=cq.Color(0.85, 0.8, 0.6, 1.0))
        if cup.get("lens") is not None:
            cq.exporters.export(cup["lens"], str(cd / "lens.step"))
            asm.add(cup["lens"], name="lens", color=cq.Color(0.6, 0.8, 1.0, 0.5))
        asm.export(str(cd / "cup_assembly.step"))
        cq.exporters.export(cup["body"], str(cd / "cup.stl"))
        (cd / "cup_cam.md").write_text(_cup_cam_md(config, cup, contract))
        fd = md / config / (band or "")
        fd.mkdir(parents=True, exist_ok=True)
        fasm = cq.Assembly()
        for name, body in build_cup_potting_fixture(cup).items():
            cq.exporters.export(body, str(fd / f"{name}.step"))
            fasm.add(body, name=name, color=cq.Color(0.6, 0.6, 0.65, 1.0))
        fasm.export(str(fd / "potting_fixture.step"))
        (fd / "potting_fixture_cam.md").write_text(
            f"# Pot-in-cup fixture — {key} (generated)\n\n"
            "The cup IS the potting container (it stays on as the outer skin). "
            "Cup stands NOSE DOWN in the cradle (its bore follows the aerodynamic nose); "
            "fill bottom-up through a tube down "
            f"the {GROOVE_ANGLES_DEG[0]:.0f}° feed groove to the nose cavity, vent at the "
            f"aft cap over the {GROOVE_ANGLES_DEG[1]:.0f}° groove. Vacuum, then pressure "
            "cure ≤ 85 °C (cells).\n\n"
            f"- Cradle: OD Ø{2*MOULD_R_OUT_MM:.0f}, bore = cup OD + {MOULD_CLEARANCE_MM} mm "
            "along the cylinder, nose-shaped at the end. PTFE (proto) / hard-anodised Al + "
            "PTFE-type coat; no release agent (spoils LDS / potting adhesion).\n"
            f"- Aft cap: fill-tube + vent ports Ø{MOULD_PORT_D_MM}.\n"
            "- Before the pour: plug the USB-C receptacle and the IR holes (radar); the "
            "radome pocket (dam rib) and the lens light tube stay air.\n")
        res[key] = {"n_vias": cup["n_vias"], "height_mm": cup["z_end_out"],
                    "dir": cd, "fixture_dir": fd, "warnings": cup["warnings"],
                    "n_active_lanes": len(cup["active"]),
                    "nose_mm": round(cup["z_end_out"] - (cup["nose"].z_payload or (0, 0))[1], 2)}
    return {"cups": res, "sleeve_dir": sd, "mould_dir": md,
            "segments": _sleeve_profile(boards, chain),
            "height_mm": max(r["height_mm"] for r in res.values()) if res else 0.0,
            "n_vias": sum(r["n_vias"] for r in res.values())}
