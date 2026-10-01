"""MetalInsert — a metal backing / core / coin the fab can bond in."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class MetalInsert:
    """A non-copper metal body bonded into or onto a board — the
    generalization of the old `Board.al_backing_mm` float.

    `role` distinguishes:
      - "backing": a plate bonded under the board (thermal spreader /
                   structural stiffener — the current Al backing)
      - "core":    a metal core the dielectric layers build out from
                   (metal-core PCB)
      - "coin":    a localized metal slug pressed in under a hot die

    `thermal_w_mk` is what the thermal mesh needs; `thickness_mm` +
    `thickness_tol_mm` carry the mechanical/Z budget.
    """
    material: str                       # "aluminium" | "copper" | "titanium" | ...
    role: str                           # "backing" | "core" | "coin"
    thickness_mm: float
    thickness_tol_mm: float = 0.0       # ± tolerance
    thermal_w_mk: float | None = None   # in-plane conductivity
    cte_ppm_k: float | None = None
    # Structural constants (Al 6061 ≈ 70/0.33/2700/270 MPa, Ti 6-4 ≈
    # 114/0.34/4430/880, Cu ≈ 117/0.34/8960, SS 304 ≈ 200/0.28/8000/215)
    youngs_modulus_gpa: float | None = None
    poisson_ratio: float | None = None
    density_kg_m3: float | None = None
    yield_strength_mpa: float | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MetalInsert":
        return cls(**d)
