"""Turn an emitted per-board `.kicad_pcb` into a *portable KiCad project*.

Every board the generator writes gets a self-contained project directory the
EE can open and edit without any dependency on this repo's absolute paths::

    <board>/
      <board>.kicad_pcb                       footprints → "Smash<Board>:<lib>_<name>"
      fp-lib-table                            nickname → ${KIPRJMOD}/footprints/…
      footprints/Smash<Board>.pretty/*.kicad_mod
      3dmodels/<package>/<model>.stp

That gives KiCad's **Update Footprints from Library** a place to update *from*,
and the 3D-model viewer a project-relative path to load.

Mirror discipline (the subtle part)
-----------------------------------
A KiCad *library* footprint is always stored front-side canonical: when the
footprint is placed on `B.Cu`, KiCad itself mirrors local X and swaps the
`F.*`/`B.*` layers at render time. The board file, by contrast, stores every
footprint instance literally — `smash.export.kicad_pcb._emit_footprint` bakes
the bottom-face mirror into back-side instances on purpose.

So extracting a library footprint from a back-side instance means *un-baking*
that mirror (negate footprint-local X, negate pad rotation, swap layers).
Copying a back-side block verbatim and only relabelling its layers yields a
pre-mirrored library entry, and the next "Update Footprints from Library"
double-flips every Y-asymmetric part — which is exactly how the first
hand-built portable package dropped a 63-pad land array onto the potting
holes. Don't do that; that is what this module exists to prevent.
"""
from __future__ import annotations

import pathlib
import re
import shutil

__all__ = ["library_nickname", "write_portable_project"]

# F.* ↔ B.* layer pairs — a bottom instance's layers are swapped back to
# front-side canonical when it is lifted into the library.
_FLIP = {
    "F.Cu": "B.Cu", "F.Mask": "B.Mask", "F.Paste": "B.Paste",
    "F.SilkS": "B.SilkS", "F.Fab": "B.Fab", "F.CrtYd": "B.CrtYd",
    "F.Adhes": "B.Adhes", "F.CrtYd.User": "B.CrtYd.User",
}
_FLIP.update({v: k for k, v in _FLIP.items()})

_NUM = r"-?\d+(?:\.\d+)?"
_PRJ = "${KIPRJMOD}/"


# ── small helpers ─────────────────────────────────────────────────────

def library_nickname(board_name: str) -> str:
    """`power_board` → `SmashPowerBoard` (the fp-lib-table nickname)."""
    return "Smash" + "".join(p.capitalize() for p in board_name.split("_") if p)


def _fp_filename(fp_name: str) -> str:
    """Board footprint id → library entry name.

    `Capacitor_SMD:C_0402_1005Metric` → `Capacitor_SMD_C_0402_1005Metric`;
    a name with no library prefix passes through unchanged.
    """
    return fp_name.replace(":", "_")


def _fmt(v: float) -> str:
    """Match the emitter's number formatting (and never print `-0`)."""
    if abs(v) < 5e-7:
        v = 0.0
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _neg(tok: str) -> str:
    return _fmt(-float(tok))


def _footprint_blocks(text: str) -> list[tuple[int, int, str]]:
    """Locate every top-level `(footprint …)` block in a board file.

    Returns `(start, end, name)` character offsets, `end` exclusive, found by
    paren counting so a `)` inside a quoted string can't end a block early.
    """
    out: list[tuple[int, int, str]] = []
    for m in re.finditer(r'^\t\(footprint "([^"]+)"', text, re.M):
        i = m.start()
        depth, j, in_str = 0, i, False
        while j < len(text):
            c = text[j]
            if in_str:
                if c == "\\":
                    j += 2
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
                    j += 1
                    break
            j += 1
        out.append((i, j, m.group(1)))
    return out


# ── board block → library footprint ───────────────────────────────────

def _unmirror(line: str) -> str:
    """Undo the baked bottom-face mirror on one line of a footprint block.

    Negates every footprint-local X (pad/graphic positions and polygon
    points) and any explicit pad rotation, since mirror∘R(θ) = R(−θ)∘mirror.
    """
    def _at(m: re.Match) -> str:
        rot = m.group(3)
        tail = "" if rot is None else f" {_neg(rot)}"
        return f"(at {_neg(m.group(1))} {m.group(2)}{tail})"

    line = re.sub(rf"\(at ({_NUM}) ({_NUM})(?: ({_NUM}))?\)", _at, line)
    line = re.sub(rf"\(xy ({_NUM}) ({_NUM})\)",
                  lambda m: f"(xy {_neg(m.group(1))} {m.group(2)})", line)
    for kw in ("start", "end", "center", "mid"):
        line = re.sub(rf"\({kw} ({_NUM}) ({_NUM})\)",
                      lambda m, k=kw: f"({k} {_neg(m.group(1))} {m.group(2)})", line)
    return line


def _flip_layers(line: str) -> str:
    """Swap every `F.*`/`B.*` layer mention on a line."""
    return re.sub(r'"([FB]\.[A-Za-z.]+)"',
                  lambda m: f'"{_FLIP.get(m.group(1), m.group(1))}"', line)


def _paren_delta(line: str) -> int:
    """Net paren depth change of a line, ignoring parens inside strings."""
    bare = re.sub(r'"(?:[^"\\]|\\.)*"', "", line)
    return bare.count("(") - bare.count(")")


def _children(block_lines: list[str]) -> list[list[str]]:
    """Split a footprint block into its direct children (2-tab indent).

    Working on whole child chunks — rather than matching stripped lines —
    keeps a pad's own `(at …)`/`(uuid …)` from being confused with the
    footprint-level ones, which differ only by indentation.
    """
    out: list[list[str]] = []
    cur: list[str] | None = None
    depth = 0
    for raw in block_lines[1:-1]:
        if cur is None:
            if not raw.startswith("\t\t("):
                continue
            cur, depth = [raw], _paren_delta(raw)
        else:
            cur.append(raw)
            depth += _paren_delta(raw)
        if depth <= 0:
            out.append(cur)
            cur, depth = None, 0
    if cur:
        out.append(cur)
    return out


def _to_library_footprint(block: str, *, entry: str, header: dict[str, str],
                          model_rewrite) -> str:
    """Rewrite one board `(footprint …)` block as a `.kicad_mod` body.

    Drops the instance-only fields (board position, instance uuid, pad nets),
    replaces Reference/Value with library placeholders, and un-mirrors the
    block when the instance sits on the back face.
    """
    lines = block.splitlines()
    bottom = _is_bottom(block)
    # KiCad stores a pad's angle absolutely (footprint orientation + any
    # pad-local rotation). A library footprint is unrotated, so the
    # instance's orientation comes back off every pad on the way in.
    orient = _orientation(block)

    body: list[str] = []
    models: list[list[str]] = []
    descr: str | None = None
    attr: str | None = None

    for chunk in _children(lines):
        head = chunk[0].strip()
        kw = head[1:].split(None, 1)[0].rstrip(")")
        if kw == "model":
            models.append(chunk)
            continue
        if kw in ("layer", "uuid", "at", "embedded_fonts"):
            continue                          # instance identity / re-emitted
        if kw == "descr":
            descr = head
            continue
        if kw == "attr":
            attr = head
            continue
        if kw == "property":
            continue                          # Reference/Value re-emitted below
        for raw in chunk:
            if raw.strip().startswith('(net "'):
                continue                      # nets belong to the board
            line = _rel_angle(raw, orient) if kw == "pad" else raw
            if bottom:
                line = _flip_layers(_unmirror(line))
            body.append(line[1:] if line.startswith("\t") else line)

    out: list[str] = [f'(footprint "{entry}"']
    out.append(f'\t(version {header["version"]})')
    out.append(f'\t(generator "{header["generator"]}")')
    out.append(f'\t(generator_version "{header["generator_version"]}")')
    out.append('\t(layer "F.Cu")')
    if descr:
        out.append(f"\t{descr}")
    if attr:
        out.append(f"\t{attr}")
    out.append('\t(property "Reference" "REF**"\n'
               '\t\t(at 0 0 0)\n'
               '\t\t(layer "F.SilkS")\n'
               '\t\t(hide yes)\n'
               '\t\t(effects (font (size 1 1) (thickness 0.15)))\n'
               '\t)')
    out.append(f'\t(property "Value" "{entry}"\n'
               '\t\t(at 0 0 0)\n'
               '\t\t(layer "F.Fab")\n'
               '\t\t(hide yes)\n'
               '\t\t(effects (font (size 1 1) (thickness 0.15)))\n'
               '\t)')
    out.extend(body)
    out.append("\t(embedded_fonts no)")
    for chunk in models:
        for raw in chunk:
            line = re.sub(r'\(model "([^"]+)"',
                          lambda m: f'(model "{model_rewrite(m.group(1))}"', raw)
            out.append(line[1:] if line.startswith("\t") else line)
    out.append(")")
    return "\n".join(out) + "\n"


def _orientation(block: str) -> float:
    """The footprint instance's orientation, from its own `(at …)` line."""
    m = re.search(rf"^\t\t\(at {_NUM} {_NUM}(?: ({_NUM}))?\)$", block, re.M)
    return float(m.group(1)) if (m and m.group(1)) else 0.0


def _rel_angle(line: str, orient: float) -> str:
    """Turn a pad's absolute `(at x y a)` angle into a footprint-local one."""
    if not orient:
        return line

    def _sub(m: re.Match) -> str:
        a = (float(m.group(3) or 0.0) - orient) % 360.0
        tail = f" {_fmt(a)}" if abs(a) > 1e-9 else ""
        return f"(at {m.group(1)} {m.group(2)}{tail})"

    return re.sub(rf"\(at ({_NUM}) ({_NUM})(?: ({_NUM}))?\)", _sub, line)


def _is_bottom(block: str) -> bool:
    """True when this footprint instance sits on the back face."""
    lines = block.splitlines()
    return bool(len(lines) > 1 and re.match(r'^\t\t\(layer "B\.Cu"\)$', lines[1]))


def _signature(kicad_mod: str) -> str:
    """Geometry-only fingerprint, for cross-checking sibling instances."""
    keep = [ln for ln in kicad_mod.splitlines()
            if not ln.strip().startswith(
                ("(uuid ", "(descr ", "(property ", "(model ",
                 "(offset ", "(scale ", "(rotate "))]
    return re.sub(r'\(uuid "[^"]+"\)', "", "\n".join(keep))


# ── the 3D-model side ─────────────────────────────────────────────────

def _model_dest(src: str) -> str | None:
    """Project-relative path a model file is copied to, or None to leave it.

    Keeps the last two components of the source path, matching how the models
    are already organised (`<package>/<file>.stp`,
    `<lib>.3dshapes/<file>.step`). Paths that are already variable-relative
    (`${KICAD…}`, `${KIPRJMOD}`) are resolved by KiCad itself and left alone.
    """
    if src.startswith("${"):
        return None
    p = pathlib.PurePath(src)
    if len(p.parts) < 2:
        return None
    return f"3dmodels/{p.parts[-2]}/{p.parts[-1]}"


# ── entry point ───────────────────────────────────────────────────────

def write_portable_project(pcb_path, *, nickname: str | None = None) -> dict:
    """Make `<pcb_path>`'s directory a portable KiCad project, in place.

    Extracts every footprint the board uses into a project-local `.pretty`
    library, copies every referenced 3D model under `3dmodels/`, repoints the
    board at both, and writes the `fp-lib-table`. Returns a small summary
    dict; never raises for a missing 3D model (it is left pointing at its
    original path and reported in `missing`).
    """
    pcb_path = pathlib.Path(pcb_path)
    proj = pcb_path.parent
    board = pcb_path.stem
    nick = nickname or library_nickname(board)
    text = pcb_path.read_text()

    header = {
        "version": (re.search(r"\(version (\d+)\)", text) or [None, "20260206"])[1],
        "generator": (re.search(r'\(generator "([^"]+)"\)', text) or [None, "smash"])[1],
        "generator_version":
            (re.search(r'\(generator_version "([^"]+)"\)', text) or [None, "10.0"])[1],
    }

    pretty = proj / "footprints" / f"{nick}.pretty"
    models_dir = proj / "3dmodels"
    # The generator owns the library: every entry is re-extracted from the
    # board below, so wipe it rather than letting a renamed or removed part
    # linger as a stale symbol. 3dmodels/ is pruned after the copy instead —
    # deleting it up front would strip an already-portable project of the
    # very files its ${KIPRJMOD} paths point at.
    shutil.rmtree(pretty, ignore_errors=True)
    pretty.mkdir(parents=True, exist_ok=True)

    copied: dict[str, str] = {}      # source path → project-relative path
    used: set[str] = set()           # project-relative paths still referenced
    missing: list[str] = []

    def _rewrite(src: str) -> str:
        if src.startswith(_PRJ):
            rel = src[len(_PRJ):]            # already portable — keep as is
            if (proj / rel).is_file():
                used.add(rel)
            else:
                missing.append(src)
            return src
        rel = _model_dest(src)
        if rel is None:
            return src
        if src not in copied:
            source = pathlib.Path(src)
            if not source.is_file():
                missing.append(src)
                return src
            dest = proj / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            copied[src] = rel
        used.add(rel)
        return _PRJ + rel

    blocks = _footprint_blocks(text)

    # One library entry per distinct footprint. Front-face instances are the
    # natural source (already canonical); a back-face one is un-mirrored. When
    # both exist the geometries must agree — a mismatch means the bottom-face
    # bake and the library extraction disagree, so surface it rather than
    # silently shipping one of them.
    entries: dict[str, str] = {}
    faces: dict[str, str] = {}
    conflicts: list[str] = []
    for start, end, fp_name in blocks:
        block = text[start:end]
        entry = _fp_filename(fp_name.split(":", 1)[1]
                             if fp_name.startswith(nick + ":") else fp_name)
        is_front = not _is_bottom(block)
        kmod = _to_library_footprint(block, entry=entry, header=header,
                                     model_rewrite=_rewrite)
        if entry not in entries:
            entries[entry] = kmod
            faces[entry] = "front" if is_front else "back"
        elif _signature(entries[entry]) != _signature(kmod):
            if faces[entry] == "back" and is_front:
                entries[entry] = kmod          # prefer the un-transformed one
                faces[entry] = "front"
            conflicts.append(entry)

    for entry, kmod in entries.items():
        (pretty / f"{entry}.kicad_mod").write_text(kmod)

    # Repoint the board: footprint ids at the project library, model paths at
    # the copied 3D files.
    def _fp_ref(m: re.Match) -> str:
        # Idempotent: a board already repointed at this library keeps its id
        # rather than growing another nickname prefix.
        name = m.group(1)
        if name.startswith(nick + ":"):
            return f'\t(footprint "{name}"'
        return f'\t(footprint "{nick}:{_fp_filename(name)}"'

    text = re.sub(r'^\t\(footprint "([^"]+)"', _fp_ref, text, flags=re.M)
    text = re.sub(r'\(model "([^"]+)"',
                  lambda m: f'(model "{_rewrite(m.group(1))}"', text)
    pcb_path.write_text(text)

    # Prune 3D models this board no longer references.
    if models_dir.is_dir():
        for f in sorted(models_dir.rglob("*")):
            if f.is_file() and str(f.relative_to(proj)) not in used:
                f.unlink()
        for d in sorted(models_dir.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

    (proj / "fp-lib-table").write_text(
        "(fp_lib_table\n"
        "  (version 7)\n"
        f'  (lib (name "{nick}")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/footprints/{nick}.pretty")(options "")'
        f'(descr "Editable Smash {board.replace("_", "-")} footprints"))\n'
        ")\n"
    )

    return {"nickname": nick, "n_footprints": len(entries),
            "n_models": len(used), "missing_models": sorted(set(missing)),
            "conflicts": sorted(set(conflicts))}
