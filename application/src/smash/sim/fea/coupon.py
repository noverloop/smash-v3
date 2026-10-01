"""Isolated CalculiX coupon for a horizontal trace free-spanning a gap.

The board-level study (`trace_strain.py`) answers the *bonded* trace
question: a route glued to a copper layer follows the board's surface
strain and survives because copper is ductile. The case it cannot
answer is a trace that is **not** fully bonded — one crossing an
unsupported span: a milled slot, an anti-pad in a plane, a cavity edge,
or a delaminated patch. There the trace is a free copper ribbon loaded
transversely by its own inertia under setback, and the response is
genuinely width- and thickness-dependent.

This module meshes exactly that coupon: a copper ribbon of width `w`
and thickness `t` running along X, rigidly fixed over an anchor length
at each end (the supported lands) and free across a central gap `L`.
Setback is applied as a ±Z gravity body load at the platform's peak
acceleration. The fixed-fixed span concentrates the bending moment at
the anchor lips (M = qL²/12) and at mid-span (qL²/24) — the classic
locations a free-spanning trace cracks.

Element type is C3D8I (incompatible-modes hex): same 8-node
connectivity as C3D8 but no shear locking, so bending stress is
trustworthy without a quadratic mesh. For long, thin spans that deflect
much more than their thickness the response turns membrane-dominated;
pass `nlgeom=True` so CCX captures the geometric stiffening (a LINEAR
solve over-predicts bending stress there — conservative, but optionally
exact).

Closed-form anchor for validation: a fixed-fixed beam of rectangular
section under a uniform transverse body load ρ·a has peak fibre stress
    σ = ρ·a·L² / (2·t)
(independent of width), with peak fibre strain σ/E. The end-to-end test
checks the FEA against this in the small-deflection (linear) regime.
"""
from __future__ import annotations

import dataclasses
import math

from smash.sim.fea.ccx_writer import (
    CCXBodyLoad, CCXBoundary, CCXDeck, CCXElementSet, CCXMaterial, CCXStep,
)
from smash.sim.fea.trace_strain import (
    CopperAllowable, _max_principal_strain, _vm_strain,
)


ELEMENT_TYPE_HEX_INCOMPAT = "C3D8I"


@dataclasses.dataclass
class TraceCouponSpec:
    """Geometry + mesh density for one free-span trace coupon."""
    width_mm: float = 0.10            # trace width (the worry: 0.1 mm)
    thickness_um: float = 35.0        # copper thickness (1 oz finished base)
    gap_mm: float = 1.0               # unsupported free-span length
    anchor_mm: float = 0.3            # fixed land length at each end
    # Mesh density.
    dx_mm: float | None = None        # in-plane element size; default gap/14
    n_width: int = 4                  # elements across the width
    n_thickness: int = 3             # elements through the copper thickness
    # Copper elastic constants (match the FabProfile foil catalog).
    youngs_gpa: float = 117.0
    poisson: float = 0.34
    density_kg_m3: float = 8960.0

    @property
    def total_length_mm(self) -> float:
        return 2.0 * self.anchor_mm + self.gap_mm

    @property
    def dx(self) -> float:
        return self.dx_mm if self.dx_mm else max(self.gap_mm / 14.0, 0.02)


def _seg(x0: float, x1: float, dx: float) -> list:
    """Inclusive node positions from x0..x1 at ~dx spacing (≥1 cell)."""
    n = max(1, int(round((x1 - x0) / dx)))
    return [x0 + (x1 - x0) * i / n for i in range(n + 1)]


@dataclasses.dataclass
class _CouponMesh:
    node_coords: list                 # [(id, x_m, y_m, z_m), ...]
    elements: list                    # [(eid, [n1..n8]), ...]
    fixed_node_ids: list              # land nodes (clamped 1-3)
    span_node_ids: list               # free-span + lip nodes (evaluation set)
    xs_mm: list
    note: str


def _build_mesh(spec: TraceCouponSpec) -> _CouponMesh:
    dx = spec.dx
    anchor, gap, L = spec.anchor_mm, spec.gap_mm, spec.total_length_mm
    t_mm = spec.thickness_um / 1000.0
    # X positions with exact nodes at the two anchor boundaries.
    left = _seg(0.0, anchor, dx)
    mid = _seg(anchor, anchor + gap, dx)
    right = _seg(anchor + gap, L, dx)
    xs = left[:-1] + mid[:-1] + right
    ys = _seg(0.0, spec.width_mm, spec.width_mm / max(1, spec.n_width))
    zs = _seg(0.0, t_mm, t_mm / max(1, spec.n_thickness))

    nx, ny, nz = len(xs), len(ys), len(zs)
    node = [[[0] * nz for _ in range(ny)] for _ in range(nx)]
    coords: list = []
    nid = 1
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                node[ix][iy][iz] = nid
                coords.append((nid, xs[ix] * 1e-3, ys[iy] * 1e-3,
                               zs[iz] * 1e-3))
                nid += 1

    eps = dx * 1e-3
    fixed: list = []
    span: list = []
    for ix in range(nx):
        x = xs[ix]
        is_land = (x <= anchor + eps) or (x >= anchor + gap - eps)
        in_span = (anchor - eps <= x <= anchor + gap + eps)
        for iy in range(ny):
            for iz in range(nz):
                if is_land:
                    fixed.append(node[ix][iy][iz])
                if in_span:
                    span.append(node[ix][iy][iz])

    elements: list = []
    eid = 1
    for ix in range(nx - 1):
        for iy in range(ny - 1):
            for iz in range(nz - 1):
                n1 = node[ix][iy][iz]
                n2 = node[ix + 1][iy][iz]
                n3 = node[ix + 1][iy + 1][iz]
                n4 = node[ix][iy + 1][iz]
                n5 = node[ix][iy][iz + 1]
                n6 = node[ix + 1][iy][iz + 1]
                n7 = node[ix + 1][iy + 1][iz + 1]
                n8 = node[ix][iy + 1][iz + 1]
                elements.append((eid, [n1, n2, n3, n4, n5, n6, n7, n8]))
                eid += 1
    return _CouponMesh(
        node_coords=coords, elements=elements,
        fixed_node_ids=fixed, span_node_ids=span, xs_mm=xs,
        note=(f"copper ribbon {spec.width_mm}×{spec.thickness_um}µm, "
              f"gap {spec.gap_mm} mm: {len(coords)} nodes, "
              f"{len(elements)} C3D8I elements "
              f"({nx-1}×{ny-1}×{nz-1})"),
    )


def build_trace_coupon_deck(spec: TraceCouponSpec, *,
                            accel_m_per_s2: float,
                            direction: str = "forward",
                            nlgeom: bool = False,
                            job_name: str | None = None) -> tuple:
    """Compose a CCXDeck for one free-span trace coupon under setback.

    Returns `(deck, mesh)` — the mesh carries the `span_node_ids`
    evaluation set the result reader needs.

    `direction` is "forward" (−Z) or "reverse" (+Z); for a symmetric
    fixed-fixed span the |stress| is direction-independent, but both are
    provided for parity with the board study.
    """
    dz = -1.0 if direction == "forward" else +1.0
    mesh = _build_mesh(spec)
    job = job_name or (
        f"trace_coupon_w{spec.width_mm:g}_t{spec.thickness_um:g}"
        f"_g{spec.gap_mm:g}_{direction}"
    )
    elements = [(eid, ELEMENT_TYPE_HEX_INCOMPAT, nodes)
                for (eid, nodes) in mesh.elements]
    material = CCXMaterial(
        name="COPPER",
        youngs_modulus_pa=spec.youngs_gpa * 1e9,
        poisson_ratio=spec.poisson, density_kg_m3=spec.density_kg_m3,
        note="bulk Cu trace (FabProfile foil constants)")
    elset = CCXElementSet(name="TRACE",
                          element_ids=[e[0] for e in mesh.elements],
                          material_name="COPPER",
                          note="free-spanning copper trace ribbon")
    step = CCXStep(
        name=f"setback_{direction}", static=True, nlgeom=nlgeom,
        body_loads=[CCXBodyLoad(elset_name="TRACE",
                                magnitude_m_per_s2=accel_m_per_s2,
                                direction=(0.0, 0.0, dz))])
    deck = CCXDeck(
        job_name=job,
        node_coords=mesh.node_coords,
        elements=elements,
        element_sets=[elset],
        node_sets={"LANDS": mesh.fixed_node_ids,
                   "SPAN": mesh.span_node_ids},
        materials=[material],
        boundaries=[CCXBoundary(nset_name="LANDS", dof_first=1, dof_last=3)],
        steps=[step],
        note=(mesh.note
              + f"\nsetback {direction} @ {accel_m_per_s2:.3e} m/s² "
                f"({accel_m_per_s2/9.80665:.0f} G)"
              + (", NLGEOM" if nlgeom else ", linear")),
    )
    return deck, mesh


# ── result reader ───────────────────────────────────────────────────────


def _last_field(frd, labels: tuple):
    """Last result field (highest total_time) whose label is in `labels`
    — the converged, full-load increment of an NLGEOM static run."""
    cand = [f for f in frd.fields if f.label in labels]
    if not cand:
        return None
    return max(cand, key=lambda f: f.total_time)


def _vm_stress_pa(s: tuple) -> float:
    sxx, syy, szz, sxy, syz, szx = s
    return math.sqrt(
        0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
        + 3.0 * (sxy * sxy + syz * syz + szx * szx))


@dataclasses.dataclass
class CouponResult:
    width_mm: float
    thickness_um: float
    gap_mm: float
    peak_g: float
    sigma_vm_mpa: float               # worst von Mises stress in the copper
    eps_principal: float              # worst principal tensile strain
    worst_pos_mm: tuple
    # margins (≥1 fails the corresponding mode)
    m_yield: float                    # σ_vm / yield  → onset of permanent sag
    m_uts: float                      # σ_vm / UTS    → stress-based fracture
    m_fracture: float                 # ε / elongation_min → strain fracture
    yields: bool
    survives: bool                    # ε < elongation_min  (no fracture)
    sigma_closed_form_mpa: float      # ρ·a·L²/(2t) check
    note: str = ""


def evaluate_coupon(frd, mesh: _CouponMesh, spec: TraceCouponSpec, *,
                    peak_g: float,
                    allowable: CopperAllowable | None = None) -> CouponResult:
    """Pull worst σ_vm + principal strain over the free-span node set."""
    allow = allowable or CopperAllowable()
    span = set(mesh.span_node_ids)
    # An NLGEOM static run writes one result block PER load increment;
    # take the LAST (full-load) block, not the first (partial-load) one.
    s_field = _last_field(frd, ("STRESS", "S"))
    e_field = _last_field(frd, ("TOSTRAIN", "E"))
    if s_field is None:
        raise ValueError("coupon FRD has no stress field")

    worst_vm = 0.0
    worst_pos = (0.0, 0.0, 0.0)
    for nid in span:
        comps = s_field.values_by_node.get(nid)
        if comps is None:
            continue
        vm = _vm_stress_pa(comps)
        if vm > worst_vm:
            worst_vm = vm
            c = frd.nodes.get(nid, (0, 0, 0))
            worst_pos = (c[0] * 1e3, c[1] * 1e3, c[2] * 1e3)
    worst_eps = 0.0
    if e_field is not None:
        for nid in span:
            comps = e_field.values_by_node.get(nid)
            if comps is None or len(comps) < 6:
                continue
            ep = _max_principal_strain(comps[:6])
            if ep > worst_eps:
                worst_eps = ep

    sigma_mpa = worst_vm / 1e6
    # Closed-form fixed-fixed beam fibre stress for a sanity anchor.
    a = peak_g * 9.80665
    L = spec.gap_mm * 1e-3
    t = spec.thickness_um * 1e-6
    sigma_cf = (spec.density_kg_m3 * a * L * L / (2.0 * t)) / 1e6

    return CouponResult(
        width_mm=spec.width_mm, thickness_um=spec.thickness_um,
        gap_mm=spec.gap_mm, peak_g=peak_g,
        sigma_vm_mpa=sigma_mpa, eps_principal=worst_eps,
        worst_pos_mm=worst_pos,
        m_yield=sigma_mpa / allow.yield_mpa,
        m_uts=sigma_mpa / allow.uts_mpa,
        m_fracture=(worst_eps / allow.elongation_min
                    if allow.elongation_min else 0.0),
        yields=sigma_mpa > allow.yield_mpa,
        survives=worst_eps < allow.elongation_min,
        sigma_closed_form_mpa=sigma_cf,
    )
