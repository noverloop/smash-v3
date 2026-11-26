"""Net classes + impedance table + decoupling map (layout handoff)."""
import json

from smash.layout import netclasses as N
from smash.sim import impedance as Z


def test_impedance_formulas_match_textbook_cases():
    assert abs(Z.microstrip_z0(2.9, 1.5, 4.5, 0.035) - 50) < 2.5      # 1.6 mm FR4 50 Ω line
    assert abs(Z.stripline_z0(0.2, 0.241, 0.241, 4.2, 0.018) - 49) < 3


def test_standard_stack_widths_are_buildable():
    t = Z.table()
    assert 0.12 < t["F.Cu"]["50"] < 0.18
    assert t["In2.Cu"]["50"] >= 0.075            # NCAB advanced minimum track
    assert 95 < Z.zdiff("In2.Cu", 0.075, 0.20) < 105


def test_classifier_covers_the_interfaces():
    assert N.classify("DDR3L_DQ7") == "DDR_SE55"
    assert N.classify("DDR3L_DQS1_P") == "DDR_DIFF100"
    assert N.classify("CAM_CSI_D0_N") == "CSI_DIFF100"
    assert N.classify("XV_PA_OUT") == "RF_50"
    assert N.classify("ACT_WIRE_12") == "HV_33V"
    assert N.classify("ACTIVATE_HV") == "HV_33V"
    assert N.classify("BAT_PROT") == "PWR_PACK"
    assert N.classify("COMP_5V_SW") == "SW_NODE"
    assert N.classify("PIEZO_P") == "ANALOG_HIZ"
    assert N.classify("SYS_SPI_SCLK__MPU") == "CLK_50"
    assert N.classify("FLEX_GND") == "GND"


def test_rf_and_power_lists_name_real_nets():
    from smash.roots import git_repo_root
    nets = {n["name"] for n in json.loads(
        (git_repo_root() / "dist" / "maximalist_canonical_netlist.json").read_text())["nets"]}
    for group in (N.RF_50, N.CLK, N.ANALOG, N.HV, N.PACK, N.P1A, N.P_LOW):
        missing = sorted(group - nets)
        assert not missing, f"class lists name nets that do not exist: {missing}"


def test_dev_power_lists_name_real_dev_nets():
    import contextlib, io, sys
    from smash.roots import git_repo_root
    root = str(git_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    import generate_devboard as GD
    with contextlib.redirect_stdout(io.StringIO()):
        d, _r, _l = GD.build_design()
    nets = {n.name for n in d.nets}
    missing = sorted((N.DEV_PACK | N.DEV_P_LOW) - nets)
    assert not missing, f"dev-board power lists name nets that do not exist: {missing}"
    assert all(N.classify(n) == "PWR_PACK" for n in N.DEV_PACK)
    assert all(N.classify(n) == "PWR_LOW" for n in N.DEV_P_LOW)


def test_project_file_carries_classes(tmp_path):
    pcb = tmp_path / "x.kicad_pcb"
    pcb.write_text('(kicad_pcb (net "BAT_PROT") (net "DDR3L_A0") (net "FOO"))')
    from smash.export.kicad_pcb import write_blank_drawing_sheet
    write_blank_drawing_sheet(pcb)
    ns = json.loads((tmp_path / "x.kicad_pro").read_text())["net_settings"]
    assert {c["name"] for c in ns["classes"]} >= {"Default", "PWR_PACK", "DDR_SE55", "RF_50"}
    pats = {p["pattern"]: p["netclass"] for p in ns["netclass_patterns"]}
    assert pats == {"BAT_PROT": "PWR_PACK", "DDR3L_A0": "DDR_SE55"}


def test_dru_rules_follow_the_fab_rules():
    blk = ('(kicad_pcb\n\t(footprint "x:BGA"\n\t\t(property "Reference" "U1")\n'
           + "".join(f'\t\t(pad "{i}" smd circle (at {0.5 * (i % 6)} {0.5 * (i // 6)}) (size 0.25 0.25))\n'
                     for i in range(36)) + "\t)\n)")
    assert N.fine_pitch_array_refs(blk) == ["U1"]
    dru = N.build_dru(blk)
    assert "intersectsCourtyard('U1')" in dru and "track_width (min 0.125mm)" in dru
    assert N.ENFORCED_MIN == 0.10
    assert "Micro" in dru and "hole_to_hole" in dru          # no stacked microvias
    assert "HV_33V" in dru
    assert N.CLASSES["Default"]["width"] == 0.125
