"""Per-reflow board-to-board stack-assembly KiCad files.

The folded snake is assembled by the fab (Eurocircuits) as a vertical stack:
each element — rigid tile OR spacer — is placed onto the one below with solder
paste + pick-and-place + reflow ("treat the boards and spacers as a chip").
This emits ONE `.kicad_pcb` per reflow step, in build order (aft→nose =
bottom→top):

  step k:  place chain[k] onto chain[k-1]
           base board  = chain[k-1] (its full PCB; its top-face J_* receiving
                         lands already carry F.Paste → the step's stencil)
           placed chip = chain[k] as a board-as-component, pads = the base's
                         receiving lands (so it mates pad-to-pad by
                         construction — fold-mirror-agnostic), nets carried
                         over, plus the element's outline + STEP 3D model.

This is pcbnew-free (S-expression writer) like the rest of the export layer.
`connect(net_name, pin)` is supplied by the caller (same pattern as
`place_lga_lands`) so this module stays decoupled from the generator.
"""
from __future__ import annotations

import math
import pathlib

from smash.export.kicad_pcb import write_kicad_pcb
from smash.layout.placer.flex_sizing import compute_link_widths
from smash.state import Footprint, Pin
from smash.state.topology.placement import Placement


def _land_chip(board, face):
    """The element's LGA land array on `face` (top = J_* receiving lands,
    bottom = P_* mating lands), or None."""
    for pl in board.chip_placements:
        c = pl.item
        if getattr(c, "manf_pn", "") == "LGA_lands" and pl.face == face:
            return c
    return None


def _disc_outline(radius_mm: float, n: int = 48) -> list:
    return [(radius_mm * math.cos(2 * math.pi * i / n),
             radius_mm * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _board_as_component(design, lower, upper, recv, step_dir):
    """A board-as-component chip representing `upper` placed on `lower`.

    Pads are `lower`'s top-face receiving lands (the exact pattern the upper
    solders onto → mates at (0,0) by construction, sidestepping the fold
    mirror). Outline + 3D are the UPPER element's (the board being placed)."""
    pads = list(recv.footprint.pads)
    r = (upper.geometry.outline_radius_mm if upper.geometry else 17.0)
    # Per-board folder layout: <step_dir>/<name>/<name>.step
    step = (pathlib.Path(step_dir) / upper.name / f"{upper.name}.step") if step_dir else None
    fp = Footprint(
        name=f"BOARD_{upper.name}",
        pads=pads,
        body_outline=_disc_outline(r),
        package_class=f"board-as-component (Ø{2*r:.0f} mm {upper.name})",
        source="project (stack assembly)",
        model_3d_path=str(step) if (step and step.exists()) else None,
        note=f"{upper.name} placed as a board-to-board component onto "
             f"{lower.name}'s receiving lands",
    )
    return design.add_chip(
        ref=f"BRD_{upper.name}", board_tag="__assembly__", manf="project",
        manf_pn="board_as_component", name=upper.name, footprint=fp,
        pins=[Pin(num=p.num, name=p.num) for p in pads],
        note="board-to-board element placed in this reflow step")


# The aft battery compartment closes with a LOW-TEMP solder step: placing
# activation_interface onto the battery column joins the cells' + tabs to it,
# and a SAC305 reflow (~245 °C) would cook the Tadiran TLM-1520 Li-primary
# cells (qualified only to a 150 °C oven). That joint reflows in In52/Sn48
# (eutectic In-Sn, 118 °C) as the LAST step before the battery compartment is
# potted. Every other board-to-board step is the default SAC305.
_DEFAULT_SOLDER = "SAC305"
_LOWTEMP_SOLDER = "In52Sn48"
_LOWTEMP_UPPER = "activation_interface"


def _solder_for_step(upper_name: str) -> tuple[str, str]:
    """(alloy, note) for the reflow step that places `upper_name`."""
    if upper_name == _LOWTEMP_UPPER:
        return (_LOWTEMP_SOLDER,
                "LOW-TEMP In52/Sn48 (118 °C): closes the cells' + tabs onto "
                "activation_interface — the LAST step before the battery "
                "compartment is potted. SAC305's ~245 °C reflow would exceed "
                "the TLM-1520 cells' 150 °C limit. The P_PIEZO PZT disc "
                "(Steminc SMD10T04R111, aft_end top — nose-facing, so setback "
                "loads the ceramic in compression) is also attached in this "
                "step: SAC temperatures risk depoling the ceramic; it pots "
                "with the cells.")
    return (_DEFAULT_SOLDER, "")


def _write_assembly_manifest(out_dir, steps) -> None:
    """Human-readable assembly-instructions sidecar (`assembly_steps.md`):
    the ordered reflow sequence + the solder alloy per step, calling out the
    low-temp In-Sn battery-close step."""
    lines = [
        "# Stack assembly — reflow sequence (aft → nose)",
        "",
        "Each element (rigid tile or spacer) is placed onto the one below "
        "with solder paste + pick-and-place + reflow — \"treat the boards and "
        "spacers as a chip\". Default alloy **SAC305** (~245 °C peak); the "
        "battery-close step uses low-temp **In52/Sn48** (118 °C). Cells are "
        "NOT in the reflow oven for any SAC305 step — they're attached for the "
        "In-Sn step only.",
        "",
        "| # | place | onto | pads | solder | note |",
        "|---|-------|------|-----:|--------|------|",
    ]
    for idx, upper, lower, npads, _has3d, solder, note in steps:
        emph = f"**{solder}**" if solder != _DEFAULT_SOLDER else solder
        lines.append(f"| {idx:02d} | {upper} | {lower} | {npads} | {emph} | {note} |")
    lines.append("")
    pathlib.Path(out_dir, "assembly_steps.md").write_text("\n".join(lines))


def build_stack_assembly_files(design, panel, boards, out_dir, *, connect,
                               link_widths=None, step_dir=None) -> list:
    """Emit one `.kicad_pcb` per reflow step into `out_dir`, plus an
    `assembly_steps.md` manifest (the assembly instructions).

    `connect(net_name, pin)` wires the placed component's pads to the
    receiving lands' nets (same pattern as `place_lga_lands`). `step_dir`, if
    given, is where per-element `<name>.step` 3D models live. Returns a list
    of ``(index, upper, lower, n_pads, has_3d, solder)`` for the steps written.
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if link_widths is None:
        link_widths, _ = compute_link_widths(design, panel)
    pin_net = {(ref, pin): n.name
               for n in design.nets for ref, pin in n.pins}
    chain = [c for c in (panel.snake_chain or []) if c in boards]

    results = []
    step_notes = []
    n = 0
    for k in range(1, len(chain)):
        lower = boards[chain[k - 1]]
        upper = boards[chain[k]]
        recv = _land_chip(lower, "top")
        if recv is None:
            continue
        # Idempotent: a prior run on this design already built + netted the
        # board-as-component, so reuse it rather than re-adding (duplicate
        # ref) or re-connecting (duplicate net pins).
        ref = f"BRD_{upper.name}"
        comp = next((c for c in design.chips if c.ref == ref), None)
        if comp is None:
            comp = _board_as_component(design, lower, upper, recv, step_dir)
            for p in comp.footprint.pads:
                net = pin_net.get((recv.ref, p.num))
                if net:
                    connect(net, comp.pin(p.num))
        pl = Placement(position_mm=(0.0, 0.0), rotation_deg=0.0,
                       item=comp, face="top", locked=True)
        lower.chip_placements.append(pl)
        n += 1
        out = out_dir / f"{n:02d}_place_{upper.name}_on_{lower.name}.kicad_pcb"
        write_kicad_pcb(design, lower, out, panel=panel,
                        link_widths_mm=link_widths)
        lower.chip_placements.remove(pl)
        solder, note = _solder_for_step(upper.name)
        results.append((n, upper.name, lower.name,
                        len(comp.footprint.pads),
                        bool(comp.footprint.model_3d_path), solder))
        step_notes.append((n, upper.name, lower.name,
                           len(comp.footprint.pads),
                           bool(comp.footprint.model_3d_path), solder, note))
    _write_assembly_manifest(out_dir, step_notes)
    return results
