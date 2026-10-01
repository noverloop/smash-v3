"""Top-level orchestrator for steady-state thermal evaluation of a
snake stack.

Builds the RC graph from a chain of `Board` objects + their populated
`chip_placements`, solves for node temperatures, classifies each die
against its `tj_max_c`, and returns a structured `StackThermalResult`.
"""
from __future__ import annotations

import dataclasses

from smash.sim.thermal.topology import (
    build_graph, POTTING_GAP_MM_DEFAULT, T_AMBIENT_C_DEFAULT,
)
from smash.sim.thermal.solve import solve


@dataclasses.dataclass
class DieVerdict:
    ref: str
    tile: str
    p_w: float
    t_die_c: float
    t_body_c: float
    delta_t_k: float                 # T_die - T_body
    tj_max_c: float | None
    headroom_k: float | None         # tj_max - T_die, None if no spec
    verdict: str                     # "pass" | "warn" | "fail" | "unknown"


@dataclasses.dataclass
class TileVerdict:
    tile: str
    kind: str                        # "rigid" | "spacer"
    t_body_c: float


@dataclasses.dataclass
class StackThermalResult:
    chain: list                       # tile names, in fold order
    t_ambient_c: float
    use_p_max: bool
    p_total_w: float
    temps: dict                       # node_name → T °C
    dies: list                        # list[DieVerdict]
    tiles: list                       # list[TileVerdict]
    worst_die: DieVerdict | None      # die with the tightest headroom (or hottest if none has T_jmax)


# Same pass/warn/fail thresholds as the legacy thermal_sim/solve.py's
# `_print_report` — chip headroom ≥ 10 K is "comfortable", 0…10 K is
# "tight" (warn), <0 K exceeds T_jmax (fail).
_WARN_HEADROOM_K = 10.0


def _verdict_for(headroom_k: float | None) -> str:
    if headroom_k is None:
        return "unknown"
    if headroom_k < 0:
        return "fail"
    if headroom_k < _WARN_HEADROOM_K:
        return "warn"
    return "pass"


def evaluate_stack(chain: list, boards: dict, *, fab=None,
                   use_p_max: bool = False,
                   t_ambient_c: float = T_AMBIENT_C_DEFAULT,
                   potting: bool = True,
                   potting_gap_mm: float = POTTING_GAP_MM_DEFAULT,
                   flex_width_overrides_mm: dict | None = None,
                   ) -> StackThermalResult:
    """Build the thermal graph for `chain`, solve it, and classify
    every dissipating die against its `chip.tj_max_c`."""
    g = build_graph(
        chain=chain, boards=boards, fab=fab, use_p_max=use_p_max,
        t_ambient_c=t_ambient_c, potting=potting,
        potting_gap_mm=potting_gap_mm,
        flex_width_overrides_mm=flex_width_overrides_mm,
    )
    temps = solve(g)

    dies: list = []
    for n in g.nodes.values():
        if n.kind != "die":
            continue
        body_t = temps.get(f"body:{n.parent_tile}", float("nan"))
        die_t = temps[n.name]
        tj = getattr(n.chip, "tj_max_c", None) if n.chip else None
        headroom = (tj - die_t) if tj is not None else None
        dies.append(DieVerdict(
            ref=n.chip.ref if n.chip else n.name,
            tile=n.parent_tile, p_w=n.p_input_w,
            t_die_c=die_t, t_body_c=body_t, delta_t_k=die_t - body_t,
            tj_max_c=tj, headroom_k=headroom,
            verdict=_verdict_for(headroom),
        ))

    tiles: list = []
    for n in g.nodes.values():
        if n.kind not in ("tile_body", "spacer_body"):
            continue
        name = n.name.removeprefix("body:")
        tiles.append(TileVerdict(
            tile=name,
            kind="spacer" if n.kind == "spacer_body" else "rigid",
            t_body_c=temps[n.name],
        ))

    worst = None
    rated = [d for d in dies if d.headroom_k is not None]
    if rated:
        worst = min(rated, key=lambda d: d.headroom_k)
    elif dies:
        worst = max(dies, key=lambda d: d.t_die_c)

    return StackThermalResult(
        chain=list(chain), t_ambient_c=t_ambient_c, use_p_max=use_p_max,
        p_total_w=sum(d.p_w for d in dies),
        temps=temps, dies=dies, tiles=tiles, worst_die=worst,
    )
