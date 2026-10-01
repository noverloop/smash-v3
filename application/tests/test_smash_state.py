"""Unit tests for smash.smash_state — Board, SmashState, configuration
chains, cost / weight rollups."""

import pytest

from smash import Design, SmashState, Board, Layer, Dielectric


# ── Core boards + add_* chains ───────────────────────────────────────────

class TestCoreAndAddChain:
    def test_new_pre_declares_core_boards(self):
        s = SmashState.new()
        for name in ("power_board", "wakeup_board", "flight_board",
                     "activation_interface", "nfc_antenna_flex",
                     "nose_cap"):
            assert name in s.boards

    def test_add_companion_computer_brings_two_tiles(self):
        s = SmashState.new().add_companion_computer()
        assert "companion_compute" in s.boards
        assert "companion_io" in s.boards

    def test_chaining_returns_self(self):
        s = (SmashState.new()
             .add_companion_computer()
             .add_radar()
             .add_camera())
        assert "companion_compute" in s.boards
        assert "radar_module" in s.boards
        assert "camera_module" in s.boards


# ── DNP feature flags ────────────────────────────────────────────────────

class TestFeatureFlags:
    def test_companion_io_defaults_dnp_for_wifi_and_rf44(self):
        s = SmashState.new().add_companion_computer()
        io = s.boards["companion_io"]
        assert io.features["wifi"] is False
        assert io.features["rf44"] is False

    def test_add_wifi_flips_flag(self):
        s = SmashState.new().add_companion_computer().add_wifi()
        assert s.boards["companion_io"].features["wifi"] is True

    def test_add_last_mile_telemetry_flips_flag(self):
        s = SmashState.new().add_companion_computer() \
                            .add_last_mile_telemetry()
        assert s.boards["companion_io"].features["rf44"] is True

    def test_add_wifi_without_companion_raises(self):
        with pytest.raises(RuntimeError,
                           match="requires companion_io"):
            SmashState.new().add_wifi()

    def test_add_last_mile_telemetry_without_companion_raises(self):
        with pytest.raises(RuntimeError,
                           match="requires companion_io"):
            SmashState.new().add_last_mile_telemetry()

    def test_add_all_enables_every_flag(self):
        s = SmashState.new().add_all()
        io = s.boards["companion_io"]
        assert io.features == {"wifi": True, "rf44": True}


# ── snake-chain ordering ─────────────────────────────────────────────────

class TestSnakeChain:
    def test_set_snake_chain_assigns_index(self):
        s = SmashState.new()
        s.set_snake_chain(["power_board", "wakeup_board", "flight_board"])
        assert s.boards["power_board"].snake_index == 0
        assert s.boards["wakeup_board"].snake_index == 1
        assert s.boards["flight_board"].snake_index == 2

    def test_set_snake_chain_marks_others_standalone(self):
        s = SmashState.new()
        s.set_snake_chain(["power_board", "wakeup_board"])
        assert s.boards["nfc_antenna_flex"].standalone is True
        assert s.boards["nfc_antenna_flex"].snake_index is None


# ── cost / weight rollups ────────────────────────────────────────────────

class TestRollups:
    def _build(self):
        d = Design()
        d.add_chip(ref="U_MPU", manf_pn="STM32MP255FAK3",
                   board_tag="companion_compute",
                   currency="EUR", price_1pc=24.0, price_20kpc=13.5,
                   weight_g=0.180)
        d.add_chip(ref="U_DDR3", manf_pn="AS4C512M16D3LC",
                   board_tag="companion_compute",
                   currency="EUR", price_1pc=10.50, price_20kpc=5.50,
                   weight_g=0.075)
        d.add_chip(ref="U_NAND_CMP", manf_pn="MT29F8G08",
                   board_tag="companion_io",
                   currency="EUR", price_1pc=8.50, price_20kpc=6.50,
                   weight_g=0.100)
        # WiFi is feature-gated — created with dnp=True since the
        # SmashState below has WiFi disabled by default.
        d.add_chip(ref="U_WIFI", manf_pn="LBEE5KL1YN",
                   board_tag="companion_io", feature="wifi", dnp=True,
                   currency="EUR", price_1pc=8.48, price_20kpc=5.61,
                   weight_g=0.058)
        smash = SmashState.new().add_companion_computer()
        return smash, d

    def test_board_cost_returns_currency_dict(self):
        smash, d = self._build()
        # Default mode: per-currency dict
        assert smash.boards["companion_compute"].cost_1pc(d) == {"EUR": 34.5}
        # WiFi is DNP by default → only U_NAND_CMP counts
        assert smash.boards["companion_io"].cost_1pc(d) == {"EUR": 8.50}

    def test_total_cost_returns_currency_dict(self):
        smash, d = self._build()
        # 24 + 10.5 + 8.5 = 43.0 EUR (WiFi DNP excluded)
        assert smash.cost_1pc(d) == {"EUR": 43.0}

    def test_total_cost_with_target_converts(self):
        smash, d = self._build()
        # Convert EUR→USD at 1.09. fx_rates maps origin → target.
        total_usd = smash.cost_1pc(d, target="USD",
                                    fx_rates={"EUR": 1.09})
        assert total_usd == pytest.approx(43.0 * 1.09)

    def test_mixed_currency_chips_round_to_target(self):
        # Some chips priced in USD, some in EUR — common when ADI/TI
        # parts coexist with ST parts. The rollup converts each leg.
        d = Design()
        d.add_chip(ref="U_TI", manf_pn="LMR10510",
                   board_tag="radar_module",
                   currency="USD", price_1pc=2.00, price_20kpc=1.05)
        d.add_chip(ref="U_ST", manf_pn="LDL112PV18R",
                   board_tag="radar_module",
                   currency="EUR", price_1pc=0.50, price_20kpc=0.35)
        smash = SmashState.new().add_radar()
        # No target → both currencies preserved
        assert smash.boards["radar_module"].cost_1pc(d) == \
               {"USD": 2.00, "EUR": 0.50}
        # Target=EUR with fx_rates → single float
        eur_total = smash.boards["radar_module"].cost_1pc(
            d, target="EUR", fx_rates={"USD": 0.92})
        assert eur_total == pytest.approx(2.00 * 0.92 + 0.50)

    def test_missing_currency_raises(self):
        d = Design()
        d.add_chip(ref="U_BAD", manf_pn="X",
                   board_tag="flight_board",
                   price_1pc=5.0)            # forgot currency tag
        smash = SmashState.new()
        with pytest.raises(ValueError, match="currency is unset"):
            smash.boards["flight_board"].cost_1pc(d)

    def test_missing_fx_rate_raises(self):
        smash, d = self._build()
        with pytest.raises(KeyError, match="missing FX rate"):
            smash.cost_1pc(d, target="USD", fx_rates={})

    def test_enabling_wifi_changes_total(self):
        smash, d = self._build()
        before = smash.cost_1pc(d)["EUR"]            # WiFi DNP
        smash.add_wifi()
        d.chip_by_ref("U_WIFI").dnp = False           # apply feature → chip
        after = smash.cost_1pc(d)["EUR"]
        assert after - before == pytest.approx(8.48)

    def test_populated_only_false_includes_dnp(self):
        smash, d = self._build()
        with_dnp    = smash.cost_1pc(d, populated_only=False)["EUR"]
        without_dnp = smash.cost_1pc(d, populated_only=True)["EUR"]
        assert with_dnp - without_dnp == pytest.approx(8.48)

    def test_weight_rollup(self):
        smash, d = self._build()
        assert smash.weight_g(d) == pytest.approx(0.355)

    def test_cost_summary_per_board(self):
        smash, d = self._build()
        summary = smash.cost_summary(d)
        assert "per_board" in summary
        assert "total_1pc" in summary
        assert "total_weight_g" in summary
        comp = summary["per_board"]["companion_compute"]
        assert comp["n_chips"] == 2
        assert comp["1pc"] == {"EUR": 34.5}

    def test_batteries_roll_up_alongside_chips(self):
        d = Design()
        d.add_chip(ref="U_EFUSE", board_tag="power_board",
                   currency="USD", price_1pc=1.85,
                   weight_g=0.012)
        for i in (1, 2, 3):
            d.add_battery(
                ref=f"BT{i}", manf_pn="TLM-1520HPM/S",
                board_tag="power_board",
                currency="EUR", price_1pc=45.0,
                weight_g=9.0,
                pack_count=3, pack_config="3p",
            )
        smash = SmashState.new()   # power_board exists by default
        # Both currencies appear in the per-board total
        pwr = smash.boards["power_board"].cost_1pc(d)
        assert pwr == {"EUR": 3 * 45.0, "USD": 1.85}
        # Weight sums chip + 3 batteries
        assert smash.boards["power_board"].weight_g(d) == pytest.approx(
            0.012 + 3 * 9.0)

    def test_empty_board_costs_empty_dict(self):
        smash, d = self._build()
        # power_board has no chips on it in this fixture
        assert smash.boards["power_board"].cost_1pc(d) == {}


# ── stackup (Layer + Dielectric on Board) ───────────────────────────────

class TestStackup:
    def _build_14L_with_embedded_caps(self):
        """Mini stackup matching companion_compute's actual shape:
        F.Cu ─ thin core ─ In1 (GND) ─ HK04 ─ In2 (VDD_DDR) ─ ...
        ─ In11 (GND) ─ HK04 ─ In12 (VDD_DDR) ─ ... ─ B.Cu

        For the test we only model the relevant layers — the
        validator and embedded_cap_pairs() should still find them.
        """
        b = Board(name="companion_compute", kind="rigid")
        # Outer ECM-pair (upper)
        fr4_thin = Dielectric(material="FR4", thickness_um=100,
                              epsilon_r=4.3, loss_tangent=0.02)
        hk04 = Dielectric(material="Oak-Mitsui HK04", thickness_um=14,
                          epsilon_r=4.0)
        b.stackup = [
            Layer(name="F.Cu",  index=0, role="signal",
                  thickness_um=17.5, dielectric_below=fr4_thin),
            Layer(name="In1",   index=1, role="embedded_cap_gnd",
                  thickness_um=35.0, rail="GND",
                  paired_with="In2", dielectric_below=hk04),
            Layer(name="In2",   index=2, role="embedded_cap_power",
                  thickness_um=35.0, rail="COMP_1V35",
                  paired_with="In1", dielectric_below=fr4_thin),
            # ... skip middle layers in this test ...
            Layer(name="In11",  index=11, role="embedded_cap_gnd",
                  thickness_um=35.0, rail="GND",
                  paired_with="In12", dielectric_below=hk04),
            Layer(name="In12",  index=12, role="embedded_cap_power",
                  thickness_um=35.0, rail="COMP_1V35",
                  paired_with="In11", dielectric_below=fr4_thin),
            Layer(name="B.Cu",  index=13, role="signal",
                  thickness_um=17.5),
        ]
        return b

    def test_layer_lookup_by_name(self):
        b = self._build_14L_with_embedded_caps()
        assert b.layer("In1").role == "embedded_cap_gnd"
        assert b.layer("In2").rail == "COMP_1V35"

    def test_layer_lookup_missing_raises(self):
        b = self._build_14L_with_embedded_caps()
        with pytest.raises(KeyError):
            b.layer("In99")

    def test_embedded_cap_pairs_finds_both(self):
        b = self._build_14L_with_embedded_caps()
        pairs = b.embedded_cap_pairs()
        assert len(pairs) == 2
        pair_names = {(p.name, g.name) for p, g, _ in pairs}
        assert pair_names == {("In2", "In1"), ("In12", "In11")}

    def test_planes_for_net(self):
        b = self._build_14L_with_embedded_caps()
        # COMP_1V35 is on In2 + In12 → two power planes
        comp = b.planes_for_net("COMP_1V35")
        assert {l.name for l in comp} == {"In2", "In12"}
        # GND is on In1 + In11
        gnd = b.planes_for_net("GND")
        assert {l.name for l in gnd} == {"In1", "In11"}

    def test_note_field_on_board_layer_dielectric(self):
        b = self._build_14L_with_embedded_caps()
        b.note = "Hybrid Rogers/FR4 stackup; see fab_notes.txt"
        b.layer("In2").note = "Carries COMP_1V35 plane absorption"
        b.layer("In1").dielectric_below.note = (
            "Oak-Mitsui HK04: pre-qualified by Smash 2026-04 lot")
        assert "Rogers" in b.note
        assert "COMP_1V35" in b.layer("In2").note
        assert "pre-qualified" in b.layer("In1").dielectric_below.note

    def test_stackup_serializes_to_dict_and_back(self, tmp_path):
        s = SmashState.new()
        s.boards["companion_compute"] = self._build_14L_with_embedded_caps()
        out = tmp_path / "smash.json"
        s.dump_json(out)
        s2 = SmashState.load_json(out)
        cc = s2.boards["companion_compute"]
        assert len(cc.stackup) == 6
        assert cc.layer("In2").rail == "COMP_1V35"
        # Dielectric survives too
        di = cc.layer("In1").dielectric_below
        assert di.material == "Oak-Mitsui HK04"
        assert di.epsilon_r == 4.0
        # embedded_cap_pairs() still works after round-trip
        assert len(cc.embedded_cap_pairs()) == 2


# ── netlist capture + JSON ───────────────────────────────────────────────

class TestNetlistCapture:
    def test_capture_netlist_projects_design(self):
        d = Design()
        mpu = d.add_chip(ref="U_MPU", manf_pn="STM32MP255",
                         pins=[("AB1", "VDD"), ("AB2", "GND")])
        d.add_ground_net("GND").connect(mpu.pin("GND"))

        smash = SmashState.new()
        smash.capture_netlist(d)
        assert smash.netlist is not None
        assert len(smash.netlist.parts) == 1
        # Netlist parts + nets are now plain dicts (NetlistPart /
        # NetlistNet classes removed during the smash.state migration).
        assert smash.netlist.parts[0]["manf_pn"] == "STM32MP255"
        assert any(n["name"] == "GND" for n in smash.netlist.nets)

    def test_smash_state_json_roundtrip(self, tmp_path):
        s = SmashState.new().add_companion_computer().add_wifi()
        out = tmp_path / "smash.json"
        s.dump_json(out)
        s2 = SmashState.load_json(out)
        assert "companion_io" in s2.boards
        assert s2.boards["companion_io"].features["wifi"] is True
