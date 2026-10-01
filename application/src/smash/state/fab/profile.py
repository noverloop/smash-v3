"""FabProfile — a factory's full set of capabilities + constraints."""
from __future__ import annotations

import dataclasses

from smash.state.issue import Issue
from smash.state.fab.laminate import Laminate
from smash.state.fab.foil import CopperFoil
from smash.state.fab.metal import MetalInsert
from smash.state.fab.tolerances import FabTolerances
from smash.state.fab.rules import DesignRules
from smash.state.fab.solder import Solder
from smash.state.fab.adhesive import Adhesive
from smash.state.fab.flex import FlexCapabilities
from smash.state.fab.milling import MillCapabilities


# Solder processes that let an assembly carry a SECOND alloy beyond the
# board-wide reflow paste (selective/wave/hand for THT + connectors,
# step for staged-melt reflow).
_MULTI_ALLOY_PROCESSES = {"selective", "wave", "hand", "step"}


@dataclasses.dataclass
class FabProfile:
    """Everything the factory can build, and the limits it imposes — the
    single authority the stackup fitter, 3D-mesh builder, and DRC all
    constrain against ("our limit is the factory, not ourselves").

    Carries the laminate + foil + metal-insert catalog (a mix of
    materials supports hybrid stackups), the DRC `rules`, and the
    process `tolerances`. Query methods (`cores`, `nearest_dielectric`,
    `combine_to_thickness`) are the hooks the stackup fitter will use;
    `check_*` methods are the DRC surface used by `validators/fab.py`.
    """
    name: str
    vendor: str | None = None
    process: str | None = None
    laminates: list = dataclasses.field(default_factory=list)      # list[Laminate]
    foils: list = dataclasses.field(default_factory=list)          # list[CopperFoil]
    metal_options: list = dataclasses.field(default_factory=list)  # list[MetalInsert]
    # ── assembly materials ──────────────────────────────────────────
    solders: list = dataclasses.field(default_factory=list)        # list[Solder]
    adhesives: list = dataclasses.field(default_factory=list)      # list[Adhesive]
    # Solder processes this house runs. "reflow" alone ⇒ one board-wide
    # alloy; selective/wave/hand/step add the capability to carry a
    # second alloy (THT/connectors/step-melt). Tracked as a capability —
    # solder is assigned board-wide (`Board.solder`), not per chip.
    solder_processes: list = dataclasses.field(
        default_factory=lambda: ["reflow"])
    rules: DesignRules = dataclasses.field(default_factory=DesignRules)
    tolerances: FabTolerances = dataclasses.field(default_factory=FabTolerances)
    # Per-process flex envelope (snake-link gap, R_min, layer count in
    # the bend, etc.). Defaults to "no flex offered" — explicit fabs
    # set their published numbers.
    flex: FlexCapabilities = dataclasses.field(default_factory=FlexCapabilities)
    # Controlled-depth routing + side-cavity tolerances. Used by the
    # attached-flex cavity placer + the embedded-cavity DRC.
    milling: MillCapabilities = dataclasses.field(default_factory=MillCapabilities)
    min_layers: int = 1
    max_layers: int = 16
    supports_hybrid: bool = True        # mixed laminate materials in one stack
    symmetric_required: bool = True     # balanced buildup about the centreline
    note: str | None = None

    # ── catalog queries (stackup-fitter hooks) ──────────────────────

    def cores(self) -> list:
        return [l for l in self.laminates if l.kind == "core"]

    def prepregs(self) -> list:
        return [l for l in self.laminates if l.kind == "prepreg"]

    def materials(self) -> set:
        """Distinct dielectric materials stocked (>1 ⇒ hybrid-capable)."""
        return {l.material for l in self.laminates}

    def rf_foils(self, *, max_rz_um: float = 2.0) -> list:
        """Low-profile foils suitable for SIW / mmWave (roughness Rz at or
        below `max_rz_um`). The copper the EM/waveguide layers select."""
        return [f for f in self.foils
                if f.is_low_profile
                or (f.roughness_rz_um is not None and f.roughness_rz_um <= max_rz_um)]

    # ── assembly-material catalog ───────────────────────────────────

    @property
    def supports_multi_alloy(self) -> bool:
        """True if this house can carry a second solder alloy beyond the
        board-wide reflow paste (selective/wave/hand/step capability)."""
        return bool(_MULTI_ALLOY_PROCESSES.intersection(self.solder_processes))

    @property
    def default_solder(self):
        """The board-wide reflow paste (first stocked solder), or None."""
        return self.solders[0] if self.solders else None

    def solder(self, name: str):
        """Look up a stocked `Solder` by name (None if absent)."""
        return next((s for s in self.solders if s.name == name), None)

    def adhesive(self, name: str):
        """Look up a stocked `Adhesive` (underfill/encapsulant) by name."""
        return next((a for a in self.adhesives if a.name == name), None)

    def laminate_for(self, material: str, kind: str | None = None) -> list:
        return [l for l in self.laminates
                if l.material == material and (kind is None or l.kind == kind)]

    def nearest_dielectric(self, target_um: float, *,
                           material: str | None = None,
                           kind: str | None = None) -> Laminate:
        """The stocked laminate whose thickness is closest to `target_um`
        (optionally filtered by material/kind). Raises if the catalog is
        empty after filtering."""
        pool = [l for l in self.laminates
                if (material is None or l.material == material)
                and (kind is None or l.kind == kind)]
        if not pool:
            raise ValueError(
                f"{self.name}: no laminate matches material={material!r} "
                f"kind={kind!r}")
        return min(pool, key=lambda l: abs(l.thickness_um - target_um))

    def combine_to_thickness(self, target_um: float, *,
                             tol_um: float = 50.0,
                             material: str | None = None) -> list:
        """Greedily select stocked laminates summing to ~`target_um`
        within `tol_um`. A hook for the stackup fitter (which adds the
        copper foils + symmetry on top). Raises if it can't get within
        tolerance. Returns a list[Laminate]."""
        pool = sorted(
            (l for l in self.laminates
             if material is None or l.material == material),
            key=lambda l: -l.thickness_um,
        )
        if not pool:
            raise ValueError(f"{self.name}: empty laminate pool")
        chosen: list = []
        remaining = target_um
        while remaining > tol_um:
            pick = next((l for l in pool if l.thickness_um <= remaining + tol_um),
                        None)
            if pick is None:
                pick = pool[-1]     # smallest available; overshoot check below
            chosen.append(pick)
            remaining -= pick.thickness_um
        total = sum(l.thickness_um for l in chosen)
        if abs(total - target_um) > tol_um:
            raise ValueError(
                f"{self.name}: cannot reach {target_um} µm within ±{tol_um} "
                f"µm from catalog (best {total} µm)")
        return chosen

    # ── DRC checks (validators/fab.py surface) ──────────────────────

    def check_trace(self, width_mm: float, *, refs: tuple = ()) -> list:
        if width_mm < self.rules.min_trace_mm:
            return [Issue("error", "min_trace",
                          f"trace {width_mm:.3f} mm < min {self.rules.min_trace_mm} mm",
                          refs)]
        return []

    def check_drill(self, dia_mm: float, *, micro: bool = False,
                    refs: tuple = ()) -> list:
        limit = self.rules.micro_min_drill_mm if micro else self.rules.min_drill_mm
        if dia_mm < limit:
            return [Issue("error", "min_drill",
                          f"drill {dia_mm:.3f} mm < min {limit} mm", refs)]
        return []

    def check_via(self, pad_diameter_mm: float, drill_mm: float, *,
                  micro: bool = False, refs: tuple = ()) -> list:
        issues = list(self.check_drill(drill_mm, micro=micro, refs=refs))
        via_min = (self.rules.micro_min_via_diameter_mm if micro
                   else self.rules.min_via_diameter_mm)
        ann_min = (self.rules.micro_min_annular_mm if micro
                   else self.rules.min_annular_ring_mm)
        if pad_diameter_mm < via_min:
            issues.append(Issue("error", "min_via_diameter",
                                f"via Ø {pad_diameter_mm:.3f} mm < min {via_min} mm",
                                refs))
        annular = (pad_diameter_mm - drill_mm) / 2.0
        if annular < ann_min:
            issues.append(Issue("error", "min_annular_ring",
                                f"annular {annular:.3f} mm < min {ann_min} mm", refs))
        return issues

    def check_aspect(self, board_thickness_mm: float, drill_mm: float, *,
                     refs: tuple = ()) -> list:
        if drill_mm <= 0:
            return []
        ar = board_thickness_mm / drill_mm
        if ar > self.rules.max_aspect_ratio:
            return [Issue("error", "max_aspect_ratio",
                          f"aspect {ar:.1f}:1 > max {self.rules.max_aspect_ratio}:1 "
                          f"({board_thickness_mm:.2f} mm ÷ {drill_mm:.3f} mm)", refs)]
        return []

    # ── flex DRC ────────────────────────────────────────────────────

    def check_flex_link(self, available_mm: float,
                        *, R_mm: float | None = None,
                        link_name: str = "",
                        refs: tuple = ()) -> list:
        """One snake link / branch flex zone, length-budget check.

        `available_mm` is the unrolled flex length the panel provides
        for this link (e.g. `TILE_PITCH_MM − tileA_Ø/2 − tileB_Ø/2` for
        a snake link). Compares against the fab's `min_zone_length_180`
        at the chosen radius. Returns `Issue("error", ...)` on shortage,
        `Issue("warn", ...)` on tight margin (< 1 mm), nothing on pass.

        No-flex fabs (where `flex.R_min_mm is None`) silently pass —
        the panel topology will be validated separately.
        """
        if self.flex.R_min_mm is None:
            return []
        required = self.flex.min_zone_length_180(R_mm=R_mm)
        if required is None:
            return []
        if available_mm < required:
            short = required - available_mm
            tag = f" ({link_name})" if link_name else ""
            return [Issue("error", "flex_zone_too_short",
                          f"flex zone{tag}: {available_mm:.1f} mm available, "
                          f"{required:.1f} mm required for 180° fold at "
                          f"R={R_mm or self.flex.R_min_mm:.1f} mm "
                          f"(short by {short:.1f} mm)", refs)]
        if available_mm < required + 1.0:
            return [Issue("warn", "flex_zone_tight",
                          f"flex zone{(' ' + link_name) if link_name else ''}: "
                          f"{available_mm:.1f} mm available, "
                          f"{required:.1f} mm required — only "
                          f"{available_mm-required:.1f} mm headroom", refs)]
        return []

    def check_flex_layer_count(self, rigid_layers: int, *,
                                refs: tuple = ()) -> list:
        """Rigid layer count must fit the flex process's stack envelope.

        Eurocircuits SEMI-FLEX, for example, only ships 4 or 6 rigid
        layers — a 14L design + SEMI-FLEX won't build."""
        if self.flex.R_min_mm is None:
            return []      # no flex process — layer count is unconstrained
        lo = self.flex.rigid_min_layers
        hi = self.flex.rigid_max_layers
        if lo is not None and rigid_layers < lo:
            return [Issue("error", "flex_rigid_too_few_layers",
                          f"{rigid_layers}L rigid < {lo}L min for "
                          f"{self.flex.process_name}", refs)]
        if hi is not None and rigid_layers > hi:
            return [Issue("error", "flex_rigid_too_many_layers",
                          f"{rigid_layers}L rigid > {hi}L max for "
                          f"{self.flex.process_name} — fab can't build "
                          f"this stack with integrated flex", refs)]
        return []

    def check_flex_width(self, width_mm: float, *, refs: tuple = ()) -> list:
        """Validate a flex strip's tangential width against the fab
        minimum. Trivial helper; covered for completeness so the panel
        layout can call it on each computed `flex.width_mm`."""
        if self.flex.min_flex_width_mm is None:
            return []
        if width_mm < self.flex.min_flex_width_mm:
            return [Issue("error", "flex_too_narrow",
                          f"flex width {width_mm:.2f} mm < min "
                          f"{self.flex.min_flex_width_mm} mm "
                          f"({self.flex.process_name})", refs)]
        return []

    # ── milling DRC ────────────────────────────────────────────────

    def check_pocket(self, *, depth_mm: float, opening_mm: float | None = None,
                     floor_mm: float | None = None,
                     refs: tuple = ()) -> list:
        """One milled pocket (cavity) — depth, opening, floor thickness.

        `floor_mm` is the remaining FR-4 below the pocket bottom (i.e.
        between the routed surface and the next inner Cu layer). Used by
        the spacer-cavity validator + the embedded-component cavity
        check."""
        if not self.milling.available:
            return [Issue("error", "milling_unavailable",
                          f"controlled-depth milling not offered by "
                          f"{self.name}", refs)]
        issues: list = []
        m = self.milling
        if m.max_depth_mm is not None and depth_mm > m.max_depth_mm:
            issues.append(Issue("error", "pocket_too_deep",
                                f"depth {depth_mm:.2f} mm > max "
                                f"{m.max_depth_mm} mm", refs))
        if m.min_depth_mm is not None and depth_mm < m.min_depth_mm:
            issues.append(Issue("error", "pocket_too_shallow",
                                f"depth {depth_mm:.2f} mm < min "
                                f"{m.min_depth_mm} mm", refs))
        if (opening_mm is not None and m.min_pocket_opening_mm
                and opening_mm < m.min_pocket_opening_mm):
            issues.append(Issue("error", "pocket_opening_too_small",
                                f"opening {opening_mm:.2f} mm < min "
                                f"{m.min_pocket_opening_mm} mm", refs))
        if (floor_mm is not None and m.min_pocket_floor_mm
                and floor_mm < m.min_pocket_floor_mm):
            issues.append(Issue("error", "pocket_floor_too_thin",
                                f"floor {floor_mm:.2f} mm < min "
                                f"{m.min_pocket_floor_mm} mm", refs))
        return issues

    def check_side_cavity(self, *, width_mm: float, depth_mm: float,
                          height_mm: float | None = None,
                          refs: tuple = ()) -> list:
        """Side-opening cavity (the attached-flex landing cavity).

        `depth_mm` is how far the cavity extends INTO the board from
        the edge; `width_mm` is along the board edge; `height_mm` is
        the Z-extent (exposed-layer thickness window)."""
        if not self.milling.side_cavity_supported:
            return [Issue("error", "side_cavity_unsupported",
                          f"{self.name} does not offer side cavities — "
                          f"attached-flex requires a fab change OR "
                          f"surface-attach (no cavity)", refs)]
        m = self.milling
        issues: list = []
        if (m.side_cavity_min_width_mm
                and width_mm < m.side_cavity_min_width_mm):
            issues.append(Issue("error", "side_cavity_too_narrow",
                                f"side cavity {width_mm:.2f} mm < min "
                                f"{m.side_cavity_min_width_mm} mm", refs))
        if (m.side_cavity_min_depth_mm
                and depth_mm < m.side_cavity_min_depth_mm):
            issues.append(Issue("error", "side_cavity_too_shallow",
                                f"side cavity {depth_mm:.2f} mm deep < min "
                                f"{m.side_cavity_min_depth_mm} mm", refs))
        if (height_mm is not None and m.side_cavity_min_height_mm
                and height_mm < m.side_cavity_min_height_mm):
            issues.append(Issue("error", "side_cavity_too_short",
                                f"side cavity {height_mm:.2f} mm tall < min "
                                f"{m.side_cavity_min_height_mm} mm", refs))
        return issues

    # ── serialization ───────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name, "vendor": self.vendor, "process": self.process,
            "laminates": [l.to_dict() for l in self.laminates],
            "foils": [f.to_dict() for f in self.foils],
            "metal_options": [m.to_dict() for m in self.metal_options],
            "solders": [s.to_dict() for s in self.solders],
            "adhesives": [a.to_dict() for a in self.adhesives],
            "solder_processes": list(self.solder_processes),
            "rules": self.rules.to_dict(),
            "tolerances": self.tolerances.to_dict(),
            "flex": self.flex.to_dict(),
            "milling": self.milling.to_dict(),
            "min_layers": self.min_layers, "max_layers": self.max_layers,
            "supports_hybrid": self.supports_hybrid,
            "symmetric_required": self.symmetric_required,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FabProfile":
        return cls(
            name=d["name"], vendor=d.get("vendor"), process=d.get("process"),
            laminates=[Laminate.from_dict(x) for x in d.get("laminates", [])],
            foils=[CopperFoil.from_dict(x) for x in d.get("foils", [])],
            metal_options=[MetalInsert.from_dict(x) for x in d.get("metal_options", [])],
            solders=[Solder.from_dict(x) for x in d.get("solders", [])],
            adhesives=[Adhesive.from_dict(x) for x in d.get("adhesives", [])],
            solder_processes=list(d.get("solder_processes", ["reflow"])),
            rules=DesignRules.from_dict(d["rules"]) if d.get("rules") else DesignRules(),
            tolerances=(FabTolerances.from_dict(d["tolerances"])
                        if d.get("tolerances") else FabTolerances()),
            flex=(FlexCapabilities.from_dict(d["flex"])
                  if d.get("flex") else FlexCapabilities()),
            milling=(MillCapabilities.from_dict(d["milling"])
                     if d.get("milling") else MillCapabilities()),
            min_layers=d.get("min_layers", 1), max_layers=d.get("max_layers", 16),
            supports_hybrid=d.get("supports_hybrid", True),
            symmetric_required=d.get("symmetric_required", True),
            note=d.get("note"),
        )
