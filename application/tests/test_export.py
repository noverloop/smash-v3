"""Tests for the smash.export writers + smash.validators.specctra.

Each writer is exercised against a small Design that mirrors the shape
of the real Smash netlist (multi-board, multi-chip, multi-net) without
depending on the full catalog. A few writers are also cross-checked
against the real catalog via factory helpers.
"""

from __future__ import annotations

import csv
import pathlib

import pytest

from smash import Design
from smash.state import Footprint, Pad, Pin
from smash.export import (
    write_bom, write_flat_netlist, write_edif,
    write_pads_netlist, write_protel_netlist,
    write_allegro_netlist, write_footprint_inventory, load_allegro_fp_map,
    write_specctra_dsn,
)
from smash.validators.specctra import validate_specctra_dsn


@pytest.fixture
def tiny_design():
    """A two-chip + one-battery design across two boards with three nets.
    Big enough to exercise every writer; small enough to assert specific
    output.
    """
    d = Design()
    fp_a = Footprint(name="SOT-23-5", pads=[
        Pad(num="1", position_mm=(0, 0), size_mm=(0.6, 1.2)),
        Pad(num="2", position_mm=(0, 1), size_mm=(0.6, 1.2)),
        Pad(num="3", position_mm=(0, 2), size_mm=(0.6, 1.2)),
        Pad(num="4", position_mm=(1.9, 0), size_mm=(0.6, 1.2)),
        Pad(num="5", position_mm=(1.9, 2), size_mm=(0.6, 1.2)),
    ], size_mm=(2.9, 1.6), package_class="SOT-23-5")
    fp_b = Footprint(name="C_0402_1005Metric", pads=[
        Pad(num="1", position_mm=(0, 0), size_mm=(0.5, 0.4)),
        Pad(num="2", position_mm=(1, 0), size_mm=(0.5, 0.4)),
    ], size_mm=(1.0, 0.5), package_class="0402")

    u1 = d.add_chip(
        ref="U1", manf="TI", manf_pn="SN74LVC1G08DCKRG4",
        value="AND", description="2-in AND",
        footprint=fp_a, board_tag="flight_board",
        fab_country="USA", currency="USD", price_1pc=0.10,
        pins=[Pin(num="1", name="A", type="input"),
              Pin(num="2", name="B", type="input"),
              Pin(num="3", name="GND", type="ground"),
              Pin(num="4", name="Y", type="output"),
              Pin(num="5", name="VCC", type="power")],
    )
    c1 = d.add_chip(
        ref="C1", manf="KEMET", value="100nF",
        footprint=fp_b, board_tag="flight_board",
        currency="USD", price_1pc=0.01,
        pins=[Pin(num="1"), Pin(num="2")],
    )
    bt1 = d.add_battery(
        ref="BT1", manf="Tadiran", manf_pn="TLM-1520HPM/S",
        chemistry="Li-MnO2", capacity_mah=125.0,
        board_tag="power_board",
        fab_country="IL", currency="USD", price_1pc=12.50,
    )

    gnd = d.add_ground_net("GND")
    gnd.connect(u1.pin("GND")).connect(c1.pin("2")).connect(bt1.pin("-"))
    vcc = d.add_power_net("VCC", voltage_v=3.3)
    vcc.connect(u1.pin("VCC")).connect(c1.pin("1"))
    sig = d.add_signal_net("CONFIRM")
    sig.connect(u1.pin("Y"))
    return d


# ── BOM ──────────────────────────────────────────────────────────────────

class TestWriteBom:
    def test_writes_header_and_rows(self, tiny_design, tmp_path):
        out = tmp_path / "bom.csv"
        result = write_bom(tiny_design, out)
        assert result["n_parts"] == 3
        # USD = 0.10 + 0.01 + 12.50 = 12.61
        assert abs(result["total_usd"] - 12.61) < 1e-6
        text = out.read_text()
        assert "Board,Ref,Value,Footprint" in text
        assert "U1" in text and "C1" in text and "BT1" in text
        assert "SN74LVC1G08DCKRG4" in text
        assert "$12.61" in text

    def test_dnp_marker(self, tiny_design, tmp_path):
        out = tmp_path / "bom.csv"
        # Mark the 0402 cap as ECM-absorbed
        result = write_bom(tiny_design, out, dnp_refs={"C1"})
        text = out.read_text()
        assert "[DNP/ECM]" in text
        assert result["n_dnp"] == 1
        # Total should drop by the C1 price
        assert abs(result["total_usd"] - (12.61 - 0.01)) < 1e-6


# ── flat netlist ────────────────────────────────────────────────────────

def test_write_flat_netlist(tiny_design, tmp_path):
    out = tmp_path / "flat.tab"
    result = write_flat_netlist(tiny_design, out)
    text = out.read_text()
    assert text.startswith("NET\tREF\tPIN\n")
    assert "GND\tU1\t3" in text
    assert "VCC\tU1\t5" in text
    # GND has 3 pin-connections; VCC has 2; CONFIRM has 1 -> total 6
    assert result["n_connections"] == 6


# ── PADS ─────────────────────────────────────────────────────────────────

def test_write_pads_netlist(tiny_design, tmp_path):
    out = tmp_path / "pads.asc"
    result = write_pads_netlist(tiny_design, out)
    text = out.read_text()
    assert "!PADS-POWERPCB-V9.0-METRIC!" in text
    assert "*PART*" in text and "*NET*" in text and "*END*" in text
    assert "U1    SN74LVC1G08DCKRG4@SOT-23-5" in text
    assert "*SIGNAL* GND" in text
    assert result["n_parts"] == 3
    assert result["n_nets"] == 3


# ── Protel ───────────────────────────────────────────────────────────────

def test_write_protel_netlist(tiny_design, tmp_path):
    out = tmp_path / "protel.NET"
    write_protel_netlist(tiny_design, out)
    text = out.read_text()
    assert "[" in text and "]" in text
    assert "U1\nSOT-23-5\nSN74LVC1G08DCKRG4\n]" in text
    assert "(\nGND\n" in text
    assert "U1-3" in text     # GND pin on the AND gate


# ── EDIF ─────────────────────────────────────────────────────────────────

class TestWriteEdif:
    def test_basic_structure(self, tiny_design, tmp_path):
        out = tmp_path / "design.edf"
        result = write_edif(tiny_design, out)
        text = out.read_text()
        assert text.startswith("(edif ")
        assert "(edifVersion 2 0 0)" in text
        assert "(library cell_lib" in text
        assert "(library design_lib" in text
        # Top-level design statement must be present (Xpedition / OrCAD
        # otherwise import as empty).
        assert "(design " in text
        assert result["n_instances"] == 3

    def test_cell_consolidation(self, tmp_path):
        """Two identical chips collapse to one EDIF cell."""
        d = Design()
        fp = Footprint(name="SOIC-8")
        pins = [Pin(num=str(i), name=f"P{i}") for i in range(1, 9)]
        d.add_chip(ref="U1", manf_pn="X", name="X", footprint=fp,
                   pins=[Pin(num=p.num, name=p.name) for p in pins])
        d.add_chip(ref="U2", manf_pn="X", name="X", footprint=fp,
                   pins=[Pin(num=p.num, name=p.name) for p in pins])
        result = write_edif(d, tmp_path / "x.edf")
        # Same name + same footprint + same pin signature → one cell
        assert result["n_cells"] == 1
        assert result["n_instances"] == 2


# ── Allegro ──────────────────────────────────────────────────────────────

class TestWriteAllegro:
    def test_telesis_format(self, tiny_design, tmp_path):
        out = tmp_path / "allegro.txt"
        result = write_allegro_netlist(tiny_design, out)
        text = out.read_text()
        assert "$PACKAGES" in text and "$NETS" in text and "$END" in text
        # Telesis $PACKAGES line shape:
        # <padstack> ! <device> ! '<class>' ; REFDES
        assert " ! " in text
        assert "; U1" in text
        assert result["n_parts"] == 3
        assert result["n_nets"] == 3

    def test_footprint_mapping(self, tiny_design, tmp_path):
        out = tmp_path / "allegro.txt"
        # Map SOT-23-5 → an Allegro-named padstack
        write_allegro_netlist(
            tiny_design, out,
            footprint_map={"SOT-23-5": "PADSTACK_SOT235_FOO"},
        )
        text = out.read_text()
        assert "PADSTACK_SOT235_FOO" in text

    def test_net_name_quoting(self, tmp_path):
        d = Design()
        # Net name with leading + — must be quoted per SPMHNI-113 rule
        n = d.add_signal_net("+3.3V")
        d.add_chip(ref="U1", footprint=Footprint(name="X"),
                   pins=[Pin(num="1", name="VCC")])
        n.connect(d.chip_by_ref("U1").pin("1"))
        out = tmp_path / "allegro.txt"
        write_allegro_netlist(d, out)
        text = out.read_text()
        assert "'+3.3V'" in text


# ── footprint inventory ─────────────────────────────────────────────────

class TestFootprintInventory:
    def test_emits_csv_and_persists_edits(self, tiny_design, tmp_path):
        out = tmp_path / "parts_to_fetch.csv"
        result = write_footprint_inventory(tiny_design, out)
        # 3 entries: SOT-23-5, C_0402_1005Metric, UNDEFINED (battery has no fp)
        assert result["n_footprints"] == 3

        # Manually fill in Allegro_Equivalent for SOT-23-5
        rows = list(csv.DictReader(open(out)))
        for r in rows:
            if r["KiCad_Footprint"] == "SOT-23-5":
                r["Allegro_Equivalent"] = "PADSTACK_SOT235"
                r["Status"] = "Downloaded"
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

        # Re-run the writer — must preserve the edit
        write_footprint_inventory(tiny_design, out)
        mapping = load_allegro_fp_map(out)
        assert mapping == {"SOT-23-5": "PADSTACK_SOT235"}

    def test_load_allegro_fp_map_missing_file(self, tmp_path):
        # Missing file → empty mapping, no exception
        mapping = load_allegro_fp_map(tmp_path / "nope.csv")
        assert mapping == {}


# ── Specctra DSN writer ────────────────────────────────────────────────

class TestWriteSpecctra:
    def test_emits_valid_dsn(self, tiny_design, tmp_path):
        out = tmp_path / "system.dsn"
        result = write_specctra_dsn(tiny_design, out)
        assert result["n_parts"] == 3
        text = out.read_text()
        # Required top-level sections
        for sect in ["structure", "library", "placement", "network", "wiring"]:
            assert f"({sect}" in text or f"({sect})" in text, f"missing {sect}"
        # Pin-token form: <REF>-<PIN>
        assert "U1-3" in text
        # The DSN must pass our own structural validator
        issues = validate_specctra_dsn(out)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], f"DSN failed validator: {errors}"


# ── Specctra DSN validator ─────────────────────────────────────────────

class TestSpecctraStructural:
    def test_balanced_parens_passes(self):
        text = "(pcb test\n  (structure)\n  (library)\n  (placement)\n  (network)\n  (wiring)\n)"
        issues = validate_specctra_dsn(text)
        # Structural rules should NOT fire — sections are present and
        # parens balance. The full-schema parser may flag missing
        # required fields beyond that; this test only asserts on the
        # structural layer.
        structural_rules = {"balanced_parens", "required_section",
                            "pin_token_form", "padstack_ref"}
        errors = [i for i in issues
                  if i.severity == "error" and i.rule in structural_rules]
        assert errors == []

    def test_unbalanced_parens_fails(self):
        # Missing closing paren
        text = "(pcb test (structure (library (placement (network (wiring"
        issues = validate_specctra_dsn(text)
        rules = {i.rule for i in issues if i.severity == "error"}
        assert "balanced_parens" in rules

    def test_missing_section_fails(self):
        text = "(pcb test\n  (structure)\n  (library)\n  (placement)\n)"
        # missing network + wiring
        issues = validate_specctra_dsn(text)
        rules = {(i.severity, i.rule, i.message) for i in issues}
        msgs = " ".join(m for *_, m in rules)
        assert "network" in msgs and "wiring" in msgs

    def test_padstack_ref_check(self):
        # Image references padstack PS_BAD that's never defined
        text = (
            "(pcb test\n"
            "  (structure)\n"
            "  (library\n"
            "    (image FOO (pin PS_BAD 1 0 0))\n"
            "  )\n"
            "  (placement)\n"
            "  (network)\n"
            "  (wiring)\n"
            ")"
        )
        issues = validate_specctra_dsn(text)
        rules = {i.rule for i in issues if i.severity == "error"}
        assert "padstack_ref" in rules


class TestSpecctraFullSchema:
    """Ports of tscircuit/specctra-dsn-json checks — full parse + typed
    dataclass output, catching field-level issues the regex validator
    misses."""

    def test_parse_full_dsn_from_writer(self, tiny_design, tmp_path):
        """The DSN our writer produces must round-trip through the
        full schema parser without errors."""
        from smash.validators.specctra import parse_dsn
        out = tmp_path / "system.dsn"
        write_specctra_dsn(tiny_design, out)
        design = parse_dsn(out)
        assert design.pcb_id == "smash"
        assert design.resolution.unit == "um"
        assert design.resolution.value == 10
        # Tiny design has 3 parts + their nets
        assert len(design.network.nets) >= 3
        # 8 layers in the default stackup
        assert len(design.structure.layers) == 8
        # All layers signal-typed
        assert all(L.type == "signal" for L in design.structure.layers)

    def test_full_validator_passes_clean_dsn(self, tiny_design, tmp_path):
        out = tmp_path / "system.dsn"
        write_specctra_dsn(tiny_design, out)
        issues = validate_specctra_dsn(out)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], f"clean DSN failed validator: {errors}"

    def test_schema_catches_missing_parser(self):
        """A DSN that passes structural checks but lacks the parser
        section gets caught by the full-schema check."""
        from smash.validators.specctra import parse_dsn
        text = (
            "(pcb test\n"
            "  (structure (layer F.Cu (type signal)))\n"
            "  (library)\n"
            "  (placement)\n"
            "  (network)\n"
            "  (wiring)\n"
            ")"
        )
        issues = validate_specctra_dsn(text)
        schema_errors = [i for i in issues
                         if i.severity == "error" and i.rule == "schema"]
        assert schema_errors, "should flag missing parser section"
        assert "parser" in schema_errors[0].message

    def test_parse_dsn_extracts_typed_data(self, tiny_design, tmp_path):
        """The parsed object should expose typed access — layers,
        component placements, nets all addressable as Python objects."""
        from smash.validators.specctra import parse_dsn
        out = tmp_path / "system.dsn"
        write_specctra_dsn(tiny_design, out)
        d = parse_dsn(out)
        # Network nets carry pin lists like "U1-3"
        net_names = {n.name for n in d.network.nets}
        assert "GND" in net_names
        # Placement groups by footprint
        all_refs = [p.component_id for c in d.placement for p in c.places]
        assert "U1" in all_refs and "C1" in all_refs and "BT1" in all_refs


# ── KiCad schematic ──────────────────────────────────────────────────────

class TestWriteKicadSchematic:
    def test_one_flat_sheet_framed_per_board(self, tiny_design, tmp_path):
        from smash.export import write_kicad_schematic
        result = write_kicad_schematic(tiny_design, tmp_path)
        assert result["n_boards"] == 2
        assert result["n_parts"] == 3
        assert sorted(f.name for f in tmp_path.iterdir()) == [
            "smash.kicad_pro", "smash.kicad_sch", "smash.kicad_sym", "sym-lib-table"]
        root = (tmp_path / "smash.kicad_sch").read_text()
        assert "(sheet " not in root
        assert '(text "flight_board"' in root and '(text "power_board"' in root
        assert root.count("(") == root.count(")")

    def test_pcb_constructs_dropped(self, tiny_design, tmp_path):
        from smash.export import write_kicad_schematic
        lands = tiny_design.add_chip(ref="J_lands", manf="project", manf_pn="LGA_lands",
                                     board_tag="flight_board", pins=[Pin(num="1")])
        sp = tiny_design.add_chip(ref="SP_x", manf="project", board_tag="spacer_x",
                                  pins=[Pin(num="1")])
        tiny_design.connect("GND", lands.pin("1"), sp.pin("1"))
        result = write_kicad_schematic(tiny_design, tmp_path)
        sch = (tmp_path / "smash.kicad_sch").read_text()
        assert result["n_boards"] == 2 and result["n_parts"] == 3
        assert "J_lands" not in sch and "SP_x" not in sch

    def test_undeclared_decoupling_not_attached(self, tiny_design, tmp_path):
        """C1 (VCC→GND) declares no pin: drawn on the rail, not on U1."""
        from smash.export import write_kicad_schematic
        r = write_kicad_schematic(tiny_design, tmp_path)
        sch = (tmp_path / "smash.kicad_sch").read_text()
        assert "Rail decoupling - no pin declared" in sch
        assert r["warnings"] == []

    def test_declared_decoupling_hangs_off_pin(self, tiny_design, tmp_path, monkeypatch):
        """A generated symbol opens empty rows under the supply pin for its
        decoupling parts (forced here: U1 also has a SamacSys symbol)."""
        import smash.export.kicad_sch as ks
        from smash.export import write_kicad_schematic
        monkeypatch.setattr(ks, "find_symbol", lambda comp: None)
        next(c for c in tiny_design.chips if c.ref == "C1").decouples = [("U1", "VCC")]
        r = write_kicad_schematic(tiny_design, tmp_path)
        sch = (tmp_path / "smash.kicad_sch").read_text()
        assert "Rail decoupling - no pin declared" not in sch
        assert '(lib_id "smash:SN74LVC1G08DCKRG4_g' in sch     # U1 rebuilt with room
        assert r["warnings"] == []

    def test_declared_pin_off_rail_warns(self, tiny_design, tmp_path):
        from smash.export import write_kicad_schematic
        next(c for c in tiny_design.chips if c.ref == "C1").decouples = [("U1", "A")]
        r = write_kicad_schematic(tiny_design, tmp_path)
        assert len(r["warnings"]) == 1 and r["warnings"][0].startswith("C1:")
        # not hung off any pin (U1's symbol is not rebuilt with room)
        assert '(lib_id "smash:SN74LVC1G08DCKRG4_g' not in (tmp_path / "smash.kicad_sch").read_text()

    def test_samacsys_symbol_used(self, tiny_design, tmp_path):
        """A part whose SamacSys symbol has its exact pins is drawn with
        it; its decoupling then stands in a bank under it."""
        from smash.export import write_kicad_schematic
        next(c for c in tiny_design.chips if c.ref == "C1").decouples = [("U1", "VCC")]
        write_kicad_schematic(tiny_design, tmp_path)
        sch = (tmp_path / "smash.kicad_sch").read_text()
        assert '(lib_id "smash:SN74LVC1G08DCKRG4")' in sch
        assert "_g" not in sch.split('(lib_id "smash:SN74LVC1G08DCKRG4')[1][:3]

    def test_samacsys_no_connect_pin_still_wired(self, tmp_path):
        """A SamacSys pin typed no_connect (TPS61175 pin 11, "NC") that the
        design ties to a net must still join it: KiCad never connects a
        no_connect-typed pin, so it is drawn passive."""
        import xml.etree.ElementTree as ET
        import subprocess
        from smash.export import write_kicad_schematic, find_kicad_cli, KiCadCliNotFound
        from smash.parts.regulators import add_tps61175pwpr
        try:
            cli = find_kicad_cli()
        except KiCadCliNotFound:
            pytest.skip("kicad-cli not installed")
        d = Design()
        u = add_tps61175pwpr(d, ref="U_BOOST", board_tag="b")
        d.add_ground_net("GND").connect(u.pin("11")).connect(u.pin("6"))
        write_kicad_schematic(d, tmp_path)
        out = tmp_path / "net.xml"
        subprocess.run([str(cli), "sch", "export", "netlist", "--format", "kicadxml",
                        "-o", str(out), str(tmp_path / "smash.kicad_sch")],
                       check=True, capture_output=True)
        gnd = next(n for n in ET.parse(out).getroot().iter("net") if n.get("name") == "GND")
        assert {(n.get("ref"), n.get("pin")) for n in gnd.iter("node")} >= {
            ("U_BOOST1", "11"), ("U_BOOST1", "6")}

    def test_pad_groups_boxed(self, tiny_design, tmp_path):
        from smash.export import write_kicad_schematic
        write_kicad_schematic(tiny_design, tmp_path,
                              pad_groups={"power_board": [("BAT", ["BT1"])]})
        sch = (tmp_path / "smash.kicad_sch").read_text()
        assert '(text "BAT"' in sch and "(type dash)" in sch

    def test_labels_and_no_connects(self, tiny_design, tmp_path):
        from smash.export import write_kicad_schematic
        write_kicad_schematic(tiny_design, tmp_path)
        fb = (tmp_path / "smash.kicad_sch").read_text()
        # Rails are power symbols, not labels
        assert '(lib_id "smash:PWR_GND_' in fb and '(lib_id "smash:PWR_VCC_' in fb
        assert '(global_label "GND"' not in fb and '(label "VCC"' not in fb
        # CONFIRM stays on flight_board → local label
        assert '(label "CONFIRM"' in fb
        # C1 (VCC→GND) is a decoupling bank under U1: drawn vertical, wired
        assert '(lib_id "smash:C__V' in fb and "(wire " in fb
        # U1 pins A and B + BT1's spare pin are unconnected → no-connect flags
        assert fb.count("(no_connect") == 3
        assert '(property "Footprint" "footprints:SOT-23-5"' in fb
        assert fb.count("(") == fb.count(")")

    def test_deterministic(self, tiny_design, tmp_path):
        from smash.export import write_kicad_schematic
        write_kicad_schematic(tiny_design, tmp_path / "a")
        write_kicad_schematic(tiny_design, tmp_path / "b")
        for f in (tmp_path / "a").iterdir():
            assert f.read_bytes() == (tmp_path / "b" / f.name).read_bytes(), f.name

    @staticmethod
    def _board_project(design, tmp_path, refs=("U1", "C1")):
        """U1 + C1 placed on one board, written the way the generator
        does: linked .kicad_pcb, its schematic, then the portable pass."""
        from smash.export import (write_kicad_pcb, write_blank_drawing_sheet,
                                  write_board_schematic)
        from smash.export.portable_project import write_portable_project
        from smash.state import Board
        from smash.state.topology.placement import Placement
        board = Board("flight_board")
        for i, ref in enumerate(refs):
            chip = next(c for c in design.chips if c.ref == ref)
            board.chip_placements.append(Placement(
                position_mm=(4.0 * i, 0), rotation_deg=0, item=chip, face="top"))
        proj = tmp_path / "flight_board"
        pcb = proj / "flight_board.kicad_pcb"
        write_kicad_pcb(design, board, pcb, link_schematic=True)
        write_blank_drawing_sheet(pcb)
        result = write_board_schematic(design, board, proj)
        write_portable_project(pcb)
        return proj, result

    def test_board_schematic_beside_pcb(self, tiny_design, tmp_path):
        from smash.export.kicad_sch import symbol_path
        proj, result = self._board_project(tiny_design, tmp_path)
        assert result["n_parts"] == 2              # BT1 is on another board
        assert {f.name for f in proj.iterdir()} >= {
            "flight_board.kicad_pcb", "flight_board.kicad_pro",
            "flight_board.kicad_sch", "flight_board.kicad_sym", "sym-lib-table"}
        sch = (proj / "flight_board.kicad_sch").read_text()
        pcb = (proj / "flight_board.kicad_pcb").read_text()
        for ref in ("U1", "C1"):                   # footprint path = symbol uuid
            assert f'(path "{symbol_path("flight_board", ref)}")' in pcb
            assert f'(uuid "{symbol_path("flight_board", ref)[1:]}")' in sch
        # Footprint fields name the portable project's library entries.
        assert '(property "Footprint" "SmashFlightBoard:SOT-23-5"' in sch
        assert '(footprint "SmashFlightBoard:SOT-23-5"' in pcb
        # Every signal keeps its PCB name: global labels, never local
        # ones (KiCad would name those "/CONFIRM").
        assert '(global_label "CONFIRM"' in sch and '(label "' not in sch
        # The no-connect pins' pads carry KiCad's unconnected-net names.
        assert '(net "unconnected-(U1-A-Pad1)")' in pcb
        # The library footprint keeps no instance link.
        lib = (proj / "footprints/SmashFlightBoard.pretty/SOT-23-5.kicad_mod").read_text()
        assert "(path " not in lib and "(sheetfile " not in lib

    def test_references_annotated(self, tiny_design, tmp_path):
        """KiCad refuses Update PCB from Schematic unless every reference
        ends in a digit: a descriptive ref gets a `1`, in the schematic,
        on the board and in the BOM alike."""
        from smash.export import write_bom
        next(c for c in tiny_design.chips if c.ref == "U1").ref = "U_GATE"
        for net in tiny_design.nets:
            net.pins = [("U_GATE" if r == "U1" else r, p) for r, p in net.pins]
        proj, _ = self._board_project(tiny_design, tmp_path, ("U_GATE", "C1"))
        sch = (proj / "flight_board.kicad_sch").read_text()
        pcb = (proj / "flight_board.kicad_pcb").read_text()
        assert '(reference "U_GATE1")' in sch and '(reference "U_GATE")' not in sch
        assert '(property "Reference" "U_GATE1"' in pcb
        assert '(net "unconnected-(U_GATE1-A-Pad1)")' in pcb
        write_bom(tiny_design, tmp_path / "bom.csv")
        assert ",U_GATE1," in (tmp_path / "bom.csv").read_text()

    def test_reference_collision_rejected(self, tiny_design, tmp_path):
        from smash.export import write_kicad_schematic
        tiny_design.add_chip(ref="U", board_tag="flight_board", pins=[Pin(num="1")])
        with pytest.raises(ValueError, match="U and U1 both become"):
            write_kicad_schematic(tiny_design, tmp_path)

    def test_wiring_hazards(self):
        """Nothing may depend on a junction (KiCad's editor deletes the ones
        it judges unneeded before Update PCB): three items at a point, or
        anything ending on a wire's middle, is rejected."""
        from smash.export.kicad_sch import _wiring_hazards
        assert _wiring_hazards([(0, 0, 5, 0), (5, 0, 10, 0)], [(5, 0)])     # 3 at a joint
        assert _wiring_hazards([(0, 0, 10, 0), (5, 0, 5, 5)], [])          # tee
        assert _wiring_hazards([(0, 0, 10, 0)], [(5, 0)])                  # pin mid-wire
        assert _wiring_hazards([(0, 0, 5, 0)], [(0, 0), (5, 0)]) == []     # pin-wire-pin

    def test_no_junctions(self, tiny_design, tmp_path):
        """Rails and decoupling banks are drawn with a power symbol on every
        pin, so the sheet needs no junction anywhere."""
        from smash.export import write_kicad_schematic
        next(c for c in tiny_design.chips if c.ref == "C1").decouples = [("U1", "VCC")]
        write_kicad_schematic(tiny_design, tmp_path)
        assert "(junction" not in (tmp_path / "smash.kicad_sch").read_text()

    def test_wires_start_before_end(self, tiny_design, tmp_path):
        """Every wire is written in canonical direction (start ≤ end)."""
        import re
        from smash.export import write_kicad_schematic
        next(c for c in tiny_design.chips if c.ref == "C1").decouples = [("U1", "VCC")]
        write_kicad_schematic(tiny_design, tmp_path)
        sch = (tmp_path / "smash.kicad_sch").read_text()
        wires = [tuple(map(float, m.groups())) for m in re.finditer(
            r"\(wire \(pts \(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)\)", sch)]
        assert wires and all((x1, y1) <= (x2, y2) for x1, y1, x2, y2 in wires)

    def test_multi_unit_footprint_linked_like_kicad(self, tiny_design, tmp_path):
        """A part split into units: the footprint lists each unit's pads
        (KiCad 10 unit metadata) and, once re-linked, points at the unit
        KiCad's own netlister associates it with."""
        import xml.etree.ElementTree as ET
        import subprocess
        from smash.export import find_kicad_cli, KiCadCliNotFound
        from smash.export.kicad_sch import relink_multi_unit_footprints
        try:
            cli = find_kicad_cli()
        except KiCadCliNotFound:
            pytest.skip("kicad-cli not installed")
        u1 = next(c for c in tiny_design.chips if c.ref == "U1")
        u1.pins = [Pin(num=str(i), name=f"P{i}") for i in range(1, 81)]
        u1.footprint = Footprint(name="BIG", pads=[
            Pad(num=str(i), position_mm=(i * 0.5, 0), size_mm=(0.3, 0.3)) for i in range(1, 81)])
        for net in tiny_design.nets:
            net.pins = [(r, p) for r, p in net.pins if r != "U1"]
        proj, _ = self._board_project(tiny_design, tmp_path)
        pcb_path = proj / "flight_board.kicad_pcb"
        assert '(unit (name "B")' in pcb_path.read_text()
        relink_multi_unit_footprints(pcb_path, proj / "flight_board.kicad_sch", cli)
        out = tmp_path / "net.xml"
        subprocess.run([str(cli), "sch", "export", "netlist", "--format", "kicadxml",
                        "-o", str(out), str(proj / "flight_board.kicad_sch")],
                       check=True, capture_output=True)
        comp = next(c for c in ET.parse(out).getroot().iter("comp") if c.get("ref") == "U1")
        first = comp.find("tstamps").text.split()[0]
        assert f'(path "/{first}")' in pcb_path.read_text()

    def test_board_protel_netlist_matches_pcb(self, tiny_design, tmp_path):
        """The Altium .NET beside a board names the same parts (refdes,
        footprint, value) and the same pads on the same nets as the
        .kicad_pcb — no-connect `unconnected-(…)` nets aside."""
        import re
        from smash.export import write_board_protel_netlist
        from smash.state import Board
        next(c for c in tiny_design.chips if c.ref == "U1").ref = "U_GATE"
        for net in tiny_design.nets:
            net.pins = [("U_GATE" if r == "U1" else r, p) for r, p in net.pins]
        proj, _ = self._board_project(tiny_design, tmp_path, ("U_GATE", "C1"))
        board = Board("flight_board")
        from smash.state.topology.placement import Placement
        for ref in ("U_GATE", "C1"):
            board.chip_placements.append(Placement(position_mm=(0, 0), rotation_deg=0,
                item=next(c for c in tiny_design.chips if c.ref == ref), face="top"))
        r = write_board_protel_netlist(tiny_design, board, proj / "flight_board.NET")
        assert r == {"n_parts": 2, "n_nets": 3}
        net_text = (proj / "flight_board.NET").read_text()
        parts = re.findall(r"\[\n(\S+)\n(\S+)\n(\S+)\n\]", net_text)
        nets = {m[0]: set(m[1].split()) for m in re.findall(r"\(\n(\S+)\n(.*?)\)", net_text, re.S)}
        pcb = (proj / "flight_board.kicad_pcb").read_text()
        want_parts, want_nets = [], {}
        for blk in re.findall(r'^\t\(footprint "SmashFlightBoard:([^"]+)"(.*?)^\t\)$', pcb, re.M | re.S):
            if "board_only" in blk[1]:
                continue                        # mounting holes: no symbol, no nets
            ref = re.search(r'\(property "Reference" "([^"]+)"', blk[1]).group(1)
            val = re.search(r'\(property "Value" "([^"]+)"', blk[1]).group(1)
            want_parts.append((ref, blk[0], val))
            for pad, net in re.findall(r'\(pad "([^"]+)".*?\(net "([^"]+)"\)', blk[1], re.S):
                if not net.startswith("unconnected-"):
                    want_nets.setdefault(net, set()).add(f"{ref}-{pad}")
        assert sorted(parts) == sorted(want_parts)
        assert nets == want_nets

    def test_board_folder_carries_datasheets_and_samacsys(self, tiny_design, tmp_path):
        """A board project carries its parts' datasheets (fields point at
        the copy, in schematic and board alike) and their SamacSys KiCad
        symbol + Altium libraries."""
        import glob
        u1 = next(c for c in tiny_design.chips if c.ref == "U1")
        pdf = sorted(glob.glob("src/smash/parts/sources/SN74LVC1G08DCKRG4/*.pdf"))[0]
        u1.datasheet = "application/" + pdf
        proj, _ = self._board_project(tiny_design, tmp_path)
        name = pathlib.Path(pdf).name
        assert (proj / "datasheets" / "SN74LVC1G08DCKRG4" / name).is_file()
        field = f"${{KIPRJMOD}}/datasheets/SN74LVC1G08DCKRG4/{name}"
        assert f'(property "Datasheet" "{field}"' in (proj / "flight_board.kicad_sch").read_text()
        assert f'(property "Datasheet" "{field}"' in (proj / "flight_board.kicad_pcb").read_text()
        lib = proj / "samacsys" / "SN74LVC1G08DCKRG4"
        assert (lib / "SN74LVC1G08DCKRG4.kicad_sym").is_file()
        assert list((lib / "Altium").glob("*.SchLib")) and list((lib / "Altium").glob("*.PcbLib"))

    def test_board_schematic_parity(self, tiny_design, tmp_path):
        """KiCad's own schematic-parity DRC finds the board and its
        schematic in sync: every footprint linked, every pad on its net,
        every field equal."""
        import json
        import subprocess
        from smash.export import find_kicad_cli, KiCadCliNotFound
        try:
            cli = find_kicad_cli()
        except KiCadCliNotFound:
            pytest.skip("kicad-cli not installed")
        proj, _ = self._board_project(tiny_design, tmp_path)
        report = tmp_path / "drc.json"
        subprocess.run([str(cli), "pcb", "drc", "--schematic-parity", "--format", "json",
                        "-o", str(report), str(proj / "flight_board.kicad_pcb")],
                       check=True, capture_output=True)
        assert json.loads(report.read_text())["schematic_parity"] == []

    def test_kicad_netlist_matches_design(self, tiny_design, tmp_path):
        """Round-trip through kicad-cli: the netlist KiCad derives from
        the schematic has the same pin groups as the Design."""
        import subprocess
        import xml.etree.ElementTree as ET
        from smash.export import write_kicad_schematic, find_kicad_cli, KiCadCliNotFound
        from smash.export._common import nets_with_pins, net_connections
        try:
            cli = find_kicad_cli()
        except KiCadCliNotFound:
            pytest.skip("kicad-cli not installed")
        write_kicad_schematic(tiny_design, tmp_path)
        out = tmp_path / "net.xml"
        subprocess.run([str(cli), "sch", "export", "netlist", "--format",
                        "kicadxml", "-o", str(out), str(tmp_path / "smash.kicad_sch")],
                       check=True, capture_output=True)
        root = ET.parse(out).getroot()
        got = {frozenset((n.get("ref"), n.get("pin")) for n in net.iter("node"))
               for net in root.iter("net")
               if not net.get("name").startswith("unconnected-")}
        want = {frozenset(net_connections(n)) for n in nets_with_pins(tiny_design)}
        assert got == want
