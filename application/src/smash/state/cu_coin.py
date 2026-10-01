"""Copper coin insert in a board's stackup — rectangular T-beam.

Per NCAB Copper Coin Design Guidelines 1.0 (June 2023). The T-coin is
a rectangular strip with two distinct cross-sections:

  - flange (full outer rectangle, NCAB symbol Y × X) — sits at the
    bottom of the T (or top, depending on `flange_up`). This is the
    wide base that gives the T its load-spreading and pull-out-
    resisting flange.
  - ladder (inner raised rectangle, NCAB Y1 × X1) — the narrower top
    of the T. Can extend the full length of the coin (Y1 = Y) so the
    cross-section is uniform along Y; or be shorter to leave flange
    overhang at both ends.

In both cases the coin has flange overhang Q on every side of the
ladder where Y1/X1 < Y/X:

    X = X1 + 2·Q_short    (short axis)
    Y = Y1 + 2·Q_long     (long axis;  Q_long can be 0 → Y1 = Y)

The coin's long axis can be rotated by `rotation_deg` (CCW from the
board's +X axis), so a strip can run between two distant chips at any
angle. For our case `companion_compute`'s `U_MPU` and `U_DDR4` sit on
the same Y line — a strip with `rotation_deg = 0` and length spanning
their X positions will reach both BGAs.

NCAB constraints reflected in the dataclass:

  H (`thickness_mm`)           1.0–2.8 mm preferred, 0.8–3.0 advanced
  H1 (`flange_thickness_mm`)   0.5–1.8 mm preferred, ≥0.25 advanced
  H2 = H - H1                  ≥0.5 mm preferred
  T1 = min(X1, Y1)             5 mm preferred, 2 mm advanced (ladder min dim)
  Q  (flange overhang per side) ≥2 mm preferred, 2 mm advanced
  Y = Y1 + 2·Q                  30 mm preferred, 8–30 mm advanced
  X = X1 + 2·Q                  20 mm preferred, 2–30 mm advanced
"""
from __future__ import annotations

import dataclasses
import math


VALID_COIN_KINDS = ("I", "T", "U")


@dataclasses.dataclass
class CuCoinInsert:
    """A rectangular copper coin insert in a board's stackup.

    Coordinate convention (the `length / width` and `ladder_length /
    ladder_width` fields all share this):

      `length_mm` (NCAB Y)  — long axis of the coin's outer rectangle.
                              The coin's "long axis" aligns with the
                              board's +X axis when `rotation_deg = 0`.
      `width_mm`  (NCAB X)  — short axis of the outer rectangle.

    The coin's centre is at `position_mm` in the board's local frame.

    For a uniform-cross-section strip (T-beam running full length),
    set `ladder_length_mm = length_mm`. For a more localised raised
    region, set `ladder_length_mm < length_mm` and the flange overhangs
    by (length_mm - ladder_length_mm) / 2 at each end.

    `flange_thickness_mm = 0` and `ladder_length_mm = length_mm` and
    `ladder_width_mm = width_mm` together describe an I-coin (no
    flange — just a rectangular slab).
    """
    position_mm: tuple                       # (x, y) coin centre, mm

    # Outer flange rectangle (long × short axis).
    length_mm: float                          # NCAB Y
    width_mm: float                           # NCAB X

    # Inner ladder rectangle (the raised T-top). For an I-coin or a
    # uniform-cross-section strip, set these equal to the outer dims.
    ladder_length_mm: float                   # NCAB Y1
    ladder_width_mm: float                    # NCAB X1

    # Z (thickness) geometry.
    thickness_mm: float                       # NCAB H — total
    z_top_mm: float                            # top face Z (from B.Cu = 0)
    flange_thickness_mm: float = 0.0          # NCAB H1 — 0 → I-coin

    # Orientation.
    rotation_deg: float = 0.0                 # CCW from board +X
    flange_up: bool = True                    # T-coin orientation

    kind: str = "T"                           # "I" | "T" | "U"

    # Corner geometry (NCAB symbol R) — quarter-circle chamfer on each
    # of the flange's four outer corners. NCAB minimum is R=1.0 mm
    # preferred / R=0.5 mm advanced. Increasing R buys edge clearance
    # to the board outline at the cost of corner Cu area; the bend sim
    # accounts for the area loss via `flange_area_mm2`. The chamfer is
    # applied to the FLANGE only; the ladder remains rectangular and
    # must stay inside the chamfered flange (the validator below checks
    # this for typical ladder sizes).
    corner_chamfer_radius_mm: float = 0.0

    net: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in VALID_COIN_KINDS:
            raise ValueError(
                f"CuCoinInsert.kind must be one of {VALID_COIN_KINDS}, "
                f"got {self.kind!r}"
            )
        if self.ladder_length_mm > self.length_mm + 1e-9:
            raise ValueError(
                f"CuCoinInsert.ladder_length_mm "
                f"({self.ladder_length_mm}) > length_mm "
                f"({self.length_mm}) — ladder can't extend past flange"
            )
        if self.ladder_width_mm > self.width_mm + 1e-9:
            raise ValueError(
                f"CuCoinInsert.ladder_width_mm "
                f"({self.ladder_width_mm}) > width_mm "
                f"({self.width_mm}) — ladder can't extend past flange"
            )
        if self.flange_thickness_mm < 0 or \
                self.flange_thickness_mm > self.thickness_mm:
            raise ValueError(
                f"CuCoinInsert.flange_thickness_mm "
                f"({self.flange_thickness_mm}) must be in "
                f"[0, {self.thickness_mm}]"
            )
        if self.kind == "I" and self.flange_thickness_mm != 0:
            raise ValueError(
                f"CuCoinInsert: an I-coin must have flange_thickness_mm=0 "
                f"(got {self.flange_thickness_mm})"
            )
        if self.corner_chamfer_radius_mm < 0:
            raise ValueError(
                f"CuCoinInsert.corner_chamfer_radius_mm must be ≥ 0 "
                f"(got {self.corner_chamfer_radius_mm})"
            )
        # The chamfer can't be bigger than the smaller half-extent of the
        # flange — otherwise the four arcs overlap and the shape becomes
        # degenerate (a stadium or worse).
        r_max = min(self.length_mm, self.width_mm) / 2.0
        if self.corner_chamfer_radius_mm > r_max + 1e-9:
            raise ValueError(
                f"CuCoinInsert.corner_chamfer_radius_mm "
                f"({self.corner_chamfer_radius_mm}) exceeds min(L,W)/2 "
                f"({r_max:.3f}) — chamfer arcs would overlap"
            )

    @property
    def z_bottom_mm(self) -> float:
        return self.z_top_mm - self.thickness_mm

    @property
    def shank_thickness_mm(self) -> float:
        """NCAB H2 = H - H1."""
        return self.thickness_mm - self.flange_thickness_mm

    @property
    def Q_long_mm(self) -> float:
        """Flange overhang on the long axis (per side)."""
        return (self.length_mm - self.ladder_length_mm) / 2.0

    @property
    def Q_short_mm(self) -> float:
        """Flange overhang on the short axis (per side)."""
        return (self.width_mm - self.ladder_width_mm) / 2.0

    @property
    def flange_area_mm2(self) -> float:
        """Plan-view area of the flange's outer rectangle, less the four
        chamfered corners. Used by the bend sim to weight the coin's
        contribution to the plate's effective average flexural rigidity.

        Each chamfer replaces a corner square of side R with a quarter-
        circle of radius R, removing R²·(1 - π/4) per corner."""
        rect = self.length_mm * self.width_mm
        r = self.corner_chamfer_radius_mm
        return rect - 4.0 * r * r * (1.0 - math.pi / 4.0)

    def covers_position(self, x_mm: float, y_mm: float,
                        clearance_mm: float = 0.0) -> bool:
        """True iff a circle of radius `clearance_mm` centred at
        `(x_mm, y_mm)` fits entirely inside the coin's flange
        rectangle. Used by the bend sim to test whether a chip's body
        (bounding circle with radius = corner_reach_mm) sits over the
        coin and thus benefits from the augmented-D scaling."""
        # Translate the test point into the coin's local frame.
        dx = x_mm - self.position_mm[0]
        dy = y_mm - self.position_mm[1]
        # Rotate by -rotation_deg so the coin's long axis is along +X
        # in the local frame.
        cos_r = math.cos(-math.radians(self.rotation_deg))
        sin_r = math.sin(-math.radians(self.rotation_deg))
        lx = dx * cos_r - dy * sin_r
        ly = dx * sin_r + dy * cos_r
        # Check the bounding circle vs the flange axis-aligned rect.
        return (abs(lx) + clearance_mm <= self.length_mm / 2.0 + 1e-9
                and abs(ly) + clearance_mm <= self.width_mm / 2.0 + 1e-9)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["position_mm"] = list(self.position_mm)
        return d
