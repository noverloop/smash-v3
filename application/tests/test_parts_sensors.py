"""Verify sensor factories transcribe their ground-truth.

Covers:
  - TMP117MAIDRVR  (TI precision temp sensor, WSON-6)
  - IIS2MDCTR      (ST 3-axis magnetometer, LGA-12)
  - ISM330DHCXTR   (ST 6-axis IMU, LGA-14)
  - H3LIS331DLTR   (ST 3-axis high-G accel, LGA-16)
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design
from smash.parts import (
    add_tmp117maidrvr, add_iis2mdctr,
    add_ism330dhcxtr, add_h3lis331dltr,
)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "application/src/smash/parts/sources"


# ─── artifact presence per part ──────────────────────────────────────────

ARTIFACTS = {
    "TMP117MAIDRVR": [
        "TMP117MAIDRVR.pdf", "LIB_TMP117MAIDRVR.samacsys.zip",
        "TMP117MAIDRVR.kicad_sym", "SON65P200X200X80-7N.kicad_mod",
        "TMP117MAIDRVR.stp", "pinmap.txt", "part_info.txt",
    ],
    "IIS2MDCTR": [
        "IIS2MDCTR.pdf", "LIB_IIS2MDCTR.samacsys.zip",
        "IIS2MDCTR.kicad_sym", "IIS2MDCTR.kicad_mod",
        "IIS2MDCTR.stp", "pinmap.txt", "part_info.txt",
    ],
    "ISM330DHCXTR": [
        "ISM330DHCXTR.pdf", "LIB_ISM330DHCXTR.samacsys.zip",
        "ISM330DHCXTR.kicad_sym", "LSM6DS3USTR.kicad_mod",
        "ISM330DHCXTR.stp", "pinmap.txt", "part_info.txt",
    ],
    "H3LIS331DLTR": [
        "H3LIS331DLTR.pdf", "LIB_H3LIS331DLTR.samacsys.zip",
        "H3LIS331DLTR.kicad_sym", "LIS3DHTR.kicad_mod",
        "H3LIS331DLTR.stp", "pinmap.txt", "part_info.txt",
    ],
}


@pytest.mark.parametrize(
    "part,fname",
    [(p, f) for p, files in ARTIFACTS.items() for f in files],
)
def test_artifact_present(part, fname):
    assert (SRC / part / fname).is_file()


# ─── TMP117MAIDRVR ───────────────────────────────────────────────────────

class TestTMP117:
    def setup_method(self):
        self.q = add_tmp117maidrvr(Design(), ref="U1")

    def test_identity(self):
        assert self.q.manf == "Texas Instruments"
        assert self.q.manf_pn == "TMP117MAIDRVR"

    def test_supply(self):
        # Datasheet §6.1: V+ abs max 6 V
        assert self.q.voltage_rating_v == 6.0

    def test_temp_range_ta(self):
        # §6.3: T_A -55 to +150 °C
        assert self.q.temp_range_c == (-55, 150)
        assert self.q.tj_max_c == 155.0     # T_J max from §6.1

    def test_pin_layout(self):
        layout = {
            "1": "SCL", "2": "GND", "3": "ALERT",
            "4": "ADD0", "5": "V+", "6": "SDA", "7": "EP",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_alert_is_open_drain_note(self):
        a = self.q.pin("ALERT")
        assert a.type == "output"
        assert "open-drain" in (a.note or "").lower()

    def test_ep_is_ground(self):
        assert self.q.pin("EP").type == "ground"

    def test_footprint(self):
        fp = self.q.footprint
        assert fp.name == "SON65P200X200X80-7N"
        assert fp.package_class == "WSON-6"
        assert len(fp.pads) == 7
        assert fp.height_mm == pytest.approx(0.8)

    def test_esd_standards(self):
        s = self.q.standards
        assert any("HBM" in x and "2000" in x for x in s)
        assert any("CDM" in x and "1000" in x for x in s)


# ─── IIS2MDCTR ───────────────────────────────────────────────────────────

class TestIIS2MDC:
    def setup_method(self):
        self.q = add_iis2mdctr(Design(), ref="U2")

    def test_identity(self):
        assert self.q.manf == "STMicroelectronics"
        assert self.q.manf_pn == "IIS2MDCTR"

    def test_supply(self):
        # DS p14: Vdd/Vdd_IO abs max 4.8 V
        assert self.q.voltage_rating_v == 4.8

    def test_temp_range(self):
        # DS p14: T_OP -40 to +85 °C
        assert self.q.temp_range_c == (-40, 85)

    def test_12_pins(self):
        assert len(self.q.pins) == 12

    def test_pin_layout(self):
        layout = {
            "1": "SCL_SPC", "2": "NC_1", "3": "CS",
            "4": "SDA_SDI_SDO", "5": "C1", "6": "GND_1",
            "7": "INT_DRDY", "8": "GND_2", "9": "VDD",
            "10": "VDD_IO", "11": "NC_2", "12": "NC_3",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_aliases(self):
        # Caller ergonomics
        assert self.q.pin("SCL").num == "1"
        assert self.q.pin("SDA").num == "4"

    def test_c1_pin_note(self):
        c1 = self.q.pin("5")
        assert c1.name == "C1"
        assert "capacitor" in (c1.note or "").lower()

    def test_footprint(self):
        fp = self.q.footprint
        assert fp.name == "IIS2MDCTR"
        assert fp.package_class == "LGA-12"
        assert len(fp.pads) == 12

    @pytest.mark.parametrize("substring", [
        "±50 gauss", "10000 gauss", "4.8 V",
        "I²C", "SPI", "Vdd_IO",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


# ─── ISM330DHCXTR ────────────────────────────────────────────────────────

class TestISM330DHCX:
    def setup_method(self):
        self.q = add_ism330dhcxtr(Design(), ref="U3")

    def test_identity(self):
        assert self.q.manf == "STMicroelectronics"
        assert self.q.manf_pn == "ISM330DHCXTR"

    def test_supply(self):
        assert self.q.voltage_rating_v == 3.6
        assert self.q.vcc_nominal_v == 1.8

    def test_temp_range_industrial(self):
        # Industrial sensor — -40 to +105 °C (not the usual +85)
        assert self.q.temp_range_c == (-40, 105)

    def test_14_pins(self):
        assert len(self.q.pins) == 14

    def test_pin_layout(self):
        layout = {
            "1": "SDO_SA0", "2": "SDX", "3": "SCX", "4": "INT1",
            "5": "VDDIO", "6": "GND_1", "7": "GND_2", "8": "VDD",
            "9": "INT2", "10": "OCS_AUX", "11": "SDO_AUX",
            "12": "CS", "13": "SCL", "14": "SDA",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_aux_interface_pins(self):
        # Aux SPI for connecting external sensors
        for n in ("2", "3", "10", "11"):
            assert self.q.pin(n).name in ("SDX", "SCX", "OCS_AUX", "SDO_AUX")

    def test_cs_mode_select_note(self):
        cs = self.q.pin("CS")
        # Datasheet: HIGH = I²C, LOW = SPI
        assert "I²C" in (cs.note or "") or "I2C" in (cs.note or "")

    def test_footprint(self):
        fp = self.q.footprint
        assert "LSM6DS3" in fp.name      # SamacSys-supplied filename
        assert fp.package_class == "LGA-14"
        assert len(fp.pads) == 14
        assert fp.size_mm == (2.5, 3.0)
        assert fp.height_mm == pytest.approx(0.86)

    @pytest.mark.parametrize("substring", [
        "6-axis",
        "Machine Learning Core",   # datasheet capitalisation, verbatim
        "Finite State Machine",
        "AN5392", "AN5388",        # ST app notes cited in datasheet
        "1.71 V", "3.6 V",
        "-40 to +105 °C",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")


# ─── H3LIS331DLTR ────────────────────────────────────────────────────────

class TestH3LIS331DL:
    def setup_method(self):
        self.q = add_h3lis331dltr(Design(), ref="U4")

    def test_identity(self):
        assert self.q.manf == "STMicroelectronics"
        assert self.q.manf_pn == "H3LIS331DLTR"

    def test_temp_range(self):
        # DS p1: T_OP -40 to +85 °C
        assert self.q.temp_range_c == (-40, 85)

    def test_voltage_rating(self):
        # 2.16-3.6 V supply range
        assert self.q.voltage_rating_v == 3.6

    def test_package(self):
        assert "TFLGA-16" in self.q.package
        assert self.q.size_mm == (3.0, 3.0)
        assert self.q.height_mm == pytest.approx(1.0)

    def test_16_pins(self):
        assert len(self.q.pins) == 16

    def test_pin_layout(self):
        layout = {
            "1": "VDD_IO", "2": "NC_1", "3": "NC_2",
            "4": "SCL_SPC", "5": "GND_1", "6": "SDA_SDI_SDO",
            "7": "SDO_SA0", "8": "CS", "9": "INT2",
            "10": "RESERVED_1", "11": "INT1", "12": "GND_2",
            "13": "GND_3", "14": "VDD", "15": "RESERVED_2",
            "16": "GND_4",
        }
        for num, name in layout.items():
            assert self.q.pin(num).name == name

    def test_reserved_pins_tied_to_gnd(self):
        # Datasheet: reserved pins must be tied to GND
        for n in ("10", "15"):
            p = self.q.pin(n)
            assert p.type == "reserved"
            assert "GND" in (p.note or "")

    def test_footprint(self):
        fp = self.q.footprint
        assert "LIS3DH" in fp.name      # SamacSys-supplied filename
        assert fp.package_class == "TFLGA-16L"
        assert len(fp.pads) == 16

    @pytest.mark.parametrize("substring", [
        "10000 g", "shock", "±100", "±200", "±400",
        "ECOPACK", "RoHS",
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")

    def test_rohs_in_standards(self):
        assert "RoHS" in self.q.standards
        assert "ECOPACK" in self.q.standards


# ─── shared invariants ───────────────────────────────────────────────────

ALL_FACTORIES = [add_tmp117maidrvr, add_iis2mdctr,
                 add_ism330dhcxtr, add_h3lis331dltr]


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_each_factory_datasheet_resolves(factory):
    d = Design()
    c = factory(d, ref="U1")
    assert (REPO_ROOT / c.datasheet).is_file()


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_each_factory_3d_model_resolves(factory):
    d = Design()
    c = factory(d, ref="U1")
    assert (REPO_ROOT / c.footprint.model_3d_path).is_file()


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_each_factory_pin_pad_correspondence(factory):
    d = Design()
    c = factory(d, ref="U1")
    pad_nums = {p.num for p in c.footprint.pads}
    pin_nums = {p.num for p in c.pins}
    assert pin_nums == pad_nums, f"{factory.__name__}: mismatch"


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_each_factory_validates_clean(factory):
    d = Design()
    chip = factory(d, ref="U_TEST")
    from _helpers import wire_chip_synthetically
    wire_chip_synthetically(d, chip)
    errors = [i for i in d.validate() if i.severity == "error"]
    assert errors == [], f"{factory.__name__}: {errors}"
