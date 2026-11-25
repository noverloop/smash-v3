"""Net classes for the tower tiles: routing widths, clearances, impedance
targets and the net → class assignment, written into every .kicad_pro.

Widths come from `smash.sim.impedance` (controlled impedance, standard
8L 2+4+2 stack-up) and IPC-2221 (current: ΔT 10 °C, outer 36 µm / inner
18 µm). Assignment is by net name — explicit lists for RF and power,
patterns for the buses — so the class map is the same in every tile
project, the panel and the configuration boards.

`classify(name)` → class name; `classes()` → the class table; the
`write_project_classes(pro, net_names)` helper patches a .kicad_pro.
"""
from __future__ import annotations

import json
import pathlib
import re

from smash.sim import impedance as Z

_T = Z.table()

# ── class table ─────────────────────────────────────────────────────────
# width = outer-layer width (F.Cu / B.Cu); inner_width where it differs.
# clearance = to other nets. Impedance classes give their target.
CLASSES: dict[str, dict] = {
    "Default": dict(width=0.10, clearance=0.075,
                    note="all other signals; 75 µm clearance (NCAB advanced HDI)"),
    "DDR_SE55": dict(width=_T["F.Cu"]["55"], inner_width=0.075, clearance=0.075, z="55 Ω SE ±10 %",
                     note="AN5489/AN5724: 55 Ω (inner 0.075 mm min track ≈ 51.5 Ω). Spacing S-3S "
                          "(S-2S fallback) outside the BGA fields, 0.075 inside. Match DQ/DM to byte "
                          "DQS ±1.42 mm, A/C to CK ±3.55 mm, DQS to CK ±12.07 mm (incl. MP25 package "
                          "lengths); switchback tuning only."),
    "DDR_DIFF100": dict(width=_T["F.Cu"]["diff100"][0], diff_gap=_T["F.Cu"]["diff100"][1],
                        inner_width=0.075, inner_diff_gap=0.20, clearance=0.15, z="100 Ω diff ±10 %",
                        note="DDR CK / DQS pairs: constant gap, no intra-pair equalisation (AN5724 §6.2)."),
    "CSI_DIFF100": dict(width=_T["F.Cu"]["diff100"][0], diff_gap=_T["F.Cu"]["diff100"][1],
                        inner_width=0.075, inner_diff_gap=0.20, clearance=0.20, z="100 Ω diff ±10 %",
                        note="MIPI CSI-2 D-PHY: intra-pair ≤ 0.1 mm, lane-to-clock ≤ 1 mm; "
                             "continuous GND reference, no layer change without GND vias."),
    "RF_50": dict(width=_T["F.Cu"]["50"], inner_width=_T["In2.Cu"]["50"], clearance=0.25, z="50 Ω SE",
                  note="outer layers over In1/In6 GND (grounded-coplanar acceptable with ≥ 0.25 mm "
                       "gap); GND via fence ≤ λ/20 (≈ 1.5 mm at 5 GHz); no vias in the RF path "
                       "except at the castellation feed."),
    "RF_DIFF100": dict(width=_T["F.Cu"]["diff100"][0], diff_gap=_T["F.Cu"]["diff100"][1],
                       clearance=0.25, z="100 Ω diff",
                       note="LTC5552 IF port to the NCS1-292+ balun."),
    "CAN_PAIR": dict(width=0.15, diff_gap=0.15, clearance=0.15, z="≈ 120 Ω diff (short stub, not critical)",
                     note="EXT_CAN_P/N: route as a tightly coupled pair to the crown contacts."),
    "CLK_50": dict(width=_T["F.Cu"]["50"], inner_width=_T["In2.Cu"]["50"], clearance=0.20, z="50 Ω SE",
                   note="clocks and the fast flash buses (OSPI NAND, radar QSPI): 3W to other "
                        "signals, no stubs, series R at the source; flash data within ±2 mm of its "
                        "clock."),
    "ANALOG_HIZ": dict(width=0.10, clearance=0.20,
                       note="high-impedance / precision nodes (piezo charge node, QPD TIA inputs, "
                            "loop filters, feedback dividers, crystals, ZQ/REXT): short, guard with "
                            "GND, keep away from SW nodes and clocks."),
    "SW_NODE": dict(width=0.50, clearance=0.15,
                    note="switch nodes: smallest copper area that carries the current; no other "
                         "signals under them on the adjacent layer."),
    "HV_33V": dict(width=0.20, clearance=0.13,
                   note="ACTIVATE_HV / cutter matrix (≤ 33 V, 0.12 A burn): IPC-2221B B4 "
                        "(31-50 V, coated/potted) 0.13 mm."),
    "PWR_PACK": dict(width=2.5, inner_width=6.0, clearance=0.15,
                     note="pack path (BAT_CELLx, BAT_RAW, BAT_PROT, REG_IN_MAIN, COMP_5V_RAW): 1.8 A "
                          "descent, 4.4 A chirp + cutter, 6.5 A with fins stepping — outer-layer pours "
                          "(IPC-2221, ΔT 10 °C: 4.4 A ≈ 2.3 mm outer, 6.5 A ≈ 3.9 mm outer; inner "
                          "18 µm needs ≈ 5×). Short, on pours, stitched to a parallel inner pour."),
    "PWR_1A": dict(width=0.50, inner_width=2.5, clearance=0.10,
                   note="regulator outputs / loads up to ≈ 1.5 A (MP25 core, DDR, radar rails, "
                        "fins, COMP_5V): 1.5 A ≈ 0.51 mm outer; prefer pours."),
    "PWR_LOW": dict(width=0.25, inner_width=0.6, clearance=0.10,
                    note="rails ≤ 0.5 A (AON, LDO outputs, sensor and RF supplies)."),
    "GND": dict(width=0.25, clearance=0.075, note="planes In1/In3/In6 + stitching vias at every GND pad."),
}

# ── assignment ──────────────────────────────────────────────────────────
RF_50 = {
    "ANT_HF_S1", "ANT_HF_S4", "ANT_S1_COM", "BLE_ANT", "BLE_RF", "WBA_RF",
    "LR_HF_ANT_IN", "LR_HF_ANT_OUT", "LR_HF_RFI", "LR_HF_RFO", "LR_HF_RX", "LR_HF_RX_M",
    "LR_HF_S1", "LR_HF_TRX", "LR_HF_TX", "LR_HF_TX_F", "LR_HF_TX_M",
    "XV_ANT_SW", "XV_BPF_M", "XV_BPF_O", "XV_IF_SW", "XV_LNA_IN", "XV_LNA_OUT",
    "XV_LO_OUT_N", "XV_LO_OUT_P", "XV_LO_PAD_I", "XV_LO_PAD_O", "XV_LO_TERM",
    "XV_MIX_IF", "XV_MIX_LO", "XV_MIX_RF", "XV_PA_IN", "XV_PA_OUT", "XV_PA_PADO",
    "XV_RF", "XV_RX_IN", "XV_RX_OUT", "XV_TX_IN", "XV_TX_OUT",
}
RF_DIFF = {"XV_MIX_IF_P", "XV_MIX_IF_N"}
CLK = {
    "CAM_EXTCLK", "COMP_HSE_IN", "WBA_HSE_IN", "WBA_HSE_OSC", "WBA_HSE_DIV",
    "LR_TCXO_OUT", "LR_TCXO_OUT_MEMS", "LR_TCXO_OUT_QZ", "LR_XTA", "LR_XTA_C", "XV_LO_REF",
    "AWR_OSC_OUT", "NAND_OSPI_CLK", "AWR_QSPI_CLK", "AWR_SPI_CLK", "SYS_SPI_SCLK",
    "WBA_HCI_SCK", "LR_SPI_SCK", "LR_SPI_SCK_L",
    # fast flash buses ride with their clock (≈ 100 MHz OSPI / 40 MHz QSPI)
    "NAND_OSPI_CS0", "NAND_OSPI_CS1", "NAND_OSPI_IO0", "NAND_OSPI_IO1", "NAND_OSPI_IO2",
    "NAND_OSPI_IO3", "AWR_QSPI_CS", "AWR_QSPI_SI", "AWR_QSPI_SO", "AWR_QSPI_IO2", "AWR_QSPI_IO3",
}
ANALOG = {
    "PIEZO_P", "COMP_INP", "QPD_A", "QPD_B", "QPD_C", "QPD_D", "QPD_VREF", "VBGAP", "CSI_REXT",
    "MPU_DDR_ZQ", "USB_TXRTUNE", "BAT_SENSE", "XV_LO_RSET", "XV_LO_VTUNE", "XV_LO_CP",
    "XV_LO_LF2", "XV_LO_VCOM", "XV_LO_VREF", "XV_LO_TEMP", "AWR_CLKREF", "AWR_CLKM",
    "COMP_5V_COMP", "COMP_5V_COMP_C", "COMP_5V_PL", "ACTIVATE_COMP", "ACTIVATE_COMP_C",
    "V08_CAP", "COMP_LSE_IN", "XV_PA_VGAIN",
}
HV = {"ACTIVATE_HV", "ACTIVATE_SW", "PARACHUTE_CUTTER_ACTIVATE", "PARACHUTE_CUTTER_ACTIVATE_G",
      "PARACHUTE_CUTTER_ACTIVATE_GD"}
PACK = {"BAT_CELL1_POS", "BAT_CELL2_POS", "BAT_CELL3_POS", "BAT_RAW", "BAT_PROT",
        "REG_IN_MAIN", "COMP_5V_RAW"}
P1A = {"COMP_5V", "XV_5V", "EXT_VIN", "AWR_1V2", "AWR_1V3", "AWR_1V3_BK", "AWR_1V8", "AWR_1V8_BK",
       "COMP_0V82", "COMP_0V9", "COMP_1V35", "COMP_1V8", "3V3", "CAM_VCORE_1V15"}
P_LOW = {"3V3_AON", "TMR_VDD", "MAG_1V8", "COMP_1V8_AON", "COMP_2V8", "COMP_3V3", "LR_VBAT",
         "XV_LO_3V3", "CAM_VAA_2V8", "HALL_VIN", "WBA_VDD11", "WBA_VDDHPA", "PMIC_INTLDO",
         "FIN_MCU_VDD11", "LR_TCXO_3V3", "XV_LNA_VDD", "XV_PA_VDD1", "LR_VR_PA", "LR_VDCC",
         "LR_VPAX", "LR_VTCXO", "AWR_VOUT_PA", "CAM_LDO2V4", "CAM_VRT", "CAM_CPPOS", "CAM_CPNEG",
         "HEALTH_COIL_D", "HEALTH_COIL_RET", "COMP_BST_VCC", "COMP_BST_CAP",
         "AWR_VOUT_14APLL", "AWR_VOUT_14SYNTH",
         "IR_TX_K", "IR_TX_K_C", "IR_TX_K_Q", "IR_TX_M", "IR_TX_M_C", "IR_TX_M_Q",
         "IR_TX_D", "IR_TX_D_C", "IR_TX_D_Q",
         "PMIC_LDO2_TERM", "PMIC_LDO4_TERM", "PMIC_LDO6_TERM", "PMIC_LDO7_TERM", "PMIC_LDO8_TERM"}

_RULES: list[tuple[str, re.Pattern]] = [
    ("GND", re.compile(r"^(FLEX_)?GND$")),
    ("DDR_DIFF100", re.compile(r"^DDR3L_(CK|DQS\d)_[PN]$")),
    ("DDR_SE55", re.compile(r"^DDR3L_")),
    ("CSI_DIFF100", re.compile(r"^CAM_CSI_(CLK|D\d)_[PN]$")),
    ("HV_33V", re.compile(r"^ACT_(ROW_\d(_G|_GD)?|WIRE_\d+|COL_\d)$")),
    ("SW_NODE", re.compile(r"(_SW|_SWB|_VLX|^PMIC_SW\d)$")),
    ("PWR_1A", re.compile(r"^FIN\d_[AB]OUT\d$")),
    ("ANALOG_HIZ", re.compile(r"^QPD_TIA_[A-D](_AMP)?$|_FB$")),
]


def classify(name: str) -> str:
    """Net class for a net name (aliases such as `FOO__MPU` follow `FOO`)."""
    base = re.sub(r"__(MPU|WBA|FIN)$", "", name)
    if base in HV or name == "ACTIVATE_SW":
        return "HV_33V"
    for cls, pat in _RULES[:1]:
        if pat.search(base):
            return cls
    if base in RF_50:
        return "RF_50"
    if base in RF_DIFF:
        return "RF_DIFF100"
    if base in ("EXT_CAN_P", "EXT_CAN_N"):
        return "CAN_PAIR"
    if base in PACK:
        return "PWR_PACK"
    for cls, pat in _RULES[1:]:
        if pat.search(base):
            return cls
    if base in CLK:
        return "CLK_50"
    if base in ANALOG:
        return "ANALOG_HIZ"
    if base in P1A:
        return "PWR_1A"
    if base in P_LOW:
        return "PWR_LOW"
    return "Default"


def classes() -> dict:
    return CLASSES


# ── KiCad project ───────────────────────────────────────────────────────
_KEY = dict(width="track_width", clearance="clearance", diff_gap="diff_pair_gap")


def kicad_classes() -> list[dict]:
    out = []
    for name, c in CLASSES.items():
        k = {"name": name, "clearance": c["clearance"], "track_width": c["width"],
             "via_diameter": 0.45, "via_drill": 0.2, "microvia_diameter": 0.25,
             "microvia_drill": 0.15, "diff_pair_width": c["width"],
             "diff_pair_gap": c.get("diff_gap", 0.15)}
        if name in ("PWR_PACK", "PWR_1A"):
            k["via_diameter"], k["via_drill"] = 0.6, 0.3
        out.append(k)
    return out


def write_project_classes(pro_path, net_names) -> None:
    """Merge the class table + an exact-name pattern per assigned net into
    an existing .kicad_pro (KiCad 7+ `netclass_patterns`)."""
    pro = pathlib.Path(pro_path)
    data = json.loads(pro.read_text()) if pro.exists() else {}
    ns = data.setdefault("net_settings", {})
    ns["classes"] = kicad_classes()
    pats = []
    for n in sorted(set(net_names)):
        cls = classify(n)
        if cls != "Default":
            pats.append({"netclass": cls, "pattern": n})
    ns["netclass_patterns"] = pats
    ns.setdefault("meta", {"version": 3})
    pro.write_text(json.dumps(data, indent=2) + "\n")


def pcb_net_names(pcb_path) -> list[str]:
    txt = pathlib.Path(pcb_path).read_text()
    return sorted({m.group(1) for m in re.finditer(r'\(net (?:\d+ )?"([^"]+)"\)', txt)})


def report_md(net_names) -> str:
    """NET_CLASSES.md: the class table, the impedance table and the members."""
    by: dict[str, list[str]] = {}
    for n in sorted(set(net_names)):
        by.setdefault(classify(n), []).append(n)
    L = ["# Net classes", "",
         "Generated by `smash.layout.netclasses`; the same classes and assignments are in every "
         "`.kicad_pro` (Board Setup → Net Classes). Widths in mm; the impedance widths are "
         "closed-form targets for the standard stack-up — ask the fab to tune them on its solver.", "",
         "## Layer plan (8L 2+4+2, 0.868 mm)", "",
         "| Layer | Use | Reference |", "|---|---|---|",
         "| F.Cu (L1) | signals, RF, DDR, pours | In1 GND |",
         "| In1.Cu (L2) | GND plane | — |",
         "| In2.Cu (L3) | signals (stripline) | In1 GND / In3 GND |",
         "| In3.Cu (L4) | GND plane | — |",
         "| In4.Cu (L5) | power planes / pours | — |",
         "| In5.Cu (L6) | signals (stripline) | In4 PWR / In6 GND |",
         "| In6.Cu (L7) | GND plane | — |",
         "| B.Cu (L8) | signals, pours | In6 GND |", "",
         "## Controlled-impedance widths", "",
         "| Layer | 50 Ω | 55 Ω | 100 Ω diff (w / gap) | 90 Ω diff (w / gap) |",
         "|---|---|---|---|---|"]
    for layer, r in _T.items():
        L.append(f"| {layer} | {r['50']:.3f} | {r['55']:.3f} | {r['diff100'][0]:.3f} / {r['diff100'][1]:.2f} "
                 f"| {r['diff90'][0]:.3f} / {r['diff90'][1]:.2f} |")
    L += ["", "Inner layers: 0.075 mm is the minimum track, so 55 Ω inner = 0.075 mm (≈ 51.5 Ω) and "
          "100 Ω inner pairs = 0.075 mm / 0.20 mm gap.", "",
          "## Classes", "", "| Class | Width outer / inner | Clearance | Target | Rule |",
          "|---|---|---|---|---|"]
    for name, c in CLASSES.items():
        w = f"{c['width']:.3f}" + (f" / {c['inner_width']:.3f}" if "inner_width" in c else "")
        if "diff_gap" in c:
            w += f" (gap {c['diff_gap']:.2f}" + (f" / {c['inner_diff_gap']:.2f}" if "inner_diff_gap" in c else "") + ")"
        L.append(f"| {name} | {w} | {c['clearance']:.3f} | {c.get('z', '')} | {c['note']} |")
    L += ["", "## Members", ""]
    for name in CLASSES:
        if name == "Default" or name not in by:
            continue
        L.append(f"- **{name}** ({len(by[name])}): " + ", ".join(by[name]))
    return "\n".join(L) + "\n"
