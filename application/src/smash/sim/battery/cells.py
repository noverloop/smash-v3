"""Tadiran Li-MnO2 cell model V(q, I, T) — ported from the August mission sim.

Source: smash-electronics tools/simulate_battery_mission.py (2026-08-07, the
Tadiran-review sim). The curve tables are digitized from the datasheets in
smash-electronics/Research/ and cross-checked by `validate_rows()` against the
datasheet text anchors (capacity at the spec currents, CCV minima).

Modelling choices (unchanged from the August sim, all flagged in its review):
  * between digitized currents V is interpolated pointwise in ln(I); above the
    highest curve an incremental pulse resistance extends the family;
  * ms-class pulses use `voltage_fast`: low-rate baseline minus r_hf * I (the
    minutes-settled RT family is far too saggy for a few-ms event);
  * temperature = capacity scale + reference sag dV at temp_ref_amps, scaled
    as dV * (I / Iref) ** cold_alpha (alpha 0.6 calibrated on the pulse-vs-
    temperature charts; 1.0 = linear worst case);
  * aging = the datasheets' accumulated-capacity-loss table applied as
    pre-consumed charge (below 22 C storage the 22 C column is scaled by
    0.5 ** ((22 - T) / 17));
  * cold + high-rate is an EXTRAPOLATION (the cold families stop at 0.25-0.5 A
    per cell) and self-heating is unmodelled (upside).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace


def interp(pairs: list[tuple[float, float]], x: float, plunge: float = 0.0) -> float:
    """Piecewise-linear lookup; beyond the last point descend at `plunge`/unit."""
    if x <= pairs[0][0]:
        return pairs[0][1]
    for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    xl, yl = pairs[-1]
    return yl - plunge * (x - xl)


_PLUNGE_V_PER_MAH = 0.15   # collapse slope past a curve's last digitized point


@dataclass(frozen=True)
class CellModel:
    name: str
    datasheet: str
    capacity_ref_mah: float                              # headline low-rate (pack)
    rt_curves: dict[float, list[tuple[float, float]]]    # PER-CELL amps -> [(mAh, V)]
    pulse_r_ohm: float                                   # per cell, above the top curve
    r_hf_ohm: float                                      # per cell, ms-class pulse R
    temp_ref_amps: float                                 # per cell
    temp_derate: dict[float, tuple[float, float]]        # T -> (cap scale, dV @ ref)
    i_cont_max: float                                    # PACK ratings
    i_pulse_1s_max: float
    n_parallel: int = 1
    r_iso_ohm: float = 0.0                               # per-cell isolation resistor

    def _temp(self, t_c: float) -> tuple[float, float]:
        pts = sorted(self.temp_derate.items())
        if t_c <= pts[0][0]:
            return pts[0][1]
        for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
            if t_c <= t1:
                f = (t_c - t0) / (t1 - t0)
                return (v0[0] + f * (v1[0] - v0[0]), v0[1] + f * (v1[1] - v0[1]))
        return pts[-1][1]

    def voltage(self, q_mah: float, i_a: float, t_c: float,
                cold_alpha: float = 0.6) -> float:
        """Settled (seconds-minutes) pack terminal voltage at consumed charge q
        and pack current i. Parallel cells share charge and current evenly."""
        q_mah, i_a = q_mah / self.n_parallel, i_a / self.n_parallel
        cap_scale, dv_ref = self._temp(t_c)
        q = q_mah / max(cap_scale, 1e-3)
        cs = sorted(self.rt_curves)
        if i_a <= cs[0]:
            v = interp(self.rt_curves[cs[0]], q, _PLUNGE_V_PER_MAH)
        elif i_a >= cs[-1]:
            v = (interp(self.rt_curves[cs[-1]], q, _PLUNGE_V_PER_MAH)
                 - (i_a - cs[-1]) * self.pulse_r_ohm)
        else:
            for lo, hi in zip(cs, cs[1:]):
                if i_a <= hi:
                    f = math.log(i_a / lo) / math.log(hi / lo)
                    vlo = interp(self.rt_curves[lo], q, _PLUNGE_V_PER_MAH)
                    vhi = interp(self.rt_curves[hi], q, _PLUNGE_V_PER_MAH)
                    v = vlo + f * (vhi - vlo)
                    break
        if dv_ref:
            v -= dv_ref * (max(i_a, 1e-9) / self.temp_ref_amps) ** cold_alpha
        return v - self.r_iso_ohm * i_a

    def voltage_fast(self, q_mah: float, i_a: float, t_c: float,
                     cold_alpha: float = 0.6) -> float:
        """ms-class pulse voltage: low-rate baseline minus the HF resistance;
        the cold penalty at ms timescales is ~0.4x the settled one."""
        q_mah, i_a = q_mah / self.n_parallel, i_a / self.n_parallel
        cap_scale, dv_ref = self._temp(t_c)
        q = q_mah / max(cap_scale, 1e-3)
        v = (interp(self.rt_curves[min(self.rt_curves)], q, _PLUNGE_V_PER_MAH)
             - self.r_hf_ohm * i_a)
        if dv_ref:
            v -= 0.4 * dv_ref * (max(i_a, 1e-9) / self.temp_ref_amps) ** cold_alpha
        return v - self.r_iso_ohm * i_a


# Accumulated capacity loss, fraction of rated (identical across the TLM family).
_AGING = {
    22.0: [(0, 0.0), (1, 0.03), (5, 0.07), (10, 0.11), (15, 0.15), (20, 0.18)],
    55.0: [(0, 0.0), (1, 0.06), (5, 0.22), (10, 0.32), (15, 0.42)],
    72.0: [(0, 0.0), (1, 0.10), (5, 0.40)],
}


def aging_loss_frac(t_c: float, years: float) -> float:
    if years <= 0:
        return 0.0
    if t_c <= 22.0:
        return interp(_AGING[22.0], years) * 0.5 ** ((22.0 - t_c) / 17.0)
    ts = sorted(_AGING)
    for t0, t1 in zip(ts, ts[1:]):
        if t_c <= t1:
            f = (t_c - t0) / (t1 - t0)
            return interp(_AGING[t0], years) * (1 - f) + interp(_AGING[t1], years) * f
    return interp(_AGING[ts[-1]], years)


# --- TLM-1520HPM Rev A (the flight cell, 125 mAh, Z < 100 mohm) -------------
# Preliminary 2016 datasheet; its gun/deceleration rating is an open Tadiran
# qualification item (power_budget Appendix A).
TLM1520HPM = CellModel(
    name="TLM-1520HPM",
    datasheet="smash-electronics/Research/TLM-1520HPM_S.pdf",
    capacity_ref_mah=125.0,
    rt_curves={
        0.005: [(0, 4.05), (3, 3.98), (10, 3.90), (25, 3.80), (50, 3.68),
                (80, 3.55), (105, 3.45), (118, 3.32), (123, 3.00),
                (126, 2.60), (128, 2.50)],
        0.062: [(0, 3.97), (5, 3.85), (15, 3.75), (40, 3.62), (70, 3.50),
                (95, 3.38), (105, 3.20), (109, 2.90), (111, 2.60)],
        0.125: [(0, 3.93), (5, 3.80), (15, 3.70), (40, 3.57), (70, 3.44),
                (88, 3.30), (96, 3.10), (100, 2.82), (103, 2.55)],
        0.25:  [(0, 3.90), (5, 3.76), (15, 3.66), (40, 3.53), (70, 3.40),
                (85, 3.28), (93, 3.08), (98, 2.80), (101, 2.50)],
        0.5:   [(0, 3.83), (5, 3.68), (15, 3.58), (40, 3.45), (70, 3.32),
                (82, 3.18), (90, 2.98), (95, 2.72), (97, 2.50)],
        1.0:   [(0, 3.70), (5, 3.55), (15, 3.46), (40, 3.33), (65, 3.20),
                (78, 3.05), (86, 2.85), (90, 2.62), (92, 2.50)],
    },
    pulse_r_ohm=0.35,
    r_hf_ohm=0.20,   # Rev A pulse chart, 5 ms: 1.5 A -> ~3.68 V from 4.05
    temp_ref_amps=0.25,
    temp_derate={
        -40.0: (0.55, 0.85), -20.0: (0.82, 0.20), 0.0: (0.92, 0.12),
        22.0: (1.00, 0.00), 85.0: (1.10, -0.05),
    },
    i_cont_max=1.75,
    i_pulse_1s_max=3.75,
)

# --- TLM-1520M Rev C (same Ø15.1 x 21 can; 20 000 gn TESTED) -----------------
TLM1520M = CellModel(
    name="TLM-1520M/S",
    datasheet="smash-electronics/Research/TLM-1520M-Rev-C.pdf",
    capacity_ref_mah=120.0,
    rt_curves={
        0.012: [(0, 4.03), (3, 3.96), (10, 3.88), (30, 3.76), (55, 3.66),
                (80, 3.56), (100, 3.44), (110, 3.30), (116, 3.05),
                (120, 2.80), (122, 2.50)],
        0.025: [(0, 4.02), (3, 3.90), (10, 3.80), (30, 3.70), (55, 3.60),
                (80, 3.50), (98, 3.38), (108, 3.22), (113, 2.95),
                (116, 2.70), (118, 2.50)],
        0.125: [(0, 3.90), (5, 3.74), (15, 3.64), (40, 3.54), (65, 3.44),
                (85, 3.32), (96, 3.18), (102, 2.98), (105, 2.80),
                (107, 2.55)],
        0.25:  [(0, 3.86), (5, 3.66), (15, 3.56), (40, 3.47), (65, 3.38),
                (82, 3.26), (92, 3.10), (98, 2.88), (101, 2.65),
                (103, 2.50)],
        0.5:   [(0, 3.75), (5, 3.52), (15, 3.43), (40, 3.34), (62, 3.24),
                (78, 3.12), (87, 2.96), (92, 2.75), (95, 2.55),
                (96, 2.50)],
        1.0:   [(0, 3.55), (5, 3.34), (15, 3.25), (35, 3.16), (55, 3.06),
                (70, 2.94), (80, 2.80), (85, 2.62), (88, 2.50)],
    },
    pulse_r_ohm=0.50,
    r_hf_ohm=0.40,
    temp_ref_amps=0.25,
    temp_derate={
        -40.0: (0.20, 1.40), -30.0: (0.62, 0.55), -20.0: (0.80, 0.40),
        0.0: (0.92, 0.15), 22.0: (1.00, 0.00), 85.0: (1.08, -0.05),
    },
    i_cont_max=1.0,
    i_pulse_1s_max=3.5,
)

# The flight pack: 3x TLM-1520HPM in parallel, one 200 mohm iso resistor per
# cell into BAT_RAW (generate_stackup.py R_BAT1..3_ISO).
PACK_3X_1520HPM = replace(
    TLM1520HPM, name="3x TLM-1520HPM", capacity_ref_mah=375.0,
    n_parallel=3, r_iso_ohm=0.2, i_cont_max=5.25, i_pulse_1s_max=11.25)

# What-if: the gun-rated M/S cell in the same trefoil.
PACK_3X_1520M = replace(
    TLM1520M, name="3x TLM-1520M/S", capacity_ref_mah=360.0,
    n_parallel=3, r_iso_ohm=0.2, i_cont_max=3.0, i_pulse_1s_max=10.5)

PACKS = {"3x1520hpm": PACK_3X_1520HPM, "3x1520m": PACK_3X_1520M}


def capacity_to(cell: CellModel, amps: float, v_cut: float, t_c: float = 22.0,
                dq: float = 0.25) -> float:
    """Constant-current mAh delivered to a cutoff (single-cell or pack)."""
    q, q_cap = 0.0, cell.capacity_ref_mah * 1.5
    while cell.voltage(q, amps, t_c) >= v_cut and q < q_cap:
        q += dq
    return q


# Datasheet text anchors: (cell, amps, cutoff V, DS mAh, source)
VALIDATION_ANCHORS = [
    (TLM1520HPM, 0.005, 2.8, 125.0, "1520HPM Rev A text"),
    (TLM1520HPM, 0.125, 2.8, 100.0, "1520HPM Rev A text"),
    (TLM1520M, 0.012, 2.8, 120.0, "1520M Rev C text"),
    (TLM1520M, 0.125, 2.8, 105.0, "1520M Rev C text"),
]


def validate_rows() -> list[tuple[str, float, float, float, float, str]]:
    """(cell, I, cutoff, DS mAh, sim mAh, source) for each anchor."""
    return [(c.name, a, v, ds, capacity_to(c, a, v), src)
            for c, a, v, ds, src in VALIDATION_ANCHORS]
