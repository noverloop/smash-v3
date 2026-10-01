"""Isolated CalculiX coupon for a plated via barrel under an AXIAL pull.

⚠ CAVEAT — this does NOT represent how a via loads under setback.
A via barrel is NOT a structural load path for a component's inertial
load. Setback bends the rim-supported board *plate*: a component's load
is reacted IN-PLANE (σxx/σyy at the copper surfaces) and spread to the
spacer-ring supports — the through-thickness direction (σzz, the barrel
axis) carries almost nothing in the board interior. The component is
held by its solder joints (see the chip-pad launch FEA), its pad-to-
laminate adhesion, and the underfill / potting; the via is an electrical
/ thermal feature embedded in laminate, and even a filled via's plug is
not a designed tension/compression member. (Confirmed: in the board FEA
the only large σzz sits at the pinned support-ring BC, r≈15.5 mm/z=0 — an
artifact — not in the field where vias live.)

This coupon fixes the bottom pad and pulls the top pad with the full
m·a, which manufactures an artificial through-thickness tether (a
"ground" on the far side of the board) that does not exist in a rim-
supported plate, and dumps a whole component's mass onto one via. So its
"max supported mass per via" output is a PATHOLOGICAL UPPER BOUND, not a
design criterion. The real via reliability concern is thermal-cycling
barrel fatigue (z-axis CTE mismatch), a different load case entirely.

Kept as a generic "isolated copper tube under an axial end load" check
(it matches σ = F/(π·d_mean·t_wall) within ~6%, validating the mesh +
*CLOAD path), NOT as a setback via verdict.
"""
from __future__ import annotations

import dataclasses
import math

from smash.sim.fea.ccx_writer import (
    CCXBodyLoad, CCXBoundary, CCXDeck, CCXElementSet, CCXMaterial,
    CCXNodalLoad, CCXStep, ELEMENT_TYPE_LINEAR_HEX,
)
from smash.sim.fea.coupon import _vm_stress_pa
from smash.sim.fea.trace_strain import CopperAllowable, _max_principal_strain


@dataclasses.dataclass
class ViaCouponSpec:
    """Geometry + mesh density for one plated-via-barrel coupon (mm/µm)."""
    drill_mm: float = 0.20            # finished hole diameter
    wall_um: float = 20.0             # plated barrel wall thickness
    board_thickness_mm: float = 1.6   # barrel length (layer span)
    pad_diameter_mm: float = 0.45     # annular pad outer diameter
    pad_thickness_um: float = 35.0    # outer-layer copper (finished)
    supported_mass_g: float = 0.1     # mass this via carries (its share)
    n_sectors: int = 16               # angular hex divisions
    nz_barrel: int = 8                # barrel z-layers
    youngs_gpa: float = 117.0
    poisson: float = 0.34
    density_kg_m3: float = 8960.0

    @property
    def barrel_area_mm2(self) -> float:
        r_in = self.drill_mm / 2.0
        r_out = r_in + self.wall_um / 1000.0
        return math.pi * (r_out * r_out - r_in * r_in)


def _seg(a: float, b: float, n: int) -> list:
    return [a + (b - a) * i / n for i in range(n + 1)]


@dataclasses.dataclass
class _ViaMesh:
    node_coords: list
    elements: list                    # [(eid, [n1..n8]), ...]
    barrel_eids: list
    top_load_nids: list
    bot_fix_nids: list
    barrel_nids: list
    note: str


def _build_mesh(spec: ViaCouponSpec) -> _ViaMesh:
    N = spec.n_sectors
    r_in = spec.drill_mm / 2.0
    r_out = r_in + spec.wall_um / 1000.0
    r_pad = spec.pad_diameter_mm / 2.0
    h = spec.board_thickness_mm
    pt = spec.pad_thickness_um / 1000.0
    cos = [math.cos(2 * math.pi * k / N) for k in range(N)]
    sin = [math.sin(2 * math.pi * k / N) for k in range(N)]

    node_map: dict = {}
    coords: list = []
    nid = [0]

    def node(r: float, k: int, z: float) -> int:
        key = (round(r, 10), k % N, round(z, 10))
        got = node_map.get(key)
        if got is not None:
            return got
        nid[0] += 1
        coords.append((nid[0], r * cos[k % N] * 1e-3,
                       r * sin[k % N] * 1e-3, z * 1e-3))
        node_map[key] = nid[0]
        return nid[0]

    elements: list = []
    eid = [0]
    barrel_eids: list = []

    def hexel(ra, rb, k, z_lo, z_hi, *, barrel=False):
        k1 = (k + 1) % N
        ns = [node(ra, k, z_lo), node(rb, k, z_lo),
              node(rb, k1, z_lo), node(ra, k1, z_lo),
              node(ra, k, z_hi), node(rb, k, z_hi),
              node(rb, k1, z_hi), node(ra, k1, z_hi)]
        eid[0] += 1
        elements.append((eid[0], ns))
        if barrel:
            barrel_eids.append(eid[0])
        return eid[0]

    z_barrel = _seg(0.0, h, spec.nz_barrel)
    for k in range(N):
        for j in range(len(z_barrel) - 1):
            hexel(r_in, r_out, k, z_barrel[j], z_barrel[j + 1], barrel=True)
        # annular pads top & bottom: inner ring [r_in,r_out] + flange [r_out,r_pad]
        hexel(r_in, r_out, k, h, h + pt)
        hexel(r_out, r_pad, k, h, h + pt)
        hexel(r_in, r_out, k, -pt, 0.0)
        hexel(r_out, r_pad, k, -pt, 0.0)

    # Node sets by z plane.
    top_z, bot_z = h + pt, -pt
    top_load, bot_fix = [], []
    for (n, x, y, z) in coords:
        if abs(z - top_z * 1e-3) < 1e-12:
            top_load.append(n)
        elif abs(z - bot_z * 1e-3) < 1e-12:
            bot_fix.append(n)
    barrel_nids = sorted({n for eid_ in barrel_eids
                          for n in elements[eid_ - 1][1]})

    return _ViaMesh(
        node_coords=coords, elements=elements, barrel_eids=barrel_eids,
        top_load_nids=top_load, bot_fix_nids=bot_fix,
        barrel_nids=barrel_nids,
        note=(f"via barrel Ø{spec.drill_mm} wall {spec.wall_um}µm × "
              f"{spec.board_thickness_mm}mm, pad Ø{spec.pad_diameter_mm}: "
              f"{len(coords)} nodes, {len(elements)} C3D8 ({N} sectors)"))


def build_via_coupon_deck(spec: ViaCouponSpec, *, accel_m_per_s2: float,
                          direction: str = "reverse",
                          job_name: str | None = None) -> tuple:
    """Compose a CCXDeck for one via-barrel coupon under setback.

    `direction` = "reverse" (+Z, tension + pad pull-off — the worst for a
    barrel) or "forward" (−Z, compression). Returns `(deck, mesh)`.
    """
    sign = +1.0 if direction == "reverse" else -1.0
    mesh = _build_mesh(spec)
    a = accel_m_per_s2
    m = spec.supported_mass_g * 1e-3
    f_total = m * a
    n_top = max(1, len(mesh.top_load_nids))
    job = job_name or (f"via_d{spec.drill_mm:g}_w{spec.wall_um:g}"
                       f"_m{spec.supported_mass_g:g}_{direction}")

    elements = [(eid, ELEMENT_TYPE_LINEAR_HEX, ns) for (eid, ns) in mesh.elements]
    material = CCXMaterial(name="COPPER",
                           youngs_modulus_pa=spec.youngs_gpa * 1e9,
                           poisson_ratio=spec.poisson,
                           density_kg_m3=spec.density_kg_m3,
                           note="plated via barrel + pads (bulk Cu)")
    elset = CCXElementSet(name="VIA", element_ids=[e[0] for e in mesh.elements],
                          material_name="COPPER", note="barrel + pads")
    step = CCXStep(
        name=f"setback_{direction}", static=True,
        body_loads=[CCXBodyLoad(elset_name="VIA", magnitude_m_per_s2=a,
                                direction=(0.0, 0.0, sign))],
        nodal_loads=[CCXNodalLoad(nset_name="TOP_PAD", dof=3,
                                  magnitude_n=sign * f_total / n_top)])
    deck = CCXDeck(
        job_name=job, node_coords=mesh.node_coords, elements=elements,
        element_sets=[elset],
        node_sets={"TOP_PAD": mesh.top_load_nids,
                   "BOT_FIX": mesh.bot_fix_nids,
                   "BARREL": mesh.barrel_nids},
        materials=[material],
        boundaries=[CCXBoundary(nset_name="BOT_FIX", dof_first=1, dof_last=3)],
        steps=[step],
        note=(mesh.note + f"\nsetback {direction}: supported mass "
              f"{spec.supported_mass_g} g × {a/9.80665:.0f} G = "
              f"{f_total:.3f} N on the top pad"))
    return deck, mesh


# ── result reader ───────────────────────────────────────────────────────


@dataclasses.dataclass
class ViaResult:
    drill_mm: float
    wall_um: float
    supported_mass_g: float
    peak_g: float
    direction: str
    sigma_vm_mpa: float               # worst von Mises in the barrel
    eps_principal: float
    worst_pos_mm: tuple
    m_yield: float                    # σ_vm / yield
    m_uts: float                      # σ_vm / UTS
    yields: bool
    survives: bool                    # σ_vm < UTS (no rupture)
    sigma_closed_form_mpa: float
    force_n: float


def evaluate_via_coupon(frd, mesh: _ViaMesh, spec: ViaCouponSpec, *,
                        peak_g: float, direction: str,
                        allowable: CopperAllowable | None = None) -> ViaResult:
    allow = allowable or CopperAllowable()
    barrel = set(mesh.barrel_nids)
    s_field = frd.field("STRESS") or frd.field("S")
    e_field = frd.field("TOSTRAIN") or frd.field("E")
    if s_field is None:
        raise ValueError("via coupon FRD has no stress field")
    worst_vm, worst_pos = 0.0, (0.0, 0.0, 0.0)
    for nid in barrel:
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
        for nid in barrel:
            comps = e_field.values_by_node.get(nid)
            if comps and len(comps) >= 6:
                worst_eps = max(worst_eps, _max_principal_strain(comps[:6]))

    sigma_mpa = worst_vm / 1e6
    a = peak_g * 9.80665
    f_total = spec.supported_mass_g * 1e-3 * a
    d_mean = (spec.drill_mm + spec.wall_um / 1000.0) * 1e-3
    t = spec.wall_um * 1e-6
    sigma_cf = (f_total / (math.pi * d_mean * t)) / 1e6 if t > 0 else 0.0
    return ViaResult(
        drill_mm=spec.drill_mm, wall_um=spec.wall_um,
        supported_mass_g=spec.supported_mass_g, peak_g=peak_g,
        direction=direction, sigma_vm_mpa=sigma_mpa,
        eps_principal=worst_eps, worst_pos_mm=worst_pos,
        m_yield=sigma_mpa / allow.yield_mpa,
        m_uts=sigma_mpa / allow.uts_mpa,
        yields=sigma_mpa > allow.yield_mpa,
        survives=sigma_mpa < allow.uts_mpa,
        sigma_closed_form_mpa=sigma_cf, force_n=f_total)
