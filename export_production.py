#!/usr/bin/env python3
"""Manufacturing package for the PCBA / tower assembler (2026-11-23, user).

Builds Manufacturing/<YYYYMMDD>/ against the assembler's data-exchange form
(VDL TBP "DATA EXCHANGE": PCBA doc, BOM, AML, PCB, Schematics, Mechanics) from
the generated outputs in dist/ (run generate_stackup.py + generate_devboard.py
first):

  README.md            structure + form item → file
  Common/              shared by every tower: ASSEMBLY (md/docx/pdf = repo-root
                       ASSEMBLY.md + generated appendix), Smash_BOM_common.xlsx
                       (5 core tiles; DNP sheet incl. the programmer strip),
                       Smash_AML.xlsx (all CPNs), PCB/ (production panel KiCad
                       project incl. schematics, stackup, spec, P&P, assembly
                       drawings; --fab adds ODB++ / Gerbers / IPC-D-356 once
                       routed), STEP/ + Drawings/ + Smash_materials.xlsx
  radar/ laser/        one folder per nose: payload-tile BOM, its LDS sleeve
  camera/              (unrolled KiCad + copper STEP), its own mechanical parts
                       (STEP + drawings + list), the complete tower STEP

Texts describe the current design only (no history); history_scan() warns.
The dev board itself is NOT part of the package. The production panel is
derived from the one design file (dist/dev_board/dev_board.kicad_pcb) here,
never kept as a second design file in dist/.

  python3 export_production.py [--date YYYYMMDD] [--force] [--no-drawings] [--fab]
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import io
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

REPO = pathlib.Path(__file__).resolve().parent
DIST = REPO / "dist"
DEVB = DIST / "dev_board"
MAXI = DIST / "maximalist"
ASSEMBLY_SRC = REPO / "ASSEMBLY.md"
CPN_REGISTRY = REPO / "availability" / "cpn_registry.csv"
ALTERNATES = REPO / "availability" / "bom_alternates.csv"
CHROME = pathlib.Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PANEL = "smash_panel"                 # name of the production KiCad project in the package
GH_LIMIT = 45 * 1024 * 1024           # zip anything bigger (GitHub warns at 50 MB, refuses 100 MB)


# ─────────────────────────────── helpers ────────────────────────────────────
def _git(*a) -> str:
    try:
        return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "?"


def _cli() -> str:
    import generate_stackup as G
    return str(G.find_kicad_cli())


def _run(cmd: list, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd[:4]))} …: {r.stderr.strip()[:400]}")
    return r


def _items(txt: str, start: int = 0, end: int | None = None):
    """(s, e) spans of the direct children of the S-expression list that
    opens at `start` (string-aware paren matching)."""
    end = len(txt) if end is None else end
    i, depth, s0, n = start, 0, None, end
    while i < n:
        c = txt[i]
        if c == '"':
            i += 1
            while i < n and txt[i] != '"':
                i += 2 if txt[i] == "\\" else 1
        elif c == "(":
            depth += 1
            if depth == 2:
                s0 = i
        elif c == ")":
            if depth == 2 and s0 is not None:
                yield s0, i + 1
                s0 = None
            depth -= 1
            if depth == 0:
                return
        i += 1


def _zip_dir(src: pathlib.Path, dst: pathlib.Path, arc_root: str) -> None:
    files = sorted(p for p in src.rglob("*") if p.is_file())
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            zi = zipfile.ZipInfo(f"{arc_root}/{p.relative_to(src).as_posix()}",
                                 date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, p.read_bytes())


def _copy_big(src: pathlib.Path, dst: pathlib.Path) -> pathlib.Path:
    """Copy as is: the package is shared as one encrypted archive
    (share_export.py), so large files are not zipped individually."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def _cam_field(md: str, key: str) -> str:
    m = re.search(rf"{key}:\s*(.+?)(?:\.\s|\n|$)", md)
    return m.group(1).strip() if m else ""


# ───────────────────────────── design data ──────────────────────────────────
def design_parts():
    """(tower parts, dev refs): every tower-tile part from the dev-board design
    (sections = the tower tiles before the dev board retags them)."""
    import generate_devboard as GD
    d, _removed, _locks = GD.build_design()
    tiles = set(GD.TILE_ORDER)
    tower = [c for c in d.chips if getattr(c, "board_tag", None) in tiles]
    # programmer strip + debug section; the aft cap's virtual contacts and the
    # SP_ scaffolds are dropped by the panel generator (no footprint) — skip them
    virt = {getattr(GD.G, "AFT_CAP", "aft_end_cap")}
    dev_chips = [c for c in d.chips if getattr(c, "board_tag", None) not in tiles | virt
                 and not c.ref.startswith("SP_")]
    return tower, {c.ref for c in dev_chips}, GD, dev_chips


def kr(ref: str) -> str:
    """The refdes as printed in the KiCad / ODB++ / P&P data (U_PMIC → U_PMIC1)."""
    from smash.export._common import kicad_ref
    return kicad_ref(ref)


def is_feature(c) -> bool:
    """PCB features drawn as footprints (castellations, lands, coils, pads):
    no component to buy or place."""
    m = (c.manf or "").strip().lower()
    pn = (c.manf_pn or "").strip().upper()
    return m in ("", "project", "pcb") or pn in ("CASTELLATIONS", "LGA_LANDS") or pn.startswith("SMASH_")


def _fmt_v(v) -> str:
    return f"{v:g}V" if v else ""


_TOL = {"B": "±0.1pF", "C": "±0.25pF", "D": "±0.5pF", "F": "1%", "G": "2%", "J": "5%", "K": "10%",
        "M": "20%"}
_KEMET_V = {"9": "6.3V", "8": "10V", "4": "16V", "3": "25V", "5": "50V", "1": "100V", "2": "200V", "A": "250V"}
_KEMET_D = {"R": "X7R", "G": "C0G", "P": "X5R", "U": "Z5U"}
_MUR_V = {"0J": "6.3V", "1A": "10V", "1C": "16V", "1E": "25V", "1H": "50V", "2A": "100V"}
_MUR_D = {"R7": "X7R", "R6": "X5R", "5C": "C0G", "C7": "X7S", "D7": "X7T"}
_SIZE = {"0201": "0201", "0402": "0402", "0603": "0603", "0805": "0805", "1206": "1206", "1210": "1210",
         "15": "0402", "18": "0603", "21": "0805", "31": "1206", "32": "1210", "03": "0201"}


def _cap_val(code: str) -> str:
    """3-char EIA code → '100nF' / '8.2pF'."""
    if "R" in code:
        v = code.replace("R", ".").rstrip("0").rstrip(".")
        return ("0" + v if v.startswith(".") else v) + "pF"
    pf = int(code[:2]) * 10 ** int(code[2])
    for div, u in ((1e6, "uF"), (1e3, "nF"), (1, "pF")):
        if pf >= div:
            return f"{pf / div:g}{u}"
    return f"{pf}pF"


def description_from_mpn(mpn: str) -> str | None:
    """Description decoded from the MPN for the passive families in the BOM
    (the design's value fields can still describe the generic placeholder)."""
    m = re.match(r"C(0201|0402|0603|0805|1206|1210)C(\w{3})([BCDFGJKM])(\w)(\w)A", mpn)
    if m:                                                        # KEMET C-series
        return " ".join(x for x in ("SMT CAP", _cap_val(m[2]), _KEMET_V.get(m[4], ""), m[1],
                                    _KEMET_D.get(m[5], ""), _TOL.get(m[3], "")) if x)
    m = re.match(r"(?:GRM|GJM|GCM)(\d\d)\w(\w\w)(\w\w)(\w{3})([BCDFGJKM])", mpn)
    if m:                                                        # Murata
        return " ".join(x for x in ("SMT CAP", _cap_val(m[4]), _MUR_V.get(m[3], ""), _SIZE.get(m[1], ""),
                                    _MUR_D.get(m[2], ""), _TOL.get(m[5], "")) if x)
    m = re.match(r"C(1005|1608|2012|3216|3225)(X7R|X5R|C0G|X7S|X7T|X6S)(\d\w)(\w{3})([BCDFGJKM])", mpn)
    if m:                                                        # TDK C-series
        size = {"1005": "0402", "1608": "0603", "2012": "0805", "3216": "1206", "3225": "1210"}[m[1]]
        return " ".join(x for x in ("SMT CAP", _cap_val(m[4]), _MUR_V.get(m[3], ""), size, m[2],
                                    _TOL.get(m[5], "")) if x)
    m = re.match(r"CL(05|10|21|31|32)([ABC])(\w{3})([BCDFGJKM])([A-Z])", mpn)
    if m:                                                        # Samsung CL
        size = {"05": "0402", "10": "0603", "21": "0805", "31": "1206", "32": "1210"}[m[1]]
        v = {"Q": "6.3V", "P": "10V", "O": "16V", "A": "25V", "B": "50V", "C": "100V"}.get(m[5], "")
        diel = {"A": "X5R", "B": "X7R", "C": "C0G"}[m[2]]
        return " ".join(x for x in ("SMT CAP", _cap_val(m[3]), v, size, diel, _TOL.get(m[4], "")) if x)
    m = re.match(r"(0402|0603)(\d)A(\w{3})([BCDFGJKM])AT", mpn)
    if m:                                                        # Kyocera AVX C0G
        v = {"5": "50V", "3": "25V", "1": "100V"}.get(m[2], "")
        return " ".join(x for x in ("SMT CAP", _cap_val(m[3]), v, m[1], "C0G", _TOL.get(m[4], "")) if x)
    m = re.match(r"CRCW(0402|0603|0805)(\w{4})([FJZ])[K0]", mpn)
    if m:                                                        # Vishay CRCW
        if m[3] == "Z":
            return f"SMT RES 0R jumper {m[1]}"
        pw = {"0402": "1/16W", "0603": "1/10W", "0805": "1/8W"}[m[1]]
        return f"SMT RES {_res_val(m[2])} {pw} {m[1]} {_TOL[m[3]]} TC100"
    m = re.match(r"RCWE(0402|0603)R(\d{3})FK", mpn)                # Vishay RCWE current sense
    if m:
        return f"SMT RES 0.{m[2].rstrip('0') or '0'}R {m[1]} 1% current-sense"
    m = re.match(r"T491([A-Z])(\d{3})([KM])(\d{3})", mpn)            # KEMET T491 tantalum
    if m:
        v = "6.3V" if m[4] == "006" else f"{int(m[4])}V"
        case = {"T": "3528-12 (case T)", "A": "3216-18", "B": "3528-21"}.get(m[1], m[1])
        return f"SMT CAP TANT {_cap_val(m[2]).replace('000nF', 'uF')} {v} {case} {_TOL[m[3]]}"
    return None


def _res_val(code: str) -> str:
    """Vishay 4-char value code: 10K0 → 10k, 2R20 → 2.2R, 0000 → 0R."""
    if code == "0000":
        return "0R (jumper)"
    for sep, u in (("K", "k"), ("M", "M"), ("R", "R")):
        if sep in code:
            a, b = code.split(sep)
            b = b.rstrip("0")
            return f"{a}{'.' + b if b else ''}{u}" if u != "R" else f"{a}{'.' + b if b else ''}R"
    return code


def description(c) -> str:
    """Unambiguous description (the form: value, voltage/power, package,
    dielectric/tolerance). Passives are decoded from the MPN; otherwise the
    part's own description."""
    d = description_from_mpn(c.manf_pn or "")
    if d:
        return d
    pkg = c.package or ""
    if getattr(c, "capacitance_f", None) or getattr(c, "resistance_ohm", None) is not None and (c.ref or "").startswith("R"):
        # generic fields may describe the placeholder, not the MPN: value + package only
        return " ".join(x for x in ("SMT CAP" if getattr(c, "capacitance_f", None) else "SMT RES",
                                    c.value or "", pkg, getattr(c, "dielectric", None) or "",
                                    "(per MPN)") if x)
    if getattr(c, "inductance_h", None):
        return " ".join(p for p in ["SMT IND", c.value or "", pkg, (c.description or "")[:80]] if p)
    return (c.description or c.value or c.manf_pn or "").replace("\n", " ")[:160]


def coo(c) -> str:
    """Country of origin as plain text (no source / date stamp)."""
    t = re.sub(r"\s*\([^()]*\)", "", getattr(c, "fab_country", "") or "")
    return re.sub(r"^origin\s+", "", t).strip()


def cpn_map(mpns: list) -> dict:
    """Customer part numbers from availability/cpn_registry.csv; new MPNs get
    the next free SMX-##### and are appended (CPNs never change)."""
    reg = {}
    if CPN_REGISTRY.exists():
        for row in csv.DictReader(CPN_REGISTRY.open()):
            reg[row["MPN"]] = row["CPN"]
    nxt = 1 + max([int(v.split("-")[1]) for v in reg.values()] or [0])
    new = []
    for m in sorted(set(mpns)):
        if m not in reg:
            reg[m] = f"SMX-{nxt:05d}"
            new.append((reg[m], m))
            nxt += 1
    if new:
        exists = CPN_REGISTRY.exists()
        with CPN_REGISTRY.open("a", newline="") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["CPN", "MPN", "Added"])
            for cpn, m in new:
                w.writerow([cpn, m, _dt.date.today().isoformat()])
    return reg


# ─────────────────────────────── BOM / AML ──────────────────────────────────
def _xl_sheet(wb, title, header, rows, widths=None):
    from openpyxl.styles import Font, PatternFill, Alignment
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
        c.alignment = Alignment(vertical="top", wrap_text=True)
    for r in rows:
        ws.append(list(r))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for i, h in enumerate(header):
        w = (widths or {}).get(h)
        if w is None:
            vals = [len(str(h))] + [len(str(r[i])) for r in rows[:400] if i < len(r)]
            w = min(60, max(8, max(vals) + 2))
        ws.column_dimensions[ws.cell(1, i + 1).column_letter].width = w
    return ws


_STOCK = None


def supply_cols(mpn: str) -> list:
    """[lead time wk, Mouser stock, Farnell stock, Digi-Key stock, checked] from
    the newest supplier response (availability/responses, stock_index).
    Lead time = the shortest factory lead time any of the three reports."""
    global _STOCK
    import sys as _sys
    if _STOCK is None:
        _sys.path.insert(0, str(REPO / "availability" / "tools"))
        import stock_index as _SI
        _STOCK = (_SI, _SI.stock_index())
    SI, idx = _STOCK
    recs = SI.lookup(idx, mpn or "")
    if not recs:
        return ["", "not checked", "not checked", "not checked", ""]
    leads = [r["lead_wk"] for r in recs.values() if r.get("lead_wk")]
    st = lambda sup: recs[sup]["stock"] if sup in recs else "not listed"
    return [int(min(leads)) if leads else "", st("Mouser"), st("Farnell"), st("Digi-Key"),
            max(r["checked"] for r in recs.values())]


def write_bom(out: pathlib.Path | None, tower: list, dev: set, tiles_order: list,
              only: list | None = None) -> dict:
    """BOM workbook for the tiles in `only` (all tiles when None); the
    programmer / debug DNP list only goes into the Common BOM (dev non-empty).
    out=None: compute only (the AML uses the full panel)."""
    from openpyxl import Workbook
    if only is not None:
        tower = [c for c in tower if c.board_tag in only]
        tiles_order = [t for t in tiles_order if t in only]
    fitted = [c for c in tower if not is_feature(c) and not getattr(c, "dnp", False)]
    dnp = [c for c in tower if not is_feature(c) and getattr(c, "dnp", False)]
    feats = [c for c in tower if is_feature(c)]
    cpn = cpn_map([c.manf_pn for c in fitted + dnp])
    groups: dict = {}
    for c in fitted:
        groups.setdefault(c.manf_pn, []).append(c)
    rows = []
    for mpn, cs in sorted(groups.items(), key=lambda kv: kv[1][0].ref):
        c0 = cs[0]
        refs = sorted(kr(c.ref) for c in cs)
        per_tile = {t: sum(1 for c in cs if c.board_tag == t) for t in tiles_order}
        note = []
        if (c0.manf or "").lower().startswith("steminc"):
            note.append("hand-attach after reflow, In52/Sn48 (ASSEMBLY §4)")
        if getattr(c0, "underfill", None) or _needs_underfill(c0):
            note.append("UNDERFILL")
        if needs_buffer(c0):
            note.append("BUFFER (silicone buffer coat, ASSEMBLY §3.2)")
        rows.append([cpn[mpn], ", ".join(refs), description(c0), len(cs), c0.manf or "", mpn,
                     c0.package or "", c0.value or "",
                     ", ".join(f"{t}×{n}" for t, n in per_tile.items() if n),
                     coo(c0), *supply_cols(mpn), "no", "no", "; ".join(note)])
    wb = Workbook()
    wb.remove(wb.active)
    hdr = ["CPN", "Reference designators", "Description", "Qty", "Manufacturer", "MPN",
           "Package", "Value", "Qty per tile", "Country of origin (supplier data)",
           "Lead time (wk)", "Mouser stock", "Farnell stock", "Digi-Key stock", "Stock checked",
           "ATEX certified", "UL/CSA certified", "Notes"]
    _xl_sheet(wb, "BOM", hdr, rows, {"Reference designators": 50, "Description": 60,
                                              "Qty per tile": 40, "Notes": 40})
    per = [[c.board_tag, kr(c.ref), cpn[c.manf_pn], c.manf or "", c.manf_pn, description(c)]
           for c in sorted(fitted, key=lambda c: (tiles_order.index(c.board_tag), c.ref))]
    _xl_sheet(wb, "Per tile", ["Tile", "Reference", "CPN", "Manufacturer", "MPN", "Description"], per,
              {"Description": 60})
    dn = [[c.board_tag, kr(c.ref), cpn[c.manf_pn], c.manf or "", c.manf_pn, description(c),
           "DNP by design (alternate / option footprint)"] for c in sorted(dnp, key=lambda c: c.ref)]
    dn += [["programmer strip / debug", kr(r), "", "", "", "", "DNP — not part of the production build"]
           for r in sorted(dev)]
    _xl_sheet(wb, "DNP", ["Tile", "Reference", "CPN", "Manufacturer", "MPN", "Description", "Why"], dn,
              {"Description": 50, "Why": 45})
    ft = [[c.board_tag, kr(c.ref), c.manf_pn or "", (c.description or "")[:120]]
          for c in sorted(feats, key=lambda c: (c.board_tag, c.ref))]
    _xl_sheet(wb, "PCB features (no part)", ["Tile", "Reference", "Feature", "Description"], ft,
              {"Description": 70})
    summ = [[t, sum(1 for c in fitted if c.board_tag == t),
             len({c.manf_pn for c in fitted if c.board_tag == t}),
             sum(1 for c in dnp if c.board_tag == t)] for t in tiles_order]
    summ.append(["TOTAL", len(fitted), len(groups), len(dnp)])
    _xl_sheet(wb, "Summary", ["Tile", "Placements", "Unique MPNs", "DNP (by design)"], summ)
    wb.move_sheet("Summary", offset=-4)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out)
    return {"fitted": fitted, "dnp": dnp, "feats": feats, "cpn": cpn, "groups": groups}


def write_aml(out: pathlib.Path, bom: dict) -> int:
    from openpyxl import Workbook
    alts: dict = {}
    if ALTERNATES.exists():
        for r in csv.DictReader(ALTERNATES.open()):
            alts.setdefault(r.get("Alternate for", ""), []).append(r)
    rows = []
    for mpn, cs in sorted(bom["groups"].items(), key=lambda kv: bom["cpn"][kv[0]]):
        c0 = cs[0]
        rows.append([bom["cpn"][mpn], c0.manf or "", mpn, "primary", ""])
        for a in alts.get(mpn, []):
            rows.append([bom["cpn"][mpn], a.get("Manufacturer", ""), a.get("Alternate MPN", ""),
                         "approved alternate", a.get("Caveat", "")])
    wb = Workbook()
    wb.remove(wb.active)
    _xl_sheet(wb, "AML", ["CPN", "Manufacturer", "MPN", "Status", "Caveat"], rows, {"Caveat": 70})
    wb.save(out)
    return len(rows)


_BUF_RE = re.compile(r"MEMS|accelerometer|gyro|\bIMU\b|magnetometer|oscillator|TCXO", re.I)


def needs_buffer(c) -> bool:
    """MEMS sensors + MEMS oscillators get the silicone buffer coat."""
    return bool(_BUF_RE.search(f"{c.description or ''} {c.manf_pn or ''}")) and not getattr(c, "dnp", False)


_UF_RE = re.compile(r"BGA|CSP|WLCSP|UCSP|FCCSP|DSBGA|AoP|AOP", re.I)


def _needs_underfill(c) -> bool:
    fp = getattr(c.footprint, "name", "") if c.footprint else ""
    t = f"{c.package or ''} {fp} {c.manf_pn or ''}"
    if re.search(r"LFCSP|QFN|DFN|SON", t, re.I):      # leadframe packages: no underfill
        return False
    return bool(_UF_RE.search(t))


# the programmable device itself (MCU / MPU / radar SoC / boot flash), by MPN
_PROG_RE = re.compile(r"^(STM32[A-Z0-9]|AWR\d|MT29F|MX25|W25Q|IS25|AT25)")


def appendix(bom: dict, tiles_order: list) -> str:
    fitted = bom["fitted"]
    L = ["", "## Appendix (generated from the design)", "",
         "### A. Tiles and part counts", "", "| Tile | Placements | Unique MPNs |", "|---|---|---|"]
    for t in tiles_order:
        cs = [c for c in fitted if c.board_tag == t]
        L.append(f"| {t} | {len(cs)} | {len({c.manf_pn for c in cs})} |")
    L.append(f"| **panel** | **{len(fitted)}** | **{len(bom['groups'])}** |")
    uf = sorted((c for c in fitted if getattr(c, "underfill", None) or _needs_underfill(c)),
                key=lambda c: (tiles_order.index(c.board_tag), c.ref))
    L += ["", "### B. Underfill + 100 % X-ray", "", "| Tile | Ref | MPN | Package | Underfill |",
          "|---|---|---|---|---|"]
    for c in uf:
        L.append(f"| {c.board_tag} | {kr(c.ref)} | {c.manf_pn} | {c.package or ''} | "
                 f"{(getattr(c, 'underfill', None) or 'Eccobond UF1173').replace('Hysol_FP4549_capillary_die_area', 'Hysol FP4549')} |")
    bf = sorted((c for c in fitted if needs_buffer(c)), key=lambda c: (tiles_order.index(c.board_tag), c.ref))
    L += ["", "### C. Silicone buffer coat (proposed, §3.2)", "", "| Tile | Ref | MPN | Part |", "|---|---|---|---|"]
    for c in bf:
        L.append(f"| {c.board_tag} | {kr(c.ref)} | {c.manf_pn} | {(c.description or '')[:70]} |")
    L += ["", "### D. DNP inside the tiles (by design)", "", "| Tile | Ref | MPN | |", "|---|---|---|---|"]
    for c in sorted(bom["dnp"], key=lambda c: c.ref):
        L.append(f"| {c.board_tag} | {kr(c.ref)} | {c.manf_pn} | {(c.description or '')[:70]} |")
    L += ["", "The programmer strip and the debug section are DNP in full (BOM sheet *DNP*).", ""]
    return "\n".join(L)


# ─────────────────────────── production panel ───────────────────────────────
def production_pcb_text(dev_txt: str, dnp_refs: set, apply_rout: bool = True) -> tuple[str, dict]:
    """The production panel from the one design file: the Production.Rout
    layer's rout polygons become Edge.Cuts, its mouse-bite marks NPTH drills,
    the dev board's rectangular outline goes, and every programmer / debug
    part (plus the by-design DNPs) gets the DNP flag."""
    import generate_devboard as GD
    prod = GD.PROD_LAYER
    spans = list(_items(dev_txt, 0))
    out, pos, n_rout, bites, n_dnp, n_outline = [], 0, 0, [], 0, 0
    for s, e in spans:
        blk = dev_txt[s:e]
        head = blk[1:12]
        new = blk
        if not apply_rout and not head.startswith("footprint"):
            pass                                                # dev board: outline + rout layer as drawn
        elif head.startswith("gr_line") and '(layer "Edge.Cuts")' in blk:
            new, n_outline = "", n_outline + 1                 # the dev board's rectangle
        elif head.startswith("gr_poly") and f'(layer "{prod}")' in blk:
            new = blk.replace(f'(layer "{prod}")', '(layer "Edge.Cuts")')
            n_rout += 1
        elif head.startswith("gr_circle") and f'(layer "{prod}")' in blk:
            m = re.search(r"\(center ([-\d.]+) ([-\d.]+)\)", blk)
            bites.append((float(m.group(1)), float(m.group(2))))
            new = ""
        elif head.startswith("footprint"):
            m = re.search(r'\(property "Reference" "([^"]*)"', blk)
            if m and m.group(1) in dnp_refs:
                a = re.search(r"\(attr ([^()]*)\)", blk)
                if a and "dnp" not in a.group(1).split():
                    new = blk[:a.start()] + f"(attr {a.group(1).strip()} dnp)" + blk[a.end():]
                elif not a:
                    lay = re.search(r'\(layer "[^"]+"\)', blk)
                    new = blk[:lay.end()] + "\n\t\t(attr dnp)" + blk[lay.end():]
                n_dnp += 1
        out.append(dev_txt[pos:s])
        out.append(new)
        pos = e
    out.append(dev_txt[pos:])
    txt = "".join(out)
    if bites:
        fps = [GD._fp_npth(f"MB{k + 1}", x, y, GD.MOUSE_BITE_D_MM, f"mb{k}")
               for k, (x, y) in enumerate(bites)]
        end = txt.rstrip().rfind(")")
        txt = txt[:end] + "\n".join(fps) + "\n" + txt[end:]
    return txt, {"rout": n_rout, "bites": len(bites), "dnp": n_dnp, "outline_removed": n_outline}


def write_pcb(pcb_dir: pathlib.Path, dnp_refs: set, cli: str, fab: bool = False,
              dnp_dev: set | None = None) -> dict:
    """PCB/: KiCad production project + ODB++ + Gerbers/drill + IPC-D-356 +
    pick & place + assembly drawings + stackup + spec."""
    kd = pcb_dir / "kicad"
    kd.mkdir(parents=True, exist_ok=True)
    dev_txt = (DEVB / "dev_board.kicad_pcb").read_text()
    txt, info = production_pcb_text(dev_txt, dnp_refs)
    pcb = kd / f"{PANEL}.kicad_pcb"
    pcb.write_text(txt)
    # (2026-11-23, user) the same board WITHOUT the production rout applied
    # (outline = the rectangle, rout + mouse bites on the Production.Rout user
    # layer) — for an assembler who panelises / routs the tiles themselves
    dev_out, _ = production_pcb_text(dev_txt, dnp_dev if dnp_dev is not None else dnp_refs,
                                     apply_rout=False)
    (kd / f"{PANEL}_dev_board.kicad_pcb").write_text(dev_out)
    # the rest of the KiCad project (schematic, libraries) under the panel name
    for src, dst in ((DEVB / "dev_board.kicad_sch", kd / f"{PANEL}.kicad_sch"),
                     (DEVB / "dev_board.kicad_pro", kd / f"{PANEL}.kicad_pro"),
                     (DEVB / "dev_board.kicad_sch", kd / f"{PANEL}_dev_board.kicad_sch"),
                     (DEVB / "dev_board.kicad_pro", kd / f"{PANEL}_dev_board.kicad_pro")):
        if src.exists():
            shutil.copy2(src, dst)
    for name in ("dev_board.kicad_sym", "fp-lib-table", "sym-lib-table", "empty.kicad_wks"):
        if (DEVB / name).exists():
            shutil.copy2(DEVB / name, kd / name)
    for sub in ("footprints", "3dmodels"):
        if (DEVB / sub).exists():
            shutil.copytree(DEVB / sub, kd / sub, dirs_exist_ok=True)
    # fab outputs
    if fab:   # (2026-11-23, user) only AFTER routing: ODB++, Gerbers, drill, netlist
        g = pcb_dir / "gerbers"
        g.mkdir(exist_ok=True)
        import generate_devboard as GD
        _run([cli, "pcb", "export", "gerbers", "--layers", ",".join(GD.FAB_LAYERS), "-o", f"{g}/", pcb])
        _run([cli, "pcb", "export", "drill", "--excellon-separate-th", "-o", f"{g}/", pcb])
        _run([cli, "pcb", "export", "odb", "-o", pcb_dir / f"{PANEL}_odb.zip", "--compression", "zip", pcb])
        _run([cli, "pcb", "export", "ipcd356", "-o", pcb_dir / f"{PANEL}_netlist.ipc", pcb])
    a = pcb_dir / "assembly"
    a.mkdir(exist_ok=True)
    for stem, src in ((PANEL, pcb), (f"{PANEL}_dev_board", kd / f"{PANEL}_dev_board.kicad_pcb")):
        for side in ("front", "back"):
            _run([cli, "pcb", "export", "pos", "--side", side, "--format", "csv", "--units", "mm",
                  "--exclude-dnp", "-o", a / f"{stem}_pick_and_place_{side}.csv", src])
        _run([cli, "pcb", "export", "pdf", "--mode-single", "--layers", "F.Fab,F.SilkS,Edge.Cuts",
              "--cdnp", "--sp", "--ibt", "--scale", "0", "-o", a / f"{stem}_assembly_top.pdf", src])
        _run([cli, "pcb", "export", "pdf", "--mode-single", "--layers", "B.Fab,B.SilkS,Edge.Cuts", "-m",
              "--cdnp", "--sp", "--ibt", "--scale", "0", "-o", a / f"{stem}_assembly_bottom.pdf", src])
    info["stackup"] = write_stackup(pcb_dir / "Smash_PCB_stackup.xlsx", txt)
    return info


def write_stackup(out: pathlib.Path, pcb_txt: str) -> int:
    from openpyxl import Workbook
    m = re.search(r"\(stackup(.*?)\(copper_finish \"([^\"]+)\"", pcb_txt, re.S)
    rows, total = [], 0.0
    if m:
        for lm in re.finditer(r'\(layer "([^"]+)" \(type "([^"]+)"\)([^\n]*)', m.group(1)):
            name, typ, rest = lm.groups()
            th = re.search(r"\(thickness ([\d.]+)\)", rest)
            mat = re.search(r'\(material "([^"]+)"\)', rest)
            er = re.search(r"\(epsilon_r ([\d.]+)\)", rest)
            tl = re.search(r"\(loss_tangent ([\d.]+)\)", rest)
            t = float(th.group(1)) if th else None
            total += t or 0.0
            rows.append([name, typ, t if t is not None else "", mat.group(1) if mat else "",
                         float(er.group(1)) if er else "", float(tl.group(1)) if tl else ""])
        rows.append(["TOTAL", "", round(total, 4), "", "", ""])
        rows.append(["Surface finish", m.group(2), "", "", "", ""])
    wb = Workbook()
    wb.remove(wb.active)
    _xl_sheet(wb, "Stackup", ["Layer", "Type", "Thickness (mm)", "Material", "εr", "tan δ"], rows)
    wb.save(out)
    return len(rows)


def pcb_spec_md(W, H, pcb: pathlib.Path, asm_dir: pathlib.Path, date: str) -> str:
    """The PCB specification in the industry "PCB Info Sheet" layout: General
    block, Parameter / Value / Notes table, appendices (stackup, via types,
    impedances). Values come from the panel file and its design rules."""
    txt = pcb.read_text() if pcb.exists() else ""
    m = re.search(r"\(stackup(.*?)\(copper_finish \"([^\"]+)\"", txt, re.S)
    stk, total, n_cu = [], 0.0, 0
    if m:
        for lm in re.finditer(r'\(layer "([^"]+)" \(type "([^"]+)"\)([^\n]*)', m.group(1)):
            name, typ, rest = lm.groups()
            th = re.search(r"\(thickness ([\d.]+)\)", rest)
            mat = re.search(r'\(material "([^"]+)"\)', rest)
            er = re.search(r"\(epsilon_r ([\d.]+)\)", rest)
            t = float(th.group(1)) if th else 0.0
            total += t
            n_cu += typ == "copper"
            nm = {(85.2, "prepreg"): "1080 prepreg RC71 %", (73.2, "prepreg"): "1080 prepreg RC66 %",
                  (127.0, "core"): "0.127 mm core (2 × 106) 18/18 µm",
                  (152.0, "core"): "0.152 mm core (1 × 1506) 18/18 µm",
                  (96.3, "prepreg"): "2113 prepreg RC58 %"}.get((round(t * 1000, 1), typ))
            if typ == "copper":
                nm = "18 µm base copper" + (" + plating" if t > 0.02 else "")
            stk.append(f"| {name} | {typ} | {t * 1000:.1f} | {nm or (mat.group(1) if mat else '')} | "
                       f"{er.group(1) if er else ''} |")

    def n_place(side):
        f = asm_dir / f"smash_panel_pick_and_place_{side}.csv"
        return max(0, len(f.read_text().splitlines()) - 1) if f.exists() else 0
    fp, bp = n_place("front"), n_place("back")
    rows = [
        ("Project number", "Smash", ""),
        ("PCB name", "Smash production panel", "one design: 8 round tiles + programmer strip; "
         "the dev board is the same panel with the tiles left in"),
        ("Part number", "assigned at order", ""),
        ("Circuits per array", "8 tiles + 1 programmer strip", f"panel {W} × {H} mm"),
        ("Prototype quantity", "TBD", ""),
        ("Batch quantity", "TBD", ""),
        ("Prototype lead time", "TBD", ""),
        ("Batch lead time", "TBD", ""),
        ("Number of copper layers", str(n_cu or 8), "HDI 2+4+2"),
        ("Standard layer stack", "No", "see Appendix A"),
        ("Minimum drill size PTH/NPTH", "200 µm", "mechanical vias, 450 µm pad, resin filled; "
         "castellations 400 µm"),
        ("Minimum laser hole", "150 µm", "microvia, 250 µm pad, copper filled (NCAB process 100 µm)"),
        ("Impedance-controlled traces", "Yes", "outer and inner layers, see Appendix C"),
        ("PCB length", f"{W} mm", "panel"),
        ("PCB width", f"{H} mm", "panel; tiles Ø34.0 mm"),
        ("Finished PCB thickness", f"{total:.3f} mm" if total else "0.868 mm", "± 10 %"),
        ("Base material", "FR4 high-Tg (Tg ≥ 170 °C)", "e.g. Isola 370HR, IT-180A; the PCB supplier "
         "can choose; prepregs and cores per Appendix A"),
        ("Outer-layer copper", "0.5 oz – 18 µm", "+ plating"),
        ("Inner-layer copper", "0.5 oz – 18 µm", ""),
        ("Total components", f"{fp + bp} placements ({fp} top, {bp} bottom)",
         "production build; the dev board adds the programmer strip parts"),
        ("Total holes", "fill in after routing", ""),
        ("Number of hole sizes", "fill in after routing", ""),
        ("Smallest hole size", "150 µm", "laser microvia"),
        ("Blind/buried vias", "Yes", "buried L2–L7 (mechanical, 200 µm / 450 µm); see Appendix B"),
        ("Microvias", "Yes", "laser 250 µm / 150 µm: L1–L2, L2–L3, L6–L7, L7–L8 (stacked allowed)"),
        ("Filled/capped vias", "Yes", "mechanical vias resin filled"),
        ("Filled and overplated vias", "Yes", "laser vias copper filled and capped; via-in-pad overplated"),
        ("Slotted holes", "Yes", "routed slots round each tile"),
        ("Minimum track width", "100 µm", ""),
        ("Minimum spacing", "75 µm", "BGA fan-out / DDR field; elsewhere ≥ 100 µm"),
        ("Number of SMD sides", "2", ""),
        ("Top solder mask", "Yes, green", "castellation pads tented on the tile faces"),
        ("Bottom solder mask", "Yes, green", ""),
        ("Top silkscreen", "Yes, white", ""),
        ("Bottom silkscreen", "Yes, white", ""),
        ("OSP ENTEK PLUS HT", "No", ""),
        ("HAL SnPb", "No", ""),
        ("Lead-free HAL", "No", ""),
        ("Chemical NiAu/ENIG", "Yes", "IPC-4552"),
        ("Chemical tin", "No", ""),
        ("Chemical silver", "No", ""),
        ("Gold fingers", "No", ""),
        ("Carbon finish", "No", ""),
        ("Full-surface galvanic gold", "No", ""),
        ("Press-fit holes", "No", ""),
        ("Inside routing", "Yes", "2 mm slot round each tile; 2.5 mm break tabs with 3 × Ø0.5 mm "
         "mouse bites"),
        ("Outside routing", "Yes", "panel outline milled"),
        ("V-scoring", "No", ""),
        ("Plated half-holes (castellations)", "Yes", "on every tile rim: Ø0.40 mm drill on the "
         "outline, Ø0.65 mm pad; plate, then rout"),
        ("Datum features", "Yes", "per tile: Ø3.0 mm NPTH (r 13 mm, 135°) and 1.2 × 1.0 mm rim notch "
         "(285°), ± 0.05 mm (stacking-fixture datums)"),
        ("UL certification and logo", "Yes", "on the programmer strip only, not on the tiles"),
        ("Date code", "Yes", "programmer strip"),
        ("Manufacturer logo", "Yes", "programmer strip"),
        ("Predefined marking/logo area", "Yes", "programmer strip"),
        ("Electrical test", "Yes", "100 % against the netlist (KiCad project)"),
        ("RoHS compliant", "Yes", ""),
        ("Suitable for lead-free processing", "Yes", ""),
        ("IPC-A-600 and IPC-6012 compliant", "Yes", "IPC-6012 Class 3"),
        ("IPC Class I", "No", ""),
        ("IPC Class II", "No", ""),
        ("IPC Class III", "Yes", ""),
        ("Leaded reflow", "No", ""),
        ("Lead-free reflow", "Yes", ""),
        ("Leaded wave soldering", "No", ""),
        ("Lead-free wave soldering", "No", ""),
        ("Selective wave soldering", "No", ""),
        ("Dimension tolerance", "Yes", "± 0.10 mm outline; ± 0.05 mm datum features"),
        ("Drill-diameter tolerance", "Yes", "± 0.05 mm PTH; ± 0.05 mm NPTH"),
        ("PCB-thickness tolerance", "Yes", f"{total:.3f} mm ± 10 %" if total else "± 10 %"),
    ]
    tab = "\n".join(f"| {a} | {b} | {c} |" for a, b, c in rows)
    stk_md = ("| Layer | Type | Thickness (µm) | Material | εr |\n|---|---|---|---|---|\n"
              + "\n".join(stk) + f"\n| **Total** | | **{total * 1000:.0f}** | | |") if stk else \
        "See `Smash_PCB_stackup.xlsx`."
    return f"""# Smash Electronics — PCB Info Sheet

| **General** | | | |
|---|---|---|---|
| Request by: | | Date: | {date[6:8]}-{date[4:6]}-{date[:4]} |
| Phone number: | | | |

| **Parameter** | **Value** | **Notes** |
|---|---|---|
{tab}

## Appendix A: Layer stackup

{stk_md}

Finish: {m.group(2) if m else 'ENIG'}. Full stackup with loss tangents: `Smash_PCB_stackup.xlsx`.

## Appendix B: Via types

| Via | Span | Drill / pad | Fill |
|---|---|---|---|
| Laser microvia | L1–L2, L2–L3, L6–L7, L7–L8 (stacking allowed) | 150 µm / 250 µm | copper filled; capped |
| Buried via | L2–L7 | 200 µm / 450 µm (mechanical) | resin filled, plated over |
| Through via | L1–L8 | 200 µm / 450 µm (mechanical) | resin filled; capped when in a pad |
| Castellation | L1–L8, on the tile outline | 400 µm / 650 µm | plated half-hole, not filled |

## Appendix C: List of required impedances

Structures as in NCAB's recommendation (Polar Si stack): soldermask-coated
outer structures, edge-coupled offset striplines inside.

| Impedance | Structure | Comments |
|---|---|---|
| 50 Ω ± 10 % | Coated coplanar waveguide with lower ground | L1 / L8 over L2 / L7: RF feeds (BLE 2.4 GHz, LoRa, 4.4–5.0 GHz transverter) to the antenna castellations |
| 55 Ω ± 10 % | Coated microstrip; offset stripline | DDR3L address / command / data (compute tile), outer and inner layers |
| 100 Ω ± 10 % | Edge-coupled coated microstrip; edge-coupled offset stripline | DDR3L clock and DQS; MIPI CSI-2 (camera module) |
| 90 Ω ± 10 % | Edge-coupled coated microstrip | USB 2.0 on the programmer strip (dev board) |

The PCB supplier adjusts trace widths to its process for these targets and reports the result with the order.
"""





# ─────────────────────────────── mechanics ──────────────────────────────────
def mech_parts(configs: dict, snake: list) -> list:
    """Every mechanical part: (key, step path, cam/notes text, qty per tower,
    configs, process). Common parts from dist/maximalist, per-config parts
    (payload ring, sleeve, nose, inserts, potting fixture) from each config."""
    parts = []

    def add(key, step, notes, qty, cfgs, process):
        if step and pathlib.Path(step).exists():
            parts.append(dict(key=key, step=pathlib.Path(step), notes=notes, qty=qty,
                              configs=cfgs, process=process))

    def notes_of(p):
        return p.read_text() if p and p.exists() else ""

    allc = list(configs)
    # battery holder + floor plate
    add("battery_holder", MAXI / "battery_holder" / "battery_holder.step",
        notes_of(MAXI / "battery_holder" / "battery_holder_cam.md"), 1, allc, "CNC machined")
    add("battery_floor_plate", MAXI / "battery_floor_plate" / "battery_floor_plate.step",
        notes_of(MAXI / "battery_floor_plate" / "battery_floor_plate_cam.md"), 1, allc, "CNC machined")
    # gap rings — per config (heights follow the parts in each gap); dedupe by content
    seen: dict = {}
    for cfg in configs:
        cdir = DIST / cfg
        for camf in sorted(cdir.glob("spacer_*/spacer_*_cam.md")):
            gap = camf.parent.name
            step = camf.parent / f"{gap}.step"
            if not step.exists():
                continue
            txt_ = camf.read_text()                       # same gap + same geometry = same part
            h = (gap, _cam_field(txt_, "Material"), _cam_field(txt_, "Geometry"))
            if h in seen:
                seen[h]["configs"].append(cfg)
                continue
            p = dict(key=gap if not any(x["key"] == gap for x in parts) else f"{gap}__{cfg}",
                     step=step, notes=camf.read_text(), qty=1, configs=[cfg], process="CNC machined")
            seen[h] = p
            parts.append(p)
    # aft cap
    ac = MAXI / "sleeve" / "aft_end_cap"
    add("aft_end_cap", ac / "aft_end_cap.step", notes_of(ac / "aft_end_cap.md"), 1, allc,
        "7075-T6 disc CNC + hard anodise; PEEK-LDS crown overmoulded onto it + LDS laser + Cu/Ni/Au plating")
    # sleeves / noses per config (variants: ir / laser)
    for cfg in configs:
        base = MAXI / "sleeve" / cfg
        variants = [base] if (base / "core_sleeve.step").exists() else sorted(
            p for p in base.glob("*") if (p / "core_sleeve.step").exists())
        for vdir in variants:
            tag = cfg if vdir == base else f"{cfg}_{vdir.name}"
            nn = notes_of(vdir / "nose_cam.md")
            for f in sorted(vdir.glob("*.step")):
                proc = ("injection moulded PEEK-LDS + LDS laser + Cu/Ni/Au plating"
                        if f.stem in ("core_sleeve", "nose_cap") else
                        "CNC / moulded natural (unfilled) PEEK, low loss at 77 GHz; bonded to the "
                        "radar tile with a closed EA 9466 bead (ASSEMBLY §5.2a)" if f.stem == "aop_dam" else
                        "CNC / moulded black PEEK (opaque); bonded to the payload tile with a closed "
                        "EA 9466 bead (ASSEMBLY §5.2a)" if f.stem == "optic_insert" else "see notes")
                if f.stem == "nose_assembly":
                    continue                              # assembly view, not a part
                add(f"{tag}__{f.stem}", f, nn, 1, [cfg], proc)
        pm = MAXI / "potting_mould" / cfg
        # (2026-11-23) the potting fixture is the assembler's design (nose-up on
        # the stacking base) — the generated nose-down cradle is not exported
        for f in []:
            if f.stem == "potting_fixture":               # = cradle + cap combined
                continue
            rel = f.relative_to(pm).with_suffix("").as_posix().replace("/", "_")
            add(f"{cfg}__potting_{rel}", f, notes_of(next(iter(sorted(f.parent.glob("*.md"))), None)),
                1, [cfg], "tooling (potting fixture, not a product part)")
    return parts


def material_of(notes: str) -> tuple[str, str]:
    mat = _cam_field(notes, "Material")
    fin = ""
    if "anodis" in mat.lower():
        fin = "hard anodised (Type III), sealed"
    if "LDS" in mat or "PEEK, LDS" in mat:
        fin = "LDS laser + electroless Cu + Ni/Au (hard gold on contact pads)"
    return mat, fin


def drawing_pdf(part: dict, out_pdf: pathlib.Path, date: str, commit: str) -> bool:
    """One generated drawing sheet per part: 3 projections from the STEP +
    title block (material, finish, tolerances, notes). The STEP is the master."""
    import cadquery as cq
    shape = cq.importers.importStep(str(part["step"]))
    bb = shape.val().BoundingBox()
    views = []
    for name, d in (("Top (+Z, nose side)", (0, 0, 1)), ("Side (+X)", (1, 0, 0)),
                    ("Isometric", (1, -1, 0.8))):
        buf = out_pdf.with_suffix(f".{len(views)}.svg")
        cq.exporters.export(shape, str(buf), opt={
            "width": 520, "height": 380, "marginLeft": 20, "marginTop": 20, "showAxes": False,
            "projectionDir": d, "strokeWidth": 0.15, "showHidden": name != "Isometric",
            "hiddenColor": (160, 160, 160)})
        views.append((name, buf.read_text()))
        buf.unlink()
    mat, fin = material_of(part["notes"])
    notes = re.sub(r"^#.*\n", "", part["notes"]).strip()
    import html as _h
    rows = "".join(f"<tr><th>{k}</th><td>{_h.escape(str(v))}</td></tr>" for k, v in (
        ("Part", part["key"]), ("Qty per tower", part["qty"]),
        ("Configurations", ", ".join(part["configs"])), ("Process", part["process"]),
        ("Material", mat or "see notes"), ("Finish", fin or "see notes"),
        ("Envelope (mm)", f"{bb.xlen:.2f} × {bb.ylen:.2f} × {bb.zlen:.2f}"),
        ("General tolerances", "ISO 2768-mK unless noted; fits and critical features per notes"),
        ("Frame", "tower frame: aft_end_board top view, 0° = +X, CCW; +Z toward the nose"),
        ("Master data", f"{part['step'].name} (STEP is the master geometry)"),
        ("Revision", f"{date} / commit {commit}")))
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Smash — drawing {_h.escape(part["key"])}</title><style>
@page {{ size: A3 landscape; margin: 10mm; }}
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #111; }}
h1 {{ font-size: 16pt; margin: 0 0 6mm; }}
.v {{ display: inline-block; width: 32%; vertical-align: top; border: 1px solid #999; margin: 0 0.5% 4mm 0; }}
.v h3 {{ font-size: 10pt; margin: 2mm; }} .v svg {{ width: 100%; height: auto; }}
table {{ border-collapse: collapse; width: 100%; }} th, td {{ border: 1px solid #999; padding: 1.5mm; text-align: left; vertical-align: top; }}
th {{ width: 22%; background: #eef2f7; }} pre {{ white-space: pre-wrap; font-size: 8.5pt; margin: 0; }}
</style></head><body><h1>Smash — {part['key']}</h1>
{''.join(f'<div class="v"><h3>{n}</h3>{s}</div>' for n, s in views)}
<table>{rows}<tr><th>Notes (from the generator's CAM notes)</th><td><pre>{_h.escape(notes)}</pre></td></tr></table>
</body></html>"""
    htmlf = out_pdf.with_suffix(".html")
    htmlf.write_text(page)
    ok = _html_to_pdf(htmlf, out_pdf)
    htmlf.unlink()
    return ok


_DOC_CSS = ("<style>body{font-family:Helvetica,Arial,sans-serif;font-size:10.5pt;max-width:180mm;"
            "margin:auto}table{border-collapse:collapse;font-size:9.5pt}td,th{border:1px solid #999;"
            "padding:3px 6px;vertical-align:top}th{background:#eef2f7}code{font-size:9.5pt}"
            "pre{white-space:pre-wrap}</style>")


def md_to_pdf(md: pathlib.Path, pdf: pathlib.Path) -> bool:
    """Markdown → standalone HTML (pandoc) → PDF (headless Chrome)."""
    title = next((l[2:].strip() for l in md.read_text().splitlines() if l.startswith("# ")), md.stem)
    hp = md.with_suffix(".tmp.html")
    try:
        _run(["pandoc", md, "-f", "gfm", "-s", "--metadata", f"pagetitle={title}",
              "-H", "/dev/stdin", "-o", hp], input=_DOC_CSS)
        return _html_to_pdf(hp, pdf)
    except Exception as e:
        print(f"  WARN pandoc {md.name}: {e}")
        return False
    finally:
        hp.unlink(missing_ok=True)


def _html_to_pdf(html: pathlib.Path, pdf: pathlib.Path) -> bool:
    if not CHROME.exists():
        return False
    r = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", html.resolve().as_uri()],
                       capture_output=True, text=True, timeout=180)
    return pdf.exists() and r.returncode == 0


MATERIALS = [
    # (category, material, grade / product, manufacturer, used for, process, key data / spec, status)
    ("PCB", "FR4 laminate + prepreg", "high-Tg FR4, Speedstack 1080 RC71 / RC66 prepregs", "PCB fab", "all tiles",
     "PCB fab", "stackup: PCB/Smash_PCB_stackup.xlsx", "specified"),
    ("PCB", "Copper foil", "ED 0.5 oz outer + plating, 0.5 oz inner", "PCB fab", "all tiles", "PCB fab", "", "specified"),
    ("PCB", "Surface finish", "ENIG", "PCB fab", "all tiles", "PCB fab", "IPC-4552", "specified"),
    ("PCBA", "Solder paste", "SAC305 (Sn96.5Ag3.0Cu0.5), type 4/5", "assembler's choice", "all SMT", "reflow",
     "lead-free", "specified"),
    ("PCBA", "Underfill", "Loctite Eccobond UF1173", "Henkel", "BGA / CSP (Appendix B)", "capillary, 5 min 150 °C",
     "", "specified"),
    ("PCBA", "Underfill", "Hysol FP4549 (or equivalent capillary)", "Henkel", "parts listed with FP4549 (ASSEMBLY App. B)", "capillary",
     "", "specified"),
    ("PCBA", "Low-temperature solder", "In52/Sn48 (118 °C)", "e.g. Indium Corp.", "piezo disc; cell leads",
     "hand / selective", "peak ≤ 145 °C", "specified"),
    ("PCBA", "Silicone buffer coat", "Dow SYLGARD 527 or Wacker SilGel 612", "Dow / Wacker",
     "MEMS sensors, MEMS oscillators (ASSEMBLY App. E)", "dispense, cure before potting",
     "thin dome 0.2-0.5 mm; Dow SYLGARD 527", "proposed"),
    ("PCBA", "Heat spreader adhesive", "Master Bond EP30AN-1 (thermally conductive epoxy)", "Master Bond",
     "camera_module 0.5 mm Al spreader", "bond", "", "proposed"),
    ("Tower", "Sleeve / aft cap / nose cap", "PEEK, LDS grade (Ensinger TECACOMP PEEK LDS)", "Ensinger",
     "sleeve, aft_end_cap crown, nose cap", "injection moulding (aft cap crown overmoulded onto its 7075 disc)", "εr 3.6, tan δ 0.002 @ 1 GHz (vendor)",
     "grade / colour to confirm"),
    ("Tower", "LDS metallisation", "electroless Cu + Ni + Au (hard gold on contact pads)", "LDS plater",
     "sleeve lanes, vias, antennas, crown contacts", "LDS laser + plating", "", "specified"),
    ("Tower", "Sleeve via fill", "Sn42Bi58 (138 °C)", "assembler's choice",
     "sleeve via ↔ castellation; aft-cap lane ↔ sleeve lane", "on the assembly fixture, before potting: CO2-laser via, "
     "residue clean, solder-jet / laser soldering", "", "proposed"),
    ("Tower", "Nose-cap adhesive", "Loctite EA 9466 structural epoxy (optional)", "Henkel",
     "nose cap press-fit", "applied before pressing; plasma activation of both PEEK faces for best bond",
     "", "optional"),
    ("Tower", "Aluminium", "7075-T6", "", "battery holder, floor plate, Al gap rings, aft cap disc", "CNC",
     "hard anodised (insulation)", "specified"),
    ("Tower", "PEEK GF30", "PEEK 30 % glass-filled, annealed after machining", "", "PEEK gap rings", "CNC",
     "break all edges (notch-sensitive)", "specified"),
    ("Tower", "Potting compound", "Loctite Stycast 1090 SI + Catalyst 23LV", "Henkel", "whole tower",
     "vacuum degas; cure 4-6 h @ 45 °C (or 16-24 h @ 25 °C), ≤ 85 °C",
     "low-density syntactic epoxy (SG 0.72, Shore D78); εr 2.16 / tanδ 0.018 @ 5 GHz (TDS); "
     "hollow microspheres: confirm vacuum / pressure limits", "selected — confirm by coupon tests"),
    ("Tower", "Screws", "M2 × 6 ISO 14580 low head, A2-70", "", "aft cap", "", "3 per tower", "proposed"),
    ("Tower", "Wire", "AWG 30 PTFE-insulated, silver-plated Cu", "", "cell + leads", "pre-wiring", "", "specified"),
    ("Tower", "Primary cells", "Tadiran TLM-1520HPM/P", "Tadiran", "battery (3 per tower)", "pre-wired",
     "Li-MnO2; ≤ 85 °C during assembly", "specified"),
    ("Tower", "Outer coat", "Parylene C, 15-25 µm", "parylene coating service", "whole tower outside incl. "
     "the nose-cap joint (aft cap contact crown masked)", "vapour deposition, room temperature", "sealing + lane insulation",
     "proposed"),
]


def write_materials(out: pathlib.Path, parts: list, common: bool) -> None:
    """Common: materials + common mechanical parts + purchased items;
    a payload folder: its own mechanical parts only."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    if common:
        _xl_sheet(wb, "Materials", ["Category", "Material", "Grade / product", "Manufacturer", "Used for",
                                    "Process", "Key data / spec", "Status"], MATERIALS,
                  {"Grade / product": 45, "Used for": 40, "Key data / spec": 40})
    rows = []
    for p in parts:
        mat, fin = material_of(p["notes"])
        geom = clean(_cam_field(p["notes"], "Geometry"))
        rows.append([p["key"], p["qty"], p["process"], mat, fin, f"STEP/{p['file']}",
                     f"Drawings/{pathlib.Path(p['file']).stem.replace('.step', '')}.pdf", geom[:300]])
    _xl_sheet(wb, "Mechanical parts", ["Part", "Qty per tower", "Process", "Material", "Finish", "STEP",
                                       "Drawing", "Geometry"], rows,
              {"Geometry": 80, "Material": 40})
    if common:
        bought = [["Tadiran TLM-1520HPM/P", "Tadiran", "TLM-1520HPM/P", 3, "pre-wired by the assembler"],
                  ["Screw M2 × 6 ISO 14580 A2-70 low head", "", "", 3, "aft cap"],
                  ["Wire AWG 30 PTFE", "", "", "≈ 3 × 40 mm", "cell + leads"],
                  ["Piezo disc Ø10 × 0.4 (Steminc SMD10T04R111)", "Steminc", "SMD10T04R111", 1,
                   "in the PCBA BOM (hand-attach)"]]
        _xl_sheet(wb, "Purchased mechanical", ["Item", "Manufacturer", "MPN", "Qty per tower", "Note"], bought)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)


# ─────────────────────────── text hygiene ───────────────────────────────────
# Outside-facing texts describe the CURRENT design only (user, 2026-11-23):
# no dates, "(user …)", "was", "no longer", "removed", "FIXED" …
_HIST_PAREN = re.compile(r"\s*\((?:[^()]*\b20\d\d-\d\d-\d\d\b[^()]*|user[^()]*)\)")
_HIST_WORDS = re.compile(r"\b(20\d\d-\d\d-\d\d|was|were|no longer|any ?more|removed|replaces?|"
                         r"replaced|formerly|previously|FIXED|retired|dropped|legacy|"
                         r"[Pp]arachute|[Nn]ichrome|[Cc]utter)\b")


def clean(text: str) -> str:
    """Strip dated / '(user …)' parentheticals from generated notes."""
    return _HIST_PAREN.sub("", text or "")


def set_pdf_titles(root: pathlib.Path) -> int:
    """Give every PDF a proper document title (viewers show it in the window
    bar): PDFs whose title is missing or just a file name (the HTML / KiCad
    renderers write "x.html" / "x.pdf") get one from their name and folder."""
    from pypdf import PdfReader, PdfWriter
    n = 0
    for pdf in sorted(root.rglob("*.pdf")):
        try:
            t = (PdfReader(str(pdf)).metadata or {}).get("/Title") or ""
        except Exception:
            continue
        if t and not re.search(r"\.(html|pdf)$", t.strip()):
            continue
        nose = pdf.relative_to(root).parts[0]
        nice = pdf.stem.replace("_", " ")
        nice = nice[:1].upper() + nice[1:]
        title = f"Smash {nose} — {nice}" if nose in FOLDER.values() else f"Smash — {nice}"
        w = PdfWriter(clone_from=str(pdf))
        w.add_metadata({"/Title": title})
        with open(pdf, "wb") as f:
            w.write(f)
        n += 1
    return n


def history_scan(root: pathlib.Path) -> list:
    """Lines in the package's text files that still read like design history."""
    hits = []
    for f in sorted(root.rglob("*")):
        if f.suffix.lower() not in (".md", ".csv", ".txt") or not f.is_file():
            continue
        for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            m = _HIST_WORDS.search(line)
            if m:
                hits.append(f"{f.relative_to(root)}:{i}: …{line[max(0, m.start() - 40):m.end() + 40]}…")
    return hits


# ───────────────────────────── payload folders ──────────────────────────────
FOLDER = {"core_radar": "radar", "core_qpd": "laser", "core_camera": "camera"}   # USB nose: deprecated
PAYLOAD_TITLE = {"core_radar": "radar nose (radar_module)",
                 "core_qpd": "laser seeker nose (qpd_module, quadrant photodiode)",
                 "core_camera": "camera nose (camera_module)",
                 }


def write_payload(d: pathlib.Path, cfg: str, tiles: set, core: set, snake: list, parts: list,
                  tower: list, tiles_order: list, date: str, commit: str, drawings: bool) -> dict:
    """<payload>/: README, BOM of the payload tile, its mechanical parts
    (STEP + drawings + list), its LDS sleeve, the full tower STEP."""
    d.mkdir(parents=True, exist_ok=True)
    stack = list(snake) + [t for t in tiles_order if t not in snake]   # payload tiles sit on top
    own_tiles = [t for t in stack if t in tiles and t not in core]
    order = [t for t in stack if t in tiles]
    bom = write_bom(d / f"Smash_BOM_{d.name}.xlsx", tower, set(), tiles_order, only=own_tiles)
    mine = [p for p in parts if p["home"] == cfg]
    for p in mine:                        # inside the nose folder the config prefix is redundant
        k = p["key"].replace(f"{cfg}__", "").replace(f"{cfg}_", "").replace("core_sleeve", "sleeve")
        p["key"] = k.replace("__", "_")
        p["file"] = _copy_big(p["step"], d / "STEP" / f"{p['key']}.step").name
    n_dr = 0
    if drawings:
        (d / "Drawings").mkdir(exist_ok=True)
        for p in mine:
            try:
                n_dr += drawing_pdf(p, d / "Drawings" / f"{p['key']}.pdf", date, commit)
            except Exception as e:
                print(f"  WARN drawing {p['key']}: {type(e).__name__}: {e}")
    write_materials(d / f"Smash_mechanics_{d.name}.xlsx", mine, common=False)
    full = DIST / f"stackup_{cfg}_components.step"
    full_out = _copy_big(full, d / f"{d.name}_tower.step") if full.exists() else None
    sleeve_files = []
    sd = DIST / cfg / "sleeve"
    if sd.exists():
        for f in sorted(sd.iterdir()):
            sleeve_files.append(_copy_big(f, d / "sleeve" / f.name.replace(cfg, d.name)).name)
    nose = ""
    base = MAXI / "sleeve" / cfg
    for nm in [base / "nose_cam.md"] + sorted(base.glob("*/nose_cam.md")):
        if nm.exists():
            body = clean(re.sub(r"^# .*\n", "", nm.read_text()))
            body = "\n".join(l for l in body.splitlines() if not l.lstrip("- ").startswith("⚠"))
            body = re.sub(r"\s*⚠[^.\n]*\.?", "", body)
            body = re.sub(r"\n## Warnings\n- none\n?", "\n", body)
            band = "" if nm.parent == base else f" — {nm.parent.name} band"
            nose += f"\n### Sleeve + nose cap{band}\n\n{body.strip()}\n"
    L = [f"# Smash — {d.name}: {PAYLOAD_TITLE[cfg]}", "",
         f"Package {date}, commit {commit}. Everything common to all noses is in `../Common/`.", "",
         f"Tower stack (aft → nose): {' → '.join(order)}", "",
         "## In this folder", "",
         f"- `Smash_BOM_{d.name}.xlsx` — PCBA BOM of the payload tile{'s' if len(own_tiles) > 1 else ''} "
         f"({', '.join(own_tiles)}): {len(bom['fitted'])} placements, {len(bom['groups'])} MPNs "
         "(same CPNs / AML as Common).",
         f"- `sleeve/` — this tower's LDS sleeve pattern: {', '.join(sleeve_files) or '—'} "
         "(unrolled 2-layer KiCad board: F.Cu = outer-face lanes, vias, antennas; the copper STEP "
         "is the same pattern wrapped on the sleeve for the LDS laser).",
         f"- `STEP/` + `Drawings/` + `Smash_mechanics_{d.name}.xlsx` — the mechanical parts only this "
         "nose uses:", ""]
    for p in mine:
        L.append(f"  - {p['key']} × {p['qty']} ({p['process']})")
    L += ["", "- `Assembly_steps.pdf` — the six assembly steps, one page each: 1 assembly nose down "
          "in the fixture (exploded), 2 sleeve vias + copper, 3 potting, 4 nose cap, 5 parylene coat, "
          "6 bench validation on the test fixture.",
          f"- `{full_out.name if full_out else '—'}` — the complete tower of this configuration "
          "(boards with parts, rings, holder, sleeve, nose) for reference.", ""]
    if nose:
        L += ["## Sleeve and nose", nose]
    (d / "README.md").write_text("\n".join(L) + "\n")
    # IKEA-style exploded view along the stacking pins
    n_ex = 0
    if drawings:
        try:
            from smash.export.exploded_view import write_assembly_pages
            base = MAXI / "sleeve" / cfg
            band = None if (base / "core_sleeve.step").exists() else next(
                (p.name for p in sorted(base.glob("*")) if (p / "core_sleeve.step").exists()), None)
            n_ex = write_assembly_pages(cfg, d / "Assembly_steps.pdf", _html_to_pdf, band=band,
                                        name=f"Smash {d.name}")
        except Exception as e:
            print(f"  WARN exploded view {cfg}: {type(e).__name__}: {e}")
    return {"bom": bom, "parts": len(mine), "drawings": n_dr, "exploded": n_ex}


PANEL_NOTE = """# Dev board and production board

One design, two builds (KiCad 10 projects in `kicad/`, board + schematics):

- **Dev board** — `kicad/smash_panel_dev_board.kicad_pro`: everything fitted
  (8 tower tiles + the development toolkit: programmer strip, debug section),
  rectangular outline, no tile cuts. The tile cuts are drawn on the
  *Production.Rout* user layer for reference.
- **Production board** — `kicad/smash_panel.kicad_pro`: the same design with the
  tile cuts applied (rout slots round each Ø34 tile on Edge.Cuts, mouse-bite NPTH
  drills in the drill file) and the development toolkit DNP: only the 8 tower
  tiles are fitted.
- Rout: 2 mm slot, its inner edge through the castellation hole centres →
  **castellated (plated half) holes** on every tile: plate, then rout.
- Break tabs: 2.5 mm, 3 × Ø0.5 mm mouse bites each, in castellation-free gaps.
- Every tile has a 1.2 × 1.0 mm rim notch at 285° (stacking-fixture datum) as
  part of its rout.
- Programmer strip + debug section (with the USB-C at the panel edge): fitted on
  the dev board; **DNP** on the production board, where it is scrap after
  depanelling. Copper outside the tiles carries nothing the tiles
  need.
- Fiducials: 3 per side (FID1-3 top, FID4-6 bottom), asymmetric.
"""


# ───────────────────────────────── main ─────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=_dt.date.today().strftime("%Y%m%d"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-drawings", action="store_true")
    ap.add_argument("--fab", action="store_true",
                    help="also ODB++ / Gerbers / drill / IPC-D-356 — only once the panel is ROUTED")
    args = ap.parse_args()
    sys.path[:0] = [str(REPO), str(REPO / "application" / "src")]
    out = REPO / "Manufacturing" / args.date
    if out.exists():
        if not args.force:
            print(f"{out} exists (use --force)")
            return 1
        shutil.rmtree(out)
    out.mkdir(parents=True)
    commit = _git("rev-parse", "--short", "HEAD")
    import generate_stackup as G
    configs = {k: set(v) for k, v in G.CONFIGS.items()}
    snake = list(G._MASTER_SNAKE)
    core = set.intersection(*configs.values())
    cli = _cli()

    tower, dev, GD, dev_chips = design_parts()
    tiles_order = list(GD.TILE_ORDER)
    core_tiles = [t for t in tiles_order if t in core]
    shipped = set().union(*(configs[c] for c in FOLDER))
    unshipped = {c.ref for c in tower if c.board_tag not in shipped}     # usb_nose tile: DNP on the panel
    tower = [c for c in tower if c.board_tag in shipped]
    print(f"design: {len(tower)} tower-tile parts, {len(dev)} programmer/debug parts (DNP)")

    com = out / "Common"
    bom_all = write_bom(None, tower, dev, tiles_order)
    bom_c = write_bom(com / "Smash_BOM_common.xlsx", tower, dev | unshipped, tiles_order, only=core_tiles)
    dev_tags = sorted({c.board_tag for c in dev_chips})
    bom_dev = write_bom(com / "Smash_BOM_dev_board.xlsx", tower + dev_chips, set(),
                        tiles_order + dev_tags)                  # the full dev board: toolkit fitted
    n_aml = write_aml(com / "Smash_AML.xlsx", bom_dev)
    print(f"BOM: common {len(bom_c['fitted'])} placements / {len(bom_c['groups'])} MPNs; "
          f"panel {len(bom_all['fitted'])} / {len(bom_all['groups'])}; AML {n_aml} rows")

    dnp_refs = {kr(r) for r in dev | unshipped} | {kr(c.ref) for c in bom_all["dnp"]}
    dnp_dev = {kr(r) for r in unshipped} | {kr(c.ref) for c in bom_dev["dnp"]}
    info = write_pcb(com / "PCB", dnp_refs, cli, fab=args.fab, dnp_dev=dnp_dev)
    W, H = getattr(GD, "PANEL_W_MM", None), getattr(GD, "PANEL_H_MM", None)
    (com / "PCB" / "PCB_SPECIFICATION.md").write_text(pcb_spec_md(
        W or 285, H or 102, com / "PCB" / "kicad" / "smash_panel.kicad_pcb",
        com / "PCB" / "assembly", args.date))
    (com / "PCB" / "PANEL_NOTES.md").write_text(PANEL_NOTE)
    print(f"PCB: production panel ({info['rout']} rout outlines, {info['bites']} mouse bites, "
          f"{info['dnp']} footprints DNP), "
          + ("ODB++, Gerbers, IPC-D-356, " if args.fab else "unrouted (no ODB++ / Gerbers yet), ")
          + "P&P, assembly PDFs")

    parts = mech_parts(configs, snake)
    for p in parts:                       # common = used by every configuration
        p["notes"] = clean(p["notes"])
        p["home"] = ("common" if set(p["configs"]) >= set(FOLDER) else
                     next((c for c in p["configs"] if c in FOLDER), "skip"))
    cparts = [p for p in parts if p["home"] == "common"]
    for p in cparts:
        p["file"] = _copy_big(p["step"], com / "STEP" / f"{p['key']}.step").name
    n_dr = 0
    if not args.no_drawings:
        (com / "Drawings").mkdir(exist_ok=True)
        for p in cparts:
            try:
                n_dr += drawing_pdf(p, com / "Drawings" / f"{p['key']}.pdf", args.date, commit)
            except Exception as e:
                print(f"  WARN drawing {p['key']}: {type(e).__name__}: {e}")
    write_materials(com / "Smash_materials.xlsx", cparts, common=True)
    print(f"Common mechanics: {len(cparts)} parts, {n_dr} drawings")

    for cfg, tiles in configs.items():
        if cfg not in FOLDER:
            continue
        r = write_payload(out / FOLDER[cfg], cfg, tiles, core, snake, parts, tower, tiles_order,
                          args.date, commit, not args.no_drawings)
        print(f"{FOLDER[cfg]}/: {len(r['bom']['fitted'])} placements, {r['parts']} parts, "
              f"{r['drawings']} drawings, assembly steps {r['exploded']} pages")

    # PCBA document: hand-written + generated appendix
    txt = ASSEMBLY_SRC.read_text()
    txt = txt.replace("# Smash tower — assembly instructions (PCBA → tower)",
                      f"# Smash tower — assembly instructions (PCBA → tower)\n\n"
                      f"*Package {args.date}, commit {commit}.*", 1) + appendix(bom_all, tiles_order)
    txt = re.sub(r"Maintained by hand in the repo root.*?\n\n", "", txt, count=1, flags=re.S)
    (com / "ASSEMBLY.md").write_text(txt)
    (out / "README.md").write_text(README.format(date=args.date, commit=commit))
    # KiCad's local-history / backup folders are not deliverables
    for junk in [*out.rglob(".history"), *out.rglob("*-backups")]:
        shutil.rmtree(junk, ignore_errors=True)
    hits = history_scan(out)
    if hits:
        print(f"  WARN {len(hits)} line(s) read like design history:")
        for h in hits[:40]:
            print("    " + h)
    # (2026-11-23, user) documents as PDF only — no .md in the package
    n_pdf = 0
    for md in sorted(out.rglob("*.md")):
        if md_to_pdf(md, md.with_suffix(".pdf")):
            md.unlink()
            n_pdf += 1
        else:
            print(f"  WARN could not convert {md.relative_to(out)} to PDF")
    print(f"documents: {n_pdf} PDF")
    set_pdf_titles(out)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"→ {out.relative_to(REPO)}  ({size / 1e6:.0f} MB)")
    return 0


README = """# Smash — manufacturing package {date}

The Smash tower is a potted stack of round PCBAs (Ø34 mm, 8-layer 2+4+2 HDI,
0.868 mm) powered by three primary lithium cells and wired board-to-board by a
laser-direct-structured PEEK sleeve. Five core tiles are in every tower:
aft_end_board (battery connection, launch sensing), activation_interface
(motion sensing: IMUs, high-g accelerometer, magnetometer, and the fin-control
MCU), wakeup_board (wake-up MCU with BLE, LoRa radio and transverter),
power_board (power conversion for all rails) and companion_compute
(STM32MP25 processor with DDR3L and NAND). On top sits one nose payload, which
sets the configuration: **radar** (TI AWR1843 77 GHz radar with antennas on
package), **laser** (quadrant-photodiode seeker, 1064 nm or 1550 nm lens
variant) or **camera** (ST VB1943 image sensor, 1064 nm or 850 nm lens
variant). Each configuration has its own sleeve and nose parts.

## Structure

- `Common/` — everything every tower shares: the PCBA document, the board (one
  design, supplied as the dev board and as the production board), the BOMs, the AML, the materials list,
  and the common mechanical parts (STEP + drawings).
- `radar/`, `laser/`, `camera/` — one folder per nose: the BOM of its
  payload tile, its LDS sleeve, its nose / ring / insert / potting-fixture
  parts (STEP + drawings + list) and the complete tower STEP. A tower = Common +
  one nose folder.

## Data-exchange form → files

| Form item | File(s) |
|---|---|
| **PCBA** — standards & approvals, special requirements, assembly instructions, test requirements | `Common/ASSEMBLY.pdf` (§2, §3, §4–5, §6) |
| **BOM** (Excel) — CPN, refdes, description, qty, manufacturer, MPN, lead time (wk), stock at Mouser / Farnell / Digi-Key with the date checked, ATEX, UL/CSA | dev board: `Common/Smash_BOM_dev_board.xlsx` (everything fitted). Production board: `Common/Smash_BOM_common.xlsx` (core tiles; DNP sheet = the development toolkit) + `<nose>/Smash_BOM_<nose>.xlsx` |
| **AML** (Excel) — CPN, manufacturer, MPN | `Common/Smash_AML.xlsx` (all CPNs) |
| PCB — dev board (KiCad 10, incl. schematics) | `Common/PCB/kicad/smash_panel_dev_board.kicad_pro` — everything fitted, rectangular outline; the tile cuts (slots, tabs, mouse bites) are drawn on the *Production.Rout* user layer |
| PCB — production board | `Common/PCB/kicad/smash_panel.kicad_pro` — the same design with the tile cuts applied and the development toolkit (programmer strip, debug section) DNP |
| PCB — assembly drawing incl. polarity, pick & place (preliminary) | `Common/PCB/assembly/` — `smash_panel_dev_board_*` and `smash_panel_*` (DNP crossed out / excluded) |
| PCB — layer stackup, specification | `Common/PCB/Smash_PCB_stackup.xlsx`, `PCB_SPECIFICATION.pdf`, `PANEL_NOTES.pdf` |
| **Schematics** | in the KiCad project (`Common/PCB/kicad/smash_panel.kicad_sch`) |
| **Mechanics** — STEP + PDF with tolerances / finish | `Common/STEP/`, `Common/Drawings/` + `<nose>/STEP/`, `<nose>/Drawings/` |
| Materials list, mechanical parts list | `Common/Smash_materials.xlsx` + `<nose>/Smash_mechanics_<nose>.xlsx` |

## Notes

- **One design, two builds:** the **dev board** (everything fitted, no tile cuts)
  and the **production board** (the same design with the tile cuts applied and
  the development toolkit DNP — only the 8 tower tiles fitted). P&P, assembly
  drawings and BOMs exist for both.
- Drawing sheets are generated from the STEP (views, envelope, material,
  finish, general tolerances ISO 2768-mK, notes); the STEP is the master
  geometry. Fully dimensioned drawings of the critical fits on request.
- Our proposals are marked **(proposed)** in `Common/ASSEMBLY.pdf` — please
  confirm or counter-propose in the quotation.
"""


if __name__ == "__main__":
    raise SystemExit(main())
