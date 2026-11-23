#!/usr/bin/env python3
"""Export the generated stackup from dist/ into Unrouted/<YYYYMMDD>/ for check-in.

dist/ is generator output and git-ignored; Unrouted/ holds one dated snapshot
of it that is checked in. Generate with STEP export on, then export:

    SMASH_STEP_EXPORT=1 SMASH_SKIP_CONFIGS=1 python3 generate_stackup.py
    python3 export_unrouted.py            # --date YYYYMMDD (default: today)

Unrouted/ is cleared first: tracked files via `git rm` (they stay in git
history), local leftovers (KiCad .history/, .DS_Store, ...) are deleted. Then
Unrouted/<date>/ gets:

  Smash.kicad_pro / .kicad_sch / .kicad_pcb
                the full stackup KiCad project (dist/stackup.*, renamed: the
                schematic's symbol instances and the PCB's sheet-file
                references follow the new name; the title block is dated)
  stackup.kicad_sym, sym-lib-table, fp-lib-table, empty.kicad_wks, footprints/
                its libraries (paths are ${KIPRJMOD}-relative)
  3dmodels/<part>.stp     component 3D models  flattened from dist's <part>/<file>;
  datasheets/<part>.pdf   datasheets           the project's links follow
  step/         every generated STEP:
                  stackup_components.step(.zip when > 100 MB) + stackup_<config>_components.step
                  (stackup.step / _no_potting / waveguide_stubs only with SMASH_FEA_STEP=1)
                  <board>/<board>.step + <board>_layered.step
                  rings/<board>-<board>_<material>.step + _cam.md, one per gap
                  battery_holder/, sleeve/, potting_mould/ with their _cam.md
                (a part's material and finish are only in its _cam.md)

  LAYOUT_EE_NOTES.md   the hand-maintained repo-root notes, stamped with date + commit
  FOOTPRINT_REVIEW.md  every footprint's provenance (self-drawn / modified vendor
                       lands first, marked CHECK), generated from the design
and Unrouted/<date>.zip next to the folder (the whole snapshot, for the layout EE).
Files over GitHub's 100 MB limit are zipped in place.

Refuses to run if Unrouted/ has uncommitted changes (--force discards them) or
if the last generator run had STEP export off. The result is staged.
"""
from __future__ import annotations

import argparse
import datetime as dt
import filecmp
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent
DIST = REPO / "dist"
MAXI = DIST / "maximalist"
OUT = REPO / "Unrouted"
PROJECT = "Smash"
ROOT_STEPS = ("stackup.step", "stackup_no_potting.step",
              "stackup_components.step", "waveguide_stubs.step")
LIB_FILES = ("stackup.kicad_sym", "sym-lib-table", "fp-lib-table", "empty.kicad_wks")
LIB_DIRS = ("footprints", "3dmodels", "datasheets")
FLAT_DIRS = ("3dmodels", "datasheets")
JUNK = shutil.ignore_patterns(".DS_Store", ".history", "~*.lck")
KIPRJ = re.compile(r'"\$\{KIPRJMOD\}/((?:[^"\\]|\\.)*)"')
WARN_MB, GITHUB_MAX_MB = 50, 100


def git(*args: str, stdin: str | None = None, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=check, input=stdin,
                          capture_output=True, text=True).stdout


def read(p: pathlib.Path) -> str:
    return p.read_bytes().decode("utf-8")


def write(p: pathlib.Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8"))


def swap(text: str, old: str, new: str, what: str) -> tuple[str, int]:
    n = text.count(old)
    if not n:
        sys.exit(f"export: {what}: {old!r} not found; has the generator's output changed?")
    return text.replace(old, new), n


def files(d: pathlib.Path) -> set[pathlib.Path]:
    return {p for p in d.rglob("*") if p.is_file()} if d.exists() else set()


def flatten(src: pathlib.Path, dst: pathlib.Path, prefix: str, warn: list) -> dict[str, str]:
    """Copy src/<part>/<file> to dst/<part><ext>: a folder's only file of its
    type takes the folder's name (the part number); files sharing a folder
    with others of their type keep their own name. Returns
    {'<prefix>/<old path>': '<prefix>/<new name>'} for relink()."""
    dst.mkdir(parents=True, exist_ok=True)
    moves: dict[str, str] = {}
    for f in sorted(src.rglob("*")):
        if not f.is_file() or f.name == ".DS_Store" or ".history" in f.parts:
            continue
        rel = f.relative_to(src)
        same = [q for q in f.parent.iterdir()
                if q.is_file() and q.suffix.lower() == f.suffix.lower()]
        name = f"{f.parent.name}{f.suffix}" if f.parent != src and len(same) == 1 else f.name
        if (dst / name).exists() and not filecmp.cmp(dst / name, f, shallow=False):
            warn.append(f"{prefix}/{rel} and another file both map to {name}; "
                        f"stored as {f.parent.name}_{f.name}")
            name = f"{f.parent.name}_{f.name}"
        if not (dst / name).exists():
            shutil.copy2(f, dst / name)
        moves[f"{prefix}/{rel.as_posix()}"] = f"{prefix}/{name}"
    return moves


def relink(text: str, moves: dict[str, str]) -> str:
    """Point the ${KIPRJMOD} paths in a KiCad file at the flattened files."""
    return KIPRJ.sub(lambda m: '"${KIPRJMOD}/' + moves.get(m.group(1), m.group(1)) + '"', text)


def _rm_readonly(func, path, _exc) -> None:
    """rmtree retry for read-only entries (KiCad's .history is a git repo)."""
    for p in (os.path.dirname(path), path):
        try:
            os.chmod(p, os.stat(p).st_mode | stat.S_IWUSR | stat.S_IXUSR)
        except OSError:
            pass
    func(path)


def gap_label(gap: str, boards: set[str]) -> str:
    """spacer_<a>_<b> -> <a>-<b>; board names contain underscores."""
    rest = gap.removeprefix("spacer_")
    for a in sorted(boards, key=len, reverse=True):
        if rest.startswith(a + "_") and rest[len(a) + 1:] in boards:
            return f"{a}-{rest[len(a) + 1:]}"
    return rest


def kind_material(cam: str) -> tuple[str, str]:
    """('ring', 'PEEK-GF30') from a _cam.md's 'Kind: <k>. Material: <m>.' line."""
    m = re.search(r"^Kind: ([\w-]+)\. Material: (.+)$", cam, re.M)
    if not m:
        return "", "unknown-material"
    kind, mat = m.groups()
    if "PEEK" in mat:
        return kind, "PEEK-GF30" if "GF30" in mat else "PEEK"
    if "7075" in mat:
        return kind, "Al7075"
    head = re.split(r"[(,]", mat)[0]
    return kind, re.sub(r"[^A-Za-z0-9]+", "-", head).strip("-") or "unknown-material"


NOTES = REPO / "LAYOUT_EE_NOTES.md"      # maintained by hand; copied into each export
_VENDOR = {"samacsys", "snapmagic", "samesky", "ultralibrarian"}


DEVB = DIST / "dev_board"
DEVB_SKIP = {"datasheets", "3dmodels", ".history", "dev_board.kicad_prl"}


def export_devboard(dst: pathlib.Path, warn: list) -> int:
    """(2026-11-23, user) dist/dev_board/ → <dst>/dev_board/: the dev-board KiCad
    project, its footprints, fab outputs and fixture collar. Its datasheets/
    and 3dmodels/ are flattened into the SHARED <dst>/datasheets + 3dmodels
    (identical files are stored once) and its ${KIPRJMOD} links point at
    ../datasheets / ../3dmodels. Returns the number of files written."""
    if not (DEVB / "dev_board.kicad_pcb").exists():
        warn.append("no dist/dev_board/: run generate_devboard.py first (dev board not exported)")
        return 0
    newest_src = max((REPO / f).stat().st_mtime for f in ("generate_stackup.py", "generate_devboard.py"))
    if (DEVB / "dev_board.kicad_pcb").stat().st_mtime < newest_src:
        warn.append("dist/dev_board is older than generate_stackup.py / generate_devboard.py — "
                    "re-run generate_devboard.py")
    locks = [p.name for p in DEVB.glob("~*.lck")]
    if locks:
        warn.append(f"KiCad has the dev board open ({', '.join(locks)}); exported the saved files")
    dd = dst / "dev_board"
    dd.mkdir()
    n = 0
    for p in sorted(DEVB.iterdir()):
        if p.name in DEVB_SKIP or p.name.startswith(("~", ".")):
            continue
        if p.is_dir():
            shutil.copytree(p, dd / p.name, ignore=JUNK)
        else:
            shutil.copy2(p, dd / p.name)
    moves: dict[str, str] = {}
    # (2026-11-23, user: the dev board came into Altium without 3D models) 3D
    # models stay INSIDE the dev-board project (dev_board/3dmodels/, linked
    # ${KIPRJMOD}/3dmodels/…) like the tower's — an importer resolving model
    # paths from the project folder can't follow ${KIPRJMOD}/../. Datasheets
    # are only links for humans: they stay shared (../datasheets).
    if (DEVB / "3dmodels").exists():
        moves.update(flatten(DEVB / "3dmodels", dd / "3dmodels", "3dmodels", warn))
    if (DEVB / "datasheets").exists():
        moves.update({k: "../" + v for k, v in
                      flatten(DEVB / "datasheets", dst / "datasheets", "datasheets", warn).items()})
    for p in [*dd.glob("*.kicad_s*"), *dd.glob("*.kicad_pcb"), *(dd / "footprints").rglob("*.kicad_mod")]:
        text = read(p)
        new = relink(text, moves)
        if new != text:
            write(p, new)
    broken = sorted({r for p in [*dd.glob("*.kicad_s*"), *dd.glob("*.kicad_pcb"),
                                 *(dd / "footprints").rglob("*.kicad_mod")]
                     for r in KIPRJ.findall(read(p)) if not (dd / r).exists()})
    if broken:
        warn.append(f"dev_board: {len(broken)} ${{KIPRJMOD}} path(s) not found: " + ", ".join(broken[:8]))
    return n


_MODEL_RX = re.compile(r'\(model\s+"([^"]+)"(.*?)\n\s*\)', re.S)
_XYZ = lambda key, body: (re.search(rf'\({key}\s*\(xyz\s+([-\d.e]+)\s+([-\d.e]+)\s+([-\d.e]+)\)', body)
                          or [None, "0", "0", "0"])


def model_map(dst: pathlib.Path) -> str:
    """(2026-11-23, user: Altium) 3D_MODEL_MAP.csv: every footprint of both
    projects with its STEP file (relative to the export root) and the offset /
    rotation KiCad applies — to attach the models by hand (Altium PcbLib:
    Place » 3D Body) if an importer drops them."""
    rows = ["project,footprint,step_file,offset_x_mm,offset_y_mm,offset_z_mm,rot_x_deg,rot_y_deg,rot_z_deg"]
    for proj, root in (("Smash (tower)", dst), ("dev_board", dst / "dev_board")):
        for mod in sorted((root / "footprints").rglob("*.kicad_mod")):
            text = read(mod)
            m = _MODEL_RX.search(text)
            if not m:
                rows.append(f'"{proj}","{mod.stem}","(no 3D model)",,,,,,')
                continue
            path, body = m.group(1), m.group(2)
            rel = path.replace("${KIPRJMOD}/", "")
            if proj == "dev_board":
                rel = rel[3:] if rel.startswith("../") else "dev_board/" + rel
            off, rot = _XYZ("offset", body), _XYZ("rotate", body)
            ok = (dst / rel).exists()
            rows.append(f'"{proj}","{mod.stem}","{rel if ok else "MISSING " + path}",'
                        f'{off[1]},{off[2]},{off[3]},{rot[1]},{rot[2]},{rot[3]}')
    return "\n".join(rows) + "\n"


ALTIUM_SCRIPT = REPO / "application" / "src" / "smash" / "export" / "altium" / "Attach3DModels.pas"


def altium_model_map(root: pathlib.Path) -> tuple[str, int]:
    """(2026-11-23, user) <project>/3D_MODEL_MAP_altium.txt for Attach3DModels.pas:
    TAB-separated footprint name, STEP path relative to the project folder
    (Windows separators), KiCad offset x/y/z (mm) and rotation x/y/z (deg) as
    KiCad stores them — the script converts the rotation sign."""
    lines = ["# Smash 3D model map for Altium (Attach3DModels.pas) - paths relative to this file",
             "# footprint\tstep_file\toffset_x_mm\toffset_y_mm\toffset_z_mm\trot_x_deg\trot_y_deg\trot_z_deg"]
    n = 0
    for mod in sorted((root / "footprints").rglob("*.kicad_mod")):
        text = read(mod)
        m = _MODEL_RX.search(text)
        if not m:
            continue
        name = re.search(r'\(footprint\s+"([^"]+)"', text).group(1).split(":")[-1]
        rel = m.group(1).replace("${KIPRJMOD}/", "")
        if not (root / rel).exists():
            continue
        off, rot = _XYZ("offset", m.group(2)), _XYZ("rotate", m.group(2))
        lines.append("\t".join([name, rel.replace("/", "\\"), off[1], off[2], off[3], rot[1], rot[2], rot[3]]))
        n += 1
    return "\n".join(lines) + "\n", n


def footprint_review(stamp_line: str) -> str:
    """FOOTPRINT_REVIEW.md: every footprint of the maximalist tower with its
    provenance. Self-drawn lands (datasheet / authored / custom / project)
    and vendor lands we changed (borrowed from a sibling part, 3D model
    rotated, pins renamed) come first and are marked CHECK."""
    import collections
    import generate_stackup as g
    from smash.parts.orderable import apply_orderable
    d = g.Design(); g._set_battery_mode("maximalist"); g._prime_power_rails(d)
    for fn in (g.build_qpd_module, g.build_radar_nose_io, g.build_usb_nose, g.build_camera_module,
               g.build_aft_end_board, g.build_activation_interface,
               g.build_radar_module_awr1843aop, g.build_companion_compute,
               g.build_power_board, g.build_wakeup_board, g.build_fins_module):
        fn(d)
    apply_orderable(d)
    by = collections.OrderedDict()
    tower_refs = {c.ref for c in d.chips}
    chips = list(d.chips)
    try:                                   # + the dev board's own (dev-only) parts
        import generate_devboard as D
        dd = D.build_design()[0]
        apply_orderable(dd)
        chips += [c for c in dd.chips if c.ref not in tower_refs]
    except Exception as e:                 # never block the review on it
        print(f"  (footprint review: dev board not included: {e!r})")
    for c in chips:
        fp = c.footprint
        if fp is None:
            continue
        e = by.setdefault(fp.name, dict(fp=fp, refs=[], mpns=set(), boards=set()))
        e["refs"].append(c.ref); e["mpns"].add(str(c.manf_pn or "")); e["boards"].add(str(c.board_tag))

    def kind(fp) -> tuple[int, str, list[str]]:
        src = (fp.source or "").strip()
        why = []
        rot = tuple(getattr(fp, "model_rotate_deg", None) or ())
        if any(abs(r) > 1e-9 for r in rot):
            why.append(f"3D model rotated {rot} by us — check pin 1 in the 3D viewer")
        if not fp.model_3d_path:
            why.append("no 3D model")
        if src.lower() in _VENDOR:
            norm = lambda x: re.sub(r"[^A-Z0-9]", "", x.upper())
            mp = str(fp.model_3d_path or "")
            src_dir = norm(pathlib.Path(mp).parent.name) if mp else ""
            same = lambda m: m and src_dir and (norm(m).startswith(src_dir) or src_dir.startswith(norm(m)))
            if src_dir and not any(same(m) for m in by[fp.name]["mpns"]):
                why.append(f"vendor land/model taken from a sibling part ({pathlib.Path(mp).parent.name}) "
                           "— confirm the package is identical")
            # a land NAMED after a different part (IPC-7351 names like QFN../SON.. are generic)
            ipc = re.match(r"(BGA|QFN|SON|SOT|SOP|SOIC|LGA|DFN|PG-|INDPM|Ceramic|DSC|SIT|SAMESKY|OSC_|WE-)",
                           fp.name, re.I)
            fn_ = norm(fp.name)
            if not ipc and not any(m and (fn_[:6] == norm(m)[:6]) for m in by[fp.name]["mpns"]):
                why.append(f"land named after another part ({fp.name}) — confirm it is the same package")
            return (1 if any("rotated" in w or "sibling" in w or "named after" in w for w in why) else 3,
                    f"vendor ({src})", why)
        if src.startswith("kicad") or str(fp.name).startswith(("Resistor_SMD:", "Capacitor_SMD:", "Inductor_SMD:")):
            return 4, "KiCad stock", why
        return 0, f"SELF-DRAWN ({src or 'unknown'})", why

    rows = []
    for name, e in by.items():
        pri, k, why = kind(e["fp"])
        rows.append((pri, name, k, e, why))
    rows.sort(key=lambda r: (r[0], r[1].lower()))
    label = {0: "CHECK — self-drawn", 1: "CHECK — vendor land modified by us",
             3: "vendor, unchanged", 4: "KiCad stock (standard chip passives)"}
    out = ["# Footprint review\n", stamp_line,
           "Every footprint in the maximalist tower, by provenance. **Self-drawn** lands were "
           "made from datasheet drawings (or project scripts) and have never been built — check "
           "pad sizes, pitch, pin 1 and the exposed pad against the datasheet before fab. "
           "**Modified vendor** lands are SamacSys/SnapMagic files we changed (land borrowed "
           "from a sibling part, 3D model rotated, pins listed from the datasheet). "
           "Positions/rotations are not part of this list.\n"]
    cur = None
    for pri, name, k, e, why in rows:
        if pri != cur:
            cur = pri
            n = sum(1 for r in rows if r[0] == pri)
            out.append(f"\n## {label[pri]} ({n})\n\n| Footprint | Part (MPN) | Refs | Board(s) | Source | Notes |\n|---|---|---|---|---|---|")
        fp = e["fp"]
        refs = ", ".join(e["refs"][:6]) + (f" +{len(e['refs']) - 6}" if len(e["refs"]) > 6 else "")
        note = " ".join(str(fp.note or "").split())
        if len(note) > 260:
            note = note[:257] + "…"
        notes = "; ".join(why + ([note] if note else [])).replace("|", "/")
        out.append(f"| `{name}` | {', '.join(sorted(m for m in e['mpns'] if m))[:60]} | {refs} | "
                   f"{', '.join(sorted(e['boards']))} | {k} | {notes} |")
    return "\n".join(out) + "\n"


def main() -> int:
    sys.path[:0] = [str(REPO), str(REPO / "application" / "src")]
    ap = argparse.ArgumentParser(description="Export dist/'s stackup into Unrouted/<date>/.")
    ap.add_argument("--date", default=dt.date.today().strftime("%Y%m%d"),
                    help="export folder date, YYYYMMDD (default: today)")
    ap.add_argument("--force", action="store_true",
                    help="discard uncommitted changes under Unrouted/")
    a = ap.parse_args()
    m = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", a.date)
    if not m:
        sys.exit("export: --date must be YYYYMMDD")
    stamp, iso = "".join(m.groups()), "-".join(m.groups())
    dt.date.fromisoformat(iso)                      # a real date
    rel = OUT.relative_to(REPO).as_posix()

    # Inputs: the full stackup project + the STEPs of a STEP-enabled run (the
    # generator deletes the stackup STEPs at the start of every run).
    need = [DIST / f"stackup.{x}" for x in ("kicad_pro", "kicad_sch", "kicad_pcb")]
    need += [DIST / f for f in (*LIB_FILES, *LIB_DIRS, "maximalist", "stackup_components.step")]
    missing = [p.name for p in need if not p.exists()]
    if missing:
        sys.exit(f"export: not in dist/: {', '.join(missing)}; run generate_stackup.py "
                 "with SMASH_STEP_EXPORT=1 first")
    locks = sorted(p.relative_to(REPO).as_posix() for p in OUT.rglob("~*.lck")
                   if ".history" not in p.parts) if OUT.exists() else []
    if locks:
        sys.exit(f"export: KiCad has the export open ({', '.join(locks)}); close it first")
    dirty = git("status", "--porcelain", "--", rel).rstrip()
    if dirty and not a.force:
        sys.exit(f"export: {rel}/ has uncommitted changes; commit them or pass --force:\n{dirty}")

    # Clear Unrouted/: tracked files through git (recoverable from history),
    # then whatever is left on disk (KiCad .history/, .DS_Store, ...).
    git("rm", "-r", "-q", "-f", "--ignore-unmatch", "--", rel)
    n_left = len(files(OUT))
    if OUT.exists():
        shutil.rmtree(OUT, onerror=_rm_readonly)
    dst = OUT / stamp
    dst.mkdir(parents=True)

    # Libraries; 3dmodels/ and datasheets/ flattened to <part>.<ext> with the
    # symbol library's and footprints' links following.
    warn = []
    for f in LIB_FILES:
        shutil.copy2(DIST / f, dst / f)
    shutil.copytree(DIST / "footprints", dst / "footprints", ignore=JUNK)
    moves: dict[str, str] = {}
    for d in FLAT_DIRS:
        moves.update(flatten(DIST / d, dst / d, d, warn))
    for p in (dst / "stackup.kicad_sym", *(dst / "footprints").rglob("*.kicad_mod")):
        text = read(p)
        new = relink(text, moves)
        if new != text:
            write(p, new)

    # The KiCad project, stackup.* -> Smash.*, linked to the flattened files.
    pro, _ = swap(read(DIST / "stackup.kicad_pro"), '"stackup.kicad_pro"',
                  f'"{PROJECT}.kicad_pro"', "kicad_pro")
    sch, n_sym = swap(read(DIST / "stackup.kicad_sch"), '(project "stackup"',
                      f'(project "{PROJECT}"', "kicad_sch symbol instances")
    sch = re.sub(r'\(title_block \(title "[^"]*"\)( \(date "[^"]*"\))?',
                 f'(title_block (title "{PROJECT}") (date "{iso}")', sch, count=1)
    pcb, _ = swap(read(DIST / "stackup.kicad_pcb"), '"stackup.kicad_sch"',
                  f'"{PROJECT}.kicad_sch"', "kicad_pcb sheet files")
    write(dst / f"{PROJECT}.kicad_pro", pro)
    write(dst / f"{PROJECT}.kicad_sch", relink(sch, moves))
    write(dst / f"{PROJECT}.kicad_pcb", relink(pcb, moves))

    # Every generated STEP (component models are 3dmodels/, not copied twice).
    # dist/maximalist/<part>/: boards, sleeve, mould, battery holder keep their
    # folder; each gap's hardware becomes rings/<a>-<b>_<material>.
    step = dst / "step"
    step.mkdir()
    # stackup.step / _no_potting / waveguide stubs are opt-in (SMASH_FEA_STEP=1):
    # copied when present; the per-config component stackups always.
    for f in ROOT_STEPS:
        if (DIST / f).exists():
            shutil.copy2(DIST / f, step / f)
        elif f == "stackup_components.step":
            warn.append(f"no dist/{f}: not generated by the last run (see its log)")
    for q in sorted(DIST.glob("stackup_*_components.step")):
        shutil.copy2(q, step / q.name)
    parts = sorted(p for p in MAXI.iterdir() if p.is_dir())
    boards = {p.name for p in parts if not p.name.startswith("spacer_")}
    for part in parts:
        steps = sorted(q for q in part.iterdir()
                       if q.is_file() and q.suffix.lower() in (".step", ".stp"))
        cams = sorted(part.glob("*_cam.md"))
        if not steps:
            continue
        if not part.name.startswith("spacer_"):
            (step / part.name).mkdir()
            for q in steps + cams:
                shutil.copy2(q, step / part.name / q.name)
            continue
        if not cams:
            warn.append(f"{part.name}: no _cam.md, material unknown")
        kind, mat = kind_material(read(cams[0]) if cams else "")
        stem = gap_label(part.name, boards) + ("" if kind in ("ring", "") else f"_{kind}") + f"_{mat}"
        (step / "rings").mkdir(exist_ok=True)
        for q in steps:
            name = stem if len(steps) == 1 else f"{stem}_{q.stem}"
            shutil.copy2(q, step / "rings" / f"{name}{q.suffix}")
        if cams:
            shutil.copy2(cams[0], step / "rings" / f"{stem}_cam.md")

    # (2026-11-23, user) the dev board travels with the tower.
    export_devboard(dst, warn)

    # (2026-11-23, user: Altium's KiCad import dropped every 3D model) footprint
    # model links become PLAIN RELATIVE paths ("3dmodels/<part>.step", resolved
    # from each project's folder — KiCad accepts that too) instead of
    # ${KIPRJMOD}/3dmodels/…, which Altium apparently does not expand.
    # Datasheet links keep ${KIPRJMOD} (humans click those, in KiCad).
    for root in (dst, dst / "dev_board"):
        for p in [*root.glob("*.kicad_pcb"), *(root / "footprints").rglob("*.kicad_mod")]:
            text = read(p)
            new = text.replace('(model "${KIPRJMOD}/', '(model "')
            if new != text:
                write(p, new)

    # (2026-11-23, user) Layout-EE notes + the footprint review list.
    head = git("rev-parse", "--short", "HEAD").strip()
    dirty_src = bool(git("status", "--porcelain", "--", "generate_stackup.py", "application",
                         check=False).strip())
    stamp_line = (f"Export {iso} from commit {head}{' + uncommitted changes' if dirty_src else ''} "
                  f"(generate_stackup.py, maximalist).\n\n")
    if NOTES.exists():
        write(dst / "LAYOUT_EE_NOTES.md", "# Layout EE notes\n\n" + stamp_line
              + read(NOTES).split("\n", 1)[1].lstrip("\n"))
    else:
        warn.append(f"no {NOTES.name}: layout notes not exported")
    write(dst / "3D_MODEL_MAP.csv", model_map(dst))
    # (2026-11-23, user) Altium drops KiCad 3D models: script + per-project map
    for root in (dst, dst / "dev_board"):
        if (root / "footprints").exists():
            text, n = altium_model_map(root)
            write(root / "3D_MODEL_MAP_altium.txt", text.replace("\n", "\r\n"))
            shutil.copy2(ALTIUM_SCRIPT, root / ALTIUM_SCRIPT.name)
    try:
        write(dst / "FOOTPRINT_REVIEW.md", footprint_review(stamp_line))
    except Exception as e:                       # never block the export on it
        warn.append(f"footprint review not written: {e!r}")

    # Checks: ${KIPRJMOD} paths resolve inside the export, nothing exported is
    # git-ignored, no file over GitHub's limit.
    written = sorted(files(dst))
    srcs = [dst / f"{PROJECT}.kicad_pcb", dst / f"{PROJECT}.kicad_sch", dst / "stackup.kicad_sym",
            dst / "sym-lib-table", dst / "fp-lib-table", *(dst / "footprints").rglob("*.kicad_mod")]
    broken = sorted({r for s in srcs for r in KIPRJ.findall(read(s))
                     if not (dst / r).exists()})
    if broken:
        warn.append(f"{len(broken)} ${{KIPRJMOD}} path(s) not found (not in dist/ either): "
                    + ", ".join(broken))
    relw = [p.relative_to(REPO).as_posix() for p in written]
    ignored = [p for p in git("check-ignore", "-z", "--stdin", stdin="\0".join(relw),
                              check=False).split("\0") if p]
    if ignored:
        warn.append(f"{len(ignored)} exported file(s) are git-ignored and won't be checked in: "
                    + ", ".join(ignored[:10]))
    for i, p in enumerate(list(written)):
        size = p.stat().st_size / 1e6
        if size > GITHUB_MAX_MB:
            # (2026-11-23) no Git LFS here: zip it (STEP text shrinks ~7×,
            # 102 MB stackup_components.step → 14 MB) instead of dropping it
            import zipfile
            z = p.with_name(p.name + ".zip")
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                zf.write(p, arcname=p.name)
            p.unlink()
            written[i] = p = z
            zsize = p.stat().st_size / 1e6
            print(f"  zipped {p.relative_to(REPO)} ({size:.0f} → {zsize:.0f} MB, GitHub limit "
                  f"{GITHUB_MAX_MB} MB)")
            if zsize > GITHUB_MAX_MB:
                warn.append(f"{p.relative_to(REPO)} is still {zsize:.0f} MB zipped: GitHub "
                            f"refuses files over {GITHUB_MAX_MB} MB (use Git LFS or leave it out)")
        elif size > WARN_MB:
            warn.append(f"{p.relative_to(REPO)} is {size:.0f} MB (GitHub warns above {WARN_MB} MB)")

    # (2026-11-23, user) Altium import test kit, next to the dated folder.
    from smash.export import altium_import_test as AIT
    model = next((p for p in (dst / "dev_board" / "3dmodels" / "Resistor_SMD.3dshapes.step",
                              dst / "3dmodels" / "Resistor_SMD.3dshapes.step") if p.exists()), None)
    if model:
        AIT.write(OUT / "altium_import_test", model)
    else:
        warn.append("altium_import_test not written: no resistor STEP in the export")

    # (2026-11-23, user) One zip of the whole snapshot next to the folder —
    # easier to hand to the layout EE.
    import zipfile
    zpath = OUT / f"{stamp}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in sorted(files(dst)):
            # fixed timestamp (the export date) → identical exports give a
            # byte-identical zip, so git stores no new 90 MB copy
            zi = zipfile.ZipInfo(p.relative_to(OUT).as_posix(), date_time=(int(iso[:4]), int(iso[5:7]), int(iso[8:10]), 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, p.read_bytes(), compresslevel=9)
    zmb = zpath.stat().st_size / 1e6
    if zmb > GITHUB_MAX_MB:
        warn.append(f"{zpath.relative_to(REPO)} is {zmb:.0f} MB: GitHub refuses files over "
                    f"{GITHUB_MAX_MB} MB (split it or leave it out)")
    elif zmb > WARN_MB:
        warn.append(f"{zpath.relative_to(REPO)} is {zmb:.0f} MB (GitHub warns above {WARN_MB} MB)")
    git("add", "-A", "--", rel)

    groups: dict[str, list[pathlib.Path]] = {}
    for p in written:
        top = p.relative_to(dst).parts
        groups.setdefault(top[0] + "/" if len(top) > 1 else "project + libraries", []).append(p)
    print(f"Exported dist/ -> {rel}/{stamp}/ (project {PROJECT}, {n_sym} symbol instances "
          "renamed); staged, commit when ready")
    for g in ("project + libraries", "footprints/", "3dmodels/", "datasheets/", "step/"):
        ps = groups.get(g, [])
        print(f"  {g:<20} {len(ps):4d} files {sum(p.stat().st_size for p in ps) / 1e6:8.1f} MB")
    print(f"  {'total':<20} {len(written):4d} files "
          f"{sum(p.stat().st_size for p in written) / 1e6:8.1f} MB")
    print(f"  + {zpath.relative_to(REPO)} ({zmb:.0f} MB), LAYOUT_EE_NOTES.md, FOOTPRINT_REVIEW.md")
    if n_left:
        print(f"  deleted {n_left} untracked local file(s) that were left in {rel}/ "
              "(KiCad .history/, .DS_Store, ...)")
    for w in warn:
        print(f"  WARN {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
