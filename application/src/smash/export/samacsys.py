"""A part's SamacSys download, as the KiCad exports use it.

`find_symbol` locates the SamacSys `.kicad_sym` whose pin numbers are
exactly the part's (the part factories build their pin lists from that
same file, so it normally is) and reads it into plain data: its pins and
its body graphics, re-centred on the 2.54 mm grid. `copy_libraries`
copies a part's SamacSys KiCad symbol and Altium libraries (`.SchLib` /
`.PcbLib`, pulled out of the `.samacsys.zip`) into a board project.
"""
from __future__ import annotations

import functools
import pathlib
import re
import shutil
import zipfile

from smash.export._common import _strip_ball_prefix
from smash.roots import resolve_repo_path

_SOURCES = (pathlib.Path(__file__).parents[1] / "parts" / "sources").resolve()
_G = 2.54
_NUM = r"-?\d+(?:\.\d+)?"
_GRAPHICS = ("rectangle", "polyline", "circle", "arc", "bezier", "text")


class SamacSysPin:
    __slots__ = ("num", "name", "etype", "x", "y", "angle", "length")

    def __init__(self, num, name, etype, x, y, angle, length):
        self.num, self.name, self.etype = num, name, etype
        self.x, self.y, self.angle, self.length = x, y, angle, length


class SamacSysSymbol:
    """One single-unit SamacSys symbol, shifted so its body is centred on
    the origin (by whole grid steps, so pins stay on grid). Coordinates
    are KiCad library coordinates (y up)."""

    def __init__(self, name, path, pins, graphics, body):
        self.name = name                 # the symbol's own name
        self.path = path                 # the .kicad_sym it came from
        self.pins = pins                 # [SamacSysPin], file order
        self.graphics = graphics         # body s-expressions, already shifted
        self.x0, self.y0, self.x1, self.y1 = body


def _block_end(text: str, i: int) -> int:
    """Index just past the `)` closing the `(` at text[i]."""
    depth, in_str = 0, False
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced s-expression")


def _children(text: str, start: int, end: int):
    """(keyword, chunk) for each direct child list of the block text[start:end]."""
    i = text.index("(", start + 1)
    while i < end - 1:
        j = _block_end(text, i)
        m = re.match(r"\((\w+)", text[i:j])
        yield (m.group(1) if m else ""), text[i:j]
        k = text.find("(", j)
        if k < 0 or k >= end - 1:
            break
        i = k


def _shift(chunk: str, dx: float, dy: float) -> str:
    def fmt(v: float) -> str:
        v = round(v, 4)
        return str(int(v)) if v == int(v) else f"{v:.4f}".rstrip("0").rstrip(".")
    return re.sub(rf"\((xy|start|end|center|mid|at) ({_NUM}) ({_NUM})",
                  lambda m: f"({m.group(1)} {fmt(float(m.group(2)) + dx)} "
                            f"{fmt(float(m.group(3)) + dy)}", chunk)


def _points(chunk: str) -> list:
    pts = [(float(x), float(y)) for _, x, y in
           re.findall(rf"\((xy|start|end|center|mid) ({_NUM}) ({_NUM})\)", chunk)]
    r = re.search(rf"\(radius ({_NUM})\)", chunk)
    c = re.search(rf"\(center ({_NUM}) ({_NUM})\)", chunk)
    if r and c:
        cx, cy, rad = float(c.group(1)), float(c.group(2)), float(r.group(1))
        pts += [(cx - rad, cy - rad), (cx + rad, cy + rad)]
    return pts


@functools.lru_cache(maxsize=None)
def _parse(path: str) -> SamacSysSymbol | None:
    """The first symbol of a SamacSys `.kicad_sym`, or None when it is one
    the schematic can't use: several units, pins off the 1.27 mm grid, or
    two pins on one spot."""
    text = pathlib.Path(path).read_text()
    m = re.search(r'\(symbol "([^"]+)"', text)
    if not m:
        return None
    start = m.start()
    end = _block_end(text, start)
    graphics, pins, units = [], [], set()

    def walk(s, e):
        for kw, chunk in _children(text, s, e):
            if kw == "symbol":
                u = re.match(r'\(symbol "[^"]*?_(\d+)_\d+"', chunk)
                if u and u.group(1) != "0":
                    units.add(u.group(1))
                off = text.index(chunk, s)
                walk(off, off + len(chunk))
            elif kw in _GRAPHICS:
                graphics.append(chunk)
            elif kw == "pin":
                h = re.match(rf'\(pin (\w+) \w+ \(at ({_NUM}) ({_NUM})(?: ({_NUM}))?\) \(length ({_NUM})\)', chunk)
                name = re.search(r'\(name "((?:[^"\\]|\\.)*)"', chunk)
                num = re.search(r'\(number "((?:[^"\\]|\\.)*)"', chunk)
                if not (h and name and num):
                    return
                pins.append(SamacSysPin(num.group(1), name.group(1), h.group(1),
                                        float(h.group(2)), float(h.group(3)),
                                        int(float(h.group(4) or 0)) % 360, float(h.group(5))))
    walk(start, end)
    if len(units) > 1 or not pins or not graphics:
        return None
    on_grid = all(abs(v / 1.27 - round(v / 1.27)) < 1e-6 for p in pins for v in (p.x, p.y))
    if not on_grid or len({(p.x, p.y) for p in pins}) != len(pins):
        return None
    if any(p.angle not in (0, 90, 180, 270) for p in pins):
        return None
    pts = [pt for g in graphics for pt in _points(g)]
    x0, x1 = min(x for x, _ in pts), max(x for x, _ in pts)
    y0, y1 = min(y for _, y in pts), max(y for _, y in pts)
    dx = -round((x0 + x1) / 2 / _G) * _G
    dy = -round((y0 + y1) / 2 / _G) * _G
    for p in pins:
        p.x, p.y = round(p.x + dx, 4), round(p.y + dy, 4)
    return SamacSysSymbol(m.group(1), path, pins, [_shift(g, dx, dy) for g in graphics],
                          (x0 + dx, y0 + dy, x1 + dx, y1 + dy))


def _source_dirs(comp) -> list:
    """Where a part's SamacSys files may live: next to its datasheet, next
    to its 3D model, or `parts/sources/<MPN>/`."""
    out = []
    ds = getattr(comp, "datasheet", None)
    if ds and not re.match(r"\w+://", ds):
        out.append(resolve_repo_path(ds).parent)
    fp = getattr(comp, "footprint", None)
    if fp is not None and getattr(fp, "model_3d_path", None):
        out.append(resolve_repo_path(fp.model_3d_path).parent)
    if getattr(comp, "manf_pn", None):
        out.append(_SOURCES / comp.manf_pn)
    seen, dirs = set(), []
    for d in out:
        if d not in seen and d.is_dir():
            seen.add(d)
            dirs.append(d)
    return dirs


def find_symbol(comp) -> SamacSysSymbol | None:
    """The SamacSys symbol whose pin numbers are exactly `comp`'s, if any."""
    want = sorted(_strip_ball_prefix(str(p.num)) for p in (getattr(comp, "pins", None) or []))
    if not want:
        return None
    for d in _source_dirs(comp):
        for f in sorted(d.glob("*.kicad_sym")):
            sym = _parse(str(f))
            if sym is not None and sorted(p.num for p in sym.pins) == want:
                return sym
    return None


def copy_libraries(comp, dest) -> list:
    """Copy `comp`'s SamacSys KiCad symbol and Altium libraries into
    `dest/<part folder>/` (Altium ones under `Altium/`). Returns the files
    written (relative to `dest`)."""
    dirs = _source_dirs(comp)
    sym = find_symbol(comp)
    src = pathlib.Path(sym.path).parent if sym else (dirs[0] if dirs else None)
    if src is None or not any(src.glob("*.kicad_sym")):
        return []
    dest = pathlib.Path(dest) / src.name
    out = []
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.glob("*.kicad_sym")):
        shutil.copy2(f, dest / f.name)
        out.append(f"{src.name}/{f.name}")
    for z in sorted(src.glob("*.zip")):
        with zipfile.ZipFile(z) as zf:
            for info in zf.infolist():
                if "/Altium/" in info.filename and info.filename.endswith((".SchLib", ".PcbLib")):
                    target = dest / "Altium" / pathlib.PurePosixPath(info.filename).name
                    target.parent.mkdir(exist_ok=True)
                    target.write_bytes(zf.read(info))
                    out.append(f"{src.name}/Altium/{target.name}")
    return out
