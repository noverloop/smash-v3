"""Fab outputs — Gerbers + Excellon drill files via kicad-cli.

Drives `kicad-cli pcb export gerbers` / `... export drill` over a tile's
`.kicad_pcb` and bundles the result into ONE `<board>_gerbers.zip` per
tile — the archive a fab actually receives. The copper layer list is
derived from the same fitted stackup the .kicad_pcb writer used
(`kicad_pcb._board_stackup`), so the plotted set always matches the
file's declared layer table (14L default, 20L coined tiles, 12L
nose_cap, …).

Output conventions (kicad-cli 10 defaults, verified):
  - Protel filename extensions (.gtl/.gbl/.g1…/.gts/.gbs/.gto/.gbo/.gm1)
  - Gerber X2 attributes + netlist attributes on
  - A `<board>-job.gbrjob` job file
  - Excellon drill in mm/decimal/absolute, PTH and NPTH separated,
    with Gerber-X2 drill maps

Spacer interposers plot the same way from their own 2-layer
`.kicad_pcb` (outline + NPTH + LGA lands + filled through-vias +
Eco1/Eco2 pocket outlines); their 3D bodies stay cadquery territory.
Flex tiles currently only exist in the stitched panel file, so they
get no per-tile fab set (their artwork is placeholder pending the
antenna EM sim).
"""
from __future__ import annotations

import pathlib
import subprocess
import zipfile

# Non-copper plots every tile needs for fab (+ paste for the stencil).
_FAB_TAIL = ("F.Mask", "B.Mask", "F.SilkS", "B.SilkS",
             "F.Paste", "B.Paste", "Edge.Cuts")

# Everything write_gerbers may drop into the gerber dir — cleared before
# each run so a shrunken layer set can't leave stale plots behind.
_FAB_SUFFIXES = (".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo",
                 ".gtp", ".gbp", ".gm1", ".gbrjob", ".drl", ".gbr")


def fab_layer_list(board) -> list[str]:
    """The plot set for one tile: its fitted copper stack (F.Cu, In*,
    B.Cu — same source as the .kicad_pcb layer table) + the fixed
    mask/silk/paste/outline tail. Spacers (2-layer interposers) also
    plot Eco1/Eco2 — their milled pocket outlines live there (top /
    bottom face; depths in the sibling `_cam.md`)."""
    from smash.export.kicad_pcb import _board_stackup
    layers = ([layer.name for layer in _board_stackup(board)]
              + list(_FAB_TAIL))
    if getattr(board, "is_spacer", False):
        layers += ["Eco1.User", "Eco2.User"]
    return layers


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-8:]
        raise RuntimeError(
            f"kicad-cli failed ({' '.join(cmd[1:4])}): " + " | ".join(tail))


def write_gerbers(pcb_path, board, *, out_dir=None, kicad_cli=None,
                  zip_path=None) -> dict:
    """Plot the full fab set for one tile .kicad_pcb.

    Writes into `<pcb dir>/gerbers/` (or `out_dir`) and zips everything
    into `<pcb dir>/<stem>_gerbers.zip` (or `zip_path`; pass False to
    skip zipping). Returns {"n_files", "n_copper", "zip", "dir"}.
    Raises on kicad-cli failure — callers in the generator wrap this in
    the same keep-resilient pattern as the STEP exports."""
    from smash.export.kicad_step import find_kicad_cli
    pcb_path = pathlib.Path(pcb_path)
    cli = kicad_cli or find_kicad_cli()
    gdir = pathlib.Path(out_dir) if out_dir else pcb_path.parent / "gerbers"
    gdir.mkdir(parents=True, exist_ok=True)
    for old in gdir.iterdir():
        sfx = old.suffix.lower()
        inner = sfx.startswith(".g") and sfx[2:].isdigit()   # .g1 … .g18
        if sfx in _FAB_SUFFIXES or inner:
            old.unlink()

    layers = fab_layer_list(board)
    _run([cli, "pcb", "export", "gerbers",
          "-o", str(gdir) + "/", "-l", ",".join(layers), str(pcb_path)])
    _run([cli, "pcb", "export", "drill",
          "-o", str(gdir) + "/", "--excellon-separate-th",
          "--generate-map", "--map-format", "gerberx2", str(pcb_path)])

    produced = sorted(p for p in gdir.iterdir() if p.is_file())
    n_copper = sum(1 for p in produced
                   if p.suffix in (".gtl", ".gbl")
                   or (p.suffix.startswith(".g") and p.suffix[2:].isdigit()))
    zp = None
    if zip_path is not False:
        zp = (pathlib.Path(zip_path) if zip_path
              else pcb_path.parent / f"{pcb_path.stem}_gerbers.zip")
        if zp.exists():
            zp.unlink()
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for p in produced:
                z.write(p, p.name)
    return {"n_files": len(produced), "n_copper": n_copper,
            "zip": zp, "dir": gdir}
