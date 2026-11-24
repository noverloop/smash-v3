"""Height audit: does an accepted swap raise the tallest part on its board face?
usage (repo root): PYTHONPATH=application/src python3 availability/tools/height_audit.py
Reads dist/maximalist/<tile>/*.kicad_pcb for ref -> face, the dev design for
current heights, and NEW_H below (datasheet / library max heights, mm)."""
import sys, re, glob, pathlib, collections
ROOT = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import generate_devboard as GD
NEW = {  # ref-prefix -> (new part, max height mm, source)
 "C_BAT_BULK": ("6TPE470MI", 3.8, "RS: D4 case 7.3x4.3x3.8"),
 "C_BOOST_OUT1": ("T521V476M016ATE070", 2.0, "KEMET V case 7343-20, 1.9 nom"),
 "CBAT1": ("2x GRM31CR60J476ME19L", 1.8, "Murata 1206 1.6 +/-0.2"),
 "CBAT2": ("2x GRM31CR60J476ME19L", 1.8, "Murata 1206 1.6 +/-0.2"),
 "L_BOOST_COMP": ("WE-MAPI 4030 74438357047", 3.1, "Wurth STEP 4.1x4.1x3.1"),
 "L_ACTIVATE": ("WE-MAPI 4030 74438357082", 3.1, "Wurth STEP"),
 "U_DDR": ("MT41K256M16TW-107 IT:P", 1.2, "Micron TW FBGA-96 1.2 max"),
 "U_CAM=": ("VB1943CAJX/1", 2.2, "SamacSys BGA74...X220"),
 "QMAIN": ("SSM3J372R,LF", 0.9, "SOT-23F"), "Q_AON_EN": ("SSM3J372R,LF", 0.9, "SOT-23F"),
 "U_FIN": ("TC78H653FTG", 0.9, "VQFN16 X90"), "U_TMP1": ("MCP9808T-E/MC", 1.0, "DFN-8 X100"),
 "U_AWR_LDO18": ("XC6220B181MR-G", 1.3, "SOT-25"), "U_AON_LDO": ("XC6504A331MR-G", 1.3, "SOT-25 X130"),
 "U_TMR_LDO": ("XC6504A331MR-G", 1.3, "SOT-25 X130"),
 "U_COMP_PZ": ("MCP6541T-E/OT", 1.45, "SOT-23-5 X145"), "U_CAN_GW": ("TJA1462BTK", 1.0, "HVSON-8 X100"),
 "U_MAG": ("BMM350", 0.54, "WLCSP X54"), "U_IMU": ("ISM330DLC", 0.86, "LGA-14"),
 "U_XV_MIX": ("ADL5801", 0.8, "LFCSP X80"), "U_G0B1": ("STM32U545REI6Q", 0.6, "UFBGA X60"),
 "U_AWR_FLASH": ("MX25V8035FZNI", 0.8, "WSON 6x5"), "Y_AWR_HSE": ("SiT1602BI 2520", 0.8, "SiTime 2520"),
 "Y_LR_TCXO": ("SiT5356 5032", 0.9, "SiTime 5032 ceramic"),
 "D_IR_WAKE": ("VEMD5110X01", 0.9, "Vishay top-view SMD"),
 "C_WBA_PI": ("GJM1555 0402", 0.55, "0402"), "D_ACTIVATE": ("RB160VAM-60", 0.7, "TUMD2SM"),
 "U_XV_BOOST": ("MCP1640D-I/MC", 1.0, "same chip"),
}
BSS = ("QHOLD", "Q_HEALTH_COIL", "Q_PARACHUTE_CUTTER_ACTIVATE_LS", "Q_ACT_ROW", "Q_ACT_COL", "Q_CAM_", "Q_IR_TX",
       "Q_ISO_DRV", "Q_ISO_EXT", "Q_EXTOR_DRV", "Q_EXT_WAKE", "Q_WBA_RST")
d, _, _ = GD.build_design()
H = {c.ref: (getattr(c, "height_mm", None) or getattr(getattr(c, "footprint", None), "height_mm", None) or 0.0, c.manf_pn) for c in d.chips}
face = {}   # ref -> (tile, F/B)
for f in glob.glob(str(ROOT / "dist/maximalist/*/*.kicad_pcb")):
    tile = pathlib.Path(f).parent.name
    if tile.startswith("spacer") or tile in ("sleeve", "potting_mould", "battery_holder"): continue
    t = open(f).read()
    rd = {}
    for c in glob.glob(str(pathlib.Path(f).parent / "*_refdes.csv")):
        import csv as _csv
        rd = {r["Ref"]: r["Design ref"] for r in _csv.DictReader(open(c))}
    for m in re.finditer(r'\(footprint "[^"]*"\s*\(layer "([FB])\.Cu"\).*?\(property "Reference" "([^"]+)"', t, re.S):
        face.setdefault(rd.get(m[2], m[2]), (tile, m[1]))
faces = collections.defaultdict(list)
for ref, (tile, side) in face.items():
    if ref in H: faces[(tile, side)].append((H[ref][0], ref))
def newh(ref):
    for k, v in NEW.items():
        if (k.endswith("=") and ref == k[:-1]) or (not k.endswith("=") and ref.startswith(k)): return v
    if any(ref.startswith(p) for p in BSS) and "BSS138" in str(H.get(ref, ("", ""))[1]):
        return ("RU1J002YNTCL", 1.05, "SOT-323FL X105")
    return None
rows = []
for ref, (tile, side) in sorted(face.items()):
    n = newh(ref)
    if not n or ref not in H: continue
    others = [h for h, r in faces[(tile, side)] if r != ref]
    oldmax = max(others + [H[ref][0]]); newmax = max(others + [n[1]])
    rows.append((round(newmax - oldmax, 2), tile, side, ref, H[ref][1], H[ref][0], n[0], n[1], max(others or [0])))
print(f"{'raise':>6} {'tile':22} face {'ref':30} {'old part':26} {'old h':>5} -> {'new part':26} {'new h':>5}  face max (others)")
for r in sorted(rows, key=lambda r: (-r[0], r[1])):
    if r[0] > 0 or r[7] > r[5] + 0.2:
        print(f"{r[0]:>6} {r[1]:22} {r[2]:4} {r[3][:30]:30} {str(r[4])[:26]:26} {r[5]:5.2f} -> {r[6][:26]:26} {r[7]:5.2f}  {r[8]:.2f}")
print("checked", len(rows), "swapped refs; refs without a face in dist/maximalist are skipped:",
      sorted({k for k in NEW} - {r[3].rstrip('0123456789_') for r in rows})[:12])
