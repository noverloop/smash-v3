"""Tests for the project-built mechanical / connector / antenna factories."""

from __future__ import annotations

import pathlib

import pytest

from smash import Design
from smash.parts import (
    add_cellattach_3x2_tlm1520,
    add_pogo_pad,
    add_mechanical_spacer_34mm,
    add_nfc_antenna_flex_27x50,
    add_mt03_092_qpd,
)


REPO = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO / "application/src/smash/parts/sources"

ALL = [
    (add_cellattach_3x2_tlm1520, "P_CELLS"),
    (add_pogo_pad, "TP_BAT"),
    (add_mechanical_spacer_34mm, "SP1"),
    (add_nfc_antenna_flex_27x50, "L_NFC_ANT"),
    (add_mt03_092_qpd, "U_QPD"),
]


@pytest.mark.parametrize("factory,ref", ALL)
def test_constructs(factory, ref):
    d = Design()
    c = factory(d, ref=ref)
    assert c.manf == "project" or c.manf == "Marktech"
    assert c.footprint is not None


@pytest.mark.parametrize("factory,ref", ALL)
def test_unique_pins_match_unique_pads(factory, ref):
    """Pin set == set of unique pad nums. Multi-pad-same-num footprints
    (e.g. NFC vias all on AC1) collapse to one Pin per unique num."""
    d = Design()
    c = factory(d, ref=ref)
    pin_nums = {p.num for p in c.pins}
    pad_nums = {p.num for p in c.footprint.pads}
    assert pin_nums == pad_nums


def test_cellattach_pin_names():
    c = add_cellattach_3x2_tlm1520(Design(), ref="P_CELLS")
    names = {p.name for p in c.pins}
    assert names == {"CELL1+", "CELL1-", "CELL2+", "CELL2-",
                     "CELL3+", "CELL3-"}


def test_pogo_pad_single_pin():
    c = add_pogo_pad(Design(), ref="TP_BAT")
    assert len(c.pins) == 1
    assert c.pin("1").name == "TP"


def test_spacer_is_mechanical_only():
    c = add_mechanical_spacer_34mm(Design(), ref="SP1")
    assert len(c.pins) == 1
    assert c.pin("1").name == "GND_TIE"
    # Spacers are mechanical — no datasheet, no part number string we can
    # query externally
    assert c.datasheet is None


def test_nfc_antenna_collapses_via_pads():
    """The NFC kicad_mod has 4 raw Pad entries:
      pad 1 (AC0) — main SMD pad
      pad 2 (AC1) — main SMD pad
      pad 2 — F.Cu↔B.Cu via at the spiral's inner end
      pad 2 — B.Cu↔F.Cu via arriving at AC1
    All three '2' pads are on the same net, so the Pin list collapses to
    exactly two Pins (AC0 + AC1)."""
    c = add_nfc_antenna_flex_27x50(Design(), ref="L_NFC_ANT")
    # 4 raw pads → 2 unique Pins
    assert len(c.footprint.pads) == 4
    assert len(c.pins) == 2
    # AC0 single pad
    assert c.pin("1").name == "AC0"
    # AC1: 1 SMD pad + 2 via pads, all num="2"
    ac1_pads = [p for p in c.footprint.pads if p.num == "2"]
    assert len(ac1_pads) == 3
    assert c.pin("2").name == "AC1"


def test_nfc_antenna_has_inductance():
    # 4.82 µH per the round-coil spec (ST25DV16KC 28.5 pF Ctun)
    c = add_nfc_antenna_flex_27x50(Design(), ref="L_NFC_ANT")
    assert c.inductance_h == pytest.approx(4.82e-6)


def test_mt03_092_qpd_pin_names():
    # Datasheet pin map (DS p2 schematic): pin 2 = common cathode
    # (backside butt weld), pin 5 = NC, anodes Q1→4 / Q2→6 / Q3→3 / Q4→1.
    c = add_mt03_092_qpd(Design(), ref="U_QPD")
    layout = {
        "1": "ANODE_Q4", "2": "CATHODE_COM",
        "3": "ANODE_Q3", "4": "ANODE_Q1",
        "5": "NC", "6": "ANODE_Q2",
    }
    for num, name in layout.items():
        assert c.pin(num).name == name


def test_mt03_092_qpd_pad_geometry():
    # Two rows of 3 leads, 2.54 mm pitch, rows 10.16 mm apart (DS p2:
    # "2.54 REF 4 PL" / "10.16 REF 3 PL"). Pins 1/2/3 on the DS bottom
    # row, 4/5/6 on the top; the loader flips KiCad y-down to model
    # y-up, so the DS bottom row lands at y = -5.08 here.
    c = add_mt03_092_qpd(Design(), ref="U_QPD")
    at = {p.num: tuple(p.position_mm) for p in c.footprint.pads}
    assert at == {
        "1": (-2.540, -5.080), "2": (0.000, -5.080), "3": (2.540, -5.080),
        "4": (-2.540, 5.080), "5": (0.000, 5.080), "6": (2.540, 5.080),
    }


@pytest.mark.parametrize("factory,ref", ALL)
def test_validators_pass(factory, ref):
    d = Design()
    c = factory(d, ref=ref)
    for p in c.pins:
        d.add_net(f"N_{ref}_{p.num}").connect(p)
    errors = [i for i in d.validate() if i.severity == "error"]
    assert errors == [], f"{factory.__name__}: {errors}"
