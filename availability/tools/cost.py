"""Price the current maximalist design from every supplier round (EUR, small qty).

usage: python3 availability/tools/cost.py   → availability/rounds/cost_maximalist_<date>.csv
Per MPN: cheapest of Mouser / Farnell / Digi-Key in the latest round that answered
(small-quantity unit price), else the part record / earlier full-BOM USD price × 0.92.
Not included: battery cells (no TLM-1520HPM price on file), PCBs, sleeve, assembly."""
import sys, os, re, csv, glob, collections, json
REPO = "/Users/nicolas/Developer/202610Smash"
sys.path.insert(0, REPO); sys.path.insert(0, REPO + "/application/src")
import openpyxl, xlrd
N = lambda s: re.sub(r"[^A-Z0-9]", "", str(s).upper())
def num(s):
    s = re.sub(r"[^\d,.]", "", str(s or ""))
    if not s: return None
    if "," in s and "." in s: s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s: s = s.replace(",", ".") if len(s.split(",")[-1]) != 3 else s.replace(",", "")
    try: return float(s)
    except: return None
price = {}   # N(mpn) -> {supplier: (eur, round)}
def put(k, sup, pr, rnd):
    if pr and pr > 0: price.setdefault(k, {})[sup] = (pr, rnd)
rounds = sorted(glob.glob(f"{REPO}/availability/responses/r*"), key=lambda p: int(p.rsplit("r", 1)[1]))
for d in rounds:
    rnd = os.path.basename(d)
    try:
        if os.path.exists(f"{d}/mouser.xlsx"):
            mr = list(openpyxl.load_workbook(f"{d}/mouser.xlsx", read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
            mi = {h: i for i, h in enumerate(mr[0])}
            for r in mr[1:]:
                g = lambda k: r[mi[k]] if k in mi and mi[k] < len(r) else None
                key = g("Mfr Part Number") or g("Mouser OR Mfr. # (Input)")
                if key: put(N(key), "Mouser", num(str(g("Order Unit Price") or "").replace(".", "").replace(",", ".")), rnd)
                if g("Mouser OR Mfr. # (Input)"): put(N(g("Mouser OR Mfr. # (Input)")), "Mouser", num(str(g("Order Unit Price") or "").replace(".", "").replace(",", ".")), rnd)
    except Exception as e: print("mouser", rnd, e, file=sys.stderr)
    try:
        if os.path.exists(f"{d}/farnell.xls"):
            sh = xlrd.open_workbook(f"{d}/farnell.xls").sheet_by_index(0); fi = {sh.cell_value(0, c): c for c in range(sh.ncols)}
            for r in range(1, sh.nrows):
                g = lambda k: sh.cell_value(r, fi[k]) if k in fi else ""
                if g("BOM: Qualifier") != "Direct": continue
                put(N(g("Mfr Part Number")), "Farnell", num(g("BOM: Unit Price(€)")), rnd)
    except Exception as e: print("farnell", rnd, e, file=sys.stderr)
    try:
        if os.path.exists(f"{d}/digikey.xlsx"):
            dr = list(openpyxl.load_workbook(f"{d}/digikey.xlsx", read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
            hdr = next((i for i, r in enumerate(dr) if r and ("Requested Part Number" in r or "Manufacturer Part Number" in r)), None)
            if hdr is not None:
                di = {h: i for i, h in enumerate(dr[hdr])}
                pk = next((k for k in di if k and str(k).startswith("Unit Price")), None)
                for r in dr[hdr + 1:]:
                    if not r or not any(r): continue
                    for col in ("Manufacturer Part Number", "Requested Part Number"):
                        if col in di and r[di[col]]:
                            put(N(r[di[col]]), "Digi-Key", num(r[di[pk]]) if pk else None, rnd)
    except Exception as e: print("digikey", rnd, e, file=sys.stderr)
# recorded USD fallback from earlier full-BOM exports
rec_usd = {}
for f in glob.glob(f"{REPO}/availability/full_bom/*.csv"):
    for row in csv.DictReader(open(f, errors="ignore")):
        v = num(row.get("Recorded 1pc USD"))
        if v and row.get("MPN"): rec_usd[N(row["MPN"])] = v

import generate_stackup as g
d = g.Design(); g._set_battery_mode("maximalist"); g._prime_power_rails(d)
for fn in (g.build_qpd_module, g.build_radar_nose_io, g.build_usb_nose, g.build_camera_module, g.build_aft_end_board,
           g.build_activation_interface, g.build_radar_module_awr1843aop, g.build_companion_compute,
           g.build_power_board, g.build_wakeup_board, g.build_fins_module):
    fn(d)
from smash.parts.orderable import apply_orderable
apply_orderable(d)
USD2EUR = 0.92
lines = collections.OrderedDict()
for c in list(d.chips) + list(getattr(d, "batteries", []) or []):
    pn = getattr(c, "manf_pn", None)
    if not pn: continue
    if str(c.ref).startswith(("TP_", "P_CELL", "J_SLEEVE")) or str(pn).startswith("GENERIC"): continue
    L = lines.setdefault(N(pn), dict(pn=pn, manf=getattr(c, "manf", ""), qty=0, refs=[], board=collections.Counter(), usd=getattr(c, "price_1pc", None)))
    L["qty"] += 1; L["refs"].append(c.ref); L["board"][getattr(c, "board_tag", "?")] += 1
total = 0.0; unpriced = []; rows = []
for k, L in lines.items():
    sup = price.get(k, {})
    if sup:
        s, (pr, rnd) = min(sup.items(), key=lambda kv: kv[1][0]); src = f"{s} {rnd}"
    elif L["usd"]:
        pr, src = L["usd"] * USD2EUR, "part record (USD)"
    elif k in rec_usd:
        pr, src = rec_usd[k] * USD2EUR, "full-BOM record (USD)"
    else:
        pr, src = None, "-"
    ext = pr * L["qty"] if pr else 0.0
    total += ext
    if pr is None: unpriced.append(L)
    rows.append((ext, L["pn"], L["manf"], L["qty"], pr, src, dict(L["board"])))
rows.sort(key=lambda r: -r[0])
import datetime
out = f"{REPO}/availability/rounds/cost_maximalist_{datetime.date.today()}.csv"
with open(out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["MPN", "Manufacturer", "Qty", "Unit EUR", "Ext EUR", "Price source", "Boards"])
    for ext, pn, m, q, pr, src, b in rows:
        w.writerow([pn, m, q, f"{pr:.3f}" if pr else "", f"{ext:.2f}", src, "; ".join(f"{k}:{v}" for k, v in b.items())])
byboard = collections.Counter()
for ext, pn, m, q, pr, src, b in rows:
    if pr:
        for bt, n in b.items(): byboard[bt] += pr * n
print(f"lines {len(rows)}, parts {sum(r[3] for r in rows)}, priced lines {len(rows)-len(unpriced)}")
print(f"TOTAL priced parts: EUR {total:.2f}")
print("by board:", ", ".join(f"{k} {v:.0f}" for k, v in byboard.most_common()))
print("top 15:")
for ext, pn, m, q, pr, src, b in rows[:15]: print(f"  {ext:8.2f}  {q:>3} x {pr:8.3f}  {pn:<32} {src}")
print("UNPRICED:", ", ".join(f"{L['pn']} x{L['qty']}" for L in unpriced))
print("written", out)
