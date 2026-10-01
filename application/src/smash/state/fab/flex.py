"""FlexCapabilities — what flex / semi-flex / rigid-flex this fab offers.

The DRC + the panel-layout machinery query this when deciding whether
a proposed flex topology (snake-link gap, branch length, layer count
in the bend region, cavity attach geometry) fits the fab's published
envelope.

Different fabs ship very different flex envelopes:

  * Eurocircuits SEMI-FLEX pool: milled-FR4 flex, R_min = 5 mm,
    2 Cu layers in the bend, 4 or 6 rigid layers.
  * Eurocircuits Flex pool: standalone polyimide flex, R_min ≈ 0.3 mm,
    1-4 Cu layers, no rigid.
  * True rigid-flex (Würth, Multi-CB, etc.): polyimide flex laminated
    INTO the rigid stack, R_min ≈ 2-3 mm, up to ~14 rigid + 2-4 flex
    layers.

This dataclass is intentionally tech-neutral so the same DRC code path
checks any of them — the fab profile picks the values that match its
process. Set unsupported attributes to `None` (e.g. a no-flex fab
sets `flex_layers_in_bend = None`).
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class FlexCapabilities:
    """Per-process flex envelope. All distances mm, all tolerances mm."""

    # ── what the process is called by the fab ───────────────────────────
    process_name: str = "none"          # "SEMI-FLEX", "Flex", "Rigid-Flex",
                                        # "attached-flex"

    # ── bend mechanics ──────────────────────────────────────────────────
    R_min_mm: float | None = None       # minimum bend radius (one-time / static)
    R_min_dynamic_mm: float | None = None  # dynamic fold rating (None if
                                        # static-only, e.g. SEMI-FLEX)
    max_bend_cycles: int | None = None  # max number of 180° folds the flex
                                        # zone can take in its lifetime
                                        # (Eurocircuits SEMI-FLEX: 5;
                                        # polyimide static: 1-3; polyimide
                                        # dynamic: ~ 10⁶+)
    max_bend_angle_deg: float = 180.0   # most flex processes fold to 180°

    # ── flex-zone geometry ──────────────────────────────────────────────
    residual_thickness_mm: float | None = None      # what survives the rout
    residual_thickness_tol_mm: float | None = None  # ± depth tolerance
    cu_layers_in_bend: int | None = None    # how many Cu layers survive
                                            # the rout (2 for SEMI-FLEX, N
                                            # for polyimide where N matches
                                            # the flex stack)
    min_flex_length_mm: float | None = None         # min manufacturable
                                                    # flex-zone length
    recommended_flex_length_mm: float | None = None
    min_flex_width_mm: float | None = None
    min_strain_relief_mm: float = 0.0       # straight flex required PAST
                                            # the rigid edge before the
                                            # bend can start (SEMI-FLEX:
                                            # 1.5; attached polyimide:
                                            # ~ 0 because the discontinuity
                                            # is a soldered joint, not a
                                            # laminated bondline)

    # ── conductors inside the bend ─────────────────────────────────────
    min_trace_in_bend_mm: float | None = None    # often relaxed vs rigid
    min_space_in_bend_mm: float | None = None
    cu_foil_type: str | None = None             # "ED", "RA", "HDC"
                                                # (rolled-annealed and
                                                # high-ductility Cu survive
                                                # tighter bends; standard
                                                # ED cracks earlier)

    # ── forbidden features inside the bend zone ─────────────────────────
    allow_pth_in_bend: bool = False     # plated through holes
    allow_via_in_bend: bool = False     # vias (any kind)
    allow_pad_in_bend: bool = False     # SMD lands
    require_balanced_copper: bool = True    # asymmetric Cu → flex curls

    # ── number of layers in the RIGID region ────────────────────────────
    rigid_min_layers: int | None = None
    rigid_max_layers: int | None = None

    note: str | None = None

    # ── helper: minimum flex-zone length for one 180° fold ──────────────

    def min_zone_length_180(self, *, R_mm: float | None = None) -> float | None:
        """Length needed for ONE 180° fold at radius `R_mm` (or `R_min`
        if not specified). Returns None if the process is no-flex."""
        if self.R_min_mm is None:
            return None
        import math
        R = R_mm if R_mm is not None else self.R_min_mm
        arc = math.pi * R
        return arc + 2 * self.min_strain_relief_mm

    # ── helper: required tile pitch for a snake link ────────────────────

    def min_tile_pitch_mm(self, tile_diameter_mm: float,
                          *, R_mm: float | None = None) -> float | None:
        """Centre-to-centre pitch needed for two adjacent rigid tiles
        whose snake-link flex makes one 180° fold. Returns None if the
        process is no-flex."""
        zone = self.min_zone_length_180(R_mm=R_mm)
        return None if zone is None else tile_diameter_mm + zone

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FlexCapabilities":
        return cls(**d)
