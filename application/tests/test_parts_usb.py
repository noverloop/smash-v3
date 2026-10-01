"""UJ31-CH-3-MSMT-TR-67 full USB-C (mid-mount) factory."""
from __future__ import annotations

import pathlib

from smash import Design
from smash.parts import add_uj31_ch_3_msmt_tr_67

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_constructs_and_identity():
    c = add_uj31_ch_3_msmt_tr_67(Design(), ref="J_USB_C")
    assert c.manf == "Same Sky"
    assert c.manf_pn == "UJ31-CH-3-MSMT-TR-67"


def test_pin_pad_correspondence():
    # 24 contacts (A1-12/B1-12) + 4 shield posts (S1-4); the shield + power
    # posts use oval drills, which the pad parser must handle.
    c = add_uj31_ch_3_msmt_tr_67(Design(), ref="J")
    assert len(c.footprint.pads) == 28
    assert {p.num for p in c.pins} == {p.num for p in c.footprint.pads}


def test_carries_usb2_data_and_power():
    c = add_uj31_ch_3_msmt_tr_67(Design(), ref="J")
    names = {p.name for p in c.pins}
    assert {"DP1", "DN1", "DP2", "DN2"} <= names   # USB2 both orientations
    assert {"VBUS", "CC1", "CC2", "GND"} <= names


def test_oval_drill_posts_are_through_hole():
    c = add_uj31_ch_3_msmt_tr_67(Design(), ref="J")
    th = {p.num for p in c.footprint.pads if p.drill_mm}
    assert {"S1", "S2", "S3", "S4"} <= th          # shield posts drilled


def test_datasheet_and_3d_resolve():
    c = add_uj31_ch_3_msmt_tr_67(Design(), ref="J")
    assert c.datasheet and (REPO / c.datasheet).is_file()
    assert c.footprint.model_3d_path and (REPO / c.footprint.model_3d_path).is_file()


def test_mid_mount_note():
    c = add_uj31_ch_3_msmt_tr_67(Design(), ref="J")
    assert "mid-mount" in (c.note or "").lower()


def test_validates_clean():
    from _helpers import wire_chip_synthetically
    d = Design(apply_assumptions=False)
    chip = add_uj31_ch_3_msmt_tr_67(d, ref="J")
    wire_chip_synthetically(d, chip)
    errors = [i for i in d.validate() if i.severity == "error"]
    assert errors == [], errors
