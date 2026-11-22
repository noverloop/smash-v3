"""Merge one round's Mouser / Farnell / Digi-Key BOM-upload answers.
usage: python3 compare4.py ../responses/rN ../rounds/problem_parts_roundN_upload.csv"""
import sys, csv, re, openpyxl, xlrd
SP, UP = sys.argv[1], sys.argv[2]
N = lambda s: re.sub(r"[^A-Z0-9]", "", str(s).upper())
def num(s):
    s = re.sub(r"[^\d,.]", "", str(s or ""))
    if not s: return 0.0
    if "," in s and "." in s: s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s: s = s.replace(",", ".") if len(s.split(",")[-1]) != 3 else s.replace(",", "")
    try: return float(s)
    except: return 0.0
mr = list(openpyxl.load_workbook(f"{SP}/mouser.xlsx", read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
mi = {h: i for i, h in enumerate(mr[0])}; M = {}
for r in mr[1:]:
    g = lambda k: r[mi[k]] if k in mi and mi[k] < len(r) else None
    if not g("Mouser OR Mfr. # (Input)"): continue
    M[N(g("Mouser OR Mfr. # (Input)"))] = dict(st=num(str(g("Availability") or "0").replace(".", "")), lt=g("Lead Time in Weeks"),
        pr=num(str(g("Order Unit Price") or "").replace(".", "").replace(",", ".")), coo="/".join(str(x) for x in (g("Country Of Origin"), g("Country Of Assembly"), g("Country Of Diffusion")) if x),
        life=str(g("Lifecycle") or ""), got=g("Mfr. #") or g("Manufacturer Part Number") or "")
sh = xlrd.open_workbook(f"{SP}/farnell.xls").sheet_by_index(0); fi = {sh.cell_value(0, c): c for c in range(sh.ncols)}; F = {}
for r in range(1, sh.nrows):
    g = lambda k: sh.cell_value(r, fi[k])
    if g("BOM: Qualifier") not in ("Direct", "Voorgesteld"): continue
    F[N(g("Mfr Part Number"))] = dict(st=num(g("BOM: Stock Availability")), lt=g("BOM: Manufacturing Lead Time in weeks"), pr=num(g("BOM: Unit Price(€)")),
        coo=str(g("BOM: Country of Origin")), life="", got=g("BOM: Matched MPN") + ("" if g("BOM: Qualifier") == "Direct" else " (sugg)"))
import os
dr = list(openpyxl.load_workbook(f"{SP}/digikey.xlsx", read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True)) if os.path.exists(f"{SP}/digikey.xlsx") else [("Requested Part Number",)]
hdr = next(i for i, r in enumerate(dr) if r and "Requested Part Number" in r); di = {h: i for i, h in enumerate(dr[hdr])}; D = {}; Dall = []
for r in dr[hdr + 1:]:
    if not any(r): continue
    rec = dict(st=num(r[di["Availability"]]), lt=r[di["Lead Weeks"]], pr=num((r[di["Unit Price 1"]] if "Unit Price 1" in di else None)), coo=str(r[di["Country of Origin"]] or ""),
               life=str(r[di["Part Status"]] or ""), got=r[di["Manufacturer Part Number"]] or "", req=r[di["Requested Part Number"]])
    Dall.append(rec)
    if rec["got"]: D[N(rec["req"])] = rec
print("Mouser cols:", [h for h in mr[0]][:40]) if "-v" in sys.argv else None
up = list(csv.DictReader(open(UP)))
seen = set()
def fmt(v):
    if not v: return f"{'-':>24}"
    return f"{int(v['st']):>7} {str(v['lt'] or '')[:4]:>4}w {v['pr']:>7.2f} {v['coo'][:9]:9}"
print(f"{'line':20} {'MPN':28} | {'MOUSER st lt price coo':^30} | {'FARNELL':^30} | {'DIGIKEY':^30} | life")
for x in up:
    k = N(x["Mfr Part Number"]); seen.add(k)
    m, f, d = M.get(k), F.get(k), D.get(k)
    life = " ".join(v["life"] for v in (m, d) if v and v["life"] and v["life"] not in ("Active", "New Product", "None"))
    print(f'{x["Customer Part Number"][:20]:20} {x["Mfr Part Number"][:28]:28} | {fmt(m)} | {fmt(f)} | {fmt(d)} | {life[:30]}')
print("\nDigi-Key rows not in the upload:")
for v in Dall:
    if N(v["req"]) not in seen: print("  ", v["req"], "->", v["got"], fmt(v), v["life"])
