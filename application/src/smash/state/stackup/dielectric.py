"""Dielectric — one insulating layer between two Cu layers."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Dielectric:
    """One insulating layer between two Cu layers in the stackup.

    Material + thickness + dielectric constant feed:
      - controlled-impedance routing (Z₀ depends on εr and thickness)
      - embedded-cap calculations (C per unit area = ε₀·εr / d)
      - FEM thermal / stress models
    Transcribe ε_r and tanδ from the laminate datasheet (FR4 grade,
    Rogers RO4350B, FaradFlex / Oak-Mitsui HK04, etc.).
    """
    material: str                       # "FR4", "RO4350B 5mil", "Oak-Mitsui HK04", "Stycast 1266"
    thickness_um: float                 # core / prepreg thickness in microns
    thickness_tol_um: float = 0.0       # ± pressed-thickness tolerance (Z budget)
    epsilon_r: float | None = None      # dielectric constant @ 1 GHz
    loss_tangent: float | None = None   # tan δ @ 1 GHz
    kind: str | None = None             # "core" | "prepreg" (lamination type)
    # Mechanical constants (for the bend / structural sim)
    youngs_modulus_gpa: float | None = None
    poisson_ratio: float | None = None
    density_kg_m3: float | None = None
    note: str | None = None             # free-form catch-all

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

