"""(2026-11-20) Every vendor 3D model the design uses must SIT ON its board
after the footprint's model transform — not hang through it. Caught: the
WE-PD 744043100 inductor model was built upside down (z −2.8…0), and the
legacy SamacSys `(module …)` files give the model offset in INCHES while we
emitted it as mm (the BLM18 bead sank into the board)."""
from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
# mid-mount parts sit THROUGH a board cut-out by design; the vertical USB-C
# has locating pegs that pass through the board (1.7 mm below)
MID_MOUNT = ("UJ20-C-H-G-MSMT", "UJ31-CH-3-MSMT", "UJ20-C-V-G-SMT")


def _kicad_xform(shape, offset, rotate):
    """KiCad's STEP exporter: rotate about X, Y, Z by −angle (in that order),
    then translate by the offset (mm)."""
    rx, ry, rz = rotate
    s = shape.rotate((0, 0, 0), (1, 0, 0), -rx)
    s = s.rotate((0, 0, 0), (0, 1, 0), -ry)
    s = s.rotate((0, 0, 0), (0, 0, 1), -rz)
    return s.translate(offset)


def test_models_sit_on_the_board():
    cq = pytest.importorskip("cadquery")
    sys.path.insert(0, str(REPO))
    try:
        gen = importlib.import_module("generate_stackup")
    finally:
        sys.path.pop(0)
    from smash.export.kicad_pcb import _parse_kicad_mod_model_xform, resolve_repo_path
    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in gen._BOARD_BUILDERS.values():
        fn(d)
    seen, bad = set(), []
    for c in d.chips:
        fp = getattr(c, "footprint", None)
        mp = getattr(fp, "model_3d_path", None) if fp else None
        if not mp or mp in seen or mp.startswith("${") or any(k in mp for k in MID_MOUNT):
            continue
        seen.add(mp)
        path = resolve_repo_path(mp)
        if not path.exists():
            continue
        if fp.model_offset_mm is not None or fp.model_rotate_deg is not None:
            xf = (tuple(fp.model_offset_mm or (0, 0, 0)), tuple(fp.model_rotate_deg or (0, 0, 0)))
        else:
            xf = next((x for x in (_parse_kicad_mod_model_xform(m)
                                   for m in path.parent.glob("*.kicad_mod")) if x),
                      ((0, 0, 0), (0, 0, 0)))
        try:
            body = cq.importers.importStep(str(path)).val()
        except Exception:
            continue
        bb = _kicad_xform(body, *xf).BoundingBox()
        if bb.zmin < -0.3 or bb.zmax <= 0.05:
            bad.append(f"{c.ref} {path.name}: z[{bb.zmin:.2f}, {bb.zmax:.2f}] (offset {xf[0]}, rotate {xf[1]})")
    assert not bad, "\n".join(bad)
