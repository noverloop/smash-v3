"""Verify the IRLML6402TRPBF factory transcribes its ground-truth
artifacts faithfully (no hallucinated values, no field drift).

Every assertion here corresponds to a specific source citation:
  DS = datasheet page, KM = SOT95P237X112-3N.kicad_mod,
  PM = pinmap.txt,    KS = IRLML6402TRPBF.kicad_sym.
"""

from __future__ import annotations

import pathlib

import pytest

from smash import Design, Pin, Pad, Footprint
from smash.parts import add_irlml6402trpbf


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCES = REPO_ROOT / "application/src/smash/parts/sources/IRLML6402TRPBF"


# ── ground-truth artifacts present in the repo ───────────────────────────

class TestSourceArtifactsPresent:
    """The factory's source-of-truth files must be colocated under
    `parts/sources/IRLML6402TRPBF/`. If any disappear, the factory loses
    its provenance."""

    @pytest.mark.parametrize("filename", [
        "IRLML6402TRPBF.pdf",
        "LIB_IRLML6402TRPBF.samacsys.zip",
        "IRLML6402TRPBF.kicad_sym",
        "SOT95P237X112-3N.kicad_mod",
        "IRLML6402TRPBF.stp",
        "pinmap.txt",
        "part_info.txt",
        "IRLML6402TRPBF.dcm",
    ])
    def test_artifact_exists(self, filename):
        assert (SOURCES / filename).is_file(), \
            f"missing ground-truth artifact: {filename}"


# ── identity + sourcing ──────────────────────────────────────────────────

class TestIdentity:
    def setup_method(self):
        self.d = Design()
        self.q = add_irlml6402trpbf(self.d, ref="Q1")

    def test_manf_is_infineon(self):
        # IR was acquired by Infineon in 2015; SamacSys + part_info.txt
        # both list Infineon as the current manufacturer.
        assert self.q.manf == "Infineon"

    def test_part_number_exact(self):
        assert self.q.manf_pn == "IRLML6402TRPBF"

    def test_value_set(self):
        # KiCad sym `Value` property is "IRLML6402TRPBF" (KS).
        assert self.q.value == "IRLML6402TRPBF"

    def test_datasheet_path_points_to_real_pdf(self):
        # The factory stores a repo-relative path; resolve against the
        # repo root and confirm the file exists.
        p = REPO_ROOT / self.q.datasheet
        assert p.is_file(), f"datasheet not found at {p}"
        assert p.suffix.lower() == ".pdf"


# ── compliance / standards (datasheet p1 + p9) ───────────────────────────

class TestCompliance:
    def setup_method(self):
        self.q = add_irlml6402trpbf(Design(), ref="Q1")

    def test_rohs_declared(self):
        # DS p1 bullet: "RoHS Compliant, Halogen-Free"
        # DS p9: "RoHS compliant: Yes"
        assert "RoHS" in self.q.standards

    def test_halogen_free_declared(self):
        assert "Halogen-Free" in self.q.standards

    def test_msl1_declared(self):
        # DS p9: "Moisture Sensitivity Level MSL1 (per JEDEC J-STD-020D)"
        assert any("MSL1" in s for s in self.q.standards)

    def test_jedec_outline_declared(self):
        # DS p7 footnote 8: "OUTLINE CONFORMS TO JEDEC OUTLINE TO-236AB"
        assert any("TO-236AB" in s for s in self.q.standards)

    def test_consumer_grade_disclosed(self):
        # DS p9 Qualification table: "Consumer (per JEDEC JESD47F)"
        # Sourcing-policy critical — this is NOT AEC-Q101 / industrial.
        assert any("Consumer" in s for s in self.q.standards)


# ── electrical ratings (datasheet p1) ────────────────────────────────────

class TestElectricalRatings:
    def setup_method(self):
        self.q = add_irlml6402trpbf(Design(), ref="Q1")

    def test_vds_max_20v(self):
        # DS p1 Absolute Max: V_DS = -20 V. We store magnitude.
        assert self.q.voltage_rating_v == 20.0

    def test_id_continuous_25c(self):
        # DS p1: I_D @ T_A=25 °C, V_GS=-4.5V = -3.7 A
        assert self.q.i_rms_a == 3.7

    def test_pd_max_25c(self):
        # DS p1: P_D @ T_A=25 °C = 1.3 W
        assert self.q.power_rating_w == 1.3
        assert self.q.p_max_w == 1.3

    def test_tj_max(self):
        # DS p1: T_J, T_STG range = -55 to +150 °C
        assert self.q.tj_max_c == 150.0

    def test_temp_range(self):
        assert self.q.temp_range_c == (-55, 150)

    def test_rthja_is_max_value(self):
        # DS p1: R_θJA typ 75 / max 100 °C/W.
        # Schema field stores the conservative (max) value; typ is in note.
        assert self.q.rth_ja_cw == 100.0

    def test_rthjc_unknown(self):
        # Datasheet only gives R_θJA, not R_θJC — must remain None
        # rather than guessed.
        assert self.q.rth_jc_cw is None


# ── pin list (datasheet p1 pin diagram + pinmap.txt + KiCad symbol) ──────

class TestPins:
    def setup_method(self):
        self.q = add_irlml6402trpbf(Design(), ref="Q1")

    def test_three_pins(self):
        # DS p1: 3-pin device. PM, KS, KM all agree.
        assert len(self.q.pins) == 3

    def test_pin1_is_gate(self):
        p = self.q.pin("1")
        assert p.name == "G"
        assert "Gate" in p.aliases
        assert p.type == "input"

    def test_pin2_is_source(self):
        p = self.q.pin("2")
        assert p.name == "S"
        assert "Source" in p.aliases
        assert p.type == "io"

    def test_pin3_is_drain(self):
        p = self.q.pin("3")
        assert p.name == "D"
        assert "Drain" in p.aliases
        assert p.type == "io"

    def test_alias_lookup_works(self):
        # Caller-side ergonomics: pin('Gate') should resolve.
        assert self.q.pin("Gate").num == "1"
        assert self.q.pin("Source").num == "2"
        assert self.q.pin("Drain").num == "3"

    def test_pin_chip_ref_back_reference(self):
        # Set by Design.add_chip so callers can pass Pin → design.connect()
        assert all(p.chip_ref == "Q1" for p in self.q.pins)


# ── footprint geometry (SOT95P237X112-3N.kicad_mod) ──────────────────────

class TestFootprint:
    def setup_method(self):
        self.q = add_irlml6402trpbf(Design(), ref="Q1")
        self.fp = self.q.footprint

    def test_footprint_present(self):
        assert isinstance(self.fp, Footprint)

    def test_footprint_name(self):
        # KM: (module "SOT95P237X112-3N" ...)
        assert self.fp.name == "SOT95P237X112-3N"

    def test_package_class(self):
        assert self.fp.package_class == "SOT-23"

    def test_height_matches_datasheet_a_max(self):
        # DS p7 dim table: A max = 1.12 mm
        assert self.fp.height_mm == pytest.approx(1.12)

    def test_pitch_matches_datasheet_e_bsc(self):
        # DS p7: e = 0.95 BSC
        assert self.fp.pitch_mm == pytest.approx(0.95)

    def test_size_matches_nominal_body(self):
        # DS p7: D≈2.92, E1≈1.30 (nominal of MIN/MAX bounds)
        assert self.fp.size_mm == (2.92, 1.30)

    def test_three_pads(self):
        assert len(self.fp.pads) == 3

    def test_pad_positions_exact_from_kicad_mod(self):
        # From KM (screen-y-down, pads carry a 90° rotation):
        #   pad 1 smd rect (at -1.05 -0.95 90) (size 0.6 1.3)
        #   pad 2 smd rect (at -1.05  0.95 90) (size 0.6 1.3)
        #   pad 3 smd rect (at  1.05  0.00 90) (size 0.6 1.3)
        # Model values: y negated into the math-y-up frame, and the 90°
        # pad rotation baked into the size (1.3 wide × 0.6 tall).
        expected = {
            "1": ((-1.05, +0.95), (1.3, 0.6)),
            "2": ((-1.05, -0.95), (1.3, 0.6)),
            "3": ((+1.05,  0.00), (1.3, 0.6)),
        }
        for pad in self.fp.pads:
            pos, size = expected[pad.num]
            assert pad.position_mm == pytest.approx(pos)
            assert pad.size_mm == pytest.approx(size)
            assert pad.shape == "rect"
            assert pad.layer == "F.Cu"

    def test_pin_pad_correspondence(self):
        # Every Pin.num must have a Pad with the same num — the validator
        # `_v_pins_match_footprint_pads` enforces this design-wide, but
        # we assert it directly here too.
        pad_nums = {p.num for p in self.fp.pads}
        pin_nums = {p.num for p in self.q.pins}
        assert pin_nums == pad_nums == {"1", "2", "3"}

    def test_3d_model_path_points_to_real_step(self):
        p = REPO_ROOT / self.fp.model_3d_path
        assert p.is_file()
        assert p.suffix.lower() == ".stp"

    def test_source_is_samacsys(self):
        assert self.fp.source == "samacsys"


# ── note carries the un-promoted datasheet facts ─────────────────────────

class TestNoteHasDatasheetExtras:
    """Every datasheet number not yet promoted to a schema field must
    appear verbatim in `note`. The user's rule: 'if any data is mentioned
    in the datasheet that lacks a field, you can add it to the notes.'"""

    def setup_method(self):
        self.q = add_irlml6402trpbf(Design(), ref="Q1")

    @pytest.mark.parametrize("substring", [
        # Absolute Max ratings not in schema
        "I_DM",                  # pulsed drain current
        "-22 A",                 # pulsed drain current value
        "E_AS",                  # single-pulse avalanche energy
        "11 mJ",                 # avalanche energy value
        "V_GS gate-source",      # V_GS max
        "±12 V",                 # V_GS max value
        "Linear derating",
        # Electrical Characteristics not in schema
        "R_DS(on) @ V_GS=-4.5V", # primary on-resistance condition
        "0.050",                 # R_DS(on) typ @ -4.5V
        "0.065",                 # R_DS(on) max @ -4.5V
        "V_GS(th)",              # gate threshold
        "gfs",                   # transconductance
        "Q_g",                   # total gate charge
        "C_iss",                 # input capacitance
        "C_oss",                 # output capacitance
        "C_rss",                 # reverse transfer capacitance
        "t_d(on)",               # switching delay
        # Body diode
        "V_SD",
        "t_rr",
        "Q_rr",
        # R_θJA typ (we store max in field)
        "75 °C/W",
        # Qualification
        "Consumer",
        "MSL1",
        # Part marking
        "\"E\"",
        # Mechanical gaps
        "body_material",
        "lead_material",
        "weight_g",
        "fab_country",
        # Distributor data
        "Mouser PN",
        "Arrow PN",
    ])
    def test_note_contains(self, substring):
        assert substring in (self.q.note or ""), \
            f"note missing datasheet citation: {substring!r}"


# ── design integration: factory composes cleanly with the model ──────────

class TestFactoryIntegrates:
    def test_added_to_design(self):
        d = Design()
        q = add_irlml6402trpbf(d, ref="Q_MAIN")
        assert d.chip_by_ref("Q_MAIN") is q

    def test_two_instances_independent(self):
        d = Design()
        a = add_irlml6402trpbf(d, ref="Q1")
        b = add_irlml6402trpbf(d, ref="Q2")
        assert a is not b
        # Each instance carries its own Footprint object — instance
        # ownership, not shared library.
        assert a.footprint is not b.footprint

    def test_duplicate_ref_raises(self):
        d = Design()
        add_irlml6402trpbf(d, ref="Q1")
        with pytest.raises(ValueError, match="duplicate"):
            add_irlml6402trpbf(d, ref="Q1")

    def test_overrides_passed_through(self):
        # board_tag is an Add-chip kwarg, not a Chip field on the
        # factory's literal dict — must be threaded via overrides.
        d = Design()
        q = add_irlml6402trpbf(d, ref="Q1",
                               board_tag="power_board", dnp=True,
                               role="main_load_switch_pmos")
        assert q.board_tag == "power_board"
        assert q.dnp is True
        assert q.role == "main_load_switch_pmos"

    def test_can_wire_into_nets(self):
        d = Design()
        q = add_irlml6402trpbf(d, ref="Q1")
        d.add_power_net("VBAT", voltage_v=4.0).connect(q.pin("S"))
        d.add_power_net("VLOAD", voltage_v=4.0).connect(q.pin("D"))
        d.add_signal_net("GATE_CTRL").connect(q.pin("G"))
        assert q.pin("S").net == "VBAT"
        assert q.pin("D").net == "VLOAD"
        assert q.pin("G").net == "GATE_CTRL"

    def test_validators_pass_with_full_design(self):
        # A single, wired-up IRLML6402 should pass every registered
        # validator (no floating chips, footprint pads match pins,
        # datasheet path present, fab_country=None is allowed, etc.)
        d = Design()
        q = add_irlml6402trpbf(d, ref="Q1")
        d.add_power_net("VBAT", voltage_v=4.0).connect(q.pin("S"))
        d.add_power_net("VLOAD", voltage_v=4.0).connect(q.pin("D"))
        d.add_signal_net("GATE_CTRL").connect(q.pin("G"))
        issues = d.validate()
        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], f"unexpected errors: {errors}"


# ── nothing hallucinated where datasheet is silent ───────────────────────

class TestNoHallucinations:
    """Fields the datasheet doesn't state must remain unset rather than
    invented. This is the discipline that keeps the catalog honest."""

    def setup_method(self):
        # Raw factory output — no assumptions.json overlay. Tests below
        # check the FACTORY didn't invent fields the datasheet doesn't
        # state. (Sourcing data like price/fab_country can still legally
        # arrive via the overlay; that's curated, not invented.)
        self.q = add_irlml6402trpbf(Design(apply_assumptions=False), ref="Q1")
        self.q_overlaid = add_irlml6402trpbf(Design(), ref="Q1")

    @pytest.mark.parametrize("field", [
        # Datasheet-absent fields the factory must NEVER fabricate,
        # even after assumptions.json runs:
        "fab_location",
        "price_20kpc",
        "weight_g",
        "body_material",
        "lead_material",
        "density_g_cm3",
        "youngs_modulus_gpa",
        "cte_ppm_k",
        "rth_jc_cw",
        "eccn",
        "itar",
    ])
    def test_field_is_unset(self, field):
        assert getattr(self.q, field) is None, \
            f"{field} was invented; datasheet doesn't state it"
        assert getattr(self.q_overlaid, field) is None, \
            f"{field} appears in assumptions.json — should be raw-factory-only"

    @pytest.mark.parametrize("field", ["fab_country", "currency", "price_1pc"])
    def test_sourcing_field_only_from_assumptions(self, field):
        """The factory must NOT bake sourcing data in — it should only
        appear via the assumptions.json overlay."""
        assert getattr(self.q, field) is None, \
            f"{field} was baked into the factory; should arrive via assumptions"
        assert getattr(self.q_overlaid, field) is not None, \
            f"{field} missing from assumptions.json for IRLML6402TRPBF"
