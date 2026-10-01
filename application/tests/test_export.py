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
