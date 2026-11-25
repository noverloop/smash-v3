import sys, csv, re, openpyxl, xlrd, os
HERE = __import__("pathlib").Path(__file__).resolve().parent
SP = sys.argv[1] if len(sys.argv) > 1 else str(HERE.parent / "responses")
OUT = sys.argv[2] if len(sys.argv) > 2 else str(HERE.parent)
N = lambda s: re.sub(r"[^A-Z0-9]", "", str(s).upper())
def num(s):
    s = re.sub(r"[^\d,.]", "", str(s or ""))
    if not s: return None
    if "," in s and "." in s: s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s: s = s.replace(",", ".") if len(s.split(",")[-1]) != 3 else s.replace(",", "")
    try: return float(s)
    except: return None
data = {}   # (supplier, key) -> rec ; later rounds override
def load(rnd):
    d = f"{SP}/{rnd}"
    if os.path.exists(f"{d}/mouser.xlsx"):
        mr = list(openpyxl.load_workbook(f"{d}/mouser.xlsx", read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
        mi = {h: i for i, h in enumerate(mr[0])}
        for r in mr[1:]:
            g = lambda k: r[mi[k]] if k in mi and mi[k] < len(r) else None
            if not g("Mouser OR Mfr. # (Input)"): continue
            data[("M", N(g("Mouser OR Mfr. # (Input)")))] = dict(st=num(str(g("Availability") or "0").replace(".", "")) or 0, lt=num(g("Lead Time in Weeks")),
                pr=num(str(g("Order Unit Price") or "").replace(".", "").replace(",", ".")),
                coo="/".join(dict.fromkeys(str(x) for x in (g("Country Of Origin"), g("Country Of Assembly"), g("Country Of Diffusion")) if x)), life=str(g("Lifecycle") or ""), rnd=rnd)
    if os.path.exists(f"{d}/farnell.xls"):
        sh = xlrd.open_workbook(f"{d}/farnell.xls").sheet_by_index(0); fi = {sh.cell_value(0, c): c for c in range(sh.ncols)}
        for r in range(1, sh.nrows):
            g = lambda k: sh.cell_value(r, fi[k])
            q = g("BOM: Qualifier")
            if q not in ("Direct", "Voorgesteld"): continue
            if q == "Voorgesteld" and not (N(g("BOM: Matched MPN")).startswith(N(g("Mfr Part Number"))) or N(g("Mfr Part Number")).startswith(N(g("BOM: Matched MPN")))): continue  # different part suggested
            data[("F", N(g("Mfr Part Number")))] = dict(st=num(g("BOM: Stock Availability")) or 0, lt=num(g("BOM: Manufacturing Lead Time in weeks")), pr=num(g("BOM: Unit Price(€)")),
                coo=str(g("BOM: Country of Origin")).strip(), life="", rnd=rnd)
    if os.path.exists(f"{d}/digikey.xlsx"):
        dr = list(openpyxl.load_workbook(f"{d}/digikey.xlsx", read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
        hdr = next(i for i, r in enumerate(dr) if r and "Requested Part Number" in r); di = {h: i for i, h in enumerate(dr[hdr])}
        for r in dr[hdr + 1:]:
            if not any(r) or not r[di["Manufacturer Part Number"]]: continue
            data[("D", N(r[di["Requested Part Number"]]))] = dict(st=num(r[di["Availability"]]) or 0, lt=num(r[di["Lead Weeks"]]), pr=num((r[di["Unit Price 1"]] if "Unit Price 1" in di else None)),
                coo=str(r[di["Country of Origin"]] or "").replace("None", ""), life=str(r[di["Part Status"]] or ""), rnd=rnd)
for rnd in ["r4", "r5", "r7", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]: load(rnd)   # later rounds override earlier

ACC = [  # line, refs, function, MPN, manufacturer, qty, library, fitted, note
 ("D_JUMP_WAKE / D_AON_WAKE", "D_JUMP_WAKE, D_JUMP_WAKE2, D_AON_WAKE, D_AON_WAKE2", "wake-OR Schottky", "BAS4002LE6327XTMA1", "Infineon", 4, "in repo", "fitted", "APPLIED in generator"),
 ("C_BAT_BULK1", "C_BAT_BULK1 (+1)", "battery bulk 470 uF 6.3 V polymer", "6TPE470MI", "Panasonic", 2, "need", "fitted", ""),
 ("C_BOOST_OUT1", "C_BOOST_OUT1", "boost output 47 uF 16 V polymer", "T521V476M016ATE070", "KEMET", 1, "need", "fitted", "promoted from alternate (R13)"),
 ("U_FIN1", "U_FIN1..U_FIN4", "fin dual H-bridge", "TC78H653FTG,EL", "Toshiba", 4, "need", "fitted", "new pin map vs DRV8428"),
 ("U_TMP1", "U_TMP1", "temperature sensor", "MCP9808T-E/MC", "Microchip", 1, "need", "fitted", "new pin map vs TMP117"),
 ("U_DEV_MCU", "U_DEV_G474", "dev-board MCU", "STM32U535CBU6", "STMicroelectronics", 1, "in repo", "fitted", "buy Mouser Taiwan lot (Digi-Key lot China); flash 128 KB"),
 ("C_TIA_A", "C_TIA_A (+3)", "8.2 pF C0G 0603", "C0603C829C5GACTU", "KEMET", 4, "in repo", "fitted", ""),
 ("C_WBA_HSE_BOT", "C_WBA_HSE_BOT", "10 pF C0G 0603", "C0603C100J5GACTU", "KEMET", 1, "in repo", "fitted", ""),
 ("C_LR_HF_RX", "C_LR_HF_RX (+1)", "0.8 pF C0G 0402 high-Q", "GJM1555C1HR80BB01D", "Murata", 2, "standard 0402", "fitted", ""),
 ("C_LR_HF_TX1", "C_LR_HF_TX1 (+1)", "1.2 pF C0G 0402 high-Q", "GJM1555C1H1R2BB01D", "Murata", 2, "standard 0402", "fitted", ""),
 ("C_XV_LNA_OUT", "C_XV_LNA_OUT", "5.1 pF C0G 0402 high-Q", "GJM1555C1H5R1BB01D", "Murata", 1, "standard 0402", "fitted", ""),
 ("C_ACTIVATE_SS", "C_ACTIVATE_SS (+1)", "47 nF X7R 0402", "GRM155R71E473KA88D", "Murata", 2, "standard 0402", "fitted", ""),
 ("L_XV_LNA_BIAS", "L_XV_LNA_BIAS", "1.8 nH 0402", "LQG15HS1N8S02D", "Murata", 1, "standard 0402", "fitted", ""),
 ("D_ACTIVATE", "D_ACTIVATE (+2)", "Schottky 60 V 1 A", "RB160VAM-60TR", "ROHM", 3, "in repo", "fitted", ""),
 ("Y_CAM_EXTCLK", "Y_CAM_EXTCLK", "27 MHz MEMS XO", "DSC1001CI1-027.0000", "Microchip", 1, "same footprint", "fitted", ""),
 ("U_XV_BOOST", "U_XV_BOOST", "5 V boost (S4 PA)", "MCP1640D-I/MC", "Microchip", 1, "same footprint", "fitted", "tube packaging"),
 ("U_AON_LDO", "U_AON_LDO (+1)", "3.3 V nano-Iq LDO", "XC6504A331MR-G", "Torex", 2, "in repo", "fitted", "single source: buy dev qty now"),
 ("U_COMP_PZ", "U_COMP_PZ", "nanopower comparator", "MCP6541T-E/OT", "Microchip", 1, "in repo", "fitted", ""),
 ("U_CAN_GW", "U_CAN_GW", "CAN FD transceiver", "TJA1462BTK/0Z", "NXP", 1, "need", "fitted", ""),
 ("U_DEV_ESD", "U_DEV_ESD", "USB ESD array", "USBLC6-4SC6", "STMicroelectronics", 1, "need", "fitted", ""),
 ("U_DEV_INA", "U_DEV_INA", "power monitor", "PAC1941T-1E/J6CX", "Microchip", 1, "need", "fitted", ""),
 ("QMAIN / Q_AON_EN", "QMAIN, Q_AON_EN", "P-FET load switch", "SSM3J372R,LF", "Toshiba", 2, "in repo", "fitted", "SOT-23F"),
 ("U_DDR3L", "U_DDR4 -> U_DDR3L", "DDR3L 4 Gb x16", "MT41K256M16TW-107 IT:P", "Micron", 1, "in repo", "fitted", "PMIC: BUCK6 1.35 V, drop LDO6, VREF 0.675 V"),
 ("QHOLD", "QHOLD (+32)", "N-FET small-signal 50 V", "RU1J002YNTCL", "ROHM", 33, "in repo", "fitted", "larger than BSS138AKM: face-fill check"),
 ("U_AWR_LDO18", "U_AWR_LDO18", "radar 1.8 V LDO", "XC6220B181MR-G", "Torex", 1, "need", "fitted", "thermal check (SOT-25 600 mW)"),
 ("Y_WBA_HSE", "Y_WBA_HSE", "32 MHz MEMS XO (kept)", "DSC1001CI5-032.0000", "Microchip", 1, "in repo", "fitted", "single source: buy dev qty now"),
 ("Y_AWR_HSE", "Y_AWR_HSE (+1)", "40 MHz MEMS XO", "SIT1602BI-12-18E-40.000000", "SiTime", 2, "SiT8008 2520 in repo (confirm pinout)", "fitted", "programmed to order"),
 ("Y_LR_TCXO", "Y_LR_TCXO", "32 MHz MEMS TCXO", "SiT5356AECFQ-33N0-32.000000T", "SiTime", 1, "in repo", "fitted", "SiTime direct; 3.3 V via load switch from VTCXO"),
 ("Y_LR_TCXO", "Y_LR_TCXO_ALT", "32 MHz quartz TCXO", "TG2016SMN 32.0000M-MCGNNM0", "Epson", 1, "in repo", "unfitted footprint", "dual footprint (user decision)"),
 ("U_CAM", "U_CAM", "RGB-NIR 5.1 MP GS/RS sensor", "VB1943CAJX/1", "STMicroelectronics", 1, "in repo", "fitted", "VCORE 1.15 V own rail"),
 ("J_DEV_USB", "J_DEV_USB", "USB-C 16P", "CX90B-16P", "Hirose", 1, "need", "fitted", ""),
 ("J_NOSE_USB", "J_NOSE_USB", "USB-C 24P", "CX90B1-24P", "Hirose", 1, "need", "fitted", ""),
 ("D_IR_WAKE", "D_IR_WAKE (+3)", "PIN photodiode 790-1050 nm", "VEMD5110X01", "Vishay", 4, "need", "fitted", "re-check wake margin (smaller area)"),
 ("U_MPU", "U_MPU", "main MPU (secure F, NPU)", "STM32MP257FAL3", "STMicroelectronics", 1, "in repo (MP255FAL footprint)", "fitted", "replaces STM32MP255FAL3 (0 stock); confirm AL ball map"),
 ("U_PMIC", "U_PMIC", "PMIC (kept)", "STPMIC25APQR", "STMicroelectronics", 1, "in repo", "fitted", "design relies on A-version NVM defaults"),
 ("U_WBA", "U_WBA", "wake/BLE MCU (kept)", "STM32WBA55UGI7", "STMicroelectronics", 1, "in repo", "fitted", "thin: buy dev qty now"),
 ("U_G0B1_FIN", "U_G0B1_FIN", "fin node MCU", "STM32U545REI6Q", "STMicroelectronics", 1, "need", "fitted", "replaces STM32G0B1REI6N; SMPS version: + inductor/caps"),
 ("U_H3LIS", "U_H3LIS", "high-g accelerometer (kept)", "H3LIS331DLTR", "STMicroelectronics", 1, "in repo", "fitted", ""),
 ("U_IMU", "U_IMU*", "IMU", "ISM330DLCTR", "STMicroelectronics", 1, "need", "fitted", "replaces ISM330DHCX (0 stock); check pinout + driver"),
 ("U_MAG", "U_MAG", "magnetometer", "BMM350", "Bosch Sensortec", 1, "need", "fitted", "replaces IIS2MDC (0 stock); WLCSP; check noise"),
 ("U_NAND", "U_NAND_A, U_NAND_B", "4 Gb SPI NAND (kept)", "MT29F4G01ABAFDWB-IT:F", "Micron", 2, "in repo", "fitted", ""),
 ("U_AWR", "U_AWR", "radar AoP (kept)", "AWR1843ARBGALPQ1", "Texas Instruments", 1, "in repo", "fitted", ""),
 ("U_DTC", "U_DTC*", "antenna tuning DTC", "PE64904D-Z", "pSemi", 1, "need", "fitted", "replaces PE64906B (0 stock); recheck matching"),
 ("U_XV_MIX", "U_XV_MIX", "S4 mixer", "ADL5801ACPZ-R7", "Analog Devices", 1, "need", "fitted", "replaces LTC5549 (restricted); mixer-stage redesign"),
 ("U_XV_PLL", "U_XV_PLL", "S4 synthesiser (kept)", "ADF4351BCPZ-RL7", "Analog Devices", 1, "in repo", "fitted", "order reel code"),
 ("U_XV_PA", "U_XV_PA", "S4 PA (kept)", "GRF5126", "Guerrilla RF", 1, "in repo", "fitted", "single maker: buy now"),
 ("U_XV_LNA", "U_XV_LNA", "S4 LNA (kept)", "GRF2073W", "Guerrilla RF", 1, "in repo", "fitted", "single maker: buy now"),
 ("U_LR", "U_LR", "LoRa transceiver (kept)", "LR2021IMLTRT", "Semtech", 1, "in repo", "fitted", ""),
 ("U_QPD", "U_QPD", "quadrant photodiode (kept)", "MT03-092", "Marktech", 1, "in repo", "fitted", "thin: buy now"),
 ("Q_ACT_ROW", "Q_PARACHUTE_CUTTER_ACTIVATE, Q_ACT_ROW0..3", "P-FET 60 V (kept)", "BUK6D120-60PX", "Nexperia", 5, "in repo", "fitted", ""),
 ("C_W107", "100 uF lines", "100 uF as 2 x 47 uF 1206", "GRM31CR60J476ME19L", "Murata", 2, "standard 1206", "fitted", "replaces T520W107 (China); qty per 100 uF position"),
 ("U_DEV_ISENSE", "U_DEV_ISENSE", "dev current sense (kept)", "INA241A2IDGKR", "Texas Instruments", 1, "in repo", "fitted", "dev-board only; 0 stock: order early"),
 ("C_WBA_PI", "C_WBA_PI1..3, C_WBA_PI2", "0.5 pF C0G 0402 high-Q", "GJM1555C1HR50BB01D", "Murata", 4, "standard 0402", "fitted", "C_WBA_PI2 0603 -> 0402"),
 ("C_LR_HF_TX2", "C_LR_HF_TX2", "1.0 pF C0G 0402 high-Q", "GJM1555C1H1R0BB01D", "Murata", 1, "standard 0402", "fitted", ""),
 ("C_XV_BPF_SH", "C_XV_BPF_SH", "1.1 pF C0G 0402 high-Q", "GJM1555C1H1R1BB01D", "Murata", 1, "standard 0402", "fitted", ""),
 ("C_AWR_CLKM", "C_AWR_CLKM", "100 pF C0G 0603", "C0603C101J5GACTU", "KEMET", 1, "standard 0603", "fitted", "replaces obsolete SQCS"),
 ("C_0402_100N", "~140 positions", "100 nF X7R 0402", "GRM155R71C104KA88D", "Murata", 140, "standard 0402", "fitted", "replaces C0402C104K3 (China lots)"),
 ("L_BOOST_COMP", "L_BOOST_COMP", "4.7 uH power inductor", "74438357047", "Wurth Elektronik", 1, "need", "fitted", "replaces Coilcraft XGL5020-472"),
 ("L_ACTIVATE", "L_ACTIVATE", "8.2 uH power inductor", "74438357082", "Wurth Elektronik", 1, "need", "fitted", "replaces Coilcraft XGL5020-822"),
 ("U_ACTIVATE_BOOST", "U_ACTIVATE_BOOST (+1)", "33 V boost", "TPS61175PWPR", "Texas Instruments", 2, "in repo", "fitted", "or TPS61175PWP (tube)"),
 ("U_AWR_FLASH", "U_AWR_FLASH", "radar QSPI NOR 8 Mb", "MX25V8035FZNI", "Macronix", 1, "need", "fitted", "confirm AWR1843 boot-ROM support"),
 ("Q_ISO", "Q_ISO, Q_DEV_TWR_PWR, Q_DEV_FLAT_PWR", "P-FET 12 V logic-level", "PMPB15XP,115", "Nexperia", 3, "in repo", "fitted", "replaces BUK6D120-60PX (not enhanced at cell V_GS); also PMPB15XPH (Mouser); confirm COO"),
 ("U_DEV_CAN", "U_DEV_CAN", "CAN FD transceiver (dev)", "TJA1462BTK/0Z", "NXP", 1, "need", "fitted", "replaces EOL TCAN1042GVDQ1"),
]
ALT = [  # line, for MPN, alternate MPN, manufacturer, why / caveat
 ("R_BAT_ISO", "ERJ-3BSFR20V", "UCR03EVPFLR200", "ROHM", "0.2 Ohm 0.25 W 0603"),
 ("C_BOOST_OUT", "GRM21BR61E226ME44L", "EMK212BBJ226MG-T", "Taiyo Yuden", "22 uF 16 V X5R 0805 1.25 mm on the 5 V rail; round 28: Farnell 15,572 + Digi-Key 32,237, Malaysia"),
 ("C_ACTIVATE_OUT", "GRM31CC72A475KE11L", "CGA5L1X7R2A475K160AC", "TDK", "4.7 uF 100 V X7R 1206 1.6 mm, AEC-Q200; round 26: Mouser 148,647, Japan"),
 ("C_BAT_BULK", "GRM21BR61A226ME51L", "C2012X5R1A226M125AB", "TDK", "22 uF 10 V X5R 0805 1.25 mm; round 25: Mouser 943, Japan"),
 ("U_DDR3L", "MT41K256M16TW-107 IT:P", "KTDM4G3C618BGIEAT", "SMARTsemi", "same JEDEC DDR3L x16 96-ball; -40..85 C"),
 ("U_DDR3L", "MT41K256M16TW-107 IT:P", "IS43TR16256BL-125KBLI", "ISSI", "DDR3L-1600; same JEDEC footprint"),
 ("C_BAT_BULK1", "6TPE470MI", "6TPF470MAH", "Panasonic", "same POSCAP family; confirm case/height"),
 ("C_BOOST_OUT1", "T521V476M016ATE070", "T520V476M016ATE070", "KEMET", "previous primary; same V case; Mouser lot only clean"),
 ("C_BOOST_OUT1", "T521V476M016ATE070", "T520D476M016ATE070", "KEMET", "D case, same 7343 land, taller"),
 ("D_JUMP_WAKE / D_AON_WAKE", "BAS4002LE6327XTMA1", "PMEG4002EL,315", "Nexperia", "SOD882 1.0x0.6; check wafer fab (Nexperia rule)"),
 ("U_DEV_MCU", "STM32U535CBU6", "STM32U535CCU6", "STMicroelectronics", "same pinout, 256 KB; Digi-Key lot Taiwan, Mouser lot China"),
 ("Y_WBA_HSE", "DSC1001CI5-032.0000", "SIT1602BI-12-33E-32.000000", "SiTime", "programmed to order; confirm pinout"),
 ("Y_AWR_HSE", "SIT1602BI-12-18E-40.000000", "DSC1001DI5-040.0000", "Microchip", "2.5 x 2.0 package (the 'C' code is 3.2 x 2.5 and does not fit the land); stock to check"),
 ("U_XV_BOOST", "MCP1640D-I/MC", "MCP1640DT-I/MC", "Microchip", "same chip, reel; Thailand"),
 ("U_CAM", "VB1943CAJX/1", "VB5943CAJX", "STMicroelectronics", "monochrome sibling, same footprint"),
 ("U_MPU", "STM32MP257FAL3", "STM32MP255CAL3", "STMicroelectronics", "secure C, 1.2 GHz; 0 stock in R10"),
 ("U_G0B1_FIN", "STM32U545REI6Q", "STM32U545REI6", "STMicroelectronics", "LDO version, different ball map; Farnell 18, Mouser due 2027-06"),
 ("U_G0B1_FIN", "STM32U545REI6Q", "STM32L443RCI6", "STMicroelectronics", "AES + DAC, all 3 suppliers in R12; different pinout"),
 ("U_PMIC", "STPMIC25APQR", "STPMIC25DPQR", "STMicroelectronics", "different NVM defaults; well stocked"),
 ("U_WBA", "STM32WBA55UGI7", "STM32WBA55UGI6", "STMicroelectronics", "-40..85 C"),
 ("U_H3LIS", "H3LIS331DLTR", "H3LIS100DLTR", "STMicroelectronics", "+/-100 g only"),
 ("U_IMU", "ISM330DLCTR", "ISM330BXTR", "STMicroelectronics", "Mouser only in R10"),
 ("U_NAND", "MT29F4G01ABAFDWB-IT:F", "W25N04KVZEIR", "Winbond", "check pinout/commands vs MP25 boot ROM"),
 ("U_NAND", "MT29F4G01ABAFDWB-IT:F", "MX35LF4GE4AD-Z4I", "Macronix", "check pinout/commands vs MP25 boot ROM"),
 ("U_DTC", "PE64904D-Z", "PE64102B-Z", "pSemi", "1.9-14 pF; Digi-Key stock"),
 ("U_XV_MIX", "ADL5801ACPZ-R7", "ADL5802ACPZ-R7", "Analog Devices", "dual-channel version"),
 ("Q_ACT_ROW", "BUK6D120-60PX", "DMP6110SVT-7", "Diodes Incorporated", "previous part, TSOT-26; buy Mouser Taiwan lot"),
]
SUP = [("M", "Mouser"), ("F", "Farnell"), ("D", "Digi-Key")]
def supcols(mpn, q):
    out = {}; good = []; lives = []; rnds = set()
    for k, name in SUP:
        v = data.get((k, N(mpn)))
        if v:
            rnds.add(v["rnd"])
            out.update({f"{name} stock": int(v["st"]), f"{name} lead wk": v["lt"] or "", f"{name} EUR": v["pr"] or "", f"{name} origin": v["coo"]})
            if v["life"] and v["life"] not in ("Active", "None", "New Product"): lives.append(f"{name[0]}:{v['life']}")
            if v["st"] >= q and v["coo"] and "china" not in v["coo"].lower(): good.append(name)
        else:
            out.update({f"{name} stock": "", f"{name} lead wk": "", f"{name} EUR": "", f"{name} origin": "not carried / not checked"})
    out["Stocked non-China at"] = " + ".join(good) or "-"
    out["Lifecycle flags"] = "; ".join(lives)
    out["Data from"] = ", ".join(sorted(r.replace("r", "round ") for r in rnds))
    return out
rows = []
for line, refs, fn, mpn, mf, q, lib, fit, note in ACC:
    rows.append({"Line": line, "Refs": refs, "Function": fn, "MPN": mpn, "Manufacturer": mf, "Qty per dev board": q, "Fitted": fit, "Library": lib, **supcols(mpn, q), "Note": note})
with open(f"{OUT}/bom_accepted.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
arows = []
for line, prim, mpn, mf, why in ALT:
    q = next(a[5] for a in ACC if a[3] == prim)
    arows.append({"Line": line, "Alternate for": prim, "Alternate MPN": mpn, "Manufacturer": mf, "Qty per dev board": q, **supcols(mpn, q), "Caveat": why, "Footprint": "none (sourcing only)"})
with open(f"{OUT}/bom_alternates.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(arows[0])); w.writeheader(); w.writerows(arows)
for r in rows: print(f"{r['MPN'][:28]:28} {r['Stocked non-China at']:26} {r['Data from']:18} {r['Lifecycle flags']}")
print("--- alternates")
for r in arows: print(f"{r['Alternate MPN'][:28]:28} {r['Stocked non-China at']:26} {r['Data from']}")
