"""Copper-layer bend-strain extraction from a board FEA `.frd`.

The launch FEA (`smash.sim.fea`) meshes a board tile and bends it under
setback body force, but `report.py` only scores *solder-joint* margins
at chip pads. This module answers a different question:

    Do the horizontal routed traces on the F.Cu / B.Cu copper layers
    survive the *bend strain* the setback imposes on the board?

The key physics: a trace bonded to a copper layer follows the board's
local in-plane surface strain by strain compatibility — the strain is
continuous across the Cu↔dielectric bond, only the *stress* jumps
(E_Cu ≫ E_FR4). So the strain a bonded trace sees is exactly the
in-plane strain of the board surface at that layer, and it is
**independent of the trace's width** — a 0.1 mm route and a 1 mm route
at the same spot strain identically. That is why this reads the strain
field (`E`) at the consolidated copper-layer element sets
(FCU_SUBSTRATE / BCU_SUBSTRATE from `mesh.py`) rather than needing a
sub-millimetre trace mesh.

Failure criterion. Copper is ductile: it *yields* at
ε_y = σ_y/E ≈ 70 MPa / 117 GPa ≈ 0.06 % strain, but does not *fracture*
until its elongation-at-break (~3 % for thin/cold ED foil, ~10 % for
IPC-6012 Class-3 plating, ~20-30 % for annealed/wrought Cu). So the
governing "survives the shock" criterion is

    max principal tensile strain  <  copper elongation

with the yield stress reported only as the (easily-passed) onset-of-
plasticity reference. For context the laminate itself cracks in tension
at ~0.5-1 % strain, so a copper trace failing in bend (needing several
%) is downstream of the board cracking — useful framing for the
verdict.

The strain tensor read from the FRD is in CCX Voigt order
(Exx, Eyy, Ezz, Exy, Eyz, Ezx) with **tensor** shear components
(Exy = γxy/2); the principal-strain eigenvalues and the von Mises
equivalent strain below assume that convention.
"""
from __future__ import annotations

import dataclasses
import json
import math
import pathlib

from smash.sim.fea.frd_parser import FRDResult
from smash.sim.fea.mesh import BoardMesh


# Bulk copper elastic modulus — matches the FabProfile foil catalog and
# the Cu-coin metal entry (117 GPa). Used to convert strain → an
# indicative copper stress for the yield/UTS reference columns.
COPPER_E_GPA_DEFAULT = 117.0


@dataclasses.dataclass
class CopperAllowable:
    """Copper strength + ductility envelope for the trace verdict.

    `elongation_*` are the strain-at-break tiers the report brackets
    against — the governing "survives the shock" line is `elongation_min`
    (the most brittle credible foil). `yield_mpa` / `uts_mpa` drive the
    indicative stress columns (σ ≈ E·ε); they are reference context, not
    the fracture line, because ductile copper survives well past yield.
    """
    # Strain-at-break tiers (dimensionless). Defaults span the credible
    # range: thin/cold ED foil → IPC-6012 Class-3 plating → annealed Cu.
    elongation_min: float = 0.03      # brittle thin ED foil — the floor
    elongation_typ: float = 0.10      # IPC-6012 Class-3 min plating
    elongation_ductile: float = 0.20  # annealed / wrought Cu
    yield_mpa: float = 70.0           # annealed Cu yield (catalog value)
    uts_mpa: float = 300.0            # as-plated ED foil / barrel UTS
    youngs_gpa: float = COPPER_E_GPA_DEFAULT
    # Laminate tensile crack strain — the board fails here first; shown
    # in the report as the "board cracks before the trace" reference.
    laminate_crack_strain: float = 0.008

    @property
    def yield_strain(self) -> float:
        """ε at which the copper first yields = σ_y / E."""
        return (self.yield_mpa * 1e6) / (self.youngs_gpa * 1e9)

    @classmethod
    def from_foil(cls, foil) -> "CopperAllowable":
        """Build the allowable envelope from a `CopperFoil`'s ductility.

        The foil's RT `elongation_pct` is the nominal (typ) elongation;
        the governing fracture floor is taken at 0.3× that (a worst-case
        thin/cold/defected-lot knockdown), so a standard ED foil (≈10%)
        lands at the same 3% floor used elsewhere, while a rolled-annealed
        RA foil (≈20%) earns a 6% floor — i.e. ductile copper is rewarded
        for the bend/crack-bridging verdict. E is taken from the foil."""
        e = (getattr(foil, "elongation_pct", None) or 10.0) / 100.0
        E = getattr(foil, "youngs_modulus_gpa", None) or COPPER_E_GPA_DEFAULT
        return cls(
            elongation_min=round(0.3 * e, 4),
            elongation_typ=round(e, 4),
            elongation_ductile=round(1.2 * e, 4),
            youngs_gpa=E,
        )


# ── per-layer verdict + result dataclasses ──────────────────────────────


@dataclasses.dataclass
class TraceStrainVerdict:
    """Worst in-plane bend strain on one copper layer of the board."""
    layer: str                       # "FCU_SUBSTRATE" | "BCU_SUBSTRATE"
    node_id: int                     # worst node (max principal strain)
    position_mm: tuple               # (x, y, z) of that node
    eps_principal_max: float         # max principal (tensile) strain
    eps_vm: float                    # von Mises equivalent strain
    sigma_indic_mpa: float           # indicative Cu stress = E · ε_principal
    margin_elong_min: float          # ε_principal / elongation_min  (governing)
    margin_elong_typ: float          # ε_principal / elongation_typ
    yields: bool                     # ε_principal > yield strain (plasticity)
    margin: float                    # = margin_elong_min (the fracture line)
    verdict: str                     # "pass" | "warn" | "fail"
    time_of_worst_s: float | None = None


@dataclasses.dataclass
class TraceStrainResult:
    board: str
    job_name: str
    load_step_time: float
    allowable: CopperAllowable
    layers: list                     # list[TraceStrainVerdict]
    worst: TraceStrainVerdict | None
    skipped: list                    # list[(layer, reason)]


# ── tensor helpers (Voigt order Exx,Eyy,Ezz,Exy,Eyz,Ezx, tensor shear) ──


def _max_principal_strain(e: tuple) -> float:
    """Largest eigenvalue (max principal strain) of the symmetric strain
    tensor given in CCX Voigt order with tensor shear components."""
    exx, eyy, ezz, exy, eyz, ezx = e
    p1 = exy * exy + eyz * eyz + ezx * ezx
    if p1 == 0.0:
        return max(exx, eyy, ezz)
    q = (exx + eyy + ezz) / 3.0
    p2 = ((exx - q) ** 2 + (eyy - q) ** 2 + (ezz - q) ** 2) + 2.0 * p1
    p = math.sqrt(p2 / 6.0)
    if p == 0.0:
        return max(exx, eyy, ezz)
    b11, b22, b33 = (exx - q) / p, (eyy - q) / p, (ezz - q) / p
    b12, b23, b13 = exy / p, eyz / p, ezx / p
    detB = (b11 * (b22 * b33 - b23 * b23)
            - b12 * (b12 * b33 - b23 * b13)
            + b13 * (b12 * b23 - b22 * b13))
    r = max(-1.0, min(1.0, detB / 2.0))
    phi = math.acos(r) / 3.0
    eig1 = q + 2.0 * p * math.cos(phi)
    eig3 = q + 2.0 * p * math.cos(phi + 2.0 * math.pi / 3.0)
    eig2 = 3.0 * q - eig1 - eig3
    return max(eig1, eig2, eig3)


def _vm_strain(e: tuple) -> float:
    """von Mises equivalent strain ε_eq = √(2/3 · e_dev:e_dev), tensor
    shear convention. Reduces to the engineering definition for the
    deviatoric part."""
    exx, eyy, ezz, exy, eyz, ezx = e
    return math.sqrt(
        (2.0 / 9.0) * ((exx - eyy) ** 2 + (eyy - ezz) ** 2 + (ezz - exx) ** 2)
        + (4.0 / 3.0) * (exy * exy + eyz * eyz + ezx * ezx)
    )


# Copper layer element sets the consolidated board mesh emits. The
# trace routing lives on these outer Cu layers, so their surface strain
# is what a bonded trace experiences.
_COPPER_LAYER_SETS = ("FCU_SUBSTRATE", "BCU_SUBSTRATE")


def _layer_node_ids(mesh: BoardMesh, elset_name: str) -> set:
    """Union of node IDs over every element in `elset_name`."""
    eids = set(mesh.element_sets.get(elset_name, []))
    if not eids:
        return set()
    out: set = set()
    for el in mesh.elements:
        if el.eid in eids:
            out.update(el.nodes)
    return out


def _verdict(margin: float) -> str:
    if margin >= 1.0:  return "fail"
    if margin >= 0.50: return "warn"
    return "pass"


# ── evaluators ──────────────────────────────────────────────────────────


def evaluate_trace_strain(frd: FRDResult, mesh: BoardMesh, board, *,
                          allowable: CopperAllowable | None = None,
                          field_label: str | None = None,
                          ) -> TraceStrainResult:
    """Find the worst bend strain on each copper layer of `board` and
    classify it against the copper elongation envelope.

    Reads the strain field `E` from the FRD (the launch deck requests
    `*EL FILE, S, E`). For each copper-layer element set, walks its
    nodes, takes the maximum principal tensile strain, and compares to
    `allowable.elongation_min` (the governing fracture line)."""
    allow = allowable or CopperAllowable()
    e_field = (frd.field(field_label) if field_label
               else (frd.field("TOSTRAIN") or frd.field("E")
                     or frd.field("STRAIN")))
    if e_field is None:
        raise ValueError(
            "FRD has no strain field — deck must request `*EL FILE, S, E` "
            "(the launch writer already does); CCX records it as TOSTRAIN."
        )
    return _classify_one_field(e_field, frd.nodes, mesh, board, allow,
                               job_name=frd.job_name or board.name)


def evaluate_trace_strain_transient(frd: FRDResult, mesh: BoardMesh,
                                    board, *,
                                    allowable: CopperAllowable | None = None,
                                    ) -> TraceStrainResult:
    """Walk EVERY strain field in the FRD (one per output increment of a
    `--dynamic` explicit run — the shockwave transit) and keep the worst
    principal strain per layer across time, recording when it peaked."""
    allow = allowable or CopperAllowable()
    strain_fields = [f for f in frd.fields
                     if f.label in ("TOSTRAIN", "E", "STRAIN")]
    if not strain_fields:
        raise ValueError("FRD has no strain (TOSTRAIN) fields.")

    by_layer: dict = {}
    last: TraceStrainResult | None = None
    for field in strain_fields:
        per_step = _classify_one_field(
            field, frd.nodes, mesh, board, allow,
            job_name=frd.job_name or board.name)
        last = per_step
        for v in per_step.layers:
            cur = by_layer.get(v.layer)
            if cur is None or v.eps_principal_max > cur.eps_principal_max:
                v.time_of_worst_s = field.total_time
                by_layer[v.layer] = v

    layers = list(by_layer.values())
    worst = max(layers, key=lambda v: v.margin) if layers else None
    return TraceStrainResult(
        board=board.name,
        job_name=frd.job_name or board.name,
        load_step_time=strain_fields[-1].total_time,
        allowable=allow, layers=layers, worst=worst,
        skipped=last.skipped if last else [],
    )


def _classify_one_field(field, nodes, mesh, board, allow,
                        *, job_name) -> TraceStrainResult:
    e_yield = allow.yield_strain
    layers: list = []
    skipped: list = []
    for layer in _COPPER_LAYER_SETS:
        node_ids = _layer_node_ids(mesh, layer)
        if not node_ids:
            skipped.append((layer, "no elements in this layer set"))
            continue
        worst_nid = None
        worst_eps = -1.0
        worst_vm = 0.0
        for nid in node_ids:
            comps = field.values_by_node.get(nid)
            if comps is None or len(comps) < 6:
                continue
            ep = _max_principal_strain(comps[:6])
            if ep > worst_eps:
                worst_eps = ep
                worst_vm = _vm_strain(comps[:6])
                worst_nid = nid
        if worst_nid is None:
            skipped.append((layer, "no strain data at any layer node"))
            continue
        eps = max(0.0, worst_eps)
        m_min = eps / allow.elongation_min if allow.elongation_min else 0.0
        m_typ = eps / allow.elongation_typ if allow.elongation_typ else 0.0
        sigma_indic = (allow.youngs_gpa * 1e9 * eps) / 1e6   # MPa
        coord = nodes.get(worst_nid, (0.0, 0.0, 0.0))
        layers.append(TraceStrainVerdict(
            layer=layer, node_id=worst_nid,
            position_mm=(coord[0] * 1e3, coord[1] * 1e3, coord[2] * 1e3),
            eps_principal_max=eps, eps_vm=worst_vm,
            sigma_indic_mpa=sigma_indic,
            margin_elong_min=m_min, margin_elong_typ=m_typ,
            yields=eps > e_yield,
            margin=m_min, verdict=_verdict(m_min),
        ))
    worst = max(layers, key=lambda v: v.margin) if layers else None
    return TraceStrainResult(
        board=board.name, job_name=job_name,
        load_step_time=field.total_time, allowable=allow,
        layers=layers, worst=worst, skipped=skipped,
    )


# ── report writer ───────────────────────────────────────────────────────


_GLYPH = {"pass": "✓", "warn": "⚠", "fail": "✗"}


def write_trace_strain_report(result: TraceStrainResult,
                              out_dir: str | pathlib.Path, *,
                              platform_label: str | None = None) -> dict:
    """Emit report.md + report.json for the trace bend-strain check."""
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    a = result.allowable

    json_blob = {
        "board": result.board,
        "job": result.job_name,
        "platform": platform_label,
        "load_step_time_s": result.load_step_time,
        "allowable": dataclasses.asdict(a),
        "layers": [dataclasses.asdict(v) for v in result.layers],
        "worst": dataclasses.asdict(result.worst) if result.worst else None,
        "skipped": [{"layer": l, "reason": r} for l, r in result.skipped],
    }
    (out / "report.json").write_text(json.dumps(json_blob, indent=2))

    lines = [f"# Trace bend-strain report — `{result.board}`", ""]
    if platform_label:
        lines += [f"Launch platform: **{platform_label}**", ""]
    lines += [
        f"Governing fracture line: ε_principal < elongation_min = "
        f"{a.elongation_min*100:.1f} %  "
        f"(typ {a.elongation_typ*100:.0f} %, ductile "
        f"{a.elongation_ductile*100:.0f} %)",
        f"Reference: Cu yields at ε_y = {a.yield_strain*100:.3f} % · "
        f"laminate cracks at ~{a.laminate_crack_strain*100:.1f} %",
        "",
        "## Worst bend strain per copper layer",
        "",
        ("| layer | pos (mm) | ε_principal | ε_vM | σ≈E·ε (MPa) | "
         "m vs ε_min | m vs ε_typ | yielded? | verdict |"),
        "|---|---|---:|---:|---:|---:|---:|:--:|---|",
    ]
    for v in sorted(result.layers, key=lambda x: -x.margin):
        x, y, z = v.position_mm
        lines.append(
            f"| `{v.layer}` | ({x:+.1f}, {y:+.1f}, {z:+.2f}) | "
            f"{v.eps_principal_max*100:.3f} % | {v.eps_vm*100:.3f} % | "
            f"{v.sigma_indic_mpa:.1f} | {v.margin_elong_min:.3f} | "
            f"{v.margin_elong_typ:.3f} | {'yes' if v.yields else 'no'} | "
            f"{_GLYPH.get(v.verdict, '?')} {v.verdict} |"
        )
    if result.worst:
        w = result.worst
        lines += [
            "",
            f"**Worst layer: `{w.layer}` — ε_principal = "
            f"{w.eps_principal_max*100:.3f} %, m = {w.margin:.3f} "
            f"({w.verdict}) vs the {a.elongation_min*100:.1f} % floor."
            + (f" (peaked at t = {w.time_of_worst_s*1e3:.2f} ms)"
               if w.time_of_worst_s is not None else "") + "**",
        ]
        if w.eps_principal_max < a.laminate_crack_strain:
            lines.append(
                f"\n> Bend strain ({w.eps_principal_max*100:.3f} %) is below "
                f"the laminate crack strain (~{a.laminate_crack_strain*100:.1f} "
                f"%): the board cracks before a bonded copper trace does, so "
                f"trace width (incl. 0.1 mm) is not the limiter here."
            )
    if result.skipped:
        lines += ["", "## Skipped", ""]
        lines += [f"- `{l}` — {r}" for l, r in result.skipped]

    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "output_dir": str(out),
        "worst_layer": result.worst.layer if result.worst else None,
        "worst_margin": result.worst.margin if result.worst else None,
        "worst_eps": (result.worst.eps_principal_max
                      if result.worst else None),
    }
