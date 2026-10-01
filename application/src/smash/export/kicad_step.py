"""Export chip-bearing PCBs to STEP via KiCad's `kicad-cli`.

The rigid board tiles carry real components, so the most faithful 3D
body comes from KiCad itself: `kicad-cli pcb export step` fuses the
board outline (from Edge.Cuts, including our through-cavity cutouts)
with each component's 3D model. This module is a thin, testable wrapper
around that command.

Spacers are the exception — KiCad would render them as flat 1.6 mm
board regions, but they are 4 mm FR4 discs with milled cavity pockets.
Those are generated separately in `smash.export.spacer_step` with
cadquery. So the full 3D set is:

    chip-bearing panels/configs  →  write_kicad_step  (this module)
    spacers                      →  write_all_spacer_steps (cadquery)

`kicad-cli` is located via (in order): an explicit `kicad_cli=` arg, the
`KICAD_CLI` env var, `kicad-cli` on PATH, then the macOS app bundle at
`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`. If none is
found, `write_kicad_step` raises `KiCadCliNotFound` so callers can skip
gracefully (the library stays runnable on machines without KiCad).
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess


# Fallback locations checked after PATH. macOS ships kicad-cli inside the
# app bundle, which is not added to PATH by the installer.
_BUNDLE_PATHS = (
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
)


class KiCadCliNotFound(FileNotFoundError):
    """Raised when no `kicad-cli` executable can be located."""


def find_kicad_cli(explicit: str | None = None) -> str:
    """Return a usable `kicad-cli` path or raise `KiCadCliNotFound`.

    Resolution order: `explicit` arg → `$KICAD_CLI` → PATH → known
    macOS app-bundle locations.
    """
    for candidate in (explicit, os.environ.get("KICAD_CLI")):
        if candidate and pathlib.Path(candidate).is_file():
            return candidate
    on_path = shutil.which("kicad-cli")
    if on_path:
        return on_path
    for candidate in _BUNDLE_PATHS:
        if pathlib.Path(candidate).is_file():
            return candidate
    raise KiCadCliNotFound(
        "kicad-cli not found. Set $KICAD_CLI, add it to PATH, or install "
        "KiCad (macOS: /Applications/KiCad/KiCad.app)."
    )


def build_step_argv(
    kicad_cli: str,
    pcb_path: str | pathlib.Path,
    output_path: str | pathlib.Path,
    *,
    no_dnp: bool = True,
    subst_models: bool = True,
    board_only: bool = False,
    no_unspecified: bool = False,
    force: bool = True,
    extra_args: tuple[str, ...] = (),
) -> list[str]:
    """Construct the `kicad-cli pcb export step` argument vector.

    Split out from `write_kicad_step` so it can be unit-tested without a
    `kicad-cli` install. Defaults mirror what the twin wants: substitute
    our repo-local STEP models for the VRML refs (`--subst-models`) and
    drop DNP parts (`--no-dnp`, e.g. the WiFi front-end when telemetry is
    absent).
    """
    argv = [kicad_cli, "pcb", "export", "step"]
    if force:
        argv.append("--force")
    if subst_models:
        argv.append("--subst-models")
    if no_dnp:
        argv.append("--no-dnp")
    if no_unspecified:
        argv.append("--no-unspecified")
    if board_only:
        argv.append("--board-only")
    argv.extend(extra_args)
    argv.extend(["-o", str(output_path), str(pcb_path)])
    return argv


def write_kicad_step(
    pcb_path: str | pathlib.Path,
    output_path: str | pathlib.Path | None = None,
    *,
    kicad_cli: str | None = None,
    no_dnp: bool = True,
    subst_models: bool = True,
    board_only: bool = False,
    no_unspecified: bool = False,
    timeout_s: float = 300.0,
    extra_args: tuple[str, ...] = (),
) -> dict:
    """Export one `.kicad_pcb` to STEP. Returns a summary dict.

    `output_path` defaults to the input path with a `.step` suffix.
    Raises `KiCadCliNotFound` if no CLI is available, `FileNotFoundError`
    if `pcb_path` doesn't exist, and `RuntimeError` if the export runs
    but produces no file.

    The summary dict carries: output_path, returncode, size_bytes, and
    `warnings` (kicad-cli's stderr lines, deduped) — KiCad emits a benign
    "Board outline is malformed" warning for our multi-tile panels, which
    does not prevent a valid body from being written.
    """
    pcb = pathlib.Path(pcb_path)
    if not pcb.is_file():
        raise FileNotFoundError(f"no such .kicad_pcb: {pcb}")
    cli = find_kicad_cli(kicad_cli)

    out = pathlib.Path(output_path) if output_path else pcb.with_suffix(".step")
    out.parent.mkdir(parents=True, exist_ok=True)

    argv = build_step_argv(
        cli, pcb, out,
        no_dnp=no_dnp, subst_models=subst_models, board_only=board_only,
        no_unspecified=no_unspecified, extra_args=extra_args,
    )
    proc = subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout_s,
    )
    if not out.is_file():
        raise RuntimeError(
            f"kicad-cli exited {proc.returncode} but wrote no STEP for "
            f"{pcb.name}.\n  cmd: {' '.join(argv)}\n"
            f"  stderr: {proc.stderr[-600:]}"
        )

    warnings = sorted({
        ln.strip() for ln in proc.stderr.splitlines()
        if "warning" in ln.lower()
    })
    return {
        "output_path": str(out),
        "returncode":  proc.returncode,
        "size_bytes":  out.stat().st_size,
        "warnings":    warnings,
    }


def write_all_board_steps(
    pcb_paths,
    output_dir: str | pathlib.Path | None = None,
    *,
    kicad_cli: str | None = None,
    **kwargs,
) -> list[dict]:
    """Export every `.kicad_pcb` in `pcb_paths` to STEP.

    With `output_dir`, each STEP lands at `<output_dir>/<stem>.step`;
    otherwise it sits beside its source. Resolves `kicad-cli` once up
    front so a missing install fails fast (rather than per-file).
    """
    cli = find_kicad_cli(kicad_cli)
    out_dir = pathlib.Path(output_dir) if output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for p in pcb_paths:
        p = pathlib.Path(p)
        dest = (out_dir / f"{p.stem}.step") if out_dir else None
        results.append(write_kicad_step(p, dest, kicad_cli=cli, **kwargs))
    return results
