"""Full current BOM as a supplier upload, with every accepted swap applied.

Builds the dev-board design (the superset: every tower tile + dev-only parts),
maps generic passive names to orderable MPNs (via the earlier full-BOM upload
availability/full_bom/dev_board_mouser_v3.csv, then passive_map rules), applies
the accepted substitutions from decisions, and writes
availability/rounds/full_bom_roundN_upload.csv.
usage (repo root): PYTHONPATH=application/src python3 availability/tools/full_bom.py 13
"""
import sys, csv, re, pathlib, collections
HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import generate_devboard as GD, passive_map as pm
rnd = sys.argv[1] if len(sys.argv) > 1 else "13"

# generic → orderable, from the earlier upload (matched on references)
old = {r["References"].split()[0]: r["MPN"] for r in csv.DictReader(open(HERE.parent / "full_bom/dev_board.csv")) if r["References"]}
gen2ord = {}
for r in csv.DictReader(open(HERE.parent / "full_bom/dev_board_mouser_v3.csv")):
    cp = r["Customer Part Number"]
    if re.search(r"\balt", cp, re.I): continue          # alternates rows, not the fitted part
    ref = cp.split("+")[0].strip()
    if ref in old and old[ref] != r["Mfr Part Number"] and " " in old[ref]:   # generic names only
        gen2ord.setdefault(old[ref], (r["Mfr Part Number"], r["Manufacturer"]))

# accepted swaps (original orderable MPN -> (new MPN, manufacturer, qty multiplier))
SWAP = {
 "T545W477M006ATE035": ("6TPE470MI", "Panasonic", 1), "T528W476M016ATE030": ("T521V476M016ATE070", "KEMET", 1), "T520V476M016ATE070": ("T521V476M016ATE070", "KEMET", 1),
 "DRV8428ERTER": ("TC78H653FTG,EL", "Toshiba", 1), "TMP117MAIDRVR": ("MCP9808T-E/MC", "Microchip", 1),
 "STM32G474CEU6": ("STM32U535CBU6", "STMicroelectronics", 1),
 "SQCSVA8R2BAT1A": ("C0603C829C5GACTU", "KEMET", 1), "SQCSVA100JAT1A": ("C0603C100J5GACTU", "KEMET", 1),
 "04025A0R8BAT2A": ("GJM1555C1HR80BB01D", "Murata", 1), "04025A1R2BAT2A": ("GJM1555C1H1R2BB01D", "Murata", 1),
 "04025A5R1BAT2A": ("GJM1555C1H5R1BB01D", "Murata", 1), "C0402C473K3RACTU": ("GRM155R71E473KA88D", "Murata", 1),
 "744784018A": ("LQG15HS1N8S02D", "Murata", 1), "PMEG6010CEJ,115": ("RB160VAM-60TR", "ROHM", 1), "PMEG6010CEJ": ("RB160VAM-60TR", "ROHM", 1),
 "DSC1001CI5-027.0000": ("DSC1001CI1-027.0000", "Microchip", 1), "MCP1640DT-I/MC": ("MCP1640D-I/MC", "Microchip", 1),
 "TPS7A0233PDQNR": ("XC6504A331MR-G", "Torex", 1), "TLV3691IDPFR": ("MCP6541T-E/OT", "Microchip", 1),
 "TCAN1042GVDRBRQ1": ("TJA1462BTK/0Z", "NXP", 1), "TPD4E05U06DQAR": ("USBLC6-4SC6", "STMicroelectronics", 1),
 "INA228AIDGSR": ("PAC1941T-1E/J6CX", "Microchip", 1), "IRLML6402TRPBF": ("SSM3J372R,LF", "Toshiba", 1),
 "KTDM4G4B626BGIEAT": ("MT41K256M16TW-107 IT:P", "Micron", 1), "BSS138AKM-QYL": ("RU1J002YNTCL", "ROHM", 1),
 "LDL112PV18R": ("XC6220B181MR-G", "Torex", 1), "DSC1001CI5-040.0000": ("SIT1602BI-12-18E-40.000000", "SiTime", 1),
 "TG2016SMN 32.0000M-MCGNNM0": ("SiT5356AECFQ-33N0-32.000000T", "SiTime", 1),
 "AR0234CSSM00SUKA0-CP": ("VB1943CAJX/1", "STMicroelectronics", 1),
 "UJ20-C-H-G-MSMT-1A-P16-TR-67": ("CX90B-16P", "Hirose", 1), "VBPW34FAS": ("VEMD5110X01", "Vishay", 1),
 "STM32MP255FAL3": ("STM32MP257FAL3", "STMicroelectronics", 1), "ISM330DHCXTR": ("ISM330DLCTR", "STMicroelectronics", 1),
 "T520W107M006ATE040": ("GRM31CR60J476ME19L", "Murata", 2), "STM32G0B1REI6N": ("STM32U545REI6Q", "STMicroelectronics", 1),
 "IIS2MDCTR": ("BMM350", "Bosch Sensortec", 1), "PE64906B-Z": ("PE64904D-Z", "pSemi", 1),
 "LTC5549IUDB#PBF": ("ADL5801ACPZ-R7", "Analog Devices", 1), "LTC5549IUDB#TRMPBF": ("ADL5801ACPZ-R7", "Analog Devices", 1), "LTC5549IUDB": ("ADL5801ACPZ-R7", "Analog Devices", 1),
 "ADF4351BCPZ": ("ADF4351BCPZ-RL7", "Analog Devices", 1),
 "DMP6110SVT-7": ("BUK6D120-60PX", "Nexperia", 1),
 "04025A0R5BAT2A": ("GJM1555C1HR50BB01D", "Murata", 1), "SQCSVA0R5BAT1A": ("GJM1555C1HR50BB01D", "Murata", 1),
 "04025A1R0BAT2A": ("GJM1555C1H1R0BB01D", "Murata", 1), "04025A1R1BAT2A": ("GJM1555C1H1R1BB01D", "Murata", 1),
 "SQCSVA101JAT1A": ("C0603C101J5GACTU", "KEMET", 1), "C0402C104K3RACTU": ("GRM155R71C104KA88D", "Murata", 1),
 "XGL5020-472MEC": ("74438357047", "Wurth Elektronik", 1), "XGL5020-822MEC": ("74438357082", "Wurth Elektronik", 1),
 "SST26VF080A-104I/MF": ("MX25V8035FZNI", "Macronix", 1), "TCAN1042GVDQ1": ("TJA1462BTK/0Z", "NXP", 1),
}
d, _, _ = GD.build_design()
rows = collections.OrderedDict(); unmapped = collections.Counter(); generic = collections.Counter()
for c in list(d.chips):
    if getattr(c, "dnp", False): continue
    pn = (c.manf_pn or c.value or "").strip(); mf = c.manf or ""
    if not pn or pn.upper().startswith("GENERIC") or "TestPoint" in pn or "TestPoint" in (c.description or ""): generic[pn or "(blank)"] += 1; continue
    if pn in gen2ord: pn, mf = gen2ord[pn]
    elif " " in pn and not re.match(r"^[A-Z0-9][\w\-/#.,:]*( (IT|AIT|WT|AUT|AAT):[A-Z])?$", pn):
        cand = pm.candidates(pn, c.description or "")
        if cand: pn = cand[0]
        else: unmapped[pn] += 1
    mult = 1
    if pn in SWAP: pn, mf, mult = SWAP[pn]
    key = pn
    e = rows.setdefault(key, {"mf": mf, "qty": 0, "refs": [], "desc": (c.description or "")[:80]})
    e["qty"] += mult; e["refs"].append(c.ref)
out = HERE.parent / f"rounds/full_bom_round{rnd}_upload.csv"
with open(out, "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["Mfr Part Number", "Manufacturer", "Quantity", "Customer Part Number", "Description"])
    for pn, e in rows.items():
        refs = e["refs"]; cp = refs[0] + (f"+{len(refs)-1}" if len(refs) > 1 else "")
        w.writerow([pn, e["mf"], e["qty"], cp, e["desc"]])
print(f"wrote {out} : {len(rows)} lines, {sum(e['qty'] for e in rows.values())} parts")
print("skipped generic:", dict(generic)); print("UNMAPPED:", dict(unmapped))
