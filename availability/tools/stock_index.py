"""Latest supplier stock / lead time per MPN, merged from every response round
(availability/responses/rN/{mouser.xlsx, farnell.xls, digikey.xlsx}).

    stock_index() -> {(supplier, NORM_MPN): {"stock", "lead_wk", "checked", "round"}}

supplier: "Mouser" | "Farnell" | "Digi-Key". Later rounds override earlier
ones; "checked" is the date the supplier file was saved (its mtime). Same
column mapping as boms.py.
"""
from __future__ import annotations

import datetime as _dt
import pathlib
import re

RESP = pathlib.Path(__file__).resolve().parents[1] / "responses"


def norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _num(s):
    s = re.sub(r"[^\d,.]", "", str(s or ""))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) != 3 else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _date(p: pathlib.Path) -> str:
    return _dt.date.fromtimestamp(p.stat().st_mtime).isoformat()


def _mouser(p, rnd, out):
    import openpyxl
    rows = list(openpyxl.load_workbook(p, read_only=True, data_only=True).worksheets[0]
                .iter_rows(values_only=True))
    if not rows:
        return
    i = {h: k for k, h in enumerate(rows[0])}
    key = next((k for k in ("Mouser OR Mfr. # (Input)", "Mfr. #", "Mfr Part Number") if k in i), None)
    if key is None:
        return
    for r in rows[1:]:
        g = lambda k: r[i[k]] if k in i and i[k] < len(r) else None
        if not g(key):
            continue
        out[("Mouser", norm(g(key)))] = dict(
            stock=int(_num(str(g("Availability") or "0").replace(".", "")) or 0),
            lead_wk=_num(g("Lead Time in Weeks")), checked=_date(p), round=rnd)


def _farnell(p, rnd, out):
    import xlrd
    sh = xlrd.open_workbook(p).sheet_by_index(0)
    i = {sh.cell_value(0, c): c for c in range(sh.ncols)}
    if "Mfr Part Number" not in i:
        return
    for r in range(1, sh.nrows):
        g = lambda k: sh.cell_value(r, i[k]) if k in i else ""
        q = g("BOM: Qualifier")
        if q and q not in ("Direct", "Voorgesteld"):
            continue
        if q == "Voorgesteld" and not (norm(g("BOM: Matched MPN")).startswith(norm(g("Mfr Part Number")))
                                       or norm(g("Mfr Part Number")).startswith(norm(g("BOM: Matched MPN")))):
            continue
        out[("Farnell", norm(g("Mfr Part Number")))] = dict(
            stock=int(_num(g("BOM: Stock Availability")) or 0),
            lead_wk=_num(g("BOM: Manufacturing Lead Time in weeks")), checked=_date(p), round=rnd)


def _digikey(p, rnd, out):
    import openpyxl
    rows = list(openpyxl.load_workbook(p, read_only=True, data_only=True).worksheets[0]
                .iter_rows(values_only=True))
    hdr = next((k for k, r in enumerate(rows) if r and "Requested Part Number" in r), None)
    if hdr is None:
        return
    i = {h: k for k, h in enumerate(rows[hdr])}
    for r in rows[hdr + 1:]:
        if not any(r) or not r[i["Manufacturer Part Number"]]:
            continue
        for key in {norm(r[i["Requested Part Number"]]), norm(r[i["Manufacturer Part Number"]])}:
            out[("Digi-Key", key)] = dict(
                stock=int(_num(r[i["Availability"]]) or 0),
                lead_wk=_num(r[i["Lead Weeks"]]) if "Lead Weeks" in i else None,
                checked=_date(p), round=rnd)


def stock_index(resp: pathlib.Path = RESP) -> dict:
    out: dict = {}
    rounds = sorted((d for d in resp.glob("r*") if d.is_dir() and d.name[1:].isdigit()),
                    key=lambda d: int(d.name[1:]))
    for d in rounds:
        for name, fn in (("mouser.xlsx", _mouser), ("farnell.xls", _farnell), ("digikey.xlsx", _digikey)):
            f = d / name
            if f.exists():
                try:
                    fn(f, d.name, out)
                except Exception as e:                      # one odd file must not stop the BOM
                    print(f"  WARN stock_index: {f.relative_to(resp.parent)}: {e}")
    return out


def lookup(idx: dict, mpn: str) -> dict:
    """{supplier: rec} for one MPN (exact normalised match, else a supplier
    record whose key starts with the MPN, e.g. a reel suffix)."""
    k = norm(mpn)
    res = {}
    for sup in ("Mouser", "Farnell", "Digi-Key"):
        rec = idx.get((sup, k))
        if rec is None and len(k) >= 6:
            cand = [v for (s, kk), v in idx.items() if s == sup and (kk.startswith(k) or k.startswith(kk) and len(kk) >= 8)]
            rec = max(cand, key=lambda v: int(v["round"][1:])) if cand else None
        if rec is not None:
            res[sup] = rec
    return res
