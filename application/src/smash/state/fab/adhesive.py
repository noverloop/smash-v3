"""Adhesive — an underfill / encapsulant / staking compound."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Adhesive:
    """A polymer the assembly bonds in — chiefly capillary/molded
    underfill under BGAs/CSPs, but also board-level encapsulant (the
    vacuum-potting Stycast) and staking adhesive.

    Constants feed the structural mesh (underfill stiffens the solder
    joints under setback — `youngs_modulus_gpa`, `cte_ppm_k`) and the
    thermal mesh (`thermal_w_mk`). `tg_c` is the glass transition (CTE
    jumps above Tg); `filler_pct` the inorganic loading.
    """
    name: str                           # "Loctite Eccobond UF1173", "Stycast 2651MM"
    role: str = "underfill"             # "underfill" | "encapsulant" | "staking"
    thermal_w_mk: float | None = None
    cte_ppm_k: float | None = None      # below Tg
    cte_above_tg_ppm_k: float | None = None
    youngs_modulus_gpa: float | None = None
    poisson_ratio: float | None = None  # bulk Poisson's ratio (filled epoxies
                                         # ~0.30; un-/lightly-filled epoxies
                                         # ~0.34; bridge-resin Stycast ~0.34).
                                         # Used by the bend / FEA elastic cards.
    tg_c: float | None = None           # glass transition
    filler_pct: float | None = None
    density_g_cm3: float | None = None
    # Uncured viscosity (mPa·s = cP at 25 °C). Matters operationally:
    # capillary underfill needs ≲10 000 cP to flow under a BGA; vacuum-
    # potting needs the mixed compound thin enough to fill voids
    # (Stycast 2651MM uses a low-viscosity catalyst variant to drop
    # mixed viscosity well below the 35 000 cP of the resin alone).
    viscosity_cps: float | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Adhesive":
        return cls(**d)
