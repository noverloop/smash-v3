"""BoardGeometry — outline + holes + keepouts for one board.

A single value object that replaces the three separate `Board` fields
(diameter_mm, rect_dimensions, outline_dxf). Loaded from
`data/board_geometries.json` via `load_board_geometry(name)`; can also
be built inline.

Flex cutouts are not stored here at construction time — they're a
panel-level fact (which neighbour, which direction, what chord). The
panel build pass fills `flex_cutouts` once the panel topology is known,
and downstream consumers call `outline_polygon()` to get the final
shape with cutouts applied.
"""
from __future__ import annotations

import dataclasses
import functools
import json
import math
import pathlib

# Default polygon segmentation for circular outlines. 64 segments
# matches what tools/layout_gen/placer.py uses for tile circles.
_DEFAULT_CIRCLE_SEGMENTS = 64

from smash.layout.cavities import (
    POTTING_HOLE_DIA_MM,
    POTTING_HOLE_RADIUS_MM,
    potting_hole_positions_math_yup,
)


# Half-side of the placement-keepout square around a potting hole.
# Grew with the hole: was 1.5 (3×3 square, +0.5 mm buffer beyond a
# Ø2 hole); now 2.0 (4×4 square) to maintain the same 0.5 mm buffer
# beyond a Ø3 hole. Originally lifted from
# tools/layout_gen/placer.py:2229.
POTTING_HOLE_KEEPOUT_HALF_MM = 2.0


# ── value objects ─────────────────────────────────────────────────────

@dataclasses.dataclass
class Hole:
    """One drilled hole through the board."""
    position_mm: tuple                 # (x, y) board-local, math y-up
    diameter_mm: float
    plated: bool = False               # PTH vs NPTH
    tag: str | None = None             # "potting" | "mount" | ...
    note: str | None = None

    def to_dict(self) -> dict:
        return {
            "position_mm": list(self.position_mm),
            "diameter_mm": self.diameter_mm,
            "plated":      self.plated,
            "tag":         self.tag,
            "note":        self.note,
        }


@dataclasses.dataclass
class Keepout:
    """A region where the named scope is forbidden."""
    polygon: list                      # list[(x, y)] board-local, math y-up
    layers: tuple = ("*.Cu",)          # which Cu layers it applies to
    scope: str = "component"           # "component" | "routing" | "both"
    tag: str | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        return {
            "polygon": [list(p) for p in self.polygon],
            "layers":  list(self.layers),
            "scope":   self.scope,
            "tag":     self.tag,
            "note":    self.note,
        }


@dataclasses.dataclass
class BoardGeometry:
    """Outline + holes + keepouts for one board.

    `shape` selects which outline parameter is authoritative:
      - "circle" → diameter_mm
      - "rect"   → rect_dimensions
      - "dxf"    → dxf_path
    """
    shape: str
    diameter_mm: float | None = None
    rect_dimensions: tuple | None = None        # (w, h)
    dxf_path: pathlib.Path | None = None

    holes:    list = dataclasses.field(default_factory=list)  # list[Hole]
    keepouts: list = dataclasses.field(default_factory=list)  # list[Keepout]

    # Populated at panel-build time once edge directions are known;
    # consumers ask `outline_polygon()` to get the base shape with
    # these chord cutouts subtracted.
    flex_cutouts: list = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "shape":           self.shape,
            "diameter_mm":     self.diameter_mm,
            "rect_dimensions": list(self.rect_dimensions)
                               if self.rect_dimensions else None,
            "dxf_path":        str(self.dxf_path) if self.dxf_path else None,
            "holes":           [h.to_dict() for h in self.holes],
            "keepouts":        [k.to_dict() for k in self.keepouts],
            # flex_cutouts intentionally omitted — panel-build artifact,
            # not a definition.
        }

    # ── derived: outline ──────────────────────────────────────────────

    @property
    def outline_radius_mm(self) -> float | None:
        """Bounding radius of the base outline (no cutouts).

        - circle: diameter_mm / 2
        - rect:   half-diagonal of rect_dimensions
        - dxf:    None (not yet supported — see TODO)

        Used by the packer's fast path on circular tiles.
        """
        if self.shape == "circle" and self.diameter_mm is not None:
            return self.diameter_mm / 2.0
        if self.shape == "rect" and self.rect_dimensions is not None:
            w, h = self.rect_dimensions
            return math.hypot(w / 2.0, h / 2.0)
        return None

    def outline_polygon(
        self, *, segments: int = _DEFAULT_CIRCLE_SEGMENTS
    ) -> list:
        """Base outline as a list of (x, y) points (board-local, math
        y-up). Does NOT subtract flex_cutouts — that's a future hook
        once the panel-build pass populates them.

        - circle: `segments`-point polygon
        - rect:   4 corners CCW
        - dxf:    NotImplementedError (postponed; no DXF boards yet)
        """
        if self.shape == "circle":
            if self.diameter_mm is None:
                raise ValueError("circle geometry missing diameter_mm")
            r = self.diameter_mm / 2.0
            return [
                (r * math.cos(2 * math.pi * i / segments),
                 r * math.sin(2 * math.pi * i / segments))
                for i in range(segments)
            ]
        if self.shape == "rect":
            if self.rect_dimensions is None:
                raise ValueError("rect geometry missing rect_dimensions")
            w, h = self.rect_dimensions
            hx, hy = w / 2.0, h / 2.0
            return [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
        if self.shape == "dxf":
            raise NotImplementedError(
                "DXF outline polygonization not yet implemented — "
                "no boards currently use shape='dxf' (activation_interface "
                "was migrated to circle in P0.8)"
            )
        raise ValueError(f"unknown geometry shape: {self.shape!r}")


# ── JSON-backed factory ───────────────────────────────────────────────

_DATA_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "data" / "board_geometries.json"
)


@functools.lru_cache(maxsize=1)
def _load_registry() -> dict:
    with _DATA_PATH.open() as f:
        return json.load(f)


def _synth_potting_holes() -> tuple[list, list]:
    """NPTH potting holes + their placement-keepout squares: two holes at
    NW (135°) + SE (315°), 14 mm radial.

    Rigid tiles carry this pair. Spacers do NOT use a fixed pattern — the
    accordion fold mirrors a spacer relative to its neighbours, so a fixed
    pair lands on the wrong diagonal. attach_cavities_to_spacers() instead
    drills each spacer's holes at the fold-projected neighbour positions."""
    holes: list = []
    keepouts: list = []
    h = POTTING_HOLE_KEEPOUT_HALF_MM
    positions = potting_hole_positions_math_yup()
    for (x, y) in positions:
        holes.append(Hole(
            position_mm=(x, y),
            diameter_mm=POTTING_HOLE_DIA_MM,
            plated=False,
            tag="potting",
        ))
        keepouts.append(Keepout(
            polygon=[(x - h, y - h), (x + h, y - h),
                     (x + h, y + h), (x - h, y + h)],
            scope="component",
            tag="potting_hole",
        ))
    return holes, keepouts


def _from_entry(entry: dict) -> BoardGeometry:
    shape = entry["shape"]
    geom = BoardGeometry(
        shape=shape,
        diameter_mm=entry.get("diameter_mm"),
        rect_dimensions=tuple(entry["rect_dimensions"])
                        if entry.get("rect_dimensions") else None,
        dxf_path=pathlib.Path(entry["dxf_path"])
                 if entry.get("dxf_path") else None,
    )
    if entry.get("potting_holes"):
        holes, keepouts = _synth_potting_holes()
        geom.holes.extend(holes)
        geom.keepouts.extend(keepouts)
    return geom


def load_board_geometry(name: str) -> BoardGeometry:
    """Look up a board's geometry by board name.

    Names starting with `spacer_` not in the explicit registry fall
    back to the `_spacer_default` template — spacers all share Ø34 +
    potting holes. Any other unknown name raises `KeyError`.
    """
    reg = _load_registry()
    boards = reg["boards"]
    if name in boards:
        return _from_entry(boards[name])
    if name.startswith("spacer_") and "_spacer_default" in reg:
        return _from_entry(reg["_spacer_default"])
    raise KeyError(
        f"no board_geometries.json entry for {name!r} (and not a spacer_*)"
    )


def all_known_names() -> list[str]:
    """Every explicit name in the registry. Excludes the `_spacer_default`
    template. Useful for tests + tooling."""
    return list(_load_registry()["boards"].keys())
