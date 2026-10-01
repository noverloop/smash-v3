"""Output-format writers for a Design.

Every writer takes a `Design` instance and a path, and returns a small
summary dict (`{n_parts, n_nets, ...}`) for the caller to log. Writers
are pure functions — no side effects beyond writing the named file.

Format coverage:
  - `write_bom`               — CSV BOM with DNP/ECM accounting
  - `write_flat_netlist`      — three-column NET<tab>REF<tab>PIN
  - `write_edif`              — EDIF 200 (Xpedition / OrCAD Capture)
  - `write_pads_netlist`      — PADS Layout ASCII (.asc)
  - `write_protel_netlist`    — Protel / Tango / Altium (.NET)
  - `write_allegro_netlist`   — Cadence Allegro Telesis (.txt) +
                                 optional KiCad→Allegro fp mapping
  - `write_footprint_inventory` — SamacSys download-checklist CSV with
                                 persisted manual columns
  - `write_specctra_dsn`      — Specctra DSN for FreeRouting / DeepPCB

Companion validator lives in `smash.validators.specctra`.
"""

from smash.export.bom import write_bom
from smash.export.flat import write_flat_netlist
from smash.export.edif import write_edif
from smash.export.pads import write_pads_netlist
from smash.export.protel import write_protel_netlist
from smash.export.allegro import write_allegro_netlist
from smash.export.fp_inventory import (
    write_footprint_inventory,
    load_allegro_fp_map,
)
from smash.export.specctra import write_specctra_dsn
from smash.export.kicad_pcb import (
    write_kicad_pcb, write_kicad_panel, write_blank_drawing_sheet,
)
from smash.export.spacer_step import (
    write_spacer_step,
    write_all_spacer_steps,
)
from smash.export.stackup_step import (
    write_stackup_step,
    write_stackup_components_step,
    write_consolidated_stackup_stl,
    write_housing_stl,
)
from smash.export.kicad_step import (
    write_kicad_step,
    write_all_board_steps,
    find_kicad_cli,
    KiCadCliNotFound,
)
from smash.export.gerbers import write_gerbers, fab_layer_list

__all__ = [
    "write_bom",
    "write_flat_netlist",
    "write_edif",
    "write_pads_netlist",
    "write_protel_netlist",
    "write_allegro_netlist",
    "write_footprint_inventory",
    "load_allegro_fp_map",
    "write_specctra_dsn",
    "write_kicad_pcb",
    "write_kicad_panel",
    "write_blank_drawing_sheet",
    "write_spacer_step",
    "write_all_spacer_steps",
    "write_stackup_step",
    "write_stackup_components_step",
    "write_consolidated_stackup_stl",
    "write_housing_stl",
    "write_kicad_step",
    "write_all_board_steps",
    "find_kicad_cli",
    "KiCadCliNotFound",
    "write_gerbers",
    "fab_layer_list",
]
