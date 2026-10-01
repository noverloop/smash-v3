"""Stackup fitter — generate a Board's layer buildup from the FabProfile.

`fit_stackup(spec)` turns an electrical/mechanical intent (`StackupSpec`)
into a concrete `list[Layer]` (each with its `dielectric_below`), drawing
copper foils + dielectrics from the `FabProfile` catalog. The factory is
the only constraint: materials, thicknesses, and foils all come from the
profile.

The default spec reproduces the project's canonical 14-layer FR4 stack —
F.Cu, In1…In12, B.Cu, with two 50-µm "FR4 thin" embedded-capacitance
gaps (In1↔In2 and In11↔In12) and 150-µm FR4 elsewhere — so converging the
exporter onto this fitter doesn't change the default board's output. The
copper+dielectric core sums to ~2.206 mm (→ 2.226 mm with solder masks);
`Board.thickness_mm` derives from it.

Per-board variation is just a different `StackupSpec`: a hybrid substrate
(Rogers on the F.Cu↔In1 gap) or a metal backing (carried as
`al_backing_mm`, not a copper layer). Deriving layer *count* from the
netlist / impedance targets is a later increment.
"""
from __future__ import annotations

import dataclasses

from smash.state.stackup.layer import Layer
from smash.state.fab.default import default_fab_profile


_ROGERS_SUBSTRATE = "rogers_ro4350b_5mil"


@dataclasses.dataclass
class StackupSpec:
    """Intent for one board's buildup. Defaults = the canonical 14L."""
    copper_layers: int = 14
    embedded_cap_pairs: list = dataclasses.field(
        default_factory=lambda: [("In1.Cu", "In2.Cu"), ("In11.Cu", "In12.Cu")])
    plane_layers: dict = dataclasses.field(default_factory=dict)
    # ^ extra standalone plane roles, e.g. {"In2.Cu": "ground"} — the
    #   AN5724 §6.5 template wants a unified GND plane between the data
    #   and A/C routing layers, outside any embedded-cap pair
    top_substrate: str = "fr4"
    al_backing_mm: float = 0.0
    target_thickness_mm: float | None = None   # None → catalog-natural

    @classmethod
    def for_board(cls, board) -> "StackupSpec":
        """Derive a spec from a Board's material/backing/layer-count overrides."""
        kwargs = dict(
            top_substrate=getattr(board, "top_substrate", "fr4") or "fr4",
            al_backing_mm=getattr(board, "al_backing_mm", 0.0) or 0.0,
        )
        cu = getattr(board, "copper_layers", None)
        if cu is not None:
            kwargs["copper_layers"] = cu
        tt = getattr(board, "target_thickness_mm", None)
        if tt is not None:
            kwargs["target_thickness_mm"] = tt
        # boards may relocate the embedded-cap pairs (companion_compute
        # buries its top pair below the DDR routing levels) and declare
        # standalone plane layers
        ecp = getattr(board, "embedded_cap_pairs_override", None)
        if ecp is not None:
            kwargs["embedded_cap_pairs"] = list(ecp)
        pl = getattr(board, "plane_roles", None)
        if pl is not None:
            kwargs["plane_layers"] = dict(pl)
        return cls(**kwargs)


def _layer_names(copper_layers: int) -> list:
    """F.Cu, In1.Cu … In(N-2).Cu, B.Cu."""
    inner = copper_layers - 2
    return ["F.Cu"] + [f"In{k}.Cu" for k in range(1, inner + 1)] + ["B.Cu"]


def fit_stackup(spec: StackupSpec | None = None, *, fab=None) -> list:
    """Build the `list[Layer]` for `spec` from the `FabProfile` catalog
    (default profile if `fab` is None). Layers are ordered top→bottom;
    each carries its `dielectric_below` (None on the bottom layer)."""
    spec = spec or StackupSpec()
    fab = fab or default_fab_profile()
    names = _layer_names(spec.copper_layers)
    n = len(names)

    # role + pairing lookup from the embedded-cap pairs (+ standalone
    # plane layers, e.g. the §6.5 mid-stack GND)
    role_of = dict(spec.plane_layers)
    paired = {}
    for gnd, pwr in spec.embedded_cap_pairs:
        role_of[gnd] = "embedded_cap_gnd"
        role_of[pwr] = "embedded_cap_power"
        paired[gnd] = pwr
        paired[pwr] = gnd
    pair_set = {frozenset(p) for p in spec.embedded_cap_pairs}

    # foil thicknesses from the catalog
    outer = min((f for f in fab.foils if f.placement in ("outer", "any")),
                key=lambda f: f.weight_oz, default=None)
    inner = next((f for f in fab.foils if f.weight_oz == 1.0),
                 outer)

    target_um = (spec.target_thickness_mm * 1000.0
                 if spec.target_thickness_mm is not None else None)

    layers = []
    fill_gap_um = 150.0          # default inter-layer FR4 thickness
    for i, name in enumerate(names):
        is_outer = i in (0, n - 1)
        foil = outer if is_outer else inner
        role = role_of.get(name, "signal")

        di = None
        if i < n - 1:
            gap_pair = frozenset((name, names[i + 1]))
            gap_num = i + 1                       # 1-indexed from the top
            if gap_pair in pair_set:
                # embedded-cap thin core
                lam = fab.nearest_dielectric(50, material="FR4 thin")
                di = lam.to_dielectric()
            elif i == 0 and spec.top_substrate == _ROGERS_SUBSTRATE:
                lam = fab.nearest_dielectric(127, material="RO4350B")
                di = lam.to_dielectric()
            else:
                kind = "prepreg" if gap_num % 2 == 1 else "core"
                lam = fab.nearest_dielectric(fill_gap_um, material="FR4", kind=kind)
                di = lam.to_dielectric()

        layers.append(Layer(
            name=name, index=i, role=role,
            thickness_um=foil.thickness_um if foil else (17.5 if is_outer else 35.0),
            thickness_tol_um=foil.thickness_tol_um if foil else 0.0,
            paired_with=paired.get(name),
            dielectric_below=di,
        ))

    if target_um is not None:
        _retarget_fill(layers, names, pair_set, spec, target_um, fab)
    return layers


def _retarget_fill(layers, names, pair_set, spec, target_um, fab) -> None:
    """Best-effort: grow/shrink the non-embedded-cap FR4 fill dielectrics
    toward `target_um`, picking the nearest stocked FR4 thickness for each
    fill gap. Embedded-cap + Rogers gaps are fixed. The reachable range is
    bounded by the catalog × fixed layer count (e.g. prepregs cap at
    150 µm), so an arbitrary target may not be hit exactly — adjust the
    layer count (a future per-board spec) for thicker boards."""
    cu = sum(l.thickness_um for l in layers)
    fixed = 0.0
    fill_idx = []
    for i, l in enumerate(layers):
        di = l.dielectric_below
        if di is None:
            continue
        gap_pair = frozenset((names[i], names[i + 1]))
        is_fixed = (gap_pair in pair_set
                    or (i == 0 and spec.top_substrate == _ROGERS_SUBSTRATE))
        if is_fixed:
            fixed += di.thickness_um
        else:
            fill_idx.append(i)
    if not fill_idx:
        return
    per_fill = max(25.0, (target_um - cu - fixed) / len(fill_idx))
    for i in fill_idx:
        kind = layers[i].dielectric_below.kind
        lam = fab.nearest_dielectric(per_fill, material="FR4", kind=kind)
        layers[i].dielectric_below = lam.to_dielectric()
