"""3D finite-element analysis pipeline for the snake stack.

Bridges between the smash design (Board / Stackup / CuCoinInsert / chips)
and the CalculiX 2.23 solver via:

  - smash.sim.fea.mesh      — parametric hex meshes per board (no
                               external mesher; numpy arrays directly).
  - smash.sim.fea.materials — element-block material assignment from
                               the FabProfile + Solder + Adhesive
                               catalog the rest of smash already uses.
  - smash.sim.fea.ccx_writer — emit a CalculiX `.inp` deck (nodes,
                               elements, materials, BCs, step header).
  - smash.sim.fea.ccx_runner — subprocess wrapper for `ccx_2.23`.
  - smash.sim.fea.frd_parser — parse the `.frd` output back into
                               numpy arrays the report writer consumes.

Body-force histories passed into `build_deck` drive the static and
transient FEA steps.
"""
from smash.sim.fea.ccx_runner import (
    CCX_BINARY_DEFAULT, find_ccx_binary, run_ccx,
)
from smash.sim.fea.ccx_writer import write_ccx_inp, CCXDeck
from smash.sim.fea.frd_parser import parse_frd, FRDResult
from smash.sim.fea.report import (
    evaluate_chip_verdicts, evaluate_chip_verdicts_transient,
    write_report,
    FEAChipVerdict, FEABoardResult,
)


__all__ = (
    "CCX_BINARY_DEFAULT", "find_ccx_binary", "run_ccx",
    "write_ccx_inp", "CCXDeck",
    "parse_frd", "FRDResult",
    "evaluate_chip_verdicts", "evaluate_chip_verdicts_transient",
    "write_report",
    "FEAChipVerdict", "FEABoardResult",
)
