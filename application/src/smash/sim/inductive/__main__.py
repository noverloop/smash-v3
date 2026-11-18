"""CLI:  python -m smash.sim.inductive [--out DIR] [--quick]

Sweeps steel wall 1–10 mm × 0.1 Hz–1 kHz for the ring-clamp ↔ tower
inductive link; writes results.json / .csv, report.md and link_sweep.png.
"""
from __future__ import annotations

import argparse
import pathlib

from smash.sim.inductive import study

REPO = pathlib.Path(__file__).resolve().parents[5]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "dist" / "sim" / "inductive"))
    ap.add_argument("--quick", action="store_true", help="3 walls × 5 frequencies")
    a = ap.parse_args(argv)
    if a.quick:
        rows = study.run(walls=(1.0, 3.0, 10.0), freqs=(0.3, 3.0, 30.0, 300.0, 1000.0), mu_sens=())
    else:
        rows = study.run()
    res = study.write(rows, a.out)
    print((res["dir"] / "report.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
