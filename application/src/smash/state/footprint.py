"""Footprint — inline first-class footprint geometry."""
from __future__ import annotations

import dataclasses

from smash.state.pad import Pad


# Default per-side courtyard clearance ring around a footprint's pads — the
# minimum keep-out baked into the footprint. Kept SMALL (0.05) because it
# grows EVERY footprint's courtyard, locked ones included: a larger ring
# overlaps the EE's hand-tightened, locked PMIC cluster on power_board. The
# extra breathing room between auto-placed parts comes from COMP_GAP_MM (the
# packer's component-to-component gap), which only spaces packed parts and
# leaves locked placements alone.
COURTYARD_CLEARANCE_MM = 0.05


# Per-footprint courtyard growth: name -> (axis, clearance_mm). The named
# footprints get their courtyard widened so it clears the pads by >=
# clearance_mm on the chosen axis ("long" or "short" of the courtyard);
# the other axis is left as ensure_courtyard_clearance / the source set it.
# Footprint-keyed and applied at build time (so the packer reserves the
# space). Grow-only + idempotent, so applying once or twice is identical.
# Used for the IPC land patterns whose pads run nearly to the courtyard.
COURTYARD_GROW_MM = {
    "Capacitor_SMD:C_0603_1608Metric":               ("long", 0.20),
    "Capacitor_SMD:C_0805_2012Metric":               ("long", 0.20),
    "Capacitor_Tantalum_SMD:CP_EIA-3528-12_Kemet-T": ("long", 0.20),
    "Inductor_SMD:L_2012_2.0x1.25mm":                ("long", 0.20),
    "SOT96P237X111-3N":                              ("short", 0.20),
}


@dataclasses.dataclass
class Footprint:
    """First-class footprint definition — the physical geometry of
    one component. Lives inline on each Chip / Battery
    (`chip.footprint = Footprint(...)`), not in a separate library.
    If two chips share the same nominal package, each carries its
    own copy — instance ownership is conceptually clean and the
    duplication is negligible at design scale (~300 components).

    Producers (SamacSys ZIP parser, KiCad-library parser, hand-built)
    populate this dataclass. Consumers (placer, BGA-fanout, validator,
    KiCad export) read geometry from here — never from a live
    `.kicad_pcb`.

    No `provisional` flag — if it's in the model, it's real. A
    chip without finalized geometry simply has `footprint=None`
    and that chip can't be placed or routed yet.
    """
    name: str                         # "BGA96C80P9X16_900X1300X120",
                                      # "C_0402_1005Metric",
                                      # "footprints:LGA-24_..."
    pads: list = dataclasses.field(default_factory=list)        # list[Pad]
    body_outline: list = dataclasses.field(default_factory=list)
                                      # F.Fab polygon points [(x, y), ...]
    courtyard: list = dataclasses.field(default_factory=list)
                                      # F.CrtYd polygon
    silk: list = dataclasses.field(default_factory=list)
                                      # silkscreen graphics (free-form
                                      # for now; structured shapes can be
                                      # added when consumers want them)
    copper_lines: list = dataclasses.field(default_factory=list)
                                      # list of {"layer", "width_mm",
                                      # "points"} dicts — copper polylines
                                      # that aren't pads (e.g. the NFC
                                      # spiral coil). Most factories
                                      # leave this empty; only chips with
                                      # printed-coil geometry populate it.
    # Nominal envelope / package facts
    pitch_mm: float | None = None     # for grid arrays (BGA / QFN)
    size_mm: tuple | None = None      # (W, H) overall envelope
    height_mm: float | None = None    # Z height (nominal package)
    package_class: str | None = None  # "BGA" | "QFN" | "SOIC" | "0402" |
                                      # "TO-220" | "LGA" | "ODCSP" | ...
    # Provenance / artifacts
    model_3d_path: str | None = None  # path to STEP / WRL
    source: str | None = None         # "samacsys", "kicad-stock", "custom"
    note: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "pads": [p.to_dict() for p in self.pads],
            "body_outline":   [list(pt) for pt in self.body_outline],
            "courtyard":      [list(pt) for pt in self.courtyard],
            "silk":           list(self.silk),
            "copper_lines":   [
                {"layer":    cl["layer"],
                 "width_mm": cl["width_mm"],
                 "points":   [list(pt) for pt in cl["points"]]}
                for cl in self.copper_lines
            ],
            "pitch_mm":       self.pitch_mm,
            "size_mm":        list(self.size_mm) if self.size_mm else None,
            "height_mm":      self.height_mm,
            "package_class":  self.package_class,
            "model_3d_path":  self.model_3d_path,
            "source":         self.source,
            "note":           self.note,
        }

    def pad(self, num: str) -> Pad:
        """Look up a Pad by num. Same exact-match semantics as
        Chip.pin() but without the alias fallback (pads don't have
        aliases — those live on the electrical Pin)."""
        for p in self.pads:
            if p.num == num:
                return p
        raise KeyError(f"footprint {self.name!r}: no pad {num!r}")

    def ensure_courtyard_clearance(
        self, clearance: float | None = None,
    ) -> "Footprint":
        """Guarantee the courtyard clears every pad by >= `clearance` mm on
        all sides, widening it only if it doesn't already. A no-op when the
        courtyard is already generous; otherwise the courtyard is replaced
        by the axis-aligned envelope of (current courtyard ∪ pads ∪ body)
        plus the clearance ring. The packer abuts courtyards, so this is
        what keeps a dense field's neighbouring pads >= 2*clearance apart
        instead of touching (a DRC short). Returns self for chaining.

        `clearance` defaults to the module global COURTYARD_CLEARANCE_MM,
        read at CALL time (not bound into the signature) so the ring is
        tunable at runtime.

        Stock library courtyards are sometimes tight to the lands (or
        absent — e.g. a SamacSys part with no F.CrtYd, or an IPC land
        pattern that omits it); this normalises them at build time without
        redrawing the artefact. Pad-less mechanical parts are left alone."""
        if clearance is None:
            clearance = COURTYARD_CLEARANCE_MM
        if not self.pads:
            return self
        xs: list = []
        ys: list = []
        for p in self.pads:
            cx, cy = p.position_mm
            w, h = p.size_mm
            xs += [cx - w / 2.0, cx + w / 2.0]
            ys += [cy - h / 2.0, cy + h / 2.0]
        need = [min(xs) - clearance, min(ys) - clearance,
                max(xs) + clearance, max(ys) + clearance]
        cur = None
        if self.courtyard:
            cxs = [pt[0] for pt in self.courtyard]
            cys = [pt[1] for pt in self.courtyard]
            cur = [min(cxs), min(cys), max(cxs), max(cys)]
            if (cur[0] <= need[0] and cur[1] <= need[1]
                    and cur[2] >= need[2] and cur[3] >= need[3]):
                return self                      # already clears the pads
            need = [min(need[0], cur[0]), min(need[1], cur[1]),
                    max(need[2], cur[2]), max(need[3], cur[3])]
        for poly in (self.body_outline,):
            if poly:
                bxs = [pt[0] for pt in poly]
                bys = [pt[1] for pt in poly]
                need = [min(need[0], min(bxs) - clearance),
                        min(need[1], min(bys) - clearance),
                        max(need[2], max(bxs) + clearance),
                        max(need[3], max(bys) + clearance)]
        x0, y0, x1, y1 = need
        self.courtyard = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        return self

    def grow_courtyard_axis(self, axis: str, clearance: float) -> "Footprint":
        """Widen the courtyard so it clears the pads by >= `clearance` mm on
        one axis — `axis` is "long" or "short" w.r.t. the current courtyard's
        dimensions. The other axis is untouched. Grow-only (takes min/max
        with the existing courtyard) and therefore idempotent. Needs both
        pads and a courtyard."""
        if not self.pads or not self.courtyard:
            return self
        pxs: list = []
        pys: list = []
        for p in self.pads:
            cx, cy = p.position_mm
            w, h = p.size_mm
            pxs += [cx - w / 2.0, cx + w / 2.0]
            pys += [cy - h / 2.0, cy + h / 2.0]
        cxs = [q[0] for q in self.courtyard]
        cys = [q[1] for q in self.courtyard]
        x0, x1, y0, y1 = min(cxs), max(cxs), min(cys), max(cys)
        x_is_long = (x1 - x0) >= (y1 - y0)
        grow_x = (axis == "long") == x_is_long
        if grow_x:
            x0 = min(x0, min(pxs) - clearance)
            x1 = max(x1, max(pxs) + clearance)
        else:
            y0 = min(y0, min(pys) - clearance)
            y1 = max(y1, max(pys) + clearance)
        self.courtyard = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        return self

    def apply_courtyard_growth(self) -> "Footprint":
        """Apply the COURTYARD_GROW_MM override for this footprint name, if
        any (a no-op otherwise). Called once where the footprint is built."""
        spec = COURTYARD_GROW_MM.get(self.name)
        if spec:
            self.grow_courtyard_axis(*spec)
        return self

    @property
    def is_bga(self) -> bool:
        """True iff this footprint is a Ball Grid Array (any sub-flavor:
        BGA / VFBGA / DSBGA / ODCSP BGA / etc.). Looks at
        `package_class` only — `LFCSP` (Lead-Frame Chip Scale Package)
        and other leaded packages stay False."""
        pc = self.package_class or ""
        return "BGA" in pc

