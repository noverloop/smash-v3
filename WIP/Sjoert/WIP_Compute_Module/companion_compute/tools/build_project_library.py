#!/usr/bin/env python3
"""
build_project_library.py - Companion Compute project-portable footprint library.

Creates, next to companion_compute.kicad_pro:

    companion_compute.pretty/      one .kicad_mod per unique footprint on the board
    companion_compute.3dshapes/    copies of every 3D model the footprints use
    fp-lib-table                   project library table (nickname "SmashCompute",
                                   uri ${KIPRJMOD}/companion_compute.pretty)

and relinks companion_compute.kicad_pcb so every footprint points at
"SmashCompute:<name>" and every 3D model at ${KIPRJMOD}/companion_compute.3dshapes/.
After that, "Tools > Update Footprints from Library..." in the PCB editor pulls
edits from the project library straight onto the board.

Back-side handling
------------------
The smash generator writes back-side footprints as a left/right mirror (x negated)
with the *front* orientation, and writes pad angles relative to the footprint.
KiCad expects back-side children as a top/bottom mirror (y negated) of the
library footprint and pad angles as absolute. The relink step converts each
footprint to KiCad's convention without moving any copper:
    back side : orientation += 180, local x/y negated (geometry identical)
    all sides : pad angle written as absolute (= footprint orientation)
so "Update Footprints from Library" reproduces the board exactly.

Usage (run from anywhere):
    python tools/build_project_library.py            # extract library + relink board
    python tools/build_project_library.py --extract  # only (re)build the library
    python tools/build_project_library.py --relink   # only relink the board
    python tools/build_project_library.py --force    # overwrite existing .kicad_mod files

Existing .kicad_mod files are kept unless --force is given, so footprints you
have edited in the library are never overwritten by a re-run.
A backup of the board is written to backup/ before it is changed.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import sys
from pathlib import Path, PureWindowsPath

LIB = "companion_compute"          # file/folder stem (.pretty, .3dshapes, .kicad_pcb)
NICKNAME = "SmashCompute"          # library name shown in KiCad's library browser
LEGACY_NICKNAMES = ("companion_compute",)  # earlier nicknames, renamed on relink
PROJECT_DIR = Path(__file__).resolve().parent.parent
PCB = PROJECT_DIR / f"{LIB}.kicad_pcb"
PRETTY = PROJECT_DIR / f"{LIB}.pretty"
SHAPES = PROJECT_DIR / f"{LIB}.3dshapes"
FP_LIB_TABLE = PROJECT_DIR / "fp-lib-table"
MODEL_PREFIX = "${KIPRJMOD}/" + f"{LIB}.3dshapes/"
# Where to look for a model when its absolute path does not exist on this machine
REPO_ROOT = PROJECT_DIR.parent.parent


# --------------------------------------------------------------------------- s-expr
class Sym(str):
    """Unquoted atom (keyword or number)."""


class Str(str):
    """Quoted string atom."""


_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse(text: str, pos: int = 0):
    """Parse one s-expression starting at text[pos]; returns (node, end_pos)."""
    stack: list[list] = []
    while True:
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"parse error at {pos}")
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            node = stack.pop()
            if not stack:
                return node, pos
            stack[-1].append(node)
        else:
            atom = Str(m.group(3)) if m.group(3) is not None else Sym(m.group(4))
            if not stack:
                return atom, pos
            stack[-1].append(atom)


def _atom(a) -> str:
    if isinstance(a, Str):
        # KiCad stores paths with raw backslashes; keep them as-is, escape quotes only
        return '"' + a.replace('"', '\\"') + '"'
    return str(a)


_INLINE = {"at", "size", "drill", "layers", "net", "uuid", "layer", "xy", "pts", "stroke",
           "fill", "effects", "font", "offset", "scale", "rotate", "xyz", "hide", "width",
           "type", "thickness", "attr", "descr", "tags", "embedded_fonts", "version",
           "generator", "generator_version", "roundrect_rratio", "pinfunction", "pintype"}


def dump(node, indent: int = 0) -> str:
    """Serialise in KiCad-like layout (tabs, one child list per line)."""
    if not isinstance(node, list):
        return _atom(node)
    head = node[0] if node else ""
    if head in _INLINE or all(not isinstance(c, list) for c in node):
        return "(" + " ".join(dump(c) for c in node) + ")"
    tab = "\t" * (indent + 1)
    parts = [dump(c) for c in node if not isinstance(c, list)]
    out = "(" + " ".join(parts)
    for c in node:
        if isinstance(c, list):
            out += "\n" + tab + dump(c, indent + 1)
    return out + "\n" + "\t" * indent + ")"


def find(node, key):
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def find_all(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def num(x) -> float:
    return float(x)


def fmt(v: float) -> Sym:
    v = round(v, 6)
    if v == 0:
        v = 0.0
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return Sym(s if s not in ("-0", "") else "0")


# --------------------------------------------------------------- geometry helpers
def swap_side(layer: str) -> str:
    if layer.startswith("F."):
        return "B." + layer[2:]
    if layer.startswith("B."):
        return "F." + layer[2:]
    return layer


def walk(node, fn):
    """Apply fn to every list node (depth first)."""
    if isinstance(node, list):
        fn(node)
        for c in node:
            walk(c, fn)


def transform_xy(fp, fx: float, fy: float):
    """Multiply every local x by fx and y by fy (pads, graphics, fields)."""
    def fn(n):
        if n and n[0] in ("xy", "start", "end", "mid", "center") and len(n) >= 3:
            n[1], n[2] = fmt(num(n[1]) * fx), fmt(num(n[2]) * fy)
        elif n and n[0] == "at" and len(n) >= 3 and n is not find(fp, "at"):
            n[1], n[2] = fmt(num(n[1]) * fx), fmt(num(n[2]) * fy)
    for c in fp:
        if isinstance(c, list) and c and c[0] not in ("at", "model"):
            walk(c, fn)


def swap_layers(fp):
    def fn(n):
        if n and n[0] == "layer" and len(n) >= 2 and isinstance(n[1], Str):
            n[1] = Str(swap_side(n[1]))
        elif n and n[0] == "layers":
            n[1:] = [Str(swap_side(x)) for x in n[1:]]
    walk(fp, fn)


def fp_side(fp) -> str:
    return str(find(fp, "layer")[1])


def fp_orient(fp) -> float:
    at = find(fp, "at")
    return num(at[3]) if at is not None and len(at) > 3 else 0.0


def set_fp_orient(fp, a: float):
    at = find(fp, "at")
    a = a % 360
    if len(at) > 3:
        at[3] = fmt(a)
    else:
        at.append(fmt(a))


def set_pad_angles(fp, angle: float):
    """Write the absolute pad angle (KiCad convention)."""
    angle = angle % 360
    for pad in find_all(fp, "pad"):
        at = find(pad, "at")
        del at[3:]
        if angle:
            at.append(fmt(angle))


def model_name(path: str) -> str:
    return PureWindowsPath(path).name if "\\" in path else Path(path).name


# ----------------------------------------------------------------- board reading
def board_footprints(text: str):
    """Yield (start, end, node) for each top-level footprint in the board text."""
    for m in re.finditer(r"^\t\(footprint ", text, re.M):
        node, end = parse(text, m.start())
        yield m.start() + 1, end, node


def fp_name(fp) -> str:
    return str(fp[1]).split(":", 1)[-1]


def is_relinked(fp) -> bool:
    return ":" in str(fp[1]) and str(fp[1]).split(":", 1)[0] in (NICKNAME,) + LEGACY_NICKNAMES


# ------------------------------------------------------------------ extraction
def to_library_footprint(inst) -> list:
    import copy
    fp = copy.deepcopy(inst)
    name = fp_name(fp)
    back = fp_side(fp) == "B.Cu"
    orient = fp_orient(fp)

    if back:
        if is_relinked(inst):
            # KiCad convention: local = library mirrored top/bottom
            transform_xy(fp, 1, -1)
        else:
            # smash generator convention: local = library mirrored left/right
            transform_xy(fp, -1, 1)
        swap_layers(fp)

    # pad angles -> relative to footprint (library frame)
    for pad in find_all(fp, "pad"):
        at = find(pad, "at")
        if len(at) > 3:
            rel = (num(at[3]) - orient) if is_relinked(inst) else num(at[3])
            if back and is_relinked(inst):
                rel = -rel
            del at[3:]
            if rel % 360:
                at.append(fmt(rel % 360))

    # strip board-only data
    keep = []
    for c in fp[2:]:
        if not isinstance(c, list):
            continue
        if c[0] in ("uuid", "at", "path", "sheetname", "sheetfile", "locked"):
            continue
        keep.append(c)

    def strip(n):
        if isinstance(n, list):
            n[:] = [c for c in n if not (isinstance(c, list) and c and c[0] in ("uuid", "net"))]
    for c in keep:
        walk(c, strip)

    for prop in find_all(keep, "property"):
        if prop[1] == "Reference":
            prop[2] = Str("REF**")
        elif prop[1] == "Value":
            prop[2] = Str(name)
    for m in find_all(keep, "model"):
        m[1] = Str(MODEL_PREFIX + model_name(m[1]))

    head = [Sym("footprint"), Str(name),
            [Sym("version"), Sym("20260206")],
            [Sym("generator"), Str("build_project_library")],
            [Sym("generator_version"), Str("10.0")]]
    layer = find(keep, "layer")
    keep.remove(layer)
    return head + [layer] + keep


def pick_instance(instances):
    def score(fp):
        return (fp_side(fp) != "F.Cu", fp_orient(fp) % 360 != 0)
    return sorted(instances, key=score)[0]


def copy_models(text: str) -> list[str]:
    SHAPES.mkdir(exist_ok=True)
    missing = []
    for path in sorted(set(re.findall(r'\(model "([^"]+)"', text))):
        if path.startswith(MODEL_PREFIX):
            continue
        name = model_name(path)
        dst = SHAPES / name
        if dst.exists():
            continue
        candidates = [Path(path)]
        win = PureWindowsPath(path)
        if "smash-electronics" in win.parts:
            rel = win.parts[win.parts.index("smash-electronics") + 1:]
            candidates.append(REPO_ROOT.joinpath(*rel))
        src = next((c for c in candidates if c.is_file()), None)
        if src:
            shutil.copy2(src, dst)
            print(f"  3D  {name}")
        else:
            missing.append(path)
    return missing


def extract(force: bool):
    text = PCB.read_text(encoding="utf-8")
    groups: dict[str, list] = {}
    for _, _, fp in board_footprints(text):
        groups.setdefault(fp_name(fp), []).append(fp)
    PRETTY.mkdir(exist_ok=True)
    for name, inst in sorted(groups.items()):
        dst = PRETTY / f"{name}.kicad_mod"
        if dst.exists() and not force:
            print(f"  keep {dst.name} (exists, use --force to overwrite)")
            continue
        lib_fp = to_library_footprint(pick_instance(inst))
        dst.write_text(dump(lib_fp) + "\n", encoding="utf-8")
        print(f"  FP  {dst.name}  ({len(inst)}x on board)")
    missing = copy_models(text)
    for m in missing:
        print(f"  WARNING: 3D model not found: {m}", file=sys.stderr)
    write_fp_lib_table()


def write_fp_lib_table():
    entry = (f'\t(lib (name "{NICKNAME}")(type "KiCad")(uri "${{KIPRJMOD}}/{LIB}.pretty")'
             f'(options "")(descr "Companion Compute project footprints"))')
    if FP_LIB_TABLE.exists():
        t = FP_LIB_TABLE.read_text(encoding="utf-8")
        if f'(name "{NICKNAME}")' in t:
            return
        for old in LEGACY_NICKNAMES:
            if f'(name "{old}")' in t:
                t = t.replace(f'(name "{old}")', f'(name "{NICKNAME}")')
                FP_LIB_TABLE.write_text(t, encoding="utf-8")
                print(f"  fp-lib-table: renamed {old} -> {NICKNAME}")
                return
        t = t.rstrip().rstrip(")").rstrip() + "\n" + entry + "\n)\n"
    else:
        t = "(fp_lib_table\n\t(version 7)\n" + entry + "\n)\n"
    FP_LIB_TABLE.write_text(t, encoding="utf-8")
    print("  fp-lib-table written")


# --------------------------------------------------------------------- relink
def relink_fp(fp):
    if is_relinked(fp):
        if str(fp[1]).split(":", 1)[0] != NICKNAME:      # legacy nickname: rename only
            fp[1] = Str(f"{NICKNAME}:{fp_name(fp)}")
            return fp, True
        return fp, False
    orient = fp_orient(fp)
    if fp_side(fp) == "B.Cu":
        # generator: abs = R(o) * mirrorX(L); KiCad: abs = R(o') * mirrorY(L)
        # mirrorX = R(180) * mirrorY  ->  o' = o + 180, local rotated by 180
        orient += 180
        set_fp_orient(fp, orient)
        transform_xy(fp, -1, -1)
    set_pad_angles(fp, orient)
    fp[1] = Str(f"{NICKNAME}:{fp_name(fp)}")
    for m in find_all(fp, "model"):
        m[1] = Str(MODEL_PREFIX + model_name(m[1]))
    return fp, True


def relink():
    text = PCB.read_text(encoding="utf-8")
    out, last, changed = [], 0, 0
    for start, end, fp in board_footprints(text):
        fp, did = relink_fp(fp)
        if did:
            out.append(text[last:start])
            out.append(dump(fp, 1))
            last = end
            changed += 1
    if not changed:
        print("  board already relinked")
        return
    out.append(text[last:])
    backup = PROJECT_DIR / "backup"
    backup.mkdir(exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(PCB, backup / f"{LIB}_{stamp}.kicad_pcb")
    PCB.write_text("".join(out), encoding="utf-8")
    print(f"  relinked {changed} footprints -> {NICKNAME}:<name>  (backup in backup/)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--extract", action="store_true", help="only build the library")
    ap.add_argument("--relink", action="store_true", help="only relink the board")
    ap.add_argument("--force", action="store_true", help="overwrite existing .kicad_mod files")
    a = ap.parse_args()
    both = not (a.extract or a.relink)
    print(f"Project: {PROJECT_DIR}")
    write_fp_lib_table()
    if a.extract or both:
        print("Extracting footprints ...")
        extract(a.force)
    if a.relink or both:
        print("Relinking board ...")
        relink()


if __name__ == "__main__":
    main()
