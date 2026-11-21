"""77 GHz radome geometry for the radar cup's closed nose (2026-11-18).

The nose_cap PCB is retired. The radar board (AWR1843AOP, antennas on the
package) is fixed into the closed nose of the config's one-piece PEEK-LDS cup
(`smash.export.cup_noses`). This module turns the radar's resolved top-face
placements into the nose features of that cup:

  * a flat half-wave **radome window** over the AoP: thickness
    t = n·λ0 / (2·√εr), its inner face RADOME_GAP_MM (≈ λ0/2) above the AoP;
  * a **no-laser / no-copper keep-out** = the AoP field-of-view cone projected
    onto the end wall (no LDS activation, no gate, no weld line there);
  * a **dam rib** on the inside of the end wall around the AoP pocket that
    seats on the radar top face, so the black Stycast (a ~0.8 dB/mm 77 GHz
    absorber) never enters the radome cavity during the pour;
  * a raised **hood** over every top-face part taller than the end wall's
    inner face (the UJ20 USB-C), plus the radial **USB-C window** in the cup
    wall in front of its mouth (it exits through the radar's N chord);
  * **IR through-holes** over D_IR_TX / D_IR_WAKE (PEEK-LDS is opaque at
    940 nm; the recessed hole is part of the wake sensor's sunlight rejection).

All geometry is returned as plain numbers (physical stack frame: math y-up,
+Z toward the nose, angles as in `smash.parts.castellations`), so it can be
unit-tested without cadquery; `cup_noses` builds the solids from it.

⚠ RADOME_ER is the vendor's 1 GHz value for TECACOMP PEEK LDS. The LDS
additive moves εr / tanδ at 77 GHz — measure on moulded plaques (0.9 / 1.0 /
1.1 mm, free-space or Fabry-Perot) and re-set RADOME_ER before tooling.
"""
from __future__ import annotations

import dataclasses
import math

C0_MM_GHZ = 299.792458          # c in mm·GHz
RADOME_F_GHZ = 77.0
RADOME_ER = 3.6                 # ⚠ TECACOMP PEEK LDS @ 1 GHz (vendor) — placeholder
RADOME_ORDER = 1                # half-wave order n (n = 1 → thinnest window)
RADOME_TOL_MM = 0.05            # ± window thickness (transmission stays > ~-0.5 dB)
RADOME_FOV_HALF_DEG = 60.0      # AoP azimuth/elevation field of view, half-angle
RADOME_GAP_MM = None            # None → λ0/2 at RADOME_F_GHZ (≈ 1.95 mm)
PART_CLEARANCE_MM = 0.3         # end wall / hood → part top
HOOD_MARGIN_MM = 0.4            # hood bore → part body (each side)
DAM_RIB_W_MM = 0.8
DAM_MARGIN_MM = 0.6             # dam rib inner edge → AoP body
IR_HOLE_MIN_D_MM = 2.0
IR_HOLE_MARGIN_MM = 0.3
USB_WINDOW_MARGIN_MM = 0.5      # around the UJ20 mouth (8.94 × 3.26 mm)
USB_MOUTH_W_MM, USB_MOUTH_H_MM = 8.94, 3.26
_USB_REF, _AWR_REF = "J_USB_C", "U_AWR"
_IR_REFS = ("D_IR_TX", "D_IR_WAKE")
# Bodies the footprint does not declare (fallbacks, mm).
_FALLBACK_SIZE = {"D_IR_TX": (2.0, 1.25), "D_IR_WAKE": (5.0, 4.3),
                  _USB_REF: (8.94, 7.35)}
_FALLBACK_HEIGHT = {"D_IR_TX": 0.85, "D_IR_WAKE": 1.0}


def wavelength_mm(f_ghz: float = RADOME_F_GHZ) -> float:
    return C0_MM_GHZ / f_ghz


def window_thickness_mm(n: int = RADOME_ORDER, er: float = RADOME_ER,
                        f_ghz: float = RADOME_F_GHZ) -> float:
    """Half-wave radome: t = n·λ0 / (2·√εr) — reflection-free at f for any n."""
    return n * wavelength_mm(f_ghz) / (2.0 * math.sqrt(er))


def radome_gap_mm(f_ghz: float = RADOME_F_GHZ) -> float:
    """AoP top → radome inner face. λ0/2 keeps the residual reflection in
    phase with the radiator (TI AoP radome guidance: multiples of λ0/2)."""
    return RADOME_GAP_MM if RADOME_GAP_MM is not None else wavelength_mm(f_ghz) / 2.0


@dataclasses.dataclass
class Part:
    ref: str
    x: float                    # physical frame, mm
    y: float
    w: float                    # body extent along physical x / y
    h: float
    height: float               # above the board top face


@dataclasses.dataclass
class RadarNose:
    """Numbers for the radar cup nose, all relative to the radar top face
    (z = 0) in the physical stack frame."""
    window_t_mm: float
    gap_mm: float
    end_in_z: float             # end-wall inner face above the radar top face
    aop: Part
    fov_keepout_half_mm: tuple  # (half-x, half-y) of the keep-out rectangle on the OUTER face
    dam: tuple                  # (x0, y0, x1, y1) inner edge of the dam rib
    hoods: list                 # [Part] — parts taller than end_in_z
    ir_holes: list              # [(ref, x, y, d)]
    usb: Part | None
    usb_window: dict | None     # {"angle_deg", "w", "z0", "z1"} radial cut in the wall
    warnings: list


def _phys(M, x, y):
    """Board-local → physical (M is orthogonal: physical = Mᵀ · local)."""
    (m11, m12), (m21, m22) = M
    return (m11 * x + m21 * y, m12 * x + m22 * y)


def _part_of(placement, M) -> Part | None:
    chip = placement.item
    fp = getattr(chip, "footprint", None)
    ref = getattr(chip, "ref", "")
    wh = getattr(fp, "size_mm", None) if fp is not None else None
    if not wh and fp is not None:
        poly = getattr(fp, "body_outline", None) or getattr(fp, "courtyard", None)
        if poly:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            wh = (max(xs) - min(xs), max(ys) - min(ys))
    wh = wh or _FALLBACK_SIZE.get(ref)
    if not wh:
        return None
    rot = (getattr(placement, "rotation_deg", 0.0) or 0.0) % 180.0
    w, h = wh if abs(rot - 90.0) > 45.0 else (wh[1], wh[0])
    hgt = (getattr(chip, "height_mm", None)
           or (getattr(fp, "height_mm", None) if fp is not None else None)
           or _FALLBACK_HEIGHT.get(ref, 1.0))
    x, y = _phys(M, *placement.position_mm)
    if abs(M[0][0]) < 0.5:                 # 90° frame turn swaps the extents
        w, h = h, w
    return Part(ref, round(x, 4), round(y, 4), w, h, float(hgt))


def radar_nose(radar_board, M=((1, 0), (0, 1)), *, board_r_mm: float = 17.0) -> RadarNose:
    """Radome / dam / hood / opening numbers from the radar's top-face parts.
    `M` maps physical → radar-local (`castellations.board_fold_transforms`)."""
    warnings = []
    parts = {}
    for p in getattr(radar_board, "chip_placements", []) or []:
        if getattr(p, "face", "top") != "top":
            continue
        pt = _part_of(p, M)
        if pt is not None:
            parts[pt.ref] = pt
    t = window_thickness_mm()
    gap = radome_gap_mm()
    aop = parts.get(_AWR_REF)
    if aop is None:                          # isolated render: centred 15 mm AoP
        aop = Part(_AWR_REF, 0.0, 0.0, 15.0, 15.0, 0.9)
        warnings.append("U_AWR not placed on radar_module — radome centred on the axis")
    end_in = aop.height + gap
    # FoV cone from the AoP body edges through the window to the OUTER face.
    reach = (gap + t) * math.tan(math.radians(RADOME_FOV_HALF_DEG))
    fov = (aop.w / 2 + reach, aop.h / 2 + reach)
    dam = (aop.x - aop.w / 2 - DAM_MARGIN_MM, aop.y - aop.h / 2 - DAM_MARGIN_MM,
           aop.x + aop.w / 2 + DAM_MARGIN_MM, aop.y + aop.h / 2 + DAM_MARGIN_MM)
    hoods = [pt for ref, pt in parts.items()
             if ref != _AWR_REF and pt.height + PART_CLEARANCE_MM > end_in]
    ir = []
    for ref in _IR_REFS:
        pt = parts.get(ref)
        if pt is None:
            continue
        d = max(IR_HOLE_MIN_D_MM, min(pt.w, pt.h) + 2 * IR_HOLE_MARGIN_MM)
        ir.append((ref, pt.x, pt.y, round(d, 3)))
    usb = parts.get(_USB_REF)
    usb_win = None
    if usb is not None:
        ang = math.degrees(math.atan2(usb.y, usb.x)) % 360.0
        usb_win = {"angle_deg": round(ang, 2),
                   "w": USB_MOUTH_W_MM + 2 * USB_WINDOW_MARGIN_MM,
                   "z0": -0.3,     # just above the radar castellation vias (board mid-plane)
                   "z1": USB_MOUTH_H_MM + USB_WINDOW_MARGIN_MM}
    # Sanity: nothing that opens or carries copper may sit in the FoV keep-out.
    # (2026-11-21, user) the IR-hole-in-FoV warning is retired: the nose is
    # open (no radome to cut) and the radar build likely drops the IR parts.
    for hd in hoods:
        if (abs(hd.x - aop.x) < fov[0] + hd.w / 2
                and abs(hd.y - aop.y) < fov[1] + hd.h / 2):
            warnings.append(f"{hd.ref} ({hd.height:.2f} mm tall, above the AoP) stands in "
                            f"the radar FoV — it may shadow low-elevation returns")
    return RadarNose(window_t_mm=round(t, 4), gap_mm=round(gap, 4),
                     end_in_z=round(end_in, 4), aop=aop,
                     fov_keepout_half_mm=(round(fov[0], 3), round(fov[1], 3)),
                     dam=tuple(round(v, 3) for v in dam), hoods=hoods,
                     ir_holes=ir, usb=usb, usb_window=usb_win, warnings=warnings)


def window_spec_md(n: RadarNose) -> str:
    lam = wavelength_mm()
    return (
        f"- Radome window: flat, normal to boresight, seamless; t = n·λ0/(2√εr) = "
        f"{n.window_t_mm:.3f} ± {RADOME_TOL_MM} mm (n = {RADOME_ORDER}, f = "
        f"{RADOME_F_GHZ:g} GHz, λ0 = {lam:.3f} mm, εr = {RADOME_ER} ⚠ 1 GHz vendor value — "
        "measure at 77 GHz on moulded plaques before tooling).\n"
        f"- AoP top → radome inner face: {n.gap_mm:.3f} mm (λ0/2); end-wall inner face "
        f"{n.end_in_z:.3f} mm above the radar top face. The whole end wall is the window "
        "thickness so the radome needs no local step.\n"
        f"- No laser / copper / gate / weld line / text inside the FoV keep-out "
        f"(±{n.fov_keepout_half_mm[0]:.2f} × ±{n.fov_keepout_half_mm[1]:.2f} mm round the AoP "
        f"centre, {RADOME_FOV_HALF_DEG:g}° half-angle cone). Surface finish ≤ Ra 1.6; no "
        "metallic pigment / paint over it.\n"
        f"- Dam rib {DAM_RIB_W_MM} mm wide round the AoP pocket (inner edge "
        f"{DAM_MARGIN_MM} mm off the package) seats on the radar top face: keeps the black "
        "Stycast out of the radome cavity (pocket stays air).\n")
