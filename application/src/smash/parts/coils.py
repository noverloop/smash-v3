"""Embedded PCB coils (project pseudo-parts: copper in the board, nothing to buy).

`add_health_coil` — the magnetic "healthy and running" beacon (2026-11-18,
user): an Archimedean spiral on ONE inner layer at the board rim, inner end
returned on the next inner layer to a second feed via. Pulsed at 3–30 Hz it
is picked up through the gun barrel by a ring clamp (smash.sim.inductive:
≥ 48 dB at 1–10 mm steel for ~2 A·turns). It lives on aft_end_board, far from
the antennas; at these frequencies the board's copper planes and the Al
battery-holder floor above it are transparent (eddy corner ≳ 0.8 kHz).

Modelled like the castellations: `manf="project"`, so it is exempt from the
part-overlap guard and the BOM; the feed vias are TENTED (the Al holder floor
— GND — bears on aft_end's top face).
"""
from __future__ import annotations

import math

from smash.state import Footprint, Pad, Pin

COIL_LAYER = "In2.Cu"
RETURN_LAYER = "In3.Cu"
VIA_D_MM, VIA_DRILL_MM = 0.6, 0.3


def spiral_points(r_out: float, r_in: float, turns: float, a0_deg: float,
                  seg_deg: float = 5.0) -> list:
    """Archimedean spiral from (r_out, a0) inward to (r_in, a0 + 360·turns), CCW."""
    n = max(2, int(round(360.0 * turns / seg_deg)))
    pts = []
    for k in range(n + 1):
        t = k / n
        r = r_out - (r_out - r_in) * t
        a = math.radians(a0_deg + 360.0 * turns * t)
        pts.append((round(r * math.cos(a), 4), round(r * math.sin(a), 4)))
    return pts


def coil_estimates(r_out: float, r_in: float, turns: int, trace_mm: float,
                   cu_um: float = 17.5) -> dict:
    """Length, DC resistance (½ oz inner copper by default) and the magnetic
    moment per amp (Σ loop areas)."""
    rm = 0.5 * (r_out + r_in)
    length = 2 * math.pi * rm * turns * 1e-3
    R = 1.7e-8 * length / (trace_mm * 1e-3 * cu_um * 1e-6)
    area = sum(math.pi * (r_in + (r_out - r_in) * (k + 0.5) / turns) ** 2 for k in range(turns)) * 1e-6
    return {"length_m": length, "R_ohm": R, "moment_Am2_per_A": area}


def add_health_coil(design, ref: str = "L_HEALTH_COIL", *, board_tag: str,
                    r_out_mm: float = 15.5, r_in_mm: float = 12.0, turns: int = 8,
                    trace_mm: float = 0.25, feed_deg: float = 31.25, **overrides):
    """Embedded 8-turn rim spiral (In2.Cu) + In3.Cu return. Pin 1 = outer feed
    (to the supply), pin 2 = return (to the low-side driver). Place at the
    board centre, rotation 0 (feed angle is board-local)."""
    pts = spiral_points(r_out_mm, r_in_mm, turns, feed_deg)
    a1 = math.radians(feed_deg)
    a2 = math.radians(feed_deg + 5.0)
    p1 = (round(r_out_mm * math.cos(a1), 4), round(r_out_mm * math.sin(a1), 4))
    p_in = pts[-1]
    p2 = (round(r_out_mm * math.cos(a2), 4), round(r_out_mm * math.sin(a2), 4))
    est = coil_estimates(r_out_mm, r_in_mm, turns, trace_mm)
    tent = -VIA_D_MM / 2.0
    pads = [Pad(num="1", position_mm=p1, size_mm=(VIA_D_MM, VIA_D_MM), shape="round",
                layer="*.Cu", drill_mm=VIA_DRILL_MM, paste=False,
                solder_mask_expansion_mm=tent, note="coil outer feed (tented)"),
            Pad(num="2", position_mm=p_in, size_mm=(VIA_D_MM, VIA_D_MM), shape="round",
                layer="*.Cu", drill_mm=VIA_DRILL_MM, paste=False,
                solder_mask_expansion_mm=tent, note="coil inner end → return layer (tented)"),
            Pad(num="2", position_mm=p2, size_mm=(VIA_D_MM, VIA_D_MM), shape="round",
                layer="*.Cu", drill_mm=VIA_DRILL_MM, paste=False,
                solder_mask_expansion_mm=tent, note="coil return feed (tented)")]
    ring = ([(r_out_mm * math.cos(math.radians(d)), r_out_mm * math.sin(math.radians(d)))
             for d in range(0, 361, 10)]
            + [(r_in_mm * math.cos(math.radians(d)), r_in_mm * math.sin(math.radians(d)))
               for d in range(360, -1, -10)])
    fp = Footprint(name=f"HealthCoil_{turns}t_R{r_in_mm:g}-{r_out_mm:g}",
                   package_class="embedded PCB coil", pads=pads,
                   body_outline=ring, size_mm=(2 * r_out_mm, 2 * r_out_mm),
                   height_mm=0.0, source="project",
                   note=(f"{turns}-turn Archimedean spiral on {COIL_LAYER}, r {r_in_mm:g}–"
                         f"{r_out_mm:g} mm, {trace_mm:g} mm trace; inner end returns on "
                         f"{RETURN_LAYER}. ≈ {est['R_ohm']:.1f} Ω (½ oz), "
                         f"{est['moment_Am2_per_A'] * 1e4:.1f} cm²·turns."))
    fp.copper_lines.append({"layer": COIL_LAYER, "width_mm": trace_mm, "points": [p1] + pts})
    fp.copper_lines.append({"layer": RETURN_LAYER, "width_mm": trace_mm, "points": [p_in, p2]})
    fields = dict(
        manf="project", manf_pn="EMBEDDED_HEALTH_COIL", name="EMBEDDED_HEALTH_COIL",
        value=f"{turns}t PCB coil", footprint=fp,
        pins=[Pin(num="1", name="FEED"), Pin(num="2", name="RET")],
        weight_g=0.0, height_mm=0.0,
        note=("Magnetic health beacon (round → ring clamp around the barrel). "
              "Copper in the board; routed by the layout EE on "
              f"{COIL_LAYER}/{RETURN_LAYER} — keep those layers clear in the ring."),
    )
    fields.update(overrides)
    return design.add_chip(ref=ref, board_tag=board_tag, **fields)
