"""MillCapabilities — controlled-depth routing + side-cavity tolerances.

Most pool fabs run a depth-controlled router used for:

  * SEMI-FLEX outer-core removal (depth = full outer stack).
  * Pocket / cavity milling for embedded chip cavities, recessed
    connectors, attached-flex side cavities, etc.
  * Edge profiling / chamfering.

The DRC consults this when validating a milled feature (depth target,
side-wall geometry, position tolerance, exposed-pad cleanliness). The
attached-flex cavity work — where a flex tail is soldered to an inner
Cu layer exposed by a side cavity — depends on these values being
tighter than the rigid stackup's own thickness tolerance.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class MillCapabilities:
    """Controlled-depth routing envelope. Distances mm."""

    available: bool = False             # process offered at all
    depth_tol_mm: float = 0.05          # ± Z-depth tolerance (typical for
                                        # depth-controlled router on 14L
                                        # stack — Eurocircuits: ±0.05 mm)
    min_depth_mm: float | None = None   # min cavity depth (limited by
                                        # tool reach / outer layer
                                        # thickness)
    max_depth_mm: float | None = None   # max cavity depth (limited by
                                        # router tool length and rigidity)

    # ── tooling ────────────────────────────────────────────────────────
    min_tool_diameter_mm: float = 0.6   # smallest router endmill the fab
                                        # spins for depth-controlled mill;
                                        # sets the inside-corner radius
                                        # of any pocket
    tool_radius_mm: float | None = None # fillet at routed edges — typically
                                        # half of the smallest tool that
                                        # makes the depth cut

    # ── pocket / cavity geometry ──────────────────────────────────────
    min_pocket_wall_mm: float = 0.5     # FR4 wall thickness between a
                                        # pocket and the board outline /
                                        # another pocket
    min_pocket_floor_mm: float = 0.3    # remaining laminate below a
                                        # pocket floor (i.e. dielectric
                                        # between exposed Cu and the
                                        # next inner layer)
    min_pocket_opening_mm: float = 1.0  # smallest pocket width the fab
                                        # qualifies

    # ── side-opening cavity (for attached-flex) ────────────────────────
    side_cavity_supported: bool = False
    side_cavity_min_height_mm: float | None = None  # cavity Z-extent
    side_cavity_min_width_mm: float | None = None   # cavity X-extent
                                                    # along the board edge
    side_cavity_min_depth_mm: float | None = None   # how far the cavity
                                                    # extends INTO the
                                                    # board from the edge

    # ── exposed inner-layer pad cleanliness ────────────────────────────
    pad_oxide_protection: str | None = None  # "ENIG" / "OSP" / "HASL" —
                                             # finish applied to the
                                             # exposed inner pad surface
                                             # so it solders cleanly when
                                             # the cavity is opened
    pad_surface_roughness_um: float | None = None    # post-mill surface
                                                     # roughness of the
                                                     # exposed Cu

    # ── positioning ────────────────────────────────────────────────────
    position_tol_mm: float = 0.05       # XY position of the cavity vs the
                                        # board outline (sets how
                                        # confidently the assembled flex
                                        # lands on its pads)

    note: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MillCapabilities":
        return cls(**d)
