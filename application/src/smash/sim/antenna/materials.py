"""Material constants for the sleeve-antenna FDTD model.

⚠ Every dielectric value here is an ASSUMPTION (typical datasheet class
values), not a measurement of the parts we will build with. Replace them
with the chosen grades' datasheet values at 2 GHz (or with measurements)
before trusting absolute efficiency numbers — resonant frequency shifts
mostly with εr, efficiency mostly with tanδ.
"""
from __future__ import annotations

import dataclasses
import math

EPS0 = 8.8541878128e-12


@dataclasses.dataclass(frozen=True)
class Dielectric:
    name: str
    eps_r: float
    tan_d: float
    assumption: str = ""

    def kappa(self, f_hz: float) -> float:
        """Equivalent conductivity [S/m] that gives `tan_d` at `f_hz`
        (openEMS models dielectric loss as a conductivity)."""
        return 2.0 * math.pi * f_hz * EPS0 * self.eps_r * self.tan_d


AIR = Dielectric("air", 1.0, 0.0)
LDS_LCP = Dielectric("lds_lcp", 3.5, 0.005,
                     "LDS-grade glass-filled LCP, typical class value — confirm grade")
POTTING_BLACK = Dielectric("potting_black", 3.5, 0.02,
                           "black filled epoxy (Stycast 2651MM class) — RF loss unknown, "
                           "0.02 is a pessimistic guess")
POTTING_RF = Dielectric("potting_rf", 3.0, 0.005,
                        "unfilled / RF-grade epoxy potting — typical class value")
FR4 = Dielectric("fr4", 4.3, 0.017, "standard FR-4 laminate")
PEEK = Dielectric("peek", 3.2, 0.004, "unfilled PEEK")
COMPOSITE = Dielectric("composite", 4.0, 0.01,
                       "glass-fibre composite battery holder — typical class value")
COATING_PTFE = Dielectric("coating_ptfe", 2.1, 0.0005,
                          "PTFE-based low-loss outer coating")

# Conductors. The FDTD model treats every conductor as PEC; LDS copper
# (electroless + electroplated) is ~3e7 S/m vs 5.8e7 bulk — its loss is a
# second-order term next to the potting tanδ at these thicknesses.
LDS_COPPER_SIGMA = 3.0e7

ALL = {m.name: m for m in (AIR, LDS_LCP, POTTING_BLACK, POTTING_RF, FR4, PEEK,
                           COMPOSITE, COATING_PTFE)}
