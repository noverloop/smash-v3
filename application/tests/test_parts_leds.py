"""Verify LTST-C190GKT LED factory transcribes its ground-truth."""

from __future__ import annotations

import pathlib

import pytest

from smash import Design, Footprint
from smash.parts import add_ltst_c190gkt


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "application/src/smash/parts/sources/LTST-C190GKT"


class TestLTSTArtifacts:
    @pytest.mark.parametrize("filename", [
        "LTST-C190GKT.pdf",
        "LIB_LTST-C190GKT.samacsys.zip",
        "LTST-C190GKT.kicad_sym",
        "LEDC1608X90N.kicad_mod",
        "LTST-C190GKT.stp",
        "pinmap.txt",
        "part_info.txt",
    ])
    def test_artifact_present(self, filename):
        assert (SRC / filename).is_file()


class TestLTSTC190GKT:
    def setup_method(self):
        self.d = Design()
        self.q = add_ltst_c190gkt(self.d, ref="D1")

    def test_identity(self):
        assert self.q.manf == "Lite-On Technology"
        assert self.q.manf_pn == "LTST-C190GKT"

    def test_datasheet_resolves(self):
        assert (REPO_ROOT / self.q.datasheet).is_file()

    def test_electrical(self):
        # DS p2 absolute max
        assert self.q.voltage_rating_v == 5.0       # reverse voltage
        assert self.q.i_rms_a == 0.030              # DC forward current
        assert self.q.power_rating_w == 0.100       # 100 mW

    def test_temp_range(self):
        # DS p2: -55 to +85 °C
        assert self.q.temp_range_c == (-55, 85)

    def test_package(self):
        assert self.q.package == "0603 (1608 metric)"
        assert self.q.size_mm == (1.6, 0.8)
        assert self.q.height_mm == pytest.approx(0.9)

    def test_pins(self):
        # Pinmap: pin 1 = K (cathode), pin 2 = A (anode)
        assert self.q.pin("1").name == "K"
        assert "Cathode" in self.q.pin("1").aliases
        assert self.q.pin("2").name == "A"
        assert "Anode" in self.q.pin("2").aliases

    def test_alias_lookup(self):
        # Caller ergonomics
        assert self.q.pin("Cathode").num == "1"
        assert self.q.pin("Anode").num == "2"

    def test_footprint(self):
        fp = self.q.footprint
        assert isinstance(fp, Footprint)
        assert fp.name == "LEDC1608X90N"
        assert fp.source == "samacsys"
        # Pad geometry from the .kicad_mod
        expected = {
            "1": ((-0.75, 0.0), (0.9, 0.95)),
            "2": ((+0.75, 0.0), (0.9, 0.95)),
        }
        for pad in fp.pads:
            pos, size = expected[pad.num]
            assert pad.position_mm == pytest.approx(pos)
            assert pad.size_mm == pytest.approx(size)

    def test_3d_model(self):
        assert (REPO_ROOT / self.q.footprint.model_3d_path).is_file()

    @pytest.mark.parametrize("substring", [
        "Water Clear",
        "GaP on GaP, Green",
        "565 nm",                       # peak wavelength
        "569 nm",                       # dominant wavelength
        "130 deg",                      # viewing angle
        "1.80 – 2.80 mcd",              # bin G intensity
        "MIL-STD-750D",
        "Mouser PN     : 859-LTST-C190GKT",
        "Munition-zone",                # design-application caveat
    ])
    def test_note(self, substring):
        assert substring in (self.q.note or "")

    @pytest.mark.parametrize("field", [
        "fab_country",
        "body_material", "lead_material", "rth_ja_cw", "rth_jc_cw",
    ])
    def test_field_unset(self, field):
        # Datasheet doesn't state these — must not be invented. (currency +
        # price_1pc ARE now populated, but from the assumptions.json sourcing
        # overlay — flagged _source:estimate — not invented by the factory.)
        assert getattr(self.q, field) is None

    def test_weight_g_from_package_class(self):
        # Lite-On's datasheet doesn't tabulate mass, but the 0603 chip-
        # LED size + epoxy density is a vendor-pool estimate (see
        # smash.parts._chip_mass.WEIGHT_G_LED_0603). Need this populated
        # so the bend sim's spin / lateral paths don't fall back to a
        # flat 0.5 g default that over-counts a 0603 LED by ~200×.
        assert self.q.weight_g and 0.001 <= self.q.weight_g <= 0.010

    def test_validators_pass(self):
        d = Design()
        led = add_ltst_c190gkt(d, ref="D1")
        d.add_signal_net("LED_K").connect(led.pin("K"))
        d.add_signal_net("LED_A").connect(led.pin("A"))
        errors = [i for i in d.validate() if i.severity == "error"]
        assert errors == []
