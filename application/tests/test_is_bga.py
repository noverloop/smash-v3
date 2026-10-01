"""Tests for Chip.is_bga and Footprint.is_bga — pure-computed @property."""
from __future__ import annotations

from smash.state import Chip, Design, Footprint, Pad, Pin

from smash.parts.mcus     import add_stm32mp255fak3, add_stm32h562aii6
from smash.parts.flash    import add_as4c512m16d3lc_12bin
from smash.parts.sensors  import add_h3lis331dltr, add_iis2mdctr
from smash.parts.passives import add_resistor_0402_vishay
from smash.parts.mosfets  import add_bss138lt1g
from smash.parts.cameras  import add_ar0234cssm00suka0_cp


# ── Footprint.is_bga ────────────────────────────────────────────────────

def _fp(package_class):
    return Footprint(name="X", package_class=package_class)


def test_footprint_is_bga_true_for_plain_bga():
    assert _fp("BGA").is_bga


def test_footprint_is_bga_true_for_vfbga_variants():
    assert _fp("VFBGA-96").is_bga
    assert _fp("VFBGA-424 (13×13 mm)").is_bga
    assert _fp("VFBGA-63 (ONFI standard)").is_bga


def test_footprint_is_bga_true_for_dsbga():
    assert _fp("DSBGA").is_bga
    assert _fp("DSBGA-4").is_bga


def test_footprint_is_bga_true_for_odcsp_bga_marker():
    assert _fp("ODCSP-83 BGA").is_bga


def test_footprint_is_bga_false_for_lfcsp():
    """LFCSP is a Lead-Frame Chip Scale Package — a QFN-class
    leaded part, NOT a ball array. Don't blanket-match 'CSP'."""
    assert not _fp("LFCSP-32").is_bga


def test_footprint_is_bga_false_for_chips():
    assert not _fp("0402").is_bga
    assert not _fp("SOIC-8").is_bga
    assert not _fp("SOT-23").is_bga
    assert not _fp("VFQFPN-56").is_bga
    assert not _fp("TSSOP-16").is_bga
    assert not _fp("LGA-module").is_bga


def test_footprint_is_bga_false_for_none_package_class():
    assert not Footprint(name="X").is_bga


# ── Chip.is_bga ─────────────────────────────────────────────────────────

def test_chip_is_bga_uses_chip_level_package():
    d = Design()
    mpu = add_stm32mp255fak3(d, ref="U_MPU_TEST")
    assert mpu.is_bga is True


def test_chip_is_bga_h562_bga():
    d = Design()
    mcu = add_stm32h562aii6(d, ref="U_H562_TEST")
    assert mcu.is_bga is True


def test_chip_is_bga_ddr3_bga():
    d = Design()
    ddr = add_as4c512m16d3lc_12bin(d, ref="U_DDR3_TEST")
    assert ddr.is_bga is True


def test_chip_is_bga_camera_odcsp_bga():
    d = Design()
    cam = add_ar0234cssm00suka0_cp(d, ref="U_CAM_TEST")
    assert cam.is_bga is True


def test_chip_is_bga_false_for_lga():
    """H3LIS331DL is LGA-16, not BGA."""
    d = Design()
    acc = add_h3lis331dltr(d, ref="U_HACC_TEST")
    assert acc.is_bga is False


def test_chip_is_bga_false_for_iis2mdc_lga():
    d = Design()
    mag = add_iis2mdctr(d, ref="U_MAG_TEST")
    assert mag.is_bga is False


def test_chip_is_bga_false_for_resistor():
    d = Design()
    r = add_resistor_0402_vishay(d, ref="R_TEST", value="10k")
    assert r.is_bga is False


def test_chip_is_bga_false_for_sot23_mosfet():
    d = Design()
    q = add_bss138lt1g(d, ref="Q_TEST")
    assert q.is_bga is False


def test_chip_is_bga_no_state():
    """is_bga is a computed @property — never gets stored on the dataclass.
    Use a footprint-free chip so only the `package` string drives the result."""
    chip = Chip(ref="U_X", package="VFBGA-424")
    assert chip.is_bga
    chip.package = "SOIC-8"
    assert not chip.is_bga
    chip.package = "DSBGA"
    assert chip.is_bga


def test_chip_is_bga_falls_back_to_footprint():
    """If chip.package is empty but footprint.package_class says BGA,
    chip.is_bga still returns True — footprint is the authoritative
    geometry source."""
    fp = Footprint(name="BGA96", package_class="VFBGA-96",
                   pads=[Pad(num="A1", position_mm=(0, 0),
                             size_mm=(0.4, 0.4))])
    chip = Chip(ref="U_X", package=None, footprint=fp,
                pins=[Pin(num="A1")])
    assert chip.is_bga
