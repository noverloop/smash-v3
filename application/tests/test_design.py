"""Unit tests for smash.design — Chip, Pin, Net, Design, validators."""

import json
import pathlib

import pytest

from smash import (
    Chip, Battery, Pin, Pad, Footprint,
    Net, Design, NetHandle, BoardView, Issue, validator,
)


# ── Chip + Pin lookup ────────────────────────────────────────────────────

class TestChipPinLookup:
    def test_pin_lookup_by_num(self):
        d = Design()
        c = d.add_chip(ref="U1", manf_pn="STM32H562AII6",
                       pins=[("J4", "PA0"), ("D9", "PD0")])
        assert c.pin("J4").name == "PA0"

    def test_pin_lookup_by_name(self):
        d = Design()
        c = d.add_chip(ref="U1",
                       pins=[("J4", "PA0"), ("D9", "PD0")])
        assert c.pin("PD0").num == "D9"

    def test_pin_lookup_by_alias(self):
        d = Design()
        c = d.add_chip(ref="U1",
                       pins=[Pin(num="D9", name="PD0",
                                 aliases=["UART4_RX", "I2C3_SCL"])])
        assert c.pin("UART4_RX").num == "D9"
        assert c.pin("I2C3_SCL").num == "D9"
        # All three retrieval paths hit the same Pin
        assert c.pin("D9") is c.pin("PD0") is c.pin("UART4_RX")

    def test_pin_lookup_missing_raises(self):
        d = Design()
        c = d.add_chip(ref="U1", pins=[("J4", "PA0")])
        with pytest.raises(KeyError, match="no pin with num/name/alias"):
            c.pin("PB99")

    def test_pin_lookup_ambiguous_alias_raises(self):
        d = Design()
        c = d.add_chip(ref="U_AMBIG",
                       pins=[Pin(num="1", name="A", aliases=["SHARED"]),
                             Pin(num="2", name="B", aliases=["SHARED"])])
        with pytest.raises(KeyError, match="matches 2 pins"):
            c.pin("SHARED")

    def test_pin_chip_ref_back_reference(self):
        d = Design()
        c = d.add_chip(ref="U_MPU", pins=[("AB1", "VDD")])
        assert c.pin("AB1").chip_ref == "U_MPU"

    def test_passive_numeric_value_fields(self):
        d = Design()
        # Cap with full numeric + rating fields
        c = d.add_chip(ref="C1", value="100nF/50V",
                       capacitance_f=100e-9,
                       voltage_rating_v=50,
                       tolerance_pct=10,
                       dielectric="X7R",
                       esr_mohm=20)
        assert c.capacitance_f == 100e-9
        assert c.voltage_rating_v == 50
        assert c.tolerance_pct == 10
        assert c.esr_mohm == 20
        # Resistor
        r = d.add_chip(ref="R1", value="10k 1%",
                       resistance_ohm=10_000,
                       tolerance_pct=1,
                       power_rating_w=0.0625)   # 1/16 W
        assert r.resistance_ohm == 10_000
        assert r.power_rating_w == 0.0625
        # Power inductor
        l = d.add_chip(ref="L_VMOT", value="10uH",
                       inductance_h=10e-6,
                       i_sat_a=6.0,
                       i_rms_a=5.0,
                       tolerance_pct=20)
        assert l.inductance_h == 10e-6
        assert l.i_sat_a == 6.0

    def test_price_with_currency_tag(self):
        d = Design()
        # Each chip has ONE price field plus a currency tag.
        c1 = d.add_chip(ref="U_AWR", manf_pn="IWR1843",
                        currency="USD", price_1pc=30.0, price_20kpc=19.5)
        c2 = d.add_chip(ref="U_MPU", manf_pn="STM32MP255",
                        currency="EUR", price_1pc=24.0, price_20kpc=13.5)
        assert c1.currency == "USD"
        assert c1.price_1pc == 30.0
        assert c2.currency == "EUR"
        assert c2.price_1pc == 24.0

    def test_note_field_on_chip_and_pin(self):
        d = Design()
        c = d.add_chip(
            ref="U_FLIGHT",
            note="STM32H562 — compliance: AEC-Q100 Grade 1 "
                 "expected by 2026Q4 (currently industrial-grade); "
                 "see vendor email 2026-03-12.",
            pins=[Pin(num="A1", name="VDD",
                      note="DNP if VDD_EXT used (cluster 7 mod)")],
        )
        assert "AEC-Q100" in c.note
        assert c.pin("A1").note.startswith("DNP if VDD_EXT")

    def test_pins_by_name_returns_all_matches(self):
        """Power pins legitimately share a name across many balls.
        H562 has VDD on multiple balls — must be queryable as a list."""
        d = Design()
        mcu = d.add_chip(ref="U1", manf_pn="STM32H562AII6",
                         pins=[Pin(num="A1", name="VDD"),
                               Pin(num="E5", name="VDD"),
                               Pin(num="F3", name="VDD"),
                               Pin(num="K9", name="VDD"),
                               Pin(num="J4", name="PA0"),
                               Pin(num="J5", name="PA1"),
                               Pin(num="B1", name="VSS"),
                               Pin(num="B2", name="VSS")])
        # Plural lookup returns all
        vdd_pins = mcu.pins_by_name("VDD")
        assert len(vdd_pins) == 4
        assert {p.num for p in vdd_pins} == {"A1", "E5", "F3", "K9"}
        # Signal pin still works as one
        assert mcu.pin("PA0").num == "J4"
        # Empty list for missing name
        assert mcu.pins_by_name("NONEXISTENT") == []
        # Singular pin() raises on ambiguity (helps catch signal-pin bugs)
        with pytest.raises(KeyError, match="pins_by_name"):
            mcu.pin("VDD")

    def test_net_connect_all_for_power_rails(self):
        d = Design()
        mcu = d.add_chip(ref="U1",
                         pins=[Pin(num="A1", name="VDD"),
                               Pin(num="E5", name="VDD"),
                               Pin(num="B1", name="VSS"),
                               Pin(num="B2", name="VSS")])
        vdd = d.add_power_net("VDD", voltage_v=3.3)
        gnd = d.add_ground_net("GND")
        vdd.connect_all(mcu.pins_by_name("VDD"))
        gnd.connect_all(mcu.pins_by_name("VSS"))
        # Both VDD pads landed on VDD net
        assert set(d.net_by_name("VDD").pins) == {("U1", "A1"), ("U1", "E5")}
        assert set(d.net_by_name("GND").pins) == {("U1", "B1"), ("U1", "B2")}

    def test_clock_freq_hz_field(self):
        """Crystals and oscillators carry their nominal frequency
        as a typed field (distinct from `clock_max_hz` for MCUs)."""
        d = Design()
        hse = d.add_chip(ref="Y1", manf_pn="DSC1001CI5-008.0000",
                         value="8.000000 MHz",
                         clock_freq_hz=8_000_000)
        lse = d.add_chip(ref="Y2", manf_pn="DSC1001CI5-032.7680",
                         value="32.768 kHz",
                         clock_freq_hz=32_768)
        h562 = d.add_chip(ref="U1", manf_pn="STM32H562AII6",
                          clock_max_hz=550_000_000)
        assert hse.clock_freq_hz == 8_000_000
        assert lse.clock_freq_hz == 32_768
        assert h562.clock_max_hz == 550_000_000
        # MCU doesn't have a fixed clock_freq; crystals don't have a
        # clock_max_hz — fields are independent.
        assert hse.clock_max_hz is None
        assert h562.clock_freq_hz is None

    def test_pin_electrical_class_fields(self):
        d = Design()
        c = d.add_chip(ref="U_MPU", pins=[
            Pin(num="AB1", name="VDD",          type="power",
                voltage_domain="VDDIO1"),
            Pin(num="AB2", name="VSS",          type="ground"),
            Pin(num="D9",  name="PD0",          type="io",
                voltage_domain="VDDIO1",        io_standard="LVCMOS33",
                aliases=["UART4_RX"]),
            Pin(num="N1",  name="DDR_DQ0",      type="io",
                voltage_domain="VDD_DDR",       io_standard="SSTL15"),
            Pin(num="N99", name="RESERVED_NC",  type="reserved"),
        ])
        # Looked up by name returns the rich Pin record
        ddr = c.pin("DDR_DQ0")
        assert ddr.type == "io"
        assert ddr.voltage_domain == "VDD_DDR"
        assert ddr.io_standard == "SSTL15"
        # alias still resolves
        rx = c.pin("UART4_RX")
        assert rx.io_standard == "LVCMOS33"
        # type defaults to None when not specified
        c2 = d.add_chip(ref="U_OTHER", pins=[("1",)])
        assert c2.pin("1").type is None

    def test_duplicate_chip_ref_raises(self):
        d = Design()
        d.add_chip(ref="U1")
        with pytest.raises(ValueError, match="duplicate chip ref"):
            d.add_chip(ref="U1")


# ── Footprint as first-class citizen ─────────────────────────────────────

class TestFootprint:
    def _r0402(self) -> Footprint:
        return Footprint(
            name="R_0402_1005Metric",
            package_class="0402",
            size_mm=(1.0, 0.5),
            height_mm=0.4,
            pads=[
                Pad(num="1", position_mm=(-0.5, 0.0), size_mm=(0.5, 0.6),
                    shape="rect", layer="F.Cu"),
                Pad(num="2", position_mm=(+0.5, 0.0), size_mm=(0.5, 0.6),
                    shape="rect", layer="F.Cu"),
            ],
            body_outline=[(-0.5, -0.25), (0.5, -0.25),
                          (0.5, 0.25), (-0.5, 0.25)],
            courtyard=[(-0.7, -0.4), (0.7, -0.4),
                       (0.7, 0.4), (-0.7, 0.4)],
            source="kicad-stock",
        )

    def test_inline_ownership(self):
        d = Design()
        fp = self._r0402()
        c = d.add_chip(ref="R1", value="10k", footprint=fp,
                       pins=[("1",), ("2",)])
        # Chip owns its Footprint directly
        assert c.footprint is fp
        # No separate library on Design
        assert not hasattr(d, "footprints")

    def test_two_chips_can_share_or_clone_footprint(self):
        """Same Footprint object can be referenced by multiple chips.
        Each chip's `footprint` is an independent attribute, so callers
        can either share (one Footprint object referenced from many
        chips) or clone (`copy.deepcopy(fp)`) per-instance — design
        choice, not enforced."""
        d = Design()
        fp = self._r0402()
        d.add_chip(ref="R1", footprint=fp, pins=[("1",), ("2",)])
        d.add_chip(ref="R2", footprint=fp, pins=[("1",), ("2",)])
        assert d.chip_by_ref("R1").footprint is d.chip_by_ref("R2").footprint

    def test_string_footprint_rejected(self):
        d = Design()
        with pytest.raises(TypeError, match="must be a Footprint instance"):
            d.add_chip(ref="R1", footprint="R_0402_1005Metric")

    def test_design_footprint_of_helper(self):
        d = Design()
        fp = self._r0402()
        c = d.add_chip(ref="R1", footprint=fp, pins=[("1",), ("2",)])
        # Works for chips
        assert d.footprint_of(c) is fp
        # And for batteries
        bat = d.add_battery(ref="BT1", manf_pn="X",
                            footprint=fp,
                            pins=[Pin(num="1", name="+"), Pin(num="2", name="-")])
        assert d.footprint_of(bat) is fp
        # Returns None for chips without a footprint
        c2 = d.add_chip(ref="U_TODO")
        assert d.footprint_of(c2) is None

    def test_pad_lookup(self):
        fp = self._r0402()
        assert fp.pad("1").position_mm == (-0.5, 0.0)
        with pytest.raises(KeyError):
            fp.pad("99")

    def test_pin_pad_mismatch_caught_by_validator(self):
        d = Design()
        fp = self._r0402()    # has pads "1" and "2"
        d.add_chip(ref="R_BAD", footprint=fp,
                   pins=[Pin(num="1"), Pin(num="3")])  # "3" not in footprint
        issues = [i for i in d.validate() if i.rule == "pin_pad_mismatch"]
        assert len(issues) == 1
        assert "pin '3'" in issues[0].message

    def test_footprint_json_roundtrip(self, tmp_path):
        d = Design()
        fp = self._r0402()
        d.add_chip(ref="R1", value="10k", footprint=fp,
                   pins=[("1",), ("2",)])
        out = tmp_path / "design.json"
        d.dump_json(out)
        d2 = Design.load_json(out)
        c2 = d2.chip_by_ref("R1")
        # Footprint round-tripped
        assert isinstance(c2.footprint, Footprint)
        assert c2.footprint.name == "R_0402_1005Metric"
        assert c2.footprint.size_mm == (1.0, 0.5)
        # Pad geometry survived
        assert c2.footprint.pad("1").position_mm == (-0.5, 0.0)
        # Pad shape preserved
        assert c2.footprint.pad("1").shape == "rect"


# ── Battery as first-class citizen ───────────────────────────────────────

class TestBattery:
    def test_battery_basics(self):
        d = Design()
        bat = d.add_battery(
            ref="BT1",
            manf="Tadiran",
            manf_pn="TLM-1520HPM/S",
            chemistry="Li-MnO2 organic",
            capacity_mah=125,
            nominal_voltage_v=4.0,
            ocv_min_v=3.95, ocv_max_v=4.07,
            ccv_min_v=3.88,
            i_continuous_a=1.75,
            i_pulse_a=3.75, pulse_duration_s=1.0,
            impedance_mohm=100,
            package="Ø14.8×21",
            size_mm=(14.8, 21.0),
            weight_g=9.0,
            temp_range_c=(-40, 85),
            chemistry_compliance=None,  # would be IEC 60086 etc.
            standards=["UN 38.3", "IEC 60086"],
            hazmat_class="UN3090",
            fab_country="IL",
            fab_location="Tadiran (Kiryat Ekron, IL)",
            distributor="Tadiran Batteries GmbH (Büdingen, DE)",
            currency="EUR", price_1pc=45.0, price_20kpc=31.50,
            board_tag="power_board",
        ) if False else d.add_battery(
            ref="BT1",
            manf="Tadiran",
            manf_pn="TLM-1520HPM/S",
            chemistry="Li-MnO2 organic",
            capacity_mah=125,
            nominal_voltage_v=4.0,
            ocv_min_v=3.95, ocv_max_v=4.07,
            ccv_min_v=3.88,
            i_continuous_a=1.75,
            i_pulse_a=3.75, pulse_duration_s=1.0,
            impedance_mohm=100,
            package="Ø14.8×21",
            size_mm=(14.8, 21.0),
            weight_g=9.0,
            temp_range_c=(-40, 85),
            standards=["UN 38.3", "IEC 60086"],
            hazmat_class="UN3090",
            fab_country="IL",
            fab_location="Tadiran (Kiryat Ekron, IL)",
            distributor="Tadiran Batteries GmbH (Büdingen, DE)",
            currency="EUR", price_1pc=45.0, price_20kpc=31.50,
            board_tag="power_board",
        )
        # Default pins added automatically
        assert len(bat.pins) == 2
        assert {p.name for p in bat.pins} == {"+", "-"}
        # Battery-specific fields
        assert bat.chemistry == "Li-MnO2 organic"
        assert bat.capacity_mah == 125
        assert bat.i_pulse_a == 3.75
        assert bat.hazmat_class == "UN3090"

    def test_battery_default_pins_polarised(self):
        d = Design()
        bat = d.add_battery(ref="BT1", manf_pn="X")
        # Default polarisation: + and -
        plus  = bat.pin("+")
        minus = bat.pin("-")
        assert plus.num == "1"
        assert minus.num == "2"
        assert plus.chip_ref == "BT1"

    def test_battery_ref_collision_with_chip(self):
        """A ref must be unique across chips + batteries."""
        d = Design()
        d.add_chip(ref="U1")
        with pytest.raises(ValueError, match="already used by a chip"):
            d.add_battery(ref="U1", manf_pn="X")
        d.add_battery(ref="BT1", manf_pn="Y")
        with pytest.raises(ValueError, match="duplicate battery ref"):
            d.add_battery(ref="BT1", manf_pn="Z")

    def test_battery_lookup_helpers(self):
        d = Design()
        d.add_chip(ref="U_MPU")
        d.add_battery(ref="BT1", manf_pn="TLM-1520HPM/S",
                      board_tag="power_board")
        d.add_battery(ref="BT2", manf_pn="TLM-1520HPM/S",
                      board_tag="power_board")
        d.add_battery(ref="BT3", manf_pn="TLM-1520HPM/S",
                      board_tag="power_board")
        assert d.battery_by_ref("BT1").manf_pn == "TLM-1520HPM/S"
        # Cross-type lookup
        assert d.component_by_ref("U_MPU").ref == "U_MPU"
        assert d.component_by_ref("BT1").ref == "BT1"
        assert d.component_by_ref("U_GHOST") is None
        # Per-board filter
        on_pwr = d.batteries_on_board("power_board")
        assert len(on_pwr) == 3

    def test_battery_connect_via_pin(self):
        d = Design()
        bat = d.add_battery(ref="BT1", manf_pn="X")
        efuse = d.add_chip(ref="U_EFUSE",
                           pins=[("1", "VIN"), ("2", "VOUT"), ("3", "GND")])
        d.add_power_net("BAT_RAW", voltage_v=4.0) \
         .connect(bat.pin("+")).connect(efuse.pin("VIN"))
        d.add_ground_net("GND") \
         .connect(bat.pin("-")).connect(efuse.pin("GND"))
        # Verify both sides
        assert ("BT1", "1") in d.net_by_name("BAT_RAW").pins
        assert ("U_EFUSE", "1") in d.net_by_name("BAT_RAW").pins
        assert bat.pin("+").net == "BAT_RAW"

    def test_battery_pack_notation(self):
        """3 cells in parallel — pack_count + pack_config metadata."""
        d = Design()
        for i in (1, 2, 3):
            d.add_battery(
                ref=f"BT{i}",
                manf_pn="TLM-1520HPM/S",
                board_tag="power_board",
                pack_count=3, pack_config="3p",
                weight_g=9.0,
                currency="EUR", price_1pc=45.0,
            )
        # Three siblings, same pack identity via metadata
        pack_members = [b for b in d.batteries if b.pack_config == "3p"]
        assert len(pack_members) == 3

    def test_battery_json_roundtrip(self, tmp_path):
        d = Design()
        bat = d.add_battery(
            ref="BT1", manf="Tadiran", manf_pn="TLM-1520HPM/S",
            chemistry="Li-MnO2 organic", capacity_mah=125,
            nominal_voltage_v=4.0, i_pulse_a=3.75,
            package="Ø14.8×21", size_mm=(14.8, 21.0),
            temp_range_c=(-40, 85),
            standards=["UN 38.3"], hazmat_class="UN3090",
            currency="EUR", price_1pc=45.0,
            board_tag="power_board",
        )
        out = tmp_path / "design.json"
        d.dump_json(out)
        d2 = Design.load_json(out)
        b2 = d2.battery_by_ref("BT1")
        assert b2.chemistry == "Li-MnO2 organic"
        assert b2.size_mm == (14.8, 21.0)
        assert b2.standards == ["UN 38.3"]
        assert b2.hazmat_class == "UN3090"


# ── Net constructors + typed kinds ───────────────────────────────────────

class TestNetConstructors:
    def test_power_net_has_voltage(self):
        d = Design()
        h = d.add_power_net("COMP_1V35", voltage_v=1.35)
        n = d.net_by_name("COMP_1V35")
        assert n.kind == "power"
        assert n.voltage_v == 1.35

    def test_ground_net(self):
        d = Design()
        d.add_ground_net("GND")
        n = d.net_by_name("GND")
        assert n.kind == "ground"

    def test_bus_net_carries_group_and_index(self):
        d = Design()
        d.add_bus_net("DDR3_A0", bus_group="DDR3_ADDR", bit_index=0,
                      impedance_ohms=55)
        n = d.net_by_name("DDR3_A0")
        assert n.kind == "bus"
        assert n.bus_group == "DDR3_ADDR"
        assert n.bit_index == 0
        assert n.impedance_ohms == 55
        # length_match_group defaults to bus_group
        assert n.length_match_group == "DDR3_ADDR"

    def test_diff_pair_creates_both_legs_with_cross_refs(self):
        d = Design()
        p, n = d.add_diff_pair("CK_P", "CK_N", impedance_ohms=100)
        assert d.net_by_name("CK_P").diff_pair == "CK_N"
        assert d.net_by_name("CK_N").diff_pair == "CK_P"
        assert d.net_by_name("CK_P").impedance_ohms == 100
        assert d.net_by_name("CK_N").impedance_ohms == 100

    def test_duplicate_net_name_raises(self):
        d = Design()
        d.add_signal_net("FOO")
        with pytest.raises(ValueError, match="duplicate net name"):
            d.add_signal_net("FOO")


# ── connections (explicit Pin passing) ───────────────────────────────────

class TestConnect:
    def test_connect_via_pin_object(self):
        d = Design()
        mpu = d.add_chip(ref="U_MPU", pins=[("K10", "DDR_A0")])
        ddr = d.add_chip(ref="U_DDR3", pins=[("P3", "A0")])
        d.add_bus_net("DDR3_A0", bus_group="DDR3_ADDR", bit_index=0) \
         .connect(mpu.pin("DDR_A0")).connect(ddr.pin("A0"))
        net = d.net_by_name("DDR3_A0")
        assert ("U_MPU", "K10") in net.pins
        assert ("U_DDR3", "P3") in net.pins

    def test_same_pin_name_different_chips_unambiguous(self):
        """Two chips both have 'PD0' — no SKiDL-style regex collision."""
        d = Design()
        h562 = d.add_chip(ref="U1", pins=[("J4", "PD0")])
        wle  = d.add_chip(ref="U_WLE", pins=[("B3", "PD0")])
        d.add_signal_net("UART_BRIDGE") \
         .connect(h562.pin("PD0")).connect(wle.pin("PD0"))
        net = d.net_by_name("UART_BRIDGE")
        assert set(net.pins) == {("U1", "J4"), ("U_WLE", "B3")}

    def test_connect_rejects_string_args(self):
        """Old SKiDL-style string passing must fail loudly."""
        d = Design()
        d.add_chip(ref="U1", pins=[("J4", "PA0")])
        with pytest.raises(TypeError, match="Pin objects"):
            d.connect("net", "U1", "J4")

    def test_connect_pin_updates_both_sides(self):
        """A connection writes both Net.pins and Pin.net so navigation
        works either direction."""
        d = Design()
        c = d.add_chip(ref="U1", pins=[("J4", "PA0")])
        d.add_signal_net("FOO").connect(c.pin("PA0"))
        assert c.pin("PA0").net == "FOO"
        assert ("U1", "J4") in d.net_by_name("FOO").pins

    def test_connect_idempotent(self):
        d = Design()
        c = d.add_chip(ref="U1", pins=[("J4", "PA0")])
        h = d.add_signal_net("FOO")
        h.connect(c.pin("PA0"))
        h.connect(c.pin("PA0"))  # second call is no-op
        assert d.net_by_name("FOO").pins == [("U1", "J4")]


# ── navigable hierarchy: design.board(tag).chip(ref).pin(name) ──────────

class TestBoardView:
    def test_board_chip_pin_chain(self):
        d = Design()
        d.add_chip(ref="U_MPU", board_tag="companion_compute",
                   pins=[("K10", "DDR_A0")])
        mpu = d.board("companion_compute").chip("U_MPU")
        assert mpu.pin("DDR_A0").num == "K10"

    def test_cross_board_lookup_raises(self):
        d = Design()
        d.add_chip(ref="U1", board_tag="flight_board")
        with pytest.raises(KeyError, match="not 'companion_compute'"):
            d.board("companion_compute").chip("U1")

    def test_board_chips_filter(self):
        d = Design()
        d.add_chip(ref="U_MPU", board_tag="companion_compute")
        d.add_chip(ref="U_DDR3", board_tag="companion_compute")
        d.add_chip(ref="U1", board_tag="flight_board")
        comp = d.board("companion_compute")
        refs = {c.ref for c in comp.chips}
        assert refs == {"U_MPU", "U_DDR3"}


# ── validators ───────────────────────────────────────────────────────────

class TestValidators:
    def test_forbidden_fab_country_detected(self):
        d = Design()
        d.add_chip(ref="U_OK",  manf_pn="STM32MP255", fab_country="FR/IT")
        d.add_chip(ref="U_BAD", manf_pn="W25Q01JV",   fab_country="TW")
        issues = [i for i in d.validate() if i.rule == "forbidden_fab"]
        assert len(issues) == 1
        assert issues[0].refs == ["U_BAD"]
        assert issues[0].severity == "error"

    def test_fab_country_with_paren_location_parses(self):
        """fab_country='USA (Micron Lehi UT)' parses to {'USA'}."""
        d = Design()
        d.add_chip(ref="U_OK", fab_country="USA (Micron Lehi UT)")
        # No forbidden_fab issue should be produced
        assert not [i for i in d.validate() if i.rule == "forbidden_fab"]

    def test_duplicate_ref_detected(self):
        # add_chip already raises on duplicate; here we test the
        # validator catches it if the duplicate slipped in some other way.
        d = Design()
        c = Chip(ref="U1")
        d.chips.append(c)
        d.chips.append(Chip(ref="U1"))
        issues = [i for i in d.validate() if i.rule == "duplicate_ref"]
        assert len(issues) == 1

    def test_datasheet_missing_warns(self):
        d = Design()
        d.add_chip(ref="U_BIG", manf_pn="X",
                   pins=[("1",), ("2",), ("3",), ("4",), ("5",)])
        issues = [i for i in d.validate() if i.rule == "missing_datasheet"]
        assert len(issues) == 1
        assert issues[0].severity == "warning"

    def test_diff_pair_symmetric_passes(self):
        d = Design()
        d.add_diff_pair("CK_P", "CK_N")
        issues = [i for i in d.validate()
                  if i.rule.startswith("diff_")]
        assert issues == []

    def test_diff_pair_missing_partner_caught(self):
        d = Design()
        d.nets.append(Net(name="ORPHAN_P", kind="diff",
                          diff_pair="ORPHAN_N"))
        # No ORPHAN_N created
        issues = [i for i in d.validate()
                  if i.rule == "diff_partner_missing"]
        assert len(issues) == 1

    def test_substitute_malformed_caught(self):
        d = Design()
        d.add_chip(ref="U_BAD", manf_pn="X",
                   substitutes=["not a tuple"])
        issues = [i for i in d.validate()
                  if i.rule == "substitute_malformed"]
        assert len(issues) == 1


# ── serialization round-trip ─────────────────────────────────────────────

class TestApplyDefaultUnderfill:
    def _fp(self):
        from smash import Footprint, Pad
        return Footprint(name="BGA64C50P8X8", pads=[Pad(num="A1", position_mm=(0, 0),
                                                       size_mm=(0.3, 0.3))],
                         size_mm=(5, 5), height_mm=1.0)

    def test_tags_every_chip_with_footprint(self):
        d = Design()
        d.add_chip(ref="U1", footprint=self._fp())
        d.add_chip(ref="U2", footprint=self._fp())
        n = d.apply_default_underfill()
        assert n == 2
        assert all(c.underfill == "Loctite Eccobond UF1173" for c in d.chips)

    def test_preserves_existing_assignments(self):
        d = Design()
        d.add_chip(ref="U1", footprint=self._fp())
        d.add_chip(ref="U2", footprint=self._fp(), underfill="Stycast 2651MM")
        n = d.apply_default_underfill()
        assert n == 1                                     # only U1 was untagged
        assert d.chip_by_ref("U2").underfill == "Stycast 2651MM"

    def test_skips_chips_without_footprint(self):
        d = Design()
        d.add_chip(ref="U_NOFP")                          # no footprint
        d.add_chip(ref="U_FP", footprint=self._fp())
        n = d.apply_default_underfill()
        assert n == 1
        assert d.chip_by_ref("U_NOFP").underfill is None


class TestSerialization:
    def test_json_roundtrip_preserves_typed_nets(self, tmp_path):
        d = Design()
        mpu = d.add_chip(ref="U_MPU", manf_pn="STM32MP255FAK3",
                         board_tag="companion_compute",
                         pins=[("AB1", "VDD"), ("K10", "DDR_A0")],
                         package="TFBGA361", size_mm=(10.0, 10.0),
                         currency="EUR", price_1pc=24.0, weight_g=0.180,
                         standards=["AEC-Q100"],
                         dielectric=None,
                         density_g_cm3=2.5)
        ddr = d.add_chip(ref="U_DDR3", manf_pn="AS4C512M16D3LC",
                         pins=[("A1", "VDD"), ("P3", "A0")])
        d.add_power_net("COMP_1V35", voltage_v=1.35) \
         .connect(mpu.pin("VDD")).connect(ddr.pin("VDD"))
        d.add_bus_net("DDR3_A0", bus_group="DDR3_ADDR", bit_index=0) \
         .connect(mpu.pin("DDR_A0")).connect(ddr.pin("A0"))
        p, n = d.add_diff_pair("CK_P", "CK_N", impedance_ohms=100)

        out = tmp_path / "design.json"
        d.dump_json(out)
        d2 = Design.load_json(out)

        assert len(d2.chips) == 2
        assert len(d2.nets) == 4
        # Tuples survive
        assert d2.chip_by_ref("U_MPU").size_mm == (10.0, 10.0)
        # Net kinds survive
        assert d2.net_by_name("COMP_1V35").kind == "power"
        assert d2.net_by_name("COMP_1V35").voltage_v == 1.35
        # Bus metadata survives
        a0 = d2.net_by_name("DDR3_A0")
        assert a0.bus_group == "DDR3_ADDR" and a0.bit_index == 0
        # Diff-pair cross-refs survive
        assert d2.net_by_name("CK_P").diff_pair == "CK_N"
        assert d2.net_by_name("CK_N").diff_pair == "CK_P"
