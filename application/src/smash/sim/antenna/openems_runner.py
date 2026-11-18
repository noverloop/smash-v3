"""openEMS FDTD run of one sleeve-antenna model (JSON from geometry.model_to_dict).

Self-contained on purpose — imports only numpy / CSXCAD / openEMS — so it runs
unchanged inside the `smash-openems` container (docker/Dockerfile):

    python3 openems_runner.py model.json OUT_DIR [--threads N]

Model → CSXCAD: every annular sector becomes an AddRotPoly (r–z rectangle
rotated about z) or AddCylinder; PEC for conductors, lossy dielectrics via an
equivalent conductivity at the band centre. The excited port is rotated onto
the +x axis so its gap lies along a Cartesian axis (y for an axial slot, z for
an arc slot); the other ports are 50 Ω loads aligned to their NEAREST axis
(coupling numbers are approximate for slots not near 0/90/180/270° after the
rotation). Cartesian mesh, 0.4 mm inside the tower radius, graded outward;
PML_8 boundaries; NF2FF box for radiated power and the roll pattern.

Writes OUT_DIR/result.json (+ s11.png when matplotlib is present).
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys

import numpy as np

C0 = 299792458.0
EPS0 = 8.8541878128e-12


def _rot(deg, rot):
    return deg + rot


def _add_sector(props, s, rot, f0):
    from CSXCAD.CSPrimitives import CSPrimitives  # noqa: F401  (import check)
    prop = props[s["material"]]
    prio = s["priority"]
    if s.get("offset_cylinder"):
        x, y = s["a0"], s["a1"]
        a = math.radians(rot)
        xr, yr = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
        prop.AddCylinder(start=[xr, yr, s["z0"]], stop=[xr, yr, s["z1"]], radius=s["r_out"],
                         priority=prio)
        return
    full = (s["a1"] - s["a0"]) >= 360.0 - 1e-9
    if full and s["r_in"] <= 0:
        prop.AddCylinder(start=[0, 0, s["z0"]], stop=[0, 0, s["z1"]], radius=s["r_out"],
                         priority=prio)
        return
    r_in = max(s["r_in"], 0.0)
    pts = np.array([[r_in, s["r_out"], s["r_out"], r_in],
                    [s["z0"], s["z0"], s["z1"], s["z1"]]])
    if full:
        ang = [0.0, 2 * math.pi]
    else:
        # The polygon lies in the x=0 plane at +y (azimuth 90°) — shift so the
        # rotated sector covers the PHYSICAL [a0, a1] after the model rotation.
        ang = [math.radians(_rot(s["a0"], rot) - 90.0), math.radians(_rot(s["a1"], rot) - 90.0)]
    prop.AddRotPoly(points=pts, norm_dir="x", elevation=0.0, rot_axis="z", angle=ang,
                    priority=prio)


NR_TS = 300000
END_CRITERIA = 1e-3          # residual field energy, -30 dB
CONVERGED_TAIL_DB = -30.0    # port-voltage ringing left at the end of the record


def _tail_db(u) -> float:
    """Peak |u| over the last 5 % of the port-voltage record vs the overall
    peak [dB]: a run that hit the timestep cap still rings at the end."""
    u = np.abs(np.asarray(u, dtype=float))
    n = max(1, len(u) // 20)
    return float(20 * np.log10(u[-n:].max() / (u.max() + 1e-30) + 1e-30))


def _mesh_lines(lo, hi, fine_lo, fine_hi, fine, coarse, extra=()):
    from CSXCAD.SmoothMeshLines import SmoothMeshLines
    lines = list(np.arange(fine_lo, fine_hi + fine / 2, fine)) + [lo, hi] + list(extra)
    return SmoothMeshLines(np.unique(np.round(lines, 4)), coarse, 1.3)


def run(model: dict, out_dir: pathlib.Path, threads: int = 0) -> dict:
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS
    out_dir.mkdir(parents=True, exist_ok=True)
    f_lo, f_hi = model["f_start_ghz"] * 1e9, model["f_stop_ghz"] * 1e9
    f0, fc = 0.5 * (f_lo + f_hi), 0.5 * (f_hi - f_lo)
    ports = {p["name"]: p for p in model["ports"]}
    exc = ports[model["excite"]]
    rot = -exc["angle_deg"]                     # excited feed onto +x

    # 2026-11-17: the 120k / -40 dB setting hit the timestep cap on almost
    # every tower run; -30 dB with a 300k cap lets them finish.
    FDTD = openEMS(NrTS=NR_TS, EndCriteria=END_CRITERIA)
    FDTD.SetGaussExcite(f0, fc)
    FDTD.SetBoundaryCond(["PML_8"] * 6)
    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    grid = CSX.GetGrid()
    grid.SetDeltaUnit(1e-3)

    props = {"pec": CSX.AddMetal("pec")}
    for name, m in model["materials"].items():
        kappa = 2 * math.pi * f0 * EPS0 * m["eps_r"] * m["tan_d"]
        props[name] = CSX.AddMaterial(name, epsilon=m["eps_r"], kappa=kappa)
    for s in model["sectors"]:
        _add_sector(props, s, rot, f0)

    # ports
    port_objs, port_xyz = {}, []
    h = model["mesh_mm"]
    for i, (name, p) in enumerate(ports.items(), 1):
        a = math.radians(_rot(p["angle_deg"], rot))
        x, y, z, g = p["r"] * math.cos(a), p["r"] * math.sin(a), p["z"], p["gap_mm"]
        if p["axis"] == "z":
            start, stop, pdir = [x - h / 2, y - h / 2, z - g / 2], [x + h / 2, y + h / 2, z + g / 2], "z"
        else:
            tx, ty = -math.sin(a), math.cos(a)          # tangent direction
            if abs(ty) >= abs(tx):
                start, stop, pdir = [x - h / 2, y - g / 2, z - h / 2], [x + h / 2, y + g / 2, z + h / 2], "y"
            else:
                start, stop, pdir = [x - g / 2, y - h / 2, z - h / 2], [x + g / 2, y + h / 2, z + h / 2], "x"
        port_objs[name] = FDTD.AddLumpedPort(i, 50.0, start, stop, pdir,
                                             excite=1.0 if name == exc["name"] else 0.0,
                                             priority=50)
        port_xyz.append((start, stop))

    # mesh: fine inside the tower radius + ports, graded to λ/15 at f_hi outside
    lam_min = C0 / f_hi * 1e3
    margin = max(40.0, C0 / f_lo * 1e3 / 6.0)
    rf = model["r_fine_mm"]
    z0, z1 = model["z_extent"]
    ex = [c for st, sp in port_xyz for c in (st, sp)]
    grid.SetLines("x", _mesh_lines(-rf - margin, rf + margin, -rf, rf, h, lam_min / 15,
                                   [e[0] for e in ex]))
    grid.SetLines("y", _mesh_lines(-rf - margin, rf + margin, -rf, rf, h, lam_min / 15,
                                   [e[1] for e in ex]))
    grid.SetLines("z", _mesh_lines(z0 - 4 - margin, z1 + 4 + margin, z0 - 1, z1 + 1, h,
                                   lam_min / 15, [e[2] for e in ex]))
    nf2ff = FDTD.CreateNF2FFBox() if model.get("nf2ff", True) else None

    sim = out_dir / "sim"
    FDTD.Run(str(sim), cleanup=True, numThreads=threads or os.cpu_count() or 4)

    f = np.linspace(f_lo, f_hi, 261)
    pe = port_objs[exc["name"]]
    pe.CalcPort(str(sim), f)
    s11 = pe.uf_ref / pe.uf_inc
    zin = pe.uf_tot / pe.if_tot
    p_acc = 0.5 * np.real(pe.uf_tot * np.conj(pe.if_tot))
    p_inc = pe.P_inc if hasattr(pe, "P_inc") else 0.5 * np.abs(pe.uf_inc) ** 2 / 50.0
    coupling = {}
    for name, po in port_objs.items():
        if name == exc["name"]:
            continue
        po.CalcPort(str(sim), f)
        coupling[name] = (20 * np.log10(np.abs(po.uf_ref / pe.uf_inc) + 1e-30)).tolist()

    s11_db = 20 * np.log10(np.abs(s11) + 1e-30)
    i_res = int(np.argmin(s11_db))
    res = {"excite": exc["name"], "f_ghz": (f / 1e9).tolist(), "s11_db": s11_db.tolist(),
           "zin_re": np.real(zin).tolist(), "zin_im": np.imag(zin).tolist(),
           "f_res_ghz": float(f[i_res] / 1e9), "s11_min_db": float(s11_db[i_res]),
           "coupling_db": coupling, "notes": model.get("notes", [])}
    try:
        res["u_tail_db"] = _tail_db(pe.u_data.ui_val[0])
        res["converged"] = res["u_tail_db"] <= CONVERGED_TAIL_DB
    except Exception:          # older openEMS python API without u_data
        res["u_tail_db"], res["converged"] = None, None
    for thr in (-6.0, -10.0):
        ok = s11_db <= thr
        res[f"bw_{int(-thr)}db_mhz"] = float(_band_width(f, ok, i_res) / 1e6)

    if nf2ff is not None:
        fr = [f[i_res]]
        sl = next((s for s in model["slots"] if "P_" + s["name"] == exc["name"]), None)
        if sl and sl.get("f_design_ghz"):
            fr.append(sl["f_design_ghz"] * 1e9)
        for fx in model.get("ff_extra_ghz") or ():          # e.g. band edges
            if f[0] <= fx * 1e9 <= f[-1]:
                fr.append(fx * 1e9)
        theta = np.arange(0.0, 181.0, 5.0)
        phi = np.arange(0.0, 361.0, 5.0)
        zc = 0.5 * (z0 + z1)
        ff = nf2ff.CalcNF2FF(str(sim), fr, theta, phi, center=[0, 0, zc * 1e-3])
        res["far_field"] = []
        for k, fk in enumerate(fr):
            ik = int(np.argmin(np.abs(f - fk)))
            prad = float(np.real(ff.Prad[k]))
            d = ff.E_norm[k] ** 2
            d = d / d.max()
            it90 = int(np.argmin(np.abs(theta - 90)))
            roll = 10 * np.log10(d[it90, :] + 1e-30)
            res["far_field"].append({
                "f_ghz": float(fk / 1e9), "P_rad_W": prad,
                "eff_rad": prad / float(p_acc[ik]) if p_acc[ik] > 0 else None,
                "eff_tot": prad / float(np.real(p_inc[ik])) if np.real(p_inc[ik]) > 0 else None,
                "Dmax_dBi": float(10 * np.log10(np.real(ff.Dmax[k]))),
                "roll_ripple_db": float(roll.max() - roll.min()),
                "roll_pattern_db": roll.tolist(), "phi_deg": phi.tolist()})
    (out_dir / "result.json").write_text(json.dumps(res, indent=1))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.plot(f / 1e9, s11_db, label=f"S11 {exc['name']}")
        for k, v in coupling.items():
            ax.plot(f / 1e9, v, "--", label=f"{k} ← {exc['name']}")
        ax.axhline(-10, color="grey", lw=0.6)
        ax.set_xlabel("GHz"); ax.set_ylabel("dB"); ax.grid(alpha=0.3); ax.legend(fontsize=7)
        fig.tight_layout(); fig.savefig(out_dir / "s11.png", dpi=120)
    except Exception:          # plotting is optional
        pass
    return res


def _band_width(f, ok, i):
    if not ok[i]:
        return 0.0
    lo = i
    while lo > 0 and ok[lo - 1]:
        lo -= 1
    hi = i
    while hi < len(f) - 1 and ok[hi + 1]:
        hi += 1
    return f[hi] - f[lo]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    threads = 0
    if "--threads" in argv:
        k = argv.index("--threads")
        threads = int(argv[k + 1])
        del argv[k:k + 2]
    model = json.loads(pathlib.Path(argv[0]).read_text())
    res = run(model, pathlib.Path(argv[1]), threads)
    print(json.dumps({k: res.get(k) for k in ("excite", "f_res_ghz", "s11_min_db",
                                              "bw_6db_mhz", "bw_10db_mhz", "converged")}))


if __name__ == "__main__":
    main()
