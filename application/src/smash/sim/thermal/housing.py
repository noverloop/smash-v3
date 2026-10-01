"""Housing heat-dissipation budget for the projectile in flight.

Lifted from the legacy (now-removed) `thermal_sim/housing_dissipation
.py` — self-contained physics (atmosphere model, recovery temperature,
turbulent flat-plate h, radiation) that doesn't touch the smash data
model. The driver passes
geometry + flight regime; the budget says how much heat the housing
can shed (or, supersonic, must absorb from the boundary layer).

Pair with `solve()` on the internal RC graph: the chip-side heat load
+ internal R_th up to the housing wall sets the housing surface T;
`compute_budget()` then checks whether the housing can carry that T to
the air at the chosen flight regime.
"""
from __future__ import annotations

import dataclasses
import math


GAMMA_AIR = 1.4
R_AIR = 287.05
PR_AIR = 0.71
CP_AIR = 1005.0
RECOVERY_FACTOR_TURB = 0.85
STEFAN_BOLTZMANN = 5.670374e-8


def standard_atmosphere(altitude_m: float) -> tuple[float, float]:
    """US Standard Atmosphere 1976. Returns (T_K, p_Pa) at altitude."""
    if altitude_m < 11_000.0:
        T = 288.15 - 0.0065 * altitude_m
        p = 101325.0 * (T / 288.15) ** 5.2561
    else:
        T = 216.65
        p = 22632.0 * math.exp(-0.0001577 * (altitude_m - 11_000.0))
    return T, p


def air_properties(T_K: float, p_Pa: float) -> tuple[float, float, float, float]:
    """(ρ, μ, k_air, ν) at given (T, p). Sutherland viscosity."""
    rho = p_Pa / (R_AIR * T_K)
    mu = 1.716e-5 * (T_K / 273.15) ** 1.5 * (273.15 + 110.4) / (T_K + 110.4)
    k_air = mu * CP_AIR / PR_AIR
    nu = mu / rho
    return rho, mu, k_air, nu


def speed_of_sound(T_K: float) -> float:
    return math.sqrt(GAMMA_AIR * R_AIR * T_K)


def recovery_temperature(T_static_K: float, mach: float,
                         recovery_factor: float = RECOVERY_FACTOR_TURB) -> float:
    return T_static_K * (1.0 + recovery_factor * (GAMMA_AIR - 1.0) / 2.0
                         * mach ** 2)


def average_h_flat_plate(velocity_m_s: float, length_m: float,
                         T_film_K: float, p_Pa: float
                         ) -> tuple[float, float]:
    """Turbulent flat-plate average h. Falls back to laminar Nu below
    the transition Re. Returns `(h W/(m²·K), Re_L)`."""
    _, _, k_air, nu = air_properties(T_film_K, p_Pa)
    Re_L = velocity_m_s * length_m / nu
    if Re_L > 5e5:
        Nu_L = 0.037 * Re_L ** 0.8 * PR_AIR ** (1.0 / 3.0)
    else:
        Nu_L = 0.664 * Re_L ** 0.5 * PR_AIR ** (1.0 / 3.0)
    return Nu_L * k_air / length_m, Re_L


def cylinder_lateral_area(dia_mm: float, length_mm: float) -> float:
    """π · D · L in m² — side-of-cylinder area, excludes end caps."""
    return math.pi * (dia_mm * 1e-3) * (length_mm * 1e-3)


@dataclasses.dataclass
class HousingBudget:
    mach: float
    altitude_m: float
    housing_dia_mm: float
    housing_len_mm: float
    emissivity: float
    t_housing_max_c: float
    q_chip_load_w: float
    # Derived
    t_static_c: float
    p_static_pa: float
    velocity_m_s: float
    t_recovery_c: float
    reynolds: float
    h_conv_w_per_m2_k: float
    area_m2: float
    q_conv_w: float
    q_rad_w: float
    q_out_total_w: float
    margin_w: float


def compute_budget(*, mach: float, altitude_m: float, housing_dia_mm: float,
                   housing_len_mm: float, emissivity: float,
                   t_housing_max_c: float, q_chip_load_w: float
                   ) -> HousingBudget:
    """Compute the housing's net heat-shedding capacity at `t_housing_max_c`
    and the margin against the internal `q_chip_load_w`."""
    T_static_K, p_Pa = standard_atmosphere(altitude_m)
    a = speed_of_sound(T_static_K)
    velocity = mach * a
    T_r_K = recovery_temperature(T_static_K, mach)
    T_h_K = t_housing_max_c + 273.15
    T_film_K = 0.5 * (T_h_K + T_r_K)
    h, Re = average_h_flat_plate(velocity, housing_len_mm * 1e-3,
                                 T_film_K, p_Pa)
    A = cylinder_lateral_area(housing_dia_mm, housing_len_mm)
    q_conv = h * A * (T_h_K - T_r_K)
    q_rad = emissivity * STEFAN_BOLTZMANN * A * (T_h_K ** 4 - T_r_K ** 4)
    q_out = q_conv + q_rad
    return HousingBudget(
        mach=mach, altitude_m=altitude_m, housing_dia_mm=housing_dia_mm,
        housing_len_mm=housing_len_mm, emissivity=emissivity,
        t_housing_max_c=t_housing_max_c, q_chip_load_w=q_chip_load_w,
        t_static_c=T_static_K - 273.15, p_static_pa=p_Pa,
        velocity_m_s=velocity, t_recovery_c=T_r_K - 273.15,
        reynolds=Re, h_conv_w_per_m2_k=h, area_m2=A,
        q_conv_w=q_conv, q_rad_w=q_rad, q_out_total_w=q_out,
        margin_w=q_out - q_chip_load_w,
    )
