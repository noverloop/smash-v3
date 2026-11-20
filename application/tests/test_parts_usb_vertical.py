"""(2026-11-19) Same Sky UJ20-C-V-G-SMT-23B-P16-TR-X5 — vertical USB-C 2.0
receptacle on the USB nose."""
from __future__ import annotations

import pathlib

from smash import Design
from smash.parts.usb import add_uj20_c_v_g_smt_23b_p16_tr_x5

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_pins_match_copper_pads_and_posts_are_npth():
    c = add_uj20_c_v_g_smt_23b_p16_tr_x5(Design(), ref="J")
    assert c.manf == "Same Sky" and c.manf_pn == "UJ20-C-V-G-SMT-23B-P16-TR-X5"
    pads = {p.num: p for p in c.footprint.pads}
    assert len(pads) == 22
    assert {p.num for p in c.pins} == set(pads) - {"MH1", "MH2"}
    assert pads["MH1"].drill_mm and pads["MH2"].drill_mm       # locating posts
    names = {p.name for p in c.pins}
    assert {"DP1", "DN1", "DP2", "DN2", "CC1", "CC2"} <= names


def test_height_and_3d_model_resolve():
    c = add_uj20_c_v_g_smt_23b_p16_tr_x5(Design(), ref="J")
    assert c.height_mm == 6.3
    assert (REPO / c.footprint.model_3d_path).exists()


def test_usb_nose_wiring():
    import sys
    sys.path.insert(0, str(REPO))
    try:
        import generate_stackup as gen
    finally:
        sys.path.pop(0)
    d = gen.Design()
    gen._prime_power_rails(d)
    gen.build_usb_nose(d)
    usb = next(c for c in d.chips if c.ref == "J_USB_C")
    assert usb.manf_pn == "UJ20-C-V-G-SMT-23B-P16-TR-X5"
    net_of = {}
    for n in d.nets:
        for ref, pin in n.pins:
            if ref == "J_USB_C":
                net_of[pin] = n.name
    for pin in ("A4", "A9", "B4", "B9"):
        assert net_of[pin] == "USB_VBUS"
    for pin in ("A1", "A12", "B1", "B12", "MP1", "MP4"):
        assert net_of[pin] in ("GND", "FLEX_GND")         # GND is aliased to FLEX_GND
    assert net_of["A6"] == net_of["B6"] == "USB_D_P"
    assert net_of["A7"] == net_of["B7"] == "USB_D_N"
    assert "A8" not in net_of and "B8" not in net_of             # SBU open
