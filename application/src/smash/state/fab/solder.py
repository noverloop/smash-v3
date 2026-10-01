"""Solder — one solder alloy the assembly line can run."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Solder:
    """One solder alloy. Constants feed both physics domains the joints
    matter for: thermal (κ at the die→board path) and structural (the
    bend/setback solder-joint shear check).

    `shear_strength_mpa` + `youngs_modulus_gpa` drive the joint-failure
    model; `cte_ppm_k` the thermal-cycling fatigue; `melting_c` (liquidus)
    flags reflow-profile / step-soldering compatibility.
    """
    name: str                           # "SAC305", "Sn63Pb37", "SnBi57"
    alloy: str | None = None            # composition, e.g. "Sn96.5Ag3.0Cu0.5"
    leaded: bool = False
    melting_c: float | None = None      # liquidus
    thermal_w_mk: float | None = None
    cte_ppm_k: float | None = None
    youngs_modulus_gpa: float | None = None
    poisson_ratio: float | None = None  # bulk Poisson's ratio (~0.40 for SAC305,
                                         # ~0.42 for Sn63Pb37). Used by the bend
                                         # sim to derive shear modulus G = E / (2(1+ν)).
    shear_strength_mpa: float | None = None
    tensile_strength_mpa: float | None = None   # effective corner-ball pull-off
                                                 # tensile strength (bulk SAC305
                                                 # ~50 MPa; ball-pad geometry +
                                                 # stress concentrators debit to
                                                 # ~35 MPa effective). Used by
                                                 # the bend-sim reverse-setback
                                                 # and impact paths.
    density_g_cm3: float | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Solder":
        return cls(**d)
