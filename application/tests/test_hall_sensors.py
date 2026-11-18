"""DRV5032FC wake Hall switch (U_MAG_WAKE): the real SamacSys SOT-23 (DBZ)
library, part 872282, vendored 2026-11-17. It replaced TO-92 data that had
been mis-vendored as "DRV5032FCQDBZR" (not a TI orderable): a TO-92 land
pattern, a 10 mm TO-92 3D model and the TO-92 pinout, which swapped OUT and
GND on the board.

Citations: DS = drv5032.pdf (SLVSDC7) "Pin Functions", SOT-23 column;
KM = SOT95P237X112-3N.kicad_mod; KS = DRV5032FCDBZT.kicad_sym.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from smash import Design
from smash.parts import add_drv5032fcdbzt

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCES = REPO_ROOT / "application/src/smash/parts/sources/DRV5032FCDBZT"


@pytest.mark.parametrize("filename", [
    "drv5032.pdf",
    "LIB_DRV5032FCDBZT.zip",
    "DRV5032FCDBZT.kicad_sym",
    "DRV5032FCDBZT.dcm",
    "SOT95P237X112-3N.kicad_mod",
    "DRV5032FCDBZT.stp",
    "part_info.txt",
])
def test_artifact_exists(filename):
    assert (SOURCES / filename).is_file(), f"missing ground-truth artifact: {filename}"


def test_the_to92_library_is_gone():
    assert not (SOURCES.parent / "DRV5032FCQDBZR").exists()


@pytest.fixture()
def hall():
    return add_drv5032fcdbzt(Design(), ref="U1")


def test_part_number_is_a_real_ti_orderable(hall):
    assert hall.manf_pn == "DRV5032FCDBZT"
    assert "PartNumber=DRV5032FCDBZT" in (SOURCES / "part_info.txt").read_text()


def test_sot23_pinout(hall):
    """DS Pin Functions, SOT-23 column: 1=VCC, 2=OUT, 3=GND. (TO-92 is
    1=VCC, 2=GND, 3=OUT — the swap the old library carried.)"""
    got = {name: hall.pin(name).num for name in ("VCC", "OUT", "GND")}
    assert got == {"VCC": "1", "OUT": "2", "GND": "3"}


def test_sot23_land_pattern(hall):
    """KM: pads 1 and 2 on one side at 0.95 mm pitch, pad 3 centred opposite."""
    pads = {p.num: p.position_mm for p in hall.footprint.pads}
    assert set(pads) == {"1", "2", "3"}
    (x1, y1), (x2, y2), (x3, y3) = pads["1"], pads["2"], pads["3"]
    assert x1 == pytest.approx(x2)
    assert x1 < 0 < x3
    assert abs(y1 - y2) == pytest.approx(1.9)
    assert y3 == pytest.approx((y1 + y2) / 2)


def test_height_and_3d_model_are_sot23(hall):
    assert hall.footprint.height_mm == pytest.approx(1.12)
    step = (SOURCES / "DRV5032FCDBZT.stp").read_text(encoding="latin-1")
    zs = [float(z) for z in re.findall(
        r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*[-\d.Ee+]+\s*,\s*[-\d.Ee+]+\s*,\s*([-\d.Ee+]+)\s*\)",
        step)]
    assert zs and max(zs) - min(zs) < 2.0     # the TO-92 model it replaced spanned 10 mm
