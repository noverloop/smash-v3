"""ncab — an NCAB-grounded fab rule family (additive).

DRC `rules` / `tolerances` / cavity-`milling` transcribed from NCAB Group's
published design-guideline posters (in `Research/`), layered onto the project
**default material catalog** — `ncab_profile()` reuses `default_fab_profile()`'s
laminates / foils / solders / adhesives / metals. This is a profile *family*
selected per-board via `Board.fab`; it sits ALONGSIDE `default_fab_profile()`,
not in place of it.

Sources (Research/):
  * NCAB_Design_Guidelines_Multilayer_3_1   — track/gap, annular, drilling,
                                              soldermask, routing
  * NCAB_Design_Guidelines_HDI_1_3          — microvia, BGA escape by pitch
  * NCAB_Design_Guidelines_Stackups_Impedances_1_0 — impedance tolerance
  * NCAB_Design_Guidelines_ViaProtection_1_1 — IPC-4761 fill types
  * NCAB_Design_Guidelines_CopperCoin_1_0    — cavity-milling envelope
  * NCAB_Design_Guidelines_Ultra_HDI_2_0     — UHDI threshold (flag only)

NCAB publishes three producibility tiers (GENERAL / MODERATE / ADVANCED) and
Class 2 / 3 columns; all are encoded as configuration, so a profile can be
built for any (ipc_class, tier) and the cheapest tier that still builds a given
board is selected per-board.

One SOURCE GAP remains (flagged in-line): the PTH plated-hole max aspect ratio
is not on the NCAB posters (only microvia AR is) — it keeps a conservative
documented value pending a fab quote; NOT an invented NCAB number.
"""
from __future__ import annotations

from typing import Literal

from smash.state.fab.tolerances import FabTolerances
from smash.state.fab.rules import DesignRules
from smash.state.fab.profile import FabProfile

Tier = Literal["general", "moderate", "advanced"]
TIERS: tuple[Tier, ...] = ("general", "moderate", "advanced")

# ── Multilayer 3.1: TRACK & GAP (mm), keyed [copper_oz][tier] → (trace, gap)
# Inner-layer (IL) values — the limiting case for dense routing. Verbatim
# from the MULTILAYER guide TRACK&GAP table.
_TRACK_GAP_IL: dict[float, dict[Tier, tuple[float, float]]] = {
    0.33: {"general": (0.075, 0.075), "moderate": (0.075, 0.075), "advanced": (0.075, 0.075)},
    0.5:  {"general": (0.150, 0.200), "moderate": (0.100, 0.150), "advanced": (0.075, 0.075)},
    1.0:  {"general": (0.150, 0.200), "moderate": (0.125, 0.150), "advanced": (0.100, 0.100)},
    2.0:  {"general": (0.200, 0.250), "moderate": (0.175, 0.225), "advanced": (0.150, 0.175)},
    3.0:  {"general": (0.250, 0.300), "moderate": (0.225, 0.275), "advanced": (0.200, 0.250)},
}
# ── Multilayer 3.1: ANNULAR RING OF VIAS (mm), [copper_oz][tier] → IL annular
_ANNULAR_IL: dict[float, dict[Tier, float]] = {
    0.33: {"general": 0.100, "moderate": 0.100, "advanced": 0.100},
    0.5:  {"general": 0.200, "moderate": 0.150, "advanced": 0.100},
    1.0:  {"general": 0.200, "moderate": 0.150, "advanced": 0.125},
    2.0:  {"general": 0.250, "moderate": 0.225, "advanced": 0.175},
    3.0:  {"general": 0.300, "moderate": 0.275, "advanced": 0.225},
}
# ── Multilayer 3.1: DRILLING — PTH diameter tolerance (mm, ±), by tier.
_PTH_DIA_TOL_MM: dict[Tier, float] = {"general": 0.100, "moderate": 0.075, "advanced": 0.050}
_NPTH_DIA_TOL_MM: dict[Tier, float] = {"general": 0.075, "moderate": 0.050, "advanced": 0.025}
# ── Multilayer 3.1: ROUTING — recommended pattern-to-edge (mm), by tier.
_PATTERN_TO_EDGE_MM: dict[Tier, float] = {"general": 0.50, "moderate": 0.30, "advanced": 0.20}
# ── Drilling — min wall-to-wall space, different net (mm) → hole-to-hole proxy
_HOLE_WALL_DIFF_NET_MM: dict[Tier, float] = {"general": 0.40, "moderate": 0.35, "advanced": 0.25}
# ── Multilayer 3.1: SOLDERMASK — SMT-to-covered-copper (silk/mask setback, mm)
_SM_SMT_TO_COPPER_MM: dict[Tier, float] = {"general": 0.20, "moderate": 0.15, "advanced": 0.10}

# ── Stackups 1.0: smallest fillable PTH (Via Protection: fill range 0.20–0.50)
# used as the min mechanical drill the via-protection process can still seal.
_MIN_PTH_DRILL_MM: dict[Tier, float] = {"general": 0.30, "moderate": 0.25, "advanced": 0.20}

# ── HDI 1.3: microvia general rules (µm → mm), by tier.
#   size = laser microvia Ø (A), land = capture/target land (B/C),
#   dielectric = L1–L2 microvia dielectric (D).
_MICROVIA: dict[Tier, dict[str, float]] = {
    # "general" tier has no microvia capability (plain multilayer).
    "general":  {"size": 0.0, "land": 0.0, "dielectric": 0.0},
    "moderate": {"size": 0.100, "land": 0.275, "dielectric": 0.075},   # HDI RECOMMENDED
    "advanced": {"size": 0.076, "land": 0.250, "dielectric": 0.050},   # HDI ADVANCED
}

# ── HDI 1.3: BGA escape by pitch — the finest BGA pitch each tier can escape.
# (pad / microvia / land / track / gap, mm). Used by the per-board selector:
# a board with a 0.50 mm-pitch BGA needs at least the tier whose row is
# non-None at 0.50 mm. Verbatim from the HDI guide BGA-layout table.
#   pitch_mm : {tier: (bga_pad, microvia, land, track, gap) | None}
_BGA_ESCAPE: dict[float, dict[Tier, tuple[float, float, float, float, float] | None]] = {
    0.80: {"general": (0.400, 0.0,   0.450, 0.100, 0.125),   # dog-bone via-in-pad
           "moderate": (0.400, 0.100, 0.300, 0.075, 0.100),
           "advanced": (0.400, 0.100, 0.300, 0.075, 0.100)},
    0.65: {"general": (0.350, 0.125, 0.300, 0.100, 0.100),
           "moderate": (0.350, 0.125, 0.300, 0.100, 0.100),
           "advanced": (0.350, 0.100, 0.250, 0.075, 0.100)},
    0.50: {"general": None,                                   # not buildable
           "moderate": (0.300, 0.125, 0.250, 0.075, 0.087),
           "advanced": (0.250, 0.100, 0.250, 0.075, 0.087)},
    0.40: {"general": None,
           "moderate": (0.250, 0.100, 0.250, 0.0,   0.0),     # via-in-pad only
           "advanced": (0.250, 0.080, 0.250, 0.0,   0.0)},
}
# Below 0.40 mm pitch the HDI guide hands off to Ultra-HDI (sub-50 µm lines /
# sub-400 µm pitch). We flag rather than silently approve.
UHDI_PITCH_THRESHOLD_MM = 0.40

# (Finished-Cu / prepreg / core-thickness tables live in the project default
# catalog, which ncab_profile reuses — no NCAB-specific copy is kept here.)

# SOURCE GAP — PTH max aspect ratio is not on the NCAB rigid/HDI posters
# (only microvia AR 0.8:1 / 1:1 is). Conservative industry value pending a
# fab quote; do NOT treat as an NCAB number.
_PTH_MAX_ASPECT_UNSOURCED = 8.0


# ── builders ────────────────────────────────────────────────────────────

def ncab_design_rules(*, ipc_class: int = 3, tier: Tier = "advanced",
                      inner_oz: float = 1.0, outer_oz: float = 0.5,
                      hdi: bool = False,
                      finest_pitch_mm: float | None = None) -> DesignRules:
    """Build a `DesignRules` from the NCAB tables for one (class, tier).

    `inner_oz` is the limiting copper weight for dense inner routing. When
    `hdi` is set, the HDI BGA-escape track/gap for `finest_pitch_mm` overrides
    the multilayer track/gap (HDI lines are finer locally inside the BGA).
    """
    trace, gap = _TRACK_GAP_IL[inner_oz][tier]
    annular = _ANNULAR_IL[inner_oz][tier]
    if hdi and finest_pitch_mm is not None:
        esc = _BGA_ESCAPE.get(finest_pitch_mm, {}).get(tier)
        if esc and esc[3] > 0:
            trace, gap = min(trace, esc[3]), min(gap, esc[4])
    mv = _MICROVIA[tier] if hdi else _MICROVIA["general"]
    micro_drill = mv["size"] or 0.10
    micro_via = mv["land"] or 0.25
    micro_annular = max((mv["land"] - mv["size"]) / 2.0, 0.05) if mv["size"] else 0.05
    drill = _MIN_PTH_DRILL_MM[tier]
    return DesignRules(
        min_trace_mm=trace,
        min_space_mm=gap,
        min_drill_mm=drill,
        min_via_diameter_mm=round(drill + 2 * annular, 3),
        min_annular_ring_mm=annular,
        max_aspect_ratio=_PTH_MAX_ASPECT_UNSOURCED,   # SOURCE GAP (see above)
        edge_clearance_mm=_PATTERN_TO_EDGE_MM[tier],
        hole_to_hole_mm=_HOLE_WALL_DIFF_NET_MM[tier],
        silk_to_pad_mm=_SM_SMT_TO_COPPER_MM[tier],
        micro_min_drill_mm=micro_drill,
        micro_min_via_diameter_mm=micro_via,
        micro_min_annular_mm=round(micro_annular, 4),
        min_board_thickness_mm=0.50,     # Multilayer 12L+ moderate floor
        max_board_thickness_mm=8.0,      # Multilayer 12L+ advanced ceiling
        note=f"NCAB Multilayer/HDI — class {ipc_class}, {tier} tier, "
             f"{inner_oz}oz inner" + (", HDI microvia" if hdi else ""),
    )


def ncab_tolerances(tier: Tier = "advanced") -> FabTolerances:
    """Process tolerances from the NCAB Multilayer + Stackups guides."""
    return FabTolerances(
        finished_thickness_pct=10.0,                 # Stackups: ±10% for >1 mm
        etch_trace_width_um=25.0,                     # typical etch window
        registration_um={"general": 75.0, "moderate": 50.0, "advanced": 40.0}[tier],
        drill_dia_um=_PTH_DIA_TOL_MM[tier] * 1000.0,  # Multilayer PTH dia tol
        true_position_um={"general": 75.0, "moderate": 50.0, "advanced": 50.0}[tier],
        impedance_pct={"general": 10.0, "moderate": 8.0, "advanced": 5.0}[tier],  # Stackups
        soldermask_registration_um={"general": 75.0, "moderate": 50.0, "advanced": 40.0}[tier],
        note=f"NCAB {tier}-tier process tolerances",
    )


def ncab_milling() -> "MillCapabilities":
    """Controlled-depth milling envelope, grounded in the NCAB Copper Coin
    design guideline (Research/NCAB_Design_Guidelines_CopperCoin_1_0_231026).
    Those are coin-cavity numbers; per design decision they're taken to apply
    to general milled cavities (the spacer pockets) too. Preferred tier.

    NOT covered by the coin guide and left at conservative defaults: router
    tool diameter / fillet, and side-opening (attached-flex) cavities."""
    from smash.state.fab.milling import MillCapabilities
    return MillCapabilities(
        available=True,
        depth_tol_mm=0.1,          # T-coin depth-rout tol ±0.1 (adv ±0.075)
        min_depth_mm=0.5,          # N1 milling depth ≥0.5
        max_depth_mm=2.8,          # H coin thickness max (preferred) — coin-
                                   # derived; deeper spacer pockets need a quote
        min_pocket_wall_mm=0.5,    # F cavity edge → outer circuit (adv 0.38)
        min_pocket_floor_mm=0.5,   # N2 min remaining thickness ≥0.5
        min_pocket_opening_mm=2.0, # O min milling slot 2.0 (adv 1.6)
        position_tol_mm=0.1,       # C/D coin edge → cavity boundary ~0.1
        pad_oxide_protection="ENIG",
        side_cavity_supported=False,   # not in the coin guide
        note="NCAB Copper Coin guide (preferred tier); coin-cavity numbers "
             "applied to general cavities per design decision",
    )


def ncab_profile(*, ipc_class: int = 3, tier: Tier = "advanced",
                 inner_oz: float = 1.0, outer_oz: float = 0.5,
                 hdi: bool = False, finest_pitch_mm: float | None = None,
                 name: str | None = None) -> FabProfile:
    """An NCAB-grounded fab profile for one (ipc_class, tier): the NCAB
    design-guideline DRC `rules` + `tolerances` + copper-coin cavity `milling`,
    layered on top of the **project default material catalog** (laminates /
    foils / solders / adhesives / metals — single-sourced from
    `default_fab_profile` so material data, incl. the SAC305 constants and the
    Cu-coin metal option, doesn't diverge).

    Additive: this is a profile *family* selected per-board via `Board.fab`,
    alongside the existing `default_fab_profile()` — it doesn't replace it."""
    from smash.state.fab.default import default_fab_profile
    base = default_fab_profile()
    nm = name or f"ncab-class{ipc_class}-{tier}" + ("-hdi" if hdi else "")
    return FabProfile(
        name=nm,
        vendor="NCAB Group (design-guideline envelope)",
        process=f"multilayer{' + laser-microvia HDI' if hdi else ''} — "
                f"IPC class {ipc_class}, {tier} tier",
        # material catalog reused from the project default (no divergence)
        laminates=base.laminates,
        foils=base.foils,
        metal_options=base.metal_options,
        solders=base.solders,
        adhesives=base.adhesives,
        solder_processes=base.solder_processes,
        # NCAB-grounded rules / tolerances / cavity milling
        rules=ncab_design_rules(ipc_class=ipc_class, tier=tier, inner_oz=inner_oz,
                                outer_oz=outer_oz, hdi=hdi,
                                finest_pitch_mm=finest_pitch_mm),
        tolerances=ncab_tolerances(tier),
        milling=ncab_milling(),     # NCAB Copper Coin guide (cavity envelope)
        min_layers=1,
        max_layers={"general": 8, "moderate": 18, "advanced": 40}[tier],
        supports_hybrid=base.supports_hybrid,
        symmetric_required=base.symmetric_required,
        note=f"NCAB DRC rules on the project default catalog — "
             f"class {ipc_class}, {tier} tier"
             + ("" if hdi else " — no HDI/microvia"),
    )


# ── per-board cheapest-viable selection ─────────────────────────────────

_AREA_ARRAY = ("BGA", "UFBGA", "VFBGA", "WLCSP", "CSP", "FCBGA", "LFBGA", "TFBGA")


def min_tier_for_pitch(pitch_mm: float | None) -> "Tier | None":
    """Cheapest NCAB tier that can escape a BGA of `pitch_mm`.

    Returns the least-capable tier whose BGA-escape row is buildable, or None
    for a pad-only board (no BGA). Raises if the pitch is below the Ultra-HDI
    threshold (the NCAB rigid/HDI guides don't cover it)."""
    if pitch_mm is None:
        return None
    if pitch_mm < UHDI_PITCH_THRESHOLD_MM:
        raise ValueError(
            f"BGA pitch {pitch_mm} mm < {UHDI_PITCH_THRESHOLD_MM} mm — Ultra-HDI "
            f"territory; the NCAB rigid/HDI guides don't cover it (needs UHDI spec)")
    pitches = sorted(p for p in _BGA_ESCAPE if p >= pitch_mm - 1e-9)
    row = _BGA_ESCAPE[pitches[0]] if pitches else _BGA_ESCAPE[min(_BGA_ESCAPE)]
    for tier in TIERS:
        if row.get(tier) is not None:
            return tier
    return "advanced"


def finest_bga_pitch_mm(chips) -> float | None:
    """Finest area-array (BGA/CSP) pitch among a board's chips, or None if
    the board has no area-array part (pad/QFN/SOIC-only → no HDI needed)."""
    pitches = []
    for c in chips:
        fp = getattr(c, "footprint", None)
        if fp is None or getattr(fp, "pitch_mm", None) is None:
            continue
        pc = (getattr(fp, "package_class", "") or "").upper()
        if any(k in pc for k in _AREA_ARRAY):
            pitches.append(fp.pitch_mm)
    return min(pitches) if pitches else None


def select_ncab_profile(chips, *, ipc_class: int = 3) -> FabProfile:
    """Cheapest viable NCAB profile for a board, by its finest BGA pitch.

    Pad/QFN-only boards get a plain multilayer profile (no HDI); area-array
    boards get the cheapest HDI tier that can escape their finest pitch."""
    pitch = finest_bga_pitch_mm(chips)
    if pitch is None:
        return ncab_profile(ipc_class=ipc_class, tier="general", hdi=False)
    tier = min_tier_for_pitch(pitch)        # "moderate" or "advanced"
    return ncab_profile(ipc_class=ipc_class, tier=tier or "advanced",
                        hdi=True, finest_pitch_mm=_nearest_escape_pitch(pitch))


def _nearest_escape_pitch(pitch_mm: float) -> float:
    """Snap to the nearest-or-coarser pitch row present in the BGA table."""
    coarser = sorted(p for p in _BGA_ESCAPE if p >= pitch_mm - 1e-9)
    return coarser[0] if coarser else min(_BGA_ESCAPE)


def select_ncab_profile_name(chips, *, ipc_class: int = 3) -> str:
    """Registry NAME of the cheapest viable NCAB profile for a board's
    chips — what a generator assigns to `Board.fab`. Pad/QFN-only boards
    get the plain-multilayer tier; area-array boards get the cheapest HDI
    tier that escapes their finest pitch."""
    pitch = finest_bga_pitch_mm(chips)
    if pitch is None:
        return f"ncab-class{ipc_class}-general"
    tier = min_tier_for_pitch(pitch) or "advanced"
    # "general" tier escapes coarse BGAs (≥0.65 mm) with dog-bone vias — no
    # microvia HDI needed, so it's the plain-multilayer profile. Only the
    # moderate/advanced tiers (0.50/0.40 mm) require the HDI microvia build.
    if tier == "general":
        return f"ncab-class{ipc_class}-general"
    return f"ncab-class{ipc_class}-{tier}-hdi"


def assign_board_fabs(design, boards: dict, *, ipc_class: int = 3) -> dict:
    """Set each rigid Board's `fab` to its cheapest viable NCAB profile,
    grouping the design's chips by `board_tag`, then re-fit its stackup.
    Returns {board_name: fab_name}. Boards whose finest BGA pitch is below
    the Ultra-HDI floor are left on the default and reported as `None`."""
    from collections import defaultdict
    by_tag: dict = defaultdict(list)
    for c in getattr(design, "chips", []):
        by_tag[getattr(c, "board_tag", None)].append(c)
    assigned: dict = {}
    for name, b in boards.items():
        if getattr(b, "kind", "rigid") != "rigid":
            continue
        try:
            fab_name = select_ncab_profile_name(by_tag.get(name, []), ipc_class=ipc_class)
        except ValueError:
            assigned[name] = None        # sub-UHDI — leave on default, flag
            continue
        b.fab = fab_name
        b.set_fitted_stackup()           # resolves b.fab via the registry
        assigned[name] = fab_name
    return assigned


# ── registry (Board.fab name → profile) ─────────────────────────────────
# Canonical names a `Board.fab` string can reference. Built lazily so the
# same name always resolves to an equivalent profile.
_REGISTRY = {
    "ncab-class3-general":      lambda: ncab_profile(ipc_class=3, tier="general"),
    "ncab-class3-moderate-hdi": lambda: ncab_profile(ipc_class=3, tier="moderate", hdi=True,
                                                     finest_pitch_mm=0.50),
    "ncab-class3-advanced-hdi": lambda: ncab_profile(ipc_class=3, tier="advanced", hdi=True,
                                                     finest_pitch_mm=0.50),
    "ncab-class2-general":      lambda: ncab_profile(ipc_class=2, tier="general"),
    "ncab-class2-moderate-hdi": lambda: ncab_profile(ipc_class=2, tier="moderate", hdi=True,
                                                     finest_pitch_mm=0.50),
    "ncab-class2-advanced-hdi": lambda: ncab_profile(ipc_class=2, tier="advanced", hdi=True,
                                                     finest_pitch_mm=0.50),
}


def get_fab_profile(name: str | None) -> FabProfile:
    """Resolve a `Board.fab` name to a FabProfile. None → the default."""
    if name is None:
        from smash.state.fab.default import default_fab_profile
        return default_fab_profile()
    if name in _REGISTRY:
        return _REGISTRY[name]()
    raise KeyError(f"unknown fab profile {name!r}; known: {sorted(_REGISTRY)}")
