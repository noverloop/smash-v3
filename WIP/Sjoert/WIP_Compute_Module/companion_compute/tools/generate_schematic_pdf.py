#!/usr/bin/env python3
"""
generate_schematic_pdf.py - Companion Compute schematic PDF from the board netlist.

The smash flow writes the board directly (there is no .kicad_sch), so this script
rebuilds a readable, net-label style schematic from companion_compute.kicad_pcb:

  - every IC is split into functional units (DDR, GPIO ports, system, power ...)
    with ball number, pin name and the net on each pin; unused pins get an X
  - passives are drawn per function with their nets and values
  - connectors / LGA interfaces show every pad and its net
  - a net cross-reference closes the document

Pin names come from the KiCad symbols in application/src/smash/parts/sources/.

Usage:
    python tools/generate_schematic_pdf.py
    python tools/generate_schematic_pdf.py -o documentation/companion_compute_schematic.pdf

Requires: reportlab  (pip install reportlab)
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import re
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PROJECT_DIR = Path(__file__).resolve().parent.parent
PCB = PROJECT_DIR / "companion_compute.kicad_pcb"
OUT = PROJECT_DIR / "documentation" / "companion_compute_schematic.pdf"
PARTS = PROJECT_DIR.parent.parent / "application" / "src" / "smash" / "parts" / "sources"

SYMBOLS = {  # value -> symbol file (relative to PARTS)
    "STM32MP255DAL3": "STM32MP255DAL3/STM32MP255DAL3.kicad_sym",
    "KTDM4G4B626BGIEAT": "KTDM4G4B626BGIEAT/KTDM4G4B626BGIEAT.kicad_sym",
    "MT29F4G01ABAFDWB-IT_F": "MT29F4G01ABAFDWB-IT_F/MT29F4G01ABAFDWB-IT_F.kicad_sym",
    "SiT1630AE-S6-DCC-32.768E": "SiT1630AE-S6-DCC-32.768E/SiT1630AE-S6-DCC-32_768.kicad_sym",
    "DSC1001CI5-040.0000": "DSC1001CI5-008.0000/DSC1001CI5-008_0000.kicad_sym",
}
GROUND_NETS = {"FLEX_GND", "GND"}

# ------------------------------------------------------------------ fonts/colors
FONT, FONT_B = "Helvetica", "Helvetica-Bold"
for path in (r"C:\Windows\Fonts\arialn.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"):
    if Path(path).exists():
        pdfmetrics.registerFont(TTFont("Cond", path))
        FONT = "Cond"
        break
for path in (r"C:\Windows\Fonts\arialnb.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"):
    if Path(path).exists():
        pdfmetrics.registerFont(TTFont("CondB", path))
        FONT_B = "CondB"
        break

C_BOX = (1.0, 1.0, 0.76)      # symbol fill (classic yellow)
C_EDGE = (0.52, 0.0, 0.0)
C_PIN = (0.0, 0.0, 0.5)
C_NET = (0.55, 0.0, 0.0)
C_PWR = (0.75, 0.25, 0.0)
C_TXT = (0.1, 0.1, 0.1)
C_GRID = (0.6, 0.6, 0.6)
PAGE = landscape(A3)
PW, PH = PAGE
MARGIN = 10 * mm
PITCH = 3.3 * mm
PIN_LEN = 6 * mm
FS = 6.0  # pin font size


# ------------------------------------------------------------------ parsing
def natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def load_board(path: Path):
    text = path.read_text(encoding="utf-8")
    parts = []
    for m in re.finditer(r"^\t\(footprint \"([^\"]+)\"(.*?)^\t\)", text, re.S | re.M):
        body = m.group(2)
        prop = lambda k: (re.search(rf'\(property "{k}" "([^"]*)"', body) or [None, ""])[1]
        pads = {}
        for p in re.finditer(r'\(pad "([^"]*)"(.*?)\n\t\t\)', body, re.S):
            n = re.search(r'\(net (?:\d+ )?"([^"]*)"\)', p.group(2))
            if p.group(1):
                pads[p.group(1)] = n.group(1) if n else None
        descr = (re.search(r'\(descr "([^"]*)"', body) or [None, ""])[1]
        layer = re.search(r'\(layer "([^"]+)"\)', body).group(1)
        parts.append(dict(lib=m.group(1).split(":")[-1], ref=prop("Reference"), value=prop("Value"),
                          descr=descr, side="Top" if layer == "F.Cu" else "Bottom", pads=pads))
    return parts


def load_symbol(value: str) -> dict:
    rel = SYMBOLS.get(value)
    if not rel or not (PARTS / rel).exists():
        return {}
    s = (PARTS / rel).read_text(encoding="utf-8", errors="ignore")
    return {num: name for name, num in
            re.findall(r'\(pin \w+ \w+.*?\(name "([^"]*)".*?\(number "([^"]*)"', s, re.S)}


# ------------------------------------------------------------------ drawing
class Sheet:
    def __init__(self, c: canvas.Canvas, title: str, number: int, total: int, meta: dict):
        self.c, self.title = c, title
        self.number, self.total, self.meta = number, total, meta
        self.frame()

    def frame(self):
        c = self.c
        c.setStrokeColorRGB(*C_GRID)
        c.setLineWidth(0.6)
        c.rect(MARGIN / 2, MARGIN / 2, PW - MARGIN, PH - MARGIN)
        # zone markers
        c.setFont(FONT, 6)
        c.setFillColorRGB(*C_GRID)
        for i in range(8):
            x = MARGIN / 2 + (PW - MARGIN) * (i + 0.5) / 8
            c.drawCentredString(x, PH - MARGIN / 2 + 1.5, str(i + 1))
            c.drawCentredString(x, MARGIN / 2 - 6, str(i + 1))
        for i, ch in enumerate("ABCDEF"):
            y = PH - MARGIN / 2 - (PH - MARGIN) * (i + 0.5) / 6
            c.drawCentredString(MARGIN / 2 - 4, y, ch)
            c.drawCentredString(PW - MARGIN / 2 + 4, y, ch)
        # title block
        w, h = 120 * mm, 26 * mm
        x0, y0 = PW - MARGIN / 2 - w, MARGIN / 2
        c.setStrokeColorRGB(0.2, 0.2, 0.2)
        c.setFillColorRGB(1, 1, 1)
        c.rect(x0, y0, w, h, fill=1)
        for yy in (7 * mm, 13 * mm, 19 * mm):
            c.line(x0, y0 + yy, x0 + w, y0 + yy)
        c.line(x0 + 70 * mm, y0, x0 + 70 * mm, y0 + 13 * mm)
        c.setFillColorRGB(*C_TXT)
        c.setFont(FONT, 6)
        c.drawString(x0 + 2, y0 + 21.5 * mm, "Title")
        c.drawString(x0 + 2, y0 + 15.5 * mm, "Project")
        c.drawString(x0 + 2, y0 + 9.5 * mm, "Source")
        c.drawString(x0 + 2, y0 + 3.5 * mm, "Date")
        c.drawString(x0 + 72 * mm, y0 + 9.5 * mm, "Sheet")
        c.drawString(x0 + 72 * mm, y0 + 3.5 * mm, "Revision")
        c.setFont(FONT_B, 10)
        c.drawString(x0 + 16 * mm, y0 + 20.8 * mm, self.title)
        c.setFont(FONT, 8)
        c.drawString(x0 + 16 * mm, y0 + 14.8 * mm, "Smash Electronics – Companion Compute module")
        c.drawString(x0 + 16 * mm, y0 + 8.8 * mm, self.meta["source"])
        c.drawString(x0 + 16 * mm, y0 + 2.8 * mm, self.meta["date"])
        c.drawString(x0 + 84 * mm, y0 + 8.8 * mm, f"{self.number} of {self.total}")
        c.drawString(x0 + 84 * mm, y0 + 2.8 * mm, self.meta["rev"])

    def heading(self, text: str, x: float, y: float, size: float = 9):
        self.c.setFillColorRGB(0.1, 0.2, 0.45)
        self.c.setFont(FONT_B, size)
        self.c.drawString(x, y, text)

    def note(self, text: str, x: float, y: float, size: float = 6.5, color=C_TXT):
        self.c.setFillColorRGB(*color)
        self.c.setFont(FONT, size)
        for i, line in enumerate(text.split("\n")):
            self.c.drawString(x, y - i * (size + 1.6), line)

    # -------------------------------------------------------------- net label
    def net(self, x: float, y: float, name: str | None, right: bool):
        """Net label at the end of a pin. right=True: text grows to the right."""
        c = self.c
        if not name:
            c.setStrokeColorRGB(0.85, 0.0, 0.0)
            c.setLineWidth(0.6)
            d = 1.0 * mm
            c.line(x - d, y - d, x + d, y + d)
            c.line(x - d, y + d, x + d, y - d)
            return
        if name in GROUND_NETS:
            self.ground(x, y, right)
            return
        color = C_PWR if re.match(r"^(COMP_|V|3V3|5V|\d+V)", name) else C_NET
        c.setStrokeColorRGB(*C_PIN)
        c.setLineWidth(0.5)
        wtxt = pdfmetrics.stringWidth(name, FONT, FS)
        x2 = x + (wtxt + 4) * (1 if right else -1)
        c.line(x, y, x2, y)
        c.setFillColorRGB(*color)
        c.setFont(FONT, FS)
        if right:
            c.drawString(x + 2, y + 1.6, name)
        else:
            c.drawRightString(x - 2, y + 1.6, name)

    def ground(self, x: float, y: float, right: bool):
        c = self.c
        s = 1 if right else -1
        x1 = x + s * 3 * mm
        c.setStrokeColorRGB(*C_PIN)
        c.setLineWidth(0.5)
        c.line(x, y, x1, y)
        for i, half in enumerate((1.6, 1.0, 0.4)):
            xx = x1 + s * i * 0.7 * mm
            c.line(xx, y - half * mm, xx, y + half * mm)
        c.setFillColorRGB(*C_PWR)
        c.setFont(FONT, 4.5)
        tx = x1 + s * 2.6 * mm
        (c.drawString if right else c.drawRightString)(tx, y - 1.5, "GND")

    # -------------------------------------------------------------- IC unit
    def unit(self, x: float, top: float, ref: str, value: str, unit_name: str,
             left: list, right: list, width: float | None = None) -> float:
        """Draw an IC unit. left/right: [(ball, name, net)]. Returns bottom y."""
        c = self.c
        c.setFont(FONT, FS)
        name_w = max([pdfmetrics.stringWidth(n, FONT, FS) for _, n, _ in left] + [0]) + \
            max([pdfmetrics.stringWidth(n, FONT, FS) for _, n, _ in right] + [0])
        w = width or max(name_w + 12 * mm, 34 * mm)
        rows = max(len(left), len(right), 1)
        h = (rows + 1) * PITCH
        y0 = top - h
        c.setFillColorRGB(*C_BOX)
        c.setStrokeColorRGB(*C_EDGE)
        c.setLineWidth(0.8)
        c.rect(x, y0, w, h, fill=1)
        c.setFillColorRGB(*C_PIN)
        c.setFont(FONT_B, 7)
        c.drawString(x, top + 1.5, f"{ref}{unit_name}")
        c.setFont(FONT, 6)
        c.drawString(x, y0 - 7, value)
        for side, pins in ((0, left), (1, right)):
            for i, (ball, name, net) in enumerate(pins):
                y = top - (i + 1) * PITCH
                xe = x + w if side else x
                xo = xe + (PIN_LEN if side else -PIN_LEN)
                c.setStrokeColorRGB(*C_PIN)
                c.setLineWidth(0.5)
                c.line(xe, y, xo, y)
                c.setFillColorRGB(*C_PIN)
                c.setFont(FONT, 5)
                if side:
                    c.drawString(xe + 0.6, y + 1.4, ball)
                else:
                    c.drawRightString(xe - 0.6, y + 1.4, ball)
                c.setFillColorRGB(*C_TXT)
                c.setFont(FONT, FS)
                if side:
                    c.drawRightString(xe - 1.5, y - 1.8, name)
                else:
                    c.drawString(xe + 1.5, y - 1.8, name)
                self.net(xo, y, net, right=bool(side))
        return y0 - 4 * mm

    # -------------------------------------------------------------- passive
    def passive(self, x: float, y: float, part: dict) -> None:
        """Vertical two-terminal part, pin 1 on top. (x, y) = body centre."""
        c = self.c
        ref, val = part["ref"], short_value(part["value"])
        n1, n2 = part["pads"].get("1"), part["pads"].get("2")
        c.setStrokeColorRGB(*C_PIN)
        c.setLineWidth(0.6)
        is_cap = ref.startswith("C")
        body = 2.2 * mm
        c.line(x, y + body, x, y + 6 * mm)
        c.line(x, y - body, x, y - 6 * mm)
        if is_cap:
            c.setLineWidth(1.0)
            c.line(x - 2 * mm, y + 0.6 * mm, x + 2 * mm, y + 0.6 * mm)
            c.line(x - 2 * mm, y - 0.6 * mm, x + 2 * mm, y - 0.6 * mm)
            c.setLineWidth(0.6)
            c.line(x, y + 0.6 * mm, x, y + body)
            c.line(x, y - 0.6 * mm, x, y - body)
        else:
            c.setFillColorRGB(1, 1, 1)
            c.rect(x - 0.9 * mm, y - body, 1.8 * mm, 2 * body, fill=1)
        c.setFillColorRGB(*C_PIN)
        c.setFont(FONT_B, 5.5)
        c.drawString(x + 2.5 * mm, y + 0.5, ref)
        c.setFont(FONT, 5.5)
        c.drawString(x + 2.5 * mm, y - 6, val)
        self.vnet(x, y + 6 * mm, n1, up=True)
        self.vnet(x, y - 6 * mm, n2, up=False)

    def vnet(self, x: float, y: float, net: str | None, up: bool):
        c = self.c
        if net in GROUND_NETS:
            for i, half in enumerate((1.6, 1.0, 0.4)):
                yy = y - i * 0.7 * mm if not up else y + i * 0.7 * mm
                c.line(x - half * mm, yy, x + half * mm, yy)
            return
        if not net:
            self.net(x, y, None, True)
            return
        c.setFillColorRGB(*(C_PWR if re.match(r"^(COMP_|V|3V3|5V)", net) else C_NET))
        c.setFont(FONT, 5.2)
        c.saveState()
        c.translate(x, y + (1.5 if up else -1.5))
        c.rotate(90)
        if up:
            c.drawString(0, -1.8, net)
        else:
            c.drawRightString(0, -1.8, net)
        c.restoreState()


def short_value(v: str) -> str:
    m = re.search(r"(\d+(?:\.\d+)?\s*[pnuµ]F|\d+(?:\.\d+)?[kKM]?\b(?=\s*1%)|\d+[kKM]?(?= 1%))", v)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d+(?:\.\d+)?[kKM]?)\b\s*1%", v)
    return m.group(1) if m else v


# ------------------------------------------------------------------ layout helpers
def pinlist(part, sym, pred, order=None):
    pins = [(b, sym.get(b, b), part["pads"].get(b)) for b in part["pads"] if pred(sym.get(b, b))]
    pins.sort(key=order or (lambda p: natural(p[1])))
    return pins


def columns(sheet, units, x0, top, gap=12 * mm, bottom=40 * mm):
    """Place units left to right, wrapping into new columns when out of height."""
    x, y, col_w = x0, top, 0
    for title, ref, value, left, right in units:
        rows = max(len(left), len(right), 1)
        need = (rows + 1) * PITCH + 10 * mm
        if y - need < bottom and y != top:
            x += col_w + gap
            y, col_w = top, 0
        c = sheet.c
        c.setFont(FONT, FS)
        lw = max([pdfmetrics.stringWidth(n or "", FONT, FS) for *_, n in left] + [0]) + PIN_LEN + 8
        x_unit = x + lw
        y = sheet.unit(x_unit, y, ref, value, title, left, right)
        rw = max([pdfmetrics.stringWidth(n or "", FONT, FS) for *_, n in right] + [0]) + PIN_LEN + 8
        name_w = max([pdfmetrics.stringWidth(n, FONT, FS) for _, n, _ in left] + [0]) + \
            max([pdfmetrics.stringWidth(n, FONT, FS) for _, n, _ in right] + [0])
        col_w = max(col_w, lw + max(name_w + 12 * mm, 34 * mm) + rw)
        y -= 6 * mm
    return x + col_w


def passive_grid(sheet, parts, x0, y_top, cols=10, dx=26 * mm, dy=30 * mm, title=None):
    if title:
        sheet.heading(title, x0, y_top + 8 * mm, 8)
    for i, p in enumerate(sorted(parts, key=lambda p: natural(p["ref"]))):
        sheet.passive(x0 + (i % cols) * dx + 8 * mm, y_top - (i // cols) * dy - 10 * mm, p)
    rows = (len(parts) + cols - 1) // cols
    return y_top - rows * dy - 6 * mm


# ------------------------------------------------------------------ sheets
def build(parts, out: Path):
    by_ref = {p["ref"]: p for p in parts}
    mpu, ddr = by_ref["U_MPU"], by_ref["U_DDR4"]
    s_mpu, s_ddr = load_symbol(mpu["value"]), load_symbol(ddr["value"])
    passives = [p for p in parts if re.match(r"^[RC]_", p["ref"])]
    used = set()

    def take(pattern):
        sel = [p for p in passives if re.match(pattern, p["ref"]) and p["ref"] not in used]
        used.update(p["ref"] for p in sel)
        return sel

    ddr_pass = take(r"^(C_DDR|R_DDR|[CR]_MPU_DDR|C_MPU_QDDR)")
    nand_pass = take(r"^C_NAND")
    clk_pass = take(r"^C_MPU_(HSE|LSE)")
    sys_pass = take(r"^(R_MPU_|C_MPU_NRST|R_USB|C_USB)")
    pwr_pass = take(r"^C_")
    other_pass = [p for p in passives if p["ref"] not in used]

    is_gpio = lambda n: re.match(r"^P[A-Z]\d+$", n)
    is_pwr = lambda n: re.match(r"^(V|DNU|PDR)", n) and not n.startswith("VREF")
    is_ddr = lambda n: n.startswith("DDR_")

    sheets = []

    def sheet(title):
        def deco(fn):
            sheets.append((title, fn))
            return fn
        return deco

    meta = dict(source=PCB.name, date=dt.date.today().isoformat(),
                rev="generated from layout netlist")

    @sheet("Cover and block diagram")
    def _cover(sh):
        c = sh.c
        c.setFillColorRGB(0.1, 0.2, 0.45)
        c.setFont(FONT_B, 26)
        c.drawString(25 * mm, PH - 35 * mm, "Companion Compute – schematic")
        c.setFont(FONT, 11)
        c.setFillColorRGB(*C_TXT)
        c.drawString(25 * mm, PH - 44 * mm,
                     "STM32MP255 + 4 Gbit DDR4 (x16) + 2 × 4 Gbit SPI-NAND  ·  Ø34 mm, 20 copper layers")
        c.setFont(FONT, 8)
        c.drawString(25 * mm, PH - 51 * mm,
                     "Generated from the layout netlist (companion_compute.kicad_pcb); the smash flow has no "
                     "schematic capture. Same net name = connected.")
        sh.heading("Sheets", 25 * mm, PH - 66 * mm, 11)
        c.setFont(FONT, 9)
        for i, (t, _) in enumerate(sheets):
            c.drawString(28 * mm, PH - (74 + i * 6) * mm, f"{i + 1:>2}   {t}")
        # block diagram
        bx, by = 190 * mm, PH - 70 * mm
        blocks = {
            "U_MPU": (bx + 60 * mm, by - 70 * mm, 60 * mm, 50 * mm, "U_MPU\nSTM32MP255DAL3"),
            "U_DDR4": (bx + 160 * mm, by - 60 * mm, 45 * mm, 28 * mm, "U_DDR4\nDDR4 4 Gbit x16"),
            "U_NAND": (bx + 160 * mm, by - 120 * mm, 45 * mm, 28 * mm, "U_NAND_A / U_NAND_B\nSPI-NAND 4 Gbit"),
            "CLK": (bx + 60 * mm, by - 5 * mm, 60 * mm, 18 * mm, "Y_MPU_HSE 40 MHz\nY_MPU_LSE 32.768 kHz"),
            "PWR": (bx - 25 * mm, by - 130 * mm, 55 * mm, 26 * mm, "P_ power board\nLGA 66 lands"),
            "RADAR": (bx - 25 * mm, by - 70 * mm, 55 * mm, 22 * mm, "J_ radar module\nLGA 27 lands"),
            "CAM": (bx - 25 * mm, by - 30 * mm, 55 * mm, 18 * mm, "Camera flex\n11 pads"),
            "QPD": (bx + 60 * mm, by - 145 * mm, 60 * mm, 16 * mm, "QPD flex\n6 pads"),
        }
        def boxes():
          for x, y, w, h, label in blocks.values():
            c.setFillColorRGB(*C_BOX)
            c.setStrokeColorRGB(*C_EDGE)
            c.rect(x, y - h, w, h, fill=1)
            c.setFillColorRGB(*C_PIN)
            for j, line in enumerate(label.split("\n")):
                c.setFont(FONT_B if j == 0 else FONT, 9 if j == 0 else 7.5)
                c.drawCentredString(x + w / 2, y - h / 2 + 3 - j * 10, line)

        def link(a, b, text):
            xa, ya, wa, ha, _ = blocks[a]
            xb, yb, wb, hb, _ = blocks[b]
            pa = (xa + wa / 2, ya - ha / 2)
            pb = (xb + wb / 2, yb - hb / 2)
            c.setStrokeColorRGB(0.1, 0.2, 0.45)
            c.setLineWidth(1.2)
            c.line(*pa, *pb)
            c.setFillColorRGB(0.1, 0.2, 0.45)
            c.setFont(FONT, 7)
            mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
            tw = pdfmetrics.stringWidth(text, FONT, 7)
            c.setFillColorRGB(1, 1, 1)
            c.rect(mx - tw / 2 - 2, my - 2.5, tw + 4, 9, stroke=0, fill=1)
            c.setFillColorRGB(0.1, 0.2, 0.45)
            c.drawCentredString(mx, my, text)

        def count(r1, refs2):
            n1 = {n for n in by_ref[r1]["pads"].values() if n and n not in GROUND_NETS}
            n2 = set()
            for r in refs2:
                n2 |= {n for n in by_ref[r]["pads"].values() if n and n not in GROUND_NETS}
            return len(n1 & n2)

        ifc = {p["ref"]: p for p in parts if p["ref"].startswith(("P_", "J_"))}
        pick = lambda key: [r for r in ifc if key in r]
        link("U_MPU", "U_DDR4", f"{count('U_MPU', ['U_DDR4'])} nets")
        link("U_MPU", "U_NAND", f"{count('U_MPU', ['U_NAND_A', 'U_NAND_B'])} nets")
        link("U_MPU", "CLK", f"{count('U_MPU', ['Y_MPU_HSE', 'Y_MPU_LSE'])} nets")
        link("U_MPU", "PWR", f"{count('U_MPU', pick('power_board'))} nets")
        link("U_MPU", "RADAR", f"{count('U_MPU', pick('radar'))} nets")
        link("U_MPU", "CAM", f"{count('U_MPU', pick('camera'))} nets")
        link("U_MPU", "QPD", f"{count('U_MPU', pick('qpd'))} nets")
        boxes()

    @sheet("MPU – DDR4 interface")
    def _ddr(sh):
        left = pinlist(mpu, s_mpu, lambda n: re.match(r"DDR_(DQ|DQS|DQM)", n))
        right = pinlist(mpu, s_mpu, lambda n: is_ddr(n) and not re.match(r"DDR_(DQ|DQS|DQM)", n))
        x = 30 * mm
        sh.unit(x + 28 * mm, PH - 22 * mm, "U_MPU", mpu["value"], "  (DDR)", left, right)
        sig = lambda n: not re.match(r"^(VDD|VSS|VPP|VDDQ|VSSQ)", n)
        dl = pinlist(ddr, s_ddr, lambda n: sig(n) and re.match(r"^(DQ|DM|DQS)", n))
        dr = pinlist(ddr, s_ddr, lambda n: sig(n) and not re.match(r"^(DQ|DM|DQS)", n))
        sh.unit(225 * mm, PH - 22 * mm, "U_DDR4", ddr["value"], "  (signals)", dl, dr)
        pl = pinlist(ddr, s_ddr, lambda n: re.match(r"^(VDD|VPP)", n))
        pr = pinlist(ddr, s_ddr, lambda n: re.match(r"^VSS", n))
        sh.unit(345 * mm, PH - 22 * mm, "U_DDR4", ddr["value"], "  (power)", pl, pr, width=30 * mm)
        passive_grid(sh, ddr_pass, 25 * mm, 95 * mm, cols=14, dx=19 * mm, dy=34 * mm,
                     title="DDR support and decoupling")

    gpio_ports = sorted({re.match(r"P([A-Z])", s_mpu[b]).group(1)
                         for b in mpu["pads"] if is_gpio(s_mpu.get(b, ""))})
    half = (len(gpio_ports) + 1) // 2
    for chunk in (gpio_ports[:half], gpio_ports[half:]):
        @sheet(f"MPU – GPIO ports {chunk[0]}–{chunk[-1]}")
        def _gpio(sh, chunk=chunk):
            units = []
            for port in chunk:
                pins = pinlist(mpu, s_mpu, lambda n, port=port: re.match(rf"^P{port}\d+$", n))
                h = (len(pins) + 1) // 2
                units.append((f"  (GPIO P{port})", "U_MPU", mpu["value"], pins[:h], pins[h:]))
            columns(sh, units, 30 * mm, PH - 22 * mm, gap=30 * mm, bottom=PH - 160 * mm)

    @sheet("MPU – system, clocks, high-speed interfaces")
    def _sys(sh):
        rest = lambda n: not (is_gpio(n) or is_pwr(n) or is_ddr(n))
        pins = pinlist(mpu, s_mpu, rest)
        groups = collections.OrderedDict()
        for p in pins:
            key = re.match(r"^([A-Z]+)", p[1].replace("-", "")).group(1)
            key = {"NRST": "SYS", "NRSTCMS": "SYS", "BOOT": "SYS", "PWR": "SYS", "NJTRST": "DEBUG",
                   "JTDO": "DEBUG", "JTMS": "DEBUG", "JTDI": "DEBUG", "JTCK": "DEBUG", "OSC": "CLOCK",
                   "ANA": "ANALOG", "VREF": "ANALOG", "UCPD": "USB", "USBH": "USB", "USBDR": "USB"}.get(key, key)
            groups.setdefault(key, []).append(p)
        units = []
        for key, ps in groups.items():
            h = (len(ps) + 1) // 2
            units.append((f"  ({key})", "U_MPU", mpu["value"], ps[:h], ps[h:]))
        xe = columns(sh, units, 18 * mm, PH - 22 * mm, gap=8 * mm, bottom=95 * mm)
        y = 80 * mm
        sh.heading("Oscillators", 20 * mm, y + 8 * mm, 8)
        xo = 45 * mm
        for ref in ("Y_MPU_HSE", "Y_MPU_LSE"):
            p = by_ref[ref]
            s = load_symbol(p["value"])
            pins = [(b, s.get(b, b), n) for b, n in sorted(p["pads"].items(), key=lambda t: natural(t[0]))]
            h = (len(pins) + 1) // 2
            sh.unit(xo, y, ref, p["value"], "", pins[:h], pins[h:])
            xo += 95 * mm
        passive_grid(sh, clk_pass + sys_pass + other_pass, 230 * mm, 88 * mm, cols=7, dx=24 * mm, dy=34 * mm,
                     title="Reset, boot, bias and clock decoupling")

    @sheet("MPU – power")
    def _pwr(sh):
        vdd = pinlist(mpu, s_mpu, lambda n: is_pwr(n) and not n.startswith("VSS"))
        vss = pinlist(mpu, s_mpu, lambda n: n.startswith("VSS"))
        h = (len(vdd) + 1) // 2
        sh.unit(45 * mm, PH - 22 * mm, "U_MPU", mpu["value"], "  (supply)", vdd[:h], vdd[h:])
        h2 = (len(vss) + 1) // 2
        sh.unit(205 * mm, PH - 22 * mm, "U_MPU", mpu["value"], "  (ground)", vss[:h2], vss[h2:])
        passive_grid(sh, pwr_pass, 280 * mm, PH - 30 * mm, cols=5, dx=24 * mm, dy=34 * mm,
                     title="MPU decoupling")

    @sheet("Boot storage – SPI-NAND")
    def _nand(sh):
        x = 70 * mm
        for ref in ("U_NAND_A", "U_NAND_B"):
            p = by_ref[ref]
            s = load_symbol(p["value"])
            pins = [(b, s.get(b, b), n) for b, n in sorted(p["pads"].items(), key=lambda t: natural(t[0]))]
            sh.unit(x, PH - 40 * mm, ref, p["value"], "", pins[:4], pins[4:][::-1])
            x += 170 * mm
        passive_grid(sh, nand_pass, 70 * mm, PH - 120 * mm, cols=6, dx=40 * mm, title="Decoupling")
        sh.note("Both devices share the MPU OCTOSPI/SPI bus; chip selects are separate nets.",
                70 * mm, PH - 190 * mm)

    @sheet("Board interfaces – LGA and flex")
    def _ifc(sh):
        units = []
        for p in sorted((p for p in parts if p["ref"].startswith(("P_", "J_"))), key=lambda p: p["ref"]):
            pins = [(b, f"pad {b}", n) for b, n in sorted(p["pads"].items(), key=lambda t: natural(t[0]))]
            h = (len(pins) + 1) // 2
            short = re.sub(r"companion_compute_?_?", "", p["ref"]).strip("_")
            units.append(("", short, p["value"], pins[:h], pins[h:]))
        columns(sh, units, 25 * mm, PH - 22 * mm, gap=14 * mm, bottom=35 * mm)

    # net cross-reference (as many sheets as needed)
    nets = collections.defaultdict(list)
    for p in parts:
        for pad, n in p["pads"].items():
            if n:
                nets[n].append(f"{p['ref']}.{pad}")
    rows = []
    for n in sorted(nets, key=natural):
        conns = sorted(nets[n], key=natural)
        text = ", ".join(conns)
        if n in GROUND_NETS or len(conns) > 40:
            refs = collections.Counter(c.split(".")[0] for c in conns)
            text = f"{len(conns)} pins: " + ", ".join(f"{r} ×{k}" for r, k in sorted(refs.items()))
        rows.append((n, len(conns), text))
    per_page = 2 * 68
    pages = [rows[i:i + per_page] for i in range(0, len(rows), per_page)]
    for k, chunk in enumerate(pages):
        @sheet(f"Net cross-reference ({k + 1}/{len(pages)})")
        def _xref(sh, chunk=chunk):
            c = sh.c
            for col in range(2):
                part_rows = chunk[col * 68:(col + 1) * 68]
                x = 15 * mm + col * 200 * mm
                y = PH - 18 * mm
                c.setFont(FONT_B, 6.5)
                c.setFillColorRGB(0.1, 0.2, 0.45)
                c.drawString(x, y, "Net")
                c.drawString(x + 40 * mm, y, "#")
                c.drawString(x + 48 * mm, y, "Connections")
                for i, (n, cnt, text) in enumerate(part_rows):
                    yy = y - (i + 1) * 3.45 * mm
                    if i % 2 == 0:
                        c.setFillColorRGB(0.95, 0.95, 0.97)
                        c.rect(x - 1, yy - 1.2, 195 * mm, 3.45 * mm, stroke=0, fill=1)
                    c.setFillColorRGB(*C_NET)
                    c.setFont(FONT, 5.8)
                    c.drawString(x, yy, n[:34])
                    c.setFillColorRGB(*C_TXT)
                    c.drawString(x + 40 * mm, yy, str(cnt))
                    t = text
                    while pdfmetrics.stringWidth(t, FONT, 5.8) > 145 * mm:
                        t = t[:-4]
                    if t != text:
                        t = t.rstrip(", ") + " …"
                    c.drawString(x + 48 * mm, yy, t)

    out.parent.mkdir(parents=True, exist_ok=True)
    cv = canvas.Canvas(str(out), pagesize=PAGE)
    cv.setTitle("Companion Compute – schematic")
    cv.setAuthor("Smash Electronics")
    cv.setSubject("Generated from companion_compute.kicad_pcb")
    for i, (title, fn) in enumerate(sheets):
        cv.bookmarkPage(f"s{i}")
        cv.addOutlineEntry(f"{i + 1}  {title}", f"s{i}", level=0)
        sh = Sheet(cv, title, i + 1, len(sheets), meta)
        fn(sh)
        cv.showPage()
    cv.save()
    return len(sheets)


def main():
    ap = argparse.ArgumentParser(description="Generate the Companion Compute schematic PDF")
    ap.add_argument("-o", "--output", type=Path, default=OUT)
    a = ap.parse_args()
    parts = load_board(PCB)
    n = build(parts, a.output)
    print(f"{a.output}  ({n} sheets, {len(parts)} parts)")


if __name__ == "__main__":
    main()
