"""Steady-state thermal sim — RC network solver for the snake stack.

  topology.build_graph(chain, boards, fab=…) → ThermalGraph
  solve.solve(graph) → {node_name: T_°C}
  evaluate.evaluate_stack(chain, boards, fab=…) → StackThermalResult
  report.write_report(result, out_dir) → JSON sidecar + report.md
  housing.compute_budget(…) → HousingBudget (flight-regime check)

Material constants source from `FabProfile` (encapsulant + underfill κ,
metal_options for Al backing κ, laminate FR-4 κ for non-Al spacers).
Spacer-floor material keyed off `Board.spacer_material` so the bend-
sim's Al spacers get their 550× κ boost on the tile-to-tile axial path.
Chip dissipation + Rth_jc + T_jmax pulled directly off `Chip` objects
(populated by the smash parts catalog).
"""
from smash.sim.thermal.topology import (
    ThermalGraph, Node, Edge, build_graph,
    POTTING_GAP_MM_DEFAULT, T_AMBIENT_C_DEFAULT,
    TILE_TO_HOUSING_K_PER_W_DEFAULT,
)
from smash.sim.thermal.solve import solve
from smash.sim.thermal.evaluate import (
    DieVerdict, TileVerdict, StackThermalResult, evaluate_stack,
)
from smash.sim.thermal.report import write_report
from smash.sim.thermal.housing import (
    HousingBudget, compute_budget,
    standard_atmosphere, speed_of_sound, recovery_temperature,
)
from smash.sim.thermal.specs import (
    ThermalSpec, load_thermal_specs, overlay_chip_thermals,
)


__all__ = (
    "ThermalGraph", "Node", "Edge",
    "build_graph", "solve",
    "DieVerdict", "TileVerdict", "StackThermalResult",
    "evaluate_stack", "write_report",
    "HousingBudget", "compute_budget",
    "standard_atmosphere", "speed_of_sound", "recovery_temperature",
    "ThermalSpec", "load_thermal_specs", "overlay_chip_thermals",
    "POTTING_GAP_MM_DEFAULT", "T_AMBIENT_C_DEFAULT",
    "TILE_TO_HOUSING_K_PER_W_DEFAULT",
)
