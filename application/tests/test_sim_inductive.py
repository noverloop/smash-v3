"""Axisymmetric magneto-quasistatic solver (smash.sim.inductive) — checked
against closed forms: a loop in free space, the long-tube DC limit, and the
eddy-current shielding of a long conducting tube."""
from __future__ import annotations

import cmath
import math

import pytest

from smash.sim.inductive.solver import MU0, Mesh, Region, graded_axis

MM = 1e-3


def _mesh(regions, r_marks, z_marks, h_fine=0.25 * MM, fine_r=0.05, fine_z=0.06):
    r = graded_axis(0.0, 1.0, r_marks, lambda a, b: h_fine if b <= fine_r + 1e-12 else None, 0.05)
    z = graded_axis(-1.0, 1.0, z_marks,
                    lambda a, b: h_fine if (a >= -fine_z - 1e-12 and b <= fine_z + 1e-12) else None, 0.05)
    return Mesh(r, z, regions)


def test_loop_in_free_space_matches_biot_savart():
    a = 20 * MM
    m = _mesh([Region("coil", a - 0.5 * MM, a + 0.5 * MM, -0.5 * MM, 0.5 * MM, turns=1)],
              [a - 0.5 * MM, a + 0.5 * MM, 0.05], [-0.06, -0.5 * MM, 0.5 * MM, 0.06])
    psi = m.solve(0.0, {"coil": 1.0})
    for z in (0.0, 10 * MM, 20 * MM, 40 * MM):
        analytic = MU0 * a * a / (2 * (a * a + z * z) ** 1.5)
        assert m.B_at(psi, 0.2 * MM, z)[1].real == pytest.approx(analytic, rel=2e-3)


def _solenoid_in_tube(mu_r, sigma, f, wall=1.0 * MM, half_len=0.15):
    """Solenoid (r 25 mm, ±half_len) around a tube (r_in 15 mm, ±half_len+0.1)."""
    ri, ro = 15 * MM, 15 * MM + wall
    regs = [Region("coil", 25 * MM, 26 * MM, -half_len, half_len, turns=300)]
    zt = half_len + 0.1
    if mu_r != 1.0 or sigma:
        regs.insert(0, Region("tube", ri, ro, -zt, zt, mu_r=mu_r, sigma=sigma))
    h_r = lambda a, b: (0.1 * MM if (a >= ri - 1e-12 and b <= ro + 1e-12)
                        else 0.5 * MM if b <= 0.03 + 1e-12 else None)
    r = graded_axis(0.0, 1.0, [ri, ro, 25 * MM, 26 * MM, 0.03], h_r, 0.05)
    z = graded_axis(-2.0, 2.0, [-zt, -half_len, half_len, zt],
                    lambda a, b: 2 * MM if (a >= -zt - 1e-12 and b <= zt + 1e-12) else None, 0.05)
    m = Mesh(r, z, regs)
    psi = m.solve(2 * math.pi * f, {"coil": 1.0})
    return m.B_at(psi, 1 * MM, 0.0)[1]


def test_long_tube_does_not_shield_axial_dc_field():
    """Tangential H is continuous and no currents flow at DC: a long permeable
    tube leaves the axial solenoid field inside unchanged (long-geometry limit;
    a µr-100 tube only ~10 diameters long already pulls ~10 % of the flux)."""
    b_air = _solenoid_in_tube(1.0, 0.0, 0.0, half_len=0.6)
    b_steel = _solenoid_in_tube(100.0, 5e6, 0.0, half_len=0.6)
    assert abs(b_steel) == pytest.approx(abs(b_air), rel=0.03)


def test_conducting_tube_shielding_matches_closed_form():
    """Axial shielding of a long tube: H_in/H_out = 1 / (cosh kt + k a/(2 µr) sinh kt),
    k = (1+j)/δ (Kaden). Non-magnetic Al, 1 mm, 1 kHz."""
    sigma, wall, f, a = 3.5e7, 1.0 * MM, 1000.0, 15.5 * MM
    b_air = _solenoid_in_tube(1.0, 0.0, f, wall)
    b_al = _solenoid_in_tube(1.0 + 1e-9, sigma, f, wall)
    delta = 1 / math.sqrt(math.pi * f * MU0 * sigma)
    k = (1 + 1j) / delta
    s = cmath.cosh(k * wall) + k * a / 2 * cmath.sinh(k * wall)
    assert abs(b_al / b_air) == pytest.approx(1 / abs(s), rel=0.08)


def test_steel_body_study_runs():
    from smash.sim.inductive.model import LinkParams
    from smash.sim.inductive.study import run_case
    rows = run_case(LinkParams(wall_mm=2.0), freqs=(3.0, 300.0))
    lo, hi = rows
    assert lo["dl_AT_hall"] > lo["dl_AT_tmr"] > 0
    assert hi["ul_M_nH"] < lo["ul_M_nH"]          # eddy currents shield more at 300 Hz
    assert lo["ul_snr_mag_dB"] > 0
