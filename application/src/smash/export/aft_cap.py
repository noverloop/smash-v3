"""aft_end_cap — the aft PUBLIC interface (2026-11-19, user).

The bench pads that used to sit on aft_end_board's bottom face become the
contacts of a PEEK-LDS cap's crown (same block-groove geometry as the nose
crown, facing AFT): each groove's LDS lane comes down the sleeve's outer
face, past the aft board, over the cap's outer skin and into its groove
(`castellations._aft_cap_contract` assigns the teeth order-preserving, so the
skin fans never cross). Three blank SCREW positions (uneven = the key); spare
positions are GND, joined by an LDS ring at the crown's inner edge and linked
to an aft-board GND castellation. Gate names are LASERED radially next to
each groove (see the face drawing).

The parachute nichrome wires are CLAMPED, not soldered: 17 clamp tabs on a
r 6.4 circle on aft_end_board's bottom (16 sector wires + common), with the two
parachute-cutter bench pads at the centre — all exposed through the cap's
central opening. The cap is fixed by 3 axial M2 screws through it and the aft
board into the Al battery holder's floor.

Outputs (`write_aft_cap`): aft_end_cap.step, aft_end_cap.md (contact map),
aft_end_cap_face.svg (aft view, radial labels).
"""
from __future__ import annotations

import math
import pathlib

CAP_R_OPEN_MM = 9.0           # central opening: the clamp-tab ring (r 6.4 ± 0.8) + clearance
CAP_PLATE_T_MM = 1.6          # plate under the crown band
CAP_SCREW_R_MM = 10.6         # = aft_end_board "aft_cap_screw" holes; in the holder's
                               # solid webs BETWEEN the cells (≈1 mm Al round the tap hole)
HOLDER_TAP_DRILL_MM = 1.6      # M2 tap drill in the Al battery holder
HOLDER_TAP_DEPTH_MM = 4.0      # tapped depth from the holder's bottom face
from smash.parts.castellations import (AFT_CAP_N_TEETH, AFT_CAP_SCREW_TEETH as CAP_SCREW_TEETH,
                                      aft_tooth_angle)
CAP_SCREW_ANGLES_DEG = tuple(aft_tooth_angle(k) for k in CAP_SCREW_TEETH)   # between the cells
CAP_GROOVE_HALF_DEG = (360.0 / AFT_CAP_N_TEETH) / 4.0 + math.degrees(0.05 / 13.9)
CAP_SCREW = "M2 × 6 low-head (ISO 14580 / Ø3.5, A2) through the floor plate into tapped M2 holes in the Al holder (≈3.3 mm engaged)"
CAP_SCREW_CLEAR_D_MM = 2.2
# (2026-11-21, user) LOCATING holes for the dev board's fixture dowels (Mill-Max
# 5849, Ø1.5, 6.5 mm above its flange) in the flat plate, the screw angles + 36°
# (uneven = the same key). THROUGH the 1.6 mm plate: the dowels stand 1.2 mm above
# the spring-pin tips, so at rest the tower sits on the pins (contact) with the
# dowels 1.2 mm in; pressed by hand, the dowel tips stop on aft_end's bottom face.
CAP_LOCATE_R_MM = 12.2
CAP_LOCATE_ANGLES_DEG = (63.0, 189.0, 309.0)   # (2026-11-23) screw angles + 36° (was +30°: hit the new + wire pocket at 48.9°)
CAP_LOCATE_D_MM, CAP_LOCATE_DEPTH_MM = 1.6, CAP_PLATE_T_MM
CAP_SCREW_HEAD_D_MM = 3.5
LABEL_SCREW_CLEAR_DEG = 10.5   # a label beside a screw head is nudged at least this far from it
CAP_SCREW_CB_MM = 1.0          # counterbore on the aft face (head below the crown plane)
# (2026-11-20) the cells' lead stubs (− pins, + wires) stand ~0.8 mm proud of
# aft_end_board's bottom: blind pockets in the cap's top face clear them.
CAP_LEAD_POCKET_D_MM = 2.2
CAP_LEAD_POCKET_DEPTH_MM = 1.0
LABEL_R_MM = 13.6              # radial gate labels: from here INWARD (≥ r 10.8, on material)
LABEL_H_MM = 0.6               # laser text height (LDS-legible ≥ 0.5 mm)
# (2026-11-20, user) SLANTED crown like the nose's, for an aft-facing
# interface. (2026-11-21, user) FLIPPED: the band is TALLEST (aft-most) at the
# inner diameter and shortest at the outer one — less height at the OD —
# under acceleration the mating plug wedges into the cone, so the contacts get
# a normal-force component + wipe and self-centre (more compliant than flat).
# (2026-11-21, user: "flat and screwed; height is precious") FLAT contact face:
# no cone — the mating part is centred / keyed by the 3 uneven screw positions
# and uses SPRING contacts (no wipe needed); saves the 2.3 mm slope of the 30°
# cone. None → the nose crown's cone (NI.BEVEL_CONE_DEG).
CAP_CONE_DEG = 0.0


def cone_deg() -> float:
    from smash.export import nose_interface as NI
    return NI.BEVEL_CONE_DEG if CAP_CONE_DEG is None else CAP_CONE_DEG


# (2026-11-21, user) cone FLIPPED: the band is TALLEST (aft-most) at the
# inner diameter and shortest at the OD — less height at the OD.
CAP_HIGH_AT = "inner"            # "inner" (2026-11-21) | "outer" (the 2026-11-20 cone)


def tip_z(r: float, z_plate: float, r_out: float = 17.9) -> float:
    """Aft face of the crown band (wall tips) at radius r: T below the plate
    at its short edge, dropping aft toward the tall edge (the inner edge
    since 2026-11-21; the outer edge before)."""
    from smash.export import nose_interface as NI
    t = math.tan(math.radians(cone_deg()))
    d = (r_out - r) if CAP_HIGH_AT == "inner" else (r - NI.CROWN_R_IN_MM)
    return z_plate - NI.TOOTH_H_MM - d * t


def _sector(cq, a_center: float, half_w_deg: float, r0: float, r1: float, z0: float, z1: float,
            pts: list | None = None):
    pts = pts or [(r0, z0), (r1, z0), (r1, z1), (r0, z1)]
    w = (cq.Workplane("XZ").polyline(pts).close()
         .revolve(2.0 * half_w_deg, (0, 0, 0), (0, 1, 0)))
    c = w.val().Center()
    return w.rotate((0, 0, 0), (0, 0, 1), a_center - math.degrees(math.atan2(c.y, c.x)))


def build_aft_cap(cq, cap: dict, r_out: float, z_top: float = 0.0):
    """Cap body (aft view = −Z): plate r CAP_R_OPEN → r_out under z_top, crown
    band r CROWN_R_IN → r_out below it — its aft face a CONE, tallest (aft-most)
    at the inner edge, shortest at r_out (2026-11-21) — with a groove (floor on the cone) at every contact /
    GND position (screw positions stay solid), 3 counterbored screw holes."""
    from smash.export import nose_interface as NI
    T = NI.TOOTH_H_MM
    z_plate = z_top - CAP_PLATE_T_MM
    body = (cq.Workplane("XY").circle(r_out).circle(CAP_R_OPEN_MM)
            .extrude(CAP_PLATE_T_MM).translate((0, 0, z_plate)))
    r_in = NI.CROWN_R_IN_MM
    # conical band: flat on the plate (overlapping it 0.2 for a clean union),
    # aft face = the cone (tip_z), low at r_out
    band = (cq.Workplane("XZ").polyline([(r_in, z_plate + 0.2), (r_out, z_plate + 0.2),
                                         (r_out, tip_z(r_out, z_plate, r_out)),
                                         (r_in, tip_z(r_in, z_plate, r_out))]).close()
            .revolve(360.0, (0, 0, 0), (0, 1, 0)))
    body = body.union(band)
    ri, ro = r_in - 0.01, r_out + 0.01
    groove = [(ri, tip_z(ri, z_plate, r_out) - 0.01), (ro, tip_z(ro, z_plate, r_out) - 0.01),
              (ro, tip_z(ro, z_plate, r_out) + T), (ri, tip_z(ri, z_plate, r_out) + T)]
    for c in cap["contacts"]:
        if c["role"] in ("key", "screw"):
            continue
        # groove floor = the cone, T deep (constant along the slant)
        body = body.cut(_sector(cq, c["angle_deg"], CAP_GROOVE_HALF_DEG, ri, ro, 0, 0,
                                pts=groove))
    from smash.export.spacer_step import cell_centres_xy, cell_wire_pads_xy
    for x, y in list(cell_centres_xy()) + list(cell_wire_pads_xy()):
        body = body.cut(cq.Workplane("XY").center(x, y).circle(CAP_LEAD_POCKET_D_MM / 2.0)
                        .extrude(CAP_LEAD_POCKET_DEPTH_MM + 0.01)
                        .translate((0, 0, z_top - CAP_LEAD_POCKET_DEPTH_MM)))
    for ang in CAP_SCREW_ANGLES_DEG:
        x, y = CAP_SCREW_R_MM * math.cos(math.radians(ang)), CAP_SCREW_R_MM * math.sin(math.radians(ang))
        hole = (cq.Workplane("XY").center(x, y).circle(CAP_SCREW_CLEAR_D_MM / 2.0)
                .extrude(CAP_PLATE_T_MM + 2.0).translate((0, 0, z_plate - 1.0)))
        cb = (cq.Workplane("XY").center(x, y).circle(CAP_SCREW_HEAD_D_MM / 2.0)
              .extrude(CAP_SCREW_CB_MM + 0.01).translate((0, 0, z_plate - 0.01)))
        body = body.cut(hole).cut(cb)
    for ang in CAP_LOCATE_ANGLES_DEG:                  # fixture dowel holes (aft face)
        x, y = CAP_LOCATE_R_MM * math.cos(math.radians(ang)), CAP_LOCATE_R_MM * math.sin(math.radians(ang))
        body = body.cut(cq.Workplane("XY").center(x, y).circle(CAP_LOCATE_D_MM / 2.0)
                        .extrude(CAP_LOCATE_DEPTH_MM).translate((0, 0, z_plate)))
    return body


def face_svg(cap: dict, r_out: float) -> str:
    """Aft view of the cap face: groove sectors + radially aligned gate names."""
    from smash.export import nose_interface as NI
    S = 10.0                                              # px per mm
    W = 2 * (r_out + 6) * S
    c = W / 2

    def P(r, a):                                          # aft view: mirror X
        return c - r * math.cos(math.radians(a)) * S, c - r * math.sin(math.radians(a)) * S
    el = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{W:.0f}" '
          f'viewBox="0 0 {W:.0f} {W:.0f}" font-family="Helvetica, Arial, sans-serif">',
          f'<rect width="100%" height="100%" fill="white"/>',
          f'<circle cx="{c}" cy="{c}" r="{r_out * S}" fill="#e9dfc4" stroke="#333"/>',
          f'<circle cx="{c}" cy="{c}" r="{NI.CROWN_R_IN_MM * S}" fill="#f4eedc" stroke="#999"/>',
          f'<circle cx="{c}" cy="{c}" r="{CAP_R_OPEN_MM * S}" fill="white" stroke="#333"/>',
          f'<circle cx="{c}" cy="{c}" r="{(NI.CROWN_R_IN_MM - 0.3) * S}" fill="none" '
          f'stroke="#b8860b" stroke-width="4"/>']             # GND ring (LDS)
    for t in cap["contacts"]:
        a = t["angle_deg"]
        if t["role"] not in ("key", "screw"):
            h = CAP_GROOVE_HALF_DEG
            pts = [P(NI.CROWN_R_IN_MM, a - h), P(r_out, a - h), P(r_out, a + h), P(NI.CROWN_R_IN_MM, a + h)]
            col = "#c9a227" if t["role"] == "signal" else "#8a8a8a"
            el.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                      + f'" fill="{col}" stroke="#555" stroke-width="0.5"/>')
        # keep clear of the screw heads: nudge a neighbour's label away
        for sa in CAP_SCREW_ANGLES_DEG:
            dd = (a - sa + 180.0) % 360.0 - 180.0
            if 0 < abs(dd) < LABEL_SCREW_CLEAR_DEG:
                a = sa + math.copysign(LABEL_SCREW_CLEAR_DEG, dd)
        x, y = P(LABEL_R_MM, a)
        # radial: along the centre → label direction in the drawing, flipped
        # where it would read upside-down (anchored at the groove end)
        rot = math.degrees(math.atan2(y - c, x - c))
        anchor = "end"
        if 90.0 < rot % 360.0 < 270.0:
            rot -= 180.0
            anchor = "start"
        if not t["label"]:
            continue
        el.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{LABEL_H_MM * S:.1f}" '
                  f'text-anchor="{anchor}" dominant-baseline="middle" '
                  f'transform="rotate({rot:.1f} {x:.1f} {y:.1f})">{t["label"]}</text>')
    for ang in CAP_SCREW_ANGLES_DEG:
        x, y = P(CAP_SCREW_R_MM, ang)
        el.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{CAP_SCREW_HEAD_D_MM / 2 * S}" '
                  f'fill="white" stroke="#333"/>')
    el.append(f'<text x="{c}" y="{c}" font-size="{1.2 * S}" text-anchor="middle" '
              f'dominant-baseline="middle">clamp tabs (aft_end_board)</text>')
    el.append("</svg>")
    return "\n".join(el)


def contact_md(cap: dict) -> str:
    from smash.export import nose_interface as NI
    rows = ["| tooth | angle ° | lane ° | net | label | role |", "|---|---|---|---|---|---|"]
    for t in cap["contacts"]:
        la = t.get("lane_angle")
        rows.append(f"| {t['tooth']} | {t['angle_deg']:.2f} | "
                    f"{'—' if la is None else f'{la:.2f}'} | {t['net'] or '—'} | "
                    f"{t['label']} | {t['role']} |")
    n_sig = sum(1 for t in cap["contacts"] if t["role"] == "signal")
    gl = cap.get("gnd_link") or {}
    return (
        "# aft_end_cap — the aft public interface (generated)\n\n"
        f"PEEK-LDS cap, crown facing AFT: {cap['n_teeth']}-position block crown ({360 / cap['n_teeth']:g}° "
        "pitch, own grid; groove "
        f"{2 * CAP_GROOVE_HALF_DEG:.2f}°, r {NI.CROWN_R_IN_MM}–17.9 mm) on a {cone_deg():g}° CONE, "
        "(2026-11-21: FLAT, 0°, screwed — height is precious; spring contacts on the mating "
        "side, the 3 uneven screw positions centre + key it); a non-zero cone wedges the mating plug, giving the "
        "contacts a normal-force component, wipe and self-centring (compliant contacts). "
        f"{n_sig} signal contacts, "
        f"teeth {', '.join(map(str, cap['screw_teeth']))} = SCREW positions (no groove; their "
        "uneven spacing is the orientation key), the rest GND (joined by an LDS "
        f"ring at the crown's inner edge; linked over the skin to the aft-board GND "
        f"castellation at {gl.get('castellation_deg', '—')}° via tooth {gl.get('tooth', '—')}).\n\n"
        "- Each groove's lane comes down the sleeve's outer face, past aft_end_board, over the "
        "cap's outer skin (order-preserving fan, no crossings) into the groove floor (LDS, "
        "Cu + Ni / hard Au). Gate names lasered radially, "
        f"{LABEL_H_MM} mm text running inward from r {LABEL_R_MM} (aft_end_cap_face.svg).\n"
        f"- Top face: Ø{CAP_LEAD_POCKET_D_MM} × {CAP_LEAD_POCKET_DEPTH_MM} mm pockets over the "
        "cells' lead stubs on aft_end_board (3 − pins at the cell axes, 3 + wires round the "
        "potting-channel exit).\n"
        f"- Central opening Ø{2 * CAP_R_OPEN_MM:.1f}: exposes aft_end_board's 17 parachute CLAMP "
        "tabs (nichrome wires are clamped, not soldered) and the two parachute-cutter pads at "
        "the centre.\n"
        f"- Fixing: 3 × {CAP_SCREW} at r {CAP_SCREW_R_MM}, in the holder's solid webs between the "
        f"cells (never into a cell bore; tapped M2, Ø{HOLDER_TAP_DRILL_MM} drill × "
        f"{HOLDER_TAP_DEPTH_MM} mm from the holder's bottom face) "
        f"({', '.join(f'{a:g}°' for a in CAP_SCREW_ANGLES_DEG)}), through the cap and "
        "aft_end_board (Ø2.2 holes).\n"
        + (f"- ⚠ No tooth / lane for: {', '.join(cap['missing'])}\n" if cap.get("missing") else "")
        + "\n## Contact map\n\n" + "\n".join(rows) + "\n")


def write_aft_cap(contract: dict, out_dir, r_out: float = 17.9) -> dict | None:
    """aft_end_cap.step + .md + _face.svg into `out_dir`. None without a cap."""
    cap = (contract or {}).get("aft_cap")
    if not cap:
        return None
    import cadquery as cq
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    body = build_aft_cap(cq, cap, r_out)
    cq.exporters.export(body, str(out_dir / "aft_end_cap.step"))
    (out_dir / "aft_end_cap.md").write_text(contact_md(cap))
    (out_dir / "aft_end_cap_face.svg").write_text(face_svg(cap, r_out))
    return {"dir": out_dir, "n_signal": sum(1 for t in cap["contacts"] if t["role"] == "signal"),
            "missing": cap.get("missing", []), "valid": body.val().isValid(),
            "solids": body.solids().size()}
