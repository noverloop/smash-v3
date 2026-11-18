"""Tower-in-steel-body model for the two-way inductive (magnetic) link, 2026-11-18.

Scenario (user): the potted tower (in its PEEK-LDS cup) sits inside a STEEL
body; the reader/writer is a RING CLAMP coil around the outside of the body,
coaxial with the tower → axisymmetric. The link carries a boolean / a few bits
as pulses:

  DOWNLINK (reader → round): the clamp drives a slow coded field; the round's
    EXISTING wake sensors hear it — U_MAG_WAKE DRV5032FC Hall (B_OP 4.8 mT max,
    20 Hz sampling) and U_MAG_SHELF RR123 TMR (B_OP 0.7 mT, 1 Hz) on the
    wakeup board. Magnetic wake-up stays as designed.
  UPLINK (round → reader): the "healthy and running" beacon — L_HEALTH_COIL,
    an 8-turn spiral embedded in aft_end_board (In2.Cu, r 12–15.5 mm, under
    the Al battery-holder floor) pulsed at ~0.19 A; the clamp coil (EMF) or a
    magnetometer on the clamp picks it up.
  The clamp is centred on the coil for the uplink and on the wakeup board's
  sensors for the downlink (two clamp positions).

Everything that conducts or guides flux near the coils is modelled as an
axisymmetric body (stack heights from smash.sim.antenna.geometry):
steel body tube, 7075 battery holder + floor, the cells (steel cans
homogenised: their eddy loops do not encircle the tower axis → σ = 0, µ_eff
from the can steel fraction), board copper planes as conductive discs, the
1 mm 7075 gap rings. PEEK, potting and FR-4 are air for this purpose.

⚠ Linear steel (µ_r constant, no hysteresis / saturation): the study reports
the peak |B| in the wall so saturation can be checked. Carbon / alloy steel:
σ ≈ 5 MS/m, initial µ_r ≈ 50–300 (sweep with `mu_r`).
"""
from __future__ import annotations

import dataclasses
import math

from smash.sim.antenna.geometry import BOARD_MID_Z_MM, BOARD_T_MM, CELL_Z_MM
from smash.sim.inductive.solver import Mesh, Region, graded_axis

MM = 1e-3
SIGMA_STEEL = 5.0e6
SIGMA_AL7075 = 1.9e7
SIGMA_CU = 5.8e7
CU_FRACTION = 0.10              # ~4 × 35 µm planes in a 1.315 mm 8L board
CELL_CAN_FRACTION = 0.04        # 3 × Ø14.8 × 0.25 mm Ni-plated steel cans / Ø32 section


@dataclasses.dataclass
class LinkParams:
    wall_mm: float = 3.0              # steel body wall thickness
    body_id_mm: float = 36.2          # body bore (cup OD 35.8 + 0.2)
    body_len_mm: float = 250.0        # open-ended tube, tower centred in it
    mu_r: float = 100.0               # steel (initial permeability)
    sigma_steel: float = SIGMA_STEEL
    # reader ring clamp (outside the body, coaxial)
    clamp_gap_mm: float = 1.0
    clamp_radial_mm: float = 6.0
    clamp_len_mm: float = 20.0
    clamp_turns: int = 200
    # tower coil: L_HEALTH_COIL, embedded in aft_end_board (smash.parts.coils)
    tower_board: str = "aft_end_board"
    tower_r_mm: tuple = (12.0, 15.5)
    tower_turns: int = 8
    # wake sensors on the wakeup board top face (r ≈ 9.8 / 11.7 mm)
    sensor_board: str = "wakeup_board"
    sensor_r_mm: float = 10.5
    clamp_on: str = "tower"           # "tower" (uplink) | "sensor" (downlink)
    with_internals: bool = True

    @property
    def body_r_in(self):
        return self.body_id_mm / 2 * MM

    @property
    def body_r_out(self):
        return self.body_r_in + self.wall_mm * MM


def _z(b):
    return BOARD_MID_Z_MM[b] * MM


def build(p: LinkParams, f_max_hz: float = 1000.0) -> tuple:
    """(Mesh, info) for one geometry. Mesh resolves the steel skin depth at
    f_max (≥ 4 cells per δ) — rebuild for higher frequencies."""
    t = BOARD_T_MM * MM
    zt = _z(p.tower_board)
    zs = _z(p.sensor_board)
    zcl = zt if p.clamp_on == "tower" else zs
    tower_mid = 0.5 * (BOARD_MID_Z_MM["aft_end_board"] + BOARD_MID_Z_MM["radar_module"]) * MM
    zb0 = tower_mid - p.body_len_mm * MM / 2
    zb1 = tower_mid + p.body_len_mm * MM / 2
    ri, ro = p.body_r_in, p.body_r_out
    rc0 = ro + p.clamp_gap_mm * MM
    rc1 = rc0 + p.clamp_radial_mm * MM
    zc0, zc1 = zcl - p.clamp_len_mm * MM / 2, zcl + p.clamp_len_mm * MM / 2
    regions = []
    if p.with_internals:
        # boards: copper planes → thin conductive discs
        for b, zm in BOARD_MID_Z_MM.items():
            if b == "radar_module":
                continue                          # not in every config; core stack only
            regions.append(Region(f"board_{b}", 0.0, 17.0 * MM, zm * MM - t / 2, zm * MM + t / 2,
                                  sigma=SIGMA_CU * CU_FRACTION))
        # 7075 battery holder: 0.8 mm skin r 16.2–17 + 1.2 mm floor, cells inside
        z_h0 = (BOARD_MID_Z_MM["aft_end_board"] + BOARD_T_MM / 2) * MM
        z_h1 = (BOARD_MID_Z_MM["activation_interface"] - BOARD_T_MM / 2) * MM
        regions.append(Region("holder_skin", 16.2 * MM, 17.0 * MM, z_h0, z_h1, sigma=SIGMA_AL7075))
        regions.append(Region("holder_floor", 0.0, 17.0 * MM, z_h0, z_h0 + 1.2 * MM, sigma=SIGMA_AL7075))
        mu_cells = 1.0 + CELL_CAN_FRACTION * (p.mu_r - 1.0)
        regions.append(Region("cells", 0.0, 15.4 * MM, CELL_Z_MM[0] * MM, CELL_Z_MM[1] * MM,
                              mu_r=mu_cells))
        # 1 mm 7075 gap rings (wakeup↔power, power↔compute); GF30 PEEK elsewhere = air
        for lo, hi in (("wakeup_board", "power_board"), ("power_board", "companion_compute")):
            regions.append(Region(f"ring_{lo}", 16.0 * MM, 17.0 * MM, _z(lo) + t / 2, _z(hi) - t / 2,
                                  sigma=SIGMA_AL7075))
        # tower coil sits in a slit-plane window of its board
        regions.append(Region("tower_window", p.tower_r_mm[0] * MM - 0.5 * MM,
                              p.tower_r_mm[1] * MM + 0.5 * MM, zt - t / 2, zt + t / 2))
    regions.append(Region("tower_coil", p.tower_r_mm[0] * MM, p.tower_r_mm[1] * MM,
                          zt - t / 2 + 0.2 * MM, zt + t / 2 - 0.2 * MM, turns=p.tower_turns))
    regions.append(Region("steel", ri, ro, zb0, zb1, mu_r=p.mu_r, sigma=p.sigma_steel))
    regions.append(Region("clamp", rc0, rc1, zc0, zc1, turns=p.clamp_turns))

    k_skin = math.pi * f_max_hz * 4e-7 * math.pi * p.mu_r * p.sigma_steel
    delta = 1.0 / math.sqrt(k_skin) if k_skin > 0 else 1.0     # no conducting body
    h_steel = min(0.25 * MM, delta / 4)
    R_MAX, Z_PAD = 0.6, 0.6
    r_marks = sorted({x for reg in regions for x in (reg.r0, reg.r1)} | {0.0, 0.03})
    z_marks = sorted({x for reg in regions for x in (reg.z0, reg.z1)})

    def h_r(a, b):
        if a >= ri - 1e-12 and b <= ro + 1e-12:
            return h_steel
        if b <= 0.03 + 1e-12:
            return 0.25 * MM
        if b <= rc1 + 1e-12:
            return 0.5 * MM
        return None

    def h_z(a, b):
        near_end = min(abs(a - zb0), abs(b - zb0), abs(a - zb1), abs(b - zb1)) < 5 * MM
        if near_end:
            return 0.5 * MM
        if a >= -5 * MM and b <= 70 * MM:
            return 0.25 * MM
        return None

    r = graded_axis(0.0, R_MAX, r_marks, h_r, 20 * MM)
    z = graded_axis(zb0 - Z_PAD, zb1 + Z_PAD, z_marks, h_z, 20 * MM)
    mesh = Mesh(r, z, regions)
    info = {"z_tower_coil": zt, "z_sensor": zs + t / 2 + 0.5 * MM,
            "r_sensor": p.sensor_r_mm * MM, "r_clamp_mid": 0.5 * (rc0 + rc1),
            "skin_depth_mm_at_fmax": delta / MM, "n_nodes": len(r) * len(z)}
    return mesh, info
