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


def main() -> int:
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
    if n_left:
        print(f"  deleted {n_left} untracked local file(s) that were left in {rel}/ "
              "(KiCad .history/, .DS_Store, ...)")
    for w in warn:
        print(f"  WARN {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
