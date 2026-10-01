"""CalculiX `.inp` deck writer.

A `.inp` is a flat text file in Abaqus format. CalculiX 2.23 parses a
subset of the Abaqus card vocabulary; the cards we need for the smash
launch-load FEA are:

  *NODE, NSET=…          — nodal coordinates (one line per node)
  *ELEMENT, TYPE=…, ELSET=…   — element connectivity (one line per element,
                                node IDs in CCX corner-ordering)
  *MATERIAL, NAME=…      — open a material block
  *ELASTIC                — E, ν (linear)
  *DENSITY                — ρ
  *PLASTIC                — multilinear true-stress / true-strain (for
                            SAC305; left for a later increment, the
                            first iteration is linear-elastic)
  *SOLID SECTION, ELSET=…, MATERIAL=…
                          — bind an element set to a material
  *BOUNDARY               — Dirichlet BCs (clamped edge, etc.)
  *DLOAD, ELSET=…         — distributed body force per unit volume
                            (= ρ·a for setback acceleration)
  *STEP                   — open a load step
  *STATIC | *DYNAMIC      — analysis type
  *NODE FILE, *EL FILE    — request output to .frd
  *END STEP

This writer assembles these cards from a `CCXDeck` dataclass that the
mesh + materials modules populate. The output deck is human-readable
(comments preserve provenance) so a CCX user can sanity-check it in
cgx before launching the solver.
"""
from __future__ import annotations

import dataclasses
import pathlib


# Element type strings CalculiX understands. The pipeline starts with
# C3D8 (linear 8-node hex) since the mesh generator produces structured
# hex grids; C3D20 (20-node serendipity hex, mid-side nodes) is the
# accuracy upgrade for stress concentrators.
ELEMENT_TYPE_LINEAR_HEX = "C3D8"
ELEMENT_TYPE_QUADRATIC_HEX = "C3D20"

# Linear spring element between two nodes (CCX *SPRING2) — used for
# the cohesive zone at solder pads in Phase G. One element per
# (node-pair, DOF) tuple; SOLDER_SPRINGS_<ref>_DOFn elsets group them.
ELEMENT_TYPE_SPRING_LINK = "SPRING2"


@dataclasses.dataclass
class CCXSpringElement:
    """One *SPRING2 element between two nodes acting on a single DOF
    (1=X, 2=Y, 3=Z translations). Stiffness is per-direction so each
    pad needs three of these to fully constrain xyz."""
    eid: int                      # 1-based CCX element ID
    n1: int                       # 1-based node ID
    n2: int
    dof_n1: int                   # 1, 2, 3
    dof_n2: int                   # usually = dof_n1


@dataclasses.dataclass
class CCXSpringSection:
    """A *SPRING card binding an ELSET to a (DOF_at_n1, DOF_at_n2,
    stiffness_N_per_m) tuple. Multiple spring elements with the same
    stiffness on the same DOF live in the same elset (efficient
    grouping); the writer emits one *SPRING card per group."""
    elset_name: str
    dof_n1: int
    dof_n2: int
    stiffness_n_per_m: float
    note: str | None = None


@dataclasses.dataclass
class CCXMaterial:
    """One material block in the deck. Linear-elastic + density now;
    plasticity table comes later via `plastic_table_mpa_strain`."""
    name: str                     # CCX uses this as the material handle
    youngs_modulus_pa: float
    poisson_ratio: float
    density_kg_m3: float
    plastic_table_mpa_strain: list | None = None    # [(σ_MPa, ε_pl), ...]
    note: str | None = None


@dataclasses.dataclass
class CCXElementSet:
    """A group of elements bound to one material (one *SOLID SECTION
    card per set). The mesh generator emits one set per layer per
    board so layered material assignment is direct."""
    name: str
    element_ids: list                  # 1-based CCX element IDs
    material_name: str
    note: str | None = None


@dataclasses.dataclass
class CCXBoundary:
    """A *BOUNDARY card — Dirichlet BC fixing some DOF on a node set
    to zero (or a prescribed value).  In CalculiX DOFs are:
        1, 2, 3 → translations Ux, Uy, Uz
        4, 5, 6 → rotations    Rx, Ry, Rz (only meaningful for beam/shell)
    A clamped edge fixes DOF 1-3 to 0; a roller fixes a single DOF."""
    nset_name: str
    dof_first: int                    # 1, 2, 3, ...
    dof_last: int                     # inclusive
    value: float = 0.0


@dataclasses.dataclass
class CCXSurface:
    """A *SURFACE card — a named collection of element faces (TYPE=
    ELEMENT) or nodes (TYPE=NODE). CCX restricts master surfaces in
    *TIE to TYPE=ELEMENT (slave can be TYPE=NODE), so for the chip-to-
    board tie our master uses element faces while the slave uses the
    column's bottom node set.

      kind="node"     → TYPE=NODE, body is a node set name.
      kind="element"  → TYPE=ELEMENT, body is a list of (elset, face_id)
                         pairs, where face_id is one of "S1".."S6" per
                         CCX C3D8 numbering."""
    name: str
    kind: str                          # "node" | "element"
    nset_name: str | None = None       # for kind="node"
    element_faces: list = dataclasses.field(default_factory=list)
                                        # for kind="element": [(elset, "S2"), ...]


@dataclasses.dataclass
class CCXTie:
    """A *TIE card — glues two surfaces. CCX enforces matching
    displacements at the slave's nodes onto the master surface (the
    slave is constrained to follow the master). For our chip+underfill
    column tied to the board's F.Cu, the underfill bottom face is the
    SLAVE (small, attached to chip) and the F.Cu surface is the MASTER
    (large, the structural backbone)."""
    name: str
    slave_surface: str                # name of CCXSurface (slave)
    master_surface: str               # name of CCXSurface (master)


@dataclasses.dataclass
class CCXAmplitude:
    """An *AMPLITUDE card — time-resolved scaling factor applied to one
    or more loads in a *DYNAMIC step. The (t, scale) pairs are emitted
    as the amplitude table; CCX interpolates linearly between them.

    For our launch FEA, the load magnitude in *DLOAD is set to the
    PEAK acceleration (m/s²) and the amplitude scales it down to the
    instantaneous a(t)/a_peak ratio — so the writer doesn't need to
    multiply ω² timeseries through itself."""
    name: str
    time_value_pairs: list           # [(t_s, scale), ...]
    smooth: bool = False             # CCX SMOOTH=0.05 default off


@dataclasses.dataclass
class CCXBodyLoad:
    """A *DLOAD card with type GRAV — distributed gravity-like body
    force, magnitude `magnitude_m_per_s2`, direction `(dx, dy, dz)`
    unit-vector. The element set is the volume the load acts on (one
    DLOAD card per element set in CCX). When `amplitude_name` is set,
    the writer emits `*DLOAD, AMPLITUDE=<name>` so a time-varying
    scaling factor multiplies the magnitude during a dynamic step."""
    elset_name: str
    magnitude_m_per_s2: float
    direction: tuple = (0.0, 0.0, -1.0)
    amplitude_name: str | None = None


@dataclasses.dataclass
class CCXNodalLoad:
    """A *CLOAD card — a concentrated force on a node set, one DOF
    (1=Fx, 2=Fy, 3=Fz). Used to apply the inertial pull of a supported
    mass onto a via's top pad (+Z for reverse setback tension, −Z for
    forward compression).

    `magnitude_n` is PER NODE, matching CCX semantics: a *CLOAD on an
    nset applies the magnitude to EVERY node in the set. To spread a
    total force F over the pad's N nodes, pass F/N (the via coupon does
    this division)."""
    nset_name: str
    dof: int
    magnitude_n: float
    amplitude_name: str | None = None


@dataclasses.dataclass
class CCXCentrifugalLoad:
    """A *DLOAD card with type CENTRIF — centrifugal body force from
    rigid-body spin. Magnitude is ω² in (rad/s)²; the axis is defined
    by a point and a direction. For the smash snake stack, every
    board sits centred on the panel's spin axis with its plane
    perpendicular to it, so axis_point=(0,0,0) and axis_dir=(0,0,1)
    are the natural defaults — the centrifugal force on every chip is
    automatically m · ω² · r where r is the chip's distance from the
    board's xy origin.

    CCX *DLOAD CENTRIF syntax (from the manual):
      elset, CENTRIF, ω², x0, y0, z0, dx, dy, dz

    `amplitude_name` lets the writer attach an *AMPLITUDE card so the
    magnitude is scaled by amp(t) during a dynamic step."""
    elset_name: str
    omega_squared_rad2_per_s2: float
    axis_point: tuple = (0.0, 0.0, 0.0)
    axis_dir: tuple = (0.0, 0.0, 1.0)
    amplitude_name: str | None = None


@dataclasses.dataclass
class CCXStep:
    """One *STEP block. Static or dynamic; if `dynamic_t_total_s` is
    populated the writer emits `*DYNAMIC, EXPLICIT` with the given total
    time + automatic time-stepping. Loads + BCs nested under the step
    apply for that step's duration. `output_frequency` throttles result
    dumps (every N increments) so a transient with 10⁵ steps doesn't
    write 10⁵ result blocks."""
    name: str
    body_loads: list = dataclasses.field(default_factory=list)
    centrifugal_loads: list = dataclasses.field(default_factory=list)
                              # list[CCXCentrifugalLoad]
    nodal_loads: list = dataclasses.field(default_factory=list)
                              # list[CCXNodalLoad]
    static: bool = True
    dynamic_t_total_s: float | None = None
    dynamic_t_initial_s: float | None = None
    output_frequency: int | None = None
    # Geometric nonlinearity. For thin features that deflect more than
    # their thickness (a trace free-spanning a gap), the response is
    # membrane-dominated and a LINEAR solve grossly over-predicts the
    # bending stress. NLGEOM=True emits `*STEP, NLGEOM` + an incremented
    # `*STATIC` so CCX captures the membrane stiffening. Default off
    # (linear is correct for the stiff board mesh and conservative for
    # thin spans).
    nlgeom: bool = False
    # Incremented static load ramp for the NLGEOM solve: (Δt_initial,
    # t_total, Δt_min, Δt_max). Only used when nlgeom=True.
    static_increment: tuple = (0.1, 1.0, 1e-5, 1.0)


@dataclasses.dataclass
class CCXDeck:
    """The full .inp deck — assembled by the pipeline and serialised
    by `write_ccx_inp()`. `node_coords` is an (N, 3) array-like; node
    IDs are 1-based (CCX convention). Elements carry their CCX element
    ID + a 1-based node-ID tuple in the CCX corner ordering."""
    job_name: str
    node_coords: list                  # [(id, x_m, y_m, z_m), ...]
    elements: list                     # [(id, eltype, [n1,n2,...]), ...]
    element_sets: list                 # list[CCXElementSet]
    node_sets: dict                    # name → list[int]
    materials: list                    # list[CCXMaterial]
    boundaries: list                   # list[CCXBoundary]
    steps: list                        # list[CCXStep]
    surfaces: list = dataclasses.field(default_factory=list)   # CCXSurface
    ties: list = dataclasses.field(default_factory=list)       # CCXTie
    spring_elements: list = dataclasses.field(default_factory=list)
                                       # list[CCXSpringElement]
    spring_sections: list = dataclasses.field(default_factory=list)
                                       # list[CCXSpringSection]
    amplitudes: list = dataclasses.field(default_factory=list)
                                       # list[CCXAmplitude]
    note: str | None = None


def _fmt_node(node_id: int, x: float, y: float, z: float) -> str:
    return f"{node_id:8d}, {x: .9e}, {y: .9e}, {z: .9e}"


def _fmt_element(eid: int, node_ids: list) -> str:
    return f"{eid:8d}, " + ", ".join(f"{n:8d}" for n in node_ids)


def _write_material(buf, m: CCXMaterial) -> None:
    if m.note:
        buf.append(f"** {m.note}")
    buf.append(f"*MATERIAL, NAME={m.name}")
    buf.append("*ELASTIC")
    buf.append(f"{m.youngs_modulus_pa: .9e}, {m.poisson_ratio: .6f}")
    buf.append("*DENSITY")
    buf.append(f"{m.density_kg_m3: .6f}")
    if m.plastic_table_mpa_strain:
        buf.append("*PLASTIC")
        for sigma_mpa, eps_pl in m.plastic_table_mpa_strain:
            # CCX wants stress in Pa, strain dimensionless.
            buf.append(f"{sigma_mpa * 1e6: .6e}, {eps_pl: .6e}")


def _write_step(buf, step: CCXStep) -> None:
    buf.append(f"** ── step: {step.name} ─────────────────────────────────")
    if step.dynamic_t_total_s is not None:
        # Explicit dynamic — CCX needs (Δt_initial, t_total). The
        # default 10 k increment cap on *STEP isn't enough for ms-scale
        # transit times with ns-scale wave-speed time steps, so we raise it
        # with INC= for the explicit case.
        dt0 = step.dynamic_t_initial_s or (step.dynamic_t_total_s / 1000.0)
        n_steps_estimate = max(
            10_000, int(step.dynamic_t_total_s / dt0 * 2)
        )
        buf.append(f"*STEP, INC={n_steps_estimate}")
        buf.append("*DYNAMIC, EXPLICIT")
        buf.append(f"{dt0: .6e}, {step.dynamic_t_total_s: .6e}")
    elif step.nlgeom:
        # Geometric-nonlinear static with an automatic increment ramp so
        # CCX picks up membrane stiffening of thin spans.
        dt0, ttot, dtmin, dtmax = step.static_increment
        buf.append("*STEP, NLGEOM")
        buf.append("*STATIC")
        buf.append(f"{dt0: .6e}, {ttot: .6e}, {dtmin: .6e}, {dtmax: .6e}")
    else:
        buf.append("*STEP")
        buf.append("*STATIC")
    # Group *DLOAD by amplitude attachment so we only emit one *DLOAD
    # header per (type, amplitude) combo.
    for bl in step.body_loads:
        dx, dy, dz = bl.direction
        amp = f", AMPLITUDE={bl.amplitude_name}" if bl.amplitude_name else ""
        buf.append(f"*DLOAD{amp}")
        buf.append(f"{bl.elset_name}, GRAV, {bl.magnitude_m_per_s2: .6e}, "
                   f"{dx: .6f}, {dy: .6f}, {dz: .6f}")
    for nl in step.nodal_loads:
        amp = f", AMPLITUDE={nl.amplitude_name}" if nl.amplitude_name else ""
        buf.append(f"*CLOAD{amp}")
        buf.append(f"{nl.nset_name}, {nl.dof}, {nl.magnitude_n: .6e}")
    for cl in step.centrifugal_loads:
        px, py, pz = cl.axis_point
        ax, ay, az = cl.axis_dir
        amp = f", AMPLITUDE={cl.amplitude_name}" if cl.amplitude_name else ""
        buf.append(f"*DLOAD{amp}")
        buf.append(
            f"{cl.elset_name}, CENTRIF, "
            f"{cl.omega_squared_rad2_per_s2: .6e}, "
            f"{px: .6e}, {py: .6e}, {pz: .6e}, "
            f"{ax: .6f}, {ay: .6f}, {az: .6f}"
        )
    # Output throttle — keeps a 10⁵-step transient run from writing
    # 10⁵ result blocks to .frd.
    if step.output_frequency:
        buf.append(f"*NODE FILE, FREQUENCY={step.output_frequency}")
    else:
        buf.append("*NODE FILE")
    buf.append("U")
    if step.output_frequency:
        buf.append(f"*EL FILE, FREQUENCY={step.output_frequency}")
    else:
        buf.append("*EL FILE")
    buf.append("S, E")
    buf.append("*END STEP")


def write_ccx_inp(deck: CCXDeck, output_path: str | pathlib.Path) -> str:
    """Serialise the deck to a CCX `.inp` file. Returns the resolved
    output path. The file is human-readable + comment-rich — open it
    in cgx (`cgx -c <file.inp>`) to visualise the mesh + BCs before
    launching the solver."""
    out = pathlib.Path(output_path).resolve()
    if out.suffix.lower() != ".inp":
        out = out.with_suffix(".inp")
    out.parent.mkdir(parents=True, exist_ok=True)

    buf: list[str] = [
        f"** CalculiX deck — job '{deck.job_name}'",
        f"** Generated by smash.sim.fea.ccx_writer",
    ]
    if deck.note:
        buf.extend(f"** {line}" for line in deck.note.splitlines())

    # ── nodes ──────────────────────────────────────────────────────────
    buf.append("*NODE, NSET=ALL_NODES")
    for nid, x, y, z in deck.node_coords:
        buf.append(_fmt_node(int(nid), float(x), float(y), float(z)))

    # ── named node sets (for BCs) ──────────────────────────────────────
    for name, ids in deck.node_sets.items():
        if not ids:
            continue
        buf.append(f"*NSET, NSET={name}")
        # CCX accepts up to 16 entries per line.
        for chunk in _chunked(ids, 16):
            buf.append(", ".join(f"{int(i)}" for i in chunk))

    # ── elements grouped by (type, set) ────────────────────────────────
    # Map elset name → list of (eid, nodes) for output ordering.
    by_set: dict = {}
    eid_to_set: dict = {}
    for es in deck.element_sets:
        for eid in es.element_ids:
            eid_to_set[eid] = es.name
        by_set.setdefault(es.name, [])
    for eid, eltype, nodes in deck.elements:
        es_name = eid_to_set.get(eid)
        if es_name is None:
            raise ValueError(
                f"element {eid} not in any element set (orphan)"
            )
        by_set[es_name].append((eid, eltype, nodes))

    for es in deck.element_sets:
        rows = by_set[es.name]
        if not rows:
            continue
        # Group by element type — CCX needs separate *ELEMENT blocks
        # per type even within the same set.
        by_type: dict = {}
        for eid, eltype, nodes in rows:
            by_type.setdefault(eltype, []).append((eid, nodes))
        for eltype, rows_typed in by_type.items():
            buf.append(f"*ELEMENT, TYPE={eltype}, ELSET={es.name}")
            for eid, nodes in rows_typed:
                buf.append(_fmt_element(eid, nodes))

    # ── spring elements (cohesive zone at solder pads) ─────────────────
    # CCX *SPRING2 connects two nodes with a single-DOF linear spring.
    # Group elements by elset (using the deck.element_sets mapping
    # populated by build_deck) so each *ELEMENT block emits one elset
    # at a time. Each spring element appears in exactly one elset.
    if deck.spring_elements:
        spring_eid_to_elset: dict = {}
        for es in deck.element_sets:
            for eid in es.element_ids:
                spring_eid_to_elset[eid] = es.name
        by_elset: dict = {}
        for se in deck.spring_elements:
            es_name = spring_eid_to_elset.get(se.eid)
            if es_name is None:
                buf.append(f"** orphan spring element {se.eid}")
                continue
            by_elset.setdefault(es_name, []).append(se)
        for es_name, spring_list in by_elset.items():
            buf.append(f"*ELEMENT, TYPE=SPRING2, ELSET={es_name}")
            for se in spring_list:
                buf.append(f"{se.eid:8d}, {se.n1:8d}, {se.n2:8d}")

    # ── materials ──────────────────────────────────────────────────────
    for m in deck.materials:
        _write_material(buf, m)

    # ── spring sections — bind stiffness to spring elsets ──────────────
    for sec in deck.spring_sections:
        if sec.note:
            buf.append(f"** {sec.note}")
        buf.append(f"*SPRING, ELSET={sec.elset_name}")
        buf.append(f"{sec.dof_n1}, {sec.dof_n2}")
        buf.append(f"{sec.stiffness_n_per_m: .6e}")

    # ── solid sections binding elset → material ────────────────────────
    # Spring-element elsets carry material_name="" — those are bound by
    # *SPRING cards elsewhere, not *SOLID SECTION.
    for es in deck.element_sets:
        if not es.material_name:
            continue
        if es.note:
            buf.append(f"** {es.note}")
        buf.append(f"*SOLID SECTION, ELSET={es.name}, "
                   f"MATERIAL={es.material_name}")

    # ── surfaces ────────────────────────────────────────────────────────
    # CCX supports two surface kinds: TYPE=NODE (node set, slave-only in
    # *TIE) and TYPE=ELEMENT (element faces, master in *TIE / target of
    # *DSLOAD). Build_deck picks the right kind per surface.
    for s in deck.surfaces:
        if s.kind == "node":
            buf.append(f"*SURFACE, NAME={s.name}, TYPE=NODE")
            buf.append(f"{s.nset_name}")
        elif s.kind == "element":
            buf.append(f"*SURFACE, NAME={s.name}, TYPE=ELEMENT")
            for elset, face_id in s.element_faces:
                buf.append(f"{elset}, {face_id}")
        else:
            raise ValueError(
                f"CCXSurface {s.name!r}: kind={s.kind!r} not in "
                f"{{'node', 'element'}}"
            )

    # ── *TIE constraints ────────────────────────────────────────────────
    # The slave surface follows the master. Use the "ADJUST=NO" option to
    # keep CCX from snapping slave nodes to the master surface — our
    # node positions are already physically correct.
    for t in deck.ties:
        buf.append(f"*TIE, NAME={t.name}, ADJUST=NO")
        buf.append(f"{t.slave_surface}, {t.master_surface}")

    # ── boundary conditions (initial step) ─────────────────────────────
    if deck.boundaries:
        buf.append("*BOUNDARY")
        for bc in deck.boundaries:
            buf.append(f"{bc.nset_name}, {bc.dof_first}, {bc.dof_last}, "
                       f"{bc.value: .6e}")

    # ── amplitudes (time-resolved load scaling for dynamic steps) ──────
    for amp in deck.amplitudes:
        smooth_tag = ", SMOOTH=0.05" if amp.smooth else ""
        buf.append(f"*AMPLITUDE, NAME={amp.name}{smooth_tag}")
        # CCX accepts up to 4 (t, v) pairs per line — use one pair per
        # line for readability and to support large tables cleanly.
        for t, v in amp.time_value_pairs:
            buf.append(f"{t: .9e}, {v: .9e}")

    # ── steps ──────────────────────────────────────────────────────────
    for step in deck.steps:
        _write_step(buf, step)

    out.write_text("\n".join(buf) + "\n", encoding="utf-8")
    return str(out)


def _chunked(seq, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
