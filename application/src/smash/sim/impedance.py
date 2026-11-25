"""Controlled-impedance trace widths for the standard tile stack-up.

Closed-form models (good to a few %, the fab tunes the final widths against
its own field solver — quote these as targets + starting widths):

  * microstrip (outer layer over its build-up prepreg): Hammerstad-Jensen
    with the Wheeler thickness correction; solder mask ignored (it lowers
    Z by ≈ 1-3 Ω, inside the ±10 % fab tolerance);
  * stripline (inner layer between two planes, possibly offset): IPC-2141A
    offset-stripline formula;
  * edge-coupled differential pairs: IPC-2141A coupling factors
    (microstrip 1 − 0.48·e^(−0.96 s/h), stripline 1 − 0.347·e^(−2.9 s/b)).

The stack-up is `fit.STACK_PRESETS["hdi8_speedstack"]` (8L 2+4+2,
0.868 mm). Layer plan used here (LAYOUT_EE_NOTES "Layer plan"):

    L1 F.Cu  signal / RF (microstrip over L2)      36 µm
       85.2 µm 1080 RC71 %  εr 3.92
    L2 In1   GND                                    18 µm
       85.2 µm 1080 RC71 %  εr 3.92
    L3 In2   signal (stripline, L2 / L4)            18 µm
       127 µm core 2×106     εr 3.83
    L4 In3   GND                                    18 µm
       73.2 µm 1080 RC66 %  εr 4.04
    L5 In4   power                                  18 µm
       127 µm core 2×106     εr 3.83
    L6 In5   signal (stripline, L5 / L7)            18 µm
       85.2 µm 1080 RC71 %  εr 3.92
    L7 In6   GND                                    18 µm
       85.2 µm 1080 RC71 %  εr 3.92
    L8 B.Cu  signal (microstrip over L7)            36 µm
"""
from __future__ import annotations

import math

UM = 1e-3   # µm → mm

# (signal layer, references, h above / below in mm, εr, copper t in mm)
LAYERS = {
    "F.Cu":   {"kind": "microstrip", "h": 85.2 * UM, "er": 3.92, "t": 36 * UM, "ref": "In1.Cu (GND)"},
    "In2.Cu": {"kind": "stripline", "h1": 85.2 * UM, "h2": 127.0 * UM, "er": (3.92 * 85.2 + 3.83 * 127.0) / 212.2,
               "t": 18 * UM, "ref": "In1.Cu (GND) / In3.Cu (GND)"},
    "In5.Cu": {"kind": "stripline", "h1": 127.0 * UM, "h2": 85.2 * UM, "er": (3.83 * 127.0 + 3.92 * 85.2) / 212.2,
               "t": 18 * UM, "ref": "In4.Cu (PWR) / In6.Cu (GND)"},
    "B.Cu":   {"kind": "microstrip", "h": 85.2 * UM, "er": 3.92, "t": 36 * UM, "ref": "In6.Cu (GND)"},
}


def microstrip_z0(w: float, h: float, er: float, t: float) -> float:
    """Hammerstad-Jensen microstrip impedance (Ω), widths in mm."""
    if t > 0:
        dw = t / math.pi * (1 + math.log(4 * math.e / math.sqrt((t / h) ** 2 + (1 / math.pi / (w / t + 1.1)) ** 2)))
        w = w + dw * (1 + 1 / er) / 2
    u = w / h
    a = 1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + math.log(1 + (u / 18.1) ** 3) / 18.7
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    e_eff = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)
    f = 6 + (2 * math.pi - 6) * math.exp(-((30.666 / u) ** 0.7528))
    z_air = 60 * math.log(f / u + math.sqrt(1 + (2 / u) ** 2))
    return z_air / math.sqrt(e_eff)


def stripline_z0(w: float, h1: float, h2: float, er: float, t: float) -> float:
    """IPC-2141A offset stripline (Ω): h1 = gap to the nearer plane."""
    a, b = min(h1, h2), max(h1, h2)
    z_sym = lambda hh: 60 / math.sqrt(er) * math.log(4 * (2 * hh + t) / (0.67 * math.pi * (0.8 * w + t)))
    # offset stripline ≈ parallel combination of the two symmetric striplines
    za, zb = z_sym(a), z_sym(b)
    return 2 * za * zb / (za + zb)


def z0(layer: str, w: float) -> float:
    L = LAYERS[layer]
    if L["kind"] == "microstrip":
        return microstrip_z0(w, L["h"], L["er"], L["t"])
    return stripline_z0(w, L["h1"], L["h2"], L["er"], L["t"])


def zdiff(layer: str, w: float, s: float) -> float:
    L = LAYERS[layer]
    if L["kind"] == "microstrip":
        return 2 * z0(layer, w) * (1 - 0.48 * math.exp(-0.96 * s / L["h"]))
    b = L["h1"] + L["h2"] + L["t"]
    return 2 * z0(layer, w) * (1 - 0.347 * math.exp(-2.9 * s / b))


def _solve(f, target: float, lo: float = 0.03, hi: float = 1.5) -> float:
    """Width (mm) where f(w) = target; f falls with w."""
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) > target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def width_for(layer: str, ohms: float) -> float:
    return _solve(lambda w: z0(layer, w), ohms)


def diff_width_for(layer: str, ohms: float, s: float) -> float:
    return _solve(lambda w: zdiff(layer, w, s), ohms)


def table() -> dict:
    """{layer: {"50": w, "55": w, "diff100": (w, s), "diff90": (w, s)}} in mm.
    Diff gap fixed at the 0.10 mm minimum on inner layers and 0.12 mm outer
    (loosely coupled enough to keep the pair tolerant of etch)."""
    out = {}
    for layer, L in LAYERS.items():
        s = 0.12 if L["kind"] == "microstrip" else 0.10
        out[layer] = {
            "ref": L["ref"],
            "50": width_for(layer, 50.0),
            "55": width_for(layer, 55.0),
            "diff100": (diff_width_for(layer, 100.0, s), s),
            "diff90": (diff_width_for(layer, 90.0, s), s),
        }
    return out


if __name__ == "__main__":
    for layer, r in table().items():
        print(f"{layer:7s} ref {r['ref']:28s} 50Ω {r['50']:.3f}  55Ω {r['55']:.3f}  "
              f"100Ω diff {r['diff100'][0]:.3f}/{r['diff100'][1]:.2f}  90Ω diff {r['diff90'][0]:.3f}/{r['diff90'][1]:.2f}")
