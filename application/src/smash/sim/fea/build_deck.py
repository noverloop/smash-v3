"""Compose a CCXDeck from a BoardMesh + Board + BodyLoadProfile + FabProfile.

This is the seam between smash's design model and the CalculiX deck the
solver consumes:

  - The MESH (smash.sim.fea.mesh) carries pure geometry — nodes,
    elements, element-set tags ("BOARD_BULK", "CU_COIN", "CHIP_<ref>"),
    node-set tags ("SUPPORT_RING_TOP"...). No materials, no BCs, no
    loads.
  - The DECK (smash.sim.fea.ccx_writer) is format-pure — it serialises a
    populated CCXDeck to CCX .inp text. No design awareness.

`build_deck` bridges these by:

  1. Looking up the FabProfile's Laminate / CopperFoil / Solder /
     Adhesive entries and turning them into CCXMaterial cards bound to
     the right element sets;
  2. Reading the BodyLoadProfile and materialising a time-resolved DLOAD
     (or, for a static analysis, the peak acceleration);
  3. Pinning the SUPPORT_RING node set with a Dirichlet BC (the
     snake-stack spacers above and below clamp the tile at its outer
     ring).

A static run uses the profile's peak acceleration. A transient run
uses one *DYNAMIC EXPLICIT step with an *AMPLITUDE table sampled from
the same profile.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np

from smash.state import Board
from smash.state.geometry3d import board_solder
from smash.sim.fea.ccx_writer import (
    CCXAmplitude, CCXBoundary, CCXBodyLoad, CCXCentrifugalLoad,
    CCXDeck, CCXElementSet,
    CCXMaterial, CCXStep, CCXSurface, CCXTie,
    CCXSpringElement, CCXSpringSection,
    ELEMENT_TYPE_LINEAR_HEX,
)
from smash.sim.fea.mesh import BoardMesh


# Standard gravity. Peak acceleration is reported in units of this.
_G = 9.80665


@dataclasses.dataclass
class BodyLoadProfile:
    """Acceleration and spin history applied as a body force.

    Arrays are shape (N,) and share the time base `t_s`.
    """
    name: str
    t_s: np.ndarray
    a_m_per_s2: np.ndarray
    omega_rad_per_s: np.ndarray
    muzzle_velocity_m_per_s: float | None = None

    @property
    def peak_g(self) -> float:
        if len(self.a_m_per_s2) == 0:
            return 0.0
        return float(np.max(self.a_m_per_s2) / _G)

    @property
    def muzzle_spin_rad_per_s(self) -> float:
        if len(self.omega_rad_per_s) == 0:
            return 0.0
        return float(self.omega_rad_per_s[-1])

    @property
    def muzzle_spin_rpm(self) -> float:
        return self.muzzle_spin_rad_per_s * 60.0 / (2.0 * math.pi)

    @property
    def duration_s(self) -> float:
        if len(self.t_s) == 0:
            return 0.0
        return float(self.t_s[-1])


# ── material lookup helpers ────────────────────────────────────────────


def _laminate_constants(fab, material: str = "FR4") -> tuple:
    """Return (E_Pa, ν, ρ_kg/m³) from the FabProfile's laminate catalog
    for the named material. Falls back to canonical FR-4 defaults when
    the catalog doesn't quote a value (older profiles)."""
    if fab is not None:
        for lam in fab.laminates:
            if lam.material == material:
                E = (lam.youngs_modulus_gpa or 20.0) * 1e9
                nu = lam.poisson_ratio or 0.30
                rho = lam.density_kg_m3 or 1850.0
                return E, nu, rho
    # FR-4 canonical defaults
    return 20e9, 0.30, 1850.0


def _copper_constants(fab) -> tuple:
    """Bulk Cu E, ν, ρ from the FabProfile foil catalog (any foil's
    populated mechanical constants — the alloy is the same)."""
    if fab is not None:
        for foil in fab.foils:
            if foil.youngs_modulus_gpa:
                return (foil.youngs_modulus_gpa * 1e9,
                        foil.poisson_ratio or 0.34,
                        foil.density_kg_m3 or 8960.0)
    # Bulk Cu fallbacks.
    return 117e9, 0.34, 8960.0


def _rogers_constants() -> tuple:
    """Rogers RO4350B canonical mechanical constants — substrate density
    and modulus are flagged on the datasheet but the FabProfile rarely
    carries the mechanical fields (it cares about ε_r / tan δ).
    Conservative midrange numbers."""
    return 9e9, 0.35, 1860.0


def _chip_body_constants() -> tuple:
    """Generic IC body — epoxy mould compound + Si die averaged. E ≈
    20 GPa is a reasonable composite; ρ keyed to the chip's `weight_g`
    over its volume in the calling code."""
    return 20e9, 0.30, 1900.0


def _al_backing_constants(fab) -> tuple:
    """Return (E_Pa, ν, ρ_kg/m³) for Al 6061-T6 from the FabProfile
    metal_options catalog. Falls back to canonical Al 6061 constants
    when the catalog doesn't carry them."""
    if fab is not None:
        for m in fab.metal_options:
            if m.material == "aluminium" and m.role == "backing":
                E = (m.youngs_modulus_gpa or 70.0) * 1e9
                nu = m.poisson_ratio or 0.33
                rho = float(m.density_kg_m3 or 2700.0)
                return E, nu, rho
    return 70e9, 0.33, 2700.0


def _adhesive_constants(fab, name: str) -> tuple | None:
    """Pull (E_Pa, ν, ρ_kg/m³) for a named `Adhesive` from the
    FabProfile catalog. Returns None if the adhesive isn't in the
    catalog or doesn't carry the mechanical fields. Density is
    converted g/cm³ → kg/m³ (catalog stores g/cm³)."""
    if fab is None:
        return None
    ad = fab.adhesive(name)
    if ad is None or ad.youngs_modulus_gpa is None:
        return None
    nu = ad.poisson_ratio if ad.poisson_ratio is not None else 0.30
    rho = (ad.density_g_cm3 or 1.5) * 1000.0     # g/cm³ → kg/m³
    return ad.youngs_modulus_gpa * 1e9, nu, rho


# ── deck assembly ──────────────────────────────────────────────────────


@dataclasses.dataclass
class DeckBuildOptions:
    """Tuning knobs for `build_static_deck`. Defaults cover the
    first-iteration sanity check; the transient builder takes different
    options."""
    job_name: str | None = None
    body_force_direction: tuple = (0.0, 0.0, -1.0)  # forward setback default
    # Explicit setback direction tag — flips the body force when set to
    # "reverse" and adjusts the job/step name so the same (board, platform)
    # pair produces distinct forward + reverse artifacts. Overrides
    # body_force_direction when not None.
    #
    #   "forward"  → body force -Z (chip pushed INTO the board; SAC305
    #                joints in compression / shear; bend-sim's forward_setback
    #                path).
    #   "reverse"  → body force +Z (chip pulled AWAY from the board;
    #                solder balls in TENSION; bend-sim's reverse_setback
    #                path. The report module compares σ_tension at pad
    #                nodes against Solder.tensile_strength_mpa).
    setback_direction: str | None = None
    # Load mode controls the body-force card type:
    #   "setback" (default) → *DLOAD GRAV with peak G in the setback
    #                          direction. Driven by profile.peak_g.
    #   "spin"              → *DLOAD CENTRIF with ω² at muzzle spin
    #                          about the board's z-axis (the spin axis
    #                          of the snake stack). Driven by
    #                          profile.muzzle_spin_rad_per_s. Smooth-
    #                          bore platforms (mortar, ω=0) skip the
    #                          run with a no-op load (build returns a
    #                          deck with no step body load).
    load_mode: str = "setback"
    pin_support_top: bool = True
    pin_support_bottom: bool = True
    # Material name overrides — pass to bypass the catalog lookup.
    laminate_material: str = "FR4"
    # --- transient explicit dynamic options (Phase J) ---
    # When `dynamic` is True, the step becomes *DYNAMIC, EXPLICIT with
    # the full BodyLoadProfile a(t)/a_peak ratio as a *AMPLITUDE table.
    # The setback load magnitude is set to peak_a; for spin, magnitude
    # = peak ω² and amplitude = (ω(t)/ω_muzzle)².
    dynamic: bool = False
    # Number of amplitude (t, v) pairs to emit (downsampled from the
    # profile's ~10⁴ µs-resolved points to keep the .inp readable).
    dynamic_amplitude_n_pairs: int = 200
    # Output throttle for the *NODE FILE / *EL FILE cards. Total step
    # count divided by this is the result-block count in .frd. Default
    # ~50 result blocks per dynamic run keeps .frd parseable.
    dynamic_output_n_blocks: int = 50
    # Optionally truncate the dynamic step's duration (defaults to the
    # full BodyLoadProfile.duration_s). Useful when only the rising
    # portion of the pulse is interesting — the structure has decayed
    # back to near-rest after ~2-3× the rise time and the trailing
    # explicit-dynamic steps just burn compute without adding signal.
    dynamic_t_total_override_s: float | None = None


def build_static_deck(mesh: BoardMesh, board: Board,
                      profile: BodyLoadProfile, *,
                      fab=None,
                      options: DeckBuildOptions | None = None) -> CCXDeck:
    """Compose a CCXDeck for a STATIC analysis at the profile's
    PEAK acceleration. First-iteration sanity check — matches the
    analytic bend-sim's worst-row stress envelope.

    Materials: pulled from the FabProfile catalog (laminate, copper
    foil, soldermask, encapsulant) so the FEA sees the same constants
    the bend / thermal sims already use. The transient builder
    (`build_dynamic_deck` — next increment) reuses this material setup.
    """
    opts = options or DeckBuildOptions()
    # Resolve effective body-force direction. setback_direction takes
    # precedence over body_force_direction for the common forward/
    # reverse case; raw tuple still wins if direction is None.
    direction_label = (opts.setback_direction or "").strip().lower() or None
    if direction_label == "forward":
        eff_direction = (0.0, 0.0, -1.0)
    elif direction_label == "reverse":
        eff_direction = (0.0, 0.0, +1.0)
    elif direction_label is None:
        eff_direction = opts.body_force_direction
    else:
        raise ValueError(
            f"DeckBuildOptions.setback_direction must be 'forward', "
            f"'reverse' or None — got {opts.setback_direction!r}"
        )
    if opts.load_mode == "spin":
        suffix = "_spin"
    elif direction_label:
        suffix = f"_{direction_label}"
    else:
        suffix = ""
    job = opts.job_name or (
        f"{board.name}_"
        f"{profile.name.replace(' ', '_').replace('/', '-')}"
        f"{suffix}"
    )

    # ── nodes (already in metres in the mesh) ───────────────────────
    nodes = list(mesh.node_coords)

    # ── elements ────────────────────────────────────────────────────
    elements = [(e.eid, ELEMENT_TYPE_LINEAR_HEX, e.nodes) for e in mesh.elements]

    # ── materials from the FabProfile catalog ───────────────────────
    E_fr4, nu_fr4, rho_fr4 = _laminate_constants(fab, opts.laminate_material)
    E_cu,  nu_cu,  rho_cu  = _copper_constants(fab)

    materials = [
        CCXMaterial(
            name="LAMINATE_FR4",
            youngs_modulus_pa=E_fr4, poisson_ratio=nu_fr4,
            density_kg_m3=rho_fr4,
            note=f"laminate {opts.laminate_material}, from FabProfile",
        ),
        CCXMaterial(
            name="COPPER",
            youngs_modulus_pa=E_cu, poisson_ratio=nu_cu,
            density_kg_m3=rho_cu,
            note="Cu coin + thin foil layers (bulk Cu)",
        ),
    ]
    # Radar tile uses Rogers RO4350B as the top dielectric — emit the
    # additional material only when relevant. (The mesh consolidates
    # top dielectric + F.Cu into the same element layer; we use the
    # composite Rogers constants since the dielectric dominates the
    # thickness.)
    has_rogers = (getattr(board, "top_substrate", "fr4")
                  == "rogers_ro4350b_5mil")
    if has_rogers:
        E_rog, nu_rog, rho_rog = _rogers_constants()
        materials.append(CCXMaterial(
            name="ROGERS_RO4350B",
            youngs_modulus_pa=E_rog, poisson_ratio=nu_rog,
            density_kg_m3=rho_rog,
            note="top dielectric on radar_module",
        ))

    # ── element sets bound to materials ─────────────────────────────
    element_sets = []
    if mesh.element_sets.get("BOARD_BULK"):
        element_sets.append(CCXElementSet(
            name="BOARD_BULK",
            element_ids=mesh.element_sets["BOARD_BULK"],
            material_name="LAMINATE_FR4",
            note="FR-4 core elements outside any Cu coin region",
        ))
    if mesh.element_sets.get("CU_COIN"):
        element_sets.append(CCXElementSet(
            name="CU_COIN",
            element_ids=mesh.element_sets["CU_COIN"],
            material_name="COPPER",
            note="Cu coin — bulk Cu replaces FR-4 in this region",
        ))
    if mesh.element_sets.get("BCU_SUBSTRATE"):
        element_sets.append(CCXElementSet(
            name="BCU_SUBSTRATE",
            element_ids=mesh.element_sets["BCU_SUBSTRATE"],
            material_name="LAMINATE_FR4",
            note="B.Cu + adjacent dielectric (Cu lumped into laminate)",
        ))
    if mesh.element_sets.get("FCU_SUBSTRATE"):
        element_sets.append(CCXElementSet(
            name="FCU_SUBSTRATE",
            element_ids=mesh.element_sets["FCU_SUBSTRATE"],
            material_name="ROGERS_RO4350B" if has_rogers else "LAMINATE_FR4",
            note=("F.Cu + top dielectric (Rogers on radar, FR-4 elsewhere)"
                  if has_rogers else
                  "F.Cu + top dielectric"),
        ))
    # Chip body blocks — generic IC body material per chip set.
    chip_set_names = sorted(n for n in mesh.element_sets
                             if n.startswith("CHIP_"))
    if chip_set_names:
        E_chip, nu_chip, rho_chip = _chip_body_constants()
        materials.append(CCXMaterial(
            name="CHIP_BODY",
            youngs_modulus_pa=E_chip, poisson_ratio=nu_chip,
            density_kg_m3=rho_chip,
            note="generic IC epoxy + Si die composite",
        ))
        for cs in chip_set_names:
            element_sets.append(CCXElementSet(
                name=cs,
                element_ids=mesh.element_sets[cs],
                material_name="CHIP_BODY",
                note=f"chip body block for {cs[5:]}",
            ))

    # Al 6061-T6 backing — only present when Board.al_backing_mm > 0
    # (camera_module today). Bonded to B.Cu via shared nodes in the
    # mesh; the spacer below now rests on the Al's bottom face.
    if mesh.element_sets.get("AL_BACKING"):
        E_al, nu_al, rho_al = _al_backing_constants(fab)
        materials.append(CCXMaterial(
            name="ALUMINIUM_6061T6",
            youngs_modulus_pa=E_al, poisson_ratio=nu_al,
            density_kg_m3=rho_al,
            note="Al 6061-T6 backing plate (thermal spreader + stiffener)",
        ))
        element_sets.append(CCXElementSet(
            name="AL_BACKING",
            element_ids=mesh.element_sets["AL_BACKING"],
            material_name="ALUMINIUM_6061T6",
            note="Al backing layer bonded under B.Cu",
        ))

    # Stycast 2651MM CAT 23LV encapsulant — board-wide fill above F.Cu.
    # Mesh emits a single STYCAST_FILL element set whose bottom-face
    # nodes coincide with F.Cu top-face nodes (shared-node bonding,
    # no *TIE needed at the F.Cu interface).
    stycast_name = "Stycast 2651MM CAT 23LV"
    if mesh.element_sets.get("STYCAST_FILL"):
        consts = _adhesive_constants(fab, stycast_name)
        if consts is None:
            raise ValueError(
                f"FabProfile.adhesives has no {stycast_name!r} with "
                f"mechanical constants populated — required for "
                f"Stycast potting"
            )
        E, nu, rho = consts
        materials.append(CCXMaterial(
            name="STYCAST_2651MM",
            youngs_modulus_pa=E, poisson_ratio=nu,
            density_kg_m3=rho,
            note=f"encapsulant {stycast_name} (from FabProfile.adhesives)",
        ))
        element_sets.append(CCXElementSet(
            name="STYCAST_FILL",
            element_ids=mesh.element_sets["STYCAST_FILL"],
            material_name="STYCAST_2651MM",
            note="vacuum potting fill above F.Cu, around chip bodies",
        ))

    # Per-chip underfill (Eccobond UF1173 etc.) — pulled from each
    # chip's `chip.underfill` attribute via the FabProfile.adhesives
    # catalog. We bucket UF_<ref> element sets by the distinct underfill
    # names referenced so each unique material only gets one *MATERIAL
    # card (typically all chips use the same UF1173, but the code
    # handles mixed-underfill assemblies correctly).
    uf_set_names = sorted(n for n in mesh.element_sets
                          if n.startswith("UF_"))
    uf_by_chip_ref = {c.ref: c.underfill for pl in board.chip_placements
                      for c in [pl.item]
                      if hasattr(c, "underfill") and c.underfill}
    uf_materials_added: set = set()
    for uf_set in uf_set_names:
        chip_ref = uf_set[3:]                                # strip "UF_"
        uf_name = uf_by_chip_ref.get(chip_ref)
        if not uf_name:
            continue
        mat_name = ("UF_" + uf_name.replace(" ", "_")
                    .replace("/", "_").upper())
        if uf_name not in uf_materials_added:
            consts = _adhesive_constants(fab, uf_name)
            if consts is None:
                raise ValueError(
                    f"FabProfile.adhesives has no {uf_name!r} or it "
                    f"lacks mechanical constants — populate "
                    f"youngs_modulus_gpa / poisson_ratio / density_g_cm3"
                )
            E, nu, rho = consts
            materials.append(CCXMaterial(
                name=mat_name,
                youngs_modulus_pa=E, poisson_ratio=nu,
                density_kg_m3=rho,
                note=f"underfill {uf_name} (from FabProfile.adhesives)",
            ))
            uf_materials_added.add(uf_name)
        element_sets.append(CCXElementSet(
            name=uf_set,
            element_ids=mesh.element_sets[uf_set],
            material_name=mat_name,
            note=f"underfill brick under chip {chip_ref}",
        ))

    # *TIE constraints — master surfaces in CCX must be element-face
    # based; slaves can be TYPE=NODE. We have two master surfaces:
    #   FCU_TOP        — +Z face (S2) of every FCU_SUBSTRATE element.
    #                     Chip-or-UF column BOTTOM nodes attach here.
    #   STYCAST_FACES — all 6 faces of every STYCAST_FILL element.
    #                     Chip TOP nodes attach here (CCX projects each
    #                     slave node onto the nearest master face, so
    #                     a chip-top node lands on the Stycast cell
    #                     directly above it). This is what captures the
    #                     bend-sim's encapsulant shear-relief in 3D.
    surfaces = []
    ties = []
    fcu_master = "S_FCU_TOP"
    stycast_master = "S_STYCAST_FILL_FACES"
    have_fcu = bool(mesh.element_sets.get("FCU_SUBSTRATE"))
    have_stycast = bool(mesh.element_sets.get("STYCAST_FILL"))
    if any(t.master_nset == "FCU_TOP" for t in mesh.ties) and have_fcu:
        surfaces.append(CCXSurface(
            name=fcu_master,
            kind="element",
            element_faces=[("FCU_SUBSTRATE", "S2")],
        ))
    if any(t.master_nset == "STYCAST_FILL_FACES"
           for t in mesh.ties) and have_stycast:
        # All 6 face IDs of every STYCAST_FILL element — CCX picks the
        # closest face per slave node.
        surfaces.append(CCXSurface(
            name=stycast_master,
            kind="element",
            element_faces=[
                ("STYCAST_FILL", f"S{i}") for i in (1, 2, 3, 4, 5, 6)
            ],
        ))

    # Map mesh's logical master-nset names to the actual CCX surface
    # names we just emitted (mesh.ties uses logical labels; the deck
    # has to convert them to the element-face surface names).
    master_lookup = {
        "FCU_TOP":             fcu_master,
        "STYCAST_FILL_FACES":  stycast_master,
    }
    for t in mesh.ties:
        master_name = master_lookup.get(t.master_nset)
        if master_name is None:
            continue
        # Skip ties whose master isn't actually present in this mesh
        # (e.g. chip-top → Stycast when potting is disabled).
        if master_name not in {s.name for s in surfaces}:
            continue
        slave_name = f"S_{t.slave_nset}"
        surfaces.append(CCXSurface(
            name=slave_name, kind="node",
            nset_name=t.slave_nset,
        ))
        ties.append(CCXTie(
            name=t.name,
            slave_surface=slave_name,
            master_surface=master_name,
        ))

    # ── boundary conditions: snake-stack support ring ──────────────
    boundaries = []
    if opts.pin_support_bottom and "SUPPORT_RING_BOT" in mesh.node_sets \
            and mesh.node_sets["SUPPORT_RING_BOT"]:
        # Bottom ring pinned in all 3 translations (the spacer below the
        # tile prevents radial / axial motion at the ring contact).
        boundaries.append(CCXBoundary(
            nset_name="SUPPORT_RING_BOT", dof_first=1, dof_last=3,
        ))
    if opts.pin_support_top and "SUPPORT_RING_TOP" in mesh.node_sets \
            and mesh.node_sets["SUPPORT_RING_TOP"]:
        # Top ring: only Z is pinned (the spacer above keeps the tile
        # from lifting in setback but allows radial breathing). Pinning
        # all 3 DOFs over-constrains the plate; let the bend live in xy.
        boundaries.append(CCXBoundary(
            nset_name="SUPPORT_RING_TOP", dof_first=3, dof_last=3,
        ))

    # ── load step: STATIC at the profile's peak acceleration ─
    body_loads = []
    centrifugal_loads = []
    note_lines: list = []

    if opts.load_mode == "setback":
        peak_a = float(profile.a_m_per_s2.max())
        dx, dy, dz = eff_direction
        for es in element_sets:
            if not es.material_name:    # spring elsets carry no body load
                continue
            body_loads.append(CCXBodyLoad(
                elset_name=es.name,
                magnitude_m_per_s2=peak_a,
                direction=(dx, dy, dz),
            ))
        step_name = (f"static_{direction_label}_{profile.peak_g:.0f}g"
                     if direction_label
                     else f"static_peak_{profile.peak_g:.0f}g")
        note_lines = [
            f"Static FEA at peak acceleration of {profile.name}"
            + (f" — {direction_label.upper()} setback" if direction_label else ""),
            f"  peak a = {peak_a:.3e} m/s² ({profile.peak_g:.0f} G)",
            f"  body force direction = ({dx}, {dy}, {dz})",
            f"  v = {profile.muzzle_velocity_m_per_s} m/s",
            f"  ω = {profile.muzzle_spin_rpm:.0f} RPM",
        ]
    elif opts.load_mode == "spin":
        omega_sq = profile.muzzle_spin_rad_per_s ** 2
        # Spin axis: Z through the board's xy origin (snake stack's
        # spin axis). Centrifugal force scales with r = √(x² + y²)
        # per element, applied radially outward.
        for es in element_sets:
            if not es.material_name:
                continue
            centrifugal_loads.append(CCXCentrifugalLoad(
                elset_name=es.name,
                omega_squared_rad2_per_s2=omega_sq,
            ))
        step_name = (
            f"static_spin_{profile.muzzle_spin_rpm:.0f}rpm"
            if omega_sq > 0 else "static_spin_zero"
        )
        note_lines = [
            f"Static FEA at spin of {profile.name}",
            f"  ω = {profile.muzzle_spin_rad_per_s:.0f} rad/s "
            f"({profile.muzzle_spin_rpm:.0f} RPM)",
            f"  ω² = {omega_sq:.3e} (rad/s)²",
            f"  spin axis = Z through board origin (snake stack axis)",
        ]
        if omega_sq == 0:
            note_lines.append(
                "  zero spin — centrifugal load is zero (deck included "
                "for sweep completeness)"
            )
    else:
        raise ValueError(
            f"DeckBuildOptions.load_mode must be 'setback' or 'spin' "
            f"— got {opts.load_mode!r}"
        )

    amplitudes: list = []
    if opts.dynamic:
        amp = _build_load_amplitude(
            profile, opts.dynamic_amplitude_n_pairs,
            mode=opts.load_mode,
        )
        amplitudes.append(amp)
        # Attach the amplitude to every body load / centrifugal load
        # so each one is scaled by amp(t) during the dynamic solve.
        for bl in body_loads:
            bl.amplitude_name = amp.name
        for cl in centrifugal_loads:
            cl.amplitude_name = amp.name
        # Total time = profile duration, or an explicit override
        # (typically used to trim to the rising portion of the pulse
        # so we don't spend compute on the decay).
        t_total = (opts.dynamic_t_total_override_s
                   if opts.dynamic_t_total_override_s
                   else profile.duration_s)
        dt0 = _critical_dt_explicit_s(mesh, fab)
        n_steps_total = max(1, int(round(t_total / dt0)))
        out_freq = max(1, n_steps_total // max(1, opts.dynamic_output_n_blocks))
        step = CCXStep(
            name=f"dynamic_{step_name.replace('static_', '')}",
            body_loads=body_loads,
            centrifugal_loads=centrifugal_loads,
            static=False,
            dynamic_t_total_s=t_total,
            dynamic_t_initial_s=dt0,
            output_frequency=out_freq,
        )
        note_lines.append(
            f"  DYNAMIC: Δt_initial = {dt0:.3e} s ({n_steps_total} steps), "
            f"output every {out_freq} steps ({n_steps_total // out_freq + 1} "
            f"FRD blocks)"
        )
    else:
        step = CCXStep(
            name=step_name,
            body_loads=body_loads,
            centrifugal_loads=centrifugal_loads,
            static=True,
        )

    # ── Phase G — cohesive zone springs at solder pads ──────────────
    # For each chip's SpringPairSpec list, emit 3 *SPRING2 elements
    # (X, Y, Z DOFs) per pad node × 4 corner pads = 12 springs per
    # chip. Per-direction stiffness is calibrated from the SAC305
    # solder modulus + the chip's joint geometry:
    #
    #   k_shear  = G_solder · A_pads / h_joint   (X, Y directions)
    #   k_normal = E_solder · A_pads / h_joint   (Z direction)
    #
    # Total k is split across the 4 corner springs so the per-spring
    # stiffness is k/4.
    spring_elements, spring_sections, spring_elsets = _emit_solder_springs(
        mesh, board, fab,
        next_eid_start=(max((eid for (eid, _, _) in elements),
                              default=0) + 1),
    )
    # Wire spring elsets into the deck (the writer needs the elset
    # binding so it can look up which spring elements belong to which
    # *SPRING card). Spring elsets don't carry a material — the
    # *SPRING card itself binds the stiffness.
    for elset_name, eids in spring_elsets.items():
        element_sets.append(CCXElementSet(
            name=elset_name, element_ids=eids,
            material_name="",
            note="solder-joint spring (Phase G cohesive zone)",
        ))

    return CCXDeck(
        job_name=job,
        node_coords=nodes,
        elements=elements,
        element_sets=element_sets,
        node_sets={k: v for k, v in mesh.node_sets.items() if v},
        materials=materials,
        boundaries=boundaries,
        steps=[step],
        surfaces=surfaces,
        ties=ties,
        spring_elements=spring_elements,
        spring_sections=spring_sections,
        amplitudes=amplitudes,
        note="\n".join(note_lines),
    )


def _critical_dt_explicit_s(mesh, fab) -> float:
    """Conservative explicit-dynamic critical time step. CCX uses
    central-difference time integration, conditionally stable with
    Δt_cr ≈ L_min / c_max where L_min is the smallest element edge
    and c_max the maximum wave speed in the mesh. For our hex grid:

      L_min ≈ min(thinnest stackup layer Cu/dielectric, xy_element_mm)
              clamped to xy_element so it's the IN-PLANE element size
              (a 17 µm Cu foil with 1 mm xy gives a degenerate aspect
              ratio and a 5 ns critical step — too small. We use the
              element minimum edge LENGTH in metres).
      c_max ≈ √(E_max / ρ_min) with Cu at the top end (~3500 m/s) and
              Stycast at the bottom (~1800 m/s); the bound uses Cu.

    Returns Δt_cr · safety where safety = 0.85 (CCX default).
    """
    # Find smallest element edge by walking element node coordinates.
    coord_by_id = {nid: (xm, ym, zm) for (nid, xm, ym, zm)
                    in mesh.node_coords}
    edge_min_m = float("inf")
    for e in mesh.elements:
        ns = e.nodes
        if len(ns) != 8:
            continue
        # Sample 4 of the 12 hex edges (sufficient for L_min estimate).
        for (i, j) in ((0, 1), (1, 2), (4, 5), (0, 4)):
            c1 = coord_by_id.get(ns[i])
            c2 = coord_by_id.get(ns[j])
            if c1 is None or c2 is None:
                continue
            dx = c2[0] - c1[0]
            dy = c2[1] - c1[1]
            dz = c2[2] - c1[2]
            d = (dx * dx + dy * dy + dz * dz) ** 0.5
            if 0 < d < edge_min_m:
                edge_min_m = d
    if edge_min_m == float("inf") or edge_min_m == 0:
        edge_min_m = 1e-3                        # 1 mm fallback

    # Cu wave speed = √(E/ρ) ≈ √(117e9 / 8960) ≈ 3614 m/s. Use this
    # as the upper bound across our material zoo (FR4 ~3290, Stycast
    # ~1620, chip body ~3240) — Cu dominates the stiffness.
    c_max = 3700.0
    safety = 0.85
    return safety * edge_min_m / c_max


def _build_load_amplitude(profile, n_pairs: int,
                            *, mode: str) -> CCXAmplitude:
    """Downsample profile.t_s + a(t)/a_peak (setback) or
    (ω(t)/ω_peak)² (spin) into n_pairs (t, scale) points. The
    *AMPLITUDE table multiplies the step's peak magnitude during
    the dynamic solve."""
    n = len(profile.t_s)
    if n == 0:
        raise ValueError("BodyLoadProfile is empty")
    if mode == "setback":
        peak = float(profile.a_m_per_s2.max())
        scale = profile.a_m_per_s2 / peak if peak > 0 else \
            np.zeros_like(profile.a_m_per_s2)
        amp_name = "PROFILE_A_OVER_PEAK"
    elif mode == "spin":
        peak_omega = float(profile.omega_rad_per_s.max())
        if peak_omega > 0:
            # ω² scaling — centrifugal force scales as ω².
            scale = (profile.omega_rad_per_s / peak_omega) ** 2
        else:
            scale = np.zeros_like(profile.omega_rad_per_s)
        amp_name = "PROFILE_OMEGA_SQ_OVER_PEAK"
    else:
        raise ValueError(f"unknown load mode {mode!r}")

    # Downsample uniformly so the table has at most n_pairs rows.
    if n <= n_pairs:
        idx = list(range(n))
    else:
        idx = list(np.linspace(0, n - 1, n_pairs).astype(int))
    pairs = [(float(profile.t_s[i]), float(scale[i])) for i in idx]
    # Ensure the table starts at t=0 with scale=0 (so the dynamic
    # solve has zero load at t=0) and ends at the integration's t_max.
    if pairs[0][0] > 0:
        pairs.insert(0, (0.0, 0.0))
    return CCXAmplitude(name=amp_name, time_value_pairs=pairs,
                         smooth=False)


def _solder_constants(fab):
    """Bulk SAC305 E + G + ν from the FabProfile.solders default
    (the same alloy the bend-sim's reverse-setback path uses).
    Returns (E_Pa, G_Pa, ν)."""
    if fab is None:
        return 41e9, 14.6e9, 0.40                # SAC305 fallback
    s = fab.default_solder
    if s is None or s.youngs_modulus_gpa is None:
        return 41e9, 14.6e9, 0.40
    E = s.youngs_modulus_gpa * 1e9
    nu = s.poisson_ratio or 0.40
    G = E / (2.0 * (1.0 + nu))
    return E, G, nu


def _emit_solder_springs(mesh: BoardMesh, board, fab,
                          *, next_eid_start: int
                          ) -> tuple[list, list, dict]:
    """Build *SPRING2 elements + *SPRING sections + elset map for the
    chip-pad cohesive zone.

    Returns:
      spring_elements:    list[CCXSpringElement]
      spring_sections:    list[CCXSpringSection]
      elset_to_eids:      {elset_name: [eid, ...]}

    Per-chip elset naming:  SOLDER_<ref>_X, SOLDER_<ref>_Y, SOLDER_<ref>_Z.
    Each elset contains 4 spring elements (one per corner pad).
    """
    E_solder, G_solder, _nu = _solder_constants(fab)

    spring_elements: list = []
    spring_sections: list = []
    elset_to_eids: dict = {}
    next_eid = next_eid_start

    # Group SpringPairSpecs by chip_ref so we can derive total joint
    # area + per-spring stiffness once per chip.
    by_chip: dict = {}
    for sp in mesh.spring_pairs:
        by_chip.setdefault(sp.chip_ref, []).append(sp)

    for ref, pairs in by_chip.items():
        if not pairs:
            continue
        sample = pairs[0]
        # Joint contact area in m².
        a_pads_m2 = max(sample.a_pad_total_mm2, 0.01) * 1e-6
        h_joint_m = max(sample.h_joint_mm, 0.025) * 1e-3
        # Total chip joint stiffness (across ALL pads). Split over
        # the 4 corner springs so per-corner is k_total / 4.
        k_shear_total = G_solder * a_pads_m2 / h_joint_m
        k_normal_total = E_solder * a_pads_m2 / h_joint_m
        k_shear = max(1.0, k_shear_total / max(1, len(pairs)))
        k_normal = max(1.0, k_normal_total / max(1, len(pairs)))

        for dof, kval, axis_name in (
                (1, k_shear, "X"),
                (2, k_shear, "Y"),
                (3, k_normal, "Z"),
        ):
            elset_name = f"SOLDER_{ref}_{axis_name}"
            elset_to_eids[elset_name] = []
            for sp in pairs:
                spring_elements.append(CCXSpringElement(
                    eid=next_eid, n1=sp.pad_node, n2=sp.fcu_node,
                    dof_n1=dof, dof_n2=dof,
                ))
                elset_to_eids[elset_name].append(next_eid)
                next_eid += 1
            spring_sections.append(CCXSpringSection(
                elset_name=elset_name,
                dof_n1=dof, dof_n2=dof,
                stiffness_n_per_m=kval,
                note=(f"SOLDER spring {ref}/{axis_name} — "
                      f"chip {sample.family or '?'}, "
                      f"A_pads={sample.a_pad_total_mm2:.3f} mm², "
                      f"h_joint={sample.h_joint_mm:.3f} mm"),
            ))
    return spring_elements, spring_sections, elset_to_eids
