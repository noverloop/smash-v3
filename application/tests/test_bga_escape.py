"""BGA escape generator: a synthetic 0.5 mm-pitch array under the fab rules."""
import math
from types import SimpleNamespace as NS

from smash.layout import bga_escape as E


def _bga(n=8, pitch=0.5, land=0.25):
    pads, pins = [], []
    off = (n - 1) * pitch / 2
    for i in range(n):
        for j in range(n):
            num = f"{chr(65 + i)}{j + 1}"
            pads.append(NS(num=num, position_mm=(j * pitch - off, off - i * pitch), size_mm=(land, land)))
            pins.append(NS(num=num, name=num))
    half = off + 0.6
    fp = NS(pads=pads, courtyard=[(-half, -half), (half, -half), (half, half), (-half, half)])
    return NS(ref="U1", footprint=fp, pins=pins)


def test_escape_meets_the_fab_rules():
    chip = _bga()
    pin_net = {}
    for k, p in enumerate(chip.pins):
        kind = "ground" if k % 9 == 4 else "power" if k % 11 == 3 else "signal"
        pin_net[("U1", p.num)] = NS(name="GND" if kind == "ground" else f"N{k}", kind=kind)
    pl = NS(position_mm=(10.0, 5.0), rotation_deg=90.0, face="top", item=chip)
    r = E.escape_bga(chip, pl, pin_net)
    assert r["unrouted"] == []
    assert all(t.width_mm >= 0.08 for t in r["tracks"])                 # nothing below 80 µm
    assert {t.layer for t in r["tracks"]} <= {"F.Cu", "In1.Cu", "In2.Cu"}
    # staggered, never stacked: no two microvias of a net share a centre
    by_pos = {}
    for v in r["vias"]:
        assert v.kind == "micro"
        key = (round(v.position_mm[0], 3), round(v.position_mm[1], 3))
        assert key not in by_pos or {by_pos[key], (v.from_layer, v.to_layer)} == {by_pos[key]}, "stacked microvia"
        by_pos[key] = (v.from_layer, v.to_layer)
    # every signal track ends outside the courtyard
    half = 3.5 * 0.5 + 0.6
    for t in r["tracks"]:
        if t.width_mm == E.W_OUT:
            x, y = t.path[-1][0] - 10.0, t.path[-1][1] - 5.0
            assert max(abs(x), abs(y)) > half - 1e-6
