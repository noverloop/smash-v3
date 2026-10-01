"""FabTolerances — process-wide manufacturing tolerances."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class FabTolerances:
    """The factory's process tolerances. These are first-class: the
    stackup fitter carries a finished-thickness budget, the 3D-mesh
    builder propagates layer-elevation tolerance (RSS), and DRC checks
    derate against etch/registration. (See the RSS precedent in
    `layout/cavities.py`.)
    """
    finished_thickness_pct: float = 10.0    # overall board thickness ±%
    etch_trace_width_um: float = 25.0       # etched trace width ± (over/under-etch)
    registration_um: float = 50.0           # layer-to-layer misregistration
    drill_dia_um: float = 50.0              # drilled hole diameter ±
    true_position_um: float = 50.0          # drill true-position
    impedance_pct: float = 10.0             # controlled-Z ±%
    soldermask_registration_um: float = 50.0
    note: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FabTolerances":
        return cls(**d)
