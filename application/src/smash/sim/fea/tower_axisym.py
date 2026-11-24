"""Tower-level axisymmetric FEA (2026-11-23, user): how much axial
acceleration the potted tower takes, per potting material.

The tower is close to axisymmetric, so it is modelled as one radial (r, z)
cross-section revolved about the axis (CalculiX CAX4): aft cap, aft_end_board,
floor plate, battery holder + cells (homogenised), the boards with their
component mass smeared in, the rim rings (7075 / PEEK GF30) with potting
inside them, the potted board-edge gap, the PEEK-LDS sleeve (bonded to the
potting all the way up) and the potting spill over the payload tile. Every
interface is bonded (shared nodes).

Load cases (linear static, so every result scales with g):
  setback — supported on the aft cap's aft face, inertia toward the aft end;
  reverse — nose-first impact: supported on the sleeve's top (nose) end, so
            the whole stack hangs on the potting↔sleeve bond.

Criteria → the acceleration at which each is reached:
  potting tensile / compressive strength, board in-plane strain (solder-joint
  / MLCC limit), ring / plate / holder / sleeve / aft cap von Mises vs
  strength, potting↔sleeve interface shear vs adhesion.

⚠ Material data (E, density, strengths) of the potting candidates are
datasheet / estimate values — see MATERIALS; the result is a COMPARISON
between pottings and a first estimate, not a qualification.
"""
from __future__ import annotations

import dataclasses
import math
import pathlib
import subprocess

G0 = 9810.0                        # mm/s²

# name: E [MPa] (or (Er, Ez, Eθ) orthotropic), nu, rho [g/cm³], strengths
MATERIALS = {
    "fr4":      dict(E=(20000.0, 9000.0, 20000.0), nu=0.15, rho=1.85, strain_limit=750e-6),
    "al7075":   dict(E=71700.0, nu=0.33, rho=2.81, vm=500.0),
    "peek_gf30": dict(E=10000.0, nu=0.38, rho=1.51, vm=150.0),
    "peek_lds": dict(E=6000.0, nu=0.38, rho=1.60, vm=90.0),
    "holder_cells": dict(E=25000.0, nu=0.33, rho=2.40, vm=500.0),   # 7075 web + cells, homogenised
    "screwlink": dict(E=71700.0, nu=0.33, rho=2.81),   # radial screws sleeve → floor plate / holder, smeared
    # potting candidates (tension / compression strength, adhesion to PEEK)
    "cat11":    dict(E=4000.0, nu=0.34, rho=1.52, tens=48.0, comp=104.0, adh=5.0),
    "cat23lv":  dict(E=4000.0, nu=0.34, rho=1.52, tens=55.0, comp=83.0, adh=5.0),
    "ur5528":   dict(E=300.0, nu=0.45, rho=1.40, tens=14.2, comp=30.0, adh=3.0),
    "1090si":   dict(E=2500.0, nu=0.32, rho=0.72, tens=20.0, comp=60.0, adh=5.0),
}
POTTING_NOTES = {
    "cat11": "Stycast 2651MM + Cat 11 — TDS strengths (tens 48 / comp 104); E assumed 4 GPa",
    "cat23lv": "Stycast 2651MM + Cat 23LV — TDS strengths (tens 55 / comp 83); E 4 GPa (fab profile)",
    "ur5528": "Electrolube UR5528 PU — tens 14.2 (TDS); E ≈ 0.3 GPa from Shore D57 and comp 30 ASSUMED",
    "1090si": "Stycast 1090 SI syntactic — SG 0.72 (TDS); E 2.5 GPa, tens 20, comp 60 ASSUMED",
}
ADHESION_NOTE = "potting↔PEEK adhesion (lap shear) ASSUMED 3-5 MPa without surface treatment"

R_BOARD, R_GAP, R_SLEEVE, R_NECK = 17.0, 17.1, 17.9, 19.0
BOARD_T = 0.868


@dataclasses.dataclass
class Layer:
    z0: float
    z1: float
    segs: list            # [(r0, r1, material or "POT")]
    tag: str = ""


def stack_layers(board_mass_g: dict, payload: str = "radar_module",
                 cap_full: bool = False, link_mm: float = 0.0, link_z: float = 2.0,
                 lip_mm: float = 0.0,
                 link_top: bool = False, cap: str = "disc") -> tuple[list, float]:
    """The radar tower, aft → nose (tower frame: z 0 = aft face of
    aft_end_board). Returns (layers, z of the sleeve's top end)."""
    L = []
    sleeve = (R_GAP, R_SLEEVE, "peek_lds")
    edge = (R_BOARD, R_GAP, "POT")

    def board(name, z0):
        L.append(Layer(z0, z0 + BOARD_T, [(0.0, R_BOARD, f"board_{name}"), edge, sleeve], name))
        return z0 + BOARD_T

    # aft cap: cap="disc" (the design) = 7075 disc r 0-13.6 (access holes not
    # modelled), the bearing face, + PEEK-LDS crown ring; "open18" = all PEEK-LDS with a Ø18
    # opening; cap_full = all PEEK-LDS, closed
    if cap_full:
        segs_cap = [(0.0, R_SLEEVE, "peek_lds")]
    elif cap == "open18":
        segs_cap = [(9.0, R_SLEEVE, "peek_lds")]
    else:   # disc: 7075 r 0-13.6 (+ ledge to 13.9) + PEEK-LDS crown; the disc's boss
            # stands 0.2 mm proud, so the support bears on the disc only
        segs_cap = [(0.0, 13.9, "al7075"), (13.9, R_SLEEVE, "peek_lds")]
        L.append(Layer(-2.6, -2.4, [(0.0, 13.6, "al7075")], "aft_cap disc boss"))
    L.append(Layer(-2.4, 0.0, segs_cap, "aft_cap"))
    z = board("aft_end_board", 0.0)
    # link_mm > 0: radial screws sleeve → holder, smeared into a rigid ring in
    # the edge gap, link_mm tall, centred link_z above the holder's bottom face
    link = (R_BOARD, R_GAP, "screwlink")
    L.append(Layer(z, z + 1.2, [(0.0, R_BOARD, "al7075"), edge, sleeve], "floor_plate")); z += 1.2
    if link_mm:
        za, zb = z + link_z - link_mm / 2, z + link_z + link_mm / 2
        L.append(Layer(z, za, [(0.0, R_BOARD, "holder_cells"), edge, sleeve], "holder"))
        L.append(Layer(za, zb, [(0.0, R_BOARD, "holder_cells"), link, sleeve], "holder (screws)"))
        L.append(Layer(zb, z + 21.0, [(0.0, R_BOARD, "holder_cells"), edge, sleeve], "holder"))
    else:
        L.append(Layer(z, z + 21.0, [(0.0, R_BOARD, "holder_cells"), edge, sleeve], "holder"))
    z += 21.0
    L.append(Layer(z, z + 0.4, [(0.0, 16.0, "POT"), (16.0, R_BOARD, "al7075"), edge, sleeve], "headroom"))
    z += 0.4
    for name, gap, ring_mat, ring_r in (("activation_interface", 2.4, "peek_gf30", 15.0),
                                        ("wakeup_board", 2.6, "peek_gf30", 15.0),
                                        ("power_board", 3.4, "al7075", 16.0),
                                        ("companion_compute", 3.0, "al7075", 16.0)):
        z = board(name, z)
        # link_top: radial screws through the sleeve into the 7075 ring under the payload
        e2 = link if (link_top and name == "companion_compute") else edge
        L.append(Layer(z, z + gap, [(0.0, ring_r, "POT"), (ring_r, R_BOARD, ring_mat), e2, sleeve],
                       f"gap above {name}"))
        z += gap
    z = board(payload, z)
    z_top = z + 2.75                                       # sleeve neck top
    if lip_mm:
        # sleeve LIP: an inner ring of the sleeve, lip_mm wide, lip_h tall,
        # seated on the payload board's top face (bonded = bearing)
        lip_h = 1.0
        r_l = R_GAP - lip_mm
        L.append(Layer(z, z + 0.5, [(0.0, r_l, "POT"), (r_l, R_NECK, "peek_lds")], "potting spill"))
        L.append(Layer(z + 0.5, z + lip_h, [(r_l, R_NECK, "peek_lds")], "sleeve lip"))
        L.append(Layer(z + lip_h, z_top, [(R_GAP, R_NECK, "peek_lds")], "sleeve neck"))
    else:
        L.append(Layer(z, z + 0.5, [(0.0, R_GAP, "POT"), (R_GAP, R_NECK, "peek_lds")], "potting spill"))
        L.append(Layer(z + 0.5, z_top, [(R_GAP, R_NECK, "peek_lds")], "sleeve neck"))
    return L, z_top


def board_masses_g() -> dict:
    """Component mass per board (weight_g where known, else body volume ×
    2.0 g/cm³) — smeared into the board's density."""
    import sys
    repo = pathlib.Path(__file__).resolve().parents[5]
    sys.path.insert(0, str(repo))
    import generate_stackup as G
    d = G.Design()
    G._prime_power_rails(d)
    for fn in G._BOARD_BUILDERS.values():
        fn(d)
    out: dict = {}
    for c in d.chips:
        w = getattr(c, "weight_g", None)
        if not w:
            sx, sy = (c.size_mm or (1.0, 0.5))
            w = sx * sy * (c.height_mm or 0.5) * 2.0e-3
        out[c.board_tag] = out.get(c.board_tag, 0.0) + float(w)
    return out


def _grid(breaks: list, h: float) -> list:
    out = []
    for a, b in zip(breaks[:-1], breaks[1:]):
        n = max(1, math.ceil((b - a) / h - 1e-9))
        out += [a + (b - a) * k / n for k in range(n)]
    return out + [breaks[-1]]


def build_mesh(layers: list, dr: float = 0.25, dz: float = 0.2):
    rb = sorted({round(v, 4) for L in layers for s in L.segs for v in s[:2]} | {0.0})
    zb = sorted({round(v, 4) for L in layers for v in (L.z0, L.z1)})
    rs, zs = _grid(rb, dr), _grid(zb, dz)
    elems = []                                   # (i, j, material, layer tag)
    for j in range(len(zs) - 1):
        zc = (zs[j] + zs[j + 1]) / 2
        lay = next((L for L in layers if L.z0 <= zc < L.z1), None)
        if lay is None:
            continue
        for i in range(len(rs) - 1):
            rc = (rs[i] + rs[i + 1]) / 2
            m = next((s[2] for s in lay.segs if s[0] <= rc < s[1]), None)
            if m:
                elems.append((i, j, m, lay.tag))
    return rs, zs, elems


def write_deck(path: pathlib.Path, rs, zs, elems, potting: str, board_mass: dict,
               case: str, g: float = 1000.0, nose_face_z: float | None = None) -> dict:
    nid = {}
    lines = ["*NODE"]
    used = set()
    for i, j, *_ in elems:
        used |= {(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)}
    for k, (i, j) in enumerate(sorted(used), 1):
        nid[(i, j)] = k
        lines.append(f"{k}, {rs[i]:.5f}, {zs[j]:.5f}")
    mats, eset = {}, {}
    einfo = {}
    lines_e = []
    for k, (i, j, m, tag) in enumerate(elems, 1):
        mname = potting if m == "POT" else m
        eset.setdefault(mname, []).append(k)
        einfo[k] = (mname, tag, (rs[i] + rs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2, zs[j + 1] - zs[j])
        lines_e.append((mname, f"{k}, {nid[(i, j)]}, {nid[(i + 1, j)]}, {nid[(i + 1, j + 1)]}, "
                               f"{nid[(i, j + 1)]}"))
    for mname, ids in eset.items():
        lines.append(f"*ELEMENT, TYPE=CAX4, ELSET=E_{mname}")
        lines += [l for mn, l in lines_e if mn == mname]
    lines.append("*ELSET, ELSET=EALL")
    lines += [f"E_{m}" for m in eset]
    for mname in eset:
        if mname.startswith("board_"):
            b = mname[6:]
            base = MATERIALS["fr4"]
            vol_cm3 = math.pi * R_BOARD ** 2 * BOARD_T / 1000.0
            rho = base["rho"] + board_mass.get(b, 0.0) / vol_cm3
            p = dict(base, rho=rho)
        else:
            p = MATERIALS[mname]
        lines.append(f"*MATERIAL, NAME=M_{mname}")
        if isinstance(p["E"], tuple):
            er, ez, et = p["E"]
            nu = p["nu"]
            grz = ez / (2 * (1 + 0.3))
            lines.append("*ELASTIC, TYPE=ENGINEERING CONSTANTS")
            lines.append(f"{er}, {ez}, {et}, {nu}, {nu}, {nu}, {grz}, {er / (2 * (1 + nu))},")
            lines.append(f"{grz}")
        else:
            lines.append("*ELASTIC")
            lines.append(f"{p['E']}, {p['nu']}")
        lines.append("*DENSITY")
        lines.append(f"{p['rho'] * 1e-9:.4e}")
        lines.append(f"*SOLID SECTION, ELSET=E_{mname}, MATERIAL=M_{mname}")
        mats[mname] = p
    axis = [n for (i, j), n in nid.items() if i == 0]
    if case == "setback":                       # aft cap's aft face on the support
        j0 = zs.index(min(zs))
        sup = [n for (i, j), n in nid.items() if j == j0]
        gdir = (0.0, -1.0)
    else:                                       # reverse: hung on the sleeve's top end
        jt = len(zs) - 1
        sup = [n for (i, j), n in nid.items() if j == jt]
        if nose_face_z is not None:             # + the nose cap bearing on the whole nose face
            jf = min(range(len(zs)), key=lambda k: abs(zs[k] - nose_face_z))
            sup += [n for (i, j), n in nid.items() if j == jf and rs[i] <= R_GAP + 1e-6]
        gdir = (0.0, 1.0)
    lines.append("*NSET, NSET=NAXIS")
    lines += [f"{n}," for n in axis]
    lines.append("*NSET, NSET=NSUP")
    lines += [f"{n}," for n in sup]
    lines += ["*BOUNDARY", "NAXIS, 1, 1", "NSUP, 2, 2",
              "*STEP", "*STATIC", "*DLOAD", f"EALL, GRAV, {g * G0:.1f}, {gdir[0]}, {gdir[1]}, 0.",
              "*EL PRINT, ELSET=EALL", "S, E", "*END STEP"]
    path.write_text("\n".join(lines) + "\n")
    return {"einfo": einfo, "mats": mats}


def _parse_dat(dat: pathlib.Path) -> tuple[dict, dict]:
    """{elem: [(sxx, syy, szz, sxy), …]} for stresses and strains (per
    integration point). CAX: x = r, y = z, z = θ."""
    S, E, cur = {}, {}, None
    for line in dat.read_text().splitlines():
        low = line.strip().lower()
        if low.startswith("stresses"):
            cur = S
            continue
        if low.startswith("strains"):
            cur = E
            continue
        if cur is None:
            continue
        parts = line.split()
        if len(parts) >= 8:
            try:
                e = int(parts[0])
                v = tuple(float(x) for x in parts[2:8])
            except ValueError:
                continue
            cur.setdefault(e, []).append(v)
    return S, E


def _principal_rz(sr, sz, st, trz):
    c = (sr + sz) / 2
    rad = math.hypot((sr - sz) / 2, trz)
    return max(c + rad, c - rad, st), min(c + rad, c - rad, st)


def _von_mises(sr, sz, st, trz):
    return math.sqrt(0.5 * ((sr - sz) ** 2 + (sz - st) ** 2 + (st - sr) ** 2) + 3 * trz ** 2)


REG_MM = 0.5     # critical distance: criteria averaged over ±REG_MM/2 in r and z


def evaluate_reg(S: dict, E: dict, einfo: dict, mats: dict, potting: str, g: float,
                 reg_mm: float = REG_MM) -> list:
    """Like evaluate(), but each criterion is the element value averaged over a
    reg_mm × reg_mm neighbourhood in the SAME material (critical-distance
    regularisation): bonded sharp corners (cap-opening edge, film ends) are
    stress singularities whose point peak grows without bound with mesh
    refinement; the averaged value converges."""
    import numpy as np
    vals: dict = {}                      # criterion → [(rc, zc, mname, tag, value)]

    def add(key, rc, zc, m, tag, v):
        vals.setdefault(key, []).append((rc, zc, m, tag, v))
    pm = MATERIALS[potting]
    limits = {}
    for e, pts in S.items():
        mname, tag, rc, zc, dz = einfo[e]
        n = len(pts)
        sr, sz, st, trz = (sum(p[k] for p in pts) / n for k in range(4))
        if mname == potting:
            s1, s3 = _principal_rz(sr, sz, st, trz)
            add("potting tension", rc, zc, mname, tag, s1); limits["potting tension"] = pm["tens"]
            add("potting compression", rc, zc, mname, tag, -s3); limits["potting compression"] = pm["comp"]
            if R_BOARD <= rc <= R_GAP + 1e-6:
                add("potting↔sleeve shear", rc, zc, mname, tag, abs(trz))
                limits["potting↔sleeve shear"] = pm["adh"]
        elif not mname.startswith("board_"):
            lim = mats.get(mname, {}).get("vm")
            if lim:
                k = f"{mname} von Mises"
                add(k, rc, zc, mname, tag, _von_mises(sr, sz, st, trz)); limits[k] = lim
    k = "board in-plane strain (solder joints / MLCC)"
    for e, pts in E.items():
        mname, tag, rc, zc, dz = einfo[e]
        if mname.startswith("board_"):
            n = len(pts)
            er, et = sum(p[0] for p in pts) / n, sum(p[2] for p in pts) / n
            add(k, rc, zc, mname, tag, max(abs(er), abs(et))); limits[k] = MATERIALS["fr4"]["strain_limit"]
    out = []
    h = reg_mm / 2
    for key, rows in vals.items():
        r = np.array([x[0] for x in rows]); z = np.array([x[1] for x in rows])
        v = np.array([x[4] for x in rows]); m = np.array([x[2] for x in rows])
        best, where = -1.0, ""
        order = np.argsort(-v)
        for i in order[:200]:                      # candidates: the top raw values
            sel = (np.abs(r - r[i]) <= h) & (np.abs(z - z[i]) <= h) & (m == m[i])
            a = float(v[sel].mean())
            if a > best:
                best, where = a, rows[i][3]
        if best > 0:
            out.append((key, best, limits[key], g * limits[key] / best, where))
    return sorted(out, key=lambda t: t[3])


def evaluate(S: dict, E: dict, einfo: dict, mats: dict, potting: str, g: float) -> list:
    """[(criterion, value at g, limit, g_limit, where)] sorted by g_limit."""
    worst: dict = {}

    def keep(key, val, limit, where):
        if val <= 0:
            return
        gl = g * limit / val
        if key not in worst or gl < worst[key][3]:
            worst[key] = (key, val, limit, gl, where)

    pm = MATERIALS[potting]
    link_force = 0.0
    for e, pts in S.items():
        mname, tag, rc, zc, dz = einfo[e]
        if mname == "screwlink":                  # axial force carried by the screws
            if abs(rc - (R_BOARD + R_GAP) / 2) < 1e-3:
                link_force += abs(sum(p[3] for p in pts) / len(pts)) * 2 * math.pi * rc * dz
            continue
        for (sr, sz, st, trz, _a, _b) in pts:
            if mname == potting:
                s1, s3 = _principal_rz(sr, sz, st, trz)
                keep("potting tension", s1, pm["tens"], tag)
                keep("potting compression", -s3, pm["comp"], tag)
                if R_BOARD <= rc <= R_GAP + 1e-6:
                    keep("potting↔sleeve shear", abs(trz), pm["adh"], tag)
            elif not mname.startswith("board_"):
                lim = mats[mname].get("vm")
                if lim:
                    keep(f"{mname} von Mises", _von_mises(sr, sz, st, trz), lim, tag)
    for e, pts in E.items():
        mname, tag, rc, zc, dz = einfo[e]
        if mname.startswith("board_"):
            for (er, ez, et, *_r) in pts:
                keep("board in-plane strain (solder joints / MLCC)", max(abs(er), abs(et)),
                     MATERIALS["fr4"]["strain_limit"], tag)
    out = sorted(worst.values(), key=lambda t: t[3])
    if link_force:
        out.append(("screw link force [N]", link_force, 0.0, float("inf"), f"at {g:g} g"))
    return out


def run(potting: str, case: str, workdir: pathlib.Path, board_mass: dict,
        g: float = 1000.0, ccx: str = "ccx_2.23", cap_full: bool = False,
        nose_full: bool = False, link_mm: float = 0.0, link_top: bool = False,
        lip_mm: float = 0.0, reg_mm: float = REG_MM, mesh: float | None = None,
        layers_hook=None, cap: str = "disc") -> list:
    layers, _zt = stack_layers(board_mass, cap_full=cap_full, link_mm=link_mm, link_top=link_top,
                               lip_mm=lip_mm, cap=cap)
    if layers_hook:
        layers_hook(layers)
    spill = next(L for L in layers if L.tag == "potting spill")
    rs, zs, elems = build_mesh(layers, dr=mesh or 0.1, dz=mesh or 0.1)
    workdir.mkdir(parents=True, exist_ok=True)
    job = f"tower_{potting}_{case}"
    meta = write_deck(workdir / f"{job}.inp", rs, zs, elems, potting, board_mass, case, g,
                      nose_face_z=spill.z1 if nose_full else None)
    subprocess.run([ccx, job], cwd=workdir, check=True, capture_output=True)
    S, E = _parse_dat(workdir / f"{job}.dat")
    if reg_mm:
        return evaluate_reg(S, E, meta["einfo"], meta["mats"], potting, g, reg_mm)
    return evaluate(S, E, meta["einfo"], meta["mats"], potting, g)
