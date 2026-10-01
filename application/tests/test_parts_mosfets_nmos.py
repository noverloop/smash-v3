"""Verify the IRLML6244TRPBF and BSS138LT1G N-MOS factories transcribe
their ground-truth artifacts faithfully.

Each part has a small dedicated TestCase; common contracts (ground-
truth artifact presence, pin/pad correspondence, validators, no-
hallucinations) are run per-part.

Source citations:
  DS-6244 = IRLML6244PbF datasheet (PD-97535A, 03/09/12).
  DS-BSS  = BSS138LT1G datasheet (BSS138LT1/D rev 14, April 2024).
  KM      = colocated .kicad_mod (only for IRLML6244 — BSS138 has none).
  PM      = pinmap.txt.
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design, Pin, Footprint
from smash.parts import add_irlml6244trpbf, add_bss138lt1g


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_ROOT  = REPO_ROOT / "application/src/smash/parts/sources"


# ─── IRLML6244TRPBF ──────────────────────────────────────────────────────

class TestIRLML6244TRPBFArtifacts:
    @pytest.mark.parametrize("filename", [
        "IRLML6244TRPBF.pdf",
        "LIB_IRLML6244TRPBF.samacsys.zip",
        "IRLML6244TRPBF.kicad_sym",
        "SOT95P237X112-3N.kicad_mod",
        "IRLML6244TRPBF.stp",
        "pinmap.txt",
        "part_info.txt",
    ])
    def test_artifact_present(self, filename):
        assert (SRC_ROOT / "IRLML6244TRPBF" / filename).is_file()


class TestIRLML6244TRPBF:
    def setup_method(self):
        self.d = Design()
        self.q = add_irlml6244trpbf(self.d, ref="Q1")

    def test_identity(self):
        assert self.q.manf == "Infineon"
        assert self.q.manf_pn == "IRLML6244TRPBF"

    def test_datasheet_resolves(self):
        assert (REPO_ROOT / self.q.datasheet).is_file()

    def test_compliance(self):
        s = self.q.standards
        assert "RoHS" in s
        assert any("TO-236AB" in x for x in s)
        assert any("MSL1" in x for x in s)
        assert any("Consumer" in x for x in s)

    def test_electrical(self):
        # DS-6244 p1
        assert self.q.voltage_rating_v == 20.0
        assert self.q.i_rms_a == 6.3
        assert self.q.power_rating_w == 1.3
        assert self.q.tj_max_c == 150.0
        # DS-6244 p1 R_θJA steady-state max
        assert self.q.rth_ja_cw == 100.0
        assert self.q.rth_jc_cw is None

    def test_temp_range(self):
        assert self.q.temp_range_c == (-55, 150)

    def test_package(self):
        assert self.q.package == "SOT-23"
        assert self.q.height_mm == pytest.approx(1.12)

    def test_pins(self):
        # PM + DS-6244 p1 + KiCad sym (3 sources agree)
        assert self.q.pin("1").name == "G"
        assert self.q.pin("2").name == "S"
        assert self.q.pin("3").name == "D"
        assert "Gate"   in self.q.pin("1").aliases
        assert "Source" in self.q.pin("2").aliases
        assert "Drain"  in self.q.pin("3").aliases
        assert all(p.chip_ref == "Q1" for p in self.q.pins)

    def test_footprint_pads_from_kicad_mod(self):
        # Same source mod as IRLML6402 (SamacSys generator): y negated
        # into the math-y-up model, 90° pad rotation baked into the size.
        expected = {
            "1": ((-1.05, +0.95), (1.3, 0.6)),
            "2": ((-1.05, -0.95), (1.3, 0.6)),
            "3": ((+1.05,  0.00), (1.3, 0.6)),
        }
        fp = self.q.footprint
        assert isinstance(fp, Footprint)
        assert fp.name == "SOT95P237X112-3N"
        assert fp.source == "samacsys"
        for pad in fp.pads:
            pos, size = expected[pad.num]
            assert pad.position_mm == pytest.approx(pos)
            assert pad.size_mm == pytest.approx(size)

    @pytest.mark.parametrize("substring", [
        "I_DM", "32 A",
        "R_DS(on) @ V_GS=4.5V",
        "16.0", "21.0",            # mΩ typ/max @ V_GS=4.5V
        "V_GS(th)", "gfs",
        "R_G internal gate resistance",
        "C_iss", "C_oss", "C_rss",
        "Consumer", "MSL1",
        "Mouser PN",
    ])
    def test_note_contains(self, substring):
        assert substring in (self.q.note or "")

    @pytest.mark.parametrize("field", [
        "fab_country", "currency", "price_1pc", "weight_g",
        "body_material", "lead_material", "rth_jc_cw",
    ])
    def test_field_unset(self, field):
        assert getattr(self.q, field) is None

    def test_validators_pass(self):
        d = Design()
        q = add_irlml6244trpbf(d, ref="Q1")
        d.add_signal_net("G").connect(q.pin("G"))
        d.add_power_net("VDD", voltage_v=3.3).connect(q.pin("D"))
        d.add_ground_net("GND").connect(q.pin("S"))
        errors = [i for i in d.validate() if i.severity == "error"]
        assert errors == []


# ─── BSS138LT1G ──────────────────────────────────────────────────────────

class TestBSS138LT1GArtifacts:
    @pytest.mark.parametrize("filename", [
        "BSS138LT1G.pdf",
        "BSS138LT1G.kicad_sym",
        "BSS138LT1G.stp",
        "pinmap.txt",
        "part_info.txt",
    ])
    def test_artifact_present(self, filename):
        assert (SRC_ROOT / "BSS138LT1G" / filename).is_file()

    def test_samacsys_archive_absent(self):
        # Documented gap — surface for future re-fetch. NOT a failure,
        # but a single assertion that codifies the gap so it can't be
        # silently filled with hallucinated data.
        assert not (SRC_ROOT / "BSS138LT1G"
                    / "LIB_BSS138LT1G.samacsys.zip").exists()


class TestBSS138LT1G:
    def setup_method(self):
        # Two designs side by side: `q` is the assumption-overlaid surface
        # the live system sees; `q_raw` is the raw factory output (no
        # assumptions.json overlay) — used to check that the factory
        # itself doesn't fabricate sourcing data.
        self.d = Design()
        self.q = add_bss138lt1g(self.d, ref="Q2")
        self.d_raw = Design(apply_assumptions=False)
        self.q_raw = add_bss138lt1g(self.d_raw, ref="Q2")

    def test_identity(self):
        assert self.q.manf == "onsemi"
        assert self.q.manf_pn == "BSS138LT1G"

    def test_datasheet_resolves(self):
        assert (REPO_ROOT / self.q.datasheet).is_file()

    def test_compliance(self):
        s = self.q.standards
        assert "RoHS" in s
        assert "Pb-Free" in s
        assert "BFR-Free" in s
        assert any("TO-236" in x for x in s)
        # DS-BSS feature bullet: HBM Class 0A, MM Class M1A, CDM Class IV
        assert any("HBM Class 0A" in x for x in s)
        assert any("MM Class M1A" in x for x in s)
        assert any("CDM Class IV" in x for x in s)

    def test_electrical(self):
        # DS-BSS p1 absolute max
        assert self.q.voltage_rating_v == 50.0          # V_DSS
        assert self.q.i_rms_a == 0.200                  # 200 mA continuous
        assert self.q.power_rating_w == 0.225           # 225 mW
        assert self.q.tj_max_c == 150.0
        assert self.q.rth_ja_cw == 556.0                # very high — SOT-23
        assert self.q.rth_jc_cw is None

    def test_package(self):
        assert self.q.package == "SOT-23"
        # DS-BSS p6 Case 318 dim table: A max = 1.11 mm
        assert self.q.height_mm == pytest.approx(1.11)

    def test_pins(self):
        # DS-BSS p1 marking diagram + p7 Case 318 Style 21 (G=1, S=2, D=3)
        assert self.q.pin("1").name == "G"
        assert self.q.pin("2").name == "S"
        assert self.q.pin("3").name == "D"

    def test_footprint_from_onsemi_recommended(self):
        # Per DS-BSS p6 recommended mounting footprint: pad 0.56 × 0.95,
        # vertical pitch 1.90 mm — rotated into the project's horizontal
        # SOT-23 orientation (leads along ±x), so each pad's long axis
        # (0.95) runs along the lead.
        fp = self.q.footprint
        assert fp.name == "SOT96P237X111-3N"
        # source must be tagged as datasheet-derived, NOT samacsys —
        # so a later validator can flag this for SamacSys upgrade.
        assert fp.source == "onsemi-datasheet"
        for pad in fp.pads:
            assert pad.size_mm == pytest.approx((0.95, 0.56))
        # Pin 1 to pin 2 vertical center-to-center == 1.90 mm, with
        # pin 1 (G) upper-left in the model's y-up frame (matches the
        # library_kicad vendor footprint's orientation).
        p1 = fp.pad("1").position_mm
        p2 = fp.pad("2").position_mm
        assert abs(p2[1] - p1[1]) == pytest.approx(1.90)
        assert p1[1] > 0 > p2[1]

    @pytest.mark.parametrize("substring", [
        "V_DSS  drain-source voltage : 50 V",
        "I_DM",
        "800 mA",                                   # pulsed I_D
        "HBM Class 0A",
        "BVSS",                                     # the automotive variant
        "AEC-Q101",
        "r_DS(on) @ V_GS=5.0V",
        "0.85 V min",                               # V_GS(th)
        "FOOTPRINT NOTE",                           # explicit gap callout
        "Mouser PN",
    ])
    def test_note_contains(self, substring):
        assert substring in (self.q.note or "")

    @pytest.mark.parametrize("field", [
        "weight_g", "body_material", "lead_material", "rth_jc_cw",
    ])
    def test_field_unset(self, field):
        """These fields aren't supplied by the catalog factory or by
        assumptions.json — they must stay None in both modes."""
        assert getattr(self.q, field) is None
        assert getattr(self.q_raw, field) is None

    @pytest.mark.parametrize("field", ["fab_country", "currency", "price_1pc"])
    def test_sourcing_field_only_from_assumptions(self, field):
        """The factory must NOT bake sourcing data in — it should only
        appear after the assumptions.json overlay runs."""
        assert getattr(self.q_raw, field) is None
        assert getattr(self.q, field) is not None

    def test_validators_pass(self):
        # Skip the assumptions overlay so `fab_country` doesn't trip
        # the forbidden_fab validator (BSS138LT1G is sourced from CN
        # per assumptions.json — a separate test asserts that rule).
        d = Design(apply_assumptions=False)
        q = add_bss138lt1g(d, ref="Q2")
        d.add_signal_net("G").connect(q.pin("G"))
        d.add_power_net("VDD", voltage_v=12.0).connect(q.pin("D"))
        d.add_ground_net("GND").connect(q.pin("S"))
        errors = [i for i in d.validate() if i.severity == "error"]
        assert errors == []


# ─── Cross-part: discrete-MOSFET factory contract ────────────────────────

class TestMosfetFactoryContract:
    """Three MOSFET factories now in the catalog. They should all
    share the same shape: 3-pin SOT-23, pin G/S/D at positions 1/2/3,
    overrides pass through, instances are independent."""

    from smash.parts import (add_irlml6402trpbf,
                             add_irlml6244trpbf,
                             add_bss138lt1g)
    FACTORIES = [add_irlml6402trpbf, add_irlml6244trpbf, add_bss138lt1g]

    @pytest.mark.parametrize("factory", FACTORIES)
    def test_three_pins(self, factory):
        d = Design()
        q = factory(d, ref="Q1")
        assert len(q.pins) == 3
        assert {p.name for p in q.pins} == {"G", "S", "D"}

    @pytest.mark.parametrize("factory", FACTORIES)
    def test_gsd_at_123(self, factory):
        d = Design()
        q = factory(d, ref="Q1")
        assert q.pin("1").name == "G"
        assert q.pin("2").name == "S"
        assert q.pin("3").name == "D"

    @pytest.mark.parametrize("factory", FACTORIES)
    def test_overrides_pass_through(self, factory):
        d = Design()
        q = factory(d, ref="Q1", board_tag="power_board", dnp=True)
        assert q.board_tag == "power_board"
        assert q.dnp is True

    @pytest.mark.parametrize("factory", FACTORIES)
    def test_instance_isolation(self, factory):
        d = Design()
        a = factory(d, ref="Q1")
        b = factory(d, ref="Q2")
        assert a is not b
        assert a.footprint is not b.footprint
        # Modifying one's pin shouldn't affect the other
        a.pin("G").net = "MUTATED"
        assert b.pin("G").net != "MUTATED"
