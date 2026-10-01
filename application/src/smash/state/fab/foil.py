"""CopperFoil — one copper weight the fab stocks."""
from __future__ import annotations

import dataclasses


# Foil weight (oz) → base copper thickness (µm). 1 oz ≈ 35 µm.
OZ_TO_UM = {0.5: 17.5, 1.0: 35.0, 2.0: 70.0, 3.0: 105.0}


@dataclasses.dataclass
class CopperFoil:
    """One copper foil option.

    `thickness_um` is the base foil; `plated_thickness_um` the finished
    thickness after plating (outer layers gain ~25 µm of plating, inners
    don't). `placement` constrains where the weight is usable.

    The RF block tracks the "special copper" substrate-integrated
    waveguides (and any mmWave routing on the radar's Rogers layers)
    need. SIW conductor loss is dominated by **foil surface roughness**
    — a tooth profile comparable to the skin depth (~0.3 µm at 60 GHz)
    wrecks insertion loss — so a SIW-grade stack calls for low-profile
    foil:

      - `foil_type`: PROCESS class — different copper sheets, NOT just a
        finish:
          * "ED"  — standard electro-deposited (plated onto a drum):
                    columnar grains, higher strength, **lower ductility**
                    (RT elongation ~5-15%, thin foil at the low end).
          * "HTE" — high-temperature-elongation ED (IPC-4562 Grade 3):
                    ductilised ED, better elongation hot.
          * "RA"  — rolled-annealed / wrought (Type W): rolled then
                    annealed → equiaxed grains, **high ductility** (RT
                    elongation ~15-25%); the flex/bend-endurance sheet.
          * "VLP"/"HVLP" — very-/hyper-very-low-profile ED (a low-
                    roughness ED for RF loss; a *roughness* class).
          * "RTF" — reverse-treated ED foil: the tooth-side treatment is
                    reversed for a low-profile bond side. Also a
                    *roughness/RF* class — NOT a ductility upgrade (it is
                    still ED copper).
        So ductility tracks ED → HTE → RA; roughness tracks ED → RTF →
        VLP → HVLP. `is_low_profile` flags the roughness classes.
      - `roughness_rz_um`: foil tooth-side roughness (Rz). The loss
        driver; lower is better at mmWave.
      - `conductivity_s_m`: bulk σ (≈ 5.8e7 for Cu), feeds the EM solver.
      - `elongation_pct`: RT elongation-at-break (%). The ductility that
        sets how much bend / crack-bridging strain a routed trace
        survives before it fractures (see `smash.sim.fea.trace_strain`).
        ED ≈ 5-15 %, HTE ≈ 10-20 %, RA ≈ 15-25 %.
      - `min_processed_thickness_um`: NCAB Stackups guide — the minimum
        copper thickness an INNER foil is left with after processing
        (18→11.4, 35→24.9, 70→55.7 µm). The worst-case `t` for any
        thickness-driven mechanical check (free-span bending ∝ 1/t).
    """
    weight_oz: float                    # 0.5, 1.0, 2.0, ...
    thickness_um: float                 # base foil thickness
    plated_thickness_um: float | None = None  # finished (outer, after plating)
    thickness_tol_um: float = 0.0       # ± tolerance
    placement: str = "any"              # "inner" | "outer" | "any"
    # ── RF / SIW "special copper" ───────────────────────────────────
    foil_type: str | None = None        # "ED"|"HTE"|"RA"|"VLP"|"HVLP"|"RTF"
    roughness_rz_um: float | None = None  # tooth-side roughness (Rz)
    conductivity_s_m: float | None = None  # bulk σ (≈ 5.8e7 for Cu)
    # Mechanical constants (annealed Cu: ~117 GPa, ν 0.34, ρ 8960)
    youngs_modulus_gpa: float | None = None
    poisson_ratio: float | None = None
    density_kg_m3: float | None = None
    elongation_pct: float | None = None   # RT elongation-at-break (ductility)
    min_processed_thickness_um: float | None = None  # NCAB inner min after proc.
    note: str | None = None

    @property
    def finished_um(self) -> float:
        """Plated thickness if set, else the base foil."""
        return self.plated_thickness_um or self.thickness_um

    @property
    def is_low_profile(self) -> bool:
        """True for the low-roughness RF foils (VLP/HVLP/RTF). NOTE this
        is a *roughness* class, independent of ductility — an RTF foil is
        still ED copper, not a rolled-annealed (RA) ductile sheet."""
        return (self.foil_type or "").upper() in ("VLP", "HVLP", "RTF")

    @property
    def is_ductile(self) -> bool:
        """True for the high-elongation sheets (rolled-annealed / HTE) —
        the ones chosen for bend / flex / shock-strain endurance."""
        return (self.foil_type or "").upper() in ("RA", "HTE")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CopperFoil":
        return cls(**d)
