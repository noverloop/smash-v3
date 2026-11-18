"""CLI:  python -m smash.sim.antenna CASE [--port P_S1] [--set key=value ...] [--out DIR]

CASE: M0 (λ/2 dipole check at 2 GHz) | A | B | C  (cases.py).
--set applies build_tower overrides, e.g. --set keepout_depth_mm=6 --set rings=peek
(rings: al_cut = Al with the antenna sector cut away, al, peek, none).
Runs openems_runner inside the `smash-openems` Docker image unless CSXCAD is
importable locally. Results: <out>/<case>[_<port>]/result.json + s11.png.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

from smash.sim.antenna import cases, geometry

REPO = pathlib.Path(__file__).resolve().parents[5]
IMAGE = "smash-openems"


def dipole_model(f_ghz: float = 2.0) -> dict:
    L = 0.47 * 299.792458 / f_ghz
    gap = 1.0
    arm = (L - gap) / 2
    sec = lambda n, z0, z1: {"name": n, "material": "pec", "r_in": -1.0, "r_out": 0.5,
                             "z0": z0, "z1": z1, "a0": 0.0, "a1": 0.0, "priority": 10,
                             "offset_cylinder": True}
    return {"sectors": [sec("arm_lo", -gap / 2 - arm, -gap / 2), sec("arm_hi", gap / 2, gap / 2 + arm)],
            "ports": [{"name": "P_DIP", "angle_deg": 0.0, "r": 0.0, "z": 0.0, "axis": "z", "gap_mm": gap}],
            "slots": [{"name": "DIP", "f_design_ghz": f_ghz}],
            "materials": {}, "z_extent": [-L / 2, L / 2], "notes": [f"λ/2 dipole L={L:.1f} mm"],
            "f_start_ghz": 1.2, "f_stop_ghz": 2.8, "excite": "P_DIP",
            "mesh_mm": 0.5, "nf2ff": True, "r_fine_mm": 3.0}


def _parse_sets(items):
    kw = {}
    for it in items or ():
        k, v = it.split("=", 1)
        try:
            kw[k] = json.loads(v)
        except json.JSONDecodeError:
            kw[k] = v
    for key in ("ring_setback_gaps", "keepout_slots", "ring_al_gaps"):     # "a,b" → ("a", "b")
        if isinstance(kw.get(key), str):
            kw[key] = tuple(x for x in kw[key].split(",") if x)
    if isinstance(kw.get("skin_clip_deg"), str):          # "109,255"
        kw["skin_clip_deg"] = tuple(float(x) for x in kw["skin_clip_deg"].split(","))
    if kw.get("rings") == "al_cut":
        kw["rings"] = "al"
        kw["ring_free_sector"] = cases.ANTENNA_SECTOR_FREE
    elif kw.get("rings") in ("al", "peek", "none"):
        kw["ring_free_sector"] = None
    return kw


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m smash.sim.antenna")
    ap.add_argument("case", choices=["M0", "A", "B", "C", "C2"])
    ap.add_argument("--port", default=None, help="excited port, e.g. P_S2 (default: first)")
    ap.add_argument("--set", action="append", help="build_tower override key=value")
    ap.add_argument("--out", default=str(REPO / "dist" / "sim" / "antenna"))
    ap.add_argument("--mesh", type=float, default=0.4)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--f-start", type=float, default=1.5, help="sweep start [GHz]")
    ap.add_argument("--f-stop", type=float, default=2.8, help="sweep stop [GHz]")
    ap.add_argument("--ff", default="", help="extra far-field frequencies, GHz, comma-separated")
    a = ap.parse_args(argv)

    if a.case == "M0":
        model = dipole_model()
    else:
        tm = cases.option_model(a.case, **_parse_sets(a.set))
        ff = tuple(float(x) for x in a.ff.split(",") if x.strip())
        model = geometry.model_to_dict(tm, excite=a.port, mesh_mm=a.mesh,
                                       f_start_ghz=a.f_start, f_stop_ghz=a.f_stop,
                                       ff_extra_ghz=ff)
    name = "_".join(x for x in (a.case, model["excite"], a.tag) if x)
    out = pathlib.Path(a.out) / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.json").write_text(json.dumps(model, indent=1))
    try:
        import CSXCAD  # noqa: F401
        local = True
    except ImportError:
        local = False
    runner = pathlib.Path(__file__).with_name("openems_runner.py")
    if local:
        cmd = [sys.executable, str(runner), str(out / "model.json"), str(out)]
    else:
        rel = lambda p: "/repo/" + str(pathlib.Path(p).resolve().relative_to(REPO))
        cmd = ["docker", "run", "--rm", "-v", f"{REPO}:/repo", IMAGE, "python3",
               rel(runner), rel(out / "model.json"), rel(out)]
    if a.threads:
        cmd += ["--threads", str(a.threads)]
    print(" ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True)
    print((out / "result.json").read_text()[:0] or str(out / "result.json"))


if __name__ == "__main__":
    main()
