"""KiCad schematic writer — one flat sheet covering every board.

Emits a documentation schematic for a `Design`:

  - `<project>.kicad_sch`   one sheet, one titled frame per board tag
  - `<project>.kicad_sym`   the generated symbol library
  - `<project>.kicad_pro` + `sym-lib-table`

The schematic is a *projection* of the Design, not a source. PCB-only
constructs are left out (LGA land fields, branch-flex launch strips,
mechanical spacers): they join same-named nets, so no connection is
lost. Symbols are
generated from each component's pin list (so symbol pin numbers always
match the footprint pads). Each multi-pin part is drawn the way a person
would: rail pins end in power symbols (adjacent pins on one rail share a
bus and one symbol), its rail-to-ground decoupling parts hang as a wired
bank underneath, and a 2-pin part on one of its signal pins (pull-up,
series R, filter cap) is wired straight off that pin. Other signals use
net labels: global labels for nets that touch more than one board (name
identical to the PCB), local labels otherwise. Pins the Design leaves unconnected carry a no-connect
flag.

Large parts are split into multi-unit symbols of at most
`_MAX_PINS_PER_UNIT` pins; power pins lead, ground pins trail, everything
else is natural-sorted by pin name in between.

Element UUIDs are uuid5-derived from (board, ref, ...) so regenerating
an unchanged Design gives a byte-identical schematic.

`write_board_schematic` draws the same way for one board, into that
board's own project directory: every footprint on it gets a symbol and
the board's footprints point at those symbols (`symbol_path`), so the
`.kicad_pcb` and `.kicad_sch` are one linked KiCad project.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import uuid as _uuid

from smash.state import Design
from smash.export._common import (
    all_components,
    nets_with_pins,
    net_connections,
    footprint_full,
    board_datasheet,
    component_value,
    kicad_ref,
    _strip_ball_prefix,
)
from smash.export.samacsys import copy_libraries, find_symbol
from smash.roots import resolve_repo_path


_NS = _uuid.UUID("8c5b9c1e-1a82-4a4a-9c4b-1c1a40000002")
_VERSION = "20231120"          # KiCad 8 file format; KiCad 9/10 open it

_G = 2.54                       # connection grid (mm)
_PIN_LEN = 2.54
_STUB = 2.54                    # wire stub from pin end to its label
_CHAR_W = 1.05                  # ~advance of the 1.27 mm stroke font
_MAX_PINS_PER_UNIT = 64
_MARGIN = 25.4                  # keep clear of the drawing-sheet frame

_PIN_ETYPE = {
    "input": "input",
    "output": "output",
    "io": "bidirectional",
    "clock": "input",
}

# Landscape ISO sizes, smallest first; anything larger gets "User".
_PAPER = [("A4", 297, 210), ("A3", 420, 297), ("A2", 594, 420),
          ("A1", 841, 594), ("A0", 1189, 841)]


def _uid(*parts: str) -> str:
    return str(_uuid.uuid5(_NS, "/".join(parts)))


def _q(s) -> str:
    """Quote a string for an s-expression."""
    s = "" if s is None else str(s)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _f(v: float) -> str:
    v = round(v, 4)
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _snap(v: float, g: float = _G) -> float:
    return round(v / g) * g


def _ceil_to(v: float, g: float) -> float:
    n = -(-v // g)
    return n * g


def _natkey(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _text_w(s: str) -> float:
    return len(s) * _CHAR_W


def _font(hide: bool = False, justify: str | None = None,
          size: float = 1.27) -> str:
    j = f" (justify {justify})" if justify else ""
    h = " hide" if hide else ""
    return f"(effects (font (size {_f(size)} {_f(size)})){j}{h})"


# ── symbol model ─────────────────────────────────────────────────────────

class _LibPin:
    __slots__ = ("num", "name", "etype", "x", "y", "angle", "length")

    def __init__(self, num, name, etype, x, y, angle, length=_PIN_LEN):
        self.num, self.name, self.etype = num, name, etype
        self.x, self.y, self.angle, self.length = x, y, angle, length


class _Unit:
    """One unit of a lib symbol: box geometry + pins (lib coords, y-up).
    `graphics` holds a SamacSys body verbatim (s-expressions); generated
    symbols draw their own."""

    def __init__(self, pins: list, half_w: float, top: float, bottom: float,
                 graphics: list | None = None):
        self.pins = pins
        self.half_w = half_w
        self.top = top
        self.bottom = bottom
        self.graphics = graphics


class _LibSymbol:
    def __init__(self, name: str, ref_prefix: str, kind: str,
                 units: list, show_pin_names: bool):
        self.name = name
        self.ref_prefix = ref_prefix
        self.kind = kind                 # "box" | "R" | "C" | "two" | "samacsys"
        self.units = units
        self.show_pin_names = show_pin_names
        self.vertical = False            # pins top/bottom (see _variant)


def _pin_list(comp) -> list:
    """(num, name, type) for every pin, BALL_ prefix stripped."""
    return [(_strip_ball_prefix(str(p.num)), str(p.name or p.num), p.type)
            for p in (getattr(comp, "pins", None) or [])]


def _ref_prefix(ref: str) -> str:
    m = re.match(r"[A-Za-z]+", ref)
    return m.group(0) if m else "X"


def _two_pin_kind(comp, pins) -> str:
    prefix = _ref_prefix(comp.ref).upper()
    if prefix in ("R", "RN"):
        return "R"
    if prefix == "C":
        return "C"
    return "two"


def _build_two_pin(name: str, comp, pins) -> _LibSymbol:
    kind = _two_pin_kind(comp, pins)
    named = any(not n.isdigit() for _, n, _ in pins)
    (n1, nm1, t1), (n2, nm2, t2) = pins
    half = 2.54 if not named else _ceil_to(
        (_text_w(nm1) + _text_w(nm2)) / 2 + 2.54, _G)
    lp = [
        _LibPin(n1, nm1, _PIN_ETYPE.get(t1, "passive"), -(half + _PIN_LEN), 0, 0),
        _LibPin(n2, nm2, _PIN_ETYPE.get(t2, "passive"), half + _PIN_LEN, 0, 180),
    ]
    unit = _Unit(lp, half, 1.016, -1.016)
    return _LibSymbol(name, _ref_prefix(comp.ref), kind, [unit],
                      show_pin_names=named and kind == "two")


def _pin_order(pins) -> list:
    def group(t):
        return 0 if t == "power" else 2 if t == "ground" else 1
    return sorted(pins, key=lambda p: (group(p[2]), _natkey(p[1]), _natkey(p[0])))


def _build_box(name: str, comp, pins, gaps: dict | None = None) -> _LibSymbol:
    """Box symbol, pins split left/right; `gaps` = {pin number: empty
    rows to leave below that pin} (room for its decoupling parts)."""
    gaps = gaps or {}
    ordered = _pin_order(pins)
    n_units = -(-len(ordered) // _MAX_PINS_PER_UNIT)
    per_unit = -(-len(ordered) // n_units)
    units = []
    for u in range(n_units):
        chunk = ordered[u * per_unit:(u + 1) * per_unit]
        n_left = -(-len(chunk) // 2)
        left, right = chunk[:n_left], chunk[n_left:]
        name_w = max((_text_w(p[1]) for p in left), default=0) \
            + max((_text_w(p[1]) for p in right), default=0)
        half = max(_ceil_to(name_w / 2 + 2.54, _G), 7.62)
        lp = []
        rows = 0
        for side, x, ang in ((left, -(half + _PIN_LEN), 0), (right, half + _PIN_LEN, 180)):
            row = 0
            for num, nm, t in side:
                lp.append(_LibPin(num, nm, _PIN_ETYPE.get(t, "passive"), x, -row * _G, ang))
                row += 1 + gaps.get(num, 0)
            rows = max(rows, row - (gaps.get(side[-1][0], 0) if side else 0))
        units.append(_Unit(lp, half, _G, -(rows - 1) * _G - _G))
    return _LibSymbol(name, _ref_prefix(comp.ref), "box", units,
                      show_pin_names=True)


def _from_samacsys(name: str, comp, ss) -> _LibSymbol:
    """A lib symbol drawn with the part's SamacSys body and pins."""
    # A `no_connect` pin never joins a net in KiCad, even when the design
    # ties it to one (TPS61175 pin 11, "NC", to ground); the sheet's own
    # no-connect flags mark the pins that really are unused.
    pins = [_LibPin(p.num, p.name, "passive" if p.etype == "no_connect" else p.etype,
                    p.x, p.y, p.angle, p.length) for p in ss.pins]
    unit = _Unit(pins, max(abs(ss.x0), abs(ss.x1)), ss.y1, ss.y0, graphics=ss.graphics)
    return _LibSymbol(name, _ref_prefix(comp.ref), "samacsys", [unit], show_pin_names=True)


def _symbol_base_name(comp, pins) -> str:
    if len(pins) == 2 and _two_pin_kind(comp, pins) in ("R", "C"):
        return _two_pin_kind(comp, pins)
    base = getattr(comp, "manf_pn", None) or getattr(comp, "value", None) \
        or _ref_prefix(comp.ref)
    if base == "LGA_lands":
        base = f"LGA_lands_{len(pins)}"
    return re.sub(r"[^A-Za-z0-9_.+-]", "_", str(base))


class _SymbolLibrary:
    """Dedupes generated symbols by (name, pin signature)."""

    def __init__(self):
        self.by_name: dict[str, _LibSymbol] = {}
        self._sig: dict[str, tuple] = {}

    def for_component(self, comp) -> _LibSymbol:
        pins = _pin_list(comp)
        # A part's own SamacSys symbol when its pins match (multi-pin parts;
        # 2-pin parts keep the generated R/C/two symbols the satellite and
        # decoupling layouts are built around).
        ss = find_symbol(comp) if len(pins) > 2 else None
        if ss is not None:
            base = re.sub(r"[^A-Za-z0-9_.+-]", "_", ss.name)
            sig = ("samacsys", ss.path)
            name = base
            if name in self._sig and self._sig[name] != sig:
                name = f"{base}_{hashlib.sha1(repr(sig).encode()).hexdigest()[:6]}"
            if name not in self.by_name:
                self.by_name[name] = _from_samacsys(name, comp, ss)
                self._sig[name] = sig
            return self.by_name[name]
        base = _symbol_base_name(comp, pins)
        if len(pins) == 2 and base in ("R", "C"):
            sig = (base,)
        else:
            sig = tuple(pins)
        name = base
        if name in self._sig and self._sig[name] != sig:
            h = hashlib.sha1(repr(sig).encode()).hexdigest()[:6]
            name = f"{base}_{h}"
        if name not in self.by_name:
            if len(pins) == 2:
                sym = _build_two_pin(name, comp, pins)
            else:
                sym = _build_box(name, comp, pins)
            self.by_name[name] = sym
            self._sig[name] = sig
        sym = self.by_name[name]
        if sig == ("R",) or sig == ("C",):
            # Generic R/C symbol: pin numbers are always 1/2.
            assert {p[0] for p in pins} == {"1", "2"}, comp.ref
        return sym

    def gapped(self, comp, sym: _LibSymbol, gaps: dict) -> _LibSymbol:
        """`sym` rebuilt with empty rows below the pins in `gaps`."""
        pins = _pin_list(comp)
        h = hashlib.sha1(repr((tuple(pins), sorted(gaps.items()))).encode()).hexdigest()[:6]
        name = f"{sym.name}_g{h}"
        if name not in self.by_name:
            self.by_name[name] = _build_box(name, comp, pins, gaps)
        return self.by_name[name]


# ── orientation variants + power symbols ─────────────────────────────────

def _variant(lib: "_SymbolLibrary", sym: _LibSymbol, orient: str) -> _LibSymbol:
    """A 2-pin symbol with its pins re-placed: "H" (as built, pin 1 left),
    "Hr" (pin 1 right), "V" (pin 1 top), "Vr" (pin 1 bottom). Separate lib
    symbols rather than rotated/mirrored instances, so instance field text
    never has to be counter-rotated."""
    if orient == "H":
        return sym
    name = f"{sym.name}__{orient}"
    if name in lib.by_name:
        return lib.by_name[name]
    u = sym.units[0]
    p1, p2 = u.pins
    ext = u.half_w + _PIN_LEN
    if orient == "Hr":
        pins = [_LibPin(p1.num, p1.name, p1.etype, ext, 0, 180),
                _LibPin(p2.num, p2.name, p2.etype, -ext, 0, 0)]
        v = _LibSymbol(name, sym.ref_prefix, sym.kind,
                       [_Unit(pins, u.half_w, u.top, u.bottom)], sym.show_pin_names)
    else:
        s = 1 if orient == "V" else -1
        pins = [_LibPin(p1.num, p1.name, p1.etype, 0, s * ext, 270 if s > 0 else 90),
                _LibPin(p2.num, p2.name, p2.etype, 0, -s * ext, 90 if s > 0 else 270)]
        v = _LibSymbol(name, sym.ref_prefix, sym.kind,
                       [_Unit(pins, u.half_w, u.half_w, -u.half_w)], False)
        v.vertical = True
    lib.by_name[name] = v
    return v


def _rot(x: float, y: float, d: str) -> tuple:
    """Glyph drawn pointing up (lib coords, y-up) → pointing `d`."""
    return {"U": (x, y), "D": (x, -y), "L": (-y, x), "R": (y, -x)}[d]


# Value-text anchor relative to the power symbol's pin, sheet coords (y-down).
_PWR_TEXT = {"U": (0, -3.81, None), "D": (0, 3.81, None),
             "L": (-3.302, 0, "right"), "R": (3.302, 0, "left")}


class _PwrSymbol:
    """Power symbol for one net, pointing one way. One lib symbol per net
    (hidden power-in pin named after the net, Value = net) so the net is
    named correctly whether KiCad reads the pin name or the Value."""

    def __init__(self, name: str, net: str, ground: bool, d: str):
        self.name, self.net, self.ground, self.d = name, net, ground, d

    def sexpr(self, lib_prefix: str | None) -> str:
        full = f"{lib_prefix}:{self.name}" if lib_prefix else self.name
        if self.ground:
            glyphs = [[(0, 0), (0, 1.27), (1.016, 1.27), (0, 2.54), (-1.016, 1.27), (0, 1.27)]]
        else:
            glyphs = [[(0, 0), (0, 2.54)], [(-0.762, 1.27), (0, 2.54), (0.762, 1.27)]]
        vx, vy, just = _PWR_TEXT[self.d]
        out = [
            f'\t(symbol {_q(full)} (power) (pin_names (offset 0) hide)',
            '\t\t(exclude_from_sim no) (in_bom yes) (on_board yes)',
            f'\t\t(property "Reference" "#PWR" (at 0 0 0) {_font(hide=True)})',
            f'\t\t(property "Value" {_q(self.net)} (at {_f(vx)} {_f(-vy)} 0) {_font(justify=just)})',
            f'\t\t(property "Footprint" "" (at 0 0 0) {_font(hide=True)})',
            f'\t\t(property "Datasheet" "" (at 0 0 0) {_font(hide=True)})',
            f'\t\t(property "Description" {_q(f"Power symbol for net {self.net}")} (at 0 0 0) {_font(hide=True)})',
            f'\t\t(symbol {_q(f"{self.name}_0_1")}',
        ]
        for pts in glyphs:
            xy = " ".join(f"(xy {_f(a)} {_f(b)})" for a, b in (_rot(x, y, self.d) for x, y in pts))
            out.append(f'\t\t\t(polyline (pts {xy}) (stroke (width 0) (type default)) (fill (type none)))')
        out += [
            '\t\t)',
            f'\t\t(symbol {_q(f"{self.name}_1_1")}',
            f'\t\t\t(pin power_in line (at 0 0 90) (length 0) hide '
            f'(name {_q(self.net)} {_font()}) (number "1" {_font()}))',
            '\t\t)',
            '\t)',
        ]
        return "\n".join(out)


def _power_symbol(lib: "_SymbolLibrary", net: str, ground: bool, d: str) -> _PwrSymbol:
    base = re.sub(r"[^A-Za-z0-9_.+-]", "_", net)
    if base != net:
        base += "_" + hashlib.sha1(net.encode()).hexdigest()[:6]
    name = f"PWR_{base}_{d}"
    if name not in lib.by_name:
        lib.by_name[name] = _PwrSymbol(name, net, ground, d)
    return lib.by_name[name]


# ── lib symbol s-expressions ─────────────────────────────────────────────

def _lib_symbol_sexpr(sym, lib_prefix: str | None) -> str:
    if isinstance(sym, _PwrSymbol):
        return sym.sexpr(lib_prefix)
    full = f"{lib_prefix}:{sym.name}" if lib_prefix else sym.name
    out = [f'\t(symbol {_q(full)}']
    if not sym.show_pin_names:
        out.append('\t\t(pin_names (offset 1.016) hide)')
    else:
        out.append('\t\t(pin_names (offset 1.016))')
    if sym.kind in ("R", "C"):
        out.append('\t\t(pin_numbers hide)')
    out.append('\t\t(exclude_from_sim no) (in_bom yes) (on_board yes)')
    u0 = sym.units[0]
    out.append(f'\t\t(property "Reference" {_q(sym.ref_prefix)} (at 0 {_f(u0.top + 1.27)} 0) {_font()})')
    out.append(f'\t\t(property "Value" {_q(sym.name)} (at 0 {_f(u0.bottom - 1.27)} 0) {_font()})')
    out.append(f'\t\t(property "Footprint" "" (at 0 0 0) {_font(hide=True)})')
    out.append(f'\t\t(property "Datasheet" "" (at 0 0 0) {_font(hide=True)})')
    out.append(f'\t\t(property "Description" "" (at 0 0 0) {_font(hide=True)})')
    if len(sym.units) > 1:
        out.append(f'\t\t(property "ki_locked" "" (at 0 0 0) {_font()})')
    for ui, unit in enumerate(sym.units, start=1):
        out.append(f'\t\t(symbol {_q(f"{sym.name}_{ui}_1")}')
        if unit.graphics is not None:
            out.extend("\t\t\t" + " ".join(g.split()) for g in unit.graphics)
        else:
            out.extend(_unit_graphics(sym, unit))
        for p in unit.pins:
            out.append(
                f'\t\t\t(pin {p.etype} line (at {_f(p.x)} {_f(p.y)} {p.angle}) '
                f'(length {_f(p.length)}) '
                f'(name {_q(p.name)} {_font()}) (number {_q(p.num)} {_font()}))')
        out.append('\t\t)')
    out.append('\t)')
    return "\n".join(out)


def _unit_graphics(sym: _LibSymbol, unit: _Unit) -> list:
    h = unit.half_w
    line = '\t\t\t(polyline (pts (xy {} {}) (xy {} {})) (stroke (width {}) (type default)) (fill (type none)))'
    if sym.vertical:
        if sym.kind == "C":
            gap = 0.508
            return [
                line.format(0, _f(h), 0, _f(gap), 0),
                line.format(0, _f(-gap), 0, _f(-h), 0),
                line.format(-1.524, _f(gap), 1.524, _f(gap), 0.3048),
                line.format(-1.524, _f(-gap), 1.524, _f(-gap), 0.3048),
            ]
        w, fill = (1.016, "none") if sym.kind == "R" else (1.27, "background")
        return [f'\t\t\t(rectangle (start {_f(-w)} {_f(h)}) (end {_f(w)} {_f(-h)}) '
                f'(stroke (width 0.254) (type default)) (fill (type {fill})))']
    if sym.kind == "C":
        gap = 0.508
        return [
            line.format(_f(-h), 0, _f(-gap), 0, 0),
            line.format(_f(gap), 0, _f(h), 0, 0),
            line.format(_f(-gap), 1.27, _f(-gap), -1.27, 0.3048),
            line.format(_f(gap), 1.27, _f(gap), -1.27, 0.3048),
        ]
    if sym.kind == "R":
        return [f'\t\t\t(rectangle (start {_f(-h)} 1.016) (end {_f(h)} -1.016) '
                f'(stroke (width 0.254) (type default)) (fill (type none)))']
    return [f'\t\t\t(rectangle (start {_f(-h)} {_f(unit.top)}) (end {_f(h)} {_f(unit.bottom)}) '
            f'(stroke (width 0.254) (type default)) (fill (type background)))']


# ── sheet layout ─────────────────────────────────────────────────────────
#
# Each multi-pin part becomes one block per unit, drawn the way a person
# would: rail pins end in power symbols (adjacent pins on the same rail
# share one, via a short bus), rail→ground decoupling parts hang as a
# wired bank under the part, and a 2-pin part on one of the part's
# signal pins (pull-up, series R, filter cap) is wired straight off that
# pin. Everything else connects by net label, as on any dense sheet.

_SMALL = 1.0                    # font size for passive ref/value text
_BANK_W = 150.0                 # decoupling-bank rows wrap past this (or the part's width)


class _Ctx:
    def __init__(self, lib, comp_sym, pin_net, global_nets, rails,
                 grounds, heavy, net_size, fp_of=None, label_all=False,
                 datasheet_of=None):
        self.lib, self.comp_sym, self.pin_net = lib, comp_sym, pin_net
        self.global_nets = global_nets
        self.fp_of = fp_of or _footprint_field
        self.datasheet_of = datasheet_of or (lambda c: getattr(c, "datasheet", None) or "")
        self.label_all = label_all      # name every net, even pin-to-pin wires
        self.rails = rails              # drawn as power symbols
        self.grounds = grounds          # subset of rails
        self.heavy = heavy              # rails + big fan-out (ownership only)
        self.net_size = net_size
        self.attach: dict = {}          # (chip ref, pin num) → [(part, its rail pin)]
        self.warnings: list = []


def _value(comp, ctx) -> str:
    return component_value(comp)


def _footprint_field(comp) -> str:
    fp = footprint_full(comp)
    if fp and ":" not in fp:
        fp = f"footprints:{fp}"
    return fp


def _named_on_wire(ctx, net) -> bool:
    """A satellite's near net gets a label on its wire when it continues
    elsewhere, or always when every net must carry its PCB name (KiCad
    would auto-name a bare pin-to-pin wire `Net-(…)`)."""
    return ctx.label_all or ctx.net_size[net] > 2


def _text_box(s: str, x: float, y: float, just: str | None, size: float) -> tuple:
    w, h = _text_w(s) * size / 1.27, size
    j = just or ""
    x0 = x - w if "right" in j else x if "left" in j else x - w / 2
    y0 = y - h if "bottom" in j else y if "top" in j else y - h / 2
    return x0, y0, x0 + w, y0 + h


class _Block:
    """A group of primitives in coordinates relative to its anchor; the
    packer moves the anchor (x, y)."""

    def __init__(self):
        self.prims: list = []
        self.bb = [float("inf"), float("inf"), float("-inf"), float("-inf")]
        self.x = self.y = 0.0

    def box(self, x0, y0, x1, y1):
        b = self.bb
        b[0], b[1] = min(b[0], x0, x1), min(b[1], y0, y1)
        b[2], b[3] = max(b[2], x0, x1), max(b[3], y0, y1)

    def text(self, s, x, y, just=None, size=1.27):
        self.box(*_text_box(s, x, y, just, size))

    def wire(self, x1, y1, x2, y2):
        if (x1, y1) != (x2, y2):
            self.prims.append(("wire", x1, y1, x2, y2))
            self.box(x1, y1, x2, y2)

    def nc(self, x, y):
        self.prims.append(("nc", x, y))
        self.box(x - 1, y - 1, x + 1, y + 1)

    def label(self, ctx, net, x, y, ang):
        glob = net in ctx.global_nets
        self.prims.append(("label", net, x, y, ang, glob))
        w = _text_w(net) + (3.5 if glob else 0)
        if ang in (90, 270):                    # runs up (90) / down (270)
            y1 = y - w if ang == 90 else y + w
            self.box(x - 1.4, y, x + (1.4 if glob else 0), y1)
        else:
            x1 = x - w if ang == 180 else x + w
            self.box(x, y - 1.4, x1, y + (1.4 if glob else 0))

    def pwr(self, ctx, net, x, y, d):
        sym = _power_symbol(ctx.lib, net, net in ctx.grounds, d)
        self.prims.append(("pwr", sym, x, y))
        self.box(*{"U": (x - 1, y - 2.54, x + 1, y), "D": (x - 1.3, y, x + 1.3, y + 2.54),
                   "L": (x - 2.54, y - 1, x, y + 1), "R": (x, y - 1, x + 2.54, y + 1)}[d])
        vx, vy, just = _PWR_TEXT[d]
        self.text(net, x + vx, y + vy, just)

    def symbol(self, ctx, lsym, comp, unit_no, x, y, ref_at, val_at, size):
        """Place a part. `ref_at` / `val_at` are (x, y, justify) relative
        to this block."""
        fp = ctx.fp_of(comp)
        value = _value(comp, ctx)
        fields = [
            ("Reference", kicad_ref(comp.ref), *ref_at, False, size),
            ("Value", value, *val_at, False, size),
            ("Footprint", fp, x, y, None, True, 1.27),
            ("Datasheet", ctx.datasheet_of(comp), x, y, None, True, 1.27),
            ("Description", getattr(comp, "description", None) or "", x, y, None, True, 1.27),
            ("MPN", getattr(comp, "manf_pn", None) or "", x, y, None, True, 1.27),
            ("Manufacturer", getattr(comp, "manf", None) or "", x, y, None, True, 1.27),
        ]
        self.prims.append(("sym", lsym, comp, unit_no, x, y, fields))
        self.text(kicad_ref(comp.ref), ref_at[0], ref_at[1], ref_at[2], size)
        self.text(value, val_at[0], val_at[1], val_at[2], size)

    # packer interface (one grid of padding all round)
    @property
    def width(self) -> float:
        return self.bb[2] - self.bb[0] + 2 * _G

    @property
    def height(self) -> float:
        return self.bb[3] - self.bb[1] + 2 * _G

    @property
    def origin_dx(self) -> float:
        return _G - self.bb[0]

    @property
    def origin_dy(self) -> float:
        return _G - self.bb[1]


def _term_w(ctx, net) -> float:
    """Room a plain pin termination takes beyond the pin end."""
    if net is None:
        return _G
    if net in ctx.rails:
        return _STUB + 3.302 + _text_w(net)
    return _STUB + _text_w(net) + (3.5 if net in ctx.global_nets else 1)


def _terminate(blk: _Block, ctx, ex, ey, d, net) -> None:
    """Stub + label / power symbol (or a no-connect) on a pin end facing
    `d` (-1 left, +1 right)."""
    if net is None:
        blk.nc(ex, ey)
        return
    lx = ex + d * _STUB
    blk.wire(ex, ey, lx, ey)
    if net in ctx.rails:
        blk.pwr(ctx, net, lx, ey, "L" if d < 0 else "R")
    else:
        blk.label(ctx, net, lx, ey, 180 if d < 0 else 0)


def _terminate_v(blk: _Block, ctx, ex, ey, d, net) -> None:
    """`_terminate` for a pin end on a top (`d` -1, up) or bottom (+1,
    down) edge."""
    if net is None:
        blk.nc(ex, ey)
        return
    ly = ey + d * _STUB
    blk.wire(ex, ey, ex, ly)
    if net in ctx.rails:
        blk.pwr(ctx, net, ex, ly, "U" if d < 0 else "D")
    else:
        blk.label(ctx, net, ex, ly, 90 if d < 0 else 270)


def _two_pin_nets(ctx, s) -> list:
    return [(num, ctx.pin_net.get((s.ref, num))) for num, _, _ in _pin_list(s)]


def _is_bank(ctx, s) -> bool:
    """Rail-to-ground 2-pin part (decoupling/bulk cap, TVS, bleeder)."""
    nets = [n for _, n in _two_pin_nets(ctx, s)]
    return (len(nets) == 2 and all(n in ctx.rails for n in nets)
            and (nets[0] in ctx.grounds) != (nets[1] in ctx.grounds))


def _unit_block(comp, ui, ctx, cands, bank, placed) -> _Block:
    sym = ctx.comp_sym[comp.ref]
    unit = sym.units[ui]
    blk = _Block()
    vertical = [p for p in unit.pins if p.angle in (90, 270)]
    if vertical:
        # Pins on the top/bottom edges (SamacSys bodies): their labels run
        # up/down from the body, so ref/value go to the left-hand corners.
        h = -unit.half_w - 1.27
        ref_at, val_at = (h, -unit.top - 1.27, "right"), (h, -unit.bottom + 1.27, "right")
    else:
        ref_at, val_at = (0, -unit.top - 1.27, None), (0, -unit.bottom + 1.27, None)
    blk.symbol(ctx, sym, comp, ui + 1, 0, 0, ref_at, val_at, 1.27)
    blk.box(-unit.half_w, -unit.top, unit.half_w, -unit.bottom)
    for d in (-1, 1):
        side = sorted((p for p in unit.pins if p.angle == (0 if d < 0 else 180)),
                      key=lambda p: -p.y)
        _layout_side(blk, ctx, comp, side, d, cands, placed)
    for p in vertical:                          # 270: top edge, 90: bottom
        _terminate_v(blk, ctx, p.x, -p.y, -1 if p.angle == 270 else 1,
                     ctx.pin_net.get((comp.ref, p.num)))
    if bank:
        _layout_bank(blk, ctx, bank, -unit.half_w - _PIN_LEN, blk.bb[3])
    return blk


def _layout_side(blk, ctx, comp, side, d, cands, placed) -> None:
    if not side:
        return
    nets = [ctx.pin_net.get((comp.ref, p.num)) for p in side]

    # Satellites: at most one 2-pin part per signal pin, never on adjacent
    # rows (nor right above a pin with decoupling parts hung off it, whose
    # rail line runs one row down), so each keeps room for its ref/value
    # text above and below.
    sat: dict = {}
    for i, p in enumerate(side[1:]):
        if (comp.ref, p.num) in ctx.attach:
            sat[i] = None                       # placeholder: row blocked
    for s in cands:
        if s.ref in placed:
            continue
        pn = _two_pin_nets(ctx, s)
        if len(pn) != 2:
            continue
        for (near, n_net), (_, f_net) in (pn, pn[::-1]):
            if (n_net is None or n_net in ctx.rails or n_net in ctx.global_nets
                    or n_net == f_net):
                continue
            row = next((i for i, n in enumerate(nets) if n == n_net
                        and not any(sat.get(j) for j in (i - 1, i + 1))
                        and i not in sat), None)
            if row is not None:
                sat[row] = (s, near, f_net)
                placed.add(s.ref)
                break

    sat = {i: v for i, v in sat.items() if v}
    # Satellites sit in one column beyond every plain termination.
    need = _G
    for i, n in enumerate(nets):
        if i in sat:
            need = max(need, _text_w(n) + 2 * _G if _named_on_wire(ctx, n) else 2 * _G)
        else:
            need = max(need, _term_w(ctx, n))
    col = _ceil_to(need + _G, _G)

    i, n_rows = 0, len(side)
    while i < n_rows:
        p, net = side[i], nets[i]
        ex, ey = p.x, -p.y                      # lib y-up → sheet y-down
        if i in sat:
            _satellite(blk, ctx, ex, ey, d, col, net, *sat[i])
            i += 1
            continue
        # Every pin gets its own stub + label / power symbol — rail pins
        # too, never a shared bus: no point on the sheet joins more than two
        # items, so nothing depends on a junction (KiCad's editor drops
        # junctions it judges unneeded before Update PCB from Schematic).
        _terminate(blk, ctx, ex, ey, d, net)
        hung = ctx.attach.get((comp.ref, p.num))
        if hung:
            _pin_bank(blk, ctx, net, ex, ey, d, hung)
        i += 1


def _satellite(blk, ctx, ex, ey, d, col, net, s, near, far_net) -> None:
    nx = ex + d * col
    blk.wire(ex, ey, nx, ey)
    if _named_on_wire(ctx, net):
        if d < 0:
            blk.label(ctx, net, nx + _G, ey, 0)
        else:
            blk.label(ctx, net, nx - _G, ey, 180)
    sym = ctx.comp_sym[s.ref]
    near_is_1 = sym.units[0].pins[0].num == near
    orient = ("Hr" if near_is_1 else "H") if d < 0 else ("H" if near_is_1 else "Hr")
    v = _variant(ctx.lib, sym, orient)
    ext = v.units[0].half_w + _PIN_LEN
    cx = nx + d * ext
    # Text runs outward from the near pin, clear of the net label on the wire.
    just = "right" if d < 0 else "left"
    blk.symbol(ctx, v, s, 1, cx, ey, (nx, ey - 1.778, just), (nx, ey + 1.778, just), _SMALL)
    blk.box(cx - ext, ey - 1.3, cx + ext, ey + 1.3)
    _terminate(blk, ctx, nx + 2 * d * ext, ey, d, far_net)


_BANK_TOP = 3 * _G               # pin row → top of a bank part (its power symbol + text)
_BANK_BOT = 2 * _G               # bottom of a bank part → clear of its ground symbol + text


def _bank_span(ctx, s) -> float:
    """Height a vertical bank part takes below the row it hangs from: its
    rail symbol, the part, its ground symbol."""
    u = ctx.comp_sym[s.ref].units[0]
    return _BANK_TOP + 2 * (u.half_w + _PIN_LEN) + _BANK_BOT


def _bank_part(blk, ctx, s, rail_pin, cx, y_top, just) -> None:
    """A rail→ground part standing vertically at `cx`, its rail pin end at
    `y_top`: each end in its own power symbol, no wire to anything."""
    sym = ctx.comp_sym[s.ref]
    v = _variant(ctx.lib, sym, "V" if sym.units[0].pins[0].num == rail_pin else "Vr")
    ext = v.units[0].half_w + _PIN_LEN
    cy = y_top + ext
    nets = dict(_two_pin_nets(ctx, s))
    gnd = next(n for num, n in nets.items() if num != rail_pin)
    blk.pwr(ctx, nets[rail_pin], cx, y_top, "U")
    blk.pwr(ctx, gnd, cx, cy + ext, "D")
    tx = cx + (-1.905 if just == "right" else 1.905)
    blk.symbol(ctx, v, s, 1, cx, cy, (tx, cy - 1.27, just), (tx, cy + 1.27, just), _SMALL)
    blk.box(cx - 1.6, y_top, cx + 1.6, cy + ext)


def _bank_step(ctx, s, rail_pin) -> float:
    """Column pitch for a bank part: its ref/value text, and its rail and
    ground symbols' net names (centred over/under it)."""
    nets = [n for _, n in _two_pin_nets(ctx, s)]
    w = max(_text_w(kicad_ref(s.ref)), _text_w(_value(s, ctx))) * _SMALL / 1.27
    return _ceil_to(max(1.905 + w, max(_text_w(n) for n in nets) / 2) + 2 * _G, _G)


def _gap_rows(span: float) -> int:
    """Empty pin rows a pin bank of this height needs below its pin."""
    return int(_ceil_to(span + 2 * _G, _G) / _G) - 1


def _attach_bank(ic, bank, ctx) -> list:
    """Hang each rail→ground part of `ic` off the pin it declares
    (`decouples`): find the run of adjacent same-rail pins holding that
    pin, rebuild `ic`'s symbol with room under the run, record the
    attachment. Returns the parts that can't be hung (no declaration
    for `ic`, or the declared pin isn't on the part's rail — reported by
    _check_declared); those are drawn beside `ic`, unwired."""
    sym = ctx.comp_sym[ic.ref]
    if not bank or sym.kind != "box":
        return bank
    run_of: dict = {}                           # pin num → last pin of its rail run
    for unit in sym.units:
        for left in (True, False):
            side = sorted((p for p in unit.pins if (p.angle == 0) == left),
                          key=lambda p: -p.y)
            nets = [ctx.pin_net.get((ic.ref, p.num)) for p in side]
            i = 0
            while i < len(side):
                j = i
                while j + 1 < len(side) and nets[j + 1] == nets[i]:
                    j += 1
                for k in range(i, j + 1):
                    run_of[side[k].num] = side[j].num
                i = j + 1
    pins = _pin_list(ic)
    attach: dict = {}
    rest = []
    for s in bank:
        (n1, a), (n2, b) = _two_pin_nets(ctx, s)
        rail_pin, rail = (n2, b) if a in ctx.grounds else (n1, a)
        keys = [k for r, k in (getattr(s, "decouples", None) or [])
                if r == ic.ref and k is not None]     # None: chip known, pin not
        nums = [num for num, name, _ in pins for k in keys if k in (num, name)]
        on_rail = [n for n in nums if ctx.pin_net.get((ic.ref, n)) == rail]
        if not on_rail:                         # bad declarations: _check_declared
            rest.append(s)
            continue
        attach.setdefault(run_of[on_rail[0]], []).append((s, rail_pin))
    if attach:
        gaps = {num: _gap_rows(max(_bank_span(ctx, s) for s, _ in items))
                for num, items in attach.items()}
        ctx.comp_sym[ic.ref] = ctx.lib.gapped(ic, sym, gaps)
        for num, items in attach.items():
            ctx.attach[(ic.ref, num)] = items
    return rest


def _pin_bank(blk, ctx, rail, ex, y, d, items) -> None:
    """Decoupling parts for one supply pin (end at `ex`, `y`), standing in
    the empty rows below it side by side going outward, each with its own
    rail and ground symbols."""
    just = "right" if d < 0 else "left"
    cx = ex + d * 2 * _G
    for s, rail_pin in items:
        _bank_part(blk, ctx, s, rail_pin, cx, y + _BANK_TOP, just)
        cx += d * _bank_step(ctx, s, rail_pin)


def _layout_bank(blk, ctx, parts, x0, y_top) -> None:
    """Rail→ground parts as vertical symbols, each with its own rail and
    ground symbols, grouped by (rail, ground) pair left to right; rows
    wrap past `_BANK_W`."""
    groups: dict = {}
    for s in parts:
        (n1, net1), (n2, net2) = _two_pin_nets(ctx, s)
        rail_pin, rail, gnd = (n2, net2, net1) if net1 in ctx.grounds else (n1, net1, net2)
        groups.setdefault((rail, gnd), []).append((s, rail_pin))
    x_start = x = _snap(x0)
    x_lim = x_start + max(blk.bb[2] - blk.bb[0], _BANK_W)
    y = _ceil_to(y_top, _G)
    row_h = 0.0
    for key in sorted(groups, key=lambda k: (_natkey(k[0]), _natkey(k[1]))):
        for s, rail_pin in groups[key]:
            step = _bank_step(ctx, s, rail_pin)
            if x > x_start and x + step > x_lim:        # wrap
                x, y, row_h = x_start, _ceil_to(y + row_h, _G), 0.0
            _bank_part(blk, ctx, s, rail_pin, x + _G, y + _BANK_TOP, "left")
            row_h = max(row_h, _bank_span(ctx, s))
            x += step


def _assign_owners(comps: list, ctx) -> tuple:
    """Multi-pin parts (U* chips first, then connectors etc., most pins
    first), the 2-pin-or-fewer parts, and each small part's owner.

    Only facts decide, never names: a part that declares the pin it
    serves (`decouples`, from cap_to_gnd(pin=...)) belongs to that chip;
    otherwise to the multi-pin part it shares the most signal nets with
    (a feedback divider next to its regulator, a pull-up next to its
    chip). A part that shares only rails with everything (an undeclared
    decoupling cap) has no owner. Chips win ties over connectors."""
    def is_chip(c):
        return _ref_prefix(c.ref).upper() == "U"
    big = sorted([c for c in comps if len(_pin_list(c)) > 2],
                 key=lambda c: (not is_chip(c), -len(_pin_list(c)), _natkey(c.ref)))
    small = sorted([c for c in comps if len(_pin_list(c)) <= 2],
                   key=lambda c: _natkey(c.ref))
    big_refs = {c.ref for c in big}
    nets_of = {c.ref: {ctx.pin_net.get((c.ref, p[0])) for p in _pin_list(c)} - {None}
               for c in comps}
    owner: dict = {}
    for s in small:
        declared = [r for r, _ in (getattr(s, "decouples", None) or []) if r in big_refs]
        if declared:
            owner[s.ref] = declared[0]
            continue
        best, best_score = None, 0.0
        for ic in big:
            n_sig = len((nets_of[s.ref] & nets_of[ic.ref]) - ctx.heavy)
            if not n_sig:
                continue
            score = 100 * n_sig + (0.5 if is_chip(ic) else 0)
            if score > best_score:
                best, best_score = ic.ref, score
        owner[s.ref] = best
    return big, small, owner


def _pack_on_paper(blocks: list) -> str:
    """Pack blocks onto the smallest landscape ISO sheet they fit;
    fall back to a 1.4:1 "User" sheet. Returns the `(paper …)` token."""
    for name, pw, ph in _PAPER:
        w, h = _shelf_pack(blocks, pw - 2 * _MARGIN)
        if w <= pw - 2 * _MARGIN and h <= ph - 2 * _MARGIN:
            return f'(paper "{name}")'
    # Too big for A0: try a range of row widths, keep the smallest page.
    side = sum(b.width * b.height for b in blocks) ** 0.5
    def cost(t):                                # smallest landscape page
        w, h = _shelf_pack(blocks, t)
        return (w < h, w * h)
    best = min((side * k / 10 for k in range(8, 26)), key=cost)
    w, h = _shelf_pack(blocks, best)
    return _paper(w, h)


def _shelf_pack(blocks: list, target_w: float,
                origin: float = _MARGIN) -> tuple[float, float]:
    """Pack blocks, in order, into rows of at most `target_w`. Within a
    row, blocks stack into columns up to the row's height (set by its
    tallest block so far), so a tall chip doesn't leave the rest of its
    row empty underneath. Returns (w, h) used."""
    if not blocks:
        return 0.0, 0.0
    target_w = max(target_w, max(b.width for b in blocks))
    row_y = row_h = used_w = 0.0
    col_x = col_y = col_w = 0.0
    for b in blocks:
        bw, bh = b.width + _G, b.height + _G
        if col_y > 0 and col_y + bh <= row_h and col_x + max(col_w, bw) <= target_w:
            pass                                # stack under the column
        elif col_x + col_w + bw <= target_w or col_x + col_w == 0:
            col_x, col_y, col_w = col_x + col_w, 0.0, 0.0   # new column
        else:
            row_y, row_h = row_y + row_h, 0.0   # new row
            col_x = col_y = col_w = 0.0
        b.x = _snap(origin + col_x + b.origin_dx)
        b.y = _snap(origin + row_y + col_y + b.origin_dy)
        col_y += bh
        col_w = max(col_w, bw)
        row_h = max(row_h, col_y)
        used_w = max(used_w, col_x + col_w)
    return used_w, row_y + row_h


def _paper(w: float, h: float) -> str:
    need_w, need_h = w + 2 * _MARGIN, h + 2 * _MARGIN
    for name, pw, ph in _PAPER:
        if need_w <= pw and need_h <= ph:
            return f'(paper "{name}")'
    return f'(paper "User" {_f(_ceil_to(need_w, 10))} {_f(_ceil_to(need_h, 10))})'


# ── writer ───────────────────────────────────────────────────────────────

# PCB-construction parts with no schematic meaning: the backbone LGA land
# fields and branch-flex launch strips (same-net anchors — each net keeps
# its name on both boards, so dropping them loses no connection) and the
# mechanical spacer discs (pin 1 tied to GND only to appear in the netlist).
_CONSTRUCT_PNS = ("LGA_lands", "FLEX_LAUNCH")


def _is_construct(c) -> bool:
    return (getattr(c, "manf_pn", None) in _CONSTRUCT_PNS
            or (getattr(c, "board_tag", "") or "").startswith("spacer_"))


def write_kicad_schematic(design: Design, out_dir, *, project: str = "smash",
                          pad_groups: dict | None = None) -> dict:
    """Write a flat, single-sheet KiCad schematic project for `design`
    into `out_dir`: one framed region per board. `pad_groups` maps a board
    to `[(title, [ref, ...]), ...]` — pads (bench/test/off-board) drawn
    together in a titled box at the end of that board's region instead of
    next to whatever chip they touch. Returns
    `{n_boards, n_parts, n_nets, n_symbols, warnings}` — warnings list
    declared decoupling pins that don't exist or aren't on the part's rail."""
    comps = [c for c in all_components(design) if not _is_construct(c)]
    board_of = {c.ref: (getattr(c, "board_tag", "") or "unassigned") for c in comps}
    r = _write_schematic(design, pathlib.Path(out_dir), project, comps, board_of,
                         pad_groups=pad_groups)
    _write_project_file(pathlib.Path(out_dir), project)
    return r


def symbol_path(board: str, ref: str) -> str:
    """The `(path …)` a footprint on `board` carries to link it to its
    symbol in `write_board_schematic`'s output: the uuid of the symbol's
    unit 1 (a flat root sheet adds no sheet uuid to the path)."""
    return "/" + _uid(board, ref, "1", "sym")


def relink_multi_unit_footprints(pcb_path, sch_path, kicad_cli) -> int:
    """Point each footprint of a multi-unit symbol at the unit KiCad itself
    links it to. `symbol_path` names unit 1, but KiCad associates the
    footprint with the first unit its netlister finds — an order no rule
    on the file reproduces — and Update PCB from Schematic then re-links
    it. So ask kicad-cli for its netlist and take the first of each part's
    tstamps. Returns the number of footprints changed."""
    import subprocess
    import tempfile
    import xml.etree.ElementTree as ET
    pcb_path = pathlib.Path(pcb_path)
    with tempfile.TemporaryDirectory() as tmp:
        net = pathlib.Path(tmp) / "net.xml"
        subprocess.run([str(kicad_cli), "sch", "export", "netlist", "--format",
                        "kicadxml", "-o", str(net), str(sch_path)],
                       check=True, capture_output=True)
        root = ET.parse(net).getroot()
    first = {c.get("ref"): "/" + c.find("tstamps").text.split()[0]
             for c in root.iter("comp")
             if len((c.find("tstamps").text or "").split()) > 1}
    text = pcb_path.read_text()
    n = 0

    def _fix(m: re.Match) -> str:
        nonlocal n
        block = m.group(0)
        ref = re.search(r'\(property "Reference" "([^"]*)"', block)
        want = first.get(ref.group(1)) if ref else None
        if want is None:
            return block
        new = re.sub(r'^(\t\t\(path ")[^"]*("\))', lambda p: p.group(1) + want + p.group(2),
                     block, count=1, flags=re.M)
        n += new != block
        return new

    text = re.sub(r'^\t\(footprint .*?^\t\)$', _fix, text, flags=re.M | re.S)
    pcb_path.write_text(text)
    return n


def symbol_units(comp) -> list:
    """[(unit name, [pin number, ...]), ...] of `comp`'s symbol — units
    "A", "B", … with their pins in symbol order: the unit metadata a KiCad
    10 footprint carries for its symbol."""
    units = _SymbolLibrary().for_component(comp).units
    return [(chr(ord("A") + ui), [p.num for p in u.pins]) for ui, u in enumerate(units)]


def unconnected_nets(comp) -> dict:
    """{pad number: net name} for `comp`'s unconnected pins — the
    `unconnected-(REF-NAME-PadN)` net KiCad derives from the no-connect
    flag on that pin (unit letter after REF on a multi-unit symbol, a
    name equal to the number left out, `/` escaped). The board carries the
    same names so schematic parity holds on no-connect pads too."""
    units = _SymbolLibrary().for_component(comp).units
    out = {}
    for ui, unit in enumerate(units):
        ref = kicad_ref(comp.ref) + (chr(ord("A") + ui) if len(units) > 1 else "")
        for p in unit.pins:
            name = p.name.replace("/", "{slash}")
            mid = "" if p.name in ("", p.num) else f"-{name}"
            out[p.num] = f"unconnected-({ref}{mid}-Pad{p.num})"
    connected = {_strip_ball_prefix(str(p.num)) for p in comp.pins if p.net}
    return {k: v for k, v in out.items() if k not in connected}


def write_board_schematic(design: Design, board, out_dir, *,
                          lib: str | None = None,
                          pad_groups: list | None = None) -> dict:
    """Write `<board>.kicad_sch` (+ its symbol library and sym-lib-table)
    into the board's own project directory, so the board's `.kicad_pcb`
    and its schematic form one KiCad project.

    Unlike the system schematic this covers *every* footprint on the
    board — LGA land fields and flex launches included — so each
    footprint has a symbol: `kicad_pcb` stamps every footprint with
    `symbol_path(board, ref)`, and symbol pin numbers are the footprint
    pad numbers. Every net carries its PCB name (power symbols for rails,
    global labels for everything else — KiCad would prefix a local label
    with the sheet path, `/NAME`), so Update PCB from Schematic and
    schematic-parity DRC see the netlist the board already has. `lib` is
    the library nickname used for both symbols and the Footprint fields
    (the portable project's footprint library). Leaves `<board>.kicad_pro`
    to the board writer."""
    from smash.export.portable_project import library_nickname, _fp_filename
    from smash.state import Chip
    from smash.state.antenna import Antenna

    name = board.name
    lib = lib or library_nickname(name)
    refs = {pl.item.ref for pl in board.chip_placements
            if isinstance(pl.item, (Chip, Antenna)) and pl.item.footprint is not None}
    comps = [c for c in all_components(design) if c.ref in refs]

    def fp_of(c) -> str:
        fp = footprint_full(c)
        return f"{lib}:{_fp_filename(fp)}" if fp else ""

    out = pathlib.Path(out_dir)
    r = _write_schematic(design, out, name, comps,
                         {c.ref: name for c in comps}, lib=lib,
                         pad_groups={name: pad_groups or []},
                         fp_of=fp_of, label_all=True, datasheet_of=board_datasheet)
    # The parts' datasheets and SamacSys libraries (KiCad symbol + Altium
    # SchLib/PcbLib) travel with the board; the generator owns both folders.
    for sub in ("datasheets", "samacsys"):
        shutil.rmtree(out / sub, ignore_errors=True)
    for c in comps:
        ds = board_datasheet(c)
        if ds.startswith("${KIPRJMOD}/"):
            src = resolve_repo_path(c.datasheet)
            if src.is_file():
                dst = out / ds[len("${KIPRJMOD}/"):]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        copy_libraries(c, out / "samacsys")
    return r


def _write_schematic(design, out, project, comps, board_of, *, lib=None,
                     pad_groups=None, fp_of=None, label_all=False,
                     datasheet_of=None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    lib = lib or project
    keep = {c.ref for c in comps}
    by_kicad: dict = {}
    for c in comps:
        other = by_kicad.setdefault(kicad_ref(c.ref), c.ref)
        if other != c.ref:
            raise ValueError(f"{other} and {c.ref} both become KiCad reference "
                             f"{kicad_ref(c.ref)}; rename one")
    pin_net: dict = {}
    net_size: dict = {}
    global_nets: set = set()
    rails: set = set()
    grounds: set = set()
    heavy: set = set()
    for n in nets_with_pins(design):
        conns = [(r, p) for r, p in net_connections(n) if r in keep]
        if not conns:
            continue
        net_size[n.name] = len(conns)
        for ref, pin in conns:
            pin_net[(ref, pin)] = n.name
        if label_all or len({board_of[r] for r, _ in conns}) > 1:
            global_nets.add(n.name)
        # Rails: declared power nets and anything named like ground
        # (FLEX_GND is declared kind="signal"). Big fan-out nets also
        # count as rails when deciding which chip a passive belongs to.
        kind = getattr(n, "kind", None)
        if kind == "ground" or "GND" in n.name.upper():
            grounds.add(n.name)
        if kind == "power" or n.name in grounds:
            rails.add(n.name)
        if n.name in rails or len(conns) > 20:
            heavy.add(n.name)

    symlib = _SymbolLibrary()
    comp_sym = {c.ref: symlib.for_component(c) for c in comps}
    ctx = _Ctx(symlib, comp_sym, pin_net, global_nets, rails, grounds, heavy,
               net_size, fp_of=fp_of, label_all=label_all,
               datasheet_of=datasheet_of)
    ctx.warnings.extend(_check_declared(comps, pin_net))

    boards = sorted({board_of[c.ref] for c in comps})
    regions = []
    for b in boards:
        blocks = _board_blocks([c for c in comps if board_of[c.ref] == b], ctx,
                               (pad_groups or {}).get(b, []))
        if blocks:
            regions.append(_Region(b, blocks))
    _write_flat(out, project, lib, regions)
    _write_library(out, project, lib, symlib)

    return {"n_boards": len(regions), "n_parts": len(comps),
            "n_nets": len(net_size), "n_symbols": len(set(comp_sym.values())),
            "warnings": ctx.warnings}


def _check_declared(comps, pin_net) -> list:
    """Every `decouples` declaration must name a pin of a part in the
    design that shares a net with the declaring part."""
    by_ref = {c.ref: c for c in comps}
    out = []
    for c in comps:
        mine = {pin_net.get((c.ref, n)) for n, _, _ in _pin_list(c)} - {None}
        for ref, key in getattr(c, "decouples", None) or []:
            if ref not in by_ref:
                out.append(f"{c.ref}: declared chip {ref} is not in this design")
                continue
            if key is None:
                continue
            nums = [n for n, name, _ in _pin_list(by_ref[ref]) if key in (n, name)]
            if not nums:
                out.append(f"{c.ref}: declared pin {ref}:{key} does not exist")
            elif not any(pin_net.get((ref, n)) in mine for n in nums):
                out.append(f"{c.ref}: declared pin {ref}:{key} is on "
                           f"{pin_net.get((ref, nums[0]))}, not on {'/'.join(sorted(mine))}")
    return out


def _board_blocks(comps, ctx, groups) -> list:
    """One board's blocks in reading order: each multi-pin part (with its
    satellites and bank) followed by its leftover small parts, then the
    unowned small parts, then the pad groups."""
    by_ref = {c.ref: c for c in comps}
    grouped = [(t, [by_ref[r] for r in refs if r in by_ref]) for t, refs in groups]
    grouped = [(t, pads) for t, pads in grouped if pads]
    in_group = {c.ref for _, pads in grouped for c in pads}
    big, small, owner = _assign_owners([c for c in comps if c.ref not in in_group], ctx)
    blocks = []
    placed: set = set()
    for ic in big:
        mine = [s for s in small if owner[s.ref] == ic.ref]
        bank = [s for s in mine if _is_bank(ctx, s)]
        cands = [s for s in mine if s.ref not in {b.ref for b in bank}]
        bank = _attach_bank(ic, bank, ctx)     # what's left has no pin to hang on
        n_units = len(ctx.comp_sym[ic.ref].units)
        for ui in range(n_units):
            blocks.append(_unit_block(ic, ui, ctx, cands,
                                      bank if ui == n_units - 1 else [], placed))
        blocks.extend(_unit_block(s, 0, ctx, [], [], placed)
                      for s in cands if s.ref not in placed and ctx.comp_sym[s.ref].units)
    loose = [s for s in small if owner[s.ref] is None and ctx.comp_sym[s.ref].units]
    rail_only = [s for s in loose if _is_bank(ctx, s)]
    blocks.extend(_unit_block(s, 0, ctx, [], [], placed)
                  for s in loose if s not in rail_only)
    if rail_only:
        # No declared pin: drawn on its rail, deliberately not on a chip.
        blk = _Block()
        title = "Rail decoupling - no pin declared"
        blk.prims.append(("text", title, 0, 0, 1.5))
        blk.text(title, 0, 0, "left bottom", 1.5)
        _layout_bank(blk, ctx, rail_only, 0, 0)
        blocks.append(blk)
    blocks.extend(_pad_group_block(t, pads, ctx) for t, pads in grouped)
    return blocks


def _shift_prim(prim, dx, dy):
    k = prim[0]
    if k == "sym":
        _, lsym, c, uno, x, y, fields = prim
        return (k, lsym, c, uno, x + dx, y + dy,
                [(n, v, fx + dx, fy + dy, j, h, s) for n, v, fx, fy, j, h, s in fields])
    if k == "wire":
        _, x1, y1, x2, y2 = prim
        return (k, x1 + dx, y1 + dy, x2 + dx, y2 + dy)
    if k == "rect":
        _, x0, y0, x1, y1 = prim
        return (k, x0 + dx, y0 + dy, x1 + dx, y1 + dy)
    if k == "pwr":
        return (k, prim[1], prim[2] + dx, prim[3] + dy)
    if k == "label":
        _, net, x, y, ang, glob = prim
        return (k, net, x + dx, y + dy, ang, glob)
    if k == "text":
        _, s, x, y, size = prim
        return (k, s, x + dx, y + dy, size)
    _, x, y = prim                              # nc
    return (k, x + dx, y + dy)


def _pad_group_block(title, pads, ctx) -> _Block:
    """Pads stacked in one column inside a titled dashed box, each pin
    labelled outward like a connector."""
    grp = _Block()
    y = 0.0
    for c in pads:                              # caller's order
        for ui in range(len(ctx.comp_sym[c.ref].units)):
            sub = _unit_block(c, ui, ctx, [], [], set())
            dy = _ceil_to(y - sub.bb[1], _G)
            grp.prims.extend(_shift_prim(p, 0, dy) for p in sub.prims)
            grp.box(sub.bb[0], sub.bb[1] + dy, sub.bb[2], sub.bb[3] + dy)
            y = sub.bb[3] + dy
    x0, y0, x1, y1 = grp.bb[0] - _G, grp.bb[1] - _G, grp.bb[2] + _G, grp.bb[3] + _G
    grp.prims.append(("rect", x0, y0, x1, y1))
    grp.prims.append(("text", title, x0, y0 - 1.0, 2.0))
    grp.box(x0, y0 - 3.5, x1, y1)
    grp.text(title, x0, y0 - 1.0, "left bottom", 2.0)
    return grp


class _Region:
    """One board's blocks, packed, inside a titled frame."""
    _PAD = 2 * _G
    _TITLE = 4 * _G

    def __init__(self, board, blocks):
        self.board, self.blocks = board, blocks
        area = sum(b.width * b.height for b in blocks)
        target = max((area * 1.6) ** 0.5, max(b.width for b in blocks))
        self.w, self.h = _shelf_pack(blocks, target, 0.0)
        self.x = self.y = 0.0

    width = property(lambda self: self.w + 2 * self._PAD)
    height = property(lambda self: self.h + 2 * self._PAD + self._TITLE)
    origin_dx = property(lambda self: self._PAD)
    origin_dy = property(lambda self: self._PAD + self._TITLE)


def _write_flat(out, project, lib, regions) -> None:
    paper = _pack_on_paper(regions)
    root_uuid = _uid(project, "root")
    inst_path = f"/{root_uuid}"
    used: dict = {}
    items: list = []
    pins: list = []                     # symbol + power-symbol pin ends
    wires: list = []
    pwr_no = 1

    for rg in regions:
        board = rg.board
        fx0, fy0 = rg.x - rg._PAD, rg.y - rg._PAD - rg._TITLE
        items.append(
            f'\t(rectangle (start {_f(fx0)} {_f(fy0)}) (end {_f(fx0 + rg.width)} {_f(fy0 + rg.height)}) '
            f'(stroke (width 0.5) (type solid)) (fill (type none)) (uuid {_q(_uid(board, "frame"))}))')
        items.append(
            f'\t(text {_q(board)} (exclude_from_sim no) (at {_f(fx0 + _G)} {_f(fy0 + 3 * _G)} 0) '
            f'(effects (font (size 5 5) (thickness 0.6)) (justify left bottom)) '
            f'(uuid {_q(_uid(board, "title"))}))')
        for bi, blk in enumerate(rg.blocks):
            BX, BY = rg.x + blk.x, rg.y + blk.y
            for pi, prim in enumerate(blk.prims):
                seed = (board, str(bi), str(pi))
                kind = prim[0]
                if kind == "sym":
                    _, lsym, c, uno, x, y, fields = prim
                    X, Y = BX + x, BY + y
                    used[lsym.name] = lsym
                    items.extend(_symbol_instance(project, lib, inst_path, board, lsym, c,
                                                  uno, X, Y, BX, BY, fields))
                    for p in lsym.units[uno - 1].pins:
                        pins.append((X + p.x, Y - p.y))
                elif kind == "pwr":
                    _, psym, x, y = prim
                    X, Y = BX + x, BY + y
                    used[psym.name] = psym
                    ref = f"#PWR{pwr_no:04d}"
                    pwr_no += 1
                    vx, vy, just = _PWR_TEXT[psym.d]
                    items += [
                        f'\t(symbol (lib_id {_q(f"{lib}:{psym.name}")}) (at {_f(X)} {_f(Y)} 0) (unit 1)',
                        '\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)',
                        f'\t\t(uuid {_q(_uid(*seed, "pwr"))})',
                        f'\t\t(property "Reference" {_q(ref)} (at {_f(X)} {_f(Y)} 0) {_font(hide=True)})',
                        f'\t\t(property "Value" {_q(psym.net)} (at {_f(X + vx)} {_f(Y + vy)} 0) {_font(justify=just)})',
                        f'\t\t(property "Footprint" "" (at {_f(X)} {_f(Y)} 0) {_font(hide=True)})',
                        f'\t\t(property "Datasheet" "" (at {_f(X)} {_f(Y)} 0) {_font(hide=True)})',
                        f'\t\t(property "Description" "" (at {_f(X)} {_f(Y)} 0) {_font(hide=True)})',
                        f'\t\t(pin "1" (uuid {_q(_uid(*seed, "pwr", "pin"))}))',
                        f'\t\t(instances (project {_q(project)} (path {_q(inst_path)} '
                        f'(reference {_q(ref)}) (unit 1))))',
                        '\t)',
                    ]
                    pins.append((X, Y))
                elif kind == "wire":
                    _, x1, y1, x2, y2 = prim
                    X1, Y1, X2, Y2 = BX + x1, BY + y1, BX + x2, BY + y2
                    # Start before end (left→right, top→bottom), a
                    # canonical form so regenerating diffs cleanly.
                    if (round(X2, 3), round(Y2, 3)) < (round(X1, 3), round(Y1, 3)):
                        X1, Y1, X2, Y2 = X2, Y2, X1, Y1
                    items.append(f'\t(wire (pts (xy {_f(X1)} {_f(Y1)}) (xy {_f(X2)} {_f(Y2)})) '
                                 f'(stroke (width 0) (type default)) (uuid {_q(_uid(*seed, "wire"))}))')
                    wires.append((X1, Y1, X2, Y2))
                elif kind == "label":
                    _, net, x, y, ang, glob = prim
                    X, Y = BX + x, BY + y
                    if glob:
                        just = "right" if ang in (180, 270) else "left"
                        items.append(
                            f'\t(global_label {_q(net)} (shape bidirectional) (at {_f(X)} {_f(Y)} {ang}) '
                            f'(fields_autoplaced yes) {_font(justify=just)} (uuid {_q(_uid(*seed, "glabel"))}))')
                    else:
                        just = "right bottom" if ang in (180, 270) else "left bottom"
                        items.append(
                            f'\t(label {_q(net)} (at {_f(X)} {_f(Y)} {ang}) '
                            f'(fields_autoplaced yes) {_font(justify=just)} (uuid {_q(_uid(*seed, "label"))}))')
                elif kind == "nc":
                    _, x, y = prim
                    items.append(f'\t(no_connect (at {_f(BX + x)} {_f(BY + y)}) '
                                 f'(uuid {_q(_uid(*seed, "nc"))}))')
                elif kind == "rect":
                    _, x0, y0, x1, y1 = prim
                    items.append(
                        f'\t(rectangle (start {_f(BX + x0)} {_f(BY + y0)}) (end {_f(BX + x1)} {_f(BY + y1)}) '
                        f'(stroke (width 0.254) (type dash)) (fill (type none)) (uuid {_q(_uid(*seed, "rect"))}))')
                elif kind == "text":
                    _, s, x, y, size = prim
                    items.append(
                        f'\t(text {_q(s)} (exclude_from_sim no) (at {_f(BX + x)} {_f(BY + y)} 0) '
                        f'{_font(justify="left bottom", size=size)} (uuid {_q(_uid(*seed, "text"))}))')
    hazards = _wiring_hazards(wires, pins)
    if hazards:
        raise ValueError(f"{project}: wiring KiCad's editor would cut on cleanup: "
                         + "; ".join(hazards[:5]))

    body = [
        f'(kicad_sch (version {_VERSION}) (generator "smash") (generator_version "10.0")',
        f'\t(uuid {_q(root_uuid)})',
        f'\t{paper}',
        f'\t(title_block (title {_q(project)}) (comment 1 "Generated by smash.export.kicad_sch from the design model - do not edit; regenerate") '
        f'(comment 2 "One frame per board. Power symbols = rails; global labels = signals that cross boards; local labels = single-board signals."))',
        '\t(lib_symbols',
        *[_lib_symbol_sexpr(used[k], lib) for k in sorted(used)],
        '\t)',
        *items,
        '\t(sheet_instances (path "/" (page "1")))',
        ')',
    ]
    (out / f"{project}.kicad_sch").write_text("\n".join(body) + "\n")


def _wiring_hazards(wires, pins) -> list:
    """Connections that would only hold through a junction. KiCad's editor
    deletes junctions it judges unneeded (and then merges the wires around
    them) before Update PCB from Schematic — kicad-cli does not, so its
    netlist can't show the damage. So every connection point must join
    exactly two items (wire ends, pin ends), and nothing may end on the
    middle of a wire."""
    def key(x, y):
        return (round(x, 3), round(y, 3))
    horiz: dict = {}                    # y → [(x0, x1)]
    vert: dict = {}                     # x → [(y0, y1)]
    count: dict = {}                    # point → items ending there
    for x1, y1, x2, y2 in wires:
        a, b = key(x1, y1), key(x2, y2)
        if a[1] == b[1]:
            horiz.setdefault(a[1], []).append(sorted((a[0], b[0])))
        else:
            vert.setdefault(a[0], []).append(sorted((a[1], b[1])))
        for k in (a, b):
            count[k] = count.get(k, 0) + 1
    for x, y in pins:
        k = key(x, y)
        count[k] = count.get(k, 0) + 1

    def on_middle(p) -> bool:
        x, y = p
        return (any(a < x < b for a, b in horiz.get(y, ()))
                or any(a < y < b for a, b in vert.get(x, ())))

    out = [f"{n} items meet at {p}" for p, n in sorted(count.items()) if n > 2]
    out += [f"something ends on the middle of a wire at {p}" for p in sorted(count) if on_middle(p)]
    return out


def _symbol_instance(project, lib, inst_path, board, lsym, c, uno, X, Y, bx, by,
                     fields) -> list:
    seed = (board, c.ref, str(uno))
    out = [
        f'\t(symbol (lib_id {_q(f"{lib}:{lsym.name}")}) (at {_f(X)} {_f(Y)} 0) (unit {uno})',
        '\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)',
        f'\t\t(uuid {_q(_uid(*seed, "sym"))})',
    ]
    for name, val, fx, fy, just, hide, size in fields:
        out.append(f'\t\t(property {_q(name)} {_q(val)} (at {_f(bx + fx)} {_f(by + fy)} 0) '
                   f'{_font(hide, just, size)})')
    for p in lsym.units[uno - 1].pins:
        out.append(f'\t\t(pin {_q(p.num)} (uuid {_q(_uid(*seed, "pin", p.num))}))')
    out.append(f'\t\t(instances (project {_q(project)} (path {_q(inst_path)} '
               f'(reference {_q(kicad_ref(c.ref))}) (unit {uno}))))')
    out.append('\t)')
    return out


def _write_library(out, project, lib: str, symlib: _SymbolLibrary) -> None:
    syms = [_lib_symbol_sexpr(symlib.by_name[k], None) for k in sorted(symlib.by_name)]
    (out / f"{project}.kicad_sym").write_text(
        f'(kicad_symbol_lib (version {_VERSION}) (generator "smash") (generator_version "10.0")\n'
        + "\n".join(syms) + "\n)\n")
    (out / "sym-lib-table").write_text(
        '(sym_lib_table\n  (version 7)\n'
        f'  (lib (name {_q(lib)})(type "KiCad")(uri "${{KIPRJMOD}}/{project}.kicad_sym")(options "")(descr "Generated by smash"))\n'
        ')\n')


def _write_project_file(out, project) -> None:
    (out / f"{project}.kicad_pro").write_text(json.dumps({
        "meta": {"filename": f"{project}.kicad_pro", "version": 3},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [],
    }, indent=2) + "\n")
