"""Per-board PCB fab notes — manufacturing callouts that don't fit in
the gerber/IPC-2581 deliverable.

For each rigid tile, emits a single `<board>_fab.md` covering:

  * stackup layer count + total thickness (for tiles that override the
    project-default 14L);
  * solder paste alloy (name + mechanical/thermal constants — the
    bend-sim's joint-shear and the thermal-cycling fatigue depend on
    these, so we surface them next to the fab callout that selects them);
  * Cu coin specs per NCAB Copper Coin Design Guidelines 1.0 (the
    structural coins on the bend-sim bottleneck tiles).

This mirrors `spacer_step.write_spacer_cam_notes()` for the milled Al
spacers: the gerber + STEP carries geometry; this file carries the
material/process choices the gerber can't express.
"""
from __future__ import annotations

import pathlib

from smash.state import Board
from smash.state.fab.default import default_fab_profile
from smash.state.geometry3d import board_solder


def _foil_lines(fab) -> list[str]:
    """Markdown lines describing the copper foils + ductility — the foil
    property that sets bend / crack-bridging survival under shock."""
    foils = getattr(fab, "foils", None) or []
    if not foils:
        return ["- (no foils in FabProfile)"]
    out = []
    for f in foils:
        ftype = f.foil_type or "ED"
        klass = ("ductile" if getattr(f, "is_ductile", False)
                 else "low-profile RF" if getattr(f, "is_low_profile", False)
                 else "standard")
        el = (f"{f.elongation_pct:.0f}% elongation"
              if f.elongation_pct else "elongation n/a")
        plated = (f", outer→{f.plated_thickness_um:.1f} µm plated"
                  if f.plated_thickness_um else "")
        proc = (f", inner→{f.min_processed_thickness_um:.1f} µm min after "
                f"processing" if getattr(f, "min_processed_thickness_um", None)
                else "")
        out.append(f"- **{f.weight_oz:g} oz {ftype}** ({klass}) — base "
                   f"{f.thickness_um:.1f} µm, {el}{plated}{proc}")
    out.append("- ductility: standard ED ≈ 10 % elongation (thin/cold ED → "
               "~3 % conservative floor); rolled-annealed **RA ≈ 20 %**. "
               "Specify RA for bend-/shock-strain-critical routing — RTF/VLP/"
               "HVLP are low-*roughness* RF foils, still ED ductility.")
    return [ln for ln in out if ln]


def _solder_lines(board: Board, fab) -> list[str]:
    """Markdown lines describing the board's solder paste selection."""
    s = board_solder(board, fab=fab)
    if s is None:
        return ["- (no solder resolved from FabProfile)"]
    out = [
        f"- **{s.name}**" + (f" — {s.alloy}" if s.alloy else ""),
        f"- liquidus: {s.melting_c} °C" if s.melting_c else "",
        f"- Young's modulus: {s.youngs_modulus_gpa} GPa, "
        f"Poisson's ratio: {s.poisson_ratio}"
        if s.youngs_modulus_gpa and s.poisson_ratio else "",
        f"- shear strength: {s.shear_strength_mpa} MPa "
        f"(bend-sim joint-shear failure threshold)"
        if s.shear_strength_mpa else "",
        f"- CTE: {s.cte_ppm_k} ppm/K" if s.cte_ppm_k else "",
        f"- thermal conductivity: {s.thermal_w_mk} W/mK" if s.thermal_w_mk else "",
    ]
    if s.note:
        out.append(f"- note: {s.note}")
    return [line for line in out if line]


def _coin_lines(board: Board) -> list[str]:
    """Markdown lines describing every CuCoinInsert on the board, in
    NCAB Copper Coin Design Guideline 1.0 symbol order so the fab can
    cross-reference the standard table directly."""
    coins = board.cu_coin_inserts or []
    if not coins:
        return []
    out = ["", "## Cu coin inserts (NCAB Copper Coin Design Guidelines 1.0)", ""]
    for i, c in enumerate(coins, 1):
        cx, cy = c.position_mm
        label = f"coin {i}" + (f" — {c.note}" if c.note else "")
        out.extend([
            f"### {label}",
            "",
            f"- **kind:** {c.kind}",
            f"- **position (board-local):** ({cx:+.2f}, {cy:+.2f}) mm",
            f"- **rotation:** {c.rotation_deg:.0f}° (CCW from board +X)",
            f"- **NCAB X (short, width):** {c.width_mm:.2f} mm",
            f"- **NCAB Y (long, length):** {c.length_mm:.2f} mm",
            f"- **NCAB X1 (ladder short):** {c.ladder_width_mm:.2f} mm",
            f"- **NCAB Y1 (ladder long):** {c.ladder_length_mm:.2f} mm",
            f"- **Q (flange overhang per side):** "
            f"short axis {c.Q_short_mm:.2f} mm, "
            f"long axis {c.Q_long_mm:.2f} mm",
            f"- **NCAB H (total thickness):** {c.thickness_mm:.2f} mm",
            f"- **NCAB H1 (flange thickness):** {c.flange_thickness_mm:.2f} mm",
            f"- **NCAB H2 (shank thickness):** {c.shank_thickness_mm:.2f} mm",
            f"- **NCAB R (corner chamfer radius):** "
            f"{c.corner_chamfer_radius_mm:.2f} mm",
            f"- **z range (from B.Cu = 0):** "
            f"{c.z_bottom_mm:.2f} → {c.z_top_mm:.2f} mm",
            f"- **flange face up:** {c.flange_up}",
            f"- **flange area (with chamfers):** {c.flange_area_mm2:.1f} mm²",
            "",
        ])
        if c.net:
            out.append(f"- electrical net: `{c.net}`")
    return out


def write_pcb_fab_notes(board: Board, output_path: str | pathlib.Path,
                         *, fab=None) -> dict:
    """Write `<output_path>` Markdown fab callout for one rigid PCB tile.

    The tile's gerber/IPC-2581 carries the copper geometry; this file
    carries the material + process choices a fab needs alongside it:
    layer count (when it differs from the project default), solder
    paste, and any embedded Cu coins. Returns a dict with `output_path`
    and a `summary` line for index pages.
    """
    if board.kind != "rigid":
        raise ValueError(
            f"{board.name}: write_pcb_fab_notes is for rigid tiles, "
            f"got kind={board.kind!r}"
        )
    fab = fab or default_fab_profile()
    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    layer_count = (board.copper_layers if board.copper_layers is not None
                   else 14)
    lines = [
        f"# `{board.name}` — PCB fab notes",
        "",
        "Companion to the tile's gerber / IPC-2581 deliverable.",
        "",
        "## Stackup",
        "",
        f"- **{layer_count}-layer** {board.top_substrate.upper()} "
        f"top substrate" if board.top_substrate != "fr4"
        else f"- **{layer_count}-layer** FR4",
        f"- total thickness (catalog): {board.thickness_mm:.3f} mm",
    ]
    if board.al_backing_mm:
        lines.append(f"- {board.al_backing_mm} mm Al thermal-spreader "
                     f"backing bonded under B.Cu")
    lines += [
        "",
        "## Copper foils",
        "",
        *_foil_lines(fab),
        "",
        "## Solder paste",
        "",
        *_solder_lines(board, fab),
    ]
    lines += _coin_lines(board)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    has_coin = bool(board.cu_coin_inserts)
    summary = (f"{layer_count}L"
               + (f" + {len(board.cu_coin_inserts)} Cu coin" if has_coin else ""))
    return {"output_path": str(out), "summary": summary}
