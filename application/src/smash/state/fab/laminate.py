"""Laminate — one core/prepreg the fab stocks."""
from __future__ import annotations

import dataclasses

from smash.state.stackup.dielectric import Dielectric


@dataclasses.dataclass
class Laminate:
    """One dielectric the factory can build into a stackup — a stocked
    core or prepreg.

    `thickness_um` is the nominal pressed thickness; `thickness_tol_um`
    its ± tolerance (tolerances are tracked on every physical dimension
    so the stackup fitter can carry a thickness budget). `epsilon_r` /
    `loss_tangent` feed controlled-impedance + EM models. A `Laminate`
    is the *catalog* entry; `to_dielectric()` mints the `Dielectric`
    that actually lands in a `Board.stackup` (so the stackup model and
    the fab catalog stay one definition, not two).
    """
    material: str                       # "FR4", "RO4350B", "Oak-Mitsui HK04", ...
    kind: str                           # "core" | "prepreg"
    thickness_um: float                 # nominal pressed thickness
    thickness_tol_um: float = 0.0       # ± tolerance
    epsilon_r: float | None = None      # @ 1 GHz
    loss_tangent: float | None = None   # tan δ @ 1 GHz
    glass_style: str | None = None      # "1080", "2116", "3313", ...
    thermal_w_mk: float | None = None   # through-plane conductivity
    cte_ppm_k: float | None = None      # z-axis CTE
    # Mechanical constants (for the bend / structural sim)
    youngs_modulus_gpa: float | None = None
    poisson_ratio: float | None = None
    density_kg_m3: float | None = None
    note: str | None = None

    def to_dielectric(self) -> Dielectric:
        """Mint the `Dielectric` this laminate becomes in a stackup."""
        return Dielectric(material=self.material, thickness_um=self.thickness_um,
                          thickness_tol_um=self.thickness_tol_um,
                          epsilon_r=self.epsilon_r, loss_tangent=self.loss_tangent,
                          kind=self.kind,
                          youngs_modulus_gpa=self.youngs_modulus_gpa,
                          poisson_ratio=self.poisson_ratio,
                          density_kg_m3=self.density_kg_m3,
                          note=self.note)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Laminate":
        return cls(**d)
