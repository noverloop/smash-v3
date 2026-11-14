"""LDS sleeve + potting mould STEP generation (2026-11-14 architecture).

The potted tower sits inside an injection-moulded LDS sleeve (glass-filled
LCP, two axial half-shells). The sleeve is the potting container AND the
outer skin; its outside carries the LDS side-wall traces + antennas, and a
plated via through its wall lands on every board-edge castellation
(`smash.parts.castellations`). The mould is the clamp fixture that holds the
two half-shells closed during vacuum potting, plus the end caps with the
fill / vent ports.

Frame: PHYSICAL stack frame (aft_end_board = chain[0]), math y-up, +Z toward
the nose, z = 0 at the aft face of aft_end_board — the same frame as
`stackup_step.write_stackup_step` and the castellation lanes.

Simplifications (flagged in the CAM notes): vias are modelled as straight
Ø0.5 mm holes (the real ones are double-cone per LPKF DR_017); no draft;
the board key notch is not modelled yet (the feed/vent grooves index the
sleeve halves, which split on the y = 0 plane through them).
"""
from __future__ import annotations

import math
import pathlib

SLEEVE_GAP_MM = 0.1            # board edge → sleeve inner wall (solder gap)
SLEEVE_WALL_MM = 0.8           # LCP wall (vias need ≤ 0.6 mm local wall: double-cone spot-face, not modelled)
SLEEVE_VIA_D_MM = 0.5
GROOVE_W_MM, GROOVE_D_MM = 2.0, 0.4      # inner feed (0°) / vent (180°) grooves
GROOVE_ANGLES_DEG = (105.0, 285.0)   # = the half-shell seams (castellations.SEAM_ANGLES_DEG)
SLEEVE_MATERIAL = "glass-filled LCP, LDS grade (e.g. Vectra E840i LDS)"

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


def build_sleeve(boards: dict, chain: list, contract: dict | None):
    """Return (half_a (y ≥ 0), half_b (y ≤ 0), n_vias, profile)."""
    import cadquery as cq
    segs = _sleeve_profile(boards, chain)
    body = None
    for z0, z1, r_in in segs:
        tube = (cq.Workplane("XY").circle(r_in + SLEEVE_WALL_MM).circle(r_in)
                .extrude(z1 - z0).translate((0, 0, z0)))
        body = tube if body is None else body.union(tube)
    # Shoulders where the bore steps out round the battery ring: an annulus
    # (small bore → big OD), SLEEVE_WALL_MM thick, placed INSIDE the big-bore
    # segment, where the battery ring is set back (spacer_step end lips).
    for (a0, a1, ra), (b0, b1, rb) in zip(segs, segs[1:]):
        lo, hi = min(ra, rb), max(ra, rb) + SLEEVE_WALL_MM
        z_sh = a1 if rb > ra else a1 - SLEEVE_WALL_MM
        shoulder = (cq.Workplane("XY").circle(hi).circle(lo)
                    .extrude(SLEEVE_WALL_MM).translate((0, 0, z_sh)))
        body = body.union(shoulder)
    z_top = segs[-1][1]
    # feed / vent grooves on the inner wall (full length)
    for ang in GROOVE_ANGLES_DEG:
        for z0, z1, r_in in segs:
            a = math.radians(ang)
            rc = r_in + GROOVE_D_MM / 2.0
            g = (cq.Workplane("XY").center(rc * math.cos(a), rc * math.sin(a))
                 .transformed(rotate=(0, 0, ang))
                 .rect(GROOVE_D_MM, GROOVE_W_MM).extrude(z1 - z0)
                 .translate((0, 0, z0)))
            body = body.cut(g)
    # vias: one radial hole per castellation, at the board's mid-thickness
    n_vias = 0
    if contract:
        zmap = stack_z_map(boards, chain)
        r_in_at = {}
        for z0, z1, r in segs:
            for n, (bz0, bz1) in zmap.items():
                if z0 - 1e-9 <= bz0 and bz1 <= z1 + 1e-9:
                    r_in_at[n] = r
        vias = None
        for _net, lane in contract.get("lanes", {}).items():
            for bn in lane["boards"]:
                if bn not in zmap:
                    continue
                zc = (zmap[bn][0] + zmap[bn][1]) / 2.0
                r = r_in_at.get(bn, 17.1)
                for ang in lane["angles"]:
                    v = (cq.Workplane("YZ").circle(SLEEVE_VIA_D_MM / 2.0)
                         .extrude(SLEEVE_WALL_MM + 1.0)
                         .translate((r - 0.5, 0, zc))
                         .rotate((0, 0, 0), (0, 0, 1), ang))
                    vias = v if vias is None else vias.union(v)
                    n_vias += 1
        if vias is not None:
            body = body.cut(vias)
    # Split plane through the axis along the seams (105° / 285°): rotate the
    # y ≥ 0 / y ≤ 0 half-spaces by (seam − 0°) so the cut lies on the seams.
    from smash.parts.castellations import SEAM_ANGLES_DEG
    big = 60.0
    rot = SEAM_ANGLES_DEG[0]
    hs_a = (cq.Workplane("XY").box(big, big / 2, z_top + 2, centered=(True, False, False))
            .translate((0, 0, -1)).rotate((0, 0, 0), (0, 0, 1), rot))
    hs_b = (cq.Workplane("XY").box(big, big / 2, z_top + 2, centered=(True, False, False))
            .translate((0, -big / 2, -1)).rotate((0, 0, 0), (0, 0, 1), rot))
    half_a = body.intersect(hs_a)
    half_b = body.intersect(hs_b)
    return half_a, half_b, n_vias, segs


def build_potting_mould(segs: list):
    """Clamp fixture (two half-tubes split on x = 0, across the sleeve seams)
    + bottom cap with the fill port + top cap with the vent port. Returns
    {part_name: body}."""
    import cadquery as cq
    z_top = segs[-1][1]
    clamp = None
    for z0, z1, r_in in segs:
        t = (cq.Workplane("XY").circle(MOULD_R_OUT_MM)
             .circle(r_in + SLEEVE_WALL_MM + MOULD_CLEARANCE_MM)
             .extrude(z1 - z0).translate((0, 0, z0)))
        clamp = t if clamp is None else clamp.union(t)
    big = 2 * MOULD_R_OUT_MM + 10
    from smash.parts.castellations import SEAM_ANGLES_DEG
    rot = SEAM_ANGLES_DEG[0]           # clamp split ⟂ to the sleeve seams
    left = clamp.intersect(cq.Workplane("XY").box(big / 2, big, z_top + 2,
                                                  centered=(False, True, False))
                           .translate((-big / 2, 0, -1)).rotate((0, 0, 0), (0, 0, 1), rot))
    right = clamp.intersect(cq.Workplane("XY").box(big / 2, big, z_top + 2,
                                                   centered=(False, True, False))
                            .translate((0, 0, -1)).rotate((0, 0, 0), (0, 0, 1), rot))
    r_port = segs[0][2] + GROOVE_D_MM / 2.0
    fa, va = (math.radians(GROOVE_ANGLES_DEG[0]), math.radians(GROOVE_ANGLES_DEG[1]))
    bottom = (cq.Workplane("XY").circle(MOULD_R_OUT_MM).extrude(MOULD_CAP_T_MM)
              .translate((0, 0, -MOULD_CAP_T_MM)))
    bottom = bottom.cut(cq.Workplane("XY").center(r_port * math.cos(fa), r_port * math.sin(fa))
                        .circle(MOULD_PORT_D_MM / 2.0).extrude(MOULD_CAP_T_MM)
                        .translate((0, 0, -MOULD_CAP_T_MM)))
    r_vent = segs[-1][2] + GROOVE_D_MM / 2.0
    top = (cq.Workplane("XY").circle(MOULD_R_OUT_MM).extrude(MOULD_CAP_T_MM)
           .translate((0, 0, z_top)))
    top = top.cut(cq.Workplane("XY").center(r_vent * math.cos(va), r_vent * math.sin(va))
                  .circle(MOULD_PORT_D_MM / 2.0).extrude(MOULD_CAP_T_MM)
                  .translate((0, 0, z_top)))
    return {"mould_clamp_left": left, "mould_clamp_right": right,
            "mould_cap_bottom_fill": bottom, "mould_cap_top_vent": top}


def write_sleeve_and_mould(boards: dict, chain: list, contract: dict | None,
                           out_dir) -> dict:
    """Write <out_dir>/sleeve/{sleeve_half_a,sleeve_half_b,sleeve}.step (+stl,
    _cam.md) and <out_dir>/potting_mould/*.step."""
    import cadquery as cq
    out_dir = pathlib.Path(out_dir)
    a, b, n_vias, segs = build_sleeve(boards, chain, contract)
    sd = out_dir / "sleeve"
    sd.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(a, str(sd / "sleeve_half_a.step"))
    cq.exporters.export(b, str(sd / "sleeve_half_b.step"))
    asm = cq.Assembly()
    asm.add(a, name="sleeve_half_a", color=cq.Color(0.85, 0.8, 0.6, 1.0))
    asm.add(b, name="sleeve_half_b", color=cq.Color(0.8, 0.75, 0.55, 1.0))
    asm.export(str(sd / "sleeve.step"))
    cq.exporters.export(a.union(b), str(sd / "sleeve.stl"))
    prof = "\n".join(f"| {z0:.2f}–{z1:.2f} | Ø{2*r:.2f} | Ø{2*(r+SLEEVE_WALL_MM):.2f} |"
                     for z0, z1, r in segs)
    (sd / "sleeve_cam.md").write_text(
        f"# LDS sleeve (generated)\n\nMaterial: {SLEEVE_MATERIAL}. Two axial "
        "half-shells split through the axis at 105° / 285° (seams = feed + vent "
        "grooves; 105° is the signal/antenna sector edge, 285° a lane-free stripe).\n\n"
        "| z (mm) | ID | OD |\n|---|---|---|\n" + prof + "\n\n"
        f"- Wall {SLEEVE_WALL_MM} mm; vias Ø{SLEEVE_VIA_D_MM} mm × {n_vias}, one per "
        "castellation at its board's mid-thickness (model: straight holes; real: "
        "double-cone, local wall ≤ 0.6 mm per LPKF DR_017).\n"
        f"- Inner feed / vent grooves {GROOVE_W_MM} × {GROOVE_D_MM} mm at "
        f"{', '.join(f'{g:.0f}°' for g in GROOVE_ANGLES_DEG)}, full length.\n"
        "- Outside: LDS side-wall traces (one per castellation lane) + antennas "
        "(non-metallic section) — laser + plate + test BEFORE assembly.\n"
        "- Open: board key notch / sleeve key rib; via spot-faces; draft.\n")
    md = out_dir / "potting_mould"
    md.mkdir(parents=True, exist_ok=True)
    parts = build_potting_mould(segs)
    masm = cq.Assembly()
    for name, body in parts.items():
        cq.exporters.export(body, str(md / f"{name}.step"))
        masm.add(body, name=name, color=cq.Color(0.6, 0.6, 0.65, 1.0))
    masm.export(str(md / "potting_mould.step"))
    (md / "potting_mould_cam.md").write_text(
        "# Potting mould / clamp fixture (generated)\n\n"
        "The LDS sleeve IS the potting container (it stays on as the outer "
        "skin); this fixture clamps its two half-shells closed during vacuum "
        "potting and closes the ends.\n\n"
        f"- Clamp: two half-tubes (split on x = 0, across the sleeve seams), "
        f"OD Ø{2*MOULD_R_OUT_MM:.0f}, bore = sleeve OD + {MOULD_CLEARANCE_MM} mm. "
        "Material: PTFE (prototype) or hard-anodised Al with a PTFE-type coating "
        "(production) — no release agent (it would spoil LDS / potting adhesion).\n"
        f"- Bottom cap (aft): fill port Ø{MOULD_PORT_D_MM} under the 0° feed groove.\n"
        f"- Top cap (nose): vent port Ø{MOULD_PORT_D_MM} over the 180° vent groove.\n"
        "- Open: radar 77 GHz air-gap dam on the nose cap side; sleeve-end seals "
        "(silicone gaskets); clamp bolts.\n")
    return {"n_vias": n_vias, "segments": segs,
            "sleeve_dir": sd, "mould_dir": md,
            "height_mm": segs[-1][1]}
