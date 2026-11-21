"""Per-config one-piece PEEK-LDS "cup": sleeve + closed nose in ONE moulding.

(2026-11-18, user) The nose_cap PCB is retired and the sleeve is no longer two
half-shells. Each configuration gets its own cup. Every nose is a FLAT face
(meplat) blended into the cylinder by a tangent elliptical shoulder — as flat
as the payload allows, but with no corners (aerodynamics, all configs):

  core         plain flat end over companion_compute (no payload)
  core_radar   very flat: the flat face IS the λ/2 radome (`nose_radome`)
  core_qpd     plano-convex lens flush in the flat face over the MT03-092
  core_camera  plano-convex lens flush in the flat face over the AR0234
               (optical cups: one variant per wavelength band — the lens
               height above the sensor is its focal length at λ, `nose_optics`)

Assembly (main route): the payload board (radar / QPD / camera) is screwed or
glued into the cup's nose against moulded STOP BOSSES (the axial datum), the
compute↔payload gap ring drops in behind it, the common core tower slides in
from the open aft end, the vias are soldered to the castellations from outside,
then the whole assembly is potted INSIDE the cup (nose down, bottom-up fill
down the feed groove). The cup is picked at assembly time — the core tower and
`companion_compute` (which carries the castellations of ALL three payloads,
`castellations.castellation_contract`) are identical in every config; a cup's
laser pattern only activates the lanes its payload uses (`active_lanes`).

Fallback (SLEEVE_SPLIT = "nose_cup"): a common core sleeve + a short
config-specific nose cup joined at the compute↔payload gap, anchored by radial
screws into that gap's ring so the vias never carry the joint shear.

Frame: the physical stack frame of `sleeve_step` (z = 0 at aft_end's aft
face, +Z to the nose, castellation angles).
"""
from __future__ import annotations

import dataclasses
import math

from smash.export import nose_radome as NR

# Config → nose payload board (None = plain closed end).
# (2026-11-18) `core` wears the USB nose (doubles as the cap); every nose plugs
# into the same crown (nose_interface).
PAYLOADS = {"core": "usb_nose", "core_radar": "radar_module",
            "core_qpd": "qpd_module", "core_camera": "camera_module"}
PAYLOAD_BOARDS = ("radar_module", "qpd_module", "camera_module", "usb_nose")
CORE_TOP = "companion_compute"
SLEEVE_SPLIT = "unified"        # "unified" (one moulding) | "nose_cup" (fallback)

END_WALL_MM = 0.8               # nose wall (core / optical cups; radar = λ/2 window)
PART_CLEARANCE_MM = 0.3         # inner nose surface → payload part tops
# ── Nose profile (2026-11-18, user: "as flat as possible but aerodynamic") ──
# Every cup ends in a FLAT face (meplat) joined to the cylinder by an
# ELLIPTICAL SHOULDER: a quarter-ellipse centred on the meplat edge, so the
# surface is tangent to the cylinder at the shoulder start AND tangent to the
# flat face at the meplat edge — no corners anywhere. The nose is fitted as
# low (flat) as the payload allows: the largest shoulder ≤ shoulder_mm whose
# INNER surface clears every payload top-face part; radar may step its
# radome gap up by λ0/2 to make room; optical noses are pinned by the lens.
# ⚠ Aero: blunt supersonic drag is dominated by the meplat area — the meplat
# ratio + shoulder length want a CFD / ballistic check per launch platform
# (Bofors 40 mm, M777, M252 — sim/launch/platforms.py in smash-electronics).
NOSE_PROFILE = {
    None:            {"meplat_r": 10.0, "shoulder_mm": 5.0},   # no nose module
    "usb_nose":      {"meplat_r": 10.0, "shoulder_mm": 4.0},   # USB-C side window + IR pipes
    "radar_module":  {"meplat_r": 13.0, "shoulder_mm": 3.5},   # very flat (radome)
    "qpd_module":    {"meplat_r": 8.0, "shoulder_mm": 6.0},
    "camera_module": {"meplat_r": 8.0, "shoulder_mm": 6.0},
}
SHOULDER_MIN_MM = 1.5
USB_VERT_H_MM = 6.3              # Same Sky UJ20-C-V-G-SMT-23B-P16-TR-X5 (vendor STEP)
USB_MOUTH_SLOT_MM = (9.4, 3.8)   # plug opening in the nose flat face (mouth 8.94 × 3.26 + margin)
SHOULDER_STEP_MM = 0.25
RADOME_MAX_ORDER = 4            # radome gap may step to k·λ0/2, k ≤ this
CORE_RAISE_MAX_MM = 10.0
OPTICAL_DAM_W_MM = 0.8          # light-tube wall from the payload top to the lens collar
# Payload stop bosses (axial datum + screw / glue land on the payload's top face).
STOP_R_MM = 11.5                # inside the Ø27 payload board (2026-11-18)
STOP_D_MM = 2.4
STOP_PILOT_D_MM = 1.1           # M1.4 thread-forming screw into PEEK (board hole Ø1.6)
STOP_PILOT_DEPTH_MM = 2.5
STOP_CANDIDATES_DEG = (285.0, 165.0, 45.0, 135.0, 225.0, 315.0, 15.0, 195.0, 75.0, 255.0)
# Fallback joint screws (radial, into the compute↔payload gap ring).
JOINT_SCREW_D_MM = 1.6
JOINT_SCREW_ANGLES_DEG = (285.0, 165.0, 45.0)


# (2026-11-19, user) "the nose doesn't have to close; a flat ridge on the side is
# enough": every nose cone is an OPEN straight shell (no shoulder / meplat).
OPEN_NOSE = True
OPEN_RIDGE_CLEAR_MM = 0.3       # ridge top over the tallest payload part
# (2026-11-20, user) NOSE CAP on top of the open nose cone: a λ/2 radome lid
# that CARRIES the 2 retaining tabs (stainless inserts); the tabs drop through
# SLOTS in the nose cone to the screws in the sleeve band. Its inner PRESS RIM
# bears on the payload board's edge: cap → board → land ring → crown is ONE
# clamp, so payload PEEK + board are pressure-fixed (pins only locate them).
CAP_T_MM = None                 # None → the radar's λ/2 window (nose_radome)
CAP_RIDGE_GAP_MM = 0.1          # lid underside over the nose-cone ridge (rim bears first)
CAP_RIM_W_MM = 0.8              # press rim on the board edge annulus (r_in − w … r_in − 0.05)
CAP_MOUTH_MARGIN_MM = 0.2       # lid cut-out round a part that rises through it (USB-C)
TAB_SLOT_CLEAR_MM = 0.1         # nose-cone slot round the cap's tab (each side)


def cap_t_mm() -> float:
    from smash.export import nose_radome as NR
    return CAP_T_MM if CAP_T_MM is not None else round(NR.window_thickness_mm(), 4)


def _open_profile(prof, parts, z_board: float, z_feature: float):
    """Straight open shell up to max(feature top, tallest part + clearance)."""
    tallest = max([z_board + p.height for p in parts] or [z_board])
    z_top = _ceil4(max(z_feature, tallest + OPEN_RIDGE_CLEAR_MM))
    return NoseProfile(prof.r_out, END_WALL_MM, prof.r_out - END_WALL_MM, z_top, z_top,
                       open=True)


def _ceil4(z: float) -> float:
    """Round UP to 0.1 µm: the nose top must never dip below what it clears."""
    return math.ceil(z * 1e4 - 1e-9) / 1e4


@dataclasses.dataclass
class NoseProfile:
    """Outer nose = cylinder r_out up to z_s, then a quarter-ellipse shoulder
    (centre (meplat_r, z_s), semi-axes a = r_out − meplat_r radial, L = z_top −
    z_s axial) into a flat face at z_top. Inner = the same construction for
    r_in = r_out − wall and L − wall (flat inner face at z_top − wall)."""
    r_out: float
    wall: float
    meplat_r: float
    z_s: float
    z_top: float
    open: bool = False           # (2026-11-19, user) open straight shell, flat ridge

    @property
    def L(self) -> float:
        return self.z_top - self.z_s

    @property
    def r_in(self) -> float:
        return self.r_out - self.wall

    @property
    def z_top_in(self) -> float:
        return self.z_top - self.wall

    def outer_pts(self, n: int = 24) -> list:
        """[(r, z)] from (r_out, z_s) to (meplat_r, z_top), tangent at both ends."""
        a = self.r_out - self.meplat_r
        return [(self.meplat_r + a * math.cos(t), self.z_s + self.L * math.sin(t))
                for t in (0.5 * math.pi * k / n for k in range(n + 1))]

    def inner_pts(self, n: int = 24) -> list:
        a = self.r_in - self.meplat_r
        b = self.L - self.wall
        return [(self.meplat_r + a * math.cos(t), self.z_s + b * math.sin(t))
                for t in (0.5 * math.pi * k / n for k in range(n + 1))]

    def inner_z_at(self, r: float) -> float:
        """Height of the inner nose surface above radius r."""
        if self.open:
            return float("inf")                # open front: nothing overhead
        if r <= self.meplat_r:
            return self.z_top_in
        a = self.r_in - self.meplat_r
        if r >= self.r_in or a <= 0:
            return self.z_s
        b = self.L - self.wall
        return self.z_s + b * math.sqrt(max(0.0, 1.0 - ((r - self.meplat_r) / a) ** 2))

    def aero_md(self) -> str:
        R = self.r_out
        if self.open:
            return (f"- Nose: OPEN straight shell (user 2026-11-19), Ø{2 * R:.1f}, wall "
                    f"{self.wall:g} mm, ending in a FLAT RIDGE at {self.z_top:.2f} mm — no "
                    "shoulder, no closed face; the potted payload is the front. Radome / lens "
                    "are separate inserts.\n")
        return (f"- Nose: flat face Ø{2 * self.meplat_r:.1f} (meplat ratio "
                f"{self.meplat_r / R:.2f}, area {100 * (self.meplat_r / R) ** 2:.0f} % of the "
                f"calibre) + elliptical shoulder {self.L:.2f} mm long ({self.L / (2 * R):.2f} "
                "calibres), tangent to the cylinder and to the flat face (no corners). "
                "⚠ Blunt-nose drag at supersonic speed is set mostly by the meplat area — "
                "check with CFD / ballistics per platform.\n")


@dataclasses.dataclass
class NoseSpec:
    config: str
    payload: str | None
    band: str | None              # optical: wavelength band ("laser" / "ir")
    z_payload: tuple | None       # (z0, z1) of the payload board (or compute for core)
    profile: NoseProfile
    hoods: list                   # [(x, y, w, h, z_top_in)] fallback only (warned)
    holes: list                   # [(kind, x, y, d)] vertical through the nose wall
    dam: tuple | None             # radar: (x0, y0, x1, y1) inner edge of the AoP dam rib
    tube: dict | None             # optical: light tube + lens collar
    lens: dict | None             # optical: lens placement / optics numbers
    radial_windows: list          # [{"angle_deg", "w", "z0", "z1", "r_from", "what"}]
    stops: list                   # [angle_deg] payload stop bosses
    notes: list
    warnings: list
    pipes: list = dataclasses.field(default_factory=list)   # IR light pipes (see _ir_pipes)
    dam_rot_deg: float = 0.0      # (2026-11-21) dam rect turn about its centre (AoP at 45°)

    # compatibility helpers
    @property
    def z_end_in(self) -> float:
        return self.profile.z_top_in

    @property
    def end_t(self) -> float:
        return self.profile.wall


def payload_of(config: str):
    return PAYLOADS.get(config)


def cup_chain(boards: dict, chain: list, payload: str | None) -> list:
    """The stack a cup holds: the core chain up to companion_compute, then (if a
    payload) the compute↔payload gap + the payload board. The gap re-uses the
    maximalist compute↔radar spacer (same ring height for every payload)."""
    core = []
    for n in chain:
        core.append(n)
        if n == CORE_TOP:
            break
    if payload is None or payload not in boards:
        return core
    gap = next((n for n in chain if n.startswith("spacer_")
                and CORE_TOP in n and "radar_module" in n), None)
    return core + ([gap] if gap else []) + [payload]


def _fold_M(chain: list, name: str):
    from smash.layout.cavities import is_rotated_180
    ref = name if name in chain else CORE_TOP           # leaves take the compute frame
    return ((-1, 0), (0, -1)) if is_rotated_180(chain, ref) else ((1, 0), (0, 1))


def _top_parts(board, M) -> list:
    out = []
    for p in getattr(board, "chip_placements", []) or []:
        if getattr(p, "face", "top") != "top":
            continue
        if getattr(p.item, "manf_pn", "") in ("CASTELLATIONS", "LGA_lands"):
            continue
        pt = NR._part_of(p, M)
        if pt is not None:
            out.append(pt)
    return out


_STOP_EXTRA_KEEP: list = []


def _hole_keeps(board, M) -> list:
    """(x, y, half, half) keep regions for the board's potting holes (physical)."""
    out = []
    g = getattr(board, "geometry", None)
    for h in (getattr(g, "holes", None) or []):
        if getattr(h, "tag", "") == "potting":
            x, y = NR._phys(M, *h.position_mm)
            out.append((x, y, h.diameter_mm / 2 + 0.3, h.diameter_mm / 2 + 0.3))
    return out


def _pick_stops(parts, keep=(), n=3) -> list:
    """n stop-boss angles at STOP_R_MM, clear of the payload's top-face parts
    and of any extra (x, y, half-w, half-h) keep regions, spread round."""
    keep = list(keep) + list(_STOP_EXTRA_KEEP)
    def clear(a):
        x, y = STOP_R_MM * math.cos(math.radians(a)), STOP_R_MM * math.sin(math.radians(a))
        r = STOP_D_MM / 2 + 0.3
        for p in parts:
            if abs(x - p.x) < p.w / 2 + r and abs(y - p.y) < p.h / 2 + r:
                return False
        for kx, ky, hw, hh in keep:
            if abs(x - kx) < hw + r and abs(y - ky) < hh + r:
                return False
        return True
    got = []
    for a in STOP_CANDIDATES_DEG:
        if clear(a) and all(min(abs(a - g), 360 - abs(a - g)) >= 60.0 for g in got):
            got.append(a)
        if len(got) == n:
            break
    return got


def _part_r(p, margin: float = 0.0) -> float:
    """Farthest radius of a part's footprint (its worst point under the shoulder)."""
    return max(math.hypot(p.x + sx * (p.w / 2 + margin), p.y + sy * (p.h / 2 + margin))
               for sx in (-1, 1) for sy in (-1, 1))


def _misfits(prof: NoseProfile, parts, z_board: float, skip=()) -> list:
    return [p for p in parts if p.ref not in skip
            and prof.inner_z_at(_part_r(p)) < z_board + p.height + PART_CLEARANCE_MM]


def _fit_shoulder(r_out, wall, meplat_r, z_top, L_max, z_floor, parts, z_board, skip=()):
    """Longest shoulder ≤ L_max (most aerodynamic) that keeps the cylinder end
    ≥ z_floor and clears every part. Returns (profile, misfits)."""
    best = None
    L = L_max
    while L >= SHOULDER_MIN_MM - 1e-9:
        z_s = z_top - L
        if z_s >= z_floor - 1e-9 and L > wall + 0.2:
            prof = NoseProfile(r_out, wall, meplat_r, round(z_s, 4), _ceil4(z_top))
            bad = _misfits(prof, parts, z_board, skip)
            if not bad:
                return prof, []
            if best is None or len(bad) < len(best[1]):
                best = (prof, bad)
        L -= SHOULDER_STEP_MM
    if best is None:                 # nose lower than the shortest shoulder allows
        L = max(SHOULDER_MIN_MM, wall + 0.25)
        prof = NoseProfile(r_out, wall, meplat_r, round(z_top - L, 4), _ceil4(z_top))
        best = (prof, _misfits(prof, parts, z_board, skip))
    return best


# IR light pipes (2026-11-18): black Stycast is opaque at 940 nm, so each IR
# diode looks out through a moulded tube from the board (emitter) or from the
# package top (photodiode, over its active area) up through the nose wall.
IR_TX_PIPE_WALL_MM = 0.6
IR_PD_PIPE_R_IN_MM = 1.8          # VBPW34FAS ~2.65 mm square active area (slight corner vignetting)
IR_PD_PIPE_WALL_MM = 0.35         # tube OD = the 4.3 mm package width: seats on the package top


def _ir_pipes(parts, z_board: float) -> list:
    """[{ref, x, y, r_in, r_out, z0}] for the IR diodes among `parts`."""
    out = []
    for p in parts:
        if p.ref.startswith("D_IR_TX"):
            r_in = math.hypot(p.w, p.h) / 2 + 0.2
            out.append({"ref": p.ref, "x": p.x, "y": p.y, "r_in": round(r_in, 3),
                        "r_out": round(r_in + IR_TX_PIPE_WALL_MM, 3), "z0": z_board})
        elif p.ref.startswith("D_IR_WAKE"):
            out.append({"ref": p.ref, "x": p.x, "y": p.y, "r_in": IR_PD_PIPE_R_IN_MM,
                        "r_out": IR_PD_PIPE_R_IN_MM + IR_PD_PIPE_WALL_MM,
                        "z0": z_board + p.height})
    return out


def _pipes_md(pipes) -> str:
    if not pipes:
        return "- ⚠ No IR diodes found under this nose.\n"
    return ("- IR light pipes (moulded tubes, potting kept out; seal the nose end with a "
            "clear IR window plug, e.g. PC / sapphire disc): "
            + ", ".join(f"{q['ref']} Ø{2 * q['r_in']:.1f}" for q in pipes) + ".\n")


def _hoods_for(bad, z_board):
    return [(p.x, p.y, p.w + 2 * NR.HOOD_MARGIN_MM, p.h + 2 * NR.HOOD_MARGIN_MM,
             z_board + p.height + PART_CLEARANCE_MM) for p in bad]


def optical_bands(payload: str) -> list:
    from smash.export.nose_optics import OPTICS
    return list(OPTICS[payload]["bands"]) if payload in OPTICS else [None]


def _ridge_height(boards: dict, chain: list) -> float:
    """(2026-11-19, user) ONE nose-cone height for every config, set by the
    radar (cfr. radar): its tallest top-face part + clearance above the board."""
    rb = boards.get("radar_module")
    if rb is None:
        return 2.0
    parts = _top_parts(rb, _fold_M(chain, "radar_module"))
    need = max([p.height for p in parts] or [1.7]) + OPEN_RIDGE_CLEAR_MM
    # (2026-11-20) the CAP is the radome: its underside sits k·λ0/2 above the
    # AoP top (smallest k that clears every radar part); ridge = that − gap
    from smash.export import nose_radome as NR
    aop = next((p.height for p in parts if p.ref == "U_AWR"), None)
    if aop is None:
        return round(need, 4)
    half = NR.wavelength_mm() / 2.0
    k = max(1, math.ceil((need + CAP_RIDGE_GAP_MM - aop) / half - 1e-9))
    return round(aop + k * half - CAP_RIDGE_GAP_MM, 4)


def nose_spec(config: str, boards: dict, chain: list, band: str | None = None,
              r_out: float | None = None) -> NoseSpec:
    """Per-config nose; with OPEN_NOSE every shell ends at the SAME ridge height
    above its payload board (the radar's) — the configuration-specific shapes
    (lens, USB mouth, radome) belong to the finishing container (OD 40)."""
    n = _nose_spec(config, boards, chain, band=band, r_out=r_out)
    if not (OPEN_NOSE and n.payload and n.z_payload):
        return n
    z_top = _ceil4(n.z_payload[1] + _ridge_height(boards, chain))
    pr = n.profile
    n.profile = NoseProfile(pr.r_out, END_WALL_MM, pr.r_out - END_WALL_MM, z_top, z_top, open=True)
    if n.tube is not None:                  # optical: light-tube DAM only, up to the ridge
        n.tube = dict(n.tube, z1=z_top, collar_r_out=None, collar_z0=None)
    if n.lens is not None and n.payload in ("qpd_module", "camera_module"):
        n.lens = dict(n.lens, in_capsule=True)
    n.notes = [x for x in n.notes if not x.startswith("- Nose:")] + [n.profile.aero_md(),
               f"- Uniform nose ridge {z_top - n.z_payload[1]:.2f} mm above the payload board "
               "(all configs, set by the radar). Lens / USB mouth / radome = the finishing "
               "container (OD 40), configuration-specific.\n"]
    n.warnings = [w for w in n.warnings if "lens" not in w and "light-tube" not in w]
    return n


def _nose_spec(config: str, boards: dict, chain: list, band: str | None = None,
               r_out: float | None = None) -> NoseSpec:
    """Numbers for one config's nose (no cadquery). Optical payloads take a
    wavelength `band` (default: the first in nose_optics.OPTICS)."""
    from smash.export.sleeve_step import stack_z_map, SLEEVE_GAP_MM, SLEEVE_WALL_MM
    payload = payload_of(config)
    cchain = cup_chain(boards, chain, payload)
    zmap = stack_z_map(boards, cchain)
    notes, warnings = [], []
    r_out = r_out or (17.0 + SLEEVE_GAP_MM + SLEEVE_WALL_MM)
    if payload is not None and payload not in boards:
        warnings.append(f"{config}: payload {payload} not in this build — plain end")
        payload = None
    prm = NOSE_PROFILE[payload]

    if payload is None:
        top = boards.get(CORE_TOP)
        z1 = zmap[CORE_TOP][1] if CORE_TOP in zmap else max(z for _a, z in zmap.values())
        parts = _top_parts(top, _fold_M(chain, CORE_TOP)) if top is not None else []
        wall = END_WALL_MM
        h_c = max([p.height for p in parts if _part_r(p) <= prm["meplat_r"]] or [0.5])
        z_top = z1 + h_c + PART_CLEARANCE_MM + wall
        prof, bad = _fit_shoulder(r_out, wall, prm["meplat_r"], z_top, prm["shoulder_mm"],
                                  z1, parts, z1)
        raise_mm = 0.0
        while bad and raise_mm < CORE_RAISE_MAX_MM:
            raise_mm += SHOULDER_STEP_MM
            prof, bad = _fit_shoulder(r_out, wall, prm["meplat_r"], z_top + raise_mm,
                                      prm["shoulder_mm"], z1, parts, z1)
        hoods = _hoods_for(bad, z1)
        if bad:
            warnings.append(f"{config}: hoods needed over {', '.join(p.ref for p in bad)}")
        notes.append(prof.aero_md())
        pipes = []          # (2026-11-18, user) no IR in `core`: the pair lives on the payload boards
        notes.append(f"- Plain closed end over companion_compute, wall {wall} mm, inner "
                     f"surface ≥ {PART_CLEARANCE_MM} mm over every top-face part. No IR "
                     "openings (core has no IR link; health beacons = aft coil + piezo).\n")
        return NoseSpec(config, None, None, (zmap.get(CORE_TOP, (z1, z1))[0], z1), prof,
                        hoods, [], None, None, None, [], [], notes, warnings, pipes)

    z0, z1 = zmap[payload]
    M = _fold_M(chain, payload)
    parts = _top_parts(boards[payload], M)
    _STOP_EXTRA_KEEP[:] = _hole_keeps(boards[payload], M)   # stop bosses avoid potting holes

    if payload == "usb_nose":
        wall = END_WALL_MM
        h_c = max([p.height for p in parts if _part_r(p) <= prm["meplat_r"]] or [0.5])
        z_top = z1 + h_c + PART_CLEARANCE_MM + wall
        prof, bad = _fit_shoulder(r_out, wall, prm["meplat_r"], z_top, prm["shoulder_mm"],
                                  z1, parts, z1)
        raise_mm = 0.0
        while bad and raise_mm < CORE_RAISE_MAX_MM:
            raise_mm += SHOULDER_STEP_MM
            prof, bad = _fit_shoulder(r_out, wall, prm["meplat_r"], z_top + raise_mm,
                                      prm["shoulder_mm"], z1, parts, z1)
        hoods = _hoods_for(bad, z1)
        if bad:
            warnings.append(f"{config}: hoods needed over {', '.join(p.ref for p in bad)}")
        usb = next((p for p in parts if p.ref == "J_USB_C"), None)
        wins, holes = [], []
        if usb is not None:
            # VERTICAL USB-C (user): its mouth is flush with the flat face, the
            # plug goes in axially through a slot in the nose tip.
            z_need = z1 + USB_VERT_H_MM
            if prof.z_top < z_need:
                prof, bad2 = _fit_shoulder(r_out, wall, max(prm["meplat_r"], math.hypot(usb.x, usb.y) + 6.5),
                                           z_need, prm["shoulder_mm"], z1, parts, z1)
            holes.append(("usb_slot", usb.x, usb.y,
                          (USB_MOUTH_SLOT_MM[0], USB_MOUTH_SLOT_MM[1])))
        pipes = _ir_pipes(parts, z1)
        if OPEN_NOSE:           # receptacle top flush with the ridge; IR sees out directly
            prof = _open_profile(prof, parts, z1, z1 + USB_VERT_H_MM)
            holes, hoods, pipes = [], [], []
            warnings = [w for w in warnings if "hoods" not in w]
        notes.append(prof.aero_md())
        notes.append("- USB NOSE (the core's default cap): VERTICAL depot USB-C at the nose tip, "
                     f"mouth flush in a {USB_MOUTH_SLOT_MM[0]} × {USB_MOUTH_SLOT_MM[1]} mm slot in the "
                     "flat face (plug it while potting) + IR pair. Receptacle: Same Sky "
                     f"UJ20-C-V-G-SMT-23B-P16-TR-X5, {USB_VERT_H_MM} mm tall (⚠ check COO).\n")
        notes.append(_pipes_md(pipes))
        stops = _pick_stops(parts, [(q["x"], q["y"], q["r_out"], q["r_out"]) for q in pipes]
                            + [(usb.x, usb.y, 5.5, 3.0)] if usb is not None else [])
        return NoseSpec(config, payload, None, (z0, z1), prof, hoods, holes, None, None, None,
                        wins, stops, notes, warnings, pipes)

    if payload == "radar_module":
        rn = NR.radar_nose(boards[payload], M)
        wall = rn.window_t_mm
        lam2 = NR.wavelength_mm() / 2.0
        chosen = None
        for k in range(1, RADOME_MAX_ORDER + 1):
            z_top = z1 + rn.aop.height + k * lam2 + wall
            prof, bad = _fit_shoulder(r_out, wall, prm["meplat_r"], z_top,
                                      prm["shoulder_mm"], z1, parts, z1, skip=("U_AWR",))
            if not bad:
                chosen = (k, prof, [])
                break
            if chosen is None:
                chosen = (k, prof, bad)
        k, prof, bad = chosen
        hoods = _hoods_for(bad, z1)
        if bad:
            warnings.append("radar nose: no flat fit up to "
                            f"{RADOME_MAX_ORDER}·λ0/2 — hoods over {', '.join(p.ref for p in bad)}")
        gap = prof.z_top_in - (z1 + rn.aop.height)
        holes = []
        pipes = _ir_pipes(parts, z1)
        radome_t = wall
        if OPEN_NOSE:
            # (2026-11-19, user) NO radome in the cone: the final capsule (OD 40)
            # carries it. The open shell keeps only an AoP DAM collar insert so
            # the black potting stays off the antennas.
            prof = _open_profile(prof, parts, z1, z1 + rn.aop.height + 0.5)
            gap, k = None, None
            hoods, pipes = [], []
            warnings = [w for w in warnings if "hoods" not in w]
        wins = []
        if rn.usb_window and rn.usb is not None:
            u = rn.usb
            wins.append({"angle_deg": rn.usb_window["angle_deg"], "w": rn.usb_window["w"],
                         "z0": z1 + rn.usb_window["z0"], "z1": z1 + rn.usb_window["z1"],
                         "r_from": max(0.0, math.hypot(u.x, u.y) - 0.5),
                         "what": "USB-C mouth (UJ20 vertical)"})
        keep = [(rn.aop.x, rn.aop.y, rn.aop.w / 2 + NR.DAM_MARGIN_MM + NR.DAM_RIB_W_MM,
                 rn.aop.h / 2 + NR.DAM_MARGIN_MM + NR.DAM_RIB_W_MM)]
        keep += [(q["x"], q["y"], q["r_out"], q["r_out"]) for q in pipes]
        stops = _pick_stops(parts, keep)       # payload board screwed into the cap
        if gap is None:          # open nose, no radome: FoV is the capsule's concern
            return NoseSpec(config, payload, None, (z0, z1), prof, [], [], rn.dam, None,
                            {"radome": None}, [], stops, notes + [prof.aero_md(),
                            "- Radar: NO radome in the nose cone — the final capsule (OD 40) "
                            "carries it. An AoP DAM collar (insert, board → ridge) keeps the "
                            "black potting off the antennas; the space above the AoP stays air.\n"],
                            warnings + rn.warnings, [], dam_rot_deg=rn.dam_rot_deg)
        reach = (gap + wall) * math.tan(math.radians(NR.RADOME_FOV_HALF_DEG))
        fov_half = (rn.aop.w / 2 + reach, rn.aop.h / 2 + reach)
        fov_r = math.hypot(*fov_half)
        if max(fov_half) > prof.meplat_r:
            notes.append(f"- ⚠ The {NR.RADOME_FOV_HALF_DEG:g}° FoV footprint (±"
                         f"{fov_half[0]:.1f} mm) is wider than the flat face "
                         f"(r {prof.meplat_r:.1f}): the outer beams cross the curved shoulder "
                         "(same λ/2 wall, oblique incidence → some extra loss / squint).\n")
        warnings += rn.warnings
        notes.append(prof.aero_md())
        notes.append(NR.window_spec_md(rn).replace(
            f"AoP top → radome inner face: {rn.gap_mm:.3f} mm (λ0/2)",
            f"AoP top → radome inner face: {gap:.3f} mm ({k}·λ0/2 — stepped up from λ0/2 "
            "so the tallest rim parts fit under the shoulder)" if k > 1 else
            f"AoP top → radome inner face: {gap:.3f} mm (λ0/2)").replace(
            f"end-wall inner face {rn.end_in_z:.3f} mm above the radar top face. The whole end "
            "wall is the window thickness so the radome needs no local step.",
            f"flat face inner surface {prof.z_top_in - z1:.3f} mm above the radar top face; "
            "the whole nose (flat face + shoulder) is the window thickness."))
        if k > 1:
            tall = max((p for p in parts if p.ref != "U_AWR"), key=lambda p: p.height)
            notes.append(f"- Flattest radar nose (λ0/2 gap) would sit "
                         f"{rn.aop.height + lam2 + wall:.2f} mm above the board; "
                         f"{tall.ref} ({tall.height:g} mm at r {_part_r(tall):.1f}) forces "
                         f"{k}·λ0/2 → {prof.z_top - z1:.2f} mm. Lower / move it inboard to "
                         "flatten the nose.\n")
        notes.append(_pipes_md(pipes))
        if wins:
            notes.append(f"- Radial USB-C window {wins[0]['w']:.1f} mm wide at "
                         f"{wins[0]['angle_deg']:.0f}°, z {wins[0]['z0']:.2f}–{wins[0]['z1']:.2f}; "
                         "plug the receptacle during the pour. ⚠ A standard USB-C plug "
                         "overmould (~12.4 × 6.5 mm) does not fit — slim plug or a pocket.\n")
        return NoseSpec(config, payload, None, (z0, z1), prof, hoods, holes, rn.dam, None,
                        {"radome_order": k, "gap_mm": round(gap, 4), "fov_r_mm": round(fov_r, 2),
                         "radome_t": radome_t, "z_in": round(z1 + rn.aop.height + gap, 4)},
                        wins, stops, notes, warnings, pipes, dam_rot_deg=rn.dam_rot_deg)

    # optical payloads: plano-convex lens, flat side flush with the meplat
    from smash.export import nose_optics as NO
    o = NO.OPTICS[payload]
    band = band or next(iter(o["bands"]))
    lam = o["bands"][band]
    lens = o["lens"]
    sensor = next((p for p in parts if p.ref == o["sensor"]), None)
    if sensor is None:
        sensor = NR.Part(o["sensor"], 0.0, 0.0, 6.0, 6.0, 1.0)
        warnings.append(f"{config}: {o['sensor']} not placed — lens centred")
    a = lens.diameter_mm / 2.0
    r_bore = a + NO.LENS_BORE_CLEAR_MM
    r_collar = r_bore + NO.LENS_COLLAR_WALL_MM
    meplat_r = max(prm["meplat_r"], math.hypot(sensor.x, sensor.y) + r_collar + 0.5)
    wall = END_WALL_MM
    z_sensor = z1 + sensor.height
    h_lens = lens.height_above_sensor_mm(lam, o["defocus_mm"])
    z_top = z_sensor + h_lens
    collar_z0 = z_top - lens.edge_mm - 0.5
    prof, bad = _fit_shoulder(r_out, wall, meplat_r, z_top, prm["shoulder_mm"], z1,
                              parts, z1, skip=(o["sensor"],))
    hoods = _hoods_for(bad, z1)
    if bad:
        warnings.append(f"{config}/{band}: lens height leaves no room for "
                        f"{', '.join(p.ref for p in bad)} under the shoulder — hoods")
    # parts under the light tube wall, or tall enough to touch the lens dome
    dome_low = z_top - lens.centre_thickness_mm
    for p in parts:
        if p.ref == o["sensor"]:
            continue
        dx = max(abs(p.x - sensor.x) - p.w / 2, 0.0)
        dy = max(abs(p.y - sensor.y) - p.h / 2, 0.0)
        near = math.hypot(dx, dy)
        far = max(math.hypot(p.x + sx * p.w / 2 - sensor.x, p.y + sy * p.h / 2 - sensor.y)
                  for sx in (-1, 1) for sy in (-1, 1))
        if far > r_bore and near < r_bore + OPTICAL_DAM_W_MM:
            warnings.append(f"{config}/{band}: {p.ref} sits under the light-tube wall")
        elif near < r_bore and z1 + p.height + PART_CLEARANCE_MM > dome_low:
            warnings.append(f"{config}/{band}: {p.ref} reaches the lens dome")
    if dome_low < z_sensor + 0.2:
        warnings.append(f"{config}/{band}: lens dome hits the sensor (f too short)")
    pipes = _ir_pipes(parts, z1)
    if OPEN_NOSE:               # lens + light tube = a separate OPTIC INSERT
        prof = _open_profile(prof, parts, z1, z_top)
        hoods, pipes = [], []
        warnings = [w for w in warnings if "hoods" not in w and "under the shoulder" not in w]
    stops = _pick_stops(parts, [(sensor.x, sensor.y, r_collar + OPTICAL_DAM_W_MM,
                                 r_collar + OPTICAL_DAM_W_MM)]
                        + [(q["x"], q["y"], q["r_out"], q["r_out"]) for q in pipes])
    notes.append(_pipes_md(pipes))
    n = NO.refractive_index(lens.material, lam)
    f = lens.focal_mm(lam)
    fov = ""
    if o.get("sensor_half_diag_mm"):
        fov = (f", full diagonal FoV {2 * math.degrees(math.atan(o['sensor_half_diag_mm'] / f)):.0f}°")
    table = "".join(f"  - {b}: λ {lm:g} nm, n {nn:.4f}, f {ff:.3f} mm, flat face "
                    f"{hh:.3f} mm above the sensor\n" for b, lm, nn, ff, hh in NO.band_table(payload))
    notes.append(prof.aero_md())
    notes.append(
        f"- Lens ({band}, λ {lam:g} nm): plano-convex {lens.material} Ø{lens.diameter_mm:g}, "
        f"R {lens.radius_mm:g}, t_c {lens.centre_thickness_mm:.2f} (edge {lens.edge_mm:g}), "
        f"n {n:.4f} → f {f:.3f} mm{fov}. Flat side OUT, flush with the flat nose face; "
        f"convex side towards {o['sensor']}; defocus {o['defocus_mm']:g} mm. Bonded into a "
        f"Ø{2 * r_bore:.2f} bore in a {NO.LENS_COLLAR_WALL_MM:g} mm collar; a "
        f"{OPTICAL_DAM_W_MM:g} mm light tube runs from the payload top to the collar (keeps "
        "the potting out of the optical path). ⚠ Lens / bands are placeholders.\n"
        f"- Height vs wavelength (same lens):\n{table}")
    tube = {"x": sensor.x, "y": sensor.y, "r_in": r_bore, "r_out": r_bore + OPTICAL_DAM_W_MM,
            "z0": z1, "z1": collar_z0, "collar_r_out": r_collar, "collar_z0": collar_z0}
    lens_d = {"x": sensor.x, "y": sensor.y, "a": a, "R": lens.radius_mm,
              "edge": lens.edge_mm, "tc": lens.centre_thickness_mm, "z_flat": z_top,
              "wavelength_nm": lam, "n": n, "f_mm": f, "material": lens.material}
    return NoseSpec(config, payload, band, (z0, z1), prof, hoods, [], None, tube, lens_d,
                    [], stops, notes, warnings, pipes)


def active_lanes(contract: dict | None, present: set, payload: str | None = None) -> dict:
    """{lane_key: [boards that get a via]} for the boards a cup holds. A lane is
    lasered only if it connects ≥ 2 present boards (GND plane / antenna feed /
    single-board exits: any present board). Unused compute castellations stay
    bare. (2026-11-19) Crown lanes are LASERED on every sleeve (one LDS pattern)
    but only get a VIA / are used where this config's payload needs the net
    (GND teeth: always)."""
    out = {}
    for key, lane in (contract or {}).get("lanes", {}).items():
        on = [b for b in lane.get("boards", []) if b in present]
        kind = lane.get("kind")
        uses = lane.get("payloads")
        needed = uses is None or (payload is not None and payload in uses)
        if kind == "crown_top":
            if on and needed:
                out[key] = on
        elif kind == "crown_payload":
            if payload and payload in lane.get("boards", []) and needed:
                out[key] = [payload]
        elif ((kind in ("gnd_plane", "antenna_feed") and on) or len(on) >= 2
              or (lane.get("aft_cap") and on)):         # runs on to the aft_end_cap
            out[key] = on
    return out
