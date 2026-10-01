"""Layer — one Cu layer in a Board stackup."""
from __future__ import annotations

import dataclasses

from smash.state.stackup.dielectric import Dielectric


@dataclasses.dataclass
class Layer:
    """One Cu layer in a board's stackup.

    `role` drives validators and routing — every layer must have a
    declared purpose:
      - "signal":             general signal layer (microstrip / stripline)
      - "power":              power-plane carrying one rail
      - "ground":             ground / return-current plane
      - "embedded_cap_power": part of an embedded-cap pair (PWR half)
      - "embedded_cap_gnd":   part of an embedded-cap pair (GND half)

    For power / embedded-cap layers, `rail` names the net carried
    (e.g. "COMP_1V35", "VDD_DDR"). For embedded-cap halves,
    `paired_with` is the name of the other half (e.g. "In2" pairs
    with "In1") — that pair plus the thin `dielectric_below`
    constitutes the embedded capacitance.
    """
    name: str                           # "F.Cu", "In1", ..., "B.Cu"
    index: int                          # 0 = top, N-1 = bottom
    role: str                           # see docstring
    thickness_um: float                 # Cu foil thickness (17.5 = 0.5 oz, 35 = 1 oz)
    thickness_tol_um: float = 0.0       # ± foil-thickness tolerance (Z budget)
    rail: str | None = None             # net name for power/gnd layers
    paired_with: str | None = None      # other half of an embedded-cap pair
    dielectric_below: Dielectric | None = None
                                        # the insulator separating this Cu
                                        # layer from the next one down
    note: str | None = None             # free-form catch-all

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        if self.dielectric_below is not None:
            d["dielectric_below"] = self.dielectric_below.to_dict()
        return d

